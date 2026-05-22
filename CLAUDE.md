# CLAUDE.md — infrascan-ai

## Pre-Session Checklist (выполнять перед каждой сессией)
```bash
python3 /root/infrascan-ai/hooks/process_watch.py   # все сервисы up?
git -C /root/infrascan-ai status                    # нет незакоммиченного мусора?
df -h /                                             # диск > 10% свободно?
```
Если диск < 10% → сначала: `podman image prune -f` (безопасно)

## Guardrails (абсолютные запреты)
- **НИКОГДА** `podman system prune -a` без `confirm_bridge.py`
- **НИКОГДА** редактировать `bot/.env` напрямую — только через переменные окружения
- **НИКОГДА** `git push --force` на main
- **НИКОГДА** удалять volume `*_db_data` — это данные баз
- Необратимые операции: всегда через `confirm_bridge.py "описание"` → Telegram-подтверждение

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
6. **Перед коммитом:** `./judge.sh` → exit 0 обязателен (ruff + pytest + health)

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

---

## Multi-Agent Orchestration Architecture (v2.0 — три движка)

```
┌──────────────────────────────────────────────────────────────────────┐
│                      CLAUDE (Orchestrator)                            │
│   PreToolUse           Core Logic           PostToolUse + Stop        │
│  ┌──────────┐       ┌────────────┐        ┌───────────────────┐      │
│  │safety_   │       │  router.py │        │run_pytest.sh      │      │
│  │guard.py  │       │            │        │stuck_detector.py  │      │
│  │(Bash)    │       │  claude?   │        │auto_journal.py    │      │
│  ├──────────┤       │  gemini?   │        │retrospective.py   │      │
│  │skill_    │       │  kimi?     │        └───────────────────┘      │
│  │vetter.py │       └──┬──────┬──┘                                   │
│  └──────────┘          │      │                                      │
│                        │      └──────────────────────┐               │
│                        ▼                             ▼               │
│              ┌──────────────────┐       ┌─────────────────────┐      │
│              │  GEMINI 2.5      │       │  KIMI 2.5           │      │
│              │  (Специалист)    │       │  (Аналитик)         │      │
│              │                  │       │                     │      │
│              │ 2M ctx + Web     │       │ 128K ctx (дёшево)   │      │
│              │ + Vision API     │       │ OpenAI-совместимый  │      │
│              │                  │       │                     │      │
│              │ modes:           │       │ modes:              │      │
│              │  review          │       │  analyze            │      │
│              │  analyze         │       │  bulk               │      │
│              │  research        │       │  draft              │      │
│              │  redteam         │       │  migrate            │      │
│              │  retrospective   │       │  compare            │      │
│              │  health          │       │  council            │      │
│              └──────────────────┘       └─────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

### Agent Registry — роли

| Агент | Когда | Примеры задач |
|---|---|---|
| **Claude** | Всегда (оркестратор) | Edit, Write, git, тесты, планирование |
| **Gemini** | Vision / Web / Security | Фото анализ, поиск в доках, red team |
| **Kimi** | Большой объём / дёшево | Весь репо, логи, черновики, миграции БД |

### Маршрутизация (router.py)

```bash
# Узнать куда идёт задача:
python3 hooks/router.py "проанализируй все логи за неделю"
# → {"engine": "kimi", "mode": "bulk", ...}

python3 hooks/router.py "найди уязвимости в webhook"
# → {"engine": "gemini", "mode": "redteam", ...}
```

### Gemini Quick Reference

```bash
bash hooks/gemini_agent.sh review          # code review git diff
bash hooks/gemini_agent.sh analyze <file>  # анализ файла/директории
bash hooks/gemini_agent.sh research "..."  # веб-поиск
bash hooks/gemini_agent.sh health          # диагностика стека
bash hooks/gemini_agent.sh redteam         # adversarial security audit
bash hooks/gemini_agent.sh retrospective   # ретроспектива сессии
```

### Kimi Quick Reference

```bash
kimi analyze /root/infrascan-ai/bot/src/   # весь bot/src/ за раз
kimi bulk /root/infrascan-ai/bot.log        # анализ логов
kimi draft "идея для новой фичи"            # черновик (дёшево)
kimi migrate /root/astrotara_bot/bot_app/src/database/models.py
kimi compare "Redis vs Postgres для кеша"
kimi council "стоит ли переходить на gRPC"
```

### Настройка Kimi API

```bash
# Добавить в /root/.env или /root/infrascan-ai/.env:
MOONSHOT_API_KEY=sk-xxxxxxxxxxxxxxxx
# Получить: https://platform.moonshot.cn/console/api-keys
```

### Слои безопасности (Hook Pipeline)

| Момент | Хук | Что делает | Действие |
|---|---|---|---|
| **PreToolUse** Bash | `safety_guard.py` | Блокирует `rm -rf /`, fork bomb, `dd if=`, mkfs | exit 2 = BLOCK |
| **PreToolUse** Write/Edit | `skill_vetter.py` | Аудит на RCE, injection, prompt injection | exit 2 = BLOCK |
| **PostToolUse** Edit/Write | `run_pytest.sh` | pytest после изменений .py файлов | exit 2 = BLOCK |
| **PostToolUse** Bash/Edit/Write | `stuck_detector.py` | 3 одинаковых ошибки → смени подход | exit 2 = BLOCK |
| **Stop** | `auto_journal.py` | Запись в Logseq журнал | info only |
| **Stop** | `retrospective.py` | Gemini Red Team review если есть git diff | info only |

### Retrospective Loop (Compound Engineering)

Каждая сессия заканчивается автоматической ретроспективой:
1. `retrospective.py` проверяет `git diff --stat HEAD`
2. Если изменения есть → вызывает `gemini_agent.sh review`
3. Результат пишется в `DECISIONS.md` с timestamp
4. Накапливается долгосрочная инженерная экспертиза

Ручной запуск полного ретро (нужно для "ночного" цикла):
```bash
bash hooks/gemini_agent.sh retrospective
```

### Overnight Autonomous Loop

```bash
# Автономная работа с бюджетом
./hooks/loop_orchestrator.sh "Покрой bot/src/ тестами до 90%" 30 120

# Из файла задачи
echo "Задача: ..." > /tmp/task.md
./hooks/loop_orchestrator.sh --file /tmp/task.md 50 240

# Мониторинг
tail -f /tmp/loop_*.log
```

Как работает `stuck_detector.py`:
1. Хешируется: tool_name + команда/файл + tail(stderr)
2. Тот же хеш ≥ 3 раз в окне 12 вызовов → exit 2 → "STUCK — смени подход"
3. После срабатывания счётчик сбрасывается

### MCP инструменты в сессии

| Сервер | Что делает |
|---|---|
| `fetch` | Загружает URL страниц |
| `odoo-infrascan` | Прямой доступ к InfraScan_bd (XML-RPC) |
| `odoo-dev-mcp` | 300+ страниц документации Odoo 19 |
| `telegram-bot-mcp` | Отправка сообщений через бота |
| `visual-qa` | Screenshot QA для amanita_odoo |
| `visual-qa-pepito` | Screenshot QA для pepito |

### Sandboxing (Podman)

Весь стек изолирован в Podman-контейнерах.
Для полной изоляции агента (VERY UNSAFE tasks):
```bash
podman run --rm -it -v /root/infrascan-ai:/workspace \
  localhost/infrascan-ai-bot:latest \
  claude --dangerously-skip-permissions -p "задача"
```

### Gemini Subagent Quick Reference

```bash
bash hooks/gemini_agent.sh review          # code review git diff
bash hooks/gemini_agent.sh analyze <file>  # deep file analysis
bash hooks/gemini_agent.sh research "..."  # web search
bash hooks/gemini_agent.sh health          # stack diagnostics
bash hooks/gemini_agent.sh redteam         # adversarial security audit
bash hooks/gemini_agent.sh retrospective   # session retrospective
bash hooks/gemini_agent.sh route "задача"  # routing decision
```

Конфигурация агентов: `config/collaboration.yaml`
Логи safety guard: `/tmp/safety_guard.log`
Логи skill vetter: `/tmp/skill_vetter.log`
