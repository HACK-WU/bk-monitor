# DJANGO_CONF_MODULE 环境配置说明

## 概述

在 `.env` 文件中，通过 `DJANGO_CONF_MODULE` 环境变量来决定项目以何种角色启动。格式为：

```
conf.{ROLE}.{ENVIRONMENT}.{PLATFORM}
```

- **ROLE**：角色类型，决定加载哪个角色配置（`web` / `worker` / `api`）
- **ENVIRONMENT**：运行环境（`development` / `testing` / `production`）
- **PLATFORM**：部署平台（如 `enterprise`）

三种配置分别为：

```bash
DJANGO_CONF_MODULE=conf.web.development.enterprise     # Web SaaS 前端服务
DJANGO_CONF_MODULE=conf.worker.development.enterprise   # 后台 Worker 服务
DJANGO_CONF_MODULE=conf.api.development.enterprise      # 内部 Kernel API 服务
```

---

## 配置加载流程

```
.env (DJANGO_CONF_MODULE)
  │
  ▼
config/tools/environment.py          # 解析出 ROLE / ENVIRONMENT / PLATFORM
  │
  ▼
settings.py                          # 根据 ROLE 动态 import config.role.{ROLE}
  │
  ├─► config/{env}.py                # 加载环境级配置 (dev.py / stag.py / prod.py)
  │
  └─► config/role/{ROLE}.py          # 加载角色级配置
        ├── web.py
        ├── worker.py
        └── api.py
```

### 核心加载逻辑（settings.py）

```python
# 1. environment.py 解析 DJANGO_CONF_MODULE → 得到 ROLE, ENVIRONMENT, PLATFORM
_, ROLE, ENVIRONMENT, PLATFORM = DJANGO_CONF_MODULE.split(".")

# 2. settings.py 根据 ROLE 动态加载角色配置
_module = __import__(f"config.role.{ROLE}", globals(), locals(), ["*"])
```

---

## 三种环境详细说明

### 1. `conf.web.development.enterprise` — Web SaaS 前端服务

| 项目 | 说明 |
|------|------|
| **角色配置文件** | `bkmonitor/config/role/web.py` |
| **环境配置文件** | `bkmonitor/config/dev.py` |
| **ROOT_URLCONF** | `urls` → `bkmonitor/urls.py` |
| **用途** | 面向用户的 Web 前端页面和 REST API（SaaS 层） |

#### 主要代码目录

| 目录 | 说明 |
|------|------|
| `packages/monitor_web/` | 监控 Web 模块（前端页面、仪表盘、Grafana 集成等） |
| `packages/monitor_api/` | 监控 API 模块（SaaS 层 REST API） |
| `packages/fta_web/` | 故障自愈 Web 模块 |
| `packages/apm_web/` | APM（应用性能监控）Web 模块 |
| `packages/weixin/` | 微信端适配模块 |
| `packages/monitor_adapter/` | 监控适配器模块 |

#### INSTALLED_APPS

```
django_celery_beat, django_celery_results, django_elasticsearch_dsl,
rest_framework, django_filters, drf_yasg, bkmonitor, healthz, metadata,
bkm_space, calendars, monitor, monitor_api, monitor_web, apm_web,
apm_ebpf, apm, weixin.core, weixin, core.drf_resource, bkm_ipchooser,
version_log, iam.contrib.iam_migration, fta_web, audit, apigw_manager,
bk_notice_sdk, ai_whale
```

#### 关键特性

- **中间件**：包含 CORS、CSRF、Session、用户认证、微信认证、API Token 认证、APIGW JWT、XSS 检查、时区处理、版本日志等完整中间件链
- **模板引擎**：Mako + Django 双模板引擎
- **Session**：支持 Redis 缓存 Session（当配置了 Redis 时）
- **认证后端**：ApiTokenAuthBackend、RioBackend、WeixinBackend、UserBackend
- **REST Framework**：使用 `MonitorJSONRenderer`、`BusinessViewPermission` 权限类
- **Grafana 集成**：内置 Grafana 配置和权限管理

---

### 2. `conf.worker.development.enterprise` — 后台 Worker 服务

| 项目 | 说明 |
|------|------|
| **角色配置文件** | `bkmonitor/config/role/worker.py` |
| **环境配置文件** | `bkmonitor/config/dev.py` |
| **ROOT_URLCONF** | `alarm_backends.urls` → `bkmonitor/alarm_backends/urls.py` |
| **用途** | 后台告警处理引擎、异步任务、定时任务调度 |

#### 主要代码目录

| 目录 | 说明 |
|------|------|
| `alarm_backends/` | 告警后端引擎（数据接入 access、检测 detect、触发 trigger、事件处理 event、收敛 converge、自愈动作 fta_action） |
| `metadata/` | 元数据管理（数据源、结果表、存储集群配置等） |
| `packages/apm/` | APM 后台任务（拓扑发现、数据源发现、配置下发等） |
| `packages/apm_ebpf/` | eBPF 相关后台任务（DeepFlow 集群发现等） |

#### INSTALLED_APPS

```
django_celery_beat, django_celery_results, django_elasticsearch_dsl,
django_jinja, bkmonitor, bkm_space, calendars, metadata,
alarm_backends, apm, apm_ebpf, core.drf_resource, ai_whale
```

#### 关键特性

- **Supervisor 进程管理**：通过 Supervisor 管理后台进程
- **定时任务（Crontab）**：配置了大量定时任务，分为三类队列：
  - `DEFAULT_CRONTAB`：策略缓存更新、BCS 资源同步、APM 任务、Metadata 管理等
  - `ACTION_TASK_CRONTAB`：告警异常检测、屏蔽策略检查、排班计划、ES 索引轮转等
  - `LONG_TASK_CRONTAB`：耗时任务（空间信息刷新、InfluxDB 路由刷新、BkBase 数据同步等）
- **Redis 多 DB 分配**：
  - DB 7：日志相关数据（不重要，可清理）
  - DB 8：配置缓存（CMDB 数据、策略、屏蔽等）
  - DB 9：服务间队列 + Celery Broker（重要，不可清理）
  - DB 10：Service 自身数据（重要，不可清理）
- **基础设施连接**：Consul、Transfer、InfluxDB、RabbitMQ、Kafka 等
- **跳过权限中心检查**：`SKIP_IAM_PERMISSION_CHECK = True`

---

### 3. `conf.api.development.enterprise` — 内部 Kernel API 服务

| 项目 | 说明 |
|------|------|
| **角色配置文件** | `bkmonitor/config/role/api.py` |
| **环境配置文件** | `bkmonitor/config/dev.py` |
| **ROOT_URLCONF** | `kernel_api.urls` → `bkmonitor/kernel_api/urls.py` |
| **用途** | 内部 API 网关服务，供其他平台和服务调用 |

#### 主要代码目录

| 目录 | 说明 |
|------|------|
| `kernel_api/` | Kernel API 核心模块（路由、视图、认证、适配器） |
| `packages/monitor_web/` | 复用 Web 模块能力 |
| `packages/monitor_api/` | 复用 API 模块能力 |
| `metadata/` | 复用元数据管理能力 |
| `packages/apm/` | 复用 APM 模块能力 |

#### INSTALLED_APPS

```
django_elasticsearch_dsl, rest_framework, django_filters, bkmonitor,
bkm_space, monitor, monitor_api, monitor_web, apm_web, apm_ebpf,
apm, fta_web, kernel_api, metadata, calendars, core.drf_resource,
django_celery_beat, django_celery_results, audit, apigw_manager, ai_whale
```

#### 关键特性

- **混合继承**：同时 import 了 `config.role.web` 和 `config.role.worker` 的配置，合并了两者的能力
  ```python
  from config.role.web import *
  from config.role.worker import *
  ```
- **缓存复用**：复用 worker 的 CACHES 配置（`CACHES = worker.CACHES`）
- **独立认证中间件**：使用 `kernel_api.middlewares.authentication.AuthenticationMiddleware`
- **REST Framework**：
  - 渲染器：`kernel_api.adapters.ApiRenderer`
  - 异常处理：`kernel_api.exceptions.api_exception_handler`
  - 认证：`kernel_api.middlewares.authentication.KernelSessionAuthentication`
  - 权限类：空（无默认权限限制）
- **认证后端**：`AppWhiteListModelBackend`（应用白名单认证）+ `UserBackend`
- **安全配置**：
  - 跳过 IAM 权限中心检查（`SKIP_IAM_PERMISSION_CHECK = True`）
  - 禁用 SSL 重定向（`SECURE_SSL_REDIRECT = False`）
  - Session 过期时间仅 60 秒（API 请求不携带 session cookie）

---

## 总结对比

| 维度 | **web** | **worker** | **api** |
|------|---------|------------|---------|
| **定位** | 用户前端 SaaS | 后台任务引擎 | 内部 API 网关 |
| **面向对象** | 用户浏览器 | 内部调度系统 | 其他平台/服务 |
| **角色配置** | `config/role/web.py` | `config/role/worker.py` | `config/role/api.py` |
| **URL 路由** | `urls.py` | `alarm_backends/urls.py` | `kernel_api/urls.py` |
| **主要代码** | `monitor_web/`, `fta_web/`, `apm_web/` | `alarm_backends/`, `metadata/` | `kernel_api/`（混合 web + worker） |
| **认证方式** | 用户登录 + Token + 微信 + APIGW JWT | 无用户认证 | 应用白名单 |
| **权限检查** | IAM 权限中心 | 跳过 IAM | 跳过 IAM |
| **Session 时长** | 浏览器关闭过期 | 无 | 60 秒 |
| **Celery 任务** | ✅ | ✅（核心） | ✅ |
| **定时任务** | ❌ | ✅（大量 Crontab） | ❌ |
