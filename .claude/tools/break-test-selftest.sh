#!/usr/bin/env bash
# break-test-selftest.sh — the break-tester, break-tested.
#
# `break-test.sh` edits a source file in place and restores it. That makes its failure mode
# destroying source code, and its FIRST version did exactly that: `mktemp` creates the
# snapshot file, so the `[ -f "$SNAP" ]` guard in the EXIT trap was true before the snapshot
# had been taken, and any early exit copied zero bytes over the target. bot.py was truncated
# to nothing on 2026-08-10 by the very run that was checking the tool's own failure modes.
#
# Every case below asserts the SAME invariant, which is the one that was violated:
# whatever happens, the target file is byte-identical afterwards. Runs entirely on temp
# files — it never touches anything in the repo.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 1

BT=".claude/tools/break-test.sh"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/bt-selftest.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

pass=0; fail=0
ok()  { printf '  \033[32mok\033[0m   %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail + 1)); }

# A tiny "module" and a "check" that passes only while the module says LIVE.
setup() {
  printf 'VALUE = "LIVE"\nOTHER = "x"\nOTHER2 = "x"\n' > "$WORK/mod.py"
  printf '#!/usr/bin/env bash\ngrep -q %s "$1/mod.py"\n' "'VALUE = \"LIVE\"'" > "$WORK/check.sh"
  chmod +x "$WORK/check.sh"
  ORIG=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$WORK/mod.py")
}
intact() {  # intact <label>
  local now
  now=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$WORK/mod.py" 2>&1)
  # Two empty hashes compare EQUAL, so a python that died at both call sites would report
  # "byte-identical" about a file it never read — fail-open, in the selftest that exists to
  # make break-tests trustworthy. Found 2026-08-21 sweeping for the run-evals.sh class.
  if [ -z "$ORIG" ] || [ -z "$now" ]; then
    bad "$1 — could not hash the target (ORIG='${ORIG}' now='${now}'); this is not evidence of anything"
  elif [ "$now" = "$ORIG" ]; then ok "$1 — target byte-identical"; else bad "$1 — TARGET CORRUPTED ($(wc -c < "$WORK/mod.py") bytes)"; fi
}
expect_rc() {  # expect_rc <want> <got> <label>
  if [ "$2" = "$1" ]; then ok "$3 — exit $2"; else bad "$3 — exit $2, wanted $1"; fi
}

echo "break-test selftest"

# 1. Happy path: a real defect the check catches.
setup
bash "$BT" --file "$WORK/mod.py" --old 'VALUE = "LIVE"' --new 'VALUE = "DEAD"' \
     -- "$WORK/check.sh" "$WORK" >/dev/null 2>&1
expect_rc 0 "$?" "happy path passes"
intact "happy path"

# 2. Anchor matches nothing — the 2026-08-10 silent non-injection.
setup
bash "$BT" --file "$WORK/mod.py" --old 'NOT_PRESENT_ANYWHERE' --new 'x' \
     -- "$WORK/check.sh" "$WORK" >/dev/null 2>&1
expect_rc 1 "$?" "0-match anchor refuses"
intact "0-match anchor"     # <-- the case that truncated bot.py

# 3. Anchor matches more than once (C17).
setup
bash "$BT" --file "$WORK/mod.py" --old 'OTHER' --new 'CHANGED' \
     -- "$WORK/check.sh" "$WORK" >/dev/null 2>&1
expect_rc 1 "$?" "2-match anchor refuses"
intact "2-match anchor"

# 4. --old and --new identical: the injection cannot change anything.
setup
bash "$BT" --file "$WORK/mod.py" --old 'VALUE = "LIVE"' --new 'VALUE = "LIVE"' \
     -- "$WORK/check.sh" "$WORK" >/dev/null 2>&1
expect_rc 1 "$?" "no-op injection refuses"
intact "no-op injection"

# 5. The check does not catch the defect — it stays green while broken.
setup
bash "$BT" --file "$WORK/mod.py" --old 'OTHER2 = "x"' --new 'OTHER2 = "y"' \
     -- "$WORK/check.sh" "$WORK" >/dev/null 2>&1
expect_rc 1 "$?" "check that stays green is reported"
intact "check stays green"

# 6. The command is killed mid-run — the trap still restores.
setup
bash "$BT" --file "$WORK/mod.py" --old 'VALUE = "LIVE"' --new 'VALUE = "DEAD"' \
     -- bash -c 'kill -TERM $$' >/dev/null 2>&1
intact "command killed mid-run"

echo "selftest: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
