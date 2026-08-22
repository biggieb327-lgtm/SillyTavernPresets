#!/usr/bin/env bash
# Stop hook — surfaces which of the 6 prose-only constraints are relevant to
# the current diff. Advisory only — exit 0 always.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
# Consume stdin (Stop hook payload) so it doesn't interfere.
cat > /dev/null
bash "$CLAUDE_PROJECT_DIR/.claude/tools/prose-constraint-check.sh" >&2
exit 0
