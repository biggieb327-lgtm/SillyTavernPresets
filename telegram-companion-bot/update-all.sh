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
# Stash any stray local changes so a fast-forward pull can't be silently blocked by them.
if [ -n "$(git -C "$DEPLOY" status --porcelain)" ]; then
  echo "    Stray changes in $DEPLOY — stashing them so the pull can proceed."
  git -C "$DEPLOY" stash push -u -m "update-all autostash $(date '+%Y-%m-%d %H:%M')" || true
fi

# Pull, and STOP LOUDLY if it fails — the old trap was set -e aborting here, leaving stale code.
if ! git -C "$DEPLOY" pull --ff-only; then
  echo "    ERROR: pull failed (branch diverged?). Fix by hand:"
  echo "      git -C $DEPLOY status"
  echo "      git -C $DEPLOY fetch && git -C $DEPLOY reset --hard @{u}   # if you want to discard local"
  exit 1
fi

cp "$DEPLOY/telegram-companion-bot/bot.py" "$BOT_SRC/bot.py"
# Verify the copy actually landed (matches the clone) — catch a silent stale deploy.
if ! cmp -s "$DEPLOY/telegram-companion-bot/bot.py" "$BOT_SRC/bot.py"; then
  echo "    ERROR: deployed bot.py does not match $DEPLOY — copy failed. Aborting."
  exit 1
fi

# Sync the helper scripts too, so a single run is always complete. (update-all.sh itself is
# left out on purpose — overwriting the running script mid-run is unsafe; copy it by hand.)
for f in run-bot.sh watchdog.sh start-bots.sh status.sh; do
  src="$DEPLOY/telegram-companion-bot/$f"
  if [ -f "$src" ]; then
    cp "$src" "$BOT_SRC/$f"
    chmod +x "$BOT_SRC/$f"
  fi
done
echo "    ✓ Deployed bot.py ($(wc -l < "$BOT_SRC/bot.py") lines) + helper scripts from $DEPLOY."

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
