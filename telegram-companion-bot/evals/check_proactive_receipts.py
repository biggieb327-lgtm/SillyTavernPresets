#!/usr/bin/env python3
"""Dependency-free checks for Sprint 1's behavior-neutral receipt writer.

Run from the repository root:
    python3 telegram-companion-bot/evals/check_proactive_receipts.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT_DIR))

from proactive_receipts import build_receipt, record_receipt  # noqa: E402


def _must_raise(fn, contains: str) -> None:
    try:
        fn()
    except ValueError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected ValueError containing {contains!r}")


def main() -> int:
    fixed_now = datetime(2026, 8, 15, 22, 40, tzinfo=timezone.utc)
    text = "hey — your dentist thing is in about 20 minutes"
    sent = build_receipt(
        chat_id=123,
        source="reminder",
        decision="sent",
        reason="due reminder passed existing gates",
        text=text,
        now=fixed_now,
    )
    assert sent["decision"] == "sent"
    assert sent["hard_veto"] is None
    assert sent["scores"] == {
        "timing": None, "specificity": None, "novelty": None, "pressure": None,
    }
    assert sent["text_preview"] == text
    assert len(sent["text_fingerprint"]) == 16

    skipped = build_receipt(
        chat_id=123,
        source="check_in",
        decision="skipped",
        reason="daily proactive budget exhausted",
        text="this full candidate should not become a second transcript",
        hard_veto="budget_exhausted",
        now=fixed_now,
    )
    assert skipped["hard_veto"] == "budget_exhausted"

    long_text = "word " * 40
    bounded = build_receipt(
        chat_id=1, source="memory", decision="drafted", reason="quiet now", text=long_text,
        now=fixed_now,
    )
    assert len(bounded["text_preview"]) <= 96
    assert "\n" not in bounded["text_preview"]

    _must_raise(lambda: build_receipt(
        chat_id=1, source="bogus", decision="sent", reason="x", now=fixed_now,
    ), "unknown proactive source")
    _must_raise(lambda: build_receipt(
        chat_id=1, source="health", decision="bogus", reason="x", now=fixed_now,
    ), "unknown proactive decision")
    _must_raise(lambda: build_receipt(
        chat_id=1, source="health", decision="sent", reason="x",
        hard_veto="quiet_hours", now=fixed_now,
    ), "sent candidate cannot carry a hard veto")
    _must_raise(lambda: build_receipt(
        chat_id=1, source="health", decision="skipped", reason="x",
        scores={"timing": 4, "specificity": 3, "novelty": 3, "pressure": 3}, now=fixed_now,
    ), "timing must be null or an integer 0..3")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipts" / "proactive.jsonl"
        written = record_receipt(
            path,
            chat_id=7,
            source="day_life",
            decision="failed",
            reason="telegram send raised",
            text="candidate",
            now=fixed_now,
        )
        rows = path.read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1
        assert json.loads(rows[0]) == written

    print("proactive receipt contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
