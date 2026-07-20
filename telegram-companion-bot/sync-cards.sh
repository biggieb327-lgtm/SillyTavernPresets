#!/data/data/com.termux/files/usr/bin/bash
# sync-cards.sh — converge every instance's character card and seed files with main.
#
# For each instance, reads CHARACTER_CARD from its .env, pulls that card from the repo,
# pulls the shared preset.txt (voiceprint, identical fleet-wide), and pulls the matching
# seed directory (people.txt, projects.txt, schedule.txt, atlas.txt) if one exists in the
# repo. Never touches .env, state files, or bot.py.
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
for entry in "nora-bot:nora:nora.json" "bonnie-bot:bonnie:bonnie.json" "cass-bot:cass:cass.json" "emily-bot:emily:emily_harper.json" "priya-bot:priya:priya.json" "jules-bot:jules:jules_nakagawa.json"; do
  dir="$HOME/${entry%%:*}"
  rest="${entry#*:}"
  name="${rest%%:*}"
  default_card="${rest#*:}"

  [ -d "$dir" ] || { echo "$name: skipped (no $dir)"; continue; }

  # Read CHARACTER_CARD from the instance's .env, fall back to the default.
  card="$default_card"
  if [ -f "$dir/.env" ]; then
    env_card=$(grep -m1 '^CHARACTER_CARD=' "$dir/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
    [ -n "$env_card" ] && card="$env_card"
  fi

  echo "$name ($card):"
  pull_file "$REPO/$card" "$dir/$card" "$card" && synced=$((synced+1))

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
