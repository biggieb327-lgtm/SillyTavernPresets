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
CONSTRAINTS = Path(_os.getenv("SWEEP_CONSTRAINTS") or REPO / ".claude" / "memory" / "constraints.md")
TESTS = Path(_os.getenv("SWEEP_TESTS") or REPO / "telegram-companion-bot" / "tests" / "test_pure.py")

# Sites reviewed and justified. Keep the reason — an allowlist without one rots into
# "this was noisy once".
ALLOW_MARKDOWN = {
    "quietwin_cmd": "int index, fixed Mon-Sun names, HH:MM strings — no metachars possible",
    "fleet_cmd": "an int, inside a ``` fence where metachars are literal",
}

ALLOW_SHARED_WRITES = {
    "_maybe_rotate_life_arc": (
        "writes BASE_DIR, the INSTANCE dir. Flagged only because BASE_DIR's *fallback* "
        "(line 97) is __file__'s parent, which applies when no instance dir is passed — "
        "the dev case, one process, no race. Every deployed instance sets it."),
    "_perform_self_update_locked": (
        "genuinely writes the shared code dir, and is correctly serialized: the caller "
        "holds the host-wide update lock, which is what the _locked suffix means."),
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
            fn = _enclosing_def(lines, i)
            if fn in ALLOW_SHARED_WRITES:
                continue
            out.append(f"{BOT.name}:{i} {fn}(): {line.strip()[:76]}")
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
        # A `return` inside a nested helper returns from the HELPER, not the handler, so
        # it cannot leave the user unanswered. dupefacts_cmd's inner `_check` returning []
        # for a short list was reported for months on exactly this confusion.
        nested = [n for n in ast.walk(fn)
                  if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n is not fn]
        inner = {ln for n in nested for ln in range(n.lineno, (n.end_lineno or n.lineno) + 1)}
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            if node.lineno in inner:
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


# ── 5. Install advice that hardcodes a package manager ──────────────────────
def install_hint() -> list[str]:
    """An install hint naming the wrong package manager sends the operator to a
    command that cannot run. `pkg` is Termux-only and does not exist on the Ubuntu
    VPS the fleet has run on since 2026-07-26; bare `pip install` is refused there
    outright (PEP 668, externally-managed-environment) and would miss the venv anyway.

    This class was fixed once per instance and came back: v2026-07-26.6 corrected the
    garminconnect pip hint, and two `pkg install` hints survived untouched — one of
    them in a message sent to Telegram. Route every hint through `_pkg_hint()` /
    `_pip_hint()` in bot.py, which derive the right command from the running host.

    Benign hits to expect: the helper definitions themselves, and comments explaining
    the history. Both are excluded below, so anything reported is a live string."""
    src = BOT.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(src, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue                                   # commentary, not advice
        if "_pkg_hint" in line or "_pip_hint" in line:
            continue                                   # correct callers
        if "sweep-ok" in line:
            continue                                   # reviewed; reason on/above the line
        if re.search(r'["\'][^"\']*\b(?:pkg|apt|apt-get)\s+install\b', line):
            out.append(f"{BOT.name}:{i} hardcoded system-package hint — use _pkg_hint()")
        if re.search(r'["\'][^"\']*(?<!-m )\bpip\s+install\b', line):
            out.append(f"{BOT.name}:{i} hardcoded pip hint — use _pip_hint()")
    return sorted(set(out))


# ── 6. constraints.md is only useful if it escalates ────────────────────────
_STOP = frozenset("""a an and are as at be because been before but by caught check
checked did does for from had has have how in into is it its not of on one only or
que ran run than that the their them then there these they this to two use used using
was were what when which while who with would you your it's don't wasn't""".split())


def _minor_entries(text: str) -> list[tuple[str, str]]:
    """(date, body) for each `- YYYY-MM-DD — …` bullet under the Minor heading."""
    tail = text.split("## Minor", 1)
    if len(tail) < 2:
        return []
    out = []
    for m in re.finditer(r'^- (\d{4}-\d{2}-\d{2}) — (.+?)(?=^- \d{4}-\d{2}-\d{2} —|\Z)',
                         tail[1], re.M | re.S):
        out.append((m.group(1), " ".join(m.group(2).split())))
    return out


def constraints_drift() -> list[str]:
    """A mistakes log that never escalates is a diary. This enforces the file's own
    rules mechanically, so the escalation does not depend on anyone remembering:

      1. A constraint at `seen: 2+` with no `**Graduated` line — by the file's own rule
         prose has failed twice and it owes a hook, eval, or scanner.
      2. A Minor backlog past 8 entries — time for a promotion pass, or the section
         stops being read.
      3. Minor entries sharing distinctive vocabulary — CANDIDATES for a shared cause,
         which is the promotion trigger. This is a word-overlap heuristic and nothing
         more: it cannot tell that two differently-worded entries share a root cause,
         and it will pair unrelated ones that happen to discuss the same file. The
         weekly reviewer decides; this only guarantees the pairs get looked at."""
    if not CONSTRAINTS.exists():
        return [f"{CONSTRAINTS} is missing — the mistakes log is the input to this check"]
    text = CONSTRAINTS.read_text(encoding="utf-8")
    out = []

    for block in re.split(r'^### ', text, flags=re.M)[1:]:
        head = block.splitlines()[0].strip()
        seen_m = re.search(r'\*\*seen:\s*(\d+)', block)
        if not seen_m:
            continue
        if int(seen_m.group(1)) >= 2 and "**Graduated" not in block:
            out.append(f"constraint '{head}' is at seen: {seen_m.group(1)} with no "
                       f"'**Graduated' line — it owes a hook/eval/scanner, not more prose")

    minors = _minor_entries(text)
    if len(minors) > 8:
        out.append(f"Minor log holds {len(minors)} entries (>8) — run a promotion pass; "
                   f"pairs sharing a cause become a numbered constraint")

    toks = []
    for date, body in minors:
        words = {w for w in re.findall(r'[a-z_][a-z0-9_.\-]{3,}', body.lower())
                 if w not in _STOP}
        toks.append((date, body, words))
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            shared = toks[i][2] & toks[j][2]
            if len(shared) >= 3:
                out.append(f"Minor {toks[i][0]} + {toks[j][0]} share "
                           f"{sorted(shared)[:4]} — candidate shared cause, promote if real: "
                           f"'{toks[i][1][:45]}…' / '{toks[j][1][:45]}…'")
    return out


def _handler_coverage() -> tuple[dict, set]:
    """({handler: mention count}, {handlers the tests actually CALL}).

    Shared by the source-assertion scanner and `.claude/hooks/delivery-gate.sh`, which
    blocks a turn that ships a changed `*_cmd` no test drives. One implementation on
    purpose: two copies of "does a test exercise this" would drift, and the drift would
    be invisible in exactly the direction that lets a broken handler through."""
    handlers = {n.name for n in ast.walk(ast.parse(BOT.read_text(encoding="utf-8")))
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
                and n.name.endswith("_cmd")}
    tree = ast.parse(TESTS.read_text(encoding="utf-8"))
    mentioned, called = {}, set()
    for node in ast.walk(tree):
        # bot.<name> anywhere — a mention, wherever it appears
        if isinstance(node, ast.Attribute) and getattr(node.value, "id", "") == "bot":
            if node.attr in handlers:
                mentioned[node.attr] = mentioned.get(node.attr, 0) + 1
        # bot.<name>(...) — an actual call, the only thing that exercises dispatch
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if getattr(node.func.value, "id", "") == "bot" and node.func.attr in handlers:
                called.add(node.func.attr)
    return mentioned, called


def handlers_at_lines(linenos) -> set[str]:
    """Which `*_cmd` handlers own these 1-indexed lines of bot.py.

    Exact line ranges, not git's hunk header: the header names the enclosing function
    only when the change sits below the hunk's leading context, so a change in a
    handler's first few lines is attributed to the PRECEDING function. The first draft
    of the delivery-gate check used the header and silently missed exactly that case."""
    want = set(linenos)
    out = set()
    for n in ast.walk(ast.parse(BOT.read_text(encoding="utf-8"))):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not n.name.endswith("_cmd"):
            continue
        if any(n.lineno <= ln <= (n.end_lineno or n.lineno) for ln in want):
            out.add(n.name)
    return out


def source_assertion() -> list[str]:
    """A test that only READS a handler's source cannot fail for the reason the handler
    exists. `/features <name> on|off` raised ValueError on every invocation for four
    releases while two tests covering it stayed green: one asserted the specs are
    3-tuples, the other grepped the handler text for "_is_admin". Neither called it
    (v2026-08-02.14; C8's fifth member, second to reach the fleet).

    Flagged: a command handler the tests MENTION but never CALL. That is the dangerous
    state — it reads as covered. A handler with no tests at all is honestly untested and
    is not reported here. A mention inside inspect.getsource(...) counts as a mention,
    never as a call; driving the handler with fake Telegram objects is what counts."""
    if not TESTS.exists():
        return [f"{TESTS} is missing — the test suite is the input to this check"]
    mentioned, called = _handler_coverage()
    return [f"{TESTS.name}: {name}() is referenced {n}× but never called — the tests read "
            f"it, nothing runs it"
            for name, n in sorted(mentioned.items()) if name not in called]


SCANNERS = {
    "markdown-interp": markdown_interp,
    "shared-writes": shared_writes,
    "silent-return": silent_return,
    "source-assertion": source_assertion,
    "env-drift": env_drift,
    "install-hint": install_hint,
    "constraints-drift": constraints_drift,
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
