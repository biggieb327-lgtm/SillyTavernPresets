"""The skill-quality benchmark: the objective validator the gate depends on.

A benchmark is a set of Tasks, each with an input prompt (`x`), a ground-truth
answer (`y`), a `split` (train / val / test), and a deterministic grader. The
validator runs an agent callable over a split and returns accuracy plus the raw
rollouts. Nothing here calls an LLM — it takes a `Callable[[str], str]` and
grades whatever text comes back — so the same benchmark scores the offline
MockLLM and a real model identically.

Answer protocol: an agent is expected to end its output with a line
`ANSWER: <value>`. The grader extracts the last such line. This keeps grading
model-agnostic and free of an LLM judge (paper App. C: do not gate on an LLM
judge alone).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

Agent = Callable[[str], str]

_ANSWER_RE = re.compile(r"ANSWER:\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)


def extract_answer(text: str) -> str:
    """Return the value of the last `ANSWER:` line, or the stripped text."""
    matches = _ANSWER_RE.findall(text or "")
    if matches:
        return matches[-1].strip()
    return (text or "").strip()


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


@dataclass(frozen=True)
class Task:
    id: str
    x: str  # the input prompt shown to the agent
    y: str  # ground-truth answer
    split: str = "train"  # "train" | "val" | "test"
    grader: str = "exact"  # "exact" | "contains" | "regex"
    meta: dict = field(default_factory=dict)

    def grade(self, output: str) -> bool:
        got = extract_answer(output)
        if self.grader == "exact":
            return _normalize(got) == _normalize(self.y)
        if self.grader == "contains":
            return _normalize(self.y) in _normalize(got)
        if self.grader == "regex":
            return re.search(self.y, got) is not None
        raise ValueError(f"unknown grader: {self.grader!r}")


@dataclass(frozen=True)
class Rollout:
    task_id: str
    prompt: str
    output: str
    correct: bool


@dataclass(frozen=True)
class Score:
    accuracy: float
    n: int
    rollouts: tuple[Rollout, ...]

    @property
    def passed(self) -> tuple[Rollout, ...]:
        return tuple(r for r in self.rollouts if r.correct)

    @property
    def failed(self) -> tuple[Rollout, ...]:
        return tuple(r for r in self.rollouts if not r.correct)


def load_tasks(path: str | Path) -> list[Task]:
    """Load tasks from a .jsonl file. Each line: {id, x, y, split?, grader?, meta?}."""
    tasks: list[Task] = []
    for line_no, raw in enumerate(Path(path).read_text().splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{line_no}: bad JSON: {e}") from e
        tasks.append(
            Task(
                id=str(d["id"]),
                x=d["x"],
                y=str(d["y"]),
                split=d.get("split", "train"),
                grader=d.get("grader", "exact"),
                meta=d.get("meta", {}),
            )
        )
    _check_unique_ids(tasks)
    return tasks


def _check_unique_ids(tasks: Iterable[Task]) -> None:
    seen: set[str] = set()
    for t in tasks:
        if t.id in seen:
            raise ValueError(f"duplicate task id: {t.id}")
        seen.add(t.id)


def split(tasks: Iterable[Task], name: str) -> list[Task]:
    return [t for t in tasks if t.split == name]


def evaluate(agent: Agent, tasks: Iterable[Task]) -> Score:
    """Run `agent` over `tasks`, grade each, return accuracy + rollouts.

    This is R(.) in the paper: the objective validation/test scorer.
    """
    rollouts: list[Rollout] = []
    for t in tasks:
        out = agent(t.x)
        rollouts.append(Rollout(t.id, t.x, out, t.grade(out)))
    n = len(rollouts)
    acc = sum(r.correct for r in rollouts) / n if n else 0.0
    return Score(accuracy=acc, n=n, rollouts=tuple(rollouts))
