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

# The hook's scope (see module docstring) is a claim about a NAMED FUNCTION. Common
# English words are not function names, so when the IDENT "identifier" is one of these
# AND does not look like code (no `_`, not called with `()`), the match is a false
# positive — e.g. the noun "cause" after a possessive ("shares its cause") tripping the
# `causes?` verb. Excluding these keeps the guard on its target, not on ordinary prose.
STOPWORDS = frozenset(
    "the a an its it this that these those each one ones our your their his her my "
    "any all some both same such which what who whom whose they them then here there "
    "only also root main first last next same other another every no not".split()
)

# Doc-description sentences describe what a document SAYS, not what code DOES at runtime
# — quoting a changelog/constraint/rule is not a behavioral claim to verify. Skip a line
# whose subject is a documentation artifact reported with a "says/records/…" verb.
DOCDESC = re.compile(
    r'\b(?:changelog|constraints?|entry|entries|docs?|document|readme|'
    r'note|notes|log|oplog|comment|section|table|row|rule|skill|manual|guide|'
    r'handoff|roadmap|audit|file|header|field|instruction|policy)\b'
    r'[^.]{0,60}?\b'
    r'(?:records?|says?|states?|notes?|documents?|describes?|lists?|covers?|'
    r'flags?|mentions?|explains?|reads?|warns?|specifies|defines?|names?|'
    r'captures?|shows?|reminds?|tells?|spells?\s+out)\b',
    re.I)

CODE_FENCE = re.compile(r'```')
ESCAPE = re.compile(r'#\s*theory-ok\b', re.I)


def _looks_like_named_function(match) -> bool:
    """A real target: called with `()`, or a snake_case identifier — not a plain word."""
    ident = match.group(1).lower()
    called = "(" in match.group(0)
    return called or "_" in ident or ident not in STOPWORDS


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
        if HEDGE.search(s):
            continue
        if DOCDESC.search(s):
            continue
        # Flag only if some match is a claim about a name that looks like a function.
        if any(_looks_like_named_function(m) for m in IDENT.finditer(s)):
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


def selftest() -> int:
    """Break-test the narrowing: false positives skip, real claims still fire.
    Run: python3 theory_guard.py --selftest
    """
    cases = [
        # (should_flag?, text)
        (False, "it earns a `C`-number only if a second entry shares its cause."),
        (False, "The constraints entry records the lesson concretely for next time."),
        (False, "The changelog documents why the timeout was raised to thirty seconds."),
        (False, "The root cause was a stale checkout on the VPS."),
        (False, "I ran it and the output shows the same cause we saw yesterday."),
        (False, "This produces cleaner handoffs, probably."),  # hedged
        (True, "_group_deliver() returns None when the shared ledger is empty."),
        (True, "The function build_prompt produces a truncated block for long cards."),
        (True, "update_cmd causes a repo_not_readable reply on the private repo."),
    ]
    fails = 0
    for want, txt in cases:
        got = bool(check(txt))
        ok = got == want
        fails += not ok
        print(("PASS" if ok else "**FAIL**"),
              "flag=%-5s want=%-5s |" % (got, want), txt[:66])
    print("selftest:", "all green" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
