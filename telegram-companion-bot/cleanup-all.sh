#!/data/data/com.termux/files/usr/bin/bash
# cleanup-all.sh — reclaim disk on the Termux phone before it silently fills up.
#
# The recurring bottleneck this closes: a dev host quietly runs out of space — not
# S3, just the phone's own storage — because nobody remembers to sweep the junk that
# accumulates around long-running workers. On this fleet that junk is pip's cache,
# __pycache__ dirs, staging dirs left behind when a backup got SIGKILLed mid-run
# (the phantom-process killer does this), orphaned *.tmp sidecars from interrupted
# atomic writes, and old character cards that sync-cards.sh leaves on disk for
# reversibility. None of it is state; all of it regenerates or is already backed up.
#
# SAFE BY DEFAULT: this is a DRY RUN unless you pass --force. A dry run only measures
# and lists what it *would* remove — it deletes nothing. Look at the report first,
# then trust it. It NEVER touches .env, state files (state.json, memories.txt,
# user_notes.txt, setting.txt, reminders.json, payments.json), bot.py, bot.py.bak,
# .alive heartbeats, bot.pid, or live logs. Character cards are only ever *reported*
# (the active one can't be reliably told from an orphan without parsing each .env),
# so you delete those by hand.
#
# Usage:
#   bash cleanup-all.sh            # dry run — report only, deletes nothing
#   bash cleanup-all.sh --force    # actually delete the unambiguous garbage
#
# One-time install on the phone (like backup-all.sh / watchdog.sh — NOT pulled by
# update-all.sh):
#   curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/cleanup-all.sh -o ~/telegram-bot/cleanup-all.sh
#
# Schedule weekly with cron (use --force so it actually cleans unattended):
#   crontab -e     # add:  0 4 * * 0  bash ~/telegram-bot/cleanup-all.sh --force >> ~/cleanup.log 2>&1
#
# Tunables (env or ~/.cleanup.conf):
#   CLEANUP_TMP_AGE_DAYS   min age of a *.tmp / staging dir before it's junk (default 1)
#   PIP_CACHE_DIR          pip cache location (default ~/.cache/pip)

set -u

[ -f "$HOME/.cleanup.conf" ] && . "$HOME/.cleanup.conf"

CLEANUP_TMP_AGE_DAYS="${CLEANUP_TMP_AGE_DAYS:-1}"
PIP_CACHE_DIR="${PIP_CACHE_DIR:-$HOME/.cache/pip}"
BOT_SRC="$HOME/telegram-bot"

FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

# Instance dirs mirror update-all.sh / backup-all.sh (the authoritative list). Nora's
# instance dir is ~/nora-bot; ~/telegram-bot is the shared CODE dir (pycache lives
# there too, so it's swept as well).
INSTANCE_DIRS="$BOT_SRC $HOME/nora-bot $HOME/bonnie-bot $HOME/cass-bot $HOME/emily-bot $HOME/priya-bot $HOME/jules-bot"

# State/config files that must never be swept, even if a pattern would otherwise match.
PROTECTED="\.env$|state\.json$|memories\.txt$|user_notes\.txt$|setting\.txt$|reminders\.json$|payments\.json$|bot\.py$|bot\.py\.bak$|\.alive$|bot\.pid$"

_bytes() { du -sb "$1" 2>/dev/null | cut -f1; }
_human() { du -sh "$1" 2>/dev/null | cut -f1; }

RECLAIM=0          # running total of bytes we would free (dry run) or freed (force)
mode_label="DRY RUN (nothing deleted — pass --force to act)"
$FORCE && mode_label="FORCE (deleting)"

echo "=== cleanup-all.sh — $mode_label ==="
echo

# --- 1. pip cache -----------------------------------------------------------------
# Always safe: pip re-downloads wheels on demand. Grows after every venv rebuild
# (the documented recovery path for a Python minor-version bump).
if [ -d "$PIP_CACHE_DIR" ]; then
  b=$(_bytes "$PIP_CACHE_DIR"); b=${b:-0}
  echo "pip cache            $(_human "$PIP_CACHE_DIR")  ($PIP_CACHE_DIR)"
  RECLAIM=$((RECLAIM + b))
  $FORCE && rm -rf "$PIP_CACHE_DIR"
fi

# --- 2. __pycache__ / *.pyc -------------------------------------------------------
# Bytecode, regenerated on next import. Safe to remove even while a bot is running.
pyc_bytes=0
for dir in $INSTANCE_DIRS; do
  [ -d "$dir" ] || continue
  while IFS= read -r pd; do
    [ -n "$pd" ] || continue
    b=$(_bytes "$pd"); pyc_bytes=$((pyc_bytes + ${b:-0}))
    $FORCE && rm -rf "$pd"
  done < <(find "$dir" -type d -name __pycache__ 2>/dev/null)
done
if [ "$pyc_bytes" -gt 0 ]; then
  echo "__pycache__ dirs     $(numfmt --to=iec "$pyc_bytes" 2>/dev/null || echo "${pyc_bytes}B")"
  RECLAIM=$((RECLAIM + pyc_bytes))
fi

# --- 3. stale backup staging dirs -------------------------------------------------
# backup-all.sh stages under ~/.backup-stage.XXXXXX and rm's it via an EXIT trap.
# A SIGKILL (phantom killer) mid-backup skips the trap and leaves the dir behind.
stage_bytes=0
while IFS= read -r sd; do
  [ -n "$sd" ] || continue
  b=$(_bytes "$sd"); stage_bytes=$((stage_bytes + ${b:-0}))
  echo "stale backup stage   $(_human "$sd")  ($sd)"
  $FORCE && rm -rf "$sd"
done < <(find "$HOME" -maxdepth 1 -type d -name '.backup-stage.*' -mtime +"$CLEANUP_TMP_AGE_DAYS" 2>/dev/null)
RECLAIM=$((RECLAIM + stage_bytes))

# --- 4. orphaned *.tmp sidecars ---------------------------------------------------
# Atomic writes (save_state, log trims) write path.tmp then rename in milliseconds.
# A .tmp older than CLEANUP_TMP_AGE_DAYS means a write was interrupted — the real
# file is intact; the sidecar is dead. Protected names are skipped defensively.
tmp_bytes=0; tmp_count=0
for dir in $INSTANCE_DIRS; do
  [ -d "$dir" ] || continue
  while IFS= read -r tf; do
    [ -n "$tf" ] || continue
    echo "$tf" | grep -Eq "$PROTECTED" && continue
    b=$(stat -c%s "$tf" 2>/dev/null || echo 0)
    tmp_bytes=$((tmp_bytes + b)); tmp_count=$((tmp_count + 1))
    $FORCE && rm -f "$tf"
  done < <(find "$dir" -maxdepth 1 -type f -name '*.tmp' -mtime +"$CLEANUP_TMP_AGE_DAYS" 2>/dev/null)
done
if [ "$tmp_count" -gt 0 ]; then
  echo "orphaned *.tmp files  $tmp_count file(s), $(numfmt --to=iec "$tmp_bytes" 2>/dev/null || echo "${tmp_bytes}B")"
  RECLAIM=$((RECLAIM + tmp_bytes))
fi

# --- 5. character cards — REPORT ONLY ---------------------------------------------
# sync-cards.sh leaves the previous card on disk (orphaned, not deleted) so a switch
# stays reversible. Over many switches these accumulate, but the *active* card can't
# be told from an orphan here without parsing each .env — so we only surface them and
# let a human delete by hand. Never auto-removed, even with --force.
card_note_printed=false
for dir in $INSTANCE_DIRS; do
  [ -d "$dir" ] || continue
  cards=$(find "$dir" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)
  if [ "$cards" -gt 1 ]; then
    if [ "$card_note_printed" = false ]; then
      echo
      echo "REVIEW (not deleted) — instance dirs holding >1 card .json (possible sync-cards orphans):"
      card_note_printed=true
    fi
    echo "  $dir  ($cards json files)"
  fi
done

# --- summary ----------------------------------------------------------------------
echo
if $FORCE; then
  echo "Freed ~$(numfmt --to=iec "$RECLAIM" 2>/dev/null || echo "${RECLAIM}B")."
else
  echo "Would free ~$(numfmt --to=iec "$RECLAIM" 2>/dev/null || echo "${RECLAIM}B").  Re-run with --force to delete."
fi
if command -v df >/dev/null 2>&1; then
  echo "Home filesystem now: $(df -h "$HOME" 2>/dev/null | awk 'NR==2 {print $4" free of "$2}')"
fi
