#!/usr/bin/env python3
"""Theory guard — C5: label a theory as a theory until evidence arrives.

Stop hook. Catches one mechanizable slice of C5: asserting what code *does* at
runtime (returns, produces, outputs, causes) without hedging, when the claim
names a specific function or identifier. The general case — diagnosing an
incident and stating a cause as fact — has no mechanical signature, same as C8's
uncovered half. This catches the shape that recurred: a behavioral claim about a
named function, told to the owner as fact, that one command would have verified.

Fails OPEN on anything unexpected.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from host_guard import last_assistant_text
except ImportError:
    sys.exit(0)

IDENT = re.compile(
    r'\b([a-z_][a-z0-9_]{2,})\b'
    r'(?:\s*\([^)]*\))?'
    r'\s+'
    r'(?:returns?|produces?|outputs?|causes?|results?\s+in|'
    r'will\s+(?:return|produce|output|cause|result\s+in)|'
    r'would\s+(?:return|produce|output|cause|result\s+in))\b',
    re.I)

HEDGE = re.compile(
    r'\b(?:probably|likely|might|may\b|could\b|possibly|I think|I believe|'
    r'hypothesis|hypothesize|unverified|uncertain|untested|not sure|unclear|'
    r'suggests?|seems?\s+to|appears?\s+to|in theory)\b'
    r'|\[hypothesis\]',
    re.I)

CODE_FENCE = re.compile(r'```')
ESCAPE = re.compile(r'#\s*theory-ok\b', re.I)


def check(text: str) -> list:
    if ESCAPE.search(text):
        return []
    problems = []
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if CODE_FENCE.match(s):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if len(s) < 20 or s.startswith(("$", "|", "#", ">")):
            continue
        if not IDENT.search(s):
            continue
        if HEDGE.search(s):
            continue
        m = IDENT.search(s)
        if m:
            problems.append("  " + (s[:150] + ("…" if len(s) > 150 else "")))
    return problems


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    text = last_assistant_text(payload.get("transcript_path") or "")
    if not text:
        return 0
    problems = check(text)
    if problems:
        sys.stderr.write(
            "[theory-guard] C5 (.claude/memory/constraints.md) — a behavioral claim "
            "about a named function was stated without hedging:\n"
            + "\n".join(problems[:3])
            + "\n Did you run it, or is this a theory? Either verify with a command "
              "and paste the output, or hedge: \"should return\", \"I expect\", "
              "\"[hypothesis]\". Reading source tells you what code says; only "
              "running it tells you what it produces.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
