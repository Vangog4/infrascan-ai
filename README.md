# InfraScan AI — Backend

**ИИ-сервис тепловизионной и строительной диагностики** зданий и оборудования.
Пользователь присылает фото объекта (термограмму, фасад, кровлю, окно,
электрощит), а **Gemini Vision** выдаёт заключение: тип объекта, температурная
картина, дефекты, уровень риска (`LOW/MEDIUM/HIGH/CRITICAL`) и рекомендации.

Каналы: **Telegram-бот** (в проде) и **Android-приложение** (готово, ждёт RuStore).
CRM, отчёты и воронка — в **Odoo 19**. Монетизация — **freemium** (бесплатный
лимит сканов + Premium за Telegram Stars), рефералы и партнёрская программа.

## Состав репозитория

| Каталог | Что внутри |
|---|---|
| `bot/` | Telegram-бот (Python 3.11+, aiogram 3.20, Redis FSM, Gemini, Odoo JSON-2) |
| `addons/infrascan_ai/` | Odoo 19 модуль: воронка CRM, авто-уведомления, cron-дайджесты |
| `config/` | `odoo.conf`, `collaboration.yaml` (мультиагентная dev-система) |
| `hooks/` | dev-агенты (Gemini/Kimi/Grok), router, safety/journal/retrospective hooks |
| `podman-compose.yml` | стек: Postgres 17 + Odoo 19 + Redis + бот |

## Архитектура (кратко)

```
Telegram ─▶ bot (aiogram) ─▶ Gemini Vision ─▶ результат
                 │                                │
                 └────────▶ Odoo 19 (JSON-2) ◀────┘
              (контейнеры: db / web / redis / bot, podman)
```

## Запуск

```bash
podman-compose -f podman-compose.yml up -d        # весь стек
podman-compose -f podman-compose.yml build bot    # пересборка бота
podman restart infrascan-ai_bot                   # безопасный рестарт ТОЛЬКО бота
```

Требования окружения: **podman/podman-compose** и **uv** (без `apt/pip/docker`).
Перед коммитом — `./judge.sh` (ruff + pytest + health), нужен exit 0.

## Документация

- 📘 **[Полное описание проекта → `docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)**
  — назначение, состав, архитектура, роли (клиент vs инженер), сервисы,
  Odoo-модуль, Android, деплой, мультиагентная dev-система, статус, безопасность,
  дорожная карта.
- `CLAUDE.md` — инструкции и guardrails для агентов.
- `CONVENTIONS.md` — стандарты кода. `DECISIONS.md` — архитектурные решения.

## Связанные репозитории

- Android: [`Vangog4/infrascan-android`](https://github.com/Vangog4/infrascan-android)

---

> Секреты (токены, ключи, пароли) в репозиторий не коммитятся — они в `.env`
> бота и в `ir.config_parameter` Odoo.
