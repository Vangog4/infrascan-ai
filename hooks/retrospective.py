#!/usr/bin/env python3
"""
Stop hook: Compound Engineering retrospective.

Triggered after each Claude session ends (Stop event).
If git diff is non-empty → runs Gemini Red Team review and
appends findings to DECISIONS.md for long-term knowledge accumulation.

Designed to be lightweight: skips Gemini call if no changes detected.
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
DECISIONS_FILE = REPO_ROOT / "DECISIONS.md"
GEMINI_AGENT = REPO_ROOT / "hooks" / "gemini_agent.sh"
MAX_DIFF_LINES = 400  # don't feed huge diffs to Gemini


def _git_diff_stat() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _git_diff_short() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "HEAD",
             "--unified=2", "--no-color"],
            capture_output=True, text=True, timeout=10,
        )
        lines = r.stdout.splitlines()
        if len(lines) > MAX_DIFF_LINES:
            lines = lines[:MAX_DIFF_LINES] + [f"… (truncated, {len(lines)} total lines)"]
        return "\n".join(lines)
    except Exception:
        return ""


def _gemini_review() -> str:
    try:
        r = subprocess.run(
            ["bash", str(GEMINI_AGENT), "review"],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _append_decisions(stat: str, review: str) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## Retrospective — {now}\n\n"
        f"### Изменения в сессии\n```\n{stat}\n```\n\n"
        f"### Gemini Red Team Review\n{review or '_Gemini review недоступен_'}\n\n---\n"
    )
    if DECISIONS_FILE.exists():
        existing = DECISIONS_FILE.read_text(encoding="utf-8")
        # Avoid duplicate entry within same minute
        if f"Retrospective — {now}" not in existing:
            DECISIONS_FILE.write_text(existing + entry, encoding="utf-8")
    else:
        DECISIONS_FILE.write_text(
            f"# DECISIONS — Ретроспективы\n{entry}", encoding="utf-8"
        )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}

    stat = _git_diff_stat()
    if not stat:
        # No changes — skip Gemini to conserve tokens
        return 0

    changed_files = [
        line.split("|")[0].strip()
        for line in stat.splitlines()
        if "|" in line
    ]
    print(f"🔍 [Retrospective] Изменено файлов: {len(changed_files)}")
    for f in changed_files[:5]:
        print(f"   · {f}")
    if len(changed_files) > 5:
        print(f"   … и ещё {len(changed_files) - 5}")

    print("🤖 [Retrospective] Запускаю Gemini Red Team review…")
    review = _gemini_review()

    _append_decisions(stat, review)

    if review:
        print("✅ [Retrospective] Анализ записан в DECISIONS.md")
    else:
        print("⚠️  [Retrospective] Gemini недоступен — stat записан без review")

    return 0


sys.exit(main())
