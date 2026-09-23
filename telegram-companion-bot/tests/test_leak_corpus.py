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


# -- Phase 1 (v2026-09-23.1): the guard saves every rejected completion in full ------------
#
# Driven through call_nanogpt with the same _one_call seam TestReasoningLeakGuard uses, so
# these prove the call site saves, not just that _save_leak_sample works when called.

REAL_LEAK = "leak/priya-2026-08-03-stepped-thinking.txt"


def _patch_calls(monkeypatch, tmp_path, outputs):
    monkeypatch.setattr(bot, "LEAK_SAMPLES_DIR", tmp_path / "leak_samples")
    monkeypatch.setattr(bot, "REASONING_LEAK_GUARD", True)
    monkeypatch.setattr(bot, "LEAK_SAMPLES", True)
    monkeypatch.setattr(bot, "_one_call", lambda messages, m: outputs.pop(0))
    monkeypatch.setattr(bot.time, "sleep", lambda s: None)
    return tmp_path / "leak_samples"


def _call():
    return bot.call_nanogpt([{"role": "user", "content": "hi"}],
                            model="thinker", fallback="plain", leak_guard=True)


def test_rejected_leak_is_saved_in_corpus_format(monkeypatch, tmp_path):
    """Each rejected attempt is one file; the file loads with this module's own _load
    and gives back the exact completion, so a reviewed sample drops into leak/ as is."""
    _, leak = _load(CORPUS / REAL_LEAK)
    d = _patch_calls(monkeypatch, tmp_path, [leak, leak, "hey. come here."])
    assert _call() == "hey. come here."
    files = sorted(d.glob("*.txt"))
    assert len(files) == 2, [f.name for f in files]
    for f in files:
        name, text = _load(f)
        assert name == bot.NAME
        assert text == leak
        assert bot._looks_like_reasoning_leak(text, name)
    assert "thinker" in files[0].name
    assert not list(d.glob("*.tmp"))


def test_delivered_reply_is_not_saved(monkeypatch, tmp_path):
    d = _patch_calls(monkeypatch, tmp_path, ["hey. come here."])
    assert _call() == "hey. come here."
    assert not d.exists()


def test_kill_switch_saves_nothing_and_guard_still_rerolls(monkeypatch, tmp_path):
    _, leak = _load(CORPUS / REAL_LEAK)
    d = _patch_calls(monkeypatch, tmp_path, [leak, "hey. come here."])
    monkeypatch.setattr(bot, "LEAK_SAMPLES", False)
    assert _call() == "hey. come here."
    assert not d.exists()


def test_oldest_samples_deleted_past_the_cap(monkeypatch, tmp_path):
    d = _patch_calls(monkeypatch, tmp_path, [])
    monkeypatch.setattr(bot, "LEAK_SAMPLES_MAX", 2)
    d.mkdir()
    for stamp in ("20260101T000000000000Z", "20260102T000000000000Z"):
        (d / f"{stamp}-old.txt").write_text("name: x\nsource: y\n---\nold\n")
    saved = bot._save_leak_sample("new text", "m")
    assert sorted(p.name for p in d.glob("*.txt")) == ["20260102T000000000000Z-old.txt", saved.name]


def test_failed_save_never_blocks_the_reroll(monkeypatch, tmp_path):
    """The save is best-effort: if the folder cannot be created (here a FILE sits at its
    path), the leak is still refused and the retry still delivers."""
    _, leak = _load(CORPUS / REAL_LEAK)
    d = _patch_calls(monkeypatch, tmp_path, [leak, "hey. come here."])
    d.write_text("not a folder")
    assert _call() == "hey. come here."
    assert d.read_text() == "not a folder"
