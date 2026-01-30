# Aggregate Node Configuration (聚合节点配置)

## 节点类型
- **NodeType**: `aggregate`
- **分类**: DATA_PROCESSING (数据处理类)
- **功能**: 对事件数据进行聚合统计，支持多种聚合函数和分组维度

## 配置 Schema

### AggregateNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class AggregateFunction(str, Enum):
    """聚合函数"""
    COUNT = "count"         # 计数
    SUM = "sum"             # 求和
    AVG = "avg"             # 平均值
    MIN = "min"             # 最小值
    MAX = "max"             # 最大值
    FIRST = "first"         # 第一个值
    LAST = "last"           # 最后一个值
    DISTINCT_COUNT = "distinct_count"  # 去重计数
    COLLECT = "collect"     # 收集为列表
    CONCAT = "concat"       # 字符串连接


class AggregateFieldSerializer(serializers.Serializer):
    """聚合字段配置"""
    source_field = serializers.CharField(help_text="源字段路径")
    target_field = serializers.CharField(help_text="目标字段名")
    function = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AggregateFunction],
        help_text="聚合函数"
    )
    # 额外配置
    distinct = serializers.BooleanField(
        default=False,
        help_text="是否去重后聚合"
    )
    separator = serializers.CharField(
        default=",",
        required=False,
        help_text="连接分隔符（function=concat时使用）"
    )
    max_items = serializers.IntegerField(
        default=100,
        required=False,
        help_text="最大收集数量（function=collect时使用）"
    )


class GroupByConfigSerializer(serializers.Serializer):
    """分组配置"""
    fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="分组字段列表"
    )
    include_in_output = serializers.BooleanField(
        default=True,
        help_text="是否在输出中包含分组字段"
    )


class AggregateWindowSerializer(serializers.Serializer):
    """聚合窗口配置"""
    type = serializers.ChoiceField(
        choices=[
            ("tumbling", "滚动窗口"),
            ("sliding", "滑动窗口"),
            ("session", "会话窗口"),
        ],
        default="tumbling",
        help_text="窗口类型"
    )
    size = serializers.IntegerField(
        min_value=1,
        help_text="窗口大小（秒）"
    )
    slide = serializers.IntegerField(
        required=False,
        help_text="滑动间隔（type=sliding时使用）"
    )
    gap = serializers.IntegerField(
        required=False,
        help_text="会话间隔（type=session时使用）"
    )


class AggregateNodeConfigSerializer(BaseNodeConfigSerializer):
    """聚合节点配置"""
    node_type = serializers.CharField(default="aggregate", read_only=True)
    
    # 聚合字段配置
    aggregations = AggregateFieldSerializer(many=True, help_text="聚合字段配置列表")
    
    # 分组配置
    group_by = GroupByConfigSerializer(
        required=False,
        allow_null=True,
        help_text="分组配置"
    )
    
    # 时间窗口
    window = AggregateWindowSerializer(
        required=False,
        allow_null=True,
        help_text="聚合窗口配置"
    )
    
    # 输出模式
    output_mode = serializers.ChoiceField(
        choices=[
            ("update", "增量更新"),
            ("complete", "完整输出"),
            ("append", "追加输出"),
        ],
        default="complete",
        help_text="输出模式"
    )
    
    # 最小聚合数量
    min_count = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="触发聚合输出的最小事件数"
    )
    
    # 空值处理
    skip_null = serializers.BooleanField(
        default=True,
        help_text="是否跳过空值"
    )
    null_value = serializers.JSONField(
        default=None,
        required=False,
        help_text="空值替换值"
    )
    
    # 保留原始事件
    keep_original_events = serializers.BooleanField(
        default=False,
        help_text="是否保留原始事件列表"
    )
    original_events_field = serializers.CharField(
        default="_original_events",
        help_text="原始事件存储字段"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="聚合状态存储后端"
    )
    
    def validate_aggregations(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一个聚合字段")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "aggregate" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `aggregations` | array | 是 | - | 聚合字段配置 |
| `group_by` | object | 否 | null | 分组配置 |
| `window` | object | 否 | null | 窗口配置 |
| `output_mode` | string | 否 | "complete" | 输出模式 |
| `min_count` | integer | 否 | 1 | 最小聚合数 |
| `skip_null` | boolean | 否 | true | 跳过空值 |
| `keep_original_events` | boolean | 否 | false | 保留原始事件 |

### 聚合字段配置 (AggregateField)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source_field` | string | 是 | - | 源字段路径 |
| `target_field` | string | 是 | - | 目标字段名 |
| `function` | string | 是 | - | 聚合函数 |
| `distinct` | boolean | 否 | false | 去重后聚合 |
| `separator` | string | 否 | "," | 连接分隔符 |
| `max_items` | integer | 否 | 100 | 最大收集数 |

### 分组配置 (GroupByConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `fields` | array | 是 | - | 分组字段 |
| `include_in_output` | boolean | 否 | true | 包含在输出 |

### 聚合函数说明

| 函数 | 说明 | 返回类型 |
|------|------|----------|
| `count` | 计数 | integer |
| `sum` | 求和 | number |
| `avg` | 平均值 | number |
| `min` | 最小值 | number |
| `max` | 最大值 | number |
| `first` | 第一个值 | any |
| `last` | 最后一个值 | any |
| `distinct_count` | 去重计数 | integer |
| `collect` | 收集为列表 | array |
| `concat` | 字符串连接 | string |

### 窗口类型说明

| 类型 | 说明 | 配置项 |
|------|------|--------|
| `tumbling` | 滚动窗口 | size |
| `sliding` | 滑动窗口 | size, slide |
| `session` | 会话窗口 | gap |

## JSON 配置示例

### 示例 1: 按主机统计告警数量

```json
{
  "name": "host_alert_aggregate",
  "description": "按主机聚合统计告警数量和严重程度",
  "enabled": true,
  "node_type": "aggregate",
  "aggregations": [
    {
      "source_field": "event.alert_id",
      "target_field": "alert_count",
      "function": "count"
    },
    {
      "source_field": "event.severity",
      "target_field": "max_severity",
      "function": "min"
    },
    {
      "source_field": "event.severity",
      "target_field": "avg_severity",
      "function": "avg"
    },
    {
      "source_field": "event.alert_name",
      "target_field": "alert_names",
      "function": "collect",
      "distinct": true,
      "max_items": 50
    }
  ],
  "group_by": {
    "fields": ["event.dimensions.host", "event.biz_id"],
    "include_in_output": true
  },
  "window": {
    "type": "tumbling",
    "size": 300
  },
  "output_mode": "complete",
  "min_count": 1,
  "skip_null": true,
  "keep_original_events": false,
  "storage_backend": "redis",
  "execution": {
    "timeout": 30
  }
}
```

### 示例 2: 滑动窗口聚合

```json
{
  "name": "sliding_window_aggregate",
  "description": "5分钟滑动窗口聚合，每分钟更新",
  "enabled": true,
  "node_type": "aggregate",
  "aggregations": [
    {
      "source_field": "event.current_value",
      "target_field": "value_sum",
      "function": "sum"
    },
    {
      "source_field": "event.current_value",
      "target_field": "value_avg",
      "function": "avg"
    },
    {
      "source_field": "event.current_value",
      "target_field": "value_max",
      "function": "max"
    },
    {
      "source_field": "event.current_value",
      "target_field": "value_min",
      "function": "min"
    },
    {
      "source_field": "event.event_id",
      "target_field": "event_count",
      "function": "count"
    }
  ],
  "group_by": {
    "fields": ["event.strategy_id", "event.dimensions.instance"],
    "include_in_output": true
  },
  "window": {
    "type": "sliding",
    "size": 300,
    "slide": 60
  },
  "output_mode": "update",
  "min_count": 5,
  "skip_null": true,
  "null_value": 0,
  "storage_backend": "redis",
  "execution": {
    "timeout": 60
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 告警汇总报告

```json
{
  "name": "alert_summary_aggregate",
  "description": "按业务和告警类型生成汇总报告",
  "enabled": true,
  "node_type": "aggregate",
  "aggregations": [
    {
      "source_field": "event.alert_id",
      "target_field": "total_alerts",
      "function": "count"
    },
    {
      "source_field": "event.target",
      "target_field": "affected_targets",
      "function": "distinct_count"
    },
    {
      "source_field": "event.target",
      "target_field": "target_list",
      "function": "collect",
      "distinct": true,
      "max_items": 20
    },
    {
      "source_field": "event.alert_name",
      "target_field": "alert_type",
      "function": "first"
    },
    {
      "source_field": "event.time",
      "target_field": "first_alert_time",
      "function": "min"
    },
    {
      "source_field": "event.time",
      "target_field": "last_alert_time",
      "function": "max"
    },
    {
      "source_field": "event.description",
      "target_field": "descriptions",
      "function": "concat",
      "separator": " | ",
      "distinct": true
    }
  ],
  "group_by": {
    "fields": ["event.biz_id", "event.alert_name", "event.severity"],
    "include_in_output": true
  },
  "window": {
    "type": "tumbling",
    "size": 3600
  },
  "output_mode": "complete",
  "min_count": 1,
  "skip_null": true,
  "keep_original_events": true,
  "original_events_field": "_source_events",
  "storage_backend": "redis",
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 120
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **告警统计**：按主机/业务/策略统计告警数量
2. **趋势分析**：滑动窗口计算指标趋势
3. **汇总报告**：生成周期性告警汇总报告
4. **去重计数**：统计受影响的唯一目标数
5. **数据降采样**：减少数据量，保留统计信息
6. **关联分析**：收集相关告警用于关联分析
7. **实时仪表盘**：为监控仪表盘提供聚合数据

## 注意事项

1. **分组字段**：
   - 分组字段过多会产生大量聚合组
   - 建议选择关键维度字段
   - 注意字段值的基数

2. **窗口配置**：
   - 滚动窗口最简单，无重叠
   - 滑动窗口可实现平滑统计
   - 会话窗口适合按活动分组

3. **内存消耗**：
   - `collect` 函数会收集列表，注意内存
   - 设置合理的 `max_items` 限制
   - 大数据量场景使用Redis存储

4. **输出模式**：
   - `complete`：每次输出完整结果
   - `update`：增量更新变化的组
   - `append`：只追加新数据

5. **空值处理**：
   - `skip_null=true` 跳过空值
   - 可设置 `null_value` 替换空值

6. **原始事件**：
   - `keep_original_events=true` 保留原始列表
   - 会增加存储开销
   - 便于后续详细分析

7. **性能考虑**：
   - 聚合计算有一定延迟
   - 大窗口需要更多存储
   - 建议先过滤再聚合

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：过滤后聚合
  - Transform（转换节点）：转换后聚合
  - Window（窗口节点）：配合窗口使用

- **下游节点**：
  - Router（路由节点）：基于聚合结果路由
  - Notification（通知节点）：发送聚合报告
  - Storage（存储节点）：存储聚合结果

### 典型组合模式

1. **Filter → Aggregate → Notification**
   - 过滤 → 聚合 → 通知

2. **Window → Aggregate → Storage**
   - 窗口 → 聚合 → 存储

3. **Transform → Aggregate → Router**
   - 转换 → 聚合 → 路由

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
