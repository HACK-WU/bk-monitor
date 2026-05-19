# apm Query 处理器迁移价值评估报告（批次 7）

> 评估范围：`apm/core/handlers/query/` 下 8 个文件（约 1,270 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 核心类 | 总分 | 结论 |
|------|--------|------|------|
| `define.py` | `TraceInfoList`, `QueryMode` | **22/25** | ✅ 强烈推荐 |
| `base.py` | `FilterOperator`, `BaseQuery`, `FakeQuery` | **21/25** | ✅ 值得迁移 |
| `proxy.py` | `QueryProxy` | 15/25 | ❌ 不迁移（参考） |
| `trace_query.py` | `TraceQuery` | 14/25 | ❌ 不迁移（参考） |
| `span_query.py` | `SpanQuery` | 14/25 | ❌ 不迁移（参考） |
| `origin_trace_query.py` | `OriginTraceQuery` | 13/25 | ❌ 不迁移（参考） |
| `ebpf_query.py` | `DeepFlowQuery` | 11/25 | ❌ 不迁移 |
| `builder.py` | (re-export) | 8/25 | ❌ 不迁移 |

---

## 二、迁移目标 1：分页数据结构与查询模式枚举（22/25）

**源文件：** `apm/core/handlers/query/define.py`

```python
@dataclass
class TraceInfoList:
    total: int = 0
    data: list = field(default_factory=list)

class QueryMode:
    TRACE = "trace"
    ORIGIN_TRACE = "origin_trace"
    SPAN = "span"
```

**零外部依赖**，纯 Python dataclass + 常量。整文件迁移，仅需重命名。

---

## 三、迁移目标 2：查询基础设施（21/25）

**源文件：** `apm/core/handlers/query/base.py`

### 核心设计

三个组件构成查询基础设施：

| 组件 | 说明 |
|------|------|
| `FilterOperator` | 策略模式过滤器，11 种操作符 + 操作符到处理器的映射表 |
| `BaseQuery` | 模板方法基类：时间范围管理 / 分页 / 过滤构建 / 聚合查询 / 字段翻译 |
| `FakeQuery` | Null Object 模式，空查询降级 |

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 多操作符过滤、时间范围管理、分页查询是通用模式 |
| **复用价值** | 5/5 | 整个查询子系统的基石，设计模式复用价值极高 |
| **独立性** | 3/5 | 依赖 Django ORM（Q）、Django 工具、平台组件 |
| **接口稳定性** | 4/5 | 接口已成熟稳定 |
| **代码质量** | 5/5 | 策略模式、模板方法、Null Object 运用得当 |

### 业务耦合清单

| 耦合点 | 解耦方案 |
|--------|----------|
| `apm.types.Filter/FilterValue/Page` | 迁移为通用类型 |
| `apm.models.*DataSource` | 抽象为数据源配置协议 |
| `bkmonitor.data_source.utils.apm.TraceQueryGuard` | 抽象为查询守卫接口 |
| `django.db.models.Q` | 替换为通用过滤器 DSL |
| `django.utils.functional.cached_property` | 替换为 `functools.cached_property` |

---

## 四、不迁移模块说明

| 文件 | 总分 | 可参考设计 |
|------|------|-----------|
| `proxy.py` | 15 | 多查询模式路由、TraceId 精确查询检测、跨应用 Trace 关联 |
| `trace_query.py` | 14 | 预计算表查询模式、字段前缀翻译、多表合并查询 |
| `span_query.py` | 14 | 字段排除机制、Trace/Span ID 查询优化 |
| `origin_trace_query.py` | 13 | distinct + 并发组装模式 |
| `ebpf_query.py` | 11 | 纯业务封装 |

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 策略模式过滤操作符 | `base.py` | 多操作符过滤器系统 |
| 模板方法查询基类 | `base.py` | 统一查询框架 |
| Null Object 空查询 | `base.py` | 查询降级/空态处理 |
| 多模式路由 | `proxy.py` | 多视角统一查询入口 |
| 字段前缀翻译 | `trace_query.py` | OTel/日志字段映射 |
| distinct + 并发组装 | `origin_trace_query.py` | 先去重再并发查询详情 |
