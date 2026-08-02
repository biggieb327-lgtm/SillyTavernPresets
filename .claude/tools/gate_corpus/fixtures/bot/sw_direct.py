from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent


def backup():
    (CODE_DIR / "bot.py.bak").write_bytes(b"x")
