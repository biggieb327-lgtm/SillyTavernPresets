#!/data/data/com.termux/files/usr/bin/bash
# Pull the latest bot.py + run-bot.sh from the repo and restart all bot instances.
# Usage: bash update-all.sh

set -e

REPO="https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot"
BOT_SRC="$HOME/telegram-bot"

echo "==> Pulling latest bot.py..."
if ! curl -fSL --retry 2 "$REPO/bot.py" -o "$BOT_SRC/bot.py"; then
  echo "    FAILED — curl could not download bot.py. Check network." >&2
  exit 1
fi
echo "    Done ($(grep -m1 '^BOT_VERSION' "$BOT_SRC/bot.py" | cut -d'"' -f2))."

echo "==> Pulling latest run-bot.sh..."
if ! curl -fSL --retry 2 "$REPO/run-bot.sh" -o "$BOT_SRC/run-bot.sh"; then
  echo "    FAILED — curl could not download run-bot.sh. Check network." >&2
  exit 1
fi
echo "    Done."

echo ""
echo "==> Restarting bots..."

# Nora — instance dir is ~/nora-bot (confirmed on-device 2026-07-11 via the STARTUP
# AUDIT "Instance:" line). ~/telegram-bot ($BOT_SRC) is the shared CODE dir (bot.py +
# venv + run-bot.sh), NOT her instance dir — keep the two distinct. Her tmux session
# may be named "nora" or "telegram-bot" depending on how it was first started, so kill
# both before restarting with the supervisor.
NORA_DIR="$HOME/nora-bot"
tmux kill-session -t nora 2>/dev/null || true
tmux kill-session -t telegram-bot 2>/dev/null || true
bash "$BOT_SRC/run-bot.sh" "$NORA_DIR" nora
echo "    nora: restarted"

# Named instances — run-bot.sh <instance-dir> <session-name>
for entry in "bonnie-bot:bonnie" "cass-bot:cass" "emily-bot:emily" "priya-bot:priya" "jules-bot:jules"; do
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
