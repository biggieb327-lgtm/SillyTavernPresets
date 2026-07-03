---
name: rp-character-cards
description: Build and audit AI roleplay character cards (SillyTavern/chub.ai spec v2 JSON) using the Friction/OCEAN architecture. Use this skill whenever the user asks to create, rebuild, audit, fix, convert, or review a character card, lorebook, mes_example block, depth prompt, or post_history_instructions — or mentions chub.ai, SillyTavern, Tavo, spec v2, OCEAN splits, the Friction Principle, banned phrase scans, or card token budgets. Also use it when converting a character concept, reference image description, or existing fiction character into a card, even if the word "card" isn't used.
---

# Roleplay Character Cards

A methodology for building and auditing character cards targeting thinking-model backends (GLM 5.1 Thinking via NanoGPT is the default assumption). The card is model-facing engineering, not prose: every field either changes model behavior or is reader-facing metadata, and the two never mix.

## The two workflows

**Build**: concept → architecture → field drafting → lorebook → validation → banned phrase scan → full JSON delivery.

**Audit**: run `scripts/validate_card.py` first, then do the judgment-layer review the script can't do (Friction coherence, anchor placement, voice consistency, token disparity between paired cards). Report hard bugs separately from design suggestions.

Both workflows end the same way: the banned phrase scan is the mandatory final step before delivery, and delivery is always a complete JSON file, never patch notes for manual application. If a source file is needed and missing, ask for it immediately before doing anything else.

## Core architecture

### The Friction Principle

Every character needs an explicitly named gap between surface presentation and core psychology. This gap is the narrative engine — it's what generates behavior instead of description. Name it in the description body in plain terms: what the character shows, what's actually underneath, and what behavior the gap produces under pressure. A card without identified Friction is a costume, not a character.

### OCEAN surface/core split

Where it serves the character, split the Big Five into surface scores (how they present) and core scores (what's true), with the deltas doing the Friction work. Skip or replace this if the character description handles personality more effectively another way — optimize for model legibility and behavioral specificity, not ritual compliance with the format.

### Behavioral tells

Abstract traits don't survive generation. Every core psychological fact needs at least one concrete, repeatable physical or verbal tell the model can deploy (e.g., a broken halo the character keeps adjusting, chain-smoking that accelerates when lying). Tells are how interiority becomes renderable.

## Directive style: positive-only

Negative instructions are suboptimal for all models and actively harmful for thinking models — an explicit reasoning trace activates every concept it mentions, including the ones being suppressed. Naming a thing to ban it puts it in the trace.

Rewrite every negative instruction as the desired behavior. Use define-by-positive-substitution: "Z, distinct from X and Y" instead of "Not X. Not Y. Z." This applies to description, personality, mes_example narration, depth prompts, and lorebook content alike.

The validation script flags negative-directive patterns for review. Not every flag is a bug (dialogue can contain "never"), but every flag in a directive field needs a rewrite or a justification.

## Field placement map

Load-bearing model data and reader-facing metadata never share a field.

| Content | Location |
|---|---|
| OCEAN, Friction statement, tells, relationships, pop culture anchors | `description` body |
| Load-bearing behavioral anchor (see sparse attention rule) | LAST line of `post_history_instructions` |
| Depth prompts | `post_history_instructions` or character notes — never lorebook |
| World/character reference data | lorebook entries |
| Reader-facing summary: concept, Friction mechanic, content framework, intended play style | `creator_notes` — required on every build/rebuild, metadata only, zero model data |

### Sparse attention rule (thinking models)

The single most load-bearing behavioral anchor goes as the **last line** of the depth prompt / post_history_instructions, in short positive declarative form. Trailing position is what survives sparse attention; anything buried mid-block degrades in long sessions.

### Pop culture anchors

Original characters only — the model has no training data for them, so one late-position sentence in the description body gives it a gravitational reference. Negative framing preferred ("closer to X than Y"). Known IP characters get no anchors; layering references over existing training data creates tonal interference. Anchors never go in depth prompts.

## Lorebook

All 15 fields required on every entry or the chub.ai importer crashes. Read `references/lorebook-schema.md` before writing any lorebook entry — it has the field list, types, and defaults. The validation script enforces this mechanically.

Lorebook is for world and character reference data only. Behavioral directives that must fire every turn belong in post_history_instructions.

## Token budget and encoding

- Target ~2,500 permanent tokens on clean builds (~3,000 ceiling outside DS4). Permanent = description + personality + scenario + mes_example + post_history_instructions + constant lorebook entries.
- When card and preset divide labor (DS4 family): preset owns prose style, card carries lean character data only.
- ASCII-safe JSON always (`ensure_ascii=True` semantics): no smart quotes, em-dashes, or any non-ASCII in field values — they break the importer. The script checks this.
- Spec v2 JSON structure throughout.

## Preset-family constraints (DS4)

When the target preset is DS4 family, mes_example narration must be preset-compliant: em-dashes banned in narration (allowed in dialogue), ellipses banned globally, similes/metaphors/comparisons banned in narration (Camera Lens Rule). Female vocal acoustics: soft/warm/quiet/clear/bright/airy/gentle — never low/deep/husky/throaty/gravelly. Run the script with `--ds4` to check these.

## Audit workflow

1. Run `python scripts/validate_card.py <card.json>` (add `--ds4` if applicable). This catches: missing/mistyped lorebook fields, non-ASCII characters, banned phrases, negative-directive patterns, missing creator_notes, and gives a permanent-token estimate.
2. Judgment layer, in order:
   - **Friction coherence**: is the gap named, and do the tells actually express it?
   - **Field placement**: any model data in creator_notes? Any depth prompt content in lorebook? Anchor in wrong position?
   - **Voice consistency**: does mes_example voice match description claims? For paired/companion cards, check token disparity and format parity between them.
   - **Sparse attention**: is the last line of post_history_instructions the load-bearing anchor, short and positive?
   - **Long-session drift risk**: sufficient vocabulary density and format anchors for turn-250+ stability?
3. Report format: **Hard bugs** (breaks importer or model behavior) first, then **design issues** (works but suboptimal), then **suggestions**. Fix hard bugs without asking; argue design changes explicitly — what the problem is, why it matters, what the alternative would be.

## Delivery rules

- Complete JSON file, always. Integration is the builder's job, not the user's.
- Banned phrase scan (`references/banned-phrases.md`, also enforced by script) is the mandatory final gate.
- Deliver via file, named with version suffix (`charactername_v2.json` pattern).
- If any source file referenced in the task is missing, stop and ask for it before proceeding.

## References

- `references/lorebook-schema.md` — the 15 required fields, types, defaults. Read before any lorebook work.
- `references/banned-phrases.md` — the full banned list with substitution guidance. Read before the final scan on any build.
- `scripts/validate_card.py` — mechanical validation. Run on every build output and at the start of every audit.
