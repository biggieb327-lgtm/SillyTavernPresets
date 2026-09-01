"""The four agents of the WikiSkill loop (paper §3.2), minus gating (see gating.py).

  InferenceAgent  — runs a task with active skills injected, no wiki access (§3.2.1)
  WikiMaintainer  — consolidates sampled traces into wiki patterns + log (§3.2.2)
  SkillProposer   — ReAct agent; reads wiki/impact/traces, emits ONE atomic
                    skill proposal (§3.2.3)
"""

from __future__ import annotations

from dataclasses import dataclass

from . import prompts
from .benchmark import Rollout
from .llm import LLM, extract_json
from .workspace import Patch, Workspace


# --------------------------------------------------------------------- 3.2.1
class InferenceAgent:
    """Conditioned on the active skill set; the wiki is deliberately out of reach."""

    def __init__(self, llm: LLM, workspace: Workspace):
        self.llm = llm
        self.ws = workspace

    def solve(self, x: str) -> str:
        skills = self.ws.read_active_skills()
        system = prompts.INFERENCE_SYSTEM
        if skills:
            system += "\n\n# Active skills\n" + skills
        return self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": x}]
        )

    def as_callable(self):
        return self.solve


# ------------------------------------------------------------ trace sampling
def stratified_sample(
    rollouts: list[Rollout],
    max_fail: int = 5,
    max_pass: int = 3,
    char_cap: int = 15000,
) -> str:
    """Sample <=max_fail failing + <=max_pass passing traces under a char budget (App. C)."""
    fails = [r for r in rollouts if not r.correct][:max_fail]
    passes = [r for r in rollouts if r.correct][:max_pass]
    blocks: list[str] = []
    for label, rs in (("FAILING", fails), ("PASSING", passes)):
        for r in rs:
            blocks.append(
                f"### {label} trace [{r.task_id}]\n"
                f"PROMPT: {r.prompt}\n"
                f"AGENT OUTPUT: {r.output}\n"
            )
    text = "\n".join(blocks)
    return text[:char_cap]


# --------------------------------------------------------------------- 3.2.2
class WikiMaintainer:
    def __init__(self, llm: LLM, workspace: Workspace):
        self.llm = llm
        self.ws = workspace

    def consolidate(self, rollouts: list[Rollout]) -> str:
        """Patch the wiki from sampled traces. Returns the maintainer's log line."""
        sample = stratified_sample(rollouts)
        patterns = "\n\n".join(
            f"--- {p} ---\n{self.ws.read_file(p)}" for p in self.ws.list_patterns()
        )
        user = (
            f"# Current wiki index\n{self.ws.wiki_index()}\n\n"
            f"# Existing pattern pages\n{patterns or '(none yet)'}\n\n"
            f"# Sampled traces\n{sample}"
        )
        reply = self.llm.chat(
            [
                {"role": "system", "content": prompts.MAINTAINER_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        data = extract_json(reply)
        for pd in data.get("patches", []):
            self.ws.apply_patch(
                Patch(
                    target=pd["target"],
                    op=pd["op"],
                    text=pd.get("text", ""),
                    old=pd.get("old", ""),
                    anchor=pd.get("anchor", ""),
                )
            )
        log = data.get("log", "(no summary)")
        self.ws.append_log(f"- {log}")
        return log


# --------------------------------------------------------------------- 3.2.3
@dataclass(frozen=True)
class SkillProposal:
    skill: str
    patch: Patch
    rationale: str


class SkillProposer:
    """ReAct proposer. Reads on demand; emits one atomic proposal per iteration."""

    def __init__(self, llm: LLM, workspace: Workspace, max_turns: int = 6):
        self.llm = llm
        self.ws = workspace
        self.max_turns = max_turns

    def propose(self, outcome_summary: str) -> SkillProposal | None:
        seed = (
            f"# Wiki index\n{self.ws.wiki_index()}\n\n"
            f"# Skill-impact tracker (do not repeat rejected edits)\n"
            f"{self.ws.read_skill_impact()}\n\n"
            f"# Training outcomes\n{outcome_summary}\n\n"
            f"# Readable files\n" + "\n".join(self.ws.list_files()) + "\n\n"
            "Inspect what you need with read_file, then propose one atomic skill change."
        )
        messages = [
            {"role": "system", "content": prompts.PROPOSER_SYSTEM},
            {"role": "user", "content": seed},
        ]
        for _ in range(self.max_turns):
            reply = self.llm.chat(messages)
            messages.append({"role": "assistant", "content": reply})
            try:
                step = extract_json(reply)
            except ValueError:
                messages.append(
                    {"role": "user", "content": "Reply with one JSON object."}
                )
                continue
            action = step.get("action")
            if action == "read_file":
                obs = self.ws.read_file_tool(step.get("path", ""))
                messages.append({"role": "user", "content": f"OBSERVATION:\n{obs}"})
                continue
            if action == "propose":
                return self._build(step.get("proposal", {}))
            messages.append(
                {"role": "user", "content": "Unknown action; read_file or propose."}
            )
        return None

    def _build(self, p: dict) -> SkillProposal | None:
        name = p.get("skill")
        op = p.get("op")
        if not name or not op:
            return None
        return SkillProposal(
            skill=name,
            patch=Patch(
                target=f"skills/{name}/SKILL.md",
                op=op,
                text=p.get("text", ""),
                old=p.get("old", ""),
                anchor=p.get("anchor", ""),
            ),
            rationale=p.get("rationale", ""),
        )
