"""The evolution loop — Algorithm 1 (paper Appendix A).

Ties the pieces together: baseline validation, then K iterations of
inference -> wiki maintenance -> skill proposal -> gating, with early stop at
R_best == 1.0. The wiki compounds across every iteration; only skills roll back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import benchmark as bm
from .agents import InferenceAgent, SkillProposer, WikiMaintainer
from .gating import GateOutcome, gate
from .llm import LLM
from .workspace import Workspace


@dataclass
class EvolveResult:
    baseline: float
    r_best: float
    history: list[GateOutcome] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> list[GateOutcome]:
        return [o for o in self.history if o.accepted]


def _outcome_summary(rollouts: list[bm.Rollout]) -> str:
    lines = [
        f"- [{'PASS' if r.correct else 'FAIL'}] {r.task_id}: got {bm.extract_answer(r.output)!r}"
        for r in rollouts
    ]
    acc = sum(r.correct for r in rollouts) / len(rollouts) if rollouts else 0.0
    return f"train accuracy: {acc:.3f}\n" + "\n".join(lines)


def evolve(
    llm: LLM,
    workspace: Workspace,
    train: list[bm.Task],
    val: list[bm.Task],
    iterations: int = 5,
    proposer_max_turns: int = 6,
) -> EvolveResult:
    inference = InferenceAgent(llm, workspace)
    maintainer = WikiMaintainer(llm, workspace)
    proposer = SkillProposer(llm, workspace, max_turns=proposer_max_turns)

    # Line 2: baseline validation with the empty skill set.
    baseline = bm.evaluate(inference.solve, val).accuracy
    result = EvolveResult(baseline=baseline, r_best=baseline)

    for k in range(1, iterations + 1):
        if result.r_best >= 1.0:  # Line 4: early stop
            break

        # Line 6: inference rollouts on the training split.
        train_score = bm.evaluate(inference.solve, train)
        for r in train_score.rollouts:
            workspace.write_trace(k, r.task_id, f"PROMPT:\n{r.prompt}\n\nOUTPUT:\n{r.output}")

        # Lines 7-8: sample + wiki maintenance (the wiki always advances).
        log = maintainer.consolidate(list(train_score.rollouts))
        result.logs.append(log)

        # Line 9: one atomic skill proposal.
        proposal = proposer.propose(_outcome_summary(list(train_score.rollouts)))
        if proposal is None:
            workspace.append_log(f"- iter {k}: proposer made no proposal")
            continue

        # Lines 10-16: apply, validate on val, gate (skills-only rollback), record.
        validator = lambda: bm.evaluate(inference.solve, val).accuracy  # noqa: E731
        result.r_best, outcome = gate(workspace, proposal, validator, result.r_best, k)
        result.history.append(outcome)

    return result
