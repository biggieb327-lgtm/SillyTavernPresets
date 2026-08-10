#!/usr/bin/env bash
# verify-can-fail.sh — prove every REQUIRED step of verify.sh is able to go red.
#
#   bash .claude/tools/verify-can-fail.sh
#
# WHY (constraint C13, seen 7 — "a verification command that cannot fail is not
# verification"): verify.sh is the harness every other claim in this repo rests on, and
# until 2026-08-10 no step of it had ever been proved capable of failing. One was not.
# `python3 -m py_compile bot.py` printed `ok  compile  bot.py` on a module that could not
# import, because compiling checks syntax and never executes module level. The label was
# trusted for as long as nobody asked it the question C13 asks of every check:
#
#     what single edit should turn this red, and have I made that edit and watched it?
#
# This script asks that question of each step, one edit at a time, and watches. It is the
# mechanical form of C13's own sentence, and it is only possible because break-test.sh
# (built the same day for C18) proves the injection landed and the revert restored — the
# two things hand-run break-tests kept silently failing to do.
#
# Deliberately NOT wired into run-evals.sh: it runs the full suite several times over and
# would make the eval-gate Stop hook unusable. The cheap half is the `verify-steps-covered`
# eval, which fails if verify.sh grows a step this script does not exercise. Run this by
# hand whenever verify.sh, run-evals.sh, or gate_corpus changes.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 1

BT=".claude/tools/break-test.sh"
BOT="telegram-companion-bot/bot.py"
pass=0; fail=0

# case <label> <file> <old> <new> <command...>
# The command must EXIT NON-ZERO with the defect present; break-test.sh enforces that,
# plus the anchor/injection/restore facts, and puts the file back on every exit path.
case_() {
  local label="$1" file="$2" old="$3" new="$4"; shift 4
  printf '\n── %s ──────────────────────────────\n' "$label"
  if bash "$BT" --file "$file" --old "$old" --new "$new" -- "$@"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf '\033[31mFAIL\033[0m  step "%s" did not go red — that step cannot fail (C13)\n' "$label"
  fi
}

echo "verify-can-fail: proving each required verify.sh step can go red"

# ── step 1: import bot.py ───────────────────────────────────────────────────────────────
# The exact 2026-08-10 defect: a module-level call placed above the helper it calls.
# py_compile passes this; importing does not. That difference is why the step changed.
case_ "1/4  import    bot.py" "$BOT" \
  '_CONFIG_WARNINGS: list[str] = []' \
  '_CONFIG_WARNINGS: list[str] = []
_VERIFY_CAN_FAIL_PROBE = _env_int("X", "1")' \
  python3 -c "import runpy; runpy.run_path('telegram-companion-bot/tests/conftest.py'); import bot"

# ── step 2: pytest ──────────────────────────────────────────────────────────────────────
# A default flip the suite pins (TestMapIntentDefaultsOn). Behavioural, not cosmetic.
case_ "2/4  pytest    unit suite" "$BOT" \
  'MAP_INTENT = _env_bool("MAP_INTENT", True)' \
  'MAP_INTENT = _env_bool("MAP_INTENT", False)' \
  python -m pytest telegram-companion-bot/tests/ -q

# ── step 3: run-evals.sh ────────────────────────────────────────────────────────────────
# Removes the force-read the `streaming-error-body` eval pins — a real past incident
# (streamed 400s arrived with empty bodies and cost three fix rounds).
case_ "3/4  evals     run-evals.sh" "$BOT" \
  '_ = resp.content' \
  '_ = None  # verify-can-fail probe' \
  bash .claude/evals/run-evals.sh

# ── step 4: gate_corpus ─────────────────────────────────────────────────────────────────
# Unregisters a scanner. gate_corpus asserts exact per-scanner outcomes, so a scanner that
# vanishes must be reported rather than silently skipped — the "fail closed" property its
# own header claims.
case_ "4/4  corpus    gate_corpus" ".claude/tools/sweep.py" \
  '    "constraints-drift": constraints_drift,' \
  '' \
  python3 .claude/tools/gate_corpus/run.py

echo
echo "────────────────────────────────────────────────"
if [ "$fail" -eq 0 ]; then
  echo "verify-can-fail: all ${pass} required step(s) proved able to go red"
else
  echo "verify-can-fail: ${fail} step(s) COULD NOT FAIL, ${pass} ok — those steps verify nothing"
fi
[ "$fail" -eq 0 ]
