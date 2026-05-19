#!/usr/bin/env bash
# Gemini subagent — запускает Gemini CLI как подчинённого агента.
#
# Режимы:
#   review                  — code review git diff (текущие изменения)
#   analyze <файл|dir>      — глубокий анализ файла или директории (2M контекст)
#   research "<вопрос>"     — веб-исследование (Gemini имеет доступ в интернет)
#   health                  — диагностика стека через autoresearch
#   redteam                 — adversarial review: ищет уязвимости как атакующий
#   retrospective           — ночной ретроспективный цикл за сессию
#   route "<задача>"        — запросить решение Agent Router (claude|gemini + режим)

set -euo pipefail

MODE="${1:-review}"
TASK="${2:-""}"
REPO_ROOT="/root/infrascan-ai"
GEMINI_BIN="${GEMINI_BIN:-gemini}"
MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"

_run_gemini() {
    local prompt="$1"
    echo "🤖 [Gemini] режим=$MODE модель=$MODEL"
    echo "---"
    "$GEMINI_BIN" --model "$MODEL" -p "$prompt" -y 2>/dev/null
}

case "$MODE" in
  review)
    DIFF=$(git -C "$REPO_ROOT" diff HEAD 2>/dev/null || echo "no changes")
    if [[ "$DIFF" == "no changes" || -z "$DIFF" ]]; then
        echo "ℹ️  Нет изменений для review"
        exit 0
    fi
    PROMPT="Ты старший инженер. Проверь этот git diff на предмет:
1. Багов и логических ошибок
2. Уязвимостей безопасности (injection, insecure deserialisation, hardcoded secrets)
3. Нарушений архитектуры (aiogram 3.x, Odoo XML-RPC, Redis FSM)
4. Утечек памяти или производительности
Будь конкретен: файл:строка → проблема → как исправить.

Diff (усечен до 50 000 символов):
${DIFF:0:50000}"
    _run_gemini "$PROMPT"
    ;;

  analyze)
    if [[ -f "$TASK" ]]; then
        # CRITICAL: Path traversal protection
        ABS_TASK=$(realpath -m "$TASK")
        if [[ "$ABS_TASK" != "$REPO_ROOT"* ]]; then
            echo "❌ Доступ к файлам вне репозитория запрещен: $TASK"
            exit 1
        fi
        CONTENT=$(cat "$ABS_TASK")
        # LLM context window limitation: truncate content
        PROMPT="Проанализируй этот файл проекта infrascan-ai (Odoo 19 + aiogram 3.x + Gemini Vision API).
Найди: баги, нарушения best practices, возможности оптимизации.
Файл: $TASK

Содержимое (усечено до 100 000 символов):
${CONTENT:0:100000}"
    elif [[ -d "$TASK" ]]; then
        # CRITICAL: Path traversal protection
        ABS_TASK=$(realpath -m "$TASK")
        if [[ "$ABS_TASK" != "$REPO_ROOT"* ]]; then
            echo "❌ Доступ к директориям вне репозитория запрещен: $TASK"
            exit 1
        fi
        # Calculate total lines for all relevant files
        TOTAL_LINES=$(find "$ABS_TASK" -type f \( -name "*.py" -o -name "*.yaml" \) -print0 | xargs -0 wc -l 2>/dev/null | tail -1 | awk '{print $1}')
        # LLM context window limitation: truncate structure
        PROMPT="Архитектурный анализ директории: $TASK
Структура (усечена до 30 файлов): $(find "$ABS_TASK" -name "*.py" -o -name "*.yaml" | head -30 | sed "s|$REPO_ROOT/||")
Общий объём: ${TOTAL_LINES:-0} строк (всего файлов)
Проект: infrascan-ai (Odoo 19 + aiogram 3.x + Gemini Vision). Что улучшить?"
    else
        echo "❌ Не найден: $TASK"
        exit 1
    fi
    _run_gemini "$PROMPT"
    ;;

  research)
    [[ -z "$TASK" ]] && { echo "Usage: $0 research \"вопрос\""; exit 1; }
    PROMPT="$TASK

Контекст: Telegram-бот на aiogram 3.x, Odoo 19 Community, анализ тепловизионных изображений через Gemini Vision API, VDS Ubuntu 24 (Podman, uv).
Отвечай кратко, конкретно, с примерами кода если применимо."
    _run_gemini "$PROMPT"
    ;;

  health)
    HEALTH=$(podman ps --format "table {{.Names}}\t{{.Status}}" 2>&1 || echo "podman недоступен")
    DISK=$(df -h / | tail -1)
    MEM=$(free -h | grep Mem)
    PROMPT="Диагностика VDS infrascan-ai ($(date '+%Y-%m-%d %H:%M')):

Контейнеры Podman:
$HEALTH

Диск: $DISK
Память: $MEM

Проект: Odoo 19 + aiogram 3.x бот + Gemini Vision.
Оцени состояние, найди риски, предложи конкретные действия."
    _run_gemini "$PROMPT"
    ;;

  redteam)
    DIFF=$(git -C "$REPO_ROOT" diff HEAD 2>/dev/null || echo "")
    FILES_CHANGED=$(git -C "$REPO_ROOT" diff HEAD --name-only 2>/dev/null || echo "")
    if [[ -z "$DIFF" ]]; then
        echo "ℹ️  Red Team: нет изменений для анализа"
        exit 0
    fi
    PROMPT="Ты опытный пентестер (Red Team). Проанализируй следующие изменения кода как потенциальный атакующий.
Ищи:
- Уязвимости для SQL injection, XSS, SSRF, Path Traversal
- Способы обхода аутентификации и авторизации
- Возможности для prompt injection в LLM-коде
- Небезопасную десериализацию или eval
- Утечки секретов или чувствительных данных
- Race conditions и TOCTOU

Измененные файлы: $FILES_CHANGED

Diff (усечен до 40 000 символов - ограничение контекста LLM):
${DIFF:0:40000}

Для каждой найденной уязвимости: CVE/CWE категория, severity (HIGH/MED/LOW), PoC эксплойт (1-2 строки), патч."
    _run_gemini "$PROMPT"
    ;;

  retrospective)
    TODAY=$(date '+%Y-%m-%d')
    JOURNAL_DIR="$REPO_ROOT/bot/logseq/journals"
    JOURNAL="$JOURNAL_DIR/$(date '+%Y_%m_%d').md"
    SESSION_LOG=$(cat "$JOURNAL" 2>/dev/null | tail -50 || echo "журнал не найден")
    DECISIONS=$(tail -100 "$REPO_ROOT/DECISIONS.md" 2>/dev/null || echo "нет")
    DIFF_STAT=$(git -C "$REPO_ROOT" diff --stat HEAD 2>/dev/null || echo "нет изменений")

    PROMPT="Ты архитектор проекта. Проведи ретроспективу сессии $TODAY.

Изменения:
$DIFF_STAT

Журнал сессии:
$SESSION_LOG

Последние решения из DECISIONS.md:
$DECISIONS

Задачи ретроспективы:
1. Что было сделано хорошо? (паттерны для повторения)
2. Что пошло не так? (паттерны для избегания)
3. Что нужно улучшить в архитектуре или процессе?
4. Следующие 3 конкретных шага (приоритет → файл → действие)

Будь конкретен. Результат войдёт в долгосрочную память проекта."
    _run_gemini "$PROMPT"
    ;;

  route)
    [[ -z "$TASK" ]] && { echo "Usage: $0 route \"описание задачи\""; exit 1; }
    python3 "$REPO_ROOT/hooks/router.py" "$TASK"
    ;;

  *)
    echo "Использование: $0 <режим> [аргумент]"
    echo ""
    echo "Режимы:"
    echo "  review                  — code review git diff"
    echo "  analyze <файл|dir>      — анализ файла/директории (2M токен контекст)"
    echo "  research \"вопрос\"       — веб-исследование"
    echo "  health                  — диагностика стека"
    echo "  redteam                 — adversarial security review"
    echo "  retrospective           — ретроспектива сессии"
    echo "  route \"задача\"          — решение Agent Router"
    exit 1
    ;;
esac
    — adversarial security review"
    echo "  retrospective           — ретроспектива сессии"
    echo "  route \"задача\"          — решение Agent Router"
    exit 1
    ;;
esac
