# Single-file deploy

**Idea:** keep the entire deployable a single file so that deployment is "curl one
URL, swap one file, keep one .bak" — executable from a chat command on a phone,
with rollback that survives a broken program.

- Realized as: bot.py + `/update` (compile-check, swap, restart) + `bot.py.bak`
  rollback + raw-URL pulls from `main` ([raw/2026-07-11-ops-manual-deploy.md]).
- Consequence: `main` must never hold a non-deployable tree — CI red on main is a
  deploy blocker ([raw/2026-07-11-run-evals.md]).
- Consequence: refactoring into modules is a recorded non-goal, whatever code
  aesthetics say ([raw/2026-07-11-claude-md.md]).
- Trade-off accepted knowingly: a 9,494-line file is the price of a one-command
  deploy from Telegram ([raw/2026-07-11-bot-py-facts.md]).
