# Autoresearch: stack-health

## Objective
Довести health_score стека infrascan-ai до 100/100. Скрипт `autoresearch.sh` проверяет:
контейнеры (db, web, redis, bot), Odoo HTTP, Odoo XML-RPC, синтаксис бота, unit-тесты, Redis PING.

## Metrics
- **Primary**: health_score (%, выше лучше)
- **Secondary**: checks_passed, checks_failed

## How to Run
`./autoresearch.sh` — выводит `METRIC name=value` строки.

## Files in Scope
- `podman-compose.yml` — стек контейнеров
- `bot/src/` — исходники бота
- `bot/tests/` — unit-тесты
- `config/odoo.conf` — конфиг Odoo
- `autoresearch.sh` — скрипт проверки

## Off Limits
- `bot/.env` — секреты, не трогать
- `addons/` — только если критично для health

## Constraints
- Использовать только podman/podman-compose (не docker)
- Не устанавливать пакеты глобально
- Тесты должны проходить

## What's Been Tried
- **Baseline run**: 18/100 — все контейнеры не запущены
