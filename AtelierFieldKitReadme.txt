# The Atelier Field Kit
### A Lean SillyTavern Preset for Any Session

**The Atelier Field Kit** is the compact companion to [The Atelier](../The_Atelier). It carries the same behavioral foundation and core style library in a leaner package — built for mobile, smaller context windows, and sessions where you want to start fast without configuring a full workshop.

**48 prompts. ~1,889 token session floor.** Everything you actually reach for.

---

## What's Different from The Atelier

| | The Atelier | The Field Kit |
|---|---|---|
| Total prompts | 140 | 48 |
| Style modules | 85 | 11 |
| Tonal presets | 6 | 4 |
| Sex scene presets | 10 (incl. combos) | 6 |
| Villain system | ✓ | — |
| RPG / RNG / CYOA engines | ✓ | — |
| Hyper addons | ✓ | — |
| Session floor (Writing Guide + CoT Short) | ~2,493t | ~1,889t |

---

## What's Inside

### Core Behavioral Foundation
- **Writing Guide** — behavior, OOC handling, turn economy, NPC consistency, no-dialogue-repetition rule
- **Model Configuration Guide** — always-active reference for Gemma 4 Thinking, GLM-5 Turbo, and non-thinking models

### Style Modules (🔊 Pick One Per Session)
11 modules covering the most distinct and universally useful registers:

- **Raymond Carver** — minimalist realism, radical omission, the unsaid
- **Bestseller Style** — cinematic commercial fiction, clean and readable
- **Angela Carter** — dark gothic fairy tale, psychosexual, lush and dangerous
- **Cormac McCarthy** — biblical cadence, no quotation marks, landscape as moral force
- **Elmore Leonard** — crime dialogue so good the narration is optional
- **Stephen King** — popular horror, character before dread, colloquial voice
- **William Gibson** — cyberpunk, fragmented sensory prose, the street finds its own uses
- **Free Indirect Style** — psychological immersive narration inside the focal character
- **Douglas Adams** — cosmic absurdism, the digression as payload, precise absurd simile
- **Greg Daniels & Michael Schur** — cringe comedy with warmth, mockumentary register
- **Penelope Douglas** — dark contemporary romance, dangerous desire, power imbalance

### Tonal Range (🔊 Pick One Per Session)
4 presets setting emotional atmosphere independently of the style module:

- **Hopeful & Kinetic** — forward momentum, competence rewarded, warm and fast
- **Detached & Ironic** — cool observer, understatement, deflated stakes
- **Bleak & Intimate** — dark and unsentimental, personal stakes, slow and dense
- **Lyrical & Intimate** — interior experience as subject, tender, present-moment

### Sex Scene Tonal (🔊 Pick One Per Session)
6 presets governing the emotional and power register of explicit content:

- **Tender** — intimacy as the subject, equal and slow
- **Erotic** — desire as the primary fact, sensation-forward
- **Dominant/Submissive** — explicit D/s, chosen power asymmetry
- **Literary** — defenses dissolve, psychological interiority
- **Dark/Transgressive** — discomfort earned by the story, complicated arousal
- **BDSM** — full D/s architecture, subspace, sensation specificity, aftercare

### CoT Prompts (💭 Pick One)
- **Short** — streamlined three-step chain for Gemma 4 Thinking
- **Non-Thinking Models** — manual `<think></think>` block for GLM-5 and standard models
- **Checklist** — lightweight positive checklist, lowest token overhead

### Addons (➕ Stack Freely)
- **Session Memory & Continuity** — key facts, character states, continuity flags (compressed)
- **Relationship & NPC Tracker** — disposition tracking, knowledge limits, inter-NPC dynamics (compressed)
- **Visceral Smut** — clinical anatomical language, sonic grounding, hypnotic rhythm; includes before/after examples
- **Grounded NPCs** — realistic psychological interpretation over trope defaults

---

## Recommended Settings

| Setting | Value |
|---|---|
| Temperature | 0.92 |
| Min-P | 0.06 |
| Top-P | 0.95 |
| Top-K | 0 (disabled) |
| Repetition Penalty | 1.05 |
| Reasoning Effort | High |
| Show Thoughts | Off |

---

## How to Use

**Minimum viable session:**
1. Enable 🔖 Writing Guide
2. Enable one 💭 CoT prompt matching your model
3. Enable one 🔊 style module
4. Start

**Adding tonal control:**
Enable one 🔊 Tonal Range preset. The style module governs prose voice. The tonal preset governs emotional atmosphere. They do not conflict.

**For explicit content:**
Enable one 🔊 Sex Scene Tonal preset. Enable ➕ Visceral Smut if you want full physical specificity.

**One 🔊 style module maximum.** One 🔊 Tonal preset maximum. One 🔊 Sex Scene preset maximum. One 💭 CoT prompt maximum.

---

## When to Use The Atelier Instead

Reach for [The Atelier](../The_Atelier) when you need:
- A specific author register not in the Field Kit (Woolf, Pratchett, Harris, Mantel, etc.)
- Villain & Antagonist archetypes and modifiers
- RPG Engine, RNG Engine, CYOA, or Describe User Actions
- Combination sex scene presets (BDSM + Literary, Dark + Dominant, etc.)
- Scene transitions, Hyper addons, Convert to Narrator
- The full tonal range (Dark & Epic, Grand & Sincere)

---

## Compatibility

Tested with: Gemma 4 31B Thinking, GLM-5 Turbo
Compatible with: Any OpenAI-format API via SillyTavern
Format: SillyTavern OpenAI preset (.json)

---
