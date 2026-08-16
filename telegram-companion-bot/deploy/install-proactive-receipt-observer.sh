#!/usr/bin/env bash
set -euo pipefail

INSTANCE="${1:-emily}"
OWNER_CHAT_ID="${OWNER_CHAT_ID:-}"
REPO_DIR="/opt/telegram-bots/.repo/telegram-companion-bot"
UNIT_SRC="$REPO_DIR/deploy/proactive-receipt-observer@.service"
UNIT_DST="/etc/systemd/system/proactive-receipt-observer@.service"
ENV_DIR="/etc/telegram-bots"
ENV_FILE="$ENV_DIR/proactive-receipt-${INSTANCE}.env"
BOT_UNIT="bot@${INSTANCE}.service"
OBS_UNIT="proactive-receipt-observer@${INSTANCE}.service"
RECEIPT_PATH="/opt/telegram-bots/${INSTANCE}/proactive-receipts.jsonl"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root." >&2
  exit 2
fi
if [[ ! "$OWNER_CHAT_ID" =~ ^[0-9]+$ ]]; then
  echo "Set OWNER_CHAT_ID to the instance owner's numeric Telegram chat id." >&2
  exit 2
fi
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Missing $UNIT_SRC — update the VPS repo checkout to current main first." >&2
  exit 2
fi
if [[ ! -f "$REPO_DIR/proactive_receipt_observer.py" ]]; then
  echo "Missing proactive_receipt_observer.py in the repo checkout." >&2
  exit 2
fi
if [[ ! -d "/opt/telegram-bots/$INSTANCE" ]]; then
  echo "Unknown instance directory: /opt/telegram-bots/$INSTANCE" >&2
  exit 2
fi
if ! systemctl is-active --quiet "$BOT_UNIT"; then
  echo "$BOT_UNIT is not active; refusing to install/start the observer against a stopped bot." >&2
  exit 3
fi

# The foreground smoke-test observer must be stopped before systemd takes over. Two readers
# would mirror the same journal events into duplicate receipt rows.
if pgrep -af "proactive_receipt_observer.py.*--out ${RECEIPT_PATH}" >/dev/null 2>&1; then
  echo "A foreground observer for $INSTANCE is already running." >&2
  echo "Stop it with Ctrl-C, then rerun this installer so only systemd owns observation." >&2
  exit 4
fi

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
install -d -m 0755 "$ENV_DIR"
printf 'OWNER_CHAT_ID=%s\n' "$OWNER_CHAT_ID" > "$ENV_FILE"
chmod 0600 "$ENV_FILE"

systemctl daemon-reload
systemctl enable --now "$OBS_UNIT"

printf '\nInstalled and started %s\n' "$OBS_UNIT"
systemctl status "$OBS_UNIT" --no-pager --lines=12
printf '\nReceipts: %s\n' "$RECEIPT_PATH"
printf 'Observer logs: journalctl -u %s -f\n' "$OBS_UNIT"
printf 'Stop observer only: systemctl stop %s\n' "$OBS_UNIT"
