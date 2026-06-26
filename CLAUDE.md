# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running multiple AI character instances on Android via Termux. One `bot.py` handles all characters; instances are differentiated by their directory, `.env`, and SillyTavern v2 character card JSON. The repo also stores character card files (`.json`) at the root level for archiving and sharing.

---

## Bot instances

| Session | Directory | Character card |
|---------|-----------|----------------|
| `nora` | `~/telegram-bot/` | `nora.json` |
| `bonnie` | `~/bonnie-bot/` | `bonnie.json` |
| `cass` | `~/cass-bot/` | `cass.json` |
| `emily` | `~/emily-bot/` | `emily_harper.json` |

All instances share the venv at `~/telegram-bot/venv/`. `bot.py` always lives in `~/telegram-bot/` and is passed an instance directory as `sys.argv[1]`.

---

## Stack

- **Runtime:** Python 3.13, Termux on Android
- **Library:** `python-telegram-bot >=21.0,<22.0` (async, with job-queue)
- **AI backend:** NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`
- **Character format:** SillyTavern `chara_card_v2` JSON
- **Repo:** `biggieb327-lgtm/SillyTavernPresets`
- **Raw URL base:** `https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/`

---

## Deployment

### Update and restart a single bot
```bash
cd ~/telegram-bot
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/bot.py -o bot.py
bash ~/telegram-bot/run-bot.sh ~/emily-bot emily
```

Nora (the default instance) uses `run.sh` instead:
```bash
tmux kill-session -t nora 2>/dev/null && bash ~/telegram-bot/run.sh
```

### Update and restart all bots at once
```bash
curl -fsSL https://raw.githubusercontent.com/biggieb327-lgtm/SillyTavernPresets/main/telegram-companion-bot/update-all.sh | bash
```

### Card-only update (no bot.py change)
```bash
curl -fsSL https://raw.githubusercontent.com/.../nora.json -o ~/telegram-bot/nora.json
bash ~/telegram-bot/run-bot.sh ~/telegram-bot nora   # or run.sh for nora
```

### Edit an instance .env
```bash
nano ~/emily-bot/.env
```

---

## Working principles

1. **Ask, don't assume.** If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements. When running unattended, pick the most reasonable interpretation, proceed, and record the assumption rather than blocking.
2. **Simplest solution first.** Implement the simplest solution for simple problems, better solutions for harder problems. Do not over-engineer or add flexibility that isn't needed yet.
3. **Don't touch unrelated code** — but do surface bad code or design smells so we can address them as a separate issue.
4. **Flag uncertainty explicitly.** If unsure, see rule 1. If appropriate, run a small, localised, low-risk experiment and bring the hypothesis and results to discuss. Confidence without certainty causes more damage than admitting a gap.
5. **Suggest better approaches.** Always open to ideas with long-lasting impact over tactical changes — don't hesitate to propose them.

---

## Git workflow

- Push all changes to `main`
- Development may happen on a feature branch (`claude/...`) but always merge to `main` before deploying, since the curl commands pull from `main`
- Commit messages should be descriptive; co-author line is added automatically by Claude Code

---

## Key .env variables

```
TELEGRAM_BOT_TOKEN=
NANOGPT_API_KEY=
NANOGPT_MODEL=zai-org/glm-5:thinking      # primary chat model
FALLBACK_MODEL=anthracite-org/magnum-v4-72b  # roleplay fallback on 5xx/timeout
VISION_MODEL=zai-org/glm-4.6v             # must support image input
DOCUMENT_MODEL=deepseek/deepseek-v4-flash  # instruction model for card analysis — NOT roleplay-tuned
SUMMARY_MODEL=zai-org/glm-4.7-flash
REACTION_MODEL=zai-org/glm-4.7-flash
CHARACTER_CARD=nora.json
ALLOWED_USERS=                             # comma-separated Telegram user IDs
```

**Emily only (WSDOT traffic):**
```
WSDOT_API_KEY=
TRAFFIC_RADIUS_MILES=10
TRAFFIC_POLL_MINUTES=10
```

---

## NanoGPT connection notes

- `call_nanogpt` retries each model up to 3 times with 2s/4s backoff before falling to the fallback
- Timeout is `(10, 300)` — 10s connect, 300s read
- `FALLBACK_MODEL=anthracite-org/magnum-v4-72b` is the recommended roleplay fallback; `Sao10K/L3.3-70B-Euryale-v2.3` is a solid alternative
- `DOCUMENT_MODEL` must be an instruction model — roleplay-tuned models will perform the character card they're analyzing

---

## Character notes

**Nora** (`nora.json` / `caa16137-nora.json`) — 25, bike messenger, Chicago South Side, Seattle. Casual conversation register. Curious and conversational, shows it by talking not interrogating. Mormor (grandmother) died a year ago; mother left at 8. Three months into something with user she won't name. Friction section describes her fear/reset pattern. Lorebook has 6 entries: Ingrid/jacket, Mother, Messenger work, The toothbrush, Money/The City, Religion/Politics.

**Bonnie** (`bonnie.json`) — libertarian gremlin housewife, chaotic surface over abandonment terror underneath. Personality order: Friction → Core → OCEAN → Energy States → Surface. Sexual behavior written as observable patterns. Four-state calm opening in first_mes.

**Cass** (`cass.json`) — writing collaborator / developmental editor. Analysis-mode bot; send a `.json` card and she gives substantive critique. Uses `DOCUMENT_MODEL` for card analysis. Has a forward-momentum rule: leads with fixes, advances conversation rather than circling.

**Emily** (`emily_harper.json`) — has `VISION_MODEL=zai-org/glm-4.6v`. Has WSDOT Western Washington traffic integration: `/traffic`, `/incidents`, live location → proactive nearby incident alerts every 10 min.

---

## Termux quirks

- `/tmp` is not writable — use `~/` for temp files
- Network goes stale during long model waits — `_keep_typing` swallows exceptions; `send_bubbles` retries with backoff
- `tmux kill-session -t name` before `new-session` with the same name or you get "duplicate session" error
- Stale `bot.pid` lock file after a crash: delete `~/instance-dir/bot.pid` before restarting
- `httpx.ConnectError` on startup or mid-session = transient network blip; kill and restart the session
- Termux wake lock is acquired automatically on startup via `termux-wake-lock`

---

## Bot commands reference (quick)

| Command | What it does |
|---------|--------------|
| `/traffic` | W. WA congestion (scoped to user if location shared) |
| `/incidents` | Open WSDOT alerts (filtered nearby if live location active) |
| `/memory` | View long-term + recent memory |
| `/selfie [hint]` | Generate a selfie |
| `/vibe <name> [Xh]` | Set timed vibe |
| `/remindme <when> <msg>` | One-off reminder |
| `/cron <schedule> \| <instruction>` | Recurring task |
| `/heartbeat` | Trigger proactive message now |
| `/model` | Show active models |
| `/usage` | NanoGPT token usage |
| `/addmem <text>` | Manually add an NPC/world memory |
| `/mems` | List all stored memories |
| `/delmem <keyword or #>` | Remove a memory by keyword or number |

---

## Repo layout

```
/
├── CLAUDE.md                          # this file
├── telegram-companion-bot/
│   ├── bot.py                         # single bot codebase, all instances
│   ├── update-all.sh                  # curl + restart all bots
│   ├── run.sh                         # start nora (default instance)
│   ├── run-bot.sh                     # start any named instance
│   ├── .env.example                   # documented config template
│   ├── nora.json                      # Nora character card (bot copy)
│   ├── bonnie.json
│   ├── cass.json
│   ├── emily_harper.json
│   ├── OPS_MANUAL.md
│   ├── PROJECT_CONTEXT.md
│   └── PROJECT_INSTRUCTIONS.md
├── caa16137-nora.json                 # Nora card (SillyTavern archive copy)
└── [other SillyTavern presets/cards]
```
