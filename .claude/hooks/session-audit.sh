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
echo "[session-audit] standing rules: read telegram-companion-bot/CHANGELOG.md before bot changes; bot.py changes need BOT_VERSION bump + changelog entry (delivery gate blocks otherwise); run .claude/evals/run-evals.sh before claiming done."
if [ "${dirty}" != "0" ]; then
  echo "[session-audit] WARNING: working tree not clean — inspect before assuming a fresh start:"
  git status --porcelain | head -10
fi
exit 0
