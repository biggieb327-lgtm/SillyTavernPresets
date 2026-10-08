#!/usr/bin/env python3
"""CI-read guard (Stop) — constraint C25: a push to `main` is not done until the check
result for that SHA has been read.

Twice on 2026-09-22 work reached `main` while CI on it went unread (one merge reported
"verified" from `run-evals.sh` alone while main had been red for 6 days; one DEFAULTS-table
slip pytest caught only in CI). `repo-change-control` already said "CI polled" — prose
had failed twice, so this is the mechanism.

The rule, after the LAST successful `git push … main` tool call in the transcript:
  allow if a later tool result contains the pushed SHA (first 7 chars) AND "completed"
        — the CI run for it was read (MCP `actions_list`, a curl of `actions/runs`, or a
        background poller's output file, all print both);
  allow if a background command that polls GitHub Actions was started after the push
        and its <task-notification> has NOT arrived yet — CI is being waited on. Once the
        notification arrives, a read (the first rule) is required;
  allow if the final message contains `ci-ok:` with a reason (no network, CI disabled);
  otherwise block.
The SHA is `git rev-parse origin/main`, which the push itself updates. `CI_GUARD_SHA`
overrides it (selftest). Fails OPEN on anything unexpected: a guard that breaks sessions
gets disabled, which is worse than no guard.

Run `python3 ci_read_guard.py --selftest`; run-evals.sh does (`ci-read-guard-selftest`).
"""
import json
import os
import re
import subprocess
import sys

PUSH_MAIN = re.compile(
    r"\bgit\s+push\b[^\n;&|]*?(?:\S:main(?![\w./-])|\s(?:origin|upstream)\s+main(?![\w./-]))")
PUSH_FAILED = re.compile(r"\brejected\b|^fatal:|^error:|\bfailed to push\b", re.I | re.M)
CI_POLL = re.compile(r"actions/runs|actions_list|actions_get|workflow_run")
OK = re.compile(r"\bci-ok:\s*\S")


def _command_text(cmd):
    """The parts of a shell command the shell executes: heredoc bodies and quoted strings
    removed, so a commit message or an `echo` that NAMES a push is not read as one."""
    out, end = [], None
    for ln in cmd.split("\n"):
        if end is not None:
            if ln.strip() == end:
                end = None
            continue
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", ln)
        if m:
            end = m.group(1)
        out.append(ln)
    return re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " ", "\n".join(out))


def _records(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    out.append(json.loads(raw))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return ""


def _blocks(rec):
    content = (rec.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _last_assistant_text(recs):
    for r in reversed(recs):
        if (r.get("message") or {}).get("role") == "assistant":
            t = "\n".join(b.get("text", "") for b in _blocks(r) if b.get("type") == "text")
            if t:
                return t
    return ""


def verdict(recs, sha):
    """None to allow, or a reason string to block."""
    if not sha:
        return None
    sha7 = sha[:7]
    uses, push_at = {}, None
    for i, r in enumerate(recs):
        for b in _blocks(r):
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                uses[b.get("id")] = (i, b.get("input") or {})
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                _, inp = uses[b.get("tool_use_id")]
                cmd = str(inp.get("command", ""))
                if (PUSH_MAIN.search(_command_text(cmd)) and not b.get("is_error")
                        and not PUSH_FAILED.search(_text(b.get("content")))):
                    push_at = i
    if push_at is None:
        return None
    if OK.search(_last_assistant_text(recs)):
        return None

    read_at, pollers, notified = None, {}, {}
    for i in range(push_at + 1, len(recs)):
        r = recs[i]
        for b in _blocks(r):
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                if (b.get("name") == "Bash" and inp.get("run_in_background")
                        and CI_POLL.search(str(inp.get("command", "")))):
                    pollers[b.get("id")] = i
            elif b.get("type") == "tool_result":
                t = _text(b.get("content"))
                if sha7 in t and "completed" in t.lower():
                    read_at = i
        if r.get("type") in ("attachment", "queue-operation", "user"):
            blob = json.dumps(r)
            if "task-notification" in blob:
                for pid in pollers:
                    if f"<tool-use-id>{pid}</tool-use-id>" in blob:
                        notified.setdefault(pid, i)

    if read_at is not None and all(read_at > at for at in notified.values()):
        return None
    if any(pid not in notified for pid in pollers):
        return None                              # a poller is still running
    if notified:
        return (f"the CI poller for {sha7} finished, but its result was not read — "
                f"read its output file and report `{sha7} | completed | <conclusion>`")
    return (f"main moved to {sha7} and no CI result for it was read, and no background "
            f"poller is waiting on it")


def _origin_main():
    if os.environ.get("CI_GUARD_SHA"):
        return os.environ["CI_GUARD_SHA"]
    try:
        p = subprocess.run(["git", "rev-parse", "origin/main"], capture_output=True,
                           text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    path = payload.get("transcript_path") or ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            if "git push" not in fh.read():
                return 0                         # cheap exit: no push this session
    except OSError:
        return 0
    try:
        reason = verdict(_records(path), _origin_main())
    except Exception:
        return 0
    if not reason:
        return 0
    sys.stderr.write(
        "[ci-read-guard] constraint C25 — a push to main is not done until CI for that "
        f"SHA has been read: {reason}.\n"
        " Poll the `evals` run for it (MCP actions_list, or a background `until` loop on\n"
        " api.github.com/repos/<owner>/<repo>/actions/runs) and read the result before\n"
        " finishing. Red on main is a deploy blocker — vps-sync.sh hard-resets to it.\n"
        " If CI genuinely cannot be read here, say so in the reply with `ci-ok: <reason>`.\n")
    return 2


# ---------------------------------------------------------------------------------------
def _bash(uid, cmd, out, err=False, bg=False):
    inp = {"command": cmd}
    if bg:
        inp["run_in_background"] = True
    return [{"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": uid, "name": "Bash", "input": inp}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": uid, "content": out, "is_error": err}]}}]


def _say(text):
    return {"type": "assistant", "message": {"role": "assistant",
                                             "content": [{"type": "text", "text": text}]}}


def _notify(uid):
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt":
            f"<task-notification>\n<tool-use-id>{uid}</tool-use-id>\n<status>completed"
            f"</status>\n</task-notification>"}}


def selftest() -> int:
    SHA = "abc1234def"
    push = _bash("p1", "git push -q origin b:main", "")
    poll_cmd = "until curl -s https://api.github.com/repos/o/r/actions/runs | grep -q x; do sleep 30; done"
    cases = [
        # (want block?, records, name)
        (False, [_say("hi")], "no push at all"),
        (False, _bash("p0", "git push origin feature", "") + [_say("done")], "push to a branch, not main"),
        (True,  push + [_say("Merged.")], "push to main, nothing read (the 2026-09-22 shape)"),
        (True,  _bash("p2", "git push origin HEAD:main", "") + [_say("ok")], "HEAD:main form"),
        (True,  _bash("p3", "git push -u origin main", "") + [_say("ok")], "origin main form"),
        (False, push + _bash("c1", "curl …/actions/runs", "abc1234: completed success 1452")
                + [_say("CI green")], "CI result read after the push"),
        (False, push + _bash("w1", poll_cmd, "started", bg=True) + [_say("waiting on CI")],
                "background poller armed, notification not yet in"),
        (True,  push + _bash("w1", poll_cmd, "started", bg=True) + [_notify("w1"), _say("done")],
                "poller finished, output never read"),
        (False, push + _bash("w1", poll_cmd, "started", bg=True) + [_notify("w1")]
                + _bash("r1", "cat /tmp/x.output", "abc1234: completed success") + [_say("green")],
                "poller finished and its output was read"),
        (True,  _bash("c0", "curl …/actions/runs", "abc1234: completed success") + push
                + [_say("ok")], "a read BEFORE the push does not count"),
        (False, _bash("pf", "git push origin b:main", "! [rejected] b -> main (non-fast-forward)")
                + [_say("rejected, will merge")], "rejected push is not a push"),
        (False, _bash("pe", "git push origin b:main", "fatal: unable to access", err=True)
                + [_say("network down")], "errored push is not a push"),
        (False, push + [_say("Pushed. ci-ok: this environment has no GitHub network access")],
                "explicit ci-ok escape"),
        (True,  push + _bash("c2", "curl …/actions/runs", "fff0000: completed success")
                + [_say("CI green")], "a different SHA's result does not count"),
        (False, _bash("x1", "echo 'git push origin b:main'", "git push origin b:main")
                + [_say("ok")], "a push named inside quotes is text, not a push"),
        (False, _bash("x2", "git commit -F - <<'MSG'\nfix: git push origin b:main docs\nMSG", "")
                + [_say("ok")], "a push named inside a heredoc body is text, not a push"),
    ]
    bad = 0
    for want, recs, name in cases:
        got = verdict(recs, SHA) is not None
        if got != want:
            bad += 1
            print(f"FAIL want block={want} got {got}: {name}")
    if verdict(push + [_say("x")], "") is not None:
        bad += 1
        print("FAIL no SHA (git unavailable) must fail open")
    print(f"ci_read_guard selftest: {len(cases) + 1 - bad}/{len(cases) + 1} ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
