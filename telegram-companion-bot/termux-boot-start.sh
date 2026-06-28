#!/data/data/com.termux/files/usr/bin/bash
# Boot launcher for the Termux:Boot addon. Install by copying this file to
#   ~/.termux/boot/start-bots.sh   (chmod +x it)
# and installing the "Termux:Boot" app from F-Droid. On device startup Termux:Boot
# runs every script in ~/.termux/boot/, which brings all the bots back after a reboot.
#
# It just hands off to watchdog.sh, which launches any bot that isn't already up.
termux-wake-lock 2>/dev/null || true
# Give the network and filesystem a moment to settle after boot before starting.
sleep 30
bash "$HOME/telegram-bot/watchdog.sh"
