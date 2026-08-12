---
name: skill-router
description: Index of available skills and when to load each. Consult this instead of preloading everything — load skills on demand.
---

Load a skill only when its trigger fires. **Nothing here arrives on its own.** Only the
one-line description of each skill reaches you for free; every body must be loaded. Until
2026-07-30 this file exempted `artifact-first-delivery` and `repo-validation-gate` from
that rule, asserting they were already in context — they were not, so the exemption
suppressed the two skills that apply most often. Both are ordinary rows below. See F1 in
`.claude/SCAFFOLDING-AUDIT-2026-07-30.md`; the `skill-index-integrity` eval now rejects any
such exemption.

| Trigger | Load |
|---|---|
| Producing any deliverable — before deciding where output goes | `artifact-first-delivery` |
| Before claiming ANY change is done | `repo-validation-gate` |
| Stress-testing a plan or design before building | `grilling` |
| Any bot.py change that will ship (feature, fix, refactor) | `repo-change-control` |
| Reviewing or writing any bot.py diff (also loaded by repo-change-control) | `bot-code-invariants` |
| A live bot is misbehaving, restarting, or silent | `repo-debugging-playbook` |
| The cause looks device-level (SIGKILL/137, venv, tzdata, pkg upgrade), or you're touching watchdog/backup/cleanup | `termux-device-ops` |
| Editing an `.env`, choosing/changing a model, or working on note follow-ups, day threads, or the shared world | `bot-config-reference` |
| The work is written and needs to become a deployed release (sequencing only) | `ship` |
| Work is merged; user needs to get it onto the fleet, or a deploy went wrong | `deploy-and-verify-fleet` |
| Editing character cards, seed files, preset.txt, or root SillyTavern presets | `edit-cards-and-presets` |
| A fix is about to ship, or a check/eval is being written | `fix-the-class` |
| Same failure class happened twice, or user asks to pin a check | `add-regression-eval` |
| Session is done and green, or the user is wrapping up — harvest lessons before context closes | `session-debrief` |
| External audit/review output (LLM or human) lists claimed bugs | `verify-external-audit` |
| Writing a tool that renders a verdict, reporting a finding, or explaining why something broke | `hubris` |
| Touching any GROUP_* code, the ledger, or bot-to-bot behavior | `group-chat-changes` |
| Moving instances from the phone to a VPS (ROADMAP 1.2) | `vps-migration` |
| Working in voicekit-starter/ | `voicekit-work` |
| Designing unattended/overnight iterative work (a Routine, /loop, or autonomous session) | `unattended-loops` |
| User asks for terse/caveman-mode chat replies, or invokes /caveman | `caveman` |
| User asks for Doc Brown mode, or invokes /doc-brown | `doc-brown` |
| User asks for the laziest/minimal-code solution, YAGNI mode, or invokes /ponytail | `ponytail` |
| Anything else | Check `ListSkills`/`SearchSkills` for harness-provided skills (code-review, verify, security-review, update-config, …) — prefer those over improvising |

Rules:
- One skill at a time; finish applying it before loading another.
- If a needed skill doesn't exist and the need has come up twice, that's a finding for `improvement-analyst` — a candidate for a new skill, written by `system-fixer`.
- New skills added under `.claude/skills/` must be registered in this table in the same change, or they're invisible tomorrow.
- **And the reverse:** every skill named in this table must exist on disk AND be
  model-invocable. A row for a skill that is missing, or that sets
  `disable-model-invocation`, is an index entry pointing at nothing — the `grill-me` alias
  was exactly that until 2026-07-30. Both directions are now pinned by the
  `skill-index-integrity` eval.
