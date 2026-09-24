"""Banned-phrase guard (SLOP_GUARD / SLOP_REROLL, v2026-09-24.1).

Driven through the real entry points: `_apply_slop_guard` (what reply_with_typing calls)
and `assemble_messages` (where the next-turn note lands). `generate_reply` is replaced
by a fake only for the re-roll cases, so no test touches the network.
"""
import asyncio

import pytest

import bot


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "SLOP_GUARD", True)
    monkeypatch.setattr(bot, "SLOP_REROLL", False)
    monkeypatch.setattr(bot, "SLOP_PHRASES_FILE", tmp_path / "slop_phrases.txt")
    bot._slop_cache.update(mtime=None, rx=None)
    bot._slop_nudge.clear()
    yield
    bot._slop_cache.update(mtime=None, rx=None)
    bot._slop_nudge.clear()


def _run(coro):
    return asyncio.run(coro)


# ── matching ──────────────────────────────────────────────────────────────────

class TestSlopHits:
    def test_plain_text_has_no_hits(self):
        assert bot._slop_hits("lol ok I'll grab tacos after my shift") == []

    def test_suffix_wildcard_matches_inflections(self):
        assert bot._slop_hits("my breath hitched a little") == ["breath hitch*"]
        assert bot._slop_hits("Breath hitches.") == ["breath hitch*"]

    def test_bare_star_matches_exactly_one_word(self):
        assert "shiver* down * spine" in bot._slop_hits("a shiver down my spine")
        assert "shiver* down * spine" not in bot._slop_hits("shivers down the whole spine")

    def test_word_boundaries(self):
        # "ozone" inside another word, and "luminous" inside "voluminous", must not hit
        assert bot._slop_hits("ozonetherapy voluminous") == []

    def test_whitespace_runs_between_words(self):
        assert bot._slop_hits("barely  above\na whisper") == ["barely above a whisper"]

    def test_each_entry_reported_once(self):
        assert bot._slop_hits("visceral. so visceral.") == ["visceral"]

    def test_ordinary_texting_words_are_not_on_the_built_in_list(self):
        # False-positive guard: these are normal in a text message.
        assert bot._slop_hits("deep convo, the crowd was electric, velvet couch") == []


class TestPhraseFile:
    def test_file_replaces_built_in_list(self):
        bot.SLOP_PHRASES_FILE.write_text("# house list\nbanana*\n", encoding="utf-8")
        assert bot._slop_hits("bananas again") == ["banana*"]
        assert bot._slop_hits("something shifted") == []

    def test_file_edit_is_picked_up_without_restart(self):
        f = bot.SLOP_PHRASES_FILE
        f.write_text("alpha\n", encoding="utf-8")
        assert bot._slop_hits("alpha beta") == ["alpha"]
        f.write_text("beta\n", encoding="utf-8")
        import os
        st = f.stat()
        os.utime(f, (st.st_atime, st.st_mtime + 5))
        assert bot._slop_hits("alpha beta") == ["beta"]

    def test_unreadable_file_falls_back_to_built_in(self):
        bot.SLOP_PHRASES_FILE.write_bytes(b"\xff\xfe\xfa not utf8")
        assert bot._slop_hits("something shifted") == ["something shifted"]


# ── the guard ─────────────────────────────────────────────────────────────────

class TestApplySlopGuard:
    def test_clean_reply_passes_untouched(self):
        before = len(bot._error_counts.get("slop", []))
        out = _run(bot._apply_slop_guard(1, "hey you", [], None, None, True))
        assert out == "hey you"
        assert 1 not in bot._slop_nudge
        assert len(bot._error_counts.get("slop", [])) == before

    def test_hit_counts_and_queues_nudge_without_a_model_call(self, monkeypatch):
        async def boom(*a, **k):
            raise AssertionError("SLOP_REROLL off must not call the model")
        monkeypatch.setattr(bot, "generate_reply", boom)
        before = len(bot._error_counts.get("slop", []))
        text = "something shifted between us"
        out = _run(bot._apply_slop_guard(2, text, [], None, None, True))
        assert out == text
        assert 2 in bot._slop_nudge
        assert len(bot._error_counts.get("slop", [])) == before + 1

    def test_non_persona_path_is_outside_the_guard(self):
        out = _run(bot._apply_slop_guard(3, "something shifted", [], None, None, False))
        assert out == "something shifted"
        assert 3 not in bot._slop_nudge

    def test_kill_switch(self, monkeypatch):
        monkeypatch.setattr(bot, "SLOP_GUARD", False)
        _run(bot._apply_slop_guard(4, "something shifted", [], None, None, True))
        assert 4 not in bot._slop_nudge
        assert bot._take_slop_nudge(4) == ""

    def test_reroll_keeps_the_cleaner_candidate(self, monkeypatch):
        monkeypatch.setattr(bot, "SLOP_REROLL", True)
        seen = {}

        async def fake(messages, model=None, fallback=None, leak_guard=True):
            seen["last"] = messages[-1]["content"]
            return "ok that actually made me laugh"
        monkeypatch.setattr(bot, "generate_reply", fake)
        msgs = [{"role": "user", "content": "hi"}]
        out = _run(bot._apply_slop_guard(5, "something shifted, visceral", msgs,
                                         None, None, True))
        assert out == "ok that actually made me laugh"
        assert seen["last"] == bot._SLOP_REROLL_NOTE
        assert len(msgs) == 1  # the caller's list is not mutated

    def test_reroll_discards_a_worse_or_empty_candidate(self, monkeypatch):
        monkeypatch.setattr(bot, "SLOP_REROLL", True)

        async def worse(*a, **k):
            return "something shifted, visceral, luminous"
        monkeypatch.setattr(bot, "generate_reply", worse)
        assert _run(bot._apply_slop_guard(6, "something shifted", [], None, None,
                                          True)) == "something shifted"

        async def empty(*a, **k):
            return "   "
        monkeypatch.setattr(bot, "generate_reply", empty)
        assert _run(bot._apply_slop_guard(6, "something shifted", [], None, None,
                                          True)) == "something shifted"

    def test_reroll_failure_delivers_original(self, monkeypatch):
        monkeypatch.setattr(bot, "SLOP_REROLL", True)

        async def fails(*a, **k):
            raise RuntimeError("api down")
        monkeypatch.setattr(bot, "generate_reply", fails)
        assert _run(bot._apply_slop_guard(7, "something shifted", [], None, None,
                                          True)) == "something shifted"


class TestNextTurnNote:
    def test_note_lands_once_then_clears(self):
        bot._slop_nudge.add(9601)
        first = bot.assemble_messages(9601, "hello")
        assert any(m.get("content") == bot._SLOP_NUDGE_NOTE for m in first)
        second = bot.assemble_messages(9601, "hello")
        assert not any(m.get("content") == bot._SLOP_NUDGE_NOTE for m in second)

    def test_no_note_without_a_flag(self):
        msgs = bot.assemble_messages(9602, "hello")
        assert not any(m.get("content") == bot._SLOP_NUDGE_NOTE for m in msgs)

    def test_notes_are_positive_only(self):
        # House rule: naming the suppressed thing activates it in a thinking model's trace.
        for note in (bot._SLOP_NUDGE_NOTE, bot._SLOP_REROLL_NOTE):
            low = note.lower()
            for neg in ("don't", "do not", "never", "avoid", "stop", "cliche", "banned"):
                assert neg not in low, (neg, note)
