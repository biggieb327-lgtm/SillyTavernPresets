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

# git checkout/restore on a path that currently holds uncommitted changes (constraints.md
# C15, seen: 2 — destroyed ~700 lines once, wiped a whole commit's worth of uncommitted
# work once). `git checkout -- <file>` / `git restore <file>` silently discard the working
# copy in favor of the last commit; on a clean file that's a no-op, on a dirty one it's
# unrecoverable, and the two look identical until it's too late. Only fires when the
# target actually has a diff right now -- a branch checkout (no matching file) or a
# checkout of an already-clean file is not what C15 is about.
if echo "$cmd" | grep -qE '\bgit[[:space:]]+(checkout|restore)[[:space:]]'; then
  rest=$(echo "$cmd" | sed -E 's/.*\bgit[[:space:]]+(checkout|restore)[[:space:]]+//')
  for tok in $rest; do
    case "$tok" in
      -*) continue ;;  # flags (--, --staged, -b, ...) are never the target path
    esac
    if [ -f "$tok" ] && ! git diff --quiet -- "$tok" 2>/dev/null; then
      block "git checkout/restore on '$tok', which has uncommitted changes right now (constraints.md C15). This discards them silently and unrecoverably. Re-edit back to the original text instead -- if the changes are real work, commit first."
    fi
  done
fi

exit 0
