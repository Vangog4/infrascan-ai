#!/usr/bin/env python3
"""
PreToolUse hook: Safety Guard for Bash commands.
Intercepts destructive shell commands before Gemini or Claude executes them.
Exit 2 = block execution, exit 0 = allow.
"""
import datetime
import json
import re
import sys
from pathlib import Path

# Patterns that BLOCK execution (exit 2)
BLOCK_RULES: list[tuple[str, str]] = [
    # Recursive delete from root or critical dirs
    (r"\brm\b.{0,30}-[a-z]*r[a-z]*\s+/(?!\w)", "rm -r от корня /"),
    (r"\brm\b.{0,30}-[a-z]*r[a-z]*.{0,30}\s+/(etc|boot|bin|sbin|usr|lib|var|sys|proc|dev)/?(\s|$)",
     "rm -r от критичного каталога"),
    (r"\brm\b.{0,30}-[a-z]*r[a-z]*.{0,30}~/?(\s|$)", "rm -r от домашней директории"),
    # Fork bomb
    (r":\s*\(\s*\)\s*\{", "fork bomb"),
    # Direct disk write
    (r"\bdd\b.{0,60}of=/dev/(sd|hd|nvme|vd|xvd)\w", "прямая запись на физический диск"),
    (r"\bmkfs\b.{0,60}/dev/", "форматирование блочного устройства"),
    (r"\bshred\b.{0,60}/dev/", "уничтожение данных на диске"),
    # Critical system file overwrite
    (r">\s*/etc/(passwd|shadow|sudoers|fstab|crontab|hosts)(\s|$)", "перезапись критичного /etc файла"),
    (r">\s*/(boot|bin|sbin)/", "перезапись системного файла"),
    # chmod/chown recursive on root
    (r"\bchmod\b.{0,20}-R.{0,20}[0-7]*7{2,}\s+/(?!\w)", "chmod 777 от корня"),
    (r"\bchown\b.{0,20}-R.{0,20}\s+/(?!\w)", "chown -R от корня"),
    # Kill systemd/init
    (r"\bkill\b.{0,10}-9\s+1\b", "kill -9 PID 1 (systemd/init)"),
    (r"\bkillall\b.{0,10}(systemd|init)\b", "killall systemd"),
    # Truncate/wipe critical files
    (r"truncate.{0,30}/etc/(passwd|shadow|fstab|sudoers)", "truncate критичного файла"),
    # Dangerous sysctl
    (r"sysctl.{0,30}kernel\.sysrq\s*=\s*1", "включение SysRq"),
]

# Patterns that WARN but don't block
WARN_RULES: list[tuple[str, str]] = [
    (r"\bsystemctl\s+(stop|disable|mask)\s+(ssh|sshd|networking)", "остановка критичного сервиса"),
    (r"\biptables\s+-F\b", "сброс всех правил iptables"),
    (r"\bufw\s+disable\b", "отключение UFW firewall"),
    (r"\bpasswd\s+root\b", "смена пароля root"),
    (r"\bsudo\s+su\b", "переключение на root через sudo"),
    (r"git\s+(push\s+--force|reset\s+--hard\s+HEAD~[2-9])", "опасная git-операция"),
    (r"\bpodman\s+(system\s+prune\s+-a|rmi\s+--all)", "удаление всех контейнеров/образов"),
]

LOG_FILE = Path("/tmp/safety_guard.log")


def _log(level: str, reason: str, cmd: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {level} | {reason} | {cmd[:300]}\n")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    cmd: str = payload.get("tool_input", {}).get("command", "")
    if not cmd:
        return 0

    # Check BLOCK patterns
    for pattern, reason in BLOCK_RULES:
        if re.search(pattern, cmd, re.IGNORECASE | re.DOTALL):
            _log("BLOCK", reason, cmd)
            print(f"⛔ [Safety Guard] ЗАБЛОКИРОВАНО: {reason}")
            print(f"   Команда: {cmd[:300]}")
            print("\n💡 Если операция необходима — запроси явное подтверждение через confirm_bridge.py")
            return 2

    # Check WARN patterns
    for pattern, reason in WARN_RULES:
        if re.search(pattern, cmd, re.IGNORECASE | re.DOTALL):
            _log("WARN", reason, cmd)
            print(f"⚠️  [Safety Guard] ВНИМАНИЕ: {reason}")
            print(f"   Команда: {cmd[:200]}")
            break  # one warning is enough

    return 0


sys.exit(main())
