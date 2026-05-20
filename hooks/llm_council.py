#!/usr/bin/env python3
"""
LLM Council — sends the same question to Claude + Gemini and synthesizes.
Implements "llm-council" / "council" pattern for high-stakes decisions.

Usage:
  python3 hooks/llm_council.py "стоит ли использовать Redis или SQLite для FSM?"
  python3 hooks/llm_council.py --file question.md
  echo "вопрос" | python3 hooks/llm_council.py -
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
GEMINI_AGENT = REPO_ROOT / "hooks" / "gemini_agent.sh"
DECISIONS_MD = REPO_ROOT / "DECISIONS.md"
CLAUDE_BIN = Path("/root/.local/bin/claude")


def _ask_gemini(question: str) -> str:
    try:
        r = subprocess.run(
            ["bash", str(GEMINI_AGENT), "research", question],
            capture_output=True, text=True, timeout=90, cwd=str(REPO_ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else "[Gemini недоступен]"
    except Exception as e:
        return f"[Gemini ошибка: {e}]"


def _ask_claude(question: str) -> str:
    """Claude self-reflection via subprocess (headless)."""
    prompt = (
        f"Контекст: проект infrascan-ai (Odoo 19 + aiogram 3.x + Gemini Vision, VDS Ubuntu).\n"
        f"Ответь кратко (3-5 предложений) как старший инженер:\n\n{question}"
    )
    try:
        claude_path = CLAUDE_BIN if CLAUDE_BIN.exists() else "claude"
        r = subprocess.run(
            [str(claude_path), "--dangerously-skip-permissions", "-p", prompt],
            capture_output=True, text=True, timeout=60, cwd=str(REPO_ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else "[Claude headless недоступен]"
    except Exception as e:
        return f"[Claude ошибка: {e}]"


def _synthesize(question: str, claude_ans: str, gemini_ans: str) -> str:
    synth_q = (
        f"Два эксперта дали разные ответы на вопрос: '{question[:200]}'\n\n"
        f"Эксперт 1 (Claude): {claude_ans[:1500]}\n\n"
        f"Эксперт 2 (Gemini): {gemini_ans[:1500]}\n\n"
        f"Синтезируй: в чём согласны, в чём расходятся, какой вывод?"
    )
    return _ask_gemini(synth_q)


def council(question: str, save_to_decisions: bool = True) -> dict:
    import datetime

    print(f"⚖️  [LLM Council] Вопрос: {question[:100]}")
    print("🤖 Запрашиваю Claude...")
    claude_ans = _ask_claude(question)
    print("🔵 Запрашиваю Gemini...")
    gemini_ans = _ask_gemini(question)
    print("🔀 Синтезирую ответы...")
    synthesis = _synthesize(question, claude_ans, gemini_ans)

    result = {
        "question": question,
        "claude": claude_ans,
        "gemini": gemini_ans,
        "synthesis": synthesis,
    }

    if save_to_decisions and DECISIONS_MD.exists():
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n## LLM Council — {now}\n\n"
            f"**Вопрос:** {question}\n\n"
            f"**Claude:** {claude_ans[:500]}\n\n"
            f"**Gemini:** {gemini_ans[:500]}\n\n"
            f"**Синтез:** {synthesis[:500]}\n\n---\n"
        )
        with open(DECISIONS_MD, "a", encoding="utf-8") as f:
            f.write(entry)
        print("✅ Сохранено в DECISIONS.md")

    return result


def main() -> None:
    if len(sys.argv) > 1:
        if sys.argv[1] == "--file" and len(sys.argv) > 2:
            question = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
        elif sys.argv[1] == "-":
            question = sys.stdin.read().strip()
        else:
            question = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        question = sys.stdin.read().strip()
    else:
        print("Usage: python3 llm_council.py \"вопрос\"")
        sys.exit(1)

    result = council(question)
    print("\n" + "="*60)
    print("🔵 CLAUDE:")
    print(result["claude"])
    print("\n🤖 GEMINI:")
    print(result["gemini"])
    print("\n🔀 СИНТЕЗ:")
    print(result["synthesis"])


if __name__ == "__main__":
    main()
