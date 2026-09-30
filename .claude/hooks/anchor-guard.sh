#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash) — constraint C7, the mechanically-detectable half:
# in-place edits addressed by LINE NUMBER against a file under version control.
#
# Line numbers are stale the moment anything above them changes. On 2026-07-27 a
# Routine prompt was spliced into routines.md using indexes read off `sed` output; they
# were off by one, and the surrounding file had already been edited twice that session.
#
# DELIBERATELY NARROW. It fires only on `sed -i` carrying a numeric address, because
# that shape is unambiguous. It does NOT catch line-index splicing inside a Python
# heredoc — detecting `readlines()` + slice + write reliably is not possible without
# false positives, and risk-guard.sh's rule applies: a guard that misfires gets
# disabled, and then guards nothing. That half stays prose in constraints.md.
#
# Content-anchored substitution (`sed -i 's/old/new/'`) is untouched — that is the
# correct form and is used constantly for version bumps.
#
# Escape hatch: put `# anchor-ok` in the command.
set -u

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null) || exit 0

case "$cmd" in *anchor-ok*) exit 0 ;; esac

# Checked one command segment at a time (split on && || ; | and newlines). Until
# 2026-09-30 the throwaway-dir exemption was tested against the WHOLE command, so
# `sed -i '21s/…/' tests/x.py && V=/tmp/…/venv` passed: the /tmp path belonged to a
# different segment (C7 occurrence 7).
blocked=0
while IFS= read -r seg; do
  # An in-place sed…
  echo "$seg" | grep -qE '\bsed\b.*(-i([^ ]*)?|--in-place)' || continue
  # …whose script begins with a line number (5d / 5,10d / 115p / 3i\ / 1,3s/…)…
  echo "$seg" | grep -qE "['\"][[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9\$]+)?[[:space:]]*[acdipsr]" || continue
  # …targeting something outside the throwaway dirs, in this same segment.
  echo "$seg" | grep -qE '(/tmp/|scratchpad)' && continue
  blocked=1
done < <(printf '%s\n' "$cmd" | sed -E 's/(&&|\|\||;|\|)/\n/g')
[ "$blocked" = 1 ] || exit 0

cat >&2 <<'MSG'
[anchor-guard] BLOCKED: constraint C7 — in-place sed addressed by line number.

Line numbers are stale the moment anything above them changes; this exact shape
spliced a Routine prompt one line off on 2026-07-27.

Use instead:
  - the Edit tool (matches on a unique surrounding string, so it cannot drift), or
  - a content-anchored sed: sed -i 's/<unique text>/<replacement>/'

If the line address is genuinely correct and intended, add `# anchor-ok` to the command.
MSG
exit 2
