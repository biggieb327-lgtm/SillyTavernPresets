---
name: companion-bot-device-ops
description: >
  Device operations for telegram-companion-bot: everything about the Termux/Android phone the
  six bot instances (nora, bonnie, cass, emily, jules, priya) run on. Load this skill whenever
  you are: deploying a change to the device, telling the owner to restart one bot or all bots,
  setting up a fresh device or a new character instance, composing ANY command the owner will
  run on the phone (chat paste-corruption rules live here), reading/interpreting bot.log or
  watchdog.log paths, editing the helper scripts (update-all.sh, run-bot.sh, watchdog.sh,
  status.sh, termux-boot-start.sh), verifying whether a deploy actually landed, or answering
  "what runs where / what file lives where" questions about ~/telegram-bot and ~/<char>-bot.
---

# Companion-bot device ops (Termux/Android)

Verified against the repo at `/home/user/SillyTavernPresets` on **2026-07-02**. Everything in
here was read from the scripts and docs listed under "Provenance" at the bottom — re-verify
there before trusting a detail after significant script changes.

**When NOT to use this skill:**
- Classifying whether a change is safe to commit/deploy, or needs owner sign-off →
  `companion-bot-change-control`.
- Diagnosing a reported bug or unexpected bot behavior → `companion-bot-debugging-playbook`.
  (Come back here only for the deploy/restart mechanics those playbooks tell you to run.)

---

## 1. Topology — read this first, every fresh session gets it wrong

There are THREE distinct locations and code only flows one way:

```
 CLOUD (where you are)                    PHONE (Termux on Android — owner's hands only)
+---------------------------+            +----------------------------------------------+
| repo /home/user/          |            |  ~/stp-deploy/                               |
|   SillyTavernPresets      |  git pull  |    git clone of the branch (PULL-ONLY,       |
| branch:                   |----------->|    never edited by hand)                     |
| claude/push-to-repo-7i2f3c|            |         |                                    |
+---------------------------+            |         | bash ~/telegram-bot/update-all.sh  |
                                         |         v  (copies files, then restarts)     |
  You NEVER touch the phone.             |  ~/telegram-bot/          <- SHARED CODE     |
  All device work is commands            |    bot.py, bot_app/,                         |
  handed to the owner through            |    acoustic_ears.py,                         |
  chat. See section 3 for the            |    run-bot.sh, watchdog.sh, status.sh,       |
  paste-corruption rules that            |    update-all.sh, .env.example,              |
  govern EVERY such command.             |    common.env, venv/, watchdog.log           |
                                         |         |                                    |
                                         |         | run-bot.sh <dir> <session> (tmux)  |
                                         |         v                                    |
                                         |  ~/nora-bot/   ~/bonnie-bot/  ~/cass-bot/    |
                                         |  ~/emily-bot/  ~/jules-bot/   ~/priya-bot/   |
                                         |    <- PER-INSTANCE STATE (.env, card JSON,   |
                                         |       state.json, bot.log, wardrobe.json,    |
                                         |       context .txt files) — NEVER synced     |
                                         +----------------------------------------------+
```

Key facts:
- **One shared `bot.py`** in `~/telegram-bot/` runs all instances; each instance is just
  `python bot.py <instance-dir>` in its own tmux session named after the character
  (`nora`, `bonnie`, `cass`, `emily`, `jules`, `priya`).
- **`~/stp-deploy` is a staging clone**, not the running code. Code runs from
  `~/telegram-bot/`. A successful `git pull` in `~/stp-deploy` deploys NOTHING by itself —
  the copy step in `update-all.sh` is what deploys.
- **Remote sessions have zero device access.** You cannot run anything on the phone, read
  its logs, or check its tmux. Every device fact comes from output the owner pastes back.
- The deploy branch is `claude/push-to-repo-7i2f3c` (single-branch clone). Deploying means:
  commit+push on that branch here, then owner runs `update-all.sh`.
- Instance existence gates everything: `update-all.sh` and `watchdog.sh` both skip a
  character whose `~/<char>-bot/` directory doesn't exist. Both scripts already list all
  six names including priya (verified: `watchdog.sh` BOTS block lines 24–31,
  `update-all.sh` restart loop line 79). Note: `docs/OPS_MANUAL.md` still says priya
  "isn't deployed yet" — the scripts are the source of truth for what WOULD run; whether
  `~/priya-bot/` exists on the device is a question only the owner can answer (`ls ~`).

---

## 2. Command classes — label them, always

Two kinds of commands appear in this project. Never mix them up:

- **REPO-SIDE** (you run them here, in `/home/user/SillyTavernPresets`): normal shell,
  `$` allowed freely.
- **DEVICE-BOUND** (the owner runs them on the phone, received through chat): governed by
  section 3. Every device-bound command in this skill obeys those rules and is marked
  `# device`.

---

## 3. THE PASTE CORRUPTION RULE (hard-won, do not relax)

Commands sent to the owner through the chat client get mangled in transit:

1. **`$...$` spans are STRIPPED** — the client renders anything between two dollar signs as
   LaTeX math. `echo "$HOME/nora-bot" && cat "$HOME/nora-bot/.env"` arrives with the span
   between the two `$` characters destroyed. This silently produces a *different, sometimes
   still-runnable* command — the owner's costliest failure class is silent corruption, not
   visible garbage.
2. **Multi-line blocks fragment** — long pasted blocks can arrive split or reordered.

Therefore every device-bound command must satisfy:

- **ZERO dollar signs.** No `$HOME`, no `$(...)`, no `$?`, no `${var}`, no shell loops with
  `$char`. Use `~` and literal paths; write one literal line per bot instead of a loop.
- **One line per command** where possible. If a multi-line file must be delivered (e.g. a
  wardrobe.json), don't send it as a shell heredoc command — send the file *content* as a
  plain block and tell the owner: open `nano ~/priya-bot/wardrobe.json`, paste, save
  (Ctrl+O, Enter, Ctrl+X). The owner editing with nano sidesteps both failure modes.
- This applies even to commands copied out of `docs/OPS_MANUAL.md` — the docs use `$`
  freely because they assume the owner is reading them directly on the device. Rewrite
  before relaying.

**Safe idempotent pattern for setting an .env key** (the canonical zero-dollar shape —
repeat one line per bot, literal paths, never a loop):

```
# device — one line, repeat per bot with the path changed
grep -q '^VAR=' ~/nora-bot/.env && sed -i 's|^VAR=.*|VAR=value|' ~/nora-bot/.env || echo VAR=value >> ~/nora-bot/.env
```

**Forensic check when a pasted command/file misbehaves** (this is what originally diagnosed
the corruption — shows every invisible/control character):

```
# device
cat -A ~/nora-bot/.env | tail -20
```

If a value the owner "definitely set" isn't taking effect, suspect paste corruption before
suspecting the code.

(Source: operational session history, 2026-06/07 — not written down in `docs/`; this skill
is the record.)

---

## 4. Fresh-device setup (Termux)

`docs/SETUP_GUIDE.md` covers this but is **stale in three ways** — trust this list:

1. SETUP_GUIDE installs files by `curl` from the **`main`** branch. The live system deploys
   from branch `claude/push-to-repo-7i2f3c` via the `~/stp-deploy` clone. On a real rebuild,
   clone instead of curling:
   ```
   # device
   git clone -b claude/push-to-repo-7i2f3c --single-branch https://github.com/biggieb327-lgtm/sillytavernpresets.git ~/stp-deploy
   ```
2. SETUP_GUIDE's package list (`pkg install python git tmux`) is incomplete for the current
   feature set. Full list:
   ```
   # device
   pkg update && pkg upgrade -y
   pkg install python git tmux ffmpeg termux-api python-numpy -y
   ```
   - `ffmpeg` — voice-note conversion, video frame extraction, PDF/OCR paths (`bot.py`
     `_run_ffmpeg`).
   - `termux-api` — provides `termux-wake-lock`, used by `watchdog.sh --loop` and
     `termux-boot-start.sh`.
   - `python-numpy` — **numpy must come from `pkg`, NOT pip.** `pip install numpy` tries to
     compile on Termux and fails (documented in `requirements.txt` and
     `docs/EPISODIC_RECALL.md`). Needed only for episodic recall (`EPISODIC_RECALL` +
     `EMBED_MODEL`), but install it up front.
3. SETUP_GUIDE's pip line omits newer deps. Install per `requirements.txt` (minus numpy):
   ```
   # device — after: python -m venv ~/telegram-bot/venv
   ~/telegram-bot/venv/bin/pip install "python-telegram-bot[job-queue]>=21.0,<22.0" python-dotenv requests tzdata pypdf garminconnect
   ```
   Then edit `~/telegram-bot/venv/pyvenv.cfg` (nano) and set
   `include-system-site-packages = true` so the venv can see the pkg-installed numpy.

Remaining fresh-device steps (SETUP_GUIDE is accurate here):
- Termux itself from **F-Droid**, not Play Store.
- `mkdir -p ~/telegram-bot`, then run `update-all.sh` from the clone once to populate it —
  but note the bootstrap chicken/egg: the first copy of `update-all.sh` must be placed by
  hand:
  ```
  # device
  cp ~/stp-deploy/telegram-companion-bot/update-all.sh ~/telegram-bot/update-all.sh
  bash ~/telegram-bot/update-all.sh
  ```
- **Termux:Boot app** from F-Droid (open it once after installing so Android allows it),
  then:
  ```
  # device
  mkdir -p ~/.termux/boot
  cp ~/stp-deploy/telegram-companion-bot/termux-boot-start.sh ~/.termux/boot/termux-boot-start.sh
  chmod +x ~/.termux/boot/termux-boot-start.sh
  ```
- Android Settings → Apps → Termux → Battery → **Unrestricted**; pin Termux in recents.
- After one reboot, confirm the watchdog loop survives:
  ```
  # device
  pgrep -f "watchdog.sh --loop"
  ```

Caveat on the venv: `run-bot.sh`'s supervisor runs plain `python -u bot.py <dir>` with no
venv activation baked in — it uses whatever `python` resolves to in a fresh tmux/Termux
environment. The working device's exact arrangement (venv on PATH via shell profile vs.
deps importable by the system python) is device state that cannot be verified from the
repo; if a rebuilt device throws `ModuleNotFoundError` under the supervisor but works with
the venv activated, this is why.

---

## 5. update-all.sh anatomy (the one deploy command)

```
# device — THE normal deploy command after any pushed change
bash ~/telegram-bot/update-all.sh
```

What it does, in order (`telegram-companion-bot/update-all.sh`, 93 lines, `set -e`):

1. **Sanity-check** `~/stp-deploy/.git` exists; if not, prints the clone command and exits.
2. **Auto-stash** any stray local changes in `~/stp-deploy`
   (`git stash push -u -m "update-all autostash <date>"`) so they can't block the pull.
3. **`git pull --ff-only` — FAILS LOUDLY.** If the pull can't fast-forward it prints repair
   commands (`git -C ~/stp-deploy status`, then `fetch` + `reset --hard @{u}`) and **exits
   before copying anything**. History: an earlier version let a failed pull slip through and
   the script kept "deploying" *stale* code — the owner's costliest failure class. Never
   weaken this. Corollary: if the owner reports "I ran update-all", always ask whether it
   printed the final `==> All done` — an early exit means nothing deployed.
4. **Copies `bot.py`** to `~/telegram-bot/bot.py`, then **`cmp`-verifies** the copy against
   the clone and aborts if they differ (catches a silent failed copy).
5. **Syncs `bot_app/`** (rm -rf + cp -r, kept in lockstep; `bot.py` imports it defensively —
   a missing package disables the migrated subsystems but cannot crash the bots).
6. **Syncs `acoustic_ears.py`** (vendored module, imported directly by bot.py).
7. **Syncs helper scripts** `run-bot.sh`, `watchdog.sh`, `status.sh` (+ `chmod +x`).
8. **Syncs `.env.example`** (template for new instances; running bots never read it).
9. **Kills the legacy `telegram-bot` tmux session** if present (old home-instance Nora).
10. **Restarts every instance whose directory exists** via
    `run-bot.sh ~/<char>-bot <char>` for nora, bonnie, cass, emily, jules, priya —
    missing dirs print `skipped`.
11. Prints `tmux ls`.

**What NEVER syncs** (deliberately): per-bot `.env`, `common.env`, `state.json` and all
other instance state, character card JSONs, context `.txt` files, `wardrobe.json`,
reference photos. Changing any of those on the device is always a manual step.

**The self-sync exception:** `update-all.sh` does **not** copy itself — overwriting the
running script mid-run is unsafe. When `update-all.sh` itself changes in the repo, the
owner must once run:
```
# device — only when update-all.sh itself changed
cp ~/stp-deploy/telegram-companion-bot/update-all.sh ~/telegram-bot/update-all.sh
bash ~/telegram-bot/update-all.sh
```
(The pull inside the second command is a no-op re-pull; harmless.)

Similarly `termux-boot-start.sh` is never synced by update-all — it lives in
`~/.termux/boot/` and must be re-copied by hand when it changes (see section 4).
`migrate_common_env.py` is a one-time tool, also copied by hand when needed.

---

## 6. Supervision chain (three layers)

**Layer 1 — `run-bot.sh <instance-dir> <session>`** (in-tmux supervisor):
- Reads `bot.pid` in the instance dir; kills a live old process and clears the lock.
- `pkill`s any orphaned `python bot.py <instance>` process, kills the old tmux session.
- Writes a per-instance supervisor script to `<instance-dir>/.supervise.sh` and launches it
  in a detached tmux session named `<session>`. The loop, forever:
  - rotates `bot.log` → `bot.log.1` when it exceeds ~5 MB (one backup kept) — **log
    rotation lives here, not in bot.py**;
  - clears a stale `bot.pid`;
  - runs `python -u bot.py <instance-dir>` with output `tee`'d to `bot.log`;
  - on exit, logs the exit code and restarts after 5 s.
- Catches: crashes, unhandled exceptions, Android OOM-killing the python process.
- Cannot catch: the tmux session (or all of Termux) dying — the loop dies with it.

**Layer 2 — `watchdog.sh`** (session-level):
- One-shot by default; `--loop` re-checks forever every `WATCHDOG_INTERVAL` seconds
  (default 300) and takes `termux-wake-lock`.
- For each of the six BOTS entries whose directory exists, relaunches via `run-bot.sh` if
  **either** (a) the tmux session is missing, **or** (b) the instance's `.alive` heartbeat
  file exists but is older than `WATCHDOG_STALE` seconds (default 300) — bot.py stamps
  `.alive` every 60 s from the event loop, so a stale stamp means the loop is wedged even
  though the process lives. A *missing* `.alive` is left alone (just-started bot).
- Logs its relaunches to `~/telegram-bot/watchdog.log`. Safe to run at any time; healthy
  bots are untouched.
- Adding/removing a bot means editing the `BOTS` list in `watchdog.sh` (and the restart
  loop in `update-all.sh`) — both already contain all six names.

**Layer 3 — `termux-boot-start.sh`** (boot + Termux-death coverage):
- Installed as `~/.termux/boot/termux-boot-start.sh` (exactly that name — NOT the removed
  `start-bots.sh`); Termux:Boot runs everything in that directory at device boot.
- Takes a wake lock, sleeps 30 s for network/filesystem, then — **only if no loop is
  already running** (pgrep guard, idempotent) — starts `watchdog.sh --loop` with
  **`setsid` … `&` + `disown`**.
- **`setsid` is load-bearing, not style.** nohup only blocks SIGHUP; Android/Termux kills
  by *process group*, and on-device testing (2026-06) showed a nohup'd loop dying when the
  short-lived launcher exited. `setsid` puts the loop in a new session, fully decoupled —
  confirmed on-device to survive where nohup did not. Never "simplify" this back to nohup,
  and keep the `disown`.
- A one-shot boot check would not be enough: the `--loop` process is what recovers from
  Android killing all of Termux *mid-session*, not just at reboot.

Session naming: one tmux session per character, named exactly `nora`, `bonnie`, `cass`,
`emily`, `jules`, `priya`. The legacy session name `telegram-bot` (old home-instance Nora)
is dead; update-all kills it on every run.

---

## 7. Routine ops recipes (all device-bound, all zero-dollar)

**Deploy a pushed change** (after change-control has approved it):
```
# device
bash ~/telegram-bot/update-all.sh
```
If a helper script other than the three synced ones changed, add the manual `cp` from
section 5/4 first.

**Restart one bot without deploying:**
```
# device
bash ~/telegram-bot/run-bot.sh ~/nora-bot nora
```

**Stop one bot** (note the supervisor: killing only the session lets watchdog resurrect it
within ~5 min — to truly stop, both lines):
```
# device
tmux kill-session -t nora
pkill -f nora-bot
```

**Check what's running:**
```
# device
tmux ls
bash ~/telegram-bot/status.sh
pgrep -f bot.py
pgrep -f "watchdog.sh --loop"
```
`status.sh` prints per bot: session up/DOWN, `.alive` age, and count of
error/traceback/exception lines in the last 300 log lines.

**Read logs:**
```
# device
tail -50 ~/nora-bot/bot.log
tail -20 ~/telegram-bot/watchdog.log
```
(Prefer bounded `tail -N` over `tail -f` — the owner has to Ctrl+C out of `-f`.)

**Verify a deploy actually landed** — two independent checks; use a marker string you know
is only in the new code (pick a literal from the diff, no `$` in it):
```
# device
cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py && echo DEPLOY-MATCHES
grep -c "the_new_marker_string" ~/telegram-bot/bot.py
```
And confirm the running processes restarted after the copy: `.alive` ages in `status.sh`
should all be young, or check the `[run-bot] starting <name>` timestamp at the end of each
`bot.log`.

**Add a new character** (using priya as the example; adjust names):
1. Confirm both scripts already list her — they do as of 2026-07-02 (`watchdog.sh` BOTS,
   `update-all.sh` restart loop). For any *seventh* character, both must be edited repo-side
   and deployed first (watchdog.sh syncs; update-all.sh needs the manual self-copy).
2. Build the instance dir:
   ```
   # device
   mkdir -p ~/priya-bot
   cp ~/telegram-bot/.env.example ~/priya-bot/.env
   cp ~/stp-deploy/telegram-companion-bot/priya/priya.json ~/priya-bot/priya.json
   cp ~/stp-deploy/telegram-companion-bot/priya/appearance.txt ~/priya-bot/appearance.txt
   cp ~/stp-deploy/telegram-companion-bot/priya/places.txt ~/priya-bot/places.txt
   ```
   (Character files are in the repo but NOT auto-deployed — the manual `cp` from
   `~/stp-deploy` is the normal path. Repo also ships `interests.txt`, `people.txt`,
   `projects.txt`, `schedule.txt`, `time_personality.txt` per character — copy the ones
   wanted, same pattern.)
3. Owner edits `.env` with nano (see section 8 for which keys): `nano ~/priya-bot/.env`
   — needs at minimum TELEGRAM_BOT_TOKEN (new @BotFather bot per character),
   NANOGPT_BASE_URL/API_KEY/MODEL (unless in common.env), ALLOWED_USERS,
   CHARACTER_CARD=priya.json, TIMEZONE, INWORLD_API_KEY (see section 8).
4. Wardrobe: deliver `wardrobe.json` content as a plain block the owner pastes into
   `nano ~/priya-bot/wardrobe.json` (shape: `{"outfits": ["desc1", "desc2"], "current": "desc1"}`)
   — or skip the file and have him use `/addoutfit` in the chat after launch.
5. Launch: `bash ~/telegram-bot/run-bot.sh ~/priya-bot priya`  `# device`
6. Verify: `bash ~/telegram-bot/status.sh` and message the bot on Telegram.

**Centralize shared .env keys** (optional, one-time): `migrate_common_env.py` moves keys
that are byte-identical across every existing bot `.env` into `~/telegram-bot/common.env`
(loaded by bot.py *before* the per-bot `.env`, which overrides it). It backs up every file
it touches to `.bak` (first run only — re-runs don't clobber the true snapshot) and never
moves TELEGRAM_BOT_TOKEN/BOT_TOKEN/CHARACTER_CARD/NAME/BOT_HOME. Copy it over by hand and
run with the venv python; then `bash ~/telegram-bot/update-all.sh` to restart.

**Back up one bot's memory** (zero-dollar variant — bake the date in yourself, no
command substitution):
```
# device
cp ~/nora-bot/state.json ~/nora-bot/state-backup-2026-07-02.json
```
Or the owner runs `/backup` in the chat (sends state.json, reminders.json, payments.json).

---

## 8. Secrets handling

- `.env` values are **typed or pasted by the owner directly on the device** (nano), never
  round-tripped through chat when avoidable — both for secrecy and because paste corruption
  (section 3) can silently mangle a key. If a key must go through chat, send it alone on
  its own line (no surrounding command) and have the owner verify with
  `cat -A ~/nora-bot/.env | grep INWORLD` style checks (that grep pattern has no `$`).
- **`INWORLD_API_KEY` (a base64 string) is required on every bot since 2026-07-01** —
  commits `ed15b25` (STT) and `faea119` (TTS) replaced NanoGPT with Inworld for voice in
  BOTH directions. Without it: incoming voice notes fail with
  "[couldn't make out that voice note]" and `/voice` replies silently don't send
  (documented in `.env.example` lines 101–114). It's the same value for all bots — a
  `common.env` candidate.
- Per-bot secrets that must stay per-bot: `TELEGRAM_BOT_TOKEN` (one @BotFather bot each),
  Garmin creds (`GARMIN_EMAIL`/`GARMIN_PASSWORD`, only on bots with the health feed).
- `update-all.sh` never touches `.env`/`common.env`, so deploys can't lose secrets.

---

## 9. What lands where on the device

`~/telegram-bot/` (shared code + shared runtime):
| File | What |
|---|---|
| `bot.py`, `bot_app/`, `acoustic_ears.py` | deployed code (synced by update-all) |
| `run-bot.sh`, `watchdog.sh`, `status.sh` | synced helpers |
| `update-all.sh` | manually copied (self-sync exception) |
| `.env.example` | synced template for new instances |
| `common.env` | optional shared settings, loaded before each per-bot `.env` |
| `venv/` | python environment |
| `watchdog.log` | watchdog relaunch log (+ run-bot output from watchdog relaunches) |

`~/<char>-bot/` (per instance — never synced, all owner-managed or bot-generated):
| File | What |
|---|---|
| `.env` | tokens/keys/config for this bot |
| `<char>.json` | character card (`CHARACTER_CARD=`) |
| `state.json` | history/memory/mood — saved once per turn and on SIGTERM/SIGINT (signal handler in bot.py); corrupt file is renamed `state.json.corrupted` at startup |
| `bot.log` / `bot.log.1` | stdout via supervisor `tee`; rotated at ~5 MB **by `.supervise.sh`, not bot.py** |
| `.supervise.sh`, `bot.pid` | written by run-bot.sh |
| `.alive` | liveness stamp, touched every 60 s by bot.py's job queue |
| `.next_heartbeat` | persisted proactive-message timer (survives restarts) |
| `wardrobe.json` | outfits (`/wardrobe` commands) |
| `reminders.json`, `payments.json` | reminder/bill stores |
| `.episodes.jsonl`, `.episodes.model` | episodic-recall archive (only with EMBED_MODEL) |
| `.garmin_snapshot`, `.garmin_cooldown` | Garmin cache (Garmin bots only); token store defaults to `~/.garminconnect` |
| context files | `life.txt`, `people.txt`, `projects.txt`, `schedule.txt`, `day.txt`, `user_notes.txt`, `places.txt`, `appearance.txt`, plus optional `interests.txt`, `time_personality.txt` |
| reference photo | `SELFIE_BASE=` e.g. `nora_base.png` |

**Generated selfies do NOT land on the device.** Verified in bot.py (`send_selfie` path,
~line 4194): image bytes are generated in memory and sent straight to Telegram via
`BytesIO`; nothing is written to the instance dir. If you need one preserved, the copy in
the Telegram chat is the only copy.

`~/.termux/boot/termux-boot-start.sh` — the boot launcher (manual copy).

---

## 10. Docker path (secondary, effectively vestigial)

`Dockerfile` + `docker-compose.yml` exist at the product root and SETUP_GUIDE mentions them
in exactly one sentence ("Docker is also available") under the Linux-VPS option. They run a
single home-instance bot (`CMD python bot.py`, no instance-dir argument, whole dir mounted,
one `.env`) — no multi-character support, no supervisor/watchdog integration, and nothing
on the Termux device uses them. Treat as an unmaintained convenience for a hypothetical VPS
user, not part of live operations. Do not reach for it when the owner says "restart".

---

## Provenance and maintenance

All paths relative to `/home/user/SillyTavernPresets/telegram-companion-bot/` unless noted.
Ground truth read on 2026-07-02: `update-all.sh`, `run-bot.sh`, `watchdog.sh`,
`termux-boot-start.sh`, `status.sh`, `migrate_common_env.py`, `requirements.txt`,
`.env.example`, `bot.py` (liveness, common.env, Inworld, selfie, state paths),
`docs/SETUP_GUIDE.md`, `docs/OPS_MANUAL.md`, `docs/EPISODIC_RECALL.md`, `Dockerfile`,
`docker-compose.yml`, repo-root `CLAUDE.md`. The paste-corruption rule (section 3) comes
from operational session history and exists nowhere else in the repo.

Re-verification one-liners (repo-side, `$` fine here):

```bash
# What update-all syncs vs skips, and the restart list:
sed -n '1,95p' telegram-companion-bot/update-all.sh
# Watchdog BOTS list + stale/interval defaults:
sed -n '16,35p' telegram-companion-bot/watchdog.sh
# setsid-not-nohup rationale still intact:
grep -n "setsid\|nohup" telegram-companion-bot/termux-boot-start.sh
# Log rotation threshold + supervisor loop:
grep -n "5242880\|restarting in" telegram-companion-bot/run-bot.sh
# .alive stamping interval:
grep -n "run_repeating(_touch_liveness" telegram-companion-bot/bot.py
# Inworld requirement + base64 note:
grep -n "INWORLD" telegram-companion-bot/.env.example
# Termux numpy rule:
grep -n "python-numpy\|include-system-site" telegram-companion-bot/requirements.txt docs/EPISODIC_RECALL.md 2>/dev/null || grep -rn "python-numpy" telegram-companion-bot/
```

Known doc staleness as of 2026-07-02 (fix docs, not this skill, when they diverge):
SETUP_GUIDE curls from `main` instead of the deploy branch; its pkg/pip lists omit
ffmpeg/termux-api/pypdf/garminconnect; OPS_MANUAL says priya isn't deployed while both
scripts already include her.
