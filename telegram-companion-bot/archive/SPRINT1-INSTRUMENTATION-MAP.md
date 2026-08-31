# Sprint 1 remaining instrumentation map

This note pins the remaining receipt work to existing behavior before any `bot.py` patch is attempted. The purpose is to avoid inventing a new proactive path just to satisfy an eval category.

## What is already observable

The journal observer currently identifies:

- `check_in`: heartbeat sent/skipped/drafted/failed outcomes and existing hard vetoes;
- `reminder`: payment and cron sends/failures;
- `day_life`: dated-note follow-up sends/failures.

Collision analysis is offline and behavior-neutral: `proactive_receipt_analysis.py` groups receipts into deterministic 30-minute windows and only calls a window a collision when more than one distinct proactive source appears.

## Memory/topic candidate

The existing heartbeat path already has memory/topic inputs rather than a separate memory sender:

- `_todays_memory_note` can inject a date-matched memory into the heartbeat trigger;
- `_generate_proactive_hook` uses user notes/recent exchange/life context to create a concrete heartbeat seed;
- prior fixes explicitly prevent `[own-day ...]` character fiction from being treated as user/shared memory.

Therefore the narrow instrumentation target should be **candidate provenance inside the heartbeat**, not a second send path. A future patch should emit an unambiguous operational log marker when the final heartbeat candidate was materially seeded by a memory/topic input, for example a marker carrying only source class + bounded fingerprint/id, never the full memory text. The observer can then classify that receipt as `source="memory"` while preserving the exact send/skip decision already made by heartbeat.

Do not add another LLM call, another send, or another memory lookup for instrumentation.

## Health candidate

Repository history does not establish a separate health-specific proactive sender on current main. `HEALTHCHECK_URL` is operational dead-man monitoring and must **not** be mislabeled as a companion health-signal candidate.

Before adding `source="health"` receipts, locate an actual user-facing health/wellbeing signal that can cause a proactive candidate. If none exists on current main, record the Sprint 1 finding as **no production health candidate path exists** rather than manufacturing one. The eval corpus may still retain health examples for the future shared queue, but live receipt coverage must describe reality.

## Collision correlation

Use receipt timestamps, not changes to send behavior. Default window: 30 minutes.

A collision requires:

1. at least two receipts in the same deterministic window; and
2. at least two distinct proactive sources.

Two reminders in the same window are not a cross-source collision. A sent heartbeat plus a skipped/drafted memory candidate in the same window still counts as a candidate collision because Sprint 1 is measuring independent triggers, not only duplicate Telegram sends.

## Patch acceptance rules

Any later `bot.py` instrumentation patch must satisfy all of these:

- no new Telegram/API/LLM calls;
- no new gate, score, sleep, retry, or timing decision;
- no change to existing sent/skipped/drafted behavior;
- logging failure cannot suppress or create a proactive message;
- no full memory/user-note/chat text in the receipt/log marker;
- own-day provenance remains excluded from user-memory classification;
- observer continues to ignore unknown lines instead of guessing.

## Sprint 1 status after this map

- fixed quality corpus: done;
- receipt contract: done;
- Emily behavior-neutral soak: running;
- check-in/reminder/day-life live observation: done;
- collision-window analysis: implemented on this branch;
- memory/topic provenance marker: specified, narrow `bot.py` patch still required;
- health live path: must be proven to exist before instrumentation; otherwise document as not applicable on current production main.
