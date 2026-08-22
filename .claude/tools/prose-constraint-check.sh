#!/usr/bin/env bash
# prose-constraint-check.sh — reminds a session of the prose-only constraints
# (.claude/memory/constraints.md) relevant to the current diff.
#
# Six constraints have no mechanical guard — a hook, eval, or scanner catches
# the other 16, but these depend on someone actually reading them against the
# diff in front of them. This script doesn't do that reading for you; it just
# flags which of the six are worth doing it for, based on what the diff touches.
#
#   bash .claude/tools/prose-constraint-check.sh
#
# Reads `git diff --cached`; falls back to `git diff HEAD` when nothing is
# staged (so it's useful before AND after `git add`). Advisory only — exit 0
# always, never blocks anything.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 1

diff_text=$(git diff --cached 2>/dev/null)
if [ -z "$diff_text" ]; then
  diff_text=$(git diff HEAD 2>/dev/null)
fi

relevant=0
total=6

echo "prose-constraint-check: checked diff against $total prose-only constraints"

check() {  # check <id> <matched:0|1> <hit-message> <quiet-message>
  local id="$1" matched="$2" hit_msg="$3" quiet_msg="$4"
  if [ "$matched" -eq 1 ]; then
    printf '  %-3s RELEVANT — %s\n' "$id" "$hit_msg"
    relevant=$((relevant + 1))
  else
    printf '  %-3s quiet — %s\n' "$id" "$quiet_msg"
  fi
}

if [ -z "$diff_text" ]; then
  echo "  (no diff found: nothing staged and no changes against HEAD)"
fi

# C4 — Search for the bug's shape, not its remembered vocabulary
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+.*\b(grep|Grep)\b'; then m=1; fi
check "C4" "$m" \
  "diff adds grep/Grep calls; search for the mechanism/shape, not just the remembered vocabulary" \
  "no new grep/Grep calls"

# C6 — A migration invalidates assertions, not just docs
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+.*\b(Android|Termux|termux|phone|VPS|systemd|proot)\b'; then m=1; fi
check "C6" "$m" \
  "diff touches platform-specific strings; sweep tests and user-facing strings too, not only docs" \
  "no platform-specific changes"

# C9 — Verify a load-bearing hypothesis before shipping, not after
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+.*(getenv\([^)]*,\s*["'"'"'][^"'"'"']*["'"'"']\)|^[+-].*=\s*(True|False|[0-9]+)\s*$)'; then m=1; fi
if printf '%s\n' "$diff_text" | grep -qiE '^\+.*\bdef (handle_|_handle_)?[a-z0-9_]*_cmd\('; then m=1; fi
check "C9" "$m" \
  "diff changes a default or ships a new feature; list the load-bearing hypotheses and verify them before shipping, not after" \
  "no default changes or new feature entry points detected"

# C10 — An unexplained default is not an unintended one: read the registries first
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+.*os\.getenv\('; then m=1; fi
if printf '%s\n' "$diff_text" | grep -qE '^\+.*(_ENABLED|_FLAG|feature.?flag)'; then m=1; fi
check "C10" "$m" \
  "diff changes an os.getenv default or flips a feature flag; check the registries first (CLAUDE.md Known-deliberate, ROADMAP Rejected, AUDIT rejected, CHANGELOG)" \
  "no os.getenv default or feature-flag changes"

# C11 — A diagnostic sent into a group chat is an in-world event
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+.*\b(GROUP_[A-Z_]+|group_guard|_handle_group_message)\b'; then m=1; fi
if printf '%s\n' "$diff_text" | grep -qE '^\+.*chat_id\s*<\s*0'; then m=1; fi
check "C11" "$m" \
  "diff touches group-chat code; anything sent as plain text in a group is a permanent in-world event, not a private diagnostic" \
  "no group-chat code touched"

# C20 — A green test suite is not proof a reused pattern is safe for the new call site
m=0
if printf '%s\n' "$diff_text" | grep -qE '^\+\s*[A-Za-z_][A-Za-z0-9_]*_cmd\s*=\s*[A-Za-z_][A-Za-z0-9_]*\('; then m=1; fi
if printf '%s\n' "$diff_text" | grep -qiE '^\+.*=\s*[A-Za-z_][A-Za-z0-9_]*(factory|wrapper)[A-Za-z0-9_]*\('; then m=1; fi
check "C20" "$m" \
  "diff appears to reuse an existing factory/wrapper at a new call site; check capture semantics and monkeypatch assumptions before trusting a green suite" \
  "no reused factory/wrapper detected at a new call site"

echo "prose-constraint-check: $relevant constraints relevant to this diff"
exit 0
