#!/usr/bin/env python3
"""
LLM Observability Tracker — lightweight SQLite-based call logger.
Tracks all Gemini and Claude calls: model, tokens, latency, task type.

Usage (as library):
  from hooks.llm_tracker import track_call, get_stats

Usage (as MCP-style log endpoint):
  python3 llm_tracker.py log --model gemini-2.5-flash --tokens 1200 --task review
  python3 llm_tracker.py stats
  python3 llm_tracker.py report
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("/root/infrascan-ai/logs/llm_calls.db")
LOG_DIR = DB_PATH.parent


def _init_db() -> sqlite3.Connection:
    LOG_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            model     TEXT NOT NULL,
            engine    TEXT NOT NULL,
            task_type TEXT,
            mode      TEXT,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            latency_ms INTEGER DEFAULT 0,
            success   INTEGER DEFAULT 1,
            notes     TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date      TEXT PRIMARY KEY,
            total_calls INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            gemini_calls INTEGER DEFAULT 0,
            claude_calls INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def track_call(
    model: str,
    engine: str = "gemini",
    task_type: str = "",
    mode: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    success: bool = True,
    notes: str = "",
) -> int:
    conn = _init_db()
    ts = datetime.datetime.now().isoformat()
    today = ts[:10]
    cur = conn.execute(
        """INSERT INTO calls (ts, model, engine, task_type, mode, tokens_in, tokens_out,
                              latency_ms, success, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (ts, model, engine, task_type, mode, tokens_in, tokens_out,
         latency_ms, int(success), notes),
    )
    call_id = cur.lastrowid
    total_tokens = tokens_in + tokens_out
    conn.execute("""
        INSERT INTO daily_stats (date, total_calls, total_tokens,
            gemini_calls, claude_calls, errors)
        VALUES (?, 1, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            total_calls = total_calls + 1,
            total_tokens = total_tokens + excluded.total_tokens,
            gemini_calls = gemini_calls + excluded.gemini_calls,
            claude_calls = claude_calls + excluded.claude_calls,
            errors = errors + excluded.errors
    """, (today, total_tokens,
          1 if engine == "gemini" else 0,
          1 if engine == "claude" else 0,
          0 if success else 1))
    conn.commit()
    conn.close()
    return call_id


@contextmanager
def timed_call(model: str, engine: str = "gemini", **kwargs):
    """Context manager that auto-measures latency."""
    start = time.monotonic()
    try:
        yield
        latency_ms = int((time.monotonic() - start) * 1000)
        track_call(model=model, engine=engine, latency_ms=latency_ms,
                   success=True, **kwargs)
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        track_call(model=model, engine=engine, latency_ms=latency_ms,
                   success=False, notes=str(e)[:200], **kwargs)
        raise


def get_stats(days: int = 7) -> dict:
    conn = _init_db()
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM daily_stats WHERE date >= ? ORDER BY date DESC", (cutoff,)
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*), SUM(tokens_in+tokens_out), SUM(latency_ms)/COUNT(*) FROM calls WHERE ts >= ?",
        (cutoff + "T00:00:00",)
    ).fetchone()
    conn.close()
    return {
        "days": days,
        "daily": [dict(zip(["date","calls","tokens","gemini","claude","errors"], r, strict=False)) for r in rows],
        "total_calls": total[0] or 0,
        "total_tokens": total[1] or 0,
        "avg_latency_ms": total[2] or 0,
    }


def print_report() -> None:
    stats = get_stats(30)
    print("📊 LLM Usage — last 30 days")
    print(f"   Total calls : {stats['total_calls']}")
    print(f"   Total tokens: {stats['total_tokens']:,}")
    print(f"   Avg latency : {stats['avg_latency_ms']}ms")
    print()
    print(f"{'Date':12} {'Calls':>6} {'Tokens':>8} {'Gemini':>7} {'Claude':>7} {'Errors':>6}")
    for d in stats["daily"]:
        print(f"{d['date']:12} {d['calls']:>6} {d['tokens']:>8,} {d['gemini']:>7} {d['claude']:>7} {d['errors']:>6}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM call tracker")
    sub = parser.add_subparsers(dest="cmd")

    log_p = sub.add_parser("log")
    log_p.add_argument("--model", default="gemini-2.5-flash")
    log_p.add_argument("--engine", default="gemini")
    log_p.add_argument("--task", default="")
    log_p.add_argument("--mode", default="")
    log_p.add_argument("--tokens-in", type=int, default=0)
    log_p.add_argument("--tokens-out", type=int, default=0)
    log_p.add_argument("--latency", type=int, default=0)
    log_p.add_argument("--error", action="store_true")

    sub.add_parser("stats")
    sub.add_parser("report")

    args = parser.parse_args()

    if args.cmd == "log":
        call_id = track_call(
            model=args.model, engine=args.engine,
            task_type=args.task, mode=args.mode,
            tokens_in=args.tokens_in, tokens_out=args.tokens_out,
            latency_ms=args.latency, success=not args.error,
        )
        print(f"✅ Logged call #{call_id}")
    elif args.cmd == "stats":
        print(json.dumps(get_stats(), ensure_ascii=False, indent=2))
    elif args.cmd == "report":
        print_report()
    else:
        print_report()


if __name__ == "__main__":
    main()
