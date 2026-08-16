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

## Persistent Emily soak

The foreground launcher is useful for a smoke test, but the seven-day soak should run under its
own systemd unit so an SSH disconnect cannot stop observation. The observer service is
**deliberately independent** of `bot@emily`: its unit contains no `Requires=`, `Wants=`, or
`PartOf=` relationship to the bot unit. Starting, stopping, restarting, enabling, or disabling
the observer therefore does not manipulate Emily's bot process.

After the systemd-observer PR is merged, update the VPS checkout to current `main`. The VPS
uses the repository-specific read-only SSH key; if needed, bind the checkout once with:

```bash
cd /opt/telegram-bots/.repo
git config core.sshCommand 'ssh -i /root/.ssh/stpresets_ro -o IdentitiesOnly=yes'
git fetch origin
git reset --hard origin/main
```

Then install the persistent Emily observer. Invoke the installer through `bash` so installation
does not depend on the repository file's executable bit:

```bash
cd /opt/telegram-bots/.repo
OWNER_CHAT_ID=8121667008 \
  bash telegram-companion-bot/deploy/install-proactive-receipt-observer.sh emily
```

The installer:

- refuses to proceed unless `bot@emily.service` is already active;
- installs `/etc/systemd/system/proactive-receipt-observer@.service`;
- stores Emily's owner id in `/etc/telegram-bots/proactive-receipt-emily.env` mode `0600`;
- runs `systemctl daemon-reload`;
- enables and starts only `proactive-receipt-observer@emily.service`.

The observer starts reading at the **end** of the journal (`journalctl -n 0 -f`), so a restart
will not replay old heartbeat lines into duplicate receipts.

## Verify persistence

```bash
systemctl status bot@emily --no-pager | head -12
systemctl status proactive-receipt-observer@emily --no-pager | head -15
systemctl is-enabled proactive-receipt-observer@emily
journalctl -u proactive-receipt-observer@emily -n 30 --no-pager
tail -n 10 /opt/telegram-bots/emily/proactive-receipts.jsonl
```

`active (running)` plus `enabled` on the observer means it survives SSH disconnects and reboot.
An empty or unchanged receipt file immediately after startup is normal; it advances only when
a recognized proactive decision appears in Emily's journal.

To prove independence safely:

```bash
systemctl stop proactive-receipt-observer@emily
systemctl is-active bot@emily
systemctl start proactive-receipt-observer@emily
systemctl is-active bot@emily
```

Both bot checks must still return `active`. Do **not** stop `bot@emily` as part of this test.

To remove persistence after the soak while leaving Emily untouched:

```bash
systemctl disable --now proactive-receipt-observer@emily
```

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
- any observer write failures or systemd restarts;
- any receipt/journal mismatch;
- whether stopping/restarting the observer changed Emily in any visible way;
- explicit **pass / revise / stop** decision.

A pass means the observer is trustworthy for the sources it can actually identify. It does
**not** close Sprint 1's all-source gate by itself.

## Current limitation and next patch

The remaining Sprint 1 instrumentation gap is explicit receipts for health and memory candidate
classes and collision-window correlation. Those should be added at their existing decision
points when a checkout-backed patch path is available; no shared triage/ranking behavior should
ship before that gap is closed.
