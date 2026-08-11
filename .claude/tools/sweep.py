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
import math as _math
import re
import sys
from datetime import date as _date
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
# Overridable for the same reason as the paths above: the archive rule is time-dependent,
# and a rule that cannot be run against a chosen date cannot be proved to fire at all.
_TODAY = _os.getenv("SWEEP_TODAY") or _date.today().isoformat()

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


def _owner_at(tree: ast.AST, lineno: int) -> str:
    """Innermost function owning this line, by AST range.

    `_enclosing_def` scans backwards for a `def` at column 0, so a hit inside a nested
    helper is credited to the top-level function containing it, and the allowlists —
    which are keyed by function name — then miss or over-match. Structure decides this,
    not indentation."""
    best, best_span = "?", None
    for n in ast.walk(tree):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        end = n.end_lineno or n.lineno
        if n.lineno <= lineno <= end and (best_span is None or end - n.lineno < best_span):
            best, best_span = n.name, end - n.lineno
    return best


def _scope_assigns(tree: ast.AST, src: str) -> list[tuple[int, int, dict]]:
    """[(start, end, {name: value_node})] per function scope, innermost-first.

    Needed because an f-string is often built into a local and passed by name one line
    later; a scanner that only inspects the call's own arguments sees a bare Name.

    Built from ONE walk. Walking each function separately is O(functions x nodes), which
    on bot.py's ~400 functions took ten seconds of the sweep's runtime for a result only
    a handful of call sites ever consult."""
    funcs, assigns = [], []
    for n in ast.walk(tree):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            funcs.append((n.lineno, n.end_lineno or n.lineno))
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            assigns.append((n.lineno, n.targets[0].id, n.value))
    scopes = []
    for start, end in funcs:
        scopes.append((start, end, {name: val for ln, name, val in assigns
                                    if start <= ln <= end}))
    scopes.sort(key=lambda s: s[1] - s[0])
    return scopes


# ── 1. Arbitrary content rendered through Telegram Markdown ───────────────────
def markdown_interp() -> list[str]:
    """Telegram rejects the WHOLE message on a stray '_' or unmatched '[', and the
    command then replies with silence — indistinguishable from a dead bot. Backticks
    are NOT a safe wrapper when the value is user input: a backtick in the data closes
    the span early.

    Structural, not line-based. Three things escaped the old text scan, each proven by
    a fixture: `parse_mode='Markdown'` in single quotes; an f-string built more than
    seven lines above the call; and any placeholder carrying a format spec or
    conversion, since `{n:>3}` did not match the placeholder regex."""
    src = BOT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = []
    scopes = None       # built lazily: only if a parse_mode call is actually found

    def placeholders(node, assigns) -> list[tuple[str, bool]]:
        """(expression source, wrapped in backticks) for every f-string placeholder
        reachable from this argument, following one level of local assignment."""
        if isinstance(node, ast.Name) and node.id in assigns:
            node = assigns[node.id]
        found = []
        for js in ast.walk(node):
            if not isinstance(js, ast.JoinedStr):
                continue
            for i, v in enumerate(js.values):
                if not isinstance(v, ast.FormattedValue):
                    continue
                prev = js.values[i - 1] if i else None
                nxt = js.values[i + 1] if i + 1 < len(js.values) else None
                wrapped = (isinstance(prev, ast.Constant)
                           and str(prev.value).endswith("`")
                           and isinstance(nxt, ast.Constant)
                           and str(nxt.value).startswith("`"))
                found.append((ast.get_source_segment(src, v.value) or "?", wrapped))
        return found

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        pm = next((k for k in call.keywords if k.arg == "parse_mode"), None)
        if pm is None:
            continue
        if "markdown" not in (ast.get_source_segment(src, pm.value) or "").lower():
            continue
        if scopes is None:
            scopes = _scope_assigns(tree, src)
        assigns = next((a for s, e, a in scopes if s <= call.lineno <= e), {})
        args = list(call.args) + [k.value for k in call.keywords if k.arg != "parse_mode"]
        risky = sorted({expr for a in args for expr, wrapped in placeholders(a, assigns)
                        if not wrapped})
        if not risky:
            continue
        fn = _owner_at(tree, call.lineno)
        if fn in ALLOW_MARKDOWN:
            continue
        out.append(f"{BOT.name}:{call.lineno} {fn}() interpolates {risky}")
    return sorted(set(out))


# ── 2. Writes to the code dir, which every instance on a host shares ──────────
def shared_writes() -> list[str]:
    """Instance dirs are per-bot; the CODE dir is shared (~/telegram-bot for the four
    phone bots, /opt/telegram-bots for cass+jules). An unsynchronised write there races
    between instances. The loud failure is a crash; the silent one corrupts a rollback
    point and reports success.

    Structural, for two reasons a fixture proved: a `__file__` assignment split over
    lines defined a shared name the line scan never saw, and `str.replace(old, new)`
    was read as `Path.replace(target)` — arity tells them apart, one argument vs two."""
    src = BOT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    shared = {"code_dir"}
    for n in ast.walk(tree):
        # Node-level check, NOT ast.get_source_segment: that re-splits the whole source
        # on every call, which is O(n²) over bot.py's ~14k lines and hung the sweep.
        if isinstance(n, ast.AnnAssign):          # CODE_DIR: Path = Path(__file__).parent
            targets, value = ([n.target] if n.target else []), n.value
        elif isinstance(n, ast.Assign):
            targets, value = n.targets, n.value
        else:
            continue
        if value is None:
            continue

        def has_file(node) -> bool:
            return any(isinstance(d, ast.Name) and d.id == "__file__" for d in ast.walk(node))

        for t in targets:
            # Tuple targets are paired with tuple values so only the element actually
            # derived from __file__ counts. `CODE_DIR, VERSION = Path(__file__).parent, "1"`
            # defined a shared name the scanner never saw (corpus mutation `sw-tuple-target`).
            if isinstance(t, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) \
                    and len(t.elts) == len(value.elts):
                for tgt, val in zip(t.elts, value.elts):
                    if isinstance(tgt, ast.Name) and has_file(val):
                        shared.add(tgt.id)
            elif has_file(value):
                for d in ast.walk(t):
                    if isinstance(d, ast.Name):
                        shared.add(d.id)
    WRITES = {"write_text", "write_bytes", "unlink", "rename", "mkdir", "touch", "replace"}
    out = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr not in WRITES:
            continue
        if call.func.attr == "replace" and len(call.args) != 1:
            continue                       # str.replace(old, new) is not a filesystem op
        # Structural membership, not a regex over the receiver's SOURCE: rendering the
        # source of every `.replace(` in bot.py (hundreds, nearly all str.replace) cost
        # six of the sweep's ten seconds, because get_source_segment re-splits the file.
        recv_names = {d.id for d in ast.walk(call.func.value) if isinstance(d, ast.Name)}
        if not recv_names & shared:
            continue
        fn = _owner_at(tree, call.lineno)
        if fn in ALLOW_SHARED_WRITES:
            continue
        stmt = " ".join((ast.get_source_segment(src, call) or "").split())
        out.append(f"{BOT.name}:{call.lineno} {fn}(): {stmt[:76]}")
    return sorted(set(out))


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
    # Every way bot.py reads the environment. os.environ.get / os.environ[...] were
    # invisible, so a setting read that way looked undocumented-and-unread from both
    # sides at once (gate_corpus `env-environ-get`).
    used = set(re.findall(r'os\.getenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    used |= set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    used |= set(re.findall(r'os\.environ\[\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    used |= set(re.findall(r'_env_(?:int|float|bool)\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot_src))
    # {1,} not {2,}: at 3+ chars a two-letter name like TZ counted as USED but never as
    # DOCUMENTED, so a correctly documented setting was reported as missing (`env-two-char-name`).
    documented = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=', env_src, re.M))
    mentioned = set(re.findall(r'\b([A-Z][A-Z0-9_]+)\b', env_src))
    out = []
    for v in sorted(documented - used):
        out.append(f".env.example documents {v} — nothing in bot.py reads it (silent no-op)")
    for v in sorted(used - mentioned):
        out.append(f"bot.py reads {v} — absent from .env.example entirely")
    return out


# ── 5. Install advice that hardcodes a package manager ──────────────────────
def async_blocking() -> list[str]:
    """A synchronous network call inside an `async def` blocks the whole event loop.

    bot-code-invariants #8 — "never call bare requests in an async handler, wrap in
    asyncio.to_thread" — had no mechanism until 2026-08-11: prose and review only. It was
    written after real incidents and every current call site obeys it, which is exactly
    when a rule quietly stops being checked.

    While the loop is blocked, PTB's httpx connection to Telegram sits unread and the
    symptom is `NetworkError: httpx.ReadError` — an error that looks like bad connectivity
    and is actually local. From `/errors` it is indistinguishable from weather.

    **Resolves one level of indirection, and this is the whole difficulty.** The first
    draft of this scanner matched only low-level names (`requests`, `_get_session`, the
    Garmin client) and returned a confident 0 — but bot.py never calls those from an
    `async def`; it calls sync WRAPPERS like `_fetch_wsdot_times()` that do the I/O
    internally. Break-testing caught it: injecting a real violation
    (`times = _fetch_wsdot_times()` in place of the `to_thread` call) left the scanner
    still reporting 0. It now computes, to a fixpoint, the set of module-level sync
    functions that reach a blocking primitive, and flags calls to those too.

    Benign hits to expect: a sync helper that only *builds* a client without performing
    I/O, and anything inside `run_in_executor` — not recognised here, since this repo
    standardised on `to_thread`; add it to the safe set if that ever changes."""
    src = BOT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    PRIMITIVES = {"requests", "urlopen", "urlretrieve", "httpx",
                  "_get_session", "_garmin_client", "_Garmin"}

    def call_roots(node):
        """Every name a call in `node` is rooted at."""
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                root = n.func
                while isinstance(root, ast.Attribute):
                    root = root.value
                yield (getattr(root, "id", None) or getattr(n.func, "attr", None)), n

    sync_fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    blocking = set(PRIMITIVES)
    while True:                       # fixpoint: wrappers of wrappers count too
        grew = False
        for name, node in sync_fns.items():
            if name in blocking:
                continue
            if any(r in blocking for r, _ in call_roots(node)):
                blocking.add(name); grew = True
        if not grew:
            break

    # Allowlist: a call the AST cannot clear, because the mitigation is a RUNTIME check.
    # Each entry carries the guard that makes it safe, and the guard is re-verified below —
    # an allowlist that outlives its reason hides the next real violation behind a name
    # nobody re-checks.
    ALLOW = {
        "assemble_messages": (
            "triggered_memories", "get_running_loop",
            "reaches _embed_text only via the query_vec=None fallback, and that branch "
            "calls asyncio.get_running_loop() and skips the embed when it is on the loop "
            "(bot.py ~4361). The reply path pre-embeds off-loop and passes query_vec in."),
    }
    out = []
    for name, (guard_fn, guard_call, why) in ALLOW.items():
        node = sync_fns.get(guard_fn)
        if node is None or guard_call not in ast.unparse(node):
            out.append(f"ALLOWLIST STALE: {name} is exempted because {guard_fn}() calls "
                       f"{guard_call}(), and that guard is now GONE — the exemption is "
                       f"hiding a real violation. Reason on file: {why}")
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        safe = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                nm = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                if nm in ("to_thread", "run_in_executor"):
                    for arg in n.args:
                        for sub in ast.walk(arg):
                            safe.add(id(sub))
        for root, node in call_roots(fn):
            if root in blocking and id(node) not in safe and root not in ALLOW:
                out.append(f"bot.py:{node.lineno} {fn.name}() calls "
                           f"{ast.unparse(node)[:52]} on the event loop — "
                           f"wrap it in asyncio.to_thread")
    return sorted(set(out))


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
    the history.

    Reads string VALUES, not source lines. Adjacent literals are concatenated by the
    parser, so a hint split across two lines is one value here and was invisible to the
    line scan. It also fixes a false positive the old docstring claimed was handled:
    the bodies of `_pkg_hint`/`_pip_hint` necessarily contain the very strings they
    exist to centralise, and were only skipped when the helper's NAME appeared on the
    same line — which it does not, one line into its own definition."""
    src = BOT.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    helper, docstrings = [], set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and \
                n.name in ("_pkg_hint", "_pip_hint"):
            helper.append((n.lineno, n.end_lineno or n.lineno))
        body = getattr(n, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))          # documentation, not advice
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Constant) or not isinstance(n.value, str):
            continue
        if id(n) in docstrings or any(a <= n.lineno <= b for a, b in helper):
            continue
        line = lines[n.lineno - 1] if n.lineno <= len(lines) else ""
        if "sweep-ok" in line or "_pkg_hint" in line or "_pip_hint" in line:
            continue
        if re.search(r'\b(?:pkg|apt|apt-get)\s+install\b', n.value):
            out.append(f"{BOT.name}:{n.lineno} hardcoded system-package hint — use _pkg_hint()")
        if re.search(r'(?<!-m )\bpip\s+install\b', n.value):
            out.append(f"{BOT.name}:{n.lineno} hardcoded pip hint — use _pip_hint()")
    return sorted(set(out))


# ── 6. constraints.md is only useful if it escalates ────────────────────────
_STOP = frozenset("""a an and are as at be because been before but by caught check
checked did does for from had has have how in into is it its not of on one only or
que ran run than that the their them then there these they this to two use used using
was were what when which while who with would you your it's don't wasn't""".split())


ARCHIVE_HEADING = "## Minor — archived"
ARCHIVE_AFTER_DAYS = 30
PAIR_LIMIT = 5      # a ranking nobody reads is just a list; show the strongest few
PAIR_MAX_DF = 2     # a token in exactly 2 entries IS those entries' shared vocabulary
PAIR_MIN_RARE = 2   # one rare word in common is a coincidence; two is a candidate


def _minor_entries(text: str) -> list[tuple[str, str]]:
    """(date, body) for each `- YYYY-MM-DD — …` bullet in the ACTIVE Minor section.

    Archived entries are excluded deliberately: a Minor entry earns its place by being
    available to pair with a FUTURE one, and after ARCHIVE_AFTER_DAYS nothing has. Its
    remaining value is archaeological, which the archive preserves — so counting it
    against the promotion threshold only guarantees the threshold fires forever."""
    return [(d, b) for d, b, _ in _minor_section(text)[0]]


_BULLET = r'^[-*+] (\d{4}-\d{2}-\d{2}) [—–-] '


def _minor_section(text: str) -> tuple[list[tuple[str, str, int]], str]:
    """([(date, body, offset)], active-section-text) for the ACTIVE Minor log.

    BOTH splits are line-anchored. The archive split had to be (the archiving rule in
    the header names that heading mid-sentence, and an unanchored split truncated the
    active log to zero entries while reporting a confident all-clear — C14 in a parser).
    The `## Minor` split has the mirror-image failure: prose naming the heading mid-
    sentence made every dated bullet BELOW it — including occurrence lists inside
    constraint bodies — parse as Minor entries. gate_corpus `cd-phantom-section`.

    Bullets accept `-`, `*`, `+` and any dash separator: a `*`-bulleted entry silently
    not counting is indistinguishable from a healthy log (gate_corpus `cd-star-bullets`)."""
    parts = re.split(r'^## Minor\b', text, maxsplit=1, flags=re.M)
    if len(parts) < 2:
        return [], ""
    active = re.split(rf'^{re.escape(ARCHIVE_HEADING)}', parts[1], maxsplit=1, flags=re.M)[0]
    out = []
    for m in re.finditer(_BULLET + r'(.+?)(?=' + _BULLET + r'|\Z)', active, re.M | re.S):
        out.append((m.group(1), " ".join(m.group(2).split()), m.start()))
    return out, active


def _last_promotion(text: str) -> str:
    """The date of the last promotion pass, from the Minor header. The backlog check
    counts what has arrived SINCE it — that is what "is another pass worth running"
    actually asks. Counting the total instead fires forever once the log is healthy:
    on 2026-08-02 a pass promoted six entries into C17/C18 and left 19 with no shared
    causes, and a total-based check would have demanded a seventh pass that could only
    invent clusters.

    Scoped to the Minor section, not the whole file: `re.search` takes the FIRST match,
    so a constraint body quoting an old date ("the header used to read **Last promotion
    pass: 2020-01-01**") hijacked it and manufactured a backlog of every entry in the
    log. gate_corpus `cd-last-pass-in-prose`."""
    _, active = _minor_section(text)
    m = re.search(r'\*\*Last promotion pass:\s*(\d{4}-\d{2}-\d{2})', active or "")
    return m.group(1) if m else ""


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
    last = _last_promotion(text)
    pass_due = False  # defined before the branch: a missing header line must not NameError
    if not last:
        out.append("the Minor header has no '**Last promotion pass: YYYY-MM-DD**' line — "
                   "the backlog check counts entries added since it and cannot run without it")
    else:
        since = [d for d, _ in minors if d > last]
        pass_due = len(since) > 8
        if pass_due:
            out.append(f"{len(since)} Minor entries added since the last promotion pass "
                       f"({last}) — run one; pairs sharing a cause become a numbered "
                       f"constraint")
        stale = [d for d, _ in minors
                 if (_date.fromisoformat(_TODAY) - _date.fromisoformat(d)).days
                 > ARCHIVE_AFTER_DAYS]
        if stale:
            out.append(f"{len(stale)} active Minor entries are older than "
                       f"{ARCHIVE_AFTER_DAYS} days (oldest {min(stale)}) — move them under "
                       f"'{ARCHIVE_HEADING}'; nothing has paired with them, so they are "
                       f"archaeology now, not candidates")

    # Pairs are the INPUT to a promotion pass, so they are listed only when one is due.
    # Otherwise they restate, every run, the candidates the last pass already looked at
    # and rejected — which is how the previous version stayed permanently noisy even
    # right after a clean pass.
    if not pass_due:
        return out

    # Ranked by how DISTINCTIVE the shared vocabulary is. Raw overlap made this unusable:
    # 19 entries produced 62 pairs, more pairs than entries, every one needing human
    # judgement — so nobody read any.
    toks = []
    for date, body in minors:
        words = {w for w in re.findall(r'[a-z_][a-z0-9_.\-]{3,}', body.lower())
                 if w not in _STOP}
        toks.append((date, body, words))
    df: dict = {}
    for _, _, words in toks:
        for w in words:
            df[w] = df.get(w, 0) + 1
    n = max(len(toks), 1)
    # Score on the RARE shared tokens only. Summing over all of them rewarded length:
    # the top pair under that scoring shared 'blocks', 'missing', 'where' — three words
    # that mean nothing together. Restricting to df<=2 took 96 pairs down to 14 and put
    # the two genuinely-related marcus entries (preset-core.txt, preset-explicit.txt) at
    # the top, which is the outcome the heuristic was always reaching for.
    ranked = []
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            rare = {w for w in toks[i][2] & toks[j][2] if df[w] <= PAIR_MAX_DF}
            if len(rare) < PAIR_MIN_RARE:
                continue
            score = sum(_math.log(n / df[w]) for w in rare)
            ranked.append((score, i, j, sorted(rare, key=lambda w: (df[w], w))[:3]))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    for score, i, j, rarest in ranked[:PAIR_LIMIT]:
        out.append(f"Minor {toks[i][0]} + {toks[j][0]} (score {score:.1f}) share {rarest} "
                   f"— candidate shared cause, promote if real: "
                   f"'{toks[i][1][:45]}…' / '{toks[j][1][:45]}…'")
    if len(ranked) > PAIR_LIMIT:
        out.append(f"({len(ranked) - PAIR_LIMIT} weaker pairs above the score floor not "
                   f"shown — raise PAIR_LIMIT in sweep.py to see them)")
    return out


def _handler_coverage() -> tuple[dict, set]:
    """({handler: mention count}, {handlers the tests actually CALL}).

    Shared by the source-assertion scanner and `.claude/hooks/delivery-gate.sh`, which
    blocks a turn that ships a changed `*_cmd` no test drives. One implementation on
    purpose: two copies of "does a test exercise this" would drift, and the drift would
    be invisible in exactly the direction that lets a broken handler through.

    `handlers` starts as every `*_cmd` function, then widens ONE HOP: any module-level
    function a `*_cmd` body calls directly by name is pulled in too. `gather_audit_data`
    is not itself named `*_cmd` but is called straight out of `audit_cmd`, and a
    source-only test on it (`test_nanogpt_reports_the_model_too`, reading its source for
    "SELFIE_MODEL"/"nanogpt" instead of calling it) slipped past the original
    `*_cmd`-only scope — CHANGELOG v2026-08-03.6, self-identified as the same family as
    the `/features` ValueError this scanner exists to catch (v2026-08-02.14). Deliberately
    NOT walked two hops out (a helper's own helpers) — that direction runs to every
    function bot.py defines and would misfire on functions legitimately tested by reading
    their source on purpose, e.g. `test_shared_prompt_hardcodes_no_character_specific_feature`
    scanning `build_selfie_prompt`'s source for hardcoded traits (v2026-08-03.2)."""
    bot_tree = ast.parse(BOT.read_text(encoding="utf-8"))
    module_funcs = {n.name: n for n in ast.walk(bot_tree)
                    if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))}
    handlers = {name for name in module_funcs if name.endswith("_cmd")}
    for name in list(handlers):
        for n in ast.walk(module_funcs[name]):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in module_funcs and n.func.id not in handlers:
                handlers.add(n.func.id)
    tree = ast.parse(TESTS.read_text(encoding="utf-8"))

    # All three ways a test can name a handler. Only `bot.<name>` was recognised, so a
    # `from bot import alpha_cmd` test that merely read its source was invisible in BOTH
    # directions — no mention, no call, no finding (gate_corpus `sa-from-import`).
    mods = {"bot"}                      # module aliases: import bot [as b]
    local: dict[str, str] = {}          # local name -> handler name, from `from bot import x`
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "bot":
                    mods.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "bot":
            for a in node.names:
                if a.name in handlers:
                    local[a.asname or a.name] = a.name

    mentioned, called = {}, set()

    def note(name):
        mentioned[name] = mentioned.get(name, 0) + 1

    for node in ast.walk(tree):
        # <module>.<name> anywhere — a mention, wherever it appears
        if isinstance(node, ast.Attribute) and getattr(node.value, "id", "") in mods:
            if node.attr in handlers:
                note(node.attr)
        # a bare name imported from bot — same thing
        elif isinstance(node, ast.Name) and node.id in local:
            note(local[node.id])
        # a CALL is the only thing that exercises dispatch, in either form
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and getattr(f.value, "id", "") in mods \
                    and f.attr in handlers:
                called.add(f.attr)
            elif isinstance(f, ast.Name) and f.id in local:
                called.add(local[f.id])
    return mentioned, called


_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')


def changed_lines_from_diff(diff: str) -> list[int]:
    """1-indexed NEW-file line numbers a unified diff touches.

    Lives here rather than inline in the hook so it can be run against a fixture: a
    parser embedded in a shell heredoc is a parser nobody will ever test.

    `+N,0` is a **pure deletion** — nothing in the new file changed, so it contributes
    NO lines. The first draft used `max(count, 1)` and credited the deletion to line N,
    which is the line *after* the removed block and usually belongs to a different
    function. `+N` with no count is exactly one line (gate_corpus `gate-diff-*`)."""
    out: list[int] = []
    for line in diff.splitlines():
        m = _HUNK.match(line)
        if not m:
            continue
        start = int(m.group(1))
        count = 1 if m.group(2) is None else int(m.group(2))
        out.extend(range(start, start + count))
    return out


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

    Flagged: a command handler (or a helper one hop below it — see `_handler_coverage`)
    the tests MENTION but never CALL. That is the dangerous state — it reads as covered.
    A handler with no tests at all is honestly untested and is not reported here. A
    mention inside inspect.getsource(...) counts as a mention, never as a call; driving
    the handler with fake Telegram objects is what counts."""
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
    "async-blocking": async_blocking,
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
