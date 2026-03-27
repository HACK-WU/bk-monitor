# 监控策略维度（Dimensions）技术详解

## 概述

在蓝鲸监控平台中，**维度（Dimensions）**是策略配置的核心概念之一，它贯穿数据采集、检测、告警生成、通知收敛等全链路。理解维度的作用对于正确配置监控策略、优化告警质量至关重要。

本文档基于策略配置示例，详细说明维度的定义、作用机制及在各模块中的应用。

---

## 1. 维度的定义

### 1.1 什么是维度

维度是用于**标识和区分监控数据特征**的键值对集合。在时间序列监控中，维度类似于标签（Labels），用于描述监控指标的上下文信息。

### 1.2 示例策略中的维度

以提供的策略配置为例：

```json
{
  "query_configs": [
    {
      "agg_dimension": [
        "le",
        "namespace", 
        "callee_method",
        "env_name",
        "service_name",
        "app_name"
      ]
    }
  ]
}
```

**维度字段说明：**

| 维度字段 | 说明 | 示例值 |
|---------|------|--------|
| `le` | 直方图桶的上限值 | 各种耗时区间 |
| `namespace` | 命名空间 | production、testing |
| `callee_method` | 被调接口方法 | GetUserInfo |
| `env_name` | 环境名称 | dev、prod |
| `service_name` | 服务名称 | dev.helloworld |
| `app_name` | 应用名称 | trpc_test |

---

## 2. 维度的核心作用

### 2.1 数据聚合（Group By）

在数据查询阶段，`agg_dimension` 用于指定**按哪些维度对原始数据进行分组聚合**。

```
原始数据 → 按维度分组 → 聚合计算 → 生成时间序列
```

**处理流程：**

1. **数据接入层** (`access/data/processor.py`)
   - 从数据源（如Prometheus、InfluxDB）拉取原始指标数据
   - 根据 `agg_dimension` 指定的维度提取维度值

2. **维度提取逻辑** (`access/data/records.py:266-282`)

```python
def _origin_dimension(self):
    """获取原始数据的维度"""
    dimensions = {}
    if self._item.query.dimensions is None:
        # 如果没有指定维度，使用所有非系统字段
        for key, value in self.raw_data.items():
            if key not in ["_time_", "_result_"]:
                dimensions[key] = value
    else:
        # 按配置的 agg_dimension 提取指定维度
        for field in self._item.query.dimensions:
            dimensions[field] = self.raw_data.get(field)
    return dimensions
```

**示例说明：**

假设原始数据包含以下记录：

| timestamp | service_name | callee_method | env_name | value |
|-----------|-------------|---------------|----------|-------|
| 10:00:01 | dev.helloworld | GetUser | dev | 100ms |
| 10:00:01 | dev.helloworld | GetUser | dev | 120ms |
| 10:00:01 | dev.helloworld | GetOrder | dev | 80ms |

配置 `agg_dimension: ["service_name", "callee_method", "env_name"]` 后，数据将按这三个维度分组聚合：

| service_name | callee_method | env_name | avg(value) |
|-------------|---------------|----------|------------|
| dev.helloworld | GetUser | dev | 110ms |
| dev.helloworld | GetOrder | dev | 80ms |

### 2.2 告警去重（Dedupe）

维度最重要的作用之一是**确定告警的唯一性**，防止同一问题产生大量重复告警。

#### 2.2.1 去重 MD5 生成机制

**核心代码** (`core/alert/event.py:205-217`)

```python
def cal_dedupe_md5(self):
    """计算去重MD5，用于标识唯一告警"""
    self._dedupe_values = []
    for key in self.dedupe_keys:
        value = self.get_field(key)
        self._dedupe_values.append(value)
    
    # 基于去重字段值计算MD5
    self.data["dedupe_md5"] = count_md5(self._dedupe_values)
```

**默认去重字段** (`constants.py:75`)

```python
DEFAULT_DEDUPE_FIELDS = ["alert_name", "strategy_id", "target_type", "target", "bk_biz_id"]
```

**去重逻辑说明：**

| 场景 | dedupe_keys | 去重粒度 |
|-----|-------------|---------|
| 有策略ID的监控 | `["strategy_id", "target_type", "target", "bk_biz_id"]` | 同一策略+目标只产生一个告警 |
| 无策略ID的事件 | `["alert_name", "target_type", "target", "bk_biz_id"]` | 同一告警名称+目标只产生一个告警 |

**维度在去重中的作用：**

虽然维度字段不直接参与默认去重MD5计算，但**维度值的变化会导致目标（target）变化**，从而影响去重结果。

```
维度变化 → 目标标识变化 → dedupe_md5 不同 → 产生新告警
```

### 2.3 告警收敛（Converge）

在告警通知阶段，维度用于**确定告警的收敛分组**，控制通知频率。

#### 2.3.1 收敛配置中的维度

**策略配置示例**中的收敛配置：

```json
{
  "converge_config": {
    "condition": [
      {"dimension": "strategy_id", "value": ["self"]},
      {"dimension": "dimensions", "value": ["self"]},
      {"dimension": "alert_level", "value": ["self"]},
      {"dimension": "signal", "value": ["self"]},
      {"dimension": "bk_biz_id", "value": ["self"]}
    ]
  }
}
```

**维度哈希计算** (`core/context/converge.py:182-196`)

```python
@cached_property
def dimensions(self):
    """普通维度 - 用于收敛分组"""
    if self.parent.action.dimension_hash:
        return self.parent.action.dimension_hash
    
    # 从告警维度构建有序字典
    dimensions_dict = {d["key"]: d["value"] for d in self.parent.alert.common_dimensions}
    order_dimensions = collections.OrderedDict(sorted(dimensions_dict.items()))
    return count_md5(order_dimensions)
```

**收敛逻辑：**

当 `dimension: "dimensions"` 配置为收敛条件时，**维度值相同的告警会被归为一组进行收敛处理**。

### 2.4 降噪处理（Noise Reduce）

维度在告警降噪中用于**识别高频低危的告警模式**。

#### 2.4.1 降噪维度配置

**降噪配置示例：**

```json
{
  "noise_reduce_config": {
    "is_enabled": true,
    "dimensions": ["namespace", "service_name"]
  }
}
```

**降噪处理流程** (`fta_action/tasks/noise_reduce.py:83-94`)

```python
# 提取告警维度信息
alert_dimensions = {dimension.key: dimension.value for dimension in self.alert.dimensions}
dimensions = self.alert.origin_alarm["data"]["dimensions"] if self.alert.origin_alarm else alert_dimensions

# 根据降噪配置提取指定维度值
dimension_value = {
    dimension_key: dimensions.get(dimension_key) 
    for dimension_key in self.noise_reduce_config["dimensions"]
}

# 计算维度值的MD5哈希，用于去重
dimension_value_hash = count_md5(dimension_value)
```

**降噪原理：**

1. 按配置的降噪维度（如 `namespace`、`service_name`）提取维度值
2. 相同维度组合的告警在降噪窗口内只发送一次通知
3. 避免同一服务的大量相似告警轰炸接收人

### 2.5 告警展示与通知模板

维度信息会在告警详情页和通知消息中展示，帮助用户快速定位问题。

#### 2.5.1 通知模板中的维度变量

**消息模板示例：**

```
{{content.dimension}}
```

**渲染结果示例：**

```
维度信息:
- 命名空间: production
- 服务名称: dev.helloworld
- 被调方法: GetUserInfo
- 环境: dev
```

---

## 3. 维度全链路流转

### 3.1 数据流向图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           维度（Dimensions）全链路流转                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  1. 策略配置                                                                     │
│     ├─ agg_dimension: ["namespace", "service_name", "callee_method"]           │
│     └─ 定义需要关注的数据维度                                                     │
│                          ↓                                                      │
│  2. 数据接入层 (access/data)                                                      │
│     ├─ 从数据源拉取原始指标                                                        │
│     ├─ 按 agg_dimension 提取维度值 → DataRecord.dimensions                      │
│     └─ 生成 record_id (维度+时间的MD5)                                            │
│                          ↓                                                      │
│  3. 检测层 (detect)                                                               │
│     ├─ 基于维度分组进行阈值检测                                                    │
│     └─ 产生异常事件 (AnomalyEvent)                                               │
│                          ↓                                                      │
│  4. 事件生成层 (trigger)                                                          │
│     ├─ 维度信息 → Event.tags                                                     │
│     ├─ 计算 dedupe_md5 (用于告警去重)                                             │
│     └─ 维度值影响目标标识                                                          │
│                          ↓                                                      │
│  5. 告警构建层 (alert/builder)                                                    │
│     ├─ 基于 dedupe_md5 进行告警去重                                               │
│     ├─ 维度信息 → Alert.dimensions                                               │
│     └─ 丰富维度信息 (CMDB、拓扑等)                                                │
│                          ↓                                                      │
│  6. 动作处理层 (fta_action)                                                       │
│     ├─ 收敛: 按维度进行告警分组 (dimension_hash)                                  │
│     ├─ 降噪: 按降噪维度抑制高频告警                                               │
│     └─ 通知: 维度信息渲染到消息模板                                                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 核心数据结构

#### 3.2.1 DataRecord 中的维度

```python
{
    "record_id": "md5_hash",        # 维度+时间的MD5
    "dimensions": {                 # 维度键值对
        "namespace": "production",
        "service_name": "dev.helloworld",
        "callee_method": "GetUserInfo"
    },
    "dimension_fields": ["namespace", "service_name", "callee_method"],
    "value": 123.45,
    "time": 1704067200
}
```

#### 3.2.2 Event 中的维度

```python
{
    "event_id": "xxx",
    "strategy_id": 10969,
    "dedupe_md5": "abc123",         # 基于去重字段的MD5
    "tags": [                       # 维度转换为标签列表
        {"key": "namespace", "value": "production"},
        {"key": "service_name", "value": "dev.helloworld"}
    ],
    "target": "dev.helloworld",     # 目标标识（通常基于维度构建）
    "target_type": "service"
}
```

#### 3.2.3 Alert 中的维度

```python
{
    "id": "alert_id",
    "dedupe_md5": "abc123",
    "dimensions": [                 # 维度详细信息
        {
            "key": "namespace",
            "value": "production",
            "display_key": "命名空间",
            "display_value": "生产环境"
        }
    ],
    "assign_tags": [...]           # 分派标签（基于维度匹配）
}
```

---

## 4. 维度配置最佳实践

### 4.1 维度选择原则

#### 4.1.1 应该包含的维度

| 类型 | 维度示例 | 说明 |
|-----|---------|------|
| 资源标识 | `service_name`, `app_name` | 标识产生告警的服务/应用 |
| 环境信息 | `namespace`, `env_name` | 区分不同环境（生产/测试） |
| 位置信息 | `region`, `zone`, `cluster` | 标识地理位置或机房 |
| 业务属性 | `biz_id`, `team`, `project` | 业务归属信息 |
| 操作维度 | `callee_method`, `endpoint` | 具体的接口或方法 |

#### 4.1.2 避免过度维度

**问题：** 维度过多会导致：
1. 时间序列爆炸（ Cardinality 过高）
2. 告警过于分散，难以收敛
3. 存储和查询成本增加

**建议：**
- 核心维度控制在 **5-8个**
- 高基数维度（如 user_id、trace_id）不应作为 agg_dimension

### 4.2 不同场景的维度配置

#### 4.2.1 服务级监控（如示例策略）

```json
{
  "agg_dimension": [
    "namespace",
    "service_name", 
    "callee_method",
    "env_name"
  ]
}
```

**效果：** 按服务+方法维度聚合，每个方法独立检测和告警。

#### 4.2.2 主机级监控

```json
{
  "agg_dimension": [
    "bk_biz_id",
    "bk_host_id",
    "ip",
    "bk_cloud_id"
  ]
}
```

**效果：** 每台主机独立产生告警。

#### 4.2.3 业务级聚合监控

```json
{
  "agg_dimension": [
    "bk_biz_id",
    "app_name"
  ]
}
```

**效果：** 应用级别聚合，不关心具体服务/方法。

### 4.3 降噪维度配置建议

**高频低危告警场景：**

```json
{
  "noise_reduce_config": {
    "is_enabled": true,
    "dimensions": ["namespace", "service_name"]
  }
}
```

**说明：** 按命名空间+服务维度降噪，同一服务的多次异常只发一次通知。

---

## 5. 维度相关代码位置索引

### 5.1 核心模块

| 功能 | 文件路径 | 关键类/方法 |
|-----|---------|------------|
| 维度提取 | `alarm_backends/service/access/data/records.py` | `DataRecord.dimensions` |
| 数据推送 | `alarm_backends/service/access/data/processor.py` | `_push_noise_data()` |
| 去重MD5 | `alarm_backends/core/alert/event.py` | `cal_dedupe_md5()` |
| 告警构建 | `alarm_backends/service/alert/builder/processor.py` | `dedupe_events_to_alerts()` |
| 收敛上下文 | `alarm_backends/core/context/converge.py` | `Converge.dimensions` |
| 降噪处理 | `alarm_backends/service/fta_action/tasks/noise_reduce.py` | `NoiseReduceRecordProcessor` |
| 动作创建 | `alarm_backends/service/fta_action/tasks/create_action.py` | `CreateActionProcessor` |

### 5.2 配置常量

| 常量 | 文件路径 | 说明 |
|-----|---------|------|
| `DEFAULT_DEDUPE_FIELDS` | `alarm_backends/constants.py:75` | 默认去重字段 |
| `StandardDataFields` | `alarm_backends/constants.py:29` | 标准数据字段 |

---

## 6. 常见问题与排查

### 6.1 告警重复产生

**现象：** 同一问题产生多个告警。

**排查：**
1. 检查 `dedupe_keys` 配置是否合理
2. 确认维度值是否稳定（如动态IP导致target变化）

### 6.2 告警未按预期收敛

**现象：** 相似告警未分组收敛。

**排查：**
1. 检查收敛配置中的 `dimension: "dimensions"` 条件
2. 确认告警的 `dimension_hash` 是否相同

### 6.3 降噪不生效

**现象：** 高频告警未触发降噪。

**排查：**
1. 检查降噪配置中的 `dimensions` 是否与实际告警维度匹配
2. 确认 `dimension_value_hash` 计算逻辑

---

## 7. 总结

维度是监控策略中连接数据与告警的核心纽带，其重要作用包括：

1. **数据聚合**：`agg_dimension` 决定数据如何分组聚合
2. **告警去重**：维度影响 `dedupe_md5` 计算，防止重复告警
3. **告警收敛**：`dimension_hash` 用于告警分组收敛
4. **降噪控制**：降噪维度抑制高频低危告警
5. **信息展示**：维度信息帮助用户快速定位问题

合理配置维度是优化告警质量、减少告警疲劳的关键。
