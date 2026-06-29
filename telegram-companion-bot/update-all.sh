#!/data/data/com.termux/files/usr/bin/bash
# Pull the latest bot.py from the ~/stp-deploy clone and restart all bot instances.
# Usage: bash update-all.sh

set -e

BOT_SRC="$HOME/telegram-bot"
DEPLOY="$HOME/stp-deploy"   # git clone of the working branch (bot.py lives under it)

echo "==> Updating $DEPLOY..."
if [ ! -d "$DEPLOY/.git" ]; then
  echo "    ERROR: $DEPLOY is not a git clone. Create it first, e.g.:"
  echo "    git clone -b claude/push-to-repo-7i2f3c --single-branch \\"
  echo "      https://github.com/biggieb327-lgtm/sillytavernpresets.git $DEPLOY"
  exit 1
fi
git -C "$DEPLOY" pull --ff-only
cp "$DEPLOY/telegram-companion-bot/bot.py" "$BOT_SRC/bot.py"
echo "    bot.py updated from $DEPLOY."

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
