---
name: skill-router
description: Index of available skills and when to load each. Consult this instead of preloading everything — load skills on demand.
---

Load a skill only when its trigger fires. Preloaded always (do not re-load): `artifact-first-delivery`, `repo-validation-gate`.

| Trigger | Load |
|---|---|
| Stress-testing a plan or design before building | `grilling` (alias: `grill-me`) |
| Any bot.py change that will ship (feature, fix, refactor) | `repo-change-control` |
| Reviewing or writing any bot.py diff (also loaded by repo-change-control) | `bot-code-invariants` |
| A live bot is misbehaving, restarting, or silent | `repo-debugging-playbook` |
| Work is merged; user needs to get it onto the fleet, or a deploy went wrong | `deploy-and-verify-fleet` |
| Editing character cards, seed files, preset.txt, or root SillyTavern presets | `edit-cards-and-presets` |
| Same failure class happened twice, or user asks to pin a check | `add-regression-eval` |
| External audit/review output (LLM or human) lists claimed bugs | `verify-external-audit` |
| Touching any GROUP_* code, the ledger, or bot-to-bot behavior | `group-chat-changes` |
| Moving instances from the phone to a VPS (ROADMAP 1.2) | `vps-migration` |
| Working in voicekit-starter/ | `voicekit-work` |
| Designing unattended/overnight iterative work (a Routine, /loop, or autonomous session) | `unattended-loops` |
| Anything else | Check `ListSkills`/`SearchSkills` for harness-provided skills (code-review, verify, security-review, update-config, …) — prefer those over improvising |

Rules:
- One skill at a time; finish applying it before loading another.
- If a needed skill doesn't exist and the need has come up twice, that's a finding for `improvement-analyst` — a candidate for a new skill, written by `system-fixer`.
- New skills added under `.claude/skills/` must be registered in this table in the same change, or they're invisible tomorrow.
