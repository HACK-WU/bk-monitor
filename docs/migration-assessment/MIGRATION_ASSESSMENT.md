# alarm_backends/core 迁移价值评估报告

> 评估范围：`bkmonitor/alarm_backends/core/` 全部 13 个子模块
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）
> 迁移目标：PythonCodeHub — 可复用、低耦合、易参考的通用 Python 代码

---

## 一、总览

| 模块 | 总分 | 结论 |
|------|------|------|
| `circuit_breaking/` | **18/25** | ✅ 部分迁移 — Matcher 层 |
| `control/` | **16/25** | ✅ 部分迁移 — DoubleCheckStrategy 注册表 |
| `storage/` | **16/25** | ✅ 部分迁移 — redis.py 核心模式 |
| `context/` | 11/25 | ❌ 业务耦合过深 |
| `cache/` | 10/25 | ❌ 基类过薄，模式分散 |
| `api_cache/` | 8/25 | ❌ 绑定 gevent/supervisor |
| `lock/` | 12/25 | ❌ 开源替代已成熟 |
| `handlers/` | 15/25 | ❌ 过于简单 |
| `processor/` | 10/25 | ❌ 过于简单 |
| `alert/` | — | ❌ 告警业务逻辑 |
| `detect_result/` | — | ❌ 检测结果业务逻辑 |
| `db/` | 0 | ❌ 空文件 |

---

## 二、迁移目标 1：通用条件匹配引擎

**源文件：** `alarm_backends/core/circuit_breaking/matcher.py`

### 2.1 核心设计

该模块实现了一个 **基于可配置规则集的通用条件匹配引擎**，采用 Manager + Matcher 分层架构：

- **Matcher 层**：通用的条件匹配器，接收 JSON 规则列表，判断输入维度字典是否命中规则集。与业务完全解耦，只关心 "字典是否命中规则"。
- **Manager 层**：面向业务的熔断管理器，子类按模块覆写 `clean_cb_dimension()` 适配不同业务维度字段。

**Matcher 核心能力：**

```
输入：维度字典 dict + 规则配置 list
输出：是否命中 bool

支持 10 种匹配方法：
  eq / neq / lt / gt / lte / gte / reg / include / exclude / range

支持逻辑连接符：
  AND（全部命中） / OR（任一命中）

支持嵌套规则：
  条件组可递归嵌套，形成树状匹配逻辑
```

**核心接口：**

```python
# 工厂函数
matcher = gen_circuit_breaking_matcher(config_rules)

# 匹配判定
result = matcher.is_match(dimensions: dict) -> bool

# 内部结构
CircuitBreakingMatcher(rules: list)
  ├── _parse_rules(rules)        # 解析 JSON 规则为内部结构
  ├── _build_condition(rule)      # 构建单条匹配条件
  └── is_match(dimensions: dict)  # 执行匹配
```

### 2.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 3/5 | Matcher 层本身是通用的规则匹配引擎；Manager 层硬编码了监控领域维度字段，通用性受限 |
| **复用价值** | 4/5 | "基于可配置规则集对维度字典做匹配判定"是微服务限流、API 熔断、流量管控等场景的通用需求 |
| **独立性** | 3/5 | Matcher 层可独立表达，但依赖了 `load_condition_instance` 和 Django ORM 常量 |
| **接口稳定性** | 4/5 | `CircuitBreakingMatcher(config_rules).is_match(dimensions)` 接口清晰、语义明确 |
| **代码质量** | 4/5 | 类型注解完整，文档字符串详尽，职责划分清晰，异常处理到位 |

**总分：18/25**

### 2.3 业务耦合清单

| 耦合点 | 位置 | 处理方式 |
|--------|------|----------|
| `load_condition_instance` | matcher.py L10 | 替换为自包含的匹配逻辑，或将该函数一并提取 |
| `django.db.models.sql.where.AND/OR` | matcher.py L9 | 替换为纯字符串常量 `"AND"` / `"OR"` |
| `CircuitBreakingCacheManager` | manager.py L14 | 不迁移 Manager 层 |
| `strategy_id`, `bk_biz_id` 等字段 | manager.py L56-83 | 不迁移 Manager 层 |
| 具体子类（Access/Alert/Action） | manager.py L127-193 | 不迁移 Manager 层 |

### 2.4 迁移范围建议

**只迁移 Matcher 层**，Manager 层作为业务实现不迁移。

迁移产物：
- `circuit_breaking_matcher.py` — 核心匹配引擎
- `condition.py` — 条件实例（从 `load_condition_instance` 提取）
- `tests/test_matcher.py` — 匹配逻辑测试

### 2.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 微服务限流 | 按请求维度（IP、用户、接口）匹配限流规则 |
| API 熔断 | 按响应指标匹配熔断条件 |
| 灰度发布 | 按用户标签、地域等维度匹配灰度规则 |
| 配置动态下发 | 按客户端特征匹配配置策略 |
| 流量管控 | 按流量特征匹配管控规则 |
| 权限控制 | 按用户属性匹配权限策略 |

### 2.6 迁移完成标准

- [ ] Matcher 完全脱离 Django 依赖
- [ ] 条件实例自包含（不依赖外部工厂函数）
- [ ] 公开接口均有 type hints
- [ ] 至少覆盖 10 种匹配方法的单元测试
- [ ] AND/OR 逻辑组合的嵌套测试
- [ ] 边界条件：空规则、空字典、非法操作符
- [ ] 最小可运行示例可复制使用

---

## 三、迁移目标 2：策略匹配注册表框架

**源文件：** `alarm_backends/core/control/mixins/double_check.py`

### 3.1 核心设计

该模块实现了一个 **Protocol + 注册表 + 条件匹配** 的可扩展策略框架：

- **Protocol 定义接口**：使用 `typing.Protocol` + `@dataclass` 定义策略的结构化接口
- **全局注册表**：通过装饰器注册策略实现，运行时按条件动态选择匹配的策略
- **插件式扩展**：新增策略只需定义一个 `@dataclass` 类并注册，无需修改框架代码

**核心接口：**

```python
# Protocol 定义
class DoubleCheckStrategy(Protocol):
    strategy_id: int
    item_id: int
    level: int

    def check_hit(self, anomaly_record) -> bool:
        """判断是否命中该策略"""
        ...

    def double_check(self, anomaly_id, dimensions, strategy_id, item_id, level) -> bool:
        """执行二次确认检查"""
        ...

# 注册机制
@register_double_check_strategy
@dataclass
class MyCustomStrategy:
    strategy_id: int = 123
    item_id: int = 1
    level: int = 1

    def check_hit(self, anomaly_record) -> bool:
        return anomaly_record.strategy_id == self.strategy_id

    def double_check(self, anomaly_id, dimensions, strategy_id, item_id, level) -> bool:
        # 自定义二次确认逻辑
        return True

# 运行时选择
strategy = pick_double_check_strategy(anomaly_record)
if strategy and strategy.double_check(...):
    # 命中策略，执行确认
    ...
```

### 3.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 3/5 | Protocol 注册表模式通用，但 `check_hit` / `double_check` 方法名是领域专用的 |
| **复用价值** | 3/5 | "策略匹配 + 注册发现"是插件系统、规则引擎等场景的通用需求 |
| **独立性** | 2/5 | 依赖 `Item` 类和业务常量，剥离后需重新定义上下文接口 |
| **接口稳定性** | 4/5 | Protocol 定义非常清晰，`@dataclass` 结构规范 |
| **代码质量** | 4/5 | Protocol 使用规范，注册表实现简洁，类型注解完整 |

**总分：16/25**

### 3.3 业务耦合清单

| 耦合点 | 位置 | 处理方式 |
|--------|------|----------|
| `Item` 类 | double_check.py | 泛化为通用的 `AnomalyRecord` Protocol |
| 业务常量（`CONST_MINUTES` 等） | double_check.py | 参数化或移除 |
| `AnomalyIDParser` | record_parser.py | 可一并提取为通用复合 ID 解析器 |
| `Checkpoint`（Redis 进度跟踪） | checkpoint.py | 可作为独立子能力一并迁移 |

### 3.4 迁移范围建议

**核心迁移：** `DoubleCheckStrategy` Protocol + 注册表机制

**可选扩展：**
- `Checkpoint` — 基于 KV 存储的消费进度跟踪器（支持自动回退）
- `AnomalyIDParser` — 通用复合 ID 解析器（`a.b.c.d.e` 格式）

迁移产物：
- `strategy_registry.py` — 核心 Protocol + 注册表 + 策略选择
- `checkpoint.py` — 进度跟踪器（需抽象后端接口）
- `record_parser.py` — 复合 ID 解析器
- `tests/test_registry.py` — 注册表机制测试
- `tests/test_checkpoint.py` — 进度跟踪测试

### 3.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 插件系统 | 运行时按条件加载和匹配插件实现 |
| 规则引擎 | 多策略竞争，按条件选择最优策略执行 |
| A/B 测试分流 | 按用户特征匹配实验分组策略 |
| 消费进度管理 | 消息队列消费断点续传、自动回退 |
| 任务调度 | 按条件匹配任务执行策略 |
| 配置路由 | 按请求特征路由到不同处理逻辑 |

### 3.6 迁移完成标准

- [ ] Protocol 定义脱离 `Item` 类依赖
- [ ] 注册表支持泛型类型参数
- [ ] Checkpoint 后端可插拔（Redis / 本地文件 / 内存）
- [ ] 公开接口均有 type hints
- [ ] 注册表：注册/发现/匹配的单元测试
- [ ] Checkpoint：首次拉取、正常推进、长时间未拉取回退的测试
- [ ] 边界条件：空注册表、无匹配策略、并发注册
- [ ] 最小可运行示例可复制使用

---

## 四、迁移目标 3：Redis 客户端工厂与重试代理模式

**源文件：** `alarm_backends/core/storage/redis.py`

### 4.1 核心设计

该模块包含三个可独立提取的设计模式：

#### 模式 A：`__getattr__` 重试代理

```python
class BaseRedisCache:
    def __getattr__(self, name):
        """拦截所有 Redis 命令调用，自动包装重试逻辑"""
        def wrapper(*args, **kwargs):
            for attempt in range(self.max_retries):
                try:
                    method = getattr(self._client, name)
                    return method(*args, **kwargs)
                except (ConnectionError, TimeoutError):
                    self._refresh_connection()
            raise RedisConnectionError(...)
        return wrapper
```

**核心价值：** 通用的"连接型客户端自动重试"范式，可泛化到任何需要重试的客户端（数据库、HTTP、gRPC 等）。

#### 模式 B：工厂路由

```python
class Cache:
    def __new__(cls, backend="default"):
        """根据 backend 名称动态选择后端实现"""
        if backend == "default":
            return RedisCache.instance()
        elif backend == "sentinel":
            return SentinelRedisCache.instance()
        elif backend == "instance":
            return InstanceCache.instance()
        else:
            raise ValueError(f"Unknown backend: {backend}")
```

**核心价值：** 按标识符动态选择后端实现，调用方无需关心具体实现类。

#### 模式 C：Sentinel 连接管理

```python
class SentinelRedisCache(BaseRedisCache):
    def __init__(self, sentinel_hosts, master_name, **kwargs):
        """多 Sentinel 节点发现 + master/slave 分离"""
        self._sentinel = Sentinel(
            [(h, p) for h, p in sentinel_hosts],
            socket_timeout=kwargs.get("socket_timeout", 1),
        )
        self._master = self._sentinel.master_for(master_name, ...)
        self._slave = self._sentinel.slave_for(master_name, ...)
```

**核心价值：** 多节点 Sentinel 发现、master/slave 分离、自动故障转移。

### 4.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 工厂+重试代理+Sentinel 管理是广泛适用的基础设施模式 |
| **复用价值** | 4/5 | 任何使用 Redis Sentinel 的 Python 项目都需要类似的封装 |
| **独立性** | 2/5 | `delay()` 方法和 `InstanceCache` 依赖深度耦合业务 |
| **接口稳定性** | 3/5 | `Cache(backend_name)` 接口语义清晰，但需去掉 `delay()` 等业务方法 |
| **代码质量** | 3/5 | 设计模式质量较高，但存在 `six` 残留和硬编码配置 |

**总分：16/25**

### 4.3 业务耦合清单

| 耦合点 | 位置 | 处理方式 |
|--------|------|----------|
| `settings.REDIS_*_CONF` | 全局配置 | 改为构造函数参数注入 |
| `delay()` 方法 | BaseRedisCache | 删除，属于 `DelayQueueManager` 业务逻辑 |
| `InstanceCache` | __new__ | 移除，或泛化为可选的单例管理器 |
| `CACHE_BACKEND_CONF_MAP` | 全局常量 | 改为配置字典参数 |
| `bkmonitor.utils.cache` | 导入 | 移除依赖 |
| `six` 库 | 兼容层 | 移除，仅支持 Python 3.8+ |

### 4.4 迁移范围建议

**迁移三个独立模式，而非整个文件：**

迁移产物：
- `retry_proxy.py` — 通用 `__getattr__` 重试代理（可泛化为装饰器或 Mixin）
- `factory_router.py` — 工厂路由模式（按标识符选择后端）
- `sentinel_manager.py` — Redis Sentinel 连接管理器
- `tests/test_retry_proxy.py` — 重试逻辑测试
- `tests/test_factory_router.py` — 工厂路由测试
- `tests/test_sentinel_manager.py` — Sentinel 连接测试

### 4.5 泛化方向

重试代理可泛化为通用的客户端包装器：

```python
class RetryProxy:
    """通用重试代理，适用于任何连接型客户端"""
    def __init__(self, client, max_retries=3, retry_on=(ConnectionError,)):
        self._client = client
        self._max_retries = max_retries
        self._retry_on = retry_on

    def __getattr__(self, name):
        def wrapper(*args, **kwargs):
            for attempt in range(self._max_retries):
                try:
                    return getattr(self._client, name)(*args, **kwargs)
                except self._retry_on:
                    if attempt == self._max_retries - 1:
                        raise
                    self._on_retry(attempt)
        return wrapper

    def _on_retry(self, attempt):
        """子类可覆写：刷新连接、指数退避等"""
        pass
```

### 4.6 跨项目使用场景

| 场景 | 说明 |
|------|------|
| Redis Sentinel 封装 | 任何使用 Redis Sentinel 高可用的项目 |
| 数据库连接池 | 重试代理模式适用于 MySQL/PostgreSQL 客户端 |
| HTTP 客户端 | 重试代理适用于 requests/httpx 等 |
| gRPC 客户端 | 重试代理适用于 grpc 客户端 |
| 多后端路由 | 按配置选择不同的存储/消息队列后端 |
| 微服务客户端 | 按服务标识路由到不同的服务实例 |

### 4.7 迁移完成标准

- [ ] 重试代理完全泛化，不依赖 Redis
- [ ] 工厂路由支持任意后端类型注册
- [ ] Sentinel 管理器配置通过构造函数注入
- [ ] 无 `six` 残留，仅支持 Python 3.8+
- [ ] 公开接口均有 type hints
- [ ] 重试代理：成功、重试成功、重试耗尽失败的测试
- [ ] 工厂路由：已知后端、未知后端、动态注册的测试
- [ ] Sentinel：master/slave 读写分离、故障转移的测试
- [ ] 边界条件：空连接池、超时、并发获取连接
- [ ] 最小可运行示例可复制使用

---

## 五、迁移优先级与建议

### 优先级排序

| 优先级 | 目标 | 理由 |
|--------|------|------|
| **P0** | 通用条件匹配引擎 | 总分最高（18），解耦成本最低，跨场景复用价值最高 |
| **P1** | 策略匹配注册表框架 | Protocol 设计规范，插件式扩展模式通用性强 |
| **P2** | Redis 客户端工厂与重试代理 | 模式通用但需泛化，工作量相对较大 |

### 迁移批次建议

```
批次 1（独立可用）：通用条件匹配引擎
  └── matcher.py + condition.py + tests

批次 2（独立可用）：策略匹配注册表框架
  └── strategy_registry.py + checkpoint.py + record_parser.py + tests

批次 3（独立可用）：Redis 客户端工厂与重试代理
  └── retry_proxy.py + factory_router.py + sentinel_manager.py + tests
```

每批独立可运行、独立可测试，不依赖后续批次才能工作。

---

## 六、不迁移模块说明

| 模块 | 评估结论 | 设计参考价值 |
|------|----------|-------------|
| `context/` | 业务耦合过深（Django ORM/ES/CMDB），剥离后骨架无价值 | 上下文对象树 + 多通道路由渲染模式 |
| `cache/` | 基类仅一个 `refresh()` 抽象，有价值模式分散在子类中 | pipeline 批量写入、增量刷新、延迟队列 |
| `api_cache/` | 绑定 gevent/supervisor/CMDB，全局变量滥用 | HashRing 分片调度思路 |
| `lock/` | 开源替代已成熟（python-redis-lock），且存在 get+delete 非原子竞态 | token 防误删模式 |
| `handlers/` | 仅一个空抽象基类，两行代码即可替代 | 无 |
| `processor/` | 仅 30 行的 Redis 队列推送，过于简单 | 数据+信号的队列推送模式 |
| `db/` | 空文件，无代码 | 无 |
