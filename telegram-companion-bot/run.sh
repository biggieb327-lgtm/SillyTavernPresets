#!/data/data/com.termux/files/usr/bin/bash
# Runs the bot in a persistent tmux session on Termux (Android).
# Usage: bash run.sh
# To attach later: tmux attach -t nora

SESSION="nora"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/bot.pid"

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

# Kill any orphaned bot.py processes for this instance
pkill -f "python.*bot\.py$" 2>/dev/null
sleep 1

# Kill existing tmux session so we always start fresh
tmux kill-session -t "$SESSION" 2>/dev/null

echo "Starting bot in tmux session '$SESSION'..."
tmux new-session -d -s "$SESSION" -c "$SCRIPT_DIR" \
  "python bot.py 2>&1 | tee bot.log"
echo "Bot started. Attach with: tmux attach -t $SESSION"
