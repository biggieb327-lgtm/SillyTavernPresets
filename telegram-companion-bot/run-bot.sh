#!/data/data/com.termux/files/usr/bin/bash
# Runs a bot instance in its own tmux session under a supervisor that
# auto-restarts it if it ever exits (crash, Android low-memory kill, or a
# PID-lock race on restart). The bot stays up without manual babysitting.
#
# Usage: bash run-bot.sh [instance-folder] [session-name]
#
# Examples:
#   bash run-bot.sh ~/bonnie-bot bonnie     # named instance
#   bash run-bot.sh                         # home instance (no folder arg)

INSTANCE_DIR="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$INSTANCE_DIR" ]; then
  # Expand ~ and make absolute so the supervisor's lock/log paths are stable.
  INSTANCE_DIR="$(cd "$INSTANCE_DIR" 2>/dev/null && pwd)"
  if [ -z "$INSTANCE_DIR" ]; then
    echo "Instance folder not found: $1"
    exit 1
  fi
  STATE_DIR="$INSTANCE_DIR"
  DEFAULT_SESSION="$(basename "$INSTANCE_DIR")"
  RUN_CMD="python bot.py '$INSTANCE_DIR'"
else
  # Home instance: code dir doubles as the instance dir, no folder arg.
  STATE_DIR="$SCRIPT_DIR"
  DEFAULT_SESSION="$(basename "$SCRIPT_DIR")"
  RUN_CMD="python bot.py"
fi

SESSION="${2:-$DEFAULT_SESSION}"
PID_FILE="$STATE_DIR/bot.pid"
LOG_FILE="$STATE_DIR/bot.log"
SUPERVISOR="$STATE_DIR/.supervise.sh"

# Stop any existing live process for this instance and clear its lock.
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Stopping existing bot (PID $OLD_PID)..."
    kill "$OLD_PID"
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Kill any orphaned process for this specific instance, then the old session.
if [ -n "$INSTANCE_DIR" ]; then
  pkill -f "python.*bot\.py.*$(basename "$INSTANCE_DIR")" 2>/dev/null
fi
sleep 1
tmux kill-session -t "$SESSION" 2>/dev/null

# Write the supervisor to its own file so there is no nested-quoting to mangle.
# The unquoted heredoc bakes in the paths/command now; \$ keeps runtime parts
# (process check, date, exit code) literal for the loop to evaluate later.
cat > "$SUPERVISOR" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd '$SCRIPT_DIR'
while true; do
  if [ -f '$PID_FILE' ]; then
    p=\$(cat '$PID_FILE' 2>/dev/null)
    if [ -z "\$p" ] || ! kill -0 "\$p" 2>/dev/null; then rm -f '$PID_FILE'; fi
  fi
  echo "[run-bot] starting $SESSION at \$(date)" | tee -a '$LOG_FILE'
  $RUN_CMD 2>&1 | tee -a '$LOG_FILE'
  echo "[run-bot] $SESSION exited (code \${PIPESTATUS[0]}) at \$(date); restarting in 5s" | tee -a '$LOG_FILE'
  sleep 5
done
EOF
chmod +x "$SUPERVISOR"

echo "Starting supervised bot: ${INSTANCE_DIR:-$SCRIPT_DIR (home)}"
tmux new-session -d -s "$SESSION" -c "$SCRIPT_DIR" "bash '$SUPERVISOR'"
echo "Bot started under supervisor. Attach with: tmux attach -t $SESSION"
