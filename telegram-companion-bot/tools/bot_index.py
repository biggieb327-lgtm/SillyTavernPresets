#!/usr/bin/env python3
"""List bot.py's top-level functions and classes with line numbers, or search them by name/docstring.

Why this exists: bot.py has no section markers, and its 556 top-level defs sit in
whatever order history put them in, not topic order — `grep -n "^def"` finds a name
but nothing about what's near it. The file doubled in a month (7,626 lines on
2026-07-05, per ROADMAP.md's survey baseline) with no sign of slowing, so the cost of
getting oriented in it grows every release. This parses bot.py fresh on every run —
never a committed snapshot — so it can't drift out of sync the way a static index would.

    python3 tools/bot_index.py                    # full index, file order
    python3 tools/bot_index.py --cmd               # just the /command handlers (*_cmd)
    python3 tools/bot_index.py selfie               # name/docstring search, case-insensitive
    python3 tools/bot_index.py --min-lines 40 memory  # ...only entries >= 40 lines long
    python3 tools/bot_index.py --sort-length --cmd  # longest command handlers first
"""
import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOT_PY = REPO / "bot.py"


def _entries(tree: ast.Module) -> list[dict]:
    """Top-level def/class nodes only — nested helpers stay folded into their parent entry."""
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        doc = ast.get_docstring(node, clean=True)
        doc_line = doc.splitlines()[0].strip() if doc else ""
        if isinstance(node, ast.ClassDef):
            kind = "class"
        elif isinstance(node, ast.AsyncFunctionDef):
            kind = "async def"
        else:
            kind = "def"
        out.append({
            "name": node.name,
            "kind": kind,
            "start": node.lineno,
            "end": end,
            "length": end - node.lineno + 1,
            "doc": doc_line,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", default="",
                    help="case-insensitive substring match on name or docstring first line")
    ap.add_argument("--cmd", action="store_true", help="only *_cmd command handlers")
    ap.add_argument("--min-lines", type=int, default=0, help="only entries at least this many lines long")
    ap.add_argument("--sort-length", action="store_true", help="longest entries first instead of file order")
    args = ap.parse_args()

    source = BOT_PY.read_text()
    tree = ast.parse(source, filename=str(BOT_PY))
    all_entries = _entries(tree)
    entries = all_entries

    if args.cmd:
        entries = [e for e in entries if e["kind"] != "class" and e["name"].endswith("_cmd")]
    if args.query:
        q = args.query.lower()
        entries = [e for e in entries if q in e["name"].lower() or q in e["doc"].lower()]
    if args.min_lines:
        entries = [e for e in entries if e["length"] >= args.min_lines]
    if args.sort_length:
        entries = sorted(entries, key=lambda e: -e["length"])

    total_lines = len(source.splitlines())
    print(f"# bot.py: {total_lines} lines, {len(all_entries)} top-level defs/classes total")
    print(f"# showing {len(entries)}\n")
    for e in entries:
        loc = f"bot.py:{e['start']}"
        tag = f"[{e['kind']}, {e['length']}L]"
        doc = f"  — {e['doc']}" if e["doc"] else ""
        print(f"{loc:<16} {e['name']:<40} {tag}{doc}")

    if not entries:
        sys.exit(1)


if __name__ == "__main__":
    main()
