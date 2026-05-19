#!/usr/bin/env bash
# PostToolUse hook: run pytest when Python bot files are edited or touched by Bash.
# Receives JSON on stdin with tool call details.
# Exits 2 to block the agent if tests fail — "Don't Stop Until Tests Pass".

INPUT=$(cat -)

FILE=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    tool = d.get('tool_name', '')
    if tool == 'Bash':
        # Extract first Python file path mentioned in the command
        cmd = ti.get('command', '')
        import re
        m = re.search(r'/bot/(?:src|tests)/[^\s]+\.py', cmd)
        print(m.group(0) if m else '')
    else:
        print(ti.get('file_path', ti.get('path', '')))
except Exception:
    print('')
" 2>/dev/null)

if echo "$FILE" | grep -qE "/bot/(src|tests)/.*\.py$"; then
    cd /root/infrascan-ai/bot

    echo "🔍 ruff check $FILE..."
    if ! uvx ruff check "$FILE" 2>&1; then
        echo "❌ ruff нашёл ошибки — исправь перед продолжением"
        exit 2
    fi

    echo "🧪 Запускаю все тесты в tests/ (после изменений в $(basename "$FILE"))..."
    if uv run pytest tests/ -q --tb=short -x 2>&1; then
        echo "✅ ruff + тесты прошли"
    else
        echo ""
        echo "❌ Тесты упали — исправь перед продолжением (hook exit 2)"
        exit 2
    fi
fi
