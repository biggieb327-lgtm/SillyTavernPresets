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

class TestTrimPromptToBudget:
    def test_noop_when_under_budget(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ]
        result = bot._trim_prompt_to_budget(list(msgs), 10000)
        assert len(result) == 4

    def test_disabled_when_zero(self):
        msgs = [{"role": "user", "content": "x" * 100000}]
        result = bot._trim_prompt_to_budget(list(msgs), 0)
        assert len(result) == 1

    def test_drops_oldest_history_first(self):
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old message"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "new message"},
        ]
        result = bot._trim_prompt_to_budget(list(msgs), 20)
        roles = [m["role"] for m in result]
        assert "system" in roles
        assert result[-1]["content"] == "new message"

    def test_never_drops_system(self):
        msgs = [
            {"role": "system", "content": "x" * 400},
            {"role": "user", "content": "hi"},
        ]
        result = bot._trim_prompt_to_budget(list(msgs), 50)
        assert any(m["role"] == "system" for m in result)

    def test_never_drops_final_user(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "a" * 400},
            {"role": "user", "content": "final question"},
        ]
        result = bot._trim_prompt_to_budget(list(msgs), 30)
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


class TestMapIntent:
    def test_route_positives(self):
        cases = {
            "how do I get to the airport": "the airport",
            "directions to pike place market": "pike place market",
            "give me directions to the ferry terminal": "the ferry terminal",
            "how far is bellevue square from here?": "bellevue square",  # filler stripped
            "how far is it to snoqualmie falls": "snoqualmie falls",
            "how long does it take to get to sea-tac": "sea-tac",
            "how long to bike to green lake": "green lake",
            "what's the commute like to redmond": "redmond",
        }
        for text, dest in cases.items():
            assert bot._map_intent(text) == ("route", dest), text

    def test_nearby_positives(self):
        cases = {
            "is there a pharmacy nearby": "pharmacy",
            "any coffee shops around here": "coffee shops",
            "closest gas station?": "gas station",
            "nearest atm to me": "atm",
        }
        for text, cat in cases.items():
            assert bot._map_intent(text) == ("nearby", cat), text

    def test_figurative_negatives(self):
        for t in ["how do I get to sleep", "how do I get to know you better",
                  "you're so far away", "how far along are you", "how far is too far",
                  "how long have you been up", "how long until you reply",
                  "how long to get over him", "get to the point",
                  "is there anything nearby", "is there any hope for us",
                  "you're the closest thing to heaven", "stay close to me",
                  "are you around?", "how's your day"]:
            assert bot._map_intent(t) is None, t

    def test_none_and_empty_safe(self):
        assert bot._map_intent(None) is None
        assert bot._map_intent("") is None

    def test_clean_dest_bounds(self):
        assert bot._clean_map_dest("x") == ""            # too short
        assert bot._clean_map_dest("a" * 61) == ""       # too long
        assert bot._clean_map_dest(" Knoxville? ") == "Knoxville"  # \b-anchored reject


class TestRouteBrief:
    _route = {"routes": [{"summary": {
        "travelTimeInSeconds": 1080, "lengthInMeters": 12713, "trafficDelayInSeconds": 240}}]}

    def test_summary_with_traffic(self):
        out = bot._route_brief(self._route, "car", "Bellevue Square")
        assert out.startswith("drive to Bellevue Square: 18 min, 7.9 mi")
        assert "+4 min traffic" in out and "🚗" not in out

    def test_small_delay_excluded(self):
        r = {"routes": [{"summary": {"travelTimeInSeconds": 600, "lengthInMeters": 3000,
                                     "trafficDelayInSeconds": 45}}]}
        assert "traffic" not in bot._route_brief(r, "car", "X")

    def test_bicycle_verb(self):
        assert bot._route_brief(self._route, "bicycle", "X").startswith("bike to X")

    def test_pedestrian_verb(self):
        assert bot._route_brief(self._route, "pedestrian", "X").startswith("walk to X")

    def test_empty_and_malformed(self):
        assert bot._route_brief({}, "car", "X") == ""
        assert bot._route_brief(None, "car", "X") == ""
        assert bot._route_brief({"routes": [{"summary": {}}]}, "car", "X") == ""


class TestPlacesBrief:
    def test_non_restaurant_category(self):
        out = bot._places_brief([
            {"poi": {"name": "Bartell Drugs", "categories": ["pharmacy"]}, "dist": 400}])
        assert "Bartell Drugs" in out and "(pharmacy, " in out and "📍" not in out

    def test_sorted_by_distance(self):
        out = bot._places_brief([
            {"poi": {"name": "Far", "categories": ["atm"]}, "dist": 900},
            {"poi": {"name": "Near", "categories": ["atm"]}, "dist": 100},
        ])
        assert out.index("Near") < out.index("Far")

    def test_skips_nameless_and_empty(self):
        assert bot._places_brief([{"poi": {}}]) == ""
        assert bot._places_brief([]) == ""


class TestFreshLocation:
    def test_fresh_passes(self):
        assert bot._fresh_location({"lat": 1, "lon": 2, "ts": 1000.0, "live_until": None}, now=1100.0)

    def test_stale_fails(self):
        assert not bot._fresh_location({"ts": 0.0, "live_until": None}, now=5 * 3600.0)

    def test_live_share_overrides_stale_ts(self):
        assert bot._fresh_location({"ts": 0.0, "live_until": 6 * 3600.0}, now=5 * 3600.0)

    def test_none_and_missing_keys_safe(self):
        assert not bot._fresh_location(None)
        assert not bot._fresh_location({})
        assert not bot._fresh_location({"lat": 1, "lon": 2})


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

    def test_graceful_stop_excluded(self):
        # CHANGED v2026-07-26.7. This used to assert the opposite, on the phone-era
        # rationale that a bare graceful stop meant an OEM battery-manager SIGTERM.
        # The fleet has been 100% systemd since 2026-07-26: a graceful SIGTERM now
        # means `systemctl restart` or a vps-sync deploy, neither of which logs a
        # '[restart] requested' marker, so every deploy was tripping the storm alert.
        lines = [
            "2026-07-11 17:10:00 [WARNING] companion: [shutdown] graceful stop — saving state.",
            self._audit("17:10:07"),
        ]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 0

    def test_sigkill_still_counts(self):
        # The guard that matters: a kill leaves NO graceful-stop line, so an OOM kill
        # or phantom-killer SIGKILL is still reported. This is what the alert is for.
        lines = [self._audit("17:10:00"), self._audit("17:25:00"), self._audit("17:45:00")]
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 3

    def test_deploy_loop_does_not_alarm(self):
        # Regression for the false alarm itself: six back-to-back vps-sync deploys.
        lines = []
        for i, t in enumerate(("17:05", "17:12", "17:19", "17:26", "17:33", "17:40")):
            lines.append(f"2026-07-11 {t}:00 [WARNING] companion: "
                         "[shutdown] graceful stop — saving state.")
            lines.append(self._audit(f"{t}:07"))
        assert bot._tally_unexpected_restarts(lines, self.CUT) == 0


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


class TestRepeatPenalty:
    def test_disabled_window_is_neutral(self):
        # window <= 0 = kill switch: no penalty regardless of history.
        assert bot._repeat_penalty(5, 6, 0, 0.15) == 1.0
        assert bot._repeat_penalty(5, 6, -1, 0.15) == 1.0

    def test_never_injected_is_neutral(self):
        assert bot._repeat_penalty(None, 6, 6, 0.15) == 1.0

    def test_full_penalty_turn_after_injection(self):
        # ago == 1 (injected last turn) → exactly the floor.
        assert bot._repeat_penalty(5, 6, 6, 0.15) == 0.15

    def test_fades_back_to_neutral_after_window(self):
        assert bot._repeat_penalty(1, 7, 6, 0.15) == 1.0     # ago == window
        assert bot._repeat_penalty(1, 20, 6, 0.15) == 1.0    # ago > window

    def test_monotonic_increasing_within_window(self):
        # Penalty relaxes each turn away from the injection until it's neutral.
        vals = [bot._repeat_penalty(0, ago, 6, 0.15) for ago in (1, 2, 3, 4, 5)]
        assert vals == sorted(vals)
        assert all(0.15 <= v < 1.0 for v in vals)


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


class TestTriggeredMemoriesRepeatSuppression:
    """MEMORY_REPEAT_SUPPRESS_TURNS: the same top memory must not win the budget every
    turn. Two equal-length lines, both semantically close to the query, but the budget
    fits only one — so which one surfaces reveals whether suppression rotated it."""
    LINE_A = "alpha memory line"
    LINE_B = "bravo memory line"

    def setup_method(self):
        self._orig_cache = dict(bot._embeddings_cache)
        self._orig_meta = dict(bot._memory_meta)
        self._orig_budget = bot.MEMORY_TOKEN_BUDGET
        self._orig_suppress = bot.MEMORY_REPEAT_SUPPRESS_TURNS
        bot.MEMORIES_FILE.write_text(self.LINE_A + "\n" + self.LINE_B + "\n",
                                     encoding="utf-8")
        bot._memories_cache["text"] = None
        bot._memories_cache["ts"] = 0.0
        bot._embeddings_cache.clear()
        bot._embeddings_cache[self.LINE_A] = [1.0, 0.0]   # cosine 1.0 vs the query
        bot._embeddings_cache[self.LINE_B] = [0.8, 0.6]   # cosine 0.8 vs the query
        bot._mem_inject_turn.clear()
        bot._mem_last_injected.clear()
        # Budget fits exactly one line (equal length → equal cost), so ranking decides.
        bot.MEMORY_TOKEN_BUDGET = bot._est_tokens(self.LINE_A)
        bot.MEMORY_REPEAT_SUPPRESS_TURNS = 6

    def teardown_method(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache.update(self._orig_cache)
        bot._memory_meta.clear()
        bot._memory_meta.update(self._orig_meta)
        bot.MEMORY_TOKEN_BUDGET = self._orig_budget
        bot.MEMORY_REPEAT_SUPPRESS_TURNS = self._orig_suppress
        bot._mem_inject_turn.clear()
        bot._mem_last_injected.clear()

    def _call(self, chat_id):
        return bot.triggered_memories("tell me something", query_vec=[1.0, 0.0],
                                      chat_id=chat_id)

    def test_top_memory_rotates_on_consecutive_turns(self):
        first = self._call(1)
        second = self._call(1)
        assert first == [self.LINE_A]      # highest score wins turn 1
        assert second == [self.LINE_B]     # A suppressed → B wins turn 2

    def test_suppression_fades_after_window(self):
        # A injected on turn 1; jump the counter so the next call is a full window later.
        self._call(1)
        bot._mem_inject_turn[1] = bot.MEMORY_REPEAT_SUPPRESS_TURNS
        assert self._call(1) == [self.LINE_A]   # penalty relaxed → A wins again

    def test_kill_switch_restores_old_behavior(self):
        bot.MEMORY_REPEAT_SUPPRESS_TURNS = 0
        assert self._call(1) == [self.LINE_A]
        assert self._call(1) == [self.LINE_A]   # identical, no rotation
        assert bot._mem_last_injected == {}     # nothing recorded

    def test_no_chat_id_records_nothing(self):
        assert self._call(None) == [self.LINE_A]
        assert self._call(None) == [self.LINE_A]
        assert bot._mem_last_injected == {}

    def test_per_chat_isolation(self):
        self._call(1)                       # records A for chat 1
        assert self._call(2) == [self.LINE_A]   # chat 2 has no history → A still wins


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


class TestSanitizeNote:
    def test_strips_json_debris(self):
        # Verbatim from the owner's live file, 2026-07-12.
        assert (bot._sanitize_note("mentions his upcoming DOR audit tour with long, "
                                   "hour-long stops (valence null)")
                == "mentions his upcoming DOR audit tour with long, hour-long stops")

    def test_strips_mid_text_noted_marker(self):
        assert (bot._sanitize_note("has a 'walk thing' scheduled for Wednesdays (noted today)")
                == "has a 'walk thing' scheduled for Wednesdays")

    def test_strips_model_emitted_due_marker(self):
        # A model-written (due …) must never reach the follow-up parser unvalidated.
        assert bot._sanitize_note("has a dentist visit (due 2026-99-99)") == "has a dentist visit"

    def test_keeps_ordinary_parentheticals(self):
        assert (bot._sanitize_note("has a shift at the DSHS office (Capitol Hill)")
                == "has a shift at the DSHS office (Capitol Hill)")

    def test_non_string_and_empty(self):
        assert bot._sanitize_note(None) == ""
        assert bot._sanitize_note("") == ""
        assert bot._sanitize_note("(valence null)") == ""


class TestNoteIsDup:
    def test_yuen_call_variants_are_dups(self):
        # Both were stored on-device 2026-07-08/09: the 20-char prefix check
        # can't see past the differing sentence opening.
        existing = ["has a call with Yuen in eight minutes (asked 2026-07-08)"]
        assert bot._note_is_dup("has a 2pm call with Yuen", existing, 0.8)

    def test_distinct_events_are_not_dups(self):
        existing = ["has a job interview on Tuesday (due 2026-07-14)"]
        assert not bot._note_is_dup("has a dentist appointment Friday", existing, 0.8)

    def test_prefix_match_still_works_with_sim_disabled(self):
        existing = ["has a job interview on Tuesday"]
        assert bot._note_is_dup("has a job interview on Tuesday afternoon", existing, 0)

    def test_sim_zero_disables_word_overlap(self):
        existing = ["has a call with Yuen in eight minutes"]
        assert not bot._note_is_dup("has a 2pm call with Yuen", existing, 0)

    def test_markers_ignored_when_comparing(self):
        existing = ["goes to derby practice (every weekly:thu) (due 2026-07-16)"]
        assert bot._note_is_dup("goes to derby practice on Thursdays", existing, 0.8)


class TestExpireAskedNotes:
    TODAY = _date(2026, 7, 12)

    def test_old_asked_note_dropped(self):
        lines = ["has a job interview on Tuesday (asked 2026-07-01)"]
        assert bot._expire_asked_notes(lines, self.TODAY, 7) == []

    def test_recent_asked_note_kept(self):
        lines = ["went whale watching (asked 2026-07-11)"]
        assert bot._expire_asked_notes(lines, self.TODAY, 7) == lines

    def test_boundary_is_strictly_older_than_ttl(self):
        lines = ["something (asked 2026-07-05)"]  # exactly 7 days ago
        assert bot._expire_asked_notes(lines, self.TODAY, 7) == lines

    def test_ttl_zero_keeps_everything(self):
        lines = ["ancient (asked 2020-01-01)"]
        assert bot._expire_asked_notes(lines, self.TODAY, 0) == lines

    def test_due_and_every_lines_untouched(self):
        lines = [
            "has practice (every weekly:thu) (due 2026-07-16)",
            "interview (due 2026-07-14)",
            "plain undated note",
        ]
        assert bot._expire_asked_notes(lines, self.TODAY, 7) == lines

    def test_malformed_date_kept(self):
        lines = ["weird (asked 2026-13-99)"]
        assert bot._expire_asked_notes(lines, self.TODAY, 7) == lines


from types import SimpleNamespace
import pytest
from telegram.ext import ApplicationHandlerStop


class TestSetOwnerClaimOnce:
    def setup_method(self):
        self._env = bot.OWNER_CHAT_ID_ENV
        self._orig = bot.OWNER_FILE.read_text() if bot.OWNER_FILE.exists() else None
        bot.OWNER_CHAT_ID_ENV = None
        if bot.OWNER_FILE.exists():
            bot.OWNER_FILE.unlink()

    def teardown_method(self):
        bot.OWNER_CHAT_ID_ENV = self._env
        if self._orig is None:
            if bot.OWNER_FILE.exists():
                bot.OWNER_FILE.unlink()
        else:
            bot.OWNER_FILE.write_text(self._orig)

    def test_first_contact_claims(self):
        bot.set_owner(111)
        assert bot.get_owner() == 111

    def test_second_chat_cannot_steal_ownership(self):
        bot.set_owner(111)
        bot.set_owner(222)  # the pre-fix /start takeover path
        assert bot.get_owner() == 111

    def test_group_id_refused(self):
        bot.set_owner(-100123)
        assert bot.get_owner() is None

    def test_env_owner_is_authoritative_and_file_untouched(self):
        bot.OWNER_CHAT_ID_ENV = "999"
        bot.set_owner(123)
        assert not bot.OWNER_FILE.exists()
        assert bot.get_owner() == 999

    def test_restart_preserves_claimed_owner(self):
        bot.set_owner(111)
        # get_owner reads the file fresh each call — same as a process restart.
        assert bot.get_owner() == 111
        bot.set_owner(333)
        assert bot.get_owner() == 111


def _gate_update(chat_id, user_id):
    chat = SimpleNamespace(id=chat_id)
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(effective_chat=chat, effective_user=user)


class TestPrivateGate:
    def setup_method(self):
        self._users = set(bot.ALLOWED_USERS)
        self._env = bot.OWNER_CHAT_ID_ENV
        self._orig = bot.OWNER_FILE.read_text() if bot.OWNER_FILE.exists() else None
        bot.OWNER_CHAT_ID_ENV = None
        if bot.OWNER_FILE.exists():
            bot.OWNER_FILE.unlink()
        bot.ALLOWED_USERS.clear()

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._users)
        bot.OWNER_CHAT_ID_ENV = self._env
        if self._orig is None:
            if bot.OWNER_FILE.exists():
                bot.OWNER_FILE.unlink()
        else:
            bot.OWNER_FILE.write_text(self._orig)

    def _run(self, update):
        return asyncio.run(bot._private_gate(update, None))

    def test_empty_allowlist_is_open(self):
        self._run(_gate_update(10, 6))  # no raise

    def test_stranger_stopped_in_private(self):
        bot.ALLOWED_USERS.add(5)
        with pytest.raises(ApplicationHandlerStop):
            self._run(_gate_update(10, 6))

    def test_allowed_user_passes(self):
        bot.ALLOWED_USERS.add(5)
        self._run(_gate_update(10, 5))

    def test_owner_passes_even_if_not_in_allowlist(self):
        bot.ALLOWED_USERS.add(5)
        bot.OWNER_FILE.write_text("7")
        self._run(_gate_update(7, 7))

    def test_group_chats_are_not_this_gates_jurisdiction(self):
        bot.ALLOWED_USERS.add(5)
        self._run(_gate_update(-100123, 6))  # group_guard owns this boundary

    def test_userless_update_passes(self):
        bot.ALLOWED_USERS.add(5)
        self._run(_gate_update(10, None))


class TestOnErrorHygiene:
    class _Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text):
            self.sent.append((chat_id, text))

    def _ctx(self, fake_bot):
        return SimpleNamespace(error=ValueError("secret internal detail"), bot=fake_bot)

    def test_private_chat_gets_generic_text_only(self):
        fake = self._Bot()
        upd = SimpleNamespace(callback_query=None,
                              effective_chat=SimpleNamespace(id=10))
        asyncio.run(bot.on_error(upd, self._ctx(fake)))
        assert len(fake.sent) == 1
        _, text = fake.sent[0]
        assert "secret internal detail" not in text
        assert "ValueError" not in text
        assert "/errors" in text

    def test_group_chat_gets_nothing(self):
        fake = self._Bot()
        upd = SimpleNamespace(callback_query=None,
                              effective_chat=SimpleNamespace(id=-100123))
        asyncio.run(bot.on_error(upd, self._ctx(fake)))
        assert fake.sent == []

    def test_no_update_is_safe(self):
        fake = self._Bot()
        asyncio.run(bot.on_error(None, self._ctx(fake)))
        assert fake.sent == []


import os


class TestRunConfigCheck:
    def test_fixture_instance_passes(self):
        assert bot._run_config_check() is True

    def test_malformed_token_fails(self):
        orig = os.environ.get("TELEGRAM_BOT_TOKEN")
        os.environ["TELEGRAM_BOT_TOKEN"] = "not-a-token"
        try:
            assert bot._run_config_check() is False
        finally:
            if orig is not None:
                os.environ["TELEGRAM_BOT_TOKEN"] = orig

    def test_corrupt_state_file_fails(self):
        f = bot.BASE_DIR / "cron_jobs.json"
        orig = f.read_text(encoding="utf-8") if f.exists() else None
        f.write_text("{corrupt", encoding="utf-8")
        try:
            assert bot._run_config_check() is False
        finally:
            if orig is None:
                f.unlink()
            else:
                f.write_text(orig, encoding="utf-8")


# ── _parse_busy_blocks / _busy_now (ROADMAP 3.6) ─────────────────────────────
# Only explicit HH:MM-HH:MM ranges may fire the busy state; loose wording never does.

class TestBusyBlocks:
    def test_explicit_range_parsed(self):
        blocks = bot._parse_busy_blocks("9:00-17:30 shift at the depot")
        assert blocks == [(540, 1050, "shift at the depot")]

    def test_loose_lines_never_fire(self):
        sched = "Monday:\nmorning shift\ngym later\nlunch around noon"
        assert bot._parse_busy_blocks(sched) == []

    def test_en_dash_and_embedded_range(self):
        blocks = bot._parse_busy_blocks("- tutoring 14:00–15:00 (Maya)")
        assert len(blocks) == 1
        start, end, activity = blocks[0]
        assert (start, end) == (14 * 60, 15 * 60)
        assert "tutoring" in activity and "Maya" in activity

    def test_overnight_and_invalid_ranges_skipped(self):
        assert bot._parse_busy_blocks("23:00-07:00 sleep") == []
        assert bot._parse_busy_blocks("25:00-26:00 nonsense") == []
        assert bot._parse_busy_blocks("10:75-11:80 typo") == []

    def test_activity_falls_back_when_line_is_only_times(self):
        blocks = bot._parse_busy_blocks("10:00-11:00")
        assert blocks[0][2] == "something on her schedule"

    def test_busy_now_inside_and_outside(self):
        from datetime import datetime
        sched = "9:00-17:00 shift"
        inside = datetime(2026, 7, 18, 12, 0)
        outside = datetime(2026, 7, 18, 18, 0)
        assert bot._busy_now(sched, now=inside) == "shift"
        assert bot._busy_now(sched, now=outside) == ""

    def test_busy_now_boundaries(self):
        from datetime import datetime
        sched = "9:00-17:00 shift"
        assert bot._busy_now(sched, now=datetime(2026, 7, 18, 9, 0)) == "shift"
        assert bot._busy_now(sched, now=datetime(2026, 7, 18, 17, 0)) == ""

    def test_empty_schedule(self):
        assert bot._busy_now("", now=None) == ""
        assert bot._parse_busy_blocks("") == []


# ── _fatigue_update / _fatigue_effective (ROADMAP 3.7) ───────────────────────
# Arithmetic-only social battery: intensity drains regardless of sign, calm-positive
# recharges, idle time decays. Clamped to [0, 100].

class TestFatigue:
    def test_intense_exchange_drains_both_signs(self):
        assert bot._fatigue_update(50.0, 2.5, 0) == 62.0
        assert bot._fatigue_update(50.0, -2.0, 0) == 62.0

    def test_calm_positive_recharges(self):
        assert bot._fatigue_update(50.0, 1.0, 0) == 35.0
        assert bot._fatigue_update(50.0, 1.9, 0) == 35.0

    def test_neutral_drifts_down(self):
        assert bot._fatigue_update(50.0, 0.0, 0) == 45.0
        assert bot._fatigue_update(50.0, -1.5, 0) == 45.0

    def test_clamped_to_bounds(self):
        assert bot._fatigue_update(98.0, 3.0, 0) == 100.0
        assert bot._fatigue_update(2.0, 1.0, 0) == 0.0

    def test_gap_decay_applies_before_exchange(self):
        # 3h gap at 10/h wipes 30 before the +12 intense hit lands.
        assert bot._fatigue_update(80.0, 3.0, 3.0, decay_per_hour=10.0) == 62.0

    def test_negative_gap_ignored(self):
        assert bot._fatigue_update(50.0, 0.0, -5.0) == 45.0

    def test_effective_decays_at_read_time(self):
        now = 1_000_000.0
        two_hours_ago = now - 7200
        assert bot._fatigue_effective(80.0, two_hours_ago, now, 10.0) == 60.0

    def test_effective_never_negative_and_zero_ts_safe(self):
        assert bot._fatigue_effective(30.0, 0.0, 1_000_000.0, 10.0) == 0.0


# ── _split_opening_mood (ROADMAP 3.7 day-mood residue) ───────────────────────
# The MOOD meta line must be peeled off before day.txt is written; a model that
# ignores the instruction degrades gracefully to no residue.

class TestSplitOpeningMood:
    def test_mood_line_parsed_and_stripped(self):
        text = "Flat tire on the route this morning.\nMOOD: annoyed but rolling with it | -1"
        events, opening = bot._split_opening_mood(text)
        assert events == "Flat tire on the route this morning."
        assert opening == ("annoyed but rolling with it", -1)

    def test_no_mood_line_returns_none(self):
        events, opening = bot._split_opening_mood("Just a normal day.")
        assert events == "Just a normal day."
        assert opening is None

    def test_valence_clamped(self):
        _, opening = bot._split_opening_mood("day stuff\nMOOD: euphoric | 9")
        assert opening == ("euphoric", 3)

    def test_last_mood_line_wins_and_mid_text_mood_not_matched(self):
        text = "She texted 'MOOD: weird flex' to Maya.\nGood day overall.\nMOOD: content | 2"
        events, opening = bot._split_opening_mood(text)
        assert opening == ("content", 2)
        assert "Maya" in events and "Good day" in events

    def test_empty_and_none_safe(self):
        assert bot._split_opening_mood("") == ("", None)
        assert bot._split_opening_mood(None) == ("", None)

    def test_empty_label_discarded(self):
        events, opening = bot._split_opening_mood("day.\nMOOD:  | 2")
        assert opening is None
        assert events == "day."


# ── _usage_summary (v2026-07-18.4) ───────────────────────────────────────────
# The subscription-usage endpoint returned active=true without 'daily' and /usage
# crashed with a KeyError. Never index an external API response directly.

class TestUsageSummary:
    def test_full_shape_formats(self):
        data = {"active": True,
                "daily": {"used": 10, "remaining": 90},
                "monthly": {"used": 100, "remaining": 900},
                "limits": {"daily": 100, "monthly": 1000}}
        msg = bot._usage_summary(data)
        assert "10 / 100" in msg and "100 / 1000" in msg

    def test_missing_daily_returns_none(self):
        assert bot._usage_summary({"active": True, "monthly": {}, "limits": {}}) is None

    def test_wrong_types_return_none(self):
        assert bot._usage_summary({"daily": "5", "monthly": {}, "limits": {}}) is None

    def test_missing_inner_keys_degrade_to_question_marks(self):
        data = {"daily": {}, "monthly": {}, "limits": {}}
        msg = bot._usage_summary(data)
        assert msg is not None and "?" in msg

    def test_empty_dict_returns_none(self):
        assert bot._usage_summary({}) is None


# ── _usage_summary new token-based shape + _fmt_count (v2026-07-18.5) ────────
# Real response captured from Jules 2026-07-18: token-based subscription with
# per-section {used, remaining, percentUsed} dicts keyed like the limits dict.

class TestUsageSummaryTokenShape:
    REAL_BODY = {
        "active": True, "provider": "stripe", "providerStatus": "active",
        "limits": {"weeklyInputTokens": 60000000, "dailyInputTokens": None,
                   "dailyImages": 100},
        "allowOverage": False,
        "period": {"currentPeriodEnd": "2026-08-10T15:15:09.000Z"},
        "dailyImages": {"used": 0, "remaining": 100, "percentUsed": 0},
        "weeklyInputTokens": {"used": 15400, "remaining": 59984600,
                              "percentUsed": 0.03},
    }

    def test_real_body_formats(self):
        msg = bot._usage_summary(self.REAL_BODY)
        assert msg is not None
        assert "15.4k / 60M" in msg
        assert "Daily images" in msg and "0 / 100" in msg
        assert "Renews: 2026-08-10" in msg

    def test_null_limit_renders_infinity(self):
        body = dict(self.REAL_BODY)
        body["dailyInputTokens"] = {"used": 5, "remaining": 995, "percentUsed": 1}
        msg = bot._usage_summary(body)
        assert "∞" in msg

    def test_sections_missing_usage_dicts_skipped(self):
        body = {"active": True, "limits": {"weeklyInputTokens": 100},
                "weeklyInputTokens": {"used": 1, "remaining": 99}}
        msg = bot._usage_summary(body)
        assert msg is not None and "Weekly" in msg and "images" not in msg

    def test_legacy_shape_still_works(self):
        data = {"daily": {"used": 10, "remaining": 90},
                "monthly": {"used": 100, "remaining": 900},
                "limits": {"daily": 100, "monthly": 1000}}
        assert "10 / 100" in bot._usage_summary(data)


class TestFmtCount:
    def test_millions_and_thousands(self):
        assert bot._fmt_count(60000000) == "60M"
        assert bot._fmt_count(15400) == "15.4k"
        assert bot._fmt_count(59984600) == "60M"

    def test_small_and_non_numeric(self):
        assert bot._fmt_count(0) == "0"
        assert bot._fmt_count(100) == "100"
        assert bot._fmt_count("?") == "?"
        assert bot._fmt_count(0.03) == "0.03"


# ── /fleet console (v2026-07-19.1) ────────────────────────────────────────────

class TestFleetParsePeers:
    def test_port_only_defaults_to_localhost(self):
        assert bot._fleet_parse_peers("nora=8080") == [("nora", "127.0.0.1", 8080)]

    def test_host_and_port(self):
        assert bot._fleet_parse_peers("jules=100.64.0.5:8085") == \
            [("jules", "100.64.0.5", 8085)]

    def test_full_fleet_mixed(self):
        peers = bot._fleet_parse_peers(
            "nora=8080, bonnie=8081,jules=100.64.0.5:8085")
        assert peers == [("nora", "127.0.0.1", 8080),
                         ("bonnie", "127.0.0.1", 8081),
                         ("jules", "100.64.0.5", 8085)]

    def test_bad_entries_skipped_not_fatal(self):
        before = len(bot._CONFIG_WARNINGS)
        peers = bot._fleet_parse_peers("nora=8080,oops,cass=notaport,=8082,priya=0")
        assert peers == [("nora", "127.0.0.1", 8080)]
        assert len(bot._CONFIG_WARNINGS) == before + 4

    def test_empty_string(self):
        assert bot._fleet_parse_peers("") == []


class TestFleetFormat:
    def test_up_row_with_all_fields(self):
        rows = [{"name": "nora", "up": True, "version": "2026-07-19.1",
                 "uptime": "45.2h", "errors": "0"}]
        out = bot._fleet_format(rows)
        assert "nora" in out and "UP" in out
        assert "2026-07-19.1" in out and "45.2h" in out and "err:0" in out

    def test_down_row_shows_detail(self):
        out = bot._fleet_format(
            [{"name": "cass", "up": False, "detail": "ConnectTimeout"}])
        assert "cass" in out and "DOWN" in out and "ConnectTimeout" in out

    def test_missing_optional_fields_omitted(self):
        out = bot._fleet_format(
            [{"name": "emily", "up": True, "version": "2026-07-18.5",
              "uptime": "", "errors": ""}])
        assert "err:" not in out and "UP" in out


class TestExtractContentNoReasoningLeak:
    """v2026-07-20.1: _extract_content must never deliver reasoning_content — it is
    raw chain-of-thought with no <think> tags for _strip_thinking to remove, so it
    leaked verbatim (Priya, 2026-07-20)."""

    def test_extract_content_uses_content(self):
        choice = {"message": {"content": "hey, running late for golf?",
                              "reasoning_content": "The user mentioned coffee. I should..."}}
        assert bot._extract_content(choice) == "hey, running late for golf?"

    def test_extract_content_never_returns_reasoning(self):
        # Empty content + populated reasoning (the leak scenario) -> empty, NOT the CoT.
        choice = {"message": {"content": "",
                              "reasoning_content": "Current state: Monday 10:36am. "
                                                   "I should incorporate the Asha thing maybe"}}
        assert bot._extract_content(choice) == ""

    def test_extract_content_strips_think_tags_from_content(self):
        choice = {"message": {"content": "<think>plan</think>the actual line"}}
        assert bot._extract_content(choice) == "the actual line"


class TestWsdotErrReasonNoKeyLeak:
    """v2026-07-20.2: WSDOT puts the AccessCode in the query string, so logging the raw
    requests exception leaked the key into errors.log. _wsdot_err_reason must classify by
    type/status and never echo the exception string (which carries the URL + key)."""

    def test_never_leaks_key(self):
        # Simulate the real leak: an exception whose str() contains the AccessCode URL.
        leaky = ("HTTPSConnectionPool(host='www.wsdot.wa.gov', port=443): Max retries "
                 "exceeded with url: /Traffic/api/...?AccessCode=SECRET-KEY-123 (Caused by "
                 "ReadTimeoutError('read timed out'))")

        class FakeReadTimeout(Exception):
            pass
        reason = bot._wsdot_err_reason(FakeReadTimeout(leaky))
        assert "SECRET-KEY-123" not in reason
        assert "AccessCode" not in reason
        assert reason == "timed out"  # classified by the "Timeout" in the class name

    def test_http_status_key_free(self):
        class FakeResp:
            status_code = 403
        class FakeHTTPError(Exception):
            response = FakeResp()
        assert bot._wsdot_err_reason(FakeHTTPError("...AccessCode=SECRET...")) == "HTTP 403"

    def test_connection_error(self):
        class ConnectionError_(Exception):
            pass
        assert bot._wsdot_err_reason(ConnectionError_("...AccessCode=SECRET...")) == "network/DNS error"


# ── _step_intent_seed ─────────────────────────────────────────────────────────
# v2026-07-23.1: stepped-thinking frame-of-mind seed. Pure freshness/validation gate;
# returns the note text or "" so a stale or missing intent never seeds the next reply.

class TestStepIntentSeed:
    def test_fresh_returns_text(self):
        now = 1000.0
        intent = {"text": "still stung, keeping her guard up", "ts": now - 60}
        assert bot._step_intent_seed(intent, now, 21600) == "still stung, keeping her guard up"

    def test_stale_dropped(self):
        now = 1000.0
        intent = {"text": "wants to lighten the mood", "ts": now - 30000}  # older than 6h
        assert bot._step_intent_seed(intent, now, 21600) == ""

    def test_missing_or_empty(self):
        now = 1000.0
        assert bot._step_intent_seed({}, now, 21600) == ""
        assert bot._step_intent_seed({"text": "", "ts": now}, now, 21600) == ""
        assert bot._step_intent_seed({"text": "   ", "ts": now}, now, 21600) == ""

    def test_non_dict_and_bad_types(self):
        now = 1000.0
        assert bot._step_intent_seed(None, now, 21600) == ""
        assert bot._step_intent_seed({"text": 123, "ts": now}, now, 21600) == ""

    def test_missing_ts_treated_as_stale(self):
        # No ts -> defaults to 0; at a real epoch now, now - 0 >> ttl -> dropped,
        # never a raw crash.
        assert bot._step_intent_seed({"text": "curious"}, 1_700_000_000.0, 21600) == ""

    def test_strips_whitespace(self):
        now = 1000.0
        assert bot._step_intent_seed({"text": "  leaning in  ", "ts": now}, now, 21600) == "leaning in"


# ── Note confidence gating (anti-hallucination, v2026-07-23.2) ──────────────

class TestNoteConfidenceConfig:
    """NOTE_AUTOCONF env var exists and defaults sanely."""

    def test_note_autoconf_default(self):
        assert hasattr(bot, "NOTE_AUTOCONF")
        assert bot.NOTE_AUTOCONF == 3

    def test_note_autoconf_is_int(self):
        assert isinstance(bot.NOTE_AUTOCONF, int)

    def test_analysis_prompt_requests_confidence(self):
        """The analysis prompt must ask the model for user_note_confidence."""
        import inspect
        src = inspect.getsource(bot._post_reply_analysis)
        assert "user_note_confidence" in src

    def test_analysis_prompt_null_over_guess(self):
        """The analysis prompt must include the null-over-guess instruction."""
        import inspect
        src = inspect.getsource(bot._post_reply_analysis)
        assert "do not fill gaps with a" in src


# ── Topic-initiative balance (PROMPT_BALANCE, v2026-07-25.1) ─────────────────
# Recall blocks were the only ones instructed to raise their contents; the live
# context blocks were passive or actively suppressed. See CHANGELOG v2026-07-25.1.

class TestInitiativeNote:
    def test_interpolates_both_names(self):
        note = bot._initiative_note("Nora", "Brian")
        assert "Nora" in note
        assert "Brian" in note

    def test_states_recall_is_not_the_default(self):
        note = bot._initiative_note("Nora", "Brian").lower()
        assert "only one option" in note
        assert "default" in note

    def test_prefers_live_opening_on_a_tie(self):
        note = bot._initiative_note("Nora", "Brian").lower()
        assert "take the live one" in note

    def test_frames_recall_as_context_not_topic_supply(self):
        note = bot._initiative_note("Nora", "Brian").lower()
        assert "context she has" in note

    def test_is_pure_and_deterministic(self):
        assert bot._initiative_note("A", "b") == bot._initiative_note("A", "b")

    def test_no_leading_or_trailing_whitespace(self):
        note = bot._initiative_note("Nora", "Brian")
        assert note == note.strip()

    def test_carries_its_own_heading(self):
        assert bot._initiative_note("Nora", "Brian").startswith("# Bringing things up")


class TestPromptBalanceConfig:
    def test_flag_exists_and_defaults_on(self):
        assert hasattr(bot, "PROMPT_BALANCE")
        assert bot.PROMPT_BALANCE is True

    def test_flag_is_bool(self):
        assert isinstance(bot.PROMPT_BALANCE, bool)


class TestPromptBalanceTails:
    """Each rewritten tail must keep the legacy string as the kill-switch branch,
    so PROMPT_BALANCE=0 restores the pre-v2026-07-25.1 prompt exactly."""

    def _src(self):
        import inspect
        return inspect.getsource(bot.assemble_messages)

    def test_legacy_notes_tail_still_present(self):
        assert "Ask about these naturally if one fits the moment" in self._src()

    def test_legacy_threads_tail_still_present(self):
        assert "Let them surface naturally if one fits" in self._src()

    def test_legacy_day_tail_still_present(self):
        assert "don't narrate it like a list" in self._src()

    def test_notes_tail_rejects_checklist_framing(self):
        assert "not a checklist to work through" in self._src()

    def test_threads_tail_rejects_filler_use(self):
        assert "just because you have nothing else" in self._src()

    def test_day_tail_grants_initiative(self):
        assert "yours to bring up unprompted" in self._src()

    def test_initiative_block_is_gated(self):
        src = self._src()
        assert "if PROMPT_BALANCE:" in src
        assert "_initiative_note(NAME, uname)" in src


# ── Garmin health feed (v2026-07-25.2) ───────────────────────────────────────
# Ported from the orphan branch claude/push-to-repo-7i2f3c, which shares no git
# history with main and so was never deployable. Pure logic split out of the I/O
# so field-name handling and the alert thresholds are testable.

class TestGarminBits:
    def test_empty_payloads_produce_nothing(self):
        assert bot._garmin_bits({}, {}, {}) == []

    def test_none_payloads_are_safe(self):
        assert bot._garmin_bits(None, None, None) == []

    def test_sleep_formats_hours_and_minutes(self):
        bits = bot._garmin_bits({"sleepTimeSeconds": 7 * 3600 + 5 * 60}, {}, {})
        assert bits == ["slept 7h05m last night"]

    def test_sleep_score_and_qualifier_appended(self):
        bits = bot._garmin_bits(
            {"sleepTimeSeconds": 3600,
             "sleepScores": {"overall": {"value": 82, "qualifierKey": "GOOD"}}}, {}, {})
        assert "sleep score 82" in bits[0]
        assert "good" in bits[0]

    def test_zero_sleep_is_dropped_not_rendered(self):
        # A 0 reading means "no data", not "slept 0h" — must not be reported.
        assert bot._garmin_bits({"sleepTimeSeconds": 0}, {}, {}) == []

    def test_steps_thousands_separator(self):
        assert "12,345 steps so far" in bot._garmin_bits({}, {"totalSteps": 12345}, {})

    def test_zero_steps_still_reported(self):
        # 0 steps is real information (unlike 0 sleep) — the key is present.
        assert "0 steps so far" in bot._garmin_bits({}, {"totalSteps": 0}, {})

    def test_negative_stress_skipped(self):
        # Garmin uses -1/-2 for "couldn't measure".
        assert bot._garmin_bits({}, {"averageStressLevel": -1}, {}) == []

    def test_stress_zero_is_kept(self):
        assert "avg stress 0" in bot._garmin_bits({}, {"averageStressLevel": 0}, {})

    def test_body_battery_reported(self):
        assert "body battery 43" in bot._garmin_bits({}, {"bodyBatteryMostRecentValue": 43}, {})

    def test_activity_distance_in_km(self):
        bits = bot._garmin_bits({}, {}, {
            "activityType": {"typeKey": "trail_running"},
            "distance": 5400, "startTimeLocal": "2026-07-24 08:00:00"})
        assert "trail running" in bits[0]
        assert "5.4km" in bits[0]
        assert "2026-07-24" in bits[0]

    def test_activity_without_distance(self):
        bits = bot._garmin_bits({}, {}, {"activityName": "yoga"})
        assert bits == ["last workout: yoga"]

    def test_one_bad_field_does_not_lose_the_others(self):
        bits = bot._garmin_bits({"sleepTimeSeconds": "nonsense"},
                                {"totalSteps": 900}, {})
        assert any("900 steps" in b for b in bits)

    def test_all_fields_together(self):
        bits = bot._garmin_bits(
            {"sleepTimeSeconds": 6 * 3600},
            {"restingHeartRate": 54, "totalSteps": 3000,
             "bodyBatteryMostRecentValue": 60, "averageStressLevel": 30},
            {"activityName": "ride"})
        assert len(bits) == 6


class TestStressSustained:
    @staticmethod
    def _pairs(values, base_ts=1_000_000.0):
        return [[base_ts + i, v] for i, v in enumerate(values)]

    def test_no_data_returns_none_avg(self):
        # None avg must be distinguishable from a calm average that rounds to 0.
        high, avg = bot._stress_sustained([], 0, 60)
        assert high is False and avg is None

    def test_too_few_samples_returns_none_avg(self):
        high, avg = bot._stress_sustained(self._pairs([80, 80]), 0, 60)
        assert high is False and avg is None

    def test_sustained_high_detected(self):
        high, avg = bot._stress_sustained(self._pairs([70, 75, 80, 72]), 0, 60)
        assert high is True and avg == 74

    def test_calm_readings_are_not_high(self):
        high, avg = bot._stress_sustained(self._pairs([10, 12, 15]), 0, 60)
        assert high is False and avg == 12

    def test_genuinely_calm_avg_zero_is_not_none(self):
        high, avg = bot._stress_sustained(self._pairs([0, 0, 0]), 0, 60)
        assert high is False and avg == 0

    def test_unmeasurable_readings_skipped(self):
        # -1/-2 must be dropped, not averaged in as low stress.
        high, avg = bot._stress_sustained(self._pairs([-1, -2, 80, 80, 80]), 0, 60)
        assert high is True and avg == 80

    def test_readings_before_cutoff_excluded(self):
        pairs = [[100, 90], [200, 90], [5000, 10], [5001, 10], [5002, 10]]
        high, avg = bot._stress_sustained(pairs, 5000, 60)
        assert high is False and avg == 10

    def test_brief_spike_is_not_sustained(self):
        # One spike in five readings fails the 70%-of-window requirement.
        high, avg = bot._stress_sustained(self._pairs([90, 10, 10, 10, 10]), 0, 60)
        assert high is False

    def test_malformed_entries_ignored(self):
        pairs = [None, [1], "junk", [1, "x"], [1, 80], [2, 80], [3, 80]]
        high, avg = bot._stress_sustained(pairs, 0, 60)
        assert high is True and avg == 80


class TestRhrBaseline:
    def test_none_when_history_empty(self):
        assert bot._rhr_baseline([], "2026-07-25", 3) is None

    def test_none_when_below_min_days(self):
        h = [{"date": "2026-07-23", "rhr": 50}, {"date": "2026-07-24", "rhr": 52}]
        assert bot._rhr_baseline(h, "2026-07-25", 3) is None

    def test_median_of_prior_days(self):
        h = [{"date": "2026-07-21", "rhr": 50},
             {"date": "2026-07-22", "rhr": 60},
             {"date": "2026-07-23", "rhr": 55}]
        assert bot._rhr_baseline(h, "2026-07-25", 3) == 55

    def test_today_excluded_from_its_own_baseline(self):
        # Today's elevated reading must not raise the baseline it's compared against.
        h = [{"date": "2026-07-22", "rhr": 50},
             {"date": "2026-07-23", "rhr": 50},
             {"date": "2026-07-24", "rhr": 50},
             {"date": "2026-07-25", "rhr": 90}]
        assert bot._rhr_baseline(h, "2026-07-25", 3) == 50

    def test_malformed_rows_ignored(self):
        h = [{"date": "a", "rhr": 50}, "junk", {"date": "b"},
             {"date": "c", "rhr": None}, {"date": "d", "rhr": 52},
             {"date": "e", "rhr": 54}]
        assert bot._rhr_baseline(h, "2026-07-25", 3) == 52

    def test_nonpositive_readings_ignored(self):
        h = [{"date": "a", "rhr": 0}, {"date": "b", "rhr": -5},
             {"date": "c", "rhr": 50}, {"date": "d", "rhr": 52},
             {"date": "e", "rhr": 54}]
        assert bot._rhr_baseline(h, "2026-07-25", 3) == 52

    def test_none_history_is_safe(self):
        assert bot._rhr_baseline(None, "2026-07-25", 3) is None


class TestGarminConfig:
    def test_kill_switch_exists_and_defaults_on(self):
        assert hasattr(bot, "GARMIN_FEED")
        assert bot.GARMIN_FEED is True

    def test_disabled_without_credentials(self):
        # No creds in the test fixture .env, so the feed must be inert.
        assert bot.GARMIN_ENABLED is False

    def test_monitors_require_the_feed(self):
        assert bot.STRESS_ALERTS is False
        assert bot.BB_ALERTS is False
        assert bot.RHR_ALERTS is False

    def test_numeric_config_went_through_env_helpers(self):
        assert isinstance(bot.STRESS_THRESHOLD, int)
        assert isinstance(bot.GARMIN_MAX_AGE_HOURS, float)
        assert isinstance(bot.BB_ALERT_COOLDOWN_HOURS, float)

    def test_off_reason_explains_missing_credentials(self):
        assert "GARMIN_EMAIL" in bot._garmin_off_reason()

    def test_audit_state_reports_off(self):
        assert "off" in bot._garmin_audit_state()

    def test_health_commands_in_menu_only_when_enabled(self):
        names = {c.command for c in bot._build_command_menu(False, False, False)}
        assert "health" not in names
        on = {c.command for c in bot._build_command_menu(False, False, True)}
        assert {"health", "healthnow", "stress"} <= on


class TestGarminInvariants:
    """Rules from bot-code-invariants that this feature could plausibly break."""

    def test_every_garmin_call_runs_off_the_event_loop(self):
        # Invariant #8: garminconnect is blocking requests underneath.
        import inspect
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job,
                   bot.rhr_monitor_job, bot.update_garmin):
            src = inspect.getsource(fn)
            assert "asyncio.to_thread" in src, fn.__name__

    def test_snapshot_never_enters_group_prompts(self):
        # GROUP_CHAT_DESIGN.md §5: watch metrics are private 1:1 state.
        import inspect
        src = inspect.getsource(bot.assemble_messages)
        assert "GARMIN_ENABLED and not group" in src

    def test_health_commands_not_group_allowed(self):
        assert bot.GROUP_ALLOWED_COMMANDS == {"chatid"}

    def test_no_raw_exception_in_garmin_logs(self):
        # Garmin errors can carry the request URL; log the type only (cf. the WSDOT
        # key-leak fix in v2026-07-20.2).
        import inspect
        for fn in (bot._fetch_garmin, bot._drop_garmin_session):
            src = inspect.getsource(fn)
            assert '", e)' not in src, fn.__name__
            assert '", exc)' not in src, fn.__name__
            # Only the exception's class name may reach a log line.
            assert ".__name__" in src, fn.__name__

    def test_check_ins_consume_the_nudge_budget(self):
        import inspect
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job, bot.rhr_monitor_job):
            assert "_consume_nudge(owner)" in inspect.getsource(fn), fn.__name__

    def test_check_ins_respect_the_proactive_gate(self):
        import inspect
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job, bot.rhr_monitor_job):
            assert "_health_nudge_ok(owner)" in inspect.getsource(fn), fn.__name__

    def test_health_nudge_gate_checks_every_condition(self):
        import inspect
        src = inspect.getsource(bot._health_nudge_ok)
        for gate in ("_is_quiet", "_is_away", "in_quiet_hours",
                     "_in_quiet_window", "_check_nudge_budget"):
            assert gate in src, gate

    def test_no_new_llm_call_added(self):
        # Invariant #3: the feed is prompt context + the existing proactive path.
        import inspect
        for fn in (bot.update_garmin, bot._fetch_garmin, bot.stress_monitor_job,
                   bot.bb_monitor_job, bot.rhr_monitor_job):
            src = inspect.getsource(fn)
            assert "call_nanogpt" not in src, fn.__name__


# ── Assembled-prompt instrumentation (PROMPT_STATS, v2026-07-25.3) ───────────
# Nothing measured a single prompt before this; _llm_stats["tok_in"] is a daily
# running sum across all LLM calls. See CHANGELOG v2026-07-25.3.

class TestPromptTokenTotal:
    def test_empty_prompt_is_zero(self):
        assert bot._prompt_token_total([]) == 0

    def test_sums_all_messages(self):
        msgs = [{"role": "system", "content": "a" * 400},
                {"role": "user", "content": "b" * 400}]
        assert bot._prompt_token_total(msgs) == 200

    def test_multipart_content_does_not_crash(self):
        # Image messages carry a list, not a str.
        msgs = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        assert bot._prompt_token_total(msgs) > 0

    def test_missing_content_key_is_safe(self):
        assert bot._prompt_token_total([{"role": "system"}]) >= 1


class TestPromptBucket:
    def test_small_prompt(self):
        assert bot._prompt_bucket(0) == "<8k"
        assert bot._prompt_bucket(7999) == "<8k"

    def test_boundaries_are_exclusive_upper(self):
        assert bot._prompt_bucket(8000) == "8-12k"
        assert bot._prompt_bucket(12000) == "12-16k"
        assert bot._prompt_bucket(16000) == "16-24k"
        assert bot._prompt_bucket(24000) == "24-32k"

    def test_overflow_bucket(self):
        assert bot._prompt_bucket(32000) == "32k+"
        assert bot._prompt_bucket(500000) == "32k+"

    def test_measured_fleet_range_lands_in_expected_buckets(self):
        # cass 11,435 and jules 14,822 as measured for this release.
        assert bot._prompt_bucket(11435) == "8-12k"
        assert bot._prompt_bucket(14822) == "12-16k"


class TestPromptTopBlocks:
    def test_returns_biggest_first(self):
        msgs = [{"role": "system", "content": "# small\n" + "x" * 40},
                {"role": "system", "content": "# big\n" + "x" * 4000},
                {"role": "user", "content": "y" * 8000}]
        top = bot._prompt_top_blocks(msgs)
        assert top[0][1] == "# big"

    def test_ignores_non_system_messages(self):
        msgs = [{"role": "user", "content": "u" * 8000},
                {"role": "system", "content": "# only\nx"}]
        assert [h for _, h in bot._prompt_top_blocks(msgs)] == ["# only"]

    def test_respects_the_limit(self):
        msgs = [{"role": "system", "content": f"# h{i}\n" + "x" * (100 * i)}
                for i in range(1, 8)]
        assert len(bot._prompt_top_blocks(msgs, n=3)) == 3

    def test_heading_is_truncated(self):
        msgs = [{"role": "system", "content": "#" + "z" * 200}]
        assert len(bot._prompt_top_blocks(msgs)[0][1]) <= 48

    def test_multipart_content_skipped_not_fatal(self):
        msgs = [{"role": "system", "content": [{"type": "text"}]},
                {"role": "system", "content": "# ok\nx"}]
        assert bot._prompt_top_blocks(msgs)[0][1] == "# ok"

    def test_empty_input(self):
        assert bot._prompt_top_blocks([]) == []


class TestRecordPromptSize:
    def setup_method(self):
        bot._prompt_stats.update({"n": 0, "sum": 0, "max": 0, "max_ts": 0.0,
                                  "max_chat": None, "max_blocks": [], "buckets": {}})

    def test_records_count_and_total(self):
        msgs = [{"role": "system", "content": "a" * 4000}]
        total = bot._record_prompt_size(msgs, 7)
        assert total == 1000
        assert bot._prompt_stats["n"] == 1
        assert bot._prompt_stats["sum"] == 1000

    def test_tracks_the_maximum_and_its_chat(self):
        bot._record_prompt_size([{"role": "system", "content": "a" * 400}], 1)
        bot._record_prompt_size([{"role": "system", "content": "a" * 40000}], 2)
        bot._record_prompt_size([{"role": "system", "content": "a" * 800}], 3)
        assert bot._prompt_stats["max"] == 10000
        assert bot._prompt_stats["max_chat"] == 2

    def test_max_blocks_captured_at_the_peak(self):
        # Index 0 is the merged card block and gets a fixed label, so put the block
        # under test after it (see TestCardBlockLabelling).
        bot._record_prompt_size(
            [{"role": "system", "content": "card"},
             {"role": "system", "content": "# peak\n" + "a" * 40000}], 1)
        assert bot._prompt_stats["max_blocks"][0][1] == "# peak"

    def test_buckets_accumulate(self):
        for _ in range(3):
            bot._record_prompt_size([{"role": "system", "content": "a" * 400}], 1)
        assert bot._prompt_stats["buckets"]["<8k"] == 3

    def test_average_is_derivable(self):
        bot._record_prompt_size([{"role": "system", "content": "a" * 4000}], 1)
        bot._record_prompt_size([{"role": "system", "content": "a" * 8000}], 1)
        s = bot._prompt_stats
        assert s["sum"] // s["n"] == 1500

    def test_audit_state_empty_before_any_prompt(self):
        assert bot._prompt_audit_state() == {}

    def test_audit_state_populated_after(self):
        bot._record_prompt_size([{"role": "system", "content": "a" * 4000}], 1)
        st = bot._prompt_audit_state()
        assert st["n"] == 1 and st["avg"] == 1000 and st["max"] == 1000


class TestTrimBudgetLogging:
    """The budget cannot be enforced when the system blocks alone exceed it — that
    used to be silent. See CHANGELOG v2026-07-25.3."""

    @staticmethod
    def _prompt(system_tokens, n_hist):
        msgs = [{"role": "system", "content": "s" * (4 * system_tokens)}]
        for i in range(n_hist):
            msgs.append({"role": "user" if i % 2 == 0 else "assistant",
                         "content": "x" * 400})
        msgs.append({"role": "user", "content": "final"})
        return msgs

    def test_disabled_budget_is_a_passthrough(self):
        m = self._prompt(1000, 5)
        assert bot._trim_prompt_to_budget(list(m), 0) == m

    def test_under_budget_is_untouched(self):
        m = self._prompt(100, 3)
        assert len(bot._trim_prompt_to_budget(list(m), 100000)) == len(m)

    def test_drops_history_oldest_first(self):
        m = self._prompt(1000, 20)
        out = bot._trim_prompt_to_budget(list(m), 1300)
        assert len(out) < len(m)
        assert out[-1]["content"] == "final"   # final user message always survives

    def test_system_blocks_are_never_dropped(self):
        m = self._prompt(1000, 20)
        out = bot._trim_prompt_to_budget(list(m), 1100)
        assert sum(1 for x in out if x["role"] == "system") == 1

    def test_over_budget_warns_and_counts_an_error(self, caplog):
        import logging
        before = len(bot._error_counts.get("prompt_budget", []))
        m = self._prompt(14000, 40)
        with caplog.at_level(logging.WARNING):
            out = bot._trim_prompt_to_budget(list(m), 8000)
        # All history stripped, still over — the case that used to pass silently.
        assert sum(1 for x in out if x["role"] != "system") == 1
        assert any("OVER BUDGET" in r.message for r in caplog.records)
        assert len(bot._error_counts.get("prompt_budget", [])) == before + 1

    def test_successful_trim_does_not_warn(self, caplog):
        import logging
        m = self._prompt(1000, 20)
        with caplog.at_level(logging.WARNING):
            bot._trim_prompt_to_budget(list(m), 5000)
        assert not any("OVER BUDGET" in r.message for r in caplog.records)


class TestPromptStatsConfig:
    def test_flag_exists_and_defaults_on(self):
        assert bot.PROMPT_STATS is True

    def test_budget_still_defaults_off(self):
        # Must stay 0 until the trimmer's priority order is fixed (v2026-07-25.4).
        assert bot.CONTEXT_TOKEN_BUDGET == 0

    def test_assemble_records_when_enabled(self):
        bot._prompt_stats.update({"n": 0, "sum": 0, "max": 0, "max_ts": 0.0,
                                  "max_chat": None, "max_blocks": [], "buckets": {}})
        bot.conversation_history[99] = []
        bot.user_names[99] = "Tester"
        bot.assemble_messages(99, "hello")
        assert bot._prompt_stats["n"] == 1
        assert bot._prompt_stats["max"] > 0


# ── Tiered prompt trimming (v2026-07-25.4) ───────────────────────────────────
# The old trimmer protected EVERY system block and dropped only conversation, so it
# would delete a dozen live turns to keep a triggered lorebook entry — and could strip
# all history and still ship over budget. See CHANGELOG v2026-07-25.4.

class TestSysOpt:
    def test_marks_the_optional_tier(self):
        m = bot._sys_opt("# Relevant memories\nx")
        assert m["role"] == "system"
        assert m["_tier"] == bot._TIER_OPTIONAL

    def test_content_is_preserved(self):
        assert bot._sys_opt("hello")["content"] == "hello"


class TestStripTiers:
    def test_removes_internal_keys(self):
        out = bot._strip_tiers([bot._sys_opt("x")])
        assert out == [{"role": "system", "content": "x"}]

    def test_leaves_normal_messages_untouched(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert bot._strip_tiers(msgs) == msgs

    def test_no_underscore_keys_survive(self):
        out = bot._strip_tiers([{"role": "system", "content": "x", "_tier": 2, "_x": 1}])
        assert not any(k.startswith("_") for m in out for k in m)

    def test_assembled_prompt_carries_no_internal_keys(self):
        # Whatever the API receives must be role/content only.
        bot.conversation_history[77] = []
        bot.user_names[77] = "Tester"
        msgs = bot.assemble_messages(77, "hello")
        assert all(set(m) <= {"role", "content"} for m in msgs)


class TestTieredTrimOrder:
    @staticmethod
    def _prompt(protected_tok, optional_toks, n_hist, hist_tok=25):
        msgs = [{"role": "system", "content": "P" * (4 * protected_tok)}]
        for t in optional_toks:
            msgs.append(bot._sys_opt("# opt\n" + "o" * (4 * t)))
        for i in range(n_hist):
            msgs.append({"role": "user" if i % 2 == 0 else "assistant",
                         "content": "h" * (4 * hist_tok)})
        msgs.append({"role": "user", "content": "final"})
        return msgs

    @staticmethod
    def _n_optional(msgs):
        return sum(1 for m in msgs if m.get("_tier") == bot._TIER_OPTIONAL)

    @staticmethod
    def _n_hist(msgs):
        return sum(1 for m in msgs if m.get("role") != "system")

    def test_optional_blocks_go_before_any_history(self):
        # The whole point of the release: conversation outlives optional context.
        m = self._prompt(1000, [500, 500], 10, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 1300, keep_recent=2)
        assert self._n_optional(out) == 0
        assert self._n_hist(out) == 11          # 10 history + final, all intact

    def test_largest_optional_dropped_first(self):
        m = self._prompt(1000, [50, 900], 2, hist_tok=10)
        out = bot._trim_prompt_to_budget(list(m), 1200, keep_recent=2)
        kept = [x for x in out if x.get("_tier") == bot._TIER_OPTIONAL]
        assert len(kept) == 1
        assert bot._msg_tokens(kept[0]) < 200   # the small one survived

    def test_history_trimmed_only_after_optional_exhausted(self):
        m = self._prompt(1000, [200], 20, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 1200, keep_recent=4)
        assert self._n_optional(out) == 0
        assert self._n_hist(out) < 21

    def test_oldest_history_goes_first_newest_survives(self):
        # Distinguishable turns so we can prove WHICH ones survived, not just how many.
        msgs = [{"role": "system", "content": "P" * 4000}]
        for i in range(20):
            msgs.append({"role": "user" if i % 2 == 0 else "assistant",
                         "content": f"turn{i:02d} " + "h" * 92})
        msgs.append({"role": "user", "content": "final"})
        out = bot._trim_prompt_to_budget(msgs, 1200, keep_recent=5)
        kept = [m["content"][:6] for m in out
                if m["role"] != "system" and m["content"] != "final"]
        assert kept, "some history should survive at this budget"
        # Whatever survived is a contiguous run ending at the newest turn.
        assert kept[-1] == "turn19"
        assert kept == sorted(kept)

    def test_keep_recent_is_held_back_until_older_is_exhausted(self):
        m = self._prompt(1000, [], 20, hist_tok=25)
        # Budget leaves room for ~3 turns, so the 15 "older" ones must all go first
        # and the dip into the newest 5 stops the moment it fits.
        out = bot._trim_prompt_to_budget(list(m), 1100, keep_recent=5)
        assert self._n_hist(out) == 4          # 3 recent + the final user message

    def test_last_resort_dips_below_keep_recent(self):
        m = self._prompt(1000, [], 20, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 1000, keep_recent=5)
        assert self._n_hist(out) == 1           # only the final user message left

    def test_final_user_message_always_survives(self):
        m = self._prompt(1000, [400], 20, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 1000, keep_recent=5)
        assert out[-1]["content"] == "final"

    def test_protected_block_never_dropped(self):
        m = self._prompt(2000, [400], 10, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 100, keep_recent=2)
        assert sum(1 for x in out if x.get("_tier") is None
                   and x["role"] == "system") == 1

    def test_stops_as_soon_as_it_fits(self):
        m = self._prompt(1000, [100, 100, 100], 5, hist_tok=10)
        out = bot._trim_prompt_to_budget(list(m), 1250, keep_recent=2)
        assert self._n_optional(out) >= 1       # didn't drop more than needed
        assert self._n_hist(out) == 6           # history untouched

    def test_under_budget_is_a_noop(self):
        m = self._prompt(100, [50], 4, hist_tok=10)
        assert len(bot._trim_prompt_to_budget(list(m), 100000)) == len(m)

    def test_zero_budget_disables_everything(self):
        m = self._prompt(9999, [999], 40)
        assert bot._trim_prompt_to_budget(list(m), 0) == m

    def test_keep_recent_zero_allows_full_history_drop(self):
        m = self._prompt(1000, [], 20, hist_tok=25)
        out = bot._trim_prompt_to_budget(list(m), 1000, keep_recent=0)
        assert self._n_hist(out) == 1

    def test_unfittable_still_warns(self, caplog):
        import logging
        m = self._prompt(5000, [200], 10, hist_tok=25)
        with caplog.at_level(logging.WARNING):
            bot._trim_prompt_to_budget(list(m), 1000, keep_recent=2)
        assert any("OVER BUDGET" in r.message for r in caplog.records)

    def test_successful_trim_does_not_warn(self, caplog):
        import logging
        m = self._prompt(1000, [500], 5, hist_tok=25)
        with caplog.at_level(logging.WARNING):
            bot._trim_prompt_to_budget(list(m), 1300, keep_recent=2)
        assert not any("OVER BUDGET" in r.message for r in caplog.records)


class TestOptionalBlocksAreMarked:
    """The blocks that should be sacrificeable actually carry the marker. Without this,
    a budget would silently fall back to eating conversation again."""

    def _assembled(self):
        import inspect
        return inspect.getsource(bot.assemble_messages)

    def test_seven_optional_blocks_marked(self):
        assert self._assembled().count("_sys_opt(") == 7

    def test_lore_is_optional(self):
        src = self._assembled()
        i = src.index("# Relevant background")
        assert "_sys_opt(" in src[max(0, i - 200):i]

    def test_memories_are_optional(self):
        src = self._assembled()
        assert "_sys_opt(block)" in src

    def test_day_context_is_optional(self):
        src = self._assembled()
        i = src.index("# What's going on today")
        assert "_sys_opt(" in src[max(0, i - 200):i]

    def test_voice_critical_blocks_are_not_optional(self):
        # The card's own instructions and the texting preset must never be droppable.
        src = self._assembled()
        for anchor in ("POST_HISTORY_RAW", "TEXTING_STYLE"):
            i = src.index(anchor)
            assert "_sys_opt(" not in src[max(0, i - 160):i], anchor


# ── Layered presets + honest card labelling (v2026-07-25.5) ──────────────────
# One shared 8.5k preset meant every bot carried instructions written for the others.
# See CHANGELOG v2026-07-25.5.

class TestPresetLayers:
    def test_layers_are_loaded(self):
        assert isinstance(bot.PRESET_LAYERS, list)
        assert bot.PRESET_LAYERS, "there must always be at least a built-in fallback"

    def test_each_layer_is_name_and_text(self):
        for name, text in bot.PRESET_LAYERS:
            assert isinstance(name, str) and name
            assert isinstance(text, str) and text.strip()

    def test_texting_style_is_the_joined_layers(self):
        assert bot.TEXTING_STYLE == "\n\n".join(t for _, t in bot.PRESET_LAYERS)

    def test_fixture_falls_back_to_builtin(self):
        # The test fixture has no preset.txt, so the built-in default must be used —
        # the documented no-preset case, and it must not warn about it.
        assert bot.PRESET_LAYERS == [("<built-in>", bot._DEFAULT_TEXTING_STYLE)]

    def test_missing_default_preset_does_not_warn(self):
        joined = " ".join(bot._CONFIG_WARNINGS)
        assert "preset layer" not in joined

    def test_preset_file_env_still_honoured(self):
        # Backward compatibility: PRESET_FILE must keep working as the single-layer name.
        assert bot.PRESET_FILE == "preset.txt"

    def test_every_layer_injected_as_its_own_block(self):
        import inspect
        src = inspect.getsource(bot.assemble_messages)
        assert "for _lname, _ltext in PRESET_LAYERS:" in src

    def test_layers_reported_in_audit(self):
        d = bot.gather_audit_data()
        assert "preset_layers" in d
        assert all(isinstance(t, int) for _, t in d["preset_layers"])


# ── /preset: switching layers from Telegram (v2026-07-26.1) ────────────────────
# The stack is a module global re-read on every message, so swapping it is live. The
# risk this suite guards is the one the fallback ladder was built for: a typo or a
# missing file quietly stripping tuned voice rules and reading as a model regression.

class _PresetFixture:
    """Write real layer files into the fixture instance dir and restore the live stack.

    The module-scope stack is asserted elsewhere (test_fixture_falls_back_to_builtin),
    so every test here MUST put it back — restoring by re-editing, never by leaving it
    to import order.
    """

    def __enter__(self):
        self._layers = bot.PRESET_LAYERS
        self._style = bot.TEXTING_STYLE
        self._override = list(bot.preset_override)
        self._env = list(bot._PRESET_ENV_NAMES)
        self._written = []
        for name, body in (("preset-core.txt", "CORE " * 100),
                           ("preset-rp.txt", "RP " * 50),
                           ("preset-explicit.txt", "EXPLICIT " * 40)):
            p = bot.BASE_DIR / name
            p.write_text(body, encoding="utf-8")
            self._written.append(p)
        return self

    def __exit__(self, *exc):
        bot.PRESET_LAYERS = self._layers
        bot.TEXTING_STYLE = self._style
        bot.preset_override[:] = self._override
        bot._PRESET_ENV_NAMES[:] = self._env
        for p in self._written:
            p.unlink(missing_ok=True)
        return False


# ── Token counts are measured, not guessed (v2026-07-26.2) ────────────────────
# Every reported figure was len(text)//4 presented as "~Nt". The provider returns the
# real count on every call; these pin that it is used, and that the calibration derived
# from it cannot be poisoned by the calls where the ratio means nothing.

class _CalFixture:
    """Isolate the module-level calibration state."""

    def __init__(self, ratio=1.0, n=0, enabled=True):
        self._want = (ratio, n, enabled)

    def __enter__(self):
        self._saved = (bot.token_calibration["ratio"], bot.token_calibration["n"],
                       bot.TOKEN_CALIBRATION)
        r, n, e = self._want
        bot.token_calibration["ratio"], bot.token_calibration["n"] = r, n
        bot.TOKEN_CALIBRATION = e
        return self

    def __exit__(self, *exc):
        (bot.token_calibration["ratio"], bot.token_calibration["n"],
         bot.TOKEN_CALIBRATION) = self._saved
        return False


class TestUsageTokenParsing:
    def test_reads_a_normal_usage_block(self):
        assert bot._usage_tokens({"prompt_tokens": 1234}, "prompt_tokens") == 1234

    def test_missing_and_null_are_zero(self):
        assert bot._usage_tokens({}, "prompt_tokens") == 0
        assert bot._usage_tokens({"prompt_tokens": None}, "prompt_tokens") == 0

    def test_garbage_is_zero_not_an_exception(self):
        # Accounting hangs off a reply that already succeeded; it must never raise.
        assert bot._usage_tokens({"prompt_tokens": "lots"}, "prompt_tokens") == 0
        assert bot._usage_tokens(None, "prompt_tokens") == 0
        assert bot._usage_tokens({"prompt_tokens": -5}, "prompt_tokens") == 0


class TestCalibrationSample:
    def test_plausible_ratio_accepted(self):
        assert bot._calibration_sample(1000, 1150) == pytest.approx(1.15)

    def test_tiny_prompts_rejected(self):
        # Per-message template overhead dominates, so the ratio would be meaningless.
        assert bot._calibration_sample(50, 200) is None

    def test_absurd_ratios_rejected(self):
        # A vision call carries image tokens with no characters behind them; folding
        # that in would corrupt every text-only reading afterwards.
        assert bot._calibration_sample(1000, 90_000) is None
        assert bot._calibration_sample(1000, 100) is None

    def test_zero_actual_rejected(self):
        assert bot._calibration_sample(1000, 0) is None


class TestCalibrationBlend:
    def test_first_sample_replaces_the_seed(self):
        # Otherwise the displayed ratio starts at a value nobody measured and crawls.
        assert bot._blend_calibration(1.0, 0, 1.30) == 1.30

    def test_later_samples_are_smoothed(self):
        out = bot._blend_calibration(1.30, 5, 1.10, alpha=0.2)
        assert 1.10 < out < 1.30

    def test_converges_toward_a_stable_signal(self):
        r, n = 1.0, 0
        for _ in range(40):
            r = bot._blend_calibration(r, n, 1.25)
            n += 1
        assert r == pytest.approx(1.25, abs=0.01)


class TestCalibratedTokens:
    def test_uncalibrated_matches_the_raw_heuristic(self):
        with _CalFixture(ratio=1.0, n=0):
            assert bot._tokens("x" * 4000) == bot._est_tokens("x" * 4000)

    def test_calibration_scales_the_estimate(self):
        with _CalFixture(ratio=1.25, n=10):
            assert bot._tokens("x" * 4000) == pytest.approx(
                bot._est_tokens("x" * 4000) * 1.25, rel=0.01)

    def test_kill_switch_returns_the_raw_estimate(self):
        with _CalFixture(ratio=1.25, n=10, enabled=False):
            assert bot._tokens("x" * 4000) == bot._est_tokens("x" * 4000)

    def test_confidence_string_distinguishes_guess_from_measurement(self):
        with _CalFixture(ratio=1.0, n=0):
            assert "no measured API call" in bot._token_confidence()
        with _CalFixture(ratio=1.25, n=7):
            s = bot._token_confidence()
            assert "1.25" in s and "7" in s
        with _CalFixture(ratio=1.25, n=7, enabled=False):
            assert "TOKEN_CALIBRATION=0" in bot._token_confidence()

    def test_memory_budget_uses_calibrated_units(self):
        # ROADMAP 4.4, owner-approved 2026-08-01: MEMORY_TOKEN_BUDGET switched from the
        # raw len//4 estimate to _tokens() (calibrated). Safe only because every live
        # instance's .env was multiplied by its own measured ratio at cutover first, so
        # this line changing is not itself the personality change -- that already
        # happened, deliberately, in each instance's .env before this shipped.
        import inspect
        import re
        whole = inspect.getsource(bot)
        m = re.search(r"budget = MEMORY_TOKEN_BUDGET.*?cost = (\w+)\(line\)",
                      whole, re.S)
        assert m and m.group(1) == "_tokens", "memory budget must use the calibrated unit"


class TestUsageAccounting:
    def _reset(self):
        bot._llm_stats.update(date="", calls=0, tok_in=0, tok_out=0,
                              measured=0, estimated=0)
        bot._stash_call_usage(None)

    def test_real_usage_is_spent_not_the_estimate(self):
        self._reset()
        with _CalFixture():
            msgs = [{"role": "user", "content": "x" * 4000}]   # est 1000
            bot._stash_call_usage({"prompt_tokens": 1234, "completion_tokens": 56})
            bot._track_llm_usage(msgs, "y" * 400)
            assert bot._llm_stats["tok_in"] == 1234
            assert bot._llm_stats["tok_out"] == 56
            assert bot._llm_stats["measured"] == 1 and bot._llm_stats["estimated"] == 0
        self._reset()

    def test_falls_back_to_the_estimate_without_usage(self):
        self._reset()
        with _CalFixture():
            msgs = [{"role": "user", "content": "x" * 4000}]
            bot._track_llm_usage(msgs, "y" * 400)
            assert bot._llm_stats["tok_in"] == 1000
            assert bot._llm_stats["estimated"] == 1 and bot._llm_stats["measured"] == 0
        self._reset()

    def test_usage_is_consumed_once(self):
        # A stale stash would let one call's real count be billed to the next.
        self._reset()
        with _CalFixture():
            bot._stash_call_usage({"prompt_tokens": 1234})
            msgs = [{"role": "user", "content": "x" * 4000}]
            bot._track_llm_usage(msgs, "r")
            bot._track_llm_usage(msgs, "r")
            assert bot._llm_stats["measured"] == 1 and bot._llm_stats["estimated"] == 1
        self._reset()

    def test_measured_call_updates_the_calibration(self):
        self._reset()
        with _CalFixture(ratio=1.0, n=0):
            msgs = [{"role": "user", "content": "x" * 4000}]     # est 1000
            bot._stash_call_usage({"prompt_tokens": 1200, "completion_tokens": 10})
            bot._track_llm_usage(msgs, "r")
            assert bot.token_calibration["n"] == 1
            assert bot.token_calibration["ratio"] == pytest.approx(1.2, rel=0.01)
        self._reset()


class TestUsageCaptureWiring:
    """The plumbing that makes a real count reachable at all."""

    def test_streaming_asks_for_usage(self):
        import inspect
        assert '"include_usage": True' in inspect.getsource(bot._one_call), \
            "a streamed response carries no usage block unless it is requested"

    def test_usage_chunk_parsed_before_the_choices_access(self):
        # The usage chunk has an EMPTY choices list: read after choices[0] it would
        # IndexError and be skipped, discarding the only real count streaming provides.
        import inspect
        src = inspect.getsource(bot._do_request)
        assert src.index('chunk.get("usage")') < src.index('chunk["choices"][0]')

    def test_non_streaming_path_captures_usage(self):
        import inspect
        assert '_stash_call_usage(body.get("usage"))' in inspect.getsource(bot._do_request)

    def test_stream_options_rejection_keeps_streaming(self):
        # Dropping to non-streaming over a rejected accounting flag would be a latency
        # regression on every reply that model serves.
        import inspect
        src = inspect.getsource(bot._one_call)
        assert "_no_usage_stream_models.add(model)" in src
        assert src.index("_no_usage_stream_models.add(model)") < \
            src.index("_no_stream_models.add(model)")

    def test_stale_usage_cleared_before_each_request(self):
        import inspect
        assert "_stash_call_usage(None)" in inspect.getsource(bot._do_request)

    def test_saved_calibration_is_validated(self):
        import inspect
        src = inspect.getsource(bot.load_state)
        assert "_TOKEN_CAL_MIN_RATIO" in src, \
            "a hand-edited state.json must not set a nonsense multiplier"


class TestPromptStatsUnits(object):
    """v2026-07-26.3: stats accumulate over time, so they must be stored in the unit that
    stays meaningful — raw — and calibrated at render. Storing calibrated numbers froze
    the ratio live at each sample, so one /audit reported the same file at two sizes."""

    def _fresh(self):
        bot._prompt_stats.update(n=0, sum=0, max=0, max_ts=0, max_chat=None,
                                 max_blocks=[], buckets={})

    def test_samples_are_stored_raw(self):
        self._fresh()
        with _CalFixture(ratio=1.5, n=10):
            msgs = [{"role": "system", "content": "x" * 40000}]   # raw 10000
            bot._record_prompt_size(msgs, 1)
            assert bot._prompt_stats["sum"] == 10000, "a live ratio must not be baked in"
        self._fresh()

    def test_render_applies_the_current_ratio(self):
        self._fresh()
        with _CalFixture(ratio=1.0, n=0):
            bot._record_prompt_size([{"role": "system", "content": "x" * 40000}], 1)
        with _CalFixture(ratio=0.92, n=9):
            st = bot._prompt_audit_state()
            assert st["avg"] == pytest.approx(9200, rel=0.01)
            assert st["max"] == pytest.approx(9200, rel=0.01)
        self._fresh()

    def test_a_sample_taken_before_calibration_is_re_expressed(self):
        # The exact reported bug: the peak was recorded uncalibrated, so /audit kept
        # showing the pre-calibration number next to a live calibrated one.
        self._fresh()
        with _CalFixture(ratio=1.0, n=0):
            bot._record_prompt_size([{"role": "system", "content": "y" * 40000}], 1)
            raw_blocks = bot._prompt_audit_state()["max_blocks"]
        with _CalFixture(ratio=0.92, n=9):
            cal_blocks = bot._prompt_audit_state()["max_blocks"]
        assert cal_blocks[0][0] < raw_blocks[0][0]
        assert cal_blocks[0][0] == pytest.approx(raw_blocks[0][0] * 0.92, rel=0.01)
        self._fresh()

    def test_audit_block_and_preset_line_agree_for_the_same_text(self):
        # The user-visible symptom: preset-core.txt shown as 4165t in one line and
        # 3839t in another, in a single audit.
        self._fresh()
        layer = "VOICE RULES [BRACKETED]\n" * 500
        with _CalFixture(ratio=1.0, n=0):
            bot._record_prompt_size([{"role": "system", "content": layer}], 1)
        with _CalFixture(ratio=0.92, n=9):
            block_tokens = bot._prompt_audit_state()["max_blocks"][0][0]
            preset_tokens = bot._tokens(layer)
            assert abs(block_tokens - preset_tokens) <= 1, \
                "the same text must not report two different sizes in one audit"
        self._fresh()

    def test_trim_budget_still_uses_calibrated_tokens(self):
        # A budget is a real ceiling, so it should track real tokens, unlike the stats.
        import inspect
        assert "_msg_tokens(" in inspect.getsource(bot._trim_prompt_to_budget)

    def test_card_fields_stored_raw_and_rendered_calibrated(self):
        # Same class: filled once at card load (before anything is measured) and
        # rendered much later, so a calibrated value there freezes at ratio 1.0.
        import inspect
        src = inspect.getsource(bot.load_character)
        assert "_est_tokens(data.get(_f)" in src, "card fields must be stored raw"
        assert "_est_tokens(json.dumps(e))" in src, "lorebook must be stored raw"
        with _CalFixture(ratio=1.0, n=0):
            raw = bot.gather_audit_data()["card_fields"]
        with _CalFixture(ratio=0.92, n=9):
            cal = bot.gather_audit_data()["card_fields"]
        # Exact, not approximate: the fixture card's fields are only a few tokens, where
        # integer rounding dominates any relative tolerance.
        for k, v in raw.items():
            assert cal[k] == int(round(v * 0.92)), k

    def test_daily_token_sum_adds_real_units_in_both_branches(self):
        # tok_in holds provider counts; the estimated branch must contribute the best
        # estimate of the SAME unit, since this sum is rendered as-is and never re-scaled.
        import inspect
        src = inspect.getsource(bot._track_llm_usage)
        est_branch = src.split("else:")[-1]
        assert "_tokens(" in est_branch and "_est_tokens(" not in est_branch


class TestPresetPlaceholdersAreFilled:
    """v2026-07-26.4: preset layers were the ONE prose block fill() never touched, so
    every voice rule in the fleet's voiceprint addressed a literal {{char}}."""

    def test_injection_applies_fill(self):
        import inspect, re
        src = inspect.getsource(bot.assemble_messages)
        m = re.search(r"for _lname, _ltext in PRESET_LAYERS:\s*\n\s*messages\.append\(([^\n]*)",
                      src)
        assert m and "fill(" in m.group(1), \
            "preset layers must be substituted like every other prose block"

    def test_shipped_layers_actually_contain_placeholders(self):
        # Pins WHY the fix matters: if the layers ever stop using placeholders this test
        # should be revisited rather than silently protecting nothing.
        import pathlib
        repo = pathlib.Path(bot.__file__).parent
        found = {p.name: p.read_text(encoding="utf-8").count("{{")
                 for p in sorted(repo.glob("preset*.txt"))}
        assert found, "no preset files in the repo to check"
        assert any(v > 0 for v in found.values()), found

    def test_fill_substitutes_both_placeholders_in_layer_text(self):
        layer = ("You are {{char}} speaking to {{user}} in an ongoing exchange.\n"
                 "Preserve {{char}}'s voice.")
        out = bot.fill(layer, "Nora", "Brian")
        assert "{{char}}" not in out and "{{user}}" not in out
        assert "You are Nora speaking to Brian" in out
        assert "Preserve Nora's voice." in out
    AVAIL = ["preset-core.txt", "preset-rp.txt", "preset.txt"]

    def test_bare_stem_resolves(self):
        assert bot._normalize_preset_name("core", self.AVAIL) == "preset-core.txt"

    def test_full_filename_resolves(self):
        assert bot._normalize_preset_name("preset-rp.txt", self.AVAIL) == "preset-rp.txt"

    def test_shared_preset_resolves_by_stem(self):
        assert bot._normalize_preset_name("preset", self.AVAIL) == "preset.txt"

    def test_unknown_name_is_none_not_a_guess(self):
        # The whole point: a typo must NOT silently land on a plausible neighbour.
        assert bot._normalize_preset_name("cor", self.AVAIL) is None
        assert bot._normalize_preset_name("explicit", self.AVAIL) is None

    def test_blank_is_none(self):
        assert bot._normalize_preset_name("   ", self.AVAIL) is None


class TestPresetArgParsing:
    def test_comma_and_space_forms_agree(self):
        assert bot._parse_preset_names(["core,rp"]) == ["core", "rp"]
        assert bot._parse_preset_names(["core", "rp"]) == ["core", "rp"]
        assert bot._parse_preset_names(["core,", "rp"]) == ["core", "rp"]

    def test_order_preserved(self):
        assert bot._parse_preset_names(["rp,core"]) == ["rp", "core"]

    def test_deduplicated(self):
        # A layer listed twice would be injected twice and silently double its cost.
        assert bot._parse_preset_names(["core,core", "core"]) == ["core"]


class TestPresetSwap:
    def test_setting_layers_rebinds_both_globals(self):
        with _PresetFixture():
            layers, warn = bot._set_preset_layers(["preset-core.txt", "preset-rp.txt"])
            assert [n for n, _ in layers] == ["preset-core.txt", "preset-rp.txt"]
            assert bot.PRESET_LAYERS == layers
            assert bot.TEXTING_STYLE == "\n\n".join(t for _, t in layers)
            assert warn == []

    def test_available_files_are_discovered(self):
        with _PresetFixture():
            avail = bot._list_preset_files()
            assert {"preset-core.txt", "preset-rp.txt", "preset-explicit.txt"} <= set(avail)

    def test_resolvable_stack_passes_the_dry_run(self):
        with _PresetFixture():
            ok, _ = bot._preset_resolves(["preset-core.txt"])
            assert ok

    def test_unresolvable_stack_fails_the_dry_run(self):
        # The command uses this to refuse BEFORE mutating, so a bad stack never goes live.
        with _PresetFixture():
            ok, warn = bot._preset_resolves(["preset-nope.txt"])
            assert not ok
            assert any("preset-nope.txt" in w for w in warn)

    def test_dry_run_does_not_mutate_the_live_stack(self):
        with _PresetFixture():
            bot._set_preset_layers(["preset-core.txt"])
            before = bot.PRESET_LAYERS
            bot._preset_resolves(["preset-nope.txt"])
            assert bot.PRESET_LAYERS is before

    def test_token_estimate_sums_the_stack(self):
        with _PresetFixture():
            layers, _ = bot._set_preset_layers(["preset-core.txt", "preset-rp.txt"])
            assert bot._preset_stack_tokens(layers) == sum(
                bot._est_tokens(t) for _, t in layers)


class TestPresetOverridePersistence:
    def test_override_is_reapplied_on_startup(self):
        with _PresetFixture():
            bot.preset_override[:] = ["preset-core.txt", "preset-rp.txt"]
            bot.apply_overrides()
            assert [n for n, _ in bot.PRESET_LAYERS] == ["preset-core.txt", "preset-rp.txt"]

    def test_kill_switch_strands_the_override(self):
        # PRESET_COMMAND=0 must let a mangled voice be recovered from .env alone.
        with _PresetFixture():
            baseline = bot.PRESET_LAYERS
            bot.preset_override[:] = ["preset-core.txt"]
            orig = bot.PRESET_COMMAND
            bot.PRESET_COMMAND = False
            try:
                bot.apply_overrides()
                assert bot.PRESET_LAYERS is baseline
            finally:
                bot.PRESET_COMMAND = orig

    def test_vanished_override_reverts_to_env_not_the_stub(self):
        # Layers deleted since the override was saved: falling through to the ~250-token
        # built-in strips tuned voice rules and reads as a model regression.
        with _PresetFixture():
            bot._PRESET_ENV_NAMES[:] = ["preset-core.txt"]
            bot.preset_override[:] = ["preset-gone.txt"]
            warnings_before = len(bot._CONFIG_WARNINGS)
            try:
                bot.apply_overrides()
                assert [n for n, _ in bot.PRESET_LAYERS] == ["preset-core.txt"]
                assert bot.preset_override == []
                assert any("reverted to the .env preset stack"
                           in w for w in bot._CONFIG_WARNINGS[warnings_before:])
            finally:
                del bot._CONFIG_WARNINGS[warnings_before:]

    def test_override_is_serialized_into_state(self):
        import json
        with _PresetFixture():
            bot.preset_override[:] = ["preset-core.txt"]
            assert json.loads(bot._serialize_state())["preset_override"] == \
                ["preset-core.txt"]

    def test_audit_flags_an_active_override(self):
        with _PresetFixture():
            bot.preset_override[:] = ["preset-core.txt"]
            assert bot.gather_audit_data()["preset_override"] == ["preset-core.txt"]


class TestPresetCommandInvariants:
    """Rules from bot-code-invariants and past incidents this command could break."""

    def test_command_is_admin_gated(self):
        import inspect
        src = inspect.getsource(bot.preset_cmd)
        assert "_is_admin(update.effective_user.id)" in src, \
            "swapping the voiceprint for every chat is an operational command"

    def test_command_is_plain_text(self):
        # v2026-07-25.7/.13: layer filenames and resolver warnings through Markdown
        # would make Telegram reject the message and the command reply with silence.
        import inspect
        assert "parse_mode" not in inspect.getsource(bot.preset_cmd)

    def test_command_refuses_an_empty_stack(self):
        import inspect
        assert "would leave no preset layers" in inspect.getsource(bot.preset_cmd)

    def test_menu_entry_mirrors_the_kill_switch(self):
        off = {c.command for c in bot._build_command_menu(False, False, False, False)}
        assert "preset" not in off
        on = {c.command for c in bot._build_command_menu(False, False, False, True)}
        assert "preset" in on

    def test_no_new_llm_call(self):
        import inspect
        src = inspect.getsource(bot.preset_cmd)
        assert "_do_request" not in src and "chat/completions" not in src


class TestCardBlockLabelling:
    """messages[0] is the MERGED card block. Labelling it by its first line credited an
    84-token section with 4,715 tokens and misdirected a real investigation."""

    def test_card_block_gets_a_fixed_label(self):
        msgs = [{"role": "system", "content": "[ATTRACTION RULE]\n" + "x" * 40000}]
        assert bot._prompt_top_blocks(msgs)[0][1] == "(card: system_prompt+description+…)"

    def test_later_blocks_still_use_their_heading(self):
        msgs = [{"role": "system", "content": "card"},
                {"role": "system", "content": "# Relevant memories\n" + "x" * 4000}]
        assert bot._prompt_top_blocks(msgs)[0][1] == "# Relevant memories"

    def test_card_label_does_not_leak_card_content(self):
        msgs = [{"role": "system", "content": "[KINK MECHANICS]\nsecret"}]
        assert "KINK" not in bot._prompt_top_blocks(msgs)[0][1]


class TestCardFieldTokens:
    def test_breakdown_is_recorded(self):
        assert isinstance(bot._card_field_tokens, dict)
        assert bot._card_field_tokens, "load_character must populate the breakdown"

    def test_fixture_fields_present(self):
        # The fixture card sets system_prompt and description.
        assert "system_prompt" in bot._card_field_tokens
        assert "description" in bot._card_field_tokens

    def test_empty_fields_are_omitted_not_zero(self):
        assert 0 not in [v for k, v in bot._card_field_tokens.items()
                         if k != "character_book"]

    def test_lorebook_tracked_separately(self):
        # Conditional cost must not be mixed into the always-on total.
        assert "character_book" in bot._card_field_tokens

    def test_reported_in_audit(self):
        d = bot.gather_audit_data()
        assert "card_fields" in d
        assert d["card_fields"]["system_prompt"] > 0


# ── Preset layer resolution + fallback ladder (v2026-07-25.6) ────────────────
# Ladder: named layers -> shared preset.txt -> built-in. The middle rung exists because
# updating .env before the layer files reach an instance would otherwise drop the bot to
# a ~250-token stub, which presents as a model regression. See CHANGELOG v2026-07-25.6.

class TestResolvePresetLayers:
    DEFAULT = "BUILT-IN DEFAULT"

    @staticmethod
    def _reader(files):
        def read(name):
            if name in files:
                return files[name]
            return ""
        return read

    def _resolve(self, names, files):
        warn = []
        out = bot._resolve_preset_layers(names, self._reader(files), self.DEFAULT, warn)
        return out, warn

    def test_single_layer_resolves(self):
        out, warn = self._resolve(["preset.txt"], {"preset.txt": "SHARED"})
        assert out == [("preset.txt", "SHARED")]
        assert warn == []

    def test_layers_keep_declared_order(self):
        files = {"a.txt": "A", "b.txt": "B", "c.txt": "C"}
        out, _ = self._resolve(["a.txt", "b.txt", "c.txt"], files)
        assert [n for n, _ in out] == ["a.txt", "b.txt", "c.txt"]

    def test_partial_resolution_keeps_what_exists_and_warns(self):
        out, warn = self._resolve(["a.txt", "gone.txt"], {"a.txt": "A"})
        assert out == [("a.txt", "A")]
        assert any("gone.txt" in w for w in warn)

    def test_missing_default_preset_does_not_warn(self):
        # The documented "no preset.txt at all" case must stay quiet.
        out, warn = self._resolve(["preset.txt"], {})
        assert out == [("<built-in>", self.DEFAULT)]
        assert warn == []

    def test_all_named_layers_missing_falls_back_to_shared(self):
        out, warn = self._resolve(["core.txt", "rp.txt"], {"preset.txt": "SHARED"})
        assert out == [("preset.txt (fallback)", "SHARED")]
        assert any("falling back to the shared" in w for w in warn)
        # And each missing layer is still named, so the cause is diagnosable.
        assert any("core.txt" in w for w in warn)

    def test_falls_through_to_builtin_when_nothing_exists(self):
        out, warn = self._resolve(["core.txt"], {})
        assert out == [("<built-in>", self.DEFAULT)]
        assert any("core.txt" in w for w in warn)

    def test_unreadable_layer_is_reported_not_fatal(self):
        def read(name):
            if name == "bad.txt":
                raise OSError("permission denied")
            return "OK" if name == "good.txt" else ""
        warn = []
        out = bot._resolve_preset_layers(["bad.txt", "good.txt"], read, self.DEFAULT, warn)
        assert out == [("good.txt", "OK")]
        assert any("could not be read" in w for w in warn)

    def test_reader_exception_does_not_leak_the_message(self):
        def read(name):
            raise OSError("/secret/path/leaked")
        warn = []
        bot._resolve_preset_layers(["x.txt"], read, self.DEFAULT, warn)
        assert not any("leaked" in w for w in warn)

    def test_empty_layer_file_treated_as_missing(self):
        out, warn = self._resolve(["core.txt"], {"core.txt": "", "preset.txt": "SHARED"})
        assert out == [("preset.txt (fallback)", "SHARED")]

    def test_fallback_never_duplicates_an_already_loaded_layer(self):
        # preset.txt listed AND resolvable: it's a normal layer, not the fallback rung.
        out, _ = self._resolve(["preset.txt", "extra.txt"],
                               {"preset.txt": "SHARED", "extra.txt": "X"})
        assert [n for n, _ in out] == ["preset.txt", "extra.txt"]
        assert not any("fallback" in n for n, _ in out)

    def test_always_returns_at_least_one_layer(self):
        for names in ([], ["nope.txt"], ["preset.txt"]):
            out, _ = self._resolve(names, {})
            assert len(out) >= 1
            assert all(t for _, t in out)


# ── /audit must be sendable whatever it finds (v2026-07-25.7) ────────────────
# v2026-07-25.5/.6 added card field names (system_prompt, mes_example) and prompt block
# headings ([VOICEPRINT PRESET …]) to a parse_mode="Markdown" message. A stray '_' or an
# unmatched '[' makes Telegram reject the whole message ("can't parse entities"), so the
# command whose job is diagnosing the bot became the thing that silently failed.

class TestAuditIsPlainText:
    def _src(self):
        """audit_cmd's source with comment lines removed — the comments deliberately
        mention parse_mode="Markdown" to explain why it must not be used."""
        import inspect
        return "\n".join(ln for ln in inspect.getsource(bot.audit_cmd).splitlines()
                         if not ln.lstrip().startswith("#"))

    def test_audit_does_not_use_parse_mode(self):
        assert "parse_mode" not in self._src(), (
            "/audit interpolates arbitrary diagnostic text (card fields, prompt headings, "
            "config warnings naming env vars) — any parse_mode makes it un-sendable "
            "depending on what it found")

    def test_header_has_no_markdown_emphasis(self):
        assert "*Self-Audit*" not in self._src()

    def test_audit_output_survives_markdown_hostile_content(self):
        # The real payload that broke it: underscores and unmatched brackets.
        bot._prompt_stats.update({"n": 1, "sum": 9000, "max": 9000, "max_ts": time.time(),
                                  "max_chat": 1, "buckets": {"8-12k": 1},
                                  "max_blocks": [(8503, "[VOICEPRINT PRESET — SINGLE SLOT]"),
                                                 (2231, "(card: system_prompt+description+…)")]})
        d = bot.gather_audit_data()
        ps = d["prompt_stats"]
        rendered = "\n".join(f"  ~{t}t  {h}" for t, h in ps["max_blocks"])
        # Exactly the conditions Telegram rejects — proof the content is hostile, which is
        # why the command must not ask Telegram to parse it.
        assert rendered.count("[") != rendered.count("]") or "_" in rendered

    def test_card_field_names_contain_underscores(self):
        # Guards the premise: if field names ever stopped containing '_', a future reader
        # might think the plain-text requirement was cosmetic.
        assert any("_" in k for k in bot._card_field_tokens)


# ── BadRequest is a client-side defect, not network noise (v2026-07-25.8) ─────
# In PTB, BadRequest SUBCLASSES NetworkError, so on_error's isinstance(err,
# (NetworkError, TimedOut)) absorbed every 400 from the Bot API — malformed markup,
# message-too-long, bad parameters — as "[net] transient" under the `network` counter.
# That is how the v2026-07-25.5 /audit markup bug presented as "network: 3".

class TestBadRequestNotNetwork:
    class _Ctx:
        def __init__(self, error):
            self.error = error

    @staticmethod
    def _counts(cat):
        return len(bot._error_counts.get(cat, []))

    def test_ptb_really_does_subclass_networkerror(self):
        # The premise. If PTB ever fixes this, the ordering guard becomes redundant
        # rather than wrong — but we want to know.
        from telegram.error import BadRequest, NetworkError
        assert issubclass(BadRequest, NetworkError)

    def test_bad_request_counted_separately(self):
        from telegram.error import BadRequest
        before_bad, before_net = self._counts("bad_request"), self._counts("network")
        asyncio.run(bot.on_error(None, self._Ctx(
            BadRequest("Can't parse entities: can't find end of the entity at byte 484"))))
        assert self._counts("bad_request") == before_bad + 1
        assert self._counts("network") == before_net, "must not also count as network"

    def test_real_network_error_still_counted_as_network(self):
        from telegram.error import NetworkError
        before_bad, before_net = self._counts("bad_request"), self._counts("network")
        asyncio.run(bot.on_error(None, self._Ctx(NetworkError("httpx.ReadError: "))))
        assert self._counts("network") == before_net + 1
        assert self._counts("bad_request") == before_bad

    def test_timeout_still_counted_as_network(self):
        from telegram.error import TimedOut
        before = self._counts("network")
        asyncio.run(bot.on_error(None, self._Ctx(TimedOut())))
        assert self._counts("network") == before + 1

    def test_ordering_is_explicit_in_source(self):
        # A future reader reordering these checks silently reintroduces the bug.
        import inspect
        src = inspect.getsource(bot.on_error)
        assert src.index("isinstance(err, BadRequest)") < \
               src.index("isinstance(err, (NetworkError, TimedOut))")

    def test_bad_request_surfaces_at_error_level(self):
        import inspect
        src = inspect.getsource(bot.on_error)
        i = src.index("isinstance(err, BadRequest)")
        j = src.index("isinstance(err, (NetworkError, TimedOut))")
        assert "log.error" in src[i:j], "a client-side defect should not log as a warning"


# ── Garmin partial-pull diagnosability (v2026-07-25.9) ───────────────────────
# A watch in battery saver returned steps and nothing else; the only way to learn WHICH
# metrics were absent was to shell in and read bot.log, because the per-field failures
# used print() (bot.log only, invisible to /errors). See CHANGELOG v2026-07-25.9.

class TestGarminFields:
    ALL = ["sleep", "resting HR", "steps", "body battery", "stress", "last workout"]

    def test_all_six_metrics_always_reported(self):
        fields = bot._garmin_fields({}, {}, {})
        assert [label for label, _ in fields] == self.ALL

    def test_empty_payloads_mean_everything_missing(self):
        assert bot._garmin_missing({}, {}, {}) == self.ALL

    def test_the_battery_saver_case(self):
        # Exactly what happened: accelerometer steps survive, every HR-derived metric
        # is gone because the optical sensor was off.
        missing = bot._garmin_missing({}, {"totalSteps": 4210}, {})
        assert "steps" not in missing
        assert set(missing) == {"sleep", "resting HR", "body battery",
                                "stress", "last workout"}

    def test_full_payload_means_nothing_missing(self):
        missing = bot._garmin_missing(
            {"sleepTimeSeconds": 6 * 3600},
            {"restingHeartRate": 54, "totalSteps": 3000,
             "bodyBatteryMostRecentValue": 60, "averageStressLevel": 30},
            {"activityName": "ride"})
        assert missing == []

    def test_fields_and_bits_agree(self):
        # The whole point of the shared source: present-phrases must equal _garmin_bits.
        args = ({"sleepTimeSeconds": 3600}, {"totalSteps": 10}, {})
        phrases = [p for _, p in bot._garmin_fields(*args) if p]
        assert phrases == bot._garmin_bits(*args)

    def test_zero_steps_counts_as_present(self):
        assert "steps" not in bot._garmin_missing({}, {"totalSteps": 0}, {})

    def test_unmeasurable_stress_counts_as_missing(self):
        assert "stress" in bot._garmin_missing({}, {"averageStressLevel": -1}, {})


class TestGarminGapNote:
    def test_silent_when_nothing_missing(self):
        assert bot._garmin_gap_note([]) == ""

    def test_names_the_missing_metrics(self):
        note = bot._garmin_gap_note(["sleep", "body battery"])
        assert "sleep" in note and "body battery" in note

    def test_explains_the_likely_cause(self):
        note = bot._garmin_gap_note(["sleep"]).lower()
        assert "battery saver" in note
        assert "sync" in note

    def test_is_plain_text(self):
        # /health and /healthnow reply without parse_mode; keep it that way.
        note = bot._garmin_gap_note(["resting HR"])
        assert "*" not in note and "_" not in note


class TestGarminFailuresReachErrors:
    def test_fetch_logs_via_log_not_print(self):
        import inspect
        src = inspect.getsource(bot._fetch_garmin)
        assert "print(" not in src, (
            "print() reaches bot.log only — /errors cannot show it, which is the gap "
            "this release closes")
        assert src.count("log.warning") >= 4

    def test_fetch_never_logs_the_exception_itself(self):
        # Garmin exceptions can carry the request URL (v2026-07-20.2 key-leak class).
        import inspect
        src = inspect.getsource(bot._fetch_garmin)
        assert '", e)' not in src and '%s", e' not in src
        assert "type(e).__name__" in src

    def test_fetch_returns_text_and_missing(self):
        import inspect
        assert inspect.getsource(bot._fetch_garmin).rstrip().endswith("return text, missing")

    def test_snapshot_loader_tolerates_pre_09_files(self):
        # Old .garmin_snapshot files have no "missing" key.
        import json as _json
        bot._garmin.update({"loaded": False, "text": "", "ts": 0.0, "missing": []})
        bot.GARMIN_FILE.write_text(_json.dumps({"text": "steps", "ts": time.time()}),
                                   encoding="utf-8")
        try:
            bot._garmin_snapshot()
            assert bot._garmin["missing"] == []
        finally:
            bot.GARMIN_FILE.unlink(missing_ok=True)
            bot._garmin.update({"loaded": False, "text": "", "ts": 0.0, "missing": []})


# ── Restart-storm DM states the correct triage rule (v2026-07-25.10) ─────────
# The wrong rule ("no graceful-stop line = SIGKILL") survived in FOUR places after the
# first correction pass, including this DM — the message the owner reads at the exact
# moment they are debugging a restart storm. See CHANGELOG v2026-07-25.10.

class TestRestartStormAdviceIsCorrect:
    def _src(self):
        import inspect
        return inspect.getsource(bot._self_audit)

    # REWRITTEN v2026-07-26.7. These previously pinned phone-era triage (bot.log's
    # "[run-bot] ... exited (code N)" line, 137/143, the Android phantom killer). The
    # fleet has been 100% systemd since 2026-07-26: bot.log is 0 bytes, there is no
    # battery manager, and that advice sent the operator to a file that no longer
    # exists. The class's purpose is unchanged — the DM must give triage that actually
    # works on the platform the bots run on.

    def test_dm_points_at_systemd_triage(self):
        src = self._src()
        assert "systemctl status" in src
        assert "journalctl" in src

    def test_dm_identifies_sigkill_and_oom(self):
        src = self._src()
        assert "status=9" in src
        assert "oom" in src.lower()

    def test_dm_does_not_send_operator_to_phone_era_artifacts(self):
        src = self._src()
        for stale in ("run-bot", "phantom", "battery manager", "bot.log"):
            assert stale not in src, f"restart-storm advice still references {stale!r}"

    def test_dm_does_not_claim_missing_line_means_sigkill(self):
        src = self._src()
        assert "no line = SIGKILL" not in src

    def test_graceful_line_asymmetry_documented_where_the_logic_lives(self):
        # The caveat moved out of the operator-facing DM (the count now excludes
        # deliberate restarts, so the operator doesn't need it) into the docstring of
        # the function that actually reasons about the line.
        import inspect
        doc = inspect.getsource(bot._tally_unexpected_restarts)
        assert "absence" in doc.lower()


# ── Concurrent /update corrupts the shared code dir (v2026-07-25.11) ─────────
# Every instance on a host shares the code dir: ~/telegram-bot for the four phone bots,
# /opt/telegram-bots for cass+jules. bot.py.new / bot.py.bak / bot.py are therefore
# shared, unsynchronised paths. Observed on the VPS 2026-07-25.

class TestSelfUpdateLock:
    def _lock_path(self):
        from pathlib import Path as _P
        return _P(bot.__file__).resolve().parent / ".update.lock"

    def test_lock_blocks_a_concurrent_update(self):
        # Hold the lock the way a second instance would, then confirm perform_self_update
        # refuses BEFORE doing any network work — no download, no temp file written.
        import fcntl
        lp = self._lock_path()
        holder = open(lp, "w")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = bot.perform_self_update()
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()
        assert result["ok"] is False
        assert result["reason"] == "update_in_progress"

    def test_refusal_names_the_correct_procedure(self):
        import fcntl
        lp = self._lock_path()
        holder = open(lp, "w")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            detail = bot.perform_self_update()["detail"]
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()
        assert "ONE instance" in detail and "/restart" in detail

    def test_lock_is_released_for_the_next_caller(self):
        # Two sequential refusals must both work; a leaked fd would make the second hang
        # or wrongly succeed.
        import fcntl
        lp = self._lock_path()
        for _ in range(2):
            holder = open(lp, "w")
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                assert bot.perform_self_update()["reason"] == "update_in_progress"
            finally:
                fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
                holder.close()

    def test_no_temp_file_written_when_refused(self):
        # The bug was one instance deleting another's bot.py.new; a refused update must
        # not touch it at all.
        import fcntl
        from pathlib import Path as _P
        tmp = _P(bot.__file__).resolve().parent / "bot.py.new"
        existed = tmp.exists()
        lp = self._lock_path()
        holder = open(lp, "w")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            bot.perform_self_update()
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()
        assert tmp.exists() == existed

    def test_body_is_separated_from_the_lock(self):
        import inspect
        assert "flock" in inspect.getsource(bot.perform_self_update)
        assert "flock" not in inspect.getsource(bot._perform_self_update_locked)


class TestUpdateCmdNeverRepliesSilently:
    def test_every_failure_reason_gets_a_reply(self):
        # An unhandled reason used to fall through to a bare `return`, which looks
        # identical to the bot being dead.
        import inspect
        src = inspect.getsource(bot.update_cmd)
        assert "update_in_progress" in src
        assert "else:" in src
        assert "Update did not run" in src


# ── Group-chat co-location warning (v2026-07-25.12) ─────────────────────────
# GROUP_CHAT_DESIGN.md §3 assumes every peer shares one filesystem. Jules moved to the
# VPS 2026-07-19 while priya stayed on the phone, so the pilot pair no longer does.

class TestGroupColocationWarning:
    def test_warning_is_gated_on_group_mode_and_peers(self):
        import inspect, re
        src = inspect.getsource(bot)
        m = re.search(r"if GROUP_MODE and GROUP_PEERS:\n(.*?)\n\n", src, re.S)
        assert m, "co-location warning block missing"
        body = m.group(1)
        assert "_CONFIG_WARNINGS.append" in body

    def test_warning_names_the_resolved_ledger_dir(self):
        # The owner has to COMPARE the path across hosts, so it must be printed.
        import inspect, re
        src = inspect.getsource(bot)
        m = re.search(r"if GROUP_MODE and GROUP_PEERS:\n(.*?)\n\n", src, re.S)
        assert "{GROUP_LEDGER_DIR}" in m.group(1)

    def test_fixture_is_group_off_so_no_warning(self):
        assert bot.GROUP_MODE is False
        assert not any("GROUP_MODE on" in w for w in bot._CONFIG_WARNINGS)

    def test_ledger_dir_defaults_to_the_shared_code_dir(self):
        # The default being shared is exactly why co-location matters.
        from pathlib import Path as _P
        assert bot.GROUP_LEDGER_DIR == _P(bot.__file__).resolve().parent


# ── No command renders arbitrary content through Markdown (v2026-07-25.13) ───
# Generalises the v2026-07-25.7 /audit outage: Telegram rejects the WHOLE message on a
# stray '_' or unmatched '[', and the command then replies with silence.

class TestNoUnescapedMarkdownInterpolation:
    # Values that are provably metachar-free: ints, fixed day names, HH:MM strings.
    ALLOWED = {"quietwin_cmd", "fleet_cmd"}

    @staticmethod
    def _offenders():
        import re, inspect, pathlib
        src = pathlib.Path(inspect.getfile(bot)).read_text().splitlines()
        out = []
        for i, line in enumerate(src, 1):
            if 'parse_mode="Markdown"' not in line or line.strip().startswith("#"):
                continue
            stmt = " ".join(x.strip() for x in src[max(0, i - 7):i]
                            if not x.strip().startswith("#"))
            risky = [m.group(1) for m in re.finditer(r'\{([a-zA-Z_][\w\[\]\'\".]*)\}', stmt)
                     if not (stmt[max(0, m.start() - 1):m.start()] == "`"
                             and stmt[m.end():m.end() + 1] == "`")]
            if not risky:
                continue
            fn = ""
            for j in range(i - 1, 0, -1):
                if src[j - 1].startswith(("async def ", "def ")):
                    fn = src[j - 1].split("(")[0].split()[-1]
                    break
            out.append((fn, i, sorted(set(risky))))
        return out

    def test_no_new_unescaped_markdown_interpolation(self):
        bad = [o for o in self._offenders() if o[0] not in self.ALLOWED]
        assert not bad, (
            "these send arbitrary values through Markdown; a '_' or '[' in the data "
            f"makes Telegram reject the message and the command replies with silence: {bad}")

    def test_the_allowlist_is_still_justified(self):
        # If either stops interpolating only provably-safe values, the allowlist is stale.
        names = {o[0] for o in self._offenders()}
        assert names <= self.ALLOWED

    def test_content_rendering_commands_are_plain_text(self):
        import inspect
        for fn in (bot.card_cmd, bot.notes_cmd, bot.status_cmd, bot.schedule_cmd,
                   bot.setcard_cmd, bot.vibe_cmd, bot.energy_cmd):
            assert "parse_mode" not in inspect.getsource(fn), fn.__name__


# ── BOT_TIMEZONE actually sets the clock (v2026-07-25.14) ───────────────────
# It was documented as THE timezone setting but only read by --check-config, so every
# instance silently ran on the America/Los_Angeles default of TIMEZONE.

class TestBotTimezoneTakesEffect:
    def test_fixture_bot_timezone_is_honoured(self):
        # conftest sets BOT_TIMEZONE=America/New_York. Before the fix this asserted
        # nothing useful because TZ came from TIMEZONE and defaulted to Los_Angeles.
        assert bot.TIMEZONE == "America/New_York"
        assert str(bot.TZ) == "America/New_York"

    def test_bot_timezone_is_read_at_module_scope(self):
        import inspect, re
        src = inspect.getsource(bot)
        m = re.search(r'^TIMEZONE = .*$', src, re.M)
        assert m and "BOT_TIMEZONE" in m.group(0), \
            "the clock must come from BOT_TIMEZONE, not just the preflight check"

    def test_legacy_timezone_still_supported(self):
        import inspect, re
        src = inspect.getsource(bot)
        m = re.search(r'^TIMEZONE = .*$', src, re.M)
        assert '"TIMEZONE"' in m.group(0), "existing .envs using TIMEZONE must keep working"

    def test_conflict_between_the_two_warns(self):
        import inspect
        src = inspect.getsource(bot)
        assert "both BOT_TIMEZONE and TIMEZONE are set and differ" in src


class TestDiagnosticModesSkipPidLock:
    """v2026-07-28.1. `--check-config` and `--claim-test` are dispatched in main(),
    which runs after the module-level `_acquire_pid_lock()`, so they used to be
    unrunnable while the instance's bot was up — precisely when an operator needs a
    diagnostic. The lock guards against a duplicate *poller*; a non-polling mode
    skipping it is not a weakening."""

    def test_diagnostic_mode_covers_both_flags(self):
        import inspect
        src = inspect.getsource(bot)
        # The constant must be derived from sys.argv and name both flags, so adding a
        # third diagnostic flag without listing it here fails loudly rather than
        # silently reintroducing the lock collision.
        assert 'DIAGNOSTIC_MODE = any(f in sys.argv for f in ("--check-config", "--claim-test"))' in src

    def test_diagnostic_mode_declared_before_the_lock_and_load_state(self):
        """Ordering is the whole fix: the constant is consulted by module-level code.

        NOT independently break-testable, and that is fine — moving the declaration
        below `_acquire_pid_lock()` makes bot.py raise `NameError` at import, so the
        real enforcement is the import itself (covered by the `bot-imports` eval), and
        this assertion is a cheap, legible restatement of it. Verified 2026-07-28: the
        injection errors at collection with `NameError: name 'DIAGNOSTIC_MODE' is not
        defined` rather than failing this test. Recorded per C3 — a check nobody has
        seen fail should say why.
        """
        import inspect
        src = inspect.getsource(bot)
        decl = src.index("DIAGNOSTIC_MODE = any(")
        assert decl < src.index("def _acquire_pid_lock")
        assert decl < src.index("def load_state")

    def test_pid_lock_returns_early_in_diagnostic_mode(self):
        import inspect
        src = inspect.getsource(bot._acquire_pid_lock)
        head = src[:src.index("if _PID_FILE.exists()")]
        assert "DIAGNOSTIC_MODE" in head and "return" in head

    def test_load_state_never_renames_live_state_in_diagnostic_mode(self):
        """The one destructive import-time path: a corrupt state file is renamed to
        .corrupted. A diagnostic now skips the PID lock, so it can run beside the live
        bot — it must not move that bot's state file out from under it."""
        import inspect
        src = inspect.getsource(bot.load_state)
        assert "DIAGNOSTIC_MODE" in src, "load_state has no diagnostic-mode guard at all"
        assert src.index("DIAGNOSTIC_MODE") < src.index("STATE_FILE.rename(backup)"), \
            "the diagnostic guard must precede the destructive rename"


class TestDuplicateInstanceAdviceIsSafe:
    """The old message said `kill <pid>` / `rm <lockfile>`. Under systemd both are
    wrong: Restart=always undoes the kill, and removing the lock admits a second
    poller — the telegram.error.Conflict class that cost hours in the 2026-07
    migrations. Pinned so the dangerous wording cannot come back."""

    def _src(self):
        import inspect
        return inspect.getsource(bot._acquire_pid_lock)

    def test_advises_systemctl_stop(self):
        assert "systemctl stop bot@" in self._src()

    def test_does_not_advise_killing_the_pid(self):
        src = self._src()
        assert "Kill it first" not in src
        assert "kill {existing_pid}" not in src

    def test_does_not_advise_removing_the_lock(self):
        src = self._src()
        assert "force-remove the lock" not in src
        assert "rm {_PID_FILE}" not in src

    def test_names_the_conflict_risk_and_the_diagnostic_escape_hatch(self):
        src = self._src()
        assert "Conflict" in src
        assert "--claim-test" in src


class TestIncoherentGroupConfigWarns:
    """v2026-07-28.2. A group instance that cannot participate is SILENT by design —
    group_guard drops the traffic at handler group -1 with no reply and nothing in
    errors.log, because silence is correct fail-closed behavior for a non-participant.
    That makes 'not configured' indistinguishable from 'broken' by observation:
    diagnosing priya's missing GROUP_MODE took six rounds on 2026-07-28 with her
    allowlist and peers already set. These warnings put the incoherence in /audit."""

    W = staticmethod(lambda *a: bot._group_config_warnings(*a))

    # --- the two incoherent states warn ---

    def test_allowlist_set_but_mode_off(self):
        out = self.W(False, {-5116757843}, [])
        assert len(out) == 1
        assert "GROUP_ALLOWED_CHATS set but GROUP_MODE is off" in out[0]

    def test_peers_set_but_mode_off(self):
        out = self.W(False, set(), ["Jules"])
        assert len(out) == 1
        assert "GROUP_PEERS set but GROUP_MODE is off" in out[0]

    def test_priyas_actual_broken_config(self):
        """The exact state that caused the incident: both set, GROUP_MODE absent."""
        out = self.W(False, {-5116757843}, ["Jules"])
        assert len(out) == 1
        assert "GROUP_ALLOWED_CHATS, GROUP_PEERS set but GROUP_MODE is off" in out[0]
        assert "Set GROUP_MODE=1 and restart" in out[0]

    def test_mode_on_but_allowlist_empty(self):
        """Same class inverted: the allowlist fails closed (GROUP_CHAT_DESIGN.md §6)."""
        out = self.W(True, set(), ["Jules"])
        assert len(out) == 1
        assert "GROUP_ALLOWED_CHATS is empty" in out[0]

    # --- the coherent states stay quiet ---

    def test_participating_config_is_silent(self):
        assert self.W(True, {-5116757843}, ["Jules"]) == []

    def test_unconfigured_instance_is_silent(self):
        """The fleet's four non-group bots must not warn on every /audit."""
        assert self.W(False, set(), []) == []

    def test_participating_without_peers_is_silent(self):
        """One bot + human in a group is a valid configuration, not an error."""
        assert self.W(True, {-5116757843}, []) == []


class TestUpdateReasonsAllHaveBranches:
    """v2026-07-28.3. Twice now a new `reason` from the self-update path has shipped
    without a matching branch in update_cmd: v2026-07-25.7 (/audit outage) and
    v2026-07-25.11 (`update_in_progress`, which would have replied with silence). A
    catch-all exists now, so the failure mode degraded from silence to an unhelpful
    "Update did not run (x)" — still wrong for a reason with a real remedy. This pins
    the CLASS: every reason the update path can return must be handled explicitly."""

    def _reasons_returned(self):
        import inspect, re
        src = inspect.getsource(bot._perform_self_update_locked)
        return set(re.findall(r'"reason":\s*"([a-z_]+)"', src))

    def _reasons_handled(self):
        import inspect, re
        src = inspect.getsource(bot.update_cmd)
        return set(re.findall(r'reason == "([a-z_]+)"', src))

    def test_every_returned_reason_has_an_explicit_branch(self):
        returned, handled = self._reasons_returned(), self._reasons_handled()
        assert returned, "no reasons parsed — the regex or the function shape changed"
        missing = returned - handled
        assert not missing, (
            f"update_cmd has no explicit branch for {sorted(missing)}; the catch-all "
            f"would reply 'Update did not run', which names no remedy")

    def test_repo_not_readable_is_one_of_them(self):
        """The private-repo case specifically — raw URLs cannot authenticate, so this
        reason is permanent, not transient, and its message must name vps-sync.sh."""
        import inspect
        assert "repo_not_readable" in self._reasons_returned()
        assert "vps-sync.sh" in inspect.getsource(bot.update_cmd)


class TestDirectiveLeakGuard:
    """v2026-07-29.1 — jules sent a selfie captioned with her own planning, rendered in
    the `[selfie: ...]` bracket syntax the reply prompt had just taught her. extract_tags
    strips react/selfie/meme/search BY NAME, so every other bracketed line reached the
    user verbatim."""

    LEAK = (
        'Lasers have never looked so aggressively monochromatic.\n'
        '[ATTRACTION RULE]: Present-tense. Maintain the patronizing "bud."\n'
        '[PACE CONTROL]: Mix it with a complaint. Business of the rink.\n'
        '[JULES TONE]: Concise, annoyed.\n'
        'Caught mid-start.'
    )

    def test_strips_the_leaked_directive_lines(self):
        clean, dropped = bot._strip_directive_lines(self.LEAK)
        assert len(dropped) == 3
        for tag in ("ATTRACTION RULE", "PACE CONTROL", "JULES TONE"):
            assert tag not in clean

    def test_keeps_the_actual_reply(self):
        clean, _ = bot._strip_directive_lines(self.LEAK)
        assert "Lasers have never looked so aggressively monochromatic." in clean
        assert "Caught mid-start." in clean

    def test_invented_labels_are_caught_not_just_known_ones(self):
        """The leak included labels absent from her card — a fix keyed to real header
        names would have missed [JULES TONE] and [NO LANGUAGES] entirely."""
        clean, dropped = bot._strip_directive_lines("[NO LANGUAGES]: keep it English\nhi")
        assert dropped and clean == "hi"

    def test_lowercase_in_character_aside_survives(self):
        """[laughs] is something a character might actually write."""
        text = "*she shrugs* [laughs] whatever, bud"
        clean, dropped = bot._strip_directive_lines(text)
        assert clean == text and dropped == []

    def test_bracket_mid_line_survives(self):
        """Only whole lines that are nothing but a label are prompt syntax."""
        text = "the sign said [OPEN] and she walked in"
        clean, dropped = bot._strip_directive_lines(text)
        assert clean == text and dropped == []

    def test_ordinary_reply_is_untouched(self):
        text = "*She leans against the doorway.*\n\"Took you long enough.\""
        clean, dropped = bot._strip_directive_lines(text)
        assert clean == text and dropped == []

    def test_kill_switch_disables_it(self, monkeypatch):
        monkeypatch.setattr(bot, "DIRECTIVE_LEAK_GUARD", False)
        clean, dropped = bot._strip_directive_lines(self.LEAK)
        assert clean == self.LEAK and dropped == []

    def test_guard_lives_at_the_generate_reply_choke_point(self):
        """v2026-07-29.2. It was first placed in extract_tags, which the selfie/meme
        caption paths never call — their text goes straight to send_photo(caption=...).
        generate_reply is the real boundary: every user-facing path reaches the model
        through it, while analysis/extraction call call_nanogpt directly."""
        import inspect
        assert "_strip_directive_lines" in inspect.getsource(bot.generate_reply)
        assert "_strip_directive_lines" not in inspect.getsource(bot.extract_tags)

    def test_analysis_paths_are_not_swept(self):
        """call_nanogpt carries the post-reply analysis JSON. A line-eating regex must
        never run there."""
        import inspect
        assert "_strip_directive_lines" not in inspect.getsource(bot.call_nanogpt)

    def test_uppercase_known_tag_survives_for_extract_tags(self):
        """The guard must not eat the feature it protects. This holds structurally, not
        by an exemption list: a tag is `[selfie: value]` with the colon INSIDE the
        brackets, and the directive pattern requires `]` right after the label. An
        exemption list was written, break-tested, found inert, and deleted."""
        text = "[SELFIE: her at the rink]"
        clean, dropped = bot._strip_directive_lines(text)
        assert dropped == [] and clean == text
        _c, _r, hint, _m = bot.extract_tags(text)
        assert hint == "her at the rink"

    def test_tag_survives_but_directive_neighbour_still_stripped(self):
        clean, dropped = bot._strip_directive_lines(
            "[SELFIE: at the rink]\n[PACE CONTROL]: slow it down\nhey")
        assert len(dropped) == 1
        assert "[SELFIE: at the rink]" in clean
        assert "PACE CONTROL" not in clean and "hey" in clean


class TestCaptionModelSlot:
    """v2026-07-29.3 — selfie and meme captions are the character talking, so they ride
    the chat model, not the background summariser slot."""

    def test_caption_model_defaults_to_the_chat_model(self):
        assert bot.CAPTION_MODEL == bot.NANOGPT_MODEL

    def test_caption_helpers_no_longer_use_the_summary_slot(self):
        """The bug: an instance pointing SUMMARY_MODEL at a small fast model for cheap
        summaries had that model writing the character's dialogue."""
        import inspect
        for fn in (bot._selfie_caption, bot._generate_meme_captions):
            src = inspect.getsource(fn)
            assert "SUMMARY_MODEL" not in src, fn.__name__
            assert "CAPTION_MODEL" in src, fn.__name__

    def test_caption_is_a_selectable_model_role(self):
        """/setmodel must be able to reach it, like every other slot."""
        assert bot.MODEL_ROLES.get("caption") == "CAPTION_MODEL"

    def test_summary_slot_still_drives_background_work(self):
        """Uniform captions must not accidentally move summarisation too."""
        import inspect
        assert "SUMMARY_MODEL" in inspect.getsource(bot._summarize)


class TestSelfiePromptFixedRules:
    """The anatomy and realism rules are appended to every selfie prompt, unconditionally.
    They were inline literals inside build_selfie_prompt until v2026-08-01.1; hoisting them
    to module constants is only safe if they still reach every prompt."""

    def test_both_rules_appear_in_every_variant(self):
        import random
        for chat_id in (None, 999):
            for hint in ("", "on the fire escape"):
                for seed in range(20):
                    random.seed(seed)
                    prompt = bot.build_selfie_prompt(hint, chat_id)
                    assert bot._SELFIE_ANATOMY_RULE in prompt
                    assert bot._SELFIE_REALISM_RULE in prompt

    def test_rules_carry_the_constraints_the_image_models_need(self):
        """Regression guards: extra limbs (Flux/Kontext) and Gemini's safety filter,
        which returns blacked-out images without an explicit SFW/clothed signal."""
        assert "No extra limbs." in bot._SELFIE_ANATOMY_RULE
        assert "Fully clothed, SFW." in bot._SELFIE_REALISM_RULE


class TestCommandMenuMirrorsHandlers:
    """_build_command_menu is hand-kept alongside the CommandHandler registrations in
    main() (its own docstring says so) -- nothing enforced that until now. Found by
    audit 2026-08-01: 17 unconditionally-registered commands (card, errors, fleet, life,
    meme, note, notes, people, projects, quiet, quietwin, recap, restart, schedule,
    setcard, today, update) were missing from the menu the whole time -- they worked if
    typed, but never appeared in Telegram's autocomplete popup."""

    def _registered_command_names(self):
        import inspect
        import re
        src = inspect.getsource(bot.main)
        return set(re.findall(r'CommandHandler\("([a-z_]+)"', src))

    def test_every_registered_command_is_in_the_full_menu(self):
        names = self._registered_command_names()
        assert len(names) > 50, "sanity check: extraction found suspiciously few commands"
        menu = {c.command for c in bot._build_command_menu(True, True, True, True)}
        missing = names - menu
        assert not missing, f"registered but not in any menu list: {sorted(missing)}"

    def test_the_full_menu_has_no_entries_without_a_handler(self):
        names = self._registered_command_names()
        menu = {c.command for c in bot._build_command_menu(True, True, True, True)}
        dead = menu - names
        assert not dead, f"in the menu but no CommandHandler registers it: {sorted(dead)}"


class TestModelInfoShowsEveryRole:
    """/model used to show only the chat model, so a background slot (SUMMARY_MODEL,
    MOOD_MODEL, ...) silently running something unexpected had no quick way to check
    without /setmodel's heavier no-args output (a live subscription-list API call plus
    picker framing). Requested after a live memory-quality investigation where the
    fix candidate was exactly "which model is actually running this slot?"."""

    class _Msg:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append(text)

    def _run(self):
        msg = self._Msg()
        update = SimpleNamespace(message=msg)
        asyncio.run(bot.model_info(update, None))
        assert len(msg.sent) == 1
        return msg.sent[0]

    def test_every_model_role_appears(self):
        text = self._run()
        for role in bot.MODEL_ROLES:
            assert f"{role}:" in text, role

    def test_shows_the_actual_configured_value_not_a_placeholder(self):
        text = self._run()
        assert bot.NANOGPT_MODEL in text

    def test_no_live_api_call(self):
        """Unlike /setmodel's no-args path, /model must stay cheap enough to check
        often -- inspect the source rather than trying to detect a network call."""
        import inspect
        src = inspect.getsource(bot.model_info)
        assert "_nanogpt_subscription_models" not in src


class TestFactAtomicity:
    """Live incident, 2026-08-01: a strong reasoning model (Priya's own SUMMARY_MODEL,
    unset -> her chat model) still produced a garbled recent_facts entry that fused an
    event (a Costco trip) with unrelated meta-commentary (an argument about how Priya's
    own line should be categorized) into one run-on sentence. Not a weak-model problem --
    _summarize()'s prompt had no instruction against exactly this kind of fusion. Fixed
    by requiring each fact to be one concrete, self-contained thing."""

    def test_summarize_requires_one_concrete_thing_per_fact(self):
        import inspect
        src = inspect.getsource(bot._summarize)
        assert "ONE" in src and "concrete thing" in src
        assert "meta-commentary" in src

    def test_consolidate_facts_forbids_fusing_on_merge(self):
        import inspect
        src = inspect.getsource(bot._consolidate_facts)
        assert "ONE concrete thing" in src
        assert "do not fuse" in src.lower()


class TestFindNearDuplicatePairs:
    """Diagnostic-only sibling of _is_semantic_dup: surfaces every near-duplicate pair
    already sitting in a list, for /dupefacts to report -- built 2026-08-01 to gather
    real evidence on whether facts/recent_facts accumulate reworded near-duplicates
    (the exact-string dedup in _summarize()/_consolidate_facts() would miss), before
    any auto-merge logic gets written."""

    def test_finds_a_pair_above_threshold(self):
        items = ["went to costco", "went to costco again"]
        vecs = [[1.0, 0.0], [0.99, 0.01]]
        out = bot._find_near_duplicate_pairs(items, vecs, 0.92)
        assert out == [(pytest.approx(bot._cosine_sim(vecs[0], vecs[1])), items[0], items[1])]

    def test_distinct_items_not_flagged(self):
        items = ["went to costco", "started a new job"]
        vecs = [[1.0, 0.0], [0.0, 1.0]]
        assert bot._find_near_duplicate_pairs(items, vecs, 0.92) == []

    def test_missing_vector_skipped_not_flagged(self):
        items = ["a", "b", "c"]
        vecs = [[1.0, 0.0], None, [1.0, 0.0]]
        out = bot._find_near_duplicate_pairs(items, vecs, 0.92)
        # only the a/c pair has both vectors present
        assert out == [(1.0, "a", "c")]

    def test_sorted_highest_similarity_first(self):
        items = ["a", "b", "c"]
        vecs = [[1.0, 0.0], [0.95, 0.05], [0.99, 0.01]]
        out = bot._find_near_duplicate_pairs(items, vecs, 0.9)
        sims = [s for s, _, _ in out]
        assert sims == sorted(sims, reverse=True)

    def test_single_item_no_pairs(self):
        assert bot._find_near_duplicate_pairs(["only one"], [[1.0, 0.0]], 0.92) == []

    def test_empty_list(self):
        assert bot._find_near_duplicate_pairs([], [], 0.92) == []


class TestEmbedAndCache:
    def setup_method(self):
        self._orig = dict(bot._embeddings_cache)
        self._orig_embed_text = bot._embed_text

    def teardown_method(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache.update(self._orig)
        bot._embed_text = self._orig_embed_text

    def test_returns_cached_vector_without_reembedding(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache["already known"] = [1.0, 0.0]
        calls = []
        bot._embed_text = lambda t: calls.append(t) or [0.0, 1.0]
        out = bot._embed_and_cache("already known")
        assert out == [1.0, 0.0]
        assert calls == []

    def test_embeds_and_caches_on_miss(self):
        bot._embeddings_cache.clear()
        bot._embed_text = lambda t: [0.5, 0.5]
        out = bot._embed_and_cache("new fact")
        assert out == [0.5, 0.5]
        assert bot._embeddings_cache["new fact"] == [0.5, 0.5]

    def test_embed_failure_returns_none_and_does_not_cache(self):
        bot._embeddings_cache.clear()
        bot._embed_text = lambda t: None
        assert bot._embed_and_cache("unembeddable") is None
        assert "unembeddable" not in bot._embeddings_cache

    def test_strips_whitespace_for_the_cache_key(self):
        bot._embeddings_cache.clear()
        bot._embed_text = lambda t: [1.0, 0.0]
        bot._embed_and_cache("  padded text  ")
        assert "padded text" in bot._embeddings_cache
        assert "  padded text  " not in bot._embeddings_cache


class TestDupefactsCmd:
    """Behavioral check that the command wires the pure pieces together correctly and
    stays strictly read-only (facts/recent_facts must be byte-identical after)."""

    class _Msg:
        def __init__(self):
            self.sent = []

        async def reply_text(self, text, **kwargs):
            self.sent.append(text)

    def setup_method(self):
        self._orig_cache = dict(bot._embeddings_cache)
        self._orig_embed_text = bot._embed_text
        self._orig_facts = dict(bot.facts)
        self._orig_recent = dict(bot.recent_facts)
        self._orig_allowed = set(bot.ALLOWED_USERS)

    def teardown_method(self):
        bot._embeddings_cache.clear()
        bot._embeddings_cache.update(self._orig_cache)
        bot._embed_text = self._orig_embed_text
        bot.facts.clear()
        bot.facts.update(self._orig_facts)
        bot.recent_facts.clear()
        bot.recent_facts.update(self._orig_recent)
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._orig_allowed)

    def _run(self, chat_id, user_id=1):
        msg = self._Msg()
        update = SimpleNamespace(
            message=msg, effective_chat=SimpleNamespace(id=chat_id),
            effective_user=SimpleNamespace(id=user_id))
        asyncio.run(bot.dupefacts_cmd(update, None))
        return msg.sent

    def test_reports_a_near_duplicate_pair(self):
        chat_id = 555001
        bot.ALLOWED_USERS.clear()  # empty = _is_allowed opens the door to anyone
        bot._embeddings_cache.clear()
        bot.recent_facts[chat_id] = [
            "Costco food court trip: a joke about it",
            "Costco food court trip: basically the same joke reworded",
        ]
        bot.facts[chat_id] = []
        bot._embed_text = lambda t: [1.0, 0.0] if "Costco" in t else [0.0, 1.0]
        sent = self._run(chat_id)
        assert any("near-duplicate" in s.lower() or "match" in s.lower() for s in sent)
        assert any("%" in s for s in sent)

    def test_no_duplicates_says_so_plainly(self):
        chat_id = 555002
        bot.ALLOWED_USERS.clear()
        bot._embeddings_cache.clear()
        bot.recent_facts[chat_id] = ["went to costco", "started a new job"]
        bot.facts[chat_id] = []
        bot._embed_text = lambda t: [1.0, 0.0] if "costco" in t else [0.0, 1.0]
        sent = self._run(chat_id)
        assert any("no near-duplicate" in s.lower() for s in sent)

    def test_never_mutates_facts_or_recent_facts(self):
        chat_id = 555003
        bot.ALLOWED_USERS.clear()
        bot._embeddings_cache.clear()
        before_recent = ["a", "b"]
        before_facts = ["c"]
        bot.recent_facts[chat_id] = list(before_recent)
        bot.facts[chat_id] = list(before_facts)
        bot._embed_text = lambda t: [1.0, 0.0]
        self._run(chat_id)
        assert bot.recent_facts[chat_id] == before_recent
        assert bot.facts[chat_id] == before_facts

    def test_disallowed_user_gets_nothing(self):
        chat_id = 555004
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.add(424242)  # non-empty and excludes the test user below
        bot.recent_facts[chat_id] = ["a", "b"]
        bot.facts[chat_id] = []
        sent = self._run(chat_id, user_id=99999)
        assert sent == []


class TestSelfieWeatherMatching:
    """v2026-08-01.7: the selfie prompt composed its scene from weather-blind random
    pools, then appended the live reading as a trailing hint that also said "don't
    describe the weather explicitly". On a 70°F clear day the draw could produce
    "bundled up against the cold" + a canvas jacket + a hoodie, and the image model
    followed the scene over the one temperature token -- a rainy selfie on a sunny day."""

    def setup_method(self):
        self._saved = dict(bot._weather_cache)
        self._match = bot.SELFIE_WEATHER_MATCH
        self._layer = bot.OUTDOOR_LAYER
        self._wardrobe = dict(bot.wardrobe)
        bot.SELFIE_WEATHER_MATCH = True
        # OUTDOOR_LAYER defaults to "" since v2026-08-01.8, which would make the
        # "courier jacket" half of _cold_markers unfalsifiable. Set it so the
        # assertion still tests something (C13).
        bot.OUTDOOR_LAYER = "Ingrid's oversized vintage canvas courier jacket"
        bot.wardrobe.clear()
        bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot._weather_cache.clear()
        bot._weather_cache.update(self._saved)
        bot.SELFIE_WEATHER_MATCH = self._match
        bot.OUTDOOR_LAYER = self._layer
        bot.wardrobe.clear()
        bot.wardrobe.update(self._wardrobe)

    def _set(self, text):
        bot._weather_cache["text"] = text
        bot._weather_cache["ts"] = 9e9

    def test_temp_takes_air_temperature_not_feels_like(self):
        """'feels like' is a second °F field; grabbing it would misjudge the threshold."""
        self._set("70°F, feels like 65°F, light rain, wind 11mph")
        assert bot._weather_temp_f() == 70.0

    def test_temp_handles_negative_and_missing(self):
        self._set("-4°F, snow, wind 9mph")
        assert bot._weather_temp_f() == -4.0
        self._set("")
        assert bot._weather_temp_f() is None

    def test_unknown_weather_is_not_warm(self):
        """Absent data must not strip her jacket in January."""
        self._set("")
        assert bot._weather_is_warm() is False

    def test_clear_is_distinct_from_merely_dry(self):
        """Overcast is dry but grey -- the prompt must not claim 'no overcast' on it."""
        self._set("55°F, overcast, wind 6mph")
        assert bot._weather_outdoor_ok() and not bot._weather_is_clear()
        self._set("70°F, clear, wind 11mph")
        assert bot._weather_is_clear()

    def test_scene_pool_never_returns_empty(self):
        self._set("90°F, clear, wind 2mph")
        assert bot._weather_scene_pool(["a", "b"], {"a", "b"}) == ["a", "b"]

    def _cold_markers(self):
        return (list(bot.SELFIE_COLD_ACTIVITIES) + list(bot.SELFIE_COLD_OUTFITS)
                + ["courier jacket"])

    def test_warm_clear_day_never_produces_cold_weather_content(self):
        """The regression itself, across the whole random space."""
        import random
        self._set("70°F, clear, wind 11mph")
        for seed in range(300):
            random.seed(seed)
            prompt = bot.build_selfie_prompt("", None)
            for marker in self._cold_markers():
                assert marker not in prompt, f"seed {seed}: {marker!r}"

    def test_cold_day_still_allows_cold_content(self):
        """The fix must not strip winter -- filtering is conditional, not global."""
        import random
        self._set("38°F, light snow, wind 12mph")
        hits = 0
        for seed in range(300):
            random.seed(seed)
            if any(m in bot.build_selfie_prompt("", None) for m in self._cold_markers()):
                hits += 1
        assert hits > 0

    def test_dry_weather_carries_an_explicit_no_rain_negative(self):
        import random
        self._set("70°F, clear, wind 11mph")
        random.seed(0)
        assert "It is NOT raining" in bot.build_selfie_prompt("", None)

    def test_rain_never_carries_the_no_rain_negative(self):
        import random
        self._set("52°F, rain, wind 14mph")
        for seed in range(50):
            random.seed(seed)
            assert "It is NOT raining" not in bot.build_selfie_prompt("", seed and None)

    def test_overcast_does_not_claim_clear_sky(self):
        import random
        self._set("55°F, overcast, wind 6mph")
        random.seed(3)
        prompt = bot.build_selfie_prompt("", None)
        assert "It is NOT raining" in prompt
        assert "no heavy grey overcast" not in prompt

    def test_kill_switch_restores_previous_behavior(self):
        """SELFIE_WEATHER_MATCH=0 must reproduce the pre-fix prompt exactly."""
        import random
        bot.SELFIE_WEATHER_MATCH = False
        self._set("70°F, clear, wind 11mph")
        hits = 0
        for seed in range(300):
            random.seed(seed)
            prompt = bot.build_selfie_prompt("", None)
            assert "It is NOT raining" not in prompt
            assert "don't describe the weather explicitly" in prompt
            if any(m in prompt for m in self._cold_markers()):
                hits += 1
        assert hits > 0


class TestDailyWardrobeRotation:
    """v2026-08-01.8: she dresses once a day, for that day's weather, instead of drawing a
    fresh random outfit per photo. Rotation runs in the MORNING and re-reads the weather --
    picking a day's clothes from midnight's reading would rebuild the frozen-snapshot
    contradiction v2026-08-01.7 removed."""

    def setup_method(self):
        self._weather = dict(bot._weather_cache)
        self._wardrobe = dict(bot.wardrobe)
        self._daily, self._match = bot.WARDROBE_DAILY, bot.SELFIE_WEATHER_MATCH
        self._save = bot.save_wardrobe
        bot.save_wardrobe = lambda: None          # keep tests off the instance dir
        bot.WARDROBE_DAILY = bot.SELFIE_WEATHER_MATCH = True
        bot.wardrobe.clear()
        bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot.save_wardrobe = self._save
        bot._weather_cache.clear(); bot._weather_cache.update(self._weather)
        bot.wardrobe.clear(); bot.wardrobe.update(self._wardrobe)
        bot.WARDROBE_DAILY, bot.SELFIE_WEATHER_MATCH = self._daily, self._match

    def _set(self, text):
        bot._weather_cache["text"] = text
        bot._weather_cache["ts"] = 9e9

    def _today(self):
        from datetime import datetime
        return (datetime.now(bot.TZ) if bot.TZ else datetime.now()).date().isoformat()

    def _rotate(self):
        import asyncio
        asyncio.run(bot.wardrobe_rotate_job(None))

    # --- classification ---
    def test_warm_day_rejects_warm_clothing(self):
        self._set("78°F, clear, wind 4mph")
        assert not bot._outfit_suits_weather("an oversized hoodie")
        assert bot._outfit_suits_weather("a tank top")

    def test_cold_day_rejects_bare_skin(self):
        self._set("38°F, light snow, wind 12mph")
        assert not bot._outfit_suits_weather("shorts and sandals")
        assert bot._outfit_suits_weather("a wool coat")

    def test_unknown_weather_suits_everything(self):
        """Absent data must never narrow the wardrobe to nothing."""
        self._set("")
        assert bot._outfit_suits_weather("an oversized hoodie")
        assert bot._outfit_suits_weather("a tank top")

    # --- picking ---
    def test_prefers_owner_wardrobe_over_builtin_pool(self):
        self._set("75°F, clear, wind 5mph")
        bot.wardrobe["outfits"] = ["a linen shirt she stole"]
        assert bot._pick_daily_outfit() == "a linen shirt she stole"

    def test_falls_back_to_builtin_pool_when_wardrobe_empty(self):
        """An instance with no /addoutfit history still changes clothes daily."""
        self._set("75°F, clear, wind 5mph")
        assert bot._pick_daily_outfit() in bot.SELFIE_OUTFITS

    def test_falls_back_when_every_owner_outfit_is_wrong_for_the_weather(self):
        self._set("85°F, clear, wind 2mph")
        bot.wardrobe["outfits"] = ["a parka", "a wool coat"]
        pick = bot._pick_daily_outfit()
        assert pick in bot.SELFIE_OUTFITS and bot._outfit_suits_weather(pick)

    def test_avoids_recent_picks(self):
        self._set("75°F, clear, wind 5mph")
        bot.wardrobe["outfits"] = ["a tank top", "a loose t-shirt"]
        bot.wardrobe["recent"] = ["a tank top"]
        assert bot._pick_daily_outfit() == "a loose t-shirt"

    def test_picked_outfit_always_suits_the_weather(self):
        import random
        self._set("82°F, clear, wind 3mph")
        for seed in range(80):
            random.seed(seed)
            assert bot._outfit_suits_weather(bot._pick_daily_outfit())

    # --- the job ---
    def test_rotation_sets_current_and_stamps_today(self):
        self._set("75°F, clear, wind 5mph")
        self._rotate()
        assert bot.wardrobe["current"]
        assert bot.wardrobe["auto"] is True
        assert bot.wardrobe["picked"] == self._today()

    def test_rotation_is_idempotent_within_a_day(self):
        self._set("75°F, clear, wind 5mph")
        self._rotate()
        first = bot.wardrobe["current"]
        self._rotate()
        assert bot.wardrobe["current"] == first

    def test_manual_outfit_holds_for_the_rest_of_the_day(self):
        """Owner decision 2026-08-01: /outfit wins today, rotation resumes tomorrow."""
        self._set("75°F, clear, wind 5mph")
        bot.wardrobe.update({"current": "a parka", "auto": False, "picked": self._today()})
        self._rotate()
        assert bot.wardrobe["current"] == "a parka"
        assert bot.wardrobe["auto"] is False

    def test_rotation_resumes_the_next_day(self):
        self._set("75°F, clear, wind 5mph")
        bot.wardrobe.update({"current": "a parka", "auto": False, "picked": "2020-01-01"})
        self._rotate()
        assert bot.wardrobe["current"] != "a parka"
        assert bot.wardrobe["auto"] is True

    def test_kill_switch_disables_rotation(self):
        bot.WARDROBE_DAILY = False
        self._set("75°F, clear, wind 5mph")
        self._rotate()
        assert bot.wardrobe.get("current") is None

    # --- the loop back into the selfie prompt ---
    def test_stale_auto_outfit_is_dropped_when_the_afternoon_outruns_it(self):
        import random
        self._set("84°F, clear, wind 3mph")
        bot.wardrobe.update({"current": "a heavy wool coat", "auto": True})
        for seed in range(40):
            random.seed(seed)
            assert "heavy wool coat" not in bot.build_selfie_prompt("", None)

    def test_hand_picked_outfit_is_honored_even_against_the_weather(self):
        """Owner intent is not second-guessed -- only rotation's own pick is re-checked."""
        import random
        self._set("84°F, clear, wind 3mph")
        bot.wardrobe.update({"current": "a heavy wool coat", "auto": False})
        random.seed(0)
        assert "a heavy wool coat" in bot.build_selfie_prompt("", None)


class TestOutdoorLayer:
    """v2026-08-01.8: outerwear is per-instance config. It was gated on
    `SELFIE_APPEARANCE is _APPEARANCE_DEFAULT`, which is only true for an unnamed run --
    every live instance passes its directory as argv[1], so the line was unreachable."""

    def setup_method(self):
        self._weather = dict(bot._weather_cache)
        self._layer = bot.OUTDOOR_LAYER
        self._wardrobe = dict(bot.wardrobe)
        bot.OUTDOOR_LAYER = "Ingrid's oversized vintage canvas courier jacket"
        bot.wardrobe.clear(); bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot.OUTDOOR_LAYER = self._layer
        bot._weather_cache.clear(); bot._weather_cache.update(self._weather)
        bot.wardrobe.clear(); bot.wardrobe.update(self._wardrobe)

    def _set(self, text):
        bot._weather_cache["text"] = text
        bot._weather_cache["ts"] = 9e9

    def _prompts(self, n=300):
        import random
        out = []
        for seed in range(n):
            random.seed(seed)
            out.append(bot.build_selfie_prompt("", None))
        return out

    def test_layer_appears_outdoors_in_cool_weather(self):
        self._set("47°F, overcast, wind 8mph")
        assert any("courier jacket" in p for p in self._prompts())

    def test_layer_never_appears_on_a_warm_day(self):
        self._set("78°F, clear, wind 4mph")
        assert not any("courier jacket" in p for p in self._prompts())

    def test_unset_layer_adds_nothing(self):
        bot.OUTDOOR_LAYER = ""
        self._set("47°F, overcast, wind 8mph")
        assert not any("Over that" in p for p in self._prompts())

    def test_appearance_default_names_no_character(self):
        """The old default described a discarded tattoo-artist Priya card (owner, 2026-08-01)."""
        low = bot._APPEARANCE_DEFAULT.lower()
        for relic in ("tattoo", "septum", "half-shaved", "ink-stained", "sleeved"):
            assert relic not in low


class TestSelfieIdentityGuard:
    """v2026-08-01.9: selfies intermittently came back not looking like her. The identity
    instruction is bits[0], and two releases of appended scene/weather/camera text pushed
    ~1000 characters after it; meanwhile 30% of random draws stacked a face-obscuring
    framing on a face-degrading camera, leaving an edit model room to drift the face."""

    def setup_method(self):
        self._weather = dict(bot._weather_cache)
        self._guard = bot.SELFIE_IDENTITY_GUARD
        self._has_base = bot._has_base_image
        self._wardrobe = dict(bot.wardrobe)
        bot.SELFIE_IDENTITY_GUARD = True
        bot._has_base_image = lambda: True
        bot._weather_cache["text"] = "55°F, overcast, wind 6mph"
        bot._weather_cache["ts"] = 9e9
        bot.wardrobe.clear(); bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot.SELFIE_IDENTITY_GUARD = self._guard
        bot._has_base_image = self._has_base
        bot._weather_cache.clear(); bot._weather_cache.update(self._weather)
        bot.wardrobe.clear(); bot.wardrobe.update(self._wardrobe)

    def _prompts(self, n=400, chat_id=None):
        import random
        out = []
        for seed in range(n):
            random.seed(seed)
            out.append(bot.build_selfie_prompt("", chat_id))
        return out

    def test_soft_framing_never_pairs_with_soft_camera(self):
        for p in self._prompts():
            soft_f = any(f in p for f in bot.SELFIE_SOFT_FRAMINGS)
            soft_c = any(c in p for c in bot.SELFIE_SOFT_CAMERA)
            assert not (soft_f and soft_c), p

    def test_stacking_still_happens_with_the_guard_off(self):
        """Proves the previous test measures the guard, not an accident of the pools."""
        bot.SELFIE_IDENTITY_GUARD = False
        assert any(
            any(f in p for f in bot.SELFIE_SOFT_FRAMINGS)
            and any(c in p for c in bot.SELFIE_SOFT_CAMERA)
            for p in self._prompts()
        )

    def test_identity_is_restated_as_the_final_instruction(self):
        """Last word, after the scene-dedup list -- that block names other setups."""
        for p in self._prompts(n=60):
            assert p.rstrip().endswith(bot._SELFIE_IDENTITY_TAIL)

    def test_identity_tail_still_last_when_dedup_list_is_present(self):
        bot._recent_selfie_hints[777] = ["on the fire escape", "at the counter"]
        try:
            for p in self._prompts(n=40, chat_id=777):
                assert "avoid recreating these recent setups" in p
                assert p.rstrip().endswith(bot._SELFIE_IDENTITY_TAIL)
        finally:
            bot._recent_selfie_hints.pop(777, None)

    def test_no_identity_tail_without_a_reference_photo(self):
        """Nothing to be 'the same as' -- the tail would be an instruction to copy nothing."""
        bot._has_base_image = lambda: False
        assert not any(bot._SELFIE_IDENTITY_TAIL in p for p in self._prompts(n=40))

    def test_kill_switch_removes_the_guard(self):
        bot.SELFIE_IDENTITY_GUARD = False
        assert not any(bot._SELFIE_IDENTITY_TAIL in p for p in self._prompts(n=40))

    def test_shared_prompt_hardcodes_no_character_specific_feature(self):
        """'freckles' was baked into the shared identity line -- Nora's trait, applied to
        all seven. Same character-bleed family as the courier jacket (v2026-08-01.8)."""
        import inspect
        src = inspect.getsource(bot.build_selfie_prompt)
        for trait in ("freckles", "septum", "tattoo", "blonde", "half-shaved"):
            assert trait not in src.lower(), trait


class TestBaseImageResolution:
    """v2026-08-01.10: SELFIE_BASE defaults to a filename inherited from the home instance.
    Nora's .env never set it, so her bot looked for priya_base.png, did not find it, and
    generated every selfie from text alone -- with nora_base.jpg sitting in her own
    directory. selfie_ready() never complained because it also accepts an appearance.txt."""

    def setup_method(self):
        import tempfile
        from pathlib import Path
        self._dir = Path(tempfile.mkdtemp(prefix="base_img_"))
        self._saved = (bot.BASE_DIR, bot.SELFIE_BASE, bot.SELFIE_BASE_AUTODETECT)
        bot.BASE_DIR = self._dir
        bot.SELFIE_BASE = "priya_base.png"
        bot.SELFIE_BASE_AUTODETECT = True

    def teardown_method(self):
        import shutil
        bot.BASE_DIR, bot.SELFIE_BASE, bot.SELFIE_BASE_AUTODETECT = self._saved
        shutil.rmtree(self._dir, ignore_errors=True)

    def _touch(self, name, data=b"\x89PNG fake"):
        (self._dir / name).write_bytes(data)

    def test_exact_configured_name_wins(self):
        self._touch("priya_base.png")
        self._touch("nora_base.jpg")
        assert bot._resolve_base_image().name == "priya_base.png"

    def test_the_nora_case_wrong_name_and_extension(self):
        """The reported bug: one candidate, different name AND suffix from the default."""
        self._touch("nora_base.jpg")
        assert bot._has_base_image()
        assert bot._resolve_base_image().name == "nora_base.jpg"

    def test_ambiguous_candidates_are_not_guessed(self):
        """Two faces on disk is a real choice -- picking one is how you ship the wrong woman."""
        self._touch("nora_base.jpg")
        self._touch("priya_base.jpg")
        assert bot._resolve_base_image() is None
        assert not bot._has_base_image()

    def test_no_candidates_is_text_only(self):
        assert bot._resolve_base_image() is None

    def test_non_image_files_are_not_candidates(self):
        self._touch("nora_base.txt", b"not an image")
        assert bot._resolve_base_image() is None

    def test_kill_switch_requires_an_exact_match(self):
        bot.SELFIE_BASE_AUTODETECT = False
        self._touch("nora_base.jpg")
        assert bot._resolve_base_image() is None

    def test_mime_follows_the_resolved_file_not_the_configured_one(self):
        """Configured name says .png; the real file is .jpg. Sending the wrong mime to
        Gemini's inline_data is how a working photo still gets rejected."""
        self._touch("nora_base.jpg")
        _, mime = bot._base_image()
        assert mime == "image/jpeg"

    def test_status_line_names_the_autodetected_file_and_says_to_fix_the_env(self):
        self._touch("nora_base.jpg")
        status = bot._base_image_status()
        assert "nora_base.jpg" in status and "AUTODETECTED" in status and ".env" in status

    def test_status_line_flags_text_only_and_lists_what_it_saw(self):
        bot.SELFIE_BASE_AUTODETECT = False
        self._touch("nora_base.jpg")
        status = bot._base_image_status()
        assert "TEXT-ONLY" in status and "nora_base.jpg" in status

    def test_status_line_is_quiet_when_correctly_configured(self):
        self._touch("priya_base.png")
        assert bot._base_image_status() == "priya_base.png"


class TestSharedPromptIsCharacterNeutral:
    """v2026-08-01.11: marcus (31, 6'2", a man) shares bot.py with six women. The
    no-appearance.txt fallback asserted "an adult woman in her late 20s", so an instance
    with no appearance.txt and no reference photo generated the wrong person outright.
    Third instance of this class after the courier jacket (.8) and freckles (.9)."""

    def test_appearance_fallbacks_assert_no_sex(self):
        """Comments are stripped first: the block explains the old wording, and a scanner
        that cannot tell describing-the-bug from doing-it flags its own changelog (C14)."""
        import inspect, re
        src = inspect.getsource(bot)
        block = src[src.find("_APPEARANCE_DEFAULT ="):src.find("CARD_NAME =")]
        code = "\n".join(ln.split("#")[0] for ln in block.splitlines())
        # Word boundaries, not substrings: "he " lives inside "the ", which made the first
        # version of this test fail on an innocent comment.
        hits = re.findall(r"\b(?:wom[ae]n|her|hers|she|m[ae]n|his|him|he)\b", code.lower())
        assert not hits, f"sexed wording in the shared appearance fallback: {hits}"

    def test_fallbacks_still_state_an_adult_age(self):
        """Gemini returns blacked-out frames when no age is stated (see SELFIE_APPEARANCE)."""
        import re
        assert re.search(r"\b(20s|30s|\d{2}-year-old)\b", bot._APPEARANCE_DEFAULT)

    def test_status_line_calls_out_the_worst_case(self):
        """No photo AND no appearance.txt is not 'text-only', it is 'nobody in particular'."""
        import tempfile, shutil
        from pathlib import Path
        d = Path(tempfile.mkdtemp(prefix="neutral_"))
        saved = (bot.BASE_DIR, bot._APPEARANCE_FILE, bot.SELFIE_BASE)
        try:
            bot.BASE_DIR = d
            bot._APPEARANCE_FILE = d / "appearance.txt"
            bot.SELFIE_BASE = "priya_base.png"
            assert "NO APPEARANCE.TXT" in bot._base_image_status()
            bot._APPEARANCE_FILE.write_text("a tall man in his 30s.")
            assert "NO APPEARANCE.TXT" not in bot._base_image_status()
        finally:
            bot.BASE_DIR, bot._APPEARANCE_FILE, bot.SELFIE_BASE = saved
            shutil.rmtree(d, ignore_errors=True)


class TestAuditReportsSelfieBase:
    """v2026-08-02.1: v2026-08-01.10 put the selfie-base status in the STARTUP AUDIT log
    line only, and I told the owner /audit would show it. Different code paths -- it did
    not. /audit is the one surface reachable from Telegram, which is the whole point when
    the question is 'is this bot being sent its own face?'."""

    def test_gathered_data_carries_the_field(self):
        assert "selfie_base" in bot.gather_audit_data()

    def test_it_reaches_the_rendered_audit_text(self):
        """The HTTP API and /audit share gather_audit_data, but only /audit renders lines;
        a key in the dict that no line prints is exactly the gap this closes."""
        import inspect
        src = inspect.getsource(bot.audit_cmd)
        assert "selfie_base" in src and "Selfie base:" in src

    def test_field_matches_the_startup_audit_source(self):
        """Both surfaces must report the same thing, or they disagree under a real fault."""
        assert bot.gather_audit_data()["selfie_base"] == bot._base_image_status()


class TestBaseImageMimeSniffing:
    """v2026-08-02.2: the mime type came from the filename extension. Renaming a PNG to
    .jpg -- routine when swapping reference photos around -- declared PNG bytes as
    image/jpeg, and a rejected reference means the face falls back to the text."""

    def test_png_bytes_named_jpg_are_still_png(self):
        assert bot._sniff_mime(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", ".jpg") == "image/png"

    def test_jpeg_bytes_named_png_are_still_jpeg(self):
        assert bot._sniff_mime(b"\xff\xd8\xff\xe0\x00\x10JFIF", ".png") == "image/jpeg"

    def test_webp_is_recognised(self):
        assert bot._sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".png") == "image/webp"

    def test_unrecognised_bytes_fall_back_to_the_extension(self):
        """Never worse than the old behaviour on a format we don't know."""
        assert bot._sniff_mime(b"garbagegarb", ".png") == "image/png"
        assert bot._sniff_mime(b"garbagegarb", ".jpg") == "image/jpeg"

    def test_end_to_end_through_base_image(self):
        import tempfile, shutil
        from pathlib import Path
        d = Path(tempfile.mkdtemp(prefix="mime_"))
        saved = (bot.BASE_DIR, bot.SELFIE_BASE)
        try:
            bot.BASE_DIR, bot.SELFIE_BASE = d, "nora_base.jpg"
            (d / "nora_base.jpg").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
            assert bot._base_image()[1] == "image/png"
        finally:
            bot.BASE_DIR, bot.SELFIE_BASE = saved
            shutil.rmtree(d, ignore_errors=True)


class TestSetBaseCommand:
    """v2026-08-02.3: /setbase installs the selfie reference photo over Telegram.

    Built because the scp route failed three times in one session -- those commands are
    phone-local while the owner's shell is on the VPS. That is C1's operator half, which
    no hook can catch, so the transfer was removed rather than re-explained."""

    def _src(self):
        import inspect
        return inspect.getsource(bot.setbase_cmd)

    def test_admin_gated(self):
        """It overwrites a file in the instance directory -- not for arbitrary users."""
        assert "_is_admin" in self._src()

    def test_registered_as_a_handler_and_in_the_menu(self):
        import inspect
        main_src = inspect.getsource(bot.main)
        assert 'CommandHandler("setbase"' in main_src
        assert any(c.command == "setbase"
                   for c in bot._build_command_menu(False, False))

    def test_rejects_non_image_bytes(self):
        """Magic-byte check, not a trusted mime header or filename."""
        src = self._src()
        assert "_BASE_IMAGE_MAGIC" in src and "refusing to install" in src

    def test_recognises_the_three_formats_it_claims(self):
        names = {name for _, name in bot._BASE_IMAGE_MAGIC}
        assert names == {"PNG", "JPEG"}
        assert "WEBP" in self._src()

    def test_backs_up_the_previous_photo(self):
        """A bad swap must be recoverable without another transfer."""
        assert ".prev" in self._src()

    def test_writes_atomically(self):
        """A half-written reference photo is worse than an old one."""
        src = self._src()
        assert ".tmp" in src and "tmp.replace(dest)" in src

    def test_targets_selfie_base_so_no_env_edit_is_needed(self):
        assert "BASE_DIR / SELFIE_BASE" in self._src()

    def test_warns_when_telegram_compressed_the_image(self):
        src = self._src()
        assert "compressed" in src and "Resend as a file" in src


class TestSetBaseCaptionDispatch:
    """v2026-08-02.4: /setbase was documented as working as a photo caption. It could not.

    PTB's CommandHandler.check_update requires message.text AND message.entities; a caption
    populates message.caption/caption_entities instead, so the update fell through to normal
    chat and the model answered it conversationally. v2026-08-02.3's tests all asserted on
    handler SOURCE -- registration, admin gate, atomic write -- and never exercised dispatch,
    which is why they were green on a path that could not run."""

    def test_command_handler_really_does_ignore_captions(self):
        """Pins the library behaviour this fix exists for, by exercising it rather than
        asserting it. If a future PTB matches captions, this fails and the extra handler
        can be reconsidered."""
        import inspect
        from telegram.ext import CommandHandler
        src = inspect.getsource(CommandHandler.check_update)
        assert "message.text" in src
        assert "caption" not in src.lower()

    def test_caption_handler_is_registered(self):
        import inspect
        main_src = inspect.getsource(bot.main)
        assert "CaptionRegex" in main_src and "setbase" in main_src

    def test_caption_handler_precedes_the_photo_handler(self):
        """handle_photo would otherwise swallow the update and reply conversationally."""
        import inspect
        main_src = inspect.getsource(bot.main)
        assert main_src.index("CaptionRegex") < main_src.index("filters.PHOTO, handle_photo")

    def test_it_accepts_documents_too(self):
        """Sending as a file is the recommended path -- Telegram recompresses photos."""
        import inspect
        main_src = inspect.getsource(bot.main)
        i = main_src.index("CaptionRegex")
        window = main_src[i - 200:i + 100]
        assert "Document.IMAGE" in window and "filters.PHOTO" in window


class TestAuditReportsSelfieProvider:
    """v2026-08-02.5: three instances were silently on NanoGPT's flux-kontext because their
    .env had no GEMINI_API_KEY, and flux-kontext preserves identity far worse than Gemini on
    an edit. /audit reported which reference photo was in play but never which backend
    consumed it, so the split was invisible from Telegram."""

    def test_provider_is_gathered_and_rendered(self):
        import inspect
        assert "selfie_provider" in bot.gather_audit_data()
        assert "selfie_provider" in inspect.getsource(bot.audit_cmd)

    def test_nanogpt_reports_the_model_too(self):
        """'nanogpt' alone doesn't say flux-kontext, which is the part that matters."""
        import inspect
        src = inspect.getsource(bot.gather_audit_data)
        assert "SELFIE_MODEL" in src and "nanogpt" in src

    def test_value_is_a_non_empty_string(self):
        v = bot.gather_audit_data()["selfie_provider"]
        assert isinstance(v, str) and v
