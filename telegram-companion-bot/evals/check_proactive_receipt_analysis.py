#!/usr/bin/env python3
"""Dependency-free checks for proactive receipt collision analysis."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proactive_receipt_analysis import analyze, collision_window_id  # noqa: E402


def row(ts: str, source: str, decision: str = "sent", veto=None):
    return {
        "ts": ts,
        "_stamp": datetime.fromisoformat(ts).replace(tzinfo=timezone.utc),
        "source": source,
        "decision": decision,
        "hard_veto": veto,
        "collision_window": None,
    }


def main() -> int:
    assert collision_window_id(datetime(2026, 8, 16, 1, 44, tzinfo=timezone.utc)) == "20260816T0130Z"

    rows = [
        row("2026-08-16T01:31:00", "check_in"),
        row("2026-08-16T01:42:00", "memory", "skipped"),
        row("2026-08-16T02:02:00", "reminder"),
        row("2026-08-16T02:04:00", "reminder", "drafted", "quiet_hours"),
    ]
    report = analyze(rows)
    assert report["receipt_count"] == 4
    assert report["collision_count"] == 1
    assert report["collisions"][0]["sources"] == ["check_in", "memory"]
    assert report["hard_vetoes"] == {"quiet_hours": 1}

    # Multiple events from one source are not cross-source collisions.
    same_source = analyze([
        row("2026-08-16T03:01:00", "reminder"),
        row("2026-08-16T03:05:00", "reminder"),
    ])
    assert same_source["collision_count"] == 0

    print("proactive receipt analysis: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
