#!/usr/bin/env bash
# count-block.sh — run one hook, and when it blocks (exit 2), add a row to the block tally.
#
#   settings.json:  bash "$CLAUDE_PROJECT_DIR/.claude/hooks/count-block.sh" bash "$CLAUDE_PROJECT_DIR/.claude/hooks/risk-guard.sh"
#
# Why: nothing recorded whether a shipped hook ever caught anything, so a guard that never
# fires and a guard that fires daily looked the same (mycelium 2026-08-23, "no meta-evaluation
# of the learning layer"). Rows land in .claude/.runtime/blocks.log (gitignored, dies with a
# cloud container); `python3 .claude/tools/mechanism-tally.py harvest` folds them into the
# committed .claude/memory/mechanism-tally.tsv at session-debrief.
#
# Contract, pinned by the `block-tally` eval — if this breaks, EVERY wrapped guard breaks:
#   - stdin, stdout, stderr pass straight through to the hook (no capture);
#   - the exit code is the hook's own, always;
#   - a failure to write the row never changes that exit code.
# No `set -e`: the hook's non-zero exit is the payload, not an error here.
# MECHANISM_TALLY=0 turns recording off (break-tests inject defects on purpose).
"$@"
rc=$?
if [ "$rc" -eq 2 ] && [ "${MECHANISM_TALLY:-1}" != "0" ]; then
  d="${CLAUDE_PROJECT_DIR:-.}/.claude/.runtime"
  { mkdir -p "$d" && printf '%s\thook\t%s\n' "$(date -u +%F)" "$(basename "${!#}")" >> "$d/blocks.log"; } 2>/dev/null
fi
exit "$rc"
