# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

`bk_monitor` is a Django app (part of the BK-LOG platform) that serves as an SDK/integration layer for the BlueKing Monitor (BK-Monitor) platform. It provides metric collection, custom time-series/event reporting, event triggering, and querying capabilities. It is not a standalone service — it's used by other Django apps (primarily `apps.log_measure`) within the BK-LOG project.

The broader BK-LOG project lives in `/root/bk-monitor-learn/bklog/`, which is a Django 4.2 web application running on Python 3.11 with Celery for async tasks, Redis as cache/broker, MySQL as the primary database, and Elasticsearch for log storage.

## Commands

### Testing

```bash
# All bk_monitor tests
python manage.py test bk_monitor.test.bk_monitor

# Single test method
python manage.py test bk_monitor.test.bk_monitor.TestBkMonitor.test_migrate
python manage.py test bk_monitor.test.bk_monitor.TestBkMonitor.test_report
python manage.py test bk_monitor.test.bk_monitor.TestBkMonitor.test_query

# All app tests (full suite)
python manage.py test apps.tests --keepdb

# Via Makefile
make unittest
```

Tests use SQLite3 automatically (no MySQL required) — `config/dev.py` switches the database when `test` is in `sys.argv`. Test env variables must be set (see `scripts/test_env.sh`).

### Linting

```bash
# Ruff (primary linter, configured at repo root pyproject.toml)
ruff check bk_monitor/
ruff format bk_monitor/

# Flake8 (legacy, configured at bklog/.flake8)
flake8 bk_monitor/

# Black (formatter, configured at bklog/pyproject.toml)
black bk_monitor/

# Pre-commit (runs ruff + ruff-format + other checks)
pre-commit run --all-files
```

Line length is 120 across all tools. Ruff rules: E4, E7, E9, F, UP.

### Other

```bash
# Django management commands
python manage.py migrate              # Run database migrations
python manage.py makemigrations       # Create new migrations

# Frontend build
make build-web

# i18n
make translate
```

## Architecture

### bk_monitor Package Structure

```
bk_monitor/
├── handler/monitor.py    # Core business logic — BKMonitor, CustomReporter, BKMonitorModel
├── api/
│   ├── client.py         # High-level BK Monitor API client (ESB + direct HTTP)
│   └── http.py           # Low-level HTTP primitives (get/post/put/delete)
├── utils/
│   ├── metric.py         # Metric class + register_metric decorator + REGISTERED_METRICS registry
│   ├── collector.py      # MetricCollector — orchestrates metric collection from registered functions
│   ├── event.py          # BkMonitorEvent + EventTrigger — event reporting
│   ├── data_name_builder.py  # DataNameBuilder — naming convention for data sources/groups
│   └── query.py          # SqlSplice + CustomTable — SQL query building for time-series queries
├── models.py             # MonitorReportConfig — Django model storing data source configs
├── constants.py          # ErrorEnum, TimeFilterEnum, ETL configs, batch size
├── exceptions.py         # BaseMonitorException hierarchy (Request, Result, GetTsData)
├── migrations/           # Django DB migrations
└── test/bk_monitor.py    # TestBkMonitor — Django TestCase with mocked API calls
```

### Data Flow

1. **Initialization (`migrate`)**: `BKMonitor.custom_metric().migrate(data_name_list)` — Creates/verifies data sources (data_id) in BK-Monitor via ESB API, creates time_series or event groups, persists config in `MonitorReportConfig` DB model.

2. **Metric Reporting (`report`)**: `CustomReporter.report()` — Collects metrics from `REGISTERED_METRICS` (populated via `@register_metric` decorator), reads collected data from `MetricDataHistory` (in `apps.log_measure`), formats as BK-Monitor payloads, pushes via `Client.custom_report()` to `/v2/push/` endpoint. Batches at 5000 records.

3. **Event Reporting**: `BKMonitor.build_event_trigger(data_name, event_name)` → `EventTrigger.trigger()` → `BkMonitorEvent` — Builds event dict and sends via `CustomReporter.trigger_event()`.

4. **Querying**: `CustomReporter.query(data_name, fields, ...)` — Builds SQL via `SqlSplice`, resolves `table_id` via `CustomTable`, queries via `Client.get_ts_data()`.

### Key Design Patterns

- **Decorator-based metric registration**: Functions decorated with `@register_metric(namespace, data_name, ...)` are auto-registered in the `REGISTERED_METRICS` global dict. `MetricCollector` discovers and calls them by importing their modules.
- **Two API calling modes**: `_call_esb_api()` adds BlueKing ESB auth headers (`X-Bkapi-Authorization`), `_call_api()` is for direct HTTP calls (e.g., push endpoint).
- **Config persistence**: `MonitorReportConfig` model stores data_id, table_id, and access_token so migrate is idempotent — skips already-initialized data sources.

### External Dependencies

- `apps.log_measure.models.MetricDataHistory` — Stores collected metric data for reporting
- `apps.log_measure.utils.metric.MetricUtils`, `get_metric_id_info` — Metric utilities used by CustomReporter
- BlueKing ESB (Enterprise Service Bus) — API gateway for monitor operations
- BK-Monitor push endpoint — Receives custom metric/event data at `report_host/v2/push/`

### Settings

Django settings cascade: `settings.py` → `config/default.py` → `config/{dev|stag|prod}.py`. Environment is selected via `DJANGO_SETTINGS_MODULE`. The `bk_monitor` app is registered in `INSTALLED_APPS` in `config/default.py`.
