#!/data/data/com.termux/files/usr/bin/bash
# watchdog.sh — catch everything the in-tmux supervisor can't: Termux itself dying,
# a bot frozen-but-technically-running, or any failure that leaves a tmux session gone.
#
# Two checks per instance, every WATCHDOG_INTERVAL seconds:
#   1. tmux session missing → relaunch via run-bot.sh
#   2. .alive heartbeat file older than WATCHDOG_STALE → kill and relaunch
#      (bot.py touches .alive every 60s via _touch_alive; if it stops, something is
#      wedged — a stuck API call, a deadlocked event loop, a zombie process)
#
# Logs its exact reasoning to watchdog.log before every relaunch so the cause is
# always diagnosable without guessing (the 2026-07-05 debugging session that led to
# this script was only resolved by reading this log).
#
# One-time install on the phone (like backup-all.sh — NOT pulled by update-all.sh):
#   curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/watchdog.sh -o ~/telegram-bot/watchdog.sh
#   chmod +x ~/telegram-bot/watchdog.sh
#
# Run in its own tmux session:
#   tmux new-session -d -s watchdog 'bash ~/telegram-bot/watchdog.sh'
#
# Or via cron (less responsive, but survives tmux being killed):
#   crontab -e   # add:  */5 * * * * bash ~/telegram-bot/watchdog.sh --once >> ~/watchdog.log 2>&1
#
# Tunables (env or ~/.watchdog.conf):
#   WATCHDOG_INTERVAL  seconds between checks (default 300, loop mode only)
#   WATCHDOG_STALE     seconds before .alive is "too old" (default 300)
#   WATCHDOG_LOG       log file path (default ~/telegram-bot/watchdog.log)

set -u

[ -f "$HOME/.watchdog.conf" ] && . "$HOME/.watchdog.conf"

WATCHDOG_INTERVAL="${WATCHDOG_INTERVAL:-300}"
WATCHDOG_STALE="${WATCHDOG_STALE:-300}"
WATCHDOG_LOG="${WATCHDOG_LOG:-$HOME/telegram-bot/watchdog.log}"
BOT_SRC="$HOME/telegram-bot"

_log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$WATCHDOG_LOG"
}

_trim_log() {
  if [ -f "$WATCHDOG_LOG" ] && [ "$(stat -c%s "$WATCHDOG_LOG" 2>/dev/null || echo 0)" -gt 2000000 ]; then
    tail -c 500000 "$WATCHDOG_LOG" > "$WATCHDOG_LOG.tmp" && mv "$WATCHDOG_LOG.tmp" "$WATCHDOG_LOG"
  fi
}

check_instance() {
  local dir="$1" session="$2"
  [ -d "$dir" ] || return

  if ! tmux has-session -t "$session" 2>/dev/null; then
    _log "RELAUNCH $session: session down (tmux session '$session' not found)"
    bash "$BOT_SRC/run-bot.sh" "$dir" "$session"
    return
  fi

  local alive="$dir/.alive"
  if [ -f "$alive" ]; then
    local now age mtime
    now=$(date +%s)
    mtime=$(stat -c%Y "$alive" 2>/dev/null || echo 0)
    age=$((now - mtime))
    if [ "$age" -gt "$WATCHDOG_STALE" ]; then
      _log "RELAUNCH $session: frozen (heartbeat ${age}s old, threshold ${WATCHDOG_STALE}s)"
      tmux kill-session -t "$session" 2>/dev/null || true
      sleep 2
      bash "$BOT_SRC/run-bot.sh" "$dir" "$session"
    fi
  fi
}

run_checks() {
  _trim_log

  # Instance list mirrors update-all.sh (the authoritative list). Nora's instance dir is
  # ~/nora-bot (confirmed on-device 2026-07-11 via the STARTUP AUDIT "Instance:" line) —
  # NOT $BOT_SRC (~/telegram-bot), which is the shared CODE dir. Her tmux session may be
  # named "nora" or "telegram-bot", so check both session names against the same dir.
  local nora_dir="$HOME/nora-bot"
  local nora_up=false
  if tmux has-session -t nora 2>/dev/null; then
    nora_up=true
    check_instance "$nora_dir" "nora"
  elif tmux has-session -t telegram-bot 2>/dev/null; then
    nora_up=true
    check_instance "$nora_dir" "telegram-bot"
  fi
  if [ "$nora_up" = false ]; then
    _log "RELAUNCH nora: session down (neither 'nora' nor 'telegram-bot' tmux session found)"
    bash "$BOT_SRC/run-bot.sh" "$nora_dir" nora
  fi

  for entry in "bonnie-bot:bonnie" "cass-bot:cass" "emily-bot:emily" "priya-bot:priya" "jules-bot:jules"; do
    local dir="$HOME/${entry%%:*}"
    local session="${entry##*:}"
    check_instance "$dir" "$session"
  done
}

if [ "${1:-}" = "--once" ]; then
  run_checks
  exit 0
fi

_log "watchdog started (interval=${WATCHDOG_INTERVAL}s, stale=${WATCHDOG_STALE}s)"
while true; do
  run_checks
  sleep "$WATCHDOG_INTERVAL"
done
