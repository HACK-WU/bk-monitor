# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

`bk_dataview` is a Django app inside the `bkmonitor` project that acts as a **Grafana proxy and integration layer**. It forwards web requests to a backend Grafana instance, synchronizes users/orgs/permissions into Grafana's database, and injects default datasources and dashboards.

- **Python version**: 3.11
- **Django version**: 4.2.27
- This app has **no standalone build or test commands**. Use the parent `bkmonitor` commands (see `../CODEBUDDY.md`):
  - `ruff check .` / `ruff format .`
  - `basedpyright`
  - `pytest packages/monitor_web/tests/grafana/...`
  - `python manage.py test ...`

## Architecture

### Request Flow

HTTP requests arrive at `/grafana/` (routed via `packages/monitor_adapter/grafana/urls.py`) and are handled by view subclasses in `packages/monitor_adapter/grafana/views.py`. These views extend the base proxy classes defined in `bk_dataview/views.py`:

1. `SwitchOrgView` (`/grafana/`, `/grafana/home`, `/grafana/d/<uid>`)
   - Determines the Grafana org from `orgName` query param or `space_uid`.
   - Runs authentication, user sync, permission sync, and **provisioning** (injecting default datasources/dashboards).
   - The production subclass is `GrafanaSwitchOrgView`.

2. `ProxyView` (all other Grafana UI paths)
   - Proxies the request to `GRAFANA_URL` with `X-WEBAUTH-USER` and `X-Grafana-Org-Id` headers.
   - The production subclass is `GrafanaProxyView`.

3. `StaticView` (`/grafana/public/`, `/grafana/avatar/`)
   - Pass-through proxy for static assets; skips auth and provisioning.

4. `ApiProxyView` (`/grafana/api/...`)
   - Like `ProxyView` but with permission classes disabled and external-user search filtering.

### Models (Grafana Database)

All models in `models.py` are **unmanaged** (`managed = False`) and map directly to Grafana's MySQL tables:

- `User`, `Org`, `OrgUser` — users and org membership
- `Dashboard`, `DataSource` — dashboards and datasources
- `Role`, `Permission`, `BuiltinRole`, `UserRole` — RBAC tables
- `Team`, `TeamMember`, `TeamRole`, `Preferences`, `Star`

The app uses a dedicated database router (`router.DBRouter`) that routes all `bk_dataview` models to the **`bk_dataview`** database alias (configured in `config/default.py` pointing to `GRAFANA_MYSQL_*`).

### Key Modules

| File | Responsibility |
|------|----------------|
| `views.py` | Base proxy view classes (`ProxyBaseView`, `SwitchOrgView`, `ProxyView`, `StaticView`). |
| `api.py` | High-level operations: `get_or_create_org`, `get_or_create_user`, `sync_user_role`, `sync_dashboard_permission`, `get_dashboard_tree`. Uses both ORM and `client.py`. |
| `client.py` | Low-level HTTP client for Grafana Admin API (users, orgs, datasources, dashboards). |
| `permissions.py` | Enums `GrafanaRole` / `GrafanaPermission` and `BasePermission` / `IsAuthenticated` / `AllowAny`. |
| `authentication.py` | `BaseAuthentication` and `SessionAuthentication`. |
| `provisioning.py` | `BaseProvisioning` / `SimpleProvisioning` for auto-injecting datasources and dashboards from YAML/JSON files. |
| `settings.py` | `GrafanaSettings` class that reads `settings.GRAFANA` dict with defaults (`HOST`, `PREFIX`, `ADMIN`, `AUTHENTICATION_CLASSES`, `PERMISSION_CLASSES`, `PROVISIONING_CLASSES`, `CODE_INJECTIONS`). |
| `router.py` | `DBRouter` forcing `bk_dataview` app models to the `bk_dataview` DB alias. |
| `utils.py` | `generate_uid`, `requests_curl_log`, `os_env` context manager. |

### Production Overrides

The base classes in `bk_dataview` are **intended to be subclassed**. The actual running code lives in:

- `packages/monitor_adapter/grafana/views.py`
  - `GrafanaSwitchOrgView` — adds IAM permission checks, external-user handling, watermark injection, and home-dashboard patching.
  - `GrafanaProxyView` — adds API exemptions, access-control blocking, and header overrides for single-dashboard permissions.
  - `ApiProxyView` — filters search results for external users.
  - `RedirectDashboardView` — redirects to a dashboard by `bizId` + `dashName`.

- `packages/monitor_web/grafana/permissions.py`
  - `DashboardPermission` — integrates with BlueKing IAM (`ActionEnum.MANAGE_DATASOURCE`, `MANAGE_DASHBOARD`, `VIEW_DASHBOARD`, `VIEW_SINGLE_DASHBOARD`, `EDIT_SINGLE_DASHBOARD`).
  - Supports folder-level permissions expanded to individual dashboards.
  - Handles external user permissions via `ExternalPermission` model.

- `packages/monitor_web/grafana/provisioning.py`
  - `BkMonitorProvisioning` — extends `SimpleProvisioning` to inject BlueKing-specific default dashboards (host, observable, kubernetes, etc.) and track creation state in `ApplicationConfig`.

## Important Conventions

- **Do not write migrations for `bk_dataview` models.** They are `managed = False` and schema changes must be applied via Grafana itself.
- **Org name = `bk_biz_id`** (business ID) in production. The org is created on first access.
- **Code injection**: `GrafanaSettings.CODE_INJECTIONS` replaces HTML tags in Grafana responses (e.g., hiding the side menu via CSS). Admin users with `?develop` can skip injection.
- **Caching**: `api.py` keeps simple module-level caches (`_ORG_CACHE`, `_USER_CACHE`).
- **Dashboard UID generation**: `utils.generate_uid` creates 9-char random strings (letters, digits, underscore) avoiding collisions.
