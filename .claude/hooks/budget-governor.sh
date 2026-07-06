#!/usr/bin/env bash
# PostToolUse hook — counts tool calls per session; nudges Claude at thresholds.
# Not a hard stop: a governor, not a brake. Thresholds chosen so a normal task never sees one.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime

sid=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("session_id") or "unknown")[:16])' 2>/dev/null) || exit 0
f=".claude/.runtime/budget-${sid}.count"
n=$(( $(cat "$f" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$f"

case "$n" in
  75|150|300)
    echo "[budget-governor] ${n} tool calls this session. Checkpoint: is current work still on the shortest path to the goal? If scope has crept, write a handoff note and re-plan; if progress is real, continue." >&2
    exit 2
    ;;
esac
exit 0
