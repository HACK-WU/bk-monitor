# apm Discover 实现层迁移价值评估报告（批次 5）

> 评估范围：`apm/core/discover/` 下 7 个具体实现文件（endpoint/host/instance/instance_data/root_endpoint/relation/remote_service_relation）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|--------|----------|--------|------------|----------|------|------|
| `instance_data.py` | 5 | 5 | 5 | 5 | 5 | **25** | ✅ 满分，强烈推荐 |
| `relation.py` | 3 | 4 | 2 | 4 | 4 | 17 | ❌ 不迁移（参考价值最高） |
| `endpoint.py` | 3 | 3 | 2 | 4 | 4 | 16 | ❌ 不迁移 |
| `instance.py` | 3 | 3 | 2 | 4 | 4 | 16 | ❌ 不迁移 |
| `root_endpoint.py` | 3 | 3 | 2 | 4 | 4 | 16 | ❌ 不迁移 |
| `remote_service_relation.py` | 3 | 3 | 2 | 4 | 4 | 16 | ❌ 不迁移 |
| `host.py` | 2 | 3 | 2 | 4 | 4 | 15 | ❌ 不迁移 |

---

## 二、迁移目标：数据契约层 DTO（25/25 满分）

**源文件：** `apm/core/discover/instance_data.py`

### 核心设计

```python
@dataclass
class BaseInstanceData(ABC):
    """Discover 系统的数据契约基类"""
    id: int = None
    updated_at: datetime = None

# 6 个具体子类
class EndpointInstanceData(BaseInstanceData): ...
class TopoInstanceData(BaseInstanceData): ...
class HostInstanceData(BaseInstanceData): ...
class RootEndpointInstanceData(BaseInstanceData): ...
class RelationInstanceData(BaseInstanceData): ...
class RemoteServiceRelationInstanceData(BaseInstanceData): ...
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 纯 dataclass 定义，不绑定任何框架或业务 |
| **复用价值** | 5/5 | 整个 discover 系统的数据契约，所有子类的公共依赖 |
| **独立性** | 5/5 | 仅依赖 `abc` + `datetime` 标准库 |
| **接口稳定性** | 5/5 | dataclass 结构稳定，字段语义清晰 |
| **代码质量** | 5/5 | 类型注解完整，继承层次清晰，职责单一 |

### 迁移范围

单文件迁移，无需携带其他依赖。建议将业务相关字段重命名（如 `component_instance_category` → `category`）。

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 服务发现 | 发现结果与数据库记录的解耦层 |
| DTO 模式 | 数据传输对象，服务间通信 |
| 缓存桥接 | 缓存系统与数据库之间的数据层 |

---

## 三、不迁移模块说明（全部 ≥15 分但依赖过深）

| 文件 | 总分 | 不迁移原因 | 最有价值的参考设计 |
|------|------|-----------|-------------------|
| `relation.py` | 17 | 依赖 TopoRelation/TopoNode Django Model | `get_relation_map`：span_id → {from, to[], kind} 关系映射构建 |
| `endpoint.py` | 16 | 依赖 Endpoint Django Model + 规则引擎 | 两阶段发现（普通接口 + 自定义服务） |
| `instance.py` | 16 | 依赖 TopoInstance Django Model | service/component 双轨发现策略 |
| `root_endpoint.py` | 16 | 依赖 RootEndpoint Django Model | Trace 级别发现：group_by_trace_id + 首 span 定位 |
| `remote_service_relation.py` | 16 | 依赖 RemoteServiceRelation Django Model | span 预分类：按 PEER_SERVICE 字段分为两个字典 |
| `host.py` | 15 | 依赖 CMDB 缓存（HostManager） | 外部系统集成 + 延迟导入模式 |

### 共性参考模式

所有 7 个文件共享以下设计模式：

| 模式 | 说明 |
|------|------|
| **增量发现** | `need_update_instances` vs `need_create_instances` 分离创建/更新 |
| **唯一键生成** | `_to_found_key()` 类方法定义缓存 key |
| **缓存 key 约定** | `to_cache_key()` + split 分隔符模式 |

---

## 四、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| DTO 数据契约层 | `instance_data.py` | 服务发现、数据传输 |
| span 关系映射构建 | `relation.py` | Trace 分析、调用链构建 |
| Trace 分组 + 首 span 定位 | `root_endpoint.py` | 入口发现 |
| span 预分类 | `remote_service_relation.py` | 远程服务关系发现 |
| 外部系统延迟集成 | `host.py` | CMDB/外部数据源集成 |
| 双轨发现策略 | `instance.py` | 服务/组件并行发现 |
