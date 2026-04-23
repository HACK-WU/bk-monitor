# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is **`apm_web`** (Application Performance Monitoring Web), a Django application package within the larger **bkmonitor** (BlueKing Monitor) project. It provides the web backend for APM features including distributed tracing, continuous profiling, metric queries, service topology, and application management.

- **Parent project**: `bkmonitor/` (see `bkmonitor/CODEBUDDY.md` for global commands and architecture)
- **Python version**: 3.11 (strictly `==3.11.*`)
- **Django version**: 4.2.27
- **Package path**: `packages/apm_web/` (added to `sys.path` at startup)

## Common Commands

### Dependencies

Dependencies are managed via `uv` in the parent `bkmonitor/` directory:

```bash
# From bkmonitor/ root
uv sync --all-groups
```

### Code Quality

Run from the `bkmonitor/` root:

```bash
ruff check packages/apm_web/
ruff format packages/apm_web/
basedpyright
```

### Testing

`apm_web` tests are **not** included in the default `pytest` testpaths. Run them explicitly:

```bash
# Run all apm_web tests
pytest packages/apm_web/tests/ --reuse-db

# Run a specific test file
pytest packages/apm_web/tests/test_list_application_async.py --reuse-db

# Run a specific test
pytest packages/apm_web/tests/test_list_application_async.py::test_list_application_async --reuse-db

# Run profile tests
pytest packages/apm_web/tests/profile/ --reuse-db

# Run trace tests
pytest packages/apm_web/tests/trace/ --reuse-db
```

Note: `--reuse-db` is recommended to speed up iterative test runs.

### Running the Development Server

From the `bkmonitor/` root:

```bash
export DJANGO_CONF_MODULE=conf.web.development.community
export django_find_project=false
python manage.py runserver 0.0.0.0:8000
```

## Architecture

### Package Structure

`apm_web/` is organized into feature modules, each following a consistent pattern:

```
apm_web/
├── meta/          # Application lifecycle (CRUD, setup, sampling, storage, custom services)
├── trace/         # Distributed tracing (trace list, span detail, trace diagram, comparisons)
├── profile/       # Continuous profiling (flamegraph, callgraph, diff, upload, pprof/perf/doris converters)
├── metric/        # APM metrics (apdex, error rate, request count, unify query integration)
├── service/       # Service management (service list, config, pipeline, code redefinition)
├── topo/          # Service topology (graph, node relations, endpoint tops)
├── db/            # DB monitoring (slow queries, DB system list, DB spans)
├── container/     # Container/K8s-related APM views
├── event/         # APM events and exceptions
├── strategy/      # Alert strategy templates and instances for APM
├── custom_metric/ # Custom metric definitions
├── log/           # APM log correlation
├── handlers/      # Business logic handlers (application, service, component, endpoint, instance, span, backend data)
├── models/        # Django models (Application, ProfileUploadRecord, service relations, strategy)
├── resources.py   # Shared base Resource classes (SidebarPageListResource, AsyncColumnsListResource)
├── constants.py   # APM-wide constants and enums
├── metric_handler.py  # Metric calculation helpers (ApdexInstance, RequestCountInstance, etc.)
├── metrics.py     # Application list metric aggregations
├── tasks.py       # Celery tasks (profile upload/parsing, data cleanup)
└── urls.py        # Root URLconf wiring submodules
```

Each submodule typically contains:
- `resources.py` — `Resource` classes implementing business logic
- `views.py` — `ResourceViewSet` classes exposing HTTP endpoints
- `urls.py` — `ResourceRouter` registration
- `serializers.py` — DRF serializers (when needed)

### API Framework (`core.drf_resource`)

Like the rest of bkmonitor, `apm_web` uses the internal `core.drf_resource` framework.

- **`Resource`** (`core/drf_resource/base.py`): Business logic unit. Implement `perform_request(self, validated_request_data)`. Define `RequestSerializer` for input validation.
- **`ResourceViewSet`** (`core/drf_resource/viewsets.py`): Exposes Resources via `resource_routes = [ResourceRoute("POST", SomeResource, endpoint="...")]`.
- **`ResourceRouter`** (`core/drf_resource/routers.py`): Auto-registers viewsets.

Example from `apm_web/meta/views.py`:
```python
class ApplicationViewSet(ResourceViewSet):
    INSTANCE_ID = "application_id"
    resource_routes = [
        ResourceRoute("GET", ApplicationInfoResource, endpoint="application_info", pk_field="application_id"),
        ResourceRoute("POST", CreateApplicationResource, endpoint="create_application"),
        ...
    ]
```

### Permission Model

APM endpoints use `bkmonitor.iam.drf` permission classes:

- **`ViewBusinessPermission`** — basic business access
- **`InstanceActionPermission`** — action on a specific APM application
- **`InstanceActionForDataPermission`** — action on an instance resolved from request data

Common actions:
- `ActionEnum.VIEW_APM_APPLICATION` — read-only access
- `ActionEnum.MANAGE_APM_APPLICATION` — write access (setup, start, stop, delete)

### Key Models

Defined in `apm_web/models/`:

- **`Application`** (`application.py`): Central APM application configuration. Stores app_name, bk_biz_id, plugin/deployment/language settings, datasource configs (ES retention, cluster), Apdex config, sampling config, and data status.
- **`ProfileUploadRecord`** (`profile.py`): Tracks uploaded profiling files.
- **`ApmMetaConfig`** (`application.py`): Key-value configuration storage for applications.
- **Service Relations** (`service.py`): `AppServiceRelation`, `CMDBServiceRelation`, `LogServiceRelation`, `UriServiceRelation` — link APM services to CMDB, logs, and URIs.
- **Strategy Models** (`strategy.py`): `StrategyTemplate`, `StrategyInstance` — APM-specific alert strategy templates.

### Profile Module Architecture

The profile module (`apm_web/profile/`) has a pluggable converter architecture for different profiling data formats:

- **`profileconverter.py`** — Registry pattern. Converters are registered in `apps.py` via `register_profile_converter`.
- **Supported formats** (`constants.InputType`):
  - `DORIS` — `DorisProfileConverter` (queries Doris database)
  - `PPROF` — `PprofProfileConverter` (Google pprof format)
  - `PERF_SCRIPT` — `PerfScriptProfileConverter` (Linux perf script output)
- **`diagrams/`** — Renderers for different visualizations:
  - `flamegraph.py`, `callgraph.py`, `table.py`, `tendency.py`, `diff.py`, `dotgraph.py`
  - `tree_converter.py` — Converts profile data to tree structure
  - `ebpf_converter.py` — eBPF-specific conversions
- **`doris/`** — Doris-specific query layer (`querier.py`, `converter.py`)
- **`file_handler.py`** — Handles uploaded profile files
- **`patch.py`** — Performance patches for profile parsing

### Trace Module Architecture

The trace module (`apm_web/trace/`) handles distributed tracing queries:

- **`resources.py`** — Trace/span listing, detail retrieval, statistics, field options, comparisons
- **`diagram/`** — Trace visualization (flamegraph, sequence, topology)
- **`trace_handler/`** — Dimension statistics and trace analysis helpers
- Exports `ListFlattenSpanResource` and `ListFlattenTraceResource` for use by the alerting system (imported in `apm_web/resources.py`)

### Metric Module Architecture

The metric module (`apm_web/metric/`) integrates with the bkmonitor unified query system:

- **`resources.py`** — Service/endpoint/instance lists, apdex/error rate/request count queries, host details, top-N queries
- **`handler/`** — `top_n.py`, `statistics.py` for metric aggregation helpers
- Uses `apm_web.metric_handler` classes (`ApdexInstance`, `RequestCountInstance`, `ErrorRateInstance`, etc.) for standardized metric calculations

### Shared Base Resources

`apm_web/resources.py` defines base Resource classes used across submodules:

- **`SidebarPageListResource`** — Paginated list with overview row calculation, dynamic sort columns, filtering, and formatting. Used for most sidebar table APIs.
- **`AsyncColumnsListResource`** — Supports columns that are populated by separate async requests.
- **`ServiceAndComponentCompatibleResource`** — Adapts field names for service/component sidebar compatibility.

### Backend Data Handlers

`apm_web/handlers/backend_data_handler.py` implements a telemetry data handler registry (`telemetry_handler_registry`) that processes incoming APM data (traces, metrics, logs, profiling) and updates application data status.

### Constants and Configuration

`apm_web/constants.py` defines:
- APM application defaults (QPS, no-data period, dimension period)
- OTLP/Jaeger span kind mappings
- Component filter mappings (DB, messaging)
- Scene keys and category enums
- Trace view configurations

## Integration Points

- **Parent URLs**: `apm_web` is wired into the root URLconf via `urls.py` in the parent project (under `apm/` path).
- **Auto-discovered resources**: Some `apm_web/profile/resources.py` and `apm_web/trace/resources.py` classes are imported in `apm_web/resources.py` to make them available to the global `resource` registry and external consumers (Grafana dashboards, alert center).
- **Celery tasks**: `apm_web/tasks.py` defines background tasks registered with the project's Celery app.
- **IAM**: Uses `bkmonitor.iam` for permission checks on APM applications.
