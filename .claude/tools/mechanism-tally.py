#!/usr/bin/env python3
"""mechanism-tally.py — how often has each hook and eval actually blocked something?

    python3 .claude/tools/mechanism-tally.py            # report (read-only)
    python3 .claude/tools/mechanism-tally.py harvest    # fold the runtime log into the ledger
    python3 .claude/tools/mechanism-tally.py check      # exit 1 if a blocking hook is not counted

Why this exists: skill-impact.md asks "did a fix hold?" by hand. The other half — which
guards have never fired and may be dead weight — had no record at all (mycelium 2026-08-23).

Where the rows come from:
  - hooks: .claude/hooks/count-block.sh wraps each hook that can exit 2 and writes a row
    when it does;
  - evals: run-evals.sh's bad() writes a row on every FAIL outside CI.
Both append to .claude/.runtime/blocks.log (gitignored; a cloud container throws it away).
`harvest`, run at session-debrief, folds it into the committed LEDGER below and empties it.
A session that never debriefs loses its rows — so counts are a floor, never a ceiling.

What a count means, stated so no reader over-reads it:
  - a firing is a block, not a verified catch — a noisy guard's false positives count too;
  - an eval that fails five times while one bug is fixed counts five firings, one day;
  - zero firings is NOT proof a guard is useless: a guard can work by being known about.
    QUIET means "review it", never "delete it".

Outcomes per mechanism (hubris Rule 1 — "could not determine" never prints as a verdict):
  FIRED        at least one firing on record
  QUIET        zero firings, and tracked for >= --window days: a candidate for review
  TOO-EARLY    zero firings, tracked for less than the window: no judgement possible yet
  NOT-COUNTED  a registered hook that can block but is not wrapped: no data can exist
  GONE         in the ledger, no longer in settings.json / run-evals.sh (renamed or deleted)

Exit codes: 0 ok; 1 `check` found a NOT-COUNTED hook; 3 could not determine (a source file
unreadable or malformed, or a scan that found nothing where something must exist).
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude/settings.json"
EVALS = ROOT / ".claude/evals/run-evals.sh"
HOOKS = ROOT / ".claude/hooks"
RUNTIME = ROOT / ".claude/.runtime/blocks.log"
LEDGER = ROOT / ".claude/memory/mechanism-tally.tsv"
WRAPPER = "count-block.sh"
COLS = ["kind", "name", "firings", "days", "first", "last"]
CAN_BLOCK = re.compile(r"\bexit 2\b|\breturn 2\b|exit\(2\)")


class Undetermined(Exception):
    pass


def read_ledger():
    """-> (tracking_since: date, {(kind, name): row dict})."""
    if not LEDGER.exists():
        raise Undetermined(f"{LEDGER.relative_to(ROOT)} is missing")
    since, rows = None, {}
    for n, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            m = re.search(r"tracking_since:\s*(\d{4}-\d{2}-\d{2})", line)
            if m:
                since = dt.date.fromisoformat(m.group(1))
            continue
        if not line.strip() or line.split("\t") == COLS:
            continue
        f = line.split("\t")
        if len(f) != len(COLS) or not f[2].isdigit() or not f[3].isdigit():
            raise Undetermined(f"ledger line {n} is malformed: {line!r}")
        r = dict(zip(COLS, f))
        r["firings"], r["days"] = int(r["firings"]), int(r["days"])
        rows[(r["kind"], r["name"])] = r
    if since is None:
        raise Undetermined("ledger has no '# tracking_since: YYYY-MM-DD' line")
    return since, rows


def write_ledger(since, rows):
    head = LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []
    comments = [l for l in head if l.startswith("#")]
    body = ["\t".join(COLS)] + [
        "\t".join(str(r[c]) for c in COLS)
        for _, r in sorted(rows.items())]
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text("\n".join(comments + body) + "\n", encoding="utf-8")
    tmp.replace(LEDGER)


def read_runtime():
    """-> (list of (date, kind, name), count of malformed rows)."""
    if not RUNTIME.exists():
        return [], 0
    good, bad = [], 0
    for line in RUNTIME.read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("\t")
        if len(f) == 3 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", f[0]) and f[1] in ("hook", "eval") and f[2]:
            good.append(tuple(f))
        elif line.strip():
            bad += 1
    return good, bad


def fold(rows, events):
    """Add runtime events into ledger rows (in place). A date already counted as `last`
    is not a new day; so is any earlier date — conservative, never double-counts."""
    by_key = {}
    for d, kind, name in events:
        by_key.setdefault((kind, name), []).append(d)
    for key, dates in by_key.items():
        r = rows.get(key) or dict(kind=key[0], name=key[1], firings=0, days=0,
                                  first=min(dates), last="")
        r["firings"] += len(dates)
        r["days"] += len({d for d in dates if d > r["last"]})
        r["first"] = min(r["first"], min(dates))
        r["last"] = max(r["last"], max(dates))
        rows[key] = r


def current_mechanisms():
    """-> (wrapped hooks, unwrapped blocking hooks, eval names)."""
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Undetermined(f"settings.json unreadable: {e}")
    wrapped, unwrapped = set(), set()
    for matchers in (settings.get("hooks") or {}).values():
        for m in matchers:
            for h in m.get("hooks", []):
                cmd = h.get("command", "")
                names = [n for n in re.findall(r"([A-Za-z0-9_.-]+\.(?:sh|py))", cmd) if n != WRAPPER]
                for n in names:
                    if WRAPPER in cmd:
                        wrapped.add(n)
                        continue
                    src = HOOKS / n
                    sib = HOOKS / (Path(n).stem.replace("-", "_") + ".py")
                    text = "".join(p.read_text(encoding="utf-8", errors="replace")
                                   for p in (src, sib) if p.exists())
                    if CAN_BLOCK.search(text):
                        unwrapped.add(n)
    try:
        evals = set(re.findall(r'\bbad "([A-Za-z0-9_.-]+)', EVALS.read_text(encoding="utf-8")))
    except OSError as e:
        raise Undetermined(f"run-evals.sh unreadable: {e}")
    if not wrapped and not unwrapped:
        raise Undetermined("found 0 blocking hooks in settings.json — the scan looked in the wrong place")
    if not evals:
        raise Undetermined("found 0 eval names in run-evals.sh — the scan looked in the wrong place")
    return wrapped, unwrapped, evals


def report(window, today):
    since, rows = read_ledger()
    events, malformed = read_runtime()
    fold(rows, events)  # in memory only; harvest is what persists
    wrapped, unwrapped, evals = current_mechanisms()
    tracked = (today - since).days
    present = {("hook", n) for n in wrapped} | {("eval", n) for n in evals}
    out = {k: [] for k in ("FIRED", "QUIET", "TOO-EARLY", "NOT-COUNTED", "GONE")}
    for key in sorted(present):
        r = rows.get(key)
        if r and r["firings"]:
            out["FIRED"].append(f"{key[0]:4}  {key[1]}  — {r['firings']} firing(s) on {r['days']} day(s), last {r['last']}")
        elif tracked >= window:
            out["QUIET"].append(f"{key[0]:4}  {key[1]}  — no firing in {tracked} days; review (dead weight, or working by deterrence?)")
        else:
            out["TOO-EARLY"].append(f"{key[0]:4}  {key[1]}")
    out["NOT-COUNTED"] = [f"hook  {n}  — can exit 2 but is not wrapped in {WRAPPER}" for n in sorted(unwrapped)]
    out["GONE"] = [f"{k[0]:4}  {k[1]}  — {rows[k]['firings']} firing(s), last {rows[k]['last']}"
                   for k in sorted(set(rows) - present)]
    print(f"mechanism-tally: tracking since {since} ({tracked} days; review window {window} days)")
    if events:
        print(f"  (includes {len(events)} unharvested runtime row(s) — run `harvest` at debrief to keep them)")
    if malformed:
        print(f"  ({malformed} malformed runtime row(s) ignored — not counted, not a verdict)")
    for k, lines in out.items():
        if k == "TOO-EARLY" and lines:
            print(f"\n{k} ({len(lines)}): zero firings, but {tracked} < {window} days tracked — cannot judge yet")
            continue
        print(f"\n{k} ({len(lines)})")
        for l in lines:
            print("  " + l)
    return out


def main(argv):
    args = argv[1:]
    window = 60
    if "--window" in args:
        i = args.index("--window")
        try:
            window = int(args[i + 1])
        except (IndexError, ValueError):
            print("--window needs a whole number of days", file=sys.stderr)
            return 2
        del args[i:i + 2]
    cmd = args[0] if args else "report"
    today = dt.datetime.now(dt.timezone.utc).date()
    try:
        if cmd == "harvest":
            since, rows = read_ledger()
            events, malformed = read_runtime()
            if not events:
                print(f"mechanism-tally: nothing to harvest ({malformed} malformed row(s))" if malformed
                      else "mechanism-tally: nothing to harvest")
                return 0
            fold(rows, events)
            write_ledger(since, rows)
            RUNTIME.write_text("", encoding="utf-8")
            print(f"mechanism-tally: harvested {len(events)} row(s) into {LEDGER.relative_to(ROOT)}"
                  + (f"; dropped {malformed} malformed" if malformed else "") + " — commit it")
            return 0
        if cmd == "check":
            _, unwrapped, _ = current_mechanisms()
            if unwrapped:
                print("not counted (can exit 2, not wrapped in count-block.sh): " + ", ".join(sorted(unwrapped)))
                return 1
            return 0
        if cmd == "report":
            report(window, today)
            return 0
        print(__doc__)
        return 3
    except Undetermined as e:
        print(f"mechanism-tally: COULD NOT DETERMINE — {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
