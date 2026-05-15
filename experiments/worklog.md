# Worklog: stack-health

## Session: 2026-05-15

### Run 1: baseline — 18/100 (KEEP)
- Timestamp: 2026-05-15
- What changed: ничего, чистый старт
- Result: health_score=18, passed=2/11 (только синтаксис бота)
- Insight: все 4 контейнера не запущены → 9 из 11 проверок падают
- Next: запустить podman-compose up -d, пересмотреть что не стартует

---

## Key Insights
- Без запущенного стека score не поднять выше ~18

## Next Ideas
- podman-compose up -d
- проверить pytest — что именно падает
