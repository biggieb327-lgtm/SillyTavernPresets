#!/usr/bin/env bash
# Stop hook — C25: a push to `main` is not done until CI for that SHA has been read.
#
# After the last successful `git push … main` this session, ending the turn needs one of:
# a later tool result showing the SHA with "completed" (CI read), a background poller on
# GitHub Actions still waiting (its notification not yet in), or `ci-ok: <reason>` in the
# reply. ci_read_guard.py's docstring has the rules; its --selftest pins them.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
printf '%s' "$(cat)" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ci_read_guard.py"
