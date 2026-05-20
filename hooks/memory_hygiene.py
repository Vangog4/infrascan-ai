#!/usr/bin/env python3
"""
memory_hygiene.py — прореживает долгосрочную память Claude.

Запуск: python3 hooks/memory_hygiene.py [--dry-run]

Что делает:
- Читает все .md файлы в ~/.claude/projects/-root/memory/
- Находит дубликаты по смыслу (точное совпадение ключевых слов)
- Находит устаревшие записи (project/feedback старше 90 дней без обновления)
- Выводит отчёт; без --dry-run предлагает удалить/смержить
"""
import argparse
import hashlib
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude/projects/-root/memory"
STALE_DAYS = 90


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.+?)\n---", text, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def content_hash(text: str) -> str:
    body = re.sub(r"^---\n.+?\n---\n", "", text, flags=re.DOTALL)
    normalized = re.sub(r"\s+", " ", body.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()


def get_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime)


def run(dry_run: bool) -> None:
    if not MEMORY_DIR.exists():
        print(f"Memory dir not found: {MEMORY_DIR}")
        sys.exit(1)

    files = [f for f in MEMORY_DIR.glob("*.md") if f.name != "MEMORY.md"]
    if not files:
        print("No memory files found.")
        return

    print(f"Scanning {len(files)} memory files in {MEMORY_DIR}\n")

    hashes: dict[str, Path] = {}
    issues: list[str] = []
    duplicates: list[tuple[Path, Path]] = []
    stale: list[Path] = []
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)

    for f in sorted(files):
        text = f.read_text()
        meta = parse_frontmatter(text)
        mtype = meta.get("type", "unknown")
        h = content_hash(text)
        mtime = get_mtime(f)

        # Duplicate detection
        if h in hashes:
            duplicates.append((hashes[h], f))
            issues.append(f"DUPLICATE: {f.name} ≈ {hashes[h].name}")
        else:
            hashes[h] = f

        # Stale detection (project/feedback only — user/reference are evergreen)
        if mtype in ("project", "feedback") and mtime < cutoff:
            stale.append(f)
            issues.append(f"STALE ({mtype}, {mtime.date()}): {f.name}")

    # Report
    print("=== Memory Hygiene Report ===\n")
    if not issues:
        print("✅ All memories are clean — no duplicates or stale entries.")
    else:
        for issue in issues:
            print(f"  ⚠️  {issue}")

    print(f"\nTotal: {len(files)} files | Duplicates: {len(duplicates)} | Stale: {len(stale)}")

    if dry_run or not issues:
        print("\n[dry-run] No changes made.")
        return

    # Interactive cleanup
    print()
    for orig, dup in duplicates:
        ans = input(f"Delete duplicate {dup.name} (keep {orig.name})? [y/N] ").strip().lower()
        if ans == "y":
            dup.unlink()
            print(f"  Deleted {dup.name}")

    for f in stale:
        ans = input(f"Archive stale {f.name} (move to memory/archive/)? [y/N] ").strip().lower()
        if ans == "y":
            archive = MEMORY_DIR / "archive"
            archive.mkdir(exist_ok=True)
            f.rename(archive / f.name)
            print(f"  Archived {f.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
