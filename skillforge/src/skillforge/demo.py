"""A deterministic offline demo brain for MockLLM.

IMPORTANT (honesty note): this brain makes the loop *reproducible without a
network* so the harness mechanics — gating math, skills-only rollback, the
never-rolled-back wiki, the skill-impact audit trail, early stop — can be tested
and demonstrated. It does NOT constitute evidence that LLM skill evolution
"works"; that claim belongs to the paper's experiments and requires a real model
(`skillforge evolve --model ...`). Here the mock plays all three roles by keying
off the role markers in each system prompt.
"""

from __future__ import annotations

import datetime
import json
import re

from .llm import Message

_HOUSE_DATE_TOKEN = "HOUSE-DATE-SKILL"
_RELEASE_TAG_TOKEN = "RELEASE-TAG-SKILL"

_HOUSE_DATE_BODY = (
    "House date format procedure.\n"
    "Given a date YYYY-MM-DD, output `<year>.<day-of-year>` where day-of-year is "
    "zero-padded to three digits.\n"
    f"marker: {_HOUSE_DATE_TOKEN}\n"
)
_RELEASE_TAG_BODY = (
    "Release tag procedure.\n"
    "Given a build date YYYY-MM-DD and a revision N, output `v<date>.<N>`.\n"
    f"marker: {_RELEASE_TAG_TOKEN}\n"
)


def _system(messages: list[Message]) -> str:
    return next((m["content"] for m in messages if m["role"] == "system"), "")


def _last_user(messages: list[Message]) -> str:
    return next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )


def _first_user(messages: list[Message]) -> str:
    return next((m["content"] for m in messages if m["role"] == "user"), "")


def demo_brain(messages: list[Message]) -> str:
    system = _system(messages)
    if "Wiki Maintainer" in system:
        return _maintain()
    if "Skill Proposer" in system:
        return _propose(messages)
    return _infer(system, _last_user(messages))


def _infer(system: str, task: str) -> str:
    m = re.search(r"date (\d{4}-\d{2}-\d{2})", task)
    if m and _HOUSE_DATE_TOKEN in system:
        d = datetime.date.fromisoformat(m.group(1))
        return f"Applying the house date format.\nANSWER: {d.year}.{d.timetuple().tm_yday:03d}"
    m = re.search(r"on (\d{4}-\d{2}-\d{2}) that is revision (\d+)", task)
    if m and _RELEASE_TAG_TOKEN in system:
        return f"Applying the release tag format.\nANSWER: v{m.group(1)}.{m.group(2)}"
    return "I do not know the required convention.\nANSWER: unknown"


def _maintain() -> str:
    return json.dumps(
        {
            "patches": [
                {
                    "target": "wiki/patterns/missing-conventions.md",
                    "op": "create",
                    "text": (
                        "# Pattern: missing conventions\n"
                        "Failing traces answer 'unknown'. Root cause: the solver has no "
                        "skill teaching the house date format or the release tag format.\n"
                    ),
                },
                {
                    "target": "wiki/index.md",
                    "op": "create",
                    "text": "# Wiki Index\n\nPattern pages:\n- wiki/patterns/missing-conventions.md\n",
                },
            ],
            "log": "solver lacks convention skills; documented root cause",
        }
    )


def _propose(messages: list[Message]) -> str:
    seen_observation = any(
        m["role"] == "user" and m["content"].startswith("OBSERVATION:")
        for m in messages
    )
    if not seen_observation:
        return json.dumps(
            {
                "thought": "Inspect the failure pattern before proposing.",
                "action": "read_file",
                "path": "wiki/patterns/missing-conventions.md",
            }
        )
    seed = _first_user(messages)
    if "skills/house-date/SKILL.md" not in seed:
        proposal = {
            "skill": "house-date",
            "op": "create",
            "text": _HOUSE_DATE_BODY,
            "rationale": "Teach the house date format so date tasks pass.",
        }
    elif "skills/release-tag/SKILL.md" not in seed:
        proposal = {
            "skill": "release-tag",
            "op": "create",
            "text": _RELEASE_TAG_BODY,
            "rationale": "Teach the release tag format so tag tasks pass.",
        }
    else:
        proposal = {
            "skill": "house-date",
            "op": "append",
            "text": "\n(redundant note)\n",
            "rationale": "No new root cause; expected to be rejected by the gate.",
        }
    return json.dumps({"thought": "Propose the smallest fix.", "action": "propose", "proposal": proposal})
