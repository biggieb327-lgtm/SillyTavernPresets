#!/usr/bin/env python3
"""Check that an instance's atlas.txt names places that exist, near where she lives.

Why this exists: `atlas.txt` is injected into every prompt as "Real spots {NAME} knows"
and is drawn from for selfie backgrounds, but nothing has ever checked that those places
are real or that they are anywhere near her. A fabricated cafe and a real one forty miles
away read identically in the file and identically in her voice — the defect only surfaces
when a human who knows the city happens to read a reply. Same shape as the reference-photo
gap closed in v2026-08-09.1: a property of the content layer no check could see, because
nothing ever looked.

    python3 tools/atlas_audit.py priya --near "Bellevue, WA"
    python3 tools/atlas_audit.py nora  --near "Olympia, WA" --radius 12

On the VPS use the fleet venv — system python has none of bot.py's dependencies, which this
imports (absolute paths, so it runs from any directory):

    /opt/telegram-bots/venv/bin/python3 \
      /opt/telegram-bots/.repo/telegram-companion-bot/tools/atlas_audit.py priya --near "Seattle"

**One instance per run, and that is deliberate** — there is no `--all`. The seven live in
different cities, so a single anchor applied across them flags every correct entry in every
other city as FAR and makes the exit code meaningless. A fleet sweep is seven invocations
with seven anchors, which is the honest shape of the job.

Pass --near the instance's LIVE `WEATHER_LOCATION`, not the city you believe she lives in.
That value is what the prompt asserts ("She currently lives in {WEATHER_LOCATION}") and
what the selfie prompt stamps on every background, so auditing against it is what catches a
`.env` that disagrees with `setting.txt`. The per-instance town tally at the end of each
report is there for exactly that: entries clustering in a town that is not your anchor is
the signal.

## Why POI search and not geocoding

The obvious implementation — geocode "<place>, <city>" — is wrong, and quietly. Asked for
`"Meydenbauer Bay Park, Seattle"` (right park, wrong city) TomTom's geocoder returns
`Bay Terrace Road, Seattle` with no error: a fuzzy matcher never says "does not exist", it
returns the nearest plausible thing. Auditing that way marks a bad atlas clean.

Position-biased POI search discriminates properly: the real park comes back as a POI named
"Meydenbauer Bay Park", and an invented business returns zero results. So this queries the
bare place name biased at the anchor, requires a POI (not a street), and requires the found
name to actually resemble what was asked for — a near-miss is NOT FOUND, not a pass.

Repo-only: nothing here deploys and `vps-sync.sh` does not copy `tools/`. It reads the
COMMITTED seed files, so where a live instance has diverged the live instance is
authoritative (v2026-08-01.10).

Needs TOMTOM_API_KEY in the environment — the same key the fleet uses. One HTTP call per
atlas entry (~150 across all seven), so prefer one instance at a time while iterating.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Every tool in tools/ that imports bot.py needs bot.py's dependencies, and the VPS's
# system python has none of them — the fleet runs from the selected release venv. Without this the
# failure is a bare `ModuleNotFoundError: No module named 'PIL'` from inside bot.py's
# import block, which says nothing about which interpreter to use (hit 2026-08-10).
_MISSING_DEPS = (
    "cannot import bot.py — {mod} is missing.\n"
    "This tool imports bot.py, so it needs bot.py's dependencies:\n"
    "  on the VPS:  /opt/telegram-bots/current/venv/bin/python3 {script} ...\n"
    "  elsewhere:   pip install --require-hashes -r <repo>/telegram-companion-bot/requirements.lock"
)
# Entries read "Name — description of what it means to her". Only the part before the dash
# is a place; the rest is characterisation and would wreck the query. Both the em dash and
# a plain hyphen appear across the seven files.
_NAME_SPLITS = ("—", " - ", "–")
# Dropped before comparing names so "The Fremont Bridge" still matches "Fremont Bridge".
_STOPWORDS = {"the", "a", "an", "of", "and", "at", "on", "in", "for"}
# Wide enough that a real-but-distant place is FOUND and reported FAR, rather than
# vanishing into NOT FOUND and reading as fabricated. Kept independent of --radius, which
# only decides the verdict.
_SEARCH_RADIUS_M = 80_000
_RETRIES = 3            # attempts per entry when the failure is a rate limit
_BACKOFF_S = 2.0        # first retry waits this long, second twice it
_SLEEP_S = 0.3          # between entries; the free tier throttles per second


def parse_atlas(text: str) -> list:
    """atlas.txt -> entry lines, using bot.py's own filter (strip, drop blanks and #)."""
    return [ln.strip() for ln in (text or "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def place_name(entry: str) -> str:
    """'Meydenbauer Bay Park — she goes when...' -> 'Meydenbauer Bay Park'.

    Falls back to the whole entry when there is no dash, which searches badly but is
    visibly the tool's problem rather than silently auditing nothing."""
    for sep in _NAME_SPLITS:
        if sep in entry:
            return entry.split(sep, 1)[0].strip()
    return entry.strip()


# Words that mark an entry as a DESCRIPTION of a place rather than its name. Relative
# pronouns and personal pronouns are the giveaway: a named place is a noun phrase, while
# "the café where the wifi is fast" and "the food cart pod she considers her main
# restaurant" are sentences about one.
_DESCRIPTIVE_MARKERS = {
    "that", "where", "which", "who", "she", "her", "hers", "his", "he", "they", "their",
    "with", "when", "someone", "everything", "knows", "found", "considers", "went",
}
# Stripped before judging capitalisation, so "The Spar" is read as "Spar".
_LEADING = {"the", "a", "an", "that", "her", "his", "their", "one", "some"}


def looks_like_a_named_place(name: str) -> bool:
    """Is this entry a place TomTom could plausibly know, or a description of one?

    Bonnie's and marcus's atlases are written as "the mailbox", "that one parking garage
    roof", "his apartment, on the eastside" — deliberate, and arguably the better style,
    since a generic landmark can never be factually wrong. Looking them up wastes a
    request each and fills the report with NOT FOUND lines that are not defects.

    A heuristic, and it says so: it errs toward SKIPPING, so a real place wrongly skipped
    goes unaudited rather than wrongly flagged. That is the safe direction here — the cost
    is a missing check, not a false accusation against good content. `--check-all` forces
    every entry through."""
    toks = re.findall(r"[A-Za-z0-9'’\-]+", name or "")
    if not toks:
        return False
    lowered = [t.lower() for t in toks]
    # Skip the first token when scanning for markers: a leading "That"/"Her" is a
    # determiner ("That alley"), while a later one is doing sentence work.
    if any(t in _DESCRIPTIVE_MARKERS for t in lowered[1:]):
        return False
    body = toks[1:] if lowered[0] in _LEADING else toks
    sig = [t for t in body if t.lower() not in _STOPWORDS]
    caps = [t for t in sig if t[:1].isupper()]
    # Proper nouns should carry the phrase, not garnish it: "Deschutes Parkway, along the
    # lake" qualifies; "rented room above the bar on Fourth" does not.
    return bool(caps) and len(caps) * 2 >= len(sig)


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in _STOPWORDS}


def name_matches(query: str, found: str, threshold: float = 0.5) -> bool:
    """Does the POI we got back actually resemble the one we asked for?

    Guards the failure this tool exists to avoid: TomTom answering "Meydenbauer Bay Park"
    with "Bay Terrace Road" and the audit calling it a pass. Token overlap against the
    QUERY's tokens, so a longer official name ("Meydenbauer Beach Park & Boat Launch")
    still matches while an unrelated street does not."""
    q = _tokens(query)
    return bool(q) and len(q & _tokens(found)) / len(q) >= threshold


def _nearest(candidates):
    """The candidate closest to the search anchor, by TomTom's own `dist` (metres).

    Relevance order is not distance order. Emily's atlas names "The Spar", a real Olympia
    bar; anchored on Olympia within an 80km radius, TomTom's top name-match was the Tacoma
    one 26 miles away and the audit reported FAR on an entry that is a five-minute walk
    from her (2026-08-10). Picking the FIRST match makes the verdict depend on TomTom's
    ranking; picking the nearest makes it depend on geography, which is what is being
    audited."""
    rows = list(candidates)
    rows.sort(key=lambda r: r.get("dist") if isinstance(r.get("dist"), (int, float)) else 9e9)
    return rows[0] if rows else None


def best_poi(results, query: str):
    """Nearest result that is a real POI whose name resembles the query, else None."""
    return _nearest(
        r for r in (results or [])
        if isinstance(r, dict)
        and ((r.get("poi") or {}).get("name") or "").strip()
        and name_matches(query, (r.get("poi") or {}).get("name", "").strip())
    )


def best_area(results, query: str):
    """First non-POI result whose ADDRESS resembles the query, else None.

    Half an atlas is not points of interest. "Old Bellevue (Main Street)" is a real
    historic district, "Factoria" a neighbourhood, "Ballard Locks" an area as much as a
    landmark — none of them carry a `poi.name`, so a POI-only audit reported the district
    as fabricated and invited deleting a perfectly good entry (observed on priya's real
    atlas, 2026-08-10).

    Runs only after `best_poi` finds nothing, and reuses `name_matches` so it cannot
    reintroduce the fuzzy-match hole the POI approach was built to close: asked for
    "Meydenbauer Bay Park", a "Bay Terrace Road" geography still scores 1/3 and is
    rejected."""
    return _nearest(
        r for r in (results or [])
        if isinstance(r, dict)
        and not (r.get("poi") or {}).get("name")
        and ((r.get("address") or {}).get("freeformAddress") or "")
        and name_matches(query, (r.get("address") or {}).get("freeformAddress", ""))
    )


def verdict(miles, radius: float, failed: bool = False) -> str:
    """One label per entry, so a 20-line report is skimmable.

    LOOKUP FAILED is emphatically NOT "NOT FOUND". The first real run rate-limited after
    nine entries and reported the remaining nine — Marymoor Park, Ballard Locks, Bellevue
    Downtown Park among them — as NOT FOUND, i.e. as fabricated places. An unanswered
    question and a negative answer are different things, and a tool that renders them
    identically invites deleting perfectly good atlas entries."""
    if failed:
        return "LOOKUP FAILED"
    if miles is None:
        return "NOT FOUND"
    return "ok" if miles <= radius else "FAR"


def _is_rate_limit(err: str) -> bool:
    return "429" in (err or "") or "rate limit" in (err or "").lower()


def lookup(bot, name: str, origin, sleep_s: float):
    """(results, error). Retries a rate limit with backoff; other failures return at once.

    TomTom's free tier throttles hard, and an atlas is 15–25 entries fired back to back:
    the first run tripped 429 on entry ten and every one after it."""
    for attempt in range(_RETRIES):
        try:
            return bot._fetch_tomtom_search(name, origin[0], origin[1], _SEARCH_RADIUS_M), None
        except Exception as e:                      # noqa: BLE001 — reported, never raised
            err = str(e)
            if _is_rate_limit(err) and attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_S * (attempt + 1))
                continue
            return None, err
    return None, "rate limited after retries"


def _fake_instance() -> Path:
    """Minimal dir so `import bot` succeeds — the conftest.py/selfie-preview recipe."""
    d = Path(tempfile.mkdtemp(prefix="atlas_audit_"))
    (d / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=audit:not-a-real-token\n"
        "NANOGPT_API_KEY=audit-not-a-real-key\n"
        "CHARACTER_CARD=blank.json\n"
        "BOT_TIMEZONE=America/Los_Angeles\n"
    )
    shutil.copy(REPO / "blank.json", d / "blank.json")
    return d


def audit(bot, instance: str, origin, radius: float, sleep_s: float = _SLEEP_S,
          check_all: bool = False) -> list:
    """(entry, name, found, town, miles, verdict) per atlas line."""
    path = REPO / instance / "atlas.txt"
    if not path.exists():
        sys.exit(f"no atlas.txt for instance {instance!r} at {path}")
    entries = parse_atlas(path.read_text(encoding="utf-8"))
    rows = []
    for i, entry in enumerate(entries):
        name = place_name(entry)
        found = town = ""
        miles = None
        if not check_all and not looks_like_a_named_place(name):
            # No request at all — this is the point. Twenty descriptive entries used to
            # cost twenty lookups and produce twenty NOT FOUND lines that were not defects.
            rows.append((entry, name, "", "", None, "not a place name"))
            continue
        if i:
            time.sleep(sleep_s)     # pace the whole run, not just the retries
        # The bare name, biased at the anchor — never "name, city". See the module
        # docstring: appending a city is what makes a wrong answer look right.
        results, err = lookup(bot, name, origin, sleep_s)
        if err:
            print(f"  ! lookup failed for {name!r}: {err}", file=sys.stderr)
            rows.append((entry, name, "", "", None, verdict(None, radius, failed=True)))
            continue
        hit = best_poi(results, name)
        if hit is None and (hit := best_area(results, name)) is not None:
            # An area, not a business. Marked so the report does not read as though a
            # named venue was confirmed.
            found = ((hit.get("address") or {}).get("freeformAddress") or "") + " [area]"
        elif hit:
            found = (hit.get("poi") or {}).get("name") or ""
        if hit:
            town = (hit.get("address") or {}).get("municipality") or ""
            pos = hit.get("position") or {}
            if pos.get("lat") is not None and pos.get("lon") is not None:
                miles = bot._haversine(origin[0], origin[1], pos["lat"], pos["lon"])
        rows.append((entry, name, found, town, miles, verdict(miles, radius)))
    return rows


def report(instance: str, rows: list) -> tuple:
    """Print one instance's findings; return (content flags, lookup failures).

    The two are counted separately and never summed. A flag is something to fix in
    atlas.txt; a failure means the audit did not run for that entry and says nothing at
    all about it."""
    flagged = [r for r in rows if r[5] in ("NOT FOUND", "FAR")]
    failed = [r for r in rows if r[5] == "LOOKUP FAILED"]
    skipped = [r for r in rows if r[5] == "not a place name"]
    checked = len(rows) - len(failed) - len(skipped)
    head = f"=== {instance}: {len(rows)} entries, {checked} checked, {len(flagged)} flagged"
    print(head + (f", {len(failed)} NOT CHECKED (lookup failed)" if failed else "")
          + (f", {len(skipped)} not place names" if skipped else ""))
    for entry, name, found, town, miles, v in rows:
        if v in ("ok", "not a place name"):
            continue
        dist = "—" if miles is None else f"{miles:.1f} mi"
        extra = f" -> {found} ({town})" if found else ""
        print(f"  [{v}] {name}  ({dist}){extra}")
    towns = Counter(r[3] for r in rows if r[3])
    if towns:
        print("  towns: " + ", ".join(f"{t}×{n}" for t, n in towns.most_common())
              + f"   (of {checked} checked)")
    if skipped:
        # Named, not listed: a descriptive atlas is a style, not a defect, and printing
        # twenty of them back is the noise this exists to remove. --check-all overrides.
        print(f"  {len(skipped)} entries read as descriptions rather than place names and "
              f"were not looked up (--check-all to force).")
        # The heuristic leans on capitalisation, so an atlas authored in lowercase would be
        # skipped wholesale and this report would look reassuringly empty. Say so rather
        # than let silence pass for a clean bill (owner raised the lowercase risk, and
        # priya's own preset does mandate lowercase — for her texting, not her seed files).
        if len(skipped) >= max(3, int(len(rows) * 0.6)):
            print(f"  ! MOST of this atlas ({len(skipped)}/{len(rows)}) was skipped. Either it "
                  f"is written descriptively on purpose — fine, nothing to audit — or it is "
                  f"written in lowercase, which this heuristic cannot tell from a "
                  f"description. Check a few by eye, or rerun with --check-all.")
    if failed:
        print(f"  ! {len(failed)} entries were never checked — rerun them before "
              f"concluding anything about those lines.")
    print()
    return len(flagged), len(failed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instance", help="seed directory name, e.g. priya")
    ap.add_argument("--near", required=True,
                    help="this instance's LIVE WEATHER_LOCATION, e.g. 'Bellevue, WA'")
    ap.add_argument("--radius", type=float, default=15.0,
                    help="miles from --near before an entry is FAR (default 15)")
    ap.add_argument("--check-all", action="store_true",
                    help="look up every entry, including ones that read as descriptions")
    ap.add_argument("--sleep", type=float, default=_SLEEP_S,
                    help=f"seconds between lookups; raise if you still hit 429 "
                         f"(default {_SLEEP_S})")
    args = ap.parse_args()

    if not os.getenv("TOMTOM_API_KEY"):
        sys.exit("TOMTOM_API_KEY is not set — this tool searches for every atlas entry.")

    home = _fake_instance()
    try:
        sys.argv = [sys.argv[0], str(home)]
        os.environ["BOT_HOME"] = str(home)
        sys.path.insert(0, str(REPO))
        try:
            import bot  # noqa: E402 -- module-level init needs the env above
        except ModuleNotFoundError as e:
            sys.exit(_MISSING_DEPS.format(mod=e.name, script=Path(__file__).resolve()))

        bot.TOMTOM_API_KEY = os.environ["TOMTOM_API_KEY"]   # fake .env has no key

        # _tomtom_geocode returns None only for "not found"; a network or HTTP failure
        # raises _TomTomError, which unwrapped gives a traceback instead of this message.
        try:
            anchor = bot._tomtom_geocode(args.near)
        except Exception as e:                      # noqa: BLE001 — any failure here is fatal
            sys.exit(f"could not reach TomTom to geocode --near {args.near!r}: {e}")
        if not anchor:
            sys.exit(f"could not geocode --near {args.near!r}")
        origin = (anchor[0], anchor[1])
        print(f"# anchor: {args.near} -> {anchor[2]} ({anchor[0]:.4f}, {anchor[1]:.4f})")
        print(f"# radius: {args.radius} miles\n")

        flagged, failed = report(args.instance,
                                 audit(bot, args.instance, origin, args.radius, args.sleep,
                                       args.check_all))
        # Distinct exit codes so a character-pass Routine can tell "the atlas has problems"
        # from "the audit did not finish" — retry the second, act on the first.
        sys.exit(2 if failed else (1 if flagged else 0))
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
