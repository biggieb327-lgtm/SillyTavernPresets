---
name: companion-persona-engineering-reference
description: Domain theory of LLM persona/companion engineering as practiced in telegram-companion-bot. Load when editing a character card (nora/bonnie/cass/emily/jules/priya JSON), editing preset.txt, editing life files (appearance.txt, people.txt, places.txt, interests.txt, projects.txt, schedule.txt, time_personality.txt, life.txt), adding a new character, tuning persona behavior, or working on mood/safety/vibe/inner-voice/selfie/voice-identity prompt logic. Covers the SillyTavern card format as this codebase actually consumes it, prompt injection order, the appraiser-model pattern, voice-preservation rules, and known traps. Do NOT use for: deploying card files to the device (companion-bot-device-ops), memory-system internals (companion-bot-memory-campaign), or commit/deploy gating rules (companion-bot-change-control).
---

# Companion persona engineering — as practiced here

Ground truth for `telegram-companion-bot/` as of 2026-07-02. Everything below is verified
against `bot.py`, `preset.txt`, the six character directories, and git history — not against
the SillyTavern spec or general lore. Where this repo deviates from the spec, the repo wins.

**Terms, defined once:**
- **Character card** — a SillyTavern V2/V3 JSON file (`spec: chara_card_v2` / `chara_card_v3`)
  describing a persona: one per character dir (`nora/nora.json`, `bonnie/bonnie.json`, …).
- **system_prompt / description / personality / scenario / first_mes / mes_example** — card
  fields. `first_mes` is the scripted greeting; `mes_example` is example dialogue.
- **post_history_instructions** — card field injected AFTER conversation history (late =
  more salient); the strongest place to put style/behavior anchors.
- **depth_prompt** — `data.extensions.depth_prompt.prompt`; merged into post-history here.
- **Lorebook / character_book** — keyword-triggered background entries embedded in the card.
- **{{char}} / {{user}} macros** — placeholders replaced with the character's and user's names.
- **Preset** — `preset.txt`, a shared plain-text block of texting-style instructions.
- **Appraiser** — a cheap single-purpose classifier LLM call (mood, safety, scene, …).

---

## 1. The card format as consumed here (`load_character()`, bot.py ~1316)

`load_character()` reads `raw["data"]` (falls back to top level for non-nested cards) and
builds exactly three prompt artifacts plus the greeting:

| Card field | Where it lands |
|---|---|
| `name` | `NAME`; used everywhere (`{{char}}`, headers, appraiser prompts) |
| `system_prompt` | First part of the main system message |
| *(hardcoded)* | Then: "You are {name}. Always stay fully in character… You may use \*asterisks\* for actions and narration, in the third person, as in the examples." |
| `description` | `# Character description` section of main system message |
| `personality` | `# Personality` section |
| `scenario` | `# Scenario` section |
| `mes_example` | `# Example dialogue` section |
| `post_history_instructions` + `extensions.depth_prompt.prompt` | `POST_HISTORY_RAW`, injected as a system message AFTER history — the final behavior anchor |
| `character_book.entries[]` | `LORE`: per entry keeps `keys` (lowercased, word-boundary regex), `content`, `constant`, and honors `enabled` |
| `first_mes` | `FIRST_MES_RAW` — used ONLY as the `/start` greeting (bot.py ~4493), never injected into normal turns |

**Ignored from the spec** (present in the checked-in cards but never read at runtime):
`creator_notes`, `tags`, `avatar`, `creator`, `character_version`, `alternate_greetings`,
and all lorebook entry metadata beyond keys/content/constant/enabled (no `insertion_order`,
no `position`, no secondary keys, no recursion). `creator_notes` IS editable via `/setcard`
and shown when a card is analyzed as a document — it's a maintainer channel, not prompt text.

**Macros:** `fill()` (bot.py ~1310) replaces exactly `{{char}}` and `{{user}}` — nothing
else. Any other SillyTavern macro (`{{random}}`, `{{time}}`, `{{original}}`, …) written into
a card leaks into the prompt as literal text. Don't use them.

**Lorebook retrieval** (`triggered_lore`, ~2074): `constant: true` entries always inject;
others inject on a word-boundary keyword hit against the last user message + last 8 history
messages; when `EMBED_MODEL` is set, entries semantically close to the turn (cosine ≥
`LORE_MIN_SIM`, default 0.42) also inject. Triggered entries appear under `# Relevant
background`, filled with `{{char}}`/`{{user}}`.

**Live editing:** `/card` and `/setcard` edit individual fields at runtime; `_save_and_reload_card()`
re-serializes the whole card with `json.dumps(indent=2)` and reloads globals without restart.

### Trap: analyzing a card as a document (Cass's job)

When a user uploads a card `.json`, the bot must critique it, not become it. This was settled
over four commits in June 2026 (b458a17 → 1cc41ab → 89804c4 → 9d19b6a):

1. First fix: wrap performative fields in block quotes + "do not perform this character" —
   insufficient. Roleplay-tuned chat models treat `system_prompt`/`first_mes`/`mes_example`
   as live instructions regardless of framing (89804c4 stripped them entirely for this reason).
2. Settled fix (9d19b6a): route ALL document/card analysis through `DOCUMENT_MODEL` — an
   **instruction** model, default `meta-llama/llama-3.3-70b-instruct` — instead of the chat
   model. That made stripping unnecessary; all card fields were restored to the analysis
   output (`_format_json_for_prompt`, bot.py ~7111, labels `system_prompt` as "System prompt:").

The rule to preserve: **never point `DOCUMENT_MODEL` at a roleplay-tuned model.** If it ever
regresses to the chat model, the "bot roleplays the card it's reviewing" bug returns. The
uploaded card body also goes through the untrusted-content quarantine channel, not durable
memory (`_note_untrusted`) — only a short placeholder persists in history.

---

## 2. `preset.txt` mechanics

`preset.txt` (per-repo, one shared copy; overridable per instance via `PRESET_FILE`) is read
at startup into `TEXTING_STYLE` and injected **verbatim** as a system message near the END of
the prompt, after history and post-history (bot.py ~3364, gated on `TEXTING_REALISM`, default
on). Two consequences:

- **It cannot carry comments.** There is no comment syntax — every character in the file is
  live prompt text the model reads. Maintainer notes about preset.txt go in bot.py comments
  (see bot.py ~218-225), never in the file itself.
- **Late position = high salience.** It out-shouts the card body for style, which is why the
  per-character escape hatch below matters.

Current content (read it before editing — summarized here as of 2026-07-02):

- **"How you text"** — plain-text texting register: no markdown, **no asterisk actions**, no
  lists, don't open with the user's name, questions only when meant, no apologizing for
  slow replies.
- **"Your inner state"** — always be somewhere emotionally real, never default-pleasant; the
  state drives the output; never announce the mood ("show, don't tell").
- **"You have a point of view"** — disagree honestly, sit with ambiguity, no performed
  interest or agreement.
- **"You're a character, not a narrator"** — perceive only what the character could perceive,
  never narrate the user's inner life; dark material handled straight, in character.
- **"Forbidden phrases"** — the anti-slop block: an explicit banlist of AI-writing tells,
  each with the reason and the replacement move. Categories: hollow openers, assistant-speak,
  cushioning, filler openers, therapeutic mirroring, soft concessions, wisdom dispensing,
  meta-commentary, hedging chains, negation stacks, empty intensifiers, vague abstractions,
  stock physical-sensation clichés ("breath catches", "knuckles whitened"…), atmospheric
  filler ("the air between them"), the held-breath cliché, stock gestures (hair-tuck,
  lip-bite), emotion-as-liquid metaphors, involuntary-action constructions ("she found
  herself…"), "something in his eyes", vague anatomical landing spots, internal-fracture
  clichés, "ghosted" as a touch verb, rhetorical internal questions, trailing-ellipsis depth.
- Closing line: don't glaze; give what the moment earns.

This banlist is belt-and-suspenders with a code-level regex (`_SLOP_OPENER_RE`, bot.py ~3413)
that strips hollow openers from every reply post-hoc.

### Intentional exceptions — do not "fix" them

preset.txt's no-asterisk rule is the **global default**. **Bonnie, Emily, and Jules** have
`system_prompt` fields in their cards that deliberately override it with asterisk-action /
third-person action-beat prose (documented in commit 1ea39e8 and the bot.py comment at
~220-225). The card's system_prompt wins as the more specific instruction. Two edit rules
follow:

1. An edit to preset.txt must not be phrased so absolutely that it steamrolls a card-level
   style override.
2. Seeing asterisk actions from Bonnie/Emily/Jules is not a bug. Seeing them from
   Nora/Cass/Priya may be.

---

## 3. The character-file suite (per instance dir)

Each character dir (`nora/`, `bonnie/`, `cass/`, `emily/`, `jules/`, `priya/`) holds the card
plus plain-text "life files". All are re-read on a ~5-minute TTL cache (`_read_life_file`),
so device-side edits land without a restart. `#`-prefixed lines are comments in the
line-oriented files (places/interests/memories/reading) but NOT in the prose files
(people/projects/schedule/life/appearance/time_personality — those inject whole).

| File | Read by | Lands in prompt as | Notes |
|---|---|---|---|
| `appearance.txt` | startup → `SELFIE_APPEARANCE` (bot.py ~290) | `# Your appearance` system block (~3373) AND embedded in every selfie generation prompt (`build_selfie_prompt`) | **Dense single paragraph, age FIRST** ("a 25-year-old woman, …"). Gemini's image-safety filter returns blacked-out images for women with no stated age in casual/intimate settings — the age must lead. Instances without the file get a generic "adult woman in her late 20s" fallback for exactly this reason. |
| `people.txt` | `_read_people()` | `# People in {NAME}'s life` (~3190) | Also sampled (first 700 chars) into `_generate_life_event()` so invented life-sim events feature real recurring NPCs. |
| `places.txt` | startup → `ATLAS` (env `ATLAS_FILE`) | `# Local places` — a random sample of `ATLAS_SAMPLE` (6) entries, resampled every 5 min (~3224) | Also the fallback selfie scene when no hint is given. One place per line; `#` comments allowed. Anti-hallucination: real venues so she doesn't invent fake businesses. |
| `interests.txt` | `_read_interests()` | Not injected directly. Feeds the reading loop: `update_reading()` picks one interest, web-searches it, stores an in-character take (with link) in `reading.txt`; keyword-triggered entries surface as `# Things she's read lately` (~3346) | One topic per line. `reading.txt` is generated state (gitignored). |
| `projects.txt` | `_read_projects()` | Merged with `life.txt` into `# {NAME}'s life right now` (~3195) | Also feeds `_generate_life_event()` (first 400 chars). Multi-day/week ongoing threads. |
| `life.txt` | `_read_life_arc()` | Same merged block as projects.txt | The current story arc — slower-moving than projects. |
| `schedule.txt` | `_read_schedule_today()` | `# {NAME}'s day today` (merged with live day-events, ~3378) | Weekly routine grouped under day-name headings (Mon/Tue/… prefixes); only TODAY's section injects. Also grounds `_generate_life_event()`. |
| `time_personality.txt` | `_read_time_personality()` → `_time_personality_line()` | Appended to `environment_note()` (the LAST system block: "Your energy right now (evening): …") and to selfie prompts | One line per day-period, format `period name: description`. Periods matched: deep night / early morning / morning / afternoon / evening / late night. Missing file falls back to a built-in default. |
| `memories.txt` | `_read_memories()` → `triggered_memories()` | `# Relevant memories` (keyword/semantic-triggered) | NPC/world memories. Internals belong to companion-bot-memory-campaign — listed here only for where it lands. |
| `wardrobe.json` | `load_wardrobe()` (bot.py ~1644) | Current/matched outfit goes into selfie prompts (`pick_outfit`), not into chat prompts | **Per-instance runtime state, gitignored.** Seeded on the device via `/addoutfit <desc>`; managed with `/wardrobe`, `/setoutfit`-style commands. Never check one in. |
| `setting.txt` | startup → `SETTING` (~1214) | `# Current setting` (second system block) | Location/background overlay. Named instances default to empty (card carries it); the un-named home instance has a built-in Priya default. |

Files starting with the character's name + image extension (`nora_base.png`, `base.jpg`, or
`SELFIE_BASE`) are the selfie reference photo.

---

## 4. Voice preservation and how to edit a card (owner non-negotiable)

Rule 3 of change control (see companion-bot-change-control): **never rewrite a character's
voice.** Card edits may restructure, condense, and reorganize, but the established
personality and prose voice must be preserved verbatim wherever possible; any actual voice
shift needs explicit owner sign-off before it ships.

Working technique, as practiced in this repo's card history (e.g. 5e07e57, ea80db7, 4d50f88):

- **Distill FROM the card, don't invent.** New `personality`/`system_prompt` text is built by
  extracting phrases and patterns already present in `description` and `mes_example` — the
  voice already exists; your job is compression and placement, not authorship.
- **Edit surgically: single-field JSON edits that preserve the file's existing formatting.**
  Load-modify-dump re-serialization of the whole card changes array/whitespace formatting
  across the entire file and pollutes the diff, hiding the one field that actually changed.
  Edit the one field's string in place (text editor / targeted Edit), keep everything else
  byte-identical. (Runtime `/setcard` does re-serialize with `indent=2` — that's the bot's
  own file on the device, not the repo copy.)
- Cards are valid JSON with embedded newlines escaped as `\n` — a literal newline inside a
  string has broken a card before (1506f9b). Validate with `python3 -m json.tool` after edits.
- Where a rule should live: durable behavior/style anchors → `post_history_instructions`
  (most salient, post-history); identity and texture → `description`/`personality`; voice
  demonstration → `mes_example`; per-character style overrides of preset.txt →
  `system_prompt`.

---

## 5. The appraiser-model pattern

One expensive roleplay model writes her replies; a fleet of cheap single-purpose classifiers
("appraisers") maintain her state around it. All default-chain to `MOOD_MODEL`, which itself
defaults to `REACTION_MODEL` — so setting one env var retargets the whole fleet.

| Env var | Default chain | Job |
|---|---|---|
| `NANOGPT_MODEL` | `zai-org/glm-5:thinking` | Her actual replies |
| `SUMMARY_MODEL` | → `NANOGPT_MODEL` | Memory distillation |
| `VISION_MODEL` | `zai-org/glm-4.6v` | Photo/video turns (main model is text-only) |
| `FALLBACK_MODEL` | empty | Retry target on chat-model 5xx/timeouts |
| `REACTION_MODEL` | `zai-org/glm-4.7-flash` | Emoji reaction pick — the cheap anchor |
| `MOOD_MODEL` | → `REACTION_MODEL` | Mood appraisal (label + valence JSON) |
| `INNER_VOICE_MODEL` | → `MOOD_MODEL` | Private pre-reply monologue |
| `SAFETY_MODEL` | → `MOOD_MODEL` | Acute-distress yes/no classifier |
| `SCENE_MODEL` | → `MOOD_MODEL` | Physical-scene continuity extraction |
| `EVENT_MODEL` | → `MOOD_MODEL` | Dated-event extraction for reminders |
| `READING_MODEL` | → `MOOD_MODEL` | In-character takes on searched articles |
| `LIFE_MODEL` | → `MOOD_MODEL` | Life-sim event invention |
| `MEMORY_MODEL` | `zai-org/glm-5.2` | Memory extraction (not chained — quality-sensitive) |
| `DOCUMENT_MODEL` | `meta-llama/llama-3.3-70b-instruct` | Card/PDF/JSON analysis — MUST stay an instruction model (§1 trap) |
| `EMBED_MODEL` / `RERANK_MODEL` | empty (off) | Semantic retrieval — memory-campaign territory |
| `WHISPER_MODEL` | `whisper-1` | Video audio only |
| `INWORLD_STT_MODEL` / `INWORLD_TTS_MODEL` | `inworld/inworld-stt-1` / `inworld-tts-1.5-max` | Voice notes in / voice replies out |
| `SELFIE_MODEL` / `GEMINI_IMAGE_MODEL` | `flux-kontext` / `gemini-2.5-flash-image` | Selfie generation |

**Lesson (commit 18d4162, 2026-06): context-blind classifiers misfire on terse fragments.**
The safety classifier once judged messages in isolation; a terse reply like "all of it" or
"I don't know" — answering a mundane question — read as ominous with no context and
false-triggered crisis mode. Fix: `_assess_safety` now feeds the last 6 conversation messages
and instructs the classifier to read the newest message *against what it's answering*. Apply
the same principle to any new appraiser: give it the conversational tail, and tell it
explicitly not to judge fragments as if they appeared alone. (Inner voice, mood, and scene
appraisers all already take history tails.)

---

## 6. Behavioral subsystems — what injects, where, when

Prompt positions refer to `assemble_messages()` (bot.py ~3170). Order matters: earlier =
stable background, later = salient for this turn. Full order: card system prompt → setting →
people → life-now → life events → Garmin → local places → capabilities → **history** →
memory → quarantined attachments → user notes → **mood** → vent mode → **vibe** → user
energy → milestones → pinned → recent questions → lore → memories → episode → **scene** →
reading → boundaries → **post-history** → **preset (TEXTING_STYLE)** → **style mirror** →
appearance → today's schedule → **environment note (last)** → user message → **inner voice**
→ (**safety prompt, appended last by the caller when flagged**).

- **Mood** (`moods`, `mood_now`, `_appraise_mood`, `_mood_behavior`, `mood_note`):
  a valence score in [-3, +3] decaying toward 0 with a **24h half-life**. After each exchange
  (≥60s since last), `MOOD_MODEL` appraises the last 4 messages into a specific in-character
  label ("pissed off, some guy doored her on her route") + valence; label stays fresh for
  `MOOD_LABEL_FRESH_HOURS` (12). Long silences apply a pre-appraisal penalty
  (`nudge_mood`: gaps >12h subtract up to 1.8). `mood_note()` injects `# Mood` mid-assembly:
  the label (the WHY) plus `_mood_behavior()` (the HOW — concrete reply-length/energy bands
  at thresholds +1.2/+0.4/−0.4/−1.2), always with "never announce it."
- **Inner voice** (`generate_inner_voice`, ~3640): 2–4 sentences of private noticing/deciding
  from `INNER_VOICE_MODEL`, seeded with the first 600 chars of the card system prompt + last
  6 messages. Appended as the FINAL system message after the user's message ("# {NAME}'s
  private thought — not shown to {user}"). **Deliberately isolated from the mood system** —
  emotion is meant to act subconsciously via `mood_note`, not be reasoned about here. It is
  **skipped when distress is flagged** ("skip the performative inner voice in a crisis").
- **Safety** (`_assess_safety` → `_safety_prompt`): per-turn yes/no classifier (with 6-message
  context, §5) run concurrently with embedding, off the event loop. On "yes", `_safety_prompt`
  is appended **last — after even the inner voice slot — making it the most salient
  instruction**: drop the bit, be present in her own voice, don't minimize or lecture, and
  gently point to `SAFETY_RESOURCES` (default: the US 988 Suicide & Crisis Lifeline). On by
  default (`SAFETY_ENABLED`); classifier failure fails open to "no".
- **Vibe modes** (`/vibe`, `VIBE_PROMPTS` ~1660, `active_vibe`): owner-set register overlay —
  cozy, flirty, serious, chaotic, low-energy, playful, chill, and `in-person` (a scene mode
  that switches to embodied action-beat prose). Injected mid-assembly after mood; supports
  expiry timestamps. Vibe also folds into `_mood_vibe()` for selfie expressions.
- **Texting-style mirroring** (`_user_style_note`, ~3129, `STYLE_MIRROR` default on): pure
  heuristics over the last 20 user messages (≥6 required) — avg length, emoji rate,
  lowercase, exclamations, textspeak — emitting `# Matching {user}'s texting style` right
  after the preset, "without losing your own voice." No model call.
- **Scene continuity — anti-teleport** (`update_scene`/`scene_note`, `SCENE_CONTINUITY`
  default on): after each exchange, `SCENE_MODEL` carries forward one phrase of where she
  physically is ("at her kitchen table, seated, coffee in hand"). Injected as `# Where you
  physically are right now … show the transition — don't just appear somewhere else."
  Stale after `SCENE_MAX_AGE_HOURS` (3); "none" for abstract texting.
- **Lull detection** (~7571, `LULL_THRESHOLD` 3): consecutive terse user replies append a
  one-turn note to the user content — shift gears, bring up something new, don't push the
  current thread. Counter resets on any non-terse message.
- **Gap-aware openers** (~7563, `GAP_AWARE_HOURS` 12): when the user returns after a long
  absence, a one-turn note ("it's been about 3d … acknowledge the gap naturally — brief,
  not a big deal") is appended to that message only. The same gap also feeds the mood
  penalty and the appraiser's context.
- **Vent mode / user energy / boundaries / pinned**: `/vent` injects validate-don't-fix;
  detected user energy (low/high) adjusts latitude; `/boundary` items inject as "Hard
  constraints — respect these without exception or comment"; pinned facts inject as "Core
  things you know and never forget."

---

## 7. Voice identity (settled 2026-07-01)

- **Output (TTS):** `TTS_VOICE` in each instance's `.env` is an **Inworld `voiceId`** passed
  straight into the TTS payload (bot.py ~6907), model `INWORLD_TTS_MODEL`
  (`inworld-tts-1.5-max`). Catalog voices use display-name-like IDs (default `Sarah`);
  **custom cloned voices use generated IDs** of the form
  `amber-swan-3291__design-voice-5e83bdda` — not the display name you gave the clone. List
  valid IDs: `curl https://api.inworld.ai/voices/v1/voices -H "Authorization: Basic KEY"`.
  A wrong ID fails silently, like a bad key. Voice replies fire at `TTS_CHANCE` (0.30) when
  `/voice` is on; audio comes back as OGG/Opus, sent as-is.
- **Input (voice notes):** two para-linguistic channels run concurrently with transcription
  (`handle_voice`, ~6762):
  1. **Inworld STT voiceProfile** — `_transcribe_inworld` requests
     `voiceProfileConfig: {enableVoiceProfile: true, topN: 1}`; `describe_voice_profile()`
     summarizes the top label per category: emotion, style (vocalStyle), pitch, age, accent.
  2. **Local acoustic tone** — `acoustic_ears.py` (optional import, needs numpy; adapted
     from menelly/AI_Ears, MIT) does offline FFT analysis of pace/pauses/volume/pitch, no
     network (`_analyze_voice_tone` → `describe_acoustic`).
  Both merge into one bracketed note on the user turn:
  `[voice message]: <transcript>` + `[How it sounded: emotion=warm, pitch=low, <tone>]` —
  so the character reacts to how it sounded, not just the words. Gated by
  `VOICE_TONE_ENABLED` (default on) for the acoustic half.

---

## 8. Selfie pipeline basics (prompt-engineering surface only)

`build_selfie_prompt()` (~3916) composes: identity clause from `SELFIE_APPEARANCE`
(= `appearance.txt`, age-first — §3) with a same-person lock against the base reference
photo when one exists; then random picks from pools — `SELFIE_FRAMINGS`,
`SELFIE_EXPRESSIONS`, `SELFIE_ACTIVITIES` (weather-filtered; outdoor poses dropped in bad
weather), `SELFIE_CAMERA` (filtered for weather/time-of-day plausibility), outfit from
`wardrobe.json` via keyword match (`pick_outfit`) or a generic pool.

Two anatomy lessons are baked in — preserve them when touching the pools:

- **Framing pool is deliberately rebalanced away from reaching-arm poses** (commit 7578e7c):
  the classic arm-extended-toward-lens selfie is what triggers extra/detached-limb artifacts,
  so most framings crop the phone arm out of frame; only a couple of arm's-length/mirror
  shots remain for variety. Don't add reaching-arm framings back casually.
- **An explicit anatomy clause is always appended** (commit 3e7b161): "exactly two arms and
  two hands; the arm holding the phone connects normally at her shoulder — no extra,
  duplicated, or detached limbs."

The shot is mood-informed: `_mood_vibe(chat_id)` ("Her mood right now: … — let it read in
her face") and the current `time_personality` line both append. Providers:
`SELFIE_PROVIDER=gemini` (default when `GEMINI_API_KEY` is set; image-to-image off the base
portrait) or `nanogpt`.

---

## Provenance and maintenance

- Verified 2026-07-02 against branch `claude/push-to-repo-7i2f3c`: `bot.py` (line refs
  approximate; re-grep function names, not line numbers), `preset.txt`, all six character
  dirs, `.gitignore`, and commits 1cc41ab/89804c4/9d19b6a (card-analysis trap), 1ea39e8
  (style exceptions), 18d4162 (safety context), 3e7b161/7578e7c (selfie anatomy),
  bae2dcb/ed15b25/faea119 (voice identity).
- The cloned-voice ID format in §7 is owner-supplied operational knowledge (2026-07-01);
  the IDs themselves live only in device `.env` files, never in this repo.
- If you change `assemble_messages` ordering, preset injection, `_format_json_for_prompt`,
  or the selfie pools, update the matching section here in the same commit.
- Line numbers drift; the load-bearing facts are the orderings, defaults, and traps.
