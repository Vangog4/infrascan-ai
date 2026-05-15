#!/bin/bash
# Автозапись при завершении сессии Claude

BOT_DIR="/root/infrascan-ai/bot"
DATE=$(date +%Y_%m_%d)
JOURNAL="${BOT_DIR}/logseq/journals/${DATE}.md"
TIMESTAMP=$(date '+%H:%M')

# Git: добавить и закоммитить изменения
cd "$BOT_DIR" || exit 0
git add -A 2>/dev/null
CHANGED=$(git diff --cached --name-only 2>/dev/null)

if [ -n "$CHANGED" ]; then
    git commit -m "auto: сессия $(date '+%Y-%m-%d %H:%M')" 2>/dev/null
    FILES_MSG="Закоммичено: $(echo "$CHANGED" | tr '\n' ' ')"
else
    FILES_MSG="Изменений в git нет"
fi

# Журнал: дописать запись
mkdir -p "$(dirname "$JOURNAL")"
if [ ! -f "$JOURNAL" ]; then
    echo "# $(date '+%Y-%m-%d') — Журнал сессии" > "$JOURNAL"
    echo "" >> "$JOURNAL"
fi

{
    echo ""
    echo "## Автозапись ${TIMESTAMP} — сессия завершена"
    echo "- ${FILES_MSG}"
} >> "$JOURNAL"
