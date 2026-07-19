#!/usr/bin/env bash
# vps-sync.sh — pull preset, card, and bot.py from main onto a VPS instance,
# normalize CHARACTER_CARD to the repo card name, restart + enable the service,
# and print verification (hashes + the new STARTUP AUDIT line).
#
# Usage (on the VPS, as root):
#   curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/deploy/vps-sync.sh | bash -s -- <instance>
#
# Mirrors /update's safety: bot.py is compile-checked before the swap and the
# previous copy is kept at bot.py.bak.
set -euo pipefail

INST="${1:?usage: vps-sync.sh <instance>}"
BASE=/opt/telegram-bots
RAW=https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot

# Card mapping mirrors sync-cards.sh (the authoritative list).
case "$INST" in
  nora)   CARD=nora.json ;;
  bonnie) CARD=bonnie.json ;;
  cass)   CARD=cass.json ;;
  emily)  CARD=emily_harper.json ;;
  priya)  CARD=priya.json ;;
  jules)  CARD=jules_nakagawa.json ;;
  *) echo "unknown instance: $INST" >&2; exit 1 ;;
esac

[ -d "$BASE/$INST" ] || { echo "no instance dir at $BASE/$INST" >&2; exit 1; }

echo "[vps-sync] pulling preset.txt, $CARD, bot.py from main..."
curl -fsSL "$RAW/preset.txt" -o "$BASE/$INST/preset.txt"
curl -fsSL "$RAW/$CARD"      -o "$BASE/$INST/$CARD"
curl -fsSL "$RAW/bot.py"     -o "$BASE/bot.py.new"

"$BASE/venv/bin/python" -m py_compile "$BASE/bot.py.new"
cp "$BASE/bot.py" "$BASE/bot.py.bak" 2>/dev/null || true
mv "$BASE/bot.py.new" "$BASE/bot.py"

# Normalize CHARACTER_CARD to the repo filename — a renamed on-device card copy
# silently exempts the instance from every future card deploy (jules, 2026-07-19).
if grep -q '^CHARACTER_CARD=' "$BASE/$INST/.env"; then
  sed -i "s/^CHARACTER_CARD=.*/CHARACTER_CARD=$CARD/" "$BASE/$INST/.env"
else
  echo "CHARACTER_CARD=$CARD" >> "$BASE/$INST/.env"
fi

chown -R bot:bot "$BASE/$INST"
chown bot:bot "$BASE/bot.py"
systemctl restart "bot@$INST"
systemctl enable "bot@$INST" 2>/dev/null || true

sleep 3
echo "--- verification ---"
echo "preset.txt  remote: $(curl -fsSL "$RAW/preset.txt" | sha256sum | cut -d' ' -f1)"
echo "preset.txt  local:  $(sha256sum "$BASE/$INST/preset.txt" | cut -d' ' -f1)"
echo "$CARD  remote: $(curl -fsSL "$RAW/$CARD" | sha256sum | cut -d' ' -f1)"
echo "$CARD  local:  $(sha256sum "$BASE/$INST/$CARD" | cut -d' ' -f1)"
journalctl -u "bot@$INST" -n 60 --no-pager | grep "STARTUP AUDIT" | tail -1 \
  || echo "no STARTUP AUDIT line yet — check: journalctl -u bot@$INST -n 30"
