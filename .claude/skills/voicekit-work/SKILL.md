---
name: voicekit-work
description: Working on voicekit-starter/ — the standalone author-voice-profiling CLI. Load for any change inside voicekit-starter/. It is a SEPARATE project sharing this repo — none of the bot's rules (BOT_VERSION, changelog gate, fleet deploy) apply to it, and none of its patterns apply to the bot.
---

# voicekit-starter work

A modular Python CLI (`src/` layout, `pyproject.toml`, entry point
`voicekit = "voicekit.cli:main"`) that extracts author voice profiles from writing
samples, generates voice-matched drafts, and judges drafts against a profile.
OpenAI-compatible API via `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL`.
Modules, all under `voicekit-starter/src/voicekit/`: `cli.py`, `core.py`, `schemas.py`,
`prompts.py`, and `voicekit-starter/src/voicekit/templates/voice_profile_template.json`.

## When NOT to use

- Anything under `telegram-companion-bot/` or repo root — different project,
  different rules. In particular do NOT import the bot's conventions here
  (BOT_VERSION, single-file rule, phone constraints) or voicekit's here
  (modular layout is fine for voicekit, banned for bot.py).
- Author-voice work for the *characters* (preset.txt, cards) — that's
  `edit-cards-and-presets`; voicekit is a general-purpose tool, not bot tooling.

## Procedure

1. Read `voicekit-starter/README.md` and `CHANGELOG.md` (it has its own — update
   it, not the bot's, and keep its existing format). The 2026-07 audit fixes
   (template path, json_mode, warnings — commit `de9b600`) show the repair/
   validation design intent: schema-validated JSON output with repair retries.
2. Install and smoke-test in this container:
   ```bash
   cd voicekit-starter && pip install -e .
   voicekit --help
   ```
3. Make the change. Keep the structured-output contract: profiles must validate
   against `schemas.py`; if you change the schema, change the template AND the
   repair-guidance prompts together — they are one contract in three files.
4. There is currently NO test suite here (verified 2026-07-11). Verification is:
   ```bash
   python -m py_compile voicekit-starter/src/voicekit/*.py
   voicekit --help          # and the changed subcommand's --help
   python3 -m json.tool voicekit-starter/src/voicekit/templates/voice_profile_template.json
   ```
   End-to-end runs need an API key; if none is configured, say exactly what was
   NOT exercised rather than implying it was.
5. Bump `version` in `pyproject.toml` for behavior changes; add a CHANGELOG.md
   entry (voicekit's own).
6. Repo-wide gates still apply — it's the same public repo:
   `bash .claude/evals/run-evals.sh` (secret-scan covers these files too; never
   commit an API key, sample corpus with personal data, or generated profiles of
   real people without the user's say-so).
7. Commit, merge to main, push (same green-merge policy).

## Quality bar

- CLI contract stable: existing flags and output paths keep working unless the
  user asked for a break.
- Schema/template/prompt triple stays consistent.
- Honest verification reporting — no implied end-to-end test that didn't run.

## Verification checklist

- [ ] `pip install -e .` succeeds; `voicekit --help` runs
- [ ] py_compile clean on all touched modules; template JSON valid
- [ ] Schema, template, and prompts consistent after any schema change
- [ ] voicekit's own CHANGELOG + pyproject version updated
- [ ] run-evals.sh green (secret-scan)

## Common mistakes

- Adding an entry to the BOT's changelog or bumping BOT_VERSION for voicekit work
  (the delivery gate won't fire for voicekit files, so nothing catches this).
- Editing the schema without the template/prompts, breaking the repair loop.
- Committing writing samples or generated profiles containing real personal data
  into a public repo.
- Assuming pytest exists here because the bot has one.

## What to report back

What changed, the verification commands' actual output, what could not be
exercised without an API key, and version/changelog updates made.
