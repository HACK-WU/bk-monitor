# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Context

`monitor` is a Django app inside the larger **bkmonitor** (BlueKing Monitor) project. It lives at `packages/monitor/` and is included in `INSTALLED_APPS` for the `web` role. It is not a standalone package — it depends on the parent Django project (`bkmonitor/`) for settings, database routing, and the `core.drf_resource` framework.

## Common Commands

This app has no independent build or test commands. Use the parent project's tooling (see `bkmonitor/CODEBUDDY.md`):

```bash
# From the bkmonitor/ repo root

# Install dependencies
uv sync --all-groups

# Format and lint
ruff check packages/monitor/
ruff format packages/monitor/

# Run the dev server (web role)
export DJANGO_CONF_MODULE=conf.web.development.community
export django_find_project=false
python manage.py runserver

# Create migrations for this app
python manage.py makemigrations monitor

# Run migrations
python manage.py migrate monitor --noinput
```

## Architecture

### Models

Models are split across two files:

- **`models/models.py`** — Current, actively used models.
- **`models/old.py`** — Legacy models (legacy collectors, dashboards, menus, component imports). These are retained for migration history and backward compatibility. Avoid adding new code that depends on them.

#### Current Models (`models/models.py`)

| Model | Purpose |
|---|---|
| `UserConfig` | Key-value user preferences (`username` + `key` unique). Known keys: `FUNCTION_ACCESS_RECORD`, `DEFAULT_BIZ_ID`. |
| `ApplicationConfig` | Key-value business (`cc_biz_id`) configuration. |
| `GlobalConfig` | Global key-value configuration (`key` is unique). |
| `RolePermission` | Role-to-permission mapping used during IAM permission upgrades. |
| `UptimeCheckNode` | Synthetic monitoring node (IP, host ID, location, carrier). |
| `UptimeCheckTask` | Synthetic monitoring task (protocol, interval, nodes, config, status). Protocols: TCP, UDP, HTTP, ICMP. |
| `UptimeCheckTaskSubscription` | Links an uptime check task to a NodeMan subscription ID per business. |
| `UptimeCheckGroup` | Groups multiple `UptimeCheckTask`s together. |
| `UptimeCheckTaskCollectorLog` | Execution logs from NodeMan when deploying uptime check tasks. |
| `UploadedFile` | Generic file upload with MD5 and `file(1)` type detection. |

All config models (`UserConfig`, `ApplicationConfig`, `GlobalConfig`) use `ConfigDataField` for their `value` column, which stores JSON-serialized data.

Uptime check models use `OperateRecordModel` as a base (adds `create_user`, `create_time`, `update_user`, `update_time`, `is_deleted`).

#### Proxy Models in `monitor_web`

`monitor_web` defines proxy models for several `monitor` models so it can attach web-specific behavior without duplicating tables:

- `monitor_web.models.UptimeCheckNode` → proxy of `monitor.UptimeCheckNode`
- `monitor_web.models.UptimeCheckTask` → proxy of `monitor.UptimeCheckTask`
- `monitor_web.models.UptimeCheckGroup` → proxy of `monitor.UptimeCheckGroup`
- `monitor_web.models.UptimeCheckTaskCollectorLog` → proxy of `monitor.UptimeCheckTaskCollectorLog`
- `monitor_web.models.RolePermission` → proxy of `monitor.RolePermission`

When modifying these base models, consider whether `monitor_web`'s proxy logic or admin registrations will be affected.

### Celery Utilities

#### Task Decorator (`tasks.py`)

`task_decorator` is a custom decorator (not a Celery task itself) that wraps functions with:

1. **Distributed locking** via Django cache (`cache.get` / `cache.set`). The lock key is derived from the function name and arguments.
2. **Jitter** — sleeps for a random value in `[0, random_range]` seconds before executing, to prevent thundering herd.
3. **Local cleanup** — calls `local.clear()` in a `finally` block.

Default parameters:
- `random_range = 10` seconds
- `task_interval = 120` seconds (cache TTL / lock duration)

> **Note:** This decorator is used on plain functions that are later invoked by Celery tasks, not on Celery task functions directly.

#### Custom Beat Scheduler (`schedulers.py`)

`MonitorDatabaseScheduler` extends `django_celery_beat.DatabaseScheduler` with `MonitorModelEntry`. When loading periodic tasks from code (e.g., `beat_schedule` in settings), it preserves the existing `enabled` flag in the database rather than overwriting it. This prevents code-level `enabled=True` from re-enabling tasks that were manually disabled in the admin.

### Admin (`admin.py`)

Django admin registrations for:
- `UserConfig`
- `ApplicationConfig`
- `GlobalConfig`
- `UptimeCheckNode`
- `UptimeCheckTask`
- `UptimeCheckGroup`

### AppConfig (`apps.py`)

`MonitorConfig.ready()` does two things at startup:
1. Clears the web cache (if `CLEAR_CACHE_ON_RESTART` is enabled) using `UsingCache.key_prefix`.
2. Patches `rest_framework.serializers.ModelSerializer.serializer_field_mapping` to use `bkmonitor.views.fields.DateTimeField` for `models.DateTimeField`.

## Important Conventions

- **Legacy models**: Do not add new features that depend on `models/old.py`. Those models are historical artifacts.
- **Migrations**: This app has a long migration history (~119 files). When adding a migration, ensure it runs correctly against both fresh and existing databases.
- **Config model keys**: `UserConfig.Keys` defines known keys; new keys can be added ad-hoc but should be documented where they are consumed.
- **Uptime check config**: The `UptimeCheckTask.config` field is a `SymmetricJsonField`. A legacy v1-to-v3 migration helper (`monitor.utils.update_task_config`) transforms old flat config structures into the newer nested format (headers, query_params, body, authorize).
- **Line length**: 120 characters (inherited from parent Ruff config).
