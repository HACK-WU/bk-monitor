# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Context

`monitor_api` is a Django app inside the larger **bkmonitor** (BlueKing Monitor) project. It lives at `packages/monitor_api/` and is included in `INSTALLED_APPS` for both the `web` and `api` roles. It is not a standalone package — it depends on the parent Django project (`bkmonitor/`) for settings, database routing, and the `core.drf_resource` framework.

## Architecture

### Auto-Generated REST API

The primary purpose of this app is to expose CRUD REST endpoints for a configurable set of Django models without hand-writing each ViewSet, Serializer, or FilterSet.

At import time, the following modules dynamically generate classes from `settings.MONITOR_API_MODELS` (defined in `config/role/web.py`):

- **`views.py`** — creates `ReadOnlyModelViewSet` or `ModelViewSet` subclasses via `get_viewset()`. Each entry in `MONITOR_API_MODELS` is a tuple of `("app_label.ModelName", read_only)`.
- **`serializers.py`** — creates `ModelSerializer` subclasses via `get_serializer()`.
- **`filtersets.py`** — creates `django_filters.FilterSet` subclasses via `get_filterset()`, with advanced lookups auto-generated per field type.

All generated classes are injected into the module's `locals()` namespace and then auto-registered by `ResourceRouter` in `urls.py`.

### Custom Endpoints

In addition to the generated ViewSets, `views.py` contains:

- **`UserConfigViewSet`** — extends the auto-generated pattern but overrides `create()` to inject `request.user.username`, and filters `get_queryset()` to the current user.
- **`AlarmTypeViewSet`** — a read-only, login-exempt endpoint that returns a hard-coded list of alarm/monitor types for host monitoring, component monitoring, shell collection, custom monitoring, and uptime checking.

### URL Routing

The app is mounted in the root `urls.py` at:

```python
path("rest/v1/", include("monitor_api.urls", namespace="monitor_api"))
```

Inside the app, `urls.py` uses `core.drf_resource.routers.ResourceRouter` to discover and register all ViewSet classes exported by `views.py`.

### Models

`models/base.py` defines a mix of:

- **Legacy unmanaged models** (`managed = False`) that map to existing tables such as `ja_monitor`, `ja_alarm_source`, `ja_detect_algorithm_config`, `ja_alarm_solution_config`, `ja_alarm_converge_config`, `ja_alarm_notice_config`, and `ja_alarm_notice_group`. These are used for querying legacy monitoring/alarm data.
- **Helper objects** like `ProcessPort`, `CustomStringIndex`, `ProcessPortIndex`, and `OSRestartIndex` — lightweight `DictObj` wrappers used by `AlarmTypeViewSet` and other consumers to represent pseudo-models.
- **`AbstractRecordModel`** — re-exported from `bkmonitor.models` and used as the base for legacy models in this app.

### Middleware

`middlewares.MonitorAPIMiddleware` is installed in `MIDDLEWARE` for the `web` role. It does two things:

1. **Exception normalization** — intercepts DRF and Django exceptions for AJAX requests and returns them as JSON 200 responses (to avoid default browser error handling). `CustomException` and `core.errors.Error` subclasses get special treatment.
2. **Gzip compression** — compresses responses when `Content-Encoding: gzip` is set, skipping small responses (< 200 bytes).

### Database

This app reads/writes to the `monitor_api` database alias, which is routed there by `bkmonitor/db_routers.py`. When `BACKEND_ALERT_MYSQL_HOST == BACKEND_MYSQL_HOST`, the `backend_alert` alias shares the same connection pool as `monitor_api`.

The `MonitorAPIConfig.ready()` method includes custom migration logic: it runs `migrate` against the `monitor_api` database, then calls `hack_settings()` before running the default migrations. It also checks for external DB aliases (e.g., `nodeman`) and removes them from `DATABASES` if unreachable.

### Pagination

`monitor_api.pagination.MonitorAPIPagination` is configured as the global DRF pagination class in `config/role/web.py`:

- Default page size: `100`
- Max page size: `1000`
- Query param: `page_size`

## Common Commands

This app has no independent build or test commands. Use the parent project's tooling:

```bash
# From the bkmonitor/ repo root

# Install dependencies
uv sync --all-groups

# Format and lint
ruff check .
ruff format .

# Run tests that touch this app (run from repo root)
pytest tests/web/fta_actions/ -k "monitor_api or monitor"
python manage.py test alarm_backends.tests

# Run the dev server (web role)
export DJANGO_CONF_MODULE=conf.web.development.community
export django_find_project=false
python manage.py runserver

# Run migrations for this app's database
python manage.py migrate monitor_api --noinput
python manage.py createcachetable --database monitor_api
```

## Key Configuration

- `MONITOR_API_MODELS` (`config/role/web.py:321`) — controls which models get auto-generated endpoints.
- `ACTIVE_VIEWS` (`config/default.py:310`) — maps `"monitor_api"` → `"monitor_api.views"` for the `ResourceRouter` auto-discovery system.
- `REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]` (`config/role/web.py:307`) — points to `monitor_api.pagination.MonitorAPIPagination`.

## Important Conventions

- Do not add hand-written ViewSets, Serializers, or FilterSets for models already listed in `MONITOR_API_MODELS`; they are generated automatically.
- Models in `models/base.py` that map to legacy tables should stay `managed = False`. Adding migrations for them will fail or clobber existing schema.
- Changes to `filtersets.py` affect **all** auto-generated endpoints because lookups are derived from field types globally.
- The `AlarmTypeViewSet` list response is constructed manually and mixes translated strings with legacy host-index logic from `utils.host_index_backend`. Be careful when modifying translation or category mappings.
