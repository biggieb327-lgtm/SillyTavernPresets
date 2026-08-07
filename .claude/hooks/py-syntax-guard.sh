#!/usr/bin/env bash
# PostToolUse hook — a Python file this turn edited no longer parses.
#
# Three times on 2026-08-02 an Edit to sweep.py put docstring prose where the docstring
# had already closed, and the module stopped importing. Each time it surfaced one to
# three tool calls later as a confusing downstream failure (a scanner "crashing", a
# corpus reporting 35 deviations) rather than as the edit that caused it. C7, occurrences
# 3-5. This says so at the moment of the edit instead.
#
# Deliberately syntax ONLY. The obvious-looking version of this hook runs a linter and
# formatter over the edited file; measured against this repo on 2026-08-02, `ruff format`
# would have rewritten 5512 lines of bot.py — a file that deploys as a single artifact
# with bot.py.bak as its only rollback — and `ruff check --fix` would auto-apply 34
# changes to a file with 73 standing violations, on every edit. Style is not this hook's
# business. "Does it still parse" is, costs milliseconds, and needs no dependency.
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

payload=$(cat)
paths=$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get("tool_input") or {}
out = []
for key in ("file_path", "notebook_path"):
    if ti.get(key):
        out.append(ti[key])
for e in (ti.get("edits") or []):          # MultiEdit-style payloads
    if isinstance(e, dict) and e.get("file_path"):
        out.append(e["file_path"])
print("\n".join(out))
' 2>/dev/null) || exit 0

broken=""
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in *.py) ;; *) continue ;; esac
  [ -f "$f" ] || continue
  if ! err=$(python3 -c '
import ast, sys
src = open(sys.argv[1], encoding="utf-8").read()
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"line {e.lineno}: {e.msg}")
    sys.exit(1)
' "$f" 2>&1); then
    broken="${broken}- ${f} — ${err}\n"
  fi
done <<< "$paths"

if [ -n "$broken" ]; then
  printf '[py-syntax-guard] the edit left Python that does not parse:\n%b Fix it now — the next tool call will fail somewhere else and read like a different bug.\n' "$broken" >&2
  exit 2
fi
exit 0
