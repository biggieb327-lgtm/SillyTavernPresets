#!/usr/bin/env bash
# Stop hook — bounded eval-fix retry loop. When this session's uncommitted work breaks
# the regression evals (or pytest), feed the failing output back for another fix round
# instead of ending the turn. Bounded: MAX_FIX_ROUNDS blocks with failure output, then
# ONE escalation block, then it stands aside so the turn can always end. Counter lives
# in .claude/.runtime (gitignored), keyed by session id like budget-governor.sh.
# Deliberately does NOT honor stop_hook_active — the counter is the loop bound;
# delivery-gate's once-only guard would make a multi-round fix loop impossible.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime
MAX_FIX_ROUNDS=3

sid=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("session_id") or "unknown")[:16])' 2>/dev/null) || exit 0
f=".claude/.runtime/eval-retries-${sid}.count"

# Only gate when this session actually changed gated surfaces (uncommitted diff vs
# HEAD). A doc-only or read-only session must never be blocked by a failure it inherited.
if git diff --quiet HEAD -- telegram-companion-bot .claude/hooks .claude/evals .claude/settings.json 2>/dev/null; then
  rm -f "$f"
  exit 0
fi

out=$(bash .claude/evals/run-evals.sh 2>&1); evals_rc=$?
py_out=""; py_rc=0
# python3 -m pytest, never bare pytest — the bare binary can belong to a different
# interpreter without the project's deps (same lesson as venv-explicit-python).
if [ $evals_rc -eq 0 ] && python3 -m pytest --version >/dev/null 2>&1; then
  py_out=$(python3 -m pytest telegram-companion-bot/tests/ -q 2>&1); py_rc=$?
fi
if [ $evals_rc -eq 0 ] && [ $py_rc -eq 0 ]; then
  rm -f "$f"
  exit 0
fi

n=$(( $(cat "$f" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$f"
fails=$(printf '%s\n%s' "$out" "$py_out" | grep -E '^FAIL|^FAILED|Error' | grep -v '^PASS' | head -10)

if [ "$n" -le "$MAX_FIX_ROUNDS" ]; then
  printf '[eval-gate] evals/tests are failing (fix round %d of %d):\n%s\nDiagnose and fix the CODE. Never edit an eval or test to make it pass — evals pin real incidents. Re-run: bash .claude/evals/run-evals.sh\n' "$n" "$MAX_FIX_ROUNDS" "$fails" >&2
  exit 2
elif [ "$n" -eq $((MAX_FIX_ROUNDS + 1)) ]; then
  printf '[eval-gate] %d fix rounds exhausted and evals still fail. STOP attempting fixes. Escalate: summarize for the owner (1) what is failing, (2) what was tried, (3) your best root-cause hypothesis. Do NOT edit evals. Then end the turn.\n' "$MAX_FIX_ROUNDS" >&2
  exit 2
fi
exit 0
