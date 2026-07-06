#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash) — blocks a short list of high-blast-radius commands.
# Exit 2 blocks the tool call and feeds stderr back to Claude. Keep this list SHORT and
# precise: a guard that misfires gets disabled, and then guards nothing.
set -u

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0

block() { echo "[risk-guard] BLOCKED: $1" >&2; exit 2; }

# Force-push to main (deploys curl from main; a bad force-push bricks every bot's /update).
if echo "$cmd" | grep -qE 'git push[^|;&]*(--force|-f)[^|;&]*[[:space:]]main([[:space:]]|$)|git push[^|;&]*[[:space:]]main[[:space:]][^|;&]*(--force|-f)'; then
  block "force-push to main. Deploys pull raw files from main; rewrite history there only with explicit user sign-off."
fi

# rm -rf aimed at a root-ish target ( /, ~, ., .. , $HOME ).
if echo "$cmd" | grep -qE 'rm[[:space:]]+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[[:space:]]+(/|~/?|\$HOME|\.|\.\.)([[:space:]]|$)'; then
  block "recursive force-delete of a root-level path. Name the specific directory instead."
fi

# Staging .env files (real bot tokens live in instance .env files; .gitignore protects
# the common paths but 'git add -f' or an unlisted path would still leak).
if echo "$cmd" | grep -qE 'git add[^|;&]*\.env([[:space:]]|$|[^.a-zA-Z])' && ! echo "$cmd" | grep -q '\.env\.example'; then
  block "staging a .env file. Bot tokens and API keys must never be committed; .env.example is the shareable template."
fi

exit 0
