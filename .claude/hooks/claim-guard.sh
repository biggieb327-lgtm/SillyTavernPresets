#!/usr/bin/env bash
# Stop hook — C8 family, graduated 2026-08-02 on the owner's stated trigger (a third
# occurrence of asserting-without-verifying).
#
# SCOPE: catches one slice of that family — claiming two artifacts are the same on
# metadata (dimensions, file size, format) rather than a hash. That slice has a
# mechanical signature; the rest of the family does not, and stays prose in C8.
#
# Escape hatch: `# claim-ok` anywhere in the message. A hash mentioned anywhere in the
# message also satisfies it, since that is how the comparison would be reported.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
payload=$(cat)
active=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null) || exit 0
[ "$active" = "True" ] && exit 0
printf '%s' "$payload" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/claim_guard.py"
