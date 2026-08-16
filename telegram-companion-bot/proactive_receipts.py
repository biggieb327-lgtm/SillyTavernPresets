"""Behavior-neutral proactive candidate receipts for Sprint 1.

This module records decisions made elsewhere. It deliberately contains no eligibility,
quality, ranking, or send logic: observing a candidate must never change whether it sends.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

VALID_SOURCES = {"reminder", "health", "memory", "day_life", "check_in", "other"}
VALID_DECISIONS = {"sent", "skipped", "drafted", "failed"}
VALID_HARD_VETOES = {
    "quiet_hours",
    "explicit_limit",
    "feature_disabled",
    "safety_privacy",
    "budget_exhausted",
    "stale_source",
}
SCORE_DIMENSIONS = ("timing", "specificity", "novelty", "pressure")

_LOCK = threading.Lock()


def _preview(text: str, limit: int = 96) -> str:
    """Single-line bounded preview; receipts are not a second transcript store."""
    clean = " ".join((text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _normalise_scores(scores: Mapping[str, int | None] | None) -> dict[str, int | None]:
    if scores is None:
        return {dim: None for dim in SCORE_DIMENSIONS}
    if set(scores) != set(SCORE_DIMENSIONS):
        raise ValueError(f"scores must contain exactly {SCORE_DIMENSIONS}")
    out: dict[str, int | None] = {}
    for dim in SCORE_DIMENSIONS:
        value = scores[dim]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3):
            raise ValueError(f"{dim} must be null or an integer 0..3")
        out[dim] = value
    return out


def build_receipt(
    *,
    chat_id: int,
    source: str,
    decision: str,
    reason: str,
    text: str = "",
    candidate_id: str | None = None,
    hard_veto: str | None = None,
    scores: Mapping[str, int | None] | None = None,
    collision_window: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Build and validate one receipt without touching disk."""
    if source not in VALID_SOURCES:
        raise ValueError(f"unknown proactive source: {source!r}")
    if decision not in VALID_DECISIONS:
        raise ValueError(f"unknown proactive decision: {decision!r}")
    if hard_veto is not None and hard_veto not in VALID_HARD_VETOES:
        raise ValueError(f"unknown hard veto: {hard_veto!r}")
    if hard_veto is not None and decision == "sent":
        raise ValueError("a sent candidate cannot carry a hard veto")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        raise ValueError("chat_id must be an integer")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be non-empty")

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    return {
        "ts": stamp.isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "source": source,
        "candidate_id": candidate_id,
        "decision": decision,
        "reason": reason.strip(),
        "hard_veto": hard_veto,
        "scores": _normalise_scores(scores),
        "collision_window": collision_window,
        "text_fingerprint": _fingerprint(text),
        "text_preview": _preview(text),
    }


def append_receipt(path: str | Path, receipt: Mapping) -> None:
    """Append one compact JSONL receipt. A process-local lock prevents torn writes."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(receipt), ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOCK:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def record_receipt(path: str | Path, **kwargs) -> dict:
    """Build, append, and return a receipt. Caller decisions remain untouched."""
    receipt = build_receipt(**kwargs)
    append_receipt(path, receipt)
    return receipt
