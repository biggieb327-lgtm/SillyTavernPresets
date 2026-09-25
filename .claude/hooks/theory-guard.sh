#!/usr/bin/env bash
# Stop hook — C5: label a theory as a theory until evidence arrives.
#
# SCOPE: catches one slice — asserting what a named function does without hedging.
# Since 2026-09-25 a code-shaped claim is checked against the session transcript:
# run earlier this session -> pass; only read, or never seen -> block (theory_guard.py
# docstring has the rules and limits). The general case (diagnosing an incident and
# stating a cause as fact) has no mechanical signature.
#
# Verify cheaply: python3 .claude/tools/probe.py 'bot.<fn>(...)'
# Escape hatch: `# theory-ok` anywhere in the message. Hedging language
# ("probably", "I think", "[hypothesis]", "source-traced") also satisfies it.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
payload=$(cat)
active=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null) || exit 0
[ "$active" = "True" ] && exit 0
printf '%s' "$payload" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/theory_guard.py"
