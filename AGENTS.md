# Codex entrypoint

This repository already has a durable, versioned context system. Use it in place; do not duplicate its facts into a second project-memory store.

## Read order

1. Read `CLAUDE.md` at the start of every task. It is the canonical project instruction set, documentation map, authority order, and deployment policy.
2. For non-trivial work, read `.claude/OPERATING_MANUAL.md`.
3. Read `.claude/skills/skill-router/SKILL.md`, then load only the skill(s) it routes to for the task.
4. For multi-step, behavior-changing, or fleet-touching work, read `.claude/operating/fable-to-opus.md` and `.claude/memory/constraints.md` before acting.
5. For a current broad view, read the newest `.claude/operating/HANDOFF-*.md`. Treat its numbers as a dated snapshot; runtime output and current code win.

Do not create a second quick-reference documentation map. `CLAUDE.md` and the skill router own that routing layer; copied maps drift.

## Context retrieval rules

- Retrieve context by task. Do not preload large logs, handoffs, the roadmap, or unrelated skills.
- Prefer runtime output for live state; then current code and configuration; then `CLAUDE.md` and the relevant canonical document; then dated handoffs or audits.
- If the Notion Fleet Knowledge Base is available, search relevant `Status=current` entries before non-trivial work. The repo's reviewed memory files remain the system of record.
- `vault/` is a pinned 2026-07-11 archive, not current source of truth. Use it only for historical provenance or when the task explicitly needs that snapshot.
- The bot's runtime memory is its own engine. Do not add Mem0 or another runtime memory backend unless the task explicitly approves a migration plan and verification.

## Memory ownership

- `.claude/memory/operational-log.md`: bot, deploy, or fleet failures that changed the system.
- `.claude/memory/constraints.md`: mistakes made while performing the work.
- `.claude/operating/routines.md`: scheduled routine prompts; keep it synchronized with any live Routine change.

Record durable findings in their owning source, not in this file. Never write secrets or live credentials into repository context files.

## Response style

- Lead with the answer or outcome.
- Use short sentences, familiar words, and active voice.
- Default to a few short paragraphs or bullets. Add detail only when it helps the user decide or act.
- Avoid jargon. When a technical term is necessary, explain it in one plain sentence.
- Do not repeat the request, narrate routine steps, or add generic caveats.
- Use headings, tables, and diagrams only when they make the answer easier to scan.
- Keep important risks, uncertainty, and verification results even when the response is brief.
- Ask one focused question only when missing information would materially change the result.

## Completion

Follow the verification and delivery rules in `CLAUDE.md` and the selected skills. Report the commands actually run, distinguish verified facts from assumptions, and leave out-of-scope findings as follow-ups rather than silently expanding the change.
