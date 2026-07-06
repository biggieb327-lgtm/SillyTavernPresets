#!/data/data/com.termux/files/usr/bin/bash
# new-bot.sh — bootstrap a new bot instance in under five minutes.
#
# Creates the instance directory, prompts for .env values, pulls the character card
# and seed files from the repo, and starts the bot under the supervisor.
#
# Usage: bash new-bot.sh <name> [card.json]
#
# Examples:
#   bash new-bot.sh luna luna.json           # new instance with a specific card
#   bash new-bot.sh luna                     # prompts for card name interactively
#
# After setup, add the instance to update-all.sh's loop manually — that list stays
# human-edited and authoritative rather than auto-discovered.

set -eu

REPO="https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot"
BOT_SRC="$HOME/telegram-bot"

if [ $# -lt 1 ]; then
  echo "Usage: bash new-bot.sh <name> [card.json]"
  echo "  e.g. bash new-bot.sh luna luna.json"
  exit 1
fi

NAME="$1"
DIR="$HOME/${NAME}-bot"
CARD="${2:-}"

if [ -d "$DIR" ]; then
  echo "ERROR: $DIR already exists. Remove it first if you want to start fresh."
  exit 1
fi

if [ ! -d "$BOT_SRC" ]; then
  echo "ERROR: $BOT_SRC not found — the home instance must be set up first."
  exit 1
fi

echo "==> Creating instance: $NAME"
mkdir -p "$DIR"

# --- Character card ---
if [ -z "$CARD" ]; then
  read -rp "Character card filename (e.g. luna.json): " CARD
fi
CARD="${CARD:?Card filename required}"

echo "    Pulling $CARD from repo..."
if ! curl -fsSL "$REPO/$CARD" -o "$DIR/$CARD" 2>/dev/null; then
  echo "    Card '$CARD' not found in repo — place it in $DIR manually."
fi

# --- Seed files ---
echo "    Pulling seed files for $NAME (if any)..."
for sf in people.txt projects.txt schedule.txt atlas.txt; do
  curl -fsSL "$REPO/$NAME/$sf" -o "$DIR/$sf" 2>/dev/null && echo "      $sf" || true
done

# --- .env ---
echo ""
echo "    Creating .env (tokens are required, the rest have sensible defaults)."
echo ""

read -rp "TELEGRAM_BOT_TOKEN (from @BotFather): " TOKEN
read -rp "NANOGPT_API_KEY: " APIKEY
read -rp "NANOGPT_MODEL [zai-org/glm-5:thinking]: " MODEL
MODEL="${MODEL:-zai-org/glm-5:thinking}"
read -rp "FALLBACK_MODEL [anthracite-org/magnum-v4-72b]: " FALLBACK
FALLBACK="${FALLBACK:-anthracite-org/magnum-v4-72b}"
read -rp "BOT_TIMEZONE [America/New_York]: " TZ_VAL
TZ_VAL="${TZ_VAL:-America/New_York}"
read -rp "ALLOWED_USERS (comma-separated Telegram user IDs, empty=anyone): " USERS

cat > "$DIR/.env" <<EOF
TELEGRAM_BOT_TOKEN=$TOKEN
NANOGPT_API_KEY=$APIKEY
NANOGPT_MODEL=$MODEL
FALLBACK_MODEL=$FALLBACK
CHARACTER_CARD=$CARD
BOT_TIMEZONE=$TZ_VAL
ALLOWED_USERS=$USERS
EOF

echo ""
echo "    .env written to $DIR/.env"

# --- Start ---
read -rp "Start the bot now? [Y/n]: " START
START="${START:-Y}"
if [[ "$START" =~ ^[Yy] ]]; then
  echo "    Starting $NAME..."
  bash "$BOT_SRC/run-bot.sh" "$DIR" "$NAME"
  echo "    $NAME is running. Follow logs: tail -f $DIR/bot.log"
else
  echo "    Skipped. Start later with: bash $BOT_SRC/run-bot.sh $DIR $NAME"
fi

echo ""
echo "==> Done! Next steps:"
echo "    1. Add this line to update-all.sh's instance loop:"
echo "       \"${NAME}-bot:${NAME}\""
echo "    2. Add the same entry to backup-all.sh if it's installed."
echo "    3. Send /audit to $NAME in Telegram to verify."
