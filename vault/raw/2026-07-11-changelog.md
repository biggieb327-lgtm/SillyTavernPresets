# Raw capture: CHANGELOG.md (head)

Source: `telegram-companion-bot/CHANGELOG.md` @ commit `d76dcdf`. Verbatim excerpts.

> Entries are newest first. Each one names the actual root cause, not just the code
> diff — that's the part worth reading twice, since re-diagnosing a solved problem
> from scratch is exactly what this file is meant to prevent.

Newest release at capture: `## v2026-07-11.6 — R6 evolution experiments (all gated,
default off)` — reaction feedback (`FEEDBACK_REACTIONS=1`), closeness score
(`CLOSENESS_ENABLED=1`), open threads (`THREADS_ENABLED=1`), joke candidates
(`JOKE_CANDIDATES=1`).

> All four features default off and have zero per-message LLM cost (reactions are
> local, closeness is a formula, threads/jokes piggyback on the existing
> post-reply analysis call that already runs).

Preceding heads: v2026-07-11.5 (R5 UX: /status tail, /quietwin recurring quiet
windows), v2026-07-11.4 (R4 prompt hygiene: `_trim_history_to_budget`, lore dedupe,
persona-break guardrail, summarization semaphore).

Version scheme: `YYYY-MM-DD.N`; changelog release headings are `## v<BOT_VERSION>`
and must match bot.py's `BOT_VERSION` exactly (eval `version-changelog-sync`).
