# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is the `support-files` directory of the BlueKing Monitor (`bkmonitor`) platform. It contains deployment configuration templates, API gateway resource definitions, initial seed data, and SQL scripts consumed by the main Django application. There is no standalone build, test suite, or package manager for this directory.

- **Parent Project**: `bkmonitor/` (see `bkmonitor/CODEBUDDY.md` for general project info)
- **Repo Root**: `bk-monitor-learn/`

## Common Commands

Commands referencing `support-files` are typically run from the `bkmonitor/` repository root.

### API Gateway

```bash
# Merge all APIGW resource YAMLs into a single resources.yaml
python support-files/apigw/scripts/merge_resources.py

# Sync gateway definition, stages, resources, docs, permissions, and public key
# (runs merge_resources.py internally)
python manage.py sync_apigw
```

### Template Rendering

Templates in `templates/` use placeholder variables (`__PLACEHOLDER__` and `${VARIABLE}`) that are substituted during deployment. There is no local render command; substitution is performed by the release packaging script (`version/pack.sh`) or deployment tooling.

### Validation

There is no dedicated test suite for `support-files`. When modifying APIGW YAMLs, run the merge script as a syntax/structure sanity check:

```bash
python support-files/apigw/scripts/merge_resources.py
```

## High-Level Architecture

### `apigw/` — BlueKing API Gateway Definitions

The monitor platform exposes APIs through the BlueKing API Gateway (`bk-monitor`). Resources are defined as OpenAPI-style YAML files and organized by visibility and authentication mode.

**Directory Layout:**

```
apigw/
├── definition.yaml          # Gateway metadata, stages, proxy, permissions
├── resources.yaml           # Generated merged resource file (do not edit manually)
├── resources/
│   ├── internal/            # Internal APIs (isPublic=false, admin-authorized only)
│   │   ├── app/             # App-state APIs (no user auth)
│   │   └── user/            # User-state APIs (user auth required)
│   └── external/            # External APIs (isPublic=true, users can apply)
│       ├── app/
│       └── user/
├── docs/zh/                 # Per-operation markdown docs (filename = operationId)
└── scripts/
    ├── merge_resources.py   # Merges resources/ into resources.yaml
    └── esb_to_apigw.py      # Converts old ESB YAML to APIGW format
```

**Conventions:**
- Path format: `/{app|user}/{module}/{action}/` or `/{app|user}/{module}/{action}/vX/`
- Operation IDs: lowercase snake_case, prefixed with module name (e.g., `metadata_create_data_id`)
- `merge_resources.py` auto-sets:
  - `isPublic` / `allowApplyPermission` based on `internal` vs `external`
  - `userVerifiedRequired` based on `app` vs `user`
  - `tags` from the YAML filename if not explicitly provided

**Consumers:**
- `bkmonitor/management/commands/sync_apigw.py` runs `merge_resources.py` and syncs to the gateway.
- `core/drf_resource/contrib/nested_api.py` loads APIGW YAMLs at runtime to build an in-memory API routing table (`API_DEFINE`) for the `api` role.

### `fta/` — Fault Tree Automation Initial Data

Seed data for builtin FTA plugins and action configs, loaded at Django startup via signal handlers.

| File | Consumer | Purpose |
|------|----------|---------|
| `action_plugin_initial.json` | `fta_web.handlers.register_builtin_plugins` | Builtin action plugins (notice, webhook, itsm, etc.) |
| `action_config_initial.json` | `fta_web.handlers.register_builtin_action_configs` | Default action config records |
| `event_plugins/*.tar.gz` | `fta_web.handlers.install_global_event_plugin` | Bundled event plugin packages (e.g., rest_api, zabbix) |

IDs below 1000 are reserved for builtins. These files are loaded via `update_or_create` on startup, so changes affect existing deployments on the next restart.

### `iam/` — Identity and Access Management Migrations

JSON files containing IAM model definitions (actions, resources, instance selections, etc.) for the `bk_monitorv3` system. These are loaded incrementally by IAM management commands in the parent project (e.g., `python manage.py iam_migrate`).

Files follow a numbered sequence (`0001_initial.json` through `0010_apm_mcp.json`) plus a `rollback.json`.

### `sql/` — Database Initialization

SQL scripts run during initial deployment. For example:
- `0001_monitor_20200113-0000_mysql.sql` — Creates `bk_monitorv3_grafana` and `bkmonitorv3_alert` databases.

### `templates/` — Service Configuration Templates

Configuration templates for satellite services and supervisors. File names use `#` as a path separator to denote target locations (e.g., `transfer#transfer.yaml` -> `transfer/transfer.yaml`).

Placeholders use two forms:
- `__UPPER_SNAKE_CASE__` — deployment-specific values (IPs, ports, credentials)
- `${PLATFORM}` — platform type (community, enterprise, ieod)

**Key templates:**

| Template | Service |
|----------|---------|
| `transfer#transfer.yaml` | bkmonitor transfer (data ingestion / ETL) |
| `ingester#ingester.yaml` | Ingester service |
| `unify-query#unify-query.yaml` | Unify Query service |
| `influxdb-proxy#etc#influxdb-proxy.yml` | InfluxDB proxy |
| `grafana#conf#grafana.ini` | Grafana (auth proxy, DB config, plugin allowlist) |
| `monitor#bin#environ.sh` | Environment variable script sourced by services |
| `#etc#supervisor-bkmonitorv3-*.conf` | Supervisor configs for monitor, transfer, grafana, influxdb-proxy |

**Deployment Note:** `version/pack.sh` strips `support-files/templates` and `support-files/sql` for `web` packages and substitutes `${PLATFORM}` for non-web packages.

### `supervisord.conf` — SaaS Supervisor Template

Template for the SaaS deployment supervisor. Defines programs for:
- `{{app_code}}_uwsgi` — Gunicorn web worker
- `{{app_code}}_celery` — General Celery worker
- `{{app_code}}_celery_resource` — Celery worker for the `celery_resource` queue

## Important Code Locations

| Concern | Location |
|---------|----------|
| APIGW merge script | `support-files/apigw/scripts/merge_resources.py` |
| APIGW sync command | `bkmonitor/management/commands/sync_apigw.py` |
| FTA plugin registration | `packages/fta_web/handlers.py` |
| Runtime API routing table | `core/drf_resource/contrib/nested_api.py` |
| Release packaging | `version/pack.sh` |
| Grafana plugin allowlist | `templates/grafana#conf#grafana.ini` [plugins] |
