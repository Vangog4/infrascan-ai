#!/usr/bin/env python3
"""
Self-Improving Agent — reads DECISIONS.md error patterns and updates agent
instructions in CLAUDE.md to prevent recurring mistakes.

Implements: self-improving-agent + reflect + compound-engineering patterns.

Usage:
  python3 hooks/self_improving_agent.py          # analyze + patch CLAUDE.md
  python3 hooks/self_improving_agent.py --dry-run # show proposed changes only
  python3 hooks/self_improving_agent.py --reflect "what went wrong in this session"
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
DECISIONS_MD = REPO_ROOT / "DECISIONS.md"
GEMINI_AGENT = REPO_ROOT / "hooks" / "gemini_agent.sh"
LEARNINGS_SECTION = "## Learned Patterns (Auto-Updated)"


def _extract_error_patterns() -> list[str]:
    """Pull recurring error mentions from DECISIONS.md."""
    if not DECISIONS_MD.exists():
        return []
    text = DECISIONS_MD.read_text(encoding="utf-8")
    # Find bullet points describing problems/fixes
    patterns = []
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith(("❌", "⚠️", "- Проблема:", "- Error:", "### Fix:")):
            patterns.append(line_stripped[:200])
    return patterns[-20:]  # keep last 20 most recent


def _get_gemini_reflection(context: str) -> str:
    """Ask Gemini to extract actionable patterns from context."""
    try:
        result = subprocess.run(
            ["bash", str(GEMINI_AGENT), "research",
             f"Из этих записей ошибок извлеки 3-5 конкретных ПРАВИЛ для агента "
             f"(формат: '- Всегда/Никогда X когда Y'). Записи:\n{context[:3000]}"],
            capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _update_claude_md(rules: str, dry_run: bool = False) -> bool:
    """Append or update the Learned Patterns section in CLAUDE.md."""
    if not CLAUDE_MD.exists():
        return False

    content = CLAUDE_MD.read_text(encoding="utf-8")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_section = (
        f"\n{LEARNINGS_SECTION}\n"
        f"_Last updated: {now}_\n\n"
        f"{rules}\n"
    )

    if LEARNINGS_SECTION in content:
        # Replace existing section
        updated = re.sub(
            rf"{re.escape(LEARNINGS_SECTION)}.*?(?=\n## |\Z)",
            new_section.lstrip("\n"),
            content,
            flags=re.DOTALL,
        )
    else:
        updated = content + new_section

    if dry_run:
        print("--- DRY RUN: proposed CLAUDE.md addition ---")
        print(new_section)
        return True

    CLAUDE_MD.write_text(updated, encoding="utf-8")
    print(f"✅ CLAUDE.md обновлён ({LEARNINGS_SECTION})")
    return True


def reflect_on_session(prompt: str) -> str:
    """Quick reflection on a specific event / problem."""
    full_prompt = (
        f"Reflect кратко (3-5 bullet points): что именно пошло не так, "
        f"как избежать в будущем, какое правило вывести. "
        f"Событие: {prompt}"
    )
    try:
        result = subprocess.run(
            ["bash", str(GEMINI_AGENT), "research", full_prompt],
            capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        )
        return result.stdout.strip()
    except Exception as e:
        return f"reflect ошибка: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-improving agent")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reflect", metavar="EVENT",
                        help="Reflect on a specific event/problem")
    args = parser.parse_args()

    if args.reflect:
        result = reflect_on_session(args.reflect)
        print(result)
        # Append to DECISIONS.md
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## Reflect — {now}\n{result}\n\n---\n"
        with open(DECISIONS_MD, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"\n✅ Reflection сохранена в DECISIONS.md")
        return

    print("🧠 Self-Improving Agent: анализирую паттерны ошибок...")
    patterns = _extract_error_patterns()

    if not patterns:
        print("ℹ️  Нет записей ошибок в DECISIONS.md")
        return

    print(f"   Найдено паттернов: {len(patterns)}")
    context = "\n".join(patterns)

    print("🤖 Запрашиваю Gemini для извлечения правил...")
    rules = _get_gemini_reflection(context)

    if not rules:
        print("⚠️  Gemini не вернул правила")
        return

    print("📝 Предложенные правила:")
    print(rules)
    print()

    _update_claude_md(rules, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
