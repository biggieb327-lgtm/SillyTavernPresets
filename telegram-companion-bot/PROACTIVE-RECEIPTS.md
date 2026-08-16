# Proactive candidate receipts — Sprint 1 contract

Sprint 1 requires observability before a shared proactive triage queue changes behavior.
A **candidate receipt** is the owner-readable record of why one proactive opportunity was
sent or skipped. The first implementation should be append-only JSONL and behavior-neutral:
record today's decision; do not introduce a new decision rule merely to produce the log.

## Required fields

```json
{
  "ts": "2026-08-15T15:40:12-07:00",
  "chat_id": 123,
  "source": "reminder",
  "candidate_id": "optional stable/local id",
  "decision": "sent",
  "reason": "due reminder passed existing budget/quiet-hours gates",
  "hard_veto": null,
  "scores": {
    "timing": null,
    "specificity": null,
    "novelty": null,
    "pressure": null
  },
  "collision_window": null,
  "text_fingerprint": "sha256-prefix-or-similar",
  "text_preview": "short redacted/owner-readable preview"
}
```

`decision` is one of `sent`, `skipped`, `drafted`, `failed`.

The score fields are nullable in the observation-only phase. Sprint 1 must not pretend a
runtime scorer exists before it does. The fixed corpus in `evals/proactive_quality_corpus.json`
defines what those dimensions mean and supplies the evaluation baseline.

## Source taxonomy

Use a small stable vocabulary so receipts aggregate cleanly:

- `reminder` — explicit reminder/cron candidate;
- `health` — Garmin or other health-derived proactive candidate;
- `memory` — remembered topic/callback becoming worth surfacing;
- `day_life` — day, schedule, milestone, or life-event follow-up;
- `check_in` — ordinary heartbeat/silence-break candidate;
- `other` — temporary escape hatch; every persistent `other` source should earn a named value.

## Hard vetoes vs future ranking signals

The shared triage design in ROADMAP 5.1 must preserve a structural distinction:

### Hard vetoes — never outweighed by urgency

- quiet hours / explicit do-not-disturb state;
- explicit user limits or disabled feature flags;
- safety/privacy policy;
- exhausted proactive-message budget;
- stale/invalid source data that makes the candidate factually unsafe to send.

A receipt should put the veto name in `hard_veto` and make `reason` human-readable.

### Ranking / quality signals — compare eligible candidates later

- timing quality within an otherwise allowed window;
- specificity to a real fresh event/fact;
- novelty relative to recent proactive sends;
- pressure / ease of ignoring;
- urgency/relevance after the quality gate;
- collision with another eligible candidate in the same decision window.

No ranking signal can cancel a hard veto.

## Privacy and retention

Receipts are operational evidence, not a second memory store. They should not persist full
private message text by default. Keep a short owner-readable preview plus a stable fingerprint
sufficient to correlate repeated candidates. Use the existing state/log retention posture
rather than inventing an unbounded archive.

## Sprint 1 acceptance checks for instrumentation

Before the future triage queue is allowed to change sends, a pilot instance must demonstrate:

1. each proactive candidate class can leave a receipt at its existing decision point;
2. sent, skipped, drafted, and failed outcomes are distinguishable;
3. quiet-hours/budget/feature vetoes name the veto rather than collapsing to “skipped”;
4. simultaneous eligible candidates can share a collision-window id;
5. disabling/removing receipt logging leaves proactive behavior identical to the baseline;
6. the owner can inspect enough context to answer “why did this send/skip?” without reading raw logs end-to-end.

The instrumentation implementation should be reviewed against this contract before any shared
queue or new runtime quality scorer is introduced.
