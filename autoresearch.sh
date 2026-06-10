#!/usr/bin/env bash
set -euo pipefail

PASS=0
FAIL=0
TOTAL=0

check() {
    local name="$1"
    local cmd="$2"
    TOTAL=$((TOTAL + 1))
    if eval "$cmd" > /tmp/check_out.txt 2>&1; then
        echo "  [OK] $name"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $name"
        cat /tmp/check_out.txt | head -5 | sed 's/^/        /'
        FAIL=$((FAIL + 1))
    fi
}

echo "=== infrascan-ai Stack Health Check ==="
echo ""

echo "--- Containers ---"
check "infrascan-ai_db running"    "podman inspect infrascan-ai_db --format '{{.State.Status}}' | grep -q running"
check "infrascan-ai_web running"   "podman inspect infrascan-ai_web --format '{{.State.Status}}' | grep -q running"
check "infrascan-ai_redis running" "podman inspect infrascan-ai_redis --format '{{.State.Status}}' | grep -q running"
check "infrascan-ai_bot running"   "podman inspect infrascan-ai_bot --format '{{.State.Status}}' | grep -q running"

echo ""
echo "--- Odoo HTTP ---"
check "Odoo /web/health OK"        "curl -sf --max-time 10 http://localhost:8069/web/health | grep -qE 'ok|pass'"
check "Odoo /web/login reachable"  "curl -sf --max-time 10 http://localhost:8069/web/login | grep -q Odoo"

echo ""
echo "--- Odoo XML-RPC (MCP odoo-infrascan) ---"
check "Odoo version RPC" "python3 -c \"
import xmlrpc.client
c = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common')
v = c.version()
print('version:', v['server_version'])
\""

echo ""
echo "--- Bot source syntax ---"
check "bot config parseable"  "cd /root/infrascan/backend/bot && uv run python -c 'import src.config'"
check "bot handlers importable" "cd /root/infrascan/backend/bot && uv run python -c 'import src.bot'"

echo ""
echo "--- Bot unit tests ---"
check "pytest (unit only)" "cd /root/infrascan/backend/bot && uv run pytest tests/ -x -q --ignore=tests/test_odoo.py 2>&1 | tail -3"

echo ""
echo "--- Redis ---"
check "Redis PING" "podman exec infrascan-ai_redis redis-cli ping | grep -q PONG"

echo ""
echo "=== Results: $PASS/$TOTAL passed, $FAIL failed ==="
SCORE=$(echo "scale=0; $PASS * 100 / $TOTAL" | bc)
echo "METRIC health_score=$SCORE"
echo "METRIC checks_passed=$PASS"
echo "METRIC checks_failed=$FAIL"
