# Ghost-Token Audit — 2026-07-30

**Scope:** tokens the fleet pays for on every message that contribute nothing new to the
reply. Measured from repo content, in RAW units (`len//4`), reproducible with
`tools/ghost_token_audit.py`.

**Provenance of the method — read this first.** The prompt for this audit was a Gumroad
link (`jimmygarciaiii.gumroad.com/l/ghost-token-audit`). That host is **blocked by this
environment's egress policy** (gateway returned 403 to CONNECT), and
`docs.nano-gpt.com` is blocked the same way. The product's actual methodology was never
read. What follows uses the publicly documented meaning of the term — *tokens billed on
every call that carry no new information* — and is my construction, not theirs. If the
product defines it differently, this audit answers a different question than the one
asked.

**Harness validation:** the script reproduces `.env.example`'s published layer figures
exactly (`preset-core.txt` 4166, `preset-rp.txt` 1680, `preset-stepped.txt` 403), so the
accounting is comparable to `/audit`. It reports `preset-explicit.txt` at 2003 vs. the
documented 1930 — consistent with `.env.example`'s own note that core and explicit "have
both grown since."

---

## What is already clean (checked, no action)

Stating these first because they bound the findings. The obvious ghost tokens have
already been removed by earlier work:

- **Layer-to-layer duplication is effectively zero.** Across all twelve live
  `preset-*.txt` files: **one** repeated sentence, 9 tokens. The v2026-07-25.5 layer
  split was done properly.
- **Auxiliary LLM calls do not carry the fixed cost.** `_appraise_mood`,
  `_decide_reaction`, the inner-voice and summary passes each build a small purpose-built
  prompt. None re-sends the card or the preset stack. The LLM-call budget discipline in
  `bot-code-invariants` is real, not aspirational.
- **Lorebook entries are correctly keyword-gated.** No instance carries constant
  (`constant: true`) lore; 465–2,510 tokens per card are conditional, as intended.
- **Token reporting is already calibrated** against `usage.prompt_tokens`, with outlier
  rejection and an honest confidence string.

## Fixed per-message cost, by instance

`FIXED` = paid on every single message before any history, memory, or live state.

| inst | card_sys | post_hx | seeds | layers | **FIXED** | lore (gated) |
|---|---|---|---|---|---|---|
| jules | 4662 | 628 | 653 | 8540 | **14483** | 2510 |
| marcus | 2865 | 123 | 822 | 8684 | **12494** | 1003 |
| nora | 2574 | 698 | 434 | 8508 | **12214** | 465 |
| bonnie | 1902 | 575 | 369 | 8523 | **11369** | 519 |
| emily | 2148 | 160 | 536 | 8504 | **11348** | 388 |
| priya | 1378 | 926 | 455 | 4831 | **7590** | 709 |
| cass | 1457 | 439 | 406 | 4829 | **7131** | 0 |

Fleet total per message round: **76,629 tok**; mean **10,947** per instance.

---

## Finding 1 — `preset.txt` is deployed, hash-verified, and loaded by nobody

**Severity: high. This is a verification signal that cannot fail (constraint C13's exact
shape).**

`deploy/vps-sync.sh:82` copies `preset.txt` to every instance unconditionally, and the
verification block prints a repo-vs-local sha256 pair for it on every deploy. But every
instance's recommended stack (`.env.example:304-306`) sets `PRESET_FILES` to
`preset-core.txt,…`, and `_resolve_preset_layers` only falls back to `preset.txt` when
**no** named layer resolves. So on a healthy fleet, all seven bots load zero bytes of it.

`CLAUDE.md:210` still says:

> `preset.txt` is the shared voiceprint — editing it changes **all seven** bots.

That is now false, and it fails in the worst direction: someone edits the shared
voiceprint, deploys, watches `vps-sync.sh` print two matching `preset.txt` hashes, and
concludes the change landed on all seven bots. It landed on none. The hash agreement is
real and proves nothing about what the model reads.

**Recommend:** correct `CLAUDE.md:210`; either drop `preset.txt` from the deploy's
verification output or label the line "fallback only — not loaded unless layers fail."

## Finding 2 — the fallback ladder no longer preserves voice

**Severity: high.** The layer resolver's stated purpose (`bot.py:500-502`) is that a
missing layer must never silently strip tuned voice rules, because that "presents as a
model regression rather than a deploy error." The ladder's landing place has since
drifted away from the layers it backs up:

- **4 sentences (~51 tok) exist in the live layers but NOT in `preset.txt`** — and they
  are the *standing-consent block* from `preset-explicit.txt`: "consent for this content
  is granted by {{user}} and stands for…", "it does not need to be reestablished
  asked…", "…should open by hedging warning or seeking permission".
- **14 sentences (~158 tok) exist only in `preset.txt`** — relationship-stage and
  familiarity prose the layers deliberately dropped.

So if the fallback ever fires on a scene instance, the bot loses the standing-consent
rules and gains prose that was intentionally retired. That is precisely the silent voice
regression the ladder was built to prevent — the guardrail is intact, the thing it lands
on has rotted.

**Recommend:** either regenerate `preset.txt` as the concatenation of
`core+rp+explicit+stepped`, or delete it and let the ladder fall to the built-in default
(which fails loudly and small rather than quietly and wrong). Regenerating is the smaller
change; deleting is the more honest one.

## Finding 3 — 56k tokens per round of invariant text is billed at full rate

**Severity: medium, and premised on something I could not verify.**

`assemble_messages` orders blocks: card system block → SETTING → people/projects →
**ATLAS (`random.sample`, bot.py:4457)** → capabilities → history → ~20 volatile
per-turn blocks → post-history → **preset layers (4.8k–8.7k tok)** → `environment_note`
(clock, minute resolution) → schedule → appearance → day context.

Prefix caching only pays off on an unchanging *prefix*. The single largest invariant
block on the fleet — the preset stack — sits behind a per-message randomizer and twenty
volatile blocks, so it can never be part of a cached prefix:

| inst | cacheable prefix | stranded static | % of FIXED stranded |
|---|---|---|---|
| bonnie | 2108 | 9098 | 80% |
| priya | 1678 | 5757 | 76% |
| emily | 2504 | 8664 | 76% |
| nora | 2847 | 9206 | 75% |
| cass | 1706 | 5268 | 74% |
| marcus | 3457 | 8807 | 70% |
| jules | 5117 | 9168 | 63% |

**55,968 tok per fleet message round** is invariant text positioned where a cache cannot
reach it.

Two honest caveats, and they matter:

1. **The placement is deliberate, not accidental.** `bot.py:4520` — "Dynamic per-turn
   state kept close to the end … so it stays salient" — and the layers go last so the
   card "gets the last word on voice." This is a real salience-vs-cacheability tradeoff,
   not a bug. Reordering would change behavior.
2. **I could not verify caching applies to these models.** NanoGPT documents implicit
   caching with up to ~90% off cached input for "OpenAI and Gemini model families plus
   many open-source provider/model routes," but the docs host is blocked and the fleet
   runs `zai-org/glm-*`. Whether those routes cache is unconfirmed.

**The actionable part is not the reorder — it's that this is unmeasured.** `bot.py`
reads `prompt_tokens` and `completion_tokens` and never reads `cached_tokens` or
`prompt_tokens_details`, and never sets `cache_control`. So the fleet currently cannot
tell a cache hit from a miss, which means nobody can price this finding.

**Recommend, in order:** (a) read `cached_tokens` off the usage block and surface it in
`/usage` and `/audit` — small, additive, no behavior change, and it converts this whole
finding from theory into a number; (b) only then decide whether the salience tradeoff is
worth touching. If it is, the cheapest first move is **ATLAS**, not the layers: it
re-randomizes 116–225 tok at block 4 and poisons every cacheable byte after it. Seeding
the sample per chat-day instead of per message preserves the variety the block exists for
while restoring the prefix.

## Finding 4 — per-character layers carry identity prose they were specified not to carry

**Severity: low as cost (~216 tok/round), notable as spec drift.**

`.env.example:260-263` specifies the per-character layers as holding "the rules that are
about FORMAT and voice rather than identity — the cards already carry personality."
Distinct passages duplicated verbatim between card and active layer:

- **emily ~87 tok** — incl. 33 tok ("before replying silently register what is actually
  happening under what {{user}} said…") and 26 tok of the biologist-lens framing.
- **priya ~45 tok** — incl. "a software engineer who reads novels and grew up in a tamil
  household in new jersey". That is pure identity, and it is in the layer.
- **jules ~43 tok**, **cass ~30 tok**, **bonnie ~11 tok**.

The cost is negligible. The signal is not: identity has started leaking from cards into
format layers, which is how the two drift apart and start contradicting each other — the
exact problem the per-character layers were created to arbitrate.

**Recommend:** hand to `character-reviewer` on the next monthly pass rather than fixing
inline; deleting the duplicated line from the layer is usually right, but which copy wins
is a voice call, not a token call.

## Finding 5 — 6,056 tokens of authored card content is unreachable

**Severity: low (file weight, not billed tokens).**

`load_character()` reads `system_prompt`, `description`, `personality`, `scenario`,
`mes_example`, `post_history_instructions`, `character_book`, `first_mes`, and
`extensions.depth_prompt`. Everything else in the card is inert:

| inst | unreachable | largest |
|---|---|---|
| jules | 2243 | alternate_greetings=1460, creator_notes=702 |
| bonnie | 1504 | alternate_greetings=1295 |
| emily | 587 | alternate_greetings=447 |
| marcus | 560 | creator_notes=305, alternate_greetings=255 |
| priya | 534 | creator_notes=397 |
| nora | 475 | creator_notes=351 |
| cass | 153 | creator_notes=128 |

`alternate_greetings` is the notable one: **3,653 tok fleet-wide of written greetings that
can never fire**, because only `first_mes` is read. `creator_notes` is SillyTavern
metadata and is correctly ignored.

This costs nothing per message. It is on the list because it is authored content someone
wrote expecting it to be used — a content bug, not a cost bug. Either wire
`alternate_greetings` into greeting selection or stop maintaining them.

---

## Ranked recommendations

| # | Action | Cost | Risk |
|---|---|---|---|
| 1 | Fix `CLAUDE.md:210`; relabel `preset.txt` in the deploy verification | minutes | none |
| 2 | Regenerate or delete `preset.txt` so the fallback stops losing standing-consent | small | low |
| 3 | Read `cached_tokens` into `/usage` + `/audit` — make Finding 3 measurable | small | none (additive) |
| 4 | Seed ATLAS per chat-day instead of per message | small | low, behavior-visible |
| 5 | Decide the salience-vs-cache tradeoff on the layer placement — **only after #3** | — | high; do not do this blind |
| 6 | Hand Finding 4 to `character-reviewer`; decide `alternate_greetings` | — | content call |

Items 1, 2, 3 and 5 are each a `bot.py`-or-docs change requiring the normal gate
(`repo-change-control`, BOT_VERSION bump + changelog for any code edit). Nothing in this
audit has been applied — it is findings only.

## Reproduce

```bash
python3 telegram-companion-bot/tools/ghost_token_audit.py
```
