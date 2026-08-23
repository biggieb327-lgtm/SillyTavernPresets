#!/usr/bin/env bash
# Stop hook — ask for a session-debrief at the one moment it can actually be done.
#
# WHY THIS EXISTS. `session-debrief`, `debrief-check.sh` and `debrief-log.md` were all
# built on 2026-08-11 and the ledger has exactly one row: the run that produced them.
# 170 commits of real work later, nothing had invoked the skill again. The only prompt was
# a SessionStart line reading "run debrief-check.sh when this session reaches a stopping
# point" — a request delivered at the START of a session about something to do at the END,
# by which time it has scrolled away or been compacted out.
#
# session-audit.sh's own comment argued SessionStart was the only actionable moment,
# reasoning that by the end the context is already being compacted. 170 commits and one
# ledger row falsify that: a reminder nobody acts on is not actionable, whatever the
# reasoning. The count still belongs at SessionStart as context; the ASK belongs here.
#
# WHAT IT DOES NOT DO. It does not decide whether the work deserves a debrief — that is
# `debrief-check.sh`'s job, and it can answer "not a stopping point yet". This hook only
# asks the question once, when the session looks like it has finished something.
#
# NO INVENTED THRESHOLD. debrief-log.md says not to pick a "debrief every N commits" rule
# before there are enough rows to show a distribution, and there is one row. So the gate is
# not a count: it is "this session committed something today and the tree is clean".
# Firing on those sessions is also what produces the rows that would justify a threshold.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime

payload=$(cat)
py() { printf '%s' "$payload" | python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

# Never fire on a stop this chain already blocked — same guard as host-guard/handoff-guard.
[ "$(py 'd.get("stop_hook_active", False)')" = "True" ] && exit 0

sid=$(py '(d.get("session_id") or "unknown")[:16]') || exit 0
marker=".claude/.runtime/debrief-nudged-${sid}"
[ -f "$marker" ] && exit 0

# A dirty tree is work in flight, not a stopping point. The other Stop hooks own that case.
[ -n "$(git status --porcelain 2>/dev/null)" ] && exit 0

today=$(date +%Y-%m-%d)
LEDGER=".claude/memory/debrief-log.md"

# Already debriefed today — nothing to ask for.
# NOT `grep -c … || echo 0`: grep -c prints "0" and exits 1 on no matches, so the fallback
# fires on success and the value becomes "0\n0" (C23, and the grep-c-fallback eval).
done_today=$(grep -c "^| ${today} |" "$LEDGER" 2>/dev/null); done_today=${done_today:-0}
[ "$done_today" != "0" ] && exit 0

# Did THIS session commit anything? "Today" is the same proxy debrief-check.sh already uses
# for its harvest check; a session spanning midnight is the known and accepted edge.
commits_today=$(git log --since="${today} 00:00" --oneline 2>/dev/null | wc -l | tr -d ' ')
[ "${commits_today:-0}" = "0" ] && exit 0

# How long since the last recorded debrief, for the message. Absent ledger or unknown sha
# is not an error — it just means the number cannot be stated, so it is not stated.
prev=$(grep -oE '^\| [0-9-]+ \| [0-9a-f]{7,} \|' "$LEDGER" 2>/dev/null | tail -1 | awk '{print $4}')
since=""
if [ -n "${prev:-}" ] && git cat-file -e "${prev}^{commit}" 2>/dev/null; then
  n=$(git rev-list --count "${prev}..HEAD" 2>/dev/null)
  [ -n "${n:-}" ] && since=" ${n} commit(s) since the last recorded debrief (${prev})."
fi

touch "$marker"
printf '[debrief-nudge] This session has %s commit(s) today and a clean tree — a stopping point.%s\nRun `bash .claude/tools/debrief-check.sh`, and load the `session-debrief` skill to harvest what this session learned into the memory layer. If it reports conditions unmet, fix those first; if the session genuinely produced nothing worth recording, say so in one line and end the turn. Record the run with `bash .claude/tools/debrief-check.sh --record`.\nFires once per session; this is the only time you will be asked.\n' \
  "$commits_today" "$since" >&2
exit 2
