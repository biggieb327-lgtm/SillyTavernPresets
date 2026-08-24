# Functions audit — 2026-08-24

A research pass on how to improve the operating machinery a session runs with: the
agent contracts, the skills library, the hooks, and the evals. Prompted by "let's do
more research on how to improve your functions."

**Status 2026-08-24 — implemented in four sprints (commits on `claude/reviewer-agent-prompt-gamqk3`):**
Sprint 1 (S1, S2, S4, S5, A1) phone-era skill drift; Sprint 2 (E1) eval coverage
inversion; Sprint 3 (S3, H2) skill body-drift check + Stop-guard behavioral fixtures;
Sprint 4 (H1) delivery-gate second-stop bypass. Deliberately NOT done: A2 (`memory:`)
and A3 (`isolation: worktree`) — recommended against / situational. Open follow-up
surfaced during the work: `bot-code-invariants` says "six bots" and treats phone
platform rules (12–13) as live — the fleet is seven since 2026-07-29 and those rules
need a VPS review; left untouched because that skill governs every bot.py diff and the
change is the owner's call, not drift to silently rewrite.

Originally research only. Each finding is grounded in an external best-practice source (URL)
or a concrete repo location (`file:line`), and the load-bearing claims were verified by
reading the cited files, not taken on a subagent's word.

Method: external grounding via WebSearch/WebFetch (egress-limited — `anthropic.com` and
several hosts are blocked; `code.claude.com` and general search work); repo audit of
`.claude/agents/` (inline), `.claude/skills/` + `.claude/hooks/` + `.claude/evals/` (two
`general-purpose` agents), with the top claims re-read and quoted before inclusion.
Verification at time of writing: `bash .claude/evals/run-evals.sh` → 51 pass, 0 fail, 1
skip.

The through-line: this repo is **ahead of the field** on the things the multi-agent
literature says systems fail on — specification ambiguity (every agent has an "Inputs
required" clause), verification gaps (the reviewer stance + `qa-engineer` + "no done
without evidence"), and error propagation from agent shorthand (CLAUDE.md rule #4). The
leverage is not in adopting more machinery; it is in **closing holes in the machinery
that already exists** and **deleting drift**, which is anti-bloat-positive.

---

## Layer 1 — Advanced subagent frontmatter features

The Claude Code sub-agents doc exposes frontmatter this repo's agents don't use. Most do
not fit; two do.

- **A1 (do) — `skills:` preload for an always-first load.** `character-reviewer` says
  "Load `edit-cards-and-presets` **first**" (`.claude/agents/character-reviewer.md:14`);
  it loads on 100% of runs. Declaring `skills: edit-cards-and-presets` guarantees it and
  removes a remember-to-load failure mode. Weaker version: `coder`/`builder` →
  `bot-code-invariants`, but those edit non-bot code too, so preloading would load it on
  runs that don't touch `bot.py`. **Effort: S.** Source:
  https://code.claude.com/docs/en/sub-agents
- **A2 (don't) — `memory:` cross-session auto-memory.** The repo already has a superior
  memory layer (`.claude/memory/` — operational-log, constraints, mycelium, watchlist)
  that is version-controlled and guarded by evals + `session-audit.sh`. A parallel
  subagent auto-memory would drift and escape those mechanisms, violating "the repo files
  are the system of record." Recommend against adopting. Source:
  https://code.claude.com/docs/en/memory
- **A3 (situational) — `isolation: worktree`.** Only worth it if parallel *writing*
  agents are ever introduced; it mitigates the "globally incompatible parallel edits"
  pitfall the failure literature names. Not needed under the current "one microtask per
  dispatch" discipline. **Effort: S when needed.**
- **A4 (minor) — `maxTurns`** on the bounded agents (`research-scout`,
  `context-librarian`) as a cheap runaway guard complementing `budget-governor.sh`.
  **Effort: S.**

---

## Layer 2 — Skills library

The `skill-index-integrity` eval proves skills *exist* (router row ↔ dir, both
directions) but never reads a skill *body* or compares it to current repo reality. Every
finding below is invisible to it, and the suite is green. Sizes are healthy (largest is
`session-debrief` at 171 lines) — no split/oversize findings; the leverage is pruning
drift and dead skills. **All four drift claims below were verified by direct quote.**

- **S1 (do) — `repo-debugging-playbook` is phone-era, but the fleet is VPS/systemd.**
  `.claude/skills/repo-debugging-playbook/SKILL.md:8` opens "You cannot touch the phone,"
  routes evidence through Termux shell / `bot.log` / `watchdog.sh` / `adb` / `tmux`, and
  its description says "behaving wrongly on **the phone**." This is the skill loaded when
  a bot is actually down, and it hands the user commands that address nothing running.
  `deploy-and-verify-fleet` already carries the correct `journalctl -u bot@<instance>` /
  `systemctl` vocabulary to draw from. **Effort: M.**
- **S2 (do) — `artifact-first-delivery` states a dead deploy mechanism, and it loads on
  every deliverable.** `.claude/skills/artifact-first-delivery/SKILL.md:11`: "deploys
  pull from `main` via raw GitHub URLs" — false since the repo went private 2026-07-28
  (raw URLs 404; deploys run `vps-sync.sh` from the `.repo` checkout). Widest-reach drift
  in the library. **Effort: S** (one-line fix).
- **S3 (do) — add a body-drift check to `skill-index-integrity`.** A grep-based check
  flagging skill bodies that still say `phone`/`Termux`/`raw.githubusercontent`/`tmux`
  without a "historical" marker (mirroring the secret-scan's style) would have caught
  S1, S2, S4, S5 and would keep them fixed. This is "mechanisms over prose" applied to
  the skill library. **Effort: M** (check + an allowlist for legitimately-historical
  mentions). Source: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- **S4 (do) — `termux-device-ops` governs an empty phone and inverts its own scope.**
  `.claude/skills/termux-device-ops/SKILL.md:17` lists VPS as "the exception (cass,
  jules)" — but all seven are VPS now. Demote to an explicitly-historical appendix or
  delete, and repoint the router row. **Effort: S–M.**
- **S5 (do) — `vps-migration` is a finished project with a dead trigger and a stale
  privacy claim.** `.claude/skills/vps-migration/SKILL.md:3` fires on "the phone→VPS
  move" (finished 2026-07-29); line 29 still says "repo is public via raw URLs" (private
  since 2026-07-28). Archive it or gate it behind an explicit "only if adding an 8th
  instance" note. **Effort: S.**
- **S6 (consider) — `grilling`'s trigger is vague and overlaps a harness skill.**
  `.claude/skills/grilling/SKILL.md:3` triggers on "any 'grill' trigger phrases" without
  naming them (contrast `caveman`/`ponytail`, which enumerate exact phrases); its "before
  building" scope overlaps the harness `pre-build-pressure-test`. Enumerate the phrases;
  add one line disambiguating. **Effort: S.**

---

## Layer 3 — Hooks

External guardrail guidance converges on two gaps here: bypass-resistance and
firing-rate telemetry. **H1 and H2 verified by reading the files.**

- **H1 (do) — the Stop-gate chain fully bypasses on the second consecutive stop.**
  `delivery-gate.sh:10`, `host-guard.sh`, `handoff-guard.sh`, `claim-guard.sh`,
  `theory-guard.sh` all `exit 0` when `stop_hook_active=True`. So the stop *after* any
  block in the chain is not re-verified by these gates — a `bot.py` edit made during the
  forced continuation can end the turn ungated. `eval-gate.sh` already demonstrates the
  fix in-repo and documents exactly why it refuses the blanket bypass: a bounded
  per-session counter instead. **Effort: M.** (Confirm the precise exploitability —
  whether `version-changelog-sync` would still catch an unbumped version — during the
  fix.) Source: https://www.arthur.ai/blog/best-practices-for-building-agents-guardrails
- **H2 (do) — the four Python Stop-guards have zero behavioral coverage.** `run-evals.sh`
  confirms `host_guard.py`/`theory_guard.py`/`claim_guard.py`/`handoff_guard.py` *compile*
  and are *wired*, but nothing feeds them a payload and asserts they block/allow. All four
  "fail OPEN" (`theory_guard.py` docstring: "Fails OPEN on anything unexpected"), so a
  gutted regex that matches nothing passes every eval — the exact class `gate_corpus/`
  solves for `sweep.py`. **Effort: M.**
- **H3 (consider) — no hook emits firing telemetry.** `evidence-log.sh` logs tool calls
  but no hook records when it fires or exits 2, so nobody can tell whether the advisory
  guards (`host-guard`/`theory-guard`/`claim-guard`) ever block. You cannot prune or
  trust a guard whose real-world firing rate is unknown. **Effort: S.**
- **H4 (consider) — `hooks-wired` checks registration but not event/matcher.** A Stop
  guard mis-placed under `PreToolUse` counts as "registered" and passes green. **Effort:
  S.**

---

## Layer 4 — Evals

- **E1 (do) — coverage inversion: the retired phone runtime is heavily pinned; the live
  VPS runtime is pinned by nothing.** `heartbeat-alive` (`run-evals.sh:27`) guards
  `watchdog.sh`, which CLAUDE.md says "manages nothing" now; `venv-explicit-python`
  (`run-evals.sh:43`) guards phone-era `run-bot.sh`. Meanwhile
  `telegram-companion-bot/deploy/bot@.service` — the actual launch/restart path
  (`Restart=always`, `ExecStart=/opt/telegram-bots/venv/bin/python`) — is guarded by no
  eval; a regression to it ships green. Delete the two stale evals, add one small
  `bot@.service` grep. Net-negative lines. **Effort: S.**
- **E2 (consider) — `eval-gate`'s 120s Stop-hook timeout is a latent silent-pass.** The
  suite runs ~8s today; if it ever grows past 120s the hook is killed, and a killed Stop
  hook does not block — the turn ends unverified with no signal. Low urgency now. **Effort:
  S.**
- **E3 (consider) — `eval-parsers-fail-loudly` scans only `run-evals.sh`, not the hook
  wrappers that use the same heredoc pattern.** The fail-loudly discipline stops one
  directory short of the guard wrappers. Partly subsumed by H2. **Effort: S.**

---

## Recommended first actions (across all layers)

Highest leverage, cheapest, most anti-bloat first:

1. **S1 + S2 + S4 + S5 — fix/prune the phone-era skill drift.** Low-risk doc fixes; S1 is
   the one loaded under live incident pressure and S2 loads on every deliverable. Highest
   value-to-effort in the whole audit.
2. **E1 — delete the two phone-era evals, add a `bot@.service` guard.** Removes bloat and
   closes the biggest coverage gap; the live deploy path is currently pinned by nothing.
3. **S3 — add the body-drift check to `skill-index-integrity`.** The mechanism that keeps
   #1 fixed instead of re-drifting.
4. **H2 — give the four Python Stop-guards a `gate_corpus`-style behavioral fixture set.**
   Applies the repo's strongest doctrine ("a check that cannot fail is not a check") to
   its newest, currently-unverified layer.
5. **H1 — replace the blanket `stop_hook_active` bypass in `delivery-gate.sh` with
   `eval-gate.sh`'s bounded-counter pattern.** Structural hole in the flagship gate, fix
   already proven in-repo. Needs care + break-testing.
6. **A1 — `skills: edit-cards-and-presets` on `character-reviewer`.** One-line guarantee
   of an always-first load.

## Sources

- Claude Code sub-agents: https://code.claude.com/docs/en/sub-agents
- Claude Code memory: https://code.claude.com/docs/en/memory
- Claude Code hooks: https://code.claude.com/docs/en/hooks-guide
- Agent Skills best practices: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- Guardrail design: https://www.arthur.ai/blog/best-practices-for-building-agents-guardrails
- Why multi-agent systems fail (MAST): https://galileo.ai/blog/why-multi-agent-systems-fail
- When multi-agent is overkill: https://www.augmentcode.com/guides/when-multi-agent-ai-is-overkill
