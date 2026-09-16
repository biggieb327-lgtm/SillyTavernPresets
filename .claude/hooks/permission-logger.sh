#!/bin/bash
# PermissionRequest hook: log each permission prompt for later analysis.
# Appends one pipe-delimited line per event to .claude/memory/permission-prompts.log
# Format: timestamp|tool_name|command_or_args

LOG_DIR="${CLAUDE_PROJECT_DIR:-.}/.claude/memory"
LOG_FILE="$LOG_DIR/permission-prompts.log"

# Only log if the memory directory exists
[ -d "$LOG_DIR" ] || exit 0

INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // .tool_input.pattern // .tool_input.file_path // empty')

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "${TIMESTAMP}|${TOOL_NAME}|${COMMAND}" >> "$LOG_FILE"
