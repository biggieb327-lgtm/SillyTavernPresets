"""End-to-end offline: the whole Algorithm 1 loop under the deterministic brain."""

from pathlib import Path

from skillforge import benchmark as bm
from skillforge.demo import demo_brain
from skillforge.llm import MockLLM
from skillforge.orchestrator import evolve
from skillforge.workspace import Workspace

TASKS = Path(__file__).resolve().parents[1] / "tasks" / "demo_tasks.jsonl"


def _run(tmp_path, iterations=5):
    tasks = bm.load_tasks(TASKS)
    ws = Workspace(tmp_path / "wk")
    llm = MockLLM(demo_brain)
    result = evolve(
        llm, ws, bm.split(tasks, "train"), bm.split(tasks, "val"), iterations=iterations
    )
    return ws, result, tasks


def test_loop_evolves_from_zero_to_perfect(tmp_path):
    ws, result, _ = _run(tmp_path)
    assert result.baseline == 0.0
    assert result.r_best == 1.0
    assert [o.accepted for o in result.history] == [True, True]
    assert [o.skill for o in result.history] == ["house-date", "release-tag"]


def test_early_stop_before_using_all_iterations(tmp_path):
    _, result, _ = _run(tmp_path, iterations=5)
    # Reached 1.0 in two accepted iterations; the loop stopped rather than run five.
    assert len(result.history) == 2


def test_wiki_accumulates_and_audit_trail_is_written(tmp_path):
    ws, result, _ = _run(tmp_path)
    impact = ws.read_skill_impact()
    assert impact.count("## Iteration") == 2
    assert "```diff" in impact
    assert "wiki/patterns/missing-conventions.md" in ws.list_files("wiki")
    # logs.md got a maintainer line each iteration.
    assert ws.read_file("wiki/logs.md").count("- ") >= 2


def test_raw_traces_are_written_per_iteration(tmp_path):
    ws, _, _ = _run(tmp_path)
    assert ws.list_files("raw/iter001")
    assert ws.list_files("raw/iter002")


def test_evolved_skills_generalize_to_held_out_test(tmp_path):
    ws, _, tasks = _run(tmp_path)
    from skillforge.agents import InferenceAgent

    llm = MockLLM(demo_brain)
    test_acc = bm.evaluate(InferenceAgent(llm, ws).solve, bm.split(tasks, "test")).accuracy
    assert test_acc == 1.0


def test_inference_agent_has_no_wiki_access(tmp_path):
    """Paper default: the inference agent sees skills, never the wiki."""
    ws, _, tasks = _run(tmp_path)
    from skillforge.agents import InferenceAgent

    calls: list = []
    llm = MockLLM(lambda msgs: (calls.append(msgs) or "ANSWER: x"))
    InferenceAgent(llm, ws).solve("Convert the date 2026-01-01 to the house date format.")
    system = calls[0][0]["content"]
    assert "Skill:" in system  # skills injected
    assert "skill-impact" not in system and "wiki/patterns" not in system  # no wiki
