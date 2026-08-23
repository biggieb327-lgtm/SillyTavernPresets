#!/usr/bin/env bash
# SessionStart hook — model/branch/state audit injected as context at session start.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "no-git")
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
# The startup context is an entry point, not the archive. Printing the WHOLE newest row
# put 7,725 characters of one closed 2026-08-10 incident into every session — 78% of this
# hook's entire output — to deliver a pointer that needs a date and a headline. The row is
# one Read away; what belongs here is the fact that it exists. Re-measure with
# `bash .claude/hooks/session-audit.sh | wc -c` if this hook grows: the same drift comes
# back one echo at a time.
last_log=$(grep -m1 '^| 20' .claude/memory/operational-log.md 2>/dev/null | cut -c1-180)

echo "[session-audit] branch=${branch} uncommitted_files=${dirty}"
if [ -n "${last_log}" ]; then
  echo "[session-audit] last operational-log entry: ${last_log}… (truncated — full row in .claude/memory/operational-log.md)"
else
  echo "[session-audit] last operational-log entry: none"
fi

# Constraints are only worth keeping if they are read BEFORE the same mistake recurs — but
# WHICH ones are worth 1,100 characters of every session's startup context is a different
# question, and the old answer was wrong.
#
# This line used to name every constraint at `seen: 2+`. That grew to 15 of 23, so a filter
# admitting two-thirds of its corpus had stopped filtering — and worse, it was selecting the
# wrong end. All 15 already had a mechanism; a hook or eval catches those whether or not the
# session read the name. The constraints where reading is the ONLY defence are the
# prose-only ones, and every one of them sat below the seen: 2 line, invisible.
#
# The evidence that the old line did not work is the session that changed it: it named C13,
# C14, C18 and C3 at startup, and that session then violated C13 three times and C14 twice.
# What actually fired was machinery — shell-semantics-guard, the delivery gate, a new eval.
#
# So: name the unguarded ones, count the rest. ~1,100 characters -> ~200, and a constraint
# now stays on this line until it earns a mechanism instead of being announced forever after
# it already has one. `constraints-mechanism-marked` keeps the parse honest; without it a
# reworded note would silently drop a constraint off this line, which is the failure this
# line exists to prevent.
if [ -f .claude/memory/constraints.md ]; then
  # One python pass rather than a grep pipeline: the two markers are mutually exclusive and
  # line-anchored, and a substring test gets it wrong — `"graduat" in body` matches
  # "**Not graduated.**" and reads an unguarded constraint as guarded.
  cline=$(python3 - 2>/dev/null <<'PYEOF'
import re, datetime
from pathlib import Path
blocks = re.split(r'\n### (C\d+) — ',
                  Path(".claude/memory/constraints.md").read_text(encoding="utf-8"))
GUARD, NOGUARD = re.compile(r'^\*\*Graduated', re.M), re.compile(r'^\*\*Not graduated', re.M)
DATE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

def dates(text):
    out = []
    for y, m, d in DATE.findall(text):
        try:
            out.append(datetime.date(int(y), int(m), int(d)))
        except ValueError:
            pass  # a malformed date is not a date; do not let it become one
    return out

bare, overdue, recurred, total = [], [], [], 0
for i in range(1, len(blocks), 2):
    cid, body = blocks[i], blocks[i + 1].split("\n### ")[0]
    total += 1
    if GUARD.search(body):
        # The mechanism-earning-its-place question: did this constraint recur AFTER its
        # guard shipped? Only decidable when a **Graduated line carries a date AND the
        # **seen: line does — an undated graduation is "could not determine", left unflagged
        # rather than guessed either way (hubris rule 1: unknown is not a negative verdict).
        # A hit is NOT a verdict that the guard failed: most of these guards state a half
        # they deliberately cannot cover (the operator's paste, a reading's meaning), and a
        # later occurrence in that half is the guard working as designed. It is a prompt to
        # read the prose and decide which half recurred — surfaced, not concluded.
        grad = dates("\n".join(l for l in body.splitlines() if l.startswith("**Graduated")))
        seen_line = re.search(r'^\*\*seen:.*', body, re.M)
        seen = dates(seen_line.group(0)) if seen_line else []
        if grad and seen and max(seen) > min(grad):
            n = re.search(r'\*\*seen: (\d+)\*\*', body)
            recurred.append(f"{cid}" + (f" (seen {n.group(1)})" if n else ""))
        continue
    seen = re.search(r'\*\*seen: (\d+)\*\*', body)
    n = int(seen.group(1)) if seen else 1
    # Rule 4: at seen 2 a constraint owes a mechanism. Prose-only AND repeating is the most
    # actionable state in the file, so it gets its own line rather than hiding in the list.
    (overdue if n >= 2 else bare).append(f"{cid}" + (f" (seen {n})" if n >= 2 else ""))
guarded = total - len(bare) - len(overdue)
if total:
    print(f"{total} active, {guarded} guarded by a mechanism.")
    if bare:
        print("PROSE ONLY — nothing mechanical will catch these, reading them is the whole "
              "defence: " + " · ".join(bare))
    if overdue:
        print("OVERDUE A MECHANISM (prose-only and already repeating — constraints.md rule "
              "4): " + " · ".join(overdue))
    if recurred:
        print("MECHANISM REVIEW — recurred after its guard shipped; read the prose to see "
              "whether the guard's covered half failed or its acknowledged prose-only half "
              "recurred (do not assume the guard failed): " + " · ".join(recurred))
    if not bare and not overdue:
        print("Every constraint is mechanically guarded — nothing here needs reading first.")
PYEOF
)
  if [ -n "${cline}" ]; then
    printf '[session-audit] constraints (.claude/memory/constraints.md): %s\n' "$(printf '%s' "${cline}" | head -1)"
    printf '%s\n' "${cline}" | tail -n +2 | sed 's/^/[session-audit] /'
  else
    # Never go quiet: an empty result means the parse broke, not that there is nothing to say.
    echo "[session-audit] constraints: could not read .claude/memory/constraints.md — read it by hand"
  fi
fi
# C22: working off a stale branch is invisible until the push is rejected — a merge-base
# EXISTING is not the same as it being recent enough to trust. One session spent four
# commits re-deriving history `origin/main` already recorded correctly, ~150 commits ahead.
# Read from the LOCAL origin/main ref with no fetch, so this is a lower bound; the ref's
# own age is printed beside it, because a staleness check that hides its own staleness is
# this constraint in miniature (C8).
if [ "${branch}" != "main" ] && git rev-parse --verify -q origin/main >/dev/null 2>&1; then
  base=$(git merge-base HEAD origin/main 2>/dev/null)
  if [ -n "${base}" ]; then
    behind=$(git rev-list --count "${base}..origin/main" 2>/dev/null || echo 0)
    refage=$(git log -1 --format=%cr origin/main 2>/dev/null || echo "unknown")
    if [ "${behind:-0}" -ge 25 ]; then
      echo "[session-audit] WARNING: merge-base is ${behind} commits behind origin/main (local ref, last moved ${refage}) — run 'git fetch origin main' and diff before extended work on shared docs (CLAUDE.md, constraints.md, operational-log.md, mycelium.md)"
    else
      echo "[session-audit] merge-base ${behind} commit(s) behind origin/main (local ref, last moved ${refage})"
    fi
  fi
fi
# How long since the last recorded session-debrief, in commits of real work.
#
# This line used to end with "run debrief-check.sh when this session reaches a stopping
# point", on the reasoning that SessionStart was the only actionable moment. 170 commits
# and one ledger row later, that reasoning is falsified: a request delivered at the START
# about something to do at the END is gone by the time it applies. The ASK moved to
# .claude/hooks/debrief-nudge.sh (Stop), which fires once per session at a clean tree.
# The NUMBER stays here, where it is useful as context for the session about to start.
#
# Reports the number and does not judge it: one data point is not a distribution, and
# inventing a "debrief every N commits" threshold from it is the estimate-as-fact trap
# (C8). Add the threshold once .claude/memory/debrief-log.md has enough rows to show one.
if [ -f .claude/memory/debrief-log.md ]; then
  last=$(grep -oE '^\| [0-9-]+ \| [0-9a-f]{7,} \|' .claude/memory/debrief-log.md 2>/dev/null | tail -1)
  lsha=$(printf '%s' "$last" | awk '{print $4}')
  ldate=$(printf '%s' "$last" | awk '{print $2}')
  if [ -n "${lsha:-}" ] && git cat-file -e "${lsha}^{commit}" 2>/dev/null; then
    since=$(git rev-list --count "${lsha}..HEAD" 2>/dev/null || echo '?')
    echo "[session-audit] last session-debrief: ${ldate} (${lsha}), ${since} commit(s) ago (debrief-nudge.sh will ask at this session's stopping point)"
  fi
fi
# Mycelium — open messages from previous sessions. The count tells the session to
# read the file; the entries themselves live there, not here.
if [ -f .claude/memory/mycelium.md ]; then
  # `|| echo 0` here shipped a hook that said "MYCELIUM: 0\n0 open message(s)" whenever the
  # file was fully acked — announcing waiting messages precisely when there were none.
  # Same trap as the constraints count above; caught 2026-08-21 by break-testing the eval.
  open_count=$(grep '^### 20' .claude/memory/mycelium.md 2>/dev/null | grep -c '| status: open$')
  open_count=${open_count:-0}
  if [ "${open_count}" != "0" ]; then
    echo "[session-audit] MYCELIUM: ${open_count} open message(s) from previous sessions — read .claude/memory/mycelium.md"
  fi
fi
echo "[session-audit] standing rules: read telegram-companion-bot/CHANGELOG.md before bot changes; bot.py changes need BOT_VERSION bump + changelog entry (delivery gate blocks otherwise); run .claude/evals/run-evals.sh before claiming done."
echo "[session-audit] NOTION: Fleet Knowledge Base (database 89c9e767576149a480221c10d7a97f47, data-source 2e75cb5e-bf93-4a2a-a1b8-9d7a1b415e4f) — before non-trivial work, search it for Status=current entries relevant to your task. Write findings, decisions, and state changes back when you produce them."
if [ "${dirty}" != "0" ]; then
  echo "[session-audit] WARNING: working tree not clean — inspect before assuming a fresh start:"
  git status --porcelain | head -10
fi
exit 0
