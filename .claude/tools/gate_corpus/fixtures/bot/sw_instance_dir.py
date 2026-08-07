import os
import sys
from pathlib import Path

BASE_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()


def save():
    (BASE_DIR / "state.json").write_text("{}", encoding="utf-8")
