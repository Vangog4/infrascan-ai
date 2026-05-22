#!/usr/bin/env python3
"""
Agent Router — три движка: Claude | Gemini | Kimi.

Иерархия:
  1. Claude override (быстрые локальные правки — всегда Claude)
  2. Gemini  (Vision, Web, Security, Code Review — специалист)
  3. Kimi    (128K контекст, логи, черновики, миграции — тяжёлые задачи)
  4. Claude  (всё остальное по умолчанию)

Usage:
  echo '{"task": "review thermal images"}' | python3 router.py
  python3 router.py "проведи code review всего проекта"

Output JSON:
  {"engine": "claude|gemini|kimi", "mode": "...", "reason": "...", "cmd": "..."}
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
GEMINI_AGENT = REPO_ROOT / "hooks" / "gemini_agent.sh"
KIMI_AGENT   = REPO_ROOT / "hooks" / "kimi_agent.sh"

LARGE_FILE_BYTES  = 8_000
HUGE_FILE_BYTES   = 50_000
LARGE_TOTAL_BYTES = 20_000
HUGE_TOTAL_BYTES  = 80_000

GEMINI_ROUTES: list[tuple[list[str], str, str, int]] = [
    (["image", "photo", "фото", "изображен", "термограмм", "thermal",
      "картинк", "скриншот", "screenshot", "vision", "тепловизор",
      "тепловой снимок", "инфракрасн"],
     "analyze", "мультимодальная задача → Gemini Vision", 10),
    (["research", "найди в интернете", "погугли", "web search", "latest",
      "актуальн", "поищи онлайн", "changelog", "odoo docs", "документаци",
      "новост", "что нового", "release notes"],
     "research", "веб-поиск → Gemini (интернет-доступ)", 9),
    (["уязвимост", "security audit", "exploit", "red team", "pentest",
      "injection", "cve", "вектор атаки", "безопасность кода",
      "xss", "ssrf", "rce", "prompt injection"],
     "redteam", "security аудит → Gemini Red Team", 8),
    (["code review", "проверь диф", "ревью диф", "review diff",
      "проверь изменения", "что изменилось", "перед коммитом"],
     "review", "code review diff → Gemini", 7),
    (["health check", "состояние системы", "диагностик", "проверка стека",
      "статус контейнеров", "статус сервисов", "всё ли работает"],
     "health", "диагностика стека → Gemini health", 6),
    (["ретроспектив", "retrospective", "итог сессии", "что сделано за сессию"],
     "retrospective", "ретроспектива → Gemini", 5),
]

KIMI_ROUTES: list[tuple[list[str], str, str, int]] = [
    (["весь репо", "full codebase", "all files", "все файлы", "весь код",
      "весь проект целиком", "все хандлеры", "все модели", "полный репозиторий",
      "скорми весь", "загрузи весь"],
     "analyze", "весь репо → Kimi 128K контекст", 9),
    (["log", "logs", "лог", "логи", "dump", "дамп", "traceback",
      "stacktrace", "journal", "история запросов", "ошибки за неделю",
      "ошибки за месяц", "bot.log", "access.log"],
     "bulk", "анализ логов → Kimi bulk режим", 8),
    (["миграци", "migration", "schema", "схема бд", "alter table",
      "добавь колонку", "alembic", "sqlalchemy модели", "недостающие колонки",
      "структура бд", "проверь модели"],
     "migrate", "анализ схемы БД → Kimi migrate", 7),
    (["сравни подходы", "compare", "a/b", "что лучше", "какой вариант",
      "два варианта", "плюсы и минусы", "trade-off"],
     "compare", "сравнение вариантов → Kimi compare", 5),
    (["второе мнение", "council", "посоветуй", "как лучше архитектурно",
      "что думаешь о решении", "стоит ли использовать"],
     "council", "архитектурный совет → Kimi council", 5),
    (["черновик", "draft", "набросок", "идея для", "предложи варианты",
      "пробный вариант", "explore", "поэкспериментируй", "а что если"],
     "draft", "черновое исследование → Kimi (дёшево)", 4),
]

CLAUDE_OVERRIDE = [
    "быстрое исправление", "quick fix", "опечатк", "typo",
    "rename", "поменяй строку", "исправь строку",
    "config", "конфиг", "добавь строку", "удали строку",
    "git commit", "git add", "закоммить",
]


def _total_file_size(files: list[str]) -> int:
    total = 0
    for p in files:
        with contextlib.suppress(Exception):
            total += Path(p).stat().st_size
    return total


def route(task: str, files: list[str] | None = None) -> dict:
    task_lower = task.lower()
    files = files or []

    if any(kw in task_lower for kw in CLAUDE_OVERRIDE):
        return {"engine": "claude", "mode": "direct",
                "reason": "быстрая правка → Claude (override)", "cmd": None}

    file_size = _total_file_size(files)
    if file_size > HUGE_FILE_BYTES:
        return {"engine": "kimi", "mode": "analyze",
                "reason": f"файл {file_size//1024}KB → Kimi 128K",
                "cmd": f"bash {KIMI_AGENT} analyze '{files[0]}'"}
    if file_size > LARGE_FILE_BYTES:
        return {"engine": "gemini", "mode": "analyze",
                "reason": f"файл {file_size//1024}KB → Gemini 2M",
                "cmd": f"bash {GEMINI_AGENT} analyze '{files[0]}'"}

    gemini_best: tuple[int, str, str] | None = None
    for keywords, mode, reason, priority in GEMINI_ROUTES:
        for kw in keywords:
            if kw in task_lower:
                if gemini_best is None or priority > gemini_best[0]:
                    gemini_best = (priority, mode, reason)
                break

    kimi_best: tuple[int, str, str] | None = None
    for keywords, mode, reason, priority in KIMI_ROUTES:
        for kw in keywords:
            if kw in task_lower:
                if kimi_best is None or priority > kimi_best[0]:
                    kimi_best = (priority, mode, reason)
                break

    if gemini_best and kimi_best:
        winner = "gemini" if gemini_best[0] >= kimi_best[0] else "kimi"
    elif gemini_best:
        winner = "gemini"
    elif kimi_best:
        winner = "kimi"
    else:
        winner = "claude"

    if winner == "gemini":
        _, mode, reason = gemini_best  # type: ignore[misc]
        cmd_map = {"research": f"bash {GEMINI_AGENT} research '{task[:200]}'",
                   "health": f"bash {GEMINI_AGENT} health"}
        return {"engine": "gemini", "mode": mode, "reason": reason,
                "cmd": cmd_map.get(mode, f"bash {GEMINI_AGENT} {mode}")}

    if winner == "kimi":
        _, mode, reason = kimi_best  # type: ignore[misc]
        arg = (files[0] if files and mode in ("analyze", "bulk", "migrate")
               else f'"{task[:200]}"')
        return {"engine": "kimi", "mode": mode, "reason": reason,
                "cmd": f"bash {KIMI_AGENT} {mode} {arg}"}

    return {"engine": "claude", "mode": "direct",
            "reason": "стандартная задача → Claude", "cmd": None}


def main() -> None:
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        files: list[str] = []
    elif not sys.stdin.isatty():
        try:
            data = json.loads(sys.stdin.read())
            task = data.get("task", "")
            files = data.get("files", [])
        except Exception:
            task = ""
            files = []
    else:
        print(json.dumps({"engine": "claude", "mode": "direct",
                          "reason": "нет задачи", "cmd": None}, ensure_ascii=False))
        return
    print(json.dumps(route(task, files), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
