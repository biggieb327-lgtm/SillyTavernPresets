# The Atelier
### A SillyTavern Preset for Serious Storytelling

**The Atelier** is a comprehensive SillyTavern preset built around a modular style library, tonal control system, and narrative quality tools. It started as a dungeon master preset and evolved into a full storytelling engine covering literary fiction, genre writing, horror, comedy, sci-fi, romance, and explicit content — with model-specific configuration for Gemma 4 Thinking, GLM-5 Turbo, and non-thinking models.

---

## What's Inside

**140 total prompts** organized into a modular system you assemble per session.

### Core Behavioral Foundation
- **Writing Guide** — always-active behavioral baseline covering persona consistency, OOC handling, turn economy with action scene exceptions, scene-specific directives, and a no-dialogue-repetition rule
- **Model Configuration Guide** — always-active reference covering optimal settings for Gemma 4 Thinking, GLM-5 Turbo, and non-thinking models
- **Expanded Main Prompt** — universal behavioral anchor

### 85 Style Modules (🔊 Pick One Per Session)

Organized into 8 groups, each with a `// STYLE:` description at the top:

**Literary Realism**
Ford/Gaitskill (Intimate Observer / HotwifeOS), Carver (Minimalist), Bestseller, Penelope Douglas (Dark Romance), Sylvia Day (Erotic Romance), Faulkner (Stream of Consciousness), Virginia Woolf (Stream of Consciousness)

**Dark & Gothic Literary**
Angela Carter, García Márquez (Magical Realism), Murakami (Quiet Surrealism), Urban Fable, Free Indirect Style

**Genre Fiction**
Cormac McCarthy, Louis L'Amour, Elmore Leonard, Chandler (Noir), Le Guin (Anthropological Sci-Fi), LitRPG, Gritty Pulp (Hardboiled), Epistolary/Found Document, Screenplay Format

**Horror**
Stephen King, Shirley Jackson, Wes Craven, Flannery O'Connor (Southern Gothic), Lovecraft (Cosmic Horror), Clive Barker (Dark Fantasy/Body Horror)

**Sci-Fi**
William Gibson (Cyberpunk), Philip K. Dick (Paranoid Realism), Octavia Butler (Afrofuturism), Arthur C. Clarke (Hard Sci-Fi), Frank Herbert (Epic/Political), Iain M. Banks (Space Opera)

**Thriller & Psychological**
Gillian Flynn, Thomas Harris

**War, Satire & Historical**
Tim O'Brien (War Literature), Kurt Vonnegut (Black Humor), Hilary Mantel (Historical Fiction), Harry Turtledove (Alternate History), Tom Clancy (Military Techno-Thriller)

**Comedy**
Roald Dahl, Douglas Adams, Terry Pratchett, P.G. Wodehouse, Mel Brooks, Christopher Guest, Greg Daniels & Michael Schur (The Office/Parks), Greg Garcia (Earl), Hunter S. Thompson (Gonzo), Modern Digital, British Humor, Hyper-Dramatic, Glitchy System, Malicious Physicist, Brainrot, E-Sports, Vince Gilligan & Peter Gould, Farrelly Brothers

### Tonal Range Dials (🔊 Pick One Per Session)

**General Tonal Range** — 6 presets that set emotional atmosphere independently of style module:
Bleak & Intimate, Dark & Epic, Hopeful & Kinetic, Detached & Ironic, Lyrical & Intimate, Grand & Sincere

**Sex Scene Tonal Range** — 10 presets covering emotional and power register for explicit content:
*Single:* Tender, Erotic, Dominant/Submissive, Literary, Dark/Transgressive, BDSM
*Combination:* BDSM + Literary, Tender + Erotic, Dark + Dominant, BDSM + Dark/Transgressive

### Villain & Antagonist System (🔊 Pick One Archetype + Stack Modifiers)

**6 Archetypes:**
The Mirror (Lecter), The System (Landa), The Force (Chigurh), The Planner (Amy Dunne), The Believer, The Wounded

**5 Stackable Modifiers:**
High Competence, Personal History, Genuine Sympathy, Visible Cost, Humor

### Addon Toggles (➕ Stack Freely)

- **Session Memory & Continuity** — key facts, character states, plot events, continuity flags, drift prevention
- **Cinematic Scene Transitions** — hard cuts, dissolves, smash cuts, time skips, location establishing beats
- **Relationship & NPC State Tracker** — disposition tracking (hostile → devoted), knowledge limits, inter-NPC dynamics
- **RPG Engine** — SPECIAL stats, HUD metadata, inventory management, anti-godmodding, dynamic action menus
- **RNG Engine** — D20 dice via tool call, checkpoint system, narrative resolution without numbers
- **CYOA** — Choose Your Own Adventure structure with dynamic choice menus
- **Describe User Actions** — expands short commands into detailed character-specific prose
- **Visceral Smut** — explicit content with clinical anatomical language, sonic grounding, and hypnotic rhythm; includes before/after examples for each rule
- **Hyper Violence** — anatomical destruction, fluid dynamics, victim reaction
- **Hyper Sexuality** — fluid volume, anatomical distortion, sensory overload
- **Hyper Expression** — cartoon face physics
- **Hyper Gluttony** — Kirby-logic consumption
- **Hyper Personality** — flanderization/trait absolutism
- **Grounded NPCs** — realistic psychological interpretation over trope defaults

### CoT Prompts (💭 Pick One)

- **Long** — full analysis chain with first-paragraph drafting; for Gemma 4 Thinking
- **Short** — streamlined three-step chain; for Gemma 4 Thinking
- **Non-Thinking Models** — injects manual `<think></think>` block; for GLM-5 and standard models
- **Checklist** — lightweight positive checklist; lowest token overhead

### Utility Prompts
- **Convert Any Card to Narrator** — ensemble/world simulation, NPC embodiment, Spotlight Rule
- **Character Card** + **User Card** — structured character/persona injection wrappers
- **World Info Start/End** — XML container wrappers for lorebook content

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

**Gemma 4 Thinking:** Use CoT Long or Short. Native `/think` suffix triggers thinking mode. Raise temperature to 0.95 if output feels flat.

**GLM-5 Turbo:** Use CoT Non-Thinking Models. Repetition penalty hard cap at 1.05 — above 1.08 prose degrades. reasoning_effort field is ignored via OpenRouter.

---

## How to Use

**Minimum viable session:**
1. Enable 🔖 Writing Guide
2. Enable 📋 Model Configuration Guide (already on)
3. Enable one 💭 CoT prompt matching your model
4. Enable one 🔊 style module

**Adding tonal control:**
Enable one 🔊 Tonal Range preset alongside the style module. The style governs prose voice; the tonal preset governs emotional atmosphere. They operate on different axes and do not conflict.

**For explicit content:**
Enable ➕ Visceral Smut alongside any style module. For BDSM scenarios, also enable a 🔊 Sex Scene Tonal preset. The Visceral Smut addon and style modules are designed to complement rather than conflict.

**For antagonists:**
Enable one 🔊 Villain archetype and stack any combination of 🔊 Villain Modifiers.

**One 🔊 style module maximum per session.** Tonal Range, Sex Scene Tonal, and Villain archetypes each count as their own category — you can have one of each active simultaneously without conflict.

---

## Compatibility

Tested with: Gemma 4 31B Thinking, GLM-5 Turbo
Compatible with: Any OpenAI-format API via SillyTavern (Claude, GPT-4o, Mistral, etc.)
Format: SillyTavern OpenAI preset (.json)

---

## Credits
Style module library draws on the distinct prose registers of 50+ authors across literary fiction, genre, horror, sci-fi, comedy, romance, and more — each module includes a description and usage notes.
