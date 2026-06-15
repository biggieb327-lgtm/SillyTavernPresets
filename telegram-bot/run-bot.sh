#!/data/data/com.termux/files/usr/bin/bash
# Runs a second (or third...) bot off the shared code, auto-restarting on crash.
#   tmux new -d -s bonnie "$HOME/telegram-bot/run-bot.sh $HOME/bonnie-bot"
BOT_HOME="${1:?Usage: run-bot.sh <bot-folder>}"
cd "$HOME/telegram-bot"
termux-wake-lock 2>/dev/null
PY="$HOME/telegram-bot/venv/bin/python"
[ -x "$PY" ] || PY=python
while true; do
    if [ -f "$BOT_HOME/bot.log" ]; then
        tail -n 2000 "$BOT_HOME/bot.log" > "$BOT_HOME/bot.log.tmp" && mv "$BOT_HOME/bot.log.tmp" "$BOT_HOME/bot.log"
    fi
    echo "[run] starting bot ($PY) $(date)" >> "$BOT_HOME/bot.log"
    "$PY" -u bot.py "$BOT_HOME" >> "$BOT_HOME/bot.log" 2>&1
    echo "[run] bot exited (code $?), restarting in 5s — $(date)" >> "$BOT_HOME/bot.log"
    sleep 5
done
