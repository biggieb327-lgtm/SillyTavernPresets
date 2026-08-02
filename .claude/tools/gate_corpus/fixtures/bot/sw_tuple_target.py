from pathlib import Path

CODE_DIR, VERSION = Path(__file__).resolve().parent, "1"


def backup():
    (CODE_DIR / "bot.py.bak").write_bytes(b"x")
