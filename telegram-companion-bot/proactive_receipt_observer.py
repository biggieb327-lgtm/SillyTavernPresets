#!/usr/bin/env python3
"""Translate existing proactive log lines into Sprint 1 JSONL receipts.

This is intentionally behavior-neutral. It does not import bot.py, call Telegram, or
participate in any send/skip decision. It consumes an existing instance's stdout/journal
stream and mirrors already-made decisions into `proactive_receipts.record_receipt`.

Typical pilot use:
    journalctl -u bot@jules -f -o cat | \
      python3 proactive_receipt_observer.py --chat-id 123456 --out proactive-receipts.jsonl

Only lines we can identify unambiguously are recorded. Unknown lines are ignored rather
than guessed into the wrong source/decision class.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from proactive_receipts import record_receipt


_PATTERNS: list[tuple[re.Pattern[str], dict]] = [
    (re.compile(r"\[heartbeat\] Owner recently active; skipping this tick\."),
     dict(source="check_in", decision="skipped",
          reason="owner recently active; heartbeat skipped", hard_veto=None)),
    (re.compile(r"\[heartbeat\] Quiet hours; saved draft\."),
     dict(source="check_in", decision="drafted",
          reason="wanted to check in but it was quiet hours", hard_veto="quiet_hours")),
    (re.compile(r"\[heartbeat\] User /quiet active; skipping\."),
     dict(source="check_in", decision="skipped",
          reason="user /quiet active", hard_veto="explicit_limit")),
    (re.compile(r"\[heartbeat\] In recurring quiet window; skipping\."),
     dict(source="check_in", decision="skipped",
          reason="recurring quiet window active", hard_veto="quiet_hours")),
    (re.compile(r"\[heartbeat\] User /away active; skipping\."),
     dict(source="check_in", decision="skipped",
          reason="user /away active", hard_veto="explicit_limit")),
    (re.compile(r"\[heartbeat\] Nudge budget exhausted; saved draft\."),
     dict(source="check_in", decision="drafted",
          reason="daily nudge budget exhausted", hard_veto="budget_exhausted")),
    (re.compile(r"\[heartbeat\] Mood is low \((?P<detail>[^)]+)\); saved draft\."),
     dict(source="check_in", decision="drafted",
          reason="mood-based soft skip", hard_veto=None)),
    (re.compile(r"\[heartbeat\] Proactive message sent\."),
     dict(source="check_in", decision="sent",
          reason="heartbeat passed existing gates and sent", hard_veto=None)),
    (re.compile(r"\[heartbeat\] Error: (?P<detail>.+)$"),
     dict(source="check_in", decision="failed",
          reason="heartbeat send failed", hard_veto=None)),
    (re.compile(r"\[note-followup\] asked about: (?P<detail>.+)$"),
     dict(source="day_life", decision="sent",
          reason="due dated-note follow-up sent", hard_veto=None)),
    (re.compile(r"\[note-followup\] failed: (?P<detail>.+)$"),
     dict(source="day_life", decision="failed",
          reason="due dated-note follow-up failed", hard_veto=None)),
    (re.compile(r"\[payments\] Reminder sent: (?P<detail>.+)$"),
     dict(source="reminder", decision="sent",
          reason="scheduled payment reminder sent", hard_veto=None)),
    (re.compile(r"\[cron #(?P<id>\d+)\] Ran: (?P<detail>.+)$"),
     dict(source="reminder", decision="sent",
          reason="scheduled cron task sent", hard_veto=None)),
    (re.compile(r"\[cron #(?P<id>\d+)\] Error: (?P<detail>.+)$"),
     dict(source="reminder", decision="failed",
          reason="scheduled cron task failed", hard_veto=None)),
]


def classify_line(line: str) -> dict | None:
    """Return receipt kwargs for a known log line, else None."""
    # journald may prepend a timestamp/unit prefix. Search rather than fullmatch.
    for rx, base in _PATTERNS:
        match = rx.search(line)
        if not match:
            continue
        out = dict(base)
        groups = match.groupdict()
        detail = (groups.get("detail") or "").strip()
        cid = groups.get("id")
        out["candidate_id"] = f"cron-{cid}" if cid else None
        out["text"] = detail
        if detail and out["decision"] in {"failed", "drafted"}:
            # Preserve useful operator context without turning the receipt into a transcript.
            out["reason"] = f"{out['reason']}: {detail}"
        return out
    return None


def observe(lines, *, chat_id: int, out_path: str | Path) -> int:
    """Record every recognized decision. Receipt write failures never stop observation."""
    count = 0
    for raw in lines:
        parsed = classify_line(raw.rstrip("\n"))
        if parsed is None:
            continue
        try:
            record_receipt(out_path, chat_id=chat_id, **parsed)
            count += 1
        except Exception as exc:  # observability is never allowed to become load-bearing
            print(f"[receipt-observer] write failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror proactive journal lines into JSONL receipts")
    parser.add_argument("--chat-id", type=int, required=True,
                        help="owner chat id for the single instance whose journal is being observed")
    parser.add_argument("--out", required=True, help="JSONL receipt path")
    args = parser.parse_args()
    observe(sys.stdin, chat_id=args.chat_id, out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
