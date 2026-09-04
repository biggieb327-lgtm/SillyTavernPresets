#!/data/data/com.termux/files/usr/bin/bash
# fleet-status.sh — one command to answer "is everyone up, what version, any errors."
#
# Hits each instance's /admin/health endpoint and prints a summary table.
# Works on-phone now (localhost), over tailnet post-VPS (set FLEET_HOST).
#
# Requires ADMIN_API_ENABLED=1 on each instance. /admin/health is unauthenticated
# (trivial liveness ping), so no token needed for the basic check. Set ADMIN_API_TOKEN
# in the environment for the extended view (audit data via /admin/audit).
#
# Usage: bash fleet-status.sh
#        FLEET_HOST=100.x.y.z bash fleet-status.sh   # over tailnet

set -u

FLEET_HOST="${FLEET_HOST:-127.0.0.1}"
ADMIN_API_TOKEN="${ADMIN_API_TOKEN:-}"
TIMEOUT="${FLEET_TIMEOUT:-5}"

# Instance list mirrors the seven-bot VPS fleet. Port is ADMIN_API_PORT from each
# instance's .env — must be distinct on a shared host. Convention:
# nora=8080, bonnie=8081, cass=8082, emily=8083, priya=8084, jules=8085, marcus=8086.
# Override with FLEET_PORT_<NAME> if needed.
declare -A PORTS
PORTS=(
  [nora]=8080
  [bonnie]=8081
  [cass]=8082
  [emily]=8083
  [priya]=8084
  [jules]=8085
  [marcus]=8086
)

# Allow overriding individual ports via env, e.g. FLEET_PORT_NORA=9090
for name in "${!PORTS[@]}"; do
  upper=$(echo "$name" | tr '[:lower:]' '[:upper:]')
  env_port="FLEET_PORT_${upper}"
  if [ -n "${!env_port:-}" ]; then
    PORTS[$name]="${!env_port}"
  fi
done

printf "%-10s %-8s %-16s %-12s %s\n" "INSTANCE" "STATUS" "VERSION" "UPTIME" "ERRORS(1h)"
printf "%-10s %-8s %-16s %-12s %s\n" "--------" "------" "-------" "------" "----------"

for name in nora bonnie cass emily priya jules marcus; do
  port="${PORTS[$name]}"
  url="http://${FLEET_HOST}:${port}/admin/health"

  resp=$(curl -sf --max-time "$TIMEOUT" "$url" 2>/dev/null)
  if [ $? -ne 0 ]; then
    printf "%-10s %-8s %-16s %-12s %s\n" "$name" "DOWN" "-" "-" "-"
    continue
  fi

  version=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
  uptime=$(echo "$resp" | python3 -c "import sys,json; h=json.load(sys.stdin).get('uptime_hours',0); print(f'{h:.1f}h')" 2>/dev/null || echo "?")

  errors="-"
  if [ -n "$ADMIN_API_TOKEN" ]; then
    audit_url="http://${FLEET_HOST}:${port}/admin/audit"
    audit_resp=$(curl -sf --max-time "$TIMEOUT" -H "Authorization: Bearer $ADMIN_API_TOKEN" "$audit_url" 2>/dev/null)
    if [ $? -eq 0 ]; then
      errors=$(echo "$audit_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors_recent',d.get('errors_1h','?')))" 2>/dev/null || echo "?")
    fi
  fi

  printf "%-10s %-8s %-16s %-12s %s\n" "$name" "UP" "$version" "$uptime" "$errors"
done
