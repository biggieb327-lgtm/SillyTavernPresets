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
# The checkout ALREADY EXISTS — install-vps.sh has maintained one at
# $INSTALL_DIR/.repo since 2026-07-06 (install-vps.sh:33) and chowns it to bot:bot
# (line 69). Do not clone a new one. One-time setup is only the SSH key:
#   ssh-keygen -t ed25519 -f /root/.ssh/stpresets_ro -N ''
#   # add /root/.ssh/stpresets_ro.pub under the repo's Deploy keys, READ-ONLY
#   git -C /opt/telegram-bots/.repo remote set-url origin \
#     git@github.com:biggieb327-lgtm/SillyTavernPresets.git
# See deploy/MIGRATION.md § "Private-repo deploys".
#
# Mirrors /update's safety: bot.py is compile-checked before the swap and the
# previous copy is kept at bot.py.bak.
set -euo pipefail

INST="${1:?usage: vps-sync.sh <instance>}"
BASE=/opt/telegram-bots
REPO="${STPRESETS_REPO:-$BASE/.repo}"
SRC="$REPO/telegram-companion-bot"
GIT_SSH_KEY="${STPRESETS_DEPLOY_KEY:-/root/.ssh/stpresets_ro}"

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
  echo "  install-vps.sh creates it; to make one by hand:" >&2
  echo "  git clone git@github.com:biggieb327-lgtm/SillyTavernPresets.git $REPO" >&2
  echo "  (needs a read-only deploy key — see the header of this script)" >&2
  exit 1
}

[ -f "$GIT_SSH_KEY" ] && export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY -o IdentitiesOnly=yes"

# `git -c safe.directory=` on every call, not a global config change: install-vps.sh
# does `chown -R bot:bot $INSTALL_DIR` (line 69), so the checkout is bot-owned while
# this script runs as root — git refuses that as "dubious ownership". Inline keeps the
# script working on a fresh host with no prior git setup.
GIT="git -c safe.directory=$REPO -C $REPO"
echo "[vps-sync] fetching main into $REPO..."
$GIT fetch --quiet origin main
$GIT reset --quiet --hard origin/main
echo "[vps-sync] checkout now at $($GIT rev-parse --short HEAD)"

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
echo "checkout HEAD:     $($GIT rev-parse --short HEAD)"
echo "preset.txt  repo:  $(sha256sum "$SRC/preset.txt" | cut -d' ' -f1)"
echo "preset.txt  local: $(sha256sum "$BASE/$INST/preset.txt" | cut -d' ' -f1)"
echo "$CARD  repo:  $(sha256sum "$SRC/$CARD" | cut -d' ' -f1)"
echo "$CARD  local: $(sha256sum "$BASE/$INST/$CARD" | cut -d' ' -f1)"
journalctl -u "bot@$INST" -n 60 --no-pager | grep "STARTUP AUDIT" | tail -1 \
  || echo "no STARTUP AUDIT line yet — check: journalctl -u bot@$INST -n 30"

# Seed files (people/projects/schedule/atlas) are deliberately NOT synced above — they
# are living, hand-edited content. But nothing else reports on them either, so a seed
# file added to the repo after an instance already existed never arrives and never
# announces itself. Found 2026-07-28: jules had no atlas.txt on the VPS. bot.py reads
# it once at import and falls back to [] when absent (bot.py:649), and /audit does not
# mention seed files at all, so the only symptom is a character quietly missing her
# geography forever.
#
# Report, never copy. An operator may have removed a seed file deliberately, and an
# absent file cannot be distinguished from an intended one (C10) — so this prints the
# gap and the command, and leaves the decision where it belongs.
seed_missing=""
if [ -d "$SRC/$INST" ]; then
  for sf in "$SRC/$INST"/*.txt; do
    [ -e "$sf" ] || continue
    sb=$(basename "$sf")
    [ -f "$BASE/$INST/$sb" ] || seed_missing="$seed_missing $sb"
  done
fi
if [ -n "$seed_missing" ]; then
  echo "seed files: in repo, MISSING on this instance —$seed_missing"
  for sb in $seed_missing; do
    echo "            cp $SRC/$INST/$sb $BASE/$INST/$sb && chown bot:bot $BASE/$INST/$sb"
  done
elif [ -d "$SRC/$INST" ]; then
  echo "seed files: all repo seed files present on this instance"
else
  echo "seed files: no seed folder in the repo for $INST (nothing to compare)"
fi
