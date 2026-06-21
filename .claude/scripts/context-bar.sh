#!/bin/bash
# Reads context window usage from stdin JSON and prints a color-coded progress bar.
# Claude Code passes session stats as JSON on stdin to the statusLine command.
# Expected fields (tries both naming conventions):
#   input_tokens / tokens_used  +  context_window / tokens_max

set -euo pipefail

# Drain stdin non-blocking; fall back to empty object if nothing arrives.
INPUT=""
if IFS= read -r -t 0.2 line 2>/dev/null; then
    INPUT="$line"
    while IFS= read -r -t 0.05 line 2>/dev/null; do
        INPUT="$INPUT $line"
    done
fi
[ -z "$INPUT" ] && INPUT="{}"

# Extract token counts, trying both naming conventions Claude Code may use.
TOKENS_USED=$(printf '%s' "$INPUT" | jq -r '
    (.input_tokens      // .tokens_used      // .context.input_tokens  // .context.tokens_used  // 0)
    + (.cache_read_tokens // 0)
    + (.cache_creation_tokens // 0)
' 2>/dev/null || echo "0")

TOKENS_MAX=$(printf '%s' "$INPUT" | jq -r '
    .context_window // .tokens_max // .context.context_window // .context.tokens_max // 0
' 2>/dev/null || echo "0")

# Sanitize to integers.
TOKENS_USED=$(printf '%s' "$TOKENS_USED" | grep -Eo '^[0-9]+' || echo "0")
TOKENS_MAX=$(printf '%s' "$TOKENS_MAX"  | grep -Eo '^[0-9]+' || echo "0")

if [ "${TOKENS_MAX:-0}" -le 0 ]; then
    printf 'Context: --'
    exit 0
fi

PCT=$(( TOKENS_USED * 100 / TOKENS_MAX ))
# Clamp to [0, 100]
[ "$PCT" -lt 0   ] && PCT=0
[ "$PCT" -gt 100 ] && PCT=100

# Build 10-char block bar
BAR_WIDTH=10
FILLED=$(( PCT * BAR_WIDTH / 100 ))
BAR=""
i=0
while [ $i -lt $FILLED ]; do
    BAR="${BAR}█"; i=$(( i + 1 ))
done
while [ $i -lt $BAR_WIDTH ]; do
    BAR="${BAR}░"; i=$(( i + 1 ))
done

# Color thresholds:  <50% green  50-69% yellow  ≥70% red
if   [ "$PCT" -lt 50 ]; then COLOR='\033[32m'   # green
elif [ "$PCT" -lt 70 ]; then COLOR='\033[33m'   # yellow
else                         COLOR='\033[31m'   # red
fi
RESET='\033[0m'

printf "${COLOR}Context [${BAR}] ${PCT}%%${RESET}"
