""".claude/tools/probe.py -- the one-command way to check what a bot.py function returns (C5).

Run as a subprocess, the way it is used: a result prints `  -> repr`, an exception prints
`  !! Type: message` and exits 1, so a failed probe can never read as a result.
"""
import subprocess
import sys
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / ".claude" / "tools" / "probe.py"


def _probe(*args):
    return subprocess.run([sys.executable, str(PROBE), *args], capture_output=True, text=True, timeout=120)


def test_a_result_prints_its_repr():
    p = _probe('bot._strip_persona_breaks("As an AI, I cannot. The rain stopped.")')
    assert p.returncode == 0, p.stderr
    assert "  -> 'The rain stopped.'" in p.stdout


def test_an_exception_is_marked_and_exits_1():
    p = _probe("bot.no_such_function(1)")
    assert p.returncode == 1
    assert "  !! AttributeError" in p.stdout and "->" not in p.stdout


def test_coroutines_are_awaited_and_tools_modules_import():
    p = _probe("-i", "rpzlib", 'rpzlib.clean("<think>x</think>hi")', "bot.asyncio.sleep(0, result=7)")
    assert p.returncode == 0, p.stderr
    assert "  -> 'hi'" in p.stdout and "  -> 7" in p.stdout
