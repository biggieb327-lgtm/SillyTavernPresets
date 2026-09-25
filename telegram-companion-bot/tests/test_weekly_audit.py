"""tools/weekly_audit.py -- driven against a fake /opt/telegram-bots tree.

Pins the outcome contract from the hubris skill: FLAG, OK, BASELINE and NOT CHECKED are
separate statuses and separate counts; "could not determine" never prints as a finding
or as a clean result.
"""
import json
import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
import weekly_audit as wa  # noqa: E402

TODAY = date(2026, 9, 27)


def _instance(base, name, replies=None, env=None, presets=None, card=True):
    d = base / name
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"error_counts": {"persona_break": [time.time()]}}))
    env = env or {}
    if card:
        shutil.copy(HERE.parent / "priya.json", d / "card.json")
        env.setdefault("CHARACTER_CARD", "card.json")
    for fname, text in (presets or {"preset-core.txt": "Replies stay short.\n"}).items():
        (d / fname).write_text(text)
    env.setdefault("PRESET_FILES", ",".join(presets or {"preset-core.txt": ""}))
    (d / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    if replies is not None:
        chat = d / "msglog" / "5550001"
        chat.mkdir(parents=True)
        lines = []
        for i, mes in enumerate(replies):
            lines.append(json.dumps({"chat_id": 5550001, "is_user": True, "is_system": False,
                                     "kind": "chat", "mes": f"user line {i}"}))
            lines.append(json.dumps({"chat_id": 5550001, "is_user": False, "is_system": False,
                                     "kind": "chat", "mes": mes}))
        (chat / f"{(TODAY - timedelta(days=1)).isoformat()}.jsonl").write_text("\n".join(lines) + "\n")
    return d


def _varied(n, capital=False):
    words = ["rain", "bus", "coffee", "deadline", "cat", "laundry", "standup", "tacos",
             "gym", "podcast", "sister", "landlord", "bike", "zine", "movie", "cold"]
    out = []
    for i in range(n):
        w = words[i % len(words)]
        s = f"ok so the {w} thing happened again at {i} and honestly {words[(i * 7) % len(words)]} too"
        out.append(s.capitalize() if capital else s)
    return out


def _by_rule(results, rule):
    return [r for r in results if r["rule"] == rule]


def _results(base, **kw):
    report, summary, payload, code = wa.run_audit(base, TODAY, **kw)
    return report, summary, payload, code


def test_tier1_bugs_flag_from_week_one_on_raw_text(tmp_path):
    replies = _varied(10)
    replies[3] = "<think>plan the reply</think>the rain stopped"
    replies[5] = "sure. let me know if you want to talk"
    _instance(tmp_path, "priya", replies)
    report, summary, _, code = _results(tmp_path)
    assert code == 1
    assert "priya chat 5550001 / reasoning-leak: 1 of 10" in summary
    assert '"let me know if" x1' in summary
    # rpzlib.clean() erases the think block, so this only works because tier 1 reads raw text
    assert wa.rpzlib.clean(replies[3]) == "the rain stopped"


def test_threshold_rules_wait_for_the_baseline(tmp_path):
    _instance(tmp_path, "priya", _varied(10, capital=True))
    report, *_ = _results(tmp_path)
    assert "BASELINE: priya-lowercase" in report and "(would flag)" in report
    audits = tmp_path / "audits"
    audits.mkdir()
    for k in (1, 2, 3):
        (audits / f"{(TODAY - timedelta(days=7 * k)).isoformat()}.json").write_text('{"instances": {}}')
    report, summary, _, code = _results(tmp_path)
    assert "priya-lowercase: 100% replies opening with a capital letter" in summary
    assert code == 1


def test_too_few_replies_is_not_checked_never_ok(tmp_path):
    _instance(tmp_path, "priya", _varied(3))
    report, summary, _, _ = _results(tmp_path)
    assert "NOT CHECKED: loops" in report and "only 3 replies" in report
    assert "OK: loops" not in report
    totals = report.split("Totals: ")[1].splitlines()[0]
    assert "NOT CHECKED" in totals and "FLAG" in totals  # counted separately, both present


def test_nothing_audited_is_loud_and_does_not_advance_the_baseline(tmp_path):
    _instance(tmp_path, "nora")  # no msglog at all
    assert wa.main(["--base", str(tmp_path), "--today", TODAY.isoformat()]) == 2
    assert (tmp_path / "audits" / f"{TODAY}.md").is_file()
    assert not (tmp_path / "audits" / f"{TODAY}.json").exists()
    _, summary, _, _ = _results(tmp_path)
    assert summary.startswith(f"Weekly audit {TODAY}: NOTHING AUDITED")
    assert "nora" in summary


def test_skipped_bot_listed_while_another_is_audited(tmp_path):
    _instance(tmp_path, "priya", _varied(10))
    _instance(tmp_path, "nora")
    report, summary, _, _ = _results(tmp_path)
    assert "## Skipped" in report and "- nora: no message-log files" in report
    assert "Skipped: nora" in summary


def test_negative_directive_in_a_preset_layer_is_flagged(tmp_path):
    _instance(tmp_path, "priya", _varied(10),
              presets={"preset-core.txt": "Replies stay short.\n", "preset-priya.txt": "ok\nNever use caps.\n"})
    report, summary, _, _ = _results(tmp_path)
    assert "priya / preset-negative-directives: preset-priya.txt:2" in summary


def test_card_regression_compares_with_last_week(tmp_path):
    _instance(tmp_path, "priya", _varied(10))
    _, _, payload, _ = _results(tmp_path)
    card = payload["instances"]["priya"]["card"]
    assert set(card) == {"non_ascii", "perm_tokens", "lore_missing"}
    audits = tmp_path / "audits"
    audits.mkdir()
    worse = dict(card, perm_tokens=card["perm_tokens"] - 10)
    (audits / f"{(TODAY - timedelta(days=7)).isoformat()}.json").write_text(
        json.dumps({"instances": {"priya": {"card": worse}}}))
    _, summary, _, _ = _results(tmp_path)
    assert f"perm_tokens {card['perm_tokens'] - 10} -> {card['perm_tokens']}" in summary


def test_missing_card_is_not_checked(tmp_path):
    _instance(tmp_path, "priya", _varied(10), card=False)
    report, *_ = _results(tmp_path)
    assert "NOT CHECKED: card-regression" in report and "NOT CHECKED: card-echo" in report


def test_main_writes_report_and_json(tmp_path):
    _instance(tmp_path, "priya", _varied(10))
    code = wa.main(["--base", str(tmp_path), "--today", TODAY.isoformat()])
    assert code in (0, 1)
    assert (tmp_path / "audits" / f"{TODAY}.md").read_text().startswith("# Weekly message audit")
    assert json.loads((tmp_path / "audits" / f"{TODAY}.json").read_text())["instances"]["priya"]["replies"] == 10


def test_notify_without_credentials_reports_instead_of_raising(tmp_path):
    _instance(tmp_path, "priya", _varied(10))
    assert wa.notify(tmp_path, "priya", "hi") == "no TELEGRAM_BOT_TOKEN or owner chat for priya"
