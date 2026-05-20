#!/usr/bin/env python3
"""
PreToolUse hook: SkillVetter — security audit of code before Write/Edit.
Checks for malware, RCE vectors, prompt injection, and hardcoded secrets.
Exit 2 = block (HIGH severity), exit 0 = allow (warn only for LOW/MEDIUM).
"""
import datetime
import json
import re
import sys
from pathlib import Path

# (regex_pattern, description, severity)  severity: HIGH=block, MED/LOW=warn
AUDIT_RULES: list[tuple[str, str, str]] = [
    # HIGH: RCE via eval/exec with user/request input
    (r"eval\s*\(\s*(input\s*\(|request\.|user_input|data\[|params\[|getattr)",
     "eval() с пользовательским вводом → RCE", "HIGH"),
    (r"exec\s*\(\s*(input\s*\(|request\.|user_input|data\[|params\[)",
     "exec() с пользовательским вводом → RCE", "HIGH"),
    # HIGH: shell injection via subprocess/os.system with f-string or concat
    (r"(subprocess\.(call|run|Popen)|os\.system)\s*\([^)]{0,100}(shell\s*=\s*True[^)]{0,60}f['\"]|f['\"][^)]+\{)",
     "shell injection: shell=True + f-строка", "HIGH"),
    (r"os\.system\s*\(\s*f['\"]",
     "os.system() с f-строкой → shell injection", "HIGH"),
    (r"os\.system\s*\([^)]{0,60}%\s*(s|r|d)\s*%",
     "os.system() с %-форматированием → shell injection", "HIGH"),
    # HIGH: obfuscated execution
    (r"base64\.(b64decode|decodebytes).{0,60}(exec|eval|compile)\s*\(",
     "base64 decode + exec → обфусцированное выполнение", "HIGH"),
    (r"compile\s*\(.{0,200}exec\s*\(",
     "compile() + exec() → обфускация кода", "HIGH"),
    # HIGH: prompt injection in instruction strings
    (r"(ignore\s+(previous|all\s+prior)|disregard\s+(all|previous)|system\s*:\s*you\s+are\s+now\s+|"
     r"act\s+as\s+if\s+you\s+are\s+a|forget\s+all\s+previous\s+instructions)",
     "prompt injection паттерн в тексте", "HIGH"),
    # MEDIUM: unsafe deserialization
    (r"pickle\.(loads|load)\s*\(",
     "pickle.loads() с неизвестным источником → RCE при небезопасных данных", "MED"),
    (r"yaml\.load\s*\([^)]+\)(?!\s*#.*safe)",
     "yaml.load() без Loader=yaml.SafeLoader", "MED"),
    (r"marshal\.loads\s*\(",
     "marshal.loads() → небезопасная десериализация", "MED"),
    # MEDIUM: subprocess without shell but with user input concat
    (r"subprocess\.(call|run|Popen)\s*\([^)]{0,80}\+\s*(user|request|input|param)",
     "subprocess с конкатенацией пользовательских данных", "MED"),
    # LOW: hardcoded credentials (not in .env files)
    (r'(?i)(password|passwd|secret_key|api_key|access_token|private_key)\s*=\s*["\'][^"\'$\{]{8,}["\']',
     "хардкод чувствительного значения — используй переменные окружения", "LOW"),
    # LOW: suspicious __import__
    (r"__import__\s*\(\s*[\"'](os|subprocess|sys|socket)[\"']",
     "__import__ для системного модуля — подозрительно", "LOW"),
]

LOG_FILE = Path("/tmp/skill_vetter.log")
CODE_EXTENSIONS = {".py", ".js", ".ts", ".sh", ".bash", ".mjs", ".cjs"}


def _log(level: str, path: str, reason: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {level} | {path} | {reason}\n")


def _is_code(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    ti = payload.get("tool_input", {})
    file_path: str = ti.get("file_path", ti.get("path", ""))

    if not file_path or not _is_code(file_path):
        return 0

    # Skip .env files for credential check (they're expected to have them)
    is_env = file_path.endswith(".env") or "/.env" in file_path

    content: str
    content = ti.get("content", "") if tool_name == "Write" else ti.get("new_string", "")

    if not content.strip():
        return 0

    high_findings: list[str] = []
    other_findings: list[str] = []

    for pattern, description, severity in AUDIT_RULES:
        if is_env and "хардкод" in description:
            continue
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            _log(severity, file_path, description)
            if severity == "HIGH":
                high_findings.append(description)
            else:
                other_findings.append(f"[{severity}] {description}")

    if not high_findings and not other_findings:
        return 0

    print(f"🔍 [SkillVetter] Аудит: {file_path}")

    for f in other_findings:
        print(f"  ⚠️  {f}")

    if high_findings:
        for f in high_findings:
            print(f"  🚨 [HIGH] {f}")
        print("\n⛔ [SkillVetter] Обнаружены уязвимости HIGH-уровня. Файл НЕ сохранён.")
        print("Устрани уязвимости перед записью файла на сервер.")
        return 2

    print("  → Предупреждения зафиксированы (не блокирующие). Продолжаю.")
    return 0


sys.exit(main())
