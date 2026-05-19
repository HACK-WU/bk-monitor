# apm Discover 基础模块迁移价值评估报告（批次 4）

> 评估范围：`apm/core/discover/base.py`（579 行）、`cached_mixin.py`（223 行）、`node.py`（403 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|--------|----------|--------|------------|----------|------|------|
| `cached_mixin.py` | 4 | 4 | 3 | 4 | 5 | **20** | ✅ 强烈推荐迁移 |
| `base.py` | 3 | 4 | 3 | 3 | 4 | 17 | ⚠️ 部分迁移（工具函数 + 注册表） |
| `node.py` | 1 | 1 | 1 | 2 | 3 | 8 | ❌ 不迁移 |

---

## 二、迁移目标：通用缓存管理 Mixin（20/25）

**源文件：** `apm/core/discover/cached_mixin.py`

### 核心设计

`CachedDiscoverMixin` 实现了"带 TTL 缓存 + 容量上限 + 增量更新"的完整缓存管理策略：

```python
class CachedDiscoverMixin:
    """缓存管理骨架，子类通过三个抽象方法定制行为"""

    def handle_cache_refresh_after_create(self, instances):
        """完整流水线：查询缓存 → 合并时间戳 → 清除过期/超量 → 增量写入"""

    # 双维度淘汰
    def _instance_clear_expired(self, ...):      # 按时间过期
    def _instance_clear_if_overflow(self, ...):  # 按数量裁剪

    # 模板方法（子类实现）
    def _get_cache_type(self) -> str: ...
    def to_cache_key(self, instance) -> str: ...
    def build_instance_data(self, model) -> BaseInstanceData: ...
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 缓存淘汰策略（过期+超量+增量刷新）是通用模式 |
| **复用价值** | 4/5 | 适用于指标聚合、日志索引、拓扑快照等场景 |
| **独立性** | 3/5 | 核心逻辑可独立，需抽象 `ApmCacheHandler` 为接口 |
| **接口稳定性** | 4/5 | 三个抽象方法契约清晰 |
| **代码质量** | 5/5 | 类型注解完整，方法职责单一，文档充分 |

### 业务耦合清单

| 耦合点 | 解耦方案 |
|--------|----------|
| `ApmCacheHandler` | 抽象为 `CacheBackend` 接口 |
| `ApmCacheConfig` | 过期时间作为构造参数 |
| `BaseInstanceData` | 已是抽象基类，保留即可 |
| `ApmApplication.trace_datasource.retention` | 参数化 `retention_days` |

### 迁移范围

- `cached_mixin.py` 全文（223 行）
- 配套迁移 `instance_data.py` 中的 `BaseInstanceData`（~10 行抽象 dataclass）

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 指标聚合缓存 | 带 TTL 和容量上限的聚合结果管理 |
| 拓扑快照管理 | 增量更新 + 过期淘汰的拓扑数据 |
| 配置热加载 | 带缓存的配置管理系统 |
| 微服务注册中心 | 实例注册/发现/淘汰的生命周期管理 |

---

## 三、有条件迁移目标：工具函数 + 注册表（17/25）

**源文件：** `apm/core/discover/base.py`

值得提取的通用组件：

| 组件 | 行数 | 可迁移性 |
|------|------|----------|
| `get_topo_instance_key` | ~30 | 高，纯函数，从 Span 嵌套结构提取字段 |
| `exists_field` | ~15 | 高，纯函数 |
| `extract_field_value` | ~7 | 高，纯函数 |
| `combine_list` | ~28 | 高，纯函数，列表合并去重 |
| `DiscoverContainer` | ~12 | 高，纯注册表模式 |
| `DiscoverBase` 核心抽象 | ~80 | 中，需泛化 Model 依赖 |
| `process_duplicate_records` | ~40 | 中，需泛化 model 参数 |

不推荐迁移：`TopoHandler`（~250 行）— ES 查询编排深度耦合 APM 专属组件。

---

## 四、不迁移模块说明

### `node.py`（8/25）

`NodeDiscover` 是纯 APM 拓扑节点发现业务逻辑，强依赖 TopoNode/BCSPod Django Model 和 ApmTopoDiscoverRule 规则体系。剥离后代码量不足 50 行，不值得迁移。

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 增量缓存刷新 | `cached_mixin.py` | 批量数据管理 |
| 双维度淘汰（时间+数量） | `cached_mixin.py` | 缓存容量管理 |
| 模板方法（三个抽象钩子） | `cached_mixin.py` | 可扩展缓存策略 |
| 注册表模式 | `base.py` | 插件式架构 |
| 规则匹配引擎 | `base.py` | 数据分类/路由 |
| 纯函数工具族 | `base.py` | Span 字段提取 |
| 批量去重 | `base.py` | 数据去重处理 |
| ES 分页 + 并行编排 | `base.py` | 大规模数据 ETL |
