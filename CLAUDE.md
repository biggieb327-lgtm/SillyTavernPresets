# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running six AI
character instances — four on Android via Termux, two on a VPS. One `bot.py` handles all
characters; instances differ only by directory, `.env`, and SillyTavern v2 character card.
The repo root also archives standalone SillyTavern presets/cards and an unrelated
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
- `.env.example` — every variable bot.py reads, documented with defaults.
- `.claude/memory/operational-log.md` — one row per failure that changed the system.

## Operating rule

General method (scoping, evidence, verification, calibrated reporting):
`.claude/OPERATING_MANUAL.md` — project rules in this file override it.

For complex work (multi-step, behavior-changing, or fleet-touching), read
`.claude/operating/fable-to-opus.md` before acting — it carries owner-settled
decisions and session-earned traps. For simple work, do not load it.

Detailed procedure lives in skills, not here. `.claude/skills/skill-router/SKILL.md`
is the index — consult it and load on demand (table below for the common cases).

The machinery that enforces this is real, not advisory:

- **`.claude/evals/run-evals.sh`** — past incidents pinned as runnable checks.
  **Run it before claiming any change done.** A failure recurring twice earns a new
  eval. Includes a secret scan (this repo is public via raw URLs) and
  BOT_VERSION↔changelog sync.
- **Hooks** (`.claude/hooks/`) — including a **delivery gate** that blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, or compile
  evidence.
- **CI** (`.github/workflows/evals.yml`) — same evals + pytest on `main`/`claude/**`.
  Deploys curl from `main`, so **a red run on main is a deploy blocker.**
- Routines are recorded in `.claude/operating/routines.md` — keep it and the live
  Routine in sync.

Do not load unrelated skills.
Do not rewrite large files unless the task requires it.
Every completion must include the verification command actually run.

## Where things live

| Topic | Load |
|---|---|
| Shipping any bot.py change | `repo-change-control` + `bot-code-invariants` |
| A live bot is silent, restarting, or misbehaving | `repo-debugging-playbook` |
| Cause looks device-level: SIGKILL/137, venv, tzdata, watchdog, `pkg upgrade` | `termux-device-ops` |
| Getting merged work onto the fleet (paths A–E) | `deploy-and-verify-fleet` |
| Model slots, timeouts, `.env` constraints, voice/vision/traffic, continuity features | `bot-config-reference` |
| Character cards, seeds, `preset.txt`, per-character canon | `edit-cards-and-presets` |
| Any `GROUP_*` code, the ledger, bot-to-bot behavior | `group-chat-changes` |
| Before declaring anything done | `repo-validation-gate` |

Full index, including the less common skills: `skill-router`.

## Known-deliberate — do not "fix" these

- **Emily runs `zai-org/glm-4.7:thinking`**, not glm-5 (owner-confirmed 2026-07-25).
  Per-instance model choice is expected, not drift.
- **bot.py stays a single file.** The whole deploy model depends on it. Recorded
  non-goal — don't propose splitting it.
- **`AUDIT-2026-07-10.md` records rejected claims.** Check it before "fixing" a
  finding someone already ruled invalid.
- **`.claude/.runtime/` is gitignored.** Never commit it, never add it back.

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
`/opt/telegram-bots/bot.py` (VPS).

The instance directory is the basename on the `=== STARTUP AUDIT === … Instance:`
line — **that runtime value is authoritative** if it ever disagrees with this table.
The authoritative instance list is the loop in `update-all.sh` (phone) and the
`bot@<instance>` systemd units (VPS). Phone scripts (`update-all.sh`,
`sync-cards.sh`, `watchdog.sh`) skip VPS instances automatically (no local dir).
Nora's directory is pinned by the `nora-instance-dir` eval.

## Stack

- Python **3.14** on Termux/Android — the `=== STARTUP AUDIT ===` line reports the
  live version; trust it over this file. Practical effect: cp314 wheels are scarce,
  so any new binary dependency is likely to compile from source on-device.
- `python-telegram-bot >=21.0,<22.0` (async, job-queue). PTB v21's deprecated
  `asyncio.get_event_loop()` call is worked around in `main()` — don't remove it.
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`.
- SillyTavern `chara_card_v2` JSON cards.
- Repo `biggieb327-lgtm/SillyTavernPresets`; raw URL base
  `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

## Deployment

Five deploy paths, split across phone (nora, bonnie, emily, priya — tmux) and VPS
(cass, jules — systemd). Both pull from `main`; the phone scripts silently skip VPS
instances, so a "fleet deploy" that only ran the phone paths leaves two bots behind.
Exact commands, verification, and rollback: **`deploy-and-verify-fleet`**.

**Bump `BOT_VERSION` on every release** — it's how `/update` detects new versions and
`/audit` proves a deploy landed. The delivery gate enforces this.

Ops essentials: `/update` `/restart` `/audit` `/errors [N]` `/backup`.
Full command reference: `OPS_MANUAL.md`.

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
- Commit real work **before** break-testing evals; revert test injections by
  re-editing, never `git checkout` on a file with uncommitted changes.
- **New-feature default policy (owner, 2026-07-18):** new features default **ON** with a
  mandatory env kill switch (unset = active, `0` = off). The kill switch is required;
  default-on is the norm. Details in `bot-code-invariants` #16.

## Repo layout

`telegram-companion-bot/` holds everything that deploys: `bot.py`, the ops scripts,
character cards + seed dirs, `preset.txt`, `tests/`, `deploy/` (VPS), and the docs
above. `ls` it for the rest. The non-obvious bits:

- `requirements.txt` is the single source of truth for pip installs.
- `preset.txt` is the shared voiceprint — editing it changes **all six** bots.
- `watchdog.sh`, `backup-all.sh`, `cleanup-all.sh` are curl-installed once and are
  **not** managed by `update-all.sh`; changing them in-repo deploys nothing.
- `character-review/` is the card inbox for the monthly character pass (see its README).
- `caa16137-nora.json` (root) is a SillyTavern archive copy that has **diverged** from
  the bot's `nora.json` — not a mirror, never sync them.
- `voicekit-starter/` is a separate project; none of the bot's rules apply to it.
