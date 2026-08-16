#!/usr/bin/env python3
"""Cheap static checks for the Sprint 1 Emily pilot launcher."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "start-proactive-receipt-pilot.sh"
PILOT = ROOT / "PROACTIVE-RECEIPT-PILOT.md"


def main() -> int:
    script = SCRIPT.read_text(encoding="utf-8")
    pilot = PILOT.read_text(encoding="utf-8")

    assert 'INSTANCE="${1:-emily}"' in script
    assert 'UNIT="bot@$INSTANCE"' in script
    assert 'systemctl is-active --quiet "$UNIT"' in script
    assert 'journalctl -u "$UNIT" -f -o cat' in script
    assert 'proactive-receipts.jsonl' in script
    assert 'systemctl restart' not in script
    assert 'systemctl stop' not in script
    assert 'systemctl start ' not in script
    assert 'bot@emily' in pilot
    assert '/opt/telegram-bots/emily/proactive-receipts.jsonl' in pilot
    assert 'seven consecutive days' in pilot

    print("Emily proactive pilot launcher: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
