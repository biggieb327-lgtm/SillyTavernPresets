# bot_app/

Modular migration package for `bot.py`. `bot.py` remains the process entry point and imports
selected services from here defensively — see **[MIGRATION.md](MIGRATION.md)** for what's
actually wired in, what's still unused scaffolding, and the migration order/status.

`main.py` (repo root) is a standalone smoke test for this package in isolation; it is not part of
the live bot's startup path.
