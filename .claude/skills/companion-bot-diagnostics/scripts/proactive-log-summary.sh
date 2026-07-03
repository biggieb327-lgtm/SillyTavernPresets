#!/data/data/com.termux/files/usr/bin/bash
# proactive-log-summary.sh — quantify one bot's log: per-tag counts, heartbeat
# outcome breakdown, proactive sends, restarts, errors. DEVICE-SIDE.
#
# DELIVERY: this file uses $ internally, so it must reach the phone as a FILE
# (copy it into ~/stp-deploy or have the owner save it via nano) — never pasted
# through chat. The invocation line below is dollar-free and safe to send in chat:
#
#   bash ~/telegram-bot/proactive-log-summary.sh ~/nora-bot/bot.log
#
# Arg 1: path to a bot.log (default ~/nora-bot/bot.log). Remember bot.log rotates
# at ~5 MB to bot.log.1 — run it on bot.log.1 too for the fuller picture.

LOG="${1:-$HOME/nora-bot/bot.log}"
if [ ! -f "$LOG" ]; then
  echo "No such log: $LOG"
  exit 1
fi

echo "== $LOG ($(wc -c < "$LOG") bytes) =="
echo
echo "-- per-tag line counts (this file only; rotation caps history at ~5 MB) --"
grep -oE '^\[[a-z][a-z0-9 #._-]*\]' "$LOG" | sort | uniq -c | sort -rn
echo
echo "-- heartbeat outcome breakdown --"
for pat in "next check in" "Proactive message sent" "Owner recently active" \
           "Quiet hours" "User /quiet active" "Nudge budget exhausted" \
           "Mood is low" "No owner yet" "Error"; do
  n=$(grep -c "^\[heartbeat\] $pat" "$LOG") || true
  printf "  %-26s %s\n" "$pat" "${n:-0}"
done
echo
echo "-- other proactive-send evidence --"
for pat in "\[followup\] scheduled" "\[stress\] high-stress check-in sent" \
           "\[bb\] low-energy check-in sent" "\[rhr\] elevated resting-HR check-in" \
           "\[onthisday\] resurfaced" "\[event\] scheduled" "\[draft\] Saved unsent thought"; do
  n=$(grep -c "^$pat" "$LOG") || true
  printf "  %-42s %s\n" "${pat//\\/}" "${n:-0}"
done
echo
echo "-- process restarts ([run-bot] starting lines, each carries a date) --"
grep -c "^\[run-bot\] starting" "$LOG" || true
grep "^\[run-bot\] starting" "$LOG" | tail -3
echo
echo "-- error/traceback/exception lines (whole file) --"
grep -ciE "error|traceback|exception" "$LOG" || true
tail -300 "$LOG" | grep -iE "error|traceback|exception" | tail -3
