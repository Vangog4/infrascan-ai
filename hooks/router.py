#!/usr/bin/env python3
"""
Agent Router: Smart routing brain for Claude ↔ Gemini delegation.

Analyzes the task context and decides which engine handles it,
implementing lazy loading — Gemini is only invoked when genuinely needed.

Usage (stdin JSON):
  echo '{"task": "review thermal images", "files": []}' | python3 router.py

Usage (CLI):
  python3 router.py "проведи code review всего проекта"

Output JSON:
  {"engine": "claude|gemini", "mode": "...", "reason": "...", "cmd": "..."}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
GEMINI_AGENT = REPO_ROOT / "hooks" / "gemini_agent.sh"
LARGE_FILE_BYTES = 8_000   # files above this → Gemini (2M context)
LARGE_TOTAL_BYTES = 20_000 # total context above this → Gemini

# Routing rules: (keywords_list, gemini_mode, reason, priority)
# Higher priority = evaluated first
ROUTES: list[tuple[list[str], str, str, int]] = [
    # Vision / thermal analysis — Gemini Vision
    (["image", "photo", "фото", "изображен", "термограмм", "thermal", "картинк",
      "скриншот", "screenshot", "vision", "виден", "снимк", "тепловизор",
      "тепловы", "тепловой", "визуальн"],
     "analyze", "мультимодальная задача → Gemini Vision API", 10),

    # Web research / latest docs — Gemini has internet access
    (["research", "найди в интернете", "погугли", "web search", "latest", "актуальн",
      "поищи онлайн", "документаци", "новост", "changelog"],
     "research", "нужен веб-поиск → Gemini (доступ к интернету)", 9),

    # Security / Red Team — Gemini as adversarial reviewer
    (["уязвимост", "security audit", "exploit", "red team", "pentest",
      "injection", "CVE", "вектор атаки", "безопасность кода"],
     "redteam", "security аудит → Gemini Red Team режим", 8),

    # Large-scale code review — Gemini 2M context window
    (["code review", "проверь весь", "ревью всего", "полный анализ",
      "all files", "весь проект", "весь репозиторий"],
     "review", "широкое ревью → окно Gemini 2M токенов", 7),

    # System health check
    (["health check", "состояние системы", "проверка стека", "диагностик",
      "работают ли контейнеры", "статус сервисов"],
     "health", "диагностика системы → Gemini health анализ", 6),
]

# These keywords keep task with Claude regardless of other matches
CLAUDE_OVERRIDE = [
    "быстрое исправление", "quick fix", "опечатк", "typo", "rename",
    "config", "конфиг", "настройка строки", "поменяй строку",
]


def _total_file_size(files: list[str]) -> int:
    total = 0
    for p in files:
        try:
            total += Path(p).stat().st_size
        except Exception:
            pass
    return total


def route(task: str, files: list[str] | None = None) -> dict:
    task_lower = task.lower()
    files = files or []

    # Override: force Claude for trivial local edits
    if any(kw in task_lower for kw in CLAUDE_OVERRIDE):
        return {
            "engine": "claude",
            "mode": "direct",
            "reason": "мелкая правка — нет смысла делегировать",
            "cmd": None,
        }

    # Large file context: delegate to Gemini
    total_size = _total_file_size(files)
    if total_size > LARGE_TOTAL_BYTES:
        cmd = f"bash {GEMINI_AGENT} analyze '{' '.join(files)}'"
        return {
            "engine": "gemini",
            "mode": "analyze",
            "reason": f"большой контекст ({total_size // 1024}KB) → Gemini 2M токенов",
            "cmd": cmd,
        }
    for f in files:
        try:
            if Path(f).stat().st_size > LARGE_FILE_BYTES:
                cmd = f"bash {GEMINI_AGENT} analyze '{f}'"
                return {
                    "engine": "gemini",
                    "mode": "analyze",
                    "reason": f"большой файл {Path(f).name} → Gemini 2M токенов",
                    "cmd": cmd,
                }
        except Exception:
            pass

    # Keyword-based routing (highest priority wins)
    best: tuple[int, str, str] | None = None
    for keywords, mode, reason, priority in ROUTES:
        for kw in keywords:
            if kw in task_lower:
                if best is None or priority > best[0]:
                    best = (priority, mode, reason)
                break

    if best:
        _, mode, reason = best
        # Build actual command for the caller
        if mode == "research":
            cmd = f"bash {GEMINI_AGENT} research '{task[:200]}'"
        elif mode == "health":
            cmd = f"bash {GEMINI_AGENT} health"
        else:
            cmd = f"bash {GEMINI_AGENT} {mode}"
        return {"engine": "gemini", "mode": mode, "reason": reason, "cmd": cmd}

    # Default: Claude
    return {
        "engine": "claude",
        "mode": "direct",
        "reason": "стандартная задача — обрабатывает Claude напрямую",
        "cmd": None,
    }


def main() -> None:
    # CLI args take priority — stdin may be a non-tty pipe in hook context
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        files = []
    elif not sys.stdin.isatty():
        try:
            data = json.loads(sys.stdin.read())
            task = data.get("task", "")
            files = data.get("files", [])
        except Exception:
            task = ""
            files = []
    else:
        print(json.dumps({
            "engine": "claude", "mode": "direct",
            "reason": "нет задачи", "cmd": None
        }, ensure_ascii=False))
        return

    result = route(task, files)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
