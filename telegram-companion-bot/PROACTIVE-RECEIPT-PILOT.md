# Sprint 1 proactive-receipt pilot

This pilot observes decisions the bot already makes. It must not change send timing,
quiet-hours behavior, nudge budget, mood skips, prompts, or model calls.

## Pilot instance

**Emily (`bot@emily`) is the Sprint 1 pilot instance.** Keep observation scoped to Emily
until the soak gate below is met. Do not fan it out fleet-wide just to increase sample size.

Two complementary receipt writers may exist:

1. **In-bot (preferred after v2026-09-04.2):** `bot.py` appends to
   `/opt/telegram-bots/emily/proactive-receipts.jsonl` via `PROACTIVE_RECEIPTS`
   (default on, fail-soft). Covers heartbeat/check-in, memory-seeded heartbeat,
   health alerts, note follow-ups, cron/payment/reminder sends, with collision-window ids.
2. **Journal observer (legacy soak path):** `proactive_receipt_observer.py` mirrors
   known journal lines into the same JSONL without importing or restarting `bot.py`.

If both run, expect possible duplicate lines for overlapping heartbeat/cron/payment
events. Prefer **one** writer during a clean soak: either keep the observer and set
`PROACTIVE_RECEIPTS=0` on Emily, or disable the observer unit and rely on in-bot writes.

## What in-bot receipts cover (v2026-09-04.2+)

- `check_in`: heartbeat sent/skipped/drafted/failed + named hard vetoes
- `memory`: heartbeat send whose candidate was seeded by a date-matched memory note
- `health`: stress / body-battery (and related) alert send/skip/fail
- `day_life`: dated-note follow-up send/skip/fail
- `reminder`: cron, payment, and `/reminder` fires

Each receipt includes a deterministic 30-minute `collision_window` for offline analysis
with `proactive_receipt_analysis.py`.

## What the journal observer still covers

`proactive_receipt_observer.py` recognizes existing log lines for:

- heartbeat/check-in: recent-activity skip, quiet hours, `/quiet`, recurring quiet window,
  `/away`, nudge-budget exhaustion, mood soft-skip, sent, and failed;
- dated user-note follow-ups: sent and failed (`day_life` source);
- payment reminders and `/cron` scheduled sends: sent/failed (`reminder` source).

It ignores unknown lines instead of guessing. Health and memory provenance require the
in-bot path above.

## Inspect receipts on the pilot instance

```bash
# In-bot JSONL (after deploy of v2026-09-04.2+)
tail -n 20 /opt/telegram-bots/emily/proactive-receipts.jsonl

# Budget + skip reasons (also shows recent receipt skips)
# In Telegram, as owner:
#   /nudges

# Offline collision summary
python3 /opt/telegram-bots/.repo/telegram-companion-bot/proactive_receipt_analysis.py \
  /opt/telegram-bots/emily/proactive-receipts.jsonl
```

Kill switch (behavior-neutral): set `PROACTIVE_RECEIPTS=0` in Emily's `.env` and restart
`bot@emily` — send/skip paths are unchanged; only receipt writes stop.

## Persistent Emily soak (journal observer)

The foreground launcher is useful for a smoke test, but a journal-based soak should run under its
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
4. receipts never write full chat transcripts — only bounded previews/fingerprints;
5. stopping receipt writers (`PROACTIVE_RECEIPTS=0` or observer stop) has no visible effect on Emily;
6. counts reconcile with `journalctl -u bot@emily` for the same interval when using the observer;
7. health and memory sources appear when those paths fire (in-bot path).

## Pilot exit record

When the soak ends, record:

- start/end timestamps and Emily's deployed `BOT_VERSION`;
- receipt counts by source and decision;
- counts by `hard_veto`;
- any write failures or systemd restarts;
- any receipt/journal mismatch;
- whether disabling receipts changed Emily in any visible way;
- explicit **pass / revise / stop** decision.

## Sprint 1 instrumentation status

- fixed quality corpus: done
- receipt contract + writer: done
- Emily soak path: done
- in-bot health + memory provenance + collision windows: done (v2026-09-04.2)
- shared triage/ranking changes under this sprint: **not started (deferred)**
