# skillforge

A small, runnable implementation of **WikiSkill** — a loop that turns agent
experience into persistent knowledge and validation-gated skills — plus the
objective **skill-quality benchmark** the gate needs to mean anything.

> Based on: **WikiSkill: Compiling Agent Experience into Persistent Knowledge for
> Skill Evolution.** Liyan Tang, Cyrus Rashtchian, Chun-Sung Ferng, Andrew
> Tomkins, Da-Cheng Juan, Tu Vu. Google Research / Virginia Tech.
> arXiv:2608.27454v1 [cs.AI], 27 Aug 2026. CC BY 4.0.
>
> All credit for the method, the three-layer architecture, Algorithm 1, and the
> agent designs belongs to the authors. This is an independent study
> reimplementation, not affiliated with Google.

## This is a separate project

`skillforge/` lives in the SillyTavernPresets repo the way `voicekit-starter/`
does: **none of the bot rules apply** (no `BOT_VERSION`, no CHANGELOG gate, no
fleet deploy), and it never reads or writes the `.claude/` memory layer. It is a
research artifact you run by hand.

## What it does

The three layers with different lifecycles (paper §3.1):

```
raw/     immutable execution traces          (permanent, write once)
wiki/    patterns/ + index.md + logs.md      (compounding, NEVER rolled back)
         + skill-impact.md
skills/  <name>/SKILL.md                       (reversible, conditional)
```

The loop (Algorithm 1), one iteration:

1. **Inference Agent** runs the training tasks with the active skills injected —
   and *no* wiki access.
2. **Wiki Maintainer** does root-cause analysis on a stratified sample of
   pass/fail traces and patch-edits the wiki (and its index + log).
3. **Skill Proposer** (ReAct) reads the wiki index, `skill-impact.md`, and the
   task outcomes, inspects patterns/traces on demand, and emits **one atomic
   skill change**.
4. **Gating**: the change is accepted only if validation accuracy *strictly*
   improves; otherwise the **skills** roll back — the **wiki never does**. Every
   attempt, accepted or rejected, is appended to `skill-impact.md` with its diff,
   score, and outcome, so the proposer won't repeat a failed edit.

Early stop when validation hits 1.0.

## The skill-quality benchmark

`benchmark.py` + `tasks/demo_tasks.jsonl`. A benchmark is a set of tasks, each
with an input, a ground-truth answer, a split (train/val/test), and a
**deterministic** grader (exact / contains / regex — never an LLM judge alone,
per App. C). The validator runs any `agent(prompt) -> text` callable and returns
accuracy, so the *same* benchmark scores the offline mock and a real model
identically. The demo tasks teach two conventions a skill must supply (a house
date format and a release-tag format), and the suite includes a
`test_benchmark_is_skill_sensitive` check so the validator provably *can* fail.

## Run it

Offline, deterministic, no network (this is what CI and the tests run):

```bash
cd skillforge
PYTHONPATH=src python3 -m skillforge bench          # describe the benchmark
PYTHONPATH=src python3 -m skillforge demo           # run the full loop offline
PYTHONPATH=src python3 -m pytest -q                 # 31 tests
```

Against a real OpenAI-compatible model (e.g. NanoGPT, the endpoint this repo
already uses):

```bash
export SKILLFORGE_API_KEY=...   # or OPENAI_API_KEY
PYTHONPATH=src python3 -m skillforge evolve \
  --workspace ./run1 --model <model-name> \
  --base-url https://nano-gpt.com/api/v1 --iterations 5
```

### Honesty note

The offline demo uses a deterministic `MockLLM` so the **harness mechanics** —
gating math, skills-only rollback, the never-rolled-back wiki, the audit trail,
early stop — are reproducible and testable. It is **not** evidence that LLM skill
evolution "works"; that claim is the paper's, and reproducing it needs a real
model via `evolve`.

## How this maps to the rest of the repo

This repo's `.claude/` machinery already is a hand-built WikiSkill: the
`operational-log`/`constraints`/`decisions` files are the wiki's pattern pages,
`.claude/skills/` + `.claude/evals/` are the gated skill layer, and CI is the
gate. The one piece it lacked was WikiSkill's **`skill-impact.md`** — a single
ledger tying *a change to the machinery* to *whether the failure it targeted
stopped recurring*. `skillforge` is where that idea is implemented and tested in
isolation; whether to graft the ledger into `.claude/memory/` is a separate call.

## Layout

```
skillforge/
├── src/skillforge/
│   ├── benchmark.py     # tasks, deterministic graders, evaluate() -> Score
│   ├── workspace.py     # three layers + patch engine + skills snapshot/rollback
│   ├── llm.py           # LLM protocol, MockLLM, OpenAI-compatible client, extract_json
│   ├── prompts.py       # agent system prompts (adapted from paper App. E)
│   ├── agents.py        # InferenceAgent, WikiMaintainer, ReAct SkillProposer
│   ├── gating.py        # strict-improvement gate + skills-only rollback + audit trail
│   ├── orchestrator.py  # Algorithm 1
│   ├── demo.py          # deterministic offline brain
│   └── cli.py           # demo | bench | evolve
├── tasks/demo_tasks.jsonl
└── tests/               # benchmark, workspace, llm, gating, end-to-end loop
```

## License

MIT (this reimplementation). The original method is the authors'; cite the paper.
