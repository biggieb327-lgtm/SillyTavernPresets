#!/data/data/com.termux/files/usr/bin/bash
# Runs the bot in a persistent tmux session on Termux (Android).
# Usage: bash run.sh
# To attach later: tmux attach -t priya

SESSION="nora"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attaching..."
  tmux attach -t "$SESSION"
else
  echo "Starting new tmux session '$SESSION'..."
  tmux new-session -d -s "$SESSION" -c "$SCRIPT_DIR" \
    "python bot.py 2>&1 | tee bot.log"
  echo "Bot started. Attach with: tmux attach -t $SESSION"
fi
