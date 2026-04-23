# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is **bkmonitor** (BlueKing Monitor), a Django-based monitoring platform. It is part of the larger `bk-monitor-learn` monorepo but operates as its own Python project under `bkmonitor/`.

- **Python version**: 3.11 (strictly `==3.11.*`)
- **Django version**: 4.2.27
- **Dependency manager**: `uv` (not pip)
- **Settings module**: `settings` (`bkmonitor/settings.py`)

## Common Commands

### Dependencies

```bash
# Install all dependencies (including test, dev, and aidev groups)
uv sync --all-groups

# Add a production dependency
uv add <package>

# Add a dev/test/aidev dependency
uv add --dev <package>
uv add --group test <package>
uv add --group aidev <package>

# Add type stubs
uv add --group stubs <package>
```

The `aidev` group is included by default (`tool.uv.default-groups`).

### Code Quality

```bash
# Format and lint (Ruff)
ruff check .
ruff format .

# Type checking (basedpyright)
basedpyright
```

Type-checker configuration in `pyproject.toml` sets `extraPaths = ["packages"]` and `stubPath = "typings"`, so IDEs should include `packages` in their Python path.

### Pre-commit

The project requires pre-commit hooks for basic checks (including Ruff). Install once after dependencies are set up:

```bash
pre-commit install
```

Configuration lives in `.pre-commit-config.yaml`.

### Testing

Tests are configured in `pyproject.toml` under `[tool.pytest.ini_options]`.

```bash
# Run all configured pytest suites
pytest

# Run a specific test file
pytest alarm_backends/tests/some/test_file.py

# Run a specific test
pytest alarm_backends/tests/some/test_file.py::test_function_name

# Run tests outside the default testpaths (e.g., monitor_web packages)
pytest packages/monitor_web/tests/ai_ops/test_ai_setting.py
pytest packages/monitor_web/tests/some/test_file.py::test_function_name

# Run with coverage
pytest --cov=alarm_backends --cov=bkmonitor/data_source

# Run Django manage.py tests
python manage.py test alarm_backends.tests
python manage.py test tests.web
```

Test paths defined in `pyproject.toml`:
- `alarm_backends/tests`
- `bkmonitor/data_source/tests`
- `metadata/tests`

Additional tests also exist in:
- `tests/` at the project root
- `packages/monitor_web/tests/` for `monitor_web` package tests

Tests that touch backend models often need to declare multiple databases:
```python
class TestSomething(TestCase):
    databases = {"monitor_api", "default"}
```

Pytest automatically sets the following environment variables (defined in `pyproject.toml`):
- `DJANGO_CONF_MODULE=conf.worker.development.community`
- `BKAPP_DEPLOY_PLATFORM=community`
- `USE_DYNAMIC_SETTINGS=0`
- `django_find_project=false`
- `BK_MONITOR_APP_CODE=bk_monitorv3`
- `BK_MONITOR_APP_SECRET=secret`

**Test environment helpers:**
- `tests/conftest.py` (project root) manually configures Django settings and fixes MySQL collation to `utf8_general_ci` for pytest compatibility.
- `.pytest_web.sh` sets `DJANGO_CONF_MODULE=conf.web.development.community` for web-role tests.

### Migrations

The project uses multiple databases. Backend apps are **blocked** from migrating on `default` by `bkmonitor/db_routers.py`.

```bash
# Migrate backend apps to monitor_api database
python manage.py migrate --database=monitor_api

# Migrate default database (SaaS apps only)
python manage.py migrate

# Fake iam migration first (common in fresh environments)
python manage.py migrate --fake iam_migration
```

When running migrations in CI or fresh environments, the typical sequence is:
1. `migrate --fake iam_migration`
2. `migrate` (default DB)
3. `migrate --database=monitor_api`

### Running the Development Server

```bash
# Ensure DJANGO_CONF_MODULE is set, e.g.:
export DJANGO_CONF_MODULE=conf.web.development.community
export django_find_project=false

python manage.py runserver
```

### Celery

```bash
# Run celery worker (example)
celery -A config worker -l info
```

### Frontend

The frontend is a micro-frontend architecture under `webpack/`:

```bash
# Install frontend dependencies (requires pnpm and Node >= 20.17)
cd webpack && pnpm i

# Start dev servers
make dev-pc        # monitor-pc (main app)
make dev-apm       # APM
make dev-fta       # FTA
make dev-vue3      # trace (Vue3)
make dev-mobile    # mobile
make dev-external  # external app
```

Local proxy config lives in `webpack/local.settings.js` (gitignored).
See `webpack/README.md` for full frontend setup.

### Backend Services (alarm_backends)

`alarm_backends` has its own dedicated `CODEBUDDY.md` with detailed pipeline documentation. Key commands from the repo root:

```bash
# Run access service (data ingestion)
python manage.py run_access -s access --access-type=data --min-interval 30

# Run a backend service (e.g., detect, trigger)
python manage.py run_service -s detect

# Run with Celery handler
python manage.py run_service -s detect -H celery

# Generate supervisor configuration
python manage.py gen_config
```

See `alarm_backends/CODEBUDDY.md` for the full alert pipeline architecture (access -> detect -> trigger -> alert -> fta_action).

## Architecture

### Role-Based Configuration

Settings are loaded in a layered chain:

```
config.default -> blueapps.patch -> config.{env} -> config.role.{role}
```

- `config/default.py`: Base Django settings
- `config/dev.py`, `config/stag.py`, `config/prod.py`: Environment overrides
- `config/role/web.py`: Web/SaaS role settings
- `config/role/worker.py`: Background worker role settings
- `config/role/api.py`: API service role settings (reuses web + worker settings)

The active role is determined by `DJANGO_CONF_MODULE`. If unset, it defaults to `config.web.{ENVIRONMENT}.{PLATFORM}`. When explicitly set, it must have four dot-separated parts:
```
{prefix}.{role}.{environment}.{platform}
```

- **prefix**: Discarded (commonly `config` or `conf`)
- **role**: `web` | `worker` | `api`
- **environment**: `development` | `testing` | `production`
- **platform**: `enterprise` | `community` | `open`

Examples:
```bash
export DJANGO_CONF_MODULE=conf.web.development.community
export DJANGO_CONF_MODULE=conf.worker.development.enterprise
export DJANGO_CONF_MODULE=conf.api.testing.enterprise
```

Role differences:
- **web**: `ROOT_URLCONF = "urls"` (full web UI), includes `monitor_web`, `fta_web`, `apm_web`, etc.
- **worker**: `ROOT_URLCONF = "alarm_backends/urls"`, includes `alarm_backends` and background processing apps.
- **api**: Combines both web and worker apps, includes `kernel_api` for REST endpoints.

**`settings.py` boot behavior:**
- Monkey-patches `json`, `shutil`, `furl`, `re` (and `redbeat.schedulers` when using RedBeat) via `monkey.py` before any app code runs.
- Adds `packages/` and `ai_agent/sdk/` to `sys.path`.
- Dynamically imports `config.role.{ROLE}` and exposes its uppercase settings.
- Loads `local_settings.py` when `RUN_MODE == "DEVELOP"`.
- Injects any environment variable starting with `BKAPP_SETTINGS_` as a Django setting.
- Merges settings from the `bk-monitor-base` dependency (`merge_django_settings`).
- Patches Django MySQL backend to allow MySQL 5.7 (minimum version check).

### `core.drf_resource` Framework

The project uses an internal lightweight framework called `core.drf_resource` for API development. It is the primary pattern for defining business logic and HTTP interfaces.

**Key abstractions:**

- **`Resource`** (`core/drf_resource/base.py`): Encapsulates a unit of business logic. Must implement `perform_request(self, validated_request_data)`. Optionally defines `RequestSerializer` and `ResponseSerializer`.
- **`ResourceViewSet`** (`core/drf_resource/viewsets.py`): Exposes one or more `Resource` classes as HTTP endpoints via `resource_routes = [ResourceRoute("POST", SomeResource)]`.
- **`ResourceRouter`** (`core/drf_resource/routers.py`): Auto-registers viewsets from a module.

**Three global entry points** are auto-discovered at startup:
- `resource`: Business logic Resources (scanned from `*/resources.py`)
- `api`: Remote API wrappers (scanned from `*/api/*/default.py`)
- `adapter`: Platform-specific overrides (scanned from `*/adapter/*/resources.py`)

Example usage:
```python
from core.drf_resource import api, resource

api.metadata.get_label({"label_type": "source_label"})
resource.some_module.some_method({"foo": "bar"})
```

**Resource naming and registration:** Resources are registered under the `resource` namespace using snake_case derived from the class name (e.g., `FetchAiSettingResource` becomes `resource.aiops.fetch_ai_setting`). Parent packages typically aggregate sub-modules via wildcard imports in `resources.py` and `views.py`.

### `kernel_api` App

`kernel_api/` is the dedicated API service entry point. It exposes REST endpoints for internal and external consumers.

- **`kernel_api/urls.py`**: Root URL configuration for the API role. Registers routes for API versions v2, v3, and v4.
- **`kernel_api/views/v2/`**, **`v3/`**, **`v4/`**: ViewSet modules organized by API version.
  - v3 is typically metadata/collector focused (`collector`, `meta`, `models`, `query`).
  - v4 covers alerting, strategy, APM, BCS, reporting, etc.
- **`kernel_api/resource/`**: Resource classes that wrap or bridge functionality from other apps (e.g., `alert.py`, `metrics.py`, `query.py`).
- **`kernel_api/extend_views/`** and **`kernel_api/extend_resource/`**: Extension hooks for custom API additions.

Views in `kernel_api` are typically very thin. Business logic lives in `Resource.perform_request()` or in the auto-discovered `resource`/`api` modules of other apps.

### Web vs API Entry Points

The project has two distinct URL configurations:

- **`urls.py`** (root): Used by the **web/SaaS** role (`ROLE=web`). Serves the full BlueKing Monitor web UI, admin, swagger, and packages (`monitor_web`, `fta_web`, `apm_web`, etc.).
- **`kernel_api/urls.py`**: Used by the **API** role (`ROLE=api`). Serves programmatic endpoints under `/api/v2/`, `/api/v3/`, `/api/v4/`, and Grafana proxy routes.

### Key Application Directories

- **`packages/`**: Added to `sys.path` at startup (`settings.py`). Contains major sub-applications:
  - `monitor_web/`: Web UI backend
  - `fta_web/`: Fault Tree Automation web
  - `apm_web/`: APM web interfaces
  - `monitor_api/`: Internal API definitions
  - `monitor_adapter/`: Adapter layer
  - `apm_trace/`: Distributed tracing interfaces
  - `weixin/`: WeChat mini-program backend
- **`bkmonitor/`**: Core Django app containing models (strategies, BCS resources, FTA, configs), data sources, and utilities.
- **`metadata/`**: Metadata management (data IDs, result tables, ES indices, storage configs, BCS entity relations, data links).
- **`alarm_backends/`**: Background alert processing engine (access, detect, trigger, action). See `alarm_backends/CODEBUDDY.md`.
- **`core/`**: Shared frameworks (`drf_resource`, `prometheus`, etc.).
- **`api/`**: ESB/APIGW client wrappers.
- **`apm/`**, **`apm_ebpf/`**: APM core and eBPF collection apps.
- **`ai_whale/`**: AI assistant integration.
- **`bkm_space/`**, **`bkm_ipchooser/`**: Space management and IP selector utilities.
- **`query_api/`**: Query-specific API layer.
- **`calendars/`**: On-call calendar management.
- **`constants/`**: Domain-specific constants shared across `bkmonitor/` and `packages/`. Examples: `constants.aiops`, `constants.data_source`, `constants.strategy`.
- **`webpack/`**: Frontend application code (TypeScript/Vue/React). Backend packages in `packages/monitor_web/` often have corresponding frontend pages under `webpack/src/monitor-pc/pages/`.

### Database Routing

Multiple databases are used, with logic in `bkmonitor/db_routers.py`:

- `default`: Main SaaS database
- `monitor_api`: Backend/monitoring API database
- `backend_alert` (or `default` when `BACKEND_DATABASE_NAME == "default"`): Alert-specific models

Routing rules:
- Backend apps (`bkmonitor`, `metadata`, `apm`, `calendars`, `monitor_api`) read/write to `monitor_api`.
- Alert models (`ActionInstance`, `ConvergeInstance`, `ConvergeRelation`) read/write to the alert router DB.
- Migrations for backend apps are **blocked** on `default` to prevent schema drift.
- Dynamic overrides are supported via `local.DB_FOR_READ_OVERRIDE` and `local.DB_FOR_WRITE_OVERRIDE`.

Legacy aliases (`bk_monitor_saas`, `bk_monitor_api`) are initialized in `settings.py` for compatibility with `bk-monitor-base`.

### `monitor_web` Sub-app Pattern

Sub-applications under `packages/monitor_web/` (and similar package dirs) follow a standard `drf_resource` layout:

- **`resources.py`**: `Resource` classes implementing business logic.
- **`views.py`**: `ResourceViewSet` classes exposing HTTP endpoints.
- **`urls.py`**: `ResourceRouter` wiring the viewsets into URL routes.
- **`serializers.py`** (optional): DRF serializers for request/response validation.

Parent packages aggregate children via wildcard imports:
```python
# monitor_web/aiops/resources.py
from monitor_web.aiops.ai_setting.resources import *  # noqa
from monitor_web.aiops.host_monitor.resources import *  # noqa
```

### `bkmonitor/models` Organization

Models are organized by domain under `bkmonitor/models/` (e.g., `aiops.py`, `strategy.py`, `fta.py`). The package-level `bkmonitor/models/__init__.py` re-exports the most commonly used models so imports like `from bkmonitor.models import AIFeatureSettings` work.

### AI / Anomaly Detection Architecture

AI features are split between a core configuration layer and a web API layer:

- **`bkmonitor/aiops/utils.py`**: `AiSetting` class is the central configuration manager for AI features per business (`bk_biz_id`). It reads/writes the `AIFeatureSettings` model and provides typed access to:
  - KPI Anomaly Detection (single-metric)
  - Multivariate Anomaly Detection (host scene)
  - Dimension Drill
  - Metric Recommend
- **`bkmonitor/models/aiops.py`**: `AIFeatureSettings` Django model stores AI configuration as JSON per `bk_biz_id`.
- **`monitor_web/aiops/`**: Web API layer (`FetchAiSettingResource`, `SaveAiSettingResource`, host anomaly queries).
- **`bkmonitor/dataflow/`**: Intelligent detection pipeline execution (dataflow task creation, status tracking).

`AiSetting.is_access_aiops()` checks whether a scene is fully enabled and its dataflow pipeline is successfully created (`AccessStatus.SUCCESS`).

## Important Conventions

- **Line length**: 120 characters (Ruff config)
- **Patch modules**: `monkey.py` patches `json`, `shutil`, `furl`, `re` at startup by loading override implementations from `patches/`. Be aware when modifying low-level behavior.
- **Local settings**: `local_settings.py` can be created for personal overrides in development. It is gitignored.
- **bk-monitor-base integration**: `settings.py` merges settings from the `bk-monitor-base` editable dependency and initializes legacy database aliases (`bk_monitor_saas`, `bk_monitor_api`).
- **Import paths**: Because `packages/` is added to `sys.path`, imports from package apps omit the `packages.` prefix:
  - `from monitor_web.xxx import ...` (not `from packages.monitor_web.xxx`)
  - `from constants.xxx import ...` (not `from bkmonitor.constants.xxx`)
  - `from bkmonitor.xxx import ...` for core utilities and models

## Sub-Project Documentation

Several major components have their own `CODEBUDDY.md` with deeper domain guidance:

- `alarm_backends/CODEBUDDY.md` — Alert pipeline architecture (access → detect → trigger → alert → fta_action), Redis queues, service handlers.
- `metadata/CODEBUDDY.md` — Metadata models, data sources, result tables, storage configs, data links, space management.
- `packages/CODEBUDDY.md` — Package inventory, sub-app patterns, proxy models, frontend correspondence.
- `packages/monitor_web/CODEBUDDY.md` — Web UI backend sub-apps, scene views, plugin lifecycle, K8s monitoring, statistics v2.
- `packages/monitor_api/CODEBUDDY.md` — Auto-generated REST API for `MONITOR_API_MODELS`.
- `packages/apm_web/CODEBUDDY.md` — APM web backend specifics.
- `query_api/CODEBUDDY.md` — Query API layer conventions.
