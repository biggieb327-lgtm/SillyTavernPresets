#!/usr/bin/env python3
"""Constraint C1 guard — see host-guard.sh for scope and rationale.

Reads the Stop-hook payload on stdin, pulls the last assistant message out of the
transcript, and checks every fenced code block for host attribution.

Fails OPEN on anything unexpected (no transcript key, unreadable file, odd schema):
a guard that breaks sessions gets disabled, which is worse than no guard.
"""
import json
import re
import sys

# Commands that exist on exactly one host in this fleet.
VPS = re.compile(r'\b(?:systemctl|journalctl)\b|/opt/telegram-bots|\bapt(?:-get)?\s+install\b')
PHONE = re.compile(r'\btmux\b|\bpkg\s+install\b|\btermux[\w-]*\b|\badb\s+shell\b'
                   r'|~/telegram-bot\b|~/[a-z]+-bot\b|/data/data/com\.termux')
PRAGMA = re.compile(r'#\s*host:\s*(vps|phone|both)\b', re.I)
FENCE = re.compile(r'```[a-zA-Z]*\n(.*?)```', re.S)


def last_assistant_text(path: str) -> str:
    """Concatenate the text blocks of the final assistant message in a JSONL transcript."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return ""
    for raw in reversed(lines):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        msg = rec.get("message") or {}
        if rec.get("type") != "assistant" and msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            out = [c.get("text", "") for c in content
                   if isinstance(c, dict) and c.get("type") == "text"]
            if any(out):
                return "\n".join(out)
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    text = last_assistant_text(payload.get("transcript_path") or "")
    if not text:
        return 0

    mentions_vps = re.search(r'\bVPS\b', text) is not None
    mentions_phone = re.search(r'\bphone\b|\bTermux\b', text, re.I) is not None

    problems = []
    for block in FENCE.findall(text):
        pragma_m = PRAGMA.search(block)
        pragma = pragma_m.group(1).lower() if pragma_m else None
        has_vps, has_phone = bool(VPS.search(block)), bool(PHONE.search(block))
        if not (has_vps or has_phone):
            continue                                    # not host-specific; ignore

        first = next((l.strip() for l in block.splitlines() if l.strip()), "")[:60]

        if has_vps and has_phone and pragma != "both":
            problems.append(
                f"  block starting {first!r} mixes VPS-only and phone-only commands. "
                "These cannot run on the same machine — split it, or mark `# host: both` "
                "if it is deliberately showing both.")
            continue
        # A pragma that contradicts the block is worse than none: it asserts the wrong host.
        if pragma == "vps" and has_phone and not has_vps:
            problems.append(f"  block starting {first!r} is marked `# host: vps` but "
                            "contains phone-only commands.")
        elif pragma == "phone" and has_vps and not has_phone:
            problems.append(f"  block starting {first!r} is marked `# host: phone` but "
                            "contains VPS-only commands.")
        elif pragma is None:
            if has_vps and not mentions_vps:
                problems.append(f"  block starting {first!r} runs VPS-only commands, but "
                                "the message never says which host. Name it, or add "
                                "`# host: vps`.")
            elif has_phone and not mentions_phone:
                problems.append(f"  block starting {first!r} runs phone-only commands, but "
                                "the message never says which host. Name it, or add "
                                "`# host: phone`.")

    if problems:
        sys.stderr.write(
            "[host-guard] constraint C1 (.claude/memory/constraints.md, seen: 4) — "
            "a command block is not clearly attributable to one host:\n"
            + "\n".join(problems)
            + "\n Fix the labelling before finishing. Wrong-host execution has cost "
              "four incidents, including a silent no-op mid-cutover.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
