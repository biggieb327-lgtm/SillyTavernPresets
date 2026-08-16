#!/usr/bin/env bash
set -euo pipefail

# Sprint 1 proactive-receipt pilot launcher.
# Foreground-only by design: stopping this process must never affect the bot service.

INSTANCE="${1:-emily}"
CHAT_ID="${OWNER_CHAT_ID:-${2:-}}"
ROOT="/opt/telegram-bots"
REPO="$ROOT/.repo/telegram-companion-bot"
OBSERVER="$REPO/proactive_receipt_observer.py"
OUT="$ROOT/$INSTANCE/proactive-receipts.jsonl"
UNIT="bot@$INSTANCE"

if [[ -z "$CHAT_ID" ]]; then
  echo "OWNER_CHAT_ID is required. Ask the pilot bot for /chatid, then:" >&2
  echo "  OWNER_CHAT_ID=<id> $0 $INSTANCE" >&2
  exit 2
fi
if [[ ! "$CHAT_ID" =~ ^-?[0-9]+$ ]]; then
  echo "OWNER_CHAT_ID must be an integer, got: $CHAT_ID" >&2
  exit 2
fi
if [[ ! -f "$OBSERVER" ]]; then
  echo "Observer not found: $OBSERVER" >&2
  echo "Deploy/pull current main into $ROOT/.repo first." >&2
  exit 3
fi
if [[ ! -d "$ROOT/$INSTANCE" ]]; then
  echo "Instance directory not found: $ROOT/$INSTANCE" >&2
  exit 3
fi
if ! systemctl is-active --quiet "$UNIT"; then
  echo "$UNIT is not active; refusing to start an observer for a stopped pilot." >&2
  exit 4
fi

# Touch as the invoking operator so permission failures are discovered before a long soak.
touch "$OUT"

echo "Sprint 1 proactive receipt pilot"
echo "  instance: $INSTANCE"
echo "  service:  $UNIT"
echo "  output:   $OUT"
echo "  mode:     foreground journal observer (Ctrl-C stops observer only)"
echo

journalctl -u "$UNIT" -f -o cat | \
  python3 "$OBSERVER" --chat-id "$CHAT_ID" --out "$OUT"
