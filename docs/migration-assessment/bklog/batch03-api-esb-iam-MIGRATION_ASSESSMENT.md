# bklog API/ESB/IAM 迁移价值评估报告（批次 3）

> 评估范围：`esb/` + `api/` + `iam/`（45 个文件，约 7,044 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `api/base.py` | 1,008 | **20/25** | ✅ 推荐迁移 |
| `iam/handlers/drf.py` | 268 | **19/25** | ✅ 推荐迁移 |
| `iam/handlers/permission.py` | 443 | **18/25** | ✅ 推荐迁移 |
| `iam/handlers/actions.py` | 290 | 17/25 | ⚠️ 有条件迁移 |
| `iam/utils.py` | 78 | 16/25 | ⚠️ 有条件迁移 |
| `iam/handlers/shortcuts.py` | 33 | 16/25 | ⚠️ 有条件迁移 |
| `api/exception.py` | 40 | 15/25 | ⚠️ 有条件迁移 |
| `api/constants.py` | 24 | 15/25 | ⚠️ 有条件迁移 |
| `iam/views/meta.py` | 199 | 14/25 | ❌ 不迁移 |
| `api/modules/utils.py` | 405 | 13/25 | ❌ 不迁移 |
| `iam/exceptions.py` | 64 | 13/25 | ❌ 不迁移 |
| `iam/handlers/compatible.py` | 139 | 12/25 | ❌ 不迁移 |
| `esb/views.py` | 211 | 10/25 | ❌ 不迁移 |
| `esb/exceptions.py` | 49 | 10/25 | ❌ 不迁移 |
| `esb/urls.py` | 37 | 8/25 | ❌ 不迁移 |
| `iam/urls.py` | 51 | 8/25 | ❌ 不迁移 |
| `api/management/commands/sync_apigw.py` | 50 | 8/25 | ❌ 不迁移 |
| `api/modules/*.py`（26 个文件） | ~3,510 | ~11/25 | ❌ 不迁移 |

---

## 二、迁移目标详细分析（≥18 分）

### 1. DataAPI HTTP 客户端封装框架（20/25）

**源文件：** `api/base.py`（1,008 行）

这是经过长期生产验证的 HTTP API 客户端封装框架，核心设计：

```python
class DataAPI:           # 声明式 API 定义：一行代码声明一个 HTTP 接口
class DataDRFAPISet:     # RESTful 资源操作声明 → DataAPI 实例
class DataApiRetryClass: # 可配置重试策略（异常列表+结果检查）
class BaseApi:           # 代理模式，版本化 API 访问
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | HTTP API 客户端封装框架，适用于任何需要封装外部 API 的项目 |
| **复用价值** | 5/5 | 任何后端项目只要存在多处 HTTP API 调用均可使用 |
| **独立性** | 3/5 | 深度依赖 Django（settings、cache、translation）和 OpenTelemetry |
| **接口稳定性** | 4/5 | 成熟的类层次，经长期使用验证 |
| **代码质量** | 4/5 | 功能覆盖全面：钩子、重试、缓存、批量并发、多租户 |

**核心设计亮点：**

| 模式 | 说明 |
|------|------|
| **声明式 API 定义** | `DataAPI(method, url, module, before_request, ...)` 一行声明 |
| **生命周期钩子** | `before_request` / `after_request` 参数预处理和响应后处理 |
| **可配置重试** | `DataApiRetryClass` 自定义异常列表和结果检查函数 |
| **批量并发** | `batch_request`（按 key 切片）和 `bulk_request`（分页并发） |
| **DRF API Set** | `BASE_ACTIONS` + `custom_config` 扩展 RESTful 资源操作 |
| **代理模式** | `BaseApi.__getattribute__` 通过 ProxyDataAPI 实现版本化 API 代理 |

**迁移范围**：核心类约 600 行。需将 `settings.*`、`cache`、`get_request_*` 改为 Protocol 注入。

### 2. DRF + IAM 权限集成层（19/25）

**源文件：** `iam/handlers/drf.py`（268 行）

```python
class IAMPermission:               # 基础权限类
class BusinessActionPermission:    # 业务关联权限
class InstanceActionPermission:    # 实例级权限
class BatchIAMPermission:          # 批量实例鉴权
def insert_permission_field:       # 装饰器：自动注入 permission 字段
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | DRF + IAM 集成模式适用于所有蓝鲸 SaaS 项目 |
| **复用价值** | 4/5 | 权限类体系和 `insert_permission_field` 装饰器是通用模式 |
| **独立性** | 3/5 | 依赖 DRF 和 IAM SDK |
| **接口稳定性** | 4/5 | 清晰的类继承体系 |
| **代码质量** | 4/5 | `insert_permission_field` 装饰器设计精巧 |

### 3. IAM Permission 核心封装（18/25）

**源文件：** `iam/handlers/permission.py`（443 行）

```python
class Permission:
    def is_allowed(self, action, resources): ...        # 单动作鉴权
    def batch_is_allowed(self, action, resources): ...   # 批量鉴权
    def get_apply_data(self, action, resources): ...     # 无权限数据生成
    def filter_space_list_by_action(self, action, ...): ... # 空间列表过滤
    def grant_creator_action(self, action, instance): ...   # 创建者授权
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | IAM 权限校验的核心封装类 |
| **复用价值** | 4/5 | 任何 IAM 项目都需要类似的 Permission 封装 |
| **独立性** | 2/5 | 强耦合 IAM SDK 内部方法 |
| **接口稳定性** | 4/5 | Permission 类接口设计成熟 |
| **代码质量** | 4/5 | 功能完整 |

**建议**：与 `drf.py` 一起迁移，作为 IAM 集成模块的两个文件。

---

## 三、有条件迁移目标（15-17 分）

| 文件 | 总分 | 可提取价值 |
|------|------|-----------|
| `iam/handlers/actions.py` | 17 | ActionMeta 基类 + fetch_related_actions 递归依赖获取 |
| `iam/utils.py` | 16 | gen_perms_apply_data 无权限交互协议数据生成 |
| `iam/handlers/shortcuts.py` | 16 | assert_allowed 快捷函数（仅 33 行） |
| `api/exception.py` | 15 | DataAPIException 携带 api_obj 和 response |
| `api/constants.py` | 15 | 缓存时长常量（过于简单，建议内联） |

---

## 四、不迁移模块说明

| 模块 | 不迁移原因 |
|------|-----------|
| `esb/views.py` | ESB 转发代理视图，强依赖 settings 和内部 API |
| `api/modules/*.py`（26 个文件） | 全部为外部 API 声明文件（CC、Monitor、Transfer 等），设计模式已在 base.py 中体现 |
| `iam/handlers/compatible.py` | IAM V1/V2 兼容模式，仅适用于特定迁移过渡场景 |
| `api/modules/utils.py` | 强耦合 settings、Space 模型、EsquerySearchPermissions |

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 声明式 API 定义 | `api/base.py` | HTTP API 客户端封装 |
| 生命周期钩子（before/after） | `api/base.py` | 请求预处理和响应后处理 |
| 可配置重试策略 | `api/base.py` | API 调用容错 |
| 批量并发请求（两种模式） | `api/base.py` | 大批量 API 数据获取 |
| DRF API Set（RESTful 声明） | `api/base.py` | RESTful 资源操作封装 |
| 分层权限类体系 | `iam/handlers/drf.py` | DRF + IAM 集成 |
| insert_permission_field 装饰器 | `iam/handlers/drf.py` | API 返回中注入权限信息 |
| ESB 转发代理 | `esb/views.py` | API 网关/代理场景 |
| 资源元数据抽象（ABC+注册表） | `iam/handlers/resources.py` | 资源类型定义与实例创建分离 |
