"""Message log (v2026-09-25.1, MESSAGE_LOG_DESIGN.md).

Driven through remember(), msglog_cmd, _prune_msglog and _msglog_status_line — nothing
here reads bot.py's source. The round trip through tools/rpzlib.py is the point of the
record shape, so one test parses a real log file with rpzlib's own load_log.
"""
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot

TOOLS = Path(__file__).resolve().parent.parent / "tools"
ADMIN = 7301


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    d = tmp_path / "msglog"
    monkeypatch.setattr(bot, "MSGLOG_DIR", d)
    monkeypatch.setattr(bot, "MESSAGE_LOG", True)
    monkeypatch.setattr(bot, "MESSAGE_LOG_DAYS", 30)
    monkeypatch.setattr(bot, "msglog_toggle", {})
    monkeypatch.setattr(bot, "save_state", lambda: None)
    return d


def _remember(cid, *turns):
    try:
        for t in turns:
            bot.remember(cid, *t)
    finally:
        bot.conversation_history.pop(cid, None)


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_remember_writes_one_line_per_turn_that_rpzlib_reads(logdir):
    cid = 880001
    _remember(cid, ("user", "hi there"), ("assistant", "the rain stopped — finally"))
    files = list((logdir / str(cid)).glob("*.jsonl"))
    assert len(files) == 1
    recs = _lines(files[0])
    assert [r["is_user"] for r in recs] == [True, False]
    assert [r["kind"] for r in recs] == ["chat", "chat"]
    assert recs[1]["mes"] == "the rain stopped — finally"
    assert all(r["ver"] == bot.BOT_VERSION and r["chat_id"] == cid for r in recs)
    assert files[0].read_text(encoding="utf-8").isascii(), "ensure_ascii=True on write"
    sys.path.insert(0, str(TOOLS))
    import rpzlib
    assert rpzlib.load_log(str(files[0])) == ["the rain stopped — finally"]


def test_kind_labels_group_and_proactive_turns(logdir):
    _remember(-100123, ("assistant", "group reply"))
    _remember(880002, ("user", "[you reached out first]", "synthetic"),
              ("assistant", "morning!", "proactive"))
    (g,) = (logdir / "-100123").glob("*.jsonl")
    assert _lines(g)[0]["kind"] == "group"
    (p,) = (logdir / "880002").glob("*.jsonl")
    recs = _lines(p)
    assert [(r["kind"], r["is_system"]) for r in recs] == [("synthetic", True), ("proactive", False)]


def test_toggle_off_writes_nothing(logdir):
    bot.msglog_toggle["on"] = False
    _remember(880003, ("assistant", "not logged"))
    assert not logdir.exists()


def test_kill_switch_beats_a_saved_toggle(logdir, monkeypatch):
    monkeypatch.setattr(bot, "MESSAGE_LOG", False)
    bot.msglog_toggle["on"] = True
    _remember(880004, ("assistant", "not logged"))
    assert not logdir.exists()
    assert bot._msglog_status_line().startswith("off (MESSAGE_LOG=0)")


def test_a_failed_write_never_breaks_remember(logdir):
    logdir.write_text("a file where the folder should be")
    cid = 880005
    try:
        bot.remember(cid, "assistant", "still remembered")
        assert bot.conversation_history[cid][-1]["content"] == "still remembered"
    finally:
        bot.conversation_history.pop(cid, None)


def test_prune_uses_the_filename_date_and_keeps_day_30(logdir):
    today = date(2026, 9, 25)
    chat = logdir / "880006"
    chat.mkdir(parents=True)
    for d in (today - timedelta(days=31), today - timedelta(days=30), today):
        (chat / f"{d.isoformat()}.jsonl").write_text("{}\n")
    (chat / "notes.txt").write_text("not a day file")
    old_only = logdir / "880007"
    old_only.mkdir()
    (old_only / f"{(today - timedelta(days=40)).isoformat()}.jsonl").write_text("{}\n")

    assert bot._prune_msglog(today=today, keep_days=30) == 2
    assert sorted(p.name for p in chat.iterdir()) == [
        "2026-08-26.jsonl", "2026-09-25.jsonl", "notes.txt"]
    assert not old_only.exists(), "an emptied chat folder is removed"


def test_prune_floor_is_one_day(logdir):
    today = date(2026, 9, 25)
    chat = logdir / "880008"
    chat.mkdir(parents=True)
    (chat / "2026-09-24.jsonl").write_text("{}\n")
    assert bot._prune_msglog(today=today, keep_days=0) == 0


# --- /msglog, driven with fake Telegram objects ---------------------------------------

class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.sent.append(text)


def _update(uid):
    msg = _Msg()
    return SimpleNamespace(message=msg, effective_chat=SimpleNamespace(id=uid),
                           effective_user=SimpleNamespace(id=uid, first_name="T")), msg


def _ctx(*args):
    return SimpleNamespace(args=list(args), bot=SimpleNamespace())


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(bot, "ALLOWED_USERS", set(bot.ALLOWED_USERS) | {ADMIN})
    return ADMIN


def test_msglog_cmd_status_off_on(logdir, admin):
    u, m = _update(admin)
    asyncio.run(bot.msglog_cmd(u, _ctx()))
    assert m.sent and m.sent[0].startswith("Message log: on,")

    asyncio.run(bot.msglog_cmd(u, _ctx("off")))
    assert bot.msglog_toggle == {"on": False} and "off via /msglog" in m.sent[-1]
    _remember(880009, ("assistant", "not logged"))
    assert not (logdir / "880009").exists()

    asyncio.run(bot.msglog_cmd(u, _ctx("on")))
    assert bot.msglog_toggle == {"on": True}
    _remember(880009, ("assistant", "logged"))
    assert list((logdir / "880009").glob("*.jsonl"))


def test_msglog_cmd_purge_needs_confirm(logdir, admin):
    _remember(880010, ("assistant", "x"))
    u, m = _update(admin)
    asyncio.run(bot.msglog_cmd(u, _ctx("purge")))
    assert "purge confirm" in m.sent[-1] and logdir.exists()
    asyncio.run(bot.msglog_cmd(u, _ctx("purge", "confirm")))
    assert m.sent[-1] == "Deleted 1 message-log day file(s)." and not logdir.exists()


def test_msglog_cmd_is_admin_gated(logdir, monkeypatch):
    outsider = 424299
    monkeypatch.setattr(bot, "get_owner", lambda: None)
    monkeypatch.setattr(bot, "ALLOWED_USERS", set())
    u, m = _update(outsider)
    asyncio.run(bot.msglog_cmd(u, _ctx("off")))
    assert m.sent == [] and bot.msglog_toggle == {}


def test_backup_archive_never_contains_the_message_log(tmp_path):
    """The log stays on the VPS only because vps-backup.sh copies top-level instance files.
    Run the real script against a fake tree and read the archive, so widening its find
    depth turns this red instead of quietly shipping chat logs to the off-box copy."""
    import subprocess
    import tarfile
    base = tmp_path / "bots"
    inst = base / "nora"
    (inst / "msglog" / "5550001").mkdir(parents=True)
    marker = "MSGLOG-MARKER-5f3a"  # searched in archive contents: the script's cp flattens
    (inst / "msglog" / "5550001" / "2026-09-25.jsonl").write_text(f'{{"mes": "{marker}"}}\n')
    (inst / "state.json").write_text("{}")
    (base / "audits").mkdir()
    (base / "audits" / "2026-09-27.md").write_text(marker)
    if Path("/etc/bot-backup.conf").exists():
        pytest.skip("a real /etc/bot-backup.conf would be sourced over this test's BACKUP_DIR")
    script = Path(__file__).resolve().parent.parent / "deploy" / "vps-backup.sh"
    # Hermetic harness, not a weakened check: the script refuses non-root (CI runs as a normal
    # user) and asks systemd for bot@ units (a real host would list real instances). Shim
    # both so it backs up exactly the fake tree; what it archives is untouched.
    shims = tmp_path / "bin"
    shims.mkdir()
    for name, body in (("id", "echo 0"), ("systemctl", "exit 0")):
        (shims / name).write_text(f"#!/bin/sh\n{body}\n")
        (shims / name).chmod(0o755)
    env = {"PATH": f"{shims}:/usr/bin:/bin", "BOT_BASE": str(base), "BACKUP_DIR": str(tmp_path / "out")}
    run = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    (archive,) = (tmp_path / "out").glob("bot-state-*.tar.gz")
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        leaked = [m.name for m in tar.getmembers()
                  if m.isfile() and marker.encode() in tar.extractfile(m).read()]
    assert any(n.endswith("nora/state.json") for n in names), names
    # paths alone cannot show a leak: the script's cp flattens subfolders into the instance
    # dir, so a leaked day file would be archived as nora/2026-09-25.jsonl
    assert leaked == [], leaked


def test_summary_survives_a_file_vanishing_mid_walk(logdir):
    _remember(880012, ("assistant", "a"))
    # a dangling symlink stats as FileNotFoundError, like a day file the prune job just deleted
    (logdir / "880012" / "2026-01-01.jsonl").symlink_to(logdir / "gone.jsonl")
    assert "chat(s)" in bot._msglog_status_line()


def test_logging_resumes_into_a_fresh_tree_after_purge(logdir):
    _remember(880013, ("assistant", "before"))
    assert bot._purge_msglog() == 1
    assert not logdir.exists() and not list(logdir.parent.glob("msglog.purge-*"))
    _remember(880013, ("assistant", "after"))
    (f,) = (logdir / "880013").glob("*.jsonl")
    assert [r["mes"] for r in _lines(f)] == ["after"]


def test_status_line_counts_files_on_disk(logdir):
    _remember(880011, ("assistant", "a"), ("user", "b"))
    line = bot._msglog_status_line()
    assert "1 chat(s), 1 day file(s)" in line and "keeps 30d" in line
