# SESSION_NOTES — заметки текущей сессии

## Текущая задача
Per-project multi-agent система — каждый проект имеет своих специализированных субагентов.

## Что сделано в эту сессию
- Починён `hooks/router.py` — добавлен `import shlex`
- Настроена система памяти: `journal_logger.py` (real-time), `auto_journal.py` (итог), `session_snapshot.py` (STATE)
- Создан `/root/agents/` — система per-project субагентов:
  - `agents/projects/infrascan.yaml` — полный контекст: стек, конвенции, бэклог, специализации
  - `agents/projects/pepito.yaml`
  - `agents/projects/astrotara.yaml`
  - `agents/projects/subarist.yaml`
  - `agents/projects/amanita.yaml`
  - `agents/orchestrator.py` — параллельный запуск агентов, автодетект проекта
- Переписан `hooks/gemini_agent.sh` — project-aware, читает YAML контекст, исправлен дублирующийся хвост
- Обновлён `kimi_agent.sh` — читает YAML контекст из `/root/agents/projects/`, поддерживает `KIMI_PROJECT_CONTEXT` env
- Создан симлинк `/usr/local/bin/agent` → `orchestrator.py`
- `SESSION_NOTES.md` создан для всех проектов (кроме dogsensei — не трогать)
- Блок ⚡ SESSION MEMORY добавлен в CLAUDE.md всех проектов

## Ключевые решения
- Контекст агентов: YAML файлы в `/root/agents/projects/` — один источник правды
- Инжекция контекста: env vars `GEMINI_PROJECT_CONTEXT` / `KIMI_PROJECT_CONTEXT` от оркестратора
- Параллельность: `concurrent.futures.ThreadPoolExecutor` в orchestrator.py
- Автодетект проекта по cwd → git root → YAML match
- НЕ делать git commit/push без явного разрешения пользователя

## Следующие шаги (незавершённое)
- Проверить работу Gemini (сейчас "недоступен" в ретроспективах — выяснить почему)
- Проверить работу Kimi-k2.6 через `/root/kimi_agent.sh council "тест"`
- Обновить `SYSTEM_GUIDE.md` с новой архитектурой агентов
- Закоммитить всё (когда пользователь даст добро)
- Обсудить: нужны ли Claude sub-agents через Anthropic API (отдельный Claude на каждый проект)

## Контекст который важно помнить
- Ветка: `autoresearch/stack-health-2026-05-15`
- Диск 88% заполнен — осторожно с новыми пакетами
- Пользователь хочет чтобы система помнила ВСЁ — журнал пишется в реальном времени
- dogsensei_bot — не трогать
