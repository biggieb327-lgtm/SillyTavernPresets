# Character & Preset Remediation Roadmap — 2026-08

Sprint plan for the ~109 findings in `PROPOSALS-2026-08.md`. This file
indexes and sequences that document — it does not duplicate its evidence.
Every item below is `PROPOSALS-2026-08.md #<n>`; read the source item for the
full before/after quote and file:line citation before applying anything.

**Still proposal-only.** Nothing here is applied. Sprints are a suggested
order of operations for the owner working interactively under
`edit-cards-and-presets`, not a commitment this session is making on its own.
Items tagged **[owner-gate]** touch a file shared by 5-7 bots
(`preset-core.txt`, `preset-rp.txt`, `preset-explicit.txt`) and need an
explicit go-ahead naming the file before editing, per ROADMAP 3.13 and this
contract's fleet-wide blast-radius rule — everything else is a single
card/seed/file, lower blast radius, safe to take owner-by-owner.

---

## Code Track — hand-off to `coder`, not a sprint

- **#81** — `bot.py:3264-3265` still dumps `mes_example` raw with no
  `<START>` parsing or speaker-label stripping. The 2026-07-20 Jules defect
  shape now reproduces in Nora, Priya, and Marcus's cards. Owner: `coder`,
  under `repo-change-control` (BOT_VERSION bump, changelog, delivery gate) —
  not a content edit, not part of the sprints below. Sprint 1's Marcus item
  (#76) is a content-side interim mitigation that does not replace this fix.

---

## Sprint 1 — Fix the flat contradictions
**Why first:** unambiguous correct side, raw-injected seed files (read every
turn), highest-confidence fixes in the whole batch.

- Nora — #50 (Chicago vs. Seattle childhood, HIGH), #51 (hair shade/state)
- Bonnie — #54 (`setting.txt` stale urban geography, MED-HIGH), #55
  (seeds describe solo living, card describes cohabitation)
- Cass — #58 (age: 27 vs. "early 30s", HIGH), #59 (appearance groomed/warmer
  than card)
- Emily — #63 (Mika vs. Warren collision, HIGH), #64 (Dad-calls vs.
  Mom-calls, HIGH), #65 (card still says "coastal town", seeds say Olympia)
- Priya — #69 (tenure: 3 years vs. July 2026 move), #70 (Austin missing from
  card entirely)
- Jules — #73 (current job: taphouse vs. dealership, 2 of 5 greetings wrong),
  #74 (tattoo placement)
- Marcus — #76 (port Jules's anti-label header into `mes_example` as interim
  mitigation for the Code Track item)

**Deploy if accepted:** one `deploy/vps-sync.sh <instance>` per character
touched.

---

## Sprint 2 — Fleet preset.txt / shared layers **[owner-gate on most items]**
**Why second:** highest blast radius in the batch — several items are
cosmetic in `preset.txt` itself but load-bearing in `preset-core.txt`,
`preset-rp.txt`, or `preset-explicit.txt`, each feeding 5-7 bots.

1. #102 — `{{char}}` hard-coded female / `{{user}}` hard-coded male
   misgenders Marcus fleet-wide via `preset-core.txt`. **[owner-gate]**
   Start here: highest value, and `preset-marcus.txt` can absorb the fix
   without touching the shared file first if the owner wants a staged
   rollout.
2. #108 — paragraph-length default has no per-card arbitration clause;
   the gap only bites during a `PRESET_FILES` deploy-order failure, but when
   it does it silently reverts Bonnie/Priya to a contract their cards
   contradict. **[owner-gate]**
3. #104 — Dead Dove tone guide is ungated where its neighbor module isn't;
   affects Nora/Bonnie/Emily/Jules/Marcus via `preset-explicit.txt`.
   **[owner-gate]**
4. #103 — quotation-marks-only channel definition doesn't fit Priya/Cass's
   texting-only format. **[owner-gate]**
5. #105 — `[SCENE RHYTHM]`'s MOBA-jargon register names carry no meaning on
   their own; touches `preset-rp.txt` + `preset-stepped.txt` together.
   **[owner-gate]**
6. #106, #107 — duplicate rule text, `preset-core.txt` only, no behavior
   change intended. **Lowest-risk items in this sprint** — good place to
   start if easing into `preset-core.txt` edits for the first time.
7. #109 — unused autistic-character module, ~200 tokens fleet-wide.
   **Observation only — do not action.** Gated behind the still-open
   ROADMAP 3.13 content-split decision; revisit after that's settled, not
   before.

**Deploy if accepted:** `deploy/vps-sync.sh <instance>` per instance whose
`PRESET_FILES` includes the touched layer; `preset.txt`-only edits ship via
the fallback path only (see PROPOSALS §5 blast-radius note).

---

## Sprint 3 — Lorebook key tightening (pattern-level fix)

- #80 — lorebook entries keyed on words too common to stay rare, defeating
  their own "keep this rare" instruction. **Confirmed this pass** in Priya,
  Jules, Marcus (worst instance). **Unverified this pass, flagged as likely**
  in Nora ("left"), Bonnie ("alone"), Emily ("work"/"Seattle") — found in the
  2026-08-11 pass but not independently re-checked in this one.
  **Suggested sequence:** (a) re-verify the three unconfirmed characters
  first — cheap, closes the gap noted above — then (b) one fleet-wide pass
  tightening over-common keys to multi-word/phrase-anchored forms across all
  seven, since the shape repeats by character rather than being one card's
  bug.

---

## Sprint 4 — Remaining fleet polish (lower severity / structural notes)

- Nora — #52 (dropped freckles / invented detail), #53 (hard-gendered `his`
  in `schedule.txt`)
- Bonnie — #56 (stale alt-greeting count invites regression), #57 (dropped
  body-image beat)
- Cass — #60 (schedule reads orderly, card claims disaster), #61 (pronoun
  slip), #62 (second-person address)
- Emily — #66 (literal `[user]` in `schedule.txt`, has a proven leak path —
  worth pulling into Sprint 1 if the owner wants it fixed sooner), #67
  (habitat-vs-map tension), #68 (stale season reference)
- Priya — #72 (anti-fix note — **do not act**, recorded so a future pass
  doesn't "fix" this into a bug)
- Jules — #75 (`"mom"` lorebook key overlaps her own chirp bank — could also
  ride with Sprint 3)
- Marcus — #77 (worst instance of the Sprint 3 pattern — cross-reference,
  don't duplicate work), #78 (bookstore description inconsistency), #79
  (structural note only, no change proposed)

---

## Sprint 5 — Root SillyTavern presets (deploy nowhere — owner loads by hand)
**Why here:** genuine defects, but zero fleet exposure — these are the
owner's personal SillyTavern files, not anything `vps-sync.sh` touches.

**TheAtelier_2.0.json** — #82 (10 dial headers render empty), #83 (World
Bias header enabled with nothing selected), #84 (untagged length dial fights
two LAWs), #85 (untagged style list self-contradicts), #86 (double
reasoning: native + prompted `<think>`), #87 (smut dial vs. always-on NPC
agency), #88 (formatting), #89 (token-share observation), #90 (rule
triplication, ~1.5-2k recoverable tokens)

**UnifiedWritersRoom_V32.json** — prioritize #91 and #92 first, both would
be felt immediately on next load: #91 (`</think>` stopping string can eat
the visible reply), #92 (`nanogpt_model` empty — model slot unset). Then
#93-98 (contradictions: airy/low vocal-register rules, hard-coded
pro-{{user}} bias, dangling "RUT" reference, in-output markup MAIN forbids,
reasoning+pacing budget exceeds `max_tokens`), #99 (context-headroom
observation), #100 (cross-module duplicate bans), #101 (stale version string
in header).

---

## Sprint 6 — Inbox cards (optional — not live characters)
**Why last:** these are candidate cards in the review inbox, not anything
currently running. Apply only if/when the owner adopts one of these for
actual use — there's no urgency while they sit unused.

- SaskiaReyes.json — #1-8 (strongest of the five; the Margaret/Pak
  name-refusal inversion, #1, is the load-bearing one)
- VivienneGrey.json — #9-16
- main_michelle-scott-...json — #17-22
- Freaky Frankenstein Micro FF5.json (preset) — #23-32
- Megumin secret sauce v2.0 fix (3).json (preset) — #33-49

---

## Suggested order of operations

1. Code Track (#81) — file/flag for `coder` independently of the sprints;
   doesn't block or get blocked by anything below.
2. Sprint 1 — do first, no gate, highest confidence.
3. Sprint 3's verification step (re-check Nora/Bonnie/Emily keys) — cheap,
   closes an open gap, worth doing before or alongside Sprint 1.
4. Sprint 2 — start with #106/#107 (no owner-gate friction) to get a feel
   for `preset-core.txt`, then #102 (highest value) once ready for the
   owner-gated items.
5. Sprint 4 — pick up alongside Sprint 1 per-character, since it's the same
   files already open.
6. Sprint 5 — whenever the owner is next in SillyTavern loading these by
   hand; no fleet urgency.
7. Sprint 6 — only on adoption of a specific inbox card.

**Not sequenced above:** the 3 external ideas in `PROPOSALS-2026-08.md` §6
are advisory reading, not actionable items — no sprint slot needed.
