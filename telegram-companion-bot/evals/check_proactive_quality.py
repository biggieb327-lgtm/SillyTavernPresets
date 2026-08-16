#!/usr/bin/env python3
"""Validate Sprint 1's proactive-message quality corpus.

This is deliberately deterministic and dependency-free. It validates the annotation
contract and proves the corpus contains the three classes Sprint 1 needs before any
live proactive ranking behavior is built: clearly good, clearly bad, and collision-
prone candidates.

Run:
    python3 telegram-companion-bot/evals/check_proactive_quality.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

CORPUS = Path(__file__).with_name("proactive_quality_corpus.json")
DIMS = ("timing", "specificity", "novelty", "pressure")
SOURCES = {"reminder", "health", "memory", "day_life", "check_in"}


def classify(scores: dict[str, int]) -> str:
    values = [scores[d] for d in DIMS]
    total = sum(values)
    if 0 in values or total <= 6:
        return "bad"
    if all(v >= 2 for v in values) and total >= 10:
        return "good"
    return "mixed"


def main() -> int:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = data.get("cases")
    assert isinstance(cases, list) and cases, "corpus must contain cases"

    seen_ids: set[str] = set()
    expected_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    collisions: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        cid = case.get("id")
        assert isinstance(cid, str) and cid, "every case needs a non-empty id"
        assert cid not in seen_ids, f"duplicate case id: {cid}"
        seen_ids.add(cid)

        source = case.get("source")
        assert source in SOURCES, f"{cid}: unknown source {source!r}"
        source_counts[source] += 1

        scores = case.get("scores")
        assert isinstance(scores, dict), f"{cid}: scores must be an object"
        assert set(scores) == set(DIMS), f"{cid}: scores must contain exactly {DIMS}"
        for dim in DIMS:
            value = scores[dim]
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{cid}: {dim} must be an integer"
            )
            assert 0 <= value <= 3, f"{cid}: {dim}={value} outside 0..3"

        expected = case.get("expected")
        actual = classify(scores)
        assert expected == actual, f"{cid}: expected {expected!r}, rubric yields {actual!r}"
        expected_counts[expected] += 1

        group = case.get("collision_group")
        assert group is None or isinstance(group, str), f"{cid}: invalid collision_group"
        if group and expected == "good":
            collisions[group].append(cid)

        for text_key in ("candidate", "context"):
            text = case.get(text_key)
            assert isinstance(text, str) and text.strip(), f"{cid}: missing {text_key}"

    missing_sources = SOURCES - set(source_counts)
    assert not missing_sources, f"missing proactive source classes: {sorted(missing_sources)}"
    assert expected_counts["good"] >= 5, "need at least five clearly good cases"
    assert expected_counts["bad"] >= 5, "need at least five clearly bad cases"
    assert expected_counts["mixed"] >= 1, "need at least one intentionally ambiguous case"

    collision_groups = {g: ids for g, ids in collisions.items() if len(ids) >= 2}
    assert collision_groups, "need at least one collision-prone window with 2+ good candidates"

    print(
        "proactive-quality corpus: PASS — "
        f"{len(cases)} cases; "
        f"good={expected_counts['good']} bad={expected_counts['bad']} "
        f"mixed={expected_counts['mixed']}; "
        f"collision_windows={len(collision_groups)}"
    )
    for group, ids in sorted(collision_groups.items()):
        print(f"  collision {group}: {', '.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
