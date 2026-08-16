#!/usr/bin/env python3
"""Offline Sprint 1 analysis for proactive receipt JSONL.

This module is intentionally outside bot.py and never participates in a send decision.
It assigns deterministic time-window ids to observed candidates and reports collisions
where more than one proactive source produced a candidate in the same window.

Usage:
    python3 proactive_receipt_analysis.py /opt/telegram-bots/emily/proactive-receipts.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

WINDOW_SECONDS = 30 * 60


def parse_ts(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def collision_window_id(stamp: datetime, seconds: int = WINDOW_SECONDS) -> str:
    epoch = int(stamp.timestamp())
    start = epoch - (epoch % seconds)
    return datetime.fromtimestamp(start, timezone.utc).strftime("%Y%m%dT%H%MZ")


def load_receipts(path: str | Path) -> list[dict]:
    rows = []
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
                row["_stamp"] = parse_ts(row["ts"])
            except Exception as exc:
                raise ValueError(f"invalid receipt line {lineno}: {exc}") from exc
            rows.append(row)
    return rows


def analyze(rows: list[dict], seconds: int = WINDOW_SECONDS) -> dict:
    by_window: dict[str, list[dict]] = defaultdict(list)
    sources = Counter()
    decisions = Counter()
    vetoes = Counter()
    for row in rows:
        window = row.get("collision_window") or collision_window_id(row["_stamp"], seconds)
        by_window[window].append(row)
        sources[row.get("source")] += 1
        decisions[row.get("decision")] += 1
        if row.get("hard_veto"):
            vetoes[row["hard_veto"]] += 1

    collisions = []
    for window, items in sorted(by_window.items()):
        distinct_sources = sorted({x.get("source") for x in items if x.get("source")})
        if len(items) > 1 and len(distinct_sources) > 1:
            collisions.append({
                "window": window,
                "count": len(items),
                "sources": distinct_sources,
                "decisions": dict(Counter(x.get("decision") for x in items)),
            })

    return {
        "receipt_count": len(rows),
        "window_minutes": seconds // 60,
        "sources": dict(sources),
        "decisions": dict(decisions),
        "hard_vetoes": dict(vetoes),
        "collision_count": len(collisions),
        "collisions": collisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Sprint 1 proactive receipts")
    parser.add_argument("receipt_file")
    parser.add_argument("--window-minutes", type=int, default=30)
    args = parser.parse_args()
    if args.window_minutes <= 0:
        parser.error("--window-minutes must be positive")
    report = analyze(load_receipts(args.receipt_file), args.window_minutes * 60)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
