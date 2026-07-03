---
name: companion-bot-docs-and-writing
description: >
  Documentation map and house writing style for telegram-companion-bot: which document is the
  record for what, which docs must move in the SAME commit as a given change class, and how this
  project writes commit messages, doc prose, and code comments. Load this when: writing or
  updating ANY doc (README, OPS_MANUAL, SETUP_GUIDE, MIGRATION, PROJECT_CONTEXT); writing a
  commit message; finishing a change and asking "what docs move with this?"; adding a command,
  env var, character/bot, or migration step; noticing doc drift or a doc contradicting the code;
  editing preset.txt (special case — it is NOT documentation); or maintaining the .claude/skills/
  library itself. Do NOT use for: env-var specifics and defaults (companion-bot-config-catalog),
  or whether/how a change ships and what sign-off it needs (companion-bot-change-control).
---

# Companion-bot documentation and writing

Certified 2026-07-02 against commit `943af21`. Docs in this repo went stale once and cost real
time: a 2026-06 audit found wrong branch names, dead deploy instructions, and a Commands
Reference missing dozens of commands (fixed in commit `e9e3880`). The rule that prevents a
repeat: **docs move in the same commit as the change that invalidates them.** This skill tells
you which doc moves for which change, and how to write it when you get there.

## Document-of-record inventory

Who owns what truth. When two docs disagree, the doc of record wins and the other one is the bug.

| Document | Role / record for | Audience | Must change when |
|---|---|---|---|
| `CLAUDE.md` (repo root) | Behavioral guidelines + the deploy-workflow contract (branch, device paths, `update-all.sh`). Highest authority for session behavior — overrides defaults. | Claude sessions | Deploy workflow, branch name, bot roster, or what `update-all.sh` syncs changes |
| `telegram-companion-bot/README.md` | Entry point: what the product is, file-by-file listing | New reader, GitHub visitor | A top-level file is added/removed/renamed, or a headline feature lands |
| `docs/OPS_MANUAL.md` | Operational truth: start/stop recipes, **Commands Reference** (the table that went stale), context files, memory tiers, heartbeat config, watchdog setup, troubleshooting | Owner operating the device | Any command added/removed/renamed; bot added/retired; ops procedure or supervision behavior changes |
| `docs/SETUP_GUIDE.md` | Fresh-device setup from zero (Termux/VPS/Mac) | Someone with a blank phone | A dependency, required env var, or setup step changes (e.g. the Inworld key requirement, 2026-07-01 — currently missing, see known-stale) |
| `docs/EPISODIC_RECALL.md` | Memory-subsystem deep-dive (embeddings, verbatim recall) | Engineer touching memory | Episodic-recall mechanics change. Audited accurate 2026-06 |
| `docs/PROJECT_CONTEXT.md`, `docs/PROJECT_INSTRUCTIONS.md` | Claude-Project knowledge files: feature map, pipelines, character notes. **Historical** — verify against current `bot.py` before citing | Claude Projects (web) | Feature pipelines change. Known drifted (voice pipeline — see known-stale) |
| `bot_app/MIGRATION.md` | **Canonical** strangler-fig migration status. `bot_app/README.md` deliberately just points here — the two contradicted once, so status lives in exactly one file | Engineer touching bot.py/bot_app | Any migration step completes, is re-scoped, or is deliberately skipped |
| `.env.example` | Config documentation that doubles as the setup template (synced to the device by `update-all.sh`). Owned jointly with **companion-bot-config-catalog** — update both | New-instance setup + config reference | Any env var added, renamed, removed, or its default changes |
| `.claude/skills/*/SKILL.md` | The skill library — operational knowledge with provenance | Future Claude sessions | See "Maintaining the skill library" below |

`preset.txt` is deliberately absent from this table — see the special case below.

## Update-triggers table: change class → docs that move in the SAME commit

| You changed... | Docs that move with it |
|---|---|
| Added/removed/renamed a `/command` in bot.py | `docs/OPS_MANUAL.md` Commands Reference table (the exact section that rotted before) |
| Added/renamed/removed an env var, or changed a default | `.env.example` (and the companion-bot-config-catalog skill's table) |
| Added a new bot/character | OPS_MANUAL roster (two places: "Starting & Stopping" intro and "Running Multiple Characters") + `watchdog.sh` BOTS list + `update-all.sh` restart loop + SETUP_GUIDE per-char loops + CLAUDE.md roster |
| Completed/re-scoped a migration step | `bot_app/MIGRATION.md` (only there — bot_app/README.md just points to it) |
| Changed deploy mechanics (what update-all.sh syncs, branch, paths) | `CLAUDE.md` deploy section + OPS_MANUAL "Starting & Stopping" |
| Changed a setup dependency or required key | `docs/SETUP_GUIDE.md` |
| Added/removed a top-level file | `telegram-companion-bot/README.md` Files table |
| Swapped an external service (LLM, STT/TTS, image gen) | SETUP_GUIDE + `.env.example` + PROJECT_CONTEXT feature map |
| Any change a skill documents, or a new settled finding | The skill file itself, same commit (see below) |

If your diff hits the left column and not the right, the commit is incomplete.

## House style

### Commit messages

- Imperative subject, ≤~70 chars: `Fix watchdog loop not surviving termux-boot-start.sh (nohup -> setsid)`.
- Body explains **WHY** — the incident, the ruled-out alternatives, the operational consequence —
  not a restatement of the diff.
- Write via `git commit -F <file>` (message in a scratch file) so apostrophes and multi-line
  bodies survive the shell.
- End with the Co-Authored-By / Claude-Session trailer per the session's git rules.

Two real examples from this repo's log:

> **`a080f99`** — `Fix watchdog loop not surviving termux-boot-start.sh (nohup -> setsid)`
> Body walks the live on-device bisection (each hypothesis tested and eliminated), then the root
> cause: "nohup only blocks the SIGHUP signal: it does not detach the process into a new
> session... Swapped to setsid, which actually starts a new session... confirmed live on the
> device to survive where nohup did not."

> **`faea119`** — `Replace NanoGPT with Inworld TTS for voice replies`
> Body records the operational fallout future readers need: "TTS_MODEL (NanoGPT-specific) is
> removed as dead config; TTS_VOICE's default changes from 'nova' to 'Sarah'... any bot with a
> NanoGPT voice name (nova/shimmer/alloy/etc.) set in its .env needs that value replaced with a
> real Inworld voiceId or voice replies will fail the same way a bad key does."

### Docs voice

- Terse. Tables for enumerable facts (commands, files, env vars, model slots); prose only where
  explanation is needed (why the watchdog has two layers, why memory has two stores).
- No marketing language. OPS_MANUAL says "Kills any existing session/process for that instance,
  then relaunches it" — not "seamlessly manages your bot lifecycle".
- Runnable commands in fenced blocks, exact paths (`~/telegram-bot/`, `~/nora-bot/`), no
  placeholders where a real value exists.
- Cross-reference instead of duplicating: OPS_MANUAL points at CLAUDE.md for deploy, SETUP_GUIDE
  for boot setup. Duplication is where contradictions breed (the bot_app/README lesson).

### Comments in code

State constraints the code cannot show. The house examples: update-all.sh explains why it skips
syncing itself ("overwriting the running script mid-run is unsafe"); the `a080f99` fix explains
why setsid and not nohup; bot_app sync comments explain that the import is defensive so a missing
package degrades instead of crashing. A comment that restates the line below it is noise; a
comment that records why the obvious alternative fails is the point.

### preset.txt — SPECIAL CASE

`preset.txt` is **NOT documentation**. Every character in it is live prompt text, verbatim-injected
into every message's prompt for every bot. Never add comments, headers, notes, or TODO markers to
it — the model will read them as instructions. Document its behavior in `bot.py` comments or under
`docs/`, never in the file itself.

## Maintaining the skill library (`.claude/skills/`)

- Every skill carries a **Provenance and maintenance** section: the commit it was certified
  against plus re-verification one-liners a future session can run in minutes.
- **A session that finds drift in a skill fixes the skill in the same change** — same rule as the
  docs. A skill that silently drifts is worse than no skill; it asserts stale facts with
  confidence.
- Same for docs flagged in a skill's known-stale list: when you fix the doc, delete the stale
  entry from the skill.
- `.claude/skills/HANDOFF.md` is a build checkpoint, not a permanent file — delete it when the
  library build completes.

## Known stale as of 2026-07-02 (flagged, not fixed)

Drift found during this skill's verification pass. Fix these in a dedicated docs commit (and then
remove the entry here):

1. **`docs/SETUP_GUIDE.md` does not mention `INWORLD_API_KEY`.** Voice notes (STT, `ed15b25`) and
   voice replies (TTS, `faea119`) both require it as of 2026-07-01; `.env.example` documents it
   (its "Voice: Inworld STT + TTS" block) but the setup guide never tells a fresh installer to
   get an Inworld key.
2. **`docs/PROJECT_CONTEXT.md` voice pipeline is outdated.** Line ~19 says voice notes go through
   "Whisper transcription" and line ~29 says TTS is "via `TTS_MODEL`/`TTS_VOICE`". Reality: STT
   and TTS are both Inworld; `TTS_MODEL` was removed as dead config in `faea119`.
3. **`docs/OPS_MANUAL.md` contradicts itself about Priya.** "Running Multiple Characters" (~line
   345) says she "isn't deployed yet", but the manual's own deploy section, `watchdog.sh`,
   `update-all.sh`, and commit `f57142c` ("Add Priya to watchdog.sh now that she is being
   deployed") all treat her as a live sixth instance.
4. **Repo-root `CLAUDE.md` deploy section is stale twice over:** it lists "all five bots (nora,
   bonnie, cass, emily, jules)" — Priya is missing — and says update-all.sh "deploys only
   bot.py" with helper scripts copied manually. `update-all.sh` now also syncs `bot_app/`,
   `acoustic_ears.py`, `run-bot.sh`, `watchdog.sh`, `status.sh`, and `.env.example`; only
   `update-all.sh` itself, `termux-boot-start.sh`, and per-bot `.env`/character files remain
   manual.

## Provenance and maintenance

Certified 2026-07-02 against commit `943af21`. Re-verification one-liners (run from repo root;
if any comes back different, update the relevant section of this skill in the same change):

```bash
git -C . rev-parse --short HEAD        # vs 943af21; if moved, re-run the checks below
# Commands Reference parity: bot.py registrations vs OPS_MANUAL table rows (74 vs 80 at
# certification — rows include aliases like "/week / /remindpayments", so expect rough
# parity, not equality; a gap of >5 growing means the table is rotting again)
grep -c 'CommandHandler(' telegram-companion-bot/bot.py
grep -c '^| `/' telegram-companion-bot/docs/OPS_MANUAL.md
# Known-stale item 1 still stale? (no output = still stale)
grep -n INWORLD telegram-companion-bot/docs/SETUP_GUIDE.md
# Known-stale item 2 still stale? (hits = still stale)
grep -n 'Whisper\|TTS_MODEL' telegram-companion-bot/docs/PROJECT_CONTEXT.md
# Roster consistency: these three should name the same set of characters
grep -o '"[a-z-]*bot:[a-z]*"' telegram-companion-bot/update-all.sh
grep -n ':\$HOME/.*-bot' telegram-companion-bot/watchdog.sh
grep -n 'nora.*bonnie.*cass' CLAUDE.md telegram-companion-bot/docs/OPS_MANUAL.md
# bot_app/README.md must still be a pointer, not a second status doc
wc -l telegram-companion-bot/bot_app/README.md   # small; grep it for "MIGRATION.md"
# HANDOFF.md should be gone once the skill library is complete
ls .claude/skills/HANDOFF.md 2>/dev/null && echo "library build still in progress"
```
