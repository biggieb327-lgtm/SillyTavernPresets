---
name: bot-code-invariants
description: The code-level rules every bot.py diff must satisfy — concurrency, output choke point, LLM-call budget, memory provenance, phone constraints. Load whenever writing OR reviewing a bot.py change, alongside repo-change-control.
---

# bot.py invariants

Check the final diff against every rule. These are pass/fail, not suggestions.

## When NOT to use

- Non-bot.py files (cards, docs, shell scripts, .claude/) — nothing here applies.
- Reading bot.py to answer a question — no diff, nothing to check.

## The rules

**Architecture**
1. bot.py stays ONE file. Never propose splitting it (recorded non-goal).
2. One instance = one directory passed as `sys.argv[1]`; never hardcode an instance
   path or name into shared logic.

**LLM call budget (phone bandwidth)**
3. NO new per-message LLM side calls. The single combined `post_reply_analysis`
   call is the extension point: add JSON keys to it. A sibling call competes with
   the user-facing reply for phone bandwidth.
4. New model-response paths MUST route through the `_do_request` choke point so
   output passes `_strip_thinking` + `_strip_native_tool_calls` + `_fix_mojibake`.
   A path that bypasses it will eventually send raw `<tool_call>` XML or mojibake
   to the user (both happened).
5. Streaming error bodies: keep the `_ = resp.content` force-read before
   `raise_for_status()` (eval-pinned). Replicate the pattern in any new HTTP code.

**Concurrency (v2026-07-10.2 fixes; regressions here corrupt state silently)**
6. State serialization happens on the event loop only — worker threads hand
   `save_state` back via `call_soon_threadsafe`, never call it directly.
7. Never iterate live state dicts from a worker thread (snapshot on the loop first).
8. Never call bare `requests` in an async handler — wrap in `asyncio.to_thread`.
9. Never hold the group-ledger flock across an `await`.

**Memory provenance (the 2026-07-10 hallucination bug)**
10. Generated content (day events, reflections, anything the character invents)
    must NEVER enter user-fact stores unlabeled. The `[own-day …]` prefix +
    per-consumer handling (`_OWN_DAY_PREFIX`) is the template — new generated
    content either stays out of memory or carries a marker every consumer honors.

**Platform (Termux/Android)**
11. No new OS processes (the phantom-process killer SIGKILLs at >32 system-wide;
    six bots already sit near the limit). No subprocess spawns, no `tee`, no
    background helpers.
12. `/tmp` is not writable on Termux — instance dir or `~/` for temp files.
13. The `_touch_alive` repeating job must stay registered (eval-pinned) — removing
    it makes watchdog.sh restart the healthy fleet forever.
14. Shutdown work goes in `post_shutdown`, never `signal.signal()` — PTB's
    `run_polling()` silently overrides signal handlers (eval-pinned).

**Config**
15. Numeric env parsing goes through `_env_int`/`_env_float` (bad values warn and
    fall back — a typo must never brick the fleet).
16. New features default ON, but MUST ship with an env kill switch (owner policy,
    2026-07-18). Unset env = feature active; setting the flag to 0/off disables it
    without a redeploy when a release misbehaves on-device. The kill switch is
    mandatory — a feature with no way to turn it off is the violation now, not a
    default-on one. (Higher-cost or higher-risk behavior may still default off with
    a one-line rationale; when in doubt, ask the owner.)

## Quality bar

Every rule checked against the *final* diff (not the plan). If a rule must be
broken, that's a design conversation with the user before the code exists — say
which rule, why, and what replaces its protection.

## Verification checklist

- [ ] Grepped the diff for `requests.` inside `async def` handlers
- [ ] Any new model-output path traced back to `_do_request`
- [ ] Any new memory write traced: does generated content reach a user-fact store?
- [ ] No new `subprocess`/`Popen`/process spawn
- [ ] `.env.example` documents new vars; defaults preserve current behavior
- [ ] `bash .claude/evals/run-evals.sh` green (several rules here are eval-pinned)

## Common mistakes

- Adding a "small, cheap" second LLM call for a new feature (rule 3 has no
  small-call exception — R6 shipped four features on zero extra calls).
- Writing extracted "facts" from model output straight into memory files without
  provenance (rule 10) because the immediate feature works fine without it.
- Using `signal.signal` for cleanup because it works in local testing (rule 14 —
  PTB overrides it only at run_polling time).

## What to report back

For a review: rule-by-rule verdict, only listing rules that are implicated by the
diff. For authored code: which rules the diff brushed against and how each was
satisfied.
