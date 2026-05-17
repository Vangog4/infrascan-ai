#!/usr/bin/env bash
# Autonomous overnight agent loop — "Ralph Loop" pattern.
#
# Usage:
#   ./loop_orchestrator.sh "task description"  [max_iter] [timeout_mins]
#   ./loop_orchestrator.sh --file task.md      [max_iter] [timeout_mins]
#
# The loop:
#   1. Runs claude --dangerously-skip-permissions in headless mode with the task
#   2. After each round checks health (pytest + stack)
#   3. Feeds test/stack failures back to claude as additional context
#   4. Stops when: all checks pass, budget exhausted, or timeout
#
# Examples:
#   ./loop_orchestrator.sh "Покрой функции в bot/src/ тестами до 90%" 30 240
#   ./loop_orchestrator.sh --file /tmp/task.md

set -euo pipefail

REPO_ROOT="/root/infrascan-ai"
LOG_DIR="$REPO_ROOT/bot/logseq/journals"
RUN_LOG="/tmp/loop_$(date +%Y%m%d_%H%M%S).log"

# ── Parse args ───────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--file" ]]; then
    TASK_FILE="${2:-}"
    [[ -f "$TASK_FILE" ]] || { echo "❌ Файл не найден: $TASK_FILE"; exit 1; }
    BASE_PROMPT="$(cat "$TASK_FILE")"
    shift 2
else
    BASE_PROMPT="${1:-}"
    [[ -n "$BASE_PROMPT" ]] || { echo "Usage: $0 \"task\" [max_iter] [timeout_mins]"; exit 1; }
    shift
fi

MAX_ITER="${1:-50}"
TIMEOUT_MINS="${2:-180}"
TIMEOUT_SECS=$(( TIMEOUT_MINS * 60 ))

# ── Helpers ──────────────────────────────────────────────────────────────────
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$RUN_LOG"; }

health_check() {
    local errors=""
    # Tests
    if ! (cd "$REPO_ROOT/bot" && uv run pytest tests/ -q --tb=line -x 2>&1); then
        errors+="pytest failed\n"
    fi
    # Stack containers
    for c in infrascan-ai_db infrascan-ai_web infrascan-ai_bot; do
        STATUS=$(podman inspect "$c" --format '{{.State.Status}}' 2>/dev/null || echo "missing")
        [[ "$STATUS" == "running" ]] || errors+="container $c is $STATUS\n"
    done
    echo -e "$errors"
}

# ── Main loop ────────────────────────────────────────────────────────────────
START=$(date +%s)
ITER=0
PROMPT="$BASE_PROMPT"
CONSECUTIVE_FAIL=0

log "🚀 Loop orchestrator запущен"
log "   Задача: ${PROMPT:0:80}…"
log "   Бюджет: $MAX_ITER итераций / ${TIMEOUT_MINS} мин"
log "   Лог: $RUN_LOG"
echo ""

while [[ $ITER -lt $MAX_ITER ]]; do
    ELAPSED=$(( $(date +%s) - START ))
    if [[ $ELAPSED -gt $TIMEOUT_SECS ]]; then
        log "⏰ Timeout: ${TIMEOUT_MINS} мин исчерпано на итерации $ITER"
        break
    fi

    ITER=$(( ITER + 1 ))
    log "━━━ Итерация $ITER/$MAX_ITER (прошло $(( ELAPSED/60 )) мин) ━━━"

    # Run claude headless
    CLAUDE_OUT=$(
        cd "$REPO_ROOT" && \
        claude --dangerously-skip-permissions -p "$PROMPT" 2>&1
    ) || true

    echo "$CLAUDE_OUT" >> "$RUN_LOG"
    log "Claude завершил итерацию $ITER"

    # Health check
    ERRORS=$(health_check)

    if [[ -z "$ERRORS" ]]; then
        CONSECUTIVE_FAIL=0
        log "✅ Проверки прошли на итерации $ITER"

        # Check if claude signaled completion
        if echo "$CLAUDE_OUT" | grep -qiE "✅ готово|задача выполнена|all tests pass|DONE|ЗАВЕРШЕНО|completed"; then
            log "🎉 Задача завершена! Итераций: $ITER, время: $(( ELAPSED/60 )) мин"
            break
        fi

        # Continue with base prompt
        PROMPT="$BASE_PROMPT"
    else
        CONSECUTIVE_FAIL=$(( CONSECUTIVE_FAIL + 1 ))
        log "❌ Проверки не прошли (подряд: $CONSECUTIVE_FAIL)"
        log "   Ошибки: $(echo -e "$ERRORS" | tr '\n' ' ')"

        # Feed errors back to claude
        PROMPT="$(printf '%s\n\n--- Проверки после итерации %d ---\n%s\nИсправь эти проблемы и продолжай.' \
            "$BASE_PROMPT" "$ITER" "$ERRORS")"

        if [[ $CONSECUTIVE_FAIL -ge 5 ]]; then
            log "🚫 5 подряд неудач — принудительное завершение (застрял)"
            break
        fi
    fi

    sleep 3
done

# Write summary to journal
TODAY=$(date +%Y_%m_%d)
JOURNAL="$LOG_DIR/${TODAY}.md"
SUMMARY="
## Loop Orchestrator — $(date +%H:%M)
- Задача: ${BASE_PROMPT:0:100}…
- Итераций: $ITER / $MAX_ITER
- Время: $(( ($(date +%s) - START) / 60 )) мин
- Лог: $RUN_LOG
"
echo "$SUMMARY" >> "$JOURNAL"
log "📝 Журнал обновлён: $JOURNAL"
log "🏁 Loop завершён. Итого итераций: $ITER"
