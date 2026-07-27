#!/usr/bin/env bash
# Stop hook — constraint C1 ("confirm the host before any host-specific command"),
# graduated from prose after seen: 4.
#
# SCOPE, stated honestly: the fleet runs on a VPS the agent cannot reach, and the
# owner runs these commands by hand. Nothing in this container can stop a command
# being pasted into the wrong shell. What this DOES enforce is the half that belongs
# to the agent: every command block it hands over must be unambiguously attributable
# to one host. Four of the C1 incidents began with an unlabelled or mixed block.
#
# Fires on two shapes:
#   A. one fenced block mixing VPS-only and phone-only commands (you cannot run both
#      on one machine in this fleet — this is the shape that wasted the most time)
#   B. a block with host-specific commands while the message never names that host
#
# Escape hatch: put `# host: vps`, `# host: phone`, or `# host: both` in the block.
# A pragma that CONTRADICTS the commands in the block is itself an error and blocks.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

payload=$(cat)

# Never block twice in a row — avoids infinite stop loops (same guard as delivery-gate).
active=$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null) || exit 0
[ "$active" = "True" ] && exit 0

printf '%s' "$payload" | python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/host_guard.py"
