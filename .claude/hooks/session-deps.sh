#!/usr/bin/env bash
# SessionStart hook — cloud sessions only: give the session a Python 3.12 environment with
# requirements.lock + pytest installed, and put it first on PATH.
#
# Why: the cloud container's default python3 is 3.11 with none of the bot's packages, so
# `verify.sh` goes red on `import bot.py` (no PIL) and `pytest` (not installed) before it
# has checked anything. Sessions then either skip verification (2026-09-22: main red for 6
# days, verified with run-evals.sh alone) or rebuild the venv by hand (2026-09-24).
#
# Mirrors CI (.github/workflows/evals.yml): the same hashed lock, binary wheels only, the
# same pytest pin. The venv lives outside the repo and is keyed on the lock's sha256, so a
# resumed or cached container reuses it and a lock change rebuilds it.
#
# Never blocks the session: any failure prints one warning line and exits 0, leaving the
# default python3 on PATH exactly as before.
set -u

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

LOCK=telegram-companion-bot/requirements.lock
PYTEST_PIN="pytest==8.4.2"   # keep in step with evals.yml "Install dependencies"
VENV="${HOME}/.venvs/sillytavernpresets-py312"
STAMP="${VENV}/.lock-sha256"

warn() { echo "[session-deps] WARNING: $* — verify.sh will use the default python3 and go red on import/pytest"; exit 0; }

[ -f "$LOCK" ] || warn "$LOCK not found"
command -v uv >/dev/null 2>&1 || warn "uv not on PATH"

want=$(printf '%s %s' "$(sha256sum "$LOCK" | cut -d' ' -f1)" "$PYTEST_PIN")

if [ -x "${VENV}/bin/python" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$want" ]; then
  status="reused"
else
  rm -rf "$VENV"
  uv venv -q -p 3.12 "$VENV" >/dev/null 2>&1 || warn "uv could not create a 3.12 venv"
  log=$(VIRTUAL_ENV="$VENV" uv pip install -q --require-hashes --only-binary=:all: -r "$LOCK" 2>&1) \
    || warn "lock install failed: $(printf '%s' "$log" | tail -1)"
  log=$(VIRTUAL_ENV="$VENV" uv pip install -q "$PYTEST_PIN" 2>&1) \
    || warn "pytest install failed: $(printf '%s' "$log" | tail -1)"
  printf '%s' "$want" > "$STAMP"
  status="installed"
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"${VENV}\""
    echo "export PATH=\"${VENV}/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
  where="on PATH for this session"
else
  where="NOT on PATH (no CLAUDE_ENV_FILE) — prefix commands with PATH=${VENV}/bin:\$PATH"
fi

echo "[session-deps] $("${VENV}/bin/python" --version 2>&1) venv ${status} at ${VENV}, ${where}"
exit 0
