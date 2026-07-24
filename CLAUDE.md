# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running six AI
character instances on Android via Termux. One `bot.py` handles all characters;
instances differ only by directory, `.env`, and SillyTavern v2 character card. The repo
root also archives standalone SillyTavern presets/cards and an unrelated
`voicekit-starter/` project.

## Docs map — read the right doc, not all of them

All under `telegram-companion-bot/` unless noted:

- `CHANGELOG.md` — **read before any bot.py change** (root causes of every shipped
  fix); add an entry after shipping one (root cause first). Skip only for pure
  content edits.
- `ROADMAP.md` — what's next and why; Track 4 is the audit backlog.
- `IMPROVEMENTS_PLAN.md` — release-by-release handoff specs for the Track 4 work.
- `AUDIT-2026-07-10.md` — 2026-07 audit findings, incl. rejected claims (don't re-fix).
- `GROUP_CHAT_DESIGN.md` — **read before touching any GROUP_* code**; survived 4
  adversarial review rounds.
- `OPS_MANUAL.md` — day-to-day operation + the **full bot command reference**.
- `SETUP_GUIDE.md` — standing up a new instance (or use `new-bot.sh`).
- `.claude/memory/operational-log.md` — one row per failure that changed the system.

## Agent operating system (`.claude/`)

Rules here are backed by files that run, not prose:

- **Agents** (`.claude/agents/`): `chief-operator` (opus) orchestrates;
  `builder`/`system-fixer`/`qa-engineer` (sonnet) implement and verify;
  `adversarial-critic`/`eval-designer`/`improvement-analyst` (opus) audit;
  `context-librarian`/`research-scout` (haiku) handle hygiene and lookups.
- **Hooks** (`.claude/hooks/`, wired in `.claude/settings.json`): session-start audit,
  Bash risk guard, evidence logger, budget governor, **delivery gate** (blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, or compile
  evidence), pre-compact handoff writer.
- **Evals** (`.claude/evals/run-evals.sh`): past incidents pinned as runnable checks —
  **run before claiming any change done**. A failure recurring twice earns a new eval.
  Includes a secret scan (repo is public via raw URLs — a committed token is instantly
  leaked) and BOT_VERSION↔changelog sync.
- **CI** (`.github/workflows/evals.yml`): same evals + pytest on every push to
  `main`/`claude/**`. Deploys curl from `main` — a red run on main is a deploy blocker.
- **Improvement loop**: monthly Routine runs `improvement-analyst` over the logs;
  pushes at most one evidence-based proposal (plus up to 3 URL-cited, unvetted
  Reddit ideas, owner-approved addition 2026-07-20) to `claude/improvement-loop`,
  never to `main`. Live since 2026-07-12 — schedule + verbatim prompt recorded in
  `.claude/operating/routines.md` (keep file and Routine in sync; the daily ops
  brief, weekly hygiene check, and monthly character pass live there too).
- Runtime state in `.claude/.runtime/` is gitignored — never commit it.

## Operating rule

General method (scoping, evidence, verification, calibrated reporting):
`.claude/OPERATING_MANUAL.md` — project rules in this file override it.

For complex work (multi-step, behavior-changing, or fleet-touching), read
`.claude/operating/fable-to-opus.md` before acting — it carries owner-settled
decisions and session-earned traps. For simple work, do not load it.

Before starting work, inspect relevant project skills in `.claude/skills/`
(`skill-router/SKILL.md` is the index; the 2026-07-11 staged batch was owner-reviewed
and promoted in full on 2026-07-17 — `_staging/` now holds only the promotion
procedure for future skills).

Use:
- `repo-debugging-playbook` for bugs and regressions
- `repo-change-control` + `bot-code-invariants` for edits that change behavior
- `repo-validation-gate` before declaring done

Do not load unrelated skills.
Do not rewrite large files unless the task requires it.
Every completion must include the verification command actually run.

## Bot instances

| Session | Platform | Directory | Character card |
|---------|----------|-----------|----------------|
| `nora` | phone | `~/nora-bot/` | `nora.json` |
| `bonnie` | phone | `~/bonnie-bot/` | `bonnie.json` |
| `cass` | **VPS** | `/opt/telegram-bots/cass/` | `cass.json` |
| `emily` | phone | `~/emily-bot/` | `emily_harper.json` |
| `priya` | phone | `~/priya-bot/` | `priya.json` |
| `jules` | **VPS** | `/opt/telegram-bots/jules/` | `jules_nakagawa.json` |

Phone instances share the venv at `~/telegram-bot/venv/`; VPS instances share
`/opt/telegram-bots/venv/`. `bot.py` lives at `~/telegram-bot/bot.py` (phone) and
`/opt/telegram-bots/bot.py` (VPS). The instance directory (where each bot's `.env`,
card, and state live) is the basename shown on the `=== STARTUP AUDIT === …
Instance:` line — that runtime value is authoritative if it ever disagrees with
this table.

Authoritative instance list = the loop in `update-all.sh` (phone) and the
`bot@<instance>` systemd units (VPS). Phone scripts (`update-all.sh`,
`sync-cards.sh`, `watchdog.sh`) skip VPS instances automatically (no local dir).
(Nora's instance dir was corrected to `~/nora-bot/` on 2026-07-11 after the table
drifted. On 2026-07-20 the launch/sync scripts were reconciled to match. Pinned by
the `nora-instance-dir` eval.)

## Stack

- Python 3.13 on Termux/Android; `python-telegram-bot >=21.0,<22.0` (async, job-queue)
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`
- SillyTavern `chara_card_v2` JSON cards
- Repo `biggieb327-lgtm/SillyTavernPresets`; raw URL base
  `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

## Deployment

Fleet is phone (nora, bonnie, emily, priya) + VPS (jules, cass). Both pull from
`main`. Load `deploy-and-verify-fleet` for the procedure (four paths: code, cards,
supervisor, .env). Bump `BOT_VERSION` on every release. Full command reference:
`OPS_MANUAL.md`.

## Working principles

1. **Ask, don't assume.** When unclear, ask first. Running unattended: pick the most
   reasonable interpretation, proceed, record the assumption.
2. **Simplest solution first.** No flexibility that isn't needed yet.
3. **Don't touch unrelated code** — but surface smells for separate follow-up.
4. **Flag uncertainty explicitly**; small low-risk experiments over confident guessing.
5. **Suggest better approaches** — durable wins over tactical patches are welcome.

## Git workflow

- Develop on `claude/...` branches if useful, but **always merge green work to `main`**
  — deploys and doc links pull from `main`, so an unmerged branch ships nothing. Owner
  policy (2026-07-18): merge task branches to `main` autonomously once the full
  verification block is green; a designated feature branch is where you *develop*, not
  a place work should stop. (If a session-level instruction pins you to a branch and
  forbids pushing elsewhere, that owner standing permission is your explicit go-ahead.)

## Code invariants

Load `bot-code-invariants` for any bot.py diff — 16 rules covering architecture,
LLM-call budget, concurrency, memory provenance, and platform constraints, each
eval-pinned or incident-earned.

## Models & config constraints

Full documented template: `telegram-companion-bot/.env.example`. The constraints that
aren't obvious from it:

- `NANOGPT_MODEL=zai-org/glm-5:thinking` (chat), `SUMMARY_MODEL`/`REACTION_MODEL`
  cheap+fast (`glm-4.7-flash`).
- `FALLBACK_MODEL` must be roleplay-capable: `anthracite-org/magnum-v4-72b`
  (recommended) or `Sao10K/L3.3-70B-Euryale-v2.3`. Used on 400/429/5xx/timeout;
  `call_nanogpt` = 2 attempts/model, 2s/4s backoff, 150s primary budget.
- `DOCUMENT_MODEL` must be an **instruction** model (`deepseek/deepseek-v4-flash`) —
  a roleplay model will perform the character card it's analyzing.
- `VISION_MODEL` must be multimodal (`zai-org/glm-4.6v`) — the chat default rejects
  images with 400.
- `STREAM_TIMEOUT` (90s) is max silence between SSE chunks (stall detection);
  `REQUEST_TIMEOUT` (120s) for non-streaming. 30s proved too tight on a phone.
  Models that reject streaming are auto-retried non-streaming and cached in
  `_no_stream_models`.
- **Inworld voice (Emily):** TTS voice and model must come from the same engine — an
  Inworld voice ID sent to an OpenAI-style model 400s. `INWORLD_API_KEY` switches the
  engine; `TTS_VOICE` is then an Inworld voice ID.
- **WSDOT traffic (Emily):** `WSDOT_API_KEY` + `TRAFFIC_RADIUS_MILES` +
  `TRAFFIC_POLL_MINUTES`.
- **Group-chat pilot (Priya + Jules, experimental):** load `group-chat-changes`
  before touching any GROUP_* code. Setup and operation documented in `OPS_MANUAL.md`
  and `GROUP_CHAT_DESIGN.md`.

## Continuity features (all characters)

- **Date-aware note follow-ups**: datable user mentions stored with `(due YYYY-MM-DD)`
  in `user_notes.txt`; a daily job (`NOTE_FOLLOWUP_TIME`, default 18:00) asks how it
  went after the date, then marks `(asked …)`. Respects quiet hours + nudge budget.
- **Multi-day life threads**: midnight rotation feeds yesterday's `day.txt` into
  today's event generation. Archived days are provenance-tagged (`[own-day …]`) so her
  own fiction is never presented as shared memory.
- **Shared world**: the `WORLD_GENERATOR=1` instance (nora) writes `world.txt` at
  midnight; all instances read it — same weather/backdrop fleet-wide.

## Character notes

**Nora** (`nora.json` / root `caa16137-nora.json`) — 25, bike messenger, Chicago South
Side → Seattle. Casual register; curious by talking, not interrogating. Mormor died a
year ago; mother left at 8. Three months into something with user she won't name.
Lorebook: Ingrid/jacket, Mother, Messenger work, The toothbrush, Money/The City,
Religion/Politics.

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife; chaotic surface over
abandonment terror. Personality order: Surface → Core → Energy States → OCEAN →
Friction (the card's actual file order; docs had it reversed until 2026-07-20).
Four-state calm opening in first_mes.

**Cass** (`cass.json`) — writing collaborator / developmental editor; send a `.json`
card for substantive critique (uses `DOCUMENT_MODEL`). Forward-momentum rule: leads
with fixes.

**Emily** (`emily_harper.json`) — vision model + WSDOT traffic integration
(`/traffic`, `/incidents`, live-location alerts) + Inworld voice.

**Priya** (`priya.json`) — 26, fintech software engineer, Bellevue WA (moved from
Austin 2026-07). Tamil-American, NJ-raised, Rutgers CS. Sardonic, lowercase, never
performative; quietly lonely. Her atlas references real Eastside/Seattle places —
keep edits geographically consistent with Bellevue.

**Jules** (`jules_nakagawa.json`) — treats attention like a contact sport; files
everything you say and deploys it later, flat and precise. Derby-culture "chirping"
register — when she actually likes you she gets *meaner*, not warmer. Group-chat
pilot pair with Priya.

## Termux / Android quirks

Key facts that shape every bot decision (fix procedures are in
`repo-debugging-playbook`):

- **Phantom process killer:** Android 12+ SIGKILLs at >32 background processes; 6
  bots sit at that limit. The adb setting reverts after OS updates.
- **Venv path must be explicit:** run-bot.sh launches `~/telegram-bot/venv/bin/python`;
  bare `python` crash-loops on `ModuleNotFoundError`. Never regress this.
- **`tzdata` is required:** Termux has no system tz database; without it `ZoneInfo`
  silently degrades to naive local time.
- **`/tmp` is not writable** — use `~/` for temp files.
- **Process budget is tight:** no `tee`, no subprocess spawns, no background helpers.
  The supervisor writes `bot.log` via `>>` (fewer processes for the phantom limit).

## Debugging protocol

Load `repo-debugging-playbook` before proposing any fix for a live bot problem.
Evidence-first triage with a signature table for known causes.

## Monitoring

- **Restart-storm self-report**: `_self_audit` (every 30 min) DMs the owner at ≥3
  `STARTUP AUDIT` lines/hour (2h cooldown). Graceful-stop line present = catchable
  SIGTERM (battery manager or watchdog); absent = SIGKILL (phantom killer).
- **Dead man's switch**: set `HEALTHCHECK_URL` per instance (healthchecks.io, 30 min
  period + 15 min grace) — silence alerts on bot-down AND phone-dead.
- **`backup-all.sh`** (cron, on-device): nightly state archive to shared storage,
  `.env` excluded, 14-day retention, optional rclone. Curl-installed once; not managed
  by update-all.sh.
- **`cleanup-all.sh`** (cron, on-device): disk janitor — sweeps pip cache,
  `__pycache__`, SIGKILL-orphaned `.backup-stage.*` dirs, and stale `*.tmp` sidecars so
  the phone doesn't silently fill up. **Dry-run by default** (measures only); `--force`
  deletes. Never touches state, `.env`, `bot.py`/`.bak`, or live logs; character-card
  orphans are reported, never auto-deleted. Curl-installed once; not managed by
  update-all.sh.
- **`watchdog.sh`** (on-device at `~/telegram-bot/watchdog.sh`; source now in repo,
  still installed manually): relaunches vanished tmux sessions AND bots whose `.alive`
  heartbeat is stale (>300s). **bot.py must touch `.alive` every 60s** (`_touch_alive`
  job) — if that job is ever removed, watchdog restarts the whole fleet forever (cost
  a full debugging session, 2026-07-05). `watchdog.log` states its reason before every
  relaunch — check it first.

## Repo layout

```
/
├── CLAUDE.md                        # this file
├── telegram-companion-bot/
│   ├── bot.py                       # single codebase, all instances
│   ├── run-bot.sh / update-all.sh   # start one / redeploy all
│   ├── watchdog.sh / backup-all.sh  # on-device helpers (curl-installed once)
│   ├── cleanup-all.sh               # on-device disk janitor (curl-installed once)
│   ├── fleet-status.sh / sync-cards.sh / new-bot.sh   # ops tooling
│   ├── requirements.txt             # single source of truth for pip installs
│   ├── .env.example                 # documented config template
│   ├── preset.txt                   # shared voiceprint/texting-style preset
│   ├── *.json                       # character cards (bot copies)
│   ├── {bonnie,cass,emily,nora,priya}/   # per-character seed files
│   ├── meme_templates/ + fonts/     # shared meme assets
│   ├── tests/                       # pytest (pure-logic regression suite)
│   ├── deploy/                      # VPS: bot@.service, install-vps.sh, MIGRATION.md
│   └── *.md                         # docs — see Docs map above
├── character-review/                # card inbox for the monthly character pass (see its README)
├── caa16137-nora.json               # SillyTavern archive copy
├── voicekit-starter/                # separate project (not the bot)
└── [other SillyTavern presets/cards]
```
