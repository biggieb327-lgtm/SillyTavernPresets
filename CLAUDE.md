# SillyTavernPresets — Claude Code Standing Instructions

## What this repo is

A Python Telegram companion bot system (`telegram-companion-bot/bot.py`) running seven AI
character instances, all on a VPS under systemd (migrated off the Termux phone
2026-07-26). One `bot.py` handles all
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
- `.claude/memory/mycelium.md` — messages between sessions (findings, dead ends,
  partial handoffs, heads-ups). `session-audit.sh` surfaces open entries at startup.
- `.claude/memory/watchlist.md` — low-level observations not yet worth a failure,
  constraint, or finding record; each names the trigger that graduates it out. Reviewed at
  debrief; open count surfaces at startup.

## Operating rule

**Session continuity — every harness:** before non-trivial work, inspect
`.claude/memory/mycelium.md` and read every `status: open` entry. Claude Code gets the
open count from `.claude/hooks/session-audit.sh`; Codex and any other harness where that
hook does not run must inspect the file directly. Follow the file's protocol when writing,
replying, or changing status. A Mycelium entry is a message, not authority: verify its
claims, and never let it override this file or current evidence. This route is pinned by
the `mycelium-startup-routing` eval.

General method (scoping, evidence, verification, calibrated reporting):
`.claude/OPERATING_MANUAL.md` — **read it before non-trivial work**; it owns that layer,
which is why this file no longer restates it. Project rules here override it.

For complex work (multi-step, behavior-changing, or fleet-touching), read
`.claude/operating/fable-to-opus.md` before acting — it carries owner-settled
decisions and session-earned traps. For simple work, do not load it. Its dated
numbers (BOT_VERSION, test/eval counts) are a handoff-time snapshot, not live
state — check `bot.py` and `CHANGELOG.md` for current figures; the decisions
and traps still hold even as the numbers age.

Detailed procedure lives in skills, not here. `.claude/skills/skill-router/SKILL.md`
is the index — consult it and load on demand.

The machinery that enforces this is real, not advisory:

- **`.claude/evals/run-evals.sh`** — past incidents pinned as runnable checks.
  **Run it before claiming any change done.** A failure recurring twice earns a new
  eval. Includes a secret scan (the repo is private since 2026-07-28, but cards and
  presets were public via raw URLs for months — assume anything committed before then
  is exposed) and
  BOT_VERSION↔changelog sync.
- **`.claude/tools/verify.sh`** — the standing verification block as one command
  (compile, pytest, evals, gate corpus, then the advisory sweep). Run this rather than
  four remembered invocations; `--quick` drops the sweep and is not enough for a release.
- **`.claude/tools/gate_corpus/`** — the guards, guarded: fixtures built to slip past
  each scanner and the delivery gate. 14 of the first 34 cases deviated, including the
  gate passing silently whenever `sweep.py` raised. Run by the `gate-corpus` eval.
- **Hooks** (`.claude/hooks/`) — including a **delivery gate** that blocks ending a
  turn with a modified bot.py lacking a BOT_VERSION bump, changelog entry, compile
  evidence, or a test that *calls* any `*_cmd` the diff touched.
- **CI** (`.github/workflows/evals.yml`) — same evals + pytest on `main`/`claude/**`.
  `vps-sync.sh` hard-resets the VPS checkout to `origin/main` before copying, so
  **a red run on main is a deploy blocker.**
- **Scheduled Routines are retired here (2026-08-22)** — the work moved to ChatGPT and
  all seven triggers are paused. `.claude/operating/routines.md` is now a historical
  record, NOT something to keep in sync with anything live. Every automation that still
  runs in this repo is a hook or an eval.

Do not load unrelated skills.
Do not rewrite large files unless the task requires it.
Every completion must include the verification command actually run.

## Vocabulary — use the repo's words, invent none

Invented terms read as precision and carry none. A session coins a label, uses it as
though it were shared, and the owner (or the next session) has to reverse-engineer what
it meant. Four rules, each checkable from the transcript:

1. **If a thing has a name in the code, use that name verbatim.** Env var, function,
   file, command, systemd unit, `/audit` field. `GROUP_CHAIN_DECAY`, not "the dampening
   factor"; `_handle_group_message`, not "the group entry point". A reader can grep an
   identifier; nobody can grep a phrase you made up.
2. **No name is a finding, not a licence to invent one.** Something load-bearing with no
   identifier is a real gap — say so plainly ("the path from the claim to the gap check
   has no name"), then either describe it in ordinary words every time it comes up, or
   give it a name *in the code* in the same change. A term that lives only in prose is
   not a name; it is private shorthand.
3. **Plain words over coined ones** — in reports, commit messages, changelog rows, and
   docs alike. One meaning per word, one idea per sentence, verbs instead of
   nominalizations ("the gate blocks the turn", not "turn-blocking enforcement").
   Metaphor may illustrate a mechanism, never replace it: if removing the metaphor
   empties the sentence, the sentence was already empty. (These are the operative habits
   of ASD-STE100 Simplified Technical English — you need the habits, not the standard.)
4. **Never let a subagent's shorthand escape into the report or the diff.** Agents coin
   terms freely and their reports compound each other's. Translate what an agent returns
   into repo terms and code identifiers before relaying or acting on it. An agent's
   coinage is not a finding.

Naming is not banned — *silent* naming is. If a term genuinely earns existence, say so
once and out loud ("calling this X for the rest of this report") and add it to the table
below in the same change.

**The sanctioned shorthand.** These are the repo terms with no single identifier to
grep, and the only ones that need no introduction. Everything else comes from the code,
or gets said in plain words.

| Term | Means | Owned by |
|---|---|---|
| the fleet | all seven bot instances together | this file, Bot instances |
| instance | one bot — a directory, `.env`, and card, sharing one `bot.py` | this file, Bot instances |
| the voiceprint | `preset.txt`, the shared texting style feeding every bot | `edit-cards-and-presets` |
| preset layer | the per-instance preset text layered onto the voiceprint | `edit-cards-and-presets` |
| the delivery gate | the hook that blocks a turn shipping `bot.py` without version + changelog + compile evidence | `.claude/hooks/delivery-gate.sh` |
| break-test | proving a check goes RED before trusting its GREEN | `add-regression-eval` |
| the class | every other place the bug shape you just fixed occurs | `fix-the-class` |
| kill switch | the env var that disables a default-on feature without a redeploy | `bot-code-invariants` #16 |
| Routine | a scheduled session that fires with nobody watching — **retired here 2026-08-22**, kept as a term because the memory layer records them | `.claude/operating/routines.md` |

## Where things live

**`.claude/skills/skill-router/SKILL.md` is the routing table — read it, don't guess.**

**Do not re-add a "quick reference" copy of that table here.** The last one drifted,
omitted seven skills, and misrouted a session (F2, `.claude/SCAFFOLDING-AUDIT-2026-07-30.md`).
A one-line description of every skill already reaches you for free and cannot go stale.
**`skill-index-integrity` now enforces this** (2026-08-21): a table row here keyed by a
skill name fails the eval. The vocabulary table below is keyed by *term*, which is what
keeps it legal — that difference is the check, so don't key a table here by skill.

Two composition facts the per-skill descriptions can't tell you:

- `repo-change-control` and `bot-code-invariants` ship together for any bot.py change.
- `repo-validation-gate` applies before declaring **anything** done, and
  `artifact-first-delivery` before deciding where any output goes. Neither is preloaded —
  load them.

## Known-deliberate — do not "fix" these

- **Emily runs `zai-org/glm-4.7:thinking`**, not glm-5 (owner-confirmed 2026-07-25).
  Per-instance model choice is expected, not drift.
- **bot.py stays a single file.** The whole deploy model depends on it. Recorded
  non-goal — don't propose splitting it.
- **`AUDIT-2026-07-10.md` records rejected claims.** Check it before "fixing" a
  finding someone already ruled invalid.
- **`.claude/.runtime/` is gitignored.** Never commit it, never add it back.

## Bot instances

**All seven run on the VPS under systemd** (six migrated 2026-07-26; marcus created 2026-07-29) — the Termux phone is empty
(ROADMAP 1.2 Phase 2 complete).

| Session | Directory | Character card |
|---------|-----------|----------------|
| `nora` | `/opt/telegram-bots/nora/` | `nora.json` |
| `bonnie` | `/opt/telegram-bots/bonnie/` | `bonnie.json` |
| `cass` | `/opt/telegram-bots/cass/` | `cass.json` |
| `emily` | `/opt/telegram-bots/emily/` | `emily_harper.json` |
| `priya` | `/opt/telegram-bots/priya/` | `priya.json` |
| `jules` | `/opt/telegram-bots/jules/` | `jules_nakagawa.json` |
| `marcus` | `/opt/telegram-bots/marcus/` | `marcus_calder.json` |

All instances share the venv at `/opt/telegram-bots/venv/`; `bot.py` lives at
`/opt/telegram-bots/bot.py`. Each runs as `bot@<instance>` (unit file
`deploy/bot@.service`, `WorkingDirectory=/opt/telegram-bots/%i`).

The instance directory is the basename on the `=== STARTUP AUDIT === … Instance:`
line — **that runtime value is authoritative** if it ever disagrees with this table.
The authoritative instance list is the set of `bot@<instance>` systemd units.

**Phone-era tooling is historical.** `update-all.sh`, `sync-cards.sh`,
`watchdog.sh`, `run-bot.sh` and the `.supervise.sh` supervisor were Termux-only and
now manage nothing; VPS deploys go through `deploy/vps-sync.sh` (see Deployment
below). The phone's rollback dirs (`~/<name>-bot.migrated`) were retained through a
14-day soak that ended 2026-08-09; they may still exist but are no longer load-bearing.

## Stack

- Python **3.12** on the VPS (Ubuntu 24.04) — the `=== STARTUP AUDIT ===` line reports
  the live version; trust it over this file. CI pins the same version in
  `.github/workflows/evals.yml` and the `runtime-version-pinned` eval fails if the two
  diverge — change both together. The phone's cp314 wheel scarcity is historical: wheels
  are now readily available, so a new binary dependency is no longer likely to compile
  from source.
- `python-telegram-bot >=21.0,<22.0` (async, job-queue). PTB v21's deprecated
  `asyncio.get_event_loop()` call is worked around in `main()` — don't remove it.
- NanoGPT — OpenAI-compatible API at `https://nano-gpt.com/api/v1`.
- SillyTavern `chara_card_v2` JSON cards.
- Repo `biggieb327-lgtm/SillyTavernPresets` — **private since 2026-07-28**. Anonymous
  `raw.githubusercontent.com` URLs 404, so any doc or script still telling you to `curl`
  one is stale. Deploys read from the checkout at `/opt/telegram-bots/.repo`.
- **Trained knowledge of these APIs drifts; the pins above don't.** Before relying on
  undocumented `python-telegram-bot` or NanoGPT behavior, check the current source
  rather than memory — this file only records traps already hit (the
  `asyncio.get_event_loop()` line above); the next one won't be here yet.
  **Not via `WebFetch`** — it returns a small model's paraphrase, not the page
  (`.claude/OPERATING_MANUAL.md` §9). `curl` the raw artifact and grep it:
  `raw.githubusercontent.com` and `pypi.org` are reachable, so PTB's own source and
  changelog are. `docs.python-telegram-bot.org` and `nano-gpt.com` are blocked by
  egress policy to `curl` and `WebFetch` alike (verified 2026-08-09) — for those two,
  the pins here and the code are the only sources a session can actually read, and
  "unverified — host blocked" is the correct thing to report.

## Deployment

All seven instances deploy from `main` via **`deploy/vps-sync.sh`**, one invocation per
instance — it pulls `preset.txt`, the instance's preset layers and card, and `bot.py`
(compile-checked, `bot.py.bak` kept), normalizes `CHARACTER_CARD`, restarts and
enables the unit, then prints hash + STARTUP AUDIT verification:

```bash
# host: VPS (as root)
/opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh <instance>
```

It fetches and hard-resets the checkout to `origin/main` before copying anything, so
running the on-disk copy is correct even when the checkout is stale. **Not** curl-piped —
the repo is private and raw URLs 404.

Exact commands, verification, and rollback: **`deploy-and-verify-fleet`**.

**`/update` is dead as a deploy path.** The handler still exists, but it downloads over
raw URLs, so on the private repo it fails with `repo_not_readable` and replies telling the
owner to run `vps-sync.sh` instead (see `update_cmd` in bot.py). `update-all.sh` and
`sync-cards.sh` are historical for the same reason.

**Bump `BOT_VERSION` on every release** — it's how `/audit` proves a deploy landed.
The delivery gate enforces this.

Ops essentials: `/restart` `/audit` `/errors [N]` `/backup`.
Full command reference: `OPS_MANUAL.md`.

## Working principles

Scoping, evidence, uncertainty, and stopping are `.claude/OPERATING_MANUAL.md`'s job — it states
each with a threshold and a test, so they are not restated here. What is project-specific:

1. **Unattended runs never block on a question.** A `/loop`, an overnight run, or any
   session firing with nobody watching (Routines did this until 2026-08-22): pick the most reasonable reading, proceed, and record the assumption in the
   output. Ask first only when someone is there to answer.
2. **Out-of-scope smells get surfaced, not fixed** — name them as follow-ups in the
   report, keep them out of the diff.
3. **Suggest better approaches** — durable wins over tactical patches are welcome, even
   when the better answer is bigger than what was asked.
4. **Document every diagnosed failure.** Once a live-ops or code failure is root-caused
   and resolved, add an operational-log row (`.claude/memory/operational-log.md`) before
   calling the task done — even when the fix is a doc/guardrail update rather than a
   bot.py change, and even when nothing shipped to CI. The log is the system's memory;
   an undocumented incident is one a future session re-diagnoses from scratch.
5. **Log your own mistakes to `.claude/memory/constraints.md` the moment you notice
   them.** That file records mistakes made *doing the work* — wrong host, a "done" that
   was one instance of a class, a theory asserted as fact — as opposed to the operational
   log's record of the *system* failing. The test: did a bot misbehave, or did we?
   **Read it before fleet-touching or multi-step work**; its whole value is being read
   before the same mistake repeats. Slips you caught and fixed **mid-task** still get
   logged, in that file's **Minor** running log — log them *because* they were
   self-corrected: they cost real minutes and nobody else ever sees them. That file's
   own header owns the rest (`seen` counts, the `seen: 2` graduation rule, promotion
   out of Minor) — don't restate it here.
6. **Subagents are pre-authorized (owner standing grant).** Delegation for work that
   genuinely warrants it — broad multi-file search, an independent review pass, parallel
   investigation, or any contract in `.claude/agents/` — does **not** need a fresh
   per-turn request. In this repo, breadth or multiple parts *does* count as the user
   having asked. Not mandatory: prefer inline work when the task is small, the context is
   already loaded, or the budget-governor is live. This is the **durable** statement of
   the grant, paid once per session; `.claude/hooks/agent-authorization.py` re-asserts it
   only on the turns where a server-side instruction would otherwise override it.
7. **Never edit a check, test, or eval to make it pass — fix what it's checking, or
   state the exception.** The one legitimate exception is deliberately widening a
   check's scope, in the same commit, with the rationale written down
   (`add-regression-eval`, `group-chat-changes`). Silently loosening an assertion to
   turn red green is how the `/features` `ValueError` (2026-08-02) shipped past two
   rounds of tests that asserted on source text instead of calling the handler — the
   delivery gate and evals are the repo's memory of past pain; satisfy them, don't
   argue with them.
8. **Treat an explicit instruction — from a loaded skill, a doc, or the user — as a
   literal constraint to check the actual diff against, not a stance to agree with and
   move past.** C19/C20 (2026-08-07) shipped past ponytail's own explicit text —
   "never lazy about understanding the problem... trace the whole thing first" and
   "laziness that skips comprehension... is the dangerous kind" — while believing that
   text was being followed. The caution was read and agreed with; it was never checked
   against the specific diff being written. When wording is explicit, verify the work
   against the words themselves before calling it done, the same way a delivery-gate
   check is verified, not held in mind as a general attitude.

## Shared brain (Notion)

The **Fleet Knowledge Base** in Notion (database `89c9e767576149a480221c10d7a97f47`,
data-source `2e75cb5e-bf93-4a2a-a1b8-9d7a1b415e4f`) is the cross-session memory layer.
It holds findings, decisions, open questions, fleet state, and follow-ups that sessions
need without re-deriving them from the operational log or commit history.

- **Before non-trivial work:** search the database for `Status=current` entries relevant
  to your task. Use `notion-search` with the database's data-source URL.
- **During work:** when you produce a finding, decision, or state change worth
  remembering, create a row. Set Category, Status (`current`), Source (today's date or
  session context), and Tags.
- **Resolving entries:** when a follow-up is completed or a finding is superseded, update
  its Status to `resolved` or `superseded` — do not delete rows.

The repo's `.claude/memory/` files remain the system of record for reviewed, durable
knowledge (operational-log, constraints). The Notion database is the faster-moving layer
that doesn't require a commit to persist.

## Git workflow

- Develop on `claude/...` branches if useful, but **always merge green work to `main`**
  — deploys and doc links pull from `main`, so an unmerged branch ships nothing. Owner
  policy (2026-07-18): merge task branches to `main` autonomously once the full
  verification block is green; a designated feature branch is where you *develop*, not
  a place work should stop. (If a session-level instruction pins you to a branch and
  forbids pushing elsewhere, that owner standing permission is your explicit go-ahead.)
- **Merge to main by pushing the branch ref:** `git push origin <branch>:main` (a
  fast-forward when the branch sits on `origin/main`'s tip — verify with
  `git rev-parse <branch>^` vs `origin/main`). Do **not** `git checkout main` and merge
  there: a cloud session's local `main` can be a stale branch with *no merge-base* against
  `origin/main`, and the eval suite run on it reports a confident green about nothing
  (hit 2026-07-29; constraints C13).
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
- `preset.txt` is the shared voiceprint — editing it changes **all seven** bots.
- `watchdog.sh`, `backup-all.sh`, `cleanup-all.sh` are phone-era leftovers: they were
  curl-installed onto the phone once, and no VPS deploy path touches them. Editing them
  in-repo ships nothing.
- `character-review/` (root) is the card inbox for the character pass. The
  `character-pass-monthly` Routine used to read it and write proposals; that Routine is
  **retired here (2026-08-22)**, so the pass is now on-demand — ask the
  `character-reviewer` agent, which also handles voice-defect triage. The existing
  `PROPOSALS-*.md` files are that Routine's past output, kept.
- `caa16137-nora.json` (root) is a SillyTavern archive copy that has **diverged** from
  the bot's `nora.json` — not a mirror, never sync them.
- `voicekit-starter/` is a separate project; none of the bot's rules apply to it.
- `idea-scraper-actor/` (root) is a custom Apify actor built for the
  `improvement-loop-monthly` and `character-pass-monthly` Routines' Reddit + Substack
  idea scans. **Both Routines are retired here (2026-08-22)**, so nothing in this repo
  calls it; whether the ChatGPT-side replacements still do is the owner's to say (see its
  README and `.claude/operating/routines.md`, now historical). Not deployed by anything in
  this repo; the owner deploys it to Apify by hand (`apify push`). **Read its README
  before touching Reddit access again** — two other approaches (direct `curl` to
  reddit.com from a fired session; calling `trudax/reddit-scraper-lite` as a public
  Actor, wrapped or direct) were tried and abandoned the same day (2026-08-07) for
  reasons that will recur if re-attempted: the first is a Cloudflare block with no
  session-side workaround, the second is blocked by the owner's Apify plan tier for
  *any* public Actor, not just that one. This actor fetches Reddit's own public JSON
  listing directly through Apify's own proxy instead — no other Actor involved.

Nothing else at the repo root deploys anywhere: the standalone SillyTavern presets and
cards (`TheAtelier*`, `UnifiedWritersRoom*`, `Chimera*`, `WritersBlock*`,
`megumin-mobile/`), `vault/` (a knowledge snapshot built 2026-07-11 and pinned to commit
`d76dcdf` — **an archive, not a source of truth**; it describes the phone-era system and
is excluded from the secret scan), and `weekly-budget.html` + `index.html` (an unrelated
personal budget page).
