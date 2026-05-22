#!/usr/bin/env python3
"""
Kimi 2.5 Subagent Client — Moonshot AI API (OpenAI-compatible).

Modes:
  analyze  <path>   — full file/dir dump into 128K context (whole repo at once)
  bulk     <file>   — large log / data dump analysis
  draft    <task>   — cheap first-pass exploration / brainstorm
  migrate  <path>   — DB schema / SQLAlchemy models migration analysis
  compare  <t>      — A/B code comparison, alternative implementations
  council  <q>      — second opinion on architectural question

Usage:
  python3 kimi_client.py analyze /root/infrascan-ai/bot/src/
  python3 kimi_client.py bulk /root/infrascan-ai/bot.log
  python3 kimi_client.py draft "как лучше реализовать кеш теплопотерь"
  python3 kimi_client.py migrate /root/astrotara_bot/bot_app/src/database/models.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── API setup ─────────────────────────────────────────────────────────────────

MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = os.environ.get("KIMI_MODEL", "moonshot-v1-128k")

# Known projects on this server
PROJECTS = {
    "/root/infrascan-ai": "InfraScan AI (Odoo 19 + aiogram 3 + Gemini Vision, Python)",
    "/root/astrotara_bot": "AstroTara (aiogram 3 + SQLite + APScheduler, астрология)",
    "/root/dogsensei_bot": "DogSensei (aiogram 3, admin monitoring bot)",
}

# Token budget per mode (128K window — stay under to avoid rate limits)
_MODE_TOKENS = {
    "analyze": 100_000,
    "bulk": 110_000,
    "draft": 8_000,
    "migrate": 60_000,
    "compare": 40_000,
    "council": 4_000,
}


def _detect_project(path: str) -> str:
    abs_path = str(Path(path).resolve())
    for prefix, desc in PROJECTS.items():
        if abs_path.startswith(prefix):
            return desc
    return "Unknown project on VDS (Ubuntu 24, Podman, uv)"


def _collect_files(path: str, max_bytes: int) -> str:
    """Collect Python/YAML/SQL/XML files under path, up to max_bytes."""
    p = Path(path)
    if p.is_file():
        content = p.read_text(errors="replace")
        return f"# {path}\n{content[:max_bytes]}"

    chunks: list[str] = []
    total = 0
    exts = {".py", ".yaml", ".yml", ".sql", ".xml", ".md", ".toml", ".csv"}
    skip_dirs = {"__pycache__", ".venv", ".git", "node_modules", ".mypy_cache"}

    for f in sorted(p.rglob("*")):
        if any(d in f.parts for d in skip_dirs):
            continue
        if f.suffix not in exts or not f.is_file():
            continue
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        rel = str(f.relative_to(p))
        chunk = f"\n{'='*60}\n# {rel}\n{'='*60}\n{text}"
        if total + len(chunk) > max_bytes:
            chunks.append(f"\n... [truncated — {max_bytes} bytes limit reached] ...")
            break
        chunks.append(chunk)
        total += len(chunk)

    return "".join(chunks)


def _call_kimi(system: str, user: str, mode: str) -> str:
    if not MOONSHOT_API_KEY:
        return (
            "⚠️  MOONSHOT_API_KEY не задан.\n"
            "Добавь в /root/infrascan-ai/.env:\n"
            "  MOONSHOT_API_KEY=sk-xxxxxxxxxxxxxxxx\n"
            "Получить ключ: https://platform.moonshot.cn/console/api-keys"
        )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
        resp = client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user[:_MODE_TOKENS[mode] * 4]},  # ~4 chars/token
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"❌ Kimi API error: {e}"


# ── Modes ─────────────────────────────────────────────────────────────────────

def mode_analyze(path: str) -> None:
    """Feed entire directory/file into 128K context for deep analysis."""
    project = _detect_project(path)
    print(f"🤖 [Kimi] mode=analyze  model={KIMI_MODEL}  path={path}")
    print("─" * 60)

    content = _collect_files(path, _MODE_TOKENS["analyze"] * 4)
    system = (
        f"Ты старший Python-инженер. Проект: {project}\n"
        "Анализируй весь переданный код как единое целое. "
        "Ищи: скрытые баги, нарушения архитектуры, дублирование, "
        "потенциальные утечки памяти, места для рефакторинга. "
        "Отвечай структурированно: файл:строка → проблема → решение."
    )
    user = f"Проанализируй следующий код проекта:\n\n{content}"
    print(_call_kimi(system, user, "analyze"))


def mode_bulk(file_path: str) -> None:
    """Analyze large log or data dump."""
    print(f"🤖 [Kimi] mode=bulk  model={KIMI_MODEL}  file={file_path}")
    print("─" * 60)

    try:
        content = Path(file_path).read_text(errors="replace")
    except Exception as e:
        print(f"❌ Не могу прочитать файл: {e}")
        return

    system = (
        "Ты DevOps-инженер. Анализируй логи/данные: найди паттерны ошибок, "
        "аномалии, узкие места. Группируй похожие ошибки. "
        "Приоритизируй по severity: CRITICAL > ERROR > WARNING."
    )
    user = f"Файл: {file_path}\n\n{content}"
    print(_call_kimi(system, user, "bulk"))


def mode_draft(task: str) -> None:
    """Cheap first-pass brainstorm / exploration."""
    print(f"🤖 [Kimi] mode=draft  model={KIMI_MODEL}")
    print("─" * 60)

    system = (
        "Ты опытный архитектор. Набрось быстрый черновик решения — "
        "не нужен идеальный код, нужны идеи, варианты, trade-offs. "
        "Отвечай кратко (до 400 слов), по пунктам."
    )
    print(_call_kimi(system, task, "draft"))


def mode_migrate(path: str) -> None:
    """Analyze DB models and suggest safe migration steps."""
    project = _detect_project(path)
    print(f"🤖 [Kimi] mode=migrate  model={KIMI_MODEL}  path={path}")
    print("─" * 60)

    content = _collect_files(path, _MODE_TOKENS["migrate"] * 4)
    system = (
        f"Ты DBA + Python backend инженер. Проект: {project}\n"
        "Анализируй SQLAlchemy/SQLite/Odoo модели. "
        "Найди: недостающие колонки, несоответствия между моделью и БД, "
        "опасные миграции (ALTER TABLE без DEFAULT на NOT NULL), "
        "отсутствующие индексы. "
        "Предложи конкретные ALTER TABLE / Alembic шаги в правильном порядке."
    )
    user = f"Модели и схема:\n\n{content}"
    print(_call_kimi(system, user, "migrate"))


def mode_compare(task: str) -> None:
    """A/B comparison of two approaches."""
    print(f"🤖 [Kimi] mode=compare  model={KIMI_MODEL}")
    print("─" * 60)

    system = (
        "Ты технический консультант. Сравни предложенные подходы по критериям: "
        "производительность, поддерживаемость, риски, сложность реализации. "
        "Дай чёткую рекомендацию с обоснованием."
    )
    print(_call_kimi(system, task, "compare"))


def mode_council(question: str) -> None:
    """Architectural second opinion."""
    print(f"🤖 [Kimi] mode=council  model={KIMI_MODEL}")
    print("─" * 60)

    system = (
        "Ты независимый технический советник. Дай честное мнение об архитектурном решении. "
        "Укажи риски которые могут быть упущены. Будь краток и конкретен."
    )
    print(_call_kimi(system, question, "council"))


# ── Entry point ───────────────────────────────────────────────────────────────

USAGE = """
Использование: python3 kimi_client.py <mode> [аргумент]

Режимы:
  analyze <путь>     — полный анализ файла/директории (128K контекст)
  bulk    <файл>     — анализ больших логов / дампов
  draft   "задача"   — быстрый черновик / брейншторм (дешёво)
  migrate <путь>     — анализ схемы БД, предложение миграций
  compare "вопрос"   — сравнение двух подходов A/B
  council "вопрос"   — второе мнение по архитектурному решению
"""

MODE_MAP = {
    "analyze": mode_analyze,
    "bulk": mode_bulk,
    "draft": mode_draft,
    "migrate": mode_migrate,
    "compare": mode_compare,
    "council": mode_council,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODE_MAP:
        print(USAGE)
        sys.exit(1)

    mode = sys.argv[1]
    arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if not arg and mode in ("analyze", "bulk", "migrate", "draft", "compare", "council"):
        print(f"❌ Режим '{mode}' требует аргумент.\n{USAGE}")
        sys.exit(1)

    MODE_MAP[mode](arg)
