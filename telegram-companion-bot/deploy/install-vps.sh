#!/usr/bin/env bash
# Installs the bot fleet on a VPS (Ubuntu 24.04 recommended), supervised by systemd
# instead of the Termux tmux+run-bot.sh+watchdog.sh stack.
#
# Usage: sudo bash install-vps.sh
#
# Safe to re-run: skips steps that are already done (existing clone gets `git pull`
# instead of a fresh clone, existing .env files are left alone, only instances whose
# config actually changed get restarted).
set -euo pipefail

# SSH, not HTTPS (2026-07-28): the repo is private, so anonymous HTTPS clone/pull
# fails. Auth is a READ-ONLY deploy key on the VPS — see deploy/MIGRATION.md
# § "Private-repo deploys". Override for a fork or a public mirror.
REPO_URL="${REPO_URL:-git@github.com:biggieb327-lgtm/SillyTavernPresets.git}"
INSTALL_DIR="/opt/telegram-bots"
BOT_USER="bot"

# The deploy key, same default as vps-sync.sh. Switching REPO_URL to SSH on 2026-07-28
# was only half the private-repo change: without this, git falls back to root's default
# identity and fails with `git@github.com: Permission denied (publickey)` — which is
# exactly what a fresh `install-vps.sh` run did on 2026-07-29.
GIT_SSH_KEY="${STPRESETS_DEPLOY_KEY:-/root/.ssh/stpresets_ro}"
[ -f "$GIT_SSH_KEY" ] && export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY -o IdentitiesOnly=yes"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this with sudo: sudo bash install-vps.sh" >&2
  exit 1
fi

echo "== 1/8: system packages =="
# Always run this (apt-get install is a no-op on already-installed packages) rather
# than gating on `command -v python3` — a stock Ubuntu image ships python3 but NOT
# python3-venv/python3-pip, so that check would skip this block and `python3 -m venv`
# below would fail on a genuinely fresh box.
apt-get update -qq
apt-get install -y git python3 python3-venv python3-pip

echo "== 2/8: cloning / updating repo =="
# Keep the actual git checkout in a hidden subfolder so a re-run can `git pull` it
# (an earlier version flattened the clone directly into INSTALL_DIR and deleted .git
# in the process, which meant every "re-run" silently did a full re-clone instead).
REPO_CHECKOUT="$INSTALL_DIR/.repo"
mkdir -p "$INSTALL_DIR"
# `-c safe.directory=` on the call, not a global config change: step 4 chowns the whole
# tree to bot:bot, so root running git in it trips "detected dubious ownership" on every
# re-run. vps-sync.sh passes the same flag for the same reason.
if [ -d "$REPO_CHECKOUT/.git" ]; then
  git -c safe.directory="$REPO_CHECKOUT" -C "$REPO_CHECKOUT" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_CHECKOUT"
fi
# The repo's telegram-companion-bot/ subfolder is what actually gets deployed; sync
# the shared files into INSTALL_DIR's flat bot.py/venv/instances layout every run, so
# a re-run actually picks up upstream changes instead of only doing this once. Per-
# character seed folders (nora/, bonnie/, ...) are excluded here — they hold living,
# hand-editable content (atlas.txt, people.txt, ...), not something to keep overwriting
# from git on every re-run. Step 5 below seeds each one once, only when that instance
# is first created.
#
# A seed folder is matched by SHAPE — a directory holding people.txt — not by a
# hardcoded name list. The list version silently missed every character added after it
# was written, and the miss is destructive rather than cosmetic: an unlisted character's
# seed folder is named exactly like its instance directory, so the copy below lands
# on top of the live instance and reverts hand-edited context files to the repo's seed
# on every re-run. Shape-matching cannot fall behind the roster.
shopt -s dotglob
for item in "$REPO_CHECKOUT"/telegram-companion-bot/*; do
  if [ -d "$item" ] && [ -f "$item/people.txt" ]; then
    continue
  fi
  cp -r "$item" "$INSTALL_DIR"/
done
shopt -u dotglob

echo "== 3/8: python venv =="
if [ ! -x "$INSTALL_DIR/venv/bin/python" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
# Single source of truth for pip installs — never hand-list packages here (a past
# hand-typed list silently dropped tzdata and broke every timezone-dependent feature).
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

echo "== 4/8: bot system user =="
if ! id -u "$BOT_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$BOT_USER"
fi
chown -R "$BOT_USER:$BOT_USER" "$INSTALL_DIR"

echo "== 5/8: configure instances =="
echo "Enter each instance you want to run. Leave the name blank to stop adding instances."
CONFIGURED_INSTANCES=()
while true; do
  read -rp "Instance name (e.g. nora, bonnie) [blank to finish]: " INSTANCE_NAME
  [ -z "$INSTANCE_NAME" ] && break
  INSTANCE_DIR="$INSTALL_DIR/$INSTANCE_NAME"
  ENV_FILE="$INSTANCE_DIR/.env"
  mkdir -p "$INSTANCE_DIR"

  if [ -f "$ENV_FILE" ]; then
    echo "  $ENV_FILE already exists — leaving it as-is. Edit it by hand and re-run to restart the unit."
  else
    read -rsp "  Telegram bot token: " TG_TOKEN; echo
    read -rsp "  NanoGPT API key: " NANOGPT_KEY; echo
    read -rp "  Character card filename (e.g. ${INSTANCE_NAME}.json): " CARD_NAME
    CARD_NAME="${CARD_NAME:-$INSTANCE_NAME.json}"
    ADMIN_TOKEN="$(openssl rand -hex 24 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9')"

    # One-time seed of this character's context files (atlas.txt, people.txt, ...)
    # from the repo. Only happens here, on first creation — never re-copied on a
    # later re-run, so hand-edits made directly on the VPS don't get clobbered.
    SEED_DIR="$REPO_CHECKOUT/telegram-companion-bot/$INSTANCE_NAME"
    if [ -d "$SEED_DIR" ]; then
      cp -r "$SEED_DIR"/. "$INSTANCE_DIR"/
    fi

    cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    {
      echo ""
      echo "# --- Generated by install-vps.sh ---"
      echo "TELEGRAM_BOT_TOKEN=$TG_TOKEN"
      echo "NANOGPT_API_KEY=$NANOGPT_KEY"
      echo "CHARACTER_CARD=$CARD_NAME"
      echo "ADMIN_API_ENABLED=1"
      echo "ADMIN_API_TOKEN=$ADMIN_TOKEN"
      echo "ADMIN_API_BIND=127.0.0.1"
    } >> "$ENV_FILE"
    echo "  Wrote $ENV_FILE (admin API token generated — bind it to your Tailscale IP"
    echo "  by setting ADMIN_API_BIND once Tailscale is set up, see step 7 below)."
  fi

  CARD="$(grep -m1 '^CHARACTER_CARD=' "$ENV_FILE" | cut -d= -f2)"
  if [ -n "$CARD" ] && [ ! -f "$INSTANCE_DIR/$CARD" ]; then
    if [ -f "$INSTALL_DIR/$CARD" ]; then
      cp "$INSTALL_DIR/$CARD" "$INSTANCE_DIR/$CARD"
    else
      echo "  WARNING: character card '$CARD' not found in $INSTALL_DIR or $INSTANCE_DIR —" >&2
      echo "  the bot will fail to start until you place it there." >&2
    fi
  fi
  chown -R "$BOT_USER:$BOT_USER" "$INSTANCE_DIR"
  CONFIGURED_INSTANCES+=("$INSTANCE_NAME")
done

echo "== 6/8: systemd unit =="
cp "$INSTALL_DIR/deploy/bot@.service" /etc/systemd/system/bot@.service
systemctl daemon-reload

echo "== 7/8: enabling instances =="
for name in "${CONFIGURED_INSTANCES[@]}"; do
  systemctl enable --now "bot@${name}"
  echo "  bot@${name} enabled. Logs: journalctl -u bot@${name} -f"
done

echo "== 8/8: Tailscale =="
if ! command -v tailscale >/dev/null 2>&1; then
  cat <<'EOF'
Tailscale is not installed. It's a one-time, interactive step this script won't
automate (it needs its own device auth flow):

  curl -fsSL https://tailscale.com/install.sh | sh
  tailscale up

Once connected, find this host's tailnet IP with `tailscale ip -4`, then set
ADMIN_API_BIND=<that IP> in each instance's .env and restart it (systemctl restart
bot@<name>) so the admin API is actually reachable over the tailnet. It's left at
127.0.0.1 (loopback-only, unreachable) until you do this.
EOF
else
  echo "Tailscale already installed. Tailnet IP: $(tailscale ip -4 2>/dev/null || echo 'not connected — run: tailscale up')"
fi

echo ""
echo "Done. Configured instances: ${CONFIGURED_INSTANCES[*]:-(none)}"
