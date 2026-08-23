# 2026-08-01 — priya topic not recalled

Archived from `.claude/memory/operational-log.md` on 2026-08-21, verbatim. The row
there is the index entry; this is the full record, including every correction
appended after the fact.

## Failure

**Priya re-surfaced a two-day-old topic in conversation as if she'd never been told.** Owner-reported live symptom, no crash, no error — a memory-quality defect.

## Root cause

`_summarize()`'s prompt had no instruction against fusing two different things into one fact. `[observed]` `/recall costco` turned up the actual stored fact: *"Costco food court trip: 'in and out like a bad lover'—Priya called it self-reporting; Brian corrected it was a simile"* — three things (the trip, a line she said, an argument about categorizing the line) folded into one run-on sentence, confusing enough that later recall couldn't cleanly reference "this already happened." `[code]` checked whether a weak background model was the cause first (precedent: `v2026-07-29.3`'s `SUMMARY_MODEL`-writes-captions bug) — ruled out: `priya/.env` has no `SUMMARY_MODEL` override, so it ran on her own `glm-5.1:thinking` chat model, a strong reasoner. The gap was `bot-code-invariants` #17's extraction-honesty discipline (confidence gating, quote grounding, null-over-guess) existing for `user_notes.txt` but never extended to the `recent_facts`/summary pipeline.

## System patch

`v2026-08-01.5`: both `_summarize()` and `_consolidate_facts()` now require each fact to describe ONE concrete thing in one sentence, resolvable without cross-referencing another fact, and forbid fusing an event with commentary about it just because they share a topic. `_consolidate_facts` also keeps two facts as two rather than force a merge when they don't reduce cleanly, since repeated consolidation passes compound this error with no way to re-check against messages once they've scrolled out of context. Prompt-only; no new call, no kill switch (a defect fix, not optional behavior).

## Eval

`TestFactAtomicity` pins the constraint text in both function sources; both assertions break-tested RED independently (constraint removed from each function in turn, confirmed the matching test failed) before being trusted. 715/715 pytest, 32/32 evals.

## Next

**Not yet confirmed the fix actually stops the behavior** — it targets the mechanism that produced the one bad example in hand, but there's no way to verify "does she stop doing this" without watching real conversation over the next several days. Also open: `MOOD_MODEL`/`REACTION_MODEL` are both unset for priya too, defaulting to the cheap `glm-4.7-flash` — unrelated to this specific fact (that pipeline writes `user_notes.txt`, not `recent_facts`), but if wonkiness shows up there too, check that slot next rather than re-deriving this same investigation. **Update 2026-08-01:** `[observed]` owner ran `/dupefacts` (v2026-08-01.6) against priya post-deploy — came back clean, no near-duplicate facts above the 0.92 threshold. Confirms the auto-merge dedup considered and declined earlier in this same investigation was correctly not built speculatively: the hypothesized problem (reworded near-duplicates accumulating across consolidation passes) isn't actually present, at least not yet, at least not for her. Does **not** confirm the original symptom is fixed — that's a different question (does she stop re-surfacing old topics as new) still answerable only by watching real conversation over time, not by this diagnostic. **Closed 2026-08-04:** `[observed]` owner confirmed, at the scheduled circle-back, zero recurrences of the original symptom since the fix shipped — explicitly not "improved," a clean "no recurrences." The fusion fix resolved the reported behavior, not merely reduced it. `MOOD_MODEL`/`REACTION_MODEL` (still unset, defaulting to `glm-4.7-flash`) remain unchanged — the observation window that would have justified touching them found nothing to act on. No further follow-up scheduled.

