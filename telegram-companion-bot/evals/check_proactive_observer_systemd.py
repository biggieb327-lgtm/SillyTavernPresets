#!/usr/bin/env python3
"""Static safety checks for the Sprint 1 persistent proactive observer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT = (ROOT / "deploy" / "proactive-receipt-observer@.service").read_text(encoding="utf-8")
INSTALL = (ROOT / "deploy" / "install-proactive-receipt-observer.sh").read_text(encoding="utf-8")
DOC = (ROOT / "PROACTIVE-RECEIPT-PILOT.md").read_text(encoding="utf-8")

# Observer must not own or manipulate the bot lifecycle.
for relation in ("Requires=bot@", "Wants=bot@", "PartOf=bot@"):
    assert relation not in UNIT, relation
for action in ("systemctl start \"$BOT_UNIT\"", "systemctl stop \"$BOT_UNIT\"",
               "systemctl restart \"$BOT_UNIT\"", "systemctl enable \"$BOT_UNIT\""):
    assert action not in INSTALL, action

# Do not replay historical journal entries after observer/service restart.
assert "journalctl -u bot@%i -f -n 0 -o cat" in UNIT

# Persistent service must use the merged behavior-neutral observer and Emily-local output.
assert "proactive_receipt_observer.py" in UNIT
assert "/opt/telegram-bots/%i/proactive-receipts.jsonl" in UNIT
assert "EnvironmentFile=/etc/telegram-bots/proactive-receipt-%i.env" in UNIT

# Installer only starts/enables the observer and verifies the bot is already active.
assert 'systemctl is-active --quiet "$BOT_UNIT"' in INSTALL
assert 'systemctl enable --now "$OBS_UNIT"' in INSTALL
assert "chmod 0600 \"$ENV_FILE\"" in INSTALL

# Emily remains the named, single pilot for the seven-day soak.
assert "Emily (`bot@emily`) is the Sprint 1 pilot instance" in DOC
assert "at least seven consecutive days" in DOC
assert "proactive-receipt-observer@emily" in DOC

print("proactive observer systemd invariants: PASS")
