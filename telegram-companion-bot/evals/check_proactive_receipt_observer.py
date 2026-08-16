#!/usr/bin/env python3
"""Dependency-free checks for the Sprint 1 proactive log observer."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

from proactive_receipt_observer import classify_line, observe  # noqa: E402


def main() -> int:
    cases = [
        ("[heartbeat] Owner recently active; skipping this tick.", "check_in", "skipped", None),
        ("[heartbeat] Quiet hours; saved draft.", "check_in", "drafted", "quiet_hours"),
        ("[heartbeat] User /quiet active; skipping.", "check_in", "skipped", "explicit_limit"),
        ("[heartbeat] In recurring quiet window; skipping.", "check_in", "skipped", "quiet_hours"),
        ("[heartbeat] User /away active; skipping.", "check_in", "skipped", "explicit_limit"),
        ("[heartbeat] Nudge budget exhausted; saved draft.", "check_in", "drafted", "budget_exhausted"),
        ("[heartbeat] Mood is low (-0.7); saved draft.", "check_in", "drafted", None),
        ("[heartbeat] Proactive message sent.", "check_in", "sent", None),
        ("2026-08-15 17:00:00 [ERROR] companion: [heartbeat] Error: TimedOut()",
         "check_in", "failed", None),
        ("[note-followup] asked about: dentist appointment", "day_life", "sent", None),
        ("[note-followup] failed: network timeout", "day_life", "failed", None),
        ("[payments] Reminder sent: 2 due 2026-08-16 → 2026-08-22.", "reminder", "sent", None),
        ("[cron #12] Ran: check the news", "reminder", "sent", None),
        ("[cron #12] Error: provider timeout", "reminder", "failed", None),
    ]

    for line, source, decision, veto in cases:
        parsed = classify_line(line)
        assert parsed is not None, line
        assert parsed["source"] == source, (line, parsed)
        assert parsed["decision"] == decision, (line, parsed)
        assert parsed["hard_veto"] == veto, (line, parsed)

    assert classify_line("[heartbeat] next check in 2.4h.") is None
    assert classify_line("ordinary unrelated log line") is None

    cron = classify_line("[cron #7] Ran: remind me to stretch")
    assert cron["candidate_id"] == "cron-7"
    assert cron["text"] == "remind me to stretch"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipts.jsonl"
        lines = [
            "[heartbeat] Quiet hours; saved draft.\n",
            "noise\n",
            "[heartbeat] Proactive message sent.\n",
            "[note-followup] failed: network timeout\n",
        ]
        count = observe(lines, chat_id=42, out_path=path)
        assert count == 3
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 3
        assert all(row["chat_id"] == 42 for row in rows)
        assert [row["decision"] for row in rows] == ["drafted", "sent", "failed"]
        assert rows[0]["hard_veto"] == "quiet_hours"
        assert rows[1]["source"] == "check_in"
        assert rows[2]["source"] == "day_life"

    print("proactive receipt observer: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
