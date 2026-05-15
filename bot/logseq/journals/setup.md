# InfraScan AI Bot — Setup Report
**Date:** 2026-04-30  
**Status:** 🟢 БОТ ЗАПУЩЕН И РАБОТАЕТ

---

## Идентификация

| Параметр | Значение |
|---|---|
| Имя бота | ИнфраСкан \| Нейро-Диагностика |
| Username | @infrascan_ai_bot |
| Bot ID | 8799508400 |
| Gemini модель | gemini-2.5-flash |
| Podman контейнер | `infrascan-bot` (--restart unless-stopped) |

---

## Архитектура — Ролевая модель

```
Все пользователи
  └─ RoleMiddleware (проверяет Odoo + локальный кэш)
       ├─ EMPLOYEE  → employee.router   (задачи, фото, SOS)
       ├─ PARTNER   → partner.router    (лиды, баланс)
       └─ CLIENT    → client.router     (аудит, калькулятор, заявка, регистрация партнёра)
```

### Pipeline middleware:
```
Update → RoleMiddleware (outer)
  └─ Message → RateLimitMiddleware → ContentDedupeMiddleware → LoggingMiddleware → Handler
```

---

## Структура кода

```
src/
├── bot.py                    — точка входа, регистрация всего
├── config.py                 — Settings (pydantic-settings)
├── services/
│   ├── roles.py              — кэш ролей (TTL 5 мин)
│   ├── gemini.py             — Gemini 2.5 Flash (audit, calc, QC)
│   └── odoo.py               — XML-RPC: lead/partner/task/attachment
├── keyboards/
│   └── menus.py              — все клавиатуры (Reply + Inline)
├── states/
│   └── flows.py              — FSM: AuditFlow, CalcFlow, LeadFlow, ...
├── middlewares/
│   ├── role.py               — RoleMiddleware
│   ├── ratelimit.py          — 5 msg/5 sec, cooldown 30 sec
│   ├── dedupe.py             — SHA-256 дедупликация контента
│   └── logging.py            — логирование событий
└── handlers/
    ├── common.py             — /start (роль-зависимый), /cancel
    ├── client.py             — фото-аудит, калькулятор, заявка, стать партнёром
    ├── partner.py            — передача лидов, баланс
    └── employee.py           — задачи, сдача фото с QC, SOS
```

---

## Реализованные функции

### Уровень 1: Клиент
- ✅ `📸 Проверить фото` — Gemini анализирует дефекты, теплопотери
- ✅ `🧮 Калькулятор потерь` — FSM опрос (3 шага) → Gemini расчёт
- ✅ `📞 Вызвать инженера` — захват контакта → Odoo CRM lead
- ✅ `🤝 Стать партнером` — регистрация, смена роли → кабинет партнёра
- ✅ Inline-кнопка «Заказать диагностику» после анализа/расчёта

### Уровень 2: Партнёр
- ✅ `➕ Передать лида` — ввод телефона клиента → Odoo lead с атрибуцией
- ✅ `💰 Мой баланс` — запрос баланса из Odoo
- ✅ `📸 Проверить фото` — тот же визуальный аудитор

### Уровень 3: Сотрудник
- ✅ `🚗 Мои выезды на сегодня` — задачи из `project.task` Odoo
- ✅ `📤 Сдать фото по объекту` — выбор задачи → приём фото → QC Gemini → `ir.attachment` Odoo
- ✅ `🆘 SOS` — уведомление всех admin_ids

---

## Контроль качества (Кибер-прораб)

```
Инженер отправляет фото
  → Gemini 2.5 Flash: чёткость + освещённость + полнота кадра
  ├─ ПРИНЯТО → 🟢 + загрузка в ir.attachment (Odoo)
  └─ БРАК    → ❌ + причина + запрос пересъёмки
```

---

## Зависимости

| Пакет | Версия |
|---|---|
| aiogram | 3.20.0 |
| google-genai | ≥1.0.0 |
| pydantic-settings | ≥2.14.0 |
| aiohttp | ≥3.11.18 |

---

## Запуск

### Podman (продакшн, уже запущен):
```bash
podman ps   # проверить статус
podman logs -f infrascan-bot   # логи в реальном времени
```

### Локально:
```bash
uv run python -m src.bot
```

---

## Что нужно настроить

- [ ] `ADMIN_IDS` в `.env` — Telegram ID для получения SOS-сигналов
- [ ] Odoo: `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD`
- [ ] В Odoo добавить поля: `x_telegram_id` (hr.employee), `x_is_partner`, `x_partner_balance` (res.partner)
- [ ] `EMPLOYEE_TG_IDS` в `.env` — пока Odoo не настроен (fallback)

---

## MCP — База знаний

```
filesystem MCP → ./logseq (Connected)
```
R/W-доступ к журналам проекта через `@modelcontextprotocol/server-filesystem`.
