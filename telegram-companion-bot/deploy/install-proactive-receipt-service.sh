#!/usr/bin/env bash
set -euo pipefail

INSTANCE="${1:-}"
OWNER_CHAT_ID="${2:-${OWNER_CHAT_ID:-}}"
ROOT=/opt/telegram-bots/.repo/telegram-companion-bot
UNIT_SRC="$ROOT/deploy/proactive-receipt@.service"
UNIT_DST=/etc/systemd/system/proactive-receipt@.service
ENV_FILE="/etc/default/proactive-receipt-${INSTANCE}"

if [[ -z "$INSTANCE" || -z "$OWNER_CHAT_ID" ]]; then
  echo "usage: $0 <instance> <owner-chat-id>" >&2
  echo "   or: OWNER_CHAT_ID=<id> $0 <instance>" >&2
  exit 2
fi
if [[ ! "$OWNER_CHAT_ID" =~ ^-?[0-9]+$ ]]; then
  echo "owner chat id must be an integer" >&2
  exit 2
fi
if [[ ! -f "$UNIT_SRC" ]]; then
  echo "missing unit template: $UNIT_SRC" >&2
  exit 1
fi
if [[ ! -f "$ROOT/proactive_receipt_observer.py" ]]; then
  echo "missing observer: $ROOT/proactive_receipt_observer.py" >&2
  exit 1
fi
if [[ ! -d "/opt/telegram-bots/$INSTANCE" ]]; then
  echo "missing instance directory: /opt/telegram-bots/$INSTANCE" >&2
  exit 1
fi
if ! systemctl is-active --quiet "bot@$INSTANCE"; then
  echo "bot@$INSTANCE is not active; refusing to install/start the observer" >&2
  exit 1
fi

# Do not silently create two observers. Stop the foreground pilot first with Ctrl-C.
if pgrep -af "proactive_receipt_observer.py.*--out /opt/telegram-bots/$INSTANCE/proactive-receipts.jsonl" >/dev/null 2>&1; then
  echo "an observer for $INSTANCE already appears to be running." >&2
  echo "Stop the foreground observer first (Ctrl-C), then rerun this installer." >&2
  exit 1
fi

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
printf 'OWNER_CHAT_ID=%s\n' "$OWNER_CHAT_ID" > "$ENV_FILE"
chmod 0600 "$ENV_FILE"

systemctl daemon-reload
systemctl enable --now "proactive-receipt@$INSTANCE.service"

echo "Installed proactive-receipt@$INSTANCE.service"
systemctl status "proactive-receipt@$INSTANCE.service" --no-pager --lines=12
