# Improvement proposals

Write target of the `improvement-loop-monthly` Routine (schedule + verbatim prompt:
`.claude/operating/routines.md`). Each run writes **at most one** proposal here as
`<YYYY-MM>.md`, committed only to the `claude/improvement-loop` branch — never to
`main` directly.

A proposal must contain: the recurring failure pattern, the ≥2 quoted occurrences
(with dates/versions) from `.claude/memory/operational-log.md` /
`telegram-companion-bot/CHANGELOG.md`, exactly one proposed patch (file + change),
and the eval that would prove it worked.

Lifecycle: the owner reviews the branch; accepted proposals are implemented by
`system-fixer` in a reviewed session (never by the Routine itself), then the
proposal file is either updated with the outcome or removed when the change lands
in the operational log. Months with no qualifying pattern write nothing.
