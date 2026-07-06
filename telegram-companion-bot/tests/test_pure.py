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
