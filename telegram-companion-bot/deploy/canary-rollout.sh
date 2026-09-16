#!/usr/bin/env bash
# canary-rollout.sh — ADMIN_API canary deployment for the seven-bot fleet.
# Run on VPS as root. Stops at each phase boundary for verification.
#
# Usage:
#   bash canary-rollout.sh           # full run (interactive checkpoints)
#   bash canary-rollout.sh phase0    # run only phase 0 (deploy code)
#   bash canary-rollout.sh phase1    # generate token
#   bash canary-rollout.sh phase2    # canary cass
#   bash canary-rollout.sh phase3    # roll remaining six
#   bash canary-rollout.sh phase4    # wire /fleet on nora
set -euo pipefail

BASE=/opt/telegram-bots
REPO="$BASE/.repo/telegram-companion-bot"
INSTANCES=(nora bonnie cass emily priya jules marcus)
declare -A PORTS=( [nora]=8080 [bonnie]=8081 [cass]=8082 [emily]=8083 [priya]=8084 [jules]=8085 [marcus]=8086 )
TOKEN_FILE="$BASE/.admin-api-token"
LOG="/tmp/canary-$(date +%Y%m%d-%H%M%S).log"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[36m%s\033[0m\n' "$*"; }
hr()    { printf '%.0s-' {1..60}; echo; }

fail() { red "FAIL: $*"; exit 1; }
ok()   { green "OK: $*"; }

checkpoint() {
    hr
    blue "CHECKPOINT: $1"
    blue "Press Enter to continue, Ctrl-C to abort."
    read -r
}

# ---------------------------------------------------------------------------
# Phase 0.5: Permissions baseline (before any token exists)
# ---------------------------------------------------------------------------
phase0_5() {
    hr
    blue "=== PHASE 0.5: Permissions baseline ==="

    # Fix marcus dir (755 -> 700)
    if [ -d "$BASE/marcus" ]; then
        chmod 700 "$BASE/marcus"
        ok "marcus dir -> 700"
    fi

    # Baseline all instance dirs to 700
    for inst in "${INSTANCES[@]}"; do
        [ -d "$BASE/$inst" ] && chmod 700 "$BASE/$inst"
    done

    # Baseline all .env files to 600
    for inst in "${INSTANCES[@]}"; do
        [ -f "$BASE/$inst/.env" ] && chmod 600 "$BASE/$inst/.env"
    done

    # Verify
    echo
    blue "Permissions verification:"
    for inst in "${INSTANCES[@]}"; do
        if [ -d "$BASE/$inst" ]; then
            dir_mode=$(stat -c '%a' "$BASE/$inst")
            env_mode=$(stat -c '%a' "$BASE/$inst/.env" 2>/dev/null || echo "MISSING")
            env_owner=$(stat -c '%U' "$BASE/$inst/.env" 2>/dev/null || echo "?")
            if [ "$dir_mode" = "700" ] && [ "$env_mode" = "600" ]; then
                ok "$inst: dir=$dir_mode .env=$env_mode owner=$env_owner"
            else
                red "WARN $inst: dir=$dir_mode .env=$env_mode owner=$env_owner"
            fi
        fi
    done
}

# ---------------------------------------------------------------------------
# Phase 0: Deploy code (ADMIN_API stays OFF)
# ---------------------------------------------------------------------------
phase0() {
    hr
    blue "=== PHASE 0: Deploy code to fleet ==="

    # Pre-deploy secret gate: no .env tracked in git
    blue "Pre-deploy secret gate..."
    cd "$BASE/.repo"
    tracked_env=$(git ls-files | grep -iE '\.env$' | grep -v '.env.example' || true)
    if [ -n "$tracked_env" ]; then
        fail "Tracked .env file(s) found in git: $tracked_env"
    fi
    ok "No .env files tracked in git"

    gitignore_check=$(git check-ignore -v telegram-companion-bot/.env 2>&1 || true)
    if echo "$gitignore_check" | grep -q '.gitignore'; then
        ok ".env is gitignored: $gitignore_check"
    else
        red "WARN: .env may not be gitignored — verify manually"
    fi

    # Deploy canary instance first (nora)
    blue "Deploying to nora (canary)..."
    "$REPO/deploy/vps-sync.sh" nora 2>&1 | tee -a "$LOG"

    echo
    blue "Verify nora /audit shows BOT_VERSION >= 2026-09-15.2 in Telegram."
    blue "Then promote to roll the code to all seven instances."
    checkpoint "Ready to promote from nora?"

    # Promote
    blue "Promoting from nora..."
    "$REPO/deploy/vps-sync.sh" --promote nora 2>&1 | tee -a "$LOG"

    # Post-promote: verify all seven active
    echo
    blue "Service status:"
    all_active=true
    for inst in "${INSTANCES[@]}"; do
        status=$(systemctl is-active "bot@$inst" 2>/dev/null || echo "inactive")
        if [ "$status" = "active" ]; then
            ok "bot@$inst: $status"
        else
            red "bot@$inst: $status"
            all_active=false
        fi
    done
    $all_active || fail "Not all instances active after promote"

    # Post-promote secret gate
    blue "Post-promote secret gate..."
    cd "$BASE/.repo"
    token_in_log=$(git log -p -1 | grep -ci 'ADMIN_API_TOKEN' || true)
    if [ "$token_in_log" -gt 0 ]; then
        fail "ADMIN_API_TOKEN found in latest commit diff!"
    fi
    ok "No token in latest commit (0 matches)"

    ok "Phase 0 complete — code deployed, ADMIN_API still OFF everywhere"
}

# ---------------------------------------------------------------------------
# Phase 1: Generate shared token
# ---------------------------------------------------------------------------
phase1() {
    hr
    blue "=== PHASE 1: Generate shared token ==="

    TOKEN=$(openssl rand -hex 24)

    # Store offline only — 600 perms, root-owned, outside any git tree
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    chown root:root "$TOKEN_FILE"

    ok "Token generated and stored at $TOKEN_FILE (mode 600, root:root)"
    blue "Token length: ${#TOKEN} chars"
    blue "This token will be written to each instance's .env in phases 2-3."
    blue "It is NEVER committed to git."
}

# ---------------------------------------------------------------------------
# Phase 2: Canary — cass only
# ---------------------------------------------------------------------------
phase2() {
    hr
    blue "=== PHASE 2: Canary — enable ADMIN_API on cass ==="

    if [ ! -f "$TOKEN_FILE" ]; then
        fail "Token file not found at $TOKEN_FILE — run phase1 first"
    fi
    TOKEN=$(cat "$TOKEN_FILE")

    local inst=cass
    local port=${PORTS[$inst]}
    local env_file="$BASE/$inst/.env"

    # Remove any existing ADMIN_API lines, then append
    sed -i '/^ADMIN_API_ENABLED=/d; /^ADMIN_API_TOKEN=/d; /^ADMIN_API_PORT=/d; /^ADMIN_API_BIND=/d' "$env_file"
    cat >> "$env_file" <<EOF
ADMIN_API_ENABLED=1
ADMIN_API_TOKEN=$TOKEN
ADMIN_API_PORT=$port
ADMIN_API_BIND=127.0.0.1
EOF
    chmod 600 "$env_file"

    ok "cass .env updated (port $port, bind 127.0.0.1)"

    # Restart
    systemctl restart "bot@$inst"
    sleep 3

    # Containment assertions
    blue "Containment checks..."

    # Token not in process args
    token_in_args=$(pgrep -af bot.py | grep -c "$TOKEN" || true)
    if [ "$token_in_args" -gt 0 ]; then
        red "FAIL: Token visible in process args!"
    else
        ok "Token not in process args"
    fi

    # Token not in journal
    token_in_journal=$(journalctl -u "bot@$inst" --since "2 min ago" --no-pager 2>/dev/null | grep -c "$TOKEN" || true)
    if [ "$token_in_journal" -gt 0 ]; then
        red "FAIL: Token visible in journal!"
    else
        ok "Token not in journal"
    fi

    # .env perms
    env_mode=$(stat -c '%a' "$env_file")
    if [ "$env_mode" = "600" ]; then
        ok ".env mode is 600"
    else
        red "WARN: .env mode is $env_mode (expected 600)"
    fi

    # Check journal for listening line
    echo
    blue "Journal (last 2 min):"
    journalctl -u "bot@$inst" --since "2 min ago" --no-pager 2>/dev/null | grep -E 'admin-api|listening|bind.failed|STARTUP' || true

    # Health check
    echo
    blue "Health endpoint:"
    health=$(curl -sf "http://127.0.0.1:$port/admin/health" 2>/dev/null) && {
        echo "$health" | python3 -m json.tool 2>/dev/null || echo "$health"
        ok "Health endpoint responding"
    } || {
        red "FAIL: Health endpoint not responding on port $port"
    }

    # All 7 processes still alive
    echo
    blue "Process count:"
    proc_count=$(pgrep -af bot.py | grep -v grep | wc -l)
    echo "bot.py processes: $proc_count"
    [ "$proc_count" -ge 7 ] && ok "All instances running" || red "Expected 7, got $proc_count"

    hr
    blue "CANARY PASS CRITERIA:"
    blue "  1. Journal shows 'listening on 127.0.0.1:$port'"
    blue "  2. Health returns JSON with version"
    blue "  3. cass stays up; siblings still healthy"
    blue "  4. No token in args or journal"
    echo
    blue "If ANY check failed: set ADMIN_API_ENABLED=0 in cass/.env, restart, stop here."
    checkpoint "Cass canary passed? Ready to roll remaining six?"
}

# ---------------------------------------------------------------------------
# Phase 3: Roll remaining six
# ---------------------------------------------------------------------------
phase3() {
    hr
    blue "=== PHASE 3: Roll ADMIN_API to remaining six instances ==="

    if [ ! -f "$TOKEN_FILE" ]; then
        fail "Token file not found at $TOKEN_FILE — run phase1 first"
    fi
    TOKEN=$(cat "$TOKEN_FILE")

    local remaining=(nora bonnie emily priya jules marcus)

    for inst in "${remaining[@]}"; do
        local port=${PORTS[$inst]}
        local env_file="$BASE/$inst/.env"

        blue "--- $inst (port $port) ---"

        # Remove any existing ADMIN_API lines, then append
        sed -i '/^ADMIN_API_ENABLED=/d; /^ADMIN_API_TOKEN=/d; /^ADMIN_API_PORT=/d; /^ADMIN_API_BIND=/d' "$env_file"
        cat >> "$env_file" <<EOF
ADMIN_API_ENABLED=1
ADMIN_API_TOKEN=$TOKEN
ADMIN_API_PORT=$port
ADMIN_API_BIND=127.0.0.1
EOF
        chmod 600 "$env_file"

        systemctl restart "bot@$inst"
        sleep 3

        # Health check
        health=$(curl -sf "http://127.0.0.1:$port/admin/health" 2>/dev/null) && {
            version=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
            ok "$inst: UP, version=$version, port=$port"
        } || {
            red "FAIL: $inst health not responding on port $port"
        }

        # Journal listening line
        journalctl -u "bot@$inst" --since "2 min ago" --no-pager 2>/dev/null | grep -E 'listening' || red "$inst: no listening line found"

        # Containment: token not in args
        token_in_args=$(pgrep -af bot.py | grep -c "$TOKEN" || true)
        [ "$token_in_args" -eq 0 ] && ok "$inst: token not in args" || red "$inst: token in args!"

        echo
    done

    # Final process count
    proc_count=$(pgrep -af bot.py | grep -v grep | wc -l)
    echo "bot.py processes: $proc_count"
    [ "$proc_count" -ge 7 ] && ok "All 7 instances running" || red "Expected 7, got $proc_count"
}

# ---------------------------------------------------------------------------
# Phase 4: Wire /fleet on nora
# ---------------------------------------------------------------------------
phase4() {
    hr
    blue "=== PHASE 4: Wire /fleet on nora ==="

    local env_file="$BASE/nora/.env"

    # Remove existing FLEET_PEERS line, then append
    sed -i '/^FLEET_PEERS=/d' "$env_file"
    echo 'FLEET_PEERS=nora=8080,bonnie=8081,cass=8082,emily=8083,priya=8084,jules=8085,marcus=8086' >> "$env_file"
    chmod 600 "$env_file"

    ok "FLEET_PEERS set on nora"

    systemctl restart bot@nora
    sleep 3

    # Verify nora is back
    health=$(curl -sf "http://127.0.0.1:8080/admin/health" 2>/dev/null) && {
        ok "nora: health responding after restart"
    } || {
        red "FAIL: nora health not responding after restart"
    }

    blue "Now test /fleet in Telegram on nora — expect UP x7 with matching versions."
    blue "Also try: bash $REPO/fleet-status.sh"
}

# ---------------------------------------------------------------------------
# Phase 5: Post-run verification
# ---------------------------------------------------------------------------
phase5() {
    hr
    blue "=== PHASE 5: Post-run verification ==="

    if [ ! -f "$TOKEN_FILE" ]; then
        blue "Token file not found — skipping token-in-git checks"
    else
        TOKEN=$(cat "$TOKEN_FILE")

        # Token not in git tree
        cd "$BASE/.repo"
        token_in_tree=$(git grep -c "$TOKEN" 2>/dev/null | wc -l || true)
        if [ "$token_in_tree" -gt 0 ]; then
            red "FAIL: Token found in git working tree!"
        else
            ok "Token not in git working tree (0 matches)"
        fi

        # Token not in git history
        token_in_history=$(git log -p --all 2>/dev/null | grep -c "$TOKEN" || true)
        if [ "$token_in_history" -gt 0 ]; then
            red "FAIL: Token found in git history!"
        else
            ok "Token not in git history (0 matches)"
        fi
    fi

    # .env perms table
    echo
    blue "Permissions summary:"
    printf "%-10s %-6s %-6s %-6s\n" "INSTANCE" "DIR" ".ENV" "OWNER"
    for inst in "${INSTANCES[@]}"; do
        dir_mode=$(stat -c '%a' "$BASE/$inst" 2>/dev/null || echo "?")
        env_mode=$(stat -c '%a' "$BASE/$inst/.env" 2>/dev/null || echo "?")
        env_owner=$(stat -c '%U' "$BASE/$inst/.env" 2>/dev/null || echo "?")
        printf "%-10s %-6s %-6s %-6s\n" "$inst" "$dir_mode" "$env_mode" "$env_owner"
    done

    # Fleet health table
    echo
    blue "Fleet health (all seven):"
    for inst in "${INSTANCES[@]}"; do
        port=${PORTS[$inst]}
        health=$(curl -sf "http://127.0.0.1:$port/admin/health" 2>/dev/null) && {
            version=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
            uptime=$(echo "$health" | python3 -c "import sys,json; print(f\"{json.load(sys.stdin).get('uptime_hours',0):.1f}h\")" 2>/dev/null || echo "?")
            printf "  %-10s UP   %-16s %s\n" "$inst" "$version" "$uptime"
        } || {
            printf "  %-10s DOWN\n" "$inst"
        }
    done

    # Token file location
    echo
    if [ -f "$TOKEN_FILE" ]; then
        tf_mode=$(stat -c '%a %U:%G' "$TOKEN_FILE")
        ok "Token file: $TOKEN_FILE ($tf_mode)"
    fi

    hr
    green "=== ROLLBACK (per instance) ==="
    echo "  # In that bot's .env: remove or set ADMIN_API_ENABLED=0"
    echo "  # Then: systemctl restart bot@<name>"
    echo "  # If token was ever exposed: rotate (regenerate + update all 7 .env files)"
    hr

    ok "Canary rollout complete. Log at: $LOG"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    if [ "$(id -u)" -ne 0 ]; then
        fail "Run as root"
    fi

    local phase="${1:-all}"

    case "$phase" in
        phase0_5|phase0.5) phase0_5 ;;
        phase0)  phase0 ;;
        phase1)  phase1 ;;
        phase2)  phase2 ;;
        phase3)  phase3 ;;
        phase4)  phase4 ;;
        phase5)  phase5 ;;
        all)
            phase0_5
            checkpoint "Perms baseline done. Ready to deploy code?"
            phase0
            phase1
            phase2
            # phase2 has its own checkpoint before continuing
            phase3
            checkpoint "All seven enabled. Ready to wire /fleet on nora?"
            phase4
            phase5
            ;;
        *) echo "Usage: $0 [phase0.5|phase0|phase1|phase2|phase3|phase4|phase5|all]"; exit 1 ;;
    esac
}

main "$@"
