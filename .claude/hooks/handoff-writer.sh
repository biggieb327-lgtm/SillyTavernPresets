#!/usr/bin/env bash
# PreCompact hook — writes a handoff snapshot before context is compacted, so the
# post-compaction session inherits ground truth instead of a lossy summary alone.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime

out=".claude/.runtime/handoff-$(date +%Y%m%d-%H%M%S).md"
{
  echo "# Handoff (pre-compact, $(date '+%Y-%m-%d %H:%M:%S'))"
  echo
  echo "## Git state"
  echo "branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo '```'
  git status --porcelain 2>/dev/null
  echo '```'
  echo "## Diffstat vs HEAD"
  echo '```'
  git diff --stat HEAD 2>/dev/null | tail -20
  echo '```'
  echo "## Last 15 evidence-log lines"
  echo '```'
  tail -15 ".claude/.runtime/evidence-$(date +%Y%m%d).log" 2>/dev/null || echo "(none)"
  echo '```'
  echo "## For the next context window"
  echo "- Re-read the last operational-log entries: .claude/memory/operational-log.md"
  echo "- Uncommitted work above is REAL and IN PROGRESS — do not discard or re-derive it."
} > "$out"

echo "[handoff-writer] wrote $out"
exit 0
