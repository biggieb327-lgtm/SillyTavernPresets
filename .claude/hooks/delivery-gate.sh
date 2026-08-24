#!/usr/bin/env bash
# Stop hook — the "no fake done" gate. Blocks ending the turn when bot.py was modified
# but the repo's own shipping rules (BOT_VERSION bump, CHANGELOG entry, a compile check
# in the evidence log) haven't been met. Re-verifies every stop; stands aside only after
# MAX_BLOCKS consecutive blocks in a session (the bound that prevents an infinite loop).
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime
MAX_BLOCKS=3

# Bounded per-session block counter, NOT a blanket stop_hook_active bypass. The old guard
# exited 0 on the SECOND consecutive stop, so a bot.py edit made during a forced
# continuation shipped ungated (2026-08-24 audit H1). Re-verify every stop; only stand
# aside after MAX_BLOCKS consecutive blocks — that bound, not a one-shot skip, is what
# prevents an infinite stop loop (the pattern eval-gate.sh uses and documents). Counter in
# .claude/.runtime (gitignored), keyed by session id like eval-gate.sh and budget-governor.
sid=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("session_id") or "unknown")[:16])' 2>/dev/null) || exit 0
cnt=".claude/.runtime/delivery-gate-blocks-${sid}.count"

BOT=telegram-companion-bot/bot.py
CHANGELOG=telegram-companion-bot/CHANGELOG.md

# Only gate when bot.py differs from HEAD (staged or unstaged). Compliant or unmodified
# resets the counter, so a later fresh non-compliant edit gets the full MAX_BLOCKS again.
if git diff --quiet HEAD -- "$BOT" 2>/dev/null; then
  rm -f "$cnt"
  exit 0
fi

missing=""

# 1. BOT_VERSION must have changed.
if git diff HEAD -- "$BOT" | grep -q '^[+-]BOT_VERSION'; then :; else
  missing="${missing}- BOT_VERSION was not bumped (required for /update + /audit to detect the deploy)\n"
fi

# 2. CHANGELOG must be touched in the same change.
if git diff --quiet HEAD -- "$CHANGELOG" 2>/dev/null; then
  missing="${missing}- no CHANGELOG.md entry (root cause first, fix second — per CLAUDE.md)\n"
fi

# 3. Evidence log must show a compile/test run today.
if ! grep -qE 'py_compile|compileall|pytest' ".claude/.runtime/evidence-$(date +%Y%m%d).log" 2>/dev/null; then
  missing="${missing}- no compile/test evidence logged (run: python3 -m py_compile ${BOT})\n"
fi

# 4. Every command handler this diff TOUCHES must be exercised by a test that CALLS it.
#    The review half of the checklist, made mechanical. /features raised ValueError on
#    every invocation for four releases while two tests "covering" it stayed green by
#    reading its source (v2026-08-02.14). git puts the enclosing def on the hunk header,
#    which is how a touched handler is identified without parsing the diff body.
#    Changed line numbers come from `git diff -U0` and are mapped to handlers by exact
#    AST line range. Not git's hunk header: it names the enclosing function only when
#    the change sits below the hunk's leading context, so a change in a handler's first
#    few lines is credited to the PREVIOUS function. The first draft used the header and
#    the break-test caught it missing that case entirely.
#    FAILS CLOSED. The first version piped stderr to /dev/null and ignored the exit
#    status, so anything that made sweep raise — an unparseable bot.py or test file, a
#    missing path, an import error — produced an empty result that read exactly like
#    "no unexercised handlers". A guard that cannot run must never look like a guard
#    that passed (gate_corpus `gate-sweep-crashes`).
unexercised=$(git diff -U0 HEAD -- "$BOT" | python3 -c "
import sys
sys.path.insert(0, '.claude/tools')
import sweep
lines = sweep.changed_lines_from_diff(sys.stdin.read())
touched = sweep.handlers_at_lines(lines)
print(' '.join(sorted(touched - sweep._handler_coverage()[1])))" 2>&1)
gate_rc=$?
if [ "$gate_rc" -ne 0 ]; then
  reason=$(printf '%s' "$unexercised" | tail -1)
  missing="${missing}- the handler-coverage check could not RUN (python exit ${gate_rc}) — unmet, not passed: ${reason}\n"
else
  for h in $unexercised; do
    missing="${missing}- ${h}() was changed but no test CALLS it — a test that reads its source cannot fail for the reason it exists (run: python3 .claude/tools/sweep.py source-assertion)\n"
  done
fi

if [ -n "$missing" ]; then
  n=$(( $(cat "$cnt" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$cnt"
  if [ "$n" -gt "$MAX_BLOCKS" ]; then
    printf '[delivery-gate] bot.py is STILL modified without the shipping checklist after %d blocks — standing aside so the turn can end. This is the loop bound, NOT approval: the checklist below is unmet and shipping it now is yours to justify.\n%b' "$MAX_BLOCKS" "$missing" >&2
    rm -f "$cnt"
    exit 0
  fi
  printf '[delivery-gate] bot.py is modified but the shipping checklist is incomplete (block %d of %d):\n%b Complete these (or explicitly tell the user why they do not apply) before finishing.\n' "$n" "$MAX_BLOCKS" "$missing" >&2
  exit 2
fi
rm -f "$cnt"
exit 0
