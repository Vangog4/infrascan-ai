# PROJECT_KNOWLEDGE.md — Odoo 19 Environment

> Version-controlled knowledge base. Update this file after any significant
> infrastructure change; do NOT rely on Logseq or external note tools for
> facts that must survive a machine rebuild.

---

## ⚠ DISK ALERT — 2026-05-01

**Disk usage: 96% (23G / 25G). Only ~1.1G free.**

| Category | Total | Reclaimable |
|----------|-------|-------------|
| Container images | 11.54 GB | **6.95 GB** (unused images) |
| Volumes | 572 MB | 340 MB (orphaned volumes) |

**Safe to delete (no data loss):**
```bash
# Orphaned empty volume (already removed 2026-05-01)
# odoo19_odoo-db-data — 4KB, was removed

# Unused images — confirm each before deleting:
podman image rm docker.io/reeoss/paperclipai-paperclip:latest  # 2.35 GB
podman image rm docker.io/library/odoo:17.0                    # 1.92 GB
podman image rm docker.io/library/postgres:15                  # 452 MB
podman image rm docker.io/library/postgres:15-alpine           # 277 MB
podman image rm docker.io/library/postgres:16-alpine           # 279 MB
# Total above: ~5.3 GB
```

**Do NOT delete without checking:**
- `amanita_odoo_odoo_amanita_db_data` — 164 MB — Amanita database, Amanita stack DOWN but data preserved
- `pepito_odoo_odoo_pepito_db_data` — 162 MB — Pepito Odoo database, stack not running

---

## Stack Overview

| Component | Image | Version |
|-----------|-------|---------|
| Application | `docker.io/library/odoo` | 19 (Community / Free) |
| Database | `docker.io/library/postgres` | 16 (LTS) |
| Compose file | `podman-compose.yml` | — |
| Runtime | Podman + podman-compose | rootless |

---

## Network Strategy

- **Network name:** `odoo-internal` (project-prefixed: `odoo19_odoo-internal`)
- **Driver:** bridge, `internal: true` — no outbound routing from this network
- **Subnet:** `172.28.0.0/24`
- **External network:** `npm_network` (must exist; created by Nginx Proxy Manager stack)

The web container is attached to BOTH `odoo-internal` AND `npm_network`.
Internet access for module downloads is routed through `npm_network`.
The database container is on `odoo-internal` only — fully isolated, no host ports.
The web container binds only to `127.0.0.1` (loopback) for direct host access.

> If `npm_network` does not exist yet, create it once:
> `podman network create npm_network`

---

## Volume Strategy

| Volume name | Mount point | Purpose |
|-------------|-------------|---------|
| `odoo-db-data` | `/var/lib/postgresql/data` | Postgres data directory |
| `odoo-web-data` | `/var/lib/odoo` | Odoo filestore, sessions, attachments |
| `./config` (bind, `:ro`) | `/etc/odoo` | `odoo.conf` and any custom config |
| `./addons` (bind, `:ro`) | `/mnt/extra-addons` | Custom / community modules |

Named volumes are managed by Podman and survive `podman-compose down`.
Only `down --volumes` removes them.

---

## `odoo.conf` Tweaks for the Website Builder

```ini
workers = 2          ; prefork workers — website builder requires ≥2
max_cron_threads = 1 ; dedicated cron slot

proxy_mode = True    ; trust X-Forwarded-* headers from reverse proxy
longpolling_port = 8072

; Generous timeouts — asset compilation / page-builder saves are slow
limit_time_cpu  = 7200   ; 2 h CPU time per request
limit_time_real = 14400  ; 4 h wall-clock per request

limit_request_size  = 2147483648  ; 2 GB — large DB restore / media upload
limit_memory_soft   = 2147483648  ; 2 GB soft per worker
limit_memory_hard   = 2684354560  ; 2.5 GB hard per worker

db_maxconn = 64   ; pool cap — keep under postgres max_connections (200)
```

**Why `workers ≥ 2`:** Odoo's website builder uses a separate HTTP worker
for long-polling (port 8072). With `workers=0` (dev mode / gevent), the
builder's live-collaboration and chat features break under any real load.

---

## Exposed Ports (loopback only)

| Port | Service | Stack |
|------|---------|-------|
| `127.0.0.1:8069` | Odoo HTTP | InfraScan |
| `127.0.0.1:8072` | Longpolling | InfraScan |
| `127.0.0.1:8070` | Odoo HTTP | Amanita |
| `127.0.0.1:8073` | Longpolling | Amanita |

NPM upstream: `/longpolling/` → `:8072` (или `:8073`), остальное → `:8069` (или `:8070`).

---

## Stack Status — 2026-05-01 (актуально)

| Стек | Контейнеры | Статус | БД |
|------|-----------|--------|-----|
| `~/odoo19/` | `odoo19_db`, `odoo19_web` | **UP healthy** | InfraScan_bd |
| `~/amanita_odoo/` | `odoo_amanita_db`, `odoo_amanita_app` | **UP healthy** | db_amanita |

Оба стека на `podman-compose.yml`. Данные целы.

---

## Compose File Migration — 2026-05-01

The canonical stack file is now **`podman-compose.yml`**. The old `compose.yml`
(Docker Compose syntax, used `docker.io` images with `npm_network` via external)
has been backed up to `compose.yml.bak`.

**⚠ Running containers as of 2026-05-01 are still using the OLD `compose.yml`:**

| Container | Name (old) | Name (new compose) |
|-----------|------------|-------------------|
| Odoo web | `odoo19` | `odoo19_web` |
| Postgres | `odoo19_db` | `odoo19_db` (unchanged) |

To migrate to the new compose, do a full recreate:
```bash
cd ~/odoo19
podman-compose -f compose.yml down        # stop old stack
podman-compose -f podman-compose.yml up -d  # start new stack
```
Named volumes (`odoo-db-data`, `odoo-web-data`) persist across this operation — data is safe.

---

## Startup Log — 2026-04-30

**Result: HEALTHY**

| Service | Status | Notes |
|---------|--------|-------|
| `odoo19_db` (Postgres 16) | Up, healthy | Listening on `odoo-internal` network |
| `odoo19_web` (Odoo 19.0-20260217) | Up, healthy | Workers alive, health endpoint 200 OK |

### Access URLs
| Endpoint | URL |
|----------|-----|
| Main UI | http://localhost:8069 |
| Longpolling / live-chat | http://localhost:8072 (via `gevent_port`) |

### Confirmed working
- `HTTP service (werkzeug) running on 0.0.0.0:8069`
- `Evented Service (longpolling) running on 0.0.0.0:8072`
- 2× `WorkerHTTP` alive + 1× `WorkerCron` alive
- 87 modules loaded in ~2.5 s; registry loaded
- `GET /web/health` → **200 OK** (healthcheck passing)
- Database: `odoo@db:5432` — connected to `InfraScan_bd`

### Warnings (non-fatal, documented)

| Warning | Root cause | Action taken |
|---------|-----------|--------------|
| `invalid addons directory '/mnt/extra-addons'` | `./addons/` is empty — no modules yet | Benign; will resolve when modules are added |
| `module infrascan_ai: not installable` | Module is installed in DB but its source is not in the container's addons path | Source lives at `./infrascan_ai/` but is not bind-mounted; add it to addons or volumes if needed |

### Config fixes applied after first boot
Odoo 19 renamed/removed several options vs. Odoo 17/18:

| Old `odoo.conf` key | Odoo 19 replacement | Notes |
|---------------------|--------------------|-|
| `longpolling_port` | `gevent_port` | Same default (8072) |
| `limit_request_size` | removed | No direct equivalent; `limit_request` is a request-count cap |
| *(missing)* | `http_interface = 0.0.0.0` | Explicit binding silences deprecation warning |

### Module count update (2026-04-30)
After moving `infrascan_ai` into `./addons/` and running the upgrade:
**88 modules loaded** (was 87). No "not installable" or "Some modules are not loaded" errors remain.

### Network incident on first launch
`odoo19_db` was already running from a prior session on `odoo19_default` network.
podman-compose reused the existing container instead of recreating it, so `odoo19_web`
(on `odoo19_odoo-internal`) could not resolve hostname `db`.

**Fix applied:**
```bash
podman network connect --alias db odoo19_odoo-internal odoo19_db
podman restart odoo19_web
```
**Permanent fix:** run `podman-compose down` (not just `stop`) before `up -d` on a
fresh deploy to ensure all containers are recreated on the correct network.

---

## Custom Modules

### `infrascan_ai` — InfraScan AI Core

| Field | Value |
|-------|-------|
| Location | `./addons/infrascan_ai/` |
| Odoo version | 19.0 |
| Technical name | `infrascan_ai` |
| Depends on | `project` (core Odoo project/task module) |
| License | LGPL-3 |
| DB installed in | `InfraScan_bd` |

**What it does:**
Extends `project.task` with a thermal image analysis action powered by the
Google Gemini API (`gemini-1.5-flash`). When a user triggers
`action_analyze_thermal_image` on a task, the module:

1. Searches the task's attachments for the most recent image file.
2. Base64-encodes the image and sends it to the Gemini vision endpoint with
   a Russian-language prompt asking for defect detection (overheating / leaks)
   and a cost estimate in RUB.
3. Posts the AI verdict back to the task chatter via `message_post`.

The module has no custom views, menus, or DB columns — it is a pure Python
`_inherit` extension with a single action method.

**API Key Management (resolved 2026-04-30)**
The original hardcoded key has been removed from Python source. The key is now
stored as an Odoo system parameter and managed entirely through the UI or DB:

- **UI path:** Settings → Technical → System Parameters → `infrascan_ai.gemini_api_key`
- **Odoo XML id:** `infrascan_ai.param_gemini_api_key`
- **Loaded via:** `data/infrascan_config_data.xml` (with `noupdate="1"`)
- **Runtime lookup:** `self.env['ir.config_parameter'].sudo().get_param('infrascan_ai.gemini_api_key')`
- **Missing key behaviour:** raises `UserError` with a clear setup message — the action will not silently fail

`noupdate="1"` means the XML value is only inserted on first install; upgrading
the module will NOT overwrite a key you have changed in the UI. To reset to the
XML default, delete the system parameter record in the UI and re-run the upgrade.

**✓ API key status:** `data/infrascan_config_data.xml` now contains only the placeholder
`REPLACE_WITH_YOUR_GEMINI_API_KEY`. The live key was removed from source.
Set the real key via: Settings → Technical → System Parameters → `infrascan_ai.gemini_api_key`
(or via `podman exec odoo19_web odoo shell` / direct DB update).

**How to upgrade after code changes:**
```bash
podman stop odoo19_web
podman run --rm \
  --network odoo19_odoo-internal \
  -v odoo19_odoo-web-data:/var/lib/odoo \
  -v /root/odoo19/config:/etc/odoo:ro \
  -v /root/odoo19/addons:/mnt/extra-addons:ro \
  -e HOST=db -e PORT=5432 -e USER=odoo -e PASSWORD=odoo_db_password \
  docker.io/library/odoo:19 \
  odoo -c /etc/odoo/odoo.conf -d InfraScan_bd -u infrascan_ai --stop-after-init
podman start odoo19_web
```

