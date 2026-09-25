#!/usr/bin/env python3
"""probe.py -- run a bot.py (or tools/) function and print what it returns. C5's cheap half.

Reading source tells you what code says; this tells you what it produces, in one command,
so a behavioral claim costs one probe instead of a guess. bot.py is loaded the way the test
suite loads it (tests/conftest.py builds a throwaway instance dir and env), so no real
instance, token or network is touched.

  python3 .claude/tools/probe.py 'bot._strip_persona_breaks("As an AI, no. The rain stopped.")'
  python3 .claude/tools/probe.py -i rpzlib 'rpzlib.clean("<think>x</think>hi")'
  python3 .claude/tools/probe.py 'bot._strip_slop("Sure thing! ok")' 'bot.BOT_VERSION'

Each expression prints on its own line, then `  -> repr(result)`. A coroutine is awaited.
An exception prints `  !! Type: message` and makes the exit code 1, so a probe that failed
never reads like a result. Import noise (bot.py's startup logging) is hidden unless the
import itself fails. Needs the bot's dependencies: the session venv, or requirements.lock.
"""
import argparse
import asyncio
import contextlib
import importlib
import io
import sys
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parents[2] / "telegram-companion-bot"


def load(mods):
    """Import conftest (fixture env), bot, and any tools/ modules; return the namespace."""
    for p in (BOT_DIR / "tools", BOT_DIR / "tests", BOT_DIR):
        sys.path.insert(0, str(p))
    noise = io.StringIO()
    try:
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            import conftest  # noqa: F401  -- sets sys.argv[1]/BOT_HOME to a throwaway instance
            import bot
            ns = {"bot": bot}
            for m in mods:
                ns[m] = importlib.import_module(m)
    except BaseException:
        sys.stderr.write(noise.getvalue())
        raise
    return ns


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluate expressions against bot.py and print the results.")
    ap.add_argument("expr", nargs="+", help="Python expression; `bot` is imported")
    ap.add_argument("-i", "--import", dest="mods", action="append", default=[],
                    help="also import a module from telegram-companion-bot/tools (repeatable)")
    a = ap.parse_args(argv)
    try:
        ns = load(a.mods)
    except Exception as e:
        print(f"probe: could not import bot.py -- {type(e).__name__}: {e}", file=sys.stderr)
        print("probe: it needs the bot's dependencies (the session venv, or requirements.lock)", file=sys.stderr)
        return 2
    code = 0
    for expr in a.expr:
        print(expr)
        try:
            result = eval(expr, ns)  # noqa: S307 -- a developer tool evaluating the caller's own input
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            print("  ->", repr(result))
        except Exception as e:
            print(f"  !! {type(e).__name__}: {e}")
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
