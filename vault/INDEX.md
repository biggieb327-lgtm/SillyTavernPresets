# Vault index

> **This repository is PUBLIC** (deploys pull raw URLs from main). Anything placed
> in this vault is world-readable the moment it's pushed. No personal data, no
> credentials, no private notes — the secret-scan eval catches token shapes, not
> sensitive prose.

Built 2026-07-11 from git-tracked repo files only, pinned at commit `d76dcdf`.
Routing rule: new material lands in `raw/` first; promotion into `entities/` or
`concepts/` cites the raw note it came from. Claims that could not be verified
from the repo are marked `UNCERTAIN` inline.

## raw/ — untouched source captures (path + commit pin + verbatim excerpts)

- `2026-07-11-claude-md.md` — CLAUDE.md: architecture, invariants, instance table, stack.
- `2026-07-11-changelog.md` — CHANGELOG head: R4–R6 releases, version scheme.
- `2026-07-11-operational-log.md` — every incident row that changed the system.
- `2026-07-11-run-evals.md` — the 14 eval checks and the pinned group boundaries.
- `2026-07-11-group-chat-design.md` — design section map, platform constraint, config posture.
- `2026-07-11-improvements-plan.md` — ground rules and standing verification block.
- `2026-07-11-ops-manual-deploy.md` — the four deploy paths, ops commands, rollback.
- `2026-07-11-roadmap-audit.md` — track status, rejected-ideas registry, audit verdict stats.
- `2026-07-11-migration-runbook.md` — VPS migration phases and the one-poller rule.
- `2026-07-11-characters.md` — all six character notes, cards, seeds, preset.txt.
- `2026-07-11-voicekit.md` — voicekit-starter purpose, packaging, no-tests status.
- `2026-07-11-bot-py-facts.md` — measured bot.py facts: size, version line, choke point, model slots.

## entities/ — one page per durable thing

- `bot-py.md` — the single-file fleet codebase and what services it.
- `termux-phone-host.md` — current production host and its Android hazards.
- `vps-target.md` — the next host: systemd, one-poller rule, pilot sequence.
- `nanogpt-api.md` — the LLM provider: model-slot constraints, retry ladder, streaming quirks.
- `agent-operating-layer.md` — .claude/ hooks, evals, skills, memory files.
- `voicekit-starter.md` — the separate CLI project and its three-file contract.
- `nora.md` — default instance; world generator; the diverged root-copy caveat.
- `bonnie.md` — personality-section order is load-bearing.
- `cass.md` — editor character; needs the instruction-model DOCUMENT slot.
- `emily.md` — integration-heavy: WSDOT traffic, Inworld voice, vision.
- `priya.md` — lowercase register; real-Bellevue geography rule; group pilot.
- `jules.md` — meaner-when-fond register; group pilot; VPS migration pilot.

## concepts/ — one reusable idea per page

- `single-file-deploy.md` — one file, one URL, one .bak: deploys runnable from a chat command.
- `memory-provenance.md` — generated content never enters a fact store unlabeled.
- `one-combined-analysis-call.md` — background LLM work rides one call as JSON keys.
- `choke-point-enforcement.md` — enforce at one structural point, never by enumeration.
- `incident-pinned-evals.md` — checks exist because something real broke; break-test new ones.
- `evidence-before-fixes.md` — cheapest discriminating observation first; instrument opaque errors.
- `fail-closed-flags.md` — unset env = today's behavior; the flag is the kill switch.
- `verify-then-fix-external-claims.md` — per-claim verdicts with line evidence; rejected claims recorded.
