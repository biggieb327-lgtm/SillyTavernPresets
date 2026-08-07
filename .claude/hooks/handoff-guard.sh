#!/usr/bin/env bash
# Stop hook — operator-handoff hygiene, C1 family, graduated 2026-08-02 after three
# slips in one session that were all in the handoff rather than the work.
#
# SCOPE, stated honestly: same limit as host-guard. The fleet is on a machine this
# container cannot reach and the owner pastes these commands by hand, so nothing here
# can stop a paste into the wrong shell. What this enforces is the agent's half —
# that a block handed over still means what it says on someone else's machine:
#   A. no relative paths after a `cd` (operators paste subsets; the `cd` never ran)
#   B. no bare single-label hostname as an ssh/scp target (prompt hostnames don't route)
#
# host-guard answers "which machine is this for?". This answers "will it work there?".
#
# Escape hatches, per block: `# handoff-ok: relative`, `# handoff-ok: hostname`.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

payload=$(cat)

# Never block twice in a row — avoids infinite stop loops (same guard as host-guard).
active=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null) || exit 0
[ "$active" = "True" ] && exit 0

printf '%s' "$payload" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/handoff_guard.py"
