# Sprint 1 proactive-receipt pilot

This pilot observes decisions the bot already makes. It must not change send timing,
quiet-hours behavior, nudge budget, mood skips, prompts, or model calls.

## What the observer covers

`proactive_receipt_observer.py` recognizes existing log lines for:

- heartbeat/check-in: recent-activity skip, quiet hours, `/quiet`, recurring quiet window,
  `/away`, nudge-budget exhaustion, mood soft-skip, sent, and failed;
- dated user-note follow-ups: sent and failed (`day_life` source);
- payment reminders and `/cron` scheduled sends: sent/failed (`reminder` source).

It ignores unknown lines instead of guessing. Health-specific and memory-specific candidates
are **not yet independently observable from current logs**; reaching Sprint 1's all-source
acceptance gate will require either an explicit log line at those existing decision points or
a later narrow `bot.py` instrumentation patch.

## Pilot command

Run against one instance only. Substitute the real owner chat id and instance name:

```bash
cd /opt/telegram-bots/telegram-companion-bot
journalctl -u bot@jules -f -o cat | \
  python3 proactive_receipt_observer.py \
    --chat-id "$OWNER_CHAT_ID" \
    --out /opt/telegram-bots/jules/proactive-receipts.jsonl
```

The observer can be stopped at any time. Stopping it cannot affect the bot because it is only
a journal reader.

## Soak checks

For the first pilot, collect at least seven days or enough activity to observe all of the
heartbeat outcomes that naturally occur. Do not force user-facing sends merely to populate
a receipt class.

Review the JSONL for:

1. `sent`, `skipped`, `drafted`, and `failed` are distinguishable when those outcomes occur;
2. quiet-hours, `/quiet`, `/away`, and budget vetoes are named rather than flattened to
   generic skips;
3. mood and recent-activity skips have `hard_veto: null`;
4. the observer never writes full chat transcripts — only the bounded detail already present
   in an operational log line;
5. stopping/restarting the observer has no visible effect on the bot;
6. counts reconcile with the source journal for the same interval.

## Current limitation and next patch

This observer is an interim safe bridge because the GitHub connector used to build this sprint
cannot apply a surgical patch to the 12k-line `bot.py` without replacing the entire file.
It gives the project a real observation-only soak for paths whose decisions are already logged,
without taking that rewrite risk.

The remaining Sprint 1 instrumentation gap is explicit receipts for health and memory candidate
classes and collision-window correlation. Those should be added at their existing decision
points when a checkout-backed patch path is available; no shared triage/ranking behavior should
ship before that gap is closed.
