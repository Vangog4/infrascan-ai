#!/bin/bash
# Полный бэкап infrascan-ai: БД + filestore
# Использование: ./backup.sh [папка для бэкапов]

set -euo pipefail

BACKUP_DIR="${1:-/root/backups/infrascan-ai}"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M")
BACKUP_FILE="$BACKUP_DIR/infrascan-ai_$TIMESTAMP.zip"

DB_CONTAINER="infrascan-ai_db"
WEB_CONTAINER="infrascan-ai_web"
DB_NAME="InfraScan_bd"
DB_USER="odoo"

mkdir -p "$BACKUP_DIR"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "[$(date +%T)] Дамп базы данных..."
podman exec "$DB_CONTAINER" pg_dump -U "$DB_USER" --no-owner "$DB_NAME" > "$TMPDIR/dump.sql"

echo "[$(date +%T)] Копирование filestore..."
podman cp "$WEB_CONTAINER:/var/lib/odoo/filestore" "$TMPDIR/filestore"

echo "[$(date +%T)] Создание манифеста..."
cat > "$TMPDIR/manifest.json" <<EOF
{
    "odoo_dump": "1",
    "db_name": "$DB_NAME",
    "backup_date": "$TIMESTAMP",
    "includes_filestore": true
}
EOF

echo "[$(date +%T)] Упаковка архива..."
(cd "$TMPDIR" && zip -r "$BACKUP_FILE" dump.sql manifest.json filestore/)

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date +%T)] ✅ Готово: $BACKUP_FILE ($SIZE)"

# Удаляем бэкапы старше 30 дней
find "$BACKUP_DIR" -name "infrascan-ai_*.zip" -mtime +30 -delete
