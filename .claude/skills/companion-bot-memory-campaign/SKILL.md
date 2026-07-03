---
name: companion-bot-memory-campaign
description: >
  The executable, decision-gated campaign to give the telegram-companion-bot characters the
  deepest possible long-term memory — recall that feels human and never contradicts itself.
  Load this skill whenever: the owner reports "she forgot X", "she misremembered", "she brought
  up the wrong thing", "she contradicted herself", or any recall-quality complaint; you are
  changing ANY memory layer (summarization, recent_facts, episodic recall/embeddings, lorebook,
  memories.txt, untrusted notes, milestones); you are touching /remember /forget /delmem
  /memory /recall /exportmemory or investigating dual-store confusion; you are designing memory
  probes, measuring recall rate, or deciding which memory layer to tune next. Do NOT use for:
  quick live triage of a symptom (companion-bot-debugging-playbook), general architecture
  questions (companion-bot-architecture-contract), interpreting diagnostic command output in
  isolation (companion-bot-diagnostics), or commit/deploy rules (companion-bot-change-control).
---

# Companion-bot memory campaign

Ground-truth date: **2026-07-02**. All line numbers refer to
`/home/user/SillyTavernPresets/telegram-companion-bot/bot.py` (~8,900 lines) at HEAD of branch
`claude/push-to-repo-7i2f3c` on that date. Verify line numbers with grep before editing; the
symbol names are the stable handles.

**Mission:** the deepest long-term memory achievable on this stack — recall that feels human
and never contradicts itself. **Success must be measured, not vibed.** Every phase below has a
gate: expected observations you must record before advancing, and branch rules for when the
observations disagree with the plan.

**The fenced-off failure mode of this entire campaign:** tuning a layer before you know which
layer is failing. A "she forgot X" report is compatible with at least four different root
causes in four different layers (Phase 2). Fixing the wrong layer burns a deploy cycle,
perturbs the baseline, and teaches you nothing. No code change to any memory layer until
Phase 1 baseline data exists.

---

## 0. What is already settled — do NOT redo this work

The `fix-bot-py` dead-branch reconciliation was **completed 2026-07-02** (full record:
`.claude/skills/companion-bot-failure-archaeology/SKILL.md`, section 0 and section 2). Summary,
so you never re-diff that branch:

- ALL memory-audit fixes from `fix-bot-py` are verifiably present in HEAD, ported via
  `d0bc024` ("Apply 13 efficiency and performance fixes") and `1a4d067` ("Fix 5 confirmed
  bugs from high-effort code review").
- ONE change was ported and then **deliberately reverted**: the `break → continue` change in
  the memory token-budget loops. HEAD uses `break` on purpose — `continue` let low-relevance
  memories fill budget slots after a high-relevance-but-oversized entry was skipped, violating
  the relevance-first guarantee of the descending sort. **Settled forever.** Do not "fix"
  `break` to `continue` in a memory budget loop.
- Verdict from the archaeology: "fix-bot-py is safe to ignore. Zero lost fixes."

Also settled (archaeology sections 2.1–2.3):

- Extraction stores **concrete third-party facts only** — never psychology, predictions, or
  feelings about the owner/relationship (the attitude-poisoning incident). Any new extraction
  path must route through the `_MEMORY_REJECT` filter and the proper-noun grounding check.
- Extraction prompts must never contain concrete example names (hallucinated-"Bob" incident).
- Embedding-input truncation lives INSIDE `_embed()` (`EMBED_MAX_CHARS`); never truncate at
  call sites.

**Therefore this campaign does NOT start with archaeology or reconciliation. It starts at
instrumentation (Phase 1).**

---

## 1. Ground truth: the eight-layer memory stack

Per-instance state lives in each bot's own directory (`~/<char>-bot/` on the device); the code
is shared `bot.py`. Layers, innermost to outermost:

| # | Layer | Code handles | Persistence | Key knobs |
|---|-------|--------------|-------------|-----------|
| 1 | Verbatim conversation window | `conversation_history` dict (~1409); scroll logic ~4360 | `state.json` (`STATE_FILE`, ~1507; atomic tmp-then-replace write ~1601) | window/scroll thresholds in code |
| 2 | LLM summarization on scroll | `_summarize` call inside the scroll path (~4364); consolidated per-turn extraction (`259889d`) | `state.json` summary + facts | — |
| 3 | Recent/situational facts | `recent_facts` dict (~1416); cap enforcement ~4377; compaction toward `RECENT_FACTS_TARGET` ~4381 | `state.json` `recent_facts` | `RECENT_FACTS_MAX` (default 30, ~4304) |
| 4 | Episodic recall (semantic) | embedded archive of scrolled-off turns, built at scroll time (~4371); `_embed()` ~620; reranker ~1032; docs: `telegram-companion-bot/docs/EPISODIC_RECALL.md` (accurate as of this date) | episode + vector files beside state.json; model identity in `EPISODES_MODEL_FILE` | `EMBED_MODEL` (~362, opt-in), `EMBED_DIM` (~364), `EPISODIC_RECALL` (~378, default on when embeddings on), `RERANK_MODEL`/`RERANK_CANDIDATES` (12)/`RERANK_ENDPOINT` (~394–397) |
| 5 | Lorebook keyword triggers | `character_book` entries loaded from the card (~1349–1351) | character card JSON | keyword coverage is authored, not learned |
| 6 | memories.txt NPC/world store | region starts ~349; `MEMORIES_FILE`, `triggered_memories` (keyword RAG, ~2127), `_append_memory`, `_memory_lock` | `memories.txt` per bot | `MEMORIES_MAX` (default 200, ~353) |
| 7 | Untrusted-notes quarantine | `_note_untrusted` (~1495), `_mem_service` from `bot_app` (~1440–1459), `untrusted_context_block` injection (~3269) | `state.json` `untrusted_notes` | `MAX_UNTRUSTED_NOTES`; attachment-derived text NEVER enters trusted history |
| 8 | Milestones / pins / on-this-day | `milestones` dict (~1419), nightly `update_milestones` (~2496), `milestone_note` (~3083); on-this-day gated on episodic recall (~405) | `state.json` `milestones` | `MILESTONES_MAX` (30, ~1306), `ONTHISDAY_ENABLED` |

**Cache-identity trap (real bug, fixed `7c205bd`):** vector caches are keyed by
`EMBED_CACHE_KEY = f"{EMBED_MODEL}|dim={EMBED_DIM}"` (~368). Before that fix, changing
`EMBED_DIM` alone left stale wrong-length vectors in the cache. Any new vector store you add
MUST key on `EMBED_CACHE_KEY`, never on `EMBED_MODEL` alone.

**Memory-editing commands** (registered ~8746–8764): `/remember`, `/forget`, `/delmem`,
`/memory`, `/recall`, `/exportmemory`, plus diagnostics `/episodes` and `/diag`.
**Dual-store confusion incident:** the owner's `/delmem` targeted the other store (facts vs
memories.txt) than the one holding the offending entry; cross-pointer hints were added in
`1996735` ("cross-point /delmem and /forget on no-match"). When the owner says "I deleted it
and she still remembers", check BOTH stores before concluding deletion is broken.

Everything a memory layer injects converges in `assemble_messages` (~3170). Position within
that assembly is itself a memory variable — a fact retrieved but buried is a fact forgotten
(Phase 2, class D→C distinction).

---

## 2. Command hygiene: two command classes

Every command in this campaign is one of:

- **DEVICE commands** — pasted by the owner into his chat client, which **strips `$...$`
  spans**. Device commands must contain **zero dollar signs**: no `$VAR`, no `$(...)`, no
  `$HOME` (use `~`). Full paste-corruption rules: companion-bot-device-ops.
- **REPO commands** — run here in the cloud repo. `$` is fine.

Label every command you emit with its class. A device command with a `$` in it will silently
mangle and the owner will run garbage.

---

## Phase 0 — Inventory (repo-side, zero risk)

Goal: a written layer map for the specific bots you will baseline, so probe results can be
interpreted.

1. Confirm the table in section 1 against HEAD: **(repo)**
   `grep -nE "RECENT_FACTS_MAX|EPISODIC_RECALL|EMBED_CACHE_KEY|MEMORIES_MAX|character_book|untrusted|milestones" telegram-companion-bot/bot.py`
2. Read the four diagnostic command handlers (`memory_cmd`, `recall_cmd`, `episodes_cmd`,
   `diag_cmd` — find via `grep -n 'async def \(memory\|recall\|episodes\|diag\)_cmd' bot.py`)
   and write down **exactly what each prints and from which store(s)**. Do not trust prose
   descriptions, including this file's. `/recall` is the campaign's primary retrieval
   instrument; you must know whether its output reflects layer 3, 4, 6, or a merge, and
   whether it exercises the same query path a live turn does. If it does NOT exercise the
   live retrieval path, note the divergence — probe results via `/recall` then only bound,
   not equal, live behavior.
3. Record per-bot config: which of the 6 instances (nora, bonnie, cass, emily, jules, priya)
   have `EMBED_MODEL` set (layer 4 on), which have `RERANK_MODEL`, and their knob values.
   Ask the owner or have him run (device, no `$`):
   `grep -h -E "EMBED_MODEL|EMBED_DIM|RERANK|EPISODIC|RECENT_FACTS|MEMORIES_MAX" ~/nora-bot/.env ~/bonnie-bot/.env ~/cass-bot/.env ~/emily-bot/.env ~/jules-bot/.env ~/priya-bot/.env`

**Gate to Phase 1:** the layer map exists, per-bot knob table exists, and you know precisely
what `/recall` measures. **Branch rule:** if the bots differ materially in config (e.g. some
lack embeddings), choose baseline bots that span the difference — one with layer 4 on, one
without.

## Phase 1 — Measurement harness (NEW work; nothing like it exists today)

Be honest in all communication: there is **no probe harness in the repo as of 2026-07-02**.
You are designing it, not finding it.

**Probe fixture** = a 4-tuple: *(planted fact, delay, probe question, expected recall)*.
Example: plant "my sister Kate is moving to Denver in August" in normal conversation; after
delay D, probe with "where is Kate headed again?"; expected: Denver (and August is bonus
precision). Design 15–25 fixtures per baselined bot, stratified across:

- **Fact type:** third-party fact (routes to memories.txt), owner-situational fact (routes to
  recent_facts/summary), emotional/relationship moment (milestones), a fact later
  *superseded* by a correction ("actually Kate chose Portland") — the supersession fixtures
  feed the contradiction and staleness metrics.
- **Delay:** same-session (within the verbatim window), post-scroll (hours/next day), and
  long (≥1 week; ≥30 days is the Phase 4 milestone but the baseline can't wait that long —
  mine EXISTING old facts from `state.json`/`memories.txt`/episodes as retrospective long-delay
  probes: pick facts with known timestamps and probe them now).
- **Probe surface:** two measurement channels per fixture where possible —
  `/recall <query>` output (retrieval-layer measurement) and a live conversational probe
  (end-to-end measurement). Divergence between the two channels is itself a Phase 2 signal.

**Metrics** (per bot, per fact type, per delay bucket):

- **Recall rate** — probes answered with the planted fact / total probes.
- **Contradiction rate** — pairs of probes eliciting mutually incompatible answers / pairs
  tested (ask the same fact two ways, hours apart).
- **Staleness rate** — probes where a superseded fact is recalled over its replacement /
  supersession fixtures tested.

**Execution:** baseline **2–3 bots** BEFORE any tuning. Keep a plain fixtures file + results
log in the repo (this is repo work; commit per companion-bot-change-control). Probes are sent
by the owner from his phone — batch them into short scripts of messages, all device-class
(no `$`), and keep per-probe timestamps so results correlate with `bot.log` lines.

**Gate to Phase 2:** baseline numbers recorded for 2–3 bots across all three metrics, every
failed probe annotated with its raw evidence (what `/recall` showed, what the reply said,
what `state.json`/`memories.txt` contained). **Branch rules:** if baseline recall is already
≥90% with zero contradictions, the owner's complaints are about a specific fact class —
re-stratify fixtures toward the complained-about class before proceeding. If `/recall` and
live-probe channels disagree wildly, that IS your Phase 2 headline finding.

## Phase 2 — Failure taxonomy (classify every failed probe; no fixes yet)

Every failed probe from Phase 1 gets exactly one class. Each class routes to a DIFFERENT
layer. This routing is the point of the whole campaign.

| Class | Definition | Discriminating check | Routes to |
|-------|-----------|----------------------|-----------|
| **A. Never stored** | Fact absent from every store | Is the fact in `state.json` (summary/facts/recent_facts), `memories.txt`, or the episode archive at all? Grep the files (device: `grep -i kate ~/nora-bot/memories.txt ~/nora-bot/state.json` — no `$`). If NO → class A. | Extraction (layer 2/6 write path) |
| **B. Stored, not retrieved** | Fact present in a store, but `/recall <query>` (and the live turn) misses it | Fact IS in a file, but `/recall` with a natural query does not surface it. Check: keyword miss (memories.txt store) vs embedding miss (episodic) — try `/recall` with the fact's own literal words; if literal words hit but paraphrase misses, it's a query/embedding-coverage problem. | Retrieval (layer 4/5/6 read path) |
| **C. Retrieved, not used** | `/recall` (or logs) shows the fact was injected, but the reply ignores it | Fact surfaces in `/recall` and appears in the assembled context, yet the conversational probe fails. | Salience/position in `assemble_messages` (~3170) |
| **D. Retrieved wrong** | A stale or contradictory version is recalled | The reply asserts the superseded value, or two probes contradict. Check whether BOTH versions coexist in the stores (they will — nothing supersedes today). | Provenance/supersession (no such mechanism exists yet) |

Run the checks in A→B→C→D order per failed probe; the first failing check classifies it.

**Gate to Phase 3:** every baseline failure classified, with a per-class count. **Branch
rule:** the class with the highest count gets fixed first — regardless of which fix is most
interesting to build. If class counts are near-uniform, fix A first (upstream of everything).

## Phase 3 — Solution menu, RANKED per class, with obligations

Pick interventions matching your dominant Phase 2 class. One intervention per deploy cycle,
so effects are attributable. Each carries obligations you may not skip.

- **(a) Extraction tuning** — for class A. The consolidated per-turn extraction call
  (`259889d`) is the choke point; tune its prompt/gates there, not by adding a second
  extraction path. *Obligations:* every change must keep the `_MEMORY_REJECT` filter and
  proper-noun grounding (settled, section 0); no concrete example names in prompts; re-run
  the class-A fixtures plus a garbage-memories spot check (archaeology 2.1 — this subsystem
  regresses in creative ways).
- **(b) Retrieval tuning** — for class B. Sub-options in order of cheapness: query
  construction for episodic recall; activating the reranker on bots that lack it
  (`RERANK_MODEL` env, zero code); widening lorebook keyword coverage on the card (authored
  fix, per-character); alias expansion in memories.txt (the `[aka: ...]` mechanism already
  exists — archaeology 2.3). *Obligations:* any embedding-side change respects
  `EMBED_CACHE_KEY` invalidation; measure retrieval precision too, not just recall — flooding
  context with weak matches trades class B for class C.
- **(c) Salience/position** — for class C. Move or reformat memory blocks within
  `assemble_messages` (~3170). *Obligations:* read companion-bot-architecture-contract's
  prompt-layering order first; this function feeds ALL six bots — A/B it (Phase 4), never
  blanket-deploy; verify token-budget loops still `break` (settled).
- **(d) Fact provenance + supersession** — for class D, and the ONLY real fix for
  contradiction/staleness. Timestamps on facts at write time; on write, a contradiction check
  against existing facts; newer supersedes older. *Obligations:* **define supersession
  semantics on paper BEFORE coding** — what counts as "the same fact" (entity+attribute
  match? embedding similarity?), whether superseded facts are deleted or archived-with-tombstone,
  and how `/forget`/`/delmem` interact with tombstones (do not create a third store for the
  dual-store trap to triple). Get owner sign-off on the semantics document.
- **(e) Periodic consolidation pass** (nightly rewrite/merge of stores) — **LAST RESORT.** It
  touches every layer at once, destroys attributability of all other interventions, and an
  LLM rewriting the whole store can corrupt everything at once. Only after (a)–(d) have been
  measured and found insufficient, and only with pre/post store snapshots.

**Gate to Phase 4:** one intervention implemented on a branch, validated per
companion-bot-validation-and-qa (compile gate + AST-extraction dry run of changed functions),
and NOT yet deployed to all bots.

## Phase 4 — Validation and promotion

1. **A/B across the 6 instances:** deploy the intervention to 2–3 treated bots; the rest are
   controls running unchanged code. (Note the standard `update-all.sh` flow deploys `bot.py`
   to ALL bots — an A/B needs either an env-flag gate on the new behavior, per-bot `.env`
   toggles being the cleanest mechanism, or a coordinated manual deploy; design this with
   companion-bot-device-ops and get owner buy-in first.)
2. Re-run the full probe suite on treated AND control bots after **≥1 week** of live use.
3. Compare against Phase 1 baseline per metric, per class.
4. Promote (deploy to all bots) via **companion-bot-change-control** only if treated bots
   beat controls on the targeted metric without regressing the others.

**Falsifiable campaign milestone:** a fact planted ≥30 days prior is retrieved in **≥9/10
probes** on treated bots; contradiction rate **0** in a 20-probe audit; control bots
measurably worse on the same suite. If controls match treated bots, the intervention did
nothing — revert it, return to Phase 2 with the new data.

**Branch rules:** metric regressed on treated bots → revert, log the attempt in
companion-bot-failure-archaeology, pick the next-ranked intervention. Targeted metric
improved but another regressed → treat as a new Phase 2 classification round on the
regressed metric before deciding.

---

## Provenance and maintenance

- Ground truth: `bot.py` at HEAD of `claude/push-to-repo-7i2f3c`, `git log`, and
  `.claude/skills/companion-bot-failure-archaeology/SKILL.md`, all read 2026-07-02; every
  commit hash above verified with `git log` that day.
- Line numbers drift with every bot.py commit — grep the symbol names; update this file's
  table when they move materially.
- After each phase gate, append the recorded observations (baseline numbers, class counts,
  intervention outcomes) to this file so the campaign is resumable by a zero-context session.
- Reverted or failed interventions belong in companion-bot-failure-archaeology, cross-linked
  here.
