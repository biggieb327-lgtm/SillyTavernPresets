---
name: bot-config-reference
description: Model slots, timeouts, per-instance integrations (voice, vision, traffic), and the continuity features those settings drive. Load when editing an .env, choosing or changing a model, debugging a config-shaped failure (400s, wrong voice, empty vision replies), or working on note follow-ups / day threads / the shared world.
---

# Bot config and feature reference

`telegram-companion-bot/.env.example` is the full documented template and accounts
for every variable bot.py reads (177 settable, 17 internal — verified 2026-07-25).
This skill holds the constraints that are **not** obvious from reading it.

## When NOT to use

- Editing card/seed/preset *content* → `edit-cards-and-presets`.
- Adding a new config var to bot.py → `repo-change-control` + `bot-code-invariants`
  (rules 15–16: `_env_int`/`_env_float`, mandatory kill switch).
- Group-chat variables specifically → `group-chat-changes` (read it first).

## Model slots — each has a hard requirement

| Slot | Value | Why it can't be anything else |
|---|---|---|
| `NANOGPT_MODEL` | `zai-org/glm-5:thinking` | main chat model |
| `SUMMARY_MODEL` / `REACTION_MODEL` | `glm-4.7-flash` | must be cheap + fast; they run off-loop |
| `FALLBACK_MODEL` | `anthracite-org/magnum-v4-72b` (recommended) or `Sao10K/L3.3-70B-Euryale-v2.3` | must be **roleplay-capable** — it serves user-facing replies on 400/429/5xx/timeout |
| `DOCUMENT_MODEL` | `deepseek/deepseek-v4-flash` | must be an **instruction** model — a roleplay model will *perform* the character card it was asked to analyze |
| `VISION_MODEL` | `zai-org/glm-4.6v` | must be **multimodal** — the chat default rejects images with a 400 |

**Emily deliberately runs `zai-org/glm-4.7:thinking`** for `NANOGPT_MODEL`
(owner-confirmed 2026-07-25). This is not drift — do not "correct" it to glm-5.
Per-instance model choice is expected: check the `=== STARTUP AUDIT ===` line for
what an instance is actually on before assuming anything.

API is NanoGPT, OpenAI-compatible, at `https://nano-gpt.com/api/v1`.
`call_nanogpt` = 2 attempts per model, 2s/4s backoff, 150s primary budget.

## Timeouts

- `STREAM_TIMEOUT` (90s) — max *silence between SSE chunks*, i.e. stall detection,
  not total request time.
- `REQUEST_TIMEOUT` (120s) — non-streaming requests.
- 30s proved too tight on a phone. Don't lower these to "reasonable" web values.
- Models that reject streaming are auto-retried non-streaming and remembered in
  `_no_stream_models`.

## Per-instance integrations

- **Inworld voice (Emily):** the TTS voice and the TTS model must come from the
  **same engine** — an Inworld voice ID sent to an OpenAI-style model 400s.
  Setting `INWORLD_API_KEY` switches the engine; `TTS_VOICE` must then be an
  Inworld voice ID.
- **WSDOT traffic (Emily):** `WSDOT_API_KEY` + `TRAFFIC_RADIUS_MILES` +
  `TRAFFIC_POLL_MINUTES` drive `/traffic`, `/incidents`, and live-location alerts.
- **Group-chat pilot (Priya + Jules, experimental):** `GROUP_MODE=1` +
  `GROUP_ALLOWED_CHATS` (fail closed) + `GROUP_PEERS`; loop caps
  `GROUP_BOT_CHAIN_MAX=2`, `GROUP_DAILY_BOT_BUDGET=30`. BotFather privacy must be
  DISABLED for pilot bots (re-add to the group after changing it). One-time
  on-device check: `python bot.py ~/priya-bot --claim-test` (expect two PASS
  lines). **Read `GROUP_CHAT_DESIGN.md` and load `group-chat-changes` before
  touching any of this.**
- **Timezone:** `BOT_TIMEZONE` is the setting; `TIMEZONE` is still honoured for
  existing `.env`s and conflicting values warn (v2026-07-25.14). Before that fix,
  `BOT_TIMEZONE` was read only to label a `--check-config` warning and every bot
  silently ran on the `America/Los_Angeles` default.

## Config failure behavior

Bad numeric `.env` values no longer crash the bot (v2026-07-10.2): `_env_int` and
`_env_float` fall back to defaults and emit a `[config]` warning. So a typo shows
up as a **warning in `/errors`, not a crash** — always check logs after an `.env`
edit rather than assuming silence means success.

## Continuity features (all characters)

- **Date-aware note follow-ups:** datable user mentions are stored with
  `(due YYYY-MM-DD)` in `user_notes.txt`; a daily job (`NOTE_FOLLOWUP_TIME`,
  default 18:00) asks how it went after the date, then marks `(asked …)`.
  Respects quiet hours and the nudge budget.
- **Multi-day life threads:** midnight rotation feeds yesterday's `day.txt` into
  today's event generation. Archived days are provenance-tagged `[own-day …]` so
  the character's own fiction is never presented as shared memory — that tag is a
  hard invariant (`bot-code-invariants` rule 10), not a formatting choice.
- **Shared world:** the `WORLD_GENERATOR=1` instance (nora) writes `world.txt` at
  midnight; all instances read it, giving the whole fleet the same weather and
  backdrop.

## Quality bar

Any model-slot change is justified against the requirement column above, not
against price or benchmark scores. Any `.env` recommendation names the file to
edit, the instance it affects, and the restart needed to apply it.

## Verification checklist

- [ ] New/changed var documented in `.env.example` with a default that preserves
      current behavior
- [ ] Model slot still satisfies its hard requirement (roleplay / instruction /
      multimodal)
- [ ] `/errors` checked for `[config]` warnings after the edit
- [ ] `/audit` confirms the instance is running the config you think it is

## Common mistakes

- "Correcting" Emily's `glm-4.7:thinking` to glm-5.
- Putting a roleplay model in `DOCUMENT_MODEL` — output looks like the character
  answering, not an analysis, and it reads as a prompt bug.
- Lowering `STREAM_TIMEOUT` to a web-typical value; it's stall detection on a
  phone connection.
- Assuming a silent bot means the `.env` edit worked — check for the warning.

## What to report back

Which variable changed on which instance, the constraint that justified the value,
the restart step, and the `[config]`/`/audit` output that confirmed it landed.
