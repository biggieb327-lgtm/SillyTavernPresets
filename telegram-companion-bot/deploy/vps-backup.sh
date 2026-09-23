#!/usr/bin/env bash
# vps-backup.sh — archive every bot instance's mutable state on the VPS.
#
# The characters' memories, relationships, episodes, life arcs, and user notes are
# the actual product of this system. This script tars each instance's state directory
# (excluding secrets) plus the shared group-ledger directory, rotates old archives,
# and optionally pushes off-box.
#
# Usage (on the VPS, as root):
#   /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-backup.sh
#   /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-backup.sh --list <archive>
#   /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-backup.sh --restore <archive> [staging-dir]
#
# Schedule nightly with cron (as root):
#   crontab -e   # add:
#   30 3 * * * /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-backup.sh >> /var/log/bot-backup.log 2>&1
#
# Tunables (env or /etc/bot-backup.conf):
#   BACKUP_DIR       — where archives land (default: /opt/telegram-bots/backups)
#   KEEP_DAYS        — local retention in days (default: 14)
#   REMOTE_KEEP_DAYS — rclone-remote retention in days (default: 30; 0 = never delete remotely)
#   BACKUP_RSYNC_DST — rsync destination for off-box copy (e.g. user@offsite:/backups/bots)
#   BACKUP_RCLONE_REMOTE — rclone remote for off-box copy (e.g. gdrive:bot-backups)
#   VERBOSE          — set to 1 for progress output on success (cron is quiet by default)

set -euo pipefail

[ -f /etc/bot-backup.conf ] && . /etc/bot-backup.conf

BASE="${BOT_BASE:-/opt/telegram-bots}"
BACKUP_DIR="${BACKUP_DIR:-$BASE/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
REMOTE_KEEP_DAYS="${REMOTE_KEEP_DAYS:-30}"
VERBOSE="${VERBOSE:-0}"
STAMP=$(date +%Y%m%d-%H%M%S)

log() { echo "[vps-backup] $(date +%H:%M:%S) $*"; }
vlog() { [ "$VERBOSE" = "1" ] && log "$@" || true; }

# --- Modes ---

if [ "${1:-}" = "--list" ]; then
  archive="${2:?usage: vps-backup.sh --list <archive>}"
  [ -f "$archive" ] || { echo "not found: $archive" >&2; exit 1; }
  tar tzf "$archive"
  exit 0
fi

if [ "${1:-}" = "--restore" ]; then
  archive="${2:?usage: vps-backup.sh --restore <archive> [staging-dir]}"
  [ -f "$archive" ] || { echo "not found: $archive" >&2; exit 1; }
  staging="${3:-/tmp/bot-restore-drill-$STAMP}"
  mkdir -p "$staging"
  tar xzf "$archive" -C "$staging"
  log "extracted to $staging"
  log "contents:"
  find "$staging" -maxdepth 2 -type f | head -40
  count=$(find "$staging" -type f | wc -l)
  log "$count files total. Verify, then copy what you need to /opt/telegram-bots/<instance>/."
  log "This is a staging area — nothing was overwritten."
  exit 0
fi

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  sed -n '2,/^$/{ s/^# //; s/^#$//; p; }' "$0"
  exit 0
fi

# --- Backup ---

if [ "$(id -u)" -ne 0 ]; then
  echo "[vps-backup] FATAL: run this as root" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

STAGE=$(mktemp -d "$BACKUP_DIR/.backup-stage.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT

# Discover instances from systemd (same pattern as vps-sync.sh).
# Fall back to directory listing if systemd is unavailable.
instances=()
if command -v systemctl >/dev/null 2>&1; then
  while IFS= read -r name; do
    instances+=("$name")
  done < <(systemctl list-units 'bot@*.service' --no-legend --plain \
    | awk '{print $1}' | sed 's/^bot@//; s/\.service$//' | sort)
fi

if [ "${#instances[@]}" -eq 0 ]; then
  while IFS= read -r dir; do
    name=$(basename "$dir")
    [[ "$name" =~ ^(selectors|releases|venvs|shared|backups|\.repo)$ ]] && continue
    [ -f "$dir/state.json" ] || continue
    instances+=("$name")
  done < <(find "$BASE" -maxdepth 1 -mindepth 1 -type d | sort)
fi

if [ "${#instances[@]}" -eq 0 ]; then
  log "FATAL: no bot instances found under $BASE"
  exit 1
fi

vlog "backing up ${#instances[@]} instances: ${instances[*]}"

total_files=0
for name in "${instances[@]}"; do
  inst_dir="$BASE/$name"
  [ -d "$inst_dir" ] || { log "WARN: $inst_dir not found, skipping $name"; continue; }

  mkdir -p "$STAGE/$name"

  # Copy all state files, excluding secrets and non-state.
  # tar the directory with exclusions rather than listing files, so new state
  # files are picked up automatically.
  # maxdepth 1, so every file lands directly in $STAGE/$name/ (no subpaths). `cp --`
  # because a filename can start with "-" (a stray "-H..." file in cass made the old
  # `dirname "$rel"` call read it as an option, 2026-09-23).
  n=0
  while IFS= read -r f; do
    case "$f" in
      *.sqlite3)
        # The bots keep machine-state.sqlite3 open in WAL mode, so a plain cp can catch
        # the database and its -wal file at different moments. SQLite's own backup API
        # takes a consistent snapshot while the bot is running.
        if python3 -c 'import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()' \
            "$f" "$STAGE/$name/$(basename -- "$f")"; then
          :
        else
          log "WARN: sqlite backup of $f failed; copying the file as-is"
          cp -- "$f" "$STAGE/$name/"
        fi
        ;;
      *.sqlite3-wal|*.sqlite3-shm)
        continue  # folded into the snapshot above
        ;;
      *)
        cp -- "$f" "$STAGE/$name/"
        ;;
    esac
    n=$((n + 1))
  done < <(find "$inst_dir" -maxdepth 1 -type f \
    ! -name '.env' \
    ! -name '.env.*' \
    ! -name '*.pyc' \
    ! -name '*.log' \
    2>/dev/null)

  total_files=$((total_files + n))
  vlog "  $name: $n files"
done

# Back up the shared group-ledger directory.
if [ -d "$BASE/shared" ]; then
  mkdir -p "$STAGE/shared"
  cp -a "$BASE/shared/." "$STAGE/shared/" 2>/dev/null || true
  shared_count=$(find "$STAGE/shared" -type f 2>/dev/null | wc -l)
  total_files=$((total_files + shared_count))
  vlog "  shared: $shared_count files"
fi

if [ "$total_files" -eq 0 ]; then
  log "ERROR: no state files found in any instance directory — nothing archived."
  exit 1
fi

ARCHIVE="$BACKUP_DIR/bot-state-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$STAGE" .
size=$(du -h "$ARCHIVE" | cut -f1)
log "wrote $ARCHIVE ($size, $total_files files, ${#instances[@]} instances)"

# Prune old archives.
pruned=$(find "$BACKUP_DIR" -name 'bot-state-*.tar.gz' -mtime +"$KEEP_DAYS" -delete -print 2>/dev/null | wc -l)
[ "$pruned" -gt 0 ] && vlog "pruned $pruned archives older than $KEEP_DAYS days"

# Off-box copy: rsync (preferred) or rclone.
offbox_ok=0
if [ -n "${BACKUP_RSYNC_DST:-}" ]; then
  if rsync -az "$ARCHIVE" "$BACKUP_RSYNC_DST/" 2>&1; then
    log "rsync to $BACKUP_RSYNC_DST OK"
    offbox_ok=1
  else
    log "WARN: rsync push failed — archive is still local at $ARCHIVE"
  fi
elif [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  if command -v rclone >/dev/null 2>&1; then
    if rclone copy "$ARCHIVE" "$BACKUP_RCLONE_REMOTE" 2>&1; then
      log "rclone to $BACKUP_RCLONE_REMOTE OK"
      offbox_ok=1
      # Remote retention, run only after a successful upload so a broken remote never
      # prunes without a fresh copy landing first. Only our own archive names match.
      if [ "$REMOTE_KEEP_DAYS" -gt 0 ] 2>/dev/null; then
        if rclone delete "$BACKUP_RCLONE_REMOTE" --include 'bot-state-*.tar.gz' \
            --min-age "${REMOTE_KEEP_DAYS}d" 2>&1; then
          vlog "remote: deleted archives older than $REMOTE_KEEP_DAYS days"
        else
          log "WARN: remote prune failed — old archives remain on $BACKUP_RCLONE_REMOTE"
        fi
      fi
    else
      log "WARN: rclone push failed — archive is still local at $ARCHIVE"
    fi
  else
    log "WARN: BACKUP_RCLONE_REMOTE set but rclone not installed (apt install rclone)"
  fi
fi

if [ -z "${BACKUP_RSYNC_DST:-}" ] && [ -z "${BACKUP_RCLONE_REMOTE:-}" ]; then
  log "NOTE: no off-box destination configured (BACKUP_RSYNC_DST or BACKUP_RCLONE_REMOTE)"
fi
