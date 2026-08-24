#!/usr/bin/env python3
"""Summarize payload-free OP_EVENT records read from journalctl on stdin.

The report is intentionally a filter: collection and retention stay with journald.
See OPS_MANUAL.md for the bounded whole-fleet query.
"""

import argparse
import json
import math
import sys
from collections import defaultdict


PREFIX = "OP_EVENT "


def parse_events(lines):
    events = []
    for line in lines:
        marker = line.find(PREFIX)
        if marker < 0:
            continue
        try:
            event = json.loads(line[marker + len(PREFIX):])
        except (TypeError, json.JSONDecodeError):
            continue
        if event.get("event") == "bot_operation" and event.get("schema") == 1:
            events.append(event)
    return events


def _percentile(values, percent):
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(percent * len(ordered)))
    return ordered[rank - 1]


def render_report(events, boundary=None):
    selected = [event for event in events
                if boundary is None or event.get("boundary") == boundary]
    groups = defaultdict(list)
    for event in selected:
        key = (
            str(event.get("instance", "unknown")),
            str(event.get("boundary", "unknown")),
            str(event.get("provider", "unknown")),
        )
        groups[key].append(event)
    if not groups:
        return "No matching structured operation events."

    headings = ("instance", "boundary", "provider", "calls", "ok", "fail",
                "p50_ms", "p95_ms", "fallback")
    rows = []
    for (instance, event_boundary, provider), group in sorted(groups.items()):
        durations = [max(0, float(event.get("duration_ms", 0))) for event in group]
        successes = sum(event.get("outcome") == "success" for event in group)
        fallbacks = sum(bool(event.get("fallback")) for event in group)
        rows.append((
            instance,
            event_boundary,
            provider,
            str(len(group)),
            str(successes),
            str(len(group) - successes),
            str(round(_percentile(durations, 0.50))),
            str(round(_percentile(durations, 0.95))),
            f"{fallbacks / len(group) * 100:.1f}%",
        ))

    widths = [max(len(headings[i]), *(len(row[i]) for row in rows))
              for i in range(len(headings))]

    def format_row(row):
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip()

    return "\n".join([
        format_row(headings),
        format_row(tuple("-" * width for width in widths)),
        *(format_row(row) for row in rows),
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare latency, outcomes, and fallback across bot instances.")
    parser.add_argument("--boundary", choices=(
        "model", "external_fetch", "scheduled_job", "delivery"))
    args = parser.parse_args(argv)
    events = parse_events(sys.stdin)
    report = render_report(events, boundary=args.boundary)
    print(report)
    return 1 if report.startswith("No matching") else 0


if __name__ == "__main__":
    raise SystemExit(main())
