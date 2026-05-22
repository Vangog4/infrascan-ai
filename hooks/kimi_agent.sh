#!/usr/bin/env bash
# kimi_agent.sh — Kimi 2.5 subagent (Moonshot AI, 128K context)
#
# Режимы:
#   analyze <путь>     — полный анализ файла/директории (весь репо за раз)
#   bulk    <файл>     — большие логи / дампы данных
#   draft   "задача"   — черновик / брейншторм (быстро и дёшево)
#   migrate <путь>     — анализ схемы БД, предложение ALTER TABLE
#   compare "вопрос"   — сравнение двух подходов A/B
#   council "вопрос"   — второе мнение по архитектуре

set -euo pipefail

MODE="${1:-}"
ARG="${2:-}"
REPO_ROOT="/root/infrascan-ai"
KIMI_SCRIPT="$REPO_ROOT/hooks/kimi_client.py"

if [[ -z "$MODE" ]]; then
    echo "Использование: $0 <mode> [аргумент]"
    echo ""
    echo "Режимы:"
    echo "  analyze <путь>     — полный анализ файла/директории (128K ctx)"
    echo "  bulk    <файл>     — анализ больших логов / дампов"
    echo "  draft   \"задача\"   — черновой брейншторм (дешёво)"
    echo "  migrate <путь>     — анализ схемы БД → предложение миграций"
    echo "  compare \"вопрос\"   — сравнение двух подходов A/B"
    echo "  council \"вопрос\"   — второе мнение по архитектуре"
    exit 1
fi

# Load MOONSHOT_API_KEY from .env if not set
if [[ -z "${MOONSHOT_API_KEY:-}" ]]; then
    ENV_FILE="$REPO_ROOT/.env"
    if [[ -f "$ENV_FILE" ]]; then
        MOONSHOT_API_KEY=$(grep -E '^MOONSHOT_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" | head -1)
        export MOONSHOT_API_KEY
    fi
fi

# Also check global env file
if [[ -z "${MOONSHOT_API_KEY:-}" && -f "/root/.env" ]]; then
    MOONSHOT_API_KEY=$(grep -E '^MOONSHOT_API_KEY=' /root/.env | cut -d= -f2- | tr -d '"' | tr -d "'" | head -1)
    export MOONSHOT_API_KEY
fi

# Security: validate mode against allowlist (prevents injection via $MODE)
case "$MODE" in
  analyze|bulk|draft|migrate|compare|council)
    ;;
  *)
    echo "❌ Неизвестный режим: $MODE"
    exit 1
    ;;
esac

# Dispatch to Python client
if [[ -n "$ARG" ]]; then
    python3 "$KIMI_SCRIPT" "$MODE" "$ARG"
else
    python3 "$KIMI_SCRIPT" "$MODE"
fi
