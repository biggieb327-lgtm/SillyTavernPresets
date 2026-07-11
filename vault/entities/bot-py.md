# bot.py — the fleet codebase

One 9,494-line Python file running all six character instances; instances differ
only by directory, `.env`, and card ([raw/2026-07-11-claude-md.md],
[raw/2026-07-11-bot-py-facts.md]).

- Single-file is a recorded non-goal to change: `/update` swaps one shared file,
  `bot.py.bak` is the rollback ([raw/2026-07-11-claude-md.md],
  [raw/2026-07-11-ops-manual-deploy.md]).
- `BOT_VERSION` (line 84 at capture) is the deploy detection mechanism; must match
  the newest `## v` changelog heading ([raw/2026-07-11-changelog.md]).
- All model output flows through the `_do_request` choke point (strip thinking /
  native tool calls / mojibake) ([raw/2026-07-11-bot-py-facts.md]).
- 162 pure-logic tests import it via a fixture that fakes an instance
  ([raw/2026-07-11-bot-py-facts.md]).
- Serviced by supervisor `run-bot.sh` (explicit `venv/bin/python`), watchdog
  (`.alive` heartbeat), nightly `backup-all.sh`
  ([raw/2026-07-11-operational-log.md], [raw/2026-07-11-ops-manual-deploy.md]).
