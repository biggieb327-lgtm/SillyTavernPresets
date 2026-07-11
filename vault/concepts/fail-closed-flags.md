# Fail-closed feature flags

**Idea:** every new feature ships behind config where *unset means today's
behavior* — so the flag doubles as the kill switch, and a fresh instance is safe
by default.

- Realized as: all four R6 experiments default off; group chat requires three
  explicit env vars and ignores groups fleet-wide otherwise; R4's token budget
  defaults to 0 = disabled ([raw/2026-07-11-changelog.md],
  [raw/2026-07-11-group-chat-design.md]).
- Extends to config robustness: bad numeric env values warn and fall back rather
  than crash — a typo must never brick the fleet ([raw/2026-07-11-claude-md.md]).
- Operational payoff: a misbehaving release is disabled from the phone by editing
  one env line and `/restart`, no code rollback needed
  ([raw/2026-07-11-improvements-plan.md]).
