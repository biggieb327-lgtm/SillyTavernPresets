# Agent operating layer — .claude/

The machinery that makes repo rules enforceable rather than prose: 9 agents,
5 hooks, a 14-check eval suite mirrored in CI, skills, and memory files
([raw/2026-07-11-run-evals.md], [raw/2026-07-11-operational-log.md]).

- Delivery gate (Stop hook) blocks ending a turn with modified bot.py lacking a
  BOT_VERSION bump, changelog entry, or compile evidence
  ([raw/2026-07-11-claude-md.md]).
- Risk guard (PreToolUse) blocks force-push to main, root-ish `rm -rf`, staging
  `.env` files ([raw/2026-07-11-claude-md.md]).
- Eval discipline: every check pins a real incident; a failure recurring twice
  earns a new eval ([concepts/incident-pinned-evals.md]).
- Skills: live under `.claude/skills/` (router-indexed); a 10-skill library sits
  in `_staging/` pending owner review (built 2026-07-11).
- Memory: `.claude/memory/operational-log.md` (one row per failure that changed
  the system); `.claude/operating/fable-to-opus.md` (session handoff);
  `.claude/OPERATING_MANUAL.md` (general method).
