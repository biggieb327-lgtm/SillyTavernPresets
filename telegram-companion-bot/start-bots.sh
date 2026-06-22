#!/bin/bash
pkill -f bot.py 2>/dev/null
sleep 1
for s in emily bonnie nora cass priya; do tmux kill-session -t $s 2>/dev/null; done

tmux new-session -d -s emily  'python ~/telegram-bot/bot.py ~/emily-bot'
tmux new-session -d -s bonnie 'python ~/telegram-bot/bot.py ~/bonnie-bot'
tmux new-session -d -s nora   'python ~/telegram-bot/bot.py ~/nora-bot'
tmux new-session -d -s cass   'python ~/telegram-bot/bot.py ~/cass-bot'
tmux new-session -d -s priya  'python ~/telegram-bot/bot.py ~/priya-bot'
