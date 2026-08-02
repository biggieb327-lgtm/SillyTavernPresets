#!/usr/bin/env python3
"""Operator-handoff guard — see handoff-guard.sh for scope and rationale.

Three failure shapes, all from 2026-08-02, all in the handoff rather than the work:

  A. A block whose later commands depend on shell state set earlier in the SAME block
     (a `cd`, then relative paths). The owner's shell was elsewhere, so seven
     `vps-sync.sh` calls resolved against the wrong directory. A relative path does
     not fail loudly — it silently targets the wrong place.

  B. A bare single-label hostname as an ssh/scp target, taken from the owner's shell
     prompt. A prompt hostname is what a box calls itself locally; it is not routable
     from another machine.

Scoped to operator-facing blocks only — ones carrying a `# host:` pragma or containing
commands specific to a host in this fleet. Illustrative snippets are left alone.

  C. A stdin-reading command (`read`) with more lines after it in the same block.
     Pasting buffers the whole block on the terminal's stdin, so `read` consumed the
     loop header as its input; the loop then ran with an empty variable.

Escape hatches, per block: `# handoff-ok: relative`, `# handoff-ok: hostname`,
`# handoff-ok: interactive`.

Fails OPEN on anything unexpected, same as host_guard: a guard that breaks sessions
gets disabled, which is worse than no guard.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    # Reuse C1's definitions so "is this operator-facing?" cannot drift between guards.
    from host_guard import FENCE, PHONE, VPS, last_assistant_text
except ImportError:
    sys.exit(0)

PRAGMA_HOST = re.compile(r'#\s*host:\s*(?:vps|phone|both)\b', re.I)
OK_RELATIVE = re.compile(r'#\s*handoff-ok:\s*relative\b', re.I)
OK_HOSTNAME = re.compile(r'#\s*handoff-ok:\s*hostname\b', re.I)
OK_INTERACTIVE = re.compile(r'#\s*handoff-ok:\s*interactive\b', re.I)
# Commands that consume stdin. In a pasted block the terminal has already buffered every
# following line, so these swallow the next line of the block instead of prompting.
STDIN_CMD = re.compile(r'(?:^|[;&|]\s*)(read|passwd|gpg|ssh-keygen)\b')

CD = re.compile(r'(?:^|[;&|]\s*|\bthen\s+|\bdo\s+)cd\s+\S')
SSH_TARGET = re.compile(r'\b(?:ssh|scp|rsync)\b[^\n]*?(?<![\w.-])[A-Za-z_][\w.-]*@([\w.-]+)')
IPV4 = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
# Leading shell noise to peel off a token before asking "is this a path?"
LEAD = re.compile(r'^(?:\d*[<>]+|[(){}]|\$\(|&&|\|\||[;|&])+')


def _strip(line: str) -> str:
    """Quoted spans and comments carry regexes and globs, not paths. Remove both."""
    line = QUOTED.sub(" ", line)
    return line.split("#", 1)[0]


def _relative_paths(line: str) -> list:
    """Path-looking tokens that resolve against the current directory."""
    out = []
    for tok in _strip(line).split():
        tok = LEAD.sub("", tok).rstrip(';&|)')
        if "/" not in tok or "://" in tok:
            continue
        if tok.startswith(("/", "~", "-")):
            continue                       # absolute, home-anchored, or an option
        if re.match(r'^\w+=', tok):        # VAR=value assignment, not a path argument
            continue
        out.append(tok)
    return out


def _operator_facing(block: str) -> bool:
    return bool(PRAGMA_HOST.search(block) or VPS.search(block) or PHONE.search(block))


def check(text: str) -> list:
    problems = []
    for block in FENCE.findall(text):
        if not _operator_facing(block):
            continue
        first = next((l.strip() for l in block.splitlines() if l.strip()), "")[:60]

        if not OK_RELATIVE.search(block):
            seen_cd = False
            for line in block.splitlines():
                if not seen_cd:
                    if CD.search(_strip(line)):
                        seen_cd = True
                    continue
                rel = _relative_paths(line)
                if rel:
                    problems.append(
                        f"  block starting {first!r} does `cd`, then uses relative "
                        f"path(s) {rel[:3]}. Operators paste subsets, and a relative "
                        f"path silently targets the wrong directory instead of failing. "
                        f"Write every path absolute.")
                    break

        if not OK_INTERACTIVE.search(block):
            lines = block.splitlines()
            for idx, line in enumerate(lines):
                if not STDIN_CMD.search(_strip(line)):
                    continue
                rest = [l for l in lines[idx + 1:]
                        if l.strip() and not l.strip().startswith("#")]
                if rest:
                    problems.append(
                        f"  block starting {first!r} runs a stdin-reading command "
                        f"({STDIN_CMD.search(_strip(line)).group(1)}) with {len(rest)} more "
                        f"line(s) after it. Pasting buffers the whole block, so it consumes "
                        f"the NEXT LINE as input instead of prompting. Split it into its own "
                        f"block marked run-alone.")
                break

        if not OK_HOSTNAME.search(block):
            for host in SSH_TARGET.findall(block):
                if "." in host or IPV4.match(host) or host in ("localhost",):
                    continue
                problems.append(
                    f"  block starting {first!r} targets bare hostname {host!r} over "
                    f"ssh/scp. A prompt or `hostname` value is not routable from another "
                    f"machine — use an address, or an ssh-config Host entry that exists "
                    f"on the machine running the command.")
                break
    return problems


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    text = last_assistant_text(payload.get("transcript_path") or "")
    if not text:
        return 0
    problems = check(text)
    if problems:
        sys.stderr.write(
            "[handoff-guard] operator-handoff hygiene (.claude/memory/constraints.md, "
            "C1 family) — a command block will not do what it says on the owner's "
            "machine:\n" + "\n".join(problems)
            + "\n Fix before finishing. Both shapes cost a round trip on 2026-08-02.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
