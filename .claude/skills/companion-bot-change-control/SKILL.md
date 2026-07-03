---
name: companion-bot-change-control
description: >
  Change-control rules for telegram-companion-bot. Load this BEFORE committing anything,
  before telling the owner how to deploy, before editing bot.py or bot_app/, before touching
  a character card (nora/bonnie/cass/emily/jules/priya JSON), before editing preset.txt,
  .env.example, update-all.sh or any helper script, and whenever you need to classify a
  change ("how does this ship?", "is this safe to auto-deploy?", "does this need owner
  sign-off?"). Covers the four non-negotiable rules, the change-classification table,
  the commit checklist, and changes that look safe but aren't.
---

# Companion-Bot Change Control

Runbook for shipping changes to `telegram-companion-bot/` safely. Facts here were verified
against the repo on 2026-07-02; re-verify anything volatile with the commands in
"Provenance and maintenance" at the bottom.

## When NOT to use this skill

| You are doing... | Use instead |
|---|---|
| Deploy mechanics on the phone (tmux, run-bot.sh, watchdog, restarting one bot) | `companion-bot-device-ops` |
| Diagnosing a bug (log spelunking, hypothesis testing) | `companion-bot-debugging-playbook` |
| Updating docs (OPS_MANUAL, PROJECT_CONTEXT, READMEs) | `companion-bot-docs-and-writing` |
| Deciding what counts as evidence / test standards | `companion-bot-validation-and-qa` |

This skill answers one question: **given a change, what gate does it pass through and how
does it reach the device?**

## Jargon (defined once)

- **The device / the phone**: the owner's Android phone running Termux. It has a git clone
  at `~/stp-deploy` and runs six bot instances from `~/telegram-bot/` (shared code) plus
  per-character instance dirs `~/nora-bot/`, `~/bonnie-bot/`, `~/cass-bot/`, `~/emily-bot/`,
  `~/jules-bot/`, `~/priya-bot/` (each with its own `.env`, `state.json`, character files).
- **update-all.sh**: the owner's one-command deploy, run on the device as
  `bash ~/telegram-bot/update-all.sh`. It git-pulls `~/stp-deploy`, copies code + helper
  scripts to `~/telegram-bot/`, and restarts all instances. Source of truth:
  `/home/user/SillyTavernPresets/telegram-companion-bot/update-all.sh`.
- **Working branch**: `claude/push-to-repo-7i2f3c` in this cloud repo. Deploy = commit/push
  here, then the owner runs update-all.sh on the phone.
- **Instance state files**: hand-managed per-bot files on the device, gitignored, listed in
  `telegram-companion-bot/.gitignore` (as of 2026-07-02): `.env`, `state.json`,
  `state.json.corrupted`, `payments.json`, `reminders.json`, `cron_jobs.json`, `jokes.json`,
  `wardrobe.json`, `owner_chat.txt`, `bot.log`, `reading.txt`.
- **There are NO tests and NO CI.** The only automated gate is a PreToolUse hook in
  `.claude/settings.json` that runs `py_compile` on `bot.py` before any `git commit`.

## Change-classification table

Classify EVERY change before committing. When one commit spans classes, the strictest
gate applies and your deploy instructions must cover every class touched.

| Class | Examples | Gate | How it reaches the device |
|---|---|---|---|
| **(a) Code** | `bot.py`, `bot_app/**`, `acoustic_ears.py` | py_compile hook; evidence rule for bug fixes (Rule 2) | Auto: commit/push, owner runs `bash ~/telegram-bot/update-all.sh` (copies + `cmp`-verifies bot.py, rsyncs bot_app/, restarts all bots) |
| **(b) Helper scripts** | `run-bot.sh`, `watchdog.sh`, `status.sh` | Manual read-through (they run unattended on the phone) | Auto: synced + `chmod +x` by update-all.sh |
| **(b')** `update-all.sh` **itself** | any edit to it | Extra care: it IS the deploy path | NOT self-synced (unsafe to overwrite mid-run). Owner must do one manual copy first: `cp ~/stp-deploy/telegram-companion-bot/update-all.sh ~/telegram-bot/update-all.sh` — then future runs use the new version |
| **(c) Character files** | `nora/nora.json`, `bonnie/*.txt`, etc.; `preset.txt` | Rule 3 (voice preservation, owner sign-off for voice changes) | NEVER auto-deployed. update-all.sh does not touch them. Owner copies by hand into the instance dir and restarts that bot, e.g. `cp ~/stp-deploy/telegram-companion-bot/nora/nora.json ~/nora-bot/nora.json && bash ~/telegram-bot/run-bot.sh ~/nora-bot nora` |
| **(d) Gitignored instance files** | `wardrobe.json`, `jokes.json`, `reminders.json`, ... | Rule 4 (never auto-touch) | Can NEVER ship via git — they're gitignored. Deliver as paste-able commands/content for the owner to apply by hand on the device |
| **(e) `.env` secrets/config** | API keys, `EMBED_MODEL`, feature flags | Rule 4; owner-only | Manual only. update-all.sh never touches `.env`. Give the owner the exact line to add/change in `~/<char>-bot/.env` |
| **(f) `.env.example`** | new config option's documented default | Normal commit | Synced by update-all.sh as a **template only** — running bots never read it; it's copied when setting up a new instance |

Notes verified against `update-all.sh` (2026-07-02):
- It syncs exactly: `bot.py` (with `cmp -s` verification), `bot_app/` (rm-then-copy),
  `acoustic_ears.py`, `run-bot.sh`/`watchdog.sh`/`status.sh` (with `chmod +x`), and
  `.env.example`. Nothing else. In particular **`preset.txt` and character dirs are NOT
  synced** — they are class (c). (Itemized manifest: companion-bot-device-ops §5.)
- It auto-stashes stray changes in `~/stp-deploy`, fails loudly (`exit 1`) if
  `git pull --ff-only` fails, and restarts all six instances (`nora`, `bonnie`, `cass`,
  `emily`, `jules`, `priya`) via `run-bot.sh <dir> <session>`, skipping any whose instance
  dir doesn't exist.

## The four non-negotiables

Owner-confirmed rules. This section is the canonical statement (siblings cite it). Do not
trade any of them away for convenience.

### 1. bot.py stays the entry point

The `bot_app/` package is a strangler-fig migration
(`telegram-companion-bot/bot_app/MIGRATION.md`), and its guiding principle is explicit:
`bot.py` remains the process entry point the whole way through; there is no switch to
`main.py`. `bot.py` imports `bot_app` defensively (see the try/except around bot.py:1445 —
a missing package logs a warning and disables only the migrated subsystems) and **must run
standalone if `bot_app/` is missing**.

Concretely:
- Never move code out of bot.py in a way that makes bot.py crash without bot_app/.
- Every new bot_app call site in bot.py must be guarded the same way the existing
  `_mem_service`/`_guards`/`_action_allowed`/`_ingestion` sites are.
- Never change how the bots are launched (`python -u bot.py '<instance-dir>'` via
  run-bot.sh) as a side effect of refactoring.
- MIGRATION.md marks steps 1 and 7 as deliberately skipped/deferred and step 6
  (`assemble_messages`) as intentionally last, behind parity tests. Don't "helpfully"
  do them.

### 2. Evidence before fixes

No fix ships on a guess. Every bug report gets: hypothesis → a diagnostic command that can
**discriminate** between hypotheses → confirm/refute → only then code changes.
(Evidence standards live in `companion-bot-validation-and-qa`; the diagnosis workflow in
`companion-bot-debugging-playbook`. This rule is the change-control gate: a fix commit
without confirmed evidence is blocked.)

The incident: a "heartbeat firing right after I message her" report was nearly misfixed
**twice** — first it looked like the follow-up feature, then like the heartbeat system
itself. Log evidence ruled out both; the real cause was a third system (event reminders
lacking an owner-active check). Wrong-diagnosis rabbit holes are one of the owner's two
costliest failure classes. If your diagnostic output would look the same under two
hypotheses, it is not a diagnostic — find one that separates them.

### 3. Never rewrite a character's voice

Character card JSON and context files (`nora/`, `bonnie/`, `cass/`, `emily/`, `jules/`,
`priya/`) may be **restructured** (fields reorganized, typos, mechanical fixes) but the
established personality and prose voice must be preserved verbatim wherever possible.
Any change that alters how a character sounds — tone, narration style, vocabulary,
system_prompt phrasing — needs explicit owner sign-off BEFORE committing.

Known intentional per-character exceptions you must not "fix": `preset.txt`'s default rule
bans asterisk actions, but Bonnie, Emily, and Jules's card `system_prompt` fields
deliberately override it with third-person/action-beat prose (documented at bot.py:220-225
and in `docs/PROJECT_INSTRUCTIONS.md`). That is design, not drift.

### 4. Never auto-touch device state

`.env`, `state.json`, `wardrobe.json`, `owner_chat.txt` and every other file in
`telegram-companion-bot/.gitignore` are hand-managed on the phone. `update-all.sh`
deliberately never touches them — that is why the owner can deploy without fear. No script,
commit, or instruction you produce may overwrite them automatically.

- Never add a `cp`/`rm`/`sed -i` targeting an instance state file to update-all.sh or any
  helper script.
- When a change needs state-file edits, produce a **paste-able command** the owner runs
  himself, clearly labeled per bot, e.g.
  `nano ~/nora-bot/.env` or `printf '...' >> ~/bonnie-bot/wardrobe.json` — and say what it
  changes before he runs it.
- If bot.py gains a new state file, add it to `telegram-companion-bot/.gitignore` in the
  same commit.

## Commit checklist

Run through this for every commit, in order:

1. **Classify** the change against the table above. Mixed commit? List every class and
   the deploy step each one needs.
2. **Verify names exist** — grep before assuming any function/variable/env var
   (CLAUDE.md rule 5):
   ```bash
   grep -n "the_name_you_are_about_to_use" telegram-companion-bot/bot.py
   ```
3. **Syntax-check** (the PreToolUse hook in `.claude/settings.json` enforces this and
   blocks the commit otherwise, but run it yourself first):
   ```bash
   python3 -c "import py_compile; py_compile.compile('telegram-companion-bot/bot.py', doraise=True)"
   ```
4. **Re-read your changed lines** after editing (CLAUDE.md rule 5). Diff should contain
   only lines traceable to the request — no adjacent "improvements".
5. **Multi-line commit messages: use `-F`, never `-m` with embedded quotes** — shell
   quoting with apostrophes has corrupted commit messages before:
   ```bash
   cat > /tmp/claude-0/msg.txt <<'EOF'
   Short subject line

   Body with apostrophes, it's fine here.
   EOF
   git commit -F /tmp/claude-0/msg.txt
   ```
6. **No PRs unless the owner asks.** Work lands directly on `claude/push-to-repo-7i2f3c`.
7. **Tell the owner how to deploy**, per class:
   - class (a)/(b)/(f) only: "commit is pushed — run `bash ~/telegram-bot/update-all.sh`".
   - class (b') touched: prepend the one-time
     `cp ~/stp-deploy/telegram-companion-bot/update-all.sh ~/telegram-bot/update-all.sh`
     (after a `git -C ~/stp-deploy pull`).
   - class (c) touched: give the exact per-file `cp` from `~/stp-deploy/...` into the
     instance dir(s) plus the single-bot restart.
   - class (d)/(e) touched: give paste-able device commands; never script them.

## Changes that look safe but aren't

- **Adding a comment to `preset.txt`.** Its entire content is injected VERBATIM as live
  prompt text (bot.py:220-225) — no comment syntax survives; a "# note to maintainers"
  becomes text the character reads every message. Documentation about preset.txt lives in
  bot.py code comments, not in the file. (Contrast: `places.txt` DOES support `#` comments
  — per `docs/OPS_MANUAL.md`. Don't generalize either way.)
- **"Tightening" preset.txt's no-asterisk rule.** Bonnie/Emily/Jules intentionally override
  it in their card system_prompts. A preset.txt edit must not be worded so it silently
  overrides or fights those exceptions (the cards win because they're the more specific,
  later instruction — keep it that way).
- **Editing `update-all.sh`.** It does not sync itself; if you change it and only say "run
  update-all.sh", the owner runs the OLD version. Always include the manual one-time `cp`.
  Also preserve its three safety behaviors: auto-stash of stray changes, loud failure on
  `git pull --ff-only`, and the `cmp -s` verification of the copied bot.py — they exist
  because a `set -e` abort once left stale code silently running (the owner's other
  costliest failure class). Never weaken them.
- **Editing a character card "just to reformat".** Restructure is allowed; voice drift is
  not (Rule 3). If a diff changes any prose the model reads, get sign-off.
- **A quick fix "that's obviously the heartbeat".** See Rule 2 — this exact bug was almost
  misfixed twice. Evidence first.
- **Committing a per-instance JSON "so it deploys".** It's gitignored on purpose
  (Rule 4/class d); forcing it into git creates a path for auto-overwriting hand-managed
  device state. Deliver paste-able commands instead.
- **Adding a new required env var and deploying.** update-all.sh never touches `.env`, so
  every running bot would start without it. New config must default safely in bot.py
  (missing var = old behavior), be documented in `.env.example`, and come with per-bot
  paste-able `.env` lines for the owner.
- **Renaming or relocating bot.py / changing the launch command.** run-bot.sh, watchdog.sh,
  update-all.sh, and the supervisor heredoc all hardcode `bot.py` and its argv contract
  (`python -u bot.py '<instance-dir>'`). That's Rule 1 territory.
- **Assuming character/preset edits deploy with the code.** They don't — update-all.sh
  syncs code and helper scripts only. A pushed card edit that's never `cp`'d to the
  instance dir simply never takes effect, which looks exactly like "the fix didn't work".

## Provenance and maintenance

Verified 2026-07-02 against branch `claude/push-to-repo-7i2f3c`. Re-verify before citing:

```bash
# What update-all.sh actually syncs (bot.py, bot_app/, acoustic_ears.py, helper scripts, .env.example):
grep -n "cp \|chmod\|cmp -s" telegram-companion-bot/update-all.sh

# That it still excludes itself from the sync loop:
grep -n "update-all.sh itself" telegram-companion-bot/update-all.sh

# Which instances it restarts (nora/bonnie/cass/emily/jules/priya as of 2026-07-02):
grep -n "for entry in" telegram-companion-bot/update-all.sh

# Current gitignored instance-state list (Rule 4 scope):
cat telegram-companion-bot/.gitignore

# The py_compile pre-commit hook still exists:
grep -n "py_compile" .claude/settings.json

# preset.txt verbatim-injection warning + Bonnie/Emily/Jules override note:
grep -n "verbatim as live prompt" telegram-companion-bot/bot.py

# Defensive bot_app import (Rule 1):
grep -n "bot_app unavailable" telegram-companion-bot/bot.py

# Migration status / deliberately-skipped steps:
sed -n '1,30p' telegram-companion-bot/bot_app/MIGRATION.md

# bot.py size (was 8,937 lines on 2026-07-02):
wc -l telegram-companion-bot/bot.py
```
