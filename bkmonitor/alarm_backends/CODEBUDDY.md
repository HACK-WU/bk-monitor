# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is `alarm_backends`, a Django app within the BlueKing Monitor (`bkmonitor`) platform. It is a backend worker service responsible for the entire alert processing pipeline: data ingestion, anomaly detection, event triggering, alert building, and action execution (notifications, convergences, etc.).

- **Language**: Python 3.11
- **Framework**: Django 4.2
- **Package Manager**: `uv` (pyproject.toml at repo root)
- **Django App Location**: `alarm_backends/`
- **Repo Root**: `bkmonitor/` (where `manage.py` lives)

## Common Commands

All commands should be run from the repository root (`bkmonitor/`) unless otherwise noted.

### Testing

```bash
# Run all alarm_backends tests
pytest alarm_backends/tests

# Run a specific test file or directory
pytest alarm_backends/tests/service/detect
pytest alarm_backends/tests/core/cache/test_strategy_group.py

# Run with coverage
pytest --cov=alarm_backends alarm_backends/tests
```

Pytest configuration is in `pyproject.toml` (`[tool.pytest.ini_options]`). It already sets:
- `DJANGO_SETTINGS_MODULE=settings`
- `DJANGO_CONF_MODULE=conf.worker.development.community`
- `BKAPP_DEPLOY_PLATFORM=community`
- `USE_DYNAMIC_SETTINGS=0`

Tests use `fakeredis` (mocked Redis) and `FakeElasticsearchBucket` instead of real external services.

### Linting & Formatting

```bash
# Linting
ruff check .

# Formatting
ruff format .

# Type checking (basedpyright, excludes tests)
basedpyright
```

Configuration is in `pyproject.toml` (`[tool.ruff]`, `[tool.pyright]`).

### Running Services Locally

```bash
# Required environment variables (adjust as needed)
export DJANGO_SETTINGS_MODULE=settings
export DJANGO_CONF_MODULE=conf.worker.development.enterprise
export APP_TOKEN=replace-me-to-your-app-token
export BK_PAAS_HOST=https://replace.me

# Run access service (data ingestion)
python manage.py run_access -s access --access-type=data --min-interval 30

# Run other backend services (e.g., detect, trigger)
python manage.py run_service -s detect

# Run with Celery handler instead of local process
python manage.py run_service -s detect -H celery

# Generate supervisor configuration
python manage.py gen_config

# Start with supervisor
supervisord -c alarm_backends/conf/supervisord.conf
```

### Other Useful Commands

```bash
# Install dependencies (including test and dev groups)
uv sync --all-groups

# Clean Python bytecode
make clean
```

## High-Level Architecture

`alarm_backends` is designed as a stream-processing pipeline where services communicate via Redis queues. Data flows through the system in discrete stages, with each stage producing output that the next stage consumes.

### Pipeline Flow

```
Data Sources (Kafka, TSDB, etc.)
    |
    v
+-----------+      +--------+      +---------+      +-------+      +----------------+
|  access   | -->  | detect | -->  | trigger | -->  | alert | -->  | fta_action /   |
| (ingest)  |      | (algo) |      | (event) |      |build  |      | notice / converge|
+-----------+      +--------+      +---------+      +-------+      +----------------+
```

### Core Services

| Service | Path | Purpose |
|---------|------|---------|
| **access** | `service/access/` | Pulls raw data from various sources (time-series, events, alerts), enriches dimensions, filters by scope, and outputs standardized data records into Redis queues. |
| **detect** | `service/detect/` | Consumes standardized data, runs anomaly detection algorithms (thresholds, YoY, MoM, etc.), and pushes anomaly records into Redis. |
| **trigger** | `service/trigger/` | Consumes anomaly signals, applies trigger logic (e.g., N violations in M periods), and emits event records. |
| **alert** | `service/alert/` | Builds alert objects from events, handles deduplication, shielding, enrichment, and QoS (rate limiting). |
| **fta_action** | `service/fta_action/` | Executes actions: notifications (webhook, SMS, phone, etc.), convergence, incident handling, ITSM integration, etc. |
| **scheduler** | `service/scheduler/` | Celery-based task scheduler for periodic and async tasks across modules. |
| **selfmonitor** | `service/selfmonitor/` | Log rotation, metrics collection, and QoS self-checks. |
| **nodata** | `service/nodata/` | No-data detection logic. |
| **preparation** | `service/preparation/` | Pre-processing and preparation tasks. |

### Inter-Service Communication (Redis)

Services do not call each other directly; they communicate through well-defined Redis keys (lists, sorted sets, hashes, strings). Key definitions are centralized in `alarm_backends/core/cache/key.py`.

Important queues:
- `access.data.{strategy_id}.{item_id}` — standardized data waiting for detection.
- `detect.anomaly.list.{strategy_id}.{item_id}` — anomaly details produced by detect.
- `detect.anomaly.signal` — lightweight signals consumed by trigger.
- `trigger.event` — events ready for alert building.
- `fta_action.{action_type}` / `converge.{converge_type}` — action/convergence queues.

**Redis DB allocation** (per `service/README.md`):
- `db:7` — logs (safe to clear)
- `db:8` — config cache, e.g., strategies, shields (clearable)
- `db:9` — inter-service queues and Celery broker (critical, do not clear)
- `db:10` — service internal state data (critical, do not clear)

**Key prefix rule**: `{app_code}.{platform}[.{env}].{service}.{key_name}`
- Example: `bk_monitor.ee.access.data.strategy_1001`
- Platform abbreviations: `enterprise` -> `ee`, `community` -> `ce`

### Service Handler Loading

Each service under `alarm_backends/service/<name>/` must expose a `handler.py` module containing handler classes that inherit from `alarm_backends.core.handlers.base.BaseHandler`.

The loader (`alarm_backends/management/base/loaders.py`) auto-discovers handlers:
- `XxxHandler` -> synchronous/process handler
- `XxxCeleryHandler` -> Celery-based async handler

Management commands `run_service` and `run_access` use this loader to instantiate and run the correct handler.

### Core Components

| Component | Path | Purpose |
|-----------|------|---------|
| **Cache** | `core/cache/` | Managers for strategy, shield, result table, action config, etc. |
| **Storage** | `core/storage/` | Abstractions over Redis, Kafka, RabbitMQ. |
| **Control** | `core/control/` | Strategy and item models, record parsing, checkpoints. |
| **Alert Models** | `core/alert/` | Alert and event object definitions and adapters. |
| **Processor Base** | `core/processor/base.py` | Base class for pushing anomaly data between stages. |
| **Circuit Breaking** | `core/circuit_breaking/` | Circuit breaker logic for protecting downstream systems. |
| **Locking** | `core/lock/` | Distributed service locks (Redis-based). |
| **i18n** | `core/i18n.py` | Internationalization utilities. |

### Management Commands

Custom Django commands live in `alarm_backends/management/commands/`:
- `run_access` — start access ingestion processes.
- `run_service` — start generic backend service processes.
- `gen_config` — generate `supervisord.conf` from templates.
- `healthz` — health check endpoint.
- `refresh_backend_cache` — refresh various backend caches.
- `check_lifecycle` — lifecycle checks.
- `alert_check`, `strategy_check`, `batch_strategy_check` — diagnostic/check commands.

## Configuration

Django settings are loaded from `settings.py` at the repo root. The actual environment-specific configs live under `config/` (not in `alarm_backends/`). Settings are composed by environment and role:

```
config.default -> blueapps.patch -> config.{env} -> config.role.{role}
```

For local development, the typical env vars are:
```bash
export DJANGO_SETTINGS_MODULE=settings
export DJANGO_CONF_MODULE=conf.worker.development.enterprise
export BKAPP_DEPLOY_PLATFORM=enterprise
export USE_DYNAMIC_SETTINGS=0
```

## Testing Notes

- `conftest.py` at `alarm_backends/tests/conftest.py` patches Redis and Elasticsearch globally for the test suite.
- `fakeredis` is used; if running on older macOS with Python <= 3.8, a `ctypes` patch may be needed (see `README.md` in `alarm_backends/`).
- Some tests require the `monitor_api` database in addition to `default`.

## Important Code Locations

| Concern | Location |
|---------|----------|
| Service handlers | `alarm_backends/service/<name>/handler.py` |
| Redis key definitions | `alarm_backends/core/cache/key.py` |
| Strategy cache manager | `alarm_backends/core/cache/strategy.py` |
| Anomaly detection algorithms | `alarm_backends/service/detect/` |
| Alert builder/processor | `alarm_backends/service/alert/` |
| Action execution | `alarm_backends/service/fta_action/` |
| Celery tasks | `alarm_backends/service/scheduler/` and per-module `tasks.py` |
| Management commands | `alarm_backends/management/commands/` |
