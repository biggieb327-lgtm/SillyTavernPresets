#!/usr/bin/env python3
"""Scan Claude Code transcripts for messages where the model explained a decision
NOT to use a subagent.

Motivation: Claude Code 2.1.219+ ships system-prompt text telling the model
"Do not call the AgentTool unless the user requested it". This script measures
whether that suppression is visible in your own session history.

Method (deliberately conservative):
  * assistant messages only, text + thinking blocks
  * a message counts only if it contains BOTH an agent term AND declining
    language. Either signal alone is far too noisy to be evidence.
  * results are grouped by session, and only the matching sentence is printed.
  * two buckets:
      HIGH CONFIDENCE - session dated after the oldest local Claude Code install
                        AND the sentence echoes the injected wording.
      OTHER           - everything else, especially declines that cite the
                        user's own config (numbered rule, CLAUDE.md, AGENTS.md,
                        a fleet/worktree policy). Printed in full so the reader
                        can check it for contamination.

IMPORTANT: this finds only declines the model *explained*. Silent ones leave no
trace in the transcript. Every number here is a floor, never a total.

Usage:  python3 subagent-decline-scan.py [--projects DIR] [--versions DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# --- signals -----------------------------------------------------------------

AGENT_TERM = re.compile(
    r"\b(agent\s?tool|agent tool|sub-?agents?|spawn(?:ing)? an agent|"
    r"task tool|delegat\w+ to an agent)\b",
    re.I,
)

DECLINE_TERM = re.compile(
    r"(won'?t spawn|will not spawn|not spawning|rather than spawning|"
    r"not calling|won'?t call|will not call|not going to call|"
    r"instead of (?:calling|spawning|using) (?:an? )?(?:sub-?agent|agent)|"
    r"forbids?|not allowed to|am told not to|instructed not to|"
    r"instruction against|told not to|shouldn'?t (?:spawn|call|use)|"
    r"doesn'?t count as a user request|didn'?t (?:ask|request) (?:for )?(?:an? )?"
    r"(?:sub-?agent|agent)|unless the user (?:requested|asks)|"
    r"handle (?:this|it) (?:myself|inline)|do(?:ing)? (?:this|it) (?:myself|inline)|"
    r"no need to (?:spawn|delegate))",
    re.I,
)

# wording that echoes the injected system-prompt section itself
INJECTED_ECHO = re.compile(
    r"(unless the user (?:requested|explicitly asked|asks)|"
    r"do not call the agent\s?tool|do not spawn agents|"
    r"system prompt (?:says|tells|instructs)|"
    r"my (?:instructions|system prompt) (?:say|tell|forbid)|"
    r"not requested by the user|user (?:did not|didn'?t) request(?:ed)? it)",
    re.I,
)

# "this decline is explained by the USER's own config", not the injection
OWN_CONFIG = re.compile(
    r"(CLAUDE\.md|AGENTS\.md|standing instruction|operating manual|"
    r"numbered rule|rule #?\d|project instruction|worktree polic|fleet polic|"
    r"skill-router|do not load unrelated skills|repo rule)",
    re.I,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


# --- transcript reading ------------------------------------------------------


def iter_assistant_texts(path: Path):
    """Yield (timestamp, text) for every assistant text/thinking block."""
    with path.open("r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "assistant":
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                blocks = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                blocks = content
            else:
                continue
            ts = rec.get("timestamp") or ""
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    yield ts, b.get("text") or ""
                elif b.get("type") == "thinking":
                    yield ts, b.get("thinking") or ""


def matching_sentences(text: str):
    """Return sentences from a message that already qualified as a whole."""
    hits = []
    for sent in SENTENCE_SPLIT.split(text):
        s = sent.strip()
        if not s:
            continue
        if AGENT_TERM.search(s) and DECLINE_TERM.search(s):
            hits.append(s)
    if hits:
        return hits
    # signals split across adjacent sentences: fall back to the agent sentence
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if AGENT_TERM.search(s)][:2]


def parse_ts(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def oldest_install(versions_dir: Path):
    """Oldest local Claude Code install time, or None if undeterminable."""
    if versions_dir.is_dir():
        stamps = [
            datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            for p in versions_dir.iterdir()
        ]
        if stamps:
            return min(stamps), str(versions_dir)
    # fallback: the installed package directory
    for cand in (
        Path("/opt/node22/lib/node_modules/@anthropic-ai/claude-code/package.json"),
        Path("/usr/local/lib/node_modules/@anthropic-ai/claude-code/package.json"),
        Path.home() / ".claude/local/node_modules/@anthropic-ai/claude-code/package.json",
    ):
        if cand.exists():
            return (
                datetime.fromtimestamp(cand.stat().st_mtime, tz=timezone.utc),
                str(cand),
            )
    return None, None


# --- main --------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default=str(Path.home() / ".claude/projects"))
    ap.add_argument("--versions", default=str(Path.home() / ".local/share/claude/versions"))
    args = ap.parse_args()

    projects = Path(args.projects)
    files = sorted(projects.glob("**/*.jsonl"))

    install_dt, install_src = oldest_install(Path(args.versions))

    print("=" * 78)
    print("SUBAGENT-DECLINE SCAN")
    print("=" * 78)
    print(f"transcript root : {projects}")
    print(f"sessions scanned: {len(files)}")
    if install_dt:
        print(f"oldest install  : {install_dt.isoformat()}  (from {install_src})")
    else:
        print("oldest install  : UNKNOWN - no versions dir and no package.json found;")
        print("                  HIGH CONFIDENCE cannot be dated, so it stays empty.")
    print()
    print("SCOPE: this finds only declines the model *explained* in text or")
    print("thinking. Silent declines leave no trace. Every number below is a")
    print("FLOOR, never a total.")
    print()

    high = defaultdict(list)   # session -> [(ts, sentence)]
    other = defaultdict(list)
    total_msgs = 0
    total_hits = 0

    for f in files:
        session = f.stem
        for ts, text in iter_assistant_texts(f):
            total_msgs += 1
            if not text:
                continue
            if not (AGENT_TERM.search(text) and DECLINE_TERM.search(text)):
                continue
            total_hits += 1
            dt = parse_ts(ts)
            for sent in matching_sentences(text):
                after_install = bool(install_dt and dt and dt >= install_dt)
                echoes = bool(INJECTED_ECHO.search(sent))
                cites_own = bool(OWN_CONFIG.search(sent))
                if after_install and echoes and not cites_own:
                    high[session].append((ts, sent))
                else:
                    other[session].append((ts, sent))

    def dump(name, bucket, truncate=None):
        n_sent = sum(len(v) for v in bucket.values())
        print("-" * 78)
        print(f"{name}: {n_sent} sentence(s) across {len(bucket)} session(s)")
        print("-" * 78)
        if not bucket:
            print("  (empty)")
            print()
            return
        for session, rows in bucket.items():
            print(f"\n  session {session}  ({len(rows)} hit(s))")
            for ts, sent in rows:
                s = sent if truncate is None else sent[:truncate]
                print(f"    [{ts}] {s}")
        print()

    dump("HIGH CONFIDENCE (after install AND echoes injected wording)", high)
    dump("OTHER (printed in full - check for contamination)", other)

    print("=" * 78)
    print(f"assistant blocks examined : {total_msgs}")
    print(f"messages matching BOTH signals: {total_hits}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
