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
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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


def best_poi(results, query: str):
    """First result that is a real POI whose name resembles the query, else None."""
    for r in results or []:
        if not isinstance(r, dict):
            continue
        name = ((r.get("poi") or {}).get("name") or "").strip()
        if name and name_matches(query, name):
            return r
    return None


def verdict(miles, radius: float) -> str:
    """One word per entry, so a 20-line report is skimmable."""
    if miles is None:
        return "NOT FOUND"
    return "ok" if miles <= radius else "FAR"


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


def audit(bot, instance: str, origin, radius: float) -> list:
    """(entry, name, found, town, miles, verdict) per atlas line."""
    path = REPO / instance / "atlas.txt"
    if not path.exists():
        sys.exit(f"no atlas.txt for instance {instance!r} at {path}")
    rows = []
    for entry in parse_atlas(path.read_text(encoding="utf-8")):
        name = place_name(entry)
        found = town = ""
        miles = None
        try:
            # The bare name, biased at the anchor — never "name, city". See the module
            # docstring: appending a city is what makes a wrong answer look right.
            results = bot._fetch_tomtom_search(name, origin[0], origin[1], _SEARCH_RADIUS_M)
        except Exception as e:                      # noqa: BLE001 — a dead entry is data
            print(f"  ! search failed for {name!r}: {e}", file=sys.stderr)
            results = []
        hit = best_poi(results, name)
        if hit:
            found = (hit.get("poi") or {}).get("name") or ""
            town = (hit.get("address") or {}).get("municipality") or ""
            pos = hit.get("position") or {}
            if pos.get("lat") is not None and pos.get("lon") is not None:
                miles = bot._haversine(origin[0], origin[1], pos["lat"], pos["lon"])
        rows.append((entry, name, found, town, miles, verdict(miles, radius)))
    return rows


def report(instance: str, rows: list) -> int:
    """Print one instance's findings; return the number flagged."""
    bad = [r for r in rows if r[5] != "ok"]
    print(f"=== {instance}: {len(rows)} entries, {len(bad)} flagged")
    for entry, name, found, town, miles, v in rows:
        if v == "ok":
            continue
        dist = "—" if miles is None else f"{miles:.1f} mi"
        extra = f" -> {found} ({town})" if found else ""
        print(f"  [{v}] {name}  ({dist}){extra}")
    towns = Counter(r[3] for r in rows if r[3])
    if towns:
        print("  towns: " + ", ".join(f"{t}×{n}" for t, n in towns.most_common()))
    print()
    return len(bad)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instance", help="seed directory name, e.g. priya")
    ap.add_argument("--near", required=True,
                    help="this instance's LIVE WEATHER_LOCATION, e.g. 'Bellevue, WA'")
    ap.add_argument("--radius", type=float, default=15.0,
                    help="miles from --near before an entry is FAR (default 15)")
    args = ap.parse_args()

    if not os.getenv("TOMTOM_API_KEY"):
        sys.exit("TOMTOM_API_KEY is not set — this tool searches for every atlas entry.")

    home = _fake_instance()
    try:
        sys.argv = [sys.argv[0], str(home)]
        os.environ["BOT_HOME"] = str(home)
        sys.path.insert(0, str(REPO))
        import bot  # noqa: E402 -- module-level init needs the env above

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

        flagged = report(args.instance, audit(bot, args.instance, origin, args.radius))
        # Non-zero when anything is flagged, so this can gate a character-pass Routine.
        sys.exit(1 if flagged else 0)
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
