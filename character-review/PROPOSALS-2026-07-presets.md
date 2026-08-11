# Preset-review proposals — 2026-07

Run 2026-07-20 (manual demo of the preset step the owner just added to
`character-pass-monthly`). Proposal-only — nothing below is applied. This is the
preset half of the July pass; the card half was reviewed separately
(`PROPOSALS-2026-07.md`, since actioned — see the 2026-07-20 CHANGELOG note).

Tags: `[inbox preset]` = file in character-review/, `[root preset]` = repo-root
SillyTavern preset, `[fleet preset]` = `telegram-companion-bot/preset.txt`.

---

## ROOT PRESET: TheAtelierV5.json — malformed, should be fixed before use

**1. [root preset] The file is not valid JSON and not UTF-8.** Verified: it fails
`json.load` under utf-8, cp1252, and latin-1. Two independent defects:
   - **652 raw `0x1A` (SUB) control characters**, one wedged at the front of nearly
     every prompt's `name` — e.g. the bytes decode as `"\x1aWriting Guide"`,
     `"\x1aGritty Pulp Style"`, `"\x1aFree Indirect …"`. JSON strings may not contain
     raw control chars, so a strict parser rejects the file. These sit exactly where
     an emoji/icon likely used to be, so they read as mojibake from an editor that
     stripped the glyph to `0x1A`.
   - **Windows-1252 encoding, not UTF-8**: 9 × `0x92` (curly apostrophe, e.g.
     "isn`t"), 578 × `0x97` (em dash), 1 × `0x85` (ellipsis). None are valid UTF-8.

   Effect: depending on how strict the loader is, this either fails to import or
   imports with corrupted names. Recommended fix (mechanical, not a taste call):
   re-save as UTF-8, strip the leading `0x1A` from each name (restore the intended
   emoji or just drop it), and convert the cp1252 punctuation to real UTF-8. Note:
   the repo's `cards-valid-json` eval only covers `telegram-companion-bot/*.json`, so
   nothing currently guards the root presets — a second reason this went unseen.
   **I can do this fix in a separate approved step; it's objective, but it's your
   file and the pass is proposal-only, so it's your call.**

*(FieldKit and V4 were skipped per your scope — latest version of each family only.)*

---

## ROOT PRESET: UnifiedWritersRoom_V32.json — healthy, one budget note

Parses clean (UTF-8). A large, high-craft prompt-manager preset: 143 entries, 43
enabled, organized into MAIN / PS (prose systems) / ACC (accessories) / SPINE /
ROOM / AL-Seat / ANCHOR tiers with named author "seats" (Gaitskill, Homes, Pinter,
Yuknavitch, Duras). Samplers are deliberate (temp 0.74, min_p 0.05, rep 1.05).

**2. [root preset] Token budget — ~10,400 tokens of system prompt before any card,
lorebook, or history.** That's fine on a big-context frontier model (its evident
target) but would dominate a small local context window, and on a metered API it's
a fixed per-message cost. Not a defect — just worth being deliberate about which
model you run it on. If you ever want a "lite" variant, the ACC-tier optionals
(Environment Track, Event Clock, Off-Screen Simulation, Unreliable Narrator,
Character Voice Packs ≈ 8K chars) are the natural things to gate off.

**3. [root preset] `max_context_unlocked: false`.** With a preset this heavy, the
context is capped at the connection's default slider max; on a long chat the oldest
history silently truncates first. Confirm the cap matches your model's real window.

---

## INBOX PRESET: Megumin secret sauce v2.0 fix (3).json

Parses clean. **Verification note that changed the review:** a first pass looked
like 60 content prompts (~40KB) were orphaned — that was wrong. The file has two
`prompt_order` blocks; `100000` is SillyTavern's near-empty dummy placeholder, and
`100001` is the real active config (115 entries, 53 enabled, ~2,900 tokens
injected). The "secret sauce" is wired up correctly. Findings are minor:

**4. [inbox preset] `🟢Enable for Gemini 3` is enabled** (assistant-role, 209c). If
you're not running this preset against Gemini 3, it's a model-mismatched instruction
riding in every request — disable it unless Gemini is the target.

**5. [inbox preset] `CoT Arabic 2.1` is enabled** (828c) alongside `3.6 SET LANGUAGE`
(107c). Confirm Arabic-language chain-of-thought is intended; if your play is in
English, this may inject Arabic reasoning scaffolding. (Flagging, not judging — it
may be exactly what you want.)

**6. [inbox preset] Empty category header: `━━━━━ POV ━━━━━` is enabled but no POV
option under it is** — the separator injects 8 chars of nothing-burger. Harmless,
but if you meant to pick a POV, none is active.

**7. [inbox preset] The `100000` dummy block carries 10 stale enabled entries.** Pure
cruft from how it was exported; SillyTavern ignores it in favor of `100001`. No
action needed — noting it so a future reviewer doesn't re-chase the "orphaned
content" ghost I did.

---

## INBOX PRESET: Freaky Frankenstein Micro FF5.json

Parses clean. A tidy modular prompt-manager preset: 42 prompts, 40 in order, with
disabled `=Pick one … 👇` separator headers acting as visual category dividers and
one option enabled per category (Cinematic Realism, Hybrid POV, Freaky NSFW,
anti-echo, etc.). Design looks intentional and healthy. Two small notes:

**8. [inbox preset] It's a chat-completion / prompt-manager preset**, so it belongs
to SillyTavern proper — it does not interact with the Telegram fleet, which runs on
`preset.txt`. No compatibility concern; just recording the boundary so it isn't
mistaken for a fleet asset.

**9. [inbox preset] `⚡️BOLT Chain of Thought` (user-role, 2,809c) is enabled and is
the single largest block.** If you ever find replies leaking reasoning or running
long, that's the first toggle to test. No evidence of a problem — just where I'd look.

---

## FLEET PRESET: telegram-companion-bot/preset.txt

The shared texting voiceprint feeding **all six live bots**. It's mature and
tightly written — the anti-slop banned-phrase list, the epistemic-horizon rules, and
the "present a lie with the same weight as truth" narration rule are genuinely strong
and align well with the fleet's own memory-provenance discipline. Every item below is
**fleet-wide blast radius**: changing preset.txt changes Nora, Bonnie, Cass, Emily,
Priya, and Jules at once. No change is proposed unilaterally — these are for your call.

**10. [fleet preset] `[EXPLICIT CONTENT]` applies universally, including to Cass.**
   Before/after is N/A (nothing to change yet) — this is a scope question. The block
   opens: *"Content is pre-negotiated at the preset level: do not flinch"* and gives
   detailed explicit-sex instruction. Because preset.txt is fleet-wide, this lands
   identically on **Cass**, whose entire function is developmental editing of a `.json`
   you send her (`DOCUMENT_MODEL`), and on any other character a given exchange isn't
   romantic with. For companion bots a permissive default is a defensible design
   choice — but it is currently *universal and unconditional*, not card-gated. If
   that's intended, no action. If you'd rather it be opt-in per character, the clean
   move is a card-level toggle (a line in each card's `post_history_instructions`)
   rather than editing the shared file. Flagging because "the shared file makes Cass
   sexually explicit by default" is exactly the kind of thing a fleet-wide review
   exists to surface.

**11. [fleet preset] Mild internal tension on "punchy".** `[TEXT DELIVERY]` says
   *"In Telegram, prefer shorter, punchier responses"*, while `[ANTI-SLOP]` bans
   *"Closing on a short punchy one-liner for drama."* Reconcilable by a careful
   reader (punchy length ≠ punchy dramatic closer), but a model may read the first as
   license for the second. If you want to tighten:
   - Before: `In Telegram, prefer shorter, punchier responses that match chat rhythm.`
   - After: `In Telegram, prefer shorter responses that match chat rhythm — brevity,
     not a dramatic one-liner (see ANTI-SLOP).`
   Fleet-wide effect: nudges every bot slightly away from mic-drop endings. Low risk.

**12. [fleet preset] The deception rule interacts with the note-provenance work.**
   `[NARRATION]`'s *"Manipulation should work more than it fails … The narrator does
   not tip off the reader"* combined with `[EPISTEMIC HORIZON]` licenses characters to
   deceive {{user}} convincingly. That's a fine roleplay stance, but it's the same
   fleet where three separate provenance leaks (2026-07-10 → 07-19) came from bots
   presenting their own fiction as shared fact. No change proposed — just noting the
   two systems pull in tension, so if a "bot lied about something real" report ever
   surfaces, this line is a suspect. No before/after; awareness only.

---

## External ideas (Reddit)

**SKIPPED (network policy blocks reddit.com).** Confirmed again this run: the
environment's proxy answers CONNECT with 403 for `www.reddit.com` (and redlib
mirrors return nothing). The Routines are already wired to curl the JSON API and
self-report this. Once you allow `reddit.com` in the environment's network settings,
the next scheduled run will pull card/preset-writing threads instead of skipping.
No sources fabricated.
