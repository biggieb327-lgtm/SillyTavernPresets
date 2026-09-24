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
# Runs async: the session starts while this installs (~2 s cold, ~0 s reused). Two things
# keep that race safe:
#   * PATH is exported FIRST, pointing at a stable symlink ($LINK). Until an install
#     finishes, the symlink does not exist and `python3` falls through to the default.
#   * Each install goes into its own lock-keyed directory; the symlink is flipped to it with
#     one rename only after every package is in. `python3` is never a half-built venv.
# Async output may not reach the session, so the outcome is also written to $STATUS.
#
# Never blocks the session: any failure writes one WARNING and exits 0, leaving the
# default python3 on PATH exactly as before.
set -u

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
echo '{"async": true, "asyncTimeout": 300000}'

LOCK=telegram-companion-bot/requirements.lock
PYTEST_PIN="pytest==8.4.2"   # keep in step with evals.yml "Install dependencies"
LINK="${HOME}/.venvs/sillytavernpresets-py312"     # what PATH points at
STATUS="${HOME}/.venvs/sillytavernpresets-py312.status"
mkdir -p "${HOME}/.venvs"

report() { echo "$1" | tee "$STATUS"; }
warn() { report "[session-deps] WARNING: $* — verify.sh will use the default python3 and go red on import/pytest"; exit 0; }

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"${LINK}\""
    echo "export PATH=\"${LINK}/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
  where="on PATH for this session"
else
  where="NOT on PATH (no CLAUDE_ENV_FILE) — prefix commands with PATH=${LINK}/bin:\$PATH"
fi

[ -f "$LOCK" ] || warn "$LOCK not found"
command -v uv >/dev/null 2>&1 || warn "uv not on PATH"

key=$(printf '%s %s' "$(sha256sum "$LOCK" | cut -d' ' -f1)" "$PYTEST_PIN" | sha256sum | cut -c1-16)
VENV="${LINK}-${key}"
STAMP="${VENV}/.complete"

if [ -x "${VENV}/bin/python" ] && [ -f "$STAMP" ]; then
  status="reused"
else
  rm -rf "$VENV"
  uv venv -q -p 3.12 "$VENV" >/dev/null 2>&1 || warn "uv could not create a 3.12 venv"
  log=$(VIRTUAL_ENV="$VENV" uv pip install -q --require-hashes --only-binary=:all: -r "$LOCK" 2>&1) \
    || warn "lock install failed: $(printf '%s' "$log" | tail -1)"
  log=$(VIRTUAL_ENV="$VENV" uv pip install -q "$PYTEST_PIN" 2>&1) \
    || warn "pytest install failed: $(printf '%s' "$log" | tail -1)"
  : > "$STAMP"
  status="installed"
fi

# A pre-async install left a real directory at $LINK; a rename cannot replace a directory.
[ -L "$LINK" ] || rm -rf "$LINK"
# Create-then-rename: `ln -sfn` unlinks before it links, leaving a moment with no $LINK.
ln -sfn "$VENV" "${LINK}.new" && mv -Tf "${LINK}.new" "$LINK" || warn "could not point $LINK at $VENV"
# Drop older lock-keyed venvs; the symlink now points at the only one in use.
for old in "${LINK}"-*; do [ "$old" = "$VENV" ] || rm -rf "$old"; done

report "[session-deps] $("${LINK}/bin/python" --version 2>&1) venv ${status} at ${VENV}, ${where}"
exit 0
