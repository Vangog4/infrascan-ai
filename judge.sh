#!/usr/bin/env bash
# judge.sh — infrascan-ai validation before commit
# Exit 0 = passed | Exit 1 = failed
set -euo pipefail
cd "$(dirname "$0")"

LOG_DIR="artifacts"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/judge-${TIMESTAMP}.log"

PASS=0; FAIL=0; SKIP=0

log()   { echo "$@" | tee -a "$LOG_FILE"; }
ok()    { log "  [PASS] $1"; ((PASS++)) || true; }
fail()  { log "  [FAIL] $1"; ((FAIL++)) || true; }
skip()  { log "  [SKIP] $1"; ((SKIP++)) || true; }
sep()   { log ""; log "=== $* ==="; }

log "=================================================="
log "  infrascan-ai — Judge Run: $TIMESTAMP"
log "=================================================="

# ------------------------------------------------------------------
sep "1. Python syntax — bot/src/**"
PY_ERRORS=0
while IFS= read -r -d '' f; do
    python3 -m py_compile "$f" 2>>"$LOG_FILE" || { fail "syntax: $f"; ((PY_ERRORS++)) || true; }
done < <(find bot/src -name "*.py" -print0 2>/dev/null)
[[ $PY_ERRORS -eq 0 ]] && ok "All Python files compile clean"

# ------------------------------------------------------------------
sep "2. Ruff lint + format"
if command -v uvx &>/dev/null; then
    uvx ruff check bot/src/ --config bot/pyproject.toml --output-format concise >>"$LOG_FILE" 2>&1 \
        && ok "ruff lint" || fail "ruff lint issues found"
    uvx ruff format bot/src/ --config bot/pyproject.toml --check >>"$LOG_FILE" 2>&1 \
        && ok "ruff format" || fail "ruff format issues found"
else
    skip "uvx not found"
fi

# ------------------------------------------------------------------
sep "3. Odoo addons — Python syntax"
PY_ERRORS=0
while IFS= read -r -d '' f; do
    python3 -m py_compile "$f" 2>>"$LOG_FILE" || { fail "syntax: $f"; ((PY_ERRORS++)) || true; }
done < <(find addons -name "*.py" -print0 2>/dev/null)
[[ $PY_ERRORS -eq 0 ]] && ok "Odoo addons compile clean"

# ------------------------------------------------------------------
sep "4. Unit tests"
if python3 -m pytest --version &>/dev/null; then
    cd bot && uv run pytest tests/ -q --tb=short >>"../$LOG_FILE" 2>&1 \
        && ok "pytest passed" || fail "pytest failures"
    cd ..
else
    skip "pytest not available"
fi

# ------------------------------------------------------------------
sep "5. Container health"
if podman ps --filter name=infrascan-ai_bot --format "{{.Status}}" 2>/dev/null | grep -q "Up"; then
    ok "infrascan-ai_bot running"
else
    skip "infrascan-ai_bot not running"
fi
if podman ps --filter name=infrascan-ai_web --format "{{.Status}}" 2>/dev/null | grep -q "Up"; then
    curl -sf http://localhost:8069/web/health &>/dev/null \
        && ok "Odoo web responding" || fail "Odoo web not responding"
else
    skip "infrascan-ai_web not running"
fi

# ------------------------------------------------------------------
sep "Summary"
log "Passed: $PASS  Failed: $FAIL  Skipped: $SKIP"
log "Log: $LOG_FILE"
if [[ $FAIL -gt 0 ]]; then
    log "EXIT 1 — fix failures, then re-run"
    exit 1
else
    log "EXIT 0 — safe to commit"
    exit 0
fi
