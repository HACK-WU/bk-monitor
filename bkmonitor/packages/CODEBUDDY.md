# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is the **`packages/`** directory of the **bkmonitor** (BlueKing Monitor) Django project. It contains the major web-facing Django applications that are mounted at runtime by adding `packages/` to `sys.path` in `settings.py`.

Each subdirectory is a self-contained Django app (or package of apps) following the project's `core.drf_resource` framework. They are not standalone packages — they depend on the parent `bkmonitor/` project for settings, models, database routing, and shared frameworks.

- **Parent project**: `bkmonitor/` (see `bkmonitor/CODEBUDDY.md` for global commands and architecture)
- **Python version**: 3.11 (strictly `==3.11.*`)
- **Django version**: 4.2.27

## Common Commands

All build, lint, and dependency commands are run from the parent `bkmonitor/` directory. See `bkmonitor/CODEBUDDY.md` for detailed setup.

```bash
# From bkmonitor/ root

# Install dependencies
uv sync --all-groups

# Format and lint
ruff check packages/<app_name>/
ruff format packages/<app_name>/
basedpyright

# Run dev server (web role)
export DJANGO_CONF_MODULE=conf.web.development.community
export django_find_project=false
python manage.py runserver
```

### Testing

Default `pytest` testpaths (defined in `pyproject.toml`) are:
- `alarm_backends/tests`
- `bkmonitor/data_source/tests`
- `metadata/tests`

Tests inside `packages/` are **not** in the default paths and must be run explicitly:

```bash
# Run all tests for a specific package
pytest packages/monitor_web/tests/
pytest packages/apm_web/tests/ --reuse-db
pytest packages/weixin/

# Run a single test file
pytest packages/monitor_web/tests/ai_ops/test_ai_setting.py
pytest packages/apm_web/tests/test_list_application_async.py --reuse-db

# Run a single test function
pytest packages/monitor_web/tests/strategies/test_some_file.py::test_function_name

# Run with Django manage.py
python manage.py test monitor_web.tests
python manage.py test apm_web.tests
python manage.py test weixin
```

Many `monitor_web` and `apm_web` tests rely on fixtures in `tests/conftest.py` at the project root.

## Architecture

### Package Inventory

| Package | Role |
|---|---|
| `monitor_web/` | Web UI backend — strategies, alert events, plugins, collecting, K8s, data explorer, scene views, Grafana, custom reporting, shielding, AI ops, IAM, export/import. See `monitor_web/CODEBUDDY.md`. |
| `apm_web/` | APM web backend — distributed tracing, continuous profiling, metric queries, service topology, application management. See `apm_web/CODEBUDDY.md`. |
| `fta_web/` | Fault Tree Automation web — actions, alerts (v1/v2), assignment, event plugins, home dashboard. |
| `monitor_api/` | Auto-generated REST API for models listed in `MONITOR_API_MODELS`. Also provides global DRF pagination and middleware. See `monitor_api/CODEBUDDY.md`. |
| `monitor/` | Core monitoring app — uptime check (synthetic monitoring), user/business/global config, role permissions, Celery utilities. See `monitor/CODEBUDDY.md`. |
| `weixin/` | WeChat / Enterprise WeChat mobile mini-program backend. See `weixin/CODEBUDDY.md`. |
| `apm_trace/` | Lightweight APM trace URL routing and views. |
| `common/` | Shared context processors, middleware, decorators, and logging utilities used across web packages. |
| `audit/` | Audit logging client and instance trackers. |
| `healthz/` | Health-check endpoints. |
| `utils/` | General package-level utilities. |
| `monitor_adapter/` | Adapter layer for platform-specific behavior. |

### Standard Sub-App Layout

Feature areas within the larger packages (`monitor_web`, `apm_web`, `fta_web`) follow a consistent pattern:

```
<package>/<feature>/
  resources.py    # Resource classes implementing business logic
  views.py        # ResourceViewSet classes exposing HTTP endpoints
  urls.py         # ResourceRouter wiring
  serializers.py  # (optional) DRF serializers
```

Parent modules aggregate children via wildcard imports:

```python
# monitor_web/aiops/resources.py
from monitor_web.aiops.ai_setting.resources import *  # noqa
from monitor_web.aiops.host_monitor.resources import *  # noqa
```

The root `urls.py` of each package then includes sub-apps with `include("<package>.<feature>.urls")`.

### API Framework (`core.drf_resource`)

All packages use the internal `core.drf_resource` framework defined in the parent project:

- **`Resource`** (`core/drf_resource/base.py`): Business logic unit. Implement `perform_request(self, validated_request_data)`. Optionally define `RequestSerializer` / `ResponseSerializer`.
- **`ResourceViewSet`** (`core/drf_resource/viewsets.py`): Exposes Resources as HTTP endpoints via `resource_routes = [ResourceRoute("POST", SomeResource)]`.
- **`ResourceRouter`** (`core/drf_resource/routers.py`): Auto-discovers and registers viewsets.

### Import Conventions

Because `packages/` is on `sys.path`, imports **omit** the `packages.` prefix:

```python
# Correct
from monitor_web.strategies.resources import SomeResource
from apm_web.meta.resources import ApplicationInfoResource
from common.context_processors import get_default_biz_id

# Incorrect
from packages.monitor_web.strategies.resources import SomeResource
```

Models defined inside a package are typically re-exported from `<package>/models/__init__.py`. Core project models live in `bkmonitor.models` and are imported as `from bkmonitor.models import ...`.

### Proxy Model Pattern

Some packages define proxy models for models declared in sibling packages. For example, `monitor_web` defines proxy models for several `monitor` models (`UptimeCheckNode`, `UptimeCheckTask`, etc.) so it can attach web-specific behavior without duplicating tables. When modifying base models in `monitor/`, check whether `monitor_web`'s proxy logic or admin registrations are affected.

### Frontend Correspondence

Backend packages under `monitor_web/` and `apm_web/` typically map 1:1 to frontend pages under:

```
webpack/src/monitor-pc/pages/
```

Examples:
- `monitor_web/strategies/` → `pages/strategy-config/`
- `monitor_web/alert_events/` → `pages/alarm-center/`, `pages/event-center/`
- `monitor_web/k8s/` → `pages/k8s/`
- `apm_web/meta/` → APM application setup pages

## Database Routing

Packages read/write through the routers defined in `bkmonitor/db_routers.py`:
- Backend apps (`bkmonitor`, `metadata`, `apm`, `calendars`, `monitor_api`) → `monitor_api` alias.
- Alert models → `backend_alert` alias (or `default` when `BACKEND_DATABASE_NAME == "default"`).

See `bkmonitor/CODEBUDDY.md` for full routing rules and dynamic override mechanisms (`local.DB_FOR_READ_OVERRIDE`, `local.DB_FOR_WRITE_OVERRIDE`).
