"""Tests for pure functions in bot.py.

These cover logic where a regression is fleet-breaking and the functions are pure
(no I/O, no Telegram, no API calls). See ROADMAP.md item 2.1.
"""
import asyncio
import json
import time

import bot


# ── extract_tags ──────────────────────────────────────────────────────────────
# Returns (clean_text, reaction, selfie_hint, clothing_override, meme_caption).

class TestExtractTags:
    def test_plain_text_unchanged(self):
        text = "hey what's up"
        clean, reaction, selfie, clothing, meme = bot.extract_tags(text)
        assert clean == text
        assert reaction is None
        assert selfie is None
        assert clothing is None
        assert meme is None

    def test_react_tag(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags("sure! [react: ❤️]")
        assert "react" not in clean.lower()
        assert reaction is not None
        assert selfie is None
        assert clothing is None
        assert meme is None

    def test_selfie_tag(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags(
            "here you go [selfie: wearing a red dress at the park]"
        )
        assert "selfie" not in clean.lower()
        assert selfie == "wearing a red dress at the park"
        assert clothing is None
        assert meme is None

    def test_selfie_inline_clothing(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags(
            "here [selfie: curled up on the couch | clothing: oversized white t-shirt]"
        )
        assert selfie == "curled up on the couch"
        assert clothing == "oversized white t-shirt"
        assert "[" not in clean

    def test_dedicated_clothing_tag(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags(
            "[selfie: mirror shot] [clothing: black lace lingerie]"
        )
        assert selfie == "mirror shot"
        assert clothing == "black lace lingerie"

    def test_dedicated_outfit_tag(self):
        _, _, _, clothing, _ = bot.extract_tags("[outfit: just a hoodie]")
        assert clothing == "just a hoodie"

    def test_dedicated_clothing_wins_over_inline(self):
        _, _, selfie, clothing, _ = bot.extract_tags(
            "[selfie: scene | clothing: from-inline] [clothing: from-dedicated]"
        )
        assert selfie == "scene"
        assert clothing == "from-dedicated"

    def test_empty_dedicated_tag_does_not_discard_the_inline_value(self):
        """v2026-08-08.2: the guard tested `is None`, so an empty "[outfit: ]" (which
        parses to "") beat a populated inline value and then fell through to the default
        -- the character's stated outfit was silently lost."""
        _, _, selfie, clothing, _ = bot.extract_tags(
            "[selfie: kitchen | clothing: a red dress][outfit: ]"
        )
        assert selfie == "kitchen"
        assert clothing == "a red dress"

    def test_meme_tag_two_parts(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags(
            "lol [meme: when the code works | on the first try]"
        )
        assert "meme" not in clean.lower()
        assert meme == ("when the code works", "on the first try")

    def test_meme_tag_one_part(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags(
            "check this out [meme: one does not simply]"
        )
        assert meme == ("one does not simply", "")

    def test_all_tags_together(self):
        text = "[react: 😂] haha [selfie: laughing] [meme: top | bottom]"
        clean, reaction, selfie, clothing, meme = bot.extract_tags(text)
        assert reaction is not None
        assert selfie == "laughing"
        assert clothing is None
        assert meme == ("top", "bottom")
        assert "[" not in clean

    def test_search_tag_stripped(self):
        clean, _, _, _, _ = bot.extract_tags("let me look [search: python async]")
        assert "search" not in clean.lower()
        assert "[" not in clean

    def test_case_insensitive(self):
        _, _, selfie, _, _ = bot.extract_tags("[Selfie: test hint]")
        assert selfie == "test hint"

    def test_empty_string(self):
        clean, reaction, selfie, clothing, meme = bot.extract_tags("")
        assert clean == ""
        assert reaction is None
        assert selfie is None
        assert clothing is None
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


def _chain(n: int) -> list:
    """A ledger tail whose last n entries are bot messages (chain length n)."""
    return [_human(1)] + [_bot(2 + i) for i in range(n)]


class TestShouldReplyToBot:
    def test_cap_overrides_addressed(self):
        entries = _chain(bot.GROUP_BOT_CHAIN_MAX)
        assert not bot._should_reply_to_bot(entries, prob_roll=0.0, addressed=True)

    def test_addressed_below_cap(self):
        entries = [_human(1), _bot(2)]
        assert bot._should_reply_to_bot(entries, prob_roll=0.99, addressed=True)

    def test_probability_gate(self):
        entries = [_human(1), _bot(2)]
        assert bot._should_reply_to_bot(entries, prob_roll=0.0, addressed=False)
        assert not bot._should_reply_to_bot(entries, prob_roll=0.99, addressed=False)

    def test_chain_longer_than_two_is_reachable(self):
        # The v1 defaults ended every exchange at 2 bot messages, which read as "they
        # only ever reply once". A third comeback must be possible at all.
        assert bot.GROUP_BOT_CHAIN_MAX > 2
        assert bot._should_reply_to_bot(_chain(2), prob_roll=0.0, addressed=False)

    def test_probability_decays_with_depth(self):
        # Same roll, deeper chain → the reply that passed at depth 0 fails later on.
        roll = bot.GROUP_BOT_REPLY_PROB * 0.9
        assert bot._should_reply_to_bot(_chain(1), roll, addressed=False)
        assert not bot._should_reply_to_bot(
            _chain(bot.GROUP_BOT_CHAIN_MAX - 1), roll, addressed=False)

    def test_addressed_is_certain_at_depth_zero_only(self):
        # Being named starts at 1.0 (v1 behaviour for the first comeback) but decays
        # with everything else — otherwise name-dropping runs every chain to the cap.
        assert bot._should_reply_to_bot(_chain(1), prob_roll=0.999, addressed=True)
        assert not bot._should_reply_to_bot(_chain(2), prob_roll=0.999, addressed=True)

    def test_decay_of_one_is_the_flat_v1_gate(self, monkeypatch):
        monkeypatch.setattr(bot, "GROUP_CHAIN_DECAY", 1.0)
        for depth in range(1, bot.GROUP_BOT_CHAIN_MAX):
            assert bot._should_reply_to_bot(_chain(depth), prob_roll=0.999, addressed=True)

    def test_cap_still_wins_over_decay_disabled(self, monkeypatch):
        monkeypatch.setattr(bot, "GROUP_CHAIN_DECAY", 1.0)
        assert not bot._should_reply_to_bot(
            _chain(bot.GROUP_BOT_CHAIN_MAX), prob_roll=0.0, addressed=True)


class TestGroupBanterDefaults:
    def test_kill_switch_present_and_on_by_default(self):
        # Owner policy: new behaviour defaults ON with an env kill switch. The fixture
        # sets no GROUP_* vars, so this is the shipped default.
        assert bot.GROUP_BANTER is True

    def test_send_throttle_allows_alternation(self):
        # A bot's own messages land ~2 turns apart in a live exchange (poll ≤5s +
        # claim delay ≤3s + generation, twice). A throttle at or above that window
        # silently ends every exchange, which is what 20s did.
        assert bot.GROUP_MIN_GAP_SECONDS <= 16

    def test_budget_covers_a_full_chain_of_exchanges(self):
        # Longer chains spend the daily bot-to-bot budget faster; a budget that runs
        # out mid-evening reproduces the original complaint silently.
        assert bot.GROUP_DAILY_BOT_BUDGET >= bot.GROUP_BOT_CHAIN_MAX * 8


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


class TestHandleMessageGroupGating:
    """v2026-08-07.2: the ponytail-audit cleanup's deletion of handle_message's
    per-handler _is_allowed check was reverted after /code-review caught it — that
    check is the ONLY per-user allowlist enforcement for group text messages.
    _private_gate (group -1) explicitly no-ops for chat_id < 0 ("group_guard's
    jurisdiction"), and group_guard only checks chat-level GROUP_ALLOWED_CHATS
    membership, never the sender's identity. GROUP_CHAT_DESIGN.md §6: "Human gating
    unchanged... strangers in an allowed group are ignored unless ALLOWED_USERS is
    empty." Pins that invariant directly against handle_message, not just _private_gate."""

    GROUP_CHAT_ID = -100777001

    def setup_method(self):
        self._allowed = set(bot.ALLOWED_USERS)
        self._group_mode = bot.GROUP_MODE
        self._group_chats = set(bot.GROUP_ALLOWED_CHATS)
        self._last_request = dict(bot._last_request)
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.add(1)  # non-empty: strangers must be rejected
        bot.GROUP_MODE = True
        bot.GROUP_ALLOWED_CHATS.clear()
        bot.GROUP_ALLOWED_CHATS.add(self.GROUP_CHAT_ID)
        bot._last_request.clear()

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._allowed)
        bot.GROUP_MODE = self._group_mode
        bot.GROUP_ALLOWED_CHATS.clear()
        bot.GROUP_ALLOWED_CHATS.update(self._group_chats)
        bot._last_request.clear()
        bot._last_request.update(self._last_request)

    def _group_update(self, user_id):
        msg = SimpleNamespace(text="hello", reply_to_message=None, message_id=1)
        return SimpleNamespace(
            message=msg,
            effective_chat=SimpleNamespace(id=self.GROUP_CHAT_ID),
            effective_user=SimpleNamespace(id=user_id, first_name="Someone"),
        )

    def test_non_allowlisted_group_member_never_reaches_group_handling(self, monkeypatch):
        called = []

        async def _fake_group_handler(update, context):
            called.append(update)

        monkeypatch.setattr(bot, "_handle_group_message", _fake_group_handler)
        asyncio.run(bot.handle_message(self._group_update(999), _cmd_ctx()))
        assert called == []

    def test_allowlisted_group_member_reaches_group_handling(self, monkeypatch):
        called = []

        async def _fake_group_handler(update, context):
            called.append(update)

        monkeypatch.setattr(bot, "_handle_group_message", _fake_group_handler)
        asyncio.run(bot.handle_message(self._group_update(1), _cmd_ctx()))
        assert len(called) == 1


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
        """Same contract as before v2026-08-02.14, different mechanism. The env flags are
        now the static preference alone; _alerts_on() carries the "and the feed is live"
        half, because folding GARMIN_ENABLED in at import froze it — /features health off
        flipped the parent and the monitors kept firing off the stale copy."""
        assert bot.GARMIN_ENABLED is False
        assert bot._alerts_on(bot.STRESS_ALERTS) is False
        assert bot._alerts_on(bot.BB_ALERTS) is False
        assert bot._alerts_on(bot.RHR_ALERTS) is False

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

    def _health_job_source(self, fn):
        # stress_monitor_job/bb_monitor_job delegate their shared shape (cooldown
        # gate, off-loop fetch, nudge gate, trigger) to _run_health_alert_job as of
        # the ponytail-audit dedup (CHANGELOG) — check the composed source, since the
        # invariant genuinely holds for both, just no longer inline in either wrapper.
        # rhr_monitor_job kept its own body (different cooldown shape), so it's
        # checked standalone.
        import inspect
        src = inspect.getsource(fn)
        if fn in (bot.stress_monitor_job, bot.bb_monitor_job):
            src += inspect.getsource(bot._run_health_alert_job)
        return src

    def test_every_garmin_call_runs_off_the_event_loop(self):
        # Invariant #8: garminconnect is blocking requests underneath.
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job,
                   bot.rhr_monitor_job, bot.update_garmin):
            assert "asyncio.to_thread" in self._health_job_source(fn), fn.__name__

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
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job, bot.rhr_monitor_job):
            assert "_consume_nudge(owner)" in self._health_job_source(fn), fn.__name__

    def test_check_ins_respect_the_proactive_gate(self):
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job, bot.rhr_monitor_job):
            assert "_health_nudge_ok(owner)" in self._health_job_source(fn), fn.__name__

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


# ── Safety: distress detection (2026-08-04, reimplemented from the abandoned
# claude/push-to-repo-7i2f3c branch's d141e84, never merged the first time) ──────

class TestSafetyClassifier:
    def test_yes_is_distress(self, monkeypatch):
        monkeypatch.setattr(bot, "call_nanogpt", lambda messages, model=None: "Yes.")
        assert bot._assess_safety("I want to end it all") is True

    def test_no_is_not_distress(self, monkeypatch):
        monkeypatch.setattr(bot, "call_nanogpt", lambda messages, model=None: "No")
        assert bot._assess_safety("just a rough day at work") is False

    def test_a_broken_classifier_reads_as_no_distress(self, monkeypatch):
        def _boom(messages, model=None):
            raise RuntimeError("api down")

        monkeypatch.setattr(bot, "call_nanogpt", _boom)
        assert bot._assess_safety("anything") is False

    def test_no_raw_exception_in_safety_log(self):
        # Only the exception's class name may reach a log line (cf. the Garmin/
        # WSDOT key-leak convention).
        import inspect
        src = inspect.getsource(bot._assess_safety)
        assert '", e)' not in src
        assert ".__name__" in src

    def test_prompt_carries_the_name_and_resource(self):
        text = bot._safety_prompt("Tester")
        assert "Tester" in text
        assert bot.SAFETY_RESOURCES in text

    def test_config_types(self):
        assert isinstance(bot.SAFETY_ENABLED, bool)
        assert isinstance(bot.SAFETY_MODEL, str) and bot.SAFETY_MODEL
        assert isinstance(bot.SAFETY_RESOURCES, str) and bot.SAFETY_RESOURCES


class TestAssembleMessagesDistress:
    def test_distress_suppresses_inner_voice(self):
        bot.conversation_history[9401] = []
        bot.user_names[9401] = "Tester"
        msgs = bot.assemble_messages(9401, "hello", inner_voice="she notices he sounds off",
                                     distress=True)
        assert not any("private thought" in (m.get("content") or "") for m in msgs)

    def test_no_distress_keeps_inner_voice(self):
        bot.conversation_history[9402] = []
        bot.user_names[9402] = "Tester"
        msgs = bot.assemble_messages(9402, "hello", inner_voice="she notices he sounds off",
                                     distress=False)
        assert any("private thought" in (m.get("content") or "") for m in msgs)

    def test_distress_appends_the_safety_prompt_last(self):
        bot.conversation_history[9403] = []
        bot.user_names[9403] = "Tester"
        msgs = bot.assemble_messages(9403, "hello", distress=True)
        assert msgs[-1]["role"] == "system"
        assert "distress" in msgs[-1]["content"]

    def test_no_distress_by_default(self):
        bot.conversation_history[9404] = []
        bot.user_names[9404] = "Tester"
        msgs = bot.assemble_messages(9404, "hello")
        assert not any("distress" in (m.get("content") or "") for m in msgs)


# ── Adaptive texting-style mirroring (2026-08-04, reimplemented from a485b1b,
# never merged) ───────────────────────────────────────────────────────────────

class TestUserStyleNote:
    def _seed(self, chat_id, msgs):
        bot.conversation_history[chat_id] = [{"role": "user", "content": m} for m in msgs]
        bot.user_names[chat_id] = "Tester"

    def test_too_few_messages_is_silent(self):
        self._seed(9501, ["hi"] * (bot.STYLE_MIN_MSGS - 1))
        assert bot._user_style_note(9501) == ""

    def test_short_clipped_texter(self):
        self._seed(9502, ["yo"] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9502)
        assert "short, clipped" in note

    def test_long_texter(self):
        long_msg = " ".join(["word"] * 30)
        self._seed(9503, [long_msg] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9503)
        assert "longer, fuller" in note

    def test_heavy_emoji_user(self):
        self._seed(9504, ["nice 😂🔥"] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9504)
        assert "emoji freely" in note

    def test_no_emoji_user(self):
        self._seed(9505, ["that sounds reasonable to me honestly"] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9505)
        assert "rarely use emoji" in note

    def test_lowercase_texter(self):
        self._seed(9506, ["hey what's up today"] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9506)
        assert "all-lowercase" in note

    def test_textspeak_user(self):
        self._seed(9507, ["lol idk rn tbh"] * bot.STYLE_MIN_MSGS)
        note = bot._user_style_note(9507)
        assert "textspeak" in note

    def test_bracket_tagged_messages_excluded(self):
        # [sent ...] / heartbeat-style synthetic entries aren't the user's own texting.
        self._seed(9508, ["[sent 10:00]"] * bot.STYLE_MIN_MSGS)
        assert bot._user_style_note(9508) == ""

    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setattr(bot, "STYLE_MIRROR", False)
        self._seed(9509, ["yo"] * bot.STYLE_MIN_MSGS)
        assert bot._user_style_note(9509) == ""

    def test_assemble_messages_includes_the_note_when_enabled(self):
        self._seed(9510, ["yo"] * bot.STYLE_MIN_MSGS)
        msgs = bot.assemble_messages(9510, "hello")
        assert any("texting style" in (m.get("content") or "") for m in msgs)

    def test_assemble_messages_omits_the_note_when_disabled(self, monkeypatch):
        monkeypatch.setattr(bot, "STYLE_MIRROR", False)
        self._seed(9511, ["yo"] * bot.STYLE_MIN_MSGS)
        msgs = bot.assemble_messages(9511, "hello")
        assert not any("texting style" in (m.get("content") or "") for m in msgs)


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

    def test_eight_optional_blocks_marked(self):
        # 7 pre-existing + triggered_episode (2026-08-04, episodic recall).
        assert self._assembled().count("_sys_opt(") == 8

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
        _c, _r, hint, _clothing, _m = bot.extract_tags(text)
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

    def test_rules_carry_the_constraints_the_image_models_need(self, monkeypatch):
        """Regression guards: extra limbs (Flux/Kontext) and Gemini's safety filter,
        which returns blacked-out images without an explicit SFW/clothed signal.

        WIDENED v2026-08-08.2: this asserted "Fully clothed, SFW." lived inside
        _SELFIE_REALISM_RULE. v2026-08-08.1 split clothing out of the realism rule into
        _SELFIE_CLOTHING_SFW/_NSFW, so the assertion pinned a constant that no longer
        owns the signal and went red while the guarantee itself still held. Assert the
        guarantee where it actually matters -- the assembled prompt -- and cover BOTH
        SFW paths, since the override path is new and had no coverage at all.
        """
        assert "No extra limbs." in bot._SELFIE_ANATOMY_RULE

        monkeypatch.setattr(bot, "SELFIE_NSFW", False)
        # Default path: no [clothing:] tag, so the SFW clothing default must carry it.
        assert "fully clothed" in bot.build_selfie_prompt("on the fire escape", None).lower()
        # Override path: the character named an outfit, so the explicit "fully clothed"
        # wording is gone by design -- an SFW signal must still reach the model.
        override = bot.build_selfie_prompt(
            "on the fire escape", None, clothing_override="a green raincoat"
        )
        assert "tasteful" in override.lower()


class TestSelfieCapabilityLineSFWSignal:
    """v2026-08-08.1 removed the word "SFW" from the selfie capability line while adding
    the clothing tag -- unconditionally, not gated on SELFIE_NSFW, and unmentioned in its
    changelog. On a default instance that deleted the only SFW instruction the character
    ever sees. Restored in v2026-08-08.2 and pinned here."""

    def _selfie_line(self, monkeypatch, nsfw):
        monkeypatch.setattr(bot, "selfie_ready", lambda: True)
        monkeypatch.setattr(bot, "SELFIE_NSFW", nsfw)
        msgs = bot.assemble_messages(918273, "hello")
        blob = "\n".join(m.get("content") or "" for m in msgs if isinstance(m.get("content"), str))
        line = [ln for ln in blob.splitlines() if ln.startswith("- Send a selfie when it fits")]
        assert line, "selfie capability line missing entirely"
        return line[0]

    def test_sfw_instance_is_told_to_keep_it_sfw(self, monkeypatch):
        assert "SFW" in self._selfie_line(monkeypatch, False)

    def test_nsfw_instance_is_not(self, monkeypatch):
        assert "SFW" not in self._selfie_line(monkeypatch, True)

    def test_clothing_tag_is_documented_either_way(self, monkeypatch):
        for nsfw in (False, True):
            assert "clothing:" in self._selfie_line(monkeypatch, nsfw)


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

    # Per-handler gating dropped (ponytail-audit cleanup, CHANGELOG): _private_gate
    # (group -1) already stops a disallowed caller before dupefacts_cmd ever runs, and
    # the per-handler `_is_allowed` check duplicated it as dead code. Gating is
    # covered by TestPrivateGate now, not here.


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
        self._lock = bot.SELFIE_FACE_LOCK
        self._has_base = bot._has_base_image
        self._wardrobe = dict(bot.wardrobe)
        bot.SELFIE_IDENTITY_GUARD = True
        bot.SELFIE_FACE_LOCK = True
        bot._has_base_image = lambda: True
        bot._weather_cache["text"] = "55°F, overcast, wind 6mph"
        bot._weather_cache["ts"] = 9e9
        bot.wardrobe.clear(); bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot.SELFIE_IDENTITY_GUARD = self._guard
        bot.SELFIE_FACE_LOCK = self._lock
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
        all seven. Same character-bleed family as the courier jacket (v2026-08-01.8).

        WIDENED v2026-08-03.2: this read build_selfie_prompt's source and nothing else, so
        a trait living in one of the appended _SELFIE_*_RULE constants escaped it entirely
        -- and .2 adds two more such constants. Scans their VALUES (not their source), so
        the surrounding comments, which have to name the traits to explain them, are out of
        scope for the same reason as C14."""
        import inspect
        shared = [inspect.getsource(bot.build_selfie_prompt)] + [
            bot._SELFIE_ANATOMY_RULE, bot._SELFIE_REALISM_RULE, bot._SELFIE_IDENTITY_TAIL,
            bot._SELFIE_PRESERVE_RULE, bot._SELFIE_FACE_CLARITY_RULE, bot._SELFIE_CHANGE_SCOPE,
        ]
        for trait in ("freckles", "septum", "tattoo", "blonde", "half-shaved"):
            for text in shared:
                assert trait not in text.lower(), trait


class TestSelfieProviderLabel:
    """v2026-08-03.6: /audit said 'gemini' and nothing else, while the NanoGPT branch named
    its model. GEMINI_IMAGE_MODEL is per-instance and changes without a code deploy, so the
    one field you check after changing it was the one field not reported."""

    def setup_method(self):
        self._saved = (bot.SELFIE_PROVIDER, bot.GEMINI_IMAGE_MODEL,
                       bot.GEMINI_RESPONSE_MODALITIES, bot.SELFIE_MODEL, bot.XAI_IMAGE_MODEL)

    def teardown_method(self):
        (bot.SELFIE_PROVIDER, bot.GEMINI_IMAGE_MODEL,
         bot.GEMINI_RESPONSE_MODALITIES, bot.SELFIE_MODEL, bot.XAI_IMAGE_MODEL) = self._saved

    def test_gemini_names_its_model(self):
        bot.SELFIE_PROVIDER = "gemini"
        bot.GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"
        bot.GEMINI_RESPONSE_MODALITIES = ["TEXT", "IMAGE"]
        label = bot._selfie_provider_label()
        assert "gemini-3-pro-image-preview" in label
        assert "TEXT+IMAGE" in label

    def test_nanogpt_still_names_its_model(self):
        bot.SELFIE_PROVIDER = "nanogpt"
        bot.SELFIE_MODEL = "flux-kontext"
        assert bot._selfie_provider_label() == "nanogpt (flux-kontext)"

    def test_xai_names_its_model(self):
        bot.SELFIE_PROVIDER = "xai"
        bot.XAI_IMAGE_MODEL = "grok-imagine-image-quality"
        assert bot._selfie_provider_label() == "xai (grok-imagine-image-quality)"

    def test_audit_payload_and_startup_line_use_the_same_label(self):
        """Two surfaces, one value -- they disagreed once already (v2026-08-02.1)."""
        import inspect
        src = inspect.getsource(bot._log_startup_diagnostic)
        assert "_selfie_provider_label()" in src
        assert "Selfie model: %s" in src


class TestGeminiResponseModalities:
    """v2026-08-03.5: GEMINI_IMAGE_MODEL was env-tunable but responseModalities was hardcoded
    to ["IMAGE"], and gemini-3-pro-image-preview requires ["TEXT","IMAGE"] — so switching to
    the Pro model by .env alone could not work. The knob existed for the model and not for
    what the model demands."""

    def setup_method(self):
        self._mods = bot.GEMINI_RESPONSE_MODALITIES
        self._post = bot._post_with_retries
        self._has_base = bot._has_base_image
        bot._has_base_image = lambda: False

    def teardown_method(self):
        bot.GEMINI_RESPONSE_MODALITIES = self._mods
        bot._post_with_retries = self._post
        bot._has_base_image = self._has_base

    def test_default_is_image_only(self):
        assert bot._parse_modalities("IMAGE") == ["IMAGE"]

    def test_the_pro_pair_parses(self):
        assert bot._parse_modalities("TEXT,IMAGE") == ["TEXT", "IMAGE"]

    def test_whitespace_and_case_are_tolerated(self):
        """.env values are hand-typed; ' text , image ' must not become a 400."""
        assert bot._parse_modalities(" text , image ") == ["TEXT", "IMAGE"]

    def test_empty_never_yields_an_empty_list(self):
        """An empty responseModalities is a 400, so a blank env value must not produce one."""
        for raw in ("", "   ", ",,", None):
            assert bot._parse_modalities(raw) == ["IMAGE"], raw

    def _capture_payload(self, parts):
        sent = {}

        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"candidates": [{"finishReason": "STOP", "content": {"parts": parts}}]}

        def _fake_post(url, **kw):
            sent.update(kw.get("json") or {})
            return _R()

        bot._post_with_retries = _fake_post
        return sent

    def test_configured_modalities_reach_the_payload(self):
        """The regression that matters: the value is read at call time, not baked in."""
        import base64
        sent = self._capture_payload([{"inlineData": {"data": base64.b64encode(b"png").decode()}}])
        bot.GEMINI_RESPONSE_MODALITIES = ["TEXT", "IMAGE"]
        assert bot._generate_selfie_gemini("x") == b"png"
        assert sent["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]

    def test_a_text_only_answer_surfaces_what_it_said(self):
        """With TEXT enabled a refusal arrives as prose that says why; discarding it left
        'no image data' as the only clue."""
        self._capture_payload([{"text": "I can't create that image."}])
        try:
            bot._generate_selfie_gemini("x")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "I can't create that image." in str(e)

    def test_image_still_wins_when_text_accompanies_it(self):
        import base64
        self._capture_payload([{"text": "Here you go"},
                               {"inlineData": {"data": base64.b64encode(b"png").decode()}}])
        assert bot._generate_selfie_gemini("x") == b"png"


class TestXaiAspectRatio:
    """SELFIE_SIZE is a "WxH" pixel string (the NanoGPT convention); xAI's images API
    takes a ratio instead. Reduced by GCD so any per-instance SELFIE_SIZE carries over."""

    def test_square_reduces_to_1_1(self):
        assert bot._xai_aspect_ratio("1024x1024") == "1:1"

    def test_portrait_reduces(self):
        assert bot._xai_aspect_ratio("768x1024") == "3:4"

    def test_landscape_reduces(self):
        assert bot._xai_aspect_ratio("1024x768") == "4:3"

    def test_garbage_falls_back_to_square(self):
        for bad in ("", "not-a-size", "0x0", "1024", None):
            assert bot._xai_aspect_ratio(bad) == "1:1", bad


class TestGenerateSelfieXai:
    """SELFIE_PROVIDER=xai calls xAI's Grok Imagine API directly. Mirrors the shape of
    TestGeminiResponseModalities's payload/response tests for the other two providers."""

    def setup_method(self):
        self._post = bot._post_with_retries
        self._get = bot._get_with_retries
        self._has_base = bot._has_base_image
        self._base_url = bot._base_data_url
        self._key = bot.XAI_API_KEY
        self._model = bot.XAI_IMAGE_MODEL
        self._url = bot.XAI_IMAGE_URL
        bot._has_base_image = lambda: False
        bot.XAI_API_KEY = "test-key"
        bot.XAI_IMAGE_MODEL = "grok-imagine-image-quality"

    def teardown_method(self):
        bot._post_with_retries = self._post
        bot._get_with_retries = self._get
        bot._has_base_image = self._has_base
        bot._base_data_url = self._base_url
        bot.XAI_API_KEY = self._key
        bot.XAI_IMAGE_MODEL = self._model
        bot.XAI_IMAGE_URL = self._url

    def _capture_post(self, response_json):
        sent = {}

        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return response_json

        def _fake_post(url, **kw):
            sent["url"] = url
            sent["json"] = kw.get("json") or {}
            return _R()

        bot._post_with_retries = _fake_post
        return sent

    def test_generations_endpoint_used_without_a_base_photo(self):
        import base64
        sent = self._capture_post({"data": [{"b64_json": base64.b64encode(b"png").decode()}]})
        assert bot._generate_selfie_xai("a selfie") == b"png"
        assert sent["url"] == f"{bot.XAI_IMAGE_URL}/generations"
        assert "image" not in sent["json"]
        assert sent["json"]["model"] == "grok-imagine-image-quality"

    def test_edits_endpoint_used_with_a_base_photo(self):
        import base64
        bot._has_base_image = lambda: True
        bot._base_data_url = lambda: "data:image/png;base64,YWJj"
        sent = self._capture_post({"data": [{"b64_json": base64.b64encode(b"png").decode()}]})
        assert bot._generate_selfie_xai("a selfie") == b"png"
        assert sent["url"] == f"{bot.XAI_IMAGE_URL}/edits"
        assert sent["json"]["image"] == {"url": "data:image/png;base64,YWJj", "type": "image_url"}

    def test_b64_json_with_a_data_uri_prefix_is_still_decoded(self):
        """Seen inconsistently in the wild: some responses put the full data URI in
        b64_json instead of raw base64. Decoding must not choke on the prefix."""
        import base64
        raw_b64 = base64.b64encode(b"png").decode()
        sent = self._capture_post({"data": [{"b64_json": f"data:image/png;base64,{raw_b64}"}]})
        assert bot._generate_selfie_xai("a selfie") == b"png"

    def test_falls_back_to_url_when_no_b64_json(self):
        sent = self._capture_post({"data": [{"url": "https://example.com/img.png"}]})

        class _Img:
            content = b"fromurl"
            def raise_for_status(self): pass

        bot._get_with_retries = lambda *a, **kw: _Img()
        assert bot._generate_selfie_xai("a selfie") == b"fromurl"

    def test_neither_field_raises(self):
        self._capture_post({"data": [{}]})
        try:
            bot._generate_selfie_xai("a selfie")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "neither b64_json nor url" in str(e)

    def test_dispatcher_routes_xai_to_xai(self):
        import base64
        saved = bot.SELFIE_PROVIDER
        try:
            bot.SELFIE_PROVIDER = "xai"
            self._capture_post({"data": [{"b64_json": base64.b64encode(b"png").decode()}]})
            assert bot.generate_selfie_image("x") == b"png"
        finally:
            bot.SELFIE_PROVIDER = saved


class TestImageRetryOnTransientStatus:
    """v2026-08-03.4: a Gemini 503 was a failed selfie. `requests` does not raise on 5xx, so
    the response came back normally, sailed past the transport-only except clause, and only
    became an error at raise_for_status() one frame up — where nothing retried it."""

    def setup_method(self):
        self._sleep = bot.time.sleep
        self._session = bot._get_session
        self._flag = bot.IMAGE_RETRY_TRANSIENT
        self.slept = []
        bot.time.sleep = self.slept.append
        bot.IMAGE_RETRY_TRANSIENT = True

    def teardown_method(self):
        bot.time.sleep = self._sleep
        bot._get_session = self._session
        bot.IMAGE_RETRY_TRANSIENT = self._flag

    class _Resp:
        def __init__(self, code, retry_after=None):
            self.status_code = code
            self.headers = {"Retry-After": retry_after} if retry_after else {}

    def _session_returning(self, codes):
        """A session whose post() yields the given statuses in order."""
        seq = list(codes)
        calls = []

        class _S:
            def post(_self, url, **kw):
                calls.append(url)
                return TestImageRetryOnTransientStatus._Resp(seq[len(calls) - 1])
            get = post

        bot._get_session = lambda: _S()
        return calls

    def test_503_is_retried_then_succeeds(self):
        calls = self._session_returning([503, 503, 200])
        assert bot._post_with_retries("http://x").status_code == 200
        assert len(calls) == 3

    def test_a_persistent_503_returns_the_response_not_an_exception(self):
        """raise_for_status() in the caller stays the single place HTTP becomes an error."""
        calls = self._session_returning([503, 503, 503])
        assert bot._post_with_retries("http://x").status_code == 503
        assert len(calls) == bot._IMAGE_RETRIES

    def test_400_is_not_retried(self):
        """A bad prompt or bad key is ours; retrying only delays the real error."""
        calls = self._session_returning([400, 200, 200])
        assert bot._post_with_retries("http://x").status_code == 400
        assert len(calls) == 1

    def test_every_retryable_status_is_covered(self):
        for code in (429, 500, 502, 503, 504):
            calls = self._session_returning([code, 200])
            assert bot._post_with_retries("http://x").status_code == 200, code
            assert len(calls) == 2, code

    def test_get_shares_the_same_loop(self):
        calls = self._session_returning([502, 200])
        assert bot._get_with_retries("http://x").status_code == 200
        assert len(calls) == 2

    def test_kill_switch_restores_transport_only_retries(self):
        bot.IMAGE_RETRY_TRANSIENT = False
        calls = self._session_returning([503, 200])
        assert bot._post_with_retries("http://x").status_code == 503
        assert len(calls) == 1

    def test_retry_after_is_honored_within_the_cap(self):
        assert bot._retry_delay(0, self._Resp(429, "5")) == 5.0

    def test_absurd_retry_after_falls_back_to_the_ramp(self):
        """A hostile or absurd header must not stall the handler."""
        assert bot._retry_delay(0, self._Resp(429, "9999")) == 2.0
        assert bot._retry_delay(0, self._Resp(429, "not-a-number")) == 2.0

    def test_transient_error_gets_plain_words_not_a_url(self):
        class _E(Exception):
            response = TestImageRetryOnTransientStatus._Resp(503)
        text = bot._media_error_text("📷", _E("503 Server Error: Service Unavailable for url: https://..."))
        assert "busy right now (HTTP 503)" in text
        assert "https://" not in text

    def test_unfamiliar_errors_keep_their_details(self):
        """An unrecognised failure is exactly when the raw text matters."""
        assert "boom" in bot._media_error_text("📷", RuntimeError("boom"))


class TestSelfieFaceLock:
    """v2026-08-03.2: Emily's selfies came back as a different, better-looking woman with
    her glasses gone, with the reference photo correctly attached. Two prompt shapes let an
    edit model rebuild the face rather than copy it -- the appearance paragraph sat inside
    the identity sentence as a spec it could satisfy with an invented face, and 'keep her
    face identical' never said which parts of a face."""

    def setup_method(self):
        self._weather = dict(bot._weather_cache)
        self._lock = bot.SELFIE_FACE_LOCK
        self._guard = bot.SELFIE_IDENTITY_GUARD
        self._has_base = bot._has_base_image
        self._wardrobe = dict(bot.wardrobe)
        self._mood_vibe = bot._mood_vibe
        bot.SELFIE_FACE_LOCK = True
        bot.SELFIE_IDENTITY_GUARD = True
        bot._has_base_image = lambda: True
        bot._weather_cache["text"] = "55°F, overcast, wind 6mph"
        bot._weather_cache["ts"] = 9e9
        bot.wardrobe.clear(); bot.wardrobe.update({"outfits": [], "current": None})

    def teardown_method(self):
        bot.SELFIE_FACE_LOCK = self._lock
        bot.SELFIE_IDENTITY_GUARD = self._guard
        bot._mood_vibe = self._mood_vibe
        bot._recent_selfie_hints.pop(901, None)
        bot._has_base_image = self._has_base
        bot._weather_cache.clear(); bot._weather_cache.update(self._weather)
        bot.wardrobe.clear(); bot.wardrobe.update(self._wardrobe)

    def _prompts(self, n=60, chat_id=None):
        import random
        out = []
        for seed in range(n):
            random.seed(seed)
            out.append(bot.build_selfie_prompt("", chat_id))
        return out

    def test_appearance_text_is_ranked_below_the_photo(self):
        """The regression that matters: appearance.txt back inside the identity sentence,
        where it reads as a person to draw rather than context about one to copy."""
        for p in self._prompts():
            assert "the photo outranks every word of it" in p
            assert f"new pose/setting. She's {bot.NAME}" not in p

    def test_the_face_rules_are_appended_when_a_reference_is_attached(self):
        for p in self._prompts():
            assert bot._SELFIE_PRESERVE_RULE in p
            assert bot._SELFIE_FACE_CLARITY_RULE in p
            assert bot._SELFIE_CHANGE_SCOPE in p

    def test_identity_tail_still_has_the_last_word(self):
        """The face rules are appended in the same region as the tail; the tail stays last
        because it is the shortest, most direct statement of the constraint."""
        bot._recent_selfie_hints[778] = ["on the fire escape", "at the counter"]
        try:
            for p in self._prompts(chat_id=778):
                assert p.rstrip().endswith(bot._SELFIE_IDENTITY_TAIL)
                assert p.index(bot._SELFIE_PRESERVE_RULE) > p.index("avoid recreating")
        finally:
            bot._recent_selfie_hints.pop(778, None)

    def test_nothing_is_added_without_a_reference_photo(self):
        """'Copy her face out of the reference photo' with no photo attached is an
        instruction to copy nothing -- the same reason the identity tail is gated."""
        bot._has_base_image = lambda: False
        for p in self._prompts():
            assert bot._SELFIE_PRESERVE_RULE not in p
            assert bot._SELFIE_FACE_CLARITY_RULE not in p
            assert bot._SELFIE_CHANGE_SCOPE not in p
            assert "the photo outranks" not in p

    def test_kill_switch_restores_the_previous_prompt(self):
        bot.SELFIE_FACE_LOCK = False
        for p in self._prompts():
            assert bot._SELFIE_PRESERVE_RULE not in p
            assert bot._SELFIE_FACE_CLARITY_RULE not in p
            assert "the photo outranks" not in p
            assert f"new pose/setting. She's {bot.NAME}" in p
            assert "New shot:" in p

    def test_mood_line_stops_instructing_a_face_edit(self):
        """v2026-08-03.3: `let it read in her face` was the only instruction in the prompt
        telling the model to modify her face, ~1500 chars ahead of the rules saying copy it.
        Production always passes a chat_id, so it was in every live selfie -- and in none of
        the 22 A/B images, because the preview tool passed chat_id=None."""
        for p in self._prompts(chat_id=901):
            assert "let it read in her face" not in p
            assert "how she's holding herself" in p

    def test_mood_itself_is_not_lost(self):
        """The mood still has to reach the image -- the fix is the verb, not the feature."""
        bot._mood_vibe = lambda _cid: "wistful [vibe: nostalgic]"
        for p in self._prompts(chat_id=901):
            assert "Her mood right now: wistful [vibe: nostalgic]" in p

    def test_text_only_instances_keep_the_old_mood_wording(self):
        """With no reference photo there is no preserved face for it to contradict."""
        bot._has_base_image = lambda: False
        for p in self._prompts(chat_id=901):
            assert "let it read in her face" in p

    def test_mood_kill_switch_restores_the_old_wording(self):
        bot.SELFIE_FACE_LOCK = False
        for p in self._prompts(chat_id=901):
            assert "let it read in her face" in p

    def test_eyewear_is_stated_both_ways_never_asserted(self):
        """The rule is shared by all seven. Asserting glasses would put them on characters
        who do not wear any -- the character-bleed trap, one release after the last one."""
        rule = bot._SELFIE_PRESERVE_RULE.lower()
        assert "if she is wearing glasses" in rule
        assert "if she is wearing none, add none" in rule

    def test_clarity_rule_does_not_contradict_the_framing_pools(self):
        """A face-size demand would fight the half-in-frame and wider draws, and a prompt
        that contradicts itself hands back the latitude this is removing."""
        low = bot._SELFIE_FACE_CLARITY_RULE.lower()
        for demand in ("large in frame", "fills the frame", "close-up", "centred", "centered"):
            assert demand not in low, demand


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
        """Scope widened in v2026-08-09.1, deliberately: the line now also carries pixel
        dimensions, so an exact-equality assertion no longer expresses what this test is
        for. "Quiet" means no warning — no AUTODETECTED, no TEXT-ONLY, no UNREADABLE —
        and that is now asserted directly instead of implied by the equality. It also
        writes a REAL png, so the dimension path is exercised rather than the failure
        branch a fake header would take."""
        from PIL import Image
        Image.new("RGB", (900, 1200), (40, 80, 120)).save(self._dir / "priya_base.png")
        status = bot._base_image_status()
        assert status == "priya_base.png 900×1200"
        for noise in ("AUTODETECTED", "TEXT-ONLY", "UNREADABLE", ".env"):
            assert noise not in status


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
        """'nanogpt' alone doesn't say flux-kontext, which is the part that matters.

        REWRITTEN v2026-08-03.6, not loosened: this read `gather_audit_data`'s SOURCE for the
        strings "SELFIE_MODEL" and "nanogpt", so it went red the moment that logic moved into
        `_selfie_provider_label()` — while the behavior it is named for was still correct. A
        source assertion cannot fail for the reason the test exists; that is the family that
        shipped the `/features` ValueError past twelve green tests (v2026-08-02.4). It now
        calls the function and checks the rendered value."""
        saved = (bot.SELFIE_PROVIDER, bot.SELFIE_MODEL)
        try:
            bot.SELFIE_PROVIDER, bot.SELFIE_MODEL = "nanogpt", "flux-kontext"
            assert bot.gather_audit_data()["selfie_provider"] == "nanogpt (flux-kontext)"
        finally:
            bot.SELFIE_PROVIDER, bot.SELFIE_MODEL = saved

    def test_xai_reports_the_model_too(self):
        saved = (bot.SELFIE_PROVIDER, bot.XAI_IMAGE_MODEL)
        try:
            bot.SELFIE_PROVIDER, bot.XAI_IMAGE_MODEL = "xai", "grok-imagine-image"
            assert bot.gather_audit_data()["selfie_provider"] == "xai (grok-imagine-image)"
        finally:
            bot.SELFIE_PROVIDER, bot.XAI_IMAGE_MODEL = saved

    def test_value_is_a_non_empty_string(self):
        v = bot.gather_audit_data()["selfie_provider"]
        assert isinstance(v, str) and v


class TestGifTagAndFiltering:
    """v2026-08-02.6: [gif: query] search via Giphy. Tenor was the original plan until
    research showed Google terminated its API on 2026-06-30. Giphy's `rating` is
    cumulative and its own issue tracker reports it returning mixed ratings, so the local
    deny-list is load-bearing rather than a backstop."""

    def setup_method(self):
        self._saved = dict(bot.gif_prefs)
        self._cache = dict(bot._gif_taste_cache)
        bot._gif_taste_cache.update({"mtime": None, "likes": (), "bans": ()})

    def teardown_method(self):
        bot.gif_prefs.clear(); bot.gif_prefs.update(self._saved)
        bot._gif_taste_cache.clear(); bot._gif_taste_cache.update(self._cache)

    # --- the leak trap ---
    def test_gif_tag_is_stripped_from_user_facing_text(self):
        """An unregistered tag reaches the user verbatim -- v2026-07-29.1, and the
        [setbase: 60F, clear...] leak on 2026-08-02."""
        clean, *_ = bot.extract_tags("that's the worst thing i've heard [gif: disgusted recoil]")
        assert "[gif:" not in clean and "disgusted" not in clean
        assert clean == "that's the worst thing i've heard"

    def test_query_is_readable_before_stripping(self):
        assert bot._gif_query("ha [gif: derby wipeout] classic") == "derby wipeout"
        assert bot._gif_query("no tag here") is None

    def test_extract_tags_still_returns_five_values(self):
        """The 5-tuple contract is pinned (clothing_override added v2026-08-08.1);
        [gif:] rides alongside like [search:] does."""
        out = bot.extract_tags("hi [gif: x]")
        assert len(out) == 5

    # --- safety ---
    def test_rating_map_offers_only_three_levels_and_never_r(self):
        assert set(bot._GIF_RATING) == {"high", "medium", "low"}
        assert "r" not in set(bot._GIF_RATING.values())
        assert bot._GIF_RATING["high"] == "g"

    def test_denylist_blocks_regardless_of_safety_level(self):
        for term in ("nsfw", "porn", "nude", "hentai", "gore"):
            assert bot._gif_blocked(f"funny {term} reaction", ()), term

    def test_denylist_does_not_eat_ordinary_phrases(self):
        """A false positive costs one GIF; the list still has to be usable."""
        for ok in ("killing it at work", "shooting hoops", "class dismissed",
                   "blood orange juice", "passing the ball"):
            assert not bot._gif_blocked(ok, ()), ok

    def test_instance_ban_terms_are_honoured(self):
        assert bot._gif_blocked("a clown car", ("clown",))
        assert not bot._gif_blocked("a clown car", ("mime",))

    def test_empty_ban_term_does_not_block_everything(self):
        """A blank line in gifs.txt must not ban every GIF."""
        assert not bot._gif_blocked("anything at all", ("",))

    # --- degradation ---
    def test_not_ready_without_an_api_key(self):
        saved = bot.GIPHY_API_KEY
        try:
            bot.GIPHY_API_KEY = ""
            assert bot.gif_ready() is False
        finally:
            bot.GIPHY_API_KEY = saved

    def test_kill_switch_disables_it(self):
        saved = (bot.GIF_ENABLED, bot.GIPHY_API_KEY)
        try:
            bot.GIF_ENABLED, bot.GIPHY_API_KEY = False, "k"
            assert bot.gif_ready() is False
        finally:
            bot.GIF_ENABLED, bot.GIPHY_API_KEY = saved

    def test_unknown_persisted_safety_falls_back_to_high(self):
        """An unrecognised value must fail safe, never open."""
        bot.gif_prefs["safety"] = "off"
        bot.load_gif_prefs()
        assert bot.gif_prefs["safety"] == "high"

    def test_command_is_registered_and_in_the_menu(self):
        import inspect
        assert 'CommandHandler("gifsafety"' in inspect.getsource(bot.main)
        assert any(c.command == "gifsafety" for c in bot._build_command_menu(False, False))

    def test_no_new_llm_call_in_the_gif_path(self):
        """Invariant #3: it rides the reply that already happened."""
        import inspect
        src = inspect.getsource(bot.send_gif) + inspect.getsource(bot._giphy_search)
        for banned in ("call_nanogpt", "generate_reply", "_do_request"):
            assert banned not in src, banned

    def test_search_runs_off_the_event_loop(self):
        """Invariant #8: no bare requests in an async handler."""
        import inspect
        assert "asyncio.to_thread" in inspect.getsource(bot.send_gif)


class TestGifCommandAndRedaction:
    """v2026-08-02.7: /gif is the parity command for /selfie and /meme, and the only way
    to distinguish a working Giphy path from a silent one. Adding it surfaced a real leak:
    Giphy takes api_key as a QUERY PARAMETER, so a requests exception carries it in the
    URL, and /errors echoes errors.log into Telegram."""

    def test_api_key_is_redacted_from_exception_text(self):
        raw = "HTTPError: 401 for https://api.giphy.com/v1/gifs/search?api_key=sk_live_SECRET123&q=hi"
        out = bot._redact_key(raw)
        assert "sk_live_SECRET123" not in out
        assert "api_key=<redacted>" in out
        assert "q=hi" in out          # the useful part survives

    def test_redaction_handles_bare_key_param_too(self):
        assert "SECRET" not in bot._redact_key("https://x/api?key=SECRET&b=1")

    def test_both_failure_paths_redact(self):
        import inspect
        src = inspect.getsource(bot.send_gif)
        assert src.count("_redact_key") >= 2, "search and send paths must both redact"

    def test_user_facing_errors_carry_no_exception_text(self):
        """no-exception-leak: details stay in the log, the chat gets a generic line."""
        import inspect
        src = inspect.getsource(bot.send_gif)
        for line in src.splitlines():
            if "_say(" in line:
                assert "{e}" not in line and "str(e)" not in line, line

    def test_auto_path_stays_silent_by_default(self):
        import inspect
        sig = inspect.signature(bot.send_gif)
        assert sig.parameters["announce_errors"].default is False

    def test_gif_command_announces_errors(self):
        """A manual command that silently does nothing is indistinguishable from broken."""
        import inspect
        assert "announce_errors=True" in inspect.getsource(bot.gif_cmd)

    def test_gif_command_is_admin_gated_registered_and_in_menu(self):
        import inspect
        assert "_is_admin" in inspect.getsource(bot.gif_cmd)
        assert 'CommandHandler("gif", gif_cmd)' in inspect.getsource(bot.main)
        assert any(c.command == "gif" for c in bot._build_command_menu(False, False))

    def test_distinguishes_no_key_from_no_results(self):
        """The two failures need different fixes, so they must not read the same."""
        src = inspect.getsource(bot.send_gif) if (inspect := __import__("inspect")) else ""
        assert "GIPHY_API_KEY set" in src and "got past the" in src


class TestMediaOfferChances:
    """v2026-08-02.8: GIF_CHANCE/MEME_CHANCE gate whether she is OFFERED the option in a
    given reply, never whether an emitted tag is honoured. Dropping a tag after the fact
    would leave her text referring to an image that never arrives."""

    def test_the_gate_is_on_the_offer_not_the_send(self):
        """send_gif/send_meme must contain no probability roll -- only the prompt does."""
        import inspect
        for fn in (bot.send_gif, bot.send_meme):
            src = inspect.getsource(fn)
            assert "GIF_CHANCE" not in src and "MEME_CHANCE" not in src, fn.__name__

    def test_chances_are_read_from_env_with_defaults(self):
        assert 0.0 <= bot.GIF_CHANCE <= 1.0
        assert 0.0 <= bot.MEME_CHANCE <= 1.0

    def test_asking_for_one_bypasses_the_dice(self):
        """Asking and being told no because of a coin flip is the worst outcome."""
        for msg in ("send me a gif", "got a GIF for that?", "jif please"):
            assert bot._ASKED_GIF.search(msg), msg
        for msg in ("make me a meme", "MEMES please"):
            assert bot._ASKED_MEME.search(msg), msg

    def test_ask_patterns_do_not_fire_on_unrelated_words(self):
        for msg in ("gifted me a book", "memento mori", "gifts for christmas"):
            assert not bot._ASKED_GIF.search(msg) or "gif" == msg, msg
            assert not bot._ASKED_MEME.search(msg), msg

    def test_both_offers_are_gated_in_the_prompt(self):
        import inspect
        src = inspect.getsource(bot.assemble_messages)
        assert "GIF_CHANCE" in src and "MEME_CHANCE" in src
        assert "_ASKED_GIF" in src and "_ASKED_MEME" in src

    def test_audit_reports_feature_readiness(self):
        """Third time this blind spot cost a round trip: selfie base, then the image
        backend, now whether meme/gif are live at all. v2026-08-02.9 widened the single
        media line into the full feature roster."""
        import inspect
        d = bot.gather_audit_data()
        assert "features" in d
        for name in ("meme=", "gif=", "selfie=", "voice="):
            assert name in d["features"], name
        assert "features" in inspect.getsource(bot.audit_cmd)

    def test_memes_are_fleet_wide_not_per_instance(self):
        """MEME_TEMPLATES_DIR resolves against bot.py, not the instance dir -- so meme
        support is all-or-nothing across all seven, not something one bot can have."""
        assert "__file__" in inspect.getsource(bot).split("MEME_TEMPLATES_DIR =")[1][:120] \
            if (inspect := __import__("inspect")) else False


class TestFeatureSwitches:
    """v2026-08-02.9: /features flips integrations at runtime without an SSH session.
    Each target is a plain module global read at call time, so flipping it reaches every
    call site untouched -- the mechanism /setmodel already uses."""

    def setup_method(self):
        self._flags = {n: getattr(bot, spec[0]) for n, spec in bot._FEATURES.items()}
        self._prefs = dict(bot.feature_prefs)
        self._save = bot.save_feature_prefs
        bot.save_feature_prefs = lambda: None

    def teardown_method(self):
        for n, v in self._flags.items():
            setattr(bot, bot._FEATURES[n][0], v)
        bot.feature_prefs.clear(); bot.feature_prefs.update(self._prefs)
        bot.save_feature_prefs = self._save

    def test_capability_and_switch_are_separate(self):
        """'off' and 'never configured' need different fixes -- conflating them is what
        made three blind spots this week cost a round trip each."""
        for name in bot._FEATURES:
            on, capable = bot._feature_state(name)
            assert isinstance(on, bool) and isinstance(capable, bool)
            if not capable:
                assert on is False, f"{name} cannot be on while incapable"

    def test_flipping_the_global_reaches_the_ready_function(self):
        """Capability is forced True: the test fixture has no selfie assets, so without
        this the assertion passes whether or not the switch is wired (caught by
        break-test, 2026-08-02 -- the same masking as C13)."""
        saved, cap = bot.SELFIE_ENABLED, bot.selfie_capable
        try:
            bot.selfie_capable = lambda: True
            bot.SELFIE_ENABLED = False
            assert bot.selfie_ready() is False
            bot.SELFIE_ENABLED = True
            assert bot.selfie_ready() is True
        finally:
            bot.SELFIE_ENABLED, bot.selfie_capable = saved, cap

    def test_meme_switch_is_independent_of_meme_assets(self):
        saved = bot.MEME_ENABLED
        try:
            bot.MEME_ENABLED = False
            assert bot.meme_ready() is False
            assert isinstance(bot.meme_capable(), bool)   # assets unchanged by the switch
        finally:
            bot.MEME_ENABLED = saved

    def test_voice_gate_is_at_the_send_choke_point(self):
        import inspect
        assert "VOICE_ENABLED" in inspect.getsource(bot._send_voice_reply)

    def test_persisted_prefs_are_applied_not_just_written(self):
        """A prefs file that is written and never read is worse than no file."""
        import inspect
        src = inspect.getsource(bot)
        assert "\nload_feature_prefs()\n" in src, "must be applied at module level"

    def test_prefs_cannot_enable_something_incapable(self):
        bot.feature_prefs["traffic"] = True
        bot.load_feature_prefs()
        on, capable = bot._feature_state("traffic")
        assert on is capable or on is False

    def test_summary_reports_na_for_unconfigured(self):
        out = bot._features_summary()
        assert all(f"{n}=" in out for n in bot._FEATURES)
        assert any(x in out for x in ("=on", "=off", "=n/a"))

    def test_seed_summary_names_only_what_is_missing(self):
        out = bot._seed_summary()
        assert out == "all present" or out.startswith("MISSING: ")

    def test_seed_check_follows_atlas_file_override(self, tmp_path, monkeypatch):
        """v2026-08-02.12: the check hardcoded "atlas.txt" while the loader honours
        ATLAS_FILE, so an instance pointing at another name (emily's places.txt) would
        be reported MISSING an atlas it in fact loads fine."""
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "ATLAS_FILE", tmp_path / "places.txt")
        for f in bot._SEED_FILES:
            (tmp_path / f).write_text("x", encoding="utf-8")
        assert bot._seed_summary().startswith("MISSING: places.txt")
        (tmp_path / "places.txt").write_text("x", encoding="utf-8")
        assert bot._seed_summary() == "all present"
        assert "atlas.txt" not in bot._SEED_FILES, "atlas is resolved, never assumed"

    def test_audit_carries_the_tier2_fields(self):
        d = bot.gather_audit_data()
        for k in ("features", "seeds", "owner", "timezone"):
            assert k in d, k

    def test_command_registered_gated_and_in_menu(self):
        import inspect
        src = inspect.getsource(bot.features_cmd)
        assert "_is_admin" in src
        assert 'CommandHandler("features"' in inspect.getsource(bot.main)
        assert any(c.command == "features" for c in bot._build_command_menu(False, False))


class TestFeatureDetailAndLocation:
    """v2026-08-02.10: "voice=on" was true on all seven and said nothing -- NanoGPT TTS
    works without Inworld, so the capability probe can only return True. Which backend is
    the actual question. Also adds Location, conspicuously absent given this whole session
    started with a weather bug and location is what drives weather."""

    def test_every_feature_spec_is_a_three_tuple(self):
        for name, spec in bot._FEATURES.items():
            assert len(spec) == 3, name
            assert isinstance(spec[0], str)
            assert callable(spec[1])
            assert spec[2] is None or callable(spec[2])

    def test_voice_reports_which_backend(self):
        saved = bot.INWORLD_API_KEY
        try:
            bot.INWORLD_API_KEY = "k"
            assert "voice=on(inworld)" in bot._features_summary()
            bot.INWORLD_API_KEY = ""
            assert "voice=on(nanogpt)" in bot._features_summary()
        finally:
            bot.INWORLD_API_KEY = saved

    def test_detail_is_omitted_when_the_feature_is_off(self):
        saved = bot.VOICE_ENABLED
        try:
            bot.VOICE_ENABLED = False
            out = bot._features_summary()
            assert "voice=off" in out and "voice=off(" not in out
        finally:
            bot.VOICE_ENABLED = saved

    def test_a_raising_detail_probe_does_not_break_the_summary(self):
        """The summary is diagnostic output -- it must never be the thing that fails."""
        saved = bot._FEATURES["meme"]
        try:
            bot._FEATURES["meme"] = (saved[0], saved[1], lambda: 1 / 0)
            assert "meme=" in bot._features_summary()
        finally:
            bot._FEATURES["meme"] = saved

    def test_location_is_reported(self):
        """Widened in v2026-08-10.4, in this class's own spirit: it exists because
        "location is what drives weather", and the coordinates are the part that actually
        does. The label alone hid jules fetching Seattle's weather under a Bellingham
        name for weeks, so the exact-equality assertion was pinning the wrong string."""
        import inspect
        d = bot.gather_audit_data()
        assert d["location"].startswith(bot.WEATHER_LOCATION)
        assert bot.WEATHER_LAT in d["location"] and bot.WEATHER_LON in d["location"]
        assert "location" in inspect.getsource(bot.audit_cmd)


class TestLifeArcRotation:
    """v2026-08-02.11: life.txt was commented 'user-maintained' and nothing ever wrote it,
    so a hand-seeded arc stayed frozen forever -- the owner noticed Bonnie's had not moved.
    day.txt already answers 'what happened today'; this is the slower thing underneath."""

    def _src(self):
        import inspect
        return inspect.getsource(bot._maybe_rotate_life_arc)

    def test_it_evolves_rather_than_replaces(self):
        """The current arc must be IN the prompt, or each rotation is a fresh invention."""
        src = self._src()
        assert "current" in src
        assert "EVOLUTION, not a replacement" in src
        assert "carry over" in src

    def test_only_one_thread_may_move(self):
        """An arc that turns over completely every week is not an arc."""
        assert "exactly ONE thing move" in self._src()

    def test_it_keeps_the_form(self):
        src = self._src()
        assert "present tense" in src and "40-60 words" in src

    def test_it_forbids_vague_filler(self):
        """'She has been reflecting on things' is the failure mode for this kind of prompt."""
        assert "reflecting" in self._src() and "concrete" in self._src().lower()

    def test_cadence_uses_a_stamp_not_a_weekday(self):
        """A weekday check skips the week entirely if the bot is down that night;
        a stamp just delays it."""
        src = self._src()
        assert "LIFE_STAMP_FILE" in src and "LIFE_ROTATE_DAYS" in src

    def test_first_run_stamps_and_waits(self):
        """Otherwise a fresh instance rewrites its seeded arc on the very first midnight."""
        assert "first run: stamp and wait" in self._src()

    def test_a_short_or_empty_result_keeps_the_existing_arc(self):
        """Never destroy a good arc because the model returned nothing useful."""
        src = self._src()
        assert "len(new) < 40" in src and "keeping the current arc" in src

    def test_the_old_arc_is_archived(self):
        assert 'life_{stamp}.txt' in self._src()

    def test_cache_is_invalidated_so_it_takes_effect(self):
        """_life_arc_cache has a 5-minute TTL; without this the new arc is invisible."""
        assert "_life_arc_cache" in self._src()

    def test_kill_switch_and_missing_file_both_short_circuit(self):
        assert "LIFE_ROTATE and LIFE_ARC_FILE.exists()" in self._src()

    def test_it_runs_off_the_event_loop(self):
        """Invariant #8 -- and invariant #3 is satisfied because this is weekly, not
        per-message."""
        assert "asyncio.to_thread" in self._src()

    def test_it_is_actually_called_from_the_midnight_job(self):
        """A rotation nothing invokes is the same bug as a life.txt nothing writes."""
        import inspect
        assert "_maybe_rotate_life_arc()" in inspect.getsource(bot._rotate_day_context)


# --- v2026-08-02.14: the /code-review batch -------------------------------------------
# Every test here EXERCISES the handler. The defects below all survived a green suite
# because the tests read the handler's source instead of calling it (C8, and the fourth
# time this family reached the fleet -- see v2026-08-02.4).

def _async_ret(value):
    async def _f(*a, **k):
        return value
    return _f


class TestFeaturesCmdActuallyFlips:
    """v2026-08-02.14: `_, probe = _FEATURES[name]` unpacked a 3-tuple into two names, so
    EVERY `/features <name> on|off` raised ValueError before reaching the flip. The switch
    never moved and the owner got silence. The suite was green: one test asserted the specs
    are 3-tuples, another read the handler's source for "_is_admin". Nothing called it."""

    def _run(self, args, uid=4242, feature_file=None):
        msg = SimpleNamespace(sent=[])

        async def reply_text(text, **k):
            msg.sent.append(text)

        msg.reply_text = reply_text
        update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=uid))
        asyncio.run(bot.features_cmd(update, SimpleNamespace(args=args)))
        return msg.sent

    def setup_method(self):
        self._orig_allowed = set(bot.ALLOWED_USERS)
        self._orig_prefs = dict(bot.feature_prefs)
        self._orig_voice = bot.VOICE_ENABLED
        self._orig_file = bot.FEATURE_PREFS_FILE
        bot.ALLOWED_USERS.add(4242)

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._orig_allowed)
        bot.feature_prefs.clear()
        bot.feature_prefs.update(self._orig_prefs)
        bot.VOICE_ENABLED = self._orig_voice
        bot.FEATURE_PREFS_FILE = self._orig_file

    def test_switching_off_moves_the_global_and_persists(self, tmp_path):
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        bot.VOICE_ENABLED = True
        sent = self._run(["voice", "off"])
        assert bot.VOICE_ENABLED is False, "the whole point of the command"
        assert bot.feature_prefs["voice"] is False
        assert json.loads(bot.FEATURE_PREFS_FILE.read_text())["voice"] is False
        assert "switched off" in sent[0]

    def test_switching_back_on_moves_it_back(self, tmp_path):
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        bot.VOICE_ENABLED = False
        self._run(["voice", "on"])
        assert bot.VOICE_ENABLED is True

    def test_it_still_refuses_what_the_instance_cannot_do(self, tmp_path):
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        sent = self._run(["health", "on"])  # no Garmin credentials in the fixture
        assert "isn't configured" in sent[0]
        assert bot.GARMIN_ENABLED is False

    def test_bare_listing_and_a_bare_name_both_answer(self, tmp_path):
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        assert self._run([])[0].startswith("\U0001F39B Features")
        assert "voice" in self._run(["voice"])[0]

    def test_the_listing_carries_the_same_detail_audit_does(self, tmp_path):
        """v2026-08-02.15: the command dedicated to features said less about them than
        /audit's one-line summary — `voice: on` against `voice=on(inworld)`. Which TTS
        backend is live is the actual question (v2026-08-02.10), and it was answerable
        only from the general audit."""
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        bot.VOICE_ENABLED = True
        saved = bot.INWORLD_API_KEY
        try:
            bot.INWORLD_API_KEY = "k"
            assert "voice: on (inworld)" in self._run([])[0]
            assert "voice=on(inworld)" in bot._features_summary(), "audit keeps its packing"
            bot.INWORLD_API_KEY = ""
            assert "voice: on (nanogpt)" in self._run([])[0]
        finally:
            bot.INWORLD_API_KEY = saved

    def test_a_switched_off_feature_shows_no_detail(self, tmp_path):
        """The detail describes what is running. Printing a backend beside `off` would
        claim something is live that isn't."""
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        bot.VOICE_ENABLED = False
        out = self._run([])[0]
        assert "voice: off" in out and "voice: off (" not in out

    def test_non_admin_gets_nothing(self, tmp_path):
        bot.FEATURE_PREFS_FILE = tmp_path / "feature_prefs.json"
        bot.ALLOWED_USERS.discard(4242)
        bot.set_owner(999999) if bot.get_owner() is None else None
        assert self._run(["voice", "off"], uid=4243) == []


class TestHealthAlertsFollowTheLiveSwitch:
    """v2026-08-02.14: STRESS/BB/RHR_ALERTS were computed as `GARMIN_ENABLED and <env>` at
    import. `/features health off` flips GARMIN_ENABLED, so the monitors kept firing off a
    frozen copy while /features and /audit both said health=off."""

    def setup_method(self):
        self._orig = bot.GARMIN_ENABLED

    def teardown_method(self):
        bot.GARMIN_ENABLED = self._orig

    def test_alerts_need_both_the_pref_and_the_live_feed(self):
        bot.GARMIN_ENABLED = True
        assert bot._alerts_on(True) is True
        assert bot._alerts_on(False) is False
        bot.GARMIN_ENABLED = False
        assert bot._alerts_on(True) is False

    def test_the_env_flags_no_longer_bake_in_the_parent(self):
        """If these fold GARMIN_ENABLED back in at import, the runtime switch is dead
        again and this whole class regresses silently."""
        import inspect
        src = inspect.getsource(bot).split("STRESS_ALERTS = ")[1].split("\n")[0]
        assert "GARMIN_ENABLED" not in src

    def test_every_monitor_gate_goes_through_the_helper(self):
        """A bare `if not STRESS_ALERTS` anywhere is the bug returning."""
        import inspect
        for fn in (bot.stress_monitor_job, bot.bb_monitor_job, bot.rhr_monitor_job,
                   bot._recent_stress_high, bot.stress_cmd):
            src = inspect.getsource(fn)
            for flag in ("STRESS_ALERTS", "BB_ALERTS", "RHR_ALERTS"):
                if flag in src:
                    assert f"_alerts_on({flag})" in src, fn.__name__

    def test_off_reason_names_the_runtime_switch(self):
        saved = (bot.GARMIN_EMAIL, bot.GARMIN_PASSWORD, bot._Garmin, bot.GARMIN_ENABLED)
        try:
            bot.GARMIN_EMAIL, bot.GARMIN_PASSWORD = "a@b.c", "pw"
            bot._Garmin = object()
            bot.GARMIN_ENABLED = False
            assert "/features health on" in bot._garmin_off_reason()
            bot.GARMIN_ENABLED = True
            assert bot._garmin_off_reason() == ""
        finally:
            (bot.GARMIN_EMAIL, bot.GARMIN_PASSWORD, bot._Garmin, bot.GARMIN_ENABLED) = saved

    def test_monitors_are_scheduled_on_capability_not_on_the_switch(self):
        """Registering under GARMIN_ENABLED made `off` a one-way trip until restart."""
        import inspect
        src = inspect.getsource(bot.main)
        assert "if GARMIN_EMAIL and GARMIN_PASSWORD and _Garmin is not None:" in src
        assert "if WSDOT_API_KEY:" in src


class TestOffVersusNeverConfigured:
    """v2026-08-02.9 split *_capable from *_ready precisely so these two states could be
    told apart; six commands still printed the credential sentence for both."""

    def test_helper_distinguishes_the_two(self):
        saved = bot.TOMTOM_API_KEY, bot.TOMTOM_ENABLED
        try:
            bot.TOMTOM_API_KEY = ""
            assert bot._feature_off_reason("maps", "MISSING", "Maps are") == "MISSING"
            bot.TOMTOM_API_KEY, bot.TOMTOM_ENABLED = "k", False
            out = bot._feature_off_reason("maps", "MISSING", "Maps are")
            assert "/features maps on" in out and "MISSING" not in out
        finally:
            bot.TOMTOM_API_KEY, bot.TOMTOM_ENABLED = saved

    def test_selfie_and_meme_report_the_switch_not_a_missing_file(self):
        import inspect
        for fn, cap in ((bot.send_selfie, "selfie_capable"), (bot.send_meme, "meme_capable")):
            src = inspect.getsource(fn)
            assert f"not {cap}()" in src, fn.__name__
            assert "switched off" in src, fn.__name__

    def test_no_command_still_hardcodes_the_credential_sentence(self):
        """The class check: every "isn't set up"/"aren't set up" string must now come from
        _feature_off_reason, not from a bare reply_text."""
        import inspect
        import re as _re
        src = inspect.getsource(bot)
        direct = _re.findall(r"reply_text\(\s*\"[^\"]*(?:aren't|isn't) set up[^\"]*\"", src)
        assert direct == [], direct


class TestTriggeredMessageDeliversTheGif:
    """v2026-08-02.14: send_triggered computed gif_query and never used it. A proactive
    message with a [gif:] tag dropped the GIF; a tag-only one sent nothing at all and
    stored an empty assistant turn, so the history gained a blank."""

    def _run(self, monkeypatch, reply_text):
        seen = {"bubbles": [], "gif": [], "remember": []}
        monkeypatch.setattr(bot, "ensure_weather", _async_ret(None))
        monkeypatch.setattr(bot, "assemble_messages", lambda cid, trig: [])
        monkeypatch.setattr(bot, "reply_with_typing", _async_ret(reply_text))

        async def _maybe_search(context, chat_id, messages, text, uname):
            return text

        monkeypatch.setattr(bot, "maybe_search", _maybe_search)

        async def _bubbles(context, chat_id, text, **k):
            seen["bubbles"].append(text)

        async def _gif(context, chat_id, query):
            seen["gif"].append(query)

        monkeypatch.setattr(bot, "send_bubbles", _bubbles)
        monkeypatch.setattr(bot, "send_gif", _gif)
        monkeypatch.setattr(bot, "maintain_memory", _async_ret(None))
        monkeypatch.setattr(bot, "remember",
                            lambda cid, role, text: seen["remember"].append((role, text)))
        asyncio.run(bot.send_triggered(None, 7788, "[SYSTEM: say hi]"))
        return seen

    def test_the_gif_is_actually_sent(self, monkeypatch):
        seen = self._run(monkeypatch, "look at this [gif: cat waving]")
        assert seen["gif"] == ["cat waving"]
        assert seen["bubbles"] == ["look at this"]

    def test_a_tag_only_message_is_not_an_empty_turn(self, monkeypatch):
        seen = self._run(monkeypatch, "[gif: raccoon panic]")
        assert seen["gif"] == ["raccoon panic"]
        assert ("assistant", "[sent a gif]") in seen["remember"]

    def test_a_plain_message_still_sends_no_gif(self, monkeypatch):
        seen = self._run(monkeypatch, "just a normal thought")
        assert seen["gif"] == []


class TestSetbaseBackupClaim:
    """v2026-08-02.14: the reply decided "previous kept as .prev" by stat-ing the path
    AFTER the write, so a leftover .prev from an earlier /setbase made a first-time
    install claim a backup of a file that was never there."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 9000

    def _run(self, tmp_path, monkeypatch, uid=4242):
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "x_base.png")
        bot.ALLOWED_USERS.add(uid)

        class _File:
            async def download_as_bytearray(self):
                return bytearray(TestSetbaseBackupClaim.PNG)

        class _Doc:
            mime_type = "image/png"

            async def get_file(self):
                return _File()

        sent = []

        async def reply_text(text, **k):
            sent.append(text)

        msg = SimpleNamespace(document=_Doc(), photo=None, reply_to_message=None,
                              reply_text=reply_text)
        update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=uid))
        try:
            asyncio.run(bot.setbase_cmd(update, SimpleNamespace(args=[])))
        finally:
            bot.ALLOWED_USERS.discard(uid)
        return sent

    def test_a_stale_prev_does_not_fake_a_backup(self, tmp_path, monkeypatch):
        (tmp_path / "x_base.png.prev").write_bytes(b"leftover from last time")
        sent = self._run(tmp_path, monkeypatch)
        assert "previous kept" not in sent[0], sent[0]
        assert (tmp_path / "x_base.png").read_bytes() == self.PNG

    def test_a_real_replacement_still_reports_the_backup(self, tmp_path, monkeypatch):
        (tmp_path / "x_base.png").write_bytes(b"the old reference photo")
        sent = self._run(tmp_path, monkeypatch)
        assert "previous kept as x_base.png.prev" in sent[0]
        assert (tmp_path / "x_base.png.prev").read_bytes() == b"the old reference photo"


# --- v2026-08-02: the source-assertion backlog, driven ---------------------------------
# `sweep.py source-assertion` listed 12 handlers the suite MENTIONED but never CALLED —
# the state that reads as covered while proving nothing about dispatch. /features sat in
# that list and raised ValueError on every invocation for four releases. These drive each
# one with fake Telegram objects. The uniform contract: a command either ANSWERS or is
# deliberately silent because a gate rejected the caller. Nothing here reads source.

class _CmdMsg:
    def __init__(self):
        self.sent = []
        self.documents = []

    async def reply_text(self, text, **kwargs):
        self.sent.append(text)
        return SimpleNamespace(message_id=1)

    async def reply_document(self, fh, **kwargs):
        self.documents.append({"bytes": fh.read(), **kwargs})

    async def set_reaction(self, *a, **k):
        return None


def _cmd_update(uid=7001, chat_id=9001):
    msg = _CmdMsg()
    return SimpleNamespace(
        message=msg,
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(id=uid, first_name="Tester"),
    ), msg


def _cmd_ctx(*args):
    return SimpleNamespace(args=list(args), bot=SimpleNamespace())


class TestEveryCommandHandlerActuallyRuns:
    """One DIRECT call per handler. Deliberately not routed through a helper that takes
    the handler as an argument: `self._run(bot.vibe_cmd)` passes a reference, and
    `source-assertion` counts that as a mention, not a call — correctly, since a
    reference proves nothing ran. The first draft of this class did exactly that and the
    scanner still reported all twelve."""

    UID = 7001

    def setup_method(self):
        self._allowed = set(bot.ALLOWED_USERS)
        bot.ALLOWED_USERS.add(self.UID)

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._allowed)

    def _outsider(self):
        """An id that is neither allow-listed nor the owner. A fixed literal is unsafe:
        another test in this file claims ownership of 999999 when none is set, so a
        hardcoded outsider silently became an admin depending on test order."""
        owner, uid = bot.get_owner(), 424242
        while uid == owner or uid in bot.ALLOWED_USERS:
            uid += 1
        return uid

    # ── admin-gated ───────────────────────────────────────────────────────────
    def test_audit_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.audit_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_audit_cmd_is_admin_gated(self):
        u, m = _cmd_update(self._outsider())
        asyncio.run(bot.audit_cmd(u, _cmd_ctx()))
        assert m.sent == [], "a non-admin must get silence, not a partial audit"

    def test_preset_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.preset_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_gif_cmd_answers_without_a_query(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.gif_cmd(u, _cmd_ctx()))
        assert m.sent and "Usage" in m.sent[0]

    def test_update_cmd_reports_the_dead_deploy_path(self, monkeypatch):
        """/update downloads over raw URLs, which 404 on the private repo. It must SAY
        so — the handler is kept for exactly that reply."""
        monkeypatch.setattr(bot, "perform_self_update",
                            lambda force: {"ok": False, "reason": "repo_not_readable",
                                           "detail": "404"})
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.update_cmd(u, _cmd_ctx()))
        assert m.sent

    # ── allowed-user gated ────────────────────────────────────────────────────
    def test_stress_cmd_explains_why_it_is_off(self):
        """No Garmin credentials in the fixture, so it must explain rather than pretend
        to check — the distinction v2026-08-02.14 restored."""
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.stress_cmd(u, _cmd_ctx()))
        assert m.sent and ("off" in m.sent[0].lower() or "set up" in m.sent[0].lower())

    # ── ungated ───────────────────────────────────────────────────────────────
    def test_card_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.card_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_setcard_cmd_usage(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.setcard_cmd(u, _cmd_ctx()))
        assert "Usage" in m.sent[0]

    def test_setcard_cmd_rejects_an_unknown_field(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.setcard_cmd(u, _cmd_ctx("nosuchfield", "x")))
        assert "Unknown field" in m.sent[0]

    def test_status_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.status_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_vibe_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.vibe_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_energy_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.energy_cmd(u, _cmd_ctx()))
        assert m.sent

    def test_schedule_cmd_shows_the_schedule(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "SCHEDULE_FILE", tmp_path / "schedule.txt")
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.schedule_cmd(u, _cmd_ctx()))
        assert "Schedule" in m.sent[0]

    def test_notes_cmd_handles_an_empty_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "USER_NOTES_FILE", tmp_path / "user_notes.txt")
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.notes_cmd(u, _cmd_ctx()))
        assert "No notes yet" in m.sent[0]

    def test_the_backlog_stays_empty(self):
        """The check that keeps it at zero: sweep's own coverage query must report no
        handler this suite mentions but never calls."""
        import pathlib as _pl
        import sys
        sys.path.insert(0, str(_pl.Path(bot.__file__).resolve().parents[1] /
                               ".claude" / "tools"))
        import sweep
        # Bind BOTH halves from one call. Written as
        # `n for n in _handler_coverage()[0] if n not in _handler_coverage()[1]`, the
        # condition re-ran the whole scan per handler: 64 calls at 0.571s each, 37s in one
        # test, and 89% of the suite's runtime sat in this line and its twin.
        mentioned, called = sweep._handler_coverage()
        stranded = sorted(n for n in mentioned if n not in called)
        assert stranded == [], stranded


# ── 2026-08-03: the second source-assertion backlog, driven ────────────────────
# `sweep.py`'s one-hop widening (operational-log 2026-08-03) found 7 more helpers
# this suite MENTIONED -- via inspect.getsource or a monkeypatch-to-a-no-op -- but
# never actually CALLED: save_feature_prefs, save_state, save_wardrobe, send_gif,
# send_meme, send_selfie, update_garmin. Same shape TestEveryCommandHandlerActuallyRuns
# closed for the original 12: drive each one for real with fakes for its I/O.

class TestTheSecondBacklogDriven:
    def test_save_state_writes_synchronously_with_no_running_loop(self, tmp_path, monkeypatch):
        # The no-loop branch (startup/shutdown): _MAIN_LOOP is None, so save_state
        # must fall straight through to a direct, synchronous write.
        monkeypatch.setattr(bot, "STATE_FILE", tmp_path / "state.json")
        monkeypatch.setattr(bot, "_MAIN_LOOP", None)
        bot.save_state()
        data = json.loads((tmp_path / "state.json").read_text())
        assert "conversation_history" in data and "llm_stats" in data

    def test_save_state_debounces_on_the_event_loop(self, tmp_path, monkeypatch):
        # The on-loop branch: a second call while one is already pending must be a
        # no-op (_save_scheduled), and the deferred write must land ~0.5s later.
        monkeypatch.setattr(bot, "STATE_FILE", tmp_path / "state.json")

        async def _run():
            bot.save_state()
            first_scheduled = bot._save_scheduled
            bot.save_state()  # must be a no-op: already scheduled
            await asyncio.sleep(0.8)
            return first_scheduled

        first_scheduled = asyncio.run(_run())
        assert first_scheduled is True
        assert bot._save_scheduled is False
        assert (tmp_path / "state.json").exists()

    def test_save_wardrobe_writes_the_live_dict(self, tmp_path, monkeypatch):
        target = tmp_path / "wardrobe.json"
        monkeypatch.setattr(bot, "WARDROBE_FILE", target)
        bot.save_wardrobe()
        assert json.loads(target.read_text()) == bot.wardrobe

    def test_save_feature_prefs_writes_the_live_dict(self, tmp_path, monkeypatch):
        target = tmp_path / "feature_prefs.json"
        monkeypatch.setattr(bot, "FEATURE_PREFS_FILE", target)
        bot.save_feature_prefs()
        assert json.loads(target.read_text()) == bot.feature_prefs

    def test_send_gif_sends_and_records_dedup(self, monkeypatch):
        monkeypatch.setattr(bot, "GIF_ENABLED", True)
        monkeypatch.setattr(bot, "GIPHY_API_KEY", "fake-key")
        monkeypatch.setattr(bot, "_giphy_search",
                            lambda query, level, seen: ("http://x/cat.gif", "gid123", "a cat"))
        bot._recent_gif_ids.pop(555, None)

        class _FakeBot:
            def __init__(self):
                self.sent = None

            async def send_animation(self, chat_id, animation):
                self.sent = (chat_id, animation)

        fb = _FakeBot()
        asyncio.run(bot.send_gif(SimpleNamespace(bot=fb), 555, "cat waving"))
        assert fb.sent == (555, "http://x/cat.gif")
        assert bot._recent_gif_ids[555] == ["gid123"]

    def test_send_meme_renders_and_sends_a_photo(self, monkeypatch):
        monkeypatch.setattr(bot, "meme_ready", lambda: True)

        async def _fake_uploading(b, cid):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        monkeypatch.setattr(bot, "_keep_uploading", _fake_uploading)

        async def _fake_captions(hint, chat_id):
            return "TOP", "BOTTOM"

        monkeypatch.setattr(bot, "_generate_meme_captions", _fake_captions)
        monkeypatch.setattr(bot, "_pick_meme_template", lambda chat_id: "fake.jpg")
        monkeypatch.setattr(bot, "render_meme",
                            lambda template, top, bottom: b"FAKEMEMEBYTES")

        class _FakeBot:
            def __init__(self):
                self.sent = None

            async def send_photo(self, chat_id, photo):
                self.sent = (chat_id, photo.read())

            async def send_message(self, chat_id, text):
                pass

        fb = _FakeBot()
        asyncio.run(bot.send_meme(SimpleNamespace(bot=fb), 777, hint="lol"))
        assert fb.sent == (777, b"FAKEMEMEBYTES")

    def test_send_selfie_sends_a_photo_and_updates_dedup(self, monkeypatch):
        monkeypatch.setattr(bot, "selfie_ready", lambda: True)

        async def _fake_uploading(b, cid):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        monkeypatch.setattr(bot, "_keep_uploading", _fake_uploading)
        monkeypatch.setattr(bot, "generate_selfie_image", lambda prompt: b"FAKESELFIEBYTES")

        async def _fake_caption(hint, chat_id):
            return "cute"

        monkeypatch.setattr(bot, "_selfie_caption", _fake_caption)
        bot._recent_selfie_hints.pop(888, None)

        class _FakeBot:
            def __init__(self):
                self.sent = None

            async def send_photo(self, chat_id, photo, caption=None):
                self.sent = (chat_id, photo.read(), caption)

            async def send_message(self, chat_id, text):
                pass

        fb = _FakeBot()
        asyncio.run(bot.send_selfie(SimpleNamespace(bot=fb), 888, hint="park day"))
        assert fb.sent == (888, b"FAKESELFIEBYTES", "cute")
        assert bot._recent_selfie_hints[888] == ["park day"]

    def test_update_garmin_writes_the_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "GARMIN_ENABLED", True)
        monkeypatch.setattr(bot, "_Garmin", object)  # any non-None sentinel
        monkeypatch.setattr(bot, "GARMIN_FILE", tmp_path / "snapshot.json")
        monkeypatch.setattr(bot, "_fetch_garmin", lambda: ("7,412 steps", []))
        asyncio.run(bot.update_garmin())
        assert bot._garmin["text"] == "7,412 steps"
        assert json.loads((tmp_path / "snapshot.json").read_text())["text"] == "7,412 steps"

    # `test_the_second_backlog_stays_empty` lived here until 2026-08-10. It re-ran
    # test_the_backlog_stays_empty's assertion, on the stated rationale that running it
    # *after* the direct calls above proved they "register as CALLS to the scanner, not
    # just more mentions". That rationale does not hold: `sweep._handler_coverage()` is
    # static AST analysis of bot.py and this file on disk, so no amount of test execution
    # can change its answer and the ordering is meaningless. It computed an identical value
    # by identical means — a duplicate costing 37s, and false assurance besides. The
    # coverage assertion lives once, in TestEveryCommandHandlerActuallyRuns. The tests
    # below, which genuinely drive save_state/send_gif/send_meme/send_selfie/etc., stay.


# ── reasoning-leak guard ──────────────────────────────────────────────────────

class TestReasoningLeakGuard:
    """v2026-08-03.1: glm-5.1:thinking wrote its ENTIRE deliberation into ordinary
    `content` — no <think> tags, non-empty, no bracket directives — so every earlier
    chain-of-thought guard passed it and priya sent a ~12k-char essay as four chunked
    messages. LEAK below is an excerpt of the real transcript; it must always trip
    the detector, and the in-character fixtures must always pass through."""

    LEAK = """Let me work through this step by step:

1. How does Priya feel about what Brian just said?
Brian just said he has to wake up at 3 AM tomorrow and will try not to wake her. They just had intimate, tender sex. She's in that quiet post-coital space where she felt seen and vulnerable. Now he's mentioning 3 AM - that's early. She knows he works dispatch and has weird hours. The mention of 3 AM is a small intrusion of reality into this soft moment.

2. What does Priya want?
She's in a tender, soft space. She doesn't want to leave this bubble yet. She might want to acknowledge the 3 AM thing without making it a big deal - she's practical.

3. Epistemic check:
She knows he works dispatch and has weird hours. She knows he just worked 6 days straight (58.5 hours). I shouldn't assume inconsistency - I should just take what he's saying at face value.

4. Rules that matter:
- This is a quiet, intimate domestic moment. Lane rhythm matters - match the quiet energy.
- Anti-echo: don't repeat his phrasing
- Keep it in character - Priya is sardonic but soft right now
- She's on her phone texting... wait, no - the scene mode says they're physically in the same space. But the format contract says she's typing on a phone.

5. Three possible directions:
a) Soft acknowledgment, practical - "3am is criminal" or something short and dry about the hour
b) A small protest - wanting him to stay, but not making it dramatic
c) A sardonic comment about his job hours, with undertones of care

Let me draft:

Option 1: "3am should be illegal. stay though. i'm not moving."
Option 2: "i'll survive. you're the one waking up at that hour." - too practical, not enough of her

How about:
"i'll be asleep anyway. probably"

That's very Priya - practical, with that "probably" at the end that's just slightly uncertain, slightly vulnerable.

Okay, I'm overthinking this. Let me just write what feels right:

"i'll be out cold by 11. you're fine."

Simple. Dry. Warm underneath. Priya.

Okay, FINAL answer:

"i'll be asleep anyway. just say bye before you go."

Simple. Direct. Warm underneath. Priya.

Done. Going with that"""

    # A long but genuinely in-character reply (rambling story, scene-register) —
    # length alone must never trip the guard.
    LONG_SCENE = (
        "okay so the whole landlord saga finally came to a head today and you're getting "
        "the entire thing because asha has officially stopped answering my texts about it. "
        "remember the ceiling stain that was 'cosmetic'? it dripped on my laptop this "
        "morning. actual water. on the actual keyboard. so i called the property office and "
        "got the guy who always sounds like i've interrupted his lunch, and he tells me "
        "maintenance can come thursday. thursday. it is monday. i said the ceiling is "
        "actively leaking and he said, and i quote, 'is it a lot of water though.' sir. "
        "define a lot. it's INDOOR RAIN. so then i did the thing you told me to do ages ago "
        "and emailed instead of calling so there's a paper trail, and suddenly — suddenly — "
        "someone can come tomorrow morning. amazing what happens when words are written "
        "down. anyway i moved the desk into the hallway which means i'm typing this from a "
        "hallway like some kind of displaced victorian orphan, and the wifi barely reaches "
        "here, and my tea went cold during the second phone call, which honestly hurt more "
        "than the laptop thing because the laptop might be covered but the tea is just "
        "gone. also the upstairs neighbor came down to ask if MY leak was MY fault, which "
        "takes a special kind of nerve when the water is coming from the direction of his "
        "bathroom. i kept it polite. barely. you would have been proud of me and also a "
        "little scared. so that's where we are: hallway desk, cold tea, thursday guy "
        "shamed into tomorrow guy, and a towel on my keyboard like a tiny hospital "
        "blanket. tell me something good about your day because mine has been plumbing "
        "themed since 8am and i need news from the dry world. also if you say 'should've "
        "gotten renter's insurance' i already did, in march, i am not a cautionary tale, "
        "i am a victim of infrastructure. come over on the weekend and admire my water "
        "damage. i'll make the good curry. bring your own ceiling. and before you ask, "
        "yes the laptop still turns on, the towel caught most of it, we are calling it a "
        "near-death experience and moving forward together. the hallway is cold. send "
        "socks. or better, bring them yourself and stay."
    )

    def test_the_real_leak_trips_it(self):
        assert len(self.LEAK) >= bot._REASONING_LEAK_MIN_CHARS
        assert bot._looks_like_reasoning_leak(self.LEAK, "Priya")

    def test_trips_without_the_name_too(self):
        """The non-name marker categories alone must carry the real transcript —
        the guard can't depend on the model naming the character."""
        assert bot._looks_like_reasoning_leak(self.LEAK, "")

    def test_normal_reply_passes(self):
        assert not bot._looks_like_reasoning_leak(
            "i'll be asleep anyway. just say bye before you go.", "Priya")

    def test_long_scene_reply_passes(self):
        assert len(self.LONG_SCENE) >= bot._REASONING_LEAK_MIN_CHARS
        assert not bot._looks_like_reasoning_leak(self.LONG_SCENE, "Priya")

    def test_short_meta_text_passes(self):
        """Markers without extreme length never trip — the length floor is the
        first gate, so ordinary replies are never even scanned."""
        txt = ("1. thing\n2. thing\n3. thing\n"
               "let me think about staying in character for the user")
        assert not bot._looks_like_reasoning_leak(txt, "Priya")

    def test_length_alone_never_trips(self):
        assert not bot._looks_like_reasoning_leak("word " * 1000, "Priya")

    def test_two_categories_are_not_enough(self):
        """Name saturation plus one marker = 2 categories; the floor is 3."""
        txt = ("Priya thought about it. Priya waited. Priya decided. "
               "option 1 it is. " + "filler " * 400)
        assert not bot._looks_like_reasoning_leak(txt, "Priya")

    def test_ordinary_deliberative_texting_passes(self):
        """Review finding: 'let me think', 'overthinking this', 'going back and
        forth', 'option 1/2' are ordinary texting vocabulary on this fleet. A long
        in-character reply weighing options must never trip on phrasing alone —
        only 'option N' is a marker, and one category is far under the floor."""
        txt = ("ok so i keep going back and forth on the apartment thing. "
               "option 1 is the studio, option 2 is splitting with asha. "
               "let me think about what actually bothers me here. honestly i'm "
               "overthinking this and i know it. " + "more rambling. " * 160)
        assert len(txt) >= bot._REASONING_LEAK_MIN_CHARS
        assert not bot._looks_like_reasoning_leak(txt, "Emily Harper")

    def test_first_name_matches_full_card_names(self):
        """Review finding: NAME is the card's full name — 'Emily Harper',
        'Bonnie (Libertarian)' — but leaked deliberation writes 'Emily', 'Bonnie'.
        The name category must key on the first token, and the parenthesized
        bonnie name must not break the pattern. Proven by contrast: the same text
        is 3 categories with the name mentions and 2 without."""
        base = ("the user seems tired. let me draft a reply. " + "filler " * 400)
        for full, first in (("Emily Harper", "Emily"), ("Bonnie (Libertarian)", "Bonnie")):
            with_name = base + f" {first} would wait. {first} is dry. {first} again."
            assert bot._looks_like_reasoning_leak(with_name, full)
            assert not bot._looks_like_reasoning_leak(base, full)

    # -- wiring: rejection inside call_nanogpt, exactly like an empty completion --

    def _patch_calls(self, monkeypatch, outputs):
        calls = []

        def fake_one_call(messages, m):
            calls.append(m)
            return outputs.pop(0)

        monkeypatch.setattr(bot, "_one_call", fake_one_call)
        monkeypatch.setattr(bot.time, "sleep", lambda s: None)
        return calls

    def test_leak_rerolls_then_falls_back(self, monkeypatch):
        calls = self._patch_calls(monkeypatch, [self.LEAK, self.LEAK, "hey. come here."])
        out = bot.call_nanogpt([{"role": "user", "content": "hi"}],
                               model="thinker", fallback="plain", leak_guard=True)
        assert out == "hey. come here."
        assert calls == ["thinker", "thinker", "plain"]

    def test_exhausted_leaks_raise_not_deliver(self, monkeypatch):
        """If every attempt is reasoning-shaped, the call fails like an empty one —
        the deliberation must never reach the caller."""
        self._patch_calls(monkeypatch, [self.LEAK] * 4)
        with pytest.raises(RuntimeError):
            bot.call_nanogpt([{"role": "user", "content": "hi"}],
                             model="thinker", fallback="plain", leak_guard=True)

    def test_kill_switch_delivers_verbatim(self, monkeypatch):
        monkeypatch.setattr(bot, "REASONING_LEAK_GUARD", False)
        self._patch_calls(monkeypatch, [self.LEAK])
        out = bot.call_nanogpt([{"role": "user", "content": "hi"}],
                               model="thinker", leak_guard=True)
        assert out == self.LEAK

    def test_analysis_paths_are_outside_the_guard(self, monkeypatch):
        """leak_guard defaults False: the analysis/summary JSON callers can never
        have a completion eaten by this guard, whatever it looks like."""
        self._patch_calls(monkeypatch, [self.LEAK])
        out = bot.call_nanogpt([{"role": "user", "content": "hi"}], model="thinker")
        assert out == self.LEAK

    def test_generate_reply_is_guarded_end_to_end(self, monkeypatch):
        """The wiring, not the detector: generate_reply must pass leak_guard, so a
        leak on the first attempt re-rolls and the user gets the second reply."""
        self._patch_calls(monkeypatch, [self.LEAK, "fine. stay."])
        out = asyncio.run(bot.generate_reply(
            [{"role": "user", "content": "hi"}], model="thinker"))
        assert out == "fine. stay."

    def test_document_analysis_opt_out_delivers_meta_replies(self, monkeypatch):
        """Review finding: a card review — which handle_document explicitly asks
        for — legitimately runs long and discusses prompts and characters, and
        DOCUMENT_MODEL has no fallback, so a guard trip there is a hard user-visible
        error. Those call sites pass leak_guard=False; this proves the opt-out
        delivers a reply the detector WOULD reject (so the exemption, not the
        detector, is what this test can fail on)."""
        review = ("honest take on this card: the system prompt is doing too much. "
                  "1. the opening is generic\n2. the user is over-specified\n"
                  "3. the voice section contradicts itself\n"
                  "it reads out of character for what you say you want. "
                  + "more detail. " * 200)
        assert bot._looks_like_reasoning_leak(review, "Priya")
        self._patch_calls(monkeypatch, [review])
        out = asyncio.run(bot.generate_reply(
            [{"role": "user", "content": "card"}], model="doc", leak_guard=False))
        assert out == review


# ── Offline life events (2026-08-04, reimplemented from b0eb485, never merged) ─────

class TestLifeEvents:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})

    def test_read_with_no_file_is_empty(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        assert bot._read_life_events() == []

    def test_append_then_read_round_trips(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._append_life_event("A teammate brought donuts to the morning standup.")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        events = bot._read_life_events()
        assert len(events) == 1
        assert "A teammate brought donuts" in events[0]
        assert events[0].startswith("[")  # date stamp prefix

    def test_blank_line_is_a_noop(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._append_life_event("   ")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        assert bot._read_life_events() == []

    def test_caps_at_life_events_max(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        for i in range(bot.LIFE_EVENTS_MAX + 5):
            bot._append_life_event(f"event {i}")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        events = bot._read_life_events()
        assert len(events) == bot.LIFE_EVENTS_MAX
        assert "event " + str(bot.LIFE_EVENTS_MAX + 4) in events[-1]  # newest kept

    def test_generate_returns_the_model_line(self, monkeypatch):
        monkeypatch.setattr(bot, "_read_schedule_today", lambda: "gym at 6, work after")
        monkeypatch.setattr(bot, "call_nanogpt", lambda messages, model=None: "Her coworker spilled coffee on the new carpet.")
        assert bot._generate_life_event() == "Her coworker spilled coffee on the new carpet."

    def test_generate_none_response_is_empty(self, monkeypatch):
        monkeypatch.setattr(bot, "_read_schedule_today", lambda: "gym at 6")
        monkeypatch.setattr(bot, "call_nanogpt", lambda messages, model=None: "none")
        assert bot._generate_life_event() == ""

    def test_generate_with_no_context_is_empty(self, monkeypatch):
        # No schedule/people/projects/arc/recent events at all -- nothing to ground it in.
        monkeypatch.setattr(bot, "_read_schedule_today", lambda: "")
        monkeypatch.setattr(bot, "_read_people", lambda: "")
        monkeypatch.setattr(bot, "_read_projects", lambda: "")
        monkeypatch.setattr(bot, "_read_life_arc", lambda: "")
        monkeypatch.setattr(bot, "_read_life_events", lambda: [])
        assert bot._generate_life_event() == ""

    def test_generate_broken_classifier_is_empty(self, monkeypatch):
        monkeypatch.setattr(bot, "_read_schedule_today", lambda: "gym at 6")

        def _boom(messages, model=None):
            raise RuntimeError("api down")

        monkeypatch.setattr(bot, "call_nanogpt", _boom)
        assert bot._generate_life_event() == ""

    def test_update_life_event_appends_when_enabled(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", True)
        monkeypatch.setattr(bot, "_generate_life_event", lambda: "Something happened today.")
        asyncio.run(bot.update_life_event())
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        assert "Something happened today." in bot._read_life_events()[0]

    def test_update_life_event_noop_when_disabled(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", False)
        called = []
        monkeypatch.setattr(bot, "_generate_life_event", lambda: called.append(1) or "x")
        asyncio.run(bot.update_life_event())
        assert called == []
        assert bot._read_life_events() == []


class TestAssembleMessagesLifeEvents:
    def test_includes_life_events_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", True)
        bot._append_life_event("Her friend adopted a cat.")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        bot.conversation_history[9601] = []
        bot.user_names[9601] = "Tester"
        msgs = bot.assemble_messages(9601, "hello")
        assert any("Her friend adopted a cat" in (m.get("content") or "") for m in msgs)

    def test_omits_life_events_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", False)
        bot._append_life_event("Her friend adopted a cat.")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        bot.conversation_history[9602] = []
        bot.user_names[9602] = "Tester"
        msgs = bot.assemble_messages(9602, "hello")
        assert not any("Her friend adopted a cat" in (m.get("content") or "") for m in msgs)


class TestExportMemoryCmd:
    """v2026-08-07: /exportmemory and the menu button's cmd:exportmemory used to build
    the export text twice, independently, with slightly different section labels —
    now both call _send_memory_export/_memory_export_text. This drives the command
    path; TestButtonCallbackExportMemory drives the button path."""

    def setup_method(self):
        self._orig_summaries = dict(bot.summaries)
        self._orig_facts = dict(bot.facts)
        self._orig_milestones = dict(bot.milestones)

    def teardown_method(self):
        bot.summaries.clear()
        bot.summaries.update(self._orig_summaries)
        bot.facts.clear()
        bot.facts.update(self._orig_facts)
        bot.milestones.clear()
        bot.milestones.update(self._orig_milestones)

    def test_sends_a_document_with_the_expected_sections(self):
        chat_id = 9801
        bot.summaries[chat_id] = "settling in well"
        bot.facts[chat_id] = ["likes rainy days"]
        bot.milestones[chat_id] = [{"text": "first inside joke", "ts": time.time()}]
        u, m = _cmd_update(chat_id=chat_id)
        asyncio.run(bot.export_memory_cmd(u, _cmd_ctx()))
        assert len(m.documents) == 1
        doc = m.documents[0]
        text = doc["bytes"].decode("utf-8")
        assert "settling in well" in text
        assert "likes rainy days" in text
        assert "=== RELATIONSHIP MILESTONES ===" in text
        assert doc["filename"] == f"memory_{bot.NAME.lower()}_{chat_id}.txt"

    def test_cleans_up_the_temp_file(self):
        chat_id = 9802
        u, m = _cmd_update(chat_id=chat_id)
        asyncio.run(bot.export_memory_cmd(u, _cmd_ctx()))
        assert not (bot.BASE_DIR / f"memory_export_{chat_id}.txt").exists()


class _CmdQuery:
    def __init__(self, chat_id, data):
        self.data = data
        self.message = SimpleNamespace(chat_id=chat_id)

    async def answer(self):
        return None


class _CmdBot:
    def __init__(self):
        self.sent_messages = []
        self.sent_documents = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent_messages.append(text)

    async def send_document(self, chat_id, document, **kwargs):
        self.sent_documents.append({"bytes": document.read(), **kwargs})


class TestButtonCallbackExportMemory:
    """The menu button's cmd:exportmemory now shares _send_memory_export with
    /exportmemory (see TestExportMemoryCmd) — this drives the button path directly,
    since button_callback had zero test coverage before this dedup."""

    def setup_method(self):
        self._orig_summaries = dict(bot.summaries)

    def teardown_method(self):
        bot.summaries.clear()
        bot.summaries.update(self._orig_summaries)

    def test_sends_the_same_shaped_document_as_the_command(self):
        chat_id = 9803
        bot.summaries[chat_id] = "doing fine"
        query = _CmdQuery(chat_id, "cmd:exportmemory")
        update = SimpleNamespace(callback_query=query)
        fake_bot = _CmdBot()
        context = SimpleNamespace(bot=fake_bot)
        asyncio.run(bot.button_callback(update, context))
        assert len(fake_bot.sent_documents) == 1
        doc = fake_bot.sent_documents[0]
        text = doc["bytes"].decode("utf-8")
        assert "doing fine" in text
        assert "=== LONG-TERM MEMORY ===" in text  # now matches the command's wording
        assert doc["filename"] == f"memory_{bot.NAME.lower()}_{chat_id}.txt"
        assert not (bot.BASE_DIR / f"memory_export_{chat_id}.txt").exists()


class TestNewsCommands:
    """Direct-call tests, matching TestTheSecondBacklogDriven's contract: a command
    either answers or is deliberately silent because a gate rejected the caller."""

    def _outsider(self):
        owner, uid = bot.get_owner(), 434242
        while uid == owner or uid in bot.ALLOWED_USERS:
            uid += 1
        return uid

    UID = 7001

    def setup_method(self):
        self._allowed = set(bot.ALLOWED_USERS)
        bot.ALLOWED_USERS.add(self.UID)

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._allowed)

    def test_news_cmd_answers_with_events(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        bot._append_life_event("A coworker got a promotion.")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        u, m = _cmd_update()
        asyncio.run(bot.news_cmd(u, _cmd_ctx()))
        assert m.sent
        assert "A coworker got a promotion" in m.sent[0]

    def test_news_cmd_empty_state_answers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})
        u, m = _cmd_update()
        asyncio.run(bot.news_cmd(u, _cmd_ctx()))
        assert m.sent
        assert "newsnow" in m.sent[0]

    # Per-handler gating dropped (ponytail-audit cleanup, CHANGELOG): _private_gate
    # (group -1) already stops a disallowed caller before news_cmd ever runs, and the
    # per-handler `_is_allowed` check duplicated it as dead code. Gating is covered by
    # TestPrivateGate now, not here.

    def test_newsnow_cmd_answers(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", True)
        monkeypatch.setattr(bot, "LIFE_EVENTS_FILE", tmp_path / "life_events.txt")
        bot._life_events_cache.update({"text": None, "ts": 0.0})

        async def _fake_update():
            bot._append_life_event("A generated event.")
            bot._life_events_cache.update({"text": None, "ts": 0.0})

        monkeypatch.setattr(bot, "update_life_event", _fake_update)
        u, m = _cmd_update()
        asyncio.run(bot.newsnow_cmd(u, _cmd_ctx()))
        assert any("A generated event" in s for s in m.sent)

    def test_newsnow_cmd_off_says_so(self, monkeypatch):
        monkeypatch.setattr(bot, "LIFE_SIM_ENABLED", False)
        u, m = _cmd_update()
        asyncio.run(bot.newsnow_cmd(u, _cmd_ctx()))
        assert "off" in m.sent[0].lower()


# ── Acoustic tone analysis on voice notes (2026-08-04, reimplemented from bae2dcb,
# never merged; vendored acoustic_ears.py unmodified from menelly/AI_Ears, MIT) ────

class TestAcousticEars:
    @staticmethod
    def _write_wav(path, freq=440.0, duration=1.0, sr=44100, amplitude=0.5):
        import wave as _wave
        import numpy as _np
        t = _np.linspace(0, duration, int(sr * duration), endpoint=False)
        samples = (amplitude * _np.sin(2 * _np.pi * freq * t) * 32767).astype(_np.int16)
        with _wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(samples.tobytes())

    def test_analyze_acoustic_on_a_tone(self, tmp_path):
        import acoustic_ears
        wav_path = tmp_path / "tone.wav"
        self._write_wav(wav_path, freq=440.0, duration=1.0)
        result = acoustic_ears.analyze_acoustic(str(wav_path))
        assert "error" not in result
        assert result["duration_s"] == pytest.approx(1.0, abs=0.05)
        assert result["sample_rate"] == 44100
        assert result["brightness_label"] in (
            "very bright", "bright", "warm", "dark")

    def test_analyze_acoustic_empty_audio_reports_error(self, tmp_path):
        import acoustic_ears
        wav_path = tmp_path / "empty.wav"
        self._write_wav(wav_path, duration=0.0)
        result = acoustic_ears.analyze_acoustic(str(wav_path))
        assert result.get("error") == "empty audio"

    def test_describe_acoustic_none_input_is_none(self):
        import acoustic_ears
        assert acoustic_ears.describe_acoustic(None) is None

    def test_describe_acoustic_error_dict_is_none(self):
        import acoustic_ears
        assert acoustic_ears.describe_acoustic({"error": "empty audio"}) is None

    def test_describe_acoustic_includes_wpm_when_word_count_given(self):
        import acoustic_ears
        a = {"duration_s": 10.0, "dynamics_label": "even", "brightness_label": "warm",
             "pauses": []}
        note = acoustic_ears.describe_acoustic(a, word_count=20)
        assert "120 wpm" in note  # 20 words / (10s/60) = 120 wpm
        assert "even volume" in note
        assert "warm tone" in note

    def test_describe_acoustic_mentions_pauses_when_present(self):
        import acoustic_ears
        a = {"duration_s": 5.0, "dynamics_label": "dynamic", "brightness_label": "bright",
             "pauses": [(1.0, 1.5, 0.5), (2.0, 2.3, 0.3)]}
        note = acoustic_ears.describe_acoustic(a)
        assert "2 notable pause(s)" in note


class TestAnalyzeVoiceTone:
    def test_returns_none_when_ffmpeg_produces_no_wav(self, monkeypatch):
        async def _fake_ffmpeg(*args):
            return (b"", b"")  # never writes the output file

        monkeypatch.setattr(bot, "_run_ffmpeg", _fake_ffmpeg)
        result = asyncio.run(bot._analyze_voice_tone(b"not real audio"))
        assert result is None

    def test_returns_the_analysis_on_success(self, monkeypatch, tmp_path):
        import wave as _wave
        import numpy as _np

        async def _fake_ffmpeg(*args):
            # args: -y -i <in> -ar 44100 -ac 1 -c:a pcm_s16le <out>
            out_path = args[-1]
            t = _np.linspace(0, 0.5, int(44100 * 0.5), endpoint=False)
            samples = (0.3 * _np.sin(2 * _np.pi * 300 * t) * 32767).astype(_np.int16)
            with _wave.open(out_path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(samples.tobytes())
            return (b"", b"")

        monkeypatch.setattr(bot, "_run_ffmpeg", _fake_ffmpeg)
        result = asyncio.run(bot._analyze_voice_tone(b"fake ogg bytes"))
        assert result is not None
        assert "error" not in result

    def test_ffmpeg_failure_is_none_not_raised(self, monkeypatch):
        async def _boom(*args):
            raise RuntimeError("ffmpeg not found")

        monkeypatch.setattr(bot, "_run_ffmpeg", _boom)
        assert asyncio.run(bot._analyze_voice_tone(b"x")) is None

    def test_config_defaults(self):
        assert isinstance(bot.VOICE_TONE_ENABLED, bool)


# ── /diag (2026-08-04, reimplemented from 71dfa44, never merged; scoped down --
# the log-error tail is dropped as redundant with /errors, and the flag list is
# trimmed to what actually exists on this bot rather than the abandoned branch's
# full set) ─────────────────────────────────────────────────────────────────────

class TestDiagCmd:
    UID = 7001

    def setup_method(self):
        self._allowed = set(bot.ALLOWED_USERS)
        bot.ALLOWED_USERS.add(self.UID)

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._allowed)

    def _outsider(self):
        owner, uid = bot.get_owner(), 444242
        while uid == owner or uid in bot.ALLOWED_USERS:
            uid += 1
        return uid

    def test_diag_cmd_answers(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.diag_cmd(u, _cmd_ctx()))
        assert m.sent
        assert "diagnostics" in m.sent[0]

    def test_diag_cmd_reports_the_new_toggles(self):
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.diag_cmd(u, _cmd_ctx()))
        text = m.sent[0]
        for label in ("safety", "style mirror", "offline life", "voice tone"):
            assert label in text, label

    # Per-handler gating dropped (ponytail-audit cleanup, CHANGELOG): see the same
    # note in TestNewsCommands. Gating is covered by TestPrivateGate now, not here.

    def test_diag_cmd_omits_the_log_error_tail(self):
        # Deliberately dropped as redundant with /errors -- must not resurface here.
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.diag_cmd(u, _cmd_ctx()))
        assert "Log errors" not in m.sent[0]


# ── Episodic recall + on-this-day reminiscing (2026-08-04, reimplemented from
# 9fa21af + a485b1b's on-this-day portion, never merged -- rewritten against this
# file's actual embedding primitives, EMBEDDING_MODEL/_embed_text, not the abandoned
# branch's own EMBED_MODEL/_embed) ──────────────────────────────────────────────

class TestEpisodesCore:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODES_FILE", tmp_path / "episodes.jsonl")
        monkeypatch.setattr(bot, "EPISODES_MODEL_FILE", tmp_path / "episodes.model")
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": False})

    def test_normalize_rows_unit_length(self):
        import numpy as np
        mat = np.array([[3.0, 4.0], [1.0, 0.0]], dtype=np.float32)
        out = bot._normalize_rows(mat)
        norms = np.linalg.norm(out, axis=1)
        assert norms == pytest.approx([1.0, 1.0], abs=1e-5)

    def test_normalize_rows_handles_zero_vector(self):
        import numpy as np
        mat = np.array([[0.0, 0.0]], dtype=np.float32)
        out = bot._normalize_rows(mat)
        assert not np.isnan(out).any()

    def test_episode_when_phrasing(self):
        now = time.time()
        assert bot._episode_when(now) == "earlier today"
        assert bot._episode_when(now - 86400) == "yesterday"
        assert bot._episode_when(now - 5 * 86400) == "about 5 days ago"
        assert bot._episode_when(now - 21 * 86400) == "about 3 weeks ago"
        assert "back around" in bot._episode_when(now - 200 * 86400)

    def test_archive_then_load_round_trips(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        fixed_vec = [1.0, 0.0, 0.0]
        monkeypatch.setattr(bot, "_embed_text", lambda text: list(fixed_vec))
        batch = [{"role": "user", "content": "hey remember the beach trip", "ts": time.time()},
                 {"role": "assistant", "content": "of course, that was fun", "ts": time.time()}]
        bot._archive_episode_chunks(batch, "Tester")
        assert len(bot._episodes["ts"]) == 1
        assert "beach trip" in bot._episodes["text"][0]

        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": False})
        bot._load_episodes()
        assert len(bot._episodes["ts"]) == 1
        assert "beach trip" in bot._episodes["text"][0]

    def test_archive_empty_batch_is_a_noop(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._archive_episode_chunks([], "Tester")
        assert bot._episodes["ts"] == []

    def test_archive_skips_on_embed_failure(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "_embed_text", lambda text: None)
        batch = [{"role": "user", "content": "hello there", "ts": time.time()}]
        bot._archive_episode_chunks(batch, "Tester")
        assert bot._episodes["ts"] == []
        assert not bot.EPISODES_FILE.exists()

    def test_load_discards_archive_on_model_change(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot.EPISODES_FILE.write_text(
            json.dumps({"ts": time.time(), "text": "old memory", "vec": [1.0, 0.0]}) + "\n",
            encoding="utf-8")
        bot.EPISODES_MODEL_FILE.write_text("some-other-embedding-model", encoding="utf-8")
        bot._load_episodes()
        assert bot._episodes["ts"] == []
        assert not bot.EPISODES_FILE.exists()  # discarded, not just ignored

    def test_load_trims_to_episode_max(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "EPISODE_MAX", 3)
        with bot.EPISODES_FILE.open("w", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps({"ts": float(i), "text": f"memory {i}", "vec": [1.0, 0.0]}) + "\n")
        bot.EPISODES_MODEL_FILE.write_text(bot.EMBEDDING_MODEL, encoding="utf-8")
        bot._load_episodes()
        assert len(bot._episodes["ts"]) == 3
        assert bot._episodes["text"] == ["memory 2", "memory 3", "memory 4"]  # newest kept


class TestTriggeredEpisode:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODES_FILE", tmp_path / "episodes.jsonl")
        monkeypatch.setattr(bot, "EPISODES_MODEL_FILE", tmp_path / "episodes.model")
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": False})

    def _seed(self, ts, text, vec=(1.0, 0.0, 0.0)):
        import numpy as np
        bot._episodes["ts"].append(ts)
        bot._episodes["text"].append(text)
        row = bot._normalize_rows(np.array([list(vec)], dtype=np.float32))
        bot._episodes["mat"] = row if bot._episodes["mat"] is None else np.vstack(
            [bot._episodes["mat"], row])

    def test_returns_empty_when_disabled(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "EPISODIC_RECALL", False)
        self._seed(time.time() - 48 * 3600, "an old memory")
        assert bot.triggered_episode([1.0, 0.0, 0.0]) == ""

    def test_returns_empty_with_no_query_vec(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        self._seed(time.time() - 48 * 3600, "an old memory")
        assert bot.triggered_episode(None) == ""

    def test_returns_empty_when_archive_is_empty(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        assert bot.triggered_episode([1.0, 0.0, 0.0]) == ""

    def test_surfaces_a_similar_old_episode(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        self._seed(time.time() - 48 * 3600, "the beach trip last month", vec=(1.0, 0.0, 0.0))
        note = bot.triggered_episode([1.0, 0.0, 0.0])
        assert "beach trip" in note
        assert "specific moment you remember" in note

    def test_below_similarity_floor_is_silent(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        self._seed(time.time() - 48 * 3600, "unrelated topic", vec=(0.0, 1.0, 0.0))
        assert bot.triggered_episode([1.0, 0.0, 0.0]) == ""

    def test_too_recent_is_gated_out(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        # Inside the live window (EPISODE_MIN_AGE_HOURS default 24h) -- must not echo it back.
        self._seed(time.time() - 3600, "something said an hour ago", vec=(1.0, 0.0, 0.0))
        assert bot.triggered_episode([1.0, 0.0, 0.0]) == ""


class TestOnThisDay:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODES_FILE", tmp_path / "episodes.jsonl")
        monkeypatch.setattr(bot, "ONTHISDAY_FILE", tmp_path / "onthisday.json")
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        monkeypatch.setattr(bot, "ONTHISDAY_ENABLED", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": True})

    def test_finds_a_one_month_anniversary(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        target_ts = time.time() - 30 * 86400
        bot._episodes["ts"] = [target_ts]
        bot._episodes["text"] = ["the anniversary moment"]
        result = bot._onthisday_episode()
        assert result is not None
        ts, text = result
        assert text == "the anniversary moment"

    def test_no_match_outside_any_window(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._episodes["ts"] = [time.time() - 10 * 86400]  # doesn't land near any interval
        bot._episodes["text"] = ["a random tuesday"]
        assert bot._onthisday_episode() is None

    def test_excludes_the_given_timestamp(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        target_ts = time.time() - 30 * 86400
        bot._episodes["ts"] = [target_ts]
        bot._episodes["text"] = ["already used"]
        assert bot._onthisday_episode(exclude_ts=target_ts) is None

    def test_prefers_the_longer_interval(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        # Both a ~30-day and a ~365-day episode qualify; the year-old one should win.
        bot._episodes["ts"] = [time.time() - 30 * 86400, time.time() - 365 * 86400]
        bot._episodes["text"] = ["recent one", "the year-old one"]
        ts, text = bot._onthisday_episode()
        assert text == "the year-old one"

    def test_job_is_a_noop_with_no_owner(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "get_owner", lambda: None)
        sent = []
        monkeypatch.setattr(bot, "send_triggered", lambda ctx, cid, trig: sent.append(1))
        asyncio.run(bot.onthisday_job(None))
        assert sent == []

    def test_job_respects_the_min_gap(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "get_owner", lambda: 42)
        monkeypatch.setattr(bot, "user_names", {42: "Tester"})
        today = datetime.now(bot.TZ).date().isoformat() if bot.TZ else datetime.now().date().isoformat()
        bot.ONTHISDAY_FILE.write_text(json.dumps({"date": today, "ts": 0}), encoding="utf-8")
        sent = []

        async def _fake_send(ctx, cid, trig):
            sent.append(trig)

        monkeypatch.setattr(bot, "send_triggered", _fake_send)
        asyncio.run(bot.onthisday_job(None))
        assert sent == []  # already reminisced today

    def test_job_sends_and_records_when_a_match_exists(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "get_owner", lambda: 42)
        monkeypatch.setattr(bot, "user_names", {42: "Tester"})
        monkeypatch.setattr(bot, "in_quiet_hours", lambda: False)
        monkeypatch.setattr(bot, "_is_quiet", lambda cid: False)
        bot._episodes["ts"] = [time.time() - 30 * 86400]
        bot._episodes["text"] = ["the moment that resurfaces"]
        sent = []

        async def _fake_send(ctx, cid, trig):
            sent.append(trig)

        monkeypatch.setattr(bot, "send_triggered", _fake_send)
        asyncio.run(bot.onthisday_job(None))
        assert len(sent) == 1
        assert "the moment that resurfaces" in sent[0]
        assert json.loads(bot.ONTHISDAY_FILE.read_text())["date"]  # recorded


class TestEpisodesCmd:
    UID = 7001

    def setup_method(self):
        self._allowed = set(bot.ALLOWED_USERS)
        bot.ALLOWED_USERS.add(self.UID)

    def teardown_method(self):
        bot.ALLOWED_USERS.clear()
        bot.ALLOWED_USERS.update(self._allowed)

    def _outsider(self):
        owner, uid = bot.get_owner(), 464242
        while uid == owner or uid in bot.ALLOWED_USERS:
            uid += 1
        return uid

    def test_off_says_so(self, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", False)
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.episodes_cmd(u, _cmd_ctx()))
        assert "off" in m.sent[0].lower()

    def test_empty_archive_says_so(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": True})
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.episodes_cmd(u, _cmd_ctx()))
        assert "No episodes archived yet" in m.sent[0]

    def test_reports_the_count(self, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [time.time()], "text": ["a stored moment"],
                              "mat": None, "loaded": True})
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.episodes_cmd(u, _cmd_ctx()))
        assert "1 chunk" in m.sent[0]
        assert "a stored moment" in m.sent[0]

    # Per-handler gating dropped (ponytail-audit cleanup, CHANGELOG): see the same
    # note in TestNewsCommands. Gating is covered by TestPrivateGate now, not here.


class TestMaintainMemoryArchivesOnScrollOff:
    def test_scroll_off_triggers_archiving(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        chat_id = 9701
        now = time.time()
        bot.conversation_history[chat_id] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}", "ts": now}
            for i in range(25)
        ]
        bot.user_names[chat_id] = "Tester"
        bot.recent_facts[chat_id] = []
        bot.recent_summaries[chat_id] = ""
        monkeypatch.setattr(bot, "_summarize", lambda *a, **k: ("a summary", []))
        monkeypatch.setattr(bot, "save_state", lambda: None)
        captured = {}

        def _fake_archive(batch, uname):
            captured["batch"] = batch
            captured["uname"] = uname

        monkeypatch.setattr(bot, "_archive_episode_chunks", _fake_archive)

        async def _run():
            await bot.maintain_memory(chat_id)
            await asyncio.sleep(0.05)  # let the fire-and-forget archive task run

        asyncio.run(_run())
        assert "batch" in captured
        assert len(captured["batch"]) > 0
        assert captured["uname"] == "Tester"

    def test_scroll_off_skips_archiving_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", False)
        chat_id = 9702
        now = time.time()
        bot.conversation_history[chat_id] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}", "ts": now}
            for i in range(25)
        ]
        bot.user_names[chat_id] = "Tester"
        bot.recent_facts[chat_id] = []
        bot.recent_summaries[chat_id] = ""
        monkeypatch.setattr(bot, "_summarize", lambda *a, **k: ("a summary", []))
        monkeypatch.setattr(bot, "save_state", lambda: None)
        called = []
        monkeypatch.setattr(bot, "_archive_episode_chunks",
                            lambda batch, uname: called.append(1))

        async def _run():
            await bot.maintain_memory(chat_id)
            await asyncio.sleep(0.05)

        asyncio.run(_run())
        assert called == []


class TestAssembleMessagesEpisodicRecall:
    def test_includes_triggered_episode_in_prompt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": True})
        import numpy as np
        bot._episodes["ts"] = [time.time() - 48 * 3600]
        bot._episodes["text"] = ["a specific archived moment"]
        bot._episodes["mat"] = bot._normalize_rows(np.array([[1.0, 0.0, 0.0]], dtype=np.float32))
        bot.conversation_history[9703] = []
        bot.user_names[9703] = "Tester"
        msgs = bot.assemble_messages(9703, "hello", query_vec=[1.0, 0.0, 0.0])
        assert any("a specific archived moment" in (m.get("content") or "") for m in msgs)

    def test_omits_episode_block_with_no_query_vec(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EPISODIC_RECALL", True)
        bot._episodes.update({"ts": [], "text": [], "mat": None, "loaded": True})
        import numpy as np
        bot._episodes["ts"] = [time.time() - 48 * 3600]
        bot._episodes["text"] = ["a specific archived moment"]
        bot._episodes["mat"] = bot._normalize_rows(np.array([[1.0, 0.0, 0.0]], dtype=np.float32))
        bot.conversation_history[9704] = []
        bot.user_names[9704] = "Tester"
        msgs = bot.assemble_messages(9704, "hello")
        assert not any("a specific archived moment" in (m.get("content") or "") for m in msgs)


class TestEpisodicConfig:
    def test_config_types(self):
        assert isinstance(bot.EPISODIC_RECALL, bool)
        assert isinstance(bot.ONTHISDAY_ENABLED, bool)
        assert isinstance(bot.EPISODE_MAX, int)
        assert isinstance(bot.EPISODE_MIN_SIM, float)


# ── Embedding cache model-version guard + cap (2026-08-04, backported from episodic
# recall's design to the pre-existing memory/lore embedding caches, which lacked
# both -- a live gap flagged during a comparison of the two designs) ───────────────

class TestEmbeddingsCacheGuard:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "EMBEDDINGS_FILE", tmp_path / "embeddings.json")
        monkeypatch.setattr(bot, "EMBEDDINGS_MODEL_FILE", tmp_path / "embeddings.model")
        bot._embeddings_cache = {}
        bot._embeddings_dirty = False

    def test_load_with_no_file_is_empty(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._load_embeddings()
        assert bot._embeddings_cache == {}

    def test_save_then_load_round_trips(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._embeddings_cache = {"hello there": [1.0, 0.0]}
        bot._embeddings_dirty = True
        bot._save_embeddings()
        bot._embeddings_cache = {}
        bot._load_embeddings()
        assert bot._embeddings_cache == {"hello there": [1.0, 0.0]}

    def test_save_writes_the_model_fingerprint(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._embeddings_cache = {"x": [1.0]}
        bot._embeddings_dirty = True
        bot._save_embeddings()
        assert bot.EMBEDDINGS_MODEL_FILE.read_text().strip() == bot.EMBEDDING_MODEL

    def test_load_discards_on_model_mismatch(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot.EMBEDDINGS_FILE.write_text(json.dumps({"old text": [1.0, 0.0]}), encoding="utf-8")
        bot.EMBEDDINGS_MODEL_FILE.write_text("some-other-model", encoding="utf-8")
        bot._load_embeddings()
        assert bot._embeddings_cache == {}
        assert not bot.EMBEDDINGS_FILE.exists()  # discarded, not just ignored

    def test_load_keeps_cache_on_model_match(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot.EMBEDDINGS_FILE.write_text(json.dumps({"kept text": [1.0, 0.0]}), encoding="utf-8")
        bot.EMBEDDINGS_MODEL_FILE.write_text(bot.EMBEDDING_MODEL, encoding="utf-8")
        bot._load_embeddings()
        assert bot._embeddings_cache == {"kept text": [1.0, 0.0]}

    def test_load_trims_to_the_cap(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "EMBEDDINGS_MAX", 3)
        data = {f"line {i}": [float(i)] for i in range(5)}
        bot.EMBEDDINGS_FILE.write_text(json.dumps(data), encoding="utf-8")
        bot.EMBEDDINGS_MODEL_FILE.write_text(bot.EMBEDDING_MODEL, encoding="utf-8")
        bot._load_embeddings()
        assert len(bot._embeddings_cache) == 3
        assert set(bot._embeddings_cache) == {"line 2", "line 3", "line 4"}  # newest kept

    def test_save_trims_to_the_cap(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        monkeypatch.setattr(bot, "EMBEDDINGS_MAX", 2)
        bot._embeddings_cache = {"a": [1.0], "b": [2.0], "c": [3.0]}
        bot._embeddings_dirty = True
        bot._save_embeddings()
        assert len(bot._embeddings_cache) == 2
        assert set(bot._embeddings_cache) == {"b", "c"}

    def test_save_is_a_noop_when_not_dirty(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._embeddings_cache = {"x": [1.0]}
        bot._embeddings_dirty = False
        bot._save_embeddings()
        assert not bot.EMBEDDINGS_FILE.exists()

    def test_no_raw_exception_in_save_log(self):
        import inspect
        src = inspect.getsource(bot._save_embeddings)
        assert '", e)' not in src
        assert ".__name__" in src


class TestLoreEmbeddingsCacheGuard:
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "LORE_EMB_FILE", tmp_path / "lore_embeddings.json")
        monkeypatch.setattr(bot, "LORE_EMB_MODEL_FILE", tmp_path / "lore_embeddings.model")
        bot._lore_embeddings = {}
        bot._lore_emb_dirty = False

    def test_save_then_load_round_trips(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._lore_embeddings = {"the tavern is in Bellevue": [1.0, 0.0]}
        bot._lore_emb_dirty = True
        bot._save_lore_embeddings()
        bot._lore_embeddings = {}
        bot._load_lore_embeddings()
        assert bot._lore_embeddings == {"the tavern is in Bellevue": [1.0, 0.0]}

    def test_load_discards_on_model_mismatch(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot.LORE_EMB_FILE.write_text(json.dumps({"old lore": [1.0]}), encoding="utf-8")
        bot.LORE_EMB_MODEL_FILE.write_text("some-other-model", encoding="utf-8")
        bot._load_lore_embeddings()
        assert bot._lore_embeddings == {}
        assert not bot.LORE_EMB_FILE.exists()

    def test_save_writes_the_model_fingerprint(self, tmp_path, monkeypatch):
        self._isolate(tmp_path, monkeypatch)
        bot._lore_embeddings = {"x": [1.0]}
        bot._lore_emb_dirty = True
        bot._save_lore_embeddings()
        assert bot.LORE_EMB_MODEL_FILE.read_text().strip() == bot.EMBEDDING_MODEL


# ── Reference-photo observability (v2026-08-09.1) ─────────────────────────────
# v2026-08-03.2 spent two releases tuning selfie prompt text against a reference photo
# nobody had looked at; the real cause was a full-body shot with the face at ~8% of the
# frame. Nothing in the system would show what the reference photo was. These pin the
# three places it is now reported.

class TestBaseImageDimensions:
    @staticmethod
    def _png(tmp_path, w, h, name="x_base.png"):
        from PIL import Image
        p = tmp_path / name
        Image.new("RGB", (w, h), (120, 90, 60)).save(p)
        return p

    def test_reads_a_real_image(self, tmp_path):
        assert bot._base_image_dimensions(self._png(tmp_path, 640, 480)) == (640, 480)

    def test_undecodable_file_is_none_not_an_exception(self, tmp_path):
        # PNG magic bytes with a garbage body: /setbase's magic-byte check accepts this,
        # so the audit path must survive it rather than raising.
        p = tmp_path / "bad_base.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 9000)
        assert bot._base_image_dimensions(p) is None

    def test_missing_file_is_none(self, tmp_path):
        assert bot._base_image_dimensions(tmp_path / "nope.png") is None

    def test_note_formats_dimensions(self, tmp_path):
        assert bot._base_image_size_note(self._png(tmp_path, 1024, 1024)) == " 1024×1024"

    def test_note_flags_an_unreadable_file(self, tmp_path):
        p = tmp_path / "bad_base.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 9000)
        assert "UNREADABLE" in bot._base_image_size_note(p)

    def test_audit_status_carries_the_dimensions(self, tmp_path, monkeypatch):
        self._png(tmp_path, 800, 1200, "priya_base.png")
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "priya_base.png")
        status = bot._base_image_status()
        assert status.startswith("priya_base.png")
        assert "800×1200" in status

    def test_text_only_status_is_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "priya_base.png")
        assert "TEXT-ONLY" in bot._base_image_status()


class TestSetbaseShowsTheCurrentPhoto:
    """Bare /setbase used to print usage and nothing else. It now answers the question a
    face-drift report actually raises: what does her reference photo look like?"""

    def _run(self, tmp_path, monkeypatch, uid=4243):
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "x_base.png")
        bot.ALLOWED_USERS.add(uid)
        sent = {"text": [], "photo": []}

        async def reply_text(text, **k):
            sent["text"].append(text)

        async def reply_photo(photo=None, caption=None, **k):
            sent["photo"].append((photo.read(), caption))

        msg = SimpleNamespace(document=None, photo=None, reply_to_message=None,
                              reply_text=reply_text, reply_photo=reply_photo)
        update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=uid))
        try:
            asyncio.run(bot.setbase_cmd(update, SimpleNamespace(args=[])))
        finally:
            bot.ALLOWED_USERS.discard(uid)
        return sent

    def test_sends_the_photo_back_with_its_dimensions(self, tmp_path, monkeypatch):
        raw = TestBaseImageDimensions._png(tmp_path, 512, 768).read_bytes()
        sent = self._run(tmp_path, monkeypatch)
        assert sent["text"] == []
        assert len(sent["photo"]) == 1
        body, caption = sent["photo"][0]
        assert body == raw          # the file on disk, not a re-encode
        assert "512×768" in caption
        assert "x_base.png" in caption

    def test_caption_says_the_face_should_fill_the_frame(self, tmp_path, monkeypatch):
        TestBaseImageDimensions._png(tmp_path, 512, 768)
        _, caption = self._run(tmp_path, monkeypatch)["photo"][0]
        # The whole point of the release: the caption states the failure in words rather
        # than implying a numeric threshold that does not exist.
        assert "fill much of this frame" in caption

    def test_no_reference_photo_reports_that_instead(self, tmp_path, monkeypatch):
        sent = self._run(tmp_path, monkeypatch)
        assert sent["photo"] == []
        assert "No reference photo in play" in sent["text"][0]
        assert "TEXT-ONLY" in sent["text"][0]

    def test_kill_switch_restores_the_usage_only_reply(self, tmp_path, monkeypatch):
        TestBaseImageDimensions._png(tmp_path, 512, 768)
        monkeypatch.setattr(bot, "SELFIE_BASE_PREVIEW", False)
        sent = self._run(tmp_path, monkeypatch)
        assert sent["photo"] == []
        assert len(sent["text"]) == 1
        assert "512×768" not in sent["text"][0]

    def test_an_unreadable_file_names_the_real_problem(self, tmp_path, monkeypatch):
        """Present-but-unreadable is live in this deploy model: the bot runs as
        bot@<instance> and a hand-copied photo arrives owned by root. Every selfie reads
        the same path, so this is a selfie outage and the reply must say so."""
        from pathlib import Path
        TestBaseImageDimensions._png(tmp_path, 512, 768)
        # chmod cannot express this: the suite runs as root, which bypasses the mode bits
        # the production failure depends on. Raise the error the OS would raise instead.
        def _denied(self):
            raise PermissionError(13, "Permission denied")
        monkeypatch.setattr(Path, "read_bytes", _denied)
        before = len(bot._error_counts.get("media", []))
        sent = self._run(tmp_path, monkeypatch)
        assert sent["photo"] == []
        assert "could not be read" in sent["text"][0]
        assert "permissions" in sent["text"][0]
        # Silent in /errors is how this stays invisible for weeks.
        assert len(bot._error_counts.get("media", [])) == before + 1

    def test_a_telegram_rejection_still_answers_in_text(self, tmp_path, monkeypatch):
        TestBaseImageDimensions._png(tmp_path, 512, 768)
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "x_base.png")
        uid = 4244
        bot.ALLOWED_USERS.add(uid)
        seen = []

        async def reply_text(text, **k):
            seen.append(text)

        async def reply_photo(**k):
            raise RuntimeError("Telegram said no")

        msg = SimpleNamespace(document=None, photo=None, reply_to_message=None,
                              reply_text=reply_text, reply_photo=reply_photo)
        update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=uid))
        try:
            asyncio.run(bot.setbase_cmd(update, SimpleNamespace(args=[])))
        finally:
            bot.ALLOWED_USERS.discard(uid)
        assert len(seen) == 1 and "512×768" in seen[0]


class TestSetbaseInstallReportsDimensions:
    """A bad reference should be visible when it is installed, not three selfies later."""

    def test_install_confirmation_carries_the_size(self, tmp_path, monkeypatch):
        from PIL import Image
        import io
        import os
        buf = io.BytesIO()
        # Noise, not a flat fill: a solid-colour PNG compresses below /setbase's 8 KB
        # "too small to be usable" floor and never reaches the confirmation message.
        Image.frombytes("RGB", (300, 900), os.urandom(300 * 900 * 3)).save(buf, format="PNG")
        raw = buf.getvalue()
        monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
        monkeypatch.setattr(bot, "SELFIE_BASE", "x_base.png")
        uid = 4245
        bot.ALLOWED_USERS.add(uid)

        class _File:
            async def download_as_bytearray(self):
                return bytearray(raw)

        class _Doc:
            mime_type = "image/png"

            async def get_file(self):
                return _File()

        seen = []

        async def reply_text(text, **k):
            seen.append(text)

        msg = SimpleNamespace(document=_Doc(), photo=None, reply_to_message=None,
                              reply_text=reply_text)
        update = SimpleNamespace(message=msg, effective_user=SimpleNamespace(id=uid))
        try:
            asyncio.run(bot.setbase_cmd(update, SimpleNamespace(args=[])))
        finally:
            bot.ALLOWED_USERS.discard(uid)
        assert "300×900" in seen[0]


# ── Neighbourhood naming on a shared location (v2026-08-09.2) ─────────────────
# She held lat/lon and could not say where that WAS, so she said nothing where a person
# says "wait, you're in Ballard?". One reverse-geocode per share, injected into one reply.

class TestPlaceLabel:
    """The field order is load-bearing: TomTom names the local-neighbourhood field
    differently across API generations, and `municipality` last keeps a rural share
    from degrading to no label at all."""

    @staticmethod
    def _resp(**addr):
        return {"addresses": [{"address": addr}]}

    def test_neighbourhood_wins_and_carries_the_town(self):
        assert bot._place_label(self._resp(
            neighbourhood="Capitol Hill", municipality="Seattle")) == "Capitol Hill, Seattle"

    def test_municipality_subdivision_is_the_other_generation(self):
        assert bot._place_label(self._resp(
            municipalitySubdivision="Ballard", municipality="Seattle")) == "Ballard, Seattle"

    def test_falls_back_to_the_town_alone(self):
        assert bot._place_label(self._resp(municipality="Wenatchee")) == "Wenatchee"

    def test_does_not_say_the_town_twice(self):
        assert bot._place_label(self._resp(
            neighbourhood="Seattle", municipality="Seattle")) == "Seattle"

    def test_empty_and_malformed_shapes_degrade_to_no_label(self):
        for bad in (None, {}, {"addresses": []}, {"addresses": [None]},
                    {"addresses": [{"address": None}]}, {"addresses": [{"address": []}]},
                    {"addresses": [{"address": {}}]}):
            assert bot._place_label(bad) == ""


class TestReverseGeocodeNeverRaises:
    """Its caller is the location handler, where a failed lookup must cost the user
    nothing — there is no degraded answer to fall back to, the feature just doesn't
    happen. Every other TomTom fetch raises _TomTomError; this one must not."""

    def setup_method(self):
        self._session = bot._get_session

    def teardown_method(self):
        bot._get_session = self._session

    def _session_raising(self, exc):
        class _S:
            def get(_self, url, **kw):
                raise exc
        bot._get_session = lambda: _S()

    def test_a_network_failure_is_an_empty_label(self):
        self._session_raising(bot.requests.exceptions.ConnectionError("no route to host"))
        assert bot._tomtom_reverse_geocode(47.6, -122.3) == ""

    def test_a_garbage_body_is_an_empty_label(self):
        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): raise ValueError("not json")
        class _S:
            def get(_self, url, **kw): return _R()
        bot._get_session = lambda: _S()
        assert bot._tomtom_reverse_geocode(47.6, -122.3) == ""

    def test_a_good_body_returns_the_label(self):
        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"addresses": [{"address": {"neighbourhood": "Fremont",
                                                   "municipality": "Seattle"}}]}
        class _S:
            def get(_self, url, **kw): return _R()
        bot._get_session = lambda: _S()
        assert bot._tomtom_reverse_geocode(47.6, -122.3) == "Fremont, Seattle"


class TestHandleLocationNamesThePlace:
    """The lookup runs as a task, NOT inside the handler: PTB is built with no
    concurrent_updates, so awaiting a 30s HTTP call there stalls every other update for
    the instance and delays the "got it" ack by the same amount."""

    CHAT = 991

    def setup_method(self):
        self._saved = (bot.LOCATION_PLACE, bot.TOMTOM_ENABLED, bot.TRAFFIC_ENABLED,
                       bot.save_state)
        bot.LOCATION_PLACE = True
        bot.TOMTOM_ENABLED = True
        bot.TRAFFIC_ENABLED = False        # else the handler tries to reply
        bot.save_state = lambda: None
        bot.user_location.pop(self.CHAT, None)

    def teardown_method(self):
        (bot.LOCATION_PLACE, bot.TOMTOM_ENABLED, bot.TRAFFIC_ENABLED,
         bot.save_state) = self._saved
        bot.user_location.pop(self.CHAT, None)

    def _share(self, lat, lon, *, live=False, initial=True):
        loc = SimpleNamespace(latitude=lat, longitude=lon,
                              live_period=3600 if live else None)
        msg = SimpleNamespace(location=loc)
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=self.CHAT),
            message=msg if initial else None,
            edited_message=None if initial else msg,
        )

        async def _go():
            await bot.handle_location(update, None)
            # Let any task the handler spawned finish, so the test observes the end state
            # rather than racing it.
            for task in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                await task

        asyncio.run(_go())
        return bot.user_location[self.CHAT]

    def test_the_handler_itself_does_not_block_on_the_lookup(self, monkeypatch):
        """The regression that matters: a slow TomTom must not hold the update slot."""
        started = []

        def _slow(la, lo):
            started.append(time.time())
            time.sleep(0.25)
            return "Ballard, Seattle"

        monkeypatch.setattr(bot, "_tomtom_reverse_geocode", _slow)
        loc = SimpleNamespace(latitude=47.6685, longitude=-122.3830, live_period=None)
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=self.CHAT),
            message=SimpleNamespace(location=loc), edited_message=None)

        async def _go():
            t0 = time.monotonic()
            await bot.handle_location(update, None)
            handler_time = time.monotonic() - t0
            for task in [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]:
                await task
            return handler_time

        handler_time = asyncio.run(_go())
        assert handler_time < 0.2, f"handler blocked for {handler_time:.3f}s"
        assert started, "the lookup never ran"
        assert bot.user_location[self.CHAT]["place"] == "Ballard, Seattle"

    def test_the_location_is_stored_before_any_lookup_happens(self, monkeypatch):
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode",
                            lambda la, lo: "Ballard, Seattle")
        entry = self._share(47.6685, -122.3830)
        assert entry["lat"] == 47.6685 and entry["place_new"] is True

    def test_the_kill_switch_skips_the_lookup_entirely(self, monkeypatch):
        looked = []
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode",
                            lambda la, lo: looked.append(1) or "Ballard")
        bot.LOCATION_PLACE = False
        entry = self._share(47.6685, -122.3830)
        assert "place" not in entry and looked == []

    def test_no_label_found_stores_nothing_but_keeps_the_location(self, monkeypatch):
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode", lambda la, lo: "")
        entry = self._share(47.6685, -122.3830)
        assert "place" not in entry
        assert entry["lat"] == 47.6685

    def test_a_live_update_nearby_carries_the_label_without_a_second_lookup(self, monkeypatch):
        looked = []
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode",
                            lambda la, lo: looked.append(1) or "Ballard, Seattle")
        self._share(47.6685, -122.3830, live=True)
        assert len(looked) == 1
        entry = self._share(47.6690, -122.3835, live=True, initial=False)
        assert entry["place"] == "Ballard, Seattle"
        # The point of the live branch: no quota spent re-learning the same answer.
        assert len(looked) == 1

    def test_a_live_update_far_away_drops_the_label_rather_than_lying(self, monkeypatch):
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode",
                            lambda la, lo: "Ballard, Seattle")
        self._share(47.6685, -122.3830, live=True)
        entry = self._share(47.6100, -122.2007, live=True, initial=False)
        assert "place" not in entry


class TestNameThePlaceStaleGuard:
    CHAT = 992

    def setup_method(self):
        self._save = bot.save_state
        bot.save_state = lambda: None
        bot.user_location.pop(self.CHAT, None)

    def teardown_method(self):
        bot.save_state = self._save
        bot.user_location.pop(self.CHAT, None)

    def test_a_newer_share_is_not_captioned_with_the_old_lookup(self, monkeypatch):
        """The lookup is in flight when a second pin lands. Writing the old answer onto
        the new position is exactly the lie the live-update branch refuses to tell."""
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode", lambda la, lo: "Ballard, Seattle")
        bot.user_location[self.CHAT] = {"lat": 47.61, "lon": -122.20, "ts": 2000.0,
                                        "live_until": None}
        asyncio.run(bot._name_the_place(self.CHAT, 1000.0, 47.6685, -122.3830))
        assert "place" not in bot.user_location[self.CHAT]

    def test_the_matching_share_is_captioned(self, monkeypatch):
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode", lambda la, lo: "Ballard, Seattle")
        bot.user_location[self.CHAT] = {"lat": 47.6685, "lon": -122.3830, "ts": 1000.0,
                                        "live_until": None}
        asyncio.run(bot._name_the_place(self.CHAT, 1000.0, 47.6685, -122.3830))
        assert bot.user_location[self.CHAT]["place"] == "Ballard, Seattle"

    def test_a_vanished_chat_does_not_raise(self, monkeypatch):
        monkeypatch.setattr(bot, "_tomtom_reverse_geocode", lambda la, lo: "Ballard")
        asyncio.run(bot._name_the_place(self.CHAT, 1000.0, 47.6, -122.3))


# ── atlas_audit.py (v2026-08-09.2, repo tooling) ──────────────────────────────

def _atlas_audit():
    """Import the tool by path — tools/ is not a package."""
    import importlib.util
    from pathlib import Path
    p = Path(bot.__file__).resolve().parent / "tools" / "atlas_audit.py"
    spec = importlib.util.spec_from_file_location("atlas_audit", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAtlasAudit:
    def test_parse_uses_bot_own_filter(self):
        aa = _atlas_audit()
        text = "# header\n\nMeydenbauer Bay Park — resets her\n  \nOld Bellevue — slow Tuesday\n"
        assert aa.parse_atlas(text) == [
            "Meydenbauer Bay Park — resets her", "Old Bellevue — slow Tuesday"]

    def test_place_name_strips_the_characterisation(self):
        aa = _atlas_audit()
        assert aa.place_name("Meydenbauer Bay Park — she goes to reset") == "Meydenbauer Bay Park"
        assert aa.place_name("Old Bellevue - slow Tuesday mornings") == "Old Bellevue"
        assert aa.place_name("Just A Name") == "Just A Name"

    def test_name_match_accepts_a_longer_official_name(self):
        aa = _atlas_audit()
        assert aa.name_matches("Meydenbauer Bay Park", "Meydenbauer Beach Park & Boat Launch")

    def test_name_match_rejects_the_fuzzy_near_miss(self):
        """The exact failure this tool exists to avoid: asking for Meydenbauer Bay Park,
        being handed Bay Terrace Road, and calling the atlas clean. Observed live."""
        aa = _atlas_audit()
        assert not aa.name_matches("Meydenbauer Bay Park", "Bay Terrace Road")

    def test_stopwords_do_not_break_a_real_match(self):
        aa = _atlas_audit()
        assert aa.name_matches("The Fremont Bridge", "Fremont Bridge")

    def test_best_poi_skips_streets_and_near_misses(self):
        aa = _atlas_audit()
        results = [
            {"address": {"streetName": "Bay Terrace Road"}},          # no poi -> a street
            {"poi": {"name": "Bay Terrace Road"}},                    # poi, wrong place
            {"poi": {"name": "Meydenbauer Bay Park"}},                # the real one
        ]
        assert aa.best_poi(results, "Meydenbauer Bay Park")["poi"]["name"] == "Meydenbauer Bay Park"
        assert aa.best_poi([], "x") is None
        assert aa.best_poi([None, "junk"], "x") is None

    def test_verdict_separates_missing_from_merely_distant(self):
        aa = _atlas_audit()
        assert aa.verdict(None, 15) == "NOT FOUND"
        assert aa.verdict(41.0, 15) == "FAR"
        assert aa.verdict(2.0, 15) == "ok"
        assert aa.verdict(15.0, 15) == "ok"


class TestPlaceNoteIsOneShot:
    """A person reacts once to "you're in Ballard?". Re-injecting for the whole 4h
    freshness window would have her reopening it on every message."""

    def setup_method(self):
        self._flag = bot.LOCATION_PLACE
        bot.LOCATION_PLACE = True

    def teardown_method(self):
        bot.LOCATION_PLACE = self._flag

    @staticmethod
    def _loc(**over):
        base = {"lat": 47.66, "lon": -122.38, "ts": time.time(), "live_until": None,
                "place": "Ballard, Seattle", "place_new": True}
        base.update(over)
        return base

    def test_first_call_returns_the_line(self):
        assert "Ballard, Seattle" in bot._place_note(self._loc())

    def test_second_call_returns_nothing(self):
        loc = self._loc()
        assert bot._place_note(loc)
        assert bot._place_note(loc) == ""
        assert loc["place_new"] is False

    def test_a_stale_share_is_not_announced(self):
        assert bot._place_note(self._loc(ts=time.time() - 5 * 3600)) == ""

    def test_a_share_still_fresh_but_no_longer_recent_is_not_announced(self):
        """_fresh_location keeps a share usable for 4h, which is right for looking up
        restaurants near it and wrong for a line that says "they just shared". Between
        the two clocks she would open with news that is hours old."""
        older = self._loc(ts=time.time() - (bot._PLACE_ANNOUNCE_SEC + 60))
        assert bot._fresh_location(older)          # still good enough to route from
        assert bot._place_note(older) == ""        # not good enough to react to

    def test_a_share_inside_the_window_is_announced(self):
        assert bot._place_note(self._loc(ts=time.time() - 60))

    def test_a_missing_or_junk_timestamp_is_not_announced(self):
        assert bot._place_note(self._loc(ts=None)) == ""
        assert bot._place_note(self._loc(ts="soon")) == ""

    def test_no_place_no_line(self):
        assert bot._place_note(self._loc(place=None)) == ""
        assert bot._place_note(self._loc(place_new=False)) == ""

    def test_kill_switch_and_junk_inputs(self):
        assert bot._place_note(None) == ""
        assert bot._place_note("not a dict") == ""
        bot.LOCATION_PLACE = False
        assert bot._place_note(self._loc()) == ""


# ── atlas_suggest.py (repo tooling) ───────────────────────────────────────────

def _atlas_suggest():
    """Import the tool by path — tools/ is not a package."""
    import importlib.util
    from pathlib import Path
    p = Path(bot.__file__).resolve().parent / "tools" / "atlas_suggest.py"
    spec = importlib.util.spec_from_file_location("atlas_suggest", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAtlasSuggest:
    def test_existing_names_uses_the_shared_atlas_parser(self, tmp_path):
        """Dedupe matches on the place NAME, so a line whose description happens to
        mention another place does not suppress that place as a suggestion."""
        a = _atlas_suggest()
        f = tmp_path / "atlas.txt"
        f.write_text("# header\n\nMeydenbauer Bay Park — near the Bellevue Library\n",
                     encoding="utf-8")
        assert a.existing_names(f) == {"meydenbauer bay park"}

    def test_missing_atlas_is_an_empty_set_not_a_crash(self, tmp_path):
        a = _atlas_suggest()
        assert a.existing_names(tmp_path / "nope.txt") == set()

    def test_suggestion_line_leaves_the_meaning_to_a_person(self):
        a = _atlas_suggest()
        line = a.suggestion_line("Bellevue Library", "1111 110th Ave NE")
        assert line.startswith("Bellevue Library — [")
        assert "1111 110th Ave NE" in line

    def test_collect_skips_known_places_and_dedupes_across_kinds(self):
        a = _atlas_suggest()

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                return [
                    {"poi": {"name": "Old Bellevue"}, "address": {"freeformAddress": "Main St"}},
                    {"poi": {"name": "Cafe Cesura"}, "address": {"freeformAddress": "10 Bel"}},
                    {"address": {"freeformAddress": "no poi here"}},      # a street
                ]

        seen = {"old bellevue"}
        out = a.collect(_Bot, (47.6, -122.2), "coffee shop", seen, limit=5)
        assert len(out) == 1 and out[0].startswith("Cafe Cesura — [")
        # Mutating `seen` is what stops a place answering two kinds being proposed twice.
        assert a.collect(_Bot, (47.6, -122.2), "bakery", seen, limit=5) == []

    def test_collect_honours_the_per_kind_limit(self):
        a = _atlas_suggest()

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                return [{"poi": {"name": f"Place {i}"}, "address": {}} for i in range(10)]

        assert len(a.collect(_Bot, (47.6, -122.2), "park", set(), limit=3)) == 3

    def test_a_failed_search_is_not_fatal(self):
        a = _atlas_suggest()

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                raise RuntimeError("TomTom said no")

        assert a.collect(_Bot, (47.6, -122.2), "park", set(), limit=3) == []


# ── Opening hours on the food paths (v2026-08-09.3) ──────────────────────────
# FOOD_SUGGESTIONS handed the model real restaurants with no idea whether any were open,
# so at 11pm she could recommend a place that shut at nine.

class TestPoiHoursNote:
    """Shape confirmed against the raw REST endpoint with the fleet key (the MCP
    connector omits openingHours entirely, which is why this took a round trip)."""

    @staticmethod
    def _poi(*ranges):
        return {"openingHours": {"mode": "nextSevenDays", "timeRanges": [
            {"startTime": {"date": sd, "hour": sh, "minute": sm},
             "endTime": {"date": ed, "hour": eh, "minute": em}}
            for sd, sh, sm, ed, eh, em in ranges]}}

    def test_inside_a_range_reports_the_closing_time(self):
        poi = self._poi(("2026-08-10", 7, 0, "2026-08-10", 13, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 9, 30)) == "open until 13:00"

    def test_closing_time_is_zero_padded(self):
        poi = self._poi(("2026-08-10", 7, 0, "2026-08-10", 9, 5))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 8, 0)) == "open until 09:05"

    def test_after_the_last_range_today_is_closed(self):
        """The case the feature exists for: 11pm, and the place shut at nine."""
        poi = self._poi(("2026-08-10", 7, 0, "2026-08-10", 21, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 23, 0)) == "closed now"

    def test_between_two_ranges_on_the_same_day_is_closed(self):
        poi = self._poi(("2026-08-10", 7, 0, "2026-08-10", 11, 0),
                        ("2026-08-10", 17, 0, "2026-08-10", 22, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 14, 0)) == "closed now"

    def test_a_payload_with_no_range_on_our_date_says_nothing(self):
        """The tz gate. ROADMAP 3.18 proposed assuming the earliest date IS the POI's
        today; the first real response had an earliest date of tomorrow, so that
        assumption was dropped. No range on our date means either another timezone or a
        payload starting tomorrow — losing a hint beats inventing one."""
        poi = self._poi(("2026-08-11", 7, 0, "2026-08-11", 21, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 9, 0)) == ""

    def test_a_range_crossing_midnight_still_works(self):
        poi = self._poi(("2026-08-10", 18, 0, "2026-08-11", 2, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 11, 0, 30)) == "open until 02:00"

    def test_no_hours_data_says_nothing(self):
        assert bot._poi_hours_note({}, datetime(2026, 8, 10, 9, 0)) == ""
        assert bot._poi_hours_note(None, datetime(2026, 8, 10, 9, 0)) == ""
        assert bot._poi_hours_note({"openingHours": {}}, datetime(2026, 8, 10, 9, 0)) == ""

    def test_malformed_ranges_are_skipped_not_raised(self):
        poi = {"openingHours": {"timeRanges": [
            {"startTime": {"date": "not-a-date", "hour": 7, "minute": 0},
             "endTime": {"date": "2026-08-10", "hour": 13, "minute": 0}},
            {"startTime": {"date": "2026-08-10", "hour": "7", "minute": "0"},
             "endTime": {"date": "2026-08-10", "hour": 13, "minute": 0}},
        ]}}
        # The junk row is dropped; the string-typed one still parses.
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 9, 0)) == "open until 13:00"

    def test_junk_container_shapes_do_not_raise(self):
        for bad in ({"openingHours": {"timeRanges": "nope"}},
                    {"openingHours": {"timeRanges": [None, 3, "x"]}},
                    {"openingHours": []}):
            assert bot._poi_hours_note(bad, datetime(2026, 8, 10, 9, 0)) == ""


class TestHoursReachTheFormatters:
    def test_prompt_brief_carries_the_hours(self):
        results = [{"dist": 100, "poi": dict(TestPoiHoursNote._poi(
            ("2026-08-10", 7, 0, "2026-08-10", 21, 0)), name="Blue Bottle",
            categories=["CAFE"])}]
        # _places_brief calls _poi_hours_note with the live clock, so pin it.
        import unittest.mock as m
        with m.patch.object(bot, "_local_now_naive", lambda: datetime(2026, 8, 10, 9, 0)):
            assert "open until 21:00" in bot._places_brief(results)

    def test_food_list_carries_the_hours(self):
        results = [{"dist": 100, "poi": dict(TestPoiHoursNote._poi(
            ("2026-08-10", 7, 0, "2026-08-10", 21, 0)), name="Blue Bottle",
            categories=["CAFE"])}]
        import unittest.mock as m
        with m.patch.object(bot, "_local_now_naive", lambda: datetime(2026, 8, 10, 23, 0)):
            assert "closed now" in bot._format_restaurants(results)

    def test_a_poi_without_hours_renders_exactly_as_before(self):
        results = [{"dist": 100, "poi": {"name": "Blue Bottle", "categories": ["CAFE"]}}]
        assert bot._places_brief(results) == "- Blue Bottle (CAFE, 328 ft)"


class TestOpeningHoursParamIsOptIn:
    """Opt-in so /place, /nearby and the atlas tools don't pay for a field they ignore."""

    def setup_method(self):
        self._session, self._flag = bot._get_session, bot.FOOD_OPEN_HOURS
        bot.FOOD_OPEN_HOURS = True
        self.seen = []

        outer = self

        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"results": []}

        class _S:
            def get(_self, url, **kw):
                outer.seen.append(kw.get("params") or {})
                return _R()

        bot._get_session = lambda: _S()

    def teardown_method(self):
        bot._get_session, bot.FOOD_OPEN_HOURS = self._session, self._flag

    def test_default_call_does_not_request_hours(self):
        bot._fetch_tomtom_search("restaurant", 47.6, -122.3, 5000)
        assert "openingHours" not in self.seen[0]

    def test_opt_in_requests_them(self):
        bot._fetch_tomtom_search("restaurant", 47.6, -122.3, 5000, True)
        assert self.seen[0]["openingHours"] == "nextSevenDays"

    def test_kill_switch_suppresses_them_even_when_asked(self):
        bot.FOOD_OPEN_HOURS = False
        bot._fetch_tomtom_search("restaurant", 47.6, -122.3, 5000, True)
        assert "openingHours" not in self.seen[0]


class TestHoursNoteCodeReviewFixes:
    """Defects /code-review found on v2026-08-10.1 before it merged."""

    def test_an_always_open_poi_gets_no_invented_closing_time(self):
        """nextSevenDays returns 24/7 places as ONE week-long range; printing its end hour
        claimed 'open until 00:00' for somewhere that never closes."""
        poi = TestPoiHoursNote._poi(("2026-08-10", 0, 0, "2026-08-17", 0, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 9, 0)) == "open now"

    def test_a_same_day_range_still_reports_its_closing_time(self):
        poi = TestPoiHoursNote._poi(("2026-08-10", 7, 0, "2026-08-10", 21, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 10, 9, 0)) == "open until 21:00"

    def test_a_midnight_crossing_range_keeps_its_closing_time(self):
        """e.date() is today here, so the clock time is meaningful and must survive."""
        poi = TestPoiHoursNote._poi(("2026-08-10", 18, 0, "2026-08-11", 2, 0))
        assert bot._poi_hours_note(poi, datetime(2026, 8, 11, 0, 30)) == "open until 02:00"


class TestAtlasAuditLookupFailures:
    """The first real run rate-limited after nine entries and reported the rest — Marymoor
    Park, Ballard Locks, Bellevue Downtown Park — as NOT FOUND, i.e. as fabricated. An
    unanswered question is not a negative answer."""

    def test_a_failed_lookup_is_not_a_missing_place(self):
        aa = _atlas_audit()
        assert aa.verdict(None, 15, failed=True) == "LOOKUP FAILED"
        assert aa.verdict(None, 15) == "NOT FOUND"

    def test_rate_limits_are_recognised_whatever_the_wording(self):
        aa = _atlas_audit()
        assert aa._is_rate_limit("rate limited (HTTP 429) — wait a moment")
        assert aa._is_rate_limit("HTTP 429")
        assert not aa._is_rate_limit("HTTP 401")
        assert not aa._is_rate_limit("")

    def test_a_rate_limit_is_retried_then_succeeds(self, monkeypatch):
        aa = _atlas_audit()
        monkeypatch.setattr(aa.time, "sleep", lambda s: None)
        calls = []

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                calls.append(q)
                if len(calls) < 3:
                    raise RuntimeError("rate limited (HTTP 429) — wait a moment")
                return [{"poi": {"name": q}}]

        results, err = aa.lookup(_Bot, "Marymoor Park", (47.6, -122.3), 0)
        assert err is None and len(calls) == 3
        assert results[0]["poi"]["name"] == "Marymoor Park"

    def test_a_non_rate_limit_error_does_not_burn_retries(self, monkeypatch):
        aa = _atlas_audit()
        monkeypatch.setattr(aa.time, "sleep", lambda s: None)
        calls = []

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                calls.append(q)
                raise RuntimeError("HTTP 401 — bad key")

        results, err = aa.lookup(_Bot, "x", (47.6, -122.3), 0)
        assert results is None and "401" in err and len(calls) == 1

    def test_a_persistent_rate_limit_gives_up_and_says_so(self, monkeypatch):
        aa = _atlas_audit()
        monkeypatch.setattr(aa.time, "sleep", lambda s: None)

        class _Bot:
            @staticmethod
            def _fetch_tomtom_search(q, lat, lon, radius):
                raise RuntimeError("rate limited (HTTP 429) — wait a moment")

        results, err = aa.lookup(_Bot, "x", (47.6, -122.3), 0)
        assert results is None and "429" in err

    def test_report_counts_failures_apart_from_flags(self, capsys):
        aa = _atlas_audit()
        rows = [
            ("a — x", "a", "a", "Bellevue", 3.0, "ok"),
            ("b — x", "b", "", "", None, "NOT FOUND"),
            ("c — x", "c", "", "", None, "LOOKUP FAILED"),
        ]
        flagged, failed = aa.report("priya", rows)
        assert (flagged, failed) == (1, 1)      # never summed into one number
        out = capsys.readouterr().out
        assert "2 checked" in out and "1 flagged" in out
        assert "NOT CHECKED" in out
        # The town tally must not imply it covered entries that were never looked up.
        assert "of 2 checked" in out


class TestAtlasAuditAreaFallback:
    """Half an atlas is districts and neighbourhoods, not businesses. A POI-only audit
    called priya's real "Old Bellevue (Main Street)" fabricated (observed 2026-08-10)."""

    def test_a_district_matches_on_its_address(self):
        aa = _atlas_audit()
        results = [{"address": {"freeformAddress": "Old Bellevue, Bellevue, WA"},
                    "position": {"lat": 47.61, "lon": -122.20}}]
        assert aa.best_area(results, "Old Bellevue") is not None

    def test_the_area_pass_does_not_reopen_the_fuzzy_hole(self):
        """The whole reason POI matching came first: a geography named Bay Terrace Road
        must still lose to a query for Meydenbauer Bay Park."""
        aa = _atlas_audit()
        results = [{"address": {"freeformAddress": "Bay Terrace Road, Seattle, WA"}}]
        assert aa.best_area(results, "Meydenbauer Bay Park") is None

    def test_a_real_poi_is_never_handled_by_the_area_pass(self):
        aa = _atlas_audit()
        results = [{"poi": {"name": "Marymoor Park"},
                    "address": {"freeformAddress": "Marymoor Park, Redmond, WA"}}]
        assert aa.best_area(results, "Marymoor Park") is None
        assert aa.best_poi(results, "Marymoor Park") is not None

    def test_an_invented_place_still_fails_both_passes(self):
        aa = _atlas_audit()
        results = []
        assert aa.best_poi(results, "The Gilded Otter") is None
        assert aa.best_area(results, "The Gilded Otter") is None


class TestTomTomQueryEscaping:
    """v2026-08-10.2: a place name containing "/" became extra URL path segments and
    TomTom returned 404. Found by tools/atlas_audit.py against jules's atlas, on
    "Boulevard Park / Taylor Dock" and "Mt. Baker Highway / Artist Point"."""

    def setup_method(self):
        self._session = bot._get_session
        self.urls = []
        outer = self

        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"results": []}

        class _S:
            def get(_self, url, **kw):
                outer.urls.append(url)
                return _R()

        bot._get_session = lambda: _S()

    def teardown_method(self):
        bot._get_session = self._session

    def test_search_escapes_a_slash_into_one_path_segment(self):
        bot._fetch_tomtom_search("Boulevard Park / Taylor Dock", 48.75, -122.47, 1000)
        assert "%2F" in self.urls[0]
        # The bug: the query must not introduce path segments of its own.
        tail = self.urls[0].split("/search/2/search/", 1)[1]
        assert tail.count("/") == 0, tail

    def test_geocode_escapes_a_slash_too(self):
        """Same shape, same file, one call site apart — fixing only the one that failed
        would leave /route and MAP_INTENT destinations still 404ing."""
        bot._tomtom_geocode("Mt. Baker Highway / Artist Point")
        tail = self.urls[0].split("/geocode/", 1)[1]
        assert "%2F" in self.urls[0] and tail.count("/") == 0, tail

    def test_ordinary_queries_are_unharmed(self):
        bot._fetch_tomtom_search("restaurant", 47.6, -122.3, 5000)
        assert self.urls[0].endswith("/search/2/search/restaurant.json")

    def test_other_reserved_characters_survive(self):
        bot._fetch_tomtom_search("Bob's Fish & Chips", 47.6, -122.3, 5000)
        tail = self.urls[0].split("/search/2/search/", 1)[1]
        assert tail.count("/") == 0 and "%26" in tail


class TestAtlasAuditPicksTheNearestMatch:
    """Emily's atlas names "The Spar", a real Olympia bar. Anchored on Olympia, TomTom's
    top name-match was the Tacoma one 26 miles out and the audit reported FAR on a place
    five minutes from her (2026-08-10). Relevance order is not distance order."""

    def test_the_nearest_name_match_wins_not_the_first(self):
        aa = _atlas_audit()
        results = [
            {"poi": {"name": "The Spar"}, "dist": 42000,
             "address": {"municipality": "Tacoma"}},
            {"poi": {"name": "The Spar Cafe"}, "dist": 300,
             "address": {"municipality": "Olympia"}},
        ]
        hit = aa.best_poi(results, "The Spar")
        assert hit["address"]["municipality"] == "Olympia"

    def test_the_area_pass_is_distance_ordered_too(self):
        aa = _atlas_audit()
        results = [
            {"dist": 50000, "address": {"freeformAddress": "Old Bellevue, Somewhere, WA"}},
            {"dist": 800, "address": {"freeformAddress": "Old Bellevue, Bellevue, WA"}},
        ]
        assert aa.best_area(results, "Old Bellevue")["dist"] == 800

    def test_a_missing_dist_never_beats_a_real_one(self):
        aa = _atlas_audit()
        results = [
            {"poi": {"name": "Marymoor Park"}, "address": {"municipality": "Nowhere"}},
            {"poi": {"name": "Marymoor Park"}, "dist": 1200,
             "address": {"municipality": "Redmond"}},
        ]
        assert aa.best_poi(results, "Marymoor Park")["address"]["municipality"] == "Redmond"


class TestAtlasAuditSkipsDescriptions:
    """Owner, 2026-08-10: "They're not real places so there's no point in trying to find
    them on TomTom." Every string below is a real line from a real atlas, taken from the
    seven-instance run — not invented examples."""

    DESCRIPTIONS = [
        "The mailbox", "That one parking garage roof",
        "The convenience store two blocks over",
        "The really good ramen place that delivers",
        "That café where the wifi is fast and no one talks to you",
        "The park bench she found that faces away from everything",
        "The 24-hour pharmacy", "That vintage shop with the unsorted bins",
        "The rooftop of her building (technically not allowed)",
        "The library branch closest to her", "A friend's place two neighborhoods over",
        "The overpass that has a good view of the freight trains",
        "That one park where the ducks are extremely bold",
        "Night bus route she knows by heart",
        "That alley with the impressive mural",
        "The food cart pod she considers her main restaurant",
        "The shop", "The rented room above the bar on Fourth",
        "His apartment, on the eastside", "The dealership", "Her parents' house",
    ]
    NAMED = [
        "The Spar", "Powell's Books", "Lone Fir Cemetery", "Marymoor Park",
        "Old Bellevue (Main Street)", "Boulevard Park / Taylor Dock",
        "Mt. Baker Highway / Artist Point", "The Deschutes Parkway, along the lake",
        "Cape Disappointment", "Westport", "Factoria", "Anacortes",
        "The 5 Point Cafe", "Bellevue Arts Museum", "Willamette River East Bank Esplanade",
    ]

    def test_descriptions_are_not_looked_up(self):
        aa = _atlas_audit()
        wrong = [s for s in self.DESCRIPTIONS if aa.looks_like_a_named_place(s)]
        assert wrong == [], f"would waste a lookup on: {wrong}"

    def test_real_place_names_still_are(self):
        aa = _atlas_audit()
        wrong = [s for s in self.NAMED if not aa.looks_like_a_named_place(s)]
        assert wrong == [], f"would skip auditing: {wrong}"

    def test_empty_and_junk_are_skipped_not_crashed(self):
        aa = _atlas_audit()
        for junk in ("", None, "   ", "!!!"):
            assert aa.looks_like_a_named_place(junk) is False

    def test_a_skipped_entry_is_not_a_flag(self):
        aa = _atlas_audit()
        rows = [("a — x", "The mailbox", "", "", None, "not a place name"),
                ("b — x", "Powell's Books", "", "", None, "NOT FOUND")]
        flagged, failed = aa.report("bonnie", rows)
        assert (flagged, failed) == (1, 0)


class TestAtlasAuditDescriptiveMarkers:
    """Pins the marker set specifically. Break-testing the skip against the 21 real
    descriptive lines came back GREEN with markers disabled — capitalisation alone decided
    every one of them, so the marker branch was untested code claiming to do work (C18: a
    break-test proves one assertion, not the check).

    These are where it actually earns its place: an entry with no em dash to split on, so
    place_name() returns the whole line, carrying a real proper noun AND sentence
    structure. Capitalisation says "named place"; the marker says "no, that's a sentence"."""

    SENTENCES_ABOUT_PLACES = [
        "Marymoor Park where she runs the loop",
        "Powell's Books that she avoids on weekends",
        "The Spar when it is not packed",
        "Lone Fir Cemetery with the old headstones",
    ]

    def test_a_proper_noun_inside_a_sentence_is_still_a_sentence(self):
        aa = _atlas_audit()
        wrong = [s for s in self.SENTENCES_ABOUT_PLACES if aa.looks_like_a_named_place(s)]
        assert wrong == [], f"capitalisation alone would look these up: {wrong}"

    def test_the_same_names_without_the_sentence_are_looked_up(self):
        """The control: strip the clause and each becomes a lookup again, so the test
        above is pinning the marker and not just rejecting these strings outright."""
        aa = _atlas_audit()
        for s in ("Marymoor Park", "Powell's Books", "The Spar", "Lone Fir Cemetery"):
            assert aa.looks_like_a_named_place(s), s


class TestPlaceAnchorsOnHer:
    """v2026-08-10.3: /place anchored only on the user's pin, so an instance they had
    never shared a location with searched nationwide — `/place Boulevard Park` on a
    Bellingham character returned Henderson NV and El Paso TX."""

    CHAT = 8801

    def setup_method(self):
        self._saved = (bot.PLACE_ANCHOR_HER, bot.WEATHER_LAT, bot.WEATHER_LON,
                       bot.WEATHER_LOCATION)
        bot.PLACE_ANCHOR_HER = True
        bot.WEATHER_LAT, bot.WEATHER_LON = "48.7519", "-122.4787"    # Bellingham
        bot.WEATHER_LOCATION = "Bellingham"
        bot.user_location.pop(self.CHAT, None)

    def teardown_method(self):
        (bot.PLACE_ANCHOR_HER, bot.WEATHER_LAT, bot.WEATHER_LON,
         bot.WEATHER_LOCATION) = self._saved
        bot.user_location.pop(self.CHAT, None)

    def test_no_pin_anchors_on_her_city_not_nowhere(self):
        lat, lon, whose = bot._place_anchor(self.CHAT)
        assert (round(lat, 3), round(lon, 3)) == (48.752, -122.479)
        assert whose == "Bellingham"

    def test_a_fresh_pin_overrides_her(self):
        bot.user_location[self.CHAT] = {"lat": 47.6, "lon": -122.3, "ts": time.time(),
                                        "live_until": None}
        lat, lon, whose = bot._place_anchor(self.CHAT)
        assert (lat, lon) == (47.6, -122.3) and whose == "your location"

    def test_a_stale_pin_does_not_override_her(self):
        """Her home is a better guess than where they were last week."""
        bot.user_location[self.CHAT] = {"lat": 47.6, "lon": -122.3,
                                        "ts": time.time() - 30 * 3600, "live_until": None}
        _, _, whose = bot._place_anchor(self.CHAT)
        assert whose == "Bellingham"

    def test_kill_switch_restores_the_old_unanchored_behaviour(self):
        bot.PLACE_ANCHOR_HER = False
        assert bot._place_anchor(self.CHAT) == (None, None, "")

    def test_unparseable_coordinates_degrade_instead_of_raising(self):
        bot.WEATHER_LAT = "not-a-number"
        assert bot._place_anchor(self.CHAT) == (None, None, "")


class TestPlaceResultsShowDistance:
    def test_results_are_labelled_with_distance(self):
        results = [
            {"poi": {"name": "Boulevard Park"}, "dist": 1200, "address": {}},
            {"poi": {"name": "Castner Range"}, "dist": 2_400_000, "address": {}},
        ]
        out = bot._format_place_results(results)
        # The defect: nothing in the reply revealed that result 2 was a thousand miles off.
        assert "·" in out.split("Castner Range")[1].split("\n")[0]

    def test_relevance_order_is_preserved_not_resorted(self):
        """/nearby coffee wants the closest; /place Mount Baker wants the mountain.
        Re-ranking five results by distance and keeping three drops the exact match in
        favour of a nearer theatre and a nearer street."""
        results = [
            {"poi": {"name": "Mount Baker"}, "dist": 90_000, "address": {}},
            {"poi": {"name": "Mount Baker Theatre"}, "dist": 800, "address": {}},
            {"poi": {"name": "Mount Baker Apartments"}, "dist": 900, "address": {}},
        ]
        out = bot._format_place_results(results)
        assert out.splitlines()[0].startswith("📍 Mount Baker ·"), out.splitlines()[0]

    def test_an_unanchored_search_still_renders(self):
        results = [{"poi": {"name": "Boulevard Park"},
                    "address": {"freeformAddress": "Boulevard Park, WA"}}]
        assert "Boulevard Park, WA" in bot._format_place_results(results)


class TestSelfiePreservesWornFaceItems:
    """ROADMAP 3.17. Priya's bindi survived in about half of six selfies; the rule had a
    dedicated clause for eyewear and nothing for any other worn face item."""

    def test_the_clause_is_stated_both_ways(self):
        rule = bot._SELFIE_PRESERVE_RULE
        assert "whatever is there in the reference is there here" in rule
        assert "whatever is absent stays absent" in rule

    def test_it_names_a_category_never_a_character(self):
        """Same guard as the eyewear clause: naming priya's bindi would be the
        character-bleed trap of v2026-08-01.8's courier jacket."""
        rule = bot._SELFIE_PRESERVE_RULE.lower()
        for trait in ("bindi", "tamil", "septum", "freckles", "tattoo"):
            assert trait not in rule, trait


class TestPlaceCmdRuns:
    """The diff rewrote place_cmd's control flow and no test called it — the exact gap the
    delivery gate was built for after the /features ValueError shipped past four releases."""

    UID = 8802

    def setup_method(self):
        self._saved = (bot.TOMTOM_ENABLED, bot.PLACE_ANCHOR_HER, bot.WEATHER_LAT,
                       bot.WEATHER_LON, bot.WEATHER_LOCATION)
        bot.TOMTOM_ENABLED = True
        bot.PLACE_ANCHOR_HER = True
        bot.WEATHER_LAT, bot.WEATHER_LON = "48.7519", "-122.4787"
        bot.WEATHER_LOCATION = "Bellingham"
        bot.ALLOWED_USERS.add(self.UID)
        bot.user_location.pop(self.UID, None)

    def teardown_method(self):
        (bot.TOMTOM_ENABLED, bot.PLACE_ANCHOR_HER, bot.WEATHER_LAT,
         bot.WEATHER_LON, bot.WEATHER_LOCATION) = self._saved
        bot.ALLOWED_USERS.discard(self.UID)

    def _run(self, monkeypatch, args, results=None, raises=None):
        seen = {}

        def _fetch(q, lat=None, lon=None, radius=None, with_hours=False):
            seen["args"] = (q, lat, lon, radius)
            if raises:
                raise raises
            return results or []

        monkeypatch.setattr(bot, "_fetch_tomtom_search", _fetch)
        u, m = _cmd_update(self.UID)
        asyncio.run(bot.place_cmd(u, _cmd_ctx(*args)))
        return m.sent, seen

    def test_it_answers_and_anchors_on_her_city(self, monkeypatch):
        sent, seen = self._run(monkeypatch, ["Boulevard", "Park"],
                               [{"poi": {"name": "Boulevard Park"}, "dist": 1200,
                                 "address": {"freeformAddress": "Boulevard Park, WA"}}])
        assert sent and "Boulevard Park" in sent[0]
        assert "near Bellingham" in sent[0]
        q, lat, lon, radius = seen["args"]
        assert q == "Boulevard Park" and round(lat, 3) == 48.752
        assert radius is None, "a radius would filter, not bias"

    def test_no_args_explains_itself(self, monkeypatch):
        sent, _ = self._run(monkeypatch, [])
        assert "Usage" in sent[0]

    def test_a_tomtom_failure_is_reported_not_raised(self, monkeypatch):
        sent, _ = self._run(monkeypatch, ["x"], raises=bot._TomTomError("HTTP 500"))
        assert "lookup failed" in sent[0].lower()

    def test_no_matches_says_so(self, monkeypatch):
        sent, _ = self._run(monkeypatch, ["nowhere"], [])
        assert "No matches found" in sent[0]


class TestWeatherConfigWarning:
    """v2026-08-10.4. WEATHER_LOCATION is a LABEL the prompt asserts and the selfie prompt
    stamps on backgrounds; WEATHER_LAT/WEATHER_LON are what the weather API reads. Nothing
    tied them together, so jules was labelled Bellingham and fetched Seattle's weather —
    87 miles south — from creation until 2026-08-10. The exact fleet state that day is the
    test matrix below."""

    LAT, LON = bot._WEATHER_LAT_DEFAULT, bot._WEATHER_LON_DEFAULT

    def test_the_jules_case_warns(self):
        w = bot._weather_config_warning("Bellingham", self.LAT, self.LON)
        assert len(w) == 1
        assert "Bellingham" in w[0] and "Seattle's weather" in w[0]

    def test_defaults_everywhere_are_coherent(self):
        """nora, cass and priya: nothing set at all. Seattle label, Seattle coordinates —
        no warning, because nobody claimed to be anywhere else."""
        assert bot._weather_config_warning("Seattle", self.LAT, self.LON) == []

    def test_both_set_is_trusted(self):
        """bonnie (Burlington), emily and marcus (Olympia): label and coordinates both
        set. Whether they AGREE is not checkable here — only that the operator set both."""
        assert bot._weather_config_warning("Burlington", "48.4759", "-122.3254") == []
        assert bot._weather_config_warning("Olympia", "47.0379", "-122.9007") == []

    def test_one_coordinate_changed_is_enough_to_count_as_set(self):
        assert bot._weather_config_warning("Bellingham", "48.7519", self.LON) == []

    def test_the_whole_fleet_of_2026_08_10_produces_exactly_one_warning(self):
        fleet = {
            "nora": ("Seattle", self.LAT, self.LON),
            "bonnie": ("Burlington", "48.4759", "-122.3254"),
            "cass": ("Seattle", self.LAT, self.LON),
            "emily": ("Olympia", "47.0379", "-122.9007"),
            "jules": ("Bellingham", self.LAT, self.LON),
            "marcus": ("Olympia", "47.0379", "-122.9007"),
            "priya": ("Seattle", self.LAT, self.LON),
        }
        warned = [n for n, cfg in fleet.items() if bot._weather_config_warning(*cfg)]
        assert warned == ["jules"], warned


class TestAuditShowsWeatherCoordinates:
    def test_the_audit_location_carries_the_coordinates(self, monkeypatch):
        monkeypatch.setattr(bot, "WEATHER_LOCATION", "Bellingham")
        monkeypatch.setattr(bot, "WEATHER_LAT", "47.6062")
        monkeypatch.setattr(bot, "WEATHER_LON", "-122.3321")
        d = bot.gather_audit_data()
        assert d["location"] == "Bellingham (47.6062, -122.3321)"


class TestErrorsLogNoticeFiltering:
    """v2026-08-10.5: jules logged "EPISODIC_RECALL is set but numpy is missing" on every
    startup for days, inside a 1.59 MB errors.log, while three features sat inert
    fleet-wide. Four routine lines per restart buried it."""

    NOTICE = f"2026-08-10 15:29:24 [WARNING] companion: {bot._NOTICE_PREFIX}=== STARTUP AUDIT === v1"
    STOP = f"2026-08-10 15:13:44 [WARNING] companion: {bot._NOTICE_PREFIX}[shutdown] graceful stop — saving state."
    REAL = "2026-08-10 14:46:06 [WARNING] companion: EPISODIC_RECALL is set but numpy is missing"

    def _log(self, monkeypatch, tmp_path, lines):
        p = tmp_path / "errors.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr(bot, "_error_log_path", p)

    def test_notices_are_hidden_and_counted(self, monkeypatch, tmp_path):
        self._log(monkeypatch, tmp_path, [self.STOP, self.NOTICE, self.REAL, self.NOTICE])
        lines, hidden = bot.tail_error_lines(20)
        assert lines == [self.REAL]
        # Counted, not silently dropped — an unexplained gap is not information.
        assert hidden == 3

    def test_all_shows_everything(self, monkeypatch, tmp_path):
        self._log(monkeypatch, tmp_path, [self.STOP, self.REAL])
        lines, hidden = bot.tail_error_lines(20, include_notices=True)
        assert len(lines) == 2 and hidden == 0

    def test_a_log_of_only_notices_reads_as_clean(self, monkeypatch, tmp_path):
        self._log(monkeypatch, tmp_path, [self.STOP, self.NOTICE])
        lines, hidden = bot.tail_error_lines(20)
        assert lines == [] and hidden == 2


class TestNoticePrefixKeepsCrashTriageWorking:
    """The prefix goes on the MESSAGE so line[:19] date parsing and the substring matches
    in _tally_unexpected_restarts survive it. That coupling is invisible and would fail
    as a silently miscounted restart storm, so it is pinned."""

    def test_a_deploy_restart_is_still_recognised_as_intentional(self):
        from datetime import datetime as _dt
        lines = [
            f"2026-08-10 15:13:44 [WARNING] companion: {bot._NOTICE_PREFIX}[shutdown] graceful stop — saving state.",
            f"2026-08-10 15:13:45 [WARNING] companion: {bot._NOTICE_PREFIX}=== STARTUP AUDIT === v1 | PID: 1",
        ]
        cutoff = _dt(2026, 8, 10, 15, 0, 0)
        assert bot._tally_unexpected_restarts(lines, cutoff) == 0

    def test_a_crash_restart_is_still_counted(self):
        from datetime import datetime as _dt
        lines = [f"2026-08-10 15:13:45 [WARNING] companion: {bot._NOTICE_PREFIX}=== STARTUP AUDIT === v1 | PID: 1"]
        cutoff = _dt(2026, 8, 10, 15, 0, 0)
        assert bot._tally_unexpected_restarts(lines, cutoff) == 1

    def test_the_timestamp_is_still_at_the_front_of_the_line(self):
        """line[:19] is parsed with strptime; a prefix in the wrong place breaks it."""
        line = f"2026-08-10 15:13:45 [WARNING] companion: {bot._NOTICE_PREFIX}=== STARTUP AUDIT ==="
        from datetime import datetime as _dt
        assert _dt.strptime(line[:19], "%Y-%m-%d %H:%M:%S").year == 2026
