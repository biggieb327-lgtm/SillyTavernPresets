# Sprint 1 proactive-receipt pilot

This pilot observes decisions the bot already makes. It must not change send timing,
quiet-hours behavior, nudge budget, mood skips, prompts, or model calls.

## Pilot instance

**Emily (`bot@emily`) is the Sprint 1 pilot instance.** Keep the observer scoped to Emily
until the soak gate below is met. Do not fan it out fleet-wide just to increase sample size.

The observer reads Emily's existing systemd journal and writes only to:

`/opt/telegram-bots/emily/proactive-receipts.jsonl`

It does not import or restart `bot.py`, open a Telegram connection, or mutate Emily's state.
Stopping the observer cannot change Emily's behavior.

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

## Start Emily's pilot observer

The authoritative bot service name and VPS layout come from `OPS_MANUAL.md`: Emily is
`bot@emily`, the repository checkout is `/opt/telegram-bots/.repo`, and her instance state
lives under `/opt/telegram-bots/emily/`.

Get the owner chat id from Emily with `/chatid`, then on the VPS run the launcher from the
repository checkout:

```bash
cd /opt/telegram-bots/.repo
OWNER_CHAT_ID=<value shown by Emily's /chatid> \
  telegram-companion-bot/deploy/start-proactive-receipt-pilot.sh emily
```

Equivalent direct command, useful when debugging the launcher:

```bash
journalctl -u bot@emily -f -o cat | \
  python3 /opt/telegram-bots/.repo/telegram-companion-bot/proactive_receipt_observer.py \
    --chat-id "$OWNER_CHAT_ID" \
    --out /opt/telegram-bots/emily/proactive-receipts.jsonl
```

The launcher is foreground-only on purpose for this first soak. Closing it stops observation
and leaves `bot@emily` untouched. Do not install it as a persistent systemd unit until the
observation format itself has survived the pilot.

## Verify before leaving it running

In a second VPS shell:

```bash
systemctl status bot@emily --no-pager | head -12
tail -n 5 /opt/telegram-bots/emily/proactive-receipts.jsonl
journalctl -u bot@emily -n 30 --no-pager | grep '\[heartbeat\]'
```

The bot must remain active before and after starting/stopping the observer. A receipt should
appear only after a recognized proactive log line occurs; an empty file immediately after
startup is normal.

## Soak checks

For Emily, collect at least seven consecutive days or enough natural activity to observe all
of the heartbeat outcomes that naturally occur. Do not force user-facing sends merely to
populate a receipt class.

Review the JSONL for:

1. `sent`, `skipped`, `drafted`, and `failed` are distinguishable when those outcomes occur;
2. quiet-hours, `/quiet`, `/away`, and budget vetoes are named rather than flattened to
   generic skips;
3. mood and recent-activity skips have `hard_veto: null`;
4. the observer never writes full chat transcripts — only the bounded detail already present
   in an operational log line;
5. stopping/restarting the observer has no visible effect on Emily;
6. counts reconcile with `journalctl -u bot@emily` for the same interval;
7. no other fleet instance produces a `proactive-receipts.jsonl` as part of this pilot.

## Pilot exit record

When the soak ends, record:

- start/end timestamps and Emily's deployed `BOT_VERSION`;
- receipt counts by source and decision;
- counts by `hard_veto`;
- any observer write failures;
- any receipt/journal mismatch;
- whether stopping/restarting the observer changed Emily in any visible way;
- explicit **pass / revise / stop** decision.

A pass means the observer is trustworthy for the sources it can actually identify. It does
**not** close Sprint 1's all-source gate by itself.

## Current limitation and next patch

This observer is an interim safe bridge because the GitHub connector used to build this sprint
cannot apply a surgical patch to the 12k-line `bot.py` without replacing the entire file.
It gives the project a real observation-only soak for paths whose decisions are already logged,
without taking that rewrite risk.

The remaining Sprint 1 instrumentation gap is explicit receipts for health and memory candidate
classes and collision-window correlation. Those should be added at their existing decision
points when a checkout-backed patch path is available; no shared triage/ranking behavior should
ship before that gap is closed.
