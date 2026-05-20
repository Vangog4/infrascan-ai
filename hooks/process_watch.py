#!/usr/bin/env python3
"""
Process Watch — monitors critical VDS processes and container health.
Implements: process-watch pattern.

Runs as a one-shot health check or as a daemon (--daemon flag).
Alerts via Telegram when critical services go down.

Usage:
  python3 hooks/process_watch.py           # one-shot health report
  python3 hooks/process_watch.py --daemon  # run every 5 min
  python3 hooks/process_watch.py --alert   # only report problems
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path("/root/infrascan-ai")
ENV_FILE = REPO_ROOT / "bot" / ".env"

CRITICAL_CONTAINERS = [
    "infrascan-ai_db",
    "infrascan-ai_web",
    "infrascan-ai_bot",
]

CRITICAL_PORTS = {
    8069: "Odoo",
    8072: "Odoo Longpolling",
    5432: "PostgreSQL",
}

CHECK_INTERVAL = 300  # 5 minutes


def _load_env() -> dict:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def _tg_send(token: str, admin_ids: list[int], text: str) -> None:
    if not token or not admin_ids:
        return
    for chat_id in admin_ids:
        try:
            data = json.dumps({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass


def check_containers() -> dict[str, str]:
    statuses = {}
    for name in CRITICAL_CONTAINERS:
        try:
            r = subprocess.run(
                ["podman", "inspect", name, "--format", "{{.State.Status}}"],
                capture_output=True, text=True, timeout=5,
            )
            statuses[name] = r.stdout.strip() if r.returncode == 0 else "missing"
        except Exception:
            statuses[name] = "error"
    return statuses


def check_ports() -> dict[int, bool]:
    import socket
    results = {}
    for port in CRITICAL_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                results[port] = True
        except Exception:
            results[port] = False
    return results


def check_disk() -> dict:
    try:
        r = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5,
        )
        lines = r.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            used_pct = int(parts[4].rstrip("%"))
            return {"total": parts[1], "used": parts[2], "free": parts[3], "pct": used_pct}
    except Exception:
        pass
    return {}


def check_memory() -> dict:
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                return {"total": parts[1], "used": parts[2], "free": parts[3]}
    except Exception:
        pass
    return {}


def run_check(alert_only: bool = False) -> list[str]:
    problems = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    if not alert_only:
        print(f"🔍 Process Watch — {now}")

    # Containers
    containers = check_containers()
    for name, status in containers.items():
        if status != "running":
            problems.append(f"🚨 Контейнер <b>{name}</b>: {status}")
            print(f"❌ {name}: {status}")
        elif not alert_only:
            print(f"✅ {name}: running")

    # Ports
    ports = check_ports()
    for port, ok in ports.items():
        svc = CRITICAL_PORTS[port]
        if not ok:
            problems.append(f"🚨 Порт {port} ({svc}) не отвечает")
            print(f"❌ Port {port} ({svc}): DOWN")
        elif not alert_only:
            print(f"✅ Port {port} ({svc}): open")

    # Disk
    disk = check_disk()
    if disk:
        pct = disk.get("pct", 0)
        if pct >= 95:
            problems.append(f"🚨 Диск заполнен на {pct}% (осталось {disk['free']})")
        elif pct >= 90:
            problems.append(f"⚠️ Диск заполнен на {pct}% (осталось {disk['free']})")
        if not alert_only:
            emoji = "❌" if pct >= 95 else ("⚠️" if pct >= 90 else "✅")
            print(f"{emoji} Disk: {pct}% used, {disk['free']} free")

    # Memory
    mem = check_memory()
    if mem and not alert_only:
        print(f"   Mem: {mem.get('used','?')}/{mem.get('total','?')} used")

    return problems


def daemon_mode() -> None:
    env = _load_env()
    token = env.get("BOT_TOKEN", "")
    admin_ids_raw = env.get("ADMIN_IDS", "[]")
    try:
        admin_ids = json.loads(admin_ids_raw)
    except Exception:
        admin_ids = []

    print(f"🤖 Process Watch daemon запущен (интервал: {CHECK_INTERVAL}s)")
    consecutive_problems: dict[str, int] = {}

    while True:
        problems = run_check(alert_only=True)

        if problems:
            for p in problems:
                key = p[:60]
                consecutive_problems[key] = consecutive_problems.get(key, 0) + 1
                if consecutive_problems[key] == 1:
                    now = datetime.datetime.now().strftime("%H:%M")
                    msg = f"🚨 <b>Process Watch</b> [{now}]\n\n" + "\n".join(problems)
                    _tg_send(token, admin_ids, msg)
                    print(f"⚠️  Alert sent: {p[:60]}")
        else:
            consecutive_problems.clear()

        time.sleep(CHECK_INTERVAL)


def main() -> None:
    alert_only = "--alert" in sys.argv
    daemon = "--daemon" in sys.argv

    if daemon:
        daemon_mode()
        return

    problems = run_check(alert_only=alert_only)

    if problems:
        print("\n🚨 ПРОБЛЕМЫ:")
        for p in problems:
            print(f"   {p}")
        sys.exit(1)
    elif not alert_only:
        print("\n✅ Все системы работают нормально")


if __name__ == "__main__":
    main()
