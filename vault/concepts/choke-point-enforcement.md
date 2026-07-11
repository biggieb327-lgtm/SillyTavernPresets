# Choke-point enforcement over hand-kept lists

**Idea:** enforce a boundary at one structural point (a choke point or an
allowlist-built function), never by enumerating all the places that could violate
it — enumeration goes stale against a large codebase.

- Origin: group-chat design review rounds 1–2 each found a flat-file write path a
  hand-kept inventory had missed ([raw/2026-07-11-operational-log.md]).
- Realized as: `_group_deliver` built from an allowlist (its body may contain none
  of the DM tail's side effects) + `GROUP_ALLOWED_COMMANDS` default-deny — both
  pinned as class-level CI evals ([raw/2026-07-11-run-evals.md]).
- Same shape elsewhere: all model output through `_do_request`'s strip/repair
  stack ([raw/2026-07-11-bot-py-facts.md]); numeric env parsing through
  `_env_int`/`_env_float` ([raw/2026-07-11-claude-md.md]).
- Corollary: widening a pinned boundary is a reviewed act — edit the eval in the
  same commit with rationale ([raw/2026-07-11-run-evals.md]).
