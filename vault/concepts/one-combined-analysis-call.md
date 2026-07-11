# One combined analysis call

**Idea:** on a constrained link, background LLM work rides one existing call as
extra JSON keys — never a sibling call per message.

- Realized as: `post_reply_analysis` carries mood + notes + memory + (since R6)
  thread updates and joke candidates in one response
  ([raw/2026-07-11-claude-md.md], [raw/2026-07-11-changelog.md]).
- Why: side calls compete with the user-facing reply for phone bandwidth; the
  constraint is the phone's uplink, not API cost
  ([raw/2026-07-11-improvements-plan.md]).
- Proof it scales: R6 shipped four features with zero added per-message LLM cost
  by extending the JSON ([raw/2026-07-11-changelog.md]).
