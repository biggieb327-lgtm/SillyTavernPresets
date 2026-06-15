#!/data/data/com.termux/files/usr/bin/bash
# Runs a second (or any named) bot instance in its own tmux session.
# Usage: bash run-bot.sh <instance-folder> [session-name]
#
# Example:
#   bash run-bot.sh ~/luna-bot luna
#
# The instance folder must contain its own .env (with TELEGRAM_BOT_TOKEN etc.)
# and optionally its own character card (priya.json or any .json card).

INSTANCE_DIR="${1:-}"
SESSION="${2:-bot-$(basename "$INSTANCE_DIR")}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$INSTANCE_DIR" ]; then
  echo "Usage: bash run-bot.sh <instance-folder> [session-name]"
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attaching..."
  tmux attach -t "$SESSION"
else
  echo "Starting bot for instance: $INSTANCE_DIR"
  tmux new-session -d -s "$SESSION" -c "$SCRIPT_DIR" \
    "python bot.py '$INSTANCE_DIR' 2>&1 | tee '$INSTANCE_DIR/bot.log'"
  echo "Bot started. Attach with: tmux attach -t $SESSION"
fi
