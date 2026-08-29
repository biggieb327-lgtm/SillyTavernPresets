#!/usr/bin/env python3
"""UserPromptSubmit hook — the enforced core of the `prompter` concept
(github.com/Terryc21/prompter): catch a short, under-specified prompt BEFORE
Claude acts on it and nudge a rewrite-for-approval.

WHY A HOOK, NOT A SKILL
prompter ships as a pure SKILL.md. A skill cannot intercept a prompt — it is
something the model chooses to invoke mid-turn, so "rewrite every prompt this
session" is advisory: the model remembers the instruction until it doesn't,
and just runs the task. Interception in Claude Code is a UserPromptSubmit hook,
which fires deterministically on every prompt before the model acts. This hook
supplies the interception the skill structurally cannot; the actual rewrite
(a semantic judgment) stays the model's job. Deterministic gate decides
WHETHER; the model decides HOW, and does nothing when a rewrite wouldn't help.

THE SPLIT
  GATE (here, a regex over the raw prompt) — cheap, catches the SHAPE: a short
  imperative task verb on a vague or unnamed object ("fix the flaky tests",
  "refactor this", "audit the auth code", "make it better"). It cannot see
  whether a rewrite would truly help — only that the prompt is shaped like one
  that usually would.

  MODEL (the injected instruction) — makes the real call. prompter's own
  principle carries over: "No rewrite is a success." A false positive here is
  cheap (the model reads the nudge and proceeds); a false negative is a missed
  rewrite, not a broken turn.

HONEST LIMITS
  - Typo-only prompts ("udpate the databse") mostly slip the gate: a regex does
    not spellcheck. Acceptable — a typo'd prompt is usually still understood,
    and the value case is the under-specified one, not the misspelled one.
  - additionalContext ACCUMULATES: turn N carries N copies (agent-authorization
    learned this the hard way — scaffolding audit F4). Cost is controlled here
    by the gate's tightness (most prompts in a session are not this shape) and a
    short body, NOT by a per-session emit cap. A cap is deliberately omitted:
    unlike agent-auth's standing grant (which CLAUDE.md carries after the cap),
    each qualifying prompt needs its OWN nudge about THAT prompt — capping would
    silently stop rewriting prompt #N+1. The gate is the cost control.

KILL SWITCH (repo policy: new features default ON with a mandatory switch)
  unset / anything else       -> enabled (default)
  PROMPTER=0 / off / false / no -> disabled (no-op)
  Disable for a session with `export PROMPTER=0`.
"""

import json
import os
import re
import sys

# ~60 tok. Names the shape, hands the judgment to the model, and defers to
# CLAUDE.md Working principles #1 (unattended runs never block on a question)
# so it cannot deadlock an overnight/automated session.
BODY = (
    "[prompter] This prompt looks short or under-specified. Before acting, judge whether "
    "rewriting it — clearer intent, a missing scope guardrail it clearly forgot (\"don't push "
    "yet\"), or a named deliverable shape — would MEANINGFULLY help. If yes, show the rewrite "
    'prefixed "Rewritten prompt:" and wait for approval. If it is already clear, or no one is '
    "present to approve (unattended run — CLAUDE.md Working principles #1), proceed without "
    "asking. No rewrite is a successful outcome."
)

_DISABLED = {"0", "off", "false", "no"}

# Whole-message operational responses — never a new task to rewrite. Matched
# against the entire stripped prompt, not searched, so "proceed with the audit"
# (a real task) is NOT caught here.
_AFFIRMATION = re.compile(
    r"^(y|n|yes|no|ok|okay|k|yep|yeah|nope|sure|proceed|go|go ahead|continue|"
    r"approved?|looks good|lgtm|sounds good|do it|ship it|done|next|stop|cancel|"
    r"skip|retry|again)[.! ]*$",
    re.I,
)

# Option / selection responses ("Option 2", "#3", "the first one", a bare number).
_SELECTION = re.compile(
    r"^(option\s*)?#?\d+[.) ]*$|^the (first|second|third|fourth|last|other) one[.! ]*$",
    re.I,
)

# Under-specifiable action verbs: the ones that beg "how?" / "what shape?".
# Deliberately EXCLUDES concrete verbs (run, show, list, deploy, commit, push,
# install, read, open, restart) — those are not vague by shape.
_TASK_VERB = re.compile(
    r"\b(fix|refactor|audit|review|clean(?:\s*up)?|tidy|improv\w*|optimi[sz]e|"
    r"handle|debug|investigate|rework|redo|rewrite|overhaul|streamline|enhance|"
    r"polish|sort out|deal with|look into|address|resolve|update|add|make|change|"
    r"adjust|modify|implement|build|speed up)\b",
    re.I,
)

# Vagueness signals: a dangling pronoun/object or a bare comparative qualifier.
_VAGUE = re.compile(
    r"\b(it|this|that|them|these|those|thing|things|stuff|everything|"
    r"the (?:code|tests?|bug|issue|app|ui|logic|function|file|thing|stuff)|"
    r"better|cleaner|faster|nicer|properly|somehow|a bit|kinda)\b",
    re.I,
)

MAX_WORDS = 40  # Longer prompts are usually already specified; the value case is short.
SHORT_WORDS = 8  # A short imperative task is under-specified by its own brevity.


def should_rewrite(prompt: str) -> bool:
    """Pure gate — testable without a hook harness. True == emit the nudge.

    Fires on: a short prompt (<= SHORT_WORDS) with an under-specifiable task verb,
    OR any prompt (up to MAX_WORDS) pairing such a verb with a vagueness signal.
    Skips: empty, slash commands, affirmations, option selections, pure questions,
    and long/detailed prompts.
    """
    p = prompt.strip()
    if not p or p.startswith("/"):
        return False
    if _AFFIRMATION.match(p) or _SELECTION.match(p):
        return False

    words = p.split()
    if len(words) > MAX_WORDS:
        return False

    # A pure information question ("what does this do?") is not a task to rewrite.
    # But a polite imperative ("can you fix the tests") carries a task verb, so it
    # is only skipped here when NO task verb is present.
    if p.endswith("?") and re.match(
        r"^(what|why|how|when|where|who|which|whose|is|are|was|were|does|do|did)\b", p, re.I
    ) and not _TASK_VERB.search(p):
        return False

    if not _TASK_VERB.search(p):
        return False

    return len(words) <= SHORT_WORDS or bool(_VAGUE.search(p))


def _emit(body: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": body,
            }
        },
        sys.stdout,
    )


# --- self-test: `python3 prompt-rewrite.py --selftest` --------------------------------
# Behavior pinned as a runnable check that CAN go red (repo ethos: "inert looks
# like working"). Each case is (prompt, expected). A gutted gate fails this.
_FIXTURES = [
    # fire — short imperative task on a vague/unnamed object
    ("the tests are flaky, fix them", True),
    ("refactor this", True),
    ("audit the auth code", True),
    ("make it better", True),
    ("clean up the code", True),
    ("improve performance of the export", True),
    ("handle the edge case", True),
    ("fix that thing from yesterday", True),
    # skip — operational responses
    ("yes", False),
    ("looks good, go ahead", False),
    ("Option 2", False),
    ("#3", False),
    ("the first one", False),
    # skip — not a task / concrete / already specified / question / slash
    ("run the test suite", False),
    ("what does the prompter skill do?", False),
    ("/audit", False),
    (
        "add cursor pagination to the /users endpoint, keep the existing response shape, "
        "add a test for the empty page, and do not touch the DB schema",
        False,
    ),
    ("", False),
]


def _selftest() -> int:
    fails = [
        f"{p!r}: got {should_rewrite(p)}, want {want}"
        for p, want in _FIXTURES
        if should_rewrite(p) != want
    ]
    if fails:
        sys.stderr.write("prompt-rewrite selftest FAILED:\n  " + "\n  ".join(fails) + "\n")
        return 1
    sys.stderr.write(f"prompt-rewrite selftest ok ({len(_FIXTURES)} cases)\n")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    if os.environ.get("PROMPTER", "").strip().lower() in _DISABLED:
        return 0

    # Always drain stdin so the CLI never blocks on an unread pipe.
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        raw = ""
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    if should_rewrite(str(data.get("prompt") or "")):
        _emit(BODY)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never block a turn on a hook failure.
        sys.exit(0)
