# telegram-companion-bot — Path-Scoped Rules

Rules that apply when working in this directory. The root `CLAUDE.md` has
repo-wide instructions; this file has the bot-specific ones.

## Test command

```bash
bash .claude/tools/verify.sh
```

`--quick` drops the advisory sweep and is not enough for a release. For evals
only: `bash .claude/evals/run-evals.sh`.

## Change rules

Every `bot.py` change requires all three — the delivery gate hook enforces this:

1. **`BOT_VERSION` bump** — how `/audit` proves a deploy landed.
2. **`CHANGELOG.md` entry** — root cause first, not symptom.
3. **Compile evidence** — `python3 -m py_compile bot.py`.

Read `CHANGELOG.md` before editing `bot.py` — it records root causes of every
shipped fix, so you know what's already been tried. Skip only for pure content
edits (cards, presets, seed files).

A test must *call* any `*_cmd` handler the diff touches — asserting on source
text is not a test (the `/features` `ValueError` of 2026-08-02 shipped past two
rounds of such "tests").

## Bot instances

All seven run on the VPS under systemd (six migrated 2026-07-26; marcus created
2026-07-29).

| Instance | Directory | Character card |
|----------|-----------|----------------|
| `nora` | `/opt/telegram-bots/nora/` | `nora.json` |
| `bonnie` | `/opt/telegram-bots/bonnie/` | `bonnie.json` |
| `cass` | `/opt/telegram-bots/cass/` | `cass.json` |
| `emily` | `/opt/telegram-bots/emily/` | `emily_harper.json` |
| `priya` | `/opt/telegram-bots/priya/` | `priya.json` |
| `jules` | `/opt/telegram-bots/jules/` | `jules_nakagawa.json` |
| `marcus` | `/opt/telegram-bots/marcus/` | `marcus_calder.json` |

All instances share the venv at `/opt/telegram-bots/venv/`; `bot.py` lives at
`/opt/telegram-bots/bot.py`. Each runs as `bot@<instance>` (unit file
`deploy/bot@.service`, `WorkingDirectory=/opt/telegram-bots/%i`).

The instance directory is the basename on the `=== STARTUP AUDIT === ... Instance:`
line — that runtime value is authoritative if it ever disagrees with this table.
The authoritative instance list is the set of `bot@<instance>` systemd units.

## Stack

- Python **3.12** on the VPS (Ubuntu 24.04) — the `=== STARTUP AUDIT ===` line
  reports the live version; trust it over this file. CI pins the same version in
  `.github/workflows/evals.yml` and the `runtime-version-pinned` eval fails if
  the two diverge — change both together.
- `python-telegram-bot >=21.0,<22.0` (async, job-queue). PTB v21's deprecated
  `asyncio.get_event_loop()` call is worked around in `main()` — don't remove it.
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`.
- SillyTavern `chara_card_v2` JSON cards.
- `requirements.txt` is the single source of truth for pip installs.
- Trained knowledge of these APIs drifts; the pins above don't. Before relying on
  undocumented behavior, check the current source rather than memory. `curl` the
  raw artifact and grep it: `raw.githubusercontent.com` and `pypi.org` are
  reachable. `docs.python-telegram-bot.org` and `nano-gpt.com` are blocked by
  egress policy — for those, the pins here and the code are the only sources a
  session can actually read.

## Deployment

All seven instances deploy from `main` via **`deploy/vps-sync.sh`**, one
invocation per instance — it pulls `preset.txt`, the instance's preset layers
and card, and `bot.py` (compile-checked, `bot.py.bak` kept), normalizes
`CHARACTER_CARD`, restarts and enables the unit, then prints hash + STARTUP
AUDIT verification:

```bash
# host: VPS (as root)
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>
```

It fetches and hard-resets the checkout to `origin/main` before copying, so
running the on-disk copy is correct even when the checkout is stale.

`/update` is dead as a deploy path — the handler downloads over raw URLs, so on
the private repo it fails with `repo_not_readable` and replies telling the owner
to run `vps-sync.sh` instead.

Exact commands, verification, and rollback: the **`deploy-and-verify-fleet`**
skill.

## Phone-era tooling

`update-all.sh`, `sync-cards.sh`, `watchdog.sh`, `run-bot.sh` and
`.supervise.sh` were Termux-only and now manage nothing. VPS deploys go through
`deploy/vps-sync.sh`. Editing phone-era scripts in-repo ships nothing.
