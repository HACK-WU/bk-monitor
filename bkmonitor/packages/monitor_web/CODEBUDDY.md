# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Package Overview

`monitor_web` is the **Web UI backend** package for BlueKing Monitor. It lives under `packages/monitor_web/` and is included in the Django web role (`ROLE=web`). It provides the HTTP API surface that backs the frontend SPA under `webpack/src/monitor-pc/pages/`.

This package is part of the larger `bkmonitor` Django project. See the project-level `CODEBUDDY.md` (repository root) for global conventions: dependency management (`uv`), code quality (`ruff`, `basedpyright`), role-based configuration, `core.drf_resource`, and database routing.

## Testing

Tests for this package live in `packages/monitor_web/tests/` and are **not** in the default `testpaths` defined in `pyproject.toml`. You must run them explicitly.

```bash
# Run all monitor_web tests
pytest packages/monitor_web/tests/

# Run a specific test file
pytest packages/monitor_web/tests/ai_ops/test_ai_setting.py

# Run a specific test function
pytest packages/monitor_web/tests/strategies/test_some_file.py::test_function_name

# Run with Django manage.py
python manage.py test monitor_web.tests
```

Shared test fixtures and API mocks are defined in:
- `packages/monitor_web/tests/conftest.py` — pytest fixtures (extensive API monkey-patching for BCS, CMDB, metadata, etc.)
- `packages/monitor_web/tests/mock.py` — reusable mock classes (`MockEventModel`, `MockQuerySet`, etc.)
- `packages/monitor_web/tests/mock_settings.py` — settings overrides for tests

Many monitor_web tests also rely on the global test fixtures in `tests/conftest.py` at the project root.

## Sub-App Architecture

Each feature area under `packages/monitor_web/` is a self-contained Django sub-app following the `drf_resource` pattern.

### Standard layout

```
monitor_web/<feature>/
  resources.py      # Resource classes (business logic)
  views.py          # ResourceViewSet classes (HTTP endpoints)
  urls.py           # ResourceRouter wiring
  serializers.py    # (optional) DRF serializers
```

### Aggregation pattern

Parent packages aggregate sub-modules via wildcard imports:

```python
# monitor_web/aiops/resources.py
from monitor_web.aiops.ai_setting.resources import *  # noqa
from monitor_web.aiops.host_monitor.resources import *  # noqa
```

The root `monitor_web/urls.py` then includes each sub-app's URLconf with `include("monitor_web.<feature>.urls")`.

### Nested sub-apps

Some packages have one extra level of nesting when the feature is large (e.g. `aiops/ai_setting/`, `aiops/host_monitor/`). In these cases the parent `urls.py` registers each nested module:

```python
router = ResourceRouter()
router.register_module(ai_setting_views)
router.register_module(host_monitor_views)
```

## Key Directories

| Directory | Responsibility |
|-----------|----------------|
| `strategies/` | Monitoring strategy CRUD, metric cache, query-config/PromQL conversion, intelligent detection models |
| `alert_events/` | Alert/event display, event center queries, incident correlation |
| `plugin/` | Collector plugin metadata, version lifecycle, release/debug workflows |
| `collecting/` | Collection configuration ( CollectConfigMeta ) management |
| `scene_view/` | Dashboard/scene view definitions, panel layouts, table formatting |
| `data_explorer/` | Ad-hoc data exploration, event exploration, unified query bridging |
| `k8s/` | Kubernetes monitoring — resource metadata, scenario metrics, PromQL generation |
| `aiops/` | AI settings (KPI anomaly, multivariate anomaly, dimension drill, metric recommend) |
| `grafana/` | Grafana organization/user provisioning, dashboard proxy |
| `custom_report/` | Custom time-series and event reporting endpoints |
| `shield/` | Alert shielding (suppression) rules |
| `notice_group/` / `user_group/` | Notification group and on-call user group management |
| `iam/` | IAM permission integration, action/resource registration |
| `export_import/` | Strategy and config export/import |
| `as_code/` | Configuration-as-code (YAML/JSON) import/export |
| `data_migrate/` | Directory-based business data migration (see `data_migrate/README.md`) |
| `statistics/` | Operational metrics collection (v2 collector framework, see `statistics/v2/README.md`) |
| `commons/` | Shared utilities: CC/Cmdb helpers, data access, file manager, job runner, token/robot helpers |
| `models/` | Django models local to `monitor_web` (re-exported in `monitor_web/models/__init__.py`) |

## Important Files

- **`tasks.py`** — Large Celery shared-task module (~77K). Contains background tasks for plugin release, AIOPS dataflow access, metric list cache refresh, uptime-check sync, statistics updates, etc.
- **`permissions.py`** — Custom DRF permission classes (`SuperuserWritePermission`, `BusinessViewPermission`, `ApiTokenPermission`). Most viewsets instead use `bkmonitor.iam.drf.BusinessActionPermission` / `ViewBusinessPermission`.
- **`constants.py`** — Package-level constants (`AGENT_STATUS`, `AlgorithmType`, `ETL_CONFIG`, graph types, AIOPS retry settings).
- **`views.py`** (root) — Intentionally empty; all viewsets are in sub-apps.

## Frontend Correspondence

Backend packages here typically map 1:1 to frontend pages under:

```
webpack/src/monitor-pc/pages/
```

Examples:
- `monitor_web/strategies/` → `pages/strategy-config/`
- `monitor_web/alert_events/` → `pages/alarm-center/`, `pages/event-center/`
- `monitor_web/plugin/` → `pages/collector-config/`
- `monitor_web/k8s/` → `pages/k8s/`
- `monitor_web/scene_view/` → `pages/custom-scenes/`
- `monitor_web/data_explorer/` → `pages/data-retrieval/`, `pages/event-explore/`

## Notable Patterns

### Scene Views (`scene_view/`)

Scene views are dashboard-like configurations composed of `Panel` objects (`scene_view/base.py`). `table_format.py` defines column renderers and filters. Built-in scene views are registered under `scene_view/builtin/`.

### Plugin Lifecycle (`plugin/`)

Plugins use a manager pattern (`plugin/manager/`):
- `PluginManagerFactory` returns the correct manager for a `PluginType`
- `Signature` (`plugin/signature.py`) handles version signing/validation
- Debug/start/release flows are exposed as Resource endpoints

### K8s Monitoring (`k8s/`)

Container monitoring uses a dual-query architecture:
- **ORM** for resource metadata (Pod, Workload, Namespace, etc.)
- **PromQL** for metrics, generated dynamically by `K8sResourceMeta` subclasses
- Scenarios (CPU, memory, network) are pluggable modules under `k8s/scenario/`

See `k8s/dev.md` for design details and extension recipes.

### Statistics v2 (`statistics/v2/`)

Operational metrics use a collector framework:
- Inherit `BaseCollector`
- Decorate metric methods with `@register(labelnames=(...))`
- Register the class in `statistics/v2/factory.py` (`INSTALLED_COLLECTORS`)
- The refresh task is `monitor_web.tasks.update_statistics_data`

See `statistics/v2/README.md` for full authoring guide.

## Data Migration (`data_migrate/`)

This is **not** Django migrations. It is a directory-based fixture system for exporting and importing business-scoped configuration data (strategies, collectors, metadata, etc.) between environments.

Entry points are exposed as management commands:

```bash
python manage.py data_migrate export --directory /tmp --bk-biz-ids 2 3 0
python manage.py data_migrate import --directory /tmp/bkmonitor-data-export
```

See `data_migrate/README.md` for supported handlers (tenant-id replacement, cluster-id remapping, model disabling, sanitization, sequence restoration).

## Import Conventions

Because `packages/` is on `sys.path`, imports omit the `packages.` prefix:

```python
# Correct
from monitor_web.strategies.resources import SomeResource
from monitor_web.models import CollectConfigMeta
from monitor_web.constants import AGENT_STATUS

# Incorrect
from packages.monitor_web.strategies.resources import SomeResource
```

Models defined inside `monitor_web` are re-exported from `monitor_web.models.__init__` for convenience. Core project models live in `bkmonitor.models`.
