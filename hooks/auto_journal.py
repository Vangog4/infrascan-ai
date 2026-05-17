#!/usr/bin/env python3
"""Stop hook: appends session-end marker to today's Logseq journal."""
import datetime
import json
import pathlib
import sys

today = datetime.date.today()
now_str = datetime.datetime.now().strftime("%H:%M")
journal_dir = pathlib.Path("/root/infrascan-ai/bot/logseq/journals")
journal_file = journal_dir / today.strftime("%Y_%m_%d.md")

# Try to extract stop reason from stdin (Claude Code Stop hook payload)
try:
    payload = json.load(sys.stdin)
    reason = payload.get("stop_reason", "")
except Exception:
    reason = ""

reason_line = f" ({reason})" if reason else ""
entry = f"\n## Сессия завершена — {now_str}{reason_line}\n- _Stop hook_\n"

if journal_file.exists():
    content = journal_file.read_text(encoding="utf-8")
    # Avoid duplicate entries within the same minute
    if f"Сессия завершена — {now_str}" not in content:
        journal_file.write_text(content + entry, encoding="utf-8")
else:
    journal_file.write_text(
        f"# {today.strftime('%Y-%m-%d')} — Журнал сессии\n{entry}",
        encoding="utf-8",
    )

print(f"✅ Журнал обновлён: {journal_file.name}")
