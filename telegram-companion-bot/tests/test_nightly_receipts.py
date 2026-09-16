"""Tests for the nightly_receipts module (Sprint 2)."""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Ensure the bot source directory is on sys.path.
_bot_dir = str(Path(__file__).resolve().parent.parent)
if _bot_dir not in sys.path:
    sys.path.insert(0, _bot_dir)

import nightly_receipts


def test_build_task_entry_valid():
    entry = nightly_receipts.build_task_entry(
        task="reflect", outcome="applied", detail="self-image updated")
    assert entry["task"] == "reflect"
    assert entry["outcome"] == "applied"
    assert entry["detail"] == "self-image updated"
    assert "error" not in entry


def test_build_task_entry_with_error():
    entry = nightly_receipts.build_task_entry(
        task="memory_promotion", outcome="failed", error="connection timeout")
    assert entry["outcome"] == "failed"
    assert entry["error"] == "connection timeout"


def test_build_task_entry_truncates_detail():
    long_detail = "x" * 500
    entry = nightly_receipts.build_task_entry(
        task="reflect", outcome="applied", detail=long_detail)
    assert len(entry["detail"]) == 300


def test_build_task_entry_rejects_unknown_task():
    try:
        nightly_receipts.build_task_entry(task="bogus", outcome="applied")
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "unknown nightly task" in str(e)


def test_build_task_entry_rejects_unknown_outcome():
    try:
        nightly_receipts.build_task_entry(task="reflect", outcome="bogus")
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "unknown nightly outcome" in str(e)


def test_build_receipt_summary():
    tasks = [
        nightly_receipts.build_task_entry(task="reflect", outcome="applied"),
        nightly_receipts.build_task_entry(task="memory_promotion", outcome="applied"),
        nightly_receipts.build_task_entry(task="predraft_hooks", outcome="drafted",
                                          detail="3 hooks"),
        nightly_receipts.build_task_entry(task="episode_consolidation", outcome="skipped",
                                          detail="feature disabled"),
        nightly_receipts.build_task_entry(task="ambient_news", outcome="failed",
                                          error="timeout"),
        nightly_receipts.build_task_entry(task="mood_reset", outcome="nothing"),
    ]
    now = datetime(2026, 9, 16, 3, 0, 0, tzinfo=timezone.utc)
    receipt = nightly_receipts.build_receipt(
        instance="emily", chat_id=12345, tasks=tasks, now=now)
    assert receipt["instance"] == "emily"
    assert receipt["chat_id"] == 12345
    assert receipt["summary"]["applied"] == 2
    assert receipt["summary"]["drafted"] == 1
    assert receipt["summary"]["skipped"] == 1
    assert receipt["summary"]["failed"] == 1
    assert receipt["summary"]["total"] == 6
    assert receipt["ts"] == "2026-09-16T03:00:00+00:00"


def test_build_receipt_duration():
    start = datetime(2026, 9, 16, 3, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 16, 3, 2, 30, tzinfo=timezone.utc)
    receipt = nightly_receipts.build_receipt(
        instance="nora", chat_id=99, tasks=[],
        started_at=start, finished_at=end)
    assert receipt["duration_s"] == 150.0
    assert "started_at" in receipt
    assert "finished_at" in receipt


def test_build_receipt_rejects_bad_chat_id():
    try:
        nightly_receipts.build_receipt(instance="nora", chat_id="bad", tasks=[])
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "chat_id" in str(e)


def test_build_receipt_rejects_empty_instance():
    try:
        nightly_receipts.build_receipt(instance="", chat_id=1, tasks=[])
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "instance" in str(e)


def test_record_and_read_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nightly-receipts.jsonl"
        tasks = [
            nightly_receipts.build_task_entry(task="reflect", outcome="applied"),
            nightly_receipts.build_task_entry(task="mood_reset", outcome="nothing"),
        ]
        nightly_receipts.record_receipt(
            path, instance="bonnie", chat_id=42, tasks=tasks)
        nightly_receipts.record_receipt(
            path, instance="bonnie", chat_id=42, tasks=[
                nightly_receipts.build_task_entry(task="reflect", outcome="failed",
                                                  error="timeout")])

        latest = nightly_receipts.read_latest(path, count=1)
        assert len(latest) == 1
        assert latest[0]["summary"]["failed"] == 1

        both = nightly_receipts.read_latest(path, count=2)
        assert len(both) == 2
        assert both[0]["summary"]["applied"] == 1


def test_read_latest_missing_file():
    result = nightly_receipts.read_latest("/nonexistent/file.jsonl")
    assert result == []


def test_record_receipt_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "dir" / "receipts.jsonl"
        nightly_receipts.record_receipt(
            path, instance="cass", chat_id=1, tasks=[])
        assert path.exists()


def test_jsonl_is_compact():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipts.jsonl"
        nightly_receipts.record_receipt(
            path, instance="test", chat_id=1, tasks=[
                nightly_receipts.build_task_entry(task="reflect", outcome="applied")])
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["instance"] == "test"


def test_all_valid_tasks_accepted():
    for task in nightly_receipts.VALID_TASKS:
        entry = nightly_receipts.build_task_entry(task=task, outcome="applied")
        assert entry["task"] == task


def test_all_valid_outcomes_accepted():
    for outcome in nightly_receipts.VALID_OUTCOMES:
        entry = nightly_receipts.build_task_entry(task="reflect", outcome=outcome)
        assert entry["outcome"] == outcome
