#!/usr/bin/env bash
# debrief-check.sh — mechanically test the `session-debrief` skill's stopping-point
# conditions, so "I ran the debrief" cannot mean "I wrote some paragraphs".
#
#   bash .claude/tools/debrief-check.sh
#
# The skill lists four conditions for a real stopping point. Three are decidable from the
# repo and are checked here. The fourth (CI polled and green for HEAD) needs the GitHub
# API, which this script deliberately does NOT fake — it prints the sha to confirm and
# says plainly that it could not check it. A tool that guessed there would be the exact
# thing this session spent a day removing: a check reporting a green it has not earned.
#
# Exit 0 only if every decidable condition passes. The harvest check is advisory, because
# a session where genuinely nothing went wrong is a real outcome and the skill says to
# report that in one line rather than manufacture findings.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 1

pass=0; fail=0
grn()  { printf '\033[32mok\033[0m    %s\n' "$1"; pass=$((pass + 1)); }
red()  { printf '\033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail + 1)); }
note() { printf '\033[36mnote\033[0m  %s\n' "$1"; }

LEDGER=".claude/memory/debrief-log.md"

# --record appends a row instead of checking. Kept as an explicit flag, not a side effect
# of a passing run: a check that mutates state cannot be run freely to ask "where am I?",
# and a check you hesitate to run is one you stop running.
if [ "${1:-}" = "--record" ]; then
  prev=$(grep -oE '^\| [0-9-]+ \| [0-9a-f]{7,} \|' "$LEDGER" 2>/dev/null | tail -1 | awk '{print $4}')
  head_sha=$(git rev-parse --short HEAD)
  if [ -n "${prev:-}" ]; then
    n=$(git rev-list --count "${prev}..HEAD" 2>/dev/null || echo '?')
  else
    n='?'
  fi
  printf '| %s | %s | %s | |\n' "$(date +%Y-%m-%d)" "$head_sha" "$n" >> "$LEDGER"
  echo "recorded: ${head_sha}, ${n} commit(s) since the previous debrief — add a note by hand"
  exit 0
fi

echo "── debrief-check ───────────────────────────────────────────────"

# --- 1. nothing uncommitted --------------------------------------------------------------
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [ "$dirty" = "0" ]; then
  grn "clean     working tree has no uncommitted changes"
else
  red "clean     ${dirty} uncommitted file(s) — the debrief's own output is not saved yet"
  git status --porcelain | head -8 | sed 's/^/        /'
fi

# --- 2. merged to main -------------------------------------------------------------------
# Read the LOCAL origin/main ref and print its age, the same honesty session-audit.sh uses:
# a staleness check that hides its own staleness is the defect it exists to catch.
head_sha=$(git rev-parse HEAD 2>/dev/null)
if git rev-parse --verify -q origin/main >/dev/null 2>&1; then
  main_sha=$(git rev-parse origin/main)
  refage=$(git log -1 --format=%cr origin/main 2>/dev/null)
  if [ "$head_sha" = "$main_sha" ]; then
    grn "merged    HEAD == origin/main (${head_sha:0:7}, ref last moved ${refage})"
  else
    ahead=$(git rev-list --count "${main_sha}..${head_sha}" 2>/dev/null || echo '?')
    red "merged    HEAD is ${ahead} commit(s) ahead of origin/main — work is not merged"
  fi
else
  red "merged    no origin/main ref — cannot tell whether anything was pushed"
fi

# --- 3. the verification block ------------------------------------------------------------
if out=$(bash .claude/tools/verify.sh --quick 2>&1); then
  grn "verify    $(printf '%s' "$out" | grep -E '^verify:' | head -1)"
else
  red "verify    verify.sh is RED — a debrief over failing checks records fiction"
  printf '%s\n' "$out" | grep -E 'FAIL' | head -6 | sed 's/^/        /'
fi

# --- 4. did the debrief actually harvest anything? (advisory) ------------------------------
today=$(date +%Y-%m-%d)
commits=$(git log --since="${today} 00:00" --oneline 2>/dev/null | wc -l | tr -d ' ')
# NOT `grep -c … || echo 0`. `grep -c` prints "0" AND exits 1 when there are no matches,
# so the fallback stacks a second line on real output and the arithmetic below dies with
# "syntax error in expression". That is C23's own shape — a fallback firing on a command
# that already succeeded at printing — and it happened while writing the tool that enforces
# C23. Left as a comment because the wrong form reads perfectly well.
minor=$(grep -c "^- ${today} —" .claude/memory/constraints.md 2>/dev/null); minor=${minor:-0}
oplog=$(grep -c "^| ${today} |" .claude/memory/operational-log.md 2>/dev/null); oplog=${oplog:-0}
if [ "$commits" = "0" ]; then
  note "harvest   no commits today — nothing to harvest"
elif [ "$((minor + oplog))" -gt 0 ]; then
  grn "harvest   ${commits} commit(s) today, ${minor} Minor + ${oplog} operational-log entr(ies)"
else
  note "harvest   ${commits} commit(s) today but NO memory-layer entry dated ${today}."
  note "          Advisory, not a failure: a session where nothing went wrong is a real"
  note "          outcome. But a long session with zero recorded slips usually means the"
  note "          near-misses went unwritten, which is what the skill exists to prevent."
fi

# --- the one thing this cannot check ------------------------------------------------------
note "ci        NOT CHECKED — confirm ${head_sha:0:7} is 'completed | success' on main by hand."
note "          This script has no GitHub access and will not guess; an unearned green here"
note "          is the failure the whole session was about."

echo "────────────────────────────────────────────────────────────────"
if [ "$fail" -eq 0 ]; then
  echo "debrief-check: ${pass} decidable condition(s) green — CI still needs confirming"
else
  echo "debrief-check: ${fail} FAILED, ${pass} green — not a stopping point yet"
fi
[ "$fail" -eq 0 ]
