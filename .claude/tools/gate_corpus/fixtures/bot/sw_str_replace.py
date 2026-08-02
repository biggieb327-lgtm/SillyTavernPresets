from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent


def label():
    return CODE_DIR.name.replace("-", "_")
