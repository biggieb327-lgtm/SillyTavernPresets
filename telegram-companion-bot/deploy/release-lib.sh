#!/usr/bin/env bash
# Shared release primitives for install-vps.sh and vps-sync.sh.
#
# A release is immutable code addressed by its full git commit. Its virtualenv is an
# immutable dependency layer addressed by the Python major/minor plus the SHA-256 of
# requirements.lock. Code-only releases therefore reuse the exact same environment.

release_secure_stores() {
  local base="$1" store owner mode
  for store in releases venvs selectors; do
    [ ! -L "$base/$store" ] || {
      echo "[release] FATAL: $base/$store must not be a symlink" >&2
      return 1
    }
    if [ ! -e "$base/$store" ]; then
      install -d -o root -g root -m 0755 "$base/$store"
    fi
    [ -d "$base/$store" ] || {
      echo "[release] FATAL: $base/$store is not a directory" >&2
      return 1
    }
    owner=$(stat -c '%u' "$base/$store")
    mode=$(stat -c '%a' "$base/$store")
    [ "$owner" = "0" ] && [ "$mode" = "755" ] || {
      echo "[release] FATAL: $base/$store must be root-owned mode 755 (got uid $owner mode $mode)" >&2
      return 1
    }
  done
}

release_secure_selector() {
  local base="$1" instance="$2" selector_dir owner mode
  [[ "$instance" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
    echo "[release] FATAL: invalid instance selector name: $instance" >&2
    return 1
  }
  release_secure_stores "$base" || return 1
  selector_dir="$base/selectors/$instance"
  [ ! -L "$selector_dir" ] || {
    echo "[release] FATAL: $selector_dir must not be a symlink" >&2
    return 1
  }
  if [ ! -e "$selector_dir" ]; then
    install -d -o root -g root -m 0755 "$selector_dir" || return 1
  fi
  [ -d "$selector_dir" ] || {
    echo "[release] FATAL: $selector_dir is not a directory" >&2
    return 1
  }
  owner=$(stat -c '%u' "$selector_dir")
  mode=$(stat -c '%a' "$selector_dir")
  [ "$owner" = "0" ] && [ "$mode" = "755" ] || {
    echo "[release] FATAL: $selector_dir must be root-owned mode 755 (got uid $owner mode $mode)" >&2
    return 1
  }
  PREPARED_SELECTOR_DIR="$selector_dir"
}

release_published_dir_ok() {
  local path="$1" owner mode
  [ ! -L "$path" ] && [ -d "$path" ] || return 1
  owner=$(stat -c '%u' "$path") || return 1
  mode=$(stat -c '%a' "$path") || return 1
  [ "$owner" = "$(id -u)" ] && [ "$mode" = "555" ]
}

release_publish_dir() {
  local path="$1" owner
  [ ! -L "$path" ] && [ -d "$path" ] || {
    echo "[release] FATAL: published path must be a real directory: $path" >&2
    return 1
  }
  owner=$(stat -c '%u' "$path") || return 1
  [ "$owner" = "$(id -u)" ] || {
    echo "[release] FATAL: refusing to publish a directory owned by uid $owner: $path" >&2
    return 1
  }
  chmod 0555 "$path" || return 1
  release_published_dir_ok "$path"
}

release_migrate_writable_state() {
  local base="$1" bot_user="$2" bot_group path destination
  bot_group=$(id -gn "$bot_user") || return 1
  install -d -o "$bot_user" -g "$bot_group" -m 0755 "$base/shared" || return 1

  # Callers stop the active fleet before the first migration. These are the only
  # writable artifacts bot.py historically derived from its code directory.
  for path in "$base"/group_*.jsonl; do
    [ -e "$path" ] || continue
    destination="$base/shared/$(basename "$path")"
    [ ! -e "$destination" ] || {
      echo "[release] FATAL: refusing to merge two group ledgers at $destination" >&2
      return 1
    }
    mv "$path" "$destination" || return 1
  done
  if [ -e "$base/group_claims" ]; then
    [ -d "$base/group_claims" ] && [ ! -e "$base/shared/group_claims" ] || {
      echo "[release] FATAL: group_claims migration target is ambiguous" >&2
      return 1
    }
    mv "$base/group_claims" "$base/shared/group_claims" || return 1
  fi
  [ -e "$base/world.txt" ] || install -o "$bot_user" -g "$bot_group" -m 0644 /dev/null "$base/world.txt" || return 1
  [ -e "$base/shared/update.lock" ] || install -o "$bot_user" -g "$bot_group" -m 0644 /dev/null "$base/shared/update.lock" || return 1
  chown -R "$bot_user:$bot_group" "$base/shared" || return 1
  chown "$bot_user:$bot_group" "$base/world.txt" || return 1
  chown root:root "$base" || return 1
  chmod 0755 "$base" || return 1
  release_secure_stores "$base"
}

release_validate() {
  local release_dir="$1" source_dir="$2" revision="$3" venv_key
  [ -f "$release_dir/.complete" ] || return 1
  [ "$(cat "$release_dir/REVISION")" = "$revision" ] || return 1
  cmp -s "$source_dir/bot.py" "$release_dir/bot.py" || return 1
  cmp -s "$source_dir/acoustic_ears.py" "$release_dir/acoustic_ears.py" || return 1
  cmp -s "$source_dir/requirements.lock" "$release_dir/requirements.lock" || return 1
  venv_key=$(cat "$release_dir/VENV_KEY") || return 1
  [ "$(readlink "$release_dir/venv")" = "../../venvs/$venv_key" ] || return 1
  release_published_dir_ok "$release_dir" || return 1
  release_published_dir_ok "$(realpath "$release_dir/venv")" || return 1
  [ -x "$release_dir/venv/bin/python" ] || return 1
}

release_prepare_venv() {
  local source_dir="$1" base="$2" python_bin="$3"
  local lock_hash python_version venv_key venv_dir temp_dir

  lock_hash=$(sha256sum "$source_dir/requirements.lock" | cut -d' ' -f1)
  python_version=$(
    "$python_bin" -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor}")'
  )
  [ "$python_version" = "312" ] || {
    echo "[release] FATAL: Python 3.12 required, got $python_version from $python_bin" >&2
    return 1
  }

  venv_key="py${python_version}-${lock_hash}"
  venv_dir="$base/venvs/$venv_key"
  if [ -f "$venv_dir/.complete" ]; then
    # Repair layers published by the first immutable-release implementation. mktemp -d
    # gave their roots mode 0700, and removing write bits left mode 0500: valid to root,
    # but impossible for the systemd service user to traverse.
    release_publish_dir "$venv_dir" || return 1
    "$venv_dir/bin/python" -m pip check >/dev/null
    PREPARED_VENV_KEY="$venv_key"
    return 0
  fi
  [ ! -e "$venv_dir" ] || {
    echo "[release] FATAL: incomplete dependency layer exists at $venv_dir" >&2
    return 1
  }

  mkdir -p "$base/venvs"
  temp_dir=$(mktemp -d "$base/venvs/.${venv_key}.tmp.XXXXXX")
  (
    set -euo pipefail
    trap 'rm -rf "$temp_dir"' EXIT
    echo "[release] building dependency layer $venv_key..."
    "$python_bin" -m venv "$temp_dir"
    "$temp_dir/bin/python" -m pip install --require-hashes --only-binary=:all: \
      -r "$source_dir/requirements.lock"
    "$temp_dir/bin/python" -m pip check
    printf '%s\n' "$lock_hash" > "$temp_dir/LOCK_SHA256"
    touch "$temp_dir/.complete"
    chmod -R a-w "$temp_dir"
    release_publish_dir "$temp_dir"
    mv "$temp_dir" "$venv_dir"
    trap - EXIT
  )
  PREPARED_VENV_KEY="$venv_key"
}

release_prepare() {
  local source_dir="$1" base="$2" revision="$3"
  local python_bin="${RELEASE_PYTHON:-/usr/bin/python3}"
  local release_dir temp_dir asset

  [ -f "$source_dir/requirements.lock" ] || {
    echo "[release] FATAL: requirements.lock is missing from $source_dir" >&2
    return 1
  }
  release_secure_stores "$base"
  release_prepare_venv "$source_dir" "$base" "$python_bin"

  release_dir="$base/releases/$revision"
  if [ -e "$release_dir" ]; then
    # The same repair is safe for an otherwise complete code release: it changes only
    # the root directory's traversal mode, not immutable release contents.
    release_publish_dir "$release_dir" || return 1
    release_validate "$release_dir" "$source_dir" "$revision" || {
      echo "[release] FATAL: release $release_dir is incomplete or does not match git" >&2
      return 1
    }
    PREPARED_RELEASE_DIR="$release_dir"
    return 0
  fi

  mkdir -p "$base/releases"
  temp_dir=$(mktemp -d "$base/releases/.${revision}.tmp.XXXXXX")
  (
    set -euo pipefail
    trap 'rm -rf "$temp_dir"' EXIT
    echo "[release] assembling immutable release $revision..."
    install -m 0444 "$source_dir/bot.py" "$temp_dir/bot.py"
    install -m 0444 "$source_dir/acoustic_ears.py" "$temp_dir/acoustic_ears.py"
    install -m 0444 "$source_dir/requirements.lock" "$temp_dir/requirements.lock"
    for asset in meme_templates fonts; do
      if [ -d "$source_dir/$asset" ]; then
        cp -a "$source_dir/$asset" "$temp_dir/$asset"
      fi
    done
    ln -s "../../venvs/$PREPARED_VENV_KEY" "$temp_dir/venv"
    ln -s "../../shared/update.lock" "$temp_dir/.update.lock"
    printf '%s\n' "$revision" > "$temp_dir/REVISION"
    printf '%s\n' "$PREPARED_VENV_KEY" > "$temp_dir/VENV_KEY"
    "$temp_dir/venv/bin/python" -m py_compile \
      "$temp_dir/bot.py" "$temp_dir/acoustic_ears.py"
    touch "$temp_dir/.complete"
    chmod -R a-w "$temp_dir"
    release_publish_dir "$temp_dir"
    mv "$temp_dir" "$release_dir"
    trap - EXIT
  )
  PREPARED_RELEASE_DIR="$release_dir"
}

release_activate() {
  local pointer_dir="$1" release_dir="$2"
  local current_target link_tmp

  [ -f "$release_dir/.complete" ] || {
    echo "[release] FATAL: cannot select incomplete release $release_dir" >&2
    return 1
  }
  current_target=$(realpath --relative-to="$pointer_dir" "$release_dir") || return 1
  if [ -L "$pointer_dir/current" ] && [ "$(readlink "$pointer_dir/current")" = "$current_target" ]; then
    return 0
  fi
  [ ! -e "$pointer_dir/current" ] || [ -L "$pointer_dir/current" ] || {
    echo "[release] FATAL: $pointer_dir/current exists and is not a symlink" >&2
    return 1
  }

  if [ -L "$pointer_dir/current" ]; then
    link_tmp="$pointer_dir/.previous.$$"
    ln -s "$(readlink "$pointer_dir/current")" "$link_tmp"
    mv -Tf "$link_tmp" "$pointer_dir/previous"
  fi
  link_tmp="$pointer_dir/.current.$$"
  ln -s "$current_target" "$link_tmp"
  mv -Tf "$link_tmp" "$pointer_dir/current"
}

release_rollback() {
  local pointer_dir="$1" current_target previous_target link_tmp
  [ -L "$pointer_dir/current" ] && [ -L "$pointer_dir/previous" ] || {
    echo "[release] FATAL: both $pointer_dir/current and $pointer_dir/previous must exist" >&2
    return 1
  }
  current_target=$(readlink "$pointer_dir/current")
  previous_target=$(readlink "$pointer_dir/previous")
  [ -f "$pointer_dir/$previous_target/.complete" ] || {
    echo "[release] FATAL: previous release is incomplete: $pointer_dir/$previous_target" >&2
    return 1
  }

  link_tmp="$pointer_dir/.current.$$"
  ln -s "$previous_target" "$link_tmp"
  mv -Tf "$link_tmp" "$pointer_dir/current"
  link_tmp="$pointer_dir/.previous.$$"
  ln -s "$current_target" "$link_tmp"
  mv -Tf "$link_tmp" "$pointer_dir/previous"
  echo "[release] current -> $previous_target (previous -> $current_target)"
}

release_select() {
  local base="$1" instance="$2" release_dir="$3"
  release_secure_selector "$base" "$instance" || return 1
  release_activate "$PREPARED_SELECTOR_DIR" "$release_dir"
}

release_selector_rollback() {
  local base="$1" instance="$2"
  release_secure_selector "$base" "$instance" || return 1
  release_rollback "$PREPARED_SELECTOR_DIR"
}

release_selected_dir() {
  local base="$1" instance="$2" selected
  release_secure_selector "$base" "$instance" || return 1
  [ -L "$PREPARED_SELECTOR_DIR/current" ] || {
    echo "[release] FATAL: $instance has no selected release" >&2
    return 1
  }
  selected=$(realpath "$PREPARED_SELECTOR_DIR/current") || return 1
  case "$selected" in
    "$base"/releases/*) ;;
    *) echo "[release] FATAL: $instance selector escapes the release store: $selected" >&2; return 1 ;;
  esac
  [ -f "$selected/.complete" ] || {
    echo "[release] FATAL: $instance selected release is incomplete: $selected" >&2
    return 1
  }
  SELECTED_RELEASE_DIR="$selected"
}
