#!/usr/bin/env bash
# PostToolUse hook — appends one line per tool call to a per-day evidence log.
# The delivery gate and the qa-engineer read this to check that verification actually ran.
# NB: the Python must be passed via -c, not a heredoc — a heredoc would occupy stdin and
# the hook's JSON payload (also on stdin) would never reach json.load().
set -u
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
mkdir -p .claude/.runtime

python3 -c '
import json, sys, datetime
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
tool = d.get("tool_name", "?")
ti = d.get("tool_input", {}) or {}
detail = ti.get("command") or ti.get("file_path") or ti.get("pattern") or ""
detail = " ".join(str(detail).split())[:160]
resp = d.get("tool_response", {})
ok = "ok"
if isinstance(resp, dict) and (resp.get("is_error") or resp.get("interrupted")):
    ok = "FAIL"
sid = (d.get("session_id") or "?")[:8]
print(f"{datetime.datetime.now():%H:%M:%S} | {sid} | {tool} | {ok} | {detail}")
' >> ".claude/.runtime/evidence-$(date +%Y%m%d).log" 2>/dev/null
exit 0
