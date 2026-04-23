# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is the `weixin` package within **bkmonitor** (BlueKing Monitor). It provides the backend for the WeChat / Enterprise WeChat (企业微信) mobile mini-program interface. It is a Django app located under `packages/weixin/` and is included in the main project via `sys.path` (see parent `settings.py`).

This package depends heavily on the parent `bkmonitor` project for settings, models, the `core.drf_resource` framework, and alert data access.

## Common Commands

This package does not have its own build system; it uses the parent project's tooling (see `../CODEBUDDY.md` for general setup with `uv`, `ruff`, and `basedpyright`).

### Testing

Run tests for this app from the repo root (`bkmonitor/`):

```bash
# Run all weixin tests
pytest packages/weixin

# Run a specific test file
pytest packages/weixin/tests.py

# Run Django manage.py tests for this app
python manage.py test weixin
python manage.py test weixin.tests
```

## Architecture

### Package Structure

```
weixin/
├── urls.py                 # Root URLconf: /weixin/ entry points
├── views.py                # Renders weixin/index.html, service-worker.js, manifest.json
├── core/                   # WeChat authentication & session management
│   ├── accounts.py         # WeixinAccount (OAuth flow, singleton)
│   ├── api.py              # WeiXinApi & QyWeiXinApi HTTP wrappers
│   ├── models.py           # BkWeixinUser model
│   ├── settings.py         # Environment-driven config (app ID, secrets, URLs)
│   ├── middlewares.py      # WeixinProxyPatch, WeixinAuthentication, WeixinLogin
│   ├── decorators.py       # @weixin_login_exempt, @weixin_login_required
│   └── context_processors.py  # Template context: WX_USER, BK_USER, WEIXIN_SITE_URL
├── event/                  # Mobile alert/event REST API
│   ├── resources.py        # Business logic: GetAlarmDetail, GetEventDetail,
│   │                       #   GetEventGraphView, GetEventList, AckEvent, QuickShield
│   ├── views.py            # EventViewSet & QuickAlertHandleViewSet (ResourceViewSet)
│   └── urls.py             # ResourceRouter for /weixin/rest/v1/event/
└── tests/                  # Test directory (currently empty except __init__.py)
```

### Authentication Flow (`weixin.core`)

The mobile backend supports both standard WeChat (微信公众号) and Enterprise WeChat (企业微信) OAuth2 login.

1. **Detection** — `WeixinProxyPatchMiddleware` detects WeChat visits by matching `request.path` against `WEIXIN_SITE_URL` and the host against `WEIXIN_APP_EXTERNAL_HOST`.
2. **Session** — `WeixinAuthenticationMiddleware` attaches `request.weixin_user` (a `BkWeixinUser` instance or `AnonymousUser`) and `request.user` (the mapped BlueKing user via `UserProperty`).
3. **Login enforcement** — `WeixinLoginMiddleware` exempts BlueKing login for WeChat paths and redirects unauthenticated users to the WeChat OAuth authorization URL.
4. **OAuth callback** — `WeixinAccount.login()` handles the callback: verifies `state` and `code`, exchanges the code for an access token/user info via `WeiXinApi` or `QyWeiXinApi`, and creates/updates the `BkWeixinUser` record.

### Event API (`weixin.event`)

The mobile client consumes alert and event data through a `ResourceViewSet`-based API under `/weixin/rest/v1/event/`.

- **Resources** in `event/resources.py` extend `AlertPermissionResource` (from `fta_web.alert.resources`) and implement `perform_request`.
- Data sources:
  - `AlertDocument` / `ActionInstanceDocument` — Elasticsearch documents for alerts and actions.
  - `ActionInstance` — Django ORM model for action instances.
- Key endpoints:
  - `get_alarm_detail` — Aggregated alert info with related event list.
  - `get_event_detail` — Single event detail with dimensions and related CMDB info.
  - `get_event_graph_view` — Metric graph data via `AIOPSManager.get_graph_panel` and `resource.alert.alert_graph_query`.
  - `get_event_list` — Lists abnormal events, grouped by strategy or target.
  - `quick_shield` / `ack_event` — Quick shielding and acknowledgement of alerts.

### URL Routing

`weixin/urls.py` mounts three sub-routes:
- `rest/v1/` → `weixin.event.urls` (ResourceRouter APIs)
- `login/` → `weixin.core.urls` (OAuth callback handler)
- `^$` → Home page (`weixin/index.html`)

## Configuration

All WeChat-specific settings are driven by environment variables and collected in `weixin/core/settings.py`:

| Variable | Purpose |
|---|---|
| `BKAPP_USE_WEIXIN` | Enable mobile WeChat access (`1` to enable) |
| `BKAPP_IS_QY_WEIXIN` | Use Enterprise WeChat (`1` to enable) |
| `BKAPP_WEIXIN_APP_ID` | WeChat App ID / Enterprise WeChat Corp ID |
| `BKAPP_WEIXIN_APP_SECRET` | Corresponding secret |
| `BKAPP_WEIXIN_AGENT_ID` | Enterprise WeChat agent ID |
| `BKAPP_WEIXIN_SITE_URL` | External mobile access path (e.g. `/xxxxx/bkmonitor/`) |
| `BKAPP_WEIXIN_STATIC_URL` | External static asset path |
| `BKAPP_WEIXIN_APP_EXTERNAL_HOST` | External domain accessible by WeChat |
| `BKAPP_WEIXIN_QY_OPEN_DOMAIN` | Private deployment OAuth domain (default: `https://open.weixin.qq.com`) |
| `BKAPP_WEIXIN_QY_API_DOMAIN` | Private deployment API domain (default: `https://qyapi.weixin.qq.com`) |

## Important Conventions

- **Line length**: 120 characters (inherited from parent Ruff config).
- The `weixin` app uses `core.drf_resource` for API development (see parent `CODEBUDDY.md` for framework details).
- Error codes for this module are defined in `core/errors/weixin/event.py` (status code `400`, base code `3319000`).
- When modifying `BkWeixinUser` fields, remember to create migrations via `python manage.py makemigrations weixin` from the repo root.
