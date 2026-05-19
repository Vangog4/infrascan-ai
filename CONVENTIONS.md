# CONVENTIONS.md — Стандарты разработки infrascan-ai

## Режимы работы агента (обязательно объявлять)
- `[REVIEW MODE]` — только анализ, без изменений кода
- `[DESIGN MODE]` — архитектура и спецификации, без кода
- `[BUILD MODE]` — полная реализация
- `[PATCH MODE]` — только diff/search-replace

## Python (bot/)
- Фреймворк: aiogram 3.x, async/await везде
- Зависимости: только через `uv` (`uv add`, `uv run`)
- Форматирование: ruff (через `uv run ruff format`)
- Типы: type hints обязательны для публичных функций
- Тесты: pytest + pytest-asyncio, `uv run pytest tests/ -v`

## Odoo (addons/)
- Префикс полей: `x_` для простых, `infrascan_` для модульных
- Версия модуля: обновлять в `__manifest__.py` при каждом изменении
- Миграция: всегда через `podman run --rm ... odoo -u infrascan_ai --stop-after-init`

## Git
- Коммиты на русском, формат: `тип: описание`
- Типы: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- Никогда не коммитить: `.env`, `secrets/`, `*.key`
- Husky pre-commit: Biome проверяет JS/TS файлы автоматически

## Контейнеры
- Только `podman` и `podman-compose`
- Никогда: `docker`, `apt install`, `pip install` (глобально)

## Безопасность
- Секреты только в `bot/.env` (не в git)
- Токены в MCP конфигах — только в `~/.claude/settings.json` (не в проектном settings)

## Hook Pipeline (глобальный — всегда активен, нельзя обойти)

| Момент | Хук | Действие |
|---|---|---|
| PreToolUse Bash | `safety_guard.py` | Блокирует rm -rf /, fork bomb, dd if=disk, overwrite /etc/* |
| PreToolUse Write/Edit | `skill_vetter.py` | Блокирует eval(input()), shell injection, prompt injection в коде |
| PostToolUse Edit/Write | `run_pytest.sh` | pytest после каждого .py — exit 2 если тесты упали |
| PostToolUse Bash/Edit/Write | `stuck_detector.py` | 3 одинаковых ошибки → exit 2 → "смени подход" |
| Stop | `auto_journal.py` | Запись в Logseq журнал (автоматически) |
| Stop | `retrospective.py` | Gemini Red Team review если есть git diff → DECISIONS.md |
| Stop | `self_improving_agent.py` | Dry-run анализ паттернов ошибок |

Хуки встроены в `~/.claude/settings.json` — работают для ВСЕХ проектов на VDS.
При срабатывании exit 2 — операция заблокирована. Не пытаться обойти.
