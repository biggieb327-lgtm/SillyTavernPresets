#!/data/data/com.termux/files/usr/bin/bash
# Pull the latest bot.py from the repo and restart all bot instances.
# Usage: bash update-all.sh

set -e

REPO="https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot"
BOT_SRC="$HOME/telegram-bot"

echo "==> Pulling latest bot.py..."
curl -fsSL "$REPO/bot.py" -o "$BOT_SRC/bot.py"
echo "    Done."

echo ""
echo "==> Restarting bots..."

# Clear the legacy "telegram-bot" home-instance session if it's still around (older setups
# ran Nora under that name; she now runs as the "nora" session from ~/nora-bot like the rest).
tmux kill-session -t telegram-bot 2>/dev/null || true

# All instances, same pattern: run-bot.sh <instance-dir> <session-name>. run-bot.sh kills the
# old session before relaunching under the supervisor; unbuilt bots are skipped.
for entry in "nora-bot:nora" "bonnie-bot:bonnie" "cass-bot:cass" "emily-bot:emily" "jules-bot:jules" "priya-bot:priya"; do
  dir="$HOME/${entry%%:*}"
  session="${entry##*:}"
  if [ -d "$dir" ]; then
    bash "$BOT_SRC/run-bot.sh" "$dir" "$session"
    echo "    $session: restarted"
  else
    echo "    $session: skipped (no $dir)"
  fi
done

echo ""
echo "==> All done. Active sessions:"
tmux ls
