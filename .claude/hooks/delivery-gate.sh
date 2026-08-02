#!/usr/bin/env bash
# Stop hook — the "no fake done" gate. Blocks ending the turn when bot.py was modified
# but the repo's own shipping rules (BOT_VERSION bump, CHANGELOG entry, a compile check
# in the evidence log) haven't been met. Fires at most once per stop (stop_hook_active guard).
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Never block twice in a row — avoids infinite stop loops.
active=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("stop_hook_active", False))' 2>/dev/null) || exit 0
[ "$active" = "True" ] && exit 0

BOT=telegram-companion-bot/bot.py
CHANGELOG=telegram-companion-bot/CHANGELOG.md

# Only gate when bot.py differs from HEAD (staged or unstaged).
git diff --quiet HEAD -- "$BOT" 2>/dev/null && exit 0

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
unexercised=$(git diff -U0 HEAD -- "$BOT" | python3 -c "
import re, sys
sys.path.insert(0, '.claude/tools')
import sweep
lines = []
for L in sys.stdin:
    m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', L)
    if m:
        start, count = int(m.group(1)), int(m.group(2) or 1)
        lines.extend(range(start, start + max(count, 1)))
touched = sweep.handlers_at_lines(lines)
print(' '.join(sorted(touched - sweep._handler_coverage()[1])))" 2>/dev/null)
for h in $unexercised; do
  missing="${missing}- ${h}() was changed but no test CALLS it — a test that reads its source cannot fail for the reason it exists (run: python3 .claude/tools/sweep.py source-assertion)\n"
done

if [ -n "$missing" ]; then
  printf '[delivery-gate] bot.py is modified but the shipping checklist is incomplete:\n%b Complete these (or explicitly tell the user why they do not apply) before finishing.\n' "$missing" >&2
  exit 2
fi
exit 0
