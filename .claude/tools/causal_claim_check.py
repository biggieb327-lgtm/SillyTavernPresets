#!/usr/bin/env python3
"""Causal-claim discriminator — C8 pattern checker.

Tests whether a reasoning paragraph contains an undiscriminated causal claim:
a conclusion drawn from evidence whose scope does not match the conclusion's,
or evidence both hypotheses predict equally, without hedging or naming a
discriminator.

Not a stop hook. C8 is prose-only for stated reasons (constraints.md): no tool
call or code shape to intercept. This is an eval tool whose selftest exercises
RED/GREEN fixtures drawn from real C8 incidents (seen 11) to prove the
discriminator rules catch the historical failure shapes.

Fixtures are the real value — they document which specific readings were
mistaken for which conclusions, so a future session hitting the same data
recognizes the shape.
"""
import re
import sys

# --- Scope-mismatch patterns from real C8 incidents ---
# (evidence_source_re, conclusion_scope_re, incident_id, description)
SCOPE_PAIRS = [
    # C8 #10 (2026-08-27): /errors names whichever slot made the call —
    # summary, caption, reaction, mood — not necessarily the reply/chat model.
    (r'(?:/errors|error.{0,20}log)\b',
     r'\bchat\s+model\b|\breply\s+(?:model|path)\b',
     'C8-10', '/errors slot -> chat model'),

    # C8 #11 (2026-09-01): memories.txt is the keyword/embedding RAG store.
    # Relationship memory lives in summaries/facts/recent_summaries (state.json).
    (r'\bmemories\.txt\b',
     r'\brelationship\s+memory\b|\bmemory\s+is\s+sparse\b',
     'C8-11', 'memories.txt -> relationship memory'),

    # C8 #8 (2026-08-21): "graduat" in body substring-matches "Not graduated."
    (r"""(?:substring|['"][^'"]{2,15}['"]\s+in\s+\w+)""",
     r'\ball\s+\d+\s+(?:already\s+)?have\b|\bevery\s+constraint\b',
     'C8-8', 'substring match -> semantic classification'),
]

# --- Non-discriminating evidence patterns ---
# A reading both hypotheses predict equally, used to support one.
NONDISCRIM_PAIRS = [
    # C8 #9 (2026-08-27): leaked text echoes preset steps -> "preset is source".
    # A thinking model invents its own scaffold; the echo does not discriminate.
    (r'\bechoes?\s+the\s+preset\b|\breproduces?\s+the\s+(?:preset|steps)\b',
     r'\bsource\s+of\b|\bis\s+the\s+(?:source|cause|origin)\b',
     'C8-9', 'echo matches preset -> preset is source'),

    # C8 #6 (2026-08-09): 1024x1024 matches both base photo and generated
    # selfie (SELFIE_SIZE defaults to 1024x1024).
    (r'\b1024.?x.?1024\b',
     r'\bconfirmed\b.{0,30}\b(?:is|same)\b|\bis\s+(?:the\s+)?(?:base|original)\b',
     'C8-6', 'size match -> identity confirmation'),
]

HEDGE_RE = re.compile(
    r'\[hypothesis\]|\bprobably\b|\blikely\b|\bmight\b|\bmay\b(?!\s+\d)'
    r'|\bcould\b|\bpossibly\b|\bI\s+think\b|\bI\s+believe\b'
    r'|\buncertain\b|\bsuggests?\b|\bappears?\s+to\b|\bseems?\s+to\b'
    r'|\bunverified\b|\bnot\s+confirmed\b|\bone\s+plausible\b'
    r'|\bhypothes(?:is|ize|etical)\b',
    re.I)

DISCRIMINATOR_RE = re.compile(
    r'\bcompeting\s+explanation\b|\balternative\s+(?:explanation|hypothesis)\b'
    r'|\bthe\s+other\s+(?:explanation|hypothesis)\b'
    r'|\bwould\s+(?:also\s+)?(?:show|explain|predict)\b'
    r'|\bdiscriminat\b|\bdistinguish\b|\brule[sd]?\s+out\b'
    r'|\btwo\s+explanations?\b|\bboth\s+hypothes[ei]s\b',
    re.I)


def check(text):
    """Returns list of (incident_id, reason) for undiscriminated causal claims."""
    findings = []
    if HEDGE_RE.search(text) or DISCRIMINATOR_RE.search(text):
        return []

    for ev_pat, conc_pat, ref, desc in SCOPE_PAIRS:
        if re.search(ev_pat, text, re.I) and re.search(conc_pat, text, re.I):
            findings.append((ref, 'scope mismatch: %s' % desc))

    for ev_pat, conc_pat, ref, desc in NONDISCRIM_PAIRS:
        if re.search(ev_pat, text, re.I) and re.search(conc_pat, text, re.I):
            findings.append((ref, 'non-discriminating evidence: %s' % desc))

    return findings


def selftest():
    """RED/GREEN fixtures from real C8 incidents."""
    cases = [
        # --- RED: must be flagged (real C8 incidents, verbatim pattern) ---

        # C8 #10 (2026-08-27): /errors showed glm-5:thinking, concluded chat
        # model drifted. Actually the summary/caption slots, not the reply path.
        (True, 'C8-10',
         '/errors showed [model] zai-org/glm-5:thinking transient error. '
         "Emily's chat model has drifted to glm-5:thinking."),

        # C8 #11 (2026-09-01): grepped memories.txt, concluded relationship
        # memory is sparse. Actually the tiered state had rich 174-word summary.
        (True, 'C8-11',
         'Grepped memories.txt for art and photo references, found only two '
         'faint traces. The relationship memory is sparse.'),

        # C8 #9 (2026-08-27): leaked text reproduced preset steps, concluded
        # preset is the source. A thinking model invents its own scaffold.
        (True, 'C8-9',
         'The leaked text reproduces the preset steps one-to-one. '
         'The [STEPPED THINKING] block is the source of the reasoning-leak.'),

        # C8 #6 (2026-08-09): image matches 1024x1024, concluded it is the
        # base photo. All generated selfies are also 1024x1024.
        (True, 'C8-6',
         "The image matches the audit's 1024x1024 progressive JPEG. "
         'Confirmed this is the base photo.'),

        # C8 #8 (2026-08-21): "graduat" in body counted all constraints as
        # guarded, but substring-matched "Not graduated."
        (True, 'C8-8',
         'Checked using "graduat" in body. '
         'All 15 already have a mechanism guarding them.'),

        # --- GREEN: must NOT be flagged ---

        # Properly scoped: conclusion matches the evidence scope exactly.
        (False, 'GREEN-scope',
         'Checked state.json for chat 8121667008: long_term_summary is 174 '
         'words, facts has 15 entries. The tiered memory for this chat is rich.'),

        # Named discriminator: two explanations and a discriminating test.
        (False, 'GREEN-discrim',
         'The leaked text echoes the preset steps. Two explanations: the model '
         'echoes the preset verbatim, or invents a similar scaffold. The '
         'discriminating test is a leak with headers the preset never contained.'),

        # Hedged: the claim carries [hypothesis].
        (False, 'GREEN-hedge',
         "/errors showed glm-5:thinking. Emily's chat model has [hypothesis] "
         'drifted to glm-5:thinking.'),

        # Evidence only, no causal claim about a broader scope.
        (False, 'GREEN-neutral',
         '/errors showed [model] zai-org/glm-5:thinking transient error on '
         'three calls in the last hour. The error rate is 12%.'),

        # Meta-discussion of the pattern, hedged.
        (False, 'GREEN-meta',
         'Using "graduat" in body is a substring test. It could match '
         'negations like "Not graduated." and would probably miscount.'),
    ]
    fails = 0
    for want_flag, label, text in cases:
        got = check(text)
        flagged = bool(got)
        passed = flagged == want_flag
        status = 'PASS' if passed else '**FAIL**'
        detail = got[0][1] if got else 'clean'
        print('%s  flag=%-5s want=%-5s %s: %s' % (
            status, flagged, want_flag, label, detail))
        if not passed:
            fails += 1
    if fails:
        print('selftest: %d FAILED' % fails)
    else:
        print('selftest: all green')
    return 1 if fails else 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(0)
