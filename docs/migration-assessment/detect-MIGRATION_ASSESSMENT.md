# alarm_backends/service/detect 迁移价值评估报告

> 评估范围：`bkmonitor/alarm_backends/service/detect/` 全部 24 个 Python 文件
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）
> 迁移目标：PythonCodeHub — 可复用、低耦合、易参考的通用 Python 代码

---

## 一、总览

### 核心框架

| 文件 | 总分 | 结论 |
|------|------|------|
| `double_check_strategies/sum.py` | 16/25 | ⚠️ 有选择性迁移价值（Protocol+注册表） |
| `core.py` | 15/25 | ⚠️ 有迁移价值，需重构（字典转属性对象） |
| `strategy/__init__.py` | 15/25 | ❌ 不迁移（设计理念值得参考） |
| `process.py` | 13/25 | ❌ 不迁移（Pipeline 编排模式有参考价值） |
| `handler.py` | 10/25 | ❌ 不迁移 |
| `tasks.py` | 10/25 | ❌ 不迁移 |
| `__init__.py` | 6/25 | ❌ 不迁移 |

### 14 个策略实现

| 分类 | 文件 | 总分 | 结论 |
|------|------|------|------|
| **最值得关注** | `time_series_forecasting.py` | 15/25 | ⚠️ `_threshold_detect` 可提取 |
| **标准同比/环比** | `advanced_ring_ratio.py` | 13/25 | ❌ 模式通用但改造成本高 |
| | `advanced_year_round.py` | 13/25 | ❌ 同上 |
| | `ring_ratio_amplitude.py` | 13/25 | ❌ 同上 |
| | `year_round_amplitude.py` | 13/25 | ❌ 同上 |
| | `year_round_range.py` | 13/25 | ❌ 同上 |
| **基类特化** | `simple_year_round.py` | 12/25 | ❌ 仅是基类配置特化 |
| **工程参考** | `os_restart.py` | 11/25 | ❌ 自治预取模式有参考价值 |
| **SDK 薄壳** | `abnormal_cluster.py` | 9/25 | ❌ 算法在外部 SDK |
| | `intelligent_detect.py` | 9/25 | ❌ 同上 |
| **极简/透传** | `ping_unreachable.py` | 8/25 | ❌ 逻辑太简单 |
| | `proc_port.py` | 8/25 | ❌ 纯表达式组合 |
| **无自有算法** | `host_anomaly_detection.py` | 6/25 | ❌ 预计算结果透传 |
| | `multivariate_anomaly_detection.py` | 6/25 | ❌ 同上 |

### Double Check 策略

| 文件 | 总分 | 结论 |
|------|------|------|
| `double_check_strategies/sum.py` | 16/25 | ⚠️ Protocol+注册表机制可提取 |
| `double_check_strategies/__init__.py` | 5/25 | ❌ 纯注册清单 |

---

## 二、评估结论：整体不建议迁移

按迁移 skill 的标准（同时满足通用性/复用价值/独立性/接口稳定性/代码质量），**detect 模块没有一个文件达到直接迁移的门槛**。

核心原因：
1. **业务耦合过深** — 14 个策略实现全部深度绑定 `DataPoint`/`Item`/`Strategy` 领域模型和 Redis 缓存体系
2. **算法在外部** — 智能检测类策略（abnormal_cluster、intelligent_detect、host_anomaly_detection）的核心算法在 AIOps SDK 侧，本模块只是调度壳
3. **框架层有价值但需重写** — `strategy/__init__.py` 的表达式引擎+组合检测器架构设计优秀，但剥离 DataPoint 后代码量缩减 60%+，不值得搬运

---

## 三、值得作为设计参考的模式

以下模式不迁移代码，但可作为 PythonCodeHub 中重新实现的参考：

### 3.1 表达式检测引擎（`strategy/__init__.py`，15/25）

```
gen_expr() → compile() → eval()
上下文通过 extra_context() 注入
支持 AND/OR 组合多个子检测器
配置校验通过 DRF serializer 实现
```

**参考方向：** 设计通用的 `ExpressionRuleEngine`，借鉴表达式编译+eval、AND/OR 组合、serializer 配置校验三处核心设计。

### 3.2 Pipeline 编排模式（`process.py`，13/25）

```
pull_data() → handle_data() → double_check() → push_data()
异常隔离：double_check 失败不影响主流程
忙时自动重入
分布式锁保护
```

**参考方向：** 抽象为通用的 `PipelineProcessor` 基类框架。

### 3.3 字典转属性对象（`core.py`，15/25）

```python
# DataPoint 通过 setattr 实现字典到对象的透明映射
class DataPoint:
    def __init__(self, item, data):
        for key, value in data.items():
            setattr(self, key, value)
        self.item = item

    def as_dict(self) -> dict: ...
    @property
    def timestamp(self): return self.time
```

**参考方向：** 抽象为通用的 `DynamicAttrDict` 或 `RecordObject` 基类，剥离 `item`/`unit` 业务依赖，移除 `six` 库。

### 3.4 AND-of-OR 多层阈值匹配（`time_series_forecasting.py`，15/25）

```python
OPERATOR_MAPPINGS = {"gt": operator.gt, "gte": operator.ge, ...}

def _threshold_detect(self, values, thresholds):
    """通用的多层阈值匹配：外层 AND，内层 OR"""
    for level_conditions in thresholds:        # 外层：AND
        if not any(                            # 内层：OR
            self._check_condition(value, cond)
            for cond in level_conditions
            for value in values
        ):
            return False
    return True
```

**参考方向：** 独立的纯算法组件，零业务依赖，可直接提取。

### 3.5 DoubleCheckStrategy Protocol + 注册表（`double_check_strategies/sum.py`，16/25）

```
Protocol 定义：check_hit() → double_check() → check_points_missing()
装饰器注册：@register_double_check_strategy
策略选择：pick_double_check_strategy() 按匹配度选择最优策略
dataclass + ClassVar 组合
```

**参考方向：** 这与 `core/control/` 评估中的 DoubleCheckStrategy 是同一套机制，已在 core 模块评估中标记为迁移目标。

### 3.6 历史数据三级缓存（`strategy/__init__.py`）

```
批量预取 → Redis 缓存 → 本地存储
支持 partial 查询容错（部分失败不影响整体）
```

**参考方向：** 通用的多级缓存预取模式。

### 3.7 同比/环比/振幅检测模式（7 个策略文件，13/25）

| 模式 | 文件 | 算法 |
|------|------|------|
| 高级同比 | `advanced_year_round.py` | 前 N 天同均值/瞬时值 → 百分比比较 |
| 高级环比 | `advanced_ring_ratio.py` | 前 N 个聚合周期均值/瞬时值 → 百分比比较 |
| 环比振幅 | `ring_ratio_amplitude.py` | 相对变化量 + 绝对变化量双重门槛 |
| 同比振幅 | `year_round_amplitude.py` | 差分序列的同比比较 |
| 同比区间 | `year_round_range.py` | 绝对值比较，遍历多天 |
| 简易同比 | `simple_year_round.py` | 上周同同时刻百分比比较 |
| 系统重启 | `os_restart.py` | 多条件复合 + 自治历史预取 |

**参考方向：** 这些算法模式在时序分析领域通用（金融风控、IoT 监控、运维自动化），但实现与 DataPoint 体系深度耦合，需从零设计通用接口后重新实现。

---

## 四、与 core/control 模块的关联

detect 模块中的 `DoubleCheckStrategy` Protocol + 注册表机制，与 `alarm_backends/core/control/mixins/double_check.py` 是**同一套代码**的不同使用位置：

- **定义位置：** `core/control/mixins/double_check.py`（Protocol + 注册表 + 策略选择）
- **使用位置：** `detect/double_check_strategies/sum.py`（具体策略实现）

在 core 模块的评估中，这套机制已被标记为 **P1 迁移目标**（16/25）。detect 模块中的 `sum.py` 是其业务实现，不单独迁移。

---

## 五、设计参考索引

| 模式 | 来源文件 | 适用场景 |
|------|----------|----------|
| 表达式编译+eval 检测 | `strategy/__init__.py` | 规则引擎、决策引擎 |
| AND/OR 组合检测器 | `strategy/__init__.py` | 复合条件判定 |
| Pipeline 编排+异常隔离 | `process.py` | 数据处理流水线 |
| 字典转属性对象 | `core.py` | 数据封装、ORM 替代 |
| 多层阈值匹配 | `time_series_forecasting.py` | 阈值告警、合规检查 |
| Protocol+注册表 | `double_check_strategies/sum.py` | 插件系统、策略框架 |
| 三级缓存预取 | `strategy/__init__.py` | 缓存优化 |
| 同比/环比/振幅算法 | 7 个策略文件 | 时序分析、异常检测 |
| 自治历史预取绕 cache | `os_restart.py` | 缓存漏报修复 |
| 锁失败延迟重入 | `tasks.py` | 分布式并发控制 |
| 二级缓存查询 | `handler.py` | 缓存降级 |
