"""The benchmark is the validator the gate trusts, so it is tested first and alone."""

from pathlib import Path

import pytest

from skillforge import benchmark as bm

TASKS = Path(__file__).resolve().parents[1] / "tasks" / "demo_tasks.jsonl"


def test_extract_answer_takes_last_answer_line():
    assert bm.extract_answer("thinking...\nANSWER: 2026.001") == "2026.001"
    assert bm.extract_answer("ANSWER: wrong\nrevised\nANSWER: right") == "right"
    # No ANSWER line -> stripped text (still gradeable, usually as a failure).
    assert bm.extract_answer("  bare  ") == "bare"


def test_graders():
    exact = bm.Task("t", "x", "2026.001", grader="exact")
    assert exact.grade("ANSWER: 2026.001")
    assert exact.grade("ANSWER:  2026.001 ")  # whitespace-insensitive
    assert not exact.grade("ANSWER: 2026.1")

    contains = bm.Task("t", "x", "v2026-08-31", grader="contains")
    assert contains.grade("ANSWER: the tag is v2026-08-31.2")
    assert not contains.grade("ANSWER: nope")

    rx = bm.Task("t", "x", r"^\d{4}\.\d{3}$", grader="regex")
    assert rx.grade("ANSWER: 2026.185")
    assert not rx.grade("ANSWER: 2026.18")


def test_load_and_splits():
    tasks = bm.load_tasks(TASKS)
    assert len(tasks) == 14
    assert len(bm.split(tasks, "train")) == 6
    assert len(bm.split(tasks, "val")) == 4
    assert len(bm.split(tasks, "test")) == 4


def test_load_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "dup.jsonl"
    p.write_text('{"id":"a","x":"1","y":"1"}\n{"id":"a","x":"2","y":"2"}\n')
    with pytest.raises(ValueError, match="duplicate"):
        bm.load_tasks(p)


def test_evaluate_scores_a_perfect_and_a_zero_agent():
    tasks = bm.split(bm.load_tasks(TASKS), "val")

    # An oracle agent that knows every answer.
    answers = {t.x: t.y for t in tasks}
    oracle = lambda x: f"ANSWER: {answers[x]}"  # noqa: E731
    score = bm.evaluate(oracle, tasks)
    assert score.accuracy == 1.0
    assert score.n == len(tasks)
    assert not score.failed

    # An agent that always says the same wrong thing.
    dumb = lambda x: "ANSWER: 42"  # noqa: E731
    score = bm.evaluate(dumb, tasks)
    assert score.accuracy == 0.0
    assert len(score.failed) == len(tasks)


def test_benchmark_is_skill_sensitive():
    """The benchmark must be able to tell a good skill from no skill.

    A guard against a validator that cannot fail (repo constraint: verification
    instruments that always pass teach nothing). Here a 'skilled' agent that
    applies the two conventions must strictly beat a 'no-skill' agent.
    """
    tasks = bm.split(bm.load_tasks(TASKS), "val")

    import datetime

    def skilled(x: str) -> str:
        # Applies the two conventions the demo skills teach.
        import re

        m = re.search(r"date (\d{4}-\d{2}-\d{2})", x)
        if m:
            d = datetime.date.fromisoformat(m.group(1))
            return f"ANSWER: {d.year}.{d.timetuple().tm_yday:03d}"
        m = re.search(r"on (\d{4}-\d{2}-\d{2}) that is revision (\d+)", x)
        if m:
            return f"ANSWER: v{m.group(1)}.{m.group(2)}"
        return "ANSWER: unknown"

    no_skill = lambda x: "ANSWER: unknown"  # noqa: E731

    assert bm.evaluate(skilled, tasks).accuracy == 1.0
    assert bm.evaluate(no_skill, tasks).accuracy == 0.0
