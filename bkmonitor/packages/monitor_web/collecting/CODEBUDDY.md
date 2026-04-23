# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## App Overview

This is the `monitor_web.collecting` Django app within **bkmonitor** (BlueKing Monitor). It manages collection configurations — the deployment, lifecycle, and status of metric/log collection plugins across hosts and Kubernetes clusters.

- **Parent project**: See `/root/bk-monitor-learn/bkmonitor/CODEBUDDY.md` for monorepo-level guidance
- **Depends on**: `monitor_web.plugin`, `monitor_web.models`, `core.drf_resource`, Node Management (bk-nodeman)

## Architecture

### Resource-Based API Layer

Like other `monitor_web` apps, this app uses the `core.drf_resource` framework:

- **`views.py`**: `CollectingConfigViewSet` exposes all HTTP endpoints via `ResourceRoute` declarations. IAM permissions are enforced per action using `BusinessActionPermission` with `ActionEnum.VIEW_COLLECTION` / `MANAGE_COLLECTION`.
- **`resources/`**: Business logic lives here. Files are organized by domain:
  - `backend.py`: Core CRUD — list, save, delete, clone, toggle status, upgrade, rollback
  - `frontend.py`: Frontend-specific adapters that reshape backend data for the UI
  - `status.py`: Deployment status queries, target status topology, instance status
  - `toolkit.py`: Maintenance utilities — legacy subscription cleanup, related strategies, adjective collect checks
  - `snmp_trap.py`: SNMP trap-specific handling

Resources are auto-discovered via the `resource` namespace (imported from `resources/__init__.py`).

### Deployment Abstraction (`deploy/`)

Collection configurations are deployed through an installer pattern:

- **`deploy/base.py`**: `BaseInstaller` abstract class defining the contract: `install`, `upgrade`, `uninstall`, `rollback`, `stop`, `start`, `run`, `retry`, `revoke`, `status`
- **`deploy/node_man.py`**: `NodeManInstaller` — for host-based and traditional service collection. Integrates with BlueKing Node Management (bk-nodeman) via subscriptions
- **`deploy/k8s.py`**: `K8sInstaller` — for Kubernetes cluster collection
- **`deploy/__init__.py`**: `get_collect_installer()` selects the installer based on `PluginType`

### Key Models

Defined in `monitor_web/models/collecting.py`:

- **`CollectConfigMeta`**: The main collection configuration record. Tracks name, business, plugin, target type, current status, and latest operation result
- **`DeploymentConfigVersion`**: Immutable deployment snapshots. Each save/upgrade/rollback creates a new version, enabling rollback

### Status and Locking

- **`constant.py`**: Defines status enums (`Status`, `CollectStatus`, `OperationType`, `OperationResult`, `TaskStatus`)
- **`lock.py`**: `CacheLock` decorator prevents concurrent edits to the same collection config using Django cache

## Tests

Tests are in `monitor_web/tests/collecting/`:

```bash
# Run collecting tests
pytest packages/monitor_web/tests/collecting/

# Run a specific test
pytest packages/monitor_web/tests/collecting/test_collecting.py::TestCollectingViewSet
```

Note: Tests use `celery_app.conf.task_always_eager = True` to run Celery tasks synchronously.

## Important Conventions

- **IAM Actions**: Read actions use `VIEW_COLLECTION`; write actions use `MANAGE_COLLECTION`. `query_post_actions` lists POST endpoints that are still read-only for permission purposes.
- **Node Management API**: Host-based deployments rely heavily on `api.node_man.*` (subscriptions, statistic fetching). Bulk requests are chunked (e.g., 20 subscription IDs per call in `fetch_sub_statistics`).
- **Plugin Lifecycle**: Collecting configs are tied to `CollectorPluginMeta` and `PluginVersionHistory`. When a plugin releases a new version, configs may need `upgrade_collect_plugin`.
- **Deployment Diff**: Installers return a `diff_node` structure showing added/removed/updated/unchanged targets after each operation.
