# bklog 公共层 + 顶层迁移价值评估报告（批次 2）

> 评估范围：`log_commons/` + `feature_toggle/` + `middleware/` + 顶层文件（约 5,100 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `feature_toggle/plugins/base.py` | 188 | **19/25** | ✅ 推荐迁移 |
| `apps/exceptions.py` | 144 | **19/25** | ✅ 推荐迁移 |
| `apps/generic.py` | 378 | **20/25** | ✅ 推荐迁移 |
| `middleware/custom_locale.py` | 68 | **21/25** | ✅ 强烈推荐迁移 |
| `middleware/pyinstrument.py` | 86 | **21/25** | ✅ 强烈推荐迁移 |
| `feature_toggle/handlers/toggle.py` | 258 | **18/25** | ✅ 推荐迁移 |
| `feature_toggle/constants.py` | 24 | **21/25** | ✅ 强烈推荐（纯常量） |
| `feature_toggle/plugins/constants.py` | 73 | **21/25** | ✅ 强烈推荐（纯常量） |
| `log_commons/adapt_ipv6.py` | 167 | 16/25 | ⚠️ 有条件迁移 |
| `log_commons/constants.py` | 24 | 17/25 | ⚠️ 有条件迁移 |
| `log_commons/exceptions.py` | 81 | 15/25 | ⚠️ 有条件迁移 |
| `log_commons/job.py` | 74 | 17/25 | ⚠️ 有条件迁移 |
| `log_commons/token.py` | 89 | 17/25 | ⚠️ 有条件迁移 |
| `middleware/apigw.py` | 124 | 17/25 | ⚠️ 有条件迁移 |
| `middleware/api_token_middleware.py` | 75 | 16/25 | ⚠️ 有条件迁移 |
| `middleware/user_middleware.py` | 171 | 16/25 | ⚠️ 有条件迁移 |
| `apps/constants.py` | 679 | 15/25 | ⚠️ 有条件迁移 |
| `apps/middlewares.py` | 232 | 16/25 | ⚠️ 有条件迁移 |
| `log_commons/cc.py` | 36 | 13/25 | ❌ 不迁移 |
| `log_commons/handlers/external_permission.py` | 210 | 13/25 | ❌ 不迁移 |
| `log_commons/management/commands/create_unify_query_api_token.py` | 116 | 12/25 | ❌ 不迁移 |
| `log_commons/share.py` | 103 | 12/25 | ❌ 不迁移 |
| `log_commons/urls.py` | 42 | 10/25 | ❌ 不迁移 |
| `log_commons/views.py` | 415 | 10/25 | ❌ 不迁移 |
| `apps/decorators.py` | 47 | 12/25 | ❌ 不迁移 |

---

## 二、迁移目标详细分析（≥18 分）

### 1. 自定义国际化中间件（21/25）

**源文件：** `middleware/custom_locale.py`（68 行）

基于 `HTTP_X_BK_LANGUAGE_CODE` 请求头获取语言偏好，兼容 Django 原生 i18n 模式（URL 前缀、Accept-Language），支持 404 时自动语言前缀重定向。

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 适用于所有需要多语言支持的 Django 应用 |
| **复用价值** | 4/5 | 替代 Django 默认 LocaleMiddleware |
| **独立性** | 4/5 | 仅依赖 Django 核心模块 |
| **接口稳定性** | 5/5 | 标准 Django 中间件接口 |
| **代码质量** | 4/5 | 代码简洁，逻辑清晰 |

### 2. 性能分析中间件（21/25）

**源文件：** `middleware/pyinstrument.py`（86 行）

通过 URL 参数 `?profile` 触发性能分析，支持配置回调函数控制是否启用，支持将分析结果保存到文件目录，超级用户可直接在浏览器查看 HTML 报告。

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 适用于所有 Django 开发/测试环境 |
| **复用价值** | 4/5 | 开发阶段性能调优利器 |
| **独立性** | 4/5 | 仅依赖 pyinstrument 库和 Django |
| **接口稳定性** | 5/5 | 标准 Django 中间件接口 |
| **代码质量** | 4/5 | 功能完整，支持文件输出和在线查看 |

### 3. DRF ViewSet 标准封装（20/25）

**源文件：** `apps/generic.py`（378 行）

```python
class FlowMixin:           # 统一 API 响应格式 {result, data, code, message}
class ValidationMixin:     # 参数验证封装
class IAMPermissionMixin:  # 权限中心集成
class APIViewSet:          # 组合以上 Mixin 的标准 ViewSet
class ModelViewSet:        # 自动序列化器生成的 Model ViewSet
def custom_exception_handler:  # 全局异常处理
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | DRF ViewSet 封装模式，适用于所有 Django REST Framework 项目 |
| **复用价值** | 5/5 | 标准化 API 响应格式、权限校验、参数验证 |
| **独立性** | 3/5 | 依赖 DRF、IAM 模块 |
| **接口稳定性** | 4/5 | Mixin 模式设计，接口稳定 |
| **代码质量** | 4/5 | 良好的 Mixin 分层设计 |

### 4. 异常层次体系（19/25）

**源文件：** `apps/exceptions.py`（144 行）

```python
class ErrorCode:       # 模块级错误码：BKLOG_PLAT_CODE + MODULE_CODE + ERROR_CODE
class BaseException:   # 支持 code、message、data、errors
class ApiError:        # → ApiResultError / ApiRequestError
class ValidationError: # 业务异常
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 3/5 | 异常层次结构设计模式适用于所有蓝鲸应用 |
| **复用价值** | 3/5 | 错误码体系和异常基类可复用 |
| **独立性** | 4/5 | 仅依赖 Django 核心 |
| **接口稳定性** | 5/5 | 异常类接口极其稳定 |
| **代码质量** | 4/5 | 清晰的错误码分层设计 |

### 5. 特性开关插件架构（19/25）

**源文件：** `feature_toggle/plugins/base.py`（188 行）

```python
class FeatureToggleBase(ABC):
    def set_status(self, toggle, status, feature_info, is_display): ...
    def action(self, toggle, feature_info): ...

@register
class DummyFeatureToggle(FeatureToggleBase): ...
```

ABC 抽象基类 + `@register` 装饰器实现插件自动注册 + `FEATURE_TOGGLE` 全局注册表。

### 6. 特性开关核心逻辑（18/25）

**源文件：** `feature_toggle/handlers/toggle.py`（258 行）

三级配置优先级（settings → DB → plugins），支持业务白名单/黑名单控制，支持 debug 模式下的环境限制。

---

## 三、有条件迁移目标（15-17 分）

| 文件 | 总分 | 可提取价值 |
|------|------|-----------|
| `middleware/apigw.py` | 17 | 内外网网关公钥切换、自定义 JWT 解析 |
| `log_commons/token.py` | 17 | Token 工厂模式（BaseTokenHandler ABC + TokenHandlerFactory） |
| `log_commons/job.py` | 17 | JOB 平台脚本执行封装（IPv6 适配） |
| `log_commons/constants.py` | 17 | Token 申请频率限制常量 |
| `log_commons/adapt_ipv6.py` | 16 | IPv4/IPv6 双栈主机适配（DHCP 场景） |
| `middleware/api_token_middleware.py` | 16 | API Token 认证中间件（存在代码质量问题） |
| `middleware/user_middleware.py` | 16 | 用户时区处理中间件 + Prometheus 监控 |
| `apps/middlewares.py` | 16 | Request 上下文传递机制（AccessSignal + RequestProvider） |
| `log_commons/exceptions.py` | 15 | 日志平台特定异常类 |
| `apps/constants.py` | 15 | 679 行业务枚举，ViewSetAction dataclass 模式可参考 |

---

## 四、不迁移模块说明

| 文件 | 总分 | 不迁移原因 |
|------|------|-----------|
| `log_commons/cc.py` | 13 | 强依赖 CCApi 和 bkm_space |
| `log_commons/handlers/external_permission.py` | 13 | 深度耦合 IAM 权限系统 |
| `log_commons/management/commands/...` | 12 | Django management command，强依赖 model |
| `log_commons/share.py` | 12 | 分享 Token 逻辑强依赖 model 和 IAM |
| `log_commons/urls.py` | 10 | 纯 URL 路由配置 |
| `log_commons/views.py` | 10 | 大量业务视图，耦合度极高 |
| `apps/decorators.py` | 12 | 仅审计日志记录装饰器，强依赖 model |

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| ViewSet Mixin 分层架构 | `apps/generic.py` | DRF API 标准化封装 |
| 异常层次体系（三级错误码） | `apps/exceptions.py` | 统一异常处理框架 |
| 特性开关插件架构（ABC+注册表） | `feature_toggle/plugins/base.py` | 功能开关/灰度发布 |
| 三级配置优先级（settings→DB→plugins） | `feature_toggle/handlers/toggle.py` | 多级配置读取 |
| Request 上下文传递（AccessSignal） | `apps/middlewares.py` | 线程级 request 获取 |
| Token 工厂模式 | `log_commons/token.py` | Token 类型管理 |
| IPv6 双栈适配 | `log_commons/adapt_ipv6.py` | DHCP 场景 IP/HostID 填充 |
| APIGW 内外网切换 | `middleware/apigw.py` | 公钥提供者动态切换 |
