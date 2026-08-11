# Character & Preset Review — 2026-08

`character-pass-monthly` Routine, Mode B (proactive review — no reported voice
defect to triage). Nothing in this file has been applied. Every item is a
proposal for the owner to accept, reject, or edit interactively under
`edit-cards-and-presets`; no card, seed file, or preset was touched by this
pass. `bash .claude/evals/run-evals.sh` was green (40 passed / 0 failed / 1
skipped) throughout, and every touched JSON validated with
`python3 -m json.tool`.

**Process note, not a card finding:** this Routine's own prompt (mirrored in
`.claude/operating/routines.md`) still says "review the six live cards named
in CLAUDE.md's instance table." CLAUDE.md's table has carried **seven** rows
since marcus was added 2026-07-29 — before this Routine's prompt was last
edited (2026-08-07). That's stale wording in the Routine itself, not a
disagreement between this prompt and `routines.md` (the two match verbatim),
so it didn't trigger the halt-and-report rule — this run applied the
reasonable reading (review all seven) and is flagging the wording for a
one-line fix next time the Routine's prompt is touched.

---

## 1. Inbox review (`character-review/`)

Five files in the inbox. Two are not `chara_card_v2` character cards at all —
they're SillyTavern **completion presets** (`prompts` + `prompt_order`), not
covered by the "drop character cards" instruction in the folder's own
README. Judged as presets since that's what they are.

### [inbox card] Freaky Frankenstein Micro FF5.json (preset, 42 prompts / 20 enabled)

- `<prose_rules>` (ON): "You must use full complete sentence… You must Ban:
  verbless fragments, telegraphic prose" directly conflicts with
  `<internal_thoughts>` (ON): "Thoughts must be broken, impulsive,
  chaotic… never use full sentences" — both apply to the same response; the
  prose rule is scoped to "Your final response," not "narrative only."
- `<npc_voice>` (ON): "Fluid, human-like full sentences flow like water. No
  run-ons, punchy, short, or clinical statements" + "Ban 'and/but/or' in
  spoken dialogue" — banning all three coordinating conjunctions while
  demanding flowing non-short sentences is self-defeating.
- Freaky NSFW module (ON): "Never repeat any details mentioned previously,
  instead, describe something completely different" is unbounded, while
  `<do_not_repeat_descriptions>` bounds the identical rule to "the last 4
  msgs." The unbounded version is unsatisfiable in a long scene.
- `<anti_omniscient_NPCs>` (ON): "NPCs treat others as strangers initially" —
  silently overrides any card whose scenario is an established relationship
  (true of all three real cards in this inbox).
- Structural: the "=Pick one…" separators are inert comments, not enforced
  choices. Four POV modules all emit `<POV>` and both NSFW modules emit
  `<adult_mode>`; enabling two ships contradictory blocks with no guard
  ("slow burn, don't rush" vs. "NSFW themes into EVERY SCENE"). `enhanceDefinitions`
  and `nsfw` exist in `prompts` but appear in no `prompt_order` entry —
  unreachable dead weight.

### [inbox card] Megumin secret sauce v2.0 fix (3).json (preset, 121 prompts / 53 enabled)

- **Read-before-write bug:** `Variables` (order index 4) sets every var
  empty; `Main Prompt` = `{{getvar::main}}` (index 5); `main` is first
  *written* by `1.1 ┃RP semi-Assist` at index 8. The system prompt renders
  blank on a fresh chat and one generation stale thereafter.
- **Variable collision:** `Variables` sets `sara4` to "megumin must put her
  text between [ ] to talk to user." `3.1 ┃🟢🧱 shut up megumin` (ON by
  default) overwrites the *same* var with unrelated text — enabling one
  toggle silently deletes the bracket-formatting rule that `🔴Rules 2`
  renders via `### {{getvar::sara4}}`.
- Two `prompt_order` blocks exist: `character_id: 100001` (all 115 entries)
  and `character_id: 100000` (only the 11 stock markers — every authored
  module absent). Under the 100000 order the preset contributes nothing.
- `1.1 ┃RP semi-Assist` (ON) hardcodes "You are megumin, an arabic writer
  that have years of experience" — a fixed character name and author
  nationality baked into what's meant to be a general-purpose preset — and
  collides with `4.5 western` (ON): "Avoid… culturally Japanese
  conversational beats."
- Same module, direct self-contradiction: under "Absolute Autonomy of
  `<user>`… strictly forbidden to: Speak, act, or think on behalf of
  `<user>`," the allow-list below it grants "Decide `<user>`'s actions,
  movements, posture, or behavior" — permission contradicts the ban stated
  one line above.
- `Variables` omits `main`, `main2`, `langu` from its init list; `voicem` is
  initialized and never read. `Chat Examples` and `Post-History
  Instructions` are disabled in the live order, so a paired card's
  `mes_example` reaches the model only via a separate `{{mesExamples}}`
  prompt, and its `post_history_instructions` not at all. Six prompts
  (including `Speech`, `2.10`–`2.12`) sit in no order block at all.
- `openai_max_context: 1000000` / `openai_max_tokens: 20000` will error on
  most backends.

### [inbox card] SaskiaReyes.json — strongest of the five; four real defects

- **Cost-band contradictions.** Lorebook "Tab Mechanics" states
  `surface-anatomical: cost: $50k-250k`, but `mes_example` bills "Three
  hundred and twenty thousand. Surface-anatomical." — outside its own
  band. Same shape: lorebook states `interior-relational: $10M+`, but
  alternate greeting 3 bills "four million" for the same tier.
- **The refused-name beat is undercut by its own examples.** Lorebook "The
  Refused Name Beat" reserves "Margaret" (used casually) for "a single
  'Margaret' under stress, said without armor" as a rare interior-relational
  beat — but `first_mes` uses "Margaret" four times casually, and "Margaret
  you do not UNDERSTAND" is listed as a routine catchphrase in
  `personality`, `description`, and `system_prompt`.
- **Surname/first-name error.** The same lorebook entry says the baseline
  address is "'Margaret' (surname only)" and "never warmly by first name" —
  but the character is Margaret **Pak**; Margaret is her first name, not her
  surname. The rule instructs the surname and demonstrates the given name.
- **Spec-invalid lorebook entry.** Entry 9 ("Peer Group / Cassidy / Talia")
  has only `comment, content, id, keys, secondary_keys` — missing `enabled`,
  `insertion_order`, `constant`, `position`, `extensions`, which the other
  eight entries all carry. May import disabled or get silently dropped.
- Minor: `token_budget: 1024` against nine ~300–500-token entries all at
  `insertion_order: 100`, with "ledger," "the woman," and "kitchen counter"
  each keying two entries — a single trigger word can fire two entries and
  silently truncate.

### [inbox card] VivienneGrey.json

- **`mes_example` mixes two incompatible registers.** The first ~12 blocks
  are bare first-person dialogue, no narration; the tail switches to third
  person with a named scene partner ("*She is at a bar in Vauxhall with
  Dee. {{user}} is not here.*") using literal speaker labels ("Dee:
  Bullshit.") — `Dee:` is not a macro SillyTavern parses, and the tail
  teaches {{user}}-absent scenes.
- **Dee exists nowhere else** — no lorebook entry, no mention in
  `description`, `personality`, or `scenario`. Only in `mes_example`.
- **Invented physical tell.** `system_prompt`'s `<dialogue_rules>` names "a
  cufflink adjusted" as a tell, but the cufflink appears in no other field —
  her wardrobe is "architectural blacks and grays… latex, leather harnesses,
  corsetry" — and `post_history_instructions`' own tell list has boot, ring,
  and tea, no cufflink.
- **Three formatting conventions inside one `mes_example` field:** no stage
  directions in most blocks, parenthetical asides in some ("(a long
  pause)"), `*italics*` stage directions in the tail.
- Dead lorebook trigger: "Mother's Departure" keys on "Nottingham," which
  appears nowhere else in the card. Over-broad triggers: "Mink the Cat" keys
  on the bare word "flat," which fires on every mention of {{user}}'s flat
  (used in `scenario`); "Mentor" keys on "older," "trained," "learning."
- `first_mes` is 83 characters against an 8,662-character `mes_example` and
  a `system_prompt` demanding physical-detail-carries-emotion — the opener
  demonstrates none of what the card claims is central.
- Structural: `spec: chara_card_v3`, not v2 (the folder asks for v2 cards);
  `character_book` uses vendor keys `tavo_spec`/`tavo_spec_version`;
  `creator: "Assistant"`.

### [inbox card] main_michelle-scott-80f0d754b955_spec_v2.json

- **POV directive contradicts every example.** `extensions.depth_prompt`
  (depth 0, lands last in context): "Keep it second-person for the user's
  immersion" — but every `mes_example` block is third person about
  {{user}} ("invading their personal space").
- **Narration recites the character sheet as prose:** "*Inwardly her core
  drive for connection kicks in*," "*Her dirty-talk style slips in, cringey
  yet earnest*" — field names leaking into the text as meta-commentary.
- **`scenario` duplicates and contradicts `first_mes`.** `scenario` contains
  a full quoted self-introduction and has her exiting the conference room
  and physically moving {{user}} ("drags them toward a meeting"); `first_mes`
  has her bursting *into* the same room and introducing herself again.
- **`creator_notes` contradicts the card:** "No heavy drama or dark twists
  intended; keep it fun and PG-13" against an "Anatomical Notes" section
  with explicit genital detail, a full kink list, and a `mes_example` that
  ends on an explicit advance.
- `mes_example` leaks its own scaffolding — its first line is literally
  "Example Dialog 1: The Awkward Introduction on Your First Day."
- Structural: `system_prompt` and `post_history_instructions` are empty
  strings, `alternate_greetings` empty, `character_book` is `null` — every
  named office character (Dwight, Pam, Jim) has zero lorebook coverage.

**Deploy:** not applicable — none of the five inbox files deploy anywhere.

---

## 2. Fleet spot-check (all seven live characters)

### Nora (`nora.json` + `nora/`)

1. **[fleet card] Geography contradicts the core transplant premise.**
   `nora/atlas.txt:13` — "Rainier Beach — she grew up near here; the
   neighborhood's changed, the hills haven't" directly conflicts with
   `nora/setting.txt:1` ("grew up on Chicago's South Side") and
   `nora.json:6` ("She grew up in Chicago"). The card's whole premise is
   "Seattle is where she lives now; Chicago is still where her instincts
   learned their shape" — this line reads like a Chicago→Seattle
   find-replace slip.
   *Proposed:* re-cast to route-knowledge — "Rainier Beach — the long
   south-end run; she knows every pothole and none of the shortcuts yet."
2. **[fleet card] Hair contradicted between card and seed.** `nora.json:6`
   "Dark blonde hair past her shoulders, usually tied back" vs.
   `nora/appearance.txt:1` "warm blonde hair a little past her shoulders …
   worn loose" — also drops the "freckles over the bridge of her nose" the
   card names. The card should win; update `appearance.txt`.
3. **[fleet card] The volunteer clinic exists only in the seed files.**
   `nora/projects.txt:4`, `nora/people.txt:3` (Dr. Flores),
   `nora/schedule.txt:2` establish a standing biweekly commitment that
   nothing in `nora.json` — description, personality, or any of the six
   lorebook entries — knows about. Not a contradiction, a gap: her card-self
   and her scheduled self are different people.
4. **Cross-check against `caa16137-nora.json`:** benign divergence
   confirmed, no contamination either direction — all 14 `data` keys still
   differ (matches the documented 2026-07-11 count); the root copy has zero
   Seattle-atlas terms and the bot copy has zero extra "South Side"
   references beyond Chicago. This is the divergence working as intended,
   not a finding.

### Bonnie (`bonnie.json` + `bonnie/`)

Personality section order verified intact: Surface → Core → Energy States →
OCEAN → Friction (`bonnie.json:6`). Four-beat calm opening intact. No
softening in `preset-bonnie.txt`. No action needed there.

5. **[fleet card] `setting.txt` still carries the urban framing its own
   atlas already purged.** `bonnie/setting.txt:1` — "the convenience store
   two blocks over, the parking garage roof when she needs sky without
   committing to outside." The 2026-08-10 atlas rewrite replaced exactly
   this framing, and `bonnie/atlas.txt` explicitly cites `setting.txt` as
   its own authority while contradicting it: "her setting.txt is explicit:
   'this is not Seattle, and she is not urban. Errands are a drive, not a
   walk.'" The atlas's actual replacements are "the parking lot behind her
   building, top row" and "Chevron on S Burlington Blvd," measured at 1.9
   km — not "two blocks."
   *Proposed:* "the Chevron mini-mart down the Boulevard, the top row of
   the lot behind her building."
6. **[fleet card] `creator_notes` states counts the file itself
   contradicts.** `bonnie.json:13` claims "Five alternate greetings
   included" — `alternate_greetings` holds **four**. The same line claims
   seven named lorebook categories ("libertarian canon, 4chan culture, NEET
   backstory, quiet/Friction moments, hyperfixation mode, goblin inventory,
   and jealousy triggers") — `character_book.entries` has **four**. The
   missing *goblin inventory* entry is load-bearing: `bonnie.json:162`
   references it directly ("she catalogs what makes her irreplaceable — the
   Bitcoin socks, the Cheeto pouch, the Nutella toast") with no entry behind
   it.
7. **[fleet card] {{user}} is absent from her entire week.**
   `bonnie/schedule.txt` names him on zero of seven days, while the card is
   built on cohabitation (`bonnie.json:10` "{{user}}'s housewife";
   `first_mes` "I don't notice you for a full ten seconds"). Compare
   `nora/schedule.txt` and `emily/schedule.txt`, which both place the user
   in the week. Her seeds currently describe a solo apartment dweller; her
   card describes a live-in wife.

### Cass (`cass.json` + `cass/`)

Forward-momentum rule verified intact in all three places it should appear
(card, `preset-cass.txt`). No drift toward critique-only or cheerleading.

8. **[fleet card] Age contradiction.** `cass.json:6` states "27" vs.
   `cass/appearance.txt:1` "a woman in her early 30s." Downstream: the card
   places her PhD exit "three years ago" (age 24 on the card's own number,
   ~30 on the seed's), and `cass/atlas.txt` reads oddly for a 27-year-old
   ("she's been going since grad school"). The card's number is canon —
   update `appearance.txt`.
9. **[fleet card] Wardrobe detail cuts against the character.**
   `cass.json:6` — "Always in something she grabbed without looking —
   oversized flannel, a worn-out sweater" vs. `cass/appearance.txt:1` "a
   fine gold chain at her throat." A chosen ornament is the one deliberate
   thing in an outfit defined as undeliberate. Low severity — drop the
   chain, or make it something she never takes off (so it stops reading as
   a choice).

### Emily (`emily_harper.json` + `emily/`)

Warren rename verified clean — zero "Marcus" references remain anywhere in
her card or seeds; the shared-metro overlap with Marcus (Browsers Bookshop,
South Capitol) is intact and deliberate.

10. **[fleet card] The card never left the coast; the seeds moved to
    Olympia.** `emily_harper.json:6` and the `scenario` field both say "a
    small PNW coastal town," while `emily/setting.txt:1` ("Emily lives in
    Olympia, Washington") and the full `emily/atlas.txt` reflect the
    2026-08-02 Portland→Olympia move. `emily/schedule.txt:3` ("coastal
    walk") carries the same residue. This is more than tidiness: the move
    exists so Emily's location matches the state WSDOT covers, and the
    card — which carries more prompt weight than the atlas — still tells
    the model she lives somewhere else.
    *Proposed:* "their shared apartment in Olympia, a small state capital
    at the bottom of Puget Sound."
11. **[fleet card] "Her only real colleague is Mika" is contradicted three
    ways, and Mika has no other footprint.** The card's own lorebook names
    Warren as "her primary collaborator… a senior colleague, not her
    supervisor; Dr. Yuen is," and `emily/people.txt` lists Dr. Yuen and
    Warren. Mika appears only in `description` and one alternate greeting —
    no seed file, no lorebook entry.
    *Proposed:* either give Mika a lorebook entry, or drop "only" and fold
    her into the Warren framing.
12. **[fleet card] A literal `[user]` reaches the prompt unsubstituted.**
    `emily/schedule.txt:6` — "whatever she and **[user]** do together."
    bot.py's macro substitution only handles `{{char}}`/`{{user}}`, and the
    schedule file is read raw, so this line hands the model a bare bracket
    token every Saturday. Sole occurrence fleet-wide.
    *Proposed:* `{{user}}`.

### Priya (`priya.json` + `priya/`)

Lowercase register verified intact everywhere it should be (`first_mes`,
`mes_example`, alternate greetings, `preset-priya.txt`). Geography clean —
all 18 atlas entries are real Eastside/Seattle places.

13. **[fleet card] Tenure contradiction, card vs. seed.** `priya.json:6` —
    "She's a transplant: **three years in now**" vs.
    `priya/setting.txt:1` — "having moved from **Austin in July 2026**…
    still a newcomer." One month vs. three years; the card never mentions
    Austin at all.
14. **[fleet card] Same fault line, downstream.** `priya.json:6`'s "the
    gray gets to her some weeks" (implies lived winters) and
    `priya/atlas.txt`'s "from when she first moved here" both assume a
    longer tenure than the July-2026 move; only `priya/life.txt` ("still
    hasn't unpacked the last three boxes") matches the recent-move story.
15. **[fleet card] Origin axis mismatch.** The card's lorebook entry
    frames her transplant lens as East-Coast-only, but
    `priya/setting.txt:1` says she measures the city "against Austin and
    against the New Jersey she grew up in" — Austin appears in exactly one
    file fleet-wide.
16. **[fleet card] Soft contradiction, reconcilable.** `priya.json:6` "She
    doesn't drink coffee — never has" vs. `priya/life.txt` "the coffee
    place she'd quietly decided was hers now closes at two." Plausibly a
    chai order at a café, but reads as a coffee habit as written.
    Unverified aside (not a finding): `priya/atlas.txt` places a Whole
    Foods "on NE 4th" — Bellevue's store is more commonly cited at 116th
    Ave NE; worth an owner spot-check.

### Jules (`jules_nakagawa.json` + `jules/`)

No softening detected anywhere — the escalated-cruelty rule in
`preset-jules.txt` and `jules/schedule.txt` ("meaner than usual because
she's happy") are both intact. Bellingham geography consistent throughout.
The `mes_example` anti-speaker-label header from the 2026-07-20 fix is still
present in her card.

17. **[fleet card] Current-job contradiction.** The lorebook entry "Jules's
    Mother" states, present tense, that she "works at a Toyota
    dealership," while `creator_notes` and `jules/atlas.txt` both place her
    current day job at "a Bellingham taphouse" with the dealership as her
    **former** job ("her old job").
18. **[fleet card] Same drift reaches the greetings.** One greeting is
    staged entirely at the dealership counter, on shift ("Welcome to
    Bellingham Toyota's parts department… I sold somebody a fuel pump" this
    week) — consistent with the stale lorebook entry, not with the
    taphouse job the rest of the card now uses.
19. **[fleet card] Tattoo location mismatch.** Card: "fine-line peony on
    her ribs" vs. `jules/appearance.txt`: "a floral piece on her thigh."

### Marcus (`marcus_calder.json` + `marcus/`)

`preset-marcus.txt` verified intact — it still scopes `preset-explicit.txt`'s
standing-consent rule to the narrator's relationship with {{user}} only
("It does not reach inside the fiction… His asking is characterization") and
accurately paraphrases the source text. No family entries invented anywhere
in `marcus/` (people.txt covers Renata, Theo, Dev, Sabine/Tomas, the
unnamed couple, Mrs. Adeyemi — the deliberate silence on parents is intact).
Olympia geography is real and Emily-consistent; the shared Browsers Bookshop
and South Capitol grid are the intended overlap, not duplication.

20. **[fleet card] Timing contradiction, seed vs. seed.**
    `marcus/atlas.txt` places his first-coffee ritual "never after dark,"
    while `marcus/schedule.txt` has Thursday evenings as when "he'll meet
    someone for a first coffee or a call."
21. Low-confidence, owner call only: `marcus/atlas.txt` mentions a
    bookstore he "rarely buys from" alongside "Browsers Bookshop… pays at
    the counter fast" — different streets per `emily/atlas.txt`, so likely
    two distinct stores rather than a contradiction. No proposal, flagging
    for awareness only.

### Cross-character pattern (one class, not one bug)

22. **[fleet card] Lorebook keys built from common single words fire the
    entry on ordinary language, defeating the entry's own "keep this rare"
    instruction.** Three instances of the same shape:
    - Nora: key `"left"` fires the Mother entry on any "I left work,"
      against the entry's own text ("does not turn this into a regular
      confession").
    - Bonnie: key `"alone"` fires the NEET-Origin entry constantly.
    - Emily: keys `"work"` and `"Seattle"` fire the Warren entry on nearly
      every message about her job.
    *Proposed:* a single pass tightening all three to multi-word or
    phrase-anchored keys, since the shape (not the individual keys) is the
    thing to fix.

**Deploy:** none of the above is actioned; nothing to deploy yet. If
accepted, items touching nora/bonnie/priya/jules/marcus/emily seeds or cards
each ship via one `deploy/vps-sync.sh <instance>` invocation per affected
instance.

---

## 3. CODE finding — not a card proposal (per the Mode B boundary check)

23. **CODE — Nora's `mes_example` still carries the pre-2026-07-20-fix
    shape; `bot.py` still doesn't parse it.** `nora.json`'s `mes_example`
    holds four literal `<START>` markers and `{{user}}:` turns. `bot.py`
    (around line 3198) still does
    `parts.append("# Example dialogue\n" + data["mes_example"].strip())`
    with no `<START>` parsing (confirmed at `bot.py:3186-3199`) — the exact
    code path documented as the root cause of Jules's 2026-07-20 speaker-
    label regression. `jules_nakagawa.json` was cleaned to zero `<START>`
    markers at the time; Nora's card was not, and the code that would make
    her card's raw markers harmless was never patched either. This surfaced
    independently in a WebSearch pass on SillyTavern's own docs/issues
    (`<START>` is official-format syntax; ST's own renderer treats each
    `<START>` block as a discrete, droppable example — see External Ideas
    below), which confirms `bot.py`'s raw dump diverges from the format's
    own semantics, not just from this repo's card content.
    **Owner of the fix: `coder`** (parse `<START>` in the `mes_example`
    assembly path, `bot.py:3186-3199`) — not a card edit. No card change is
    proposed for Nora; the residue in her `mes_example` is evidence, not
    the defect.

---

## 4. Root SillyTavern presets (deploy nowhere — owner loads by hand)

Reviewed the confirmed-newest of each family: `TheAtelier_2.0.json` and
`UnifiedWritersRoom_V32.json`. (Verified first: SillyTavern resolves prompt
inclusion from `prompt_order[].order[].enabled`, not each prompt's own
`enabled` flag, and chat-completion reads the order block with
`dummyId: 100001` — so `prompt.enabled` mismatches against a *stale, unused*
order block are inert, not defects, and aren't reported below.)

### TheAtelier_2.0.json

24. **[root preset] Stale second `prompt_order` (character_id 100000, 36
    entries) sits alongside the live one (100001, 50 entries) with no dial
    options selected.** Dead weight today; would emit 17 bare dial headings
    if ST's `dummyId` default ever changed. Recommend deleting it or
    regenerating from the live order.
25. **[root preset] The one dial group with nothing selected.** World Bias
    is enabled as a header, but none of `bias_neg`/`bias_mid`/`bias_pos` is
    on — the header renders, then an empty variable, then a blank line in
    the settings summary. Every other dial group has a selection.
    *Proposed:* enable `interview_bias_mid` ("Honest World"), already
    written as the premise's default made explicit.
26. **[root preset] The enabled length dial contradicts the always-on
    pacing rule.** `interview_rlen_high` (enabled): "Target Length:
    900-1400+ words per response… Every response should feel chapter-like."
    The always-on corepack says the opposite: "Length is governed by what
    the scene needs, not by a default response size… A light beat gets a
    light response, and a response is allowed to be short." The sibling
    option `interview_rlen_mid` explicitly resolves this with a handoff
    rule; `rlen_high` never mentions one, and its "write every line of it"
    instruction can burn the corepack's own single-open-beat LAW.
27. **[root preset] The enabled smut-pacing dial may be silently
    outranked.** `interview_smut_mid` (enabled): "they do not initiate
    sexual escalation unprompted. The user sets the pace" — but the
    always-on Premise's "Autonomous Agency" LAW says `<char>` "pursues
    their own goals independent of `<user>`'s input," and the preset's own
    Rule Priority block says dials don't override the Premise unless
    explicitly tagged higher-priority. This dial carries no such tag.
28. **[root preset] Same class, currently latent.** `interview_stakes_low`
    and `interview_bias_pos` — neither selected today — both directly
    contradict the always-on "An Honest World" boundary ("neither rigged
    against `<user>` nor bent toward them") if either is ever turned on.
    Flagging so a future dial change doesn't ship a self-cancelling
    combination silently.
29. **[root preset] Literal `<think>`/`</think>` tags inside the system
    prompt text itself.** `interview_cot` (enabled) contains real opening
    and closing `<think>` tags as part of its instruction body, while the
    same file sets `reasoning_effort: "max"` and `show_thoughts: true` —
    two reasoning mechanisms plus literal delimiters in the prompt is the
    shape that produces leaked or doubled reasoning on models with a native
    reasoning channel.
    *Proposed:* fence the example (backticks, or a renamed placeholder like
    `[THINK]`), or disable `interview_cot` on native-reasoning models.
30. **[root preset] Verbatim and near-verbatim duplication across
    always-on Core prompts.** "Compliance without motivation is a failure
    of character" appears identically in two always-on blocks. Backstory-
    as-behavior-driver is stated as its own rule in two different modules
    with different headings. User autonomy is restated **five** separate
    times across always-on prompts (six counting the settings reminder);
    NPC autonomy, **four** times. One deliberate restatement at low depth
    is anti-drift; four to six in the same system block is redundancy that
    costs tokens without adding signal.
31. **[root preset] Organizational nit.** `GenreStyleBias` has a slot in
    the corepack and a settings-reminder key, but no dial group of its own —
    it's set as a side effect of whichever `interview_worldlogic_*` option
    is picked. Works today because all five options set it; breaks silently
    if a sixth option is ever added without doing the same.

### UnifiedWritersRoom_V32.json

32. **[root preset] The roster contradicts the room contract on spine
    count.** `main` states "One SPINE active at a time," but the enabled
    room header requires a spine *pair* (FRICTION + RESTRAINT), and both
    are enabled together as designed. The mutex module only enforces
    one-room-at-a-time, never spine count.
    *Proposed:* fix the `main` line to "one spine **pair** active at a
    time."
33. **[root preset] `main`'s always-on roster omits four modules that are
    in fact enabled and always on** (`ps-mutex`, `ps-de-positivity`,
    `ps-banned-list`, `ps-specificity-engine`) — `ps-prose-quality` then
    defers to "the [BANNED LIST] module" that `main` never tells the reader
    exists.
34. **[root preset] Two dangling references to modules absent from the
    file.** `ps-reaction-patterns` distinguishes itself from a "RUT" module
    that doesn't exist anywhere in the preset. `ps-intimacy-mechanics`
    references "BOTH general and NSFW banned lists" when there is exactly
    one (the `nsfw` prompt is empty and disabled).
35. **[root preset] Same word on the prefer-list and the replace-list of
    one sentence.** The banned-list module's vocal-register rule prefers
    "airy" for any voice, then separately restricts "airy (only for
    female-character voices; for non-female characters drop it)" on its own
    replace clause — self-contradictory within one sentence.
36. **[root preset] Two always-on modules disagree on the word "low."**
    The banned-list module prefers "low" for any voice; the intimacy-
    mechanics module says to avoid "low/deep/husky/throaty/gravelly/
    guttural" — directly in the scenes where vocal register matters most.
37. **[root preset] Duplicate construction bans across two always-on
    modules.** Both `ps-prose-quality` and `ps-banned-list` separately ban
    "not only X but also Y" and standalone simile fragments, worded almost
    identically. Pick one owner module.
38. **[root preset] An assistant-identity statement injected at depth 1,
    in the character's own voice slot.** `ps-de-positivity` injects, as an
    `assistant`-role message at depth 1: "I'm a neutral model, I never
    glaze {{user}}… I have no personal beliefs, I'm not an activist" —
    immediately before generation, in a preset whose own voice-constraint
    module opens with an "ASSISTANT-DEFAULT LEAK TEST" and whose `main`
    says "write directly in {{char}}'s voice."
    *Proposed:* convert to a `system`-role prohibition phrased about the
    narrator, not the model.
39. **[root preset] A hard-coded pro-{{user}} rule embedded in an
    anti-positivity-bias preset.** `ps-reaction-patterns`: a character who
    gave {{user}} an instruction and got compliance must respond with
    approval/thanks/neutral acceptance, and "the one who gave instruction
    backs {{user}}" if another character objects. This is positivity bias
    by another name, and it directly contradicts `ps-de-positivity`'s own
    "strictly forbidden" framing and the alignment-position logic in
    `ps-npc-psych`. Reads like a one-scene patch generalized into an
    always-on law.
40. **[root preset] Flagged as a concern, not a proven defect:** the
    reasoning-token cap ("keep reasoning blocks under 1500 tokens") sits
    against a large always-on reasoning workload — branch divergence,
    hidden-state tracking, knowledge-vector sorting, up to 6 off-screen
    characters, event-clock arithmetic, an 8-point delivery gate. Not
    measured this pass; worth a token count before trusting the cap holds.
41. **[root preset] Minor.** `main`'s own header still says "[WRITERS' ROOM
    v12.1]" in a file named V32. Room-switch guidance
    (`acc-room-switch`, `doc-room-swap-cheatsheet`) is deliberately
    disabled, so nothing currently reminds the owner to update temperature
    on a room switch even though room headers name per-room values.
42. **[root preset] Low severity but worth aligning:** `acc-unreliable`
    instructs emitting an HTML comment (`<!-- HIDDEN: … -->`) into the
    response, while three other always-on modules separately say "never
    emit scaffold / visible state block / OOC or meta block anywhere in the
    reply." HTML comments don't render, so this is cosmetic inconsistency
    in the instructions rather than a live leak.

**Deploy:** not applicable — both root presets deploy nowhere; the owner
loads them into SillyTavern by hand.

---

## 5. Fleet preset — `telegram-companion-bot/preset.txt`

**Live blast radius, as actually found (not assumed).** Layered
`preset-*.txt` files are the configured voiceprint for all seven instances
today (owner-confirmed 2026-08-01, ROADMAP.md), so `preset.txt` is not any
instance's *primary* layer right now. It is **not dead**, though:
`bot.py` still defaults `PRESET_FILE=preset.txt` and falls back to it for
**any** instance when a named `PRESET_FILES` layer fails to resolve on disk
— exactly the failure mode most likely during a deploy that lands `.env`
before the layer files. **Every item below therefore carries this blast
radius: an edit to `preset.txt` changes the text every one of the seven
instances silently falls back to, and the fallback is triggered precisely
when nobody is watching for it.**

43. **[fleet preset] Cross-reference to a rule that doesn't exist in the
    section it points to.**
    - *Before* (`preset.txt:604-606`): "In Telegram, prefer shorter
      responses that match chat rhythm — brevity, not a dramatic one-liner
      (see ANTI-SLOP). Never pad."
    - *After:* "In Telegram, prefer shorter responses that match chat
      rhythm. Brevity means cutting padding, not cutting the concrete
      detail ANTI-SLOP asks for — a bare dramatic one-liner is not the
      goal. Never pad."
    - *Fleet-wide effect:* `[ANTI-SLOP]` contains no rule about
      one-liners — the pointer sends the model looking for a constraint
      that isn't there, for any of the seven instances that ever fall back
      to this file. Note the identical stale text is *currently live* in
      `preset-core.txt` (which all seven instances do load) — fixing only
      `preset.txt` fixes the fallback and leaves the live copy wrong; both
      need the same edit if this is accepted.
44. **[fleet preset] The same contradiction-resolution paragraph is written
    twice, with two different word lists.**
    - *Before* (`[NPC MANAGEMENT]`, `preset.txt:327-333`): "When an NPC's
      words and actions conflict within a scene, the conflict resolves
      through the character's specific psychology. They may correct
      course, their mask may slip, they may destabilize, or they may deny,
      deflect, project, compartmentalize, or simply not notice… The
      contradiction resolves, even if the resolution is messy or
      incomplete."
    - *After* (replace the NPC-section copy only): "NPCs resolve a
      words-versus-state contradiction the same way {{char}} does — see
      [CHARACTER AGENCY]. The only difference is that {{char}}'s voice
      takes priority in how the conflict is rendered."
    - *Fleet-wide effect:* ~110 duplicated tokens stating one rule twice
      with slightly different verb lists (one adds "destabilize," the other
      "compartmentalize"), which reads as two different rules rather than
      one, for any instance that falls back here.
45. **[fleet preset] Duplicated emotion-verb list.**
    - *Before* (`preset.txt:362-365`): "Use human metaphors: feelings ache,
      gnaw, bloom, settle, spike. Emotion is always present, communicated
      through the character's own patterns — body language, vocal shifts,
      behavioral changes."
    - *After:* "Emotion is always present, communicated through the
      character's own patterns — body language, vocal shifts, behavioral
      changes. The body carries it, per [ANTI-SLOP]."
    - *Fleet-wide effect:* the same five verbs are prescribed twice
      (`preset.txt:191-194` has the first copy), and the pair sits oddly
      against `[ANTI-SLOP]`'s own banned example ("A wave of sadness washed
      over her") — a fallback preset that both bans and prescribes
      emotion-as-motion in different sections needs one statement, not two.
46. **[fleet preset] A default-OFF feature's rules apply unconditionally in
    this file.**
    - *Before* (`preset.txt:687-715`, `[RELATIONSHIP STAGE]`): "The system
      may inject a relationship stage. Let it shape defaults, not override
      the moment:" — unconditional, no gating.
    - *After:* cut the section entirely, or gate its opening line:
      "`[RELATIONSHIP STAGE]` — applies only when the system injects a
      relationship stage; if none is injected, ignore this section."
    - *Fleet-wide effect:* this text is byte-for-byte `preset-closeness.txt`,
      documented in `.env.example` as pairing with `CLOSENESS_ENABLED`,
      default **OFF** on most instances. Any instance that falls back to
      `preset.txt` gets the closeness voiceprint with the feature switched
      off elsewhere in its config. The same shape applies to
      `[STEPPED THINKING]` (`preset.txt:655-685`, mirrors
      `preset-stepped.txt`, pairs with `STEP_INTENT` — that one defaults
      on, so lower urgency, same shape).
47. **[fleet preset] The fallback text pushes Marcus out of his designed
    register.**
    - *Before* (`preset.txt:396-397, 450-452`): "Do not explain, warn, or
      hedge." / "NPCs pursue their own sexual goals. They do not ask
      permission unless asking is part of their persona. They act on
      desire."
    - *After:* "Do not explain, warn, or hedge — this governs the
      narrator's relationship with {{user}}, not what characters do inside
      the fiction. A character whose card makes asking, checking in, or
      declining part of who they are keeps doing all three; that is
      characterization, not a safety hedge." / "NPCs pursue their own
      sexual goals, at the pace their persona sets. They act on desire."
    - *Fleet-wide effect:* this is exactly the conflict `preset-marcus.txt`
      exists to resolve, with **none** of that scoping present here. A
      fallback onto `preset.txt` on the marcus instance strips his defining
      trait (asking first, declining what crosses his code) — the
      register damage is fleet-wide in mechanism, character-specific to
      Marcus in effect.
48. **[fleet preset] `preset.txt` has drifted stale against the live
    layers — flagging, not proposing a blind port.** It has no standing-
    consent block and no banned-rhetoric paragraph that the current
    `preset-core.txt` + `preset-rp.txt` + `preset-explicit.txt` +
    `preset-stepped.txt` + `preset-closeness.txt` stack carries. A naive
    port is a known trap: ROADMAP 3.14's own history records that porting
    the banned-rhetoric block into a layer shared by non-narrating
    instances produced a false positive on Priya (flagging a natural
    first-person hedge — "yeah. i'm fine. not mad or anything, just
    tired" — as banned rhetoric), which is why it shipped into
    `preset-rp.txt` only. `preset.txt` is the fallback for narrating *and*
    non-narrating instances alike, so it's the wrong home for that
    specific rule.
    *Proposed:* add a one-line header —
    `[FALLBACK ONLY — this file is not any instance's configured
    voiceprint. It exists so a missing-layer deploy lands on a full preset
    instead of a stub. The authoritative text is preset-core.txt and the
    preset-*.txt layers.]` — then port only the standing-consent block,
    deliberately leaving the banned-rhetoric paragraph out. Owner call.
49. **[fleet preset] The voiceprint's default pronoun assumes a female
    character.**
    - *Before* (`preset.txt:232-236`): "{{char}} has her own agenda, shaped
      by her mood, her day, and what she actually cares about right now."
      (96 `she`/`her` tokens across the file.)
    - *After:* "{{char}} has their own agenda, shaped by their mood, their
      day, and what they actually care about right now."
    - *Fleet-wide effect:* Marcus is male and written third person — the
      fallback text quietly argues against his card on every message it's
      loaded for. Same class, out of scope for this file but worth a
      companion note: `preset-core.txt` (which *is* live for all seven,
      including marcus, today) carries 52 of the same gendered tokens.
50. **[fleet preset] One word, two different rule definitions.**
    - *Before A* (`preset.txt:482-483`, `[EXPLICIT]` module): "### Aftermath
      / When the scene crests, write through the landing." — a mandatory
      post-climax beat.
    - *Before B* (`preset.txt:631-634`, `[SCENE RHYTHM]`): "Aftermath —
      minimalism. Silence carries weight. Short sentences, physical
      stillness…" — one of four named intensity registers.
    - *After* (rename B and its later references at `preset.txt:636-641`):
      "Cooldown — minimalism. Silence carries weight. Short sentences,
      physical stillness, the absence of the intensity that just passed."
    - *Fleet-wide effect:* `[SCENE RHYTHM]` tells the model to shift *into*
      a register called Aftermath while the explicit module requires an
      Aftermath *beat* — the collision makes a register instruction read as
      a content requirement, for any instance that falls back here.
51. **[fleet preset] Minor — coined MOBA labels carry no meaning to the
    model on their own.**
    - *Before* (`preset.txt:612,618,625`): "Laning — low-intensity,
      zero-degree prose." / "Gank — show-don't-tell intensifies." /
      "Teamfight — full descriptive power."
    - *After:* "Ambient — low-intensity, zero-degree prose." / "Charged —
      show-don't-tell intensifies." / "Full — full descriptive power."
      (plus matching renames at `preset.txt:636-641` and in
      `[STEPPED THINKING]` step 4.)
    - *Fleet-wide effect:* three of the four register names are
      League-of-Legends jargon whose ordinary meaning ("gank" = ambush)
      doesn't describe the prose behavior defined under it; the definitions
      do all the actual work, so the labels only add a mapping step. Low
      severity, but the labels are referenced by name in a second section
      (`[STEPPED THINKING]`), so they're load-bearing in more than one
      place.

**Deploy:** none of the above is actioned. If any item is accepted,
`preset.txt` ships via `deploy/vps-sync.sh <instance>` per affected
instance — but since no instance currently names `preset.txt` in its
`PRESET_FILES`, `vps-sync.sh` pulls it only as the fallback file, not as an
active layer; an accepted change reaches a running bot only via that
fallback path unless the owner also adds it to an instance's layer list.

---

## 6. External ideas (Reddit + Substack via `idea-scraper-actor/`, plus WebSearch)

Apify call succeeded (HTTP 201, 30 items: 10 Reddit `r/SillyTavernAI`, 20
Substack across `emergingai.substack.com` and `substack.com/@gencay`).
Most Substack items were general Claude/agent-building content with no
card-writing angle (skipped as out of scope for this pass). WebSearch
supplement: 3 queries, scoped to SillyTavern's own docs/blogs/GitHub.

- **[reddit idea]** "Freaky Frankenstein 5: Internal States — Beta Round 2:
  Final Testing" —
  https://www.reddit.com/r/SillyTavernAI/comments/1v5bnzi/freaky_frankenstein_5_internal_states_beta_round/
  — the author's changelog for this release specifically calls out
  "Positivity Bias removed," "GLM echo gone," "Anti-drafting updates," and
  "Dialogue overhauls." Directly relevant here: the inbox review (§1) found
  `Freaky Frankenstein Micro FF5.json` — an earlier/smaller build in the
  same preset family — carrying exactly the kind of self-contradicting
  prose-vs-thought rules this later release claims to have fixed. Worth a
  diff read against the inbox copy before deciding whether to propose
  updating it, rather than reviewing the micro version in isolation next
  time.
- **[substack idea]** "Memory Engineering: The System That Gives Your AI a
  Past" —
  https://emergingai.substack.com/p/memory-engineering-the-system-that-
  — a practical guide to persistent memory, retrieval, forgetting, and
  grounding for conversational agents. Relevant to this fleet specifically
  because the operational log's still-open thread on emily's error mix
  names `memory_ungrounded` and `note_ungrounded` as live guard categories;
  this piece's framing of "forgetting" as a designed behavior (not a
  failure) may be useful vocabulary the next time a card or preset needs to
  describe what a character does and doesn't remember.
- **[external idea]** SillyTavern's own official docs on the Author's Note
  mechanism —
  https://github.com/SillyTavern/SillyTavern-Docs/blob/main/Usage/Characters/Author's-Note.md
  — depth and frequency are configurable per-chat, and placement close to
  the bottom of the prompt has more influence on the next response. None of
  the fleet's cards currently lean on Author's Note; it's a lever that
  exists independent of card/preset text and could reduce reliance on
  repeated always-on directives (see finding #30 above, where the same
  rule is restated 4-6 times in the root Atelier preset instead of being
  placed once at controlled depth).
- **[external idea]** GitHub issue confirming `<START>`-tag semantics for
  `mes_example` are official ST format, not this repo's invention —
  https://github.com/SillyTavern/SillyTavern/issues/534 — each `<START>`
  block is a discrete example that ST pushes out of context block-by-block
  as space runs low; the persona's name is *not* auto-appended to example
  dialogue the way it is to real chat history, which is itself a known
  source of formatting drift. Directly supports the CODE finding in §3
  above (`bot.py` still dumps `mes_example` raw for Nora's card) and is
  worth keeping on hand for whoever picks that fix up.
- **[external idea]** MiniTavern/TavernSprite character-card guidance
  (aggregated from a card-writing blog search) — "every token should earn
  its place… a few hundred well-chosen tokens outperform a thousand vague
  ones" and "2-3 example dialogues teach voice better than paragraphs of
  description." Cited generally, not to one URL, since several
  near-identical blog posts made the same point. Directly applicable to
  two inbox findings above: VivienneGrey's 8,662-character `mes_example`
  against an 83-character `first_mes` (§1), and the general pattern across
  several inbox cards of `mes_example` carrying more characterization load
  than the fields meant to define voice.

---

**Summary for the owner:** 5 inbox files reviewed (2 turned out to be
completion presets, not cards — 25+ individual defects between the five,
detailed in §1); 22 numbered fleet-card findings across all seven live
characters plus one cross-character pattern (§2, items 1-22); 1 CODE-verdict
finding handed to `coder`, not proposed as a card edit (§3, item 23); 19
root-preset findings — 8 on TheAtelier_2.0.json, 11 on
UnifiedWritersRoom_V32.json (§4, items 24-42); 9 fleet-preset findings on
`preset.txt`, each with its required before/after quote and fleet-wide
blast-radius note (§5, items 43-51); and 5 cited external ideas (§6).
Nothing applied — every item above is a proposal.
