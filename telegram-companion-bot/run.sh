#!/data/data/com.termux/files/usr/bin/bash
# Runs the bot in this folder, auto-restarting on crash. Use with tmux:
#   tmux new -d -s companion "$HOME/telegram-bot/run.sh"
cd "$HOME/telegram-bot"
termux-wake-lock 2>/dev/null
PY="$HOME/telegram-bot/venv/bin/python"
[ -x "$PY" ] || PY=python
while true; do
    if [ -f bot.log ]; then
        tail -n 2000 bot.log > bot.log.tmp && mv bot.log.tmp bot.log
    fi
    echo "[run] starting bot ($PY) $(date)" >> bot.log
    "$PY" -u bot.py >> bot.log 2>&1
    echo "[run] bot exited (code $?), restarting in 5s — $(date)" >> bot.log
    sleep 5
done
