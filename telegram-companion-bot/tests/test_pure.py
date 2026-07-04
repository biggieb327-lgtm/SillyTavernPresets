"""Pure-function tests for bot.py. Loaded and run by run.py, which passes in `extract` (pulls a
function from bot.py source) and `check(name, cond)` (records a pass/fail). Each block covers a
function that had a real bug or guards an invariant one of the two audits found."""
import re
import json
import time as _time
from datetime import datetime, timedelta, date, time as dtime


def run(extract, check):
    # --- _parse_hhmm: the single time-parse chokepoint (Part 1) ---
    p = extract(["_parse_hhmm"])["_parse_hhmm"]
    check("_parse_hhmm valid", p("08:30") == (8, 30))
    check("_parse_hhmm midnight", p("00:00") == (0, 0))
    check("_parse_hhmm hour out of range", p("25:00") is None)
    check("_parse_hhmm minute out of range", p("08:75") is None)
    check("_parse_hhmm empty", p("") is None)
    check("_parse_hhmm no colon", p("9") is None)
    check("_parse_hhmm non-numeric", p("aa:bb") is None)
    check("_parse_hhmm extra seconds tolerated", p("08:30:00") == (8, 30))

    # --- parse_cron_schedule (bug: 25:00 persisted then crashed boot) ---
    ns = extract(["_parse_hhmm", "parse_cron_schedule"], {"re": re})
    pcs = ns["parse_cron_schedule"]
    check("cron daily valid", pcs("daily 08:30") == {"type": "daily", "hour": 8, "minute": 30})
    check("cron daily out of range", pcs("daily 25:00") is None)
    check("cron interval hours", pcs("every 2h") == {"type": "interval", "seconds": 7200})
    check("cron interval minutes", pcs("every 30m") == {"type": "interval", "seconds": 1800})
    check("cron garbage", pcs("nonsense") is None)

    # --- parse_when (bug: /remindme 25:00 and 2026-13-40 raised) ---
    ns = extract(["_parse_hhmm", "parse_when"],
                 {"re": re, "datetime": datetime, "timedelta": timedelta, "date": date, "TZ": None})
    pw = ns["parse_when"]
    check("parse_when relative", pw(["30m", "ping"])[0] is not None)
    check("parse_when valid HH:MM", pw(["08:30", "meds"])[0] is not None)
    check("parse_when hour out of range", pw(["25:00", "x"]) == (None, None))
    check("parse_when bad date", pw(["2026-13-40", "x"]) == (None, None))
    check("parse_when tomorrow bad time", pw(["tomorrow", "30:00", "x"]) == (None, None))
    check("parse_when tomorrow default time", pw(["tomorrow", "lunch"])[0] is not None)
    check("parse_when empty", pw([]) == (None, None))

    # --- next_occurrence / next_occurrence_p / due_between (bug: only first occurrence found) ---
    import calendar
    ns = extract(["next_occurrence", "next_occurrence_p", "due_between"],
                 {"date": date, "timedelta": timedelta, "calendar": calendar})
    ns["payments"] = [{"recur": "every", "start": "2026-06-28", "interval": 3, "count": None, "name": "L", "amount": 1}]
    db = ns["due_between"]
    got = db(date(2026, 7, 2), date(2026, 7, 8))
    check("due_between finds multiple in window", len(got) == 2)
    check("due_between dates correct", [d for d, _ in got] == [date(2026, 7, 4), date(2026, 7, 7)])
    ns["payments"] = [{"recur": "monthly", "day": 15, "name": "rent", "amount": 100}]
    got2 = ns["due_between"](date(2026, 7, 1), date(2026, 7, 31))
    check("due_between monthly one hit", len(got2) == 1 and got2[0][0] == date(2026, 7, 15))
    # next_occurrence day-of-month clamp (31 in a 30-day month)
    check("next_occurrence clamps day 31", ns["next_occurrence"](31, date(2026, 4, 1)) == date(2026, 4, 30))

    # --- in_quiet_hours (wrap-past-midnight logic) ---
    ns = extract(["in_quiet_hours"], {"datetime": datetime, "TZ": None,
                                      "_QS_H": 22, "_QS_M": 0, "_QE_H": 8, "_QE_M": 0})
    iqh = ns["in_quiet_hours"]
    check("quiet at 02:00", iqh(datetime(2026, 7, 4, 2, 0)) is True)
    check("quiet at 23:00", iqh(datetime(2026, 7, 4, 23, 0)) is True)
    check("not quiet at 12:00", iqh(datetime(2026, 7, 4, 12, 0)) is False)
    check("not quiet at 08:00 boundary", iqh(datetime(2026, 7, 4, 8, 0)) is False)

    # --- _seconds_until_daytime_slot (Part-of B3: never lands back in quiet hours) ---
    import random as _random
    class _FixedNow(datetime):
        _fx = None
        @classmethod
        def now(cls, tz=None):
            return cls._fx
    ns = extract(["in_quiet_hours", "_seconds_until_daytime_slot"],
                 {"datetime": _FixedNow, "timedelta": timedelta, "random": _random, "TZ": None,
                  "_QS_H": 22, "_QS_M": 0, "_QE_H": 8, "_QE_M": 0})
    slot = ns["_seconds_until_daytime_slot"]
    ok = True
    for hh in (2, 23, 6):
        _FixedNow._fx = _FixedNow(2026, 7, 4, hh, 0, 0)
        for _ in range(100):
            tgt = _FixedNow._fx + timedelta(seconds=slot())
            if not (8 <= tgt.hour + tgt.minute / 60 < 22):
                ok = False
    check("daytime slot always lands in waking window", ok)

    # --- _reminder_due_str (bug: /reminders crashed on a daily reminder) ---
    ns = extract(["fmt_due_dt", "_reminder_due_str"], {"datetime": datetime})
    rds = ns["_reminder_due_str"]
    check("reminder_due_str daily", rds({"daily": True, "due": "08:30"}) == "daily at 08:30")
    check("reminder_due_str one-off no crash", isinstance(rds({"due": "2026-07-10T14:00:00"}), str))

    # --- _looks_like_refusal (bug: false-positive on 'considered high risk') ---
    ns = extract(["_REFUSAL_MARKERS", "_looks_like_refusal"])
    lr = ns["_looks_like_refusal"]
    check("refusal real", lr("The request was rejected because it was considered high risk.") is True)
    check("refusal benign not flagged", lr("honestly that's considered high risk, be careful") is False)
    check("refusal empty", lr("") is False)

    # --- _format_json_for_prompt (bug: crashed on non-dict top-level JSON) ---
    ns = extract(["_format_json_for_prompt"], {"json": json})
    fj = ns["_format_json_for_prompt"]
    for bad in ([1, 2, 3], "hi", 42, None, True):
        try:
            fj(bad, "x.json")
        except Exception:
            check(f"format_json non-dict {type(bad).__name__}", False)
            break
    else:
        check("format_json non-dict inputs all safe", True)

    # --- _valid_reminder / _valid_cron / _valid_payment (Part 2 load-time guards) ---
    ns = extract(["_parse_hhmm", "_valid_reminder", "_valid_cron", "_valid_payment"],
                 {"datetime": datetime, "date": date})
    vr, vc, vp = ns["_valid_reminder"], ns["_valid_cron"], ns["_valid_payment"]
    check("valid_reminder daily ok", vr({"id": 1, "chat_id": 5, "due": "08:30", "daily": True}) is True)
    check("valid_reminder daily bad time", vr({"id": 1, "chat_id": 5, "due": "25:00", "daily": True}) is False)
    check("valid_reminder oneoff ok", vr({"id": 1, "chat_id": 5, "due": "2026-07-10T09:00:00"}) is True)
    check("valid_reminder missing id", vr({"chat_id": 5, "due": "08:30", "daily": True}) is False)
    check("valid_cron daily ok", vc({"id": 1, "chat_id": 5, "schedule": {"type": "daily", "hour": 8, "minute": 0}}) is True)
    check("valid_cron daily bad", vc({"id": 1, "chat_id": 5, "schedule": {"type": "daily", "hour": 25, "minute": 0}}) is False)
    check("valid_cron interval ok", vc({"id": 1, "chat_id": 5, "schedule": {"type": "interval", "seconds": 600}}) is True)
    check("valid_payment monthly ok", vp({"name": "r", "amount": 10, "recur": "monthly", "day": 15}) is True)
    check("valid_payment bad day", vp({"name": "r", "amount": 10, "recur": "monthly", "day": 40}) is False)

    # --- mood decay: penalty must survive the immediately-following mood_now read (Part-of C1) ---
    ns = extract(["mood_now", "nudge_mood"], {"time": _time, "moods": {}})
    ns["nudge_mood"](999, 48.0)  # fresh chat, long gap -> penalty applied
    check("mood penalty not decayed away", ns["mood_now"](999) < -1.0)
