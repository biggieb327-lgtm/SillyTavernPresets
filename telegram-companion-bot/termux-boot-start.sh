#!/data/data/com.termux/files/usr/bin/bash
# Boot launcher for the Termux:Boot addon. Install by copying this file to
#   ~/.termux/boot/termux-boot-start.sh   (chmod +x it; note the name -- it is NOT
#   start-bots.sh, an unrelated and now-removed script)
# and installing the "Termux:Boot" app from F-Droid. On device startup Termux:Boot
# runs every script in ~/.termux/boot/, which brings all the bots back after a reboot.
#
# Launches watchdog.sh in continuous --loop mode, backgrounded and detached from this
# script's own short lifetime, so bots get relaunched not just once at boot but for as
# long as the device stays up. A one-shot check here is not enough: if Android kills
# all of Termux mid-session (not a reboot), nothing would bring the bots back again
# until the next reboot -- the --loop process is what actually catches that case.
#
# Uses setsid (not nohup) to launch the loop: nohup only blocks the SIGHUP signal, it
# does not detach the process into a new session, and on-device testing showed the
# nohup'd loop getting killed anyway when this short-lived launcher script exited --
# Termux/Android's process-group cleanup isn't SIGHUP, so nohup alone didn't help.
# setsid actually starts a new session, fully decoupling the loop from this script's
# process group; confirmed on-device to survive where nohup did not.
termux-wake-lock 2>/dev/null || true
# Give the network and filesystem a moment to settle after boot before starting.
sleep 30
# Idempotent: don't start a second loop if one is already running (e.g. this script
# firing more than once, or a loop that survived from before).
if ! pgrep -f "watchdog.sh --loop" >/dev/null 2>&1; then
  setsid bash "$HOME/telegram-bot/watchdog.sh" --loop >> "$HOME/telegram-bot/watchdog.log" 2>&1 &
  disown
fi
