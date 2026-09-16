"""Structured nightly receipts for Sprint 2.

Records what reflection_job considered, changed, and prepared each run.
Behavior-neutral: observing the nightly run never changes what it does.
Mirrors the proactive_receipts.py pattern — JSONL append, thread-safe,
fail-soft.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

VALID_TASKS = {
    "reflect",
    "memory_promotion",
    "memory_audit",
    "episode_consolidation",
    "mood_reset",
    "engagement_snapshot",
    "predraft_hooks",
    "ambient_news",
}

VALID_OUTCOMES = {"applied", "drafted", "skipped", "failed", "nothing"}

_LOCK = threading.Lock()


def build_task_entry(
    *,
    task: str,
    outcome: str,
    detail: str = "",
    error: str | None = None,
) -> dict:
    """Build one task-level entry for inclusion in a nightly receipt."""
    if task not in VALID_TASKS:
        raise ValueError(f"unknown nightly task: {task!r}")
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"unknown nightly outcome: {outcome!r}")
    entry: dict[str, Any] = {
        "task": task,
        "outcome": outcome,
    }
    if detail:
        entry["detail"] = detail[:300]
    if error:
        entry["error"] = str(error)[:200]
    return entry


def build_receipt(
    *,
    instance: str,
    chat_id: int,
    tasks: list[dict],
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    now: datetime | None = None,
) -> dict:
    """Build and validate a full nightly receipt."""
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        raise ValueError("chat_id must be an integer")
    if not isinstance(instance, str) or not instance.strip():
        raise ValueError("instance must be non-empty")
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    applied = sum(1 for t in tasks if t.get("outcome") == "applied")
    drafted = sum(1 for t in tasks if t.get("outcome") == "drafted")
    skipped = sum(1 for t in tasks if t.get("outcome") == "skipped")
    failed = sum(1 for t in tasks if t.get("outcome") == "failed")

    receipt: dict[str, Any] = {
        "ts": stamp.isoformat(timespec="seconds"),
        "instance": instance.strip(),
        "chat_id": chat_id,
        "summary": {
            "applied": applied,
            "drafted": drafted,
            "skipped": skipped,
            "failed": failed,
            "total": len(tasks),
        },
        "tasks": tasks,
    }
    if started_at is not None:
        s = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        receipt["started_at"] = s.isoformat(timespec="seconds")
    if finished_at is not None:
        f = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
        receipt["finished_at"] = f.isoformat(timespec="seconds")
        if started_at is not None:
            receipt["duration_s"] = round((finished_at - started_at).total_seconds(), 1)
    return receipt


def append_receipt(path: str | Path, receipt: Mapping) -> None:
    """Append one compact JSONL nightly receipt. Thread-safe."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(receipt), ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOCK:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def record_receipt(path: str | Path, **kwargs) -> dict:
    """Build, append, and return a nightly receipt."""
    receipt = build_receipt(**kwargs)
    append_receipt(path, receipt)
    return receipt


def read_latest(path: str | Path, count: int = 1) -> list[dict]:
    """Read the last N nightly receipts from a JSONL file."""
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict] = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except (TypeError, ValueError):
                continue
    except OSError:
        return []
    return rows[-count:]
