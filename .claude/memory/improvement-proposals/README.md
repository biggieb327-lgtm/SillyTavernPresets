# Improvement proposals

**The `improvement-loop-monthly` Routine that wrote here is retired (2026-08-22)** — the
scheduled work moved to ChatGPT. Nothing writes to this directory any more, and a stale
directory is now the expected state rather than a missed run.

What is here is that Routine's past output: at most one proposal per run, `<YYYY-MM>.md`,
originally committed only to the `claude/improvement-loop` branch and never to `main`
directly. Its prompt is preserved in `.claude/operating/routines.md` (historical).

A proposal must contain: the recurring failure pattern, the ≥2 quoted occurrences
(with dates/versions) from `.claude/memory/operational-log.md` /
`telegram-companion-bot/CHANGELOG.md`, exactly one proposed patch (file + change),
and the eval that would prove it worked.

Lifecycle: the owner reviews the branch; accepted proposals are implemented by
`system-fixer` in a reviewed session (never by the Routine itself), then the
proposal file is either updated with the outcome or removed when the change lands
in the operational log. Months with no qualifying pattern write nothing.
