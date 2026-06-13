# InfraScan AI — Полное описание проекта

> Состояние на **13 июня 2026**. Документ собран по фактическому коду репозитория
> (`bot/src/`, `addons/infrascan_ai/`, `podman-compose.yml`, `config/`) и памяти проекта.
> Секреты (токены, пароли, API-ключи, реальные Telegram-ID) намеренно не раскрываются.

## Оглавление

1. [Что такое InfraScan AI](#1-что-такое-infrascan-ai)
2. [Из чего состоит проект](#2-из-чего-состоит-проект)
3. [Архитектура и стек](#3-архитектура-и-стек)
4. [Роли и функции (клиент vs инженер)](#4-роли-и-функции-клиент-vs-инженер)
5. [Ключевые сервисы и модули бота](#5-ключевые-сервисы-и-модули-бота)
6. [Odoo-модуль `infrascan_ai`](#6-odoo-модуль-infrascan_ai)
7. [Android-приложение](#7-android-приложение)
8. [Деплой и эксплуатация](#8-деплой-и-эксплуатация)
9. [Мультиагентная dev-система](#9-мультиагентная-dev-система)
10. [Текущий статус](#10-текущий-статус)
11. [Безопасность](#11-безопасность)
12. [Дорожная карта](#12-дорожная-карта)

---

## 1. Что такое InfraScan AI

**InfraScan AI** — ИИ-сервис тепловизионной и строительной диагностики зданий и
оборудования. Пользователь (инженер или клиент) присылает фотографию объекта
(термограмму, фасад, кровлю, окно, электрощит и т. п.), а система с помощью
**Gemini Vision** выдаёт структурированное заключение: тип объекта, температурная
картина, выявленные дефекты, уровень риска (`LOW / MEDIUM / HIGH / CRITICAL`),
численная оценка риска и рекомендации.

Назначение:

- **для инженеров на выезде** — мгновенный «второй взгляд» ИИ-эксперта
  («Кибер-прораб»), контроль качества снимков и автоматическое прикрепление
  фото и отчёта к задаче в CRM;
- **для клиентов (B2C/B2B)** — самодиагностика жилья/объекта по фото, приём
  заявок на выезд инженера, история отчётов;
- **для бизнеса** — CRM-воронка (лиды → выезды → отчёты) в Odoo, авто-уведомления,
  утренние/вечерние дайджесты, ежемесячная аналитика.

Монетизация — **freemium**: бесплатный лимит сканов в день + платная подписка
**Premium** за Telegram Stars (расширенный анализ, PDF, голосовые заключения,
сравнения «до/после»). Есть **реферальная программа** и **партнёрская** схема.

Точки контакта с пользователем: **Telegram-бот** (основной канал, в проде) и
**Android-приложение** (готово, ждёт регистрации в RuStore).

---

## 2. Из чего состоит проект

| Компонент | Технология | Статус |
|---|---|---|
| **Backend-бот** | Python 3.11+, aiogram 3.20, Redis FSM | ✅ в проде |
| **Odoo CRM + модуль `infrascan_ai`** | Odoo 19 Community, PostgreSQL 17 | ✅ в проде |
| **Android-приложение** | Kotlin, Jetpack Compose, Hilt, RuStore SDK | ✅ код готов, 🔒 блокер RuStore |
| **Мультиагентная dev-система** | Claude + Gemini + Kimi + Grok + hooks | ✅ рабочий инструментарий |

Репозитории:

- backend (этот) — `github.com/Vangog4/infrascan-ai`;
- android — `github.com/Vangog4/infrascan-android`.

---

## 3. Архитектура и стек

### Контейнеры (podman-compose)

| Контейнер | Образ | Роль | Сети |
|---|---|---|---|
| `infrascan-ai_db` | `pgvector/pgvector:pg17` | PostgreSQL 17 (БД Odoo) | `odoo-internal` |
| `infrascan-ai_web` | `odoo:19` | Odoo 19 Community + модуль | `odoo-internal`, `npm_network`, `bot-net` |
| `infrascan-ai_redis` | `redis:7-alpine` | FSM-хранилище, кэш, очереди | `bot-net` |
| `infrascan-ai_bot` | `infrascan-ai-bot:latest` (собирается из `bot/Containerfile`) | Telegram-бот (aiogram 3) | `bot-net`, `npm_network` (alias `infrascan-bot`) |

Сети:

- **`odoo-internal`** (172.28.0.0/24, `internal: true`) — изолированный канал
  Odoo ↔ Postgres, без выхода в интернет;
- **`bot-net`** (172.29.0.0/24) — бот ↔ Odoo web ↔ Redis, есть выход наружу
  (Telegram API, Gemini, Open-Meteo);
- **`npm_network`** (внешняя) — Nginx Proxy Manager маршрутизирует HTTPS
  `infrascan-ai.ru` → Odoo web и `/bot/*` → контейнер бота.

Бот обращается к Odoo напрямую по внутренней сети: `http://infrascan-ai_web:8069`.

### Стек бота

- **aiogram 3.20** (webhook или long-polling), **RedisStorage** для FSM;
- **google-genai** (Gemini Vision/Text), **httpx** (Odoo JSON-2), **aiohttp**
  (HTTP-сервер webhook/health/metrics/webapp), **Pillow** (препроцессинг фото),
  **fpdf2** (PDF), **gTTS** (озвучка), **sentry-sdk** (опционально);
- **pydantic-settings** для конфигурации с fail-fast валидацией;
- инструментарий dev: **uv** (зависимости), **ruff** + **pytest** + **mypy**.

### Поток данных «фото → отчёт»

```
                 ┌─────────────┐
   Telegram  ──▶ │  aiogram bot │  (webhook /bot/webhook : 8080)
   (фото/      │ middlewares: │
    голос/      │ role, geo,   │
    альбом)     │ ratelimit,   │
                │ dedupe, log  │
                └──────┬──────┘
                       │  download bytes
                       ▼
         ┌──────────────────────────┐
         │  image_prep (downscale)  │
         │  + voice_context (TTS→STT)│
         └────────────┬─────────────┘
                       │  sha256(frames + ctx) → Redis cache?
              hit ◀────┤
                       │ miss
                       ▼
         ┌──────────────────────────┐         ┌──────────────────┐
         │   Gemini Vision API       │◀──retry─│ fallback-модель  │
         │  analyze_photo / _photos  │         │ (flash-lite)     │
         └────────────┬─────────────┘         └──────────────────┘
                       │  dict: object_type, risk_level,
                       │        risk_score, verdict, ...
        ┌──────────────┼───────────────────────────┐
        ▼              ▼                            ▼
  format_free/    Redis cache              Odoo (JSON-2 REST)
  premium →TG     (analysis)            - клиент: infrascan.bot.report
  + PDF/voice                            - инженер: ir.attachment + project.task
```

Ключевые HTTP-эндпоинты бота (порт 8080, проксируются через NPM с префиксом `/bot`):

- `POST /bot/webhook` — приём апдейтов Telegram (с secret-token);
- `GET /health`, `GET /bot/health` — проверка Redis (200/503);
- `GET /metrics`, `GET /bot/metrics` — метрики Prometheus;
- `GET /webapp-data/{key}` — данные для Telegram WebApp (валидация ключа).

---

## 4. Роли и функции (клиент vs инженер)

Роль определяется `RoleMiddleware` и сервисом `roles.py`:

- **CLIENT** — все по умолчанию;
- **EMPLOYEE** (инженер) — Telegram-ID из настройки `EMPLOYEE_TG_IDS`
  (`is_employee()` = `telegram_id in settings.employee_tg_ids`).
  **Важно: список `EMPLOYEE_TG_IDS` сейчас пуст**, поэтому инженерное меню в
  проде никому не выдаётся, пока в `.env` не добавят ID. Источник истины — env;
  Redis хранит лишь кэш роли (TTL 5 мин), для партнёра — 30 дней;
- **PARTNER** — роль с TTL 30 дней (переживает рестарты), для передачи лидов.

### Клиент (`handlers/client.py`, `payments.py`, `referral.py`, `account.py`, `reports.py`)

- **Анализ фото** — приём одиночного фото, **документа** (термограмма в полном
  качестве) и **альбома** (media_group, до нескольких кадров, дебаунс-буфер).
  Перед фото можно отправить **голосовой комментарий** — он транскрибируется и
  добавляется в контекст анализа (с защитой от prompt-injection).
- **Freemium-квота** — `FREE_DAILY_SCANS` (по умолчанию **3**) в сутки, счётчик
  в Redis с TTL до полуночи UTC. Сверх лимита — предложение Premium или
  трата бонусных сканов.
- **Premium** — подписка за **150 Stars/мес** (по умолчанию, 30 дней): анализ
  без лимита, премиальный формат заключения, PDF-отчёт, голосовое заключение,
  сравнение «до/после». Источник истины премиума — Redis (TTL = срок подписки),
  запись в Odoo — для биллинга/аналитики.
- **Приём заявок (лиды)** — клиент оставляет заявку на выезд → `create_lead()`:
  основной путь `crm.lead`, fallback — `project.task` в проекте «Выезд».
- **Рефералы** — `/ref`: персональный код, +5 бонусных сканов рефералу при
  регистрации, +5 сканов пригласившему за первый анализ друга, +7 дней Premium
  за покупку другом (лимит 50 активаций/мес).
- **Кабинет** (`/account`) — план, остаток сканов, бонусы, рефералы;
  **`/myreports`** — последние отчёты из Odoo.
- **Серийный аудит** (`serial_audit.py`) — пакетный анализ до 5 фото за раз.
- **Напоминания** — фоновый цикл шлёт follow-up через 30 дней после анализа.

### Инженер (`handlers/employee.py`)

Доступно только при роли EMPLOYEE. Меню:

- **🚗 Мои выезды на сегодня** — `get_today_tasks()` из Odoo: задачи проекта
  «Выезд» с дедлайном на сегодня (или без даты), отфильтрованные по
  `x_telegram_id` инженера (или общие), исключая лиды `[Лид]`.
- **📤 Сдать фото по объекту** — выбор задачи → отправка фото. Каждый снимок:
  1) **контроль качества** (`gemini.check_quality` — «Кибер-прораб» оценивает
  пригодность кадра 0–100, даёт вердикт/совет); 2) при приёмке — **ИИ-анализ**
  термограммы и **прикрепление в Odoo** (`ir.attachment` к `project.task`),
  выполняются параллельно (`asyncio.gather`).
- **/done** — формирует HTML-отчёт по всем снимкам и сохраняет в описание
  задачи (`save_analysis_report`).
- **🆘 SOS** — экстренный сигнал админам (`ADMIN_IDS`) с данными инженера.

Новые выезды инженеру дополнительно приходят пушем: фоновый `_task_notify_loop`
опрашивает Odoo каждые 5 минут и уведомляет о новых задачах; Odoo-модуль шлёт
уведомление при назначении (`x_telegram_id`) и при смене стадии задачи.

---

## 5. Ключевые сервисы и модули бота

`bot/src/services/`:

| Модуль | Назначение |
|---|---|
| **gemini.py** | Vision/Text через `google-genai`. Ретраи на основной модели (3 попытки, backoff+jitter, transient = 429/500/502/503/504 + сетевые/таймауты), затем **fallback-модель** (`GEMINI_FALLBACK_MODEL`, в проде `gemini-2.5-flash-lite`). Парсинг JSON с безопасным fallback при не-JSON-ответе. Метрики по каждому вызову. `analyze_photo/_photos`, `check_quality`, `transcribe_voice`, форматтеры free/premium. Санитизация голосового контекста против prompt-injection. |
| **odoo.py** | Клиент **Odoo JSON-2 REST** (`POST /json/2/{model}/{method}`, `Authorization: Bearer`). Ретраи transient (429/502/503/504 + сетевые), 4xx и «протухшая сессия» (не-JSON 200) → `None` без ретрая. Лиды, задачи, вложения, отчёты `infrascan.bot.report`, статус Premium, баланс партнёра. |
| **redis.py** | Подключение к Redis, FSM-storage, кэш анализов, WebApp-данные, очередь напоминаний. |
| **premium.py** | Квоты и подписки. Redis — источник истины (`scans:{id}`, `premium:{id}`). Бесплатный счётчик с TTL до полуночи UTC. Атомарный `consume_scan` (INCR-reserve + rollback) есть, но в hot-path ещё **не вплетён** (TODO — см. ниже). |
| **referral.py** | Реферальная программа (коды, бонусные сканы, премиум-дни, месячный лимит, идемпотентность через SETNX). |
| **roles.py** | Роли CLIENT/PARTNER/EMPLOYEE, телефон, трекинг пользователей (для broadcast). |
| **album_buffer.py** | Дебаунс-буфер альбомов (media_group): кадры буферизуются и обрабатываются как один отчёт; `can_accept()` отсекает переполнение до скачивания байт. |
| **image_prep.py** | Даунскейл крупных изображений (документы-термограммы) перед отправкой в Gemini; мелкие — без перекодирования. |
| **weather.py** | Текущая уличная температура через Open-Meteo (без ключа) — добавляется в контекст анализа. |
| **tts.py** | Озвучка заключения (gTTS, без ключа), запуск в thread-pool. |
| **pdf.py** | Брендированный PDF-отчёт для Premium (fpdf2, шрифты DejaVu). |
| **comparison.py** | Сравнение «до/после» по уровню и баллу риска. |
| **metrics.py** | Лёгкий in-process реестр метрик (Prometheus text exposition) без внешних зависимостей: счётчики Gemini-вызовов/ретраев, латентность, анализы фото, кэш-хиты, сбои фоновых задач. |
| **i18n.py** | Переводы для 5 локалей: `ru, en, de, tr, kk`. |

Middlewares (`bot/src/middlewares/`): `role` (роль), `geo` (локаль/локальность),
`ratelimit`, `dedupe` (защита от дублей контента), `logging`.
FSM-состояния (`states/flows.py`): `EmployeePhotoFlow`, `AuditFlow`,
`SerialAuditFlow`, `PartnerLeadFlow`.

---

## 6. Odoo-модуль `infrascan_ai`

Модуль `InfraScan AI Core` (v1.3, depends: `project`, `website`). Что добавляет:

- **`project.task`** (расширение): поля `x_telegram_id` (инженер),
  `x_client_tg_id` (клиент). Авто-уведомления в Telegram при назначении
  инженера, смене стадии (инженеру и клиенту), закрытии задачи (админам),
  создании лида `[Лид]` (с ИИ-оценкой качества лида через Gemini). Кнопка
  «Уведомить инженера». Серверный анализ термограммы по вложению
  (`action_analyze_thermal_image`).
- **`infrascan.bot.report`** (новая модель): отчёты бота — `client_tg_id`,
  `object_type`, `risk_level`, `risk_score`, `verdict`, `is_premium`. Источник
  истории `/myreports` и ежемесячного B2B-дайджеста.
- **`res.partner`** (расширение): `x_telegram_id`, `x_is_premium`,
  `x_premium_ends`, `x_partner_balance`.
- **Cron-задачи** (`ir_cron.xml`): утренний брифинг инженерам (07:45 МСК),
  вечерний отчёт админу с ИИ-инсайтом (18:00 МСК), напоминание о необработанных
  лидах (каждые 2 часа), ежемесячный дайджест клиентам (1-е число).
- Стадии воронки (`project_stage_data.xml`), системные параметры
  (`infrascan_config_data.xml`: токен бота, ключ Gemini, ID админов — хранятся
  в `ir.config_parameter`, не в коде), кастомный CSS/JS сайта, WebApp
  (`static/src/webapp/index.html`).

**Воронка CRM:** заявка/лид → проект «Выезд» (`project.task`) → назначение
инженера (`x_telegram_id`) → выезд и сдача фото через бота → отчёт в задаче →
закрытие стадии → уведомления клиенту и админу.

---

## 7. Android-приложение

Каталог `/root/infrascan/android/`, репозиторий `Vangog4/infrascan-android`,
пакет `ai.infrascan.app`, версия `0.1.0`.

- **Стек:** Kotlin + Jetpack Compose + Hilt + Room + CameraX + ML Kit OCR +
  Gemini Android SDK; VK ID 2.7.0 (One Tap авторизация); RuStore BOM 2026.04.02
  (Billing/Pay/Push); связь с Odoo через Retrofit.
- **Сборка:** только на **GitHub Actions** (на VDS не хватает памяти). Debug APK
  и подписанный Release AAB собираются зелёными; keystore-секреты настроены.
- **Статус:** код технически готов, последний CI собрал и подписал AAB.
- 🔒 **Блокер:** публикация в RuStore требует **`RUSTORE_COMPANY_ID`** —
  пользователю нужно зарегистрироваться разработчиком на rustore.ru, получить
  `companyId`, загрузить публичный ключ и создать приложение. До этого шаг
  «Publish to RuStore» делает graceful skip (PR #1) — CI на main зелёный без
  публикации.
- ⏳ **Технический долг:** миграция биллинга `BillingClient → ru.rustore.sdk:pay`
  с **дедлайном RuStore Pay 01.08.2026**; обновление actions Node 20 → 24.

---

## 8. Деплой и эксплуатация

Правила окружения (см. `CLAUDE.md`): **только podman/podman-compose**, **только
uv** для Python, никаких `apt/pip/docker`.

### Управление стеком

```bash
# Полный стек
podman-compose -f podman-compose.yml up -d

# Только Odoo
podman-compose -f podman-compose.yml restart web
```

### ⚠️ Безопасный деплой ТОЛЬКО бота (без рестарта стека)

`podman-compose up -d bot` может перезапустить весь стек (гоча зависимостей).
Безопасный путь — пересобрать образ и перезапустить **только** контейнер бота:

```bash
podman-compose -f podman-compose.yml build bot
podman restart infrascan-ai_bot
```

### Маршрутизация и наблюдаемость

- **NPM** проксирует HTTPS `infrascan-ai.ru/bot/*` → контейнер бота. В конфиге
  NPM используется **resolver + переменная** (динамический upstream), а alias
  сети — уникальный `infrascan-bot` (общий `bot` конфликтовал с другим проектом).
- **`/health`** — Redis ping (200 ok / 503 degraded), используется healthcheck'ами;
- **`/metrics`** — Prometheus-метрики бота;
- **Логи** — JSON-формат (`LOG_FORMAT=json`), ротация во всех контейнерах
  (`json-file`, max-size 10m × 3 файла);
- **Sentry** — опционально (если задан `SENTRY_DSN`).

### Тома (external, не удалять)

`infrascan-ai_db_data`, `infrascan-ai_web_data`, `infrascan-ai_redis_data`.

### Перед коммитом

`./judge.sh` → требуется **exit 0** (ruff + pytest + health). Для изменений
только в документации запуск можно опустить; при правках кода — обязателен.

---

## 9. Мультиагентная dev-система

Оркестрация разработки (конфиг `config/collaboration.yaml`, v2.1) — **четыре
движка**:

| Движок | Роль | Ниша |
|---|---|---|
| **Claude** | Оркестратор | Edit/Write/Bash, git, тесты, архитектура, финальные решения |
| **Gemini** | Специалист (2M ctx + Web + Vision) | анализ фото/термограмм, web-research, red team, code review, health |
| **Kimi** | Аналитик (262K ctx, thinking) | анализ всего `bot/src/` за один вызов, логи, миграции, второе мнение |
| **Grok** | Контрарианец (realtime X/web) | независимое мнение «другой школы», адвокат дьявола, swarm-аудит |

- **router.py** маршрутизирует задачу по ключевым словам/размеру файла к
  нужному движку и режиму (`analyze/research/redteam/review/...`).
- **Grok swarm** — оркестратор может спавнить до 8 параллельных read-only
  субагентов по измерениям аудита → единый отчёт.
- **Hook-пайплайн безопасности:**
  - *PreToolUse* `safety_guard.py` (блок `rm -rf /`, fork-bomb, `dd if=`, `mkfs`),
    `skill_vetter.py` (аудит Write/Edit на RCE/injection);
  - *PostToolUse* `run_pytest.sh` (pytest после правок `.py`),
    `stuck_detector.py` (3 одинаковые ошибки → смени подход);
  - *Stop* `auto_journal.py` (Logseq-журнал), `retrospective.py` (Gemini-ревью
    диффа → запись в `DECISIONS.md`).
- Необратимые операции проходят через `confirm_bridge.py` → подтверждение в Telegram.

> Примечание к этой сессии: запуск `kimi_agent.sh analyze bot/src` вернул пустой
> вывод (движок не ответил/таймаут), поэтому описание собрано по прямому чтению
> кода — как и предусмотрено протоколом «не блокироваться на недоступном движке».

---

## 10. Текущий статус

### ✅ Сделано / в проде
- Telegram-бот (клиент + инженер), Odoo 19 + модуль `infrascan_ai`, Redis FSM.
- Gemini Vision с ретраями и fallback-моделью; метрики `/metrics`; `/health`.
- Freemium (3 скана/день), Premium за Stars, рефералы, партнёрские лиды.
- Анализ одиночных фото, документов-термограмм, альбомов, серийный аудит,
  голосовой контекст, PDF и голосовые заключения, сравнение «до/после».
- Odoo: авто-уведомления, утренние/вечерние дайджесты, лид-фоллоуап, B2B-дайджест.
- Webhook + NPM-маршрутизация `/bot/*`; ротация логов; JSON-логи.

### ⏳ Отложено (с TODO)
- **Вайринг атомарного `consume_scan`** в hot-path: сейчас `client._check_quota`
  использует неатомарную проверку `scans_remaining` (узкое окно TOCTOU при
  параллельных фото). Атомарный `premium.consume_scan` готов, но требует решения
  по refund-пути и переписи квотных тестов. Заодно — Lua-скрипт для полной
  атомарности INCR+EXPIRE.
- **Non-root контейнер бота** — запуск под непривилегированным пользователем.

### 🔒 Блокеры
- **Android `RUSTORE_COMPANY_ID`** — нет регистрации разработчика в RuStore.
- **Текущая ветка не влита в `main`** — работа идёт на ветке
  `autoresearch/stack-health-2026-05-15`.

---

## 11. Безопасность

Что закрыто за последние сессии:

- **Санитизация голосового контекста против prompt-injection**
  (`gemini._sanitize_voice_context`): чистит управляющие символы и схлопывает
  ввод, прежде чем подмешать транскрипт в промпт и ключ кэша.
- **Fail-fast валидация конфига** (`config.py`): при старте падаем, если нет
  `GEMINI_API_KEY` (когда не stub) или `WEBHOOK_SECRET` при заданном
  `WEBHOOK_URL` — кривой конфиг ловится на старте, а не в рантайме.
- **Ретраи Odoo** (`odoo._call`): transient-ошибки ретраятся с backoff+jitter;
  4xx и «протухшая сессия» (не-JSON 200) не ретраятся — защита от зацикливания.
- **Supervise fire-and-forget задач** (`client._supervise_task`): фоновые
  `asyncio.create_task` (например `save_report`) логируют падения и пишут
  метрику `background_task_failures_total`, а не молча теряются.
- **`.dockerignore`** в `bot/`: `.env`/секреты/мусор не попадают в build-context
  (при этом `*.lock` не исключается — иначе ломается `COPY uv.lock`).
- **Webhook secret-token** обязателен; валидация ключа в `/webapp-data/{key}`.
- **Сетевая изоляция**: Postgres только во внутренней сети без выхода наружу;
  порты Odoo (`8069/8072`) и бота (`8080`) слушают только `127.0.0.1`, наружу —
  через NPM.
- **Секреты вне кода**: токены/ключи в `.env` бота и в `ir.config_parameter`
  Odoo, не в репозитории.

---

## 12. Дорожная карта

Ближайшие шаги (по приоритету):

1. **Вплести атомарный `consume_scan`** в hot-path квоты + refund-путь + Lua-скрипт.
2. **Влить рабочую ветку в `main`** после стабилизации.
3. **Non-root контейнер бота**.
4. **Android → RuStore**: получить `RUSTORE_COMPANY_ID`, опубликовать (staged 5%),
   мигрировать биллинг на RuStore Pay SDK до **01.08.2026**.
5. Подключить `EMPLOYEE_TG_IDS` реальными инженерами (сейчас пуст — инженерное
   меню недоступно).
6. Расширить наблюдаемость (дашборды по `/metrics`, алерты).

---

*Документ подготовлен в рамках проектной сессии InfraScan AI backend.*
