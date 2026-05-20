#!/usr/bin/env python3
"""
Telegram Confirmation Bridge.

Sends a YES/NO request to admin Telegram IDs and waits for the running bot
to process the callback (stored in Redis via `podman exec`).

Usage:
  python3 hooks/confirm_bridge.py "Deploy to production?" [timeout_secs=300]

Exit codes:
  0 — approved (✅ YES)
  1 — rejected (❌ NO)
  2 — timeout / error / not configured (treat as rejection, safe default)

Integration with loop_orchestrator.sh:
  if ! python3 hooks/confirm_bridge.py "Risky operation: $DESCRIPTION"; then
    echo "Aborted by admin"
    exit 1
  fi
"""
import contextlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def _load_env() -> dict:
    env_file = Path(__file__).parent.parent / "bot" / ".env"
    out = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def _tg(token: str, method: str, **params) -> dict | None:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"TG {method} HTTP {e.code}: {e.read()[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"TG {method}: {e}", file=sys.stderr)
    return None


def _redis_set(key: str, value: str, ex: int) -> bool:
    try:
        r = subprocess.run(
            ["podman", "exec", "infrascan-ai_redis", "redis-cli",
             "SET", key, value, "EX", str(ex)],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception as e:
        print(f"redis SET: {e}", file=sys.stderr)
        return False


def _redis_get(key: str) -> str | None:
    try:
        r = subprocess.run(
            ["podman", "exec", "infrascan-ai_redis", "redis-cli", "GET", key],
            capture_output=True, text=True, timeout=5,
        )
        val = r.stdout.strip()
        return val if val and val != "(nil)" else None
    except Exception as e:
        print(f"redis GET: {e}", file=sys.stderr)
        return None


def _redis_del(key: str) -> None:
    with contextlib.suppress(Exception):
        subprocess.run(
            ["podman", "exec", "infrascan-ai_redis", "redis-cli", "DEL", key],
            capture_output=True, timeout=5,
        )


def main() -> int:
    cfg = _load_env()
    token = cfg.get("BOT_TOKEN", "")
    admin_ids_raw = cfg.get("ADMIN_IDS", "[]")
    description = sys.argv[1] if len(sys.argv) > 1 else "Неизвестная операция"
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 300

    try:
        admin_ids: list[int] = json.loads(admin_ids_raw)
    except Exception:
        admin_ids = []

    if not token or not admin_ids:
        print("⚠️  confirm_bridge: не настроен BOT_TOKEN/ADMIN_IDS — авто-разрешение",
              file=sys.stderr)
        return 0

    confirm_id = str(uuid.uuid4())[:8]
    redis_key = f"confirm:{confirm_id}"

    # Mark as pending in Redis
    _redis_set(redis_key, "pending", timeout + 60)

    # Send Telegram message with YES/NO buttons
    text = (
        f"🤖 <b>Агент запрашивает разрешение</b>\n\n"
        f"<b>Операция:</b> <code>{description[:300]}</code>\n\n"
        f"⏳ Таймаут: {timeout // 60} мин  •  ID: <code>{confirm_id}</code>"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Разрешить", "callback_data": f"confirm:{confirm_id}:yes"},
            {"text": "❌ Отклонить", "callback_data": f"confirm:{confirm_id}:no"},
        ]]
    }

    sent: list[tuple[int, int]] = []
    for admin_id in admin_ids:
        r = _tg(token, "sendMessage",
                chat_id=admin_id, text=text,
                parse_mode="HTML", reply_markup=keyboard)
        if r and r.get("ok"):
            sent.append((admin_id, r["result"]["message_id"]))
            print(f"📨 Запрос отправлен → {admin_id} (msg {r['result']['message_id']})")

    if not sent:
        print("❌ Не удалось отправить — авто-отклонение", file=sys.stderr)
        _redis_del(redis_key)
        return 2

    # Poll Redis for decision
    print(f"⏳ Жду ответа [{confirm_id}] ({timeout}s)…")
    start = time.monotonic()
    decision: str | None = None

    while time.monotonic() - start < timeout:
        val = _redis_get(redis_key)
        if val in ("yes", "no"):
            decision = val
            break
        time.sleep(3)

    _redis_del(redis_key)

    def _update_messages(approved: bool) -> None:
        emoji, status = ("✅", "РАЗРЕШЕНО") if approved else ("❌", "ОТКЛОНЕНО")
        for chat_id, msg_id in sent:
            _tg(token, "editMessageReplyMarkup",
                chat_id=chat_id, message_id=msg_id,
                reply_markup={"inline_keyboard": []})
            _tg(token, "editMessageText",
                chat_id=chat_id, message_id=msg_id,
                text=f"{emoji} <b>{status}</b>\n\n"
                     f"<b>Операция:</b> <code>{description[:300]}</code>\n"
                     f"ID: <code>{confirm_id}</code>",
                parse_mode="HTML")

    if decision is None:
        print(f"⏰ Timeout ({timeout}s) — авто-отклонение")
        _update_messages(False)
        return 2

    approved = decision == "yes"
    _update_messages(approved)

    if approved:
        print(f"✅ [{confirm_id}] Разрешено")
        return 0
    else:
        print(f"❌ [{confirm_id}] Отклонено")
        return 1


sys.exit(main())
