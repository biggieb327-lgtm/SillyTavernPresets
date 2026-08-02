#!/usr/bin/env python3
"""gate_corpus — prove the guard scripts catch what they claim to catch.

Why this exists: on 2026-08-02 three separate pattern bugs shipped inside guards
written the same day (a test that flagged its own comment, a hook that fired on prose
quoting a command, a parser that matched a heading named mid-sentence and reported a
confident zero). Every one was found by hand. A guard that has never been run against
an input designed to slip past it is not a guard — it is a hope with a regex in it.

Each case pins an EXACT expected outcome for one pattern-matching assumption:

    expect="hit"    the scanner must report a finding containing `match`
    expect="clean"  the scanner must report nothing

Scanners run in a subprocess with SWEEP_* pointing at fixtures, because sweep.py
resolves its paths at import time — running them in-process would leak the first
case's paths into every later one. The delivery gate runs end to end against a
throwaway git repo, since its input is a real `git diff`.

    python3 .claude/tools/gate_corpus/run.py            # all cases
    python3 .claude/tools/gate_corpus/run.py -v         # show every case
    python3 .claude/tools/gate_corpus/run.py constraints-drift   # one scanner

Exit 1 if any case deviates. Wired into run-evals.sh as `gate-corpus`, so the gate
is itself gated.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"
TOOLS = HERE.parent
REPO = TOOLS.parent.parent

# name, scanner, fixture overrides, expected outcome, and the assumption it probes.
CASES = [
    # ── markdown-interp ────────────────────────────────────────────────────
    dict(name="md-plain-interp", scanner="markdown-interp", bot="md_plain.py",
         expect="hit", match="['name']", probes="baseline: bare {var} through Markdown"),
    dict(name="md-backticked", scanner="markdown-interp", bot="md_backticked.py",
         expect="clean", probes="baseline: backtick-wrapped value is the documented exemption"),
    dict(name="md-single-quotes", scanner="markdown-interp", bot="md_single_quotes.py",
         expect="hit", match="name",
         probes="A6 — parse_mode matched as a double-quoted literal only"),
    dict(name="md-far-interp", scanner="markdown-interp", bot="md_far_interp.py",
         expect="hit", match="name", probes="A7 — fixed 7-line lookback window"),
    dict(name="md-format-spec", scanner="markdown-interp", bot="md_format_spec.py",
         expect="hit", match="['n']", probes="A10 — placeholder regex rejects :format specs"),

    # ── shared-writes ──────────────────────────────────────────────────────
    dict(name="sw-direct", scanner="shared-writes", bot="sw_direct.py",
         expect="hit", match="bot.py.bak", probes="baseline: write to a __file__-derived dir"),
    dict(name="sw-instance-dir", scanner="shared-writes", bot="sw_instance_dir.py",
         expect="clean", probes="baseline: instance dir from argv is not shared"),
    dict(name="sw-multiline-assign", scanner="shared-writes", bot="sw_multiline_assign.py",
         expect="hit", match="bot.py.bak",
         probes="A11 — __file__ assignment assumed to be on one line"),
    dict(name="sw-str-replace", scanner="shared-writes", bot="sw_str_replace.py",
         expect="clean", probes="A13 — write verbs matched as substrings; str.replace is not a write"),

    # ── silent-return ──────────────────────────────────────────────────────
    dict(name="sr-silent-branch", scanner="silent-return", bot="sr_silent_branch.py",
         expect="hit", match="a_cmd", probes="baseline: early return with no reply"),
    dict(name="sr-guarded", scanner="silent-return", bot="sr_guarded.py",
         expect="clean", probes="baseline: _is_admin returns silently on purpose"),
    dict(name="sr-nested-helper", scanner="silent-return", bot="sr_nested_helper.py",
         expect="clean", probes="regression: a return inside a nested helper is not the handler's"),
    dict(name="sr-reply-named-guard", scanner="silent-return", bot="sr_reply_named_guard.py",
         expect="hit", match="a_cmd",
         probes="A17 — REPLY names matched as substrings; _reply_budget_ok is not a reply"),

    # ── source-assertion ───────────────────────────────────────────────────
    dict(name="sa-mention-only", scanner="source-assertion", bot="sa_handlers.py",
         tests="sa_mention_only.py", expect="hit", match="alpha_cmd",
         probes="baseline: getsource mention with no call"),
    dict(name="sa-called", scanner="source-assertion", bot="sa_handlers.py",
         tests="sa_called.py", expect="clean", probes="baseline: a real call clears it"),
    dict(name="sa-from-import", scanner="source-assertion", bot="sa_handlers.py",
         tests="sa_from_import.py", expect="hit", match="alpha_cmd",
         probes="A37 — handlers assumed to be referenced as bot.<name>"),

    # ── env-drift ──────────────────────────────────────────────────────────
    dict(name="env-undocumented", scanner="env-drift", bot="env_reads_newvar.py",
         env="env_missing_newvar.example", expect="hit", match="NEWVAR",
         probes="baseline: read but absent from .env.example"),
    dict(name="env-documented-unread", scanner="env-drift", bot="env_reads_nothing.py",
         env="env_documents_ghost.example", expect="hit", match="GHOSTVAR",
         probes="baseline: documented but nothing reads it"),
    dict(name="env-environ-get", scanner="env-drift", bot="env_environ_get.py",
         env="env_documents_nothing.example", expect="hit", match="SNEAKY",
         probes="A21 — env reads assumed to go through os.getenv/_env_int/_env_float"),
    dict(name="env-two-char-name", scanner="env-drift", bot="env_reads_tz.py",
         env="env_documents_tz_only.example", expect="clean",
         probes="A23 — {2,} makes 2-char names like TZ invisible in BOTH directions"),

    # ── install-hint ───────────────────────────────────────────────────────
    dict(name="ih-pkg", scanner="install-hint", bot="ih_pkg.py",
         expect="hit", match="system-package", probes="baseline: hardcoded pkg install"),
    dict(name="ih-helper", scanner="install-hint", bot="ih_helper.py",
         expect="clean", probes="baseline: routed through _pkg_hint"),
    dict(name="ih-multiline-string", scanner="install-hint", bot="ih_multiline_string.py",
         expect="hit", match="system-package",
         probes="A26 — quote and hint assumed to be on the same line"),

    # ── constraints-drift ──────────────────────────────────────────────────
    dict(name="cd-healthy", scanner="constraints-drift", constraints="neutral.md",
         expect="clean", probes="baseline: a healthy log is silent"),
    dict(name="cd-backlog", scanner="constraints-drift", constraints="cd_backlog.md",
         expect="hit", match="since the last promotion pass",
         probes="baseline: 12 entries since the last pass"),
    dict(name="cd-phantom-section", scanner="constraints-drift",
         constraints="cd_phantom_section.md", today="2026-08-02", expect="clean",
         probes="A28 — '## Minor' split is not line-anchored: prose naming it turns dated "
                "bullets elsewhere into phantom entries"),
    dict(name="cd-last-pass-in-prose", scanner="constraints-drift",
         constraints="cd_last_pass_in_prose.md", expect="clean",
         probes="A31 — first '**Last promotion pass:**' ANYWHERE wins, so prose quoting an "
                "old date manufactures a backlog that isn't there"),
    dict(name="cd-star-bullets", scanner="constraints-drift",
         constraints="cd_star_bullets.md", expect="hit",
         match="since the last promotion pass",
         probes="A30 — entries assumed to use '- ' bullets"),
    dict(name="cd-ungraduated", scanner="constraints-drift",
         constraints="cd_ungraduated.md", expect="hit", match="owes a hook",
         probes="baseline: seen>=2 with no Graduated line"),
    dict(name="cd-stale-active", scanner="constraints-drift",
         constraints="cd_stale_active.md", today="2026-08-02", expect="hit",
         match="older than 30 days", probes="baseline: an entry past the archive window"),
    dict(name="cd-stale-archived", scanner="constraints-drift",
         constraints="cd_stale_archived.md", today="2026-08-02", expect="clean",
         probes="baseline: the same entry, archived, must not count"),

    # ── mutations invented AFTER the fixes, to catch overfitting to the first corpus ──
    dict(name="md-parsemode-enum", scanner="markdown-interp", bot="md_parsemode_enum.py",
         expect="hit", match="['who']",
         probes="MUTATION: parse_mode as an enum attribute, not a string literal"),
    dict(name="sw-tuple-target", scanner="shared-writes", bot="sw_tuple_target.py",
         expect="hit", match="bot.py.bak",
         probes="MUTATION: __file__ assigned through a TUPLE target"),
    dict(name="sw-annassign", scanner="shared-writes", bot="sw_annassign.py",
         expect="hit", match="bot.py.bak",
         probes="MUTATION: annotated assignment (AnnAssign), not a plain Assign"),
    dict(name="sa-module-alias", scanner="source-assertion", bot="sa_handlers.py",
         tests="sa_module_alias.py", expect="hit", match="alpha_cmd",
         probes="MUTATION: `import bot as b`, mention-only via the alias"),
    dict(name="cd-en-dash", scanner="constraints-drift", constraints="cd_en_dash.md",
         expect="hit", match="since the last promotion pass",
         probes="MUTATION: entries separated by an en dash rather than an em dash"),
]

# Delivery-gate cases run end to end against a throwaway git repo.
GATE_CASES = [
    dict(name="gate-unexercised-handler", bot="sa_handlers.py", tests="sa_mention_only.py",
         edit=('    await update.message.reply_text("a")',
               '    await update.message.reply_text("a")  # touched'),
         expect="block", match="alpha_cmd",
         probes="baseline: a changed handler no test calls"),
    dict(name="gate-exercised-handler", bot="sa_handlers.py", tests="sa_called.py",
         edit=('    await update.message.reply_text("a")',
               '    await update.message.reply_text("a")  # touched'),
         expect="allow",
         probes="baseline: a changed handler a test drives must not be flagged"),
    dict(name="gate-sweep-crashes", bot="sa_handlers.py", tests="sa_mention_only.py",
         corrupt_tests=True,
         edit=('    await update.message.reply_text("a")',
               '    await update.message.reply_text("a")  # touched'),
         expect="block", match="could not RUN",
         probes="A47 — sweep raising must be reported as UNMET, never as passed"),
]

RUNNER = """
import json, sys
sys.path.insert(0, %r)
import sweep
print("@@JSON@@" + json.dumps(sweep.SCANNERS[%r]()))
"""


def run_scanner(case) -> tuple[list[str], str]:
    env = dict(os.environ)
    env["SWEEP_BOT"] = str(FIX / "bot" / case.get("bot", "neutral.py"))
    env["SWEEP_TESTS"] = str(FIX / "tests" / case.get("tests", "neutral.py"))
    env["SWEEP_CONSTRAINTS"] = str(FIX / "constraints" / case.get("constraints", "neutral.md"))
    env["SWEEP_ENV"] = str(FIX / "env" / case.get("env", "neutral.example"))
    env["SWEEP_TODAY"] = case.get("today", "2026-08-02")
    r = subprocess.run([sys.executable, "-c", RUNNER % (str(TOOLS), case["scanner"])],
                       capture_output=True, text=True, env=env)
    if "@@JSON@@" not in r.stdout:
        return [], f"scanner crashed: {(r.stderr or r.stdout).strip().splitlines()[-1:]}"
    return json.loads(r.stdout.split("@@JSON@@", 1)[1]), ""


def run_gate(case) -> tuple[bool, str, str]:
    """(blocked, output, error). Builds a throwaway repo and runs the real hook."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "telegram-companion-bot" / "tests").mkdir(parents=True)
        (root / ".claude" / "tools").mkdir(parents=True)
        (root / ".claude" / "hooks").mkdir(parents=True)
        bot_p = root / "telegram-companion-bot" / "bot.py"
        bot_p.write_text((FIX / "bot" / case["bot"]).read_text(encoding="utf-8"),
                         encoding="utf-8")
        tests_src = (FIX / "tests" / case["tests"]).read_text(encoding="utf-8")
        if case.get("corrupt_tests"):
            tests_src += "\ndef broken(:\n"      # unparseable → sweep raises
        (root / "telegram-companion-bot" / "tests" / "test_pure.py").write_text(
            tests_src, encoding="utf-8")
        (root / "telegram-companion-bot" / "CHANGELOG.md").write_text("# c\n", encoding="utf-8")
        for f in ("sweep.py",):
            (root / ".claude" / "tools" / f).write_text(
                (TOOLS / f).read_text(encoding="utf-8"), encoding="utf-8")
        hook = root / ".claude" / "hooks" / "delivery-gate.sh"
        hook.write_text((REPO / ".claude" / "hooks" / "delivery-gate.sh").read_text(
            encoding="utf-8"), encoding="utf-8")
        g = dict(GIT_AUTHOR_NAME="c", GIT_AUTHOR_EMAIL="c@c", GIT_COMMITTER_NAME="c",
                 GIT_COMMITTER_EMAIL="c@c", **os.environ)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "commit", "-qm", "base"]):
            subprocess.run(cmd, cwd=root, env=g, capture_output=True)
        src = bot_p.read_text(encoding="utf-8")
        old, new = case["edit"]
        if src.count(old) != 1:
            return False, "", f"edit anchor matched {src.count(old)}× (expected 1)"
        bot_p.write_text(src.replace(old, new, 1), encoding="utf-8")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
        r = subprocess.run(["bash", str(hook)], input="{}", capture_output=True,
                           text=True, cwd=root, env=env)
        return r.returncode == 2, (r.stderr or "") + (r.stdout or ""), ""


DIFF_CASES = [
    dict(name="gate-diff-normal", diff="normal_change.diff", expect=[10, 11, 12],
         probes="baseline: +10,3 covers three new-file lines"),
    dict(name="gate-diff-pure-deletion", diff="pure_deletion.diff", expect=[],
         probes="A46 — +9,0 is a deletion: no new-file line changed, so no handler is touched"),
    dict(name="gate-diff-single-no-count", diff="single_line_no_count.diff", expect=[10],
         probes="baseline: +10 with no count is exactly one line"),
]

DIFF_RUNNER = """
import json, sys
sys.path.insert(0, %r)
import sweep
print("@@JSON@@" + json.dumps(sweep.changed_lines_from_diff(open(%r, encoding="utf-8").read())))
"""


def run_diff(case) -> tuple[list, str]:
    r = subprocess.run(
        [sys.executable, "-c", DIFF_RUNNER % (str(TOOLS), str(FIX / "diffs" / case["diff"]))],
        capture_output=True, text=True)
    if "@@JSON@@" not in r.stdout:
        return [], f"crashed: {(r.stderr or '').strip().splitlines()[-1:]}"
    return json.loads(r.stdout.split("@@JSON@@", 1)[1]), ""


def main(argv) -> int:
    verbose = "-v" in argv
    only = [a for a in argv[1:] if not a.startswith("-")]
    rows, failures = [], 0

    for case in CASES:
        if only and case["scanner"] not in only and case["name"] not in only:
            continue
        findings, err = run_scanner(case)
        if err:
            got, ok = "CRASH", False
        elif case["expect"] == "clean":
            got, ok = ("clean" if not findings else f"{len(findings)} finding(s)"), not findings
        else:
            hit = any(case["match"] in f for f in findings)
            got, ok = ("hit" if hit else ("clean" if not findings else "wrong finding")), hit
        rows.append((case["name"], case["expect"], got, ok, case["probes"],
                     err or (findings[0] if findings else "")))
        failures += not ok

    if not only or "delivery-gate" in only:
        for case in DIFF_CASES:
            got_lines, err = run_diff(case)
            ok = not err and got_lines == case["expect"]
            rows.append((case["name"], str(case["expect"]), str(got_lines), ok,
                         case["probes"], err))
            failures += not ok


        for case in GATE_CASES:
            blocked, out, err = run_gate(case)
            if err:
                got, ok = "HARNESS ERROR: " + err, False
            elif case["expect"] == "block":
                ok = blocked and case["match"] in out
                got = "block" if blocked else "allow"
                if blocked and not ok:
                    got = "blocked for another reason"
            else:
                ok = case["match"] not in out if case.get("match") else \
                    "CALLS it" not in out
                got = "allow" if ok else "block"
            rows.append((case["name"], case["expect"], got, ok, case["probes"],
                         err or ""))
            failures += not ok

    w = max(len(r[0]) for r in rows)
    print(f"{'case'.ljust(w)}  {'expect':<7} {'got':<18} probes")
    print("-" * (w + 60))
    for name, exp, got, ok, probes, detail in rows:
        if ok and not verbose:
            continue
        mark = "ok " if ok else "FAIL"
        print(f"{mark} {name.ljust(w - 3)}  {exp:<7} {got:<18} {probes}")
        if detail and not ok:
            print(f"     ↳ {detail[:150]}")
    print(f"\ngate-corpus: {len(rows) - failures}/{len(rows)} cases behave as specified"
          + (f" — {failures} deviation(s)" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
