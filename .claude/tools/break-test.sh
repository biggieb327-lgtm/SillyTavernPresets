#!/usr/bin/env bash
# break-test.sh — perform a break-test, and prove the break-test itself worked.
#
#   bash .claude/tools/break-test.sh \
#        --file telegram-companion-bot/bot.py \
#        --old 'MAP_INTENT = _env_bool("MAP_INTENT", True)' \
#        --new 'MAP_INTENT = _env_bool("MAP_INTENT", False)' \
#        -- python3 -m pytest telegram-companion-bot/tests/test_pure.py -q -k MapIntent
#
# WHY THIS EXISTS (2026-08-10 session autopsy, .claude/SESSION-AUTOPSY-2026-08-10.md):
# break-testing is what this repo relies on to trust every check it has, and it was
# performed by hand every time. Across ~18 runs in one session, five were defective:
#
#   * two injections matched 0 and 4 anchors and changed nothing — the suite went green
#     and that green was read as "the check holds" when it meant "no defect was introduced"
#   * one revert dropped a leading newline, folding restored code into the comment above
#     it; `py_compile` passed and the corruption surfaced two steps later
#   * one ran against a checkout that predated the code being tested
#
# Constraint C18 was left as prose because "nothing can observe from outside whether two
# injections were applied together." True for that case. It does not extend to these:
# whether the injection LANDED and whether the revert RESTORED are both mechanically
# observable, and neither was being observed. This observes both.
#
# Six facts, all required, in order. Exit 0 only if all six hold:
#   1. the anchor matches EXACTLY once          (0 or 2+ means the edit is ambiguous — C17)
#   2. a snapshot of the file is taken          (hash printed)
#   3. the injection actually changed the file  (hash differs)
#   4. the command goes RED                     (non-zero — a check that will not go red
#                                                is a bug in the check, not a clean tree)
#   5. the file is restored BYTE-IDENTICAL      (hash matches the snapshot — C15: restore
#                                                from our own copy, never `git checkout`,
#                                                so uncommitted work is never at risk)
#   6. the command goes GREEN again             (zero — the other half of C3)
#
# The file is restored on EVERY exit path, including a failed command, a crash, or Ctrl-C.
set -u

FILE=""; OLD=""; NEW=""
while [ $# -gt 0 ]; do
  case "$1" in
    --file) FILE="${2:-}"; shift 2 ;;
    --old)  OLD="${2:-}";  shift 2 ;;
    --new)  NEW="${2:-}";  shift 2 ;;
    --)     shift; break ;;
    *) echo "break-test: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

if [ -z "$FILE" ] || [ -z "$OLD" ] || [ $# -eq 0 ]; then
  sed -n '2,10p' "$0" >&2
  echo "break-test: need --file, --old, and a command after --" >&2
  exit 2
fi
[ -f "$FILE" ] || { echo "break-test: no such file: $FILE" >&2; exit 2; }

SNAP=$(mktemp "${TMPDIR:-/tmp}/break-test.XXXXXX")
SNAPPED=0   # 1 only once the snapshot actually holds the file's contents

# The trap must NEVER write a snapshot that was not taken. `mktemp` creates the file, so
# an `[ -f "$SNAP" ]` guard is true from the start — the first version of this script used
# exactly that and truncated bot.py to zero bytes when it exited early on a bad anchor.
# Caught by break-testing this script's own failure modes, which is the argument for
# having done so. Two conditions now, not one: the snapshot was taken, AND it is non-empty.
restore() {
  if [ "$SNAPPED" = "1" ]; then
    if [ -s "$SNAP" ]; then
      cp "$SNAP" "$FILE"
    else
      echo "break-test: REFUSING to restore — snapshot is empty. ${FILE} left as-is." >&2
    fi
  fi
  rm -f "$SNAP"
}
trap restore EXIT INT TERM

hash_of() { python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()[:12])" "$1"; }

# --- 1. the anchor matches exactly once ------------------------------------------------
matches=$(python3 - "$FILE" "$OLD" <<'PY'
import pathlib, sys
print(pathlib.Path(sys.argv[1]).read_text().count(sys.argv[2]))
PY
)
if [ "$matches" != "1" ]; then
  echo "✗ anchor: ${matches} match(es) in ${FILE} — need exactly 1, NOT injecting."
  echo "  A 0-match anchor injects nothing and the run goes green for the wrong reason;"
  echo "  a 2+ match anchor edits more than you named. Both happened on 2026-08-10."
  exit 1
fi
echo "✓ anchor:   1 match in ${FILE}"

# --- 2. snapshot ------------------------------------------------------------------------
cp "$FILE" "$SNAP"
SNAPPED=1
before=$(hash_of "$SNAP")
echo "✓ snapshot: ${before}"

# --- 3. inject, and prove the file changed ---------------------------------------------
python3 - "$FILE" "$OLD" "$NEW" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text().replace(sys.argv[2], sys.argv[3], 1))
PY
after=$(hash_of "$FILE")
if [ "$after" = "$before" ]; then
  echo "✗ injected: file is UNCHANGED (${after}) — --old and --new are the same text."
  exit 1
fi
echo "✓ injected: file changed → ${after}"

# --- 4. the command must go RED ---------------------------------------------------------
set +e
out=$("$@" 2>&1); rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo "✗ red:      command exited 0 WITH the defect injected — the check does not catch it."
  echo "  A break-test that will not go red is a bug in the check, not a clean tree (C18)."
  printf '%s\n' "$out" | tail -15 | sed 's/^/            /'
  exit 1
fi
echo "✓ red:      command exited ${rc} with the defect injected"

# --- 5. restore, and prove it is byte-identical ----------------------------------------
cp "$SNAP" "$FILE"
restored=$(hash_of "$FILE")
if [ "$restored" != "$before" ]; then
  echo "✗ restored: ${restored} != snapshot ${before} — the file did NOT come back clean."
  exit 1
fi
echo "✓ restored: byte-identical to ${before}"

# --- 6. and green again -----------------------------------------------------------------
set +e
out=$("$@" 2>&1); rc=$?
set -e
if [ "$rc" -ne 0 ]; then
  echo "✗ green:    command exited ${rc} after restore — something else is broken."
  printf '%s\n' "$out" | tail -15 | sed 's/^/            /'
  exit 1
fi
echo "✓ green:    command exited 0 after restore"
echo "break-test: PASS — the check catches this defect, and the tree is clean."
