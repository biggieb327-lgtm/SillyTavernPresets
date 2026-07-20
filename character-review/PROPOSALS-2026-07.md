# Character pass proposals — 2026-07

Run 2026-07-20 (manual demo run of `character-pass-monthly`, executed in-session at
the owner's request). Proposal-only: nothing below has been applied. Tags:
`[inbox card]` = file in character-review/, `[fleet card]` = live bot content,
`[web idea]` = external source (see Reddit note at bottom).

## Inbox: nora (1).json

1. **[inbox card] Byte-identical duplicate — propose deleting from the inbox.**
   `cmp` confirms it is byte-for-byte the fleet's live `telegram-companion-bot/nora.json`
   (and NOT the diverged SillyTavern-side `caa16137-nora.json`). Nothing to review;
   keeping it here risks a future session "syncing" the wrong copy somewhere.

## Inbox: SaskiaReyes.json

Strong writing — the Saperstein/Delvey anchor split and the behavior-clause "tab" are
a genuinely original engine, and the Margaret Pak dynamic gives every scene a third
rail. Proposals are about deployment fit, not quality.

2. **[inbox card] `data.name` is `"Saskia Reyes (Tech IPO Princess)"` — trim to
   `"Saskia Reyes"`.** The name field is injected as her literal name; the
   parenthetical belongs in `tags`/`creator_notes`, not in every prompt line.
3. **[inbox card] Frame decision needed before any fleet deploy: this is an
   in-person SillyTavern RP card, not a texting card.** first_mes and mes_example
   are built on asterisk narration, staging, and markdown bold — the exact devices
   the fleet's texting frame forbids (compare `priya.json`'s system_prompt /
   post_history_instructions, the house template). Fine as-is for SillyTavern
   proper; for a seventh bot she needs a texting-frame conversion pass.
4. **[inbox card] first_mes moves {{user}}** ("You let yourself in… You kiss me").
   Standard RP hygiene: rewrite those beats as Saskia reacting to what {{user}}
   might do, or leave the door open ("the key you've had for four months") without
   executing the action for them.
5. **[inbox card] Heaviest card in the repo (62KB vs 9–49KB fleet range).** The TOON
   canon block duplicates material the lorebook could carry keyword-gated. On a
   phone-context budget, propose moving the `tab:` category table and Margaret's
   full bio into lorebook entries and keeping description to identity + default
   state + friction engine. (Lorebook not fully audited this pass — flag, not spec.)

## Inbox: VivienneGrey.json

6. **[inbox card] spec v3 is fine for the bot — no conversion needed.** Verified
   `bot.py` accepts `chara_card_v2` and `chara_card_v3` (bot.py:7807, 7949). Only
   relevant if she's meant for the fleet; SillyTavern handles v3 natively.
7. **[inbox card] Same frame decision as Saskia, softer version.** Scenario is
   in-person/session-based, but her voice already texts well (the one-line
   first_mes "Tea is ready. I've already decided to let you stay…" is excellent and
   register-perfect). A texting conversion would be mostly scenario + mes_example
   work, not a voice rewrite.
8. **[inbox card] Fleet-differentiation note, owner judgment:** composed / dry /
   precise / observant sits near Jules's lane ("flat and precise, files everything
   and deploys it later"). Distinct engines (service-dominance + tested tenderness
   vs derby chirping), but in short text bursts the registers could converge.
   If both run, consider sharpening Vivienne's pet-name cadence and Jules's
   meanness-as-affection so the overlap never blurs.

## Inbox: main_michelle-scott-80f0d754b955_spec_v2.json (Michelle Scott)

9. **[inbox card] `data.personality` is empty — populate it.** One-line summary of
   the interior (approval-starved cringe-comedy boss, confidence over insecurity)
   pulled from the description's Personality & Interior section.
10. **[inbox card] Inconsistent "you" referent — normalize before use.** The
    description and first_mes use second person for *Michelle* ("You stand at
    5'6"… *You burst into the conference room*"), while the scenario uses "You"
    for *{{user}}* ("You arrive… for your first day"). Mixing referents for "you"
    across fields is a reliable way to make a model swap speaker mid-scene.
    Propose third person for Michelle everywhere, {{user}} for the user.
11. **[inbox card] Scenario is a one-shot cold open, not a continuity companion.**
    "First day at the office" burns out after one conversation. If she's meant for
    the ongoing-texting fleet, the scenario needs an ongoing-relationship rewrite
    (coworker/boss who texts after hours would preserve the whole comic engine).

## Fleet spot-check

12. **[fleet card] Bonnie: CLAUDE.md's recorded section order is the exact reverse
    of the card.** Card (`bonnie.json` description, byte order): Surface → Core →
    Energy States → OCEAN → Friction. CLAUDE.md + `edit-cards-and-presets`:
    "Friction → Core → OCEAN → Energy States → Surface." Git history shows the
    card was never reordered in-repo — the docs most likely recorded the order
    bottom-up at some point. Owner picks canon: if the card is right (likely),
    this is a two-line doc fix in CLAUDE.md + the skill; if the docs are right,
    reordering the card is a content change to schedule deliberately.
13. **[fleet card] Priya: residence is Belltown (Seattle) while everything else
    frames her as Bellevue.** "small Belltown apartment" appears in the
    description and again in the Nimbus lorebook entry; CLAUDE.md, the atlas
    header ("Priya's places — Bellevue, WA"), and her Eastside weekend defaults
    (Chainline in Kirkland, Old Bellevue slow Tuesdays) all say Eastside. The
    2026-07 Austin→Bellevue relocation (CHANGELOG) updated card + atlas but left
    the apartment line. Two clean options: (a) move the apartment to Bellevue
    (edit description + lorebook entry id 2 together — the facts live in both
    places); or (b) keep Belltown and add one clause acknowledging the cross-lake
    commute so the geography reads as chosen, not accidental. mes_example's "pay
    rent in seattle" follows whichever is picked. Otherwise the card is in
    excellent shape — best texting-frame template in the repo.
14. **[fleet card] Jules is the only character with no seed dir.** Five characters
    have `{people,projects,schedule,atlas}.txt`; Jules has none (only
    `jules_appearance.txt`). `sync-cards.sh` already maps `jules-bot:jules:` so
    seeds would deploy the moment `telegram-companion-bot/jules/` exists. Propose
    creating one: derby-league people (she'd have opinions on every one), a
    practice/bout schedule, and a Seattle atlas in her register. Without seeds she
    runs on card-only context while her whole engine is "files everything you say"
    — she'd be sharper with a world to file things against.

## External ideas

Reddit itself is **blocked from this cloud environment** (both old.reddit.com and
the JSON API refused the fetch) — the scheduled Routine will likely hit the same
wall and report this step SKIPPED. The search pass still surfaced applicable
guidance from non-Reddit sources, cited as `[web idea]`:

15. **[web idea] Example dialogues are the highest-leverage field** — 3–5 exchanges
    showing the voice beat any amount of description prose; models copy style and
    length from first_mes/mes_example more than from trait lists. Michelle Scott
    (no usable mes_example after the POV fix) and Saskia (examples are all
    staged-RP, none texting) are the two cards that would gain most.
    Source: https://blog.mini-tavern.com/blog/sillytavern-character-card-template-the-ultimate-guide-to-formatting-and-best-pr-eec44c
16. **[web idea] Keep lorebook entries standalone and concise** — activation keys
    and titles are never injected, so each entry must read as a complete fact on
    its own; move keyword-gateable canon out of description to reclaim context.
    Supports proposal 5 (Saskia's tab table → lorebook).
    Source: https://docs.sillytavern.app/usage/core-concepts/worldinfo/

---
*Out of scope for this pass but surfaced separately to the owner: update-all.sh and
sync-cards.sh treat nora's instance dir as `~/telegram-bot` while CLAUDE.md's table
says `~/nora-bot` — verify on-device which is real before the next card sync.*
