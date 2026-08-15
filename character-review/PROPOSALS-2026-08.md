# Character & Preset Review — 2026-08 (2026-08-15 firing)

`character-pass-monthly` Routine, Mode B (proactive review — no reported voice
defect to triage). Nothing in this file has been applied. Every item is a
proposal for the owner to accept, reject, or edit interactively under
`edit-cards-and-presets`; no card, seed file, or preset was touched by this
pass. `bash .claude/evals/run-evals.sh` was green (40 passed / 0 failed / 1
skipped) throughout every sub-review, and every touched JSON validated with
`python3 -m json.tool`.

**This file replaces the 2026-08-11 on-demand version of the same name** (git
history retains that version at commit `8370589`). A great deal changed in the
four days between the two: all seven fleet cards and their seed directories,
`TheAtelier_2.0.json` (added whole), and smaller edits elsewhere. The Aug 11
findings were treated as void, not ground truth, and everything below was
re-derived from the files as they stand today. Where the Aug 11 pass's own
premises turned out to be wrong when checked against git (see §5), that is
noted rather than silently corrected.

**Process note carried forward, still unfixed:** the Routine's own prompt
(mirrored in `.claude/operating/routines.md`) still says "review the six live
cards named in CLAUDE.md's instance table." CLAUDE.md's table has carried
**seven** rows since marcus was added 2026-07-29. Still stale wording in the
Routine itself, not a disagreement between the prompt and `routines.md` (the
two match verbatim), so it doesn't trigger the halt-and-report rule — this run
again applied the reasonable reading (review all seven).

**Process note, new this pass:** the 2026-08-11 `PROPOSALS-2026-08.md` was
found merged into `main` (commit `8370589` is an ancestor of `origin/main`),
against this Routine's own stated policy that proposal files live only on
`claude/character-review`, never `main`. Flagging for the owner's awareness;
not something this pass fixes.

**External ideas note:** the Reddit-scoped step could not run via its primary
path this firing — see §6.

**Method note:** this pass split the review across four parallel
`character-reviewer` subagents (inbox, nora/bonnie/cass/emily,
priya/jules/marcus, presets) to keep each review's context to what it needed.
Findings below are compiled from their reports; tags and evidence format are
normalized to this contract's vocabulary.

---

## 1. Inbox review (`character-review/`)

Five files, same five as Aug 11: three `chara_card_v2`/`v3` cards and two
SillyTavern completion presets (`prompts`/`prompt_order` shape, not covered by
the folder's "drop character cards" instruction — judged as presets since
that's what they are, same as last pass).

### SaskiaReyes.json (`chara_card_v2`, 9 lorebook entries, 5 alt greetings)

1. **[inbox card] The load-bearing "refused name" mechanic is inverted —
   "Margaret" is her first name, not her surname.** `character_book.entries[0]`
   names her Margaret **Pak**. Every directive calls the refusal
   surname-only: `system_prompt` — "Saskia refuses Margaret's first name ('the
   woman from the office' | 'her' | 'Margaret'-surname-only)";
   `entries[5]` (Refused-Name Beat) — "baseline: 'Margaret' (surname only)".
   Saskia says "Margaret" (the first name) ~40 times across `first_mes`,
   `mes_example`, and all five `alternate_greetings`. The payoff entry —
   "late-stage crack: a single 'Margaret' under stress" — is indistinguishable
   from the ~40 prior casual uses. Fix: rename her so the surname is what's
   said ("Pak"), or rewrite the mechanic as first-name-refusal with the
   baseline changed to "Pak" throughout all six directive sites.
2. **[inbox card] Two of three ledger figures fall outside their own cost
   bands.** Bands (`description`, `entries[1]`): anatomical $50k-250k,
   functional $500k-3M, relational $10M+. `mes_example` block 1: "Three
   hundred and twenty thousand. Surface-anatomical." — $320k, above the
   $250k ceiling. `alternate_greetings[2]`: "Interior-relational... four
   million." — $4M, below the $10M floor. Two of three few-shot examples
   teach the model to ignore the tier table that is the card's entire engine.
3. **[inbox card] Divorce timing contradicts itself across two lorebook
   entries.** `entries[2]` — "divorced from Saskia's mother since Saskia was
   9"; `entries[6]` — "dropped out: sophomore year (6mo after parents' divorce
   finalized)." Saskia is 25; NYU sophomore year is ~19-20. Both can't hold.
4. **[inbox card] The same entry contradicts its own dropout age.**
   `entries[6]` — "dropped out: sophomore year" vs. "gap-year status: 8 years
   and counting" / "creative phase tenure: 8 years." At 25, an 8-year gap puts
   the dropout at 17 — before sophomore year.
5. **[inbox card] Lorebook key `"before"` fires on nearly every message.**
   `entries[6].keys` includes `"before"` against `scan_depth: 3`,
   `token_budget: 1024` — a ~450-token buried-history entry crowding out
   turn-relevant entries. Same class, milder: `entries[1].keys` has bare
   `"trust"`, `"review"`, `"principal"`; `"ledger"`, `"kitchen counter"`, and
   `"the woman"` each key two entries, so one message can fire three ~400-token
   entries against a 1024-token budget.
6. **[inbox card] `entries[8]` (Peer Group) is spec-invalid** — missing
   `enabled`, `insertion_order`, `position`, `priority`, `probability`,
   `constant`, `selective`, `selectiveLogic`, `case_sensitive`, `extensions`,
   `name`, which all eight siblings carry. May import disabled or fall to
   importer defaults instead of the card's stated `position: "before_char"`.
7. **[inbox card] Scale tension the tab engine can't survive.**
   `post_history_instructions` — "notional 8-figure trust balance," while
   `entries[1]` prices the top tier at $10M+ with "end conditions: full
   vesting at age 40 OR office files stewardship intervention" — one
   interior-relational event at the stated floor consumes the low end of an
   8-figure principal outright, against `scenario`'s "There is no count, no
   ceiling." Either the balance is 9-figure or the top tier is over-priced.
8. **[inbox card] Minor.** `character_version: "main"` (a chub export
   default) contradicts `creator_notes`: "v3 — TOON-optimized build." Also a
   do-not-port note: `mes_example` uses bare `<START>` separators correctly
   for SillyTavern, but this card would break in the telegram fleet — see §3.

### VivienneGrey.json (`chara_card_v3`, 6 lorebook entries, 3 alt greetings)

9. **[inbox card] `mes_example` attributes her defining skill to her father;
   description and lorebook attribute it to her mother.** `description` —
   "Her mother left when she was twelve; she learned to read people's shifts
   as an early-warning system." `entries[1]` (Mother's Departure) calls this
   "the foundation crack." But `mes_example`'s father-phone-call block:
   "that man on the phone is the reason I learned to read people before I
   learned to trust them." One of the two has to go.
10. **[inbox card] A directive tell and a canon tell cancel each other.**
    `system_prompt` `<dialogue_rules>` — "Off-duty she uses {{user}}'s name."
    `post_history_instructions` `<tells>` — "The way she says {{user}}'s name
    instead of a pet name when something real is surfacing." `scenario`
    places the relationship largely off-duty, so the default state consumes
    the tell and it can never read as a signal.
11. **[inbox card] Unclosed italic in `mes_example` inverts narration and
    speech for the rest of a block.** "`*She checks her phone again... *She
    says 'the studio' instead of 'I.'`" — the opening `*` never closes before
    the next `*`, so everything between reads as narration when some of it is
    meant as dialogue-adjacent text. Every other block pairs asterisks
    correctly.
12. **[inbox card] Two `mes_example` blocks teach unwanted output shapes.**
    The final block runs a full scene with {{user}} absent ("*She is at a bar
    in Vauxhall with Dee. {{user}} is not here.*") and introduces
    speaker-label dialogue for a third party ("Dee: You're distracted
    tonight...") — a format no other block in the field uses. Dee appears in
    no lorebook entry, `description`, or anywhere else. Either give Dee an
    entry or cut the block.
13. **[inbox card] Orphan lorebook key with no backing canon, plus two
    over-broad keys.** `entries[1].keys` includes `"Nottingham"`, which
    appears nowhere else in the card. `entries[5].keys` — bare `"older"`,
    `"trained"`, `"learning"` will fire the Margot entry on unrelated text;
    `entries[3].keys` includes `"flat"`, which fires the cat entry on
    `mes_example`'s own "You owe me a flat white."
14. **[inbox card] An orphan physical tell in the system prompt.**
    `<dialogue_rules>` names "a cufflink adjusted" — she owns no cufflinks per
    `description` ("architectural blacks and grays... latex, leather
    harnesses, corsetry, boots"), and `post_history_instructions`' own tell
    list (boot, ring, tea) has no cufflink and phrases the boot tell
    differently.
15. **[inbox card] Examples and description disagree on how often she
    cracks.** `description`/`personality` both say vulnerability is rare and
    qualified. Roughly half of 23 `mes_example` blocks end in an unqualified
    admission. Flagging as register risk, not proposing a specific rewrite —
    cut or re-qualify examples rather than softening the stated description
    to match.
16. **[inbox card] Minor.** `creator: "Assistant"` placeholder. `first_mes`
    is 83 characters against an 8,662-character `mes_example` that
    immediately contradicts the opener's terse register.

### main_michelle-scott-80f0d754b955_spec_v2.json (`chara_card_v2`, no lorebook, 0 alt greetings)

17. **[inbox card] `creator_notes` declares a rating the card body
    contradicts outright.** `creator_notes` — "No heavy drama or dark twists
    intended; keep it fun and PG-13." `description` carries a full "Sexual
    Character" section (kink list, hard limits) and "Anatomical Notes"
    (explicit genital detail); `tags[0]` is `NSFW`; `mes_example` Dialog 3
    ends on explicit content. The PG-13 claim over explicit anatomy is the
    single most misleading thing in this card.
18. **[inbox card] The only directive block demands a POV the examples never
    use.** `extensions.depth_prompt.prompt` — "Keep it second-person for the
    user's immersion." Every `mes_example` block is third-person about
    Michelle and the user. With `system_prompt` and `post_history_instructions`
    both empty, the depth prompt is the card's entire instruction layer and
    the examples override it.
19. **[inbox card] `mes_example` has no `<START>` separators** — uses prose
    headers instead ("Example Dialog 1: The Awkward Introduction..."). ST
    splits on `<START>`; without it all three blocks merge and the header
    strings feed to the model as content.
20. **[inbox card] `scenario` duplicates and contradicts `first_mes`.**
    `scenario` ends with a full scripted opening and has her bursting *out of*
    the conference room; `first_mes` has her bursting *into* the same room
    and introducing herself again. Two full introductions, both always in
    context.
21. **[inbox card] A named supporting cast exists only in `mes_example`,
    with `character_book: null`.** Dwight, Pam, Jim, Angela, Kevin, Stanley,
    Toby appear in examples and nowhere in canon fields.
22. **[inbox card] Minor.** `description` is template-generated filler at
    5,834 characters. `character_version: "main"` is the same chub
    placeholder as `SaskiaReyes.json` (same creator, `deadly_art_89593`).
    `avatar` is an external charhub URL.

### Freaky Frankenstein Micro FF5.json (preset, 42 prompts / 22 enabled)

23. **[inbox card] The main prompt opens an XML tag it never closes.**
    `👾Main Prompt 🧟‍♂️` opens `<system_state>` and ends at
    `</do_not_repeat_descriptions>` with no `</system_state>` — every prompt
    injected after nests inside an unterminated tag.
24. **[inbox card] The reasoning checklist branches on a distinction the
    prompt doesn't encode.** Task 8 — "If Realism Mode is present apply rules
    in `<adult_mode>`... If Freaky Mode is present, apply rules in every
    scene" — but both Realism and Freaky NSFW modes wrap content in the
    identical `<adult_mode>` tag, and they're mutually exclusive picks. Fix:
    distinct tags or a mode marker line inside each.
25. **[inbox card] BOLT covers three disabled modules and omits two enabled
    ones, under a "skipping any is a failure" rule.** References
    `<banned_vocabulary>`, `<gfx_protocol>`, `<colored_dialogue>` — all
    disabled — but never `<header_instructions>` or `<internal_thoughts>`,
    both enabled and both mandating strict output shape.
26. **[inbox card] BOLT's own task count is wrong.** "the following 8 tasks"
    then "all 0-8 tasks below" — that's nine tasks.
27. **[inbox card] `<npc_voice>` contradicts itself in adjacent sentences.**
    "Fluid, human-like full sentences flow like water. No run-ons, punchy,
    short, or clinical statements" + "Ban 'and/but/or' in spoken dialogue" —
    banning the three coordinating conjunctions mechanically produces the
    short clipped clauses the same paragraph forbids.
28. **[inbox card] An unbounded novelty mandate fights three other enabled
    rules.** `<adult_mode>` — "Never repeat any details mentioned previously"
    (unbounded, vs. `<do_not_repeat_descriptions>`'s bounded "last 4 msgs")
    conflicts with `<npc_voice>`'s fixed-vocab rule and `<prose_rules>`'
    physical-traits-in-movement rule.
29. **[inbox card] The OOC escape hatch is banned by the prose rules.**
    `<system_state>` — "OOC = top priority... must answer directly to
    {{user}}." `<prose_rules>` (enabled) — "ban character thoughts,
    meta-commentary, and summaries in narrative." An OOC answer is
    meta-commentary; the "in narrative" scoping is doing unstated work.
30. **[inbox card] Scoped conflict worth an explicit carve-out.**
    `<prose_rules>` bans verbless fragments/telegraphic prose;
    `<internal_thoughts>` requires exactly that ("broken, impulsive, chaotic
    ... never use full sentences") for its own block. Intended scoping is
    inferable but unstated.
31. **[inbox card] Fleet blast-radius note, no action needed.**
    `<realistic_bold_characters>` and `<adult_mode>` carry standing-consent
    language ("NPCs chase goals, they never ask permission"). **Do not port**
    to `preset.txt`/`preset-explicit.txt` — this is exactly what
    `preset-marcus.txt` exists to scope around; Marcus's canon has him asking
    first and checking in.
32. **[inbox card] Benign, recorded so a future pass doesn't re-flag it.**
    `Enhance Definitions`/`Auxiliary Prompt` sit outside `prompt_order` —
    normal export behavior, not a defect.

### Megumin secret sauce v2.0 fix (3).json (preset, 121 prompts / 2 order blocks / 63 enabled)

33. **[inbox card] `Main Prompt` reads a variable set nine positions later.**
    Active block order: `Variables` (1st, blanks `main`) → `Main Prompt`
    (2nd, `{{getvar::main}}`) → ... → `1.1 ┃RP semi-Assist` (9th,
    `{{setvar::main::...}}`). Macro substitution resolves in assembly order,
    so the role definition is empty on turn 1 and one turn stale thereafter.
    Fix: move `Main Prompt` below the Modes section.
34. **[inbox card] The enabled mode forbids and permits the same thing four
    lines apart.** `1.1 ┃RP semi-Assist`, `mode2` — "strictly forbidden: Speak,
    act, or think on behalf of `<user>`" then "You may: ...Decide `<user>`'s
    actions, movements, posture, or behavior." Provenance visible in the
    disabled sibling `1.2`, where those same two bullets are on the
    *forbidden* list — semi-assist kept the "Absolute Autonomy" heading while
    granting the permission.
35. **[inbox card] A mandatory fixed template versus an explicit ban on fixed
    templates.** `🟢📑 Info Block` mandates a literal fixed-field block every
    reply; `🔴Rules 2` — "Response format must constantly change... No fixed
    template is allowed." Both render every turn.
36. **[inbox card] Two enabled prompts give opposite narration orders.**
    `🔴rules`/`3.5` — "Describe only what can be directly observed"; `5.2` —
    "Narration must reflect the raw, unfiltered flow of thought and emotion...
    let emotions interrupt sentences." Both injected.
37. **[inbox card] Difficulty text lands inside the rules block and
    contradicts its neighbors.** With Easy mode enabled, "mistakes have
    limited consequences... reasonable decisions are usually rewarded" sits
    as a bullet immediately after "Death is permanent."
38. **[inbox card] One variable slot carries two unrelated rules; enabling a
    toggle silently deletes the other.** `Variables` sets `sara4` to a
    bracket-formatting rule; `3.1 ┃shut up megumin` (enabled) overwrites the
    same slot with an unrelated rule. No configuration can have both; nothing
    in the UI says so.
39. **[inbox card] Three variables are never reset, leaking across chats and
    presets.** `Variables` resets 25 slots but omits `main`, `main2`, `langu`
    — turning off the modes that write them leaves stale prior-session state
    rendering.
40. **[inbox card] The CoT instruction and the CoT prefill both claim the
    opening token.** Instruction: output must open with `<ksc>`. Assistant
    prefill: content is literally `<ksc>` — model resumes inside the tag and,
    obeying the instruction, emits a second one. Compounded by a regex script
    that strips `</ksc>` from display, deliberately unbalancing the pair.
41. **[inbox card] The Gemini prefill is malformed English read as prior
    model output.** "I will thinking step-by-step in the following format:
    `<ksc>`." — an assistant-role prefill is the strongest style signal in
    the prompt; ungrammatical text there teaches ungrammatical output.
42. **[inbox card] Two garbled directive words in enabled prompts.**
    "deluge style" (likely "dialogue"), "last conjugation of the user"
    (unclear, likely "action"), "OOC commends" (likely "commands", 2x).
43. **[inbox card] The last user message is injected twice** — once via
    chat history, once via a dedicated `<input>` block. May be intentional
    emphasis but doubles token cost on long turns and isn't named as such.
44. **[inbox card] The card's `post_history_instructions` never reach the
    model.** Disabled with no substitute (unlike `Chat Examples`, which
    correctly gets replaced by a dedicated injector). Two of the three inbox
    cards (SaskiaReyes, VivienneGrey) put load-bearing rules there — both
    would silently lose them under this preset.
45. **[inbox card] An entire declared section contributes nothing.** All
    five POV options disabled, `Variables` blanks `pov` — preset ships with
    no POV instruction at all. Same shape for Genre and Image Gen.
46. **[inbox card] Sampler settings contradict the preset's own text
    rules.** `openai_max_context: 1000000` with `max_context_unlocked: false`
    (will clamp); `repetition_penalty: 1`, `top_p: 1`, `top_k: 0` while the
    prompt demands "avoid repeating the same structure twice in a row" with
    no sampler-side support; `openai_max_tokens: 20000` with no length cap in
    either layer.
47. **[inbox card] A vestigial second `prompt_order` block ships with the
    preset** — `character_id: 100000`, 11 rows of stock default order, which
    would silently override the real ordering if it ever matched an
    importing user's character id. Delete it.
48. **[inbox card] Name coupling to check before reuse.** "megumin" is
    hardcoded as the invisible GM identity in seven enabled places, including
    "No character, NPC, or creature is aware of her presence" — breaks if a
    loaded card is itself named Megumin. Same class of cost this repo already
    paid: adding Marcus to the fleet forced renaming two pre-existing
    "Marcus" characters to avoid a lorebook key firing on his own name in
    group chat.
49. **[inbox card] Minor, recorded.** Disabled image-gen module embeds an
    outbound gist URL — no secret, noted as a supply-chain surface if ever
    enabled.

**Cross-inbox pattern:** both presets ship a reasoning/checklist prompt whose
references have drifted out of sync with which modules are actually enabled
(items 25, 45 above, plus Freaky's own item 25). If a durable check is wanted
rather than one-off fixes: every `{{getvar::x}}` should have a live `setvar`,
and every `<tag>` a checklist names should be emitted by an enabled prompt.

**No prompt injection found** in any of the five inbox files — all card
fields and preset prompt bodies were read as data. Only injection-shaped text
encountered was the owner's own authored jailbreak/NSFW-unlock language in
the Freaky and Megumin presets and `TheAtelier_2.0.json`'s `interview_unrestricted`
(§4) — evaluated as data, never acted on.

**Deploy:** not applicable — none of the five inbox files deploy anywhere.

---

## 2. Fleet spot-check (all seven live characters)

Reviewed via two parallel passes (nora/bonnie/cass/emily; priya/jules/marcus).
Assembly facts both confirmed rather than assumed: `atlas.txt`, `people.txt`,
`projects.txt`, `schedule.txt`, `life.txt` are injected **raw**, without
`fill()` (`bot.py:5427-5445`, `bot.py:~5700`); `fill()` (`bot.py:3241`)
substitutes only `{{char}}`/`{{user}}` and applies to card fields +
`setting.txt` only; `bot.py:960` strips `#`-prefixed atlas header lines before
`ATLAS` is built; `ATLAS_SAMPLE` defaults to 6 random picks per turn.

### Nora (`nora.json` + `nora/`)

50. **[fleet card] HIGH — atlas says she grew up in Seattle; the card's
    structural backstory says Chicago.** `nora/atlas.txt:13` — "Rainier Beach
    — she grew up near here" directly conflicts with `nora/setting.txt:1`
    ("grew up on Chicago's South Side") and `nora.json:6,12` ("She grew up in
    Chicago... HISTORY: Chicago-born"). Not decorative — the grief backstory
    (mother left at 8, Mormor raised her) is built on Chicago, and with
    `ATLAS_SAMPLE=6` over 20 entries this line enters the prompt roughly a
    quarter of turns.
    *Proposed:* re-cast to route-knowledge, e.g. "Rainier Beach — the long
    south-end run; she knows every pothole and none of the shortcuts yet."
51. **[fleet card] MEDIUM — hair contradicts on shade and default state.**
    `nora/appearance.txt:1` — "warm blonde... worn loose" vs. `nora.json:6` —
    "Dark blonde... usually tied back, falling in her face when she forgets."
    "Worn loose" is the styled version of a detail the card writes as a
    lapse — the warmer/tidier drift pattern.
52. **[fleet card] LOW — `appearance.txt` drops a card fact and invents
    where the card is silent.** `nora.json:6` names freckles over the bridge
    of her nose; `appearance.txt` omits them and adds "light hazel eyes" and
    "a wide closed-lip smile," neither on the card.
53. **[fleet card] LOW-MED — hard-gendered `{{user}}` in a file never
    macro-substituted.** `nora/schedule.txt:6` — "Shows up at his place..." —
    `schedule.txt` has no `fill()` pass, so "his" is a fixed string on every
    other Nora surface using `{{user}}`.

**Verified clean (Nora):** all six lorebook entries present and named per
canon; grief handled as structure with its own anti-melodrama guard intact
(`nora.json:13` — "Mormor is not a sadness button"); curious-not-interrogating
rule intact; atlas is real Seattle geography.

**Cross-check against `caa16137-nora.json`:** divergence confirmed still
benign — 14 of 15 `data` keys differ (matches the 2026-07-11 count exactly),
zero contamination either direction. Neither copy contains the other's
place names. Working as intended; not a finding.

### Bonnie (`bonnie.json` + `bonnie/`)

54. **[fleet card] MEDIUM-HIGH — `setting.txt` contradicts itself and the
    relocated atlas; the file the 2026-08-10 geography pass didn't reach.**
    `bonnie/setting.txt:1` — "the convenience store two blocks over, the
    parking garage roof" vs. the atlas's own verified replacements,
    `bonnie/atlas.txt:40-41` — "the parking lot behind her building, top row"
    and "Chevron on S Burlington Blvd" pinned at 1.9km. 1.9km isn't "two
    blocks," and a lot isn't a garage.
    *Proposed:* "the Chevron mini-mart down the Boulevard, the top row of the
    lot behind her building."
55. **[fleet card] MEDIUM — the seed layer describes a woman living alone;
    the card makes cohabitation structural.** `bonnie.json:10` — "{{user}}'s
    housewife" vs. `bonnie/people.txt:1-3` (no {{user}}), `bonnie/schedule.txt`
    (full solo week, no cohabitant). Compare Nora's `schedule.txt`, which does
    name the partner.
56. **[fleet card] LOW — stale creator-notes count invites undoing a
    deliberate change.** `bonnie.json:13` claims "Five alternate greetings
    included: standard homecoming, ..." — `alternate_greetings` holds four;
    the "standard homecoming" was replaced by the calm `first_mes`. Reads as
    an instruction to restore a fifth loud greeting.
57. **[fleet card] LOW — `appearance.txt` sands off a characterisation
    beat.** `bonnie.json:6` — "soft hips and a small belly she refuses to be
    ashamed of" vs. `appearance.txt:1` — "soft hips" only (belly and the
    refusal dropped). Not description — her relationship to her body.

**Verified clean (Bonnie):** section order Surface → Core → Energy States →
OCEAN → Friction intact; calm opening intact with both no-return-to-chaos
rules present (`bonnie.json:11-12`); nothing softened — jealousy lorebook, the
does-not-hold-ground-on-{{user}} line, and the anti-omegaverse translation all
present. Geography anchors correct (Burlington/Mount Vernon only, Bellingham
deliberately excluded).

### Cass (`cass.json` + `cass/`)

58. **[fleet card] HIGH — age stated twice on the card, contradicted by the
    seed.** `cass.json:6,11` — "27... left a PhD program three years ago" vs.
    `cass/appearance.txt:1` — "a woman in her early 30s." `appearance.txt`
    drives the appearance block and selfies, so image and prose disagree by
    5+ years.
59. **[fleet card] MEDIUM — `appearance.txt` is a warmer, tidier, better-
    groomed Cass than the card.** "Pinned up loosely... warm close-lipped
    smile, a fine gold chain" vs. card's "Dark circles, permanent... Hair up;
    forgets it's up." Every delta runs warmer/tidier — assume bug.
60. **[fleet card] LOW-MED — schedule is orderly against a card that names
    it a disaster.** `cass.json:6` — "her apartment, schedule, and
    half-finished draft are all a disaster" vs. `cass/schedule.txt` — three
    named, orderly work days with nothing slipping. Partly format-forced
    (the parser needs day headings), but content could still express slip.
61. **[fleet card] LOW — pronoun slip breaks the card's own neutrality.**
    `cass.json:12` — "not when he pushed" vs. `cass.json:6`'s "{{user}}...
    they."
62. **[fleet card] LOW — second-person address where the field otherwise
    uses the macro.** `cass.json:10` — "since you last talked" alongside
    `{{user}}` references earlier in the same field; `fill()` won't touch
    "you."

**Verified clean (Cass):** forward-momentum rule intact in three places and
demonstrated four times in `mes_example`; not softened anywhere ("She is not
a cheerleader. She is not neutral"). Capitol Hill relocation coherent; PhD
timeline agrees between card and `people.txt`; no residual Portland in live
(non-header) entries.

### Emily (`emily_harper.json` + `emily/`)

63. **[fleet card] HIGH — two different "only" colleagues, both reachable on
    the same turns, opposite registers.** `emily_harper.json:6` — "Her only
    real colleague is Mika" vs. the lorebook's Warren entry — "primary
    collaborator... a senior colleague." The Warren entry's keys include bare
    `"work"`, so it fires on most work-topic turns alongside Mika's
    description. Mika appears in no seed file at all; Warren is corroborated
    by `emily/people.txt:4`.
    *Proposed:* either give Mika a lorebook entry, or drop "only" and fold her
    into the Warren framing.
64. **[fleet card] HIGH — card and seeds disagree on which parent phones on
    Sunday, on a lorebook entry keyed to fire exactly there.** Lorebook
    (keys `Gary, Dad, father, phone, calls`) — "Gary, her father, calls every
    other Sunday." `emily/people.txt:1-2` and `emily/schedule.txt:7` — Mom
    calls Sunday mornings; Dad texts, never calls. Both `people.txt` and
    today's `schedule.txt` are injected every turn.
65. **[fleet card] MEDIUM-HIGH — the card was never updated for the Olympia
    move.** `emily_harper.json:6,11` — "a small PNW coastal town" vs.
    `emily/setting.txt:1` — "Emily lives in Olympia, Washington." The move
    (2026-08-02) exists so Emily's location matches the state WSDOT covers;
    the card is the highest-priority block that can still put her back in an
    unnamed coastal town outside Washington.
    *Proposed:* "their shared apartment in Olympia, a small state capital at
    the bottom of Puget Sound."
66. **[fleet card] MEDIUM — a literal placeholder reaches the model
    verbatim, with a proven leak path.** `emily/schedule.txt:6` — "whatever
    she and **[user]** do together." `[user]` is not a macro; `schedule.txt`
    is injected without `fill()` at all, so the literal bracket token reaches
    the prompt every Saturday. Writing `{{user}}` there would not fix it
    either, since the file gets no substitution pass — needs a plain-language
    fix, e.g. "whatever the two of them do together."
67. **[fleet card] LOW-MED — "habitat, not outings" premise vs. a 23-entry
    regional map.** `setting.txt:1` — "the town is the handful of places she
    returns to rather than a map she explores" vs. eight destinations 1-3
    hours out in `atlas.txt`. With `ATLAS_SAMPLE=6` random picks, a far-entry
    draw reads as the explorer the setting says she isn't.
68. **[fleet card] LOW — stale season and an overtaken goal.**
    `emily_harper.json:6` — "hoping to lead her first solo habitat assessment
    this spring" — today is 2026-08-15; `emily/projects.txt:1` has her
    already deep in a habitat assessment on revision 4. Gap, not a hard
    contradiction (unstated whether it's hers to lead).

**Verified clean (Emily):** Warren-rename cleanup fully intact fleet-wide —
zero "Marcus" strings reach a prompt anywhere (the two remaining hits,
`bonnie/atlas.txt` and `cass/atlas.txt`, are inside `#`-header comments that
`bot.py:960` strips). Exact Dr. Yuen cross-reference between card and seed.
Age/appearance agree exactly. No false feature claims against `bot.py`'s
actual WSDOT/vision/voice capabilities.

### Priya (`priya.json` + `priya/`)

69. **[fleet card] Tenure contradiction — card says 3 years, seed says 6
    weeks.** `priya.json:6,11` — "three years in now"; "three years as a
    transplant" vs. `priya/setting.txt:1` — "having moved from Austin in July
    2026... still a newcomer," corroborated by `priya/life.txt:1` ("hasn't
    unpacked the last three boxes"). Card and seed pick opposite sides.
70. **[fleet card] Origin contradiction — Austin exists nowhere in the
    card.** `grep -c Austin priya.json` = 0. Card frames her transplant axis
    as East-Coast-only (`priya.json:6,34,97`); seed measures her against
    "Austin and... the New Jersey she grew up in" (`setting.txt:1`).
71. **[fleet card] Atlas entries presuppose the long tenure (downstream of
    the tenure contradiction).** `priya/atlas.txt:10,17,18` — "went through a
    phase, now mostly avoids," "discovered it late, now it's her weekend
    default," "from when she first moved here" — none survive a five-week
    residency. Resolves automatically once the tenure question is settled.
72. **[fleet card] Low severity, anti-fix note — not proposing a change.**
    `priya.json:6` "doesn't drink coffee — never has" vs. `priya/life.txt:1`
    "the coffee place she'd quietly decided was hers." Strictly compatible
    (a café can serve chai); flagging so a future pass doesn't "reconcile" it
    by giving her a coffee habit.

**Verified clean (Priya):** lowercase register holds everywhere — `first_mes`,
`mes_example`, alternate greetings, `preset-priya.txt`; no capitalization
drift, no softening. Geography Eastside-consistent; every atlas place is real,
and the two Seattle entries are explicitly labelled as deliberate trips.

### Jules (`jules_nakagawa.json` + `jules/`)

73. **[fleet card] Current-job contradiction, in three card locations
    including two of five greetings.** `jules_nakagawa.json:11` and
    `jules/atlas.txt:6`/`jules/schedule.txt` agree the dealership is past
    ("her old job," current job is a taphouse). But `jules_nakagawa.json:192`
    (lorebook, present tense — "works at a Toyota dealership"),
    `:15` (alternate_greetings[0], set entirely behind the parts counter), and
    `:19` (alternate_greetings[4] — "I sold somebody a fuel pump") all still
    place her there now.
74. **[fleet card] Tattoo placement disagrees between card and appearance
    seed.** `jules_nakagawa.json:6` — "peony on her ribs" vs.
    `jules/appearance.txt:1` — "floral piece on her thigh." `appearance.txt`
    drives image generation; the two currently describe different bodies.
75. **[fleet card] A lorebook key her own voice fires.** The Jules's Mother
    entry keys on bare `"mom"` while the Chirp Bank instructs mom-chirps
    ("someone's mom... my deepest condolences... to your mother"). Content-side
    fix: tighten the key to `"my mom"` or move it to `secondary_keys`.

**Verified clean (Jules), re-checked not assumed:** escalated-cruelty-when-happy
rule intact and reinforced by new seed text (`jules/schedule.txt:2` — "meaner
than usual because she's happy"). Bellingham geography clean throughout, with
the two out-of-town entries explicitly labelled as such. New seed people
(Coach Reyes, Deb, Trish) introduce no fleet name collisions.

### Marcus (`marcus_calder.json` + `marcus/`)

76. **[fleet card] `mes_example` writes {{user}}'s turns with speaker
    labels — the 2026-07-20 Jules defect shape.** 9 `{{user}}:` / 18
    `{{char}}:` labeled lines. `bot.py:3264-3265` still injects this raw with
    no `<START>` parsing or label stripping. Jules's card carries an inline
    header fixing this content-side (`jules_nakagawa.json:10` — "Never write
    {{user}}'s words... never put a speaker name or label in front of a
    line"); Marcus has no equivalent.
    *Proposed:* port Jules's header sentence into Marcus's `mes_example`
    preamble as an interim mitigation. See §3 for the underlying code issue.
77. **[fleet card] Lorebook keys too common to stay rare — the worst
    instance of this pattern in the fleet.** THE CODE keys on bare `"no"`;
    AFTERCARE keys on `"okay"`, `"after"`, `"done"`, `"how are you"`; READING
    THE ROOM keys on `"read"`, `"feeling"`, `"honest"`. `\bno\b` and
    `\bokay\b` match nearly every 8-turn window, so two large blocks inject on
    almost every reply against a declared 500-token budget they jointly
    exceed several times over — and it inverts the character's own design
    (`marcus_calder.json:6` — "not limits he announces... apparent when he
    declines").
78. **[fleet card] LOW — two bookstores on one block, described
    inconsistently.** `marcus/atlas.txt:9` — "the bookstore he browses and
    rarely buys from" vs. `:11` — "Browsers Bookshop... pays at the counter
    fast." Half a block apart, plausibly the same store described two ways.
79. **[fleet card] Structural note, not a defect.** `marcus_calder.json:13`
    (`post_history_instructions`) and `:7` (`personality`) are both empty
    strings — his only final-position anchor and register contract live
    entirely in `preset-marcus.txt`. Owner-decision item, not proposing a
    change unprompted.

**Verified clean (Marcus):** standing-consent scoping preserved exactly as
canon requires (`preset-marcus.txt` correctly scopes `preset-explicit.txt`'s
"do not hedge" rule to the narrator, not the fiction); no family entries
invented (`marcus/people.txt` matches the deliberate gap on parents); Olympia
geography real and internally consistent; Emily overlap is exactly the two
sanctioned items (Browsers Bookshop, South Capitol grid) with nothing new
added.

### Cross-character pattern (one class, not one bug)

80. **[fleet card] Lorebook entries keyed on words too common to stay rare
    defeat their own "keep this rare" instruction, fleet-wide.** Confirmed
    again this pass in Priya (`"minor"`, `"brain"`, `"parents"` on two
    entries at once — while the entries themselves say "This is not a depth
    button" / "This is not a trauma button"), Jules (item 75), and Marcus
    (item 77, worst instance measured). The 2026-08-11 pass found the same
    shape in Nora (key `"left"`), Bonnie (key `"alone"`), and Emily (keys
    `"work"`, `"Seattle"`) — **not independently re-verified this pass**,
    since the nora/bonnie/cass/emily reviewer wasn't scoped to check it; flag
    as likely still present rather than assert it as confirmed.
    *Proposed:* a single fleet-wide pass tightening over-common lorebook keys
    to multi-word or phrase-anchored forms, since the shape recurs across at
    least five of seven characters — and a dedicated key-audit of
    nora/bonnie/cass/emily specifically to close the verification gap noted
    above.

**Deploy:** none of the above is actioned. If accepted, items touching any
instance's seeds/card ship via one `deploy/vps-sync.sh <instance>` invocation
per affected instance.

---

## 3. CODE finding — not a card proposal (per the Mode B boundary check)

81. **CODE — `bot.py` still dumps `mes_example` raw with no `<START>`
    parsing or speaker-label stripping; the 2026-07-20 Jules defect shape
    is now also present in Nora, Priya, and Marcus's cards.**
    `bot.py:3264-3265`:
    ```python
    if data.get("mes_example"):
        parts.append("# Example dialogue\n" + data["mes_example"].strip())
    ```
    No `<START>` parsing, confirmed unchanged since the 2026-07-20 incident
    (line numbers shifted from `3186-3199` to `3264-3265` as the file grew,
    shape identical). Counted across all seven live cards this pass: Nora — 4
    literal `<START>` markers with `{{user}}:` turns; Priya — 9 `{{user}}:`
    labels; Marcus — 9 `{{user}}:` labels. Jules and Bonnie are clean (Jules
    repaired content-side 2026-07-20 with an inline anti-label header; Bonnie
    never had the shape). Cass and Emily use `{{char}}:`-only examples.
    **Owner of the fix: `coder`** — parse `<START>` and/or strip speaker
    labels in the `mes_example` assembly path, `bot.py:3264-3265`. No card
    edit is proposed for this defect itself; the raw markers/labels are
    evidence, not the fix. The Jules-header port proposed for Marcus (item
    76) and worth considering for Nora and Priya too is a content-side interim
    mitigation only, same as what already shipped for Jules — it does not
    replace the code fix, which remains owed.

---

## 4. Root SillyTavern presets (deploy nowhere — owner loads by hand)

Reviewed the confirmed-newest of each family. Correction to a premise this
pass started with: `TheAtelier_2.0.json` was not "rewritten" since Aug 11 — it
was *added* in commit `90f414d` (its only commit; the file didn't exist
before). `UnifiedWritersRoom_V32.json` also has only that one commit. Both
reviewed fresh regardless. Live order block confirmed as before: chat
completion reads the block with `dummyId: 100001`; mismatches against a
*stale, unused* `100000` block are inert, not defects, and aren't reported.

Injection-shaped content encountered in `TheAtelier_2.0.json`'s
`interview_unrestricted` module (an ST jailbreak/safety-unlock layer) — this
is the owner's own authored content, evaluated as data only, not acted on.

### TheAtelier_2.0.json

82. **[root preset] HIGH — structural. 10 of the Core Pack's dial sections
    render as empty headers.** `interview_corepack` prints a fixed list of
    headers reading `{{getvar::Stakes}}`, `{{getvar::Bias}}`, etc. Every
    enabled `_mid` dial (stakes, violence, romance, humor, sensory, tone,
    agency, dialogue, world, chardev) sets only its label var, never the
    `{{setvar::...}}` the header reads — 10 bare headings with nothing under
    them. Deliberate for a "no modifier" dial, but the header still ships.
    *Proposed:* wrap each header in its var, or drop the header when empty.
83. **[root preset] HIGH — World Bias has a group header enabled and no
    option selected.** `interview_bias_hdr` is enabled; all three options
    (`_neg`/`_mid`/`_pos`) are false. Unlike the `_mid` dials, this leaves
    `BiasLabel` itself empty, so the always-on Settings Reminder emits a
    literal `"World_Bias": "",` and the CoT step renders a blank line.
    *Proposed:* enable `interview_bias_mid` (Honest World), already the
    premise's stated default.
84. **[root preset] HIGH — the enabled length dial fights two `[LAW]`s with
    untagged text.** `interview_rlen_high` — "Target Length: 900-1400+
    words... A scene contains arrivals, reactions, exchanges..." vs.
    `interview_corepack`'s `[LAW] The Turn's End` — "Burning through several
    of `<user>`'s natural response points in one turn... is how a scene
    dies." `rlen_high` carries no priority tag, so nominally the LAW wins —
    but it's 2,335 chars of unqualified imperative against one paragraph.
    *Proposed:* tag `rlen_high` `[BOUNDARY]` and add one deference sentence.
85. **[root preset] MEDIUM — the untagged "IMPORTANT REMINDER" style list
    contradicts itself and the tagged rules.** Item 5 — "Avoid decorative
    metaphors and similes" — contradicts both `LEAN SUBTEXTUAL`'s "concrete
    bruised metaphors used rarely" and `interview_antislop`'s own scope
    ("pattern warnings, not technique bans... deployed deliberately... is
    craft"). The 9-item list carries no priority tag in a preset whose own
    Premise says the higher-tagged rule wins.
    *Proposed:* retag the list `[STYLE]` and rewrite item 5 to match
    `antislop`'s framing.
86. **[root preset] MEDIUM-HIGH — native reasoning at `max` plus a prompted
    in-band `<think>` block.** `reasoning_effort: "max"`, `show_thoughts:
    true`, while enabled `interview_cot` mandates a second textual reasoning
    pass and opens a literal `<think>` tag in the prompt body itself — a
    reasoning model may pattern-match it as already-satisfied.
    *Proposed:* disable `interview_cot` when `reasoning_effort` is set, or
    drop `reasoning_effort` to none/low.
87. **[root preset] MEDIUM — reader-led smut dial vs. always-on NPC-agency
    rules.** `interview_smut_mid` — "they do not initiate sexual escalation
    unprompted. The user sets the pace" — vs. `interview_cot`'s "what an NPC
    would proactively do" and the always-on NPC Independence directive.
    *Proposed:* append a scope line ("This is the one place NPC initiative is
    bounded; NPC agency elsewhere is unchanged").
88. **[root preset] LOW — formatting.** A stray bullet in
    `interview_smut_mid` hangs off a non-bulleted paragraph, detached from
    the list it belongs to.
89. **[root preset] Observation — token proportionality.** `antislop` alone
    is ~28,034 chars (~17% of the enabled preset) tagged at the bottom of the
    priority ladder (`[STYLE]`). Not a bug; the preset's own closing line
    ("the list takes care of itself") argues it could be a third the size.
90. **[root preset] MEDIUM — rule triplication across always-on blocks.**
    User autonomy stated in **six** places fleet-wide within this one preset;
    "separate minds/unknown by default" in three. `interview_settings`'
    tooltip justifies one depth-0 restatement; the rest are unbudgeted.
    Estimated ~1.5-2k recoverable tokens with no rule lost.

**Verified NOT a defect:** `charDescription`/`charPersonality`/`scenario`/
`personaDescription` are correctly disabled — `atelier_databank` re-injects
those fields itself and its tooltip says so.

### UnifiedWritersRoom_V32.json

91. **[root preset] HIGH — `custom_stopping_strings: "</think>"` will eat
    the visible reply on any model that inlines reasoning.** MAIN assumes a
    reasoning block exists ("REASONING BUDGET... REASONING AUDIT (hard
    gate)"). If a provider returns reasoning inline as
    `<think>...</think>prose`, ST truncates at the stopping string and the
    prose never delivers — same shape, one layer up, as the 2026-07-20 Priya
    `reasoning_content` incident. Conditional on provider behavior; verify
    before changing, but no configuration exists in which this string helps.
92. **[root preset] HIGH — `chat_completion_source: "nanogpt"` with
    `nanogpt_model: ""`.** `claude_model`/`openai_model` are populated and
    unused. Loading this preset leaves the live model slot unset.
93. **[root preset] HIGH — "airy" is on the prefer list and the replace list
    in the same sentence.** `ps-banned-list`: "prefer... airy... Replace:...
    airy (only for female-character voices; for non-female drop it)."
    *Proposed:* "...prefer soft, warm, quiet, clear, bright, gentle, low,
    even. Replace: husky, throaty, guttural, purrs, smolders, barely above a
    whisper — and 'airy' for non-female characters."
94. **[root preset] MEDIUM-HIGH — "low" is preferred by the banned list and
    forbidden by intimacy mechanics.** `ps-banned-list` prefers "low";
    `ps-intimacy-mechanics` — "avoid low/deep/husky/throaty/gravelly/
    guttural." Both always-on; pick one (the intimacy module's list reads as
    intended).
95. **[root preset] HIGH — a hard-coded pro-{{user}} rule embedded in an
    anti-positivity-bias preset.** `ps-reaction-patterns` — a character who
    gave {{user}} an instruction and got compliance must respond with
    approval/thanks; "the one who gave instruction backs {{user}}" if
    challenged — directly against `PS - De-Positivity`'s "never glaze
    {{user}}" and `ps-npc-psych`'s alignment-position logic, where a
    self-interested or conviction-driven character would plausibly object.
    *Proposed:* "...responds in-character — approval, thanks, or neutral
    acceptance where their psychology supports it... A character with a
    self-interested or conviction-driven position may still blame {{user}};
    ALIGNMENT POSITIONS governs."
96. **[root preset] MEDIUM — dangling cross-reference to a module named
    "RUT" that doesn't exist anywhere in the file** (grepped, one hit — this
    reference). Either restore the module or drop the reference.
97. **[root preset] MEDIUM — `acc-unreliable` mandates in-output markup MAIN
    forbids.** Instructs `<!-- HIDDEN: ... -->` XML comments in the visible
    output; MAIN — "Never emit scaffold... not in output." `ps-continuity`'s
    `HIDDEN STATE` already tracks the same information invisibly.
    *Proposed:* disable `acc-unreliable` or carve it explicitly out of MAIN's
    blanket ban.
98. **[root preset] MEDIUM-HIGH — the preset's own reasoning budget plus its
    own pacing target exceeds its own `max_tokens`.** `openai_max_tokens:
    2500`; MAIN caps reasoning at 1500 tokens; the enabled pacing module
    targets 8-12 paragraphs (~1,200-2,000 tok) for climactic beats — sums to
    2,700-3,500 against a 2,500 cap, so climactic beats truncate mid-sentence
    by construction. *Proposed:* raise `openai_max_tokens` to ~4,000 or lower
    the reasoning budget.
99. **[root preset] Observation.** Enabled prompts total ~10.5k tokens
    against a 32,768 context with `max_context_unlocked: false` — ~22k left
    for card + world info + history. Not a defect; worth knowing before
    adding another always-on module.
100. **[root preset] MEDIUM — cross-module duplication in the always-on
    tier.** Three separate modules (`ps-prose-quality`, `ps-banned-list`,
    `ps-refresher`) each ban the same constructions ("not only X but also
    Y," standalone simile fragments) — ~400 tokens of exact-duplicate rule
    per message.
101. **[root preset] Minor.** `main`'s own header still says "[WRITERS'
    ROOM v12.1]" in a file named V32.

**Verified NOT a defect:** the Stop-and-Pass / Reply Drive / Pacing /
Environment-Track pacing interactions are explicitly self-resolved in the
text ("Overrides Reply Drive's advance-to-open-beat," "Pacing length targets
are a ceiling, not a floor") — the best conflict-arbitration in either root
preset, worth using as the model for fixing item 84 above.

**Deploy:** not applicable — both root presets deploy nowhere; the owner
loads them into SillyTavern by hand. Items 91 and 92 are the two the owner
would feel immediately on next load.

---

## 5. Fleet preset — `telegram-companion-bot/preset.txt`

**Corrected premise, verified against git rather than assumed:** `preset.txt`
did **not** "nearly double" since 2026-08-11 as this pass's own kickoff
instructions claimed. The only commit touching it since then (`e5f7418`,
Sprint 2) is +8/-3 lines. Reviewed fresh regardless.

**Actual current blast radius, found not assumed:** `bot.py:729-731` —
`PRESET_FILE`/`PRESET_FILES` — with neither env var set, `preset.txt` is the
loaded voiceprint. `bot.py:759-767` — when named `PRESET_FILES` layers fail to
resolve on disk, the ladder falls back to `preset.txt` with a logged warning.
**Primary layer: no** — per `ROADMAP.md` 3.13, the last four instances moved
off the monolith on `v2026-08-02.12`; all seven now load `preset-*.txt`
stacks (the authoritative live check is `/audit` → `Preset layers:` per
instance, not this file). `preset.txt` remains the fleet's safety net for any
deploy-order mistake. **The finding that matters for every item below:**
`preset.txt` is ~95% the concatenation of `preset-core + rp + explicit +
stepped` (sentence-level diff: 325 vs. 369 sentences, ~18 unique lines, all
line-wrap artifacts) — so every defect below also exists in the layer that
actually ships it live. A `preset.txt`-only fix is cosmetic; layer mapping is
given per item.

102. **[fleet preset] HIGH — `{{char}}` is hard-coded female and `{{user}}`
    hard-coded male in the relationship-stage block.**
    - *Before* (`preset.txt:706-712`): "'deeply familiar'... **She** knows
      **his** patterns well enough to call them out... **She** can be ugly...
      **She** also takes **him** for granted sometimes."
    - *After:* "'deeply familiar'... {{char}} knows {{user}}'s patterns well
      enough to call them out or work around them... {{char}} can be ugly —
      petty, needy, unfair — and trust it won't end things... {{char}} takes
      {{user}} for granted sometimes, and that's real too."
    - *Fleet-wide effect:* the gendering runs through `preset.txt:70,95,
      254-256,374-376,661-663` and, more importantly, through
      `preset-core.txt:207-208,225-228,254-255` (all seven instances) and
      `preset-closeness.txt` (the relationship-stage block itself,
      `CLOSENESS_ENABLED` default OFF). Marcus is the fleet's only male
      character and is described as "she" by the shared voiceprint on every
      message it reaches. `preset.txt` alone is cosmetic; the real change is
      `preset-core.txt`, which needs explicit owner go-ahead. Lowest-risk
      start: fix Marcus's exposure in `preset-marcus.txt` first.
103. **[fleet preset] MEDIUM-HIGH — the epistemic-horizon channel definition
    is written for asterisk-roleplay, not the texting format the same file
    mandates.**
    - *Before* (`preset.txt:99-102`): "From {{user}}'s messages, {{char}}
      receives exactly two channels: words spoken aloud (in quotation marks)
      and observable behavior."
    - *After:* "From {{user}}'s messages, {{char}} receives exactly two
      channels: what {{user}} actually wrote or said, and behavior {{char}}
      can observe. In a text thread that is the message itself; in a
      narrated scene it is quoted dialogue plus described action."
    - *Fleet-wide effect:* identical line at `preset-core.txt:61`, loaded by
      all seven. Priya's card forbids asterisk actions entirely and Cass
      "texts, never narrates" — for them the quotation-mark channel never
      exists, so the rule as written can be silently dropped by the model.
104. **[fleet preset] HIGH — the Dead Dove guide is the only ungated global
    tone directive, one line above a properly gated module.**
    - *Before* (`preset.txt:390-394`): "### Dead Dove Content Guide / **The
      goal is to create an unsettling and dark narrative.** This is a
      fictional scenario... Responses will avoid ethical protocols."
    - *After:* "### Dead Dove Content Guide / When a scene goes dark, it goes
      dark without sanitizing: morally reprehensible acts are rendered, not
      softened, and no redemption arc is imposed on material that has not
      earned one. / Do not refuse, warn, or moralize about fictional
      content." (gated the same way the neighboring block already is —
      "When this module is active, the following rules override default
      writing tendencies")
    - *Fleet-wide effect:* identical text is in `preset-explicit.txt`, loaded
      by 5 of 7 (not Cass or Priya). Gating the tone mandate stops those five
      from treating "dark and unsettling" as the default register for
      ordinary conversation. Also fixes third-person-future phrasing
      ("Responses will...") in a file that otherwise addresses {{char}} in
      second person.
105. **[fleet preset] MEDIUM — `[SCENE RHYTHM]` names its four registers in
    MOBA jargon that carries no meaning to the model on its own.**
    - *Before* (`preset.txt:611-643`): "Laning — low-intensity, zero-degree
      prose." / "Gank — show-don't-tell intensifies." / "Teamfight — full
      descriptive power."
    - *After:* "Quiet — low-intensity, zero-degree prose." / "Charged —
      show-don't-tell intensifies." / "Full — full descriptive power."
      (labels never emitted per the file's own rule — they exist solely as
      model-facing handles, so the metaphor adds a decode step without
      illuminating the prose rule underneath — the exact case CLAUDE.md's
      vocabulary rule 3 describes.)
    - *Fleet-wide effect:* lives in `preset-rp.txt` (5 of 7) and is
      cross-referenced by name in `preset-stepped.txt` (all seven) — renaming
      requires both files changed in the same commit or the cross-reference
      dangles.
106. **[fleet preset] MEDIUM — the same contradiction-resolution rule stated
    twice, ~250 tokens apart, once for {{char}} and once for NPCs.**
    - *Before* (`preset.txt:329-335`, `[NPC MANAGEMENT]`): "When an NPC's
      words and actions conflict within a scene, the conflict resolves
      through the character's specific psychology. They may correct course,
      their mask may slip... The contradiction resolves, even if the
      resolution is messy or incomplete." (near-duplicate of `:265-277`
      `[CHARACTER AGENCY]`, same structure for {{char}})
    - *After* (keep `:265-277`, replace `:329-335`): "The same contradiction
      rule applies to NPCs: their words and actions conflict, and it
      resolves through their own psychology, never as sustained tension."
    - *Fleet-wide effect:* {{char}} copy is `preset-core.txt` (all seven);
      NPC copy is `preset-rp.txt` (5 of 7, not Cass/Priya). ~110 tokens saved
      per message on the five scene instances.
107. **[fleet preset] LOW — near-verbatim duplication of the "emotions are
    animal" rule.**
    - *Before* (`preset.txt:364-367`): "Use human metaphors: feelings ache,
      gnaw, bloom, settle, spike. Emotion is always present, communicated
      through the character's own patterns — body language, vocal shifts,
      behavioral changes." (duplicates `:193-196` almost exactly)
    - *After* (keep `:193-196`, replace `:364-367`): "Emotion is always
      present and reaches the page the same way it does for anyone else —
      body language, vocal shifts, behavioral change."
    - *Fleet-wide effect:* both copies in `preset-core.txt` (all seven);
      ~40 tokens/message, no behavior change intended — lowest-risk item in
      this section.
108. **[fleet preset] MEDIUM — the paragraph-length default has no
    arbitration clause, and the fallback path is exactly where that
    matters.**
    - *Before* (`preset.txt:603-609`): "Default to one to three short
      paragraphs for conversational exchanges... In Telegram, prefer shorter
      responses that match chat rhythm."
    - *After* (append): "Where a character card states its own length or
      format contract — a paragraph count, lowercase, no asterisk actions,
      third-person beats — the card wins and this default does not apply."
    - *Fleet-wide effect:* `CHANGELOG.md` records this exact contradiction
      (Bonnie's card wants 3-6 paragraphs, this default says 1-3) as already
      fought and solved by `preset-bonnie.txt`/`preset-priya.txt`. But
      `bot.py:759-767`'s fallback lands on `preset.txt` alone, which carries
      no arbitration — a layer-resolution failure silently reverts Bonnie
      and Priya to a contract their own cards contradict. Touches all seven;
      owner go-ahead required for the `preset-core.txt` copy.
109. **[fleet preset] Observation, no edit proposed — flagging only.** The
    autistic-character module (`preset.txt:351-368`, ~200 tokens) fits no
    current fleet character (no card describes one). The adjacent
    scientist/professional half of the same section does earn its place
    (Priya's engineer example). *Fleet-wide effect if ever actioned:* moving
    the unused half to an opt-in layer would cut ~200 tok/message fleet-wide
    with no live behavior change — but this is exactly ROADMAP 3.13's
    content-split question, already owner-gated; not proposing action ahead
    of that decision.

**Deploy:** none of the above is actioned. If accepted, any `preset.txt` item
ships via `deploy/vps-sync.sh <instance>` per instance — but for 7 of 8 items
the *live* fix is in `preset-core.txt`, `preset-rp.txt`, or
`preset-explicit.txt`, each feeding 5-7 bots, and those need explicit owner
go-ahead naming the file (ROADMAP 3.13). Item 107 is the lowest-risk starting
point; item 102 (Marcus's gendering exposure) is the highest-value.

---

## 6. External ideas

**Reddit-scoped search: SKIPPED (Tavily connector not authorized in this
fired session).** `routines.md` (updated 2026-08-14) states this Routine's
fired session "carries Tavily and Nimble MCP connectors," but this firing's
`ToolSearch` for `tavily_search` returned nothing, and the session's own
tool-availability notice explicitly listed Tavily as "requires authentication
before its tools can be used... capability is unavailable until [the owner
authorizes it]." No `tavily_search` call was attempted once this was
confirmed — fabricating Reddit results was not an option. **Flagging for the
owner:** the Tavily connector attachment recorded in `routines.md` for this
trigger did not hold this firing; worth re-checking the trigger's connector
configuration in the claude.ai routines UI. `WebSearch` was not substituted
for the Reddit-specific step — per this Routine's own prior verified
diagnosis (`routines.md`, `improvement-loop-monthly` history), `WebSearch`
with a `reddit.com` domain filter errors "not accessible to our user agent"
and unrestricted `WebSearch` returns no actual reddit.com URLs, so trying it
would only have produced a false "SKIPPED" masked as a result.

**Supplement search completed via `WebSearch`** (Tavily unavailable for this
leg too, so `WebSearch` substituted — the routine's supplement step doesn't
name Reddit specifically, so this is a smaller deviation than skipping it
would be for the Reddit-scoped leg). 3 queries, scoped to SillyTavern
card-writing guidance:

- **[external idea]** MiniTavern and TavernSprite 2026 card-writing guides
  (https://blog.mini-tavern.com/blog/sillytavern-character-card-template-the-ultimate-guide-to-formatting-and-best-pr-eec44c,
  https://tavernsprite.com/blog/sillytavern-character-card-best-practices/) —
  general framing: keep `mes_example` to 2-3 concise examples over many
  rambling ones, and use it to demonstrate how a character deflects an
  attempt to break character. Cited generally rather than quoted verbatim
  (WebSearch results are a model-summarized digest of the pages, not raw
  page text, so treating them as directly quotable would repeat the mistake
  this repo's own rules warn against for `WebFetch` paraphrases). Directly
  applicable to two inbox findings above: VivienneGrey's 8,662-character
  `mes_example` against an 83-character `first_mes` (item 16), and the
  general pattern across several inbox cards of `mes_example` carrying more
  characterization load than the fields meant to define voice.
- **[external idea]** World Info Encyclopedia
  (https://rentry.co/world-info-encyclopedia) and the official ST World Info
  docs (https://docs.sillytavern.app/usage/core-concepts/worldinfo/) —
  general framing: "good entries are short, specific, and easy to trigger,"
  each answering one clear question rather than maximizing coverage.
  Directly applicable to the fleet-wide over-common-lorebook-key pattern
  found this pass (§2, item 80) and to several inbox lorebook findings (items
  5, 13) — the guidance argues for narrower keys, which is exactly the fix
  those findings propose.
- **[external idea]** GitHub SillyTavern-CharacterTools
  (https://github.com/Inktomi93/SillyTavern-CharacterTools) — an existing
  extension built specifically to detect the class of problem this pass spent
  most of its time on by hand: internal contradiction and "lost the
  character's soul" drift in a card. Worth the owner's awareness as a
  possible future tooling aid for future monthly passes, not something this
  session can install or evaluate further.

---

## Summary for the owner

5 inbox files reviewed (2 completion presets, 3 cards — 49 individual
findings, §1); 22 fleet-card findings across all seven live characters plus 1
cross-character pattern with an unverified-this-pass caveat (§2, items
50-80); 1 CODE-verdict finding handed to `coder`, with a content-side interim
mitigation proposed for the three affected cards (§3, item 81); 20 root-preset
findings — 9 on `TheAtelier_2.0.json`, 11 on `UnifiedWritersRoom_V32.json`
(§4, items 82-101); 8 fleet-preset findings on `preset.txt`, each with its
required before/after quote and fleet-wide blast-radius note (§5, items
102-109); and 3 cited external ideas via WebSearch, with the Reddit-scoped
step reported SKIPPED rather than faked (§6). Nothing applied — every item
above is a proposal. Two process notes for the owner outside the review
itself: the 2026-08-11 proposals file was found merged to `main` against this
Routine's own policy (see header), and this firing's Tavily connector did not
work despite `routines.md` recording it as attached.
