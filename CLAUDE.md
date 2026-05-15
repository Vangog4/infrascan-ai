# CLAUDE.md — infrascan-ai

## Sandbox Rules (MANDATORY — no exceptions)
- Container runtime: **podman** and **podman-compose** ONLY
- Python tooling: **uv** ONLY (`uv run`, `uv pip`, `uv tool install`)
- **NEVER** run `apt install`, `pip install`, or any global package manager
- **NEVER** invoke `docker` or `docker-compose`
- **NEVER** write to system Python (`/usr/lib/python*`) or `/usr/local`
- All MCP servers must be installed via `uv tool install` into `~/.local/`

## Project Layout
```
infrascan-ai/
├── podman-compose.yml      # единый стек: Odoo 19 + Postgres 17 + Telegram бот
├── config/odoo.conf        # proxy_mode=True, workers=2
├── addons/                 # кастомные модули Odoo (bind-mount :ro)
│   └── infrascan_ai/       # основной модуль: тепловизионный анализ через Gemini
└── bot/                    # Telegram бот (aiogram 3.x)
    ├── src/
    │   ├── bot.py          # точка входа, Dispatcher
    │   ├── config.py       # pydantic-settings (.env)
    │   ├── handlers/       # client, employee, partner, common
    │   ├── services/
    │   │   ├── odoo.py     # XML-RPC интеграция с Odoo
    │   │   └── gemini.py   # Gemini Vision API
    │   ├── middlewares/    # role, ratelimit, dedupe, logging
    │   ├── keyboards/      # меню сотрудника и клиента
    │   └── states/         # FSM flows (EmployeePhotoFlow и др.)
    ├── Containerfile
    ├── pyproject.toml
    └── .env                # секреты (не коммитить!)
```

## Контейнеры и сети
| Контейнер | Роль | Сети |
|---|---|---|
| `infrascan-ai_db` | PostgreSQL 17 | `odoo-internal` |
| `infrascan-ai_web` | Odoo 19 Community | `odoo-internal`, `npm_network`, `bot-net` |
| `infrascan-ai_bot` | Telegram бот | `bot-net` |

- **`odoo-internal`** — изолированная сеть (172.28.0.0/24), только Odoo ↔ Postgres
- **`bot-net`** — мост (172.29.0.0/24), бот ↔ Odoo web, есть выход в интернет (Telegram API)
- **`npm_network`** — внешняя, Nginx Proxy Manager → Odoo web

Бот обращается к Odoo **напрямую по внутренней сети**: `http://infrascan-ai_web:8069`

## Управление стеком
```bash
# Полный стек
podman-compose -f podman-compose.yml up -d
podman-compose -f podman-compose.yml down

# Пересборка и перезапуск бота
podman-compose -f podman-compose.yml build bot
podman-compose -f podman-compose.yml up -d bot

# Только Odoo
podman-compose -f podman-compose.yml restart web

# Логи
podman-compose -f podman-compose.yml logs -f web
podman-compose -f podman-compose.yml logs -f bot
```

Odoo UI → https://infrascan-ai.ru | Odoo local → http://localhost:8069 | Longpolling → :8072

## Интеграция бот ↔ Odoo
Бот использует XML-RPC API Odoo (`src/services/odoo.py`):
- Пользователь API: `api@infrascan-ai.ru` (права в Odoo: res.partner read, project.task read+create, ir.attachment read+create)
- CRM лиды: `crm.lead` (требует роль Sales/User) → fallback на `project.task` в проекте "Выезд" (id=1)
- Роли бота: сотрудник (из `EMPLOYEE_TG_IDS`) vs клиент (остальные)
- Фото от сотрудников прикрепляются к задачам через `ir.attachment`

## Модуль Odoo `infrascan_ai` (addons/)
- Расширяет `project.task` полями тепловизионного анализа
- Интеграция с Gemini Vision API для анализа термограмм
- API ключ Gemini хранится в `ir.config_parameter` (не хардкодить!)

## Переменные окружения бота (bot/.env)
```
BOT_TOKEN=...
ADMIN_IDS=[tg_id, ...]
EMPLOYEE_TG_IDS=[tg_id, ...]
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
ODOO_URL=http://infrascan-ai_web:8069   # внутренняя сеть!
ODOO_DB=InfraScan_bd
ODOO_USERNAME=api@infrascan-ai.ru
ODOO_PASSWORD=...
```

## AI Toolchain
| Tool | Role |
|------|------|
| **AutoResearch** | Autonomous web research plugin for Claude Code |
| **Gemini CLI context bridge** | Cross-model review — passes repo context to Gemini |
| **Logseq журнал** | Локальные дневные файлы в `bot/logseq/journals/` |

## Logseq — Журнал сессий (ОБЯЗАТЕЛЬНО)
Каждая сессия работы **должна быть задокументирована** в Logseq-журнале.

- **Путь:** `bot/logseq/journals/YYYY_MM_DD.md`
- **Когда писать:** в конце каждой сессии или после завершения значимой задачи
- **Что писать:** что сделано, почему, результат (тесты прошли / упали), статус стека
- **Формат имени файла:** `2026_05_11.md` (год_месяц_день)

Правило: **не заканчивать сессию без записи в журнал**.

## Development Workflow
1. Изменения в модуле Odoo → `podman-compose restart web`
2. Изменения в боте → `podman-compose build bot && podman-compose up -d bot`
3. Скрипты Python: `uv run <script>.py` (в папке `bot/`)
4. Никогда не коммитить `bot/.env` и `admin_passwd`
5. Website builder: workers ≥ 2 и `proxy_mode = True` (уже настроено)

## Режимы работы (Spec-Driven Development)
Объявлять режим в начале каждого ответа:
- `[DESIGN MODE]` — сначала спека, без кода
- `[BUILD MODE]` — реализация после согласования спеки
- `[PATCH MODE]` — точечные правки
- `[REVIEW MODE]` — только анализ

## STATE_MEMORY — обязательный протокол
В конце **каждого значимого ответа** фиксировать:
```
<STATE_MEMORY>
✅ Сделано: [список]
🔄 Открыто: [незакрытые задачи]
➡️ Следующий шаг: [конкретное действие]
</STATE_MEMORY>
```

## Документация проекта
- `CONVENTIONS.md` — стандарты кода и инструментов
- `DECISIONS.md` — архитектурные решения (обновлять при каждом значимом решении)
- `bot/logseq/journals/` — журнал сессий (пишется автоматически через Stop hook)
