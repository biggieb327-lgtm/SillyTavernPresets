#!/usr/bin/env python3
"""sweep.py — find every OTHER instance of a bug class you just fixed.

Born 2026-07-25, when four separate "one-line fixes" each turned out to be a class:

  /audit sent arbitrary text through Markdown   -> 13 more sites across 11 commands
  perform_self_update raced on the shared dir   -> vps-sync.sh has the same race
  "no graceful-stop line = SIGKILL" was wrong   -> asserted in 4 more places
  BOT_TIMEZONE didn't set the timezone          -> whole-file env/doc drift

Every one was found by a throwaway scanner written in the moment and then lost. These
are those scanners, kept.

Usage:
    python3 .claude/tools/sweep.py                 # run every scanner
    python3 .claude/tools/sweep.py markdown-interp # run one
    python3 .claude/tools/sweep.py --list

Exit code 1 if any scanner reports findings, so it can gate a "done" claim.

Findings are CANDIDATES, not defects. Each scanner prints why a hit might be benign.
Judgement stays with the reader — the scanner's job is to make sure the reader sees
every site, not to decide.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Overridable so the scanners can be break-tested against a deliberately broken copy.
# A checker nobody has proved RED is not a checker — the first version of the
# audit-plain-text eval (2026-07-25) used an awk range that collapsed to one line and
# could never fail. It passed for exactly as long as it was useless.
import os as _os
BOT = Path(_os.getenv("SWEEP_BOT") or REPO / "telegram-companion-bot" / "bot.py")
ENV = Path(_os.getenv("SWEEP_ENV") or REPO / "telegram-companion-bot" / ".env.example")

# Sites reviewed and justified. Keep the reason — an allowlist without one rots into
# "this was noisy once".
ALLOW_MARKDOWN = {
    "quietwin_cmd": "int index, fixed Mon-Sun names, HH:MM strings — no metachars possible",
    "fleet_cmd": "an int, inside a ``` fence where metachars are literal",
}


def _src_lines() -> list[str]:
    return BOT.read_text(encoding="utf-8").splitlines()


def _enclosing_def(lines: list[str], lineno: int) -> str:
    for j in range(lineno - 1, 0, -1):
        if lines[j - 1].startswith(("async def ", "def ")):
            return lines[j - 1].split("(")[0].split()[-1]
    return "?"


# ── 1. Arbitrary content rendered through Telegram Markdown ───────────────────
def markdown_interp() -> list[str]:
    """Telegram rejects the WHOLE message on a stray '_' or unmatched '[', and the
    command then replies with silence — indistinguishable from a dead bot. Backticks
    are NOT a safe wrapper when the value is user input: a backtick in the data closes
    the span early."""
    lines, out = _src_lines(), []
    for i, line in enumerate(lines, 1):
        if 'parse_mode="Markdown"' not in line or line.strip().startswith("#"):
            continue
        stmt = " ".join(x.strip() for x in lines[max(0, i - 7):i]
                        if not x.strip().startswith("#"))
        risky = [m.group(1) for m in re.finditer(r'\{([a-zA-Z_][\w\[\]\'\".]*)\}', stmt)
                 if not (stmt[max(0, m.start() - 1):m.start()] == "`"
                         and stmt[m.end():m.end() + 1] == "`")]
        if not risky:
            continue
        fn = _enclosing_def(lines, i)
        if fn in ALLOW_MARKDOWN:
            continue
        out.append(f"{BOT.name}:{i} {fn}() interpolates {sorted(set(risky))}")
    return out


# ── 2. Writes to the code dir, which every instance on a host shares ──────────
def shared_writes() -> list[str]:
    """Instance dirs are per-bot; the CODE dir is shared (~/telegram-bot for the four
    phone bots, /opt/telegram-bots for cass+jules). An unsynchronised write there races
    between instances. The loud failure is a crash; the silent one corrupts a rollback
    point and reports success."""
    lines, out = _src_lines(), []
    shared = set()
    for i, line in enumerate(lines, 1):
        m = re.match(r'\s*([A-Za-z_][\w]*)\s*=.*__file__', line)
        if m:
            shared.add(m.group(1))
    shared |= {"code_dir"}
    writes = ("write_text", "write_bytes", "replace(", "unlink(", "rename(", "mkdir(")
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("#"):
            continue
        if not any(w in line for w in writes):
            continue
        if any(re.search(rf'\b{re.escape(n)}\b', line) for n in shared):
            out.append(f"{BOT.name}:{i} {_enclosing_def(lines, i)}(): {line.strip()[:76]}")
    return out


# ── 3. Command handlers that can return without replying ─────────────────────
def silent_return() -> list[str]:
    """A handler that returns without replying looks exactly like a dead bot. Access
    guards (_is_allowed/_is_admin) return silently ON PURPOSE and are excluded."""
    src = BOT.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    GUARD = ("_is_allowed", "_is_admin", "_guard", "effective_user", "ALLOWED_USERS")
    REPLY = ("reply", "send_message", "answer", "send_photo", "send_voice",
             "send_document", "send_chat_action")
    out = []

    def replies(nodes) -> bool:
        mod = ast.Module(body=list(nodes), type_ignores=[])
        for n in ast.walk(mod):
            if isinstance(n, ast.Call):
                name = getattr(n.func, "attr", None) or getattr(n.func, "id", "")
                if any(r in name for r in REPLY):
                    return True
        return False

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not fn.name.endswith("_cmd"):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            test = " ".join(lines[node.test.lineno - 1:node.test.end_lineno])
            if any(g in test for g in GUARD):
                continue
            has_ret = any(isinstance(s, ast.Return)
                          for s in ast.walk(ast.Module(body=node.body, type_ignores=[])))
            if has_ret and not replies(node.body):
                out.append(f"{BOT.name}:{node.lineno} {fn.name}(): if {test.strip()[:60]}")
        # if/elif dispatch chains with no else fall through to silence
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            branches, cur, has_else = [node], node, False
            while cur.orelse:
                if len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
                    cur = cur.orelse[0]
                    branches.append(cur)
                else:
                    has_else = True
                    break
            if len(branches) >= 2 and not has_else and all(replies(b.body) for b in branches):
                out.append(f"{BOT.name}:{node.lineno} {fn.name}(): "
                           f"{len(branches)}-branch dispatch with no else")
    return sorted(set(out))


# ── 4. .env.example vs what bot.py actually reads ────────────────────────────
def env_drift() -> list[str]:
    """Drift in BOTH directions is dangerous. Documented-but-unread is worse than
    undocumented: setting NUDGE_MAX looked like it capped proactive messages and did
    nothing at all.

    NOTE the limit of this check: it asks "is the name referenced?", NOT "does it do
    what the docs claim". BOT_TIMEZONE passed this check for months while the clock
    came from TIMEZONE. For any setting the docs describe by BEHAVIOUR, trace the value
    to its use by hand."""
    bot_src, env_src = BOT.read_text(encoding="utf-8"), ENV.read_text(encoding="utf-8")
    used = set(re.findall(r'os\.getenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    used |= set(re.findall(r'_env_(?:int|float)\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    documented = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]{2,})=', env_src, re.M))
    mentioned = set(re.findall(r'\b([A-Z][A-Z0-9_]{2,})\b', env_src))
    out = []
    for v in sorted(documented - used):
        out.append(f".env.example documents {v} — nothing in bot.py reads it (silent no-op)")
    for v in sorted(used - mentioned):
        out.append(f"bot.py reads {v} — absent from .env.example entirely")
    return out


SCANNERS = {
    "markdown-interp": markdown_interp,
    "shared-writes": shared_writes,
    "silent-return": silent_return,
    "env-drift": env_drift,
}


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for name, fn in SCANNERS.items():
            print(f"{name:<18} {(fn.__doc__ or '').strip().splitlines()[0]}")
        return 0
    picked = [a for a in argv[1:] if not a.startswith("-")] or list(SCANNERS)
    unknown = [p for p in picked if p not in SCANNERS]
    if unknown:
        print(f"unknown scanner(s): {unknown}\navailable: {list(SCANNERS)}", file=sys.stderr)
        return 2
    total = 0
    for name in picked:
        findings = SCANNERS[name]()
        total += len(findings)
        print(f"\n=== {name} — {len(findings)} candidate(s) ===")
        if not findings:
            print("  none")
            continue
        print("  " + (SCANNERS[name].__doc__ or "").strip().replace("\n    ", "\n  "))
        print()
        for f in findings:
            print(f"  {f}")
    print(f"\nsweep: {total} candidate(s) across {len(picked)} scanner(s)."
          f"{' Review each — a candidate is not a defect.' if total else ''}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
