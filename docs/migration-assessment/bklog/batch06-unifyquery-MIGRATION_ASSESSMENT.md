# log_unifyquery 模块迁移价值评估报告（批次 6）

> 评估范围：`bklog/apps/log_unifyquery/`（16 个文件，约 4,862 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `builder/context.py` | 284 | **20/25** | ✅ 推荐迁移 |
| `builder/tail.py` | 325 | **18/25** | ✅ 推荐迁移 |
| `constants.py` | 99 | **18/25** | ✅ 推荐迁移 |
| `handler/mapping.py` | 852 | 17/25 | ⚠️ 有条件迁移 |
| `handler/field.py` | 245 | 16/25 | ⚠️ 有条件迁移 |
| `handler/terms_aggs.py` | 162 | 15/25 | ⚠️ 有条件迁移 |
| `handler/pattern.py` | 108 | 15/25 | ⚠️ 有条件迁移 |
| `utils.py` | 91 | 15/25 | ⚠️ 有条件迁移 |
| `handler/base.py` | 1,510 | 11/25 | ❌ 不迁移 |
| `handler/async_export_handlers.py` | 406 | 12/25 | ❌ 不迁移 |
| `handler/context.py` | 261 | 12/25 | ❌ 不迁移 |
| `handler/chart.py` | 119 | 12/25 | ❌ 不迁移 |
| `handler/agg.py` | 72 | 12/25 | ❌ 不迁移 |
| `handler/tail.py` | 112 | 11/25 | ❌ 不迁移 |
| `views.py` | 183 | 9/25 | ❌ 不迁移 |
| `urls.py` | 33 | 10/25 | ❌ 不迁移 |

---

## 二、迁移目标 1：上下文查询条件构造器（20/25）

**源文件：** `log_unifyquery/builder/context.py`

### 核心设计

基于多字段排序的上下文查询条件构造算法：

```python
def create_context_conditions(sort_fields, search_after, direction="+", extra_conditions=None):
    """
    对 N 个排序字段，生成 N 组 OR 条件，每组内部用 AND 连接前序精确匹配和当前范围条件
    支持 +（向后翻页）和 -（向前翻页）两种方向
    """
```

三个 Builder 类适配不同场景：
- `CreateSearchContextBodyScenarioBkData`：BKData 场景（gseindex/_iteration_idx/dtEventTimeStamp）
- `CreateSearchContextBodyScenarioLog`：LOG 场景（gseIndex/iterationIndex/dtEventTimeStamp）
- `CreateSearchContextBodyCustomField`：自定义字段场景

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 上下文查询条件构造是搜索系统通用能力 |
| **复用价值** | 4/5 | 多字段排序条件构造算法可直接复用 |
| **独立性** | 4/5 | 不依赖 Django models，仅依赖 arrow 时间库 |
| **接口稳定性** | 4/5 | Builder 模式接口明确，kwargs 参数结构稳定 |
| **代码质量** | 3/5 | 算法清晰，但三个 Builder 类存在代码重复 |

### 迁移范围

- `create_context_conditions` 函数（核心算法，约 60 行）
- `build_context_params` 时间范围计算辅助函数（15 行）
- 三个 Builder 类（建议先抽取公共基类后迁移，约 200 行）

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 日志/文本检索上下文查看 | 从任意位置向前后翻页 |
| 多字段排序分页 | 支持复合排序键的 search_after 分页 |
| 容器日志实时定位 | container_id + logfile 组合定位 |

---

## 三、迁移目标 2：实时日志尾部查询构造器（18/25）

**源文件：** `log_unifyquery/builder/tail.py`

三个 Builder 类分别适配 LOG、BKData、自定义字段场景的实时 tail 查询，支持 `zero` 模式（定位最新日志）和 `gse_index` 模式（从指定位置继续）。

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 实时日志 tail 查询是日志系统通用能力 |
| **复用价值** | 4/5 | Builder 模式构造查询参数可复用 |
| **独立性** | 4/5 | 不依赖 Django models，仅依赖 arrow 和 time |
| **接口稳定性** | 4/5 | 接口通过 kwargs 传参，结构稳定 |
| **代码质量** | 2/5 | 三个 Builder 类存在大量重复代码，未做基类抽象 |

### 迁移建议

迁移前先抽取公共基类消除重复代码。约 325 行。

---

## 四、迁移目标 3：查询操作符映射常量（18/25）

**源文件：** `log_unifyquery/constants.py`

### 核心设计

```python
BASE_OP_MAP = {      # 基础操作符：=, !=, contains, >, is one of → eq, ne, contains, gt
    OperatorEnum.EQ: "eq",
    OperatorEnum.NE: "ne",
    OperatorEnum.CONTAINS: "contains",
    ...
}
ADVANCED_OP_MAP = {  # 高级操作符：match_phrase, wildcard, exists 等
    OperatorEnum.MATCH_PHRASE: "match_phrase",
    OperatorEnum.WILDCARD: "wildcard",
    ...
}
AggTypeEnum           # 聚合类型枚举：max/min/avg/median
FIELD_TYPE_MAP        # 字段类型映射表
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 操作符映射是查询系统通用常量 |
| **复用价值** | 3/5 | 可作为查询系统操作符映射标准参考 |
| **独立性** | 4/5 | 仅依赖 `log_search.constants.OperatorEnum` |
| **接口稳定性** | 3/5 | 操作符集会随业务增长，但基础映射稳定 |
| **代码质量** | 4/5 | 定义清晰，枚举和映射表结构合理 |

---

## 五、有条件迁移目标（15-17 分）

| 文件 | 总分 | 可提取价值 |
|------|------|-----------|
| `handler/mapping.py` | 17 | 虚拟字段注入模式、字段能力分析模式、缓存策略分层 |
| `handler/field.py` | 16 | 聚合结果处理模式（handle_count_data、get_agg_value_by_agg_method） |
| `handler/terms_aggs.py` | 15 | 多字段 Terms 聚合合并模式 |
| `handler/pattern.py` | 15 | 结果维度重排序模式 |
| `utils.py` | 15 | `deal_time_format` 时间格式处理可独立提取 |

---

## 六、不迁移模块说明

| 文件 | 总分 | 不迁移原因 |
|------|------|-----------|
| `handler/base.py` | 11 | "上帝类"设计，1510 行依赖 15+ Django model，职责过重 |
| `handler/async_export_handlers.py` | 12 | 异步导出与 Django ORM + Celery 深度耦合 |
| `handler/context.py` | 12 | 上下文搜索与特定字段结构强绑定 |
| `handler/chart.py` | 12 | 纯薄包装层，与 UnifyQueryApi 直接耦合 |
| `handler/agg.py` | 12 | 仪表盘聚合查询的薄封装 |
| `handler/tail.py` | 11 | 纯分发层，无独立逻辑 |
| `views.py` | 9 | Django REST Framework 标准 ViewSet |
| `urls.py` | 10 | Django URL 配置 |

---

## 七、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 多字段排序条件构造算法（OR/AND 组合） | `builder/context.py` | search_after 分页查询 |
| Builder 模式构造复杂查询参数 | `builder/context.py`、`builder/tail.py` | 查询参数构建 |
| 操作符映射表（前端→后端） | `constants.py` | 查询系统操作符标准化 |
| 虚拟字段注入模式 | `handler/mapping.py` | 动态计算字段 |
| 字段能力分析模式 | `handler/mapping.py` | 根据字段组合判断系统能力 |
| 缓存策略分层（1分钟/10分钟） | `handler/mapping.py` | 不同数据源差异化缓存 |
| 聚合结果处理模式 | `handler/field.py` | 统一聚合计算 |
| 脱敏装饰器模式 | `handler/base.py` | 字段配置返回格式统一 |
| 滚动导出生成器（yield 分批） | `handler/base.py` | 大数据量分批导出 |
| 预查询优化策略 | `handler/base.py` | 双阶段查询减少全量查询 |
| 嵌套字典 dotted key 转换 | `handler/base.py` | dotted path → 嵌套字典构建 |
