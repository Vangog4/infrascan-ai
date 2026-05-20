#!/usr/bin/env python3
"""
PostToolUse hook: stuck detection.

Tracks the last N tool calls. If the same failure signature repeats
>= STUCK_THRESHOLD times in the window → print guidance and exit 2,
forcing the agent to change its approach before continuing.

State is stored in /tmp/infrascan_stuck_state.json (session-scoped).
"""
import hashlib
import json
import sys
from pathlib import Path

STUCK_THRESHOLD = 3
WINDOW = 12
STATE_FILE = Path("/tmp/infrascan_stuck_state.json")


def _load() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"history": []}


def _save(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def _sig(payload: dict) -> str:
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input", {})
    resp = payload.get("tool_response", {})

    # Primary key depends on tool
    if tool == "Bash":
        key = inp.get("command", "")[:250]
    elif tool in ("Edit", "Write"):
        key = inp.get("file_path", inp.get("path", ""))
    elif tool == "WebFetch":
        key = inp.get("url", "")
    else:
        key = json.dumps(inp, sort_keys=True)[:200]

    # Error tail (last 300 chars of output)
    err = ""
    if isinstance(resp, dict):
        raw = resp.get("output") or resp.get("stdout") or resp.get("error") or ""
        err = str(raw)[-300:]

    return hashlib.md5(f"{tool}|{key}|{err}".encode()).hexdigest()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Only track failed calls (exit_code != 0 or error present)
    resp = payload.get("tool_response", {})
    if isinstance(resp, dict):
        exit_code = resp.get("exit_code", 0)
        has_error = bool(resp.get("error") or resp.get("stderr"))
        if exit_code == 0 and not has_error:
            sys.exit(0)

    sig = _sig(payload)
    state = _load()
    history: list = state.get("history", [])
    history.append(sig)
    history = history[-WINDOW:]
    state["history"] = history
    _save(state)

    count = history.count(sig)
    if count >= STUCK_THRESHOLD:
        tool = payload.get("tool_name", "?")
        print(f"\n🚫 STUCK [{tool}]: одна и та же ошибка повторяется {count} раз.")
        print("━━━ Обязательно смени подход ━━━")
        print("  • Попробуй другой инструмент или команду")
        print("  • Разбей задачу на более мелкие шаги")
        print("  • Проверь исходные предположения — возможно, условие изменилось")
        print("  • Если это тест — посмотри на другой тест или упрости проверку")
        print(f"  [sig: {sig[:8]}…]")
        # Reset to avoid repeated blocking on same sig
        state["history"] = [s for s in history if s != sig]
        _save(state)
        sys.exit(2)


main()
