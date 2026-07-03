#!/usr/bin/env bash
# enumerate-log-tags.sh — re-derive the bracketed log-tag list from bot.py (REPO-SIDE).
#
# bot.py logs by convention with print("[tag] ...") / print(f"[tag] ..."). This script
# extracts every such tag so the tag table in SKILL.md can be checked for staleness.
#
# Usage:
#   bash .claude/skills/companion-bot-diagnostics/scripts/enumerate-log-tags.sh [path-to-bot.py]
#
# Default bot.py: <repo-root>/telegram-companion-bot/bot.py (repo root found via git).
# Output: count per tag, then the bot.py line numbers where it is printed.
set -euo pipefail

BOT_PY="${1:-}"
if [ -z "$BOT_PY" ]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  BOT_PY="$ROOT/telegram-companion-bot/bot.py"
fi
if [ ! -f "$BOT_PY" ]; then
  echo "bot.py not found: $BOT_PY" >&2
  exit 1
fi

echo "== bracketed log tags in $BOT_PY =="
grep -nE 'print\(f?"\[' "$BOT_PY" \
  | sed -E 's/^([0-9]+):.*print\(f?"(\[[^]]*\]).*/\1 \2/' \
  | awk '{lines[$2] = lines[$2] ", " $1; count[$2]++}
         END {for (t in count) printf "%3d  %-16s lines %s\n", count[t], t, substr(lines[t], 3)}' \
  | sort -rn -k1,1
echo
echo "total tagged print sites: $(grep -cE 'print\(f?"\[' "$BOT_PY")"
