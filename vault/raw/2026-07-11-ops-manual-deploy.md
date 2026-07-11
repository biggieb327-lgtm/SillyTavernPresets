# Raw capture: deployment paths (OPS_MANUAL.md + CLAUDE.md §Deployment)

Sources: `telegram-companion-bot/OPS_MANUAL.md`, `CLAUDE.md` @ commit `d76dcdf`.

> **Preferred (no shell):** push to `main`, send `/update` to **one** bot (verifies
> compile, keeps `bot.py.bak`, swaps the shared file, restarts), then `/restart` to
> the others. Verify each with `/audit` (shows BOT_VERSION).

> **When run-bot.sh changed (shell required)** — `/update` never regenerates the
> supervisor:
> curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash

> **Card/seed-only update:** `sync-cards.sh`, or curl the card into the instance dir
> and rerun `run-bot.sh <dir> <name>`. **.env edit:** edit on-device, then
> `/restart` that bot.

Ops command essentials: `/update` `/restart` `/audit` `/errors [N]` `/backup`.
`/audit` output includes version, uptime, error counts, `State file:` path, PID
(from `audit_cmd`, bot.py:8891 at capture).

Rollback: `~/telegram-bot/bot.py.bak` is the previous bot.py; there is deliberately
no `/rollback` command (rejected — a broken bot can't be trusted to roll itself
back, ROADMAP §Rejected).
