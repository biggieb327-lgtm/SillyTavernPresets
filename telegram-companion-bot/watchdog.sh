#!/data/data/com.termux/files/usr/bin/bash
# Watchdog: make sure every bot has a live tmux session, relaunching any that
# are missing. This catches the failure the in-tmux supervisor cannot -- when
# the tmux session itself (or all of Termux) was killed by Android, the
# supervisor loop dies with it and nothing brings the bot back.
#
# Usage:
#   bash watchdog.sh           one-shot check (for termux-job-scheduler / cron / boot)
#   bash watchdog.sh --loop    run forever, re-checking every $WATCHDOG_INTERVAL seconds
#
# It is safe to run at any time: a bot whose session is already up is left
# untouched; only missing sessions are (re)launched.
#
# To add or remove a bot, edit the BOTS list below. Format: session:instance-dir
# (a line whose instance-dir does not exist is skipped, so unbuilt bots are fine).
set -u
BOT_SRC="$HOME/telegram-bot"
LOG="$BOT_SRC/watchdog.log"
INTERVAL="${WATCHDOG_INTERVAL:-300}"
# A bot whose .alive heartbeat is older than this (seconds) is treated as frozen and
# restarted even if its tmux session still exists. The bot stamps .alive every 60s.
STALE="${WATCHDOG_STALE:-300}"

BOTS="
nora:$HOME/nora-bot
bonnie:$HOME/bonnie-bot
cass:$HOME/cass-bot
emily:$HOME/emily-bot
jules:$HOME/jules-bot
priya:$HOME/priya-bot
"

check_once() {
  now=$(date +%s)
  for entry in $BOTS; do
    session="${entry%%:*}"
    dir="${entry##*:}"
    [ -d "$dir" ] || continue
    reason=""
    if ! tmux has-session -t "$session" 2>/dev/null; then
      reason="session down"
    else
      # Session is up -- check the heartbeat to catch a frozen-but-alive bot.
      # A missing .alive is left alone (old bot.py, or just-started): only a
      # heartbeat that exists and has gone stale counts as a hang.
      alive="$dir/.alive"
      if [ -f "$alive" ]; then
        mtime=$(stat -c %Y "$alive" 2>/dev/null || echo "$now")
        age=$(( now - mtime ))
        if [ "$age" -gt "$STALE" ]; then
          reason="frozen (heartbeat ${age}s old)"
        fi
      fi
    fi
    [ -n "$reason" ] || continue
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $session $reason -> relaunching" >> "$LOG"
    bash "$BOT_SRC/run-bot.sh" "$dir" "$session" >> "$LOG" 2>&1
  done
}

if [ "${1:-}" = "--loop" ]; then
  termux-wake-lock 2>/dev/null || true
  while true; do
    check_once
    sleep "$INTERVAL"
  done
else
  check_once
fi
