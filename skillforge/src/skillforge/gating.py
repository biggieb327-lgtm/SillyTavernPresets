"""Gating and rollback (paper §3.2.4).

The one asymmetry that defines WikiSkill: a rejected proposal rolls back the
SKILLS only; the wiki is never rolled back. Every validated proposal — accepted
or rejected — appends an entry to wiki/skill-impact.md, giving the proposer an
objective, ground-truth record so it does not repeat a failed edit.
"""

from __future__ import annotations

import datetime
import difflib
from dataclasses import dataclass
from typing import Callable

from .agents import SkillProposal
from .workspace import PatchError, Workspace

Validator = Callable[[], float]  # evaluates the current skill set on val -> score


@dataclass(frozen=True)
class GateOutcome:
    iteration: int
    skill: str
    accepted: bool
    score: float
    r_best_before: float
    r_best_after: float
    diff: str
    error: str = ""

    @property
    def label(self) -> str:
        if self.error:
            return "Rejected (invalid patch)"
        return "Accepted" if self.accepted else "Rejected"


def _skill_body(ws: Workspace, skill: str) -> str:
    try:
        return ws.read_file(f"skills/{skill}/SKILL.md")
    except (FileNotFoundError, PatchError):
        return ""


def _unified_diff(before: str, after: str, skill: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/skills/{skill}/SKILL.md",
        tofile=f"b/skills/{skill}/SKILL.md",
    )
    return "".join(lines) or "(no textual change)"


def gate(
    ws: Workspace,
    proposal: SkillProposal,
    validator: Validator,
    r_best: float,
    iteration: int,
) -> tuple[float, GateOutcome]:
    """Apply a proposal, validate, accept on strict improvement else roll skills back.

    Returns (updated_r_best, outcome). Always records to skill-impact.md.
    """
    snapshot = ws.snapshot_skills()
    before = _skill_body(ws, proposal.skill)

    error = ""
    try:
        ws.apply_patch(proposal.patch)
    except PatchError as e:
        error = str(e)

    if error:
        after = before
        score = r_best  # invalid patch never scored; treat as no improvement
        accepted = False
        ws.restore_skills(snapshot)
    else:
        after = _skill_body(ws, proposal.skill)
        score = validator()
        accepted = score > r_best
        if not accepted:
            ws.restore_skills(snapshot)  # skills-only rollback; wiki untouched

    r_best_after = score if accepted else r_best
    outcome = GateOutcome(
        iteration=iteration,
        skill=proposal.skill,
        accepted=accepted,
        score=score,
        r_best_before=r_best,
        r_best_after=r_best_after,
        diff=_unified_diff(before, after, proposal.skill),
        error=error,
    )
    _record(ws, proposal, outcome)
    return r_best_after, outcome


def _record(ws: Workspace, proposal: SkillProposal, outcome: GateOutcome) -> None:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = (
        f"\n## Iteration {outcome.iteration} — {outcome.label}\n"
        f"- when: {stamp}\n"
        f"- skill: `{outcome.skill}`  op: `{proposal.patch.op}`\n"
        f"- rationale: {proposal.rationale or '(none given)'}\n"
        f"- validation score: {outcome.score:.4f}  (R_best was {outcome.r_best_before:.4f})\n"
    )
    if outcome.error:
        entry += f"- error: {outcome.error}\n"
    entry += "- diff:\n```diff\n" + outcome.diff.rstrip("\n") + "\n```\n"
    ws.append_skill_impact(entry)
