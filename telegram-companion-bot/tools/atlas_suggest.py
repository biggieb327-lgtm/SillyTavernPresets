#!/usr/bin/env python3
"""Propose real nearby places for an instance's atlas.txt, by kind.

The companion to `atlas_audit.py`. That one checks what is already in the file; this one
helps write it. Both exist because `atlas.txt` is injected into every prompt as "Real spots
{NAME} knows" and drawn from for selfie backgrounds, and until now the only way to author
one was to invent places and hope they existed.

    python3 tools/atlas_suggest.py priya --near "Bellevue, WA"
    python3 tools/atlas_suggest.py cass  --near "Portland, OR" --kinds "coffee shop,park"

Prints ready-to-paste atlas lines with the description left blank — the half only a person
can write. It **proposes and never edits**, the same contract `character-review/` has: a
place list is not a character, and what a place MEANS to her is the whole point of the file.

Entries already in her atlas are skipped, so re-running after an edit only shows what is
new. Matching is on the place name, using `atlas_audit.place_name`, so a line whose
description mentions a different place does not suppress it.

One instance per run and one anchor, for the reason `atlas_audit` has no `--all`: the seven
live in different cities.

Repo-only — nothing here deploys and `vps-sync.sh` does not copy `tools/`. Needs
TOMTOM_API_KEY. One HTTP call per kind (12 by default).
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas_audit  # noqa: E402 -- sibling tool; shares the atlas parser so it cannot drift

REPO = Path(__file__).resolve().parent.parent

# What an atlas is actually made of, read off the seven committed files: places she goes
# on purpose, not services she uses. Deliberately not TomTom's full category taxonomy —
# that has hundreds of codes and almost none of them are somewhere a character hangs out.
DEFAULT_KINDS = (
    "coffee shop", "park", "bar", "grocery store", "gym", "bookstore",
    "diner", "library", "viewpoint", "trail", "record store", "bakery",
)
_SEARCH_RADIUS_M = 8_000     # walkable-to-short-drive; an atlas is her neighbourhood


def existing_names(atlas_path: Path) -> set:
    """Lowercased place names already in the file, for dedupe."""
    if not atlas_path.exists():
        return set()
    return {atlas_audit.place_name(e).lower()
            for e in atlas_audit.parse_atlas(atlas_path.read_text(encoding="utf-8"))}


def suggestion_line(name: str, address: str) -> str:
    """A pasteable atlas row with the meaning left for a human to supply."""
    return f"{name} — [what it means to her]   # {address}"


def collect(bot, origin, kind: str, seen: set, limit: int) -> list:
    """Up to `limit` POIs of one kind near origin, skipping anything already known.

    `seen` is mutated so a place that answers two kinds is proposed once."""
    try:
        results = bot._fetch_tomtom_search(kind, origin[0], origin[1], _SEARCH_RADIUS_M)
    except Exception as e:                          # noqa: BLE001 — one dead kind is not fatal
        print(f"  ! search failed for {kind!r}: {e}", file=sys.stderr)
        return []
    out = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        name = ((r.get("poi") or {}).get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        addr = ((r.get("address") or {}).get("freeformAddress") or "").strip()
        out.append(suggestion_line(name, addr))
        if len(out) >= limit:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("instance", help="seed directory name, e.g. priya")
    ap.add_argument("--near", required=True,
                    help="this instance's LIVE WEATHER_LOCATION, e.g. 'Bellevue, WA'")
    ap.add_argument("--kinds", default="",
                    help=f"comma-separated place kinds (default: {', '.join(DEFAULT_KINDS)})")
    ap.add_argument("--per-kind", type=int, default=3,
                    help="how many candidates per kind (default 3)")
    args = ap.parse_args()

    if not os.getenv("TOMTOM_API_KEY"):
        sys.exit("TOMTOM_API_KEY is not set — this tool searches for places near her.")
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()] or list(DEFAULT_KINDS)

    home = atlas_audit._fake_instance()
    try:
        sys.argv = [sys.argv[0], str(home)]
        os.environ["BOT_HOME"] = str(home)
        sys.path.insert(0, str(REPO))
        import bot  # noqa: E402 -- module-level init needs the env above

        bot.TOMTOM_API_KEY = os.environ["TOMTOM_API_KEY"]   # fake .env has no key

        try:
            anchor = bot._tomtom_geocode(args.near)
        except Exception as e:                      # noqa: BLE001 — any failure here is fatal
            sys.exit(f"could not reach TomTom to geocode --near {args.near!r}: {e}")
        if not anchor:
            sys.exit(f"could not geocode --near {args.near!r}")

        atlas = REPO / args.instance / "atlas.txt"
        seen = existing_names(atlas)
        print(f"# anchor: {args.near} -> {anchor[2]}")
        print(f"# {args.instance}: {len(seen)} places already in atlas.txt, skipped below\n")

        total = 0
        for kind in kinds:
            lines = collect(bot, (anchor[0], anchor[1]), kind, seen, args.per_kind)
            if not lines:
                continue
            total += len(lines)
            print(f"## {kind}")
            for ln in lines:
                print(ln)
            print()
        print(f"# {total} candidates. Nothing was written — paste the ones that fit and "
              f"replace the bracket with what the place means to her.")
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
