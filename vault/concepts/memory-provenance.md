# Memory provenance

**Idea:** generated content must never enter a fact store unlabeled. Anything the
system invents either stays out of memory or carries a marker that every consumer
honors.

- Origin incident: the character's own generated "day" fiction was archived into
  recent_facts unmarked, presented as shared history, and promoted to permanent
  facts weekly — hallucinated memories asserted to the user
  ([raw/2026-07-11-operational-log.md]).
- Realized as: the `[own-day …]` prefix + per-consumer handling (v2026-07-10.2);
  R1 extended it to source-attached memories with quote grounding and a review
  queue ([raw/2026-07-11-claude-md.md], [raw/2026-07-11-changelog.md]).
- Reused beyond the bot: this vault's own routing rule (raw → entities/concepts
  with citations) is the same discipline (`vault/INDEX.md`).
