#!/usr/bin/env bash
# vps-sync.sh — sync preset, card, and bot.py from main onto a VPS instance,
# normalize CHARACTER_CARD to the repo card name, restart + enable the service,
# and print verification (hashes + the new STARTUP AUDIT line).
#
# Usage (on the VPS, as root):
#   /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>
#
# SOURCE OF TRUTH IS A GIT CHECKOUT, not raw.githubusercontent.com (changed
# 2026-07-28). Anonymous raw URLs 404 on a private repo, so every curl-based deploy
# path breaks the moment the repo's visibility changes — including bot.py's own
# /update. A checkout authenticates once, via a read-only deploy key, and behaves
# identically whether the repo is public or private. It also collapses nine separate
# fetch call sites into one working tree, so a partial deploy can no longer leave an
# instance with a new bot.py and a stale card.
#
# One-time setup on the VPS:
#   ssh-keygen -t ed25519 -f /root/.ssh/stpresets_deploy -N ''
#   # add /root/.ssh/stpresets_deploy.pub to the repo's Deploy keys (read-only)
#   git clone git@github.com:biggieb327-lgtm/SillyTavernPresets.git \
#     /opt/telegram-bots/.repo
# See deploy/MIGRATION.md § "Private-repo deploys".
#
# Mirrors /update's safety: bot.py is compile-checked before the swap and the
# previous copy is kept at bot.py.bak.
set -euo pipefail

INST="${1:?usage: vps-sync.sh <instance>}"
BASE=/opt/telegram-bots
REPO="${STPRESETS_REPO:-$BASE/.repo}"
SRC="$REPO/telegram-companion-bot"
GIT_SSH_KEY="${STPRESETS_DEPLOY_KEY:-/root/.ssh/stpresets_deploy}"

# Card mapping mirrors sync-cards.sh (the authoritative list).
case "$INST" in
  nora)   CARD=nora.json ;;
  bonnie) CARD=bonnie.json ;;
  cass)   CARD=cass.json ;;
  emily)  CARD=emily_harper.json ;;
  priya)  CARD=priya.json ;;
  jules)  CARD=jules_nakagawa.json ;;
  marcus) CARD=marcus_calder.json ;;
  *) echo "unknown instance: $INST" >&2; exit 1 ;;
esac

[ -d "$BASE/$INST" ] || { echo "no instance dir at $BASE/$INST" >&2; exit 1; }

# --- refresh the checkout -------------------------------------------------------------
# Fatal if missing: silently falling back to whatever is already on disk would deploy
# stale code while reporting success, which is the failure mode this script exists to
# prevent (bot.py.bak becoming a copy of the new code, 2026-07-25).
[ -d "$REPO/.git" ] || {
  echo "[vps-sync] FATAL: no git checkout at $REPO" >&2
  echo "  git clone git@github.com:biggieb327-lgtm/SillyTavernPresets.git $REPO" >&2
  echo "  (needs a read-only deploy key — see the header of this script)" >&2
  exit 1
}

[ -f "$GIT_SSH_KEY" ] && export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY -o IdentitiesOnly=yes"

echo "[vps-sync] fetching main into $REPO..."
git -C "$REPO" fetch --quiet origin main
git -C "$REPO" reset --quiet --hard origin/main
echo "[vps-sync] checkout now at $(git -C "$REPO" rev-parse --short HEAD)"

# A file named in .env but absent from the repo is fatal on purpose: continuing would
# start the bot missing voice rules or its card, which reads as a model regression
# rather than a failed deploy.
need() {
  [ -f "$SRC/$1" ] || { echo "[vps-sync] FATAL: '$1' is not in the repo" >&2; exit 1; }
}

echo "[vps-sync] syncing preset.txt, $CARD, bot.py..."
need preset.txt; need "$CARD"; need bot.py
cp "$SRC/preset.txt" "$BASE/$INST/preset.txt"
cp "$SRC/$CARD"      "$BASE/$INST/$CARD"
cp "$SRC/bot.py"     "$BASE/bot.py.new"

# Preset LAYERS (v2026-07-25.5): copy exactly the layers THIS instance names in its own
# PRESET_FILES. Self-maintaining — no layer list to keep in sync here.
LAYERS=$(sed -n 's/^[[:space:]]*PRESET_FILES[[:space:]]*=[[:space:]]*//p' \
         "$BASE/$INST/.env" 2>/dev/null | tail -1 | tr -d '"'"'"'' | tr ',' ' ')
for pl in $LAYERS; do
  [ "$pl" = "preset.txt" ] && continue          # already copied above
  echo "[vps-sync] syncing preset layer $pl..."
  need "$pl"
  cp "$SRC/$pl" "$BASE/$INST/$pl"
done

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
echo "checkout HEAD:     $(git -C "$REPO" rev-parse --short HEAD)"
echo "preset.txt  repo:  $(sha256sum "$SRC/preset.txt" | cut -d' ' -f1)"
echo "preset.txt  local: $(sha256sum "$BASE/$INST/preset.txt" | cut -d' ' -f1)"
echo "$CARD  repo:  $(sha256sum "$SRC/$CARD" | cut -d' ' -f1)"
echo "$CARD  local: $(sha256sum "$BASE/$INST/$CARD" | cut -d' ' -f1)"
journalctl -u "bot@$INST" -n 60 --no-pager | grep "STARTUP AUDIT" | tail -1 \
  || echo "no STARTUP AUDIT line yet — check: journalctl -u bot@$INST -n 30"
