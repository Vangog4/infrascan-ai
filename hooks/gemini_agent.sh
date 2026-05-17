#!/usr/bin/env bash
# Запускает Gemini CLI как подчинённый агент в headless-режиме.
# Использование:
#   ./gemini_agent.sh "review" [файл или описание задачи]
#   ./gemini_agent.sh "research" "вопрос или тема"
#   ./gemini_agent.sh "analyze" [путь к файлу]
#
# Gemini имеет контекстное окно 2M токенов — используй для больших задач.

set -euo pipefail

MODE="${1:-review}"
TASK="${2:-""}"
REPO_ROOT="/root/infrascan-ai"

case "$MODE" in
  review)
    # Code review текущих изменений через Gemini
    DIFF=$(git -C "$REPO_ROOT" diff HEAD 2>/dev/null || echo "no changes")
    PROMPT="Ты старший инженер. Проверь этот git diff на предмет: багов, уязвимостей безопасности, нарушений архитектуры (aiogram 3.x, Odoo XML-RPC, Redis FSM). Будь краток. Diff:\n\n$DIFF"
    ;;
  analyze)
    # Анализ конкретного файла
    if [[ -f "$TASK" ]]; then
      CONTENT=$(cat "$TASK")
      PROMPT="Проанализируй этот файл проекта infrascan-ai (Odoo 19 + aiogram 3.x + Gemini Vision API). Найди проблемы и улучшения:\n\n$CONTENT"
    else
      echo "❌ Файл не найден: $TASK"
      exit 1
    fi
    ;;
  research)
    # Веб-исследование через Gemini (доступ к интернету)
    PROMPT="$TASK. Контекст проекта: Telegram-бот на aiogram 3.x, Odoo 19, тепловизионный анализ через Gemini Vision API. Отвечай кратко и конкретно."
    ;;
  health)
    # Анализ health check результатов
    HEALTH=$(bash "$REPO_ROOT/autoresearch.sh" 2>&1)
    PROMPT="Проанализируй результаты health check infrascan-ai и предложи конкретные улучшения:\n\n$HEALTH"
    ;;
  *)
    echo "Режимы: review | analyze <файл> | research <вопрос> | health"
    exit 1
    ;;
esac

echo "🤖 Gemini агент запущен (режим: $MODE)..."
echo "---"
gemini --model gemini-2.5-flash -p "$PROMPT" -y 2>/dev/null
