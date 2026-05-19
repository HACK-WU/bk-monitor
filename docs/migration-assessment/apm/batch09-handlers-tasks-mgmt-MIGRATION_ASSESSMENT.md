# apm Handlers + Tasks + Management 迁移价值评估报告（批次 9）

> 评估范围：`apm/core/handlers/` 剩余文件 + `task/` + `management/commands/`（11 个文件，约 1,380 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 总分 | 结论 |
|------|------|------|
| `handlers/application_hepler.py` | **20/25** | ✅ 强烈推荐（可配置规则引擎） |
| `handlers/apm_cache_handler.py` | **19/25** | ✅ 推荐迁移（Redis 分布式锁） |
| `handlers/profile/query.py` | 16/25 | ⚠️ 有条件迁移（Fluent Builder） |
| `handlers/discover_handler.py` | 10/25 | ❌ 不迁移 |
| `handlers/serializers.py` | 10/25 | ❌ 不迁移 |
| `task/tasks.py` | 8/25 | ❌ 不迁移 |
| `management/commands/apm_daemon.py` | 8/25 | ❌ 不迁移 |
| `management/commands/create_builtin_profile_datasource.py` | 8/25 | ❌ 不迁移 |
| `management/commands/deploy_manual_config.py` | 13/25 | ❌ 不迁移 |
| `management/commands/refresh_apm_datalink.py` | 8/25 | ❌ 不迁移 |
| `management/commands/set_ebpf_config.py` | 8/25 | ❌ 不迁移 |

---

## 二、迁移目标 1：可配置规则引擎（20/25）

**源文件：** `apm/core/handlers/application_hepler.py`

### 核心设计

"抽象规则 + 工厂 + AND/OR 组合器"的经典可配置规则引擎：

```python
class SharedDatasourceRule(ABC):
    TYPE_KEY = ""
    def match(self, bk_biz_id, app_name) -> bool: ...

class SpaceTypeRule(SharedDatasourceRule): ...
class AppNamePrefixRule(SharedDatasourceRule): ...

class SharedDatasourceRuleFactory:
    BUILDER_REGISTER = {}  # 注册表

    @classmethod
    def create(cls, rule_type, params) -> SharedDatasourceRule: ...

# 组合逻辑：group 间 OR，group 内支持 AND/OR
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 3/5 | 规则引擎模式通用，但 `bk_biz_id`/`app_name` 作为匹配上下文 |
| **复用价值** | 5/5 | 配置驱动的规则匹配框架，适合特性开关灰度、多租户路由等 |
| **独立性** | 3/5 | 需泛化匹配上下文，剥离 SpaceType 依赖 |
| **接口稳定性** | 4/5 | `match()` 接口清晰 |
| **代码质量** | 5/5 | 注册表+工厂+AND/OR 组合，设计成熟 |

### 迁移范围

仅提取规则引擎框架部分（约 120 行）：`SharedDatasourceRule`、`SharedDatasourceRuleFactory` 及所有 Rule 子类。`ApplicationHelper` 的集群配置逻辑不迁移。

---

## 三、迁移目标 2：Redis 分布式锁（19/25）

**源文件：** `apm/core/handlers/apm_cache_handler.py`

### 核心设计

```python
class ApmLock:
    """基于 Redis SET NX EX 的分布式锁，token 防误释放"""
    def acquire(self): ...
    def release(self): ...

class ApmCacheHandler:
    @contextmanager
    def distributed_lock(self):
        """上下文管理器：自动 acquire/release"""
```

### 迁移范围

仅提取 `ApmLock` 类（约 35 行）和 `distributed_lock` 上下文管理器模式。需将 Redis 客户端获取改为注入式。

---

## 四、有条件迁移目标

### Fluent Builder 查询构建器（`handlers/profile/query.py`，16/25）

`ProfileQueryBuilder` 实现链式调用构建查询参数：
- `from_table()` → `with_*()` → `execute()`
- `deepcopy` 支持分支查询
- overwrite-warning 防御性设计（同名参数重复设置时 log warning）

---

## 五、不迁移模块说明

| 文件 | 不迁移原因 |
|------|-----------|
| `handlers/discover_handler.py` | 薄封装层，仅做 retention 过滤和时间格式转换 |
| `handlers/serializers.py` | 仅 16 行，附属 `ApplicationHelper` 的嵌套 DRF serializer |
| `task/tasks.py` | 纯 APM Celery 任务编排，深度耦合 APM 全链路服务 |
| 5 个 management commands | 纯运维工具或薄封装，无通用设计价值 |

---

## 六、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 可配置规则引擎（ABC+注册表+AND/OR 组合） | `application_hepler.py` | 特性开关、多租户路由 |
| Redis 分布式锁（token 防误释放 + context manager） | `apm_cache_handler.py` | 分布式互斥执行 |
| Fluent Builder（overwrite-warning 防御） | `profile/query.py` | 复杂查询参数构建 |
| 配置文件批量收集与下发 | `deploy_manual_config.py` | K8s 配置下发 |
