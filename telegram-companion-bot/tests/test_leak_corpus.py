"""ROADMAP 2.7 Phase 0 — score `_looks_like_reasoning_leak` against every leak on record.

The reasoning-leak class came back three times (skill-impact.md: v2026-07-29.1,
v2026-08-03.1, v2026-08-25.1 all `recurred`), and each fix was fitted to the leak that had
just happened. TestReasoningLeakGuard in test_pure.py pins each leak on its own; this file
runs the detector over ALL of them at once, plus normal replies, so a change that catches
the newest leak cannot quietly stop catching an older one or start flagging real replies.

Corpus: tests/leak_corpus/{leak,clean}/*.txt, each file
    name: <card name, as bot.NAME would be>
    source: <where the text came from>
    ---
    <the completion, verbatim>
plus every card's first_mes and alternate_greetings, loaded live from the card JSON — the
characters' own authored messages, so a card edit that the detector would flag fails here.

known-misses.txt lists samples the detector gets wrong on purpose (a leak it misses, or a
normal reply it flags). Those are asserted to STAY wrong, so fixing one fails the test and
forces the list to be updated — the list cannot silently go stale.

The repo is public: a leak/ file from a real chat is committed only after redaction.
"""
import json
from pathlib import Path

import pytest

import bot

HERE = Path(__file__).parent
CORPUS = HERE / "leak_corpus"
CARDS = ["nora.json", "bonnie.json", "cass.json", "emily_harper.json", "priya.json",
         "jules_nakagawa.json", "marcus_calder.json"]


def _load(path: Path):
    raw = path.read_text(encoding="utf-8")
    head, sep, body = raw.partition("\n---\n")
    assert sep, f"{path.name}: missing the '---' line between header and text"
    meta = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    assert "name" in meta and "source" in meta, f"{path.name}: header needs name: and source:"
    return meta["name"], body[:-1] if body.endswith("\n") else body


def _known_misses():
    out = {}
    for line in (CORPUS / "known-misses.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rel, _, reason = line.partition("\t")
            assert reason.strip(), f"known-misses.txt: '{rel}' has no reason after a tab"
            out[rel] = reason
    return out


def _samples(kind):
    return sorted(p.relative_to(CORPUS).as_posix() for p in (CORPUS / kind).glob("*.txt"))


def _card_greetings():
    out = []
    for card in CARDS:
        data = json.loads((HERE.parent / card).read_text(encoding="utf-8"))["data"]
        texts = [data.get("first_mes") or ""] + list(data.get("alternate_greetings") or [])
        out += [(f"{card}#{i}", data["name"], t) for i, t in enumerate(texts) if t.strip()]
    return out


KNOWN = _known_misses()
LEAKS = _samples("leak")
CLEAN = _samples("clean")
GREETINGS = _card_greetings()


@pytest.mark.parametrize("rel", LEAKS)
def test_leak_is_caught(rel):
    name, text = _load(CORPUS / rel)
    caught = bot._looks_like_reasoning_leak(text, name)
    if rel in KNOWN:
        assert not caught, (f"{rel} is now CAUGHT — good. Delete its line from "
                            f"known-misses.txt so the list stays true.")
    else:
        assert caught, (f"{rel} ({len(text)} chars) is a recorded leak and the detector "
                        f"passed it — this change reopens a leak that was already fixed.")


@pytest.mark.parametrize("rel", CLEAN)
def test_clean_reply_passes(rel):
    name, text = _load(CORPUS / rel)
    flagged = bot._looks_like_reasoning_leak(text, name)
    if rel in KNOWN:
        assert flagged, (f"{rel} is no longer flagged — good. Delete its line from "
                         f"known-misses.txt so the list stays true.")
    else:
        assert not flagged, (f"{rel} ({len(text)} chars) is a normal reply and the "
                             f"detector flagged it — it would be re-rolled, never delivered.")


@pytest.mark.parametrize("label,name,text", GREETINGS, ids=[g[0] for g in GREETINGS])
def test_card_greeting_passes(label, name, text):
    assert not bot._looks_like_reasoning_leak(text, name), (
        f"{label}: the character's own authored greeting is flagged as a reasoning leak — "
        f"either the card edit or the detector change is wrong")


def test_known_misses_name_real_files():
    missing = [rel for rel in KNOWN if not (CORPUS / rel).exists()]
    assert not missing, f"known-misses.txt names files that do not exist: {missing}"


def test_corpus_can_fail():
    """A clean set made only of short texts cannot fail: both length floors reject it
    before any rule runs. Require clean texts above each floor, so each rule is
    actually exercised on something it must NOT flag, and a leak set that is not
    all known misses."""
    lengths = [len(_load(CORPUS / r)[1]) for r in CLEAN] + [len(g[2]) for g in GREETINGS]
    assert any(n >= bot._OUTLINE_HEADER_MIN_CHARS for n in lengths), \
        "no clean text reaches the structural rule's floor — that rule is untested here"
    assert any(n >= bot._REASONING_LEAK_MIN_CHARS for n in lengths), \
        "no clean text reaches the vocabulary rule's floor — that rule is untested here"
    assert [r for r in LEAKS if r not in KNOWN], "every leak is a known miss — nothing is pinned"
