#!/data/data/com.termux/files/usr/bin/bash
# sync-cards.sh — converge every instance's character card and seed files with main.
#
# For each instance, pulls its canonical repo card, the shared preset.txt (voiceprint,
# identical fleet-wide), and the matching seed directory (people.txt, projects.txt,
# schedule.txt, atlas.txt) if one exists in the repo. Never touches state files or bot.py.
#
# CHARACTER_CARD normalization: if an instance's .env names a card other than the repo's
# canonical one (e.g. a renamed local emily.json vs the repo's emily_harper.json), the
# bot loads a local file that card deploys can never reach, silently exempting it from
# every future update (jules 2026-07-19, emily 2026-07-20). This script rewrites the
# .env's CHARACTER_CARD to the canonical name so the bot loads what we deploy. The old
# local card is left on disk (orphaned, not deleted) so the switch stays reversible, and
# a loud warning fires when that old card differs from the repo version.
#
# Usage: bash sync-cards.sh
#        bash sync-cards.sh --dry-run   # show what would be pulled, don't write
#
# After syncing, send /restart to each bot from Telegram to pick up the new files.

set -u

REPO="https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot"
DRY_RUN=false
[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

SEED_FILES="people.txt projects.txt schedule.txt atlas.txt"

pull_file() {
  local url="$1" dest="$2" label="$3"
  if $DRY_RUN; then
    echo "  [dry-run] would pull $label"
    return 0
  fi
  if curl -fsSL "$url" -o "$dest" 2>/dev/null; then
    echo "  pulled $label"
    return 0
  else
    echo "  skip $label (not in repo)"
    return 1
  fi
}

synced=0

# Instance list mirrors update-all.sh. The seed directory name is the character name
# (lowercase), not the card filename — e.g. nora/ not nora.json/.
for entry in "nora-bot:nora:nora.json" "bonnie-bot:bonnie:bonnie.json" "emily-bot:emily:emily_harper.json" "priya-bot:priya:priya.json"; do
  dir="$HOME/${entry%%:*}"
  rest="${entry#*:}"
  name="${rest%%:*}"
  default_card="${rest#*:}"

  [ -d "$dir" ] || { echo "$name: skipped (no $dir)"; continue; }

  # The canonical card is the repo filename from the instance list above — NOT whatever
  # the .env currently says. Read the .env's value only to detect (and correct) drift.
  canonical="$default_card"
  env_card=""
  if [ -f "$dir/.env" ]; then
    env_card=$(grep -m1 '^CHARACTER_CARD=' "$dir/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
  fi

  echo "$name ($canonical):"

  # Normalize a drifted or missing CHARACTER_CARD so the bot loads the card we deploy.
  if [ -f "$dir/.env" ] && [ "$env_card" != "$canonical" ]; then
    if [ -n "$env_card" ]; then
      echo "  !! CHARACTER_CARD=$env_card is not the repo card ($canonical)"
      # If the old local card exists and differs from the repo version, the bot will
      # switch cards on restart — say so loudly; the old file is left for rollback.
      if [ -f "$dir/$env_card" ] && \
         ! curl -fsSL "$REPO/$canonical" 2>/dev/null | diff -q - "$dir/$env_card" >/dev/null 2>&1; then
        echo "  !! local $env_card DIFFERS from repo $canonical — bot switches cards on restart"
        echo "  !! old card left at $dir/$env_card (delete it once you've confirmed the switch)"
      fi
    else
      echo "  !! no CHARACTER_CARD line in .env (bot would fall back to the wrong default)"
    fi
    if $DRY_RUN; then
      echo "  [dry-run] would set CHARACTER_CARD=$canonical in .env"
    elif grep -q '^CHARACTER_CARD=' "$dir/.env"; then
      sed -i "s/^CHARACTER_CARD=.*/CHARACTER_CARD=$canonical/" "$dir/.env"
      echo "  normalized CHARACTER_CARD -> $canonical in .env"
    else
      echo "CHARACTER_CARD=$canonical" >> "$dir/.env"
      echo "  added CHARACTER_CARD=$canonical to .env"
    fi
  fi

  pull_file "$REPO/$canonical" "$dir/$canonical" "$canonical" && synced=$((synced+1))

  # Shared voiceprint preset — same file for every instance (bot.py reads BASE_DIR/preset.txt).
  pull_file "$REPO/preset.txt" "$dir/preset.txt" "preset.txt"

  # Seed files live in a per-character subdirectory in the repo.
  for sf in $SEED_FILES; do
    pull_file "$REPO/$name/$sf" "$dir/$sf" "$name/$sf"
  done
done

echo ""
if $DRY_RUN; then
  echo "Dry run complete — no files written. Run without --dry-run to apply."
else
  echo "Synced $synced card(s). Send /restart to each bot to pick up the new files."
fi
