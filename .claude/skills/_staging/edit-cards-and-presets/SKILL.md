---
name: edit-cards-and-presets
description: Safely editing SillyTavern character cards, per-instance seed files, preset.txt, and the root-level SillyTavern presets. Load for any content/personality edit — bot character cards (telegram-companion-bot/*.json), seed dirs, or root presets like TheAtelier*.json and UnifiedWritersRoom*.json.
---

# Edit cards, seeds, and presets

Two distinct families live in this repo:

- **Bot cards** — `telegram-companion-bot/{nora,bonnie,cass,emily_harper,priya,jules_nakagawa}.json`
  (`chara_card_v2` spec) + seed dirs `{nora,bonnie,cass,emily,priya}/` each holding
  `people.txt, projects.txt, schedule.txt, atlas.txt`. These deploy to live bots.
- **Root presets** — `TheAtelier*.json`, `UnifiedWritersRoom_*.json`,
  `caa16137-nora.json`, etc. at repo root. Live files the owner still uses in
  SillyTavern proper, but they deploy nowhere.

`caa16137-nora.json` is the SillyTavern-side copy of Nora and has **diverged
substantially** from `telegram-companion-bot/nora.json` (verified 2026-07-11: 14
differing data keys). They are NOT mirrors. Never "helpfully" sync them; edit the
one the task names, and if the user seems to conflate them, ask which they mean.

## When NOT to use

- The change needs bot.py logic (new command, new behavior) → `ship-bot-release`.
- Editing `blank.json` as a template for a NEW character → follow `SETUP_GUIDE.md`
  / `new-bot.sh` instead; this skill is for existing content.

## Procedure

1. **Identify the file and read it fully before editing.** Card structure:
   top-level `spec`/`spec_version`/`data`; inside `data`: `name, description,
   personality, scenario, first_mes, mes_example, system_prompt,
   post_history_instructions, alternate_greetings, character_book.entries[...]`.
   Lorebook entries key on trigger words — check `character_book` before editing
   body text, because facts often live in both places and must stay consistent.

2. **Respect per-character canon** (CLAUDE.md §Character notes is authoritative;
   highlights that are easy to violate):
   - *Nora*: casual register; grief backstory (Mormor, mother) is load-bearing.
   - *Bonnie*: personality section ORDER matters — Friction → Core → OCEAN →
     Energy States → Surface. Don't reorder while editing.
   - *Priya*: lowercase, sardonic, never performative; her atlas references real
     Bellevue/Eastside places — keep new geography real and consistent.
   - *Jules*: gets meaner when she likes you, not warmer. Softening her is a
     character bug, not an improvement.
   - *Emily*: card interacts with vision/traffic/voice features — content edits
     fine; feature references in the card must match what bot.py provides.

3. **Seed files** are plain text the bot feeds into prompts as-is: keep the
   existing format of each file (headings/line style).
   `preset.txt` is the shared texting-style voiceprint for ALL six bots — an edit
   there changes every character; flag that blast radius before making it.

4. **Validate** every touched JSON file:
   ```bash
   python3 -m json.tool <file> > /dev/null && echo OK
   bash .claude/evals/run-evals.sh   # includes cards-valid-json + secret-scan
   ```

5. **Ship:** commit, merge to main, push (green = merge autonomously, same policy
   as code). No BOT_VERSION bump, no changelog release entry for content-only
   changes — the delivery gate won't fire. A dated changelog note
   (`## YYYY-MM-DD — ...`) is optional for notable content shifts.

6. **Deploy (bot cards/seeds only):** user runs `sync-cards.sh` (dry-run first)
   then `/restart` affected bots — see `deploy-and-verify-fleet` path C. Root
   presets need no deploy; the owner loads them into SillyTavern manually.

## Quality bar

- Valid JSON, spec structure untouched (edit values, don't restructure keys).
- Voice consistent with the character's register through the whole edit — a card
  is a prompt; one off-register paragraph leaks into every future reply.
- Lorebook and description don't contradict each other after the edit.
- No real-world secrets or personal data introduced (repo is public via raw URLs).

## Verification checklist

- [ ] `python3 -m json.tool` passes on every touched JSON file
- [ ] `run-evals.sh` green (cards-valid-json, secret-scan)
- [ ] Cross-references checked: lorebook vs description vs seed files
- [ ] The right copy edited (bot card vs root SillyTavern copy)
- [ ] Deploy step communicated (or explicitly n/a for root presets)

## Common mistakes

- Editing `nora.json` when the user meant `caa16137-nora.json` or vice versa.
- Breaking JSON with a stray quote in prose — always validate, never eyeball.
- "Improving" a character out of their designed register (Jules warmer, Priya
  capitalized, Bonnie reordered).
- Editing `preset.txt` for one character's issue — it's fleet-wide.
- Inventing fake Seattle-area geography for Priya/Emily instead of checking the
  atlas files for the places already established.

## What to report back

Which files changed and why, validation output, canon constraints that shaped the
edit, and the deploy step (sync-cards + restart) or its inapplicability.
