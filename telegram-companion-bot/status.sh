#!/data/data/com.termux/files/usr/bin/bash
# Quick health check of all bot instances at a glance. Usage: bash status.sh
#   SESSION   — is the tmux session alive?
#   HEARTBEAT — how long since the bot last stamped .alive (stale = likely wedged)
#   ERRORS    — error/traceback lines in the last 300 log lines (recent, not all-time)
now=$(date +%s)
printf "%-8s %-8s %-16s %s\n" "BOT" "SESSION" "HEARTBEAT" "RECENT-ERRORS"
printf "%-8s %-8s %-16s %s\n" "---" "-------" "---------" "-------------"
for b in nora bonnie cass emily jules priya; do
  dir="$HOME/$b-bot"
  [ -d "$dir" ] || continue
  if tmux has-session -t "$b" 2>/dev/null; then sess="up"; else sess="DOWN"; fi
  if [ -f "$dir/.alive" ]; then
    age=$(( now - $(stat -c %Y "$dir/.alive" 2>/dev/null || echo "$now") ))
    if   [ "$age" -lt 120 ];  then hb="${age}s ago"
    elif [ "$age" -lt 7200 ]; then hb="$((age/60))m ago"
    else                           hb="$((age/3600))h ago (stale)"; fi
  else
    hb="—"
  fi
  errs=$(tail -300 "$dir/bot.log" 2>/dev/null | grep -ciE "error|traceback|exception" || true)
  printf "%-8s %-8s %-16s %s\n" "$b" "$sess" "$hb" "${errs:-0}"
done
