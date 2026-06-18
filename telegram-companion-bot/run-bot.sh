#!/data/data/com.termux/files/usr/bin/bash
# Runs a second (or any named) bot instance in its own tmux session.
# Usage: bash run-bot.sh <instance-folder> [session-name]
#
# Example:
#   bash run-bot.sh ~/bonnie-bot bonnie

INSTANCE_DIR="${1:-}"
SESSION="${2:-bot-$(basename "$INSTANCE_DIR")}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$INSTANCE_DIR/bot.pid"

if [ -z "$INSTANCE_DIR" ]; then
  echo "Usage: bash run-bot.sh <instance-folder> [session-name]"
  exit 1
fi

# Kill any stale process holding the PID file
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing bot (PID $OLD_PID)..."
    kill "$OLD_PID"
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Kill any orphaned process for this specific instance dir
pkill -f "python.*bot\.py.*$(basename "$INSTANCE_DIR")" 2>/dev/null
sleep 1

# Kill existing tmux session so we always start fresh
tmux kill-session -t "$SESSION" 2>/dev/null

echo "Starting bot for instance: $INSTANCE_DIR"
tmux new-session -d -s "$SESSION" -c "$SCRIPT_DIR" \
  "python bot.py '$INSTANCE_DIR' 2>&1 | tee '$INSTANCE_DIR/bot.log'"
echo "Bot started. Attach with: tmux attach -t $SESSION"
