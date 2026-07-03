#!/usr/bin/env bash
# config-drift-check.sh — find env-var drift between code and .env.example (REPO-SIDE).
#
# Lists (a) env vars read by bot.py / bot_app but never mentioned in .env.example
# (undocumented knobs), and (b) vars in .env.example that no code reads (phantom or
# renamed — the classic "I set X and nothing changed" cause).
#
# Usage:
#   bash .claude/skills/companion-bot-diagnostics/scripts/config-drift-check.sh
#
# Notes:
# - Code vars are extracted from two real patterns: os.getenv("NAME") — matched
#   across line breaks, since a few calls wrap (SAFETY_RESOURCES, PAYMENTS_ENABLED) —
#   and the sampling-knob table entries ("key", "NAME", type) that bot.py reads in a
#   loop near line 130. bot.py/bot_app use no other env-read pattern (verify with:
#   grep -n 'os.environ' bot.py — no hits).
# - .env.example documents most vars as commented "# NAME=value" lines, so commented
#   entries count as documented.
# - Not every "undocumented" var is a bug: some are internal (BOT_HOME is set by the
#   launcher, WATCHDOG_STALE/WATCHDOG_INTERVAL belong to watchdog.sh). Judge each hit.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DIR="$ROOT/telegram-companion-bot"
ENV_EXAMPLE="$DIR/.env.example"
if [ ! -f "$DIR/bot.py" ] || [ ! -f "$ENV_EXAMPLE" ]; then
  echo "expected $DIR/bot.py and $ENV_EXAMPLE" >&2
  exit 1
fi

# -z treats each file as one record so os.getenv( calls that wrap lines still match.
GETENV_VARS="$(grep -rhozE 'os\.getenv\(\s*"[A-Z][A-Z0-9_]*"' "$DIR/bot.py" "$DIR/bot_app" 2>/dev/null \
  | tr '\0\n' '  ' | grep -oE '"[A-Z][A-Z0-9_]*"' | tr -d '"')"
# Sampling knobs are read via a table loop: ("temperature", "TEMPERATURE", float), ...
TABLE_VARS="$(grep -hoE '\("[a-z_]+", "[A-Z][A-Z0-9_]*", (float|int|str)\)' "$DIR/bot.py" \
  | grep -oE '"[A-Z][A-Z0-9_]*"' | tr -d '"')"
CODE_VARS="$(printf '%s\n%s\n' "$GETENV_VARS" "$TABLE_VARS" | grep -v '^$' | sort -u)"
DOC_VARS="$(grep -hoE '^[# ]*[A-Z][A-Z0-9_]*=' "$ENV_EXAMPLE" \
  | sed -E 's/^[# ]*([A-Z0-9_]+)=/\1/' | sort -u)"

echo "== Read by code but NOT in .env.example (undocumented; check if internal) =="
comm -23 <(printf '%s\n' "$CODE_VARS") <(printf '%s\n' "$DOC_VARS")
echo
echo "== In .env.example but NOT read by any code (phantom / renamed var) =="
comm -13 <(printf '%s\n' "$CODE_VARS") <(printf '%s\n' "$DOC_VARS")
echo
echo "(code reads $(printf '%s\n' "$CODE_VARS" | wc -l) distinct vars; .env.example lists $(printf '%s\n' "$DOC_VARS" | wc -l))"
