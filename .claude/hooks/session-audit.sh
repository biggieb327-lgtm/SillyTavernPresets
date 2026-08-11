#!/usr/bin/env bash
# SessionStart hook — model/branch/state audit injected as context at session start.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
last_log=$(grep -m1 '^| 20' .claude/memory/operational-log.md 2>/dev/null || echo "none")

echo "[session-audit] branch=${branch} uncommitted_files=${dirty}"
echo "[session-audit] last operational-log entry: ${last_log}"

# Constraints are only worth keeping if they are read BEFORE the same mistake recurs.
# Surface the repeat offenders (seen: 2+) by name — those are the ones prose has
# already failed to prevent at least once.
if [ -f .claude/memory/constraints.md ]; then
  total=$(grep -c '^### C' .claude/memory/constraints.md 2>/dev/null || echo 0)
  repeats=$(grep -B1 '^\*\*seen: [2-9]' .claude/memory/constraints.md 2>/dev/null \
            | grep '^### C' | sed 's/^### //' | paste -sd '|' - | sed 's/|/ · /g')
  echo "[session-audit] constraints (.claude/memory/constraints.md): ${total} active"
  [ -n "${repeats}" ] && echo "[session-audit] REPEAT MISTAKES — read these first: ${repeats}"
fi
# C22: working off a stale branch is invisible until the push is rejected — a merge-base
# EXISTING is not the same as it being recent enough to trust. One session spent four
# commits re-deriving history `origin/main` already recorded correctly, ~150 commits ahead.
# Read from the LOCAL origin/main ref with no fetch, so this is a lower bound; the ref's
# own age is printed beside it, because a staleness check that hides its own staleness is
# this constraint in miniature (C8).
if [ "${branch}" != "main" ] && git rev-parse --verify -q origin/main >/dev/null 2>&1; then
  base=$(git merge-base HEAD origin/main 2>/dev/null)
  if [ -n "${base}" ]; then
    behind=$(git rev-list --count "${base}..origin/main" 2>/dev/null || echo 0)
    refage=$(git log -1 --format=%cr origin/main 2>/dev/null || echo "unknown")
    if [ "${behind:-0}" -ge 25 ]; then
      echo "[session-audit] WARNING: merge-base is ${behind} commits behind origin/main (local ref, last moved ${refage}) — run 'git fetch origin main' and diff before extended work on shared docs (routines.md, CLAUDE.md, constraints.md, operational-log.md)"
    else
      echo "[session-audit] merge-base ${behind} commit(s) behind origin/main (local ref, last moved ${refage})"
    fi
  fi
fi
# How long since the last recorded session-debrief, in commits of real work. Surfaced HERE
# because SessionStart is the only moment it is actionable — by the end of a session the
# context that would have been harvested is already being compacted away.
# Reports the number and does not judge it: one data point is not a distribution, and
# inventing a "debrief every N commits" threshold from it is the estimate-as-fact trap
# (C8). Add the threshold once .claude/memory/debrief-log.md has enough rows to show one.
if [ -f .claude/memory/debrief-log.md ]; then
  last=$(grep -oE '^\| [0-9-]+ \| [0-9a-f]{7,} \|' .claude/memory/debrief-log.md 2>/dev/null | tail -1)
  lsha=$(printf '%s' "$last" | awk '{print $4}')
  ldate=$(printf '%s' "$last" | awk '{print $2}')
  if [ -n "${lsha:-}" ] && git cat-file -e "${lsha}^{commit}" 2>/dev/null; then
    since=$(git rev-list --count "${lsha}..HEAD" 2>/dev/null || echo '?')
    echo "[session-audit] last session-debrief: ${ldate} (${lsha}), ${since} commit(s) ago — \`bash .claude/tools/debrief-check.sh\` when this session reaches a stopping point"
  fi
fi
echo "[session-audit] standing rules: read telegram-companion-bot/CHANGELOG.md before bot changes; bot.py changes need BOT_VERSION bump + changelog entry (delivery gate blocks otherwise); run .claude/evals/run-evals.sh before claiming done."
if [ "${dirty}" != "0" ]; then
  echo "[session-audit] WARNING: working tree not clean — inspect before assuming a fresh start:"
  git status --porcelain | head -10
fi
exit 0
