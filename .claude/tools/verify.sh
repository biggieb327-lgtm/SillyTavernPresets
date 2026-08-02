#!/usr/bin/env bash
# verify.sh — the standing verification block, as ONE command.
#
# Exists because the block was four separate invocations typed from memory every time,
# and "I ran the tests" was drifting to mean different subsets on different days. One
# script means one deterministic signal, reusable from a hook or from CI.
#
#   bash .claude/tools/verify.sh          # everything
#   bash .claude/tools/verify.sh --quick  # skip the sweep (advisory, and the slowest)
#
# Exit 0 only if every REQUIRED step passed. The sweep is advisory by design — it emits
# candidates, not defects (see its header) — so it reports but never fails the run.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 1

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

pass=0; fail=0
red() { printf '\033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail + 1)); }
grn() { printf '\033[32mok\033[0m    %s\n' "$1"; pass=$((pass + 1)); }

step() {  # step <label> <command...>
  local label="$1"; shift
  local out
  if out=$("$@" 2>&1); then
    grn "$label — $(printf '%s' "$out" | tail -1)"
  else
    red "$label"
    printf '%s\n' "$out" | tail -15 | sed 's/^/        /'
  fi
}

echo "── verify ──────────────────────────────────────────────────────"
step "compile   bot.py"        python3 -m py_compile telegram-companion-bot/bot.py
step "pytest    unit suite"    python -m pytest telegram-companion-bot/tests/ -q
step "evals     run-evals.sh"  bash .claude/evals/run-evals.sh
step "corpus    gate_corpus"   python3 .claude/tools/gate_corpus/run.py

if [ "$QUICK" -eq 0 ]; then
  # Advisory: candidates need judgement, so a hit is printed but never fails the run.
  sweep_out=$(python3 .claude/tools/sweep.py 2>&1)
  printf '\033[36mnote\033[0m  sweep     %s\n' "$(printf '%s' "$sweep_out" | grep '^sweep:')"
  printf '%s\n' "$sweep_out" | grep -E '^  [a-z_]+\.(py|md):' | sed 's/^/        /' | head -15
fi

echo "────────────────────────────────────────────────────────────────"
if [ "$fail" -eq 0 ]; then
  echo "verify: ${pass} required check(s) green"
else
  echo "verify: ${fail} FAILED, ${pass} green — do not claim done"
fi
[ "$fail" -eq 0 ]
