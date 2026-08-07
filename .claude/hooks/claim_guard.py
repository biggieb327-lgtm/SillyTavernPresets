#!/usr/bin/env python3
"""Claim guard — see claim-guard.sh for scope and rationale.

Graduated from the C8-family prose entry after its third occurrence (2026-08-02),
on the owner's stated trigger. Catches the one slice of that family with a
mechanical signature: **asserting two artifacts are the same on metadata alone.**

The 2026-08-02 instance: `file` reported 1024x1024 progressive JPEG for both an
uploaded image and `priya_base.jpg`, and I wrote "confirmed... grounded in her real
reference". Matching size is *consistent with* sameness; it does not establish it.
Three appearance.txt files were written on that footing, and they were in fact
different images.

What this does NOT cover, deliberately: claims that a code path or user-facing
surface behaves some way without exercising it (occurrences 1 and 2). Those have no
signature a scanner can see — the text looks identical whether or not the path was
run. That half stays prose in C8, and the `audit-keys-rendered` eval pins the one
concrete instance of it that could regress.

Fails OPEN on anything unexpected, same as the other guards.
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

# Words that assert sameness or settledness, rather than reporting a comparison.
CLAIM = re.compile(
    r'\b(?:confirm(?:ed|s)?|verified|identical|byte-identical|proves?|proven|'
    r'establish(?:es|ed)|match(?:es|ing)?\b[^.]{0,40}\bexactly|the same file|'
    r'is (?:in fact )?(?:her|his|the) reference)\b',
    re.I)
# Evidence that only narrows the space -- never sole grounds for an identity claim.
METADATA = re.compile(
    r'\b(?:\d{3,5}\s*[x×]\s*\d{3,5}|dimensions?|resolution|file ?size|\d+\s*bytes|'
    r'same size|progressive|JFIF|8-bit)\b', re.I)
# Evidence that actually establishes identity.
STRONG = re.compile(r'\b(?:md5|sha1|sha256|sha512|checksum|hash(?:ed|es)?|cmp\b|diff\b)', re.I)
HEDGE = re.compile(
    r'\b(?:consistent with|does not (?:establish|prove|confirm)|not (?:proof|confirmation)|'
    r'cannot claim|unverified|likely|probably|almost certainly|suggests?|may be|might be)\b', re.I)

SENT = re.compile(r'[^.!?\n]+[.!?]?')


def check(text: str) -> list:
    # Whole-message escape hatch and whole-message evidence: a hash anywhere in the
    # message is enough, since that is how the comparison would actually be reported.
    if re.search(r'#\s*claim-ok\b', text, re.I) or STRONG.search(text):
        return []
    problems = []
    # Line-granular, not sentence-granular: the 2026-08-02 instance put the claim
    # ("Priya: confirmed.") and its evidence ("1024x1024 progressive JPEG") in adjacent
    # sentences on one line. Lines, not paragraphs -- a wider window pairs a claim with
    # unrelated numbers further down the message.
    for line in text.splitlines():
        s = line.strip()
        if len(s) < 15 or s.startswith(("```", "|", "$", "#")):
            continue
        if CLAIM.search(s) and METADATA.search(s) and not HEDGE.search(s):
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
            "[claim-guard] C8 family (.claude/memory/constraints.md) — an identity/sameness "
            "claim rests on metadata, which narrows the space but settles nothing:\n"
            + "\n".join(problems)
            + "\n Hash it (`md5sum`/`sha256sum`/`cmp`), or downgrade the wording to what the "
              "reading actually supports (\"consistent with\", \"likely\"). Writing three "
              "appearance.txt files on a dimensions match cost a full round trip on 2026-08-02.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
