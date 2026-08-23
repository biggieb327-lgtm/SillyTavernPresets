# AGENTS.md

## Project overview

A Python Telegram companion-bot fleet: seven AI character instances share **one**
`telegram-companion-bot/bot.py`, differing only by directory, `.env`, and SillyTavern
v2 character card. All seven run on a VPS under systemd. The repo root also archives
standalone SillyTavern presets/cards and an unrelated `voicekit-starter/`.

This repo already has a durable, versioned context system. **Use it in place; do not
duplicate its facts into a second project-memory store.** `CLAUDE.md` is the canonical
instruction set, documentation map, authority order, and deployment policy — read it
first, and link deeper docs instead of repeating them here.

## Read order

1. `CLAUDE.md` — every task.
2. `.claude/OPERATING_MANUAL.md` — non-trivial work.
3. `.claude/skills/skill-router/SKILL.md`, then load only the skill(s) it routes to.
4. `.claude/operating/fable-to-opus.md` + `.claude/memory/constraints.md` — multi-step,
   behavior-changing, or fleet-touching work.
5. Newest `.claude/operating/HANDOFF-*.md` — broad view. Its numbers are a dated
   snapshot; runtime output and current code win.

Do not create a second quick-reference documentation map. `CLAUDE.md` and the skill
router own the routing layer; copied maps drift (eval-enforced).

## Context retrieval

- Retrieve by task. Do not preload large logs, handoffs, the roadmap, or unrelated skills.
- Prefer runtime output for live state; then current code/config; then `CLAUDE.md` and
  the relevant canonical doc; then dated handoffs or audits.
- If the Notion Fleet Knowledge Base is available, search `Status=current` entries before
  non-trivial work. The repo's reviewed memory files remain the system of record.
- `vault/` is a pinned 2026-07-11 archive, not current truth.
- The bot's runtime memory is its own engine. Do not add Mem0 or another runtime memory
  backend unless the task explicitly approves a migration plan and verification.

## Project structure

- `telegram-companion-bot/` — everything that deploys: `bot.py` (single file), the seven
  character cards + seed dirs, `preset.txt` (shared voiceprint), `tests/`, `deploy/` (VPS),
  and the canonical docs (CHANGELOG, ROADMAP, OPS_MANUAL, …).
- `.claude/` — the agent system: `skills/`, `evals/`, `hooks/`, `tools/`, `memory/`,
  `operating/`.
- Repo root also holds standalone SillyTavern presets/cards and the unrelated
  `voicekit-starter/` — none of the bot's rules apply there.

## Setup & build

- Python **3.12**; `python-telegram-bot >=21,<22`. `requirements.txt` is the single
  source of truth for pip installs. `bot.py` stays one file — the deploy model depends on it.

```bash
pip install -r telegram-companion-bot/requirements.txt   # setup
telegram-companion-bot/deploy/vps-sync.sh <instance>     # deploy one instance (VPS, root)
```

## Testing

```bash
.claude/tools/verify.sh                       # full gate: compile, pytest, evals, corpus, sweep
.claude/tools/verify.sh --quick               # drops the sweep — NOT enough for a release
.claude/evals/run-evals.sh                    # evals only (past incidents pinned as checks)
pytest telegram-companion-bot/tests/test_pure.py -k <name>   # a single test
```

- Run `verify.sh` before claiming **any** change done; report the command actually run.
- Never delete, weaken, disable, or rewrite a test/eval to make a change pass. Fix what
  it checks, or state the exception. The one legitimate exception is widening a check's
  scope, same commit, rationale written down.
- Do not claim an interrupted or timed-out run passed. Distinguish verified facts from
  assumptions.
- A bot.py change MUST ship: BOT_VERSION bump + a `CHANGELOG.md` row (root cause first) +
  compile evidence + a test that *calls* any `*_cmd` the diff touches. The delivery-gate
  hook blocks the turn otherwise.

## Code style

- Lint/compile is part of the gate: `python -m py_compile telegram-companion-bot/bot.py`
  (also run by `verify.sh`, which adds the advisory sweep across `.claude/`).
- Match neighboring files. Use the repo's own words — if a thing has a name in the code
  (env var, function, command, unit), use that name verbatim; invent no new terms silently.
- Plain words over coined ones in reports, commits, and docs. Do not add comments that
  restate the code. Do not reformat code you are not otherwise changing.

## Git workflow

- Develop on `claude/...` branches; **merge green work to `main`** — deploys and doc links
  pull from `main`. Owner policy: merge to `main` autonomously once the full verification
  block is green (`git push origin <branch>:main`, a fast-forward). This repo does **not**
  follow "never push unless asked."
- New features default **ON** with a mandatory env kill switch (unset = active, `0` = off).
- CI (`.github/workflows/evals.yml`) must be green on `main`/`claude/**`; a red run on
  `main` is a deploy blocker.

## Boundaries

- Do not modify unrelated files or widen scope beyond the request. Surface out-of-scope
  smells as follow-ups; keep them out of the diff.
- Do not add a dependency without cause. Never write secrets or live credentials into
  repository context files; `.claude/.runtime/` is gitignored — never commit it.
- If a command fails, report the failure. Do not guess or present assumptions as confirmed.

## Response style

Lead with the answer. Short sentences, active voice, familiar words. A few short
paragraphs or bullets; add detail only when it helps the user decide or act. Keep risks,
uncertainty, and verification results even when brief. Ask one focused question only when
missing information would materially change the result.

## Completion

Follow the verification and delivery rules in `CLAUDE.md` and the selected skills. Report
the commands actually run, distinguish verified facts from assumptions, and leave
out-of-scope findings as follow-ups rather than silently expanding the change.
