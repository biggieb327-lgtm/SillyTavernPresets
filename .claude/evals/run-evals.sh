#!/usr/bin/env bash
# Regression evals — each one pins a real incident from this project's history so it
# fails loudly if the mistake is ever reintroduced. See README.md for the discipline.
# Usage: bash .claude/evals/run-evals.sh   (exit 0 = all PASS, exit 1 = any FAIL)
set -u
cd "$(dirname "$0")/../.." || exit 1

pass=0; fail=0
ok()  { echo "PASS  $1"; pass=$((pass+1)); }
bad() { echo "FAIL  $1 — $2"; fail=$((fail+1)); }

BOT=telegram-companion-bot/bot.py

# Incident: streaming 400s arrived with an empty body and were undiagnosable (cost 3 fix
# rounds). The error body must be force-read before raise_for_status().
if grep -q '_ = resp.content' "$BOT"; then
  ok "streaming-error-body: response body force-read before raise_for_status"
else
  bad "streaming-error-body" "'_ = resp.content' missing from bot.py — streamed error bodies will be empty again"
fi

# Incident 2026-07-05: watchdog.sh restarted the whole healthy fleet forever because
# bot.py stopped writing the .alive heartbeat. The repeating job must stay registered.
if grep -q 'run_repeating(_touch_alive' "$BOT"; then
  ok "heartbeat-alive: _touch_alive repeating job registered"
else
  bad "heartbeat-alive" "run_repeating(_touch_alive...) missing — watchdog.sh will judge every bot frozen and restart the fleet forever"
fi

# Incident v2026-07-05.8: PTB's run_polling() silently overrides signal.signal() handlers;
# shutdown logging must be wired via post_shutdown, not a plain signal handler.
if grep -q '\.post_shutdown(_on_shutdown)' "$BOT"; then
  ok "graceful-shutdown: post_shutdown hook wired"
else
  bad "graceful-shutdown" ".post_shutdown(_on_shutdown) missing — SIGTERM diagnostics (phantom-killer triage) are lost"
fi

# Incident: bare 'python' in a launcher crash-looped bots with ModuleNotFoundError when
# the venv wasn't on PATH. The supervisor must invoke the venv interpreter explicitly.
if grep -q 'venv/bin/python' telegram-companion-bot/run-bot.sh; then
  ok "venv-explicit-python: run-bot.sh launches via venv/bin/python"
else
  bad "venv-explicit-python" "run-bot.sh no longer uses the explicit venv interpreter"
fi

# Incident v2026-07-05.5: missing tzdata made ZoneInfo silently fall back, then a
# tz-aware reminder vs naive now() TypeError killed bots at startup. Keep it pinned.
if grep -q '^tzdata' telegram-companion-bot/requirements.txt; then
  ok "tzdata-pinned: tzdata present in requirements.txt"
else
  bad "tzdata-pinned" "tzdata missing from requirements.txt — Termux has no system tz database"
fi

# Tokens must never land in the repo. The risk-guard hook blocks `git add .env`, but a
# token pasted into a card, a doc, or a committed backup file would slip past it — this
# repo is pulled from over raw public URLs, so a leaked token is instantly public.
# Patterns: Telegram bot token (digits:35-char secret), OpenAI-style sk- key, AWS key ID.
leaks=$(git grep -InE '[0-9]{8,10}:[A-Za-z0-9_-]{35}([^A-Za-z0-9_-]|$)|\bsk-[A-Za-z0-9]{32,}|\bAKIA[0-9A-Z]{16}\b' -- . ':!.claude/evals/run-evals.sh' 2>/dev/null || true)
if [ -z "$leaks" ]; then
  ok "secret-scan: no token-shaped strings in tracked files"
else
  bad "secret-scan" "possible credential committed: $(echo "$leaks" | head -3 | tr '\n' ' ')"
fi

# The delivery gate checks that BOT_VERSION and CHANGELOG.md both changed, but not that
# they AGREE. Convention: release entries are titled '## v<version>' and must match
# bot.py's BOT_VERSION; non-release entries (docs, ops tooling) use '## YYYY-MM-DD — ...'
# headings, which this check ignores.
bv=$(grep -m1 '^BOT_VERSION' "$BOT" | cut -d'"' -f2)
top=$(grep -m1 -oE '^## v[0-9][^ ]*' telegram-companion-bot/CHANGELOG.md | sed 's/^## v//')
if [ -n "$bv" ] && [ "$bv" = "$top" ]; then
  ok "version-changelog-sync: BOT_VERSION $bv matches newest release entry"
else
  bad "version-changelog-sync" "BOT_VERSION is '$bv' but newest '## v' changelog entry is '$top' — bumped one, forgot the other"
fi

# Character cards and instance seeds are hand-edited JSON; a syntax slip bricks a bot at load.
json_bad=""
for f in telegram-companion-bot/*.json; do
  python3 -m json.tool "$f" >/dev/null 2>&1 || json_bad="$json_bad $f"
done
if [ -z "$json_bad" ]; then
  ok "cards-valid-json: all telegram-companion-bot/*.json parse"
else
  bad "cards-valid-json" "invalid JSON:$json_bad"
fi

# bot.py must always compile — /update refuses to install a non-compiling bot.py, but
# catching it here is one deploy cycle cheaper.
if python3 -m py_compile "$BOT" 2>/dev/null; then
  ok "bot-compiles: python3 -m py_compile bot.py"
else
  bad "bot-compiles" "bot.py does not compile"
fi

# The operating machinery itself: hooks must parse, settings.json must be valid JSON.
hook_bad=""
for h in .claude/hooks/*.sh telegram-companion-bot/*.sh; do
  bash -n "$h" 2>/dev/null || hook_bad="$hook_bad $h"
done
if [ -z "$hook_bad" ]; then
  ok "shell-scripts-parse: all hook + bot shell scripts pass bash -n"
else
  bad "shell-scripts-parse" "syntax errors in:$hook_bad"
fi
if [ -f .claude/settings.json ]; then
  if python3 -m json.tool .claude/settings.json >/dev/null 2>&1; then
    ok "settings-valid-json: .claude/settings.json parses"
  else
    bad "settings-valid-json" ".claude/settings.json is invalid JSON — every hook silently dies"
  fi
fi

echo
echo "evals: ${pass} passed, ${fail} failed"
[ "$fail" -eq 0 ]
