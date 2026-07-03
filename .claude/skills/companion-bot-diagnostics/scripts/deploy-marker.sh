#!/usr/bin/env bash
# deploy-marker.sh — produce an on-device deploy-confirmation check (REPO-SIDE).
#
# Prints the HEAD short hash, the last commit that touched bot.py, the expected
# deployed line count, and a paste-safe MARKER line unique to the current bot.py
# (chosen from lines ADDED by that last commit, filtered to survive the owner's
# chat client: no $, no quotes, no backslash/backtick). Ends with the ready-to-send
# zero-dollar device command: grep count 1 = deploy landed, 0 = stale bot.py.
#
# Usage:
#   bash .claude/skills/companion-bot-diagnostics/scripts/deploy-marker.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BOT_PY="telegram-companion-bot/bot.py"

HEAD_SHORT="$(git log -1 --format=%h)"
LAST="$(git log -n1 --format=%h -- "$BOT_PY")"
LAST_SUBJ="$(git log -n1 --format=%s -- "$BOT_PY")"
LINES="$(wc -l < "$BOT_PY")"

echo "HEAD: $HEAD_SHORT"
echo "Last commit touching bot.py: $LAST  ($LAST_SUBJ)"
echo "Expected deployed line count: $LINES   (update-all.sh prints this after copying)"

# Candidate markers: lines added in $LAST, paste-safe, 25-70 chars trimmed, and
# occurring exactly once in the current file (so grep -c 1/0 is a clean verdict).
MARKER=""
while IFS= read -r line; do
  n="$(grep -cF "$line" "$BOT_PY")" || true
  if [ "$n" = "1" ]; then
    MARKER="$line"
    break
  fi
done < <(git show "$LAST" -- "$BOT_PY" \
  | grep -E '^\+[^+]' | cut -c2- \
  | grep -vE '[$"'\''\\`]' \
  | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//' \
  | awk 'length($0) >= 25 && length($0) <= 70' || true)

echo
if [ -z "$MARKER" ]; then
  echo "No paste-safe unique marker line in $LAST. Fall back to the line-count check;"
  echo "send the owner (zero-dollar):"
  echo "  wc -l ~/telegram-bot/bot.py"
  echo "and compare against $LINES."
  exit 0
fi

echo "Marker line (added in $LAST, unique in current bot.py):"
echo "  $MARKER"
echo
echo "Send the owner this zero-dollar command (reply 1 = deploy landed, 0 = stale):"
echo "  grep -cF '$MARKER' ~/telegram-bot/bot.py"
