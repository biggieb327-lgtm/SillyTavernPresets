# Vault index

> **This repository is PUBLIC** (deploys pull raw URLs from main). Anything placed
> in this vault is world-readable the moment it's pushed. No personal data, no
> credentials, no private notes — the secret-scan eval catches token shapes, not
> sensitive prose.

## Layout

- `raw/` — unprocessed captures. Append-only; dated filenames
  (`YYYY-MM-DD-<slug>.md`); never edited after capture, only distilled out of.
- `entities/` — one file per durable thing (person, project, place, system).
  Filename is the entity name; facts carry their source (link to the raw note).
- `concepts/` — one file per reusable idea or pattern. Cross-link to the
  entities and raw notes that ground it.

## Routing rule

New material lands in `raw/` first. Promotion into `entities/` or `concepts/` is
a deliberate edit that cites the raw note it came from — the same provenance
discipline the bot's memory system uses (unlabeled generated content never enters
a fact store).

## Status

Scaffold created 2026-07-11; conventions above are a proposal — rewrite freely.
