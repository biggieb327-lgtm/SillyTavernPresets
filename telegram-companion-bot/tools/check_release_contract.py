#!/usr/bin/env python3
"""Fail if CI and VPS release mechanics drift away from the immutable contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT_DIR = ROOT / "telegram-companion-bot"


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _shell_function(script: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n(.*?)^\}}$", script)
    return match.group(1) if match else ""


def main() -> int:
    problems: list[str] = []
    source = (BOT_DIR / "requirements.txt").read_text(encoding="utf-8")
    lock = (BOT_DIR / "requirements.lock").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/evals.yml").read_text(encoding="utf-8")
    release_lib = (BOT_DIR / "deploy/release-lib.sh").read_text(encoding="utf-8")
    vps_sync = (BOT_DIR / "deploy/vps-sync.sh").read_text(encoding="utf-8")
    installer = (BOT_DIR / "deploy/install-vps.sh").read_text(encoding="utf-8")
    service = (BOT_DIR / "deploy/bot@.service").read_text(encoding="utf-8")

    direct_names = {
        _normalized(re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip())
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    lock_names: set[str] = set()
    blocks = re.split(r"(?m)(?=^[A-Za-z0-9_.-]+==)", lock)
    package_blocks = [block for block in blocks if re.match(r"^[A-Za-z0-9_.-]+==", block)]
    for block in package_blocks:
        first = block.splitlines()[0]
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==[^ ]+ \\", first)
        if not match:
            problems.append(f"lock entry is not exact: {first}")
            continue
        lock_names.add(_normalized(match.group(1)))
        if "--hash=sha256:" not in block:
            problems.append(f"lock entry has no SHA-256 hash: {match.group(1)}")
    if not package_blocks:
        problems.append("requirements.lock contains no package entries")
    missing = sorted(direct_names - lock_names)
    if missing:
        problems.append(f"direct requirements absent from lock: {', '.join(missing)}")
    expected_header = (
        "uv pip compile telegram-companion-bot/requirements.txt --python-version 3.12 "
        "--generate-hashes --output-file telegram-companion-bot/requirements.lock"
    )
    if expected_header not in lock:
        problems.append("lock header does not carry the canonical regeneration command")

    workflow_required = (
        "uv pip compile telegram-companion-bot/requirements.txt",
        "git diff --exit-code -- telegram-companion-bot/requirements.lock",
        "python -m pip install --require-hashes --only-binary=:all:",
        "-r telegram-companion-bot/requirements.lock",
        "python -m pip check",
    )
    for fragment in workflow_required:
        if fragment not in workflow:
            problems.append(f"CI release contract missing: {fragment}")

    function_contracts = {
        "release_secure_stores": (
            "must be root-owned mode 755",
            'install -d -o root -g root -m 0755 "$base/$store"',
        ),
        "release_migrate_writable_state": (
            'install -d -o "$bot_user" -g "$bot_group" -m 0755 "$base/shared"',
            'chown root:root "$base"',
            'release_secure_stores "$base"',
        ),
        "release_prepare_venv": (
            'sha256sum "$source_dir/requirements.lock"',
            'venv_key="py${python_version}-${lock_hash}"',
            "pip install --require-hashes --only-binary=:all:",
            '"$temp_dir/bin/python" -m pip check',
            'chmod -R a-w "$temp_dir"',
        ),
        "release_prepare": (
            'release_secure_stores "$base"',
            'release_dir="$base/releases/$revision"',
            'ln -s "../../shared/update.lock" "$temp_dir/.update.lock"',
            'mv "$temp_dir" "$release_dir"',
            'chmod -R a-w "$temp_dir"',
        ),
        "release_activate": (
            'mv -Tf "$link_tmp" "$base/previous"',
            'mv -Tf "$link_tmp" "$base/current"',
        ),
        "release_rollback": (
            'mv -Tf "$link_tmp" "$base/current"',
            'mv -Tf "$link_tmp" "$base/previous"',
        ),
    }
    for function_name, fragments in function_contracts.items():
        body = _shell_function(release_lib, function_name)
        if not body:
            problems.append(f"release library function missing: {function_name}")
            continue
        for fragment in fragments:
            if fragment not in body:
                problems.append(f"{function_name} contract missing: {fragment}")

    if "REVISION=$($GIT rev-parse HEAD)" not in vps_sync:
        problems.append("vps-sync does not address releases by the full deployed git SHA")
    for script_name, script in (("vps-sync", vps_sync), ("install-vps", installer)):
        if 'release_prepare "$SRC"' not in script or "release_activate" not in script:
            problems.append(f"{script_name} bypasses the shared release prepare/activate path")
        if "release_migrate_writable_state" not in script:
            problems.append(f"{script_name} does not isolate writable state from release pointers")
    if 'MODE=rollback' not in vps_sync or 'release_rollback "$BASE"' not in vps_sync:
        problems.append("vps-sync has no immutable-pointer rollback mode")

    service_required = (
        "Environment=WORLD_FILE=/opt/telegram-bots/world.txt",
        "Environment=GROUP_LEDGER_DIR=/opt/telegram-bots/shared",
        "ExecStart=/opt/telegram-bots/current/venv/bin/python "
        "/opt/telegram-bots/current/bot.py /opt/telegram-bots/%i",
        "Restart=always",
    )
    for fragment in service_required:
        if fragment not in service:
            problems.append(f"systemd release contract missing: {fragment}")

    if problems:
        print("release contract is broken:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(
        f"release contract ok: {len(package_blocks)} exact hashed packages; "
        "CI and VPS share the lock; git-SHA releases and rollback are wired"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
