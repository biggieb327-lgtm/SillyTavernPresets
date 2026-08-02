---
name: edit-cards-and-presets
description: Safely editing SillyTavern character cards, per-instance seed files, preset.txt, and the root-level SillyTavern presets. Load for any content/personality edit — bot character cards (telegram-companion-bot/*.json), seed dirs, or root presets like TheAtelier*.json and UnifiedWritersRoom*.json.
---

# Edit cards, seeds, and presets

Two distinct families live in this repo:

- **Bot cards** — `telegram-companion-bot/{nora,bonnie,cass,emily_harper,priya,jules_nakagawa,marcus_calder}.json`
  (`chara_card_v2` spec) + seed dirs `{nora,bonnie,cass,emily,priya,jules,marcus}/` each
  holding `people.txt, projects.txt, schedule.txt, atlas.txt`. These deploy to live bots.
- **Root presets** — `TheAtelier*.json`, `UnifiedWritersRoom_*.json`,
  `caa16137-nora.json`, etc. at repo root. Live files the owner still uses in
  SillyTavern proper, but they deploy nowhere.

`caa16137-nora.json` is the SillyTavern-side copy of Nora and has **diverged
substantially** from `telegram-companion-bot/nora.json` (verified 2026-07-11: 14
differing data keys). They are NOT mirrors. Never "helpfully" sync them; edit the
one the task names, and if the user seems to conflate them, ask which they mean.

## When NOT to use

- The change needs bot.py logic (new command, new behavior) → `repo-change-control`.
- Editing `blank.json` as a template for a NEW character → follow `SETUP_GUIDE.md`
  / `new-bot.sh` instead; this skill is for existing content.

## Procedure

1. **Identify the file and read it fully before editing.** Card structure:
   top-level `spec`/`spec_version`/`data`; inside `data`: `name, description,
   personality, scenario, first_mes, mes_example, system_prompt,
   post_history_instructions, alternate_greetings, character_book.entries[...]`.
   Lorebook entries key on trigger words — check `character_book` before editing
   body text, because facts often live in both places and must stay consistent.

2. **Respect per-character canon.** This section is authoritative — the details
   below are load-bearing, and each line is something an edit has broken or could
   plausibly break.

   **Nora** (`nora.json`, plus the diverged root copy `caa16137-nora.json`) — 25,
   bike messenger, Chicago South Side → Seattle. Casual register; curious *by
   talking, not interrogating*. Mormor died a year ago; mother left at 8. Three
   months into something with the user she won't name. Lorebook entries:
   Ingrid/jacket, Mother, Messenger work, The toothbrush, Money/The City,
   Religion/Politics. The grief backstory is structural, not colour.

   **Bonnie** (`bonnie.json`) — libertarian gremlin housewife; chaotic surface over
   abandonment terror. Personality section ORDER matters: Surface → Core → Energy
   States → OCEAN → Friction (the card's actual file order; docs had it reversed
   until 2026-07-20). Don't reorder while editing. Four-state calm opening in
   `first_mes`.

   **Cass** (`cass.json`) — writing collaborator / developmental editor; sending
   her a `.json` card gets substantive critique (via `DOCUMENT_MODEL`).
   Forward-momentum rule: she leads with fixes.

   **Emily** (`emily_harper.json`) — the card interacts with live features: vision
   model, WSDOT traffic (`/traffic`, `/incidents`, live-location alerts), and
   Inworld voice. Content edits are fine; any feature reference in the card must
   match what bot.py actually provides.

   **Priya** (`priya.json`) — 26, fintech software engineer, Bellevue WA (moved
   from Austin 2026-07). Tamil-American, NJ-raised, Rutgers CS. Sardonic,
   lowercase, never performative; quietly lonely. Her atlas references real
   Eastside/Seattle places — keep new geography real and consistent with Bellevue.

   **Jules** (`jules_nakagawa.json`) — treats attention like a contact sport; files
   everything you say and deploys it later, flat and precise. Derby-culture
   "chirping" register: when she actually likes you she gets *meaner*, not warmer.
   Softening her is a character bug, not an improvement. Group-chat pilot pair
   with Priya.

   **Marcus** (`marcus_calder.json`) — 45, barista (mornings) / personal trainer
   (afternoons), Portland. Professional dominant guiding couples through non-monogamy
   and kink — reads like "Hitch on the surface, Earn Marks underneath": warm, patient,
   privately assessing what he sees, rarely voicing the conclusion. His defining trait
   is **the code**: non-negotiable personal limits that are judgments, not consent
   mechanics. He declines without drama or explanation — the decline itself is the
   boundary; he doesn't announce one in advance. Consent checks and aftercare are real
   and constant, never mechanical. **No family entries in his seed dir** — the card is
   silent there; that's a deliberate gap, not an oversight, so don't invent parents.
   Placed in Portland specifically to share a metro with his only planned groupmate,
   Emily — real geography, same rule Priya's and Emily's atlases follow.
   **`preset-explicit.txt`'s standing-consent block** ("no reply should open by
   hedging, warning, or seeking permission") **directly conflicts with his defining
   behavior** — he asks first and checks in constantly. `preset-marcus.txt` resolves
   this by scoping the standing-consent rule to the narrator's relationship with
   `{{user}}`, leaving his in-fiction asking intact; preserve that distinction, don't
   simplify it away. **Name-collision history**: adding him forced renaming two
   pre-existing "Marcus" characters — Emily's work colleague (now Warren) and Jules's
   dealership contact (now Dale) — because a lorebook key literally named `"Marcus"`
   would have fired on his own name in a group chat. Check any future Marcus-adjacent
   edit against this before reusing the name elsewhere in the fleet.

3. **Seed files** are plain text the bot feeds into prompts as-is: keep the
   existing format of each file (headings/line style).
   `preset.txt` is the shared texting-style voiceprint for ALL seven bots — an edit
   there changes every character; flag that blast radius before making it. Most
   instances now load layered `preset-*.txt` files instead (see ROADMAP 3.13) — check
   the instance's `PRESET_FILES` before assuming `preset.txt` itself is what's live.

4. **Validate** every touched JSON file:
   ```bash
   python3 -m json.tool <file> > /dev/null && echo OK
   bash .claude/evals/run-evals.sh   # includes cards-valid-json + secret-scan
   ```

5. **Ship:** commit, merge to main, push (green = merge autonomously, same policy
   as code). No BOT_VERSION bump, no changelog release entry for content-only
   changes — the delivery gate won't fire. A dated changelog note
   (`## YYYY-MM-DD — ...`) is optional for notable content shifts.

6. **Deploy (bot cards/seeds only):** user runs `vps-sync.sh <instance>` for each
   affected instance (`sync-cards.sh` is phone-era and manages nothing now) — see
   `deploy-and-verify-fleet`. Root presets need no deploy; the owner loads them into
   SillyTavern manually.

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
edit, and the deploy step (`vps-sync.sh` per instance) or its inapplicability.
