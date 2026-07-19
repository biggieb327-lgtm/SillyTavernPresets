# Staged skill library — written 2026-07-11

> **2026-07-17:** the original ten-skill batch was owner-reviewed and promoted in
> full (each skill fact-checked against the repo per step 1 below; router rows
> added in the same commit). `_staging/` is now empty except this README, which
> stays as the procedure for any future staged skill.

These skills are STAGED, not live. Claude Code only auto-discovers skills directly
under `.claude/skills/<name>/SKILL.md`, so nothing in `_staging/` loads until promoted.

## How to promote a skill

1. Read it. Check the facts against the repo (paths, commands, file names).
2. `git mv .claude/skills/_staging/<name> .claude/skills/<name>`
3. Add its row to the table in `.claude/skills/skill-router/SKILL.md` **in the same
   commit** — unregistered skills are invisible tomorrow (skill-router's own rule).
4. Commit with a message saying which skill went live and why.

## Proposed skill-router rows (paste into the router table when promoting)

| Trigger | Load |
|---|---|
| Any bot.py change that will ship (feature, fix, refactor) | `repo-change-control` |
| Reviewing or writing any bot.py diff (also loaded by repo-change-control) | `bot-code-invariants` |
| A live bot is misbehaving, restarting, or silent | `repo-debugging-playbook` |
| Work is merged; user needs to get it onto the fleet, or a deploy went wrong | `deploy-and-verify-fleet` |
| Editing character cards, seed files, preset.txt, or root SillyTavern presets | `edit-cards-and-presets` |
| Same failure class happened twice, or user asks to pin a check | `add-regression-eval` |
| External audit/review output (LLM or human) lists claimed bugs | `verify-external-audit` |
| Touching any GROUP_* code, the ledger, or bot-to-bot behavior | `group-chat-changes` |
| Moving instances from the phone to a VPS (ROADMAP 1.2) | `vps-migration` |
| Working in voicekit-starter/ | `voicekit-work` |

## Known-good baseline when these were written

- `main` == `claude/clean-git-branch-dvmldk` == `8d4b23e`, BOT_VERSION `2026-07-11.6`,
  162 pytest tests, eval suite 14 checks — all verified green on 2026-07-11, but only
  after TWO environment fixes a fresh remote container needs:
  1. `pip install -r telegram-companion-bot/requirements.txt pytest`
     (otherwise `bot-imports` fails on missing Pillow — not a code bug)
  2. `pip install --upgrade cryptography`
     (Debian's system cryptography panics with `pyo3_runtime.PanicException` at
     pytest collection — also not a code bug)
- Container Python here is 3.11; CI and the phone run 3.13. Local green is strong
  evidence, CI on main is the authority.
