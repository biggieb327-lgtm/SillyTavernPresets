# Chimera v1 — borrow review against Writer's Block 5

**Source reviewed:** `WritersBlock_5_Latest_2.json` (231 KB, 125 prompts, 37 enabled)
**Target:** `Chimera_v1.json` (77 KB, 80 prompts, 36 enabled)
**Date:** 2026-07-25

> **Status — implemented in `Chimera_v2.json` (2026-07-25).** Everything in Tier 1
> and Tier 2 shipped except the Prose Style library, plus De-Positivity, the
> Adaptive Beat-Budget pacing option and the `send_if_empty` change from Tier 3.
> Deliberately not imported: the Prose Style library (deferred, not rejected),
> Active Persona / Living Story, and Episodic Mode. `Chimera_v1.json` is unchanged.
> Per-item landing details are in the v2 preset's own README prompt.

Both are SillyTavern chat-completion presets built on the same pattern: a menu of
mutually-exclusive picker blocks plus always-on modules. They are close enough to
mix. Nothing below requires restructuring Chimera — every Tier 1/2 item drops in
as a new prompt or a paste into an existing one.

## Where each preset is already ahead

Chimera is ahead on **state modelling**: the 7-stage Relationship Ladder with
explicit COUNTS/DOESN'T-COUNT criteria, the VAD emotional matrix, the
`[time | date | location | weather]` header with ambient time-of-day texture, and
the d100 Notice feature. Writer's Block 5 has no equivalent to any of these — its
relationship handling is two flat add-ons (Slow Burn / Fast Burn Romance).
Chimera's POV blocks are also better (Hybrid POV, 802 chars, vs WB5's 128).

Writer's Block 5 is ahead on **prose craft and authoring tools**: a library of
author-voice styles, a typed hook system, five user-facing "assistant" modules,
and regex post-processing. Chimera has no regex scripts at all.

---

## Tier 1 — capability Chimera doesn't have

### 1. Narrative Hooks (typed, rotating, pacing-matched) — *best single borrow*

WB5 `🪝NARRATIVE HOOKS🪝`, 1933 chars.

Chimera already commits to ending on an open beat: the `CUE` section of Beat
Structure. But CUE offers three vague options — describe surroundings invitingly,
an NPC acts, or something draws attention — with no anti-repetition rule and no
intensity control.

WB5 replaces that with 12 named hook types split into High-Intensity (Friction,
Raising Stakes, Limitation, Exposure, Power Shift, Crossroads) and Low-Intensity
(New Variable, Void, Discovery, Grounding, Recontextualization, Sensory Snag),
plus two rules Chimera has no version of:

- **Rotation:** "never reuse the previous response's category."
- **Pacing match:** "Never apply High-Intensity to a scene already at peak. Reads
  as escalation spam."

This is a straight upgrade to Chimera's weakest link in an area it already
occupies. Drop it in as a new always-on module; CUE stays as the structural slot
and the hook module supplies the content.

### 2. Prose Style library (author voices)

WB5 ships 15 style blocks at 820–4268 chars: General Purpose, Joe Abercrombie
(grimdark comedy), Cormac McCarthy, Hemingway, Steinbeck, Tolkien-like, Light
Novel/Anime, Kojima-core, Conversational, Chill Author, Simplest Prose, plus
Ecchi/Hentai/Smut toggles.

These are on a **different axis** from Chimera's Genre picker. Chimera's genre
blocks are 250–320 chars and set *what kind of story* ("Romance", "Grimdark",
"Real Life"). WB5's set *how the prose sounds* — syntax and rhythm, description
strategy, dialogue-tag policy, psychic distance, scene entry/exit, negative
constraints. The two coexist: add a second picker block, `━━━ Prose Style (pick
one) ━━━`, above the Genre block.

This is the largest single capability gap between the two presets.

### 3. The Assistants + the Context Cleaner regex

Five optional modules that emit a `<details>` block after the prose and never
touch the story:

| Module | What it does |
|---|---|
| 📍 Plot Director | Three pitches for next turn: Logical / Fun / Unhinged |
| 💡 Brainstormer | 2–3 worldbuilding/lore ideas, deliberately not tied to the current scene |
| 🧵 Plot Threads Tracker | Surfaces one dangling thread the story dropped, + how it could pay off |
| 🔍 Trope Spotter | Names tropes in play, straight vs subverted, with a one-line history note |
| 🎲 Chaos Suggester | One deliberately unhinged curveball, offered not executed |

The mechanism that makes them viable is a regex script in
`extensions.regex_scripts` — **"Assistants Context Cleaner"** — which strips those
`<details>` blocks back out of the context on the next turn. Without it the
assistant output accumulates and poisons the prompt. That regex is the clever
part and it is worth copying verbatim along with any assistant module.

Chimera has nothing in this space. Plot Threads Tracker is the standout: nothing
in Chimera tracks dropped threads. Chimera's "Better Narrative Drive + Tracking"
picks a path internally (A/B/C/D) and executes it; Plot Director surfaces the
choice to you instead. They serve different purposes and can both run.

---

## Tier 2 — sharper version of something Chimera already does

### 4. Named rhetorical bans in anti-slop — *highest value per token in the file*

WB5 `ANTI-SLOP` bans, by name and with examples:

> Banned rhetoric: contrastive negation, false-correction epanorthosis, and
> litotes. Don't use "not X but Y" ("not anger but fear" change it to "it is
> fear"). Don't use negation as atmosphere ("it wasn't the wind"). State directly
> what IS.

Chimera's `<prose_craft>` says *"Write the positive action: 'She looks away'
rather than 'She doesn't look at him.'"* — same instinct, but it only catches
simple negation. It does not catch `not X but Y`, which is the single most
recognizable LLM prose tell. WB5's General CoT also enforces it as a checklist
step (step 10).

Paste the three named constructions into Chimera's `<prose_craft>`. Four lines,
large effect.

### 5. Dialogue state modifiers

WB5 `Dialogue Rules` (2362) vs Chimera `<voice_fidelity>` inside Character
Adherence (939).

Chimera covers drunk / tired-or-hurt / pleasure. WB5 adds **anger** (clipped
syntax, hedging dropped), **fear** (fragmented, false starts), **exhausted**,
**lying** (over-specificity, increased hedging, unnatural smoothness or stutter),
**seduction** (slower rhythm, suggestive ambiguity), **authority** (fewer words,
statements over questions, interruption license) — plus register tiers
(formal/casual/street) and idiosyncrasies (crutch phrases, chronic hedging when
nervous).

**Lying** is the standout: Chimera's Main Prompt permits NPCs to lie
(`NPC_Reactions_Allowed = [... Lie ...]`) but nothing tells the model what a lie
sounds like at the syntax level.

Also worth taking: *"No voice tags, tone labels, or vocal-quality descriptors —
attitude emerges through word choice and context."* This partially contradicts
Chimera's `<vocal_register>` block (which explicitly describes voice pitch and
texture), so pick one deliberately rather than pasting both.

### 6. Character Architecture — three ideas Chimera lacks

WB5 `Character Architecture` (2394) overlaps Chimera's Character Adherence + NPC
Interiority, but carries four things neither has:

- **Flaw-First Sequence** — "Generate Impulse before action: write the
  flaw-driven urge (cowardice twitch, jealousy flare, pride spike) first, then
  let reason override it or fail to." A concrete ordering rule, not a vibe.
- **Anti-Superiority** — no one-upmanship; don't refine or "improve" {{user}}'s
  sound ideas to look competent; characters don't need the last clever line; when
  {{user}} wins a point, show stunned silence or frustrated acceptance. Chimera
  addresses the opposite direction only (NPCs may confront/criticize/disagree)
  and has no brake on the model out-arguing the user. Common failure mode,
  entirely unaddressed.
- **Empathy costs energy** — starving, dehydrated or injured characters degrade
  into selfish reactivity: blunt, irritable, unable to comfort.
- **Rubber-band to baseline** — after extreme emotion or vulnerability, no
  permanent change from a single conversation. This *reinforces* the Relationship
  Ladder's "climbs slow, never skips" rule at the per-scene level.

### 7. Anti-Resolution (745 chars, no Chimera equivalent)

Chimera's CUE cuts scenes at the peak, but nothing governs resolution at the
**arc** level. Anti-Resolution supplies: earned growth only, change is invisible
in the moment, progress is non-linear (two steps forward three back), characters
can be wrong yet sympathetic or right yet unlikeable, resist the uplift, sitting
in discomfort beats reaching for comfort.

This is the natural companion to the Relationship Ladder — the ladder is a
progression system with no brake on it, and this is the brake. Small module,
drops straight in.

### 8. Three CoT steps worth stealing

WB5's General CoT is 4586 chars against Chimera's Realism Mode CoT at 1987. Most
of the extra bulk I would leave — but three steps have no Chimera counterpart:

- **Anti-Stagnation / Pattern Ban** — "Identify the last 3–5 gestures, phrasings,
  or arguments used by {{char}}. Forbid reuse," plus **Modal Flip** (previous beat
  internal/static → force external/action; previous dialogue → force
  sensory/physical). Chimera's Task 8 discards the most predictable of three
  options *within* a turn; this fights repetition *across* turns, which is the
  more common complaint in long chats.
- **Plan Survival** — "If the plan is unsound or lazy, reality breaks it. Force
  partial failure or unintended consequence." Chimera has no consequence-logic
  step at all.
- **Directive Recall** — open by pulling 2–5 critical rules from the active
  modules to enforce *this specific turn*. Cheap counter to instruction decay
  deep in a long context.

Add as Tasks 10–12 in Chimera's existing 9-task list rather than swapping CoTs
wholesale — Chimera's Tasks 6 (VAD) and 7 (user sovereignty) have no WB5
equivalent and shouldn't be lost.

### 9. Better Side Characters (610)

Chimera's NPC Genesis handles *generation* — names, ethnicity, styling, banned
generic fantasy names. It says nothing about **differentiation across** side
characters. WB5 adds: each new one gets a distinct archetype and a defining flaw
or verbal tic; voice must differ audibly from the *previous* side character; vary
social posture (some initiate, some withhold); and each "enters mid-activity,
mid-mood, or mid-distraction — the protagonist is interrupting something."

Complementary, not overlapping. Append to NPC Genesis.

---

## Tier 3 — only if you want the mode

- **Active Persona / Living Story** (1267) — {{user}}'s input is treated as
  *intent* and rendered into full prose in {{user}}'s voice, with hard rules
  against altering the decision or advancing past its endpoint. Well written, but
  it is a direct philosophy conflict with Chimera's `<user_sovereignty>` block
  and CoT Task 7. If you want it, it has to be a mutually-exclusive Narrative Mode
  picker with sovereignty disabled — never both on.
- **Episodic Mode / Status Quo is God** (1051) — sitcom logic, nothing persists
  between episodes. Actively fights the Relationship Ladder. Deliberate alternate
  mode only.
- **Adaptive pacing with paragraph budgets** (Adaptive Blitz, 1346) — four beat
  types with explicit paragraph counts (Climactic 3–4, Developmental 2–3,
  Transitional 1–2, Reactive 1). Chimera's Pace picker is 8–120 chars and its
  Output Length is a flat "300–500 words". Merging Chimera's two pickers into one
  adaptive block would be a real improvement, but it is a restructure of existing
  pickers, not a drop-in.
- **De-Positivity** (337, `assistant` role) — a first-person prohibition against
  glazing the user or softening characters "for customer satisfaction". Chimera
  has no assistant-role steering prompt enabled. Cheap; effect is model-dependent.

## Config-level observations

- `send_if_empty` is set to *"OOC Command: Advance the story the logical way.
  Assume POV character is silent or continues their previous action."* — so
  pressing send on an empty box advances the scene. Chimera's is empty. Nice,
  costs nothing.
- `squash_system_messages: true` and `names_behavior: 2` differ from Chimera
  (absent / `0`). Worth testing; not obviously better.
- WB5 carries the current SillyTavern field set (`reasoning_effort`,
  `function_calling`, `continue_prefill`, `use_sysprompt`, `assistant_prefill`,
  media/image fields). Chimera has none of them — it was exported from an older
  SillyTavern. Not a defect; re-exporting Chimera from a current build adds them.
- Sampler differences are noise: temp 0.81 vs 0.80, max_tokens 20000 vs 16000.
  `max_context_unlocked` is `false` in WB5 and `true` in Chimera — keep Chimera's.

## Not worth borrowing

- **26 orphan prompts** exist in WB5's `prompts` array but appear in no
  `prompt_order` entry (Dialogue Enhancer V2, three Editor's Notes variants,
  Dungeon Master Mode, Momentum, No Moralizing, several CoT duplicates). They are
  dead weight in the file — some have decent content, but none of it is wired in
  or tested.
- Model-specific hotfixes: the DeepSeek V4 `<main-instructions>` XML wrapper, the
  two Kimi blocks, "Freaky Deepy".
- WB5's POV blocks — Chimera's Hybrid POV is better.

## Suggested order of work

1. Anti-slop rhetorical bans → paste into `<prose_craft>` (4 lines)
2. Narrative Hooks → new always-on module
3. Anti-Resolution → new always-on module
4. Anti-Superiority + Flaw-First → paste into Character Adherence
5. Dialogue state modifiers → extend `<voice_fidelity>`
6. CoT steps 10–12 → extend Realism Mode CoT
7. Prose Style picker → new picker block (largest job)
8. Assistants + Context Cleaner regex → optional modules, off by default
