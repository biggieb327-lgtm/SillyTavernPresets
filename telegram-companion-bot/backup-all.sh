#!/data/data/com.termux/files/usr/bin/bash
# backup-all.sh — archive every bot instance's state off Termux, automatically.
#
# The characters' memories, user notes, and relationship state are the actual product of
# this system, and they live on one phone. /backup (per bot, manual, to the chat) covers
# spot checks; this covers the phone dying. Same file list as /backup — .env is NEVER
# included (tokens don't belong in backups that leave the device).
#
# One-time install on the phone (like watchdog.sh, this is NOT pulled by update-all.sh):
#   curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/backup-all.sh -o ~/telegram-bot/backup-all.sh
#   termux-setup-storage        # once, grants access to Android shared storage
#
# Schedule nightly with cron:
#   pkg install cronie termux-services && sv-enable crond
#   crontab -e     # add:  30 3 * * * bash ~/telegram-bot/backup-all.sh >> ~/backup.log 2>&1
#
# Destination: ~/storage/shared/bot-backups (Android shared storage — survives a Termux
# uninstall and is visible to any file manager / auto-sync app). For true off-phone
# safety, set BACKUP_RCLONE_REMOTE in the environment or in ~/.bot-backup.conf, e.g.:
#   BACKUP_RCLONE_REMOTE=gdrive:bot-backups
# and each run also pushes the archive there via rclone (pkg install rclone; rclone config).
#
# Tunables (env or ~/.bot-backup.conf): BACKUP_DIR, KEEP_DAYS (default 14), BACKUP_RCLONE_REMOTE.

set -u

[ -f "$HOME/.bot-backup.conf" ] && . "$HOME/.bot-backup.conf"

KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP=$(date +%Y%m%d-%H%M)

# Prefer Android shared storage; fall back to Termux home if termux-setup-storage
# hasn't been run (still better than nothing, but warn — it dies with Termux).
if [ -n "${BACKUP_DIR:-}" ]; then
  DEST="$BACKUP_DIR"
elif [ -d "$HOME/storage/shared" ]; then
  DEST="$HOME/storage/shared/bot-backups"
else
  DEST="$HOME/bot-backups"
  echo "WARN: ~/storage/shared not available (run termux-setup-storage once);" \
       "falling back to $DEST — this does NOT survive a Termux uninstall."
fi
mkdir -p "$DEST"

# /tmp is not writable on Termux — stage under $HOME.
STAGE=$(mktemp -d "$HOME/.backup-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT

# Same state-file list as the /backup command; .env deliberately excluded.
FILES="state.json memories.txt user_notes.txt setting.txt reminders.json payments.json"

# Instance list mirrors update-all.sh (the authoritative list): nora is the home
# instance at ~/telegram-bot, the rest are ~/<name>-bot.
copied=0
for entry in "telegram-bot:nora" "bonnie-bot:bonnie" "cass-bot:cass" "emily-bot:emily" "priya-bot:priya" "jules-bot:jules"; do
  dir="$HOME/${entry%%:*}"
  name="${entry##*:}"
  [ -d "$dir" ] || { echo "  $name: skipped (no $dir)"; continue; }
  mkdir -p "$STAGE/$name"
  n=0
  for f in $FILES; do
    if [ -f "$dir/$f" ]; then
      cp "$dir/$f" "$STAGE/$name/$f"
      n=$((n+1))
    fi
  done
  copied=$((copied+n))
  echo "  $name: $n files"
done

if [ "$copied" -eq 0 ]; then
  echo "ERROR: no state files found in any instance directory — nothing archived."
  exit 1
fi

ARCHIVE="$DEST/bot-state-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$STAGE" .
echo "Wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Prune old archives so shared storage doesn't fill up.
find "$DEST" -name 'bot-state-*.tar.gz' -mtime +"$KEEP_DAYS" -delete 2>/dev/null

# Optional off-phone copy.
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  if command -v rclone >/dev/null 2>&1; then
    if rclone copy "$ARCHIVE" "$BACKUP_RCLONE_REMOTE" 2>&1; then
      echo "Pushed to $BACKUP_RCLONE_REMOTE"
    else
      echo "WARN: rclone push failed — archive is still on-device at $ARCHIVE"
    fi
  else
    echo "WARN: BACKUP_RCLONE_REMOTE set but rclone not installed (pkg install rclone)"
  fi
fi
