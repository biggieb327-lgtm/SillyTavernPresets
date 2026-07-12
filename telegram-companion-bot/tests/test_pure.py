"""Tests for pure functions in bot.py.

These cover logic where a regression is fleet-breaking and the functions are pure
(no I/O, no Telegram, no API calls). See ROADMAP.md item 2.1.
"""
import asyncio
import json
import time

import bot


# ── extract_tags ──────────────────────────────────────────────────────────────
# Returns (clean_text, reaction, selfie_hint, meme_caption).

class TestExtractTags:
    def test_plain_text_unchanged(self):
        text = "hey what's up"
        clean, reaction, selfie, meme = bot.extract_tags(text)
        assert clean == text
        assert reaction is None
        assert selfie is None
        assert meme is None

    def test_react_tag(self):
        clean, reaction, selfie, meme = bot.extract_tags("sure! [react: ❤️]")
        assert "react" not in clean.lower()
        assert reaction is not None
        assert selfie is None
        assert meme is None

    def test_selfie_tag(self):
        clean, reaction, selfie, meme = bot.extract_tags(
            "here you go [selfie: wearing a red dress at the park]"
        )
        assert "selfie" not in clean.lower()
        assert selfie == "wearing a red dress at the park"
        assert meme is None

    def test_meme_tag_two_parts(self):
        clean, reaction, selfie, meme = bot.extract_tags(
            "lol [meme: when the code works | on the first try]"
        )
        assert "meme" not in clean.lower()
        assert meme == ("when the code works", "on the first try")

    def test_meme_tag_one_part(self):
        clean, reaction, selfie, meme = bot.extract_tags(
            "check this out [meme: one does not simply]"
        )
        assert meme == ("one does not simply", "")

    def test_all_tags_together(self):
        text = "[react: 😂] haha [selfie: laughing] [meme: top | bottom]"
        clean, reaction, selfie, meme = bot.extract_tags(text)
        assert reaction is not None
        assert selfie == "laughing"
        assert meme == ("top", "bottom")
        assert "[" not in clean

    def test_search_tag_stripped(self):
        clean, _, _, _ = bot.extract_tags("let me look [search: python async]")
        assert "search" not in clean.lower()
        assert "[" not in clean

    def test_case_insensitive(self):
        _, _, selfie, _ = bot.extract_tags("[Selfie: test hint]")
        assert selfie == "test hint"

    def test_empty_string(self):
        clean, reaction, selfie, meme = bot.extract_tags("")
        assert clean == ""
        assert reaction is None
        assert selfie is None
        assert meme is None


# ── parse_cron_schedule ───────────────────────────────────────────────────────

class TestParseCronSchedule:
    def test_daily_with_time(self):
        result = bot.parse_cron_schedule("daily 09:30")
        assert result == {"type": "daily", "hour": 9, "minute": 30}

    def test_daily_midnight(self):
        result = bot.parse_cron_schedule("daily 00:00")
        assert result == {"type": "daily", "hour": 0, "minute": 0}

    def test_every_n_hours(self):
        result = bot.parse_cron_schedule("every 3h")
        assert result == {"type": "interval", "seconds": 10800}

    def test_every_n_minutes(self):
        result = bot.parse_cron_schedule("every 30m")
        assert result == {"type": "interval", "seconds": 1800}

    def test_every_with_space(self):
        result = bot.parse_cron_schedule("every 2 h")
        assert result == {"type": "interval", "seconds": 7200}

    def test_invalid_returns_none(self):
        assert bot.parse_cron_schedule("sometime tomorrow") is None
        assert bot.parse_cron_schedule("") is None
        assert bot.parse_cron_schedule("weekly 09:00") is None

    def test_whitespace_stripped(self):
        result = bot.parse_cron_schedule("  daily 14:00  ")
        assert result == {"type": "daily", "hour": 14, "minute": 0}


# ── describe_cron_schedule ────────────────────────────────────────────────────

class TestDescribeCronSchedule:
    def test_daily(self):
        assert bot.describe_cron_schedule({"type": "daily", "hour": 9, "minute": 5}) == "daily 09:05"

    def test_interval_hours(self):
        assert bot.describe_cron_schedule({"type": "interval", "seconds": 7200}) == "every 2h"

    def test_interval_minutes(self):
        assert bot.describe_cron_schedule({"type": "interval", "seconds": 1800}) == "every 30m"

    def test_roundtrip(self):
        for spec in ["daily 08:15", "every 4h", "every 45m"]:
            parsed = bot.parse_cron_schedule(spec)
            assert parsed is not None
            assert bot.describe_cron_schedule(parsed) == spec


# ── _extract_json ─────────────────────────────────────────────────────────────

class TestExtractJson:
    def test_bare_json(self):
        assert bot._extract_json('{"key": "value"}') == {"key": "value"}

    def test_json_in_prose(self):
        raw = 'Here is the result:\n{"mood": "happy", "score": 0.8}\nHope that helps!'
        result = bot._extract_json(raw)
        assert result["mood"] == "happy"
        assert result["score"] == 0.8

    def test_json_in_code_fence(self):
        raw = '```json\n{"items": [1, 2, 3]}\n```'
        result = bot._extract_json(raw)
        assert result["items"] == [1, 2, 3]

    def test_empty_string(self):
        assert bot._extract_json("") == {}

    def test_none_input(self):
        assert bot._extract_json(None) == {}

    def test_no_json_at_all(self):
        assert bot._extract_json("just some plain text") == {}

    def test_nested_json(self):
        raw = '{"outer": {"inner": true}}'
        result = bot._extract_json(raw)
        assert result["outer"]["inner"] is True

    def test_malformed_json_returns_empty(self):
        assert bot._extract_json('{"broken": }') == {}

    def test_object_followed_by_stray_brace(self):
        # The greedy first-{-to-last-} span used to swallow both and lose the
        # valid first object (v2026-07-10.2 fix: balanced raw_decode fallback).
        assert bot._extract_json('{"mood": "ok"} and then { something') == {"mood": "ok"}

    def test_two_objects_takes_first(self):
        assert bot._extract_json('{"a": 1} {"b": 2}') == {"a": 1}


# ── parse_when (reminder time parsing) ────────────────────────────────────────

class TestParseWhen:
    def test_relative_minutes(self):
        dt, msg = bot.parse_when(["30m", "take", "a", "break"])
        assert dt is not None
        assert msg == "take a break"

    def test_relative_hours(self):
        dt, msg = bot.parse_when(["2h", "check", "oven"])
        assert dt is not None
        assert msg == "check oven"

    def test_relative_days(self):
        dt, msg = bot.parse_when(["3d", "follow", "up"])
        assert dt is not None
        assert msg == "follow up"

    def test_absolute_time(self):
        dt, msg = bot.parse_when(["14:30", "meeting"])
        assert dt is not None
        assert dt.hour == 14
        assert dt.minute == 30
        assert msg == "meeting"

    def test_tomorrow(self):
        dt, msg = bot.parse_when(["tomorrow", "09:00", "dentist"])
        assert dt is not None
        assert dt.hour == 9
        assert dt.minute == 0
        assert msg == "dentist"

    def test_date_format(self):
        dt, msg = bot.parse_when(["2026-12-25", "15:00", "christmas", "dinner"])
        assert dt is not None
        assert dt.month == 12
        assert dt.day == 25
        assert dt.hour == 15
        assert msg == "christmas dinner"

    def test_empty_returns_none(self):
        dt, msg = bot.parse_when([])
        assert dt is None
        assert msg is None

    def test_garbage_returns_none(self):
        dt, msg = bot.parse_when(["asdf"])
        assert dt is None
        assert msg is None


# ── _est_tokens ───────────────────────────────────────────────────────────────

class TestEstTokens:
    def test_short_string(self):
        assert bot._est_tokens("hi") >= 1

    def test_longer_string(self):
        text = "this is a longer piece of text with several words in it"
        result = bot._est_tokens(text)
        assert result > 5

    def test_empty_string(self):
        assert bot._est_tokens("") == 1


# ── _count_error tracking ────────────────────────────────────────────────────

# ── _cosine_sim ───────────────────────────────────────────────────────────────

class TestCosineSim:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert abs(bot._cosine_sim(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        assert abs(bot._cosine_sim([1, 0, 0], [0, 1, 0])) < 1e-6

    def test_opposite_vectors(self):
        assert abs(bot._cosine_sim([1, 0], [-1, 0]) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        assert bot._cosine_sim([0, 0], [1, 1]) == 0.0


# ── Group chat turn-taking / loop prevention (GROUP_CHAT_DESIGN.md) ─────────

def _human(msg_id=1, sender="Brian", text="hey"):
    return {"ts": 1000.0, "msg_id": msg_id, "sender": sender, "kind": "human",
            "text": text, "reply_to": None}


def _bot(msg_id=2, sender="Priya", text="hi", reply_to=None):
    return {"ts": 1000.0, "msg_id": msg_id, "sender": sender, "kind": "bot",
            "text": text, "reply_to": reply_to}


class TestParseLedgerLines:
    def test_valid_lines(self):
        lines = [json.dumps(_human(1)), json.dumps(_bot(2))]
        out = bot._parse_ledger_lines(lines)
        assert len(out) == 2
        assert out[0]["kind"] == "human"

    def test_bad_json_skipped(self):
        lines = ["{not json", json.dumps(_bot(2)), ""]
        out = bot._parse_ledger_lines(lines)
        assert len(out) == 1
        assert out[0]["msg_id"] == 2

    def test_missing_fields_skipped(self):
        out = bot._parse_ledger_lines(['{"kind": "bot"}', '{"msg_id": 5}',
                                       '{"msg_id": 5, "kind": "alien"}'])
        assert out == []


class TestBotChainLen:
    def test_empty(self):
        assert bot._bot_chain_len([]) == 0

    def test_all_human(self):
        assert bot._bot_chain_len([_human(1), _human(2)]) == 0

    def test_bot_tail(self):
        assert bot._bot_chain_len([_human(1), _bot(2), _bot(3)]) == 2

    def test_human_resets(self):
        assert bot._bot_chain_len([_bot(1), _bot(2), _human(3)]) == 0


class TestIsAddressed:
    def test_mention(self):
        assert bot._is_addressed("hey @priya_bot what up", "Priya", "priya_bot")

    def test_first_name_word_boundary(self):
        assert bot._is_addressed("priya, you're wrong", "Priya Sharma", "x_bot")
        assert bot._is_addressed("I think Jules is right", "Jules Nakagawa", "y_bot")

    def test_substring_is_not_a_match(self):
        assert not bot._is_addressed("I visited julesburg once", "Jules", "y_bot")
        assert not bot._is_addressed("priyanka called", "Priya", "x_bot")

    def test_reply_to_own(self):
        assert bot._is_addressed("totally", "Priya", "x_bot", replied_to_own=True)

    def test_unaddressed(self):
        assert not bot._is_addressed("nice weather today", "Priya", "priya_bot")

    def test_empty_text(self):
        assert not bot._is_addressed("", "Priya", "priya_bot")


class TestShouldReplyToBot:
    def test_cap_overrides_addressed(self):
        entries = [_human(1), _bot(2), _bot(3)]  # chain == GROUP_BOT_CHAIN_MAX (2)
        assert not bot._should_reply_to_bot(entries, prob_roll=0.0, addressed=True)

    def test_addressed_below_cap(self):
        entries = [_human(1), _bot(2)]
        assert bot._should_reply_to_bot(entries, prob_roll=0.99, addressed=True)

    def test_probability_gate(self):
        entries = [_human(1), _bot(2)]
        assert bot._should_reply_to_bot(entries, prob_roll=0.0, addressed=False)
        assert not bot._should_reply_to_bot(entries, prob_roll=0.99, addressed=False)


class TestClaimDelay:
    def test_jitter_range(self):
        entries = [_human(1)]
        assert abs(bot._claim_delay(entries, "Priya", 0.0) - 0.5) < 1e-9
        assert abs(bot._claim_delay(entries, "Priya", 1.0) - 3.0) < 1e-9

    def test_alternation_penalty_when_self_spoke_last(self):
        entries = [_human(1), _bot(2, sender="Priya")]
        base = bot._claim_delay([_human(1)], "Priya Sharma", 0.0)
        penalized = bot._claim_delay(entries, "Priya Sharma", 0.0)
        assert abs((penalized - base) - bot.GROUP_ALTERNATION_PENALTY) < 1e-9

    def test_no_penalty_when_peer_spoke_last(self):
        entries = [_human(1), _bot(2, sender="Jules")]
        assert abs(bot._claim_delay(entries, "Priya", 0.0) - 0.5) < 1e-9

    def test_last_bot_found_past_humans(self):
        # Humans after the bot don't hide it — "last BOT to speak" is what matters.
        entries = [_bot(1, sender="Priya"), _human(2)]
        assert bot._claim_delay(entries, "Priya", 0.0) > 2.0


class TestGroupLedgerPath:
    def test_negative_id_in_name(self):
        p = bot._group_ledger_path(-1001234)
        assert p.name == "group_-1001234.jsonl"


class TestGroupCommandAllowlist:
    def test_pinned_to_chatid_only(self):
        # Widening this is a deliberate act — see GROUP_CHAT_DESIGN.md §12 and the
        # group-cmd-allowlist eval. Update both together or not at all.
        assert bot.GROUP_ALLOWED_COMMANDS == {"chatid"}


# ── Own-day memory provenance (heartbeat hallucination fix, v2026-07-10.2) ──

class TestOwnDayFacts:
    def test_is_own_day(self):
        assert bot._is_own_day_fact("[own-day Jul 09] rode to Fremont")
        assert not bot._is_own_day_fact("has a job interview Tuesday")
        assert not bot._is_own_day_fact(None)

    def test_split(self):
        real, own = bot._split_own_day_facts(
            ["likes coffee", "[own-day Jul 09] rode to Fremont", "sister named Amy"])
        assert real == ["likes coffee", "sister named Amy"]
        assert own == ["[own-day Jul 09] rode to Fremont"]

    def test_split_empty_and_none(self):
        assert bot._split_own_day_facts([]) == ([], [])
        assert bot._split_own_day_facts(None) == ([], [])

    def test_retag_legacy(self):
        out = bot._retag_legacy_day_facts(
            ["[Jul 09] her day archive", "met Bob on Jul 09", "[own-day Jul 08] already tagged"])
        assert out[0] == "[own-day Jul 09] her day archive"
        assert out[1] == "met Bob on Jul 09"
        assert out[2] == "[own-day Jul 08] already tagged"

    def test_retag_spares_voice_notes(self):
        # handle_voice stores user voice notes with the same date-bracket prefix —
        # they are USER content, not her own fiction.
        out = bot._retag_legacy_day_facts(['[Jul 10] Voice note: "running late, start without me"'])
        assert out[0].startswith("[Jul 10] Voice note:")

    def test_memory_block_separates_own_days(self):
        cid = -424242
        for d in (bot.facts, bot.summaries, bot.recent_summaries):
            d.pop(cid, None)
        bot.recent_facts[cid] = ["works at a fintech startup",
                                 "[own-day Jul 09] biked to Meydenbauer Bay at sunset"]
        try:
            block = bot.memory_block(cid, "Brian")
            # Real fact under Recent specifics; her own day NOT there.
            recent_sec = block.split("# Your own recent days")[0]
            assert "works at a fintech startup" in recent_sec
            assert "Meydenbauer" not in recent_sec
            # Own day rendered under its clearly-framed section.
            assert "# Your own recent days" in block
            assert "Jul 09: biked to Meydenbauer Bay at sunset" in block
            assert "NOT shared memories" in block
        finally:
            bot.recent_facts.pop(cid, None)

    def test_memory_block_moves_own_day_out_of_longterm(self):
        cid = -424243
        for d in (bot.recent_facts, bot.summaries, bot.recent_summaries):
            d.pop(cid, None)
        bot.facts[cid] = ["[own-day Jul 07] a promoted archive", "real durable fact"]
        try:
            block = bot.memory_block(cid, "Brian")
            longterm_sec = block.split("# Your own recent days")[0]
            assert "real durable fact" in longterm_sec
            assert "promoted archive" not in longterm_sec
            assert "Jul 07: a promoted archive" in block
        finally:
            bot.facts.pop(cid, None)


# ── Native tool-call stripping (raw XML leak fix, v2026-07-10.2) ─────────────

class TestStripNativeToolCalls:
    # The exact payload Priya leaked to the user on 2026-07-09.
    LEAKED = ("<tool_call>\n<function=search>\n"
              "<parameter=query>Seattle news today July 9 2026</parameter>\n"
              "</function>\n</tool_call>")

    def test_leaked_payload_becomes_search_tag(self):
        out = bot._strip_native_tool_calls(self.LEAKED)
        assert out == "[search: Seattle news today July 9 2026]"

    def test_embedded_in_prose(self):
        out = bot._strip_native_tool_calls(
            "hang on let me check\n" + self.LEAKED + "\nback in a sec")
        assert "<tool_call" not in out
        assert "[search: Seattle news today July 9 2026]" in out
        assert "hang on let me check" in out

    def test_non_search_tool_call_stripped(self):
        block = ("<tool_call><function=get_weather>"
                 "<parameter=city>Seattle</parameter></function></tool_call>")
        assert bot._strip_native_tool_calls("sure! " + block) == "sure!"

    def test_truncated_block_stripped(self):
        out = bot._strip_native_tool_calls(
            "one sec\n<tool_call>\n<function=search>\n<parameter=query>half a")
        assert out == "one sec"

    def test_bare_function_block(self):
        out = bot._strip_native_tool_calls(
            "<function=search>\n<parameter=query>bike routes fremont</parameter>\n</function>")
        assert out == "[search: bike routes fremont]"

    def test_clean_text_unchanged(self):
        text = "just a normal reply about my day <3"
        assert bot._strip_native_tool_calls(text) == text

    def test_search_query_survives_intact(self):
        # The converted tag must be parseable by the existing [search:] extractor.
        out = bot._strip_native_tool_calls(self.LEAKED)
        import re as _re
        m = _re.search(r"\[search:\s*(.*?)\]", out)
        assert m and m.group(1) == "Seattle news today July 9 2026"


# ── Config id-set parsing (import-crash fix, v2026-07-10.2) ──────────────────

class TestParseIdSet:
    def test_normal(self):
        assert bot._parse_id_set("123, 456", "T") == {123, 456}

    def test_negative_group_ids(self):
        assert bot._parse_id_set("-1001234567890", "T") == {-1001234567890}

    def test_bad_tokens_skipped_not_fatal(self):
        # '--123' passed the old isdigit-after-lstrip filter but crashed int().
        assert bot._parse_id_set("--123, 456, abc, ", "T") == {456}

    def test_empty(self):
        assert bot._parse_id_set("", "T") == set()


# ── Env parsing that can't brick the fleet (v2026-07-10.2) ───────────────────

class TestEnvHelpers:
    def test_env_int_good(self, monkeypatch):
        monkeypatch.setenv("X_TEST_INT", "42")
        assert bot._env_int("X_TEST_INT", "7") == 42

    def test_env_int_bad_value_falls_back(self, monkeypatch):
        monkeypatch.setenv("X_TEST_INT", "not-a-number")
        assert bot._env_int("X_TEST_INT", "7") == 7

    def test_env_int_unset_uses_default(self, monkeypatch):
        monkeypatch.delenv("X_TEST_INT", raising=False)
        assert bot._env_int("X_TEST_INT", "7") == 7

    def test_env_float_no_default_means_none(self, monkeypatch):
        monkeypatch.delenv("X_TEST_F", raising=False)
        assert bot._env_float("X_TEST_F") is None

    def test_env_float_bad_with_default(self, monkeypatch):
        monkeypatch.setenv("X_TEST_F", "abc")
        assert bot._env_float("X_TEST_F", "0.5") == 0.5

    def test_env_float_empty_string_uses_default(self, monkeypatch):
        monkeypatch.setenv("X_TEST_F", "")
        assert bot._env_float("X_TEST_F", "0.5") == 0.5


# ── Schedule day-heading matching (v2026-07-10.2) ────────────────────────────

class TestScheduleHeadings:
    def _today_section(self, tmp_path, text, monkeypatch, today="Monday"):
        sched = tmp_path / "schedule.txt"
        sched.write_text(text, encoding="utf-8")
        monkeypatch.setattr(bot, "SCHEDULE_FILE", sched)

        class _FakeDT:
            @staticmethod
            def now(tz=None):
                import datetime as _dt
                # 2026-07-06 was a Monday; 07-07 Tuesday
                base = {"Monday": _dt.datetime(2026, 7, 6, 12, 0),
                        "Tuesday": _dt.datetime(2026, 7, 7, 12, 0)}[today]
                return base.replace(tzinfo=tz) if tz else base

        monkeypatch.setattr(bot, "datetime", _FakeDT)
        try:
            return bot._read_schedule_today()
        finally:
            monkeypatch.undo()

    def test_money_is_not_monday(self, tmp_path, monkeypatch):
        text = "Monday\n- standup 9am\nmoney is tight this week\nTuesday\n- dentist"
        out = self._today_section(tmp_path, text, monkeypatch, today="Monday")
        # "money is tight" must be treated as content, not a new heading
        assert "standup" in out
        assert "money is tight" in out
        assert "dentist" not in out

    def test_real_headings_still_work(self, tmp_path, monkeypatch):
        text = "Mon:\n- standup\nTue:\n- dentist\nWed:\n- gym"
        out = self._today_section(tmp_path, text, monkeypatch, today="Tuesday")
        assert "dentist" in out
        assert "standup" not in out
        assert "gym" not in out


# ── _count_error tracking ────────────────────────────────────────────────────

class TestCountError:
    def test_counts_increment(self):
        cat = "_test_category_unique"
        bot._error_counts.pop(cat, None)
        bot._count_error(cat)
        bot._count_error(cat)
        assert len(bot._error_counts[cat]) == 2

    def test_caps_at_200(self):
        cat = "_test_cap_unique"
        bot._error_counts.pop(cat, None)
        for _ in range(250):
            bot._count_error(cat)
        assert len(bot._error_counts[cat]) == 200


# ── Quote grounding (R1 memory auditor, anti-hallucination) ──────────────────

class TestQuoteGrounded:
    def test_exact_match(self):
        assert bot._quote_grounded("my sister got married", ["my sister got married last week"])

    def test_case_insensitive(self):
        assert bot._quote_grounded("My Sister Got Married", ["my sister got married last week"])

    def test_whitespace_tolerance(self):
        assert bot._quote_grounded("my  sister   got married", ["my sister got married last week"])

    def test_substring_of_user_line(self):
        assert bot._quote_grounded("job interview", ["I have a job interview on Tuesday"])

    def test_assistant_line_not_matched(self):
        # Only user lines are passed — but verify the function doesn't match on wrong input
        assert not bot._quote_grounded("rode my bike to Fremont", [])

    def test_fabricated_quote(self):
        assert not bot._quote_grounded(
            "I'm getting a divorce",
            ["my sister got married last week", "we had dinner on Friday"])

    def test_empty_quote(self):
        assert not bot._quote_grounded("", ["some user line"])

    def test_empty_user_lines(self):
        assert not bot._quote_grounded("something", [])

    def test_none_handling(self):
        assert not bot._quote_grounded(None, ["line"])
        assert not bot._quote_grounded("quote", None)


# ── Memory replace (R1 memory auditor) ───────────────────────────────────────

class TestMemoryReplace:
    def test_add_new_line(self, tmp_path):
        bot.MEMORIES_FILE.write_text("line one\nline two\n", encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        result = bot._memory_replace(None, "line three", meta={"origin": "test"})
        assert result is True
        content = bot.MEMORIES_FILE.read_text(encoding="utf-8")
        assert "line three" in content
        assert bot._memory_meta.get("line three", {}).get("origin") == "test"

    def test_delete_line(self, tmp_path):
        bot.MEMORIES_FILE.write_text("line one\nline two\n", encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        result = bot._memory_replace("line one", None)
        assert result is True
        content = bot.MEMORIES_FILE.read_text(encoding="utf-8")
        assert "line one" not in content
        assert "line two" in content

    def test_edit_line(self, tmp_path):
        bot.MEMORIES_FILE.write_text("old text\nkeep this\n", encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        result = bot._memory_replace("old text", "new text", meta={"origin": "edit"})
        assert result is True
        content = bot.MEMORIES_FILE.read_text(encoding="utf-8")
        assert "old text" not in content
        assert "new text" in content

    def test_delete_nonexistent_returns_false(self, tmp_path):
        bot.MEMORIES_FILE.write_text("line one\n", encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        result = bot._memory_replace("nonexistent", None)
        assert result is False


# ── Availability awareness (R2) ──────────────────────────────────────────────

class TestIsAway:
    def setup_method(self):
        bot.away.clear()
        self._orig_save = bot.save_state
        bot.save_state = lambda: None

    def teardown_method(self):
        bot.away.clear()
        bot.save_state = self._orig_save

    def test_not_away_when_empty(self):
        assert bot._is_away(123) is False

    def test_away_when_set(self):
        bot.away[123] = {"reason": "driving", "since": time.time(), "origin": "manual", "expires": None}
        assert bot._is_away(123) is True

    def test_expired_away_clears(self):
        bot.away[123] = {"reason": "meeting", "since": time.time() - 7200,
                         "origin": "auto", "expires": time.time() - 1}
        assert bot._is_away(123) is False
        assert 123 not in bot.away

    def test_no_expiry_stays(self):
        bot.away[123] = {"reason": "vacation", "since": time.time() - 86400,
                         "origin": "manual", "expires": None}
        assert bot._is_away(123) is True


class TestClearAway:
    def setup_method(self):
        bot.away.clear()

    def teardown_method(self):
        bot.away.clear()

    def test_clear_returns_old_entry(self):
        entry = {"reason": "driving", "since": 1.0, "origin": "manual", "expires": None}
        bot.away[123] = entry
        old = bot._clear_away(123)
        assert old == entry
        assert 123 not in bot.away

    def test_clear_when_not_away_returns_none(self):
        assert bot._clear_away(999) is None


class TestVibePresetsR2:
    def test_busy_preset_exists(self):
        assert "busy" in bot.VIBE_PROMPTS

    def test_working_preset_exists(self):
        assert "working" in bot.VIBE_PROMPTS

    def test_driving_preset_exists(self):
        assert "driving" in bot.VIBE_PROMPTS

    def test_in_person_still_exists(self):
        assert "in-person" in bot.VIBE_PROMPTS


# ── R3: Observability & robustness ──────────────────────────────────────────

class TestAtomicWriteText:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "test.json"
        bot._atomic_write_text(p, '{"key": "value"}')
        assert p.read_text(encoding="utf-8") == '{"key": "value"}'

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text("old", encoding="utf-8")
        bot._atomic_write_text(p, "new")
        assert p.read_text(encoding="utf-8") == "new"

    def test_no_partial_write_on_disk(self, tmp_path):
        p = tmp_path / "data.json"
        bot._atomic_write_text(p, "complete")
        tmp = p.with_name(p.name + ".tmp")
        assert not tmp.exists()


class TestConfigWarnings:
    def test_list_exists(self):
        assert isinstance(bot._CONFIG_WARNINGS, list)

    def test_env_int_bad_value_collects_warning(self):
        import os
        os.environ["_TEST_BAD_INT"] = "not_a_number"
        before = len(bot._CONFIG_WARNINGS)
        result = bot._env_int("_TEST_BAD_INT", "42")
        assert result == 42
        assert len(bot._CONFIG_WARNINGS) > before
        assert "_TEST_BAD_INT" in bot._CONFIG_WARNINGS[-1]
        del os.environ["_TEST_BAD_INT"]
        bot._CONFIG_WARNINGS.pop()

    def test_env_float_bad_value_collects_warning(self):
        import os
        os.environ["_TEST_BAD_FLOAT"] = "xyz"
        before = len(bot._CONFIG_WARNINGS)
        result = bot._env_float("_TEST_BAD_FLOAT", "3.14")
        assert result == 3.14
        assert len(bot._CONFIG_WARNINGS) > before
        del os.environ["_TEST_BAD_FLOAT"]
        bot._CONFIG_WARNINGS.pop()


class TestTrackLlmUsage:
    def test_increments_calls(self):
        old_calls = bot._llm_stats["calls"]
        bot._track_llm_usage([{"content": "hello"}], "world")
        assert bot._llm_stats["calls"] == old_calls + 1
        assert bot._llm_stats["date"] == time.strftime("%Y-%m-%d")

    def test_resets_on_new_day(self):
        bot._llm_stats["date"] = "1999-01-01"
        bot._llm_stats["calls"] = 99
        bot._track_llm_usage([{"content": "test"}], "reply")
        assert bot._llm_stats["calls"] == 1
        assert bot._llm_stats["date"] == time.strftime("%Y-%m-%d")

    def test_estimates_tokens(self):
        bot._llm_stats["date"] = time.strftime("%Y-%m-%d")
        bot._llm_stats["tok_in"] = 0
        bot._llm_stats["tok_out"] = 0
        msgs = [{"content": "a" * 100}]
        bot._track_llm_usage(msgs, "b" * 40)
        assert bot._llm_stats["tok_in"] == 25
        assert bot._llm_stats["tok_out"] == 10


class TestErrorCountsPersistence:
    def test_serialize_includes_error_counts(self):
        bot._error_counts["test_cat"] = [1.0, 2.0, 3.0]
        payload = json.loads(bot._serialize_state())
        assert "error_counts" in payload
        assert payload["error_counts"]["test_cat"] == [1.0, 2.0, 3.0]
        del bot._error_counts["test_cat"]

    def test_serialize_includes_llm_stats(self):
        payload = json.loads(bot._serialize_state())
        assert "llm_stats" in payload
        assert "calls" in payload["llm_stats"]


class TestGatherAuditData:
    def test_includes_config_warnings(self):
        d = bot.gather_audit_data()
        assert "config_warnings" in d
        assert isinstance(d["config_warnings"], list)

    def test_includes_llm_stats(self):
        d = bot.gather_audit_data()
        assert "llm_stats" in d
        assert "calls" in d["llm_stats"]


# ── R4: Prompt hygiene & safety ─────────────────────────────────────────────

class TestTrimHistoryToBudget:
    def test_noop_when_under_budget(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ]
        result = bot._trim_history_to_budget(list(msgs), 10000)
        assert len(result) == 4

    def test_disabled_when_zero(self):
        msgs = [{"role": "user", "content": "x" * 100000}]
        result = bot._trim_history_to_budget(list(msgs), 0)
        assert len(result) == 1

    def test_drops_oldest_history_first(self):
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "new message"},
        ]
        result = bot._trim_history_to_budget(list(msgs), 20)
        roles = [m["role"] for m in result]
        assert "system" in roles
        assert result[-1]["content"] == "new message"

    def test_never_drops_system(self):
        msgs = [
            {"role": "system", "content": "x" * 400},
            {"role": "user", "content": "hi"},
        ]
        result = bot._trim_history_to_budget(list(msgs), 50)
        assert any(m["role"] == "system" for m in result)

    def test_never_drops_final_user(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "a" * 400},
            {"role": "user", "content": "final question"},
        ]
        result = bot._trim_history_to_budget(list(msgs), 30)
        assert result[-1]["content"] == "final question"


class TestTriggeredLoreDedupe:
    def test_no_duplicates(self):
        original_lore = list(bot.LORE)
        bot.LORE.append({"keys": ["testxyz"], "content": "shared entry", "constant": False})
        bot.LORE.append({"keys": ["testxyz"], "content": "shared entry", "constant": False})
        try:
            results = bot.triggered_lore("testxyz is here")
            assert results.count("shared entry") == 1
        finally:
            bot.LORE[:] = original_lore


class TestStripPersonaBreaks:
    def test_strips_ai_admission(self):
        text = "I'm an AI assistant. How can I help?"
        result = bot._strip_persona_breaks(text)
        assert "AI" not in result

    def test_strips_as_an_ai(self):
        text = "As an AI language model, I cannot feel. But I think it's cool."
        result = bot._strip_persona_breaks(text)
        assert "AI" not in result
        assert "cool" in result

    def test_strips_no_feelings(self):
        text = "I don't have feelings like humans do. Anyway, what's up?"
        result = bot._strip_persona_breaks(text)
        assert "feelings" not in result
        assert "what's up" in result

    def test_strips_large_language_model(self):
        text = "I am a large language model. Let me help."
        result = bot._strip_persona_breaks(text)
        assert "large language model" not in result

    def test_preserves_third_person_ai_reference(self):
        text = "My AI coworker shipped a bug today."
        result = bot._strip_persona_breaks(text)
        assert result == text

    def test_preserves_non_first_person(self):
        text = "That AI tool is pretty cool."
        result = bot._strip_persona_breaks(text)
        assert result == text

    def test_empty_after_strip_returns_empty(self):
        text = "I'm an AI and I don't have personal experiences."
        result = bot._strip_persona_breaks(text)
        assert result == ""

    def test_clean_text_unchanged(self):
        text = "I had a great day at work. The weather was nice."
        assert bot._strip_persona_breaks(text) == text


class TestSummarizeSemaphore:
    def test_semaphore_exists(self):
        assert hasattr(bot, '_SUMMARIZE_SEM')
        assert isinstance(bot._SUMMARIZE_SEM, asyncio.Semaphore)


# ── _in_quiet_window ─────────────────────────────────────────────────────────

from datetime import datetime


class TestInQuietWindow:
    def _dt(self, dow, hour, minute):
        """Build a datetime with a specific weekday. 2026-07-06 is a Monday (dow=0)."""
        from datetime import timedelta
        base = datetime(2026, 7, 6, hour, minute)  # Monday
        return base + timedelta(days=dow)

    def test_empty_windows(self):
        now = self._dt(4, 23, 30)  # Fri 23:30
        assert bot._in_quiet_window(now, []) is False

    def test_simple_window_inside(self):
        # Fri 22:00-23:30, check at Fri 22:15
        windows = [{"dow": 4, "start": 22 * 60, "end": 23 * 60 + 30}]
        assert bot._in_quiet_window(self._dt(4, 22, 15), windows) is True

    def test_simple_window_outside(self):
        windows = [{"dow": 4, "start": 22 * 60, "end": 23 * 60 + 30}]
        assert bot._in_quiet_window(self._dt(4, 21, 59), windows) is False
        assert bot._in_quiet_window(self._dt(4, 23, 30), windows) is False

    def test_wrong_day(self):
        # Window is Friday, check on Saturday same time
        windows = [{"dow": 4, "start": 22 * 60, "end": 23 * 60 + 30}]
        assert bot._in_quiet_window(self._dt(5, 22, 15), windows) is False

    def test_midnight_crossing_same_night(self):
        # Fri 23:00-08:00, check at Fri 23:30
        windows = [{"dow": 4, "start": 23 * 60, "end": 8 * 60}]
        assert bot._in_quiet_window(self._dt(4, 23, 30), windows) is True

    def test_midnight_crossing_next_morning(self):
        # Fri 23:00-08:00, check at Sat 07:00 (next day after the window started)
        windows = [{"dow": 4, "start": 23 * 60, "end": 8 * 60}]
        assert bot._in_quiet_window(self._dt(5, 7, 0), windows) is True

    def test_midnight_crossing_after_end(self):
        # Fri 23:00-08:00, check at Sat 08:00 (end, exclusive)
        windows = [{"dow": 4, "start": 23 * 60, "end": 8 * 60}]
        assert bot._in_quiet_window(self._dt(5, 8, 0), windows) is False

    def test_midnight_crossing_wrong_day(self):
        # Fri 23:00-08:00, check on Thu 23:30
        windows = [{"dow": 4, "start": 23 * 60, "end": 8 * 60}]
        assert bot._in_quiet_window(self._dt(3, 23, 30), windows) is False

    def test_boundary_start_inclusive(self):
        windows = [{"dow": 2, "start": 10 * 60, "end": 12 * 60}]
        assert bot._in_quiet_window(self._dt(2, 10, 0), windows) is True

    def test_boundary_end_exclusive(self):
        windows = [{"dow": 2, "start": 10 * 60, "end": 12 * 60}]
        assert bot._in_quiet_window(self._dt(2, 12, 0), windows) is False

    def test_multiple_windows(self):
        windows = [
            {"dow": 0, "start": 22 * 60, "end": 6 * 60},  # Mon night
            {"dow": 4, "start": 23 * 60, "end": 8 * 60},  # Fri night
        ]
        assert bot._in_quiet_window(self._dt(0, 23, 0), windows) is True
        assert bot._in_quiet_window(self._dt(4, 23, 30), windows) is True
        assert bot._in_quiet_window(self._dt(2, 23, 0), windows) is False


# ── _compute_closeness ───────────────────────────────────────────────────────

class TestComputeCloseness:
    def test_zero_inputs(self):
        score, bucket = bot._compute_closeness(0, 0, 0, 0)
        assert score == 0.0
        assert bucket == "getting to know each other"

    def test_all_maxed(self):
        score, bucket = bot._compute_closeness(100, 1000, 20, 10)
        assert score == 1.0
        assert bucket == "deeply familiar"

    def test_mid_range(self):
        score, bucket = bot._compute_closeness(30, 250, 4, 3)
        assert 0.33 <= score < 0.66
        assert bucket == "comfortable"

    def test_fresh_user(self):
        score, bucket = bot._compute_closeness(3, 20, 0, 0)
        assert score < 0.33
        assert bucket == "getting to know each other"

    def test_deeply_familiar_threshold(self):
        score, bucket = bot._compute_closeness(60, 500, 8, 6)
        assert score >= 0.66
        assert bucket == "deeply familiar"


# ── TomTom Maps (routing + place/POI search) ──────────────────────────────────
# Pure parsers/formatters only; the network fetch helpers are exercised on-device
# (they need TOMTOM_API_KEY). Formatters are defensive/total — a shape change must
# degrade to a message, never crash a bot mid-reply.

class TestParseRouteQuery:
    def test_simple(self):
        assert bot._parse_route_query("Bellevue to Seattle") == ("Bellevue", "Seattle")

    def test_from_prefix(self):
        assert bot._parse_route_query("from Bellevue to SeaTac airport") == ("Bellevue", "SeaTac airport")

    def test_splits_on_last_to(self):
        # 'Toronto' contains no ' to '; a destination that literally does must survive.
        assert bot._parse_route_query("A to B to C") == ("A to B", "C")

    def test_no_separator(self):
        assert bot._parse_route_query("just one place") is None

    def test_empty_side(self):
        assert bot._parse_route_query("to Seattle") is None
        assert bot._parse_route_query("Bellevue to ") is None

    def test_empty_and_none(self):
        assert bot._parse_route_query("") is None
        assert bot._parse_route_query(None) is None


class TestFmtDistanceDuration:
    def test_miles(self):
        assert bot._fmt_distance(1609.344) == "1.0 mi"

    def test_feet_under_tenth_mile(self):
        assert bot._fmt_distance(100).endswith("ft")

    def test_distance_bad_input(self):
        assert bot._fmt_distance(None) == "?"
        assert bot._fmt_distance("x") == "?"

    def test_minutes(self):
        assert bot._fmt_duration(1800) == "30 min"

    def test_hours_exact(self):
        assert bot._fmt_duration(3600) == "1 hr"

    def test_hours_and_minutes(self):
        assert bot._fmt_duration(3660) == "1 hr 1 min"

    def test_duration_bad_input(self):
        assert bot._fmt_duration(None) == "?"
        assert bot._fmt_duration("x") == "?"


class TestTomTomMode:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("TOMTOM_TRAVEL_MODE", raising=False)
        assert bot._tomtom_mode() == "car"

    def test_valid_mode(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_TRAVEL_MODE", "Bicycle")
        assert bot._tomtom_mode() == "bicycle"

    def test_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_TRAVEL_MODE", "hovercraft")
        assert bot._tomtom_mode() == "car"


class TestFormatRoute:
    def test_basic(self):
        out = bot._format_route(
            {"routes": [{"summary": {"travelTimeInSeconds": 1830, "lengthInMeters": 21000,
                                     "trafficDelayInSeconds": 180}}]}, "car")
        assert "30 min" in out and "13.0 mi" in out and "traffic" in out

    def test_mode_icon(self):
        out = bot._format_route(
            {"routes": [{"summary": {"travelTimeInSeconds": 600, "lengthInMeters": 2000}}]}, "bicycle")
        assert "🚲" in out

    def test_no_traffic_note_when_small(self):
        out = bot._format_route(
            {"routes": [{"summary": {"travelTimeInSeconds": 600, "lengthInMeters": 2000,
                                     "trafficDelayInSeconds": 30}}]}, "car")
        assert "traffic" not in out

    def test_empty_and_malformed(self):
        assert bot._format_route({"routes": []}, "car") == "No route found."
        assert bot._format_route({}, "car") == "No route found."
        assert bot._format_route(None, "car") == "No route found."


class TestFormatPlaceAndNearby:
    def test_place_name_and_address(self):
        out = bot._format_place_results(
            [{"poi": {"name": "Pike Place Market", "phone": "206-555-0100"},
              "address": {"freeformAddress": "85 Pike St, Seattle"}}])
        assert "Pike Place Market" in out and "85 Pike St" in out and "206-555-0100" in out

    def test_place_empty(self):
        assert bot._format_place_results([]) == "No matches found."
        assert bot._format_place_results(None) == "No matches found."

    def test_nearby_sorted_by_distance(self):
        out = bot._format_nearby_results([
            {"poi": {"name": "Far"}, "address": {}, "dist": 900},
            {"poi": {"name": "Near"}, "address": {}, "dist": 50},
        ])
        assert out.index("Near") < out.index("Far")

    def test_nearby_empty(self):
        assert bot._format_nearby_results([]) == "Nothing found nearby."

    def test_nearby_missing_fields_no_crash(self):
        # Total: a result with no poi/address/dist must still render a line.
        out = bot._format_nearby_results([{}])
        assert "Unknown" in out


class TestFoodFormatting:
    def test_cuisine_prefers_specific(self):
        assert bot._poi_cuisine({"categories": ["restaurant", "thai"]}) == "thai"

    def test_cuisine_generic_only(self):
        assert bot._poi_cuisine({"categories": ["restaurant"]}) == "restaurant"

    def test_cuisine_underscores_spaced(self):
        assert bot._poi_cuisine({"categories": ["restaurant", "fast_food"]}) == "fast food"

    def test_cuisine_empty(self):
        assert bot._poi_cuisine({}) == "" and bot._poi_cuisine(None) == ""

    def test_restaurants_sorted_with_cuisine_and_distance(self):
        out = bot._format_restaurants([
            {"poi": {"name": "Far Thai", "categories": ["restaurant", "thai"]}, "dist": 900},
            {"poi": {"name": "Near Ramen", "categories": ["restaurant", "ramen"]}, "dist": 100},
        ])
        assert out.index("Near Ramen") < out.index("Far Thai")
        assert "thai" in out and "ramen" in out and "mi" in out

    def test_restaurants_empty(self):
        assert bot._format_restaurants([]) == "No restaurants found nearby."

    def test_restaurants_missing_fields_no_crash(self):
        assert "Unknown" in bot._format_restaurants([{}])


class TestFoodQueryDetection:
    def test_positive_phrases(self):
        for t in ["where should i eat?", "i'm starving", "any good restaurants nearby",
                  "what should i eat", "let's grab a bite", "somewhere to eat for dinner"]:
            assert bot._is_food_query(t), t

    def test_negative_phrases(self):
        for t in ["how's your day", "i love you", "did you finish the report",
                  "the weather is nice", ""]:
            assert not bot._is_food_query(t), t

    def test_none_safe(self):
        assert bot._is_food_query(None) is False


class TestRestaurantsBrief:
    def test_plain_sorted_no_emoji(self):
        out = bot._restaurants_brief([
            {"poi": {"name": "Far", "categories": ["restaurant", "thai"]}, "dist": 800},
            {"poi": {"name": "Near", "categories": ["restaurant", "ramen"]}, "dist": 90},
        ])
        assert out.index("Near") < out.index("Far")
        assert "🍽" not in out and "(ramen, " in out

    def test_skips_nameless(self):
        assert bot._restaurants_brief([{"poi": {}}, {"address": {}}]) == ""

    def test_empty(self):
        assert bot._restaurants_brief([]) == ""


class TestBuildCommandMenu:
    @staticmethod
    def _names(cmds):
        return {c.command for c in cmds}

    def test_maps_always_present(self):
        # The maps handlers are registered unconditionally, so the menu must list them.
        assert {"route", "nearby", "place", "food"} <= self._names(bot._build_command_menu(False, False))

    def test_traffic_and_payments_gated(self):
        off = self._names(bot._build_command_menu(False, False))
        assert "traffic" not in off and "addpayment" not in off
        on = self._names(bot._build_command_menu(True, True))
        assert {"traffic", "incidents", "addpayment"} <= on

    def test_base_present(self):
        assert "help" in self._names(bot._build_command_menu(False, False))


class TestTallyUnexpectedRestarts:
    CUT = bot.datetime(2026, 7, 11, 17, 0, 0)

    @staticmethod
    def _audit(t):
        return f"2026-07-11 {t} [WARNING] companion: === STARTUP AUDIT === v1 | Instance: x"

    def test_crashes_counted(self):
        lines = [self._audit("17:05:00"), self._audit("17:20:00"), self._audit("17:40:00")]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 3

    def test_user_restart_and_update_excluded(self):
        lines = [
            "2026-07-11 17:05:00 [WARNING] companion: [restart] requested via /restart",
            self._audit("17:05:05"),
            "2026-07-11 17:20:00 [WARNING] companion: [update] v1 -> v2; restarting",
            self._audit("17:20:05"),
        ]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 0

    def test_mixed_counts_only_crash(self):
        lines = [
            "2026-07-11 17:05:00 [WARNING] companion: [restart] requested via /restart",
            self._audit("17:05:05"),      # intentional → excluded
            self._audit("17:30:00"),      # crash → counted
        ]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 1

    def test_outside_window_excluded(self):
        lines = [self._audit("16:30:00"), self._audit("17:30:00")]  # first is before cutoff
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 1

    def test_graceful_stop_alone_still_counts(self):
        # A graceful-stop WITHOUT a /restart or /update marker (e.g. a battery-manager
        # SIGTERM) is a real restart and must still be counted.
        lines = [
            "2026-07-11 17:10:00 [WARNING] companion: [shutdown] graceful stop — saving state.",
            self._audit("17:10:07"),
        ]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 1


class TestTomTomRouteParams:
    def test_route_type_is_rest_spelling(self):
        # The raw REST API uses "fastest", not the MCP tool's "fast" — pin it so the
        # HTTP-400 ("Invalid route type: [fast]") regression can't come back.
        assert bot._tomtom_route_params("car")["routeType"] == "fastest"
        assert bot._tomtom_route_params("bicycle")["routeType"] == "fastest"

    def test_motorized_gets_traffic(self):
        p = bot._tomtom_route_params("car")
        assert p["travelMode"] == "car" and p.get("traffic") == "true"

    def test_bicycle_no_traffic(self):
        # traffic=true + bicycle makes TomTom 400; it must be omitted.
        assert "traffic" not in bot._tomtom_route_params("bicycle")

    def test_pedestrian_no_traffic(self):
        assert "traffic" not in bot._tomtom_route_params("pedestrian")


class TestTomTomErrReason:
    class _Resp:
        def __init__(self, code, body=None):
            self.status_code = code
            self._body = body

        def json(self):
            if self._body is None:
                raise ValueError("no json")
            return self._body

    class _HTTPErr(Exception):
        def __init__(self, code, body=None):
            self.response = TestTomTomErrReason._Resp(code, body)

    def test_401_says_key_rejected(self):
        r = bot._tomtom_err_reason(self._HTTPErr(401))
        assert "key rejected" in r and "401" in r

    def test_403_says_key_rejected(self):
        assert "key rejected" in bot._tomtom_err_reason(self._HTTPErr(403))

    def test_429_rate_limited(self):
        assert "rate limited" in bot._tomtom_err_reason(self._HTTPErr(429))

    def test_other_http_code_no_body(self):
        assert bot._tomtom_err_reason(self._HTTPErr(500)) == "HTTP 500"

    def test_400_includes_tomtom_message(self):
        e = self._HTTPErr(400, {"detailedError": {"message": "Traffic unsupported for Bicycle"}})
        r = bot._tomtom_err_reason(e)
        assert "400" in r and "Traffic unsupported for Bicycle" in r

    def test_400_error_description_shape(self):
        e = self._HTTPErr(400, {"error": {"description": "bad param"}})
        assert "bad param" in bot._tomtom_err_reason(e)

    def test_timeout(self):
        assert bot._tomtom_err_reason(TimeoutError()) == "timed out"

    def test_connection(self):
        assert bot._tomtom_err_reason(ConnectionError()) == "network/DNS error"

    def test_reason_never_leaks_url_or_key(self):
        # The whole point: the reason must never carry the request URL (which holds the key).
        bodies = [None, {"message": "key=SECRET leaked"}, {"detailedError": {"message": "ok"}}]
        for code in (401, 500, 400):
            for b in bodies:
                r = bot._tomtom_err_reason(self._HTTPErr(code, b)).lower()
                assert "tomtom.com" not in r and "key=" not in r
        for e in (TimeoutError(), ConnectionError()):
            assert "key=" not in bot._tomtom_err_reason(e).lower()


# ── Memory loops (v2026-07-12.1): recency decay, hedging, weekly audit ────────

class TestRecencyWeight:
    def test_disabled_halflife_is_neutral(self):
        assert bot._recency_weight(time.time() - 86400 * 365, time.time(), 0) == 1.0

    def test_no_timestamp_is_neutral(self):
        # Legacy pre-meta memories are never punished.
        assert bot._recency_weight(None, time.time(), 90) == 1.0
        assert bot._recency_weight(0, time.time(), 90) == 1.0
        assert bot._recency_weight("bogus", time.time(), 90) == 1.0

    def test_fresh_memory_full_weight(self):
        now = time.time()
        assert bot._recency_weight(now, now, 90) == 1.0

    def test_half_at_halflife(self):
        now = time.time()
        w = bot._recency_weight(now - 90 * 86400, now, 90)
        assert abs(w - 0.5) < 0.01

    def test_floor_at_point_one(self):
        now = time.time()
        assert bot._recency_weight(now - 90 * 86400 * 50, now, 90) == 0.1

    def test_monotonic_decreasing(self):
        now = time.time()
        weights = [bot._recency_weight(now - d * 86400, now, 90)
                   for d in (0, 30, 90, 180, 365)]
        assert weights == sorted(weights, reverse=True)


class TestHedgeMemoryLines:
    def test_low_confidence_hedged(self):
        meta = {"saw a fox": {"confidence": 4}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert out == ["(unsure) saw a fox"] and hedged is True

    def test_high_confidence_unmarked(self):
        meta = {"saw a fox": {"confidence": 9}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert out == ["saw a fox"] and hedged is False

    def test_at_threshold_unmarked(self):
        meta = {"saw a fox": {"confidence": 7}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert out == ["saw a fox"] and hedged is False

    def test_legacy_no_meta_unmarked(self):
        out, hedged = bot._hedge_memory_lines(["old memory"], {}, 7, True)
        assert out == ["old memory"] and hedged is False

    def test_disabled_passthrough(self):
        meta = {"saw a fox": {"confidence": 1}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, False)
        assert out == ["saw a fox"] and hedged is False

    def test_input_not_mutated(self):
        lines = ["saw a fox"]
        bot._hedge_memory_lines(lines, {"saw a fox": {"confidence": 1}}, 7, True)
        assert lines == ["saw a fox"]


class TestAuditPairKey:
    def test_order_insensitive(self):
        assert bot._audit_pair_key(["a b", "c d"]) == bot._audit_pair_key(["c d", "a b"])

    def test_whitespace_and_case_normalized(self):
        assert bot._audit_pair_key(["A  b "]) == bot._audit_pair_key(["a b"])

    def test_distinct_pairs_distinct(self):
        assert bot._audit_pair_key(["a", "b"]) != bot._audit_pair_key(["a", "c"])


class TestParseAuditFindings:
    entries = ["likes tea", "hates tea", "moved to Austin", "moved to Bellevue",
               "has a dog", "plays chess", "runs daily", "reads sci-fi"]

    def test_valid_merge(self):
        data = {"findings": [{"type": "contradiction", "lines": [1, 2],
                              "action": "merge", "merged_text": "tea feelings evolved",
                              "reason": "conflict"}]}
        out = bot._parse_audit_findings(data, self.entries, 3)
        assert len(out) == 1
        assert out[0]["targets"] == ["likes tea", "hates tea"]
        assert out[0]["merged_text"] == "tea feelings evolved"

    def test_valid_delete(self):
        data = {"findings": [{"type": "superseded", "lines": [3],
                              "action": "delete", "reason": "moved again"}]}
        out = bot._parse_audit_findings(data, self.entries, 3)
        assert out[0]["targets"] == ["moved to Austin"]
        assert out[0]["merged_text"] is None

    def test_out_of_range_dropped(self):
        data = {"findings": [{"type": "stale", "lines": [99], "action": "delete"}]}
        assert bot._parse_audit_findings(data, self.entries, 3) == []

    def test_merge_without_text_dropped(self):
        data = {"findings": [{"type": "contradiction", "lines": [1, 2], "action": "merge"}]}
        assert bot._parse_audit_findings(data, self.entries, 3) == []

    def test_single_line_merge_dropped(self):
        data = {"findings": [{"type": "contradiction", "lines": [1],
                              "action": "merge", "merged_text": "x"}]}
        assert bot._parse_audit_findings(data, self.entries, 3) == []

    def test_caps_at_max(self):
        f = {"type": "stale", "lines": [1], "action": "delete"}
        data = {"findings": [dict(f, lines=[i]) for i in range(1, 7)]}
        assert len(bot._parse_audit_findings(data, self.entries, 3)) == 3

    def test_bad_shapes_empty(self):
        assert bot._parse_audit_findings({}, self.entries, 3) == []
        assert bot._parse_audit_findings({"findings": "nope"}, self.entries, 3) == []
        assert bot._parse_audit_findings({"findings": [42]}, self.entries, 3) == []
        assert bot._parse_audit_findings(None, self.entries, 3) == []

    def test_bad_type_or_action_dropped(self):
        data = {"findings": [
            {"type": "vibes", "lines": [1], "action": "delete"},
            {"type": "stale", "lines": [1], "action": "explode"},
        ]}
        assert bot._parse_audit_findings(data, self.entries, 3) == []


class TestAuditReviewItem:
    def test_merge_item_shape(self):
        item = bot._audit_review_item({"type": "contradiction", "action": "merge",
                                       "targets": ["a", "b"], "merged_text": "c",
                                       "reason": "conflict"})
        assert item["kind"] == "audit" and item["action"] == "merge"
        assert item["targets"] == ["a", "b"] and item["merged_text"] == "c"
        assert "AUDIT merge" in item["text"] and "conflict" in item["text"]
        assert item["meta"]["origin"] == "audit"

    def test_delete_item_shape(self):
        item = bot._audit_review_item({"type": "stale", "action": "delete",
                                       "targets": ["a"], "merged_text": None,
                                       "reason": ""})
        assert item["action"] == "delete" and "AUDIT delete" in item["text"]


class TestEnqueueAuditProposals:
    def _p(self, targets):
        return {"type": "stale", "action": "delete", "targets": targets,
                "merged_text": None, "reason": "r"}

    def test_adds_new(self):
        q, added = bot._enqueue_audit_proposals([], [self._p(["a"])], {}, 20)
        assert added == 1 and q[0]["kind"] == "audit"

    def test_rejected_key_skipped(self):
        seen = {bot._audit_pair_key(["a"]): time.time()}
        q, added = bot._enqueue_audit_proposals([], [self._p(["a"])], seen, 20)
        assert added == 0 and q == []

    def test_already_pending_skipped(self):
        q = [bot._audit_review_item(self._p(["a"]))]
        q2, added = bot._enqueue_audit_proposals(q, [self._p(["a"])], {}, 20)
        assert added == 0 and len(q2) == 1

    def test_cap_never_evicts(self):
        q = [{"kind": "memory", "text": f"organic {i}"} for i in range(20)]
        q2, added = bot._enqueue_audit_proposals(q, [self._p(["a"])], {}, 20)
        assert added == 0 and len(q2) == 20 and q2[0]["text"] == "organic 0"


class TestApplyAuditItem:
    def _reset(self, lines, meta=None):
        bot.MEMORIES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        bot._memory_meta.clear()
        bot._memory_meta.update(meta or {})

    def test_delete(self):
        self._reset(["fact one", "fact two"], {"fact one": {"confidence": 8}})
        ok, msg = bot._apply_audit_item(
            {"kind": "audit", "action": "delete", "targets": ["fact one"]})
        assert ok is True
        content = bot.MEMORIES_FILE.read_text(encoding="utf-8")
        assert "fact one" not in content and "fact two" in content
        assert "fact one" not in bot._memory_meta

    def test_merge(self):
        self._reset(["likes tea", "hates tea", "other"],
                    {"likes tea": {"confidence": 8}, "hates tea": {"confidence": 4}})
        ok, msg = bot._apply_audit_item(
            {"kind": "audit", "action": "merge",
             "targets": ["likes tea", "hates tea"],
             "merged_text": "tea feelings evolved over time"})
        assert ok is True
        content = bot.MEMORIES_FILE.read_text(encoding="utf-8")
        assert "tea feelings evolved over time" in content
        assert "likes tea" not in content and "hates tea" not in content
        m = bot._memory_meta.get("tea feelings evolved over time", {})
        assert m.get("origin") == "audit-merge"
        assert m.get("confidence") == 4  # min of the merged entries
        assert "merged:" in m.get("source", "")

    def test_vanished_target_delete(self):
        self._reset(["fact two"])
        ok, msg = bot._apply_audit_item(
            {"kind": "audit", "action": "delete", "targets": ["gone"]})
        assert ok is False
        assert "fact two" in bot.MEMORIES_FILE.read_text(encoding="utf-8")

    def test_vanished_target_merge(self):
        self._reset(["fact two"])
        ok, msg = bot._apply_audit_item(
            {"kind": "audit", "action": "merge", "targets": ["gone", "fact two"],
             "merged_text": "merged"})
        assert ok is False
        assert "fact two" in bot.MEMORIES_FILE.read_text(encoding="utf-8")

    def test_no_targets(self):
        ok, msg = bot._apply_audit_item({"kind": "audit", "action": "delete", "targets": []})
        assert ok is False


# ── Embedding-based memory (v2026-07-12.2) ────────────────────────────────────

class TestSemanticRecallVec:
    def setup_method(self):
        self._orig = dict(bot._embeddings_cache)

    def teardown_method(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache.update(self._orig)

    def test_ranks_by_cosine(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache["a"] = [1.0, 0.0]
        bot._embeddings_cache["b"] = [0.0, 1.0]
        bot._embeddings_cache["c"] = [0.9, 0.1]
        out = bot._semantic_recall_vec([1.0, 0.0], ["a", "b", "c"], top_k=3)
        assert [line for _, line in out] == ["a", "c", "b"]

    def test_top_k(self):
        bot._embeddings_cache.clear()
        for i in range(5):
            bot._embeddings_cache[str(i)] = [1.0, float(i)]
        out = bot._semantic_recall_vec([1.0, 0.0], [str(i) for i in range(5)], top_k=2)
        assert len(out) == 2

    def test_empty_query_vec(self):
        assert bot._semantic_recall_vec([], ["a"], top_k=3) == []

    def test_entries_without_cached_vector_skipped(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache["a"] = [1.0, 0.0]
        out = bot._semantic_recall_vec([1.0, 0.0], ["a", "uncached"], top_k=3)
        assert [line for _, line in out] == ["a"]


class TestIsSemanticDup:
    def test_dup_above_threshold(self):
        assert bot._is_semantic_dup([1.0, 0.0], [[0.99, 0.01]], 0.92) is True

    def test_distinct_below_threshold(self):
        assert bot._is_semantic_dup([1.0, 0.0], [[0.0, 1.0]], 0.92) is False

    def test_empty_existing(self):
        assert bot._is_semantic_dup([1.0, 0.0], [], 0.92) is False

    def test_empty_vec(self):
        assert bot._is_semantic_dup([], [[1.0, 0.0]], 0.92) is False

    def test_threshold_zero_disables(self):
        assert bot._is_semantic_dup([1.0, 0.0], [[1.0, 0.0]], 0.0) is False

    def test_skips_falsy_existing(self):
        assert bot._is_semantic_dup([1.0, 0.0], [None, [], [1.0, 0.0]], 0.92) is True


class TestEvictByValue:
    def test_no_op_under_cap(self):
        lines = ["a", "b"]
        kept, dropped = bot._evict_by_value(lines, {}, 5)
        assert kept == lines and dropped == []

    def test_low_confidence_evicted_first(self):
        lines = ["keep", "drop"]
        meta = {"keep": {"confidence": 9, "ts": 100.0},
                "drop": {"confidence": 2, "ts": 100.0}}
        kept, dropped = bot._evict_by_value(lines, meta, 1)
        assert kept == ["keep"] and dropped == ["drop"]

    def test_tie_broken_by_oldest_ts(self):
        lines = ["old", "new"]
        meta = {"old": {"confidence": 5, "ts": 100.0},
                "new": {"confidence": 5, "ts": 200.0}}
        kept, dropped = bot._evict_by_value(lines, meta, 1)
        assert kept == ["new"] and dropped == ["old"]

    def test_legacy_no_meta_neutral(self):
        # No-meta defaults to confidence 5; a conf-2 line loses to it.
        lines = ["legacy", "lowconf"]
        meta = {"lowconf": {"confidence": 2, "ts": 100.0}}
        kept, dropped = bot._evict_by_value(lines, meta, 1)
        assert kept == ["legacy"] and dropped == ["lowconf"]

    def test_keeps_original_order(self):
        lines = ["a", "b", "c", "d"]
        meta = {"a": {"confidence": 1}, "b": {"confidence": 9},
                "c": {"confidence": 1}, "d": {"confidence": 9}}
        kept, dropped = bot._evict_by_value(lines, meta, 2)
        assert kept == ["b", "d"] and set(dropped) == {"a", "c"}


class TestLoreSemanticHits:
    def setup_method(self):
        self._orig_lore = bot.LORE
        self._orig_emb = dict(bot._lore_embeddings)

    def teardown_method(self):
        bot.LORE = self._orig_lore
        bot._lore_embeddings.clear()
        bot._lore_embeddings.update(self._orig_emb)

    def test_ranks_and_respects_topk_and_floor(self):
        bot.LORE = [
            {"keys": [], "content": "near", "constant": False},
            {"keys": [], "content": "far", "constant": False},
            {"keys": [], "content": "orthogonal", "constant": False},
        ]
        bot._lore_embeddings.clear()
        bot._lore_embeddings["near"] = [1.0, 0.0]
        bot._lore_embeddings["far"] = [0.8, 0.6]
        bot._lore_embeddings["orthogonal"] = [0.0, 1.0]  # cosine 0 < 0.3 floor
        hits = bot._lore_semantic_hits([1.0, 0.0], top_k=3)
        assert hits == ["near", "far"]  # orthogonal filtered by 0.3 floor

    def test_constant_entries_ignored(self):
        bot.LORE = [{"keys": [], "content": "always", "constant": True}]
        bot._lore_embeddings.clear()
        bot._lore_embeddings["always"] = [1.0, 0.0]
        assert bot._lore_semantic_hits([1.0, 0.0], top_k=3) == []

    def test_empty_vec_or_zero_topk(self):
        assert bot._lore_semantic_hits([], top_k=3) == []
        assert bot._lore_semantic_hits([1.0, 0.0], top_k=0) == []


class TestProvenanceHedge:
    def test_hedged_line_gets_source_suffix(self):
        meta = {"saw a fox": {"confidence": 4, "source": "there was a fox"}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert hedged is True
        assert out[0].startswith("(unsure) saw a fox")
        assert 'you recall this from: "there was a fox"' in out[0]

    def test_hedged_without_source_plain(self):
        meta = {"saw a fox": {"confidence": 4}}
        out, _ = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert out == ["(unsure) saw a fox"]

    def test_high_confidence_no_source_shown(self):
        meta = {"saw a fox": {"confidence": 9, "source": "secret"}}
        out, hedged = bot._hedge_memory_lines(["saw a fox"], meta, 7, True)
        assert out == ["saw a fox"] and hedged is False


class TestQueryEmbedCache:
    def setup_method(self):
        self._orig_embed = bot._embed_text
        bot._QUERY_EMBED_CACHE.clear()

    def teardown_method(self):
        bot._embed_text = self._orig_embed
        bot._QUERY_EMBED_CACHE.clear()

    def test_cache_hit_avoids_reembed(self):
        calls = {"n": 0}
        def fake(text):
            calls["n"] += 1
            return [1.0, 0.0]
        bot._embed_text = fake
        v1 = asyncio.run(bot._embed_query_cached("Hello There"))
        v2 = asyncio.run(bot._embed_query_cached("hello there"))  # normalized -> same key
        assert v1 == v2 == [1.0, 0.0]
        assert calls["n"] == 1

    def test_none_on_failed_embed(self):
        bot._embed_text = lambda text: None
        assert asyncio.run(bot._embed_query_cached("anything")) is None

    def test_empty_text_returns_none_without_call(self):
        calls = {"n": 0}
        def fake(text):
            calls["n"] += 1
            return [1.0]
        bot._embed_text = fake
        assert asyncio.run(bot._embed_query_cached("   ")) is None
        assert calls["n"] == 0

    def test_lru_eviction(self):
        bot._embed_text = lambda text: [1.0, 0.0]
        for i in range(bot._QUERY_EMBED_CACHE_MAX + 10):
            asyncio.run(bot._embed_query_cached(f"msg {i}"))
        assert len(bot._QUERY_EMBED_CACHE) <= bot._QUERY_EMBED_CACHE_MAX


class TestTriggeredMemoriesLivePath:
    """Proves semantic recall now fires on the reply path when a query vector is
    passed — the whole point of v2026-07-12.2."""
    def setup_method(self):
        self._orig_cache = dict(bot._embeddings_cache)
        self._orig_meta = dict(bot._memory_meta)
        bot.MEMORIES_FILE.write_text("the vessel departed at dawn\nunrelated grocery list\n",
                                     encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        bot._embeddings_cache.clear()
        # "ship" query vector is close to the "vessel" line, far from groceries,
        # and shares NO keywords with it.
        bot._embeddings_cache["the vessel departed at dawn"] = [1.0, 0.0]
        bot._embeddings_cache["unrelated grocery list"] = [0.0, 1.0]

    def teardown_method(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache.update(self._orig_cache)
        bot._memory_meta.clear()
        bot._memory_meta.update(self._orig_meta)

    def test_semantic_hit_with_no_keyword_overlap(self):
        out = bot.triggered_memories("tell me about the ship", query_vec=[1.0, 0.0])
        assert "the vessel departed at dawn" in out

    def test_without_query_vec_on_loop_is_keyword_only(self):
        async def run():
            return bot.triggered_memories("tell me about the ship")
        out = asyncio.run(run())
        assert "the vessel departed at dawn" not in out


from datetime import date as _date


class TestParseRecurrence:
    def test_weekly_valid(self):
        assert bot._parse_recurrence("weekly:thu") == "weekly:thu"

    def test_weekly_full_day_name_normalized(self):
        assert bot._parse_recurrence("weekly:thursday") == "weekly:thu"
        assert bot._parse_recurrence("Weekly:MONDAY") == "weekly:mon"

    def test_weekly_garbage_day_rejected(self):
        assert bot._parse_recurrence("weekly:xyz") == ""

    def test_monthly_valid_and_bounds(self):
        assert bot._parse_recurrence("monthly:15") == "monthly:15"
        assert bot._parse_recurrence("monthly:01") == "monthly:1"
        assert bot._parse_recurrence("monthly:31") == "monthly:31"
        assert bot._parse_recurrence("monthly:0") == ""
        assert bot._parse_recurrence("monthly:32") == ""

    def test_yearly_valid_and_zero_padded(self):
        assert bot._parse_recurrence("yearly:07-22") == "yearly:07-22"
        assert bot._parse_recurrence("yearly:7-2") == "yearly:07-02"
        assert bot._parse_recurrence("yearly:13-01") == ""
        assert bot._parse_recurrence("yearly:00-10") == ""

    def test_non_string_and_junk(self):
        assert bot._parse_recurrence(None) == ""
        assert bot._parse_recurrence(7) == ""
        assert bot._parse_recurrence("") == ""
        assert bot._parse_recurrence("daily") == ""
        assert bot._parse_recurrence("every thursday") == ""


class TestNextRecurrence:
    def test_weekly_same_day_is_strictly_after(self):
        # 2026-07-16 is a Thursday — next thu must be a week out, not today.
        assert bot._next_recurrence("weekly:thu", _date(2026, 7, 16)) == _date(2026, 7, 23)

    def test_weekly_other_day(self):
        # From a Sunday (2026-07-12), next thu is the 16th.
        assert bot._next_recurrence("weekly:thu", _date(2026, 7, 12)) == _date(2026, 7, 16)

    def test_monthly_later_this_month(self):
        assert bot._next_recurrence("monthly:20", _date(2026, 7, 12)) == _date(2026, 7, 20)

    def test_monthly_rolls_to_next_month(self):
        assert bot._next_recurrence("monthly:5", _date(2026, 7, 12)) == _date(2026, 8, 5)

    def test_monthly_day_31_clamps_to_short_month(self):
        assert bot._next_recurrence("monthly:31", _date(2026, 4, 15)) == _date(2026, 4, 30)

    def test_monthly_december_rolls_to_january(self):
        assert bot._next_recurrence("monthly:5", _date(2026, 12, 20)) == _date(2027, 1, 5)

    def test_yearly_later_this_year(self):
        assert bot._next_recurrence("yearly:09-01", _date(2026, 7, 12)) == _date(2026, 9, 1)

    def test_yearly_rolls_to_next_year(self):
        assert bot._next_recurrence("yearly:03-14", _date(2026, 7, 12)) == _date(2027, 3, 14)

    def test_yearly_same_day_is_strictly_after(self):
        assert bot._next_recurrence("yearly:07-12", _date(2026, 7, 12)) == _date(2027, 7, 12)

    def test_yearly_feb_29_clamps_on_non_leap_year(self):
        assert bot._next_recurrence("yearly:02-29", _date(2026, 3, 1)) == _date(2027, 2, 28)

    def test_invalid_rule_returns_none(self):
        assert bot._next_recurrence("", _date(2026, 7, 12)) is None
        assert bot._next_recurrence("weekly:xyz", _date(2026, 7, 12)) is None
        assert bot._next_recurrence("daily", _date(2026, 7, 12)) is None


class TestRecurNoteRegex:
    def test_recurring_line_parses_with_clean_note(self):
        m = bot._RECUR_NOTE_RE.match("has derby practice (every weekly:thu) (due 2026-07-16)")
        assert m
        assert m.group("note") == "has derby practice"
        assert m.group("rule") == "weekly:thu"
        assert m.group("date") == "2026-07-16"

    def test_plain_due_line_still_matches_due_re(self):
        m = bot._DUE_NOTE_RE.match("has a job interview (due 2026-07-14)")
        assert m
        assert m.group("note") == "has a job interview"

    def test_recur_re_does_not_match_plain_due_line(self):
        assert bot._RECUR_NOTE_RE.match("has a job interview (due 2026-07-14)") is None

    def test_due_re_greedily_matches_recurring_line_hence_recur_first(self):
        # Documents WHY note_followup_job must try _RECUR_NOTE_RE first: the plain
        # regex matches too, but swallows the (every …) marker into the note text.
        m = bot._DUE_NOTE_RE.match("has derby practice (every weekly:thu) (due 2026-07-16)")
        assert m
        assert "(every" in m.group("note")


class TestAppendUserNoteRecurring:
    def setup_method(self):
        self._orig = (bot.USER_NOTES_FILE.read_text(encoding="utf-8")
                      if bot.USER_NOTES_FILE.exists() else None)
        if bot.USER_NOTES_FILE.exists():
            bot.USER_NOTES_FILE.unlink()
        bot._user_notes_cache["text"] = None

    def teardown_method(self):
        if self._orig is None:
            if bot.USER_NOTES_FILE.exists():
                bot.USER_NOTES_FILE.unlink()
        else:
            bot.USER_NOTES_FILE.write_text(self._orig, encoding="utf-8")
        bot._user_notes_cache["text"] = None

    def test_recurring_note_gets_both_markers_in_followup_parseable_order(self):
        bot._append_user_note("has derby practice", due="2026-07-16", every="weekly:thu")
        line = bot.USER_NOTES_FILE.read_text(encoding="utf-8").strip()
        assert line == "has derby practice (every weekly:thu) (due 2026-07-16)"
        assert bot._RECUR_NOTE_RE.match(line)

    def test_one_off_note_unchanged(self):
        bot._append_user_note("has a job interview", due="2026-07-14")
        line = bot.USER_NOTES_FILE.read_text(encoding="utf-8").strip()
        assert line == "has a job interview (due 2026-07-14)"

    def test_every_without_due_stores_bare_note(self):
        # The caller guards against this, but the writer itself must not emit an
        # (every …) marker that can never fire.
        bot._append_user_note("plays board games", due="", every="weekly:fri")
        line = bot.USER_NOTES_FILE.read_text(encoding="utf-8").strip()
        assert line == "plays board games"
