#!/usr/bin/env bash
# Behavioral regression for per-instance release selection. This intentionally tests
# pointer mechanics without root-only store creation so it runs in CI and locally.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TEST_BASE=$(mktemp -d "${TMPDIR:-/tmp}/release-selectors.XXXXXX")
cleanup() { rm -rf "$TEST_BASE"; }
trap cleanup EXIT INT TERM

# shellcheck source=../deploy/release-lib.sh
source "$ROOT/deploy/release-lib.sh"

# mktemp roots begin private. Publishing must add read/traversal for the systemd service
# user while retaining immutability, and must reject a symlink in place of an artifact.
private_dir="$TEST_BASE/private-published"
mkdir "$private_dir"
chmod 0500 "$private_dir"
release_publish_dir "$private_dir"
[ "$(stat -c '%a' "$private_dir")" = "555" ]
ln -s "$private_dir" "$TEST_BASE/published-link"
if release_publish_dir "$TEST_BASE/published-link" >/dev/null 2>&1; then
  echo "symlink was accepted as a published directory" >&2
  exit 1
fi

mkdir -p "$TEST_BASE/releases" "$TEST_BASE/selectors/nora" "$TEST_BASE/selectors/emily"
for revision in aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb; do
  mkdir "$TEST_BASE/releases/$revision"
  touch "$TEST_BASE/releases/$revision/.complete"
done
release_a="$TEST_BASE/releases/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
release_b="$TEST_BASE/releases/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

release_activate "$TEST_BASE/selectors/nora" "$release_a"
release_activate "$TEST_BASE/selectors/emily" "$release_a"

# Canary: only Nora moves.
release_activate "$TEST_BASE/selectors/nora" "$release_b"
[ "$(readlink -f "$TEST_BASE/selectors/nora/current")" = "$release_b" ]
[ "$(readlink -f "$TEST_BASE/selectors/emily/current")" = "$release_a" ]

# Promotion: Emily selects the exact release Nora already tested.
release_activate "$TEST_BASE/selectors/emily" \
  "$(readlink -f "$TEST_BASE/selectors/nora/current")"
[ "$(readlink -f "$TEST_BASE/selectors/emily/current")" = "$release_b" ]

# Rollback stays scoped to Emily and returns her to A without moving Nora.
release_rollback "$TEST_BASE/selectors/emily" >/dev/null
[ "$(readlink -f "$TEST_BASE/selectors/emily/current")" = "$release_a" ]
[ "$(readlink -f "$TEST_BASE/selectors/nora/current")" = "$release_b" ]

# An incomplete artifact must never become current.
mkdir "$TEST_BASE/releases/incomplete"
if release_activate "$TEST_BASE/selectors/nora" "$TEST_BASE/releases/incomplete" \
   >/dev/null 2>&1; then
  echo "incomplete release was selectable" >&2
  exit 1
fi

echo "release behavior ok: published roots traversable; canary isolated; exact promotion; scoped rollback; incomplete rejected"
