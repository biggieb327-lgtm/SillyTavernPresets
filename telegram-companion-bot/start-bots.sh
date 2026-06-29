#!/bin/bash
pkill -f bot.py 2>/dev/null
sleep 1
for s in emily bonnie nora cass priya jules; do tmux kill-session -t $s 2>/dev/null; done

tmux new-session -d -s emily  'python -u ~/telegram-bot/bot.py ~/emily-bot'
tmux new-session -d -s bonnie 'python -u ~/telegram-bot/bot.py ~/bonnie-bot'
tmux new-session -d -s nora   'python -u ~/telegram-bot/bot.py ~/nora-bot'
tmux new-session -d -s cass   'python -u ~/telegram-bot/bot.py ~/cass-bot'
tmux new-session -d -s priya  'python -u ~/telegram-bot/bot.py ~/priya-bot'
tmux new-session -d -s jules  'python -u ~/telegram-bot/bot.py ~/jules-bot'
