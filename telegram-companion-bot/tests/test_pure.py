"""Tests for pure functions in bot.py.

These cover logic where a regression is fleet-breaking and the functions are pure
(no I/O, no Telegram, no API calls). See ROADMAP.md item 2.1.
"""
import json

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
