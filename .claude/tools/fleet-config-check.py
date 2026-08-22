#!/usr/bin/env python3
"""fleet-config-check.py — configuration consistency/drift checker for the fleet.

Checks all 7 instance directories under telegram-companion-bot/ for:
  1. context-file presence (majority rule)
  2. character card schema consistency (chara_card_v2 top-level + data keys)
  3. empty/whitespace-only context files
  4. presence of the per-instance preset layer (preset-<name>.txt)

Stdlib only. Exit 0 if no issues, 1 otherwise.
"""
import json
import sys
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parents[2] / "telegram-companion-bot"

# instance name -> (directory name, card filename)
INSTANCES = {
    "nora": ("nora", "nora.json"),
    "bonnie": ("bonnie", "bonnie.json"),
    "cass": ("cass", "cass.json"),
    "emily": ("emily", "emily_harper.json"),
    "priya": ("priya", "priya.json"),
    "jules": ("jules", "jules_nakagawa.json"),
    "marcus": ("marcus", "marcus_calder.json"),
}

CONTEXT_FILES = [
    "appearance.txt",
    "atlas.txt",
    "people.txt",
    "projects.txt",
    "schedule.txt",
    "setting.txt",
    "life.txt",
]

MAJORITY_THRESHOLD = 4  # "4+ others have it"

issues = []


def check_file_presence():
    presence = {name: set() for name in INSTANCES}
    for name, (dirname, _) in INSTANCES.items():
        idir = BASE / dirname
        for fname in CONTEXT_FILES:
            if (idir / fname).is_file():
                presence[name].add(fname)

    for fname in CONTEXT_FILES:
        have = [n for n in INSTANCES if fname in presence[n]]
        missing = [n for n in INSTANCES if fname not in presence[n]]
        if len(have) >= MAJORITY_THRESHOLD and missing:
            for n in missing:
                issues.append(
                    f"file-presence: {n} is missing {fname} "
                    f"(present in {len(have)}/{len(INSTANCES)} other instances)"
                )


def check_card_schema():
    top_keys = {}
    data_keys = {}
    for name, (dirname, cardfile) in INSTANCES.items():
        path = BASE / cardfile
        if not path.is_file():
            issues.append(f"card-schema: {name} card not found at {path}")
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            issues.append(f"card-schema: {name} card {cardfile} failed to parse: {e}")
            continue
        top_keys[name] = set(card.keys())
        data_keys[name] = set(card.get("data", {}).keys()) if isinstance(card.get("data"), dict) else set()

    _flag_key_drift("card-top-level", top_keys)
    _flag_key_drift("card-data", data_keys)


def _flag_key_drift(label, keysets):
    if not keysets:
        return
    n = len(keysets)
    counts = Counter(k for keys in keysets.values() for k in keys)
    majority_keys = {k for k, c in counts.items() if c >= MAJORITY_THRESHOLD}
    for name, keys in keysets.items():
        missing = majority_keys - keys
        for k in sorted(missing):
            issues.append(
                f"{label}: {name} is missing key '{k}' "
                f"(present in {counts[k]}/{n} instances)"
            )
        extra = keys - majority_keys
        for k in sorted(extra):
            # only flag as "extra" if it's genuinely a minority key, not universal
            if counts[k] < n:
                issues.append(
                    f"{label}: {name} has extra key '{k}' "
                    f"not present in the majority ({counts[k]}/{n} instances)"
                )


def check_empty_files():
    for name, (dirname, _) in INSTANCES.items():
        idir = BASE / dirname
        for fname in CONTEXT_FILES:
            path = idir / fname
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                issues.append(f"empty-file: {name}/{fname} could not be read: {e}")
                continue
            if content.strip() == "":
                issues.append(f"empty-file: {name}/{fname} is empty or whitespace-only")


def check_preset_layers():
    for name in INSTANCES:
        preset_path = BASE / f"preset-{name}.txt"
        if not preset_path.is_file():
            issues.append(f"preset-layer: preset-{name}.txt is missing")


def main():
    check_file_presence()
    check_card_schema()
    check_empty_files()
    check_preset_layers()

    for issue in issues:
        print(issue)

    print(f"fleet-config-check: {len(INSTANCES)} instances checked, {len(issues)} issues found")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
