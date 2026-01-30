# Window Node Configuration (窗口节点配置)

## 节点类型
- **NodeType**: `window`
- **分类**: DATA_PROCESSING (数据处理类)
- **功能**: 基于时间窗口对事件进行分组和缓冲处理

## 配置 Schema

### WindowNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class WindowType(str, Enum):
    """窗口类型"""
    TUMBLING = "tumbling"       # 滚动窗口
    SLIDING = "sliding"         # 滑动窗口
    SESSION = "session"         # 会话窗口
    GLOBAL = "global"           # 全局窗口


class WindowTrigger(str, Enum):
    """窗口触发方式"""
    TIME = "time"               # 时间触发
    COUNT = "count"             # 数量触发
    TIME_OR_COUNT = "time_or_count"  # 时间或数量触发
    CUSTOM = "custom"           # 自定义触发


class WindowOutputMode(str, Enum):
    """窗口输出模式"""
    BATCH = "batch"             # 批量输出
    STREAM = "stream"           # 流式输出
    ON_CLOSE = "on_close"       # 窗口关闭时输出


class TumblingWindowConfigSerializer(serializers.Serializer):
    """滚动窗口配置"""
    size = serializers.IntegerField(
        min_value=1,
        help_text="窗口大小（秒）"
    )
    offset = serializers.IntegerField(
        default=0,
        help_text="窗口偏移量（秒）"
    )


class SlidingWindowConfigSerializer(serializers.Serializer):
    """滑动窗口配置"""
    size = serializers.IntegerField(
        min_value=1,
        help_text="窗口大小（秒）"
    )
    slide = serializers.IntegerField(
        min_value=1,
        help_text="滑动间隔（秒）"
    )


class SessionWindowConfigSerializer(serializers.Serializer):
    """会话窗口配置"""
    gap = serializers.IntegerField(
        min_value=1,
        help_text="会话间隔（秒）"
    )
    max_duration = serializers.IntegerField(
        default=3600,
        help_text="最大会话时长（秒）"
    )


class WindowKeyConfigSerializer(serializers.Serializer):
    """窗口键配置"""
    fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="分组字段列表"
    )
    separator = serializers.CharField(
        default="|",
        help_text="字段分隔符"
    )


class WindowTriggerConfigSerializer(serializers.Serializer):
    """窗口触发配置"""
    trigger_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in WindowTrigger],
        default="time",
        help_text="触发类型"
    )
    # 时间触发配置
    time_interval = serializers.IntegerField(
        default=60,
        help_text="时间触发间隔（秒）"
    )
    # 数量触发配置
    count_threshold = serializers.IntegerField(
        default=100,
        help_text="数量触发阈值"
    )
    # 早期触发
    early_trigger_enabled = serializers.BooleanField(
        default=False,
        help_text="是否启用早期触发"
    )
    early_trigger_interval = serializers.IntegerField(
        default=10,
        help_text="早期触发间隔（秒）"
    )


class LateDataConfigSerializer(serializers.Serializer):
    """迟到数据配置"""
    allowed_lateness = serializers.IntegerField(
        default=0,
        help_text="允许的迟到时间（秒）"
    )
    late_data_action = serializers.ChoiceField(
        choices=[
            ("drop", "丢弃"),
            ("update", "更新窗口"),
            ("side_output", "侧输出"),
        ],
        default="drop",
        help_text="迟到数据处理方式"
    )
    side_output_field = serializers.CharField(
        default="_late_events",
        help_text="侧输出字段名"
    )


class WindowNodeConfigSerializer(BaseNodeConfigSerializer):
    """窗口节点配置"""
    node_type = serializers.CharField(default="window", read_only=True)
    
    # 窗口类型
    window_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in WindowType],
        default="tumbling",
        help_text="窗口类型"
    )
    
    # 滚动窗口配置
    tumbling = TumblingWindowConfigSerializer(
        required=False,
        help_text="滚动窗口配置"
    )
    
    # 滑动窗口配置
    sliding = SlidingWindowConfigSerializer(
        required=False,
        help_text="滑动窗口配置"
    )
    
    # 会话窗口配置
    session = SessionWindowConfigSerializer(
        required=False,
        help_text="会话窗口配置"
    )
    
    # 窗口键配置
    window_key = WindowKeyConfigSerializer(
        required=False,
        help_text="窗口键配置（分组）"
    )
    
    # 时间字段
    time_field = serializers.CharField(
        default="event.time",
        help_text="事件时间字段"
    )
    use_processing_time = serializers.BooleanField(
        default=False,
        help_text="是否使用处理时间（而非事件时间）"
    )
    
    # 触发配置
    trigger = WindowTriggerConfigSerializer(
        required=False,
        help_text="窗口触发配置"
    )
    
    # 迟到数据配置
    late_data = LateDataConfigSerializer(
        required=False,
        help_text="迟到数据配置"
    )
    
    # 输出模式
    output_mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in WindowOutputMode],
        default="on_close",
        help_text="输出模式"
    )
    
    # 窗口元数据
    include_window_info = serializers.BooleanField(
        default=True,
        help_text="是否包含窗口元数据"
    )
    window_start_field = serializers.CharField(
        default="_window_start",
        help_text="窗口开始时间字段"
    )
    window_end_field = serializers.CharField(
        default="_window_end",
        help_text="窗口结束时间字段"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="窗口状态存储后端"
    )
    
    # 最大窗口数
    max_windows = serializers.IntegerField(
        default=1000,
        help_text="最大并行窗口数"
    )
    
    def validate(self, attrs):
        window_type = attrs.get('window_type')
        if window_type == 'tumbling' and not attrs.get('tumbling'):
            raise serializers.ValidationError(
                "window_type=tumbling时必须配置tumbling参数"
            )
        if window_type == 'sliding' and not attrs.get('sliding'):
            raise serializers.ValidationError(
                "window_type=sliding时必须配置sliding参数"
            )
        if window_type == 'session' and not attrs.get('session'):
            raise serializers.ValidationError(
                "window_type=session时必须配置session参数"
            )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "window" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `window_type` | string | 否 | "tumbling" | 窗口类型 |
| `time_field` | string | 否 | "event.time" | 时间字段 |
| `use_processing_time` | boolean | 否 | false | 使用处理时间 |
| `output_mode` | string | 否 | "on_close" | 输出模式 |
| `include_window_info` | boolean | 否 | true | 包含窗口信息 |
| `max_windows` | integer | 否 | 1000 | 最大窗口数 |

### 滚动窗口配置 (TumblingWindowConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `size` | integer | 是 | - | 窗口大小（秒） |
| `offset` | integer | 否 | 0 | 窗口偏移量 |

### 滑动窗口配置 (SlidingWindowConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `size` | integer | 是 | 窗口大小（秒） |
| `slide` | integer | 是 | 滑动间隔（秒） |

### 会话窗口配置 (SessionWindowConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `gap` | integer | 是 | - | 会话间隔（秒） |
| `max_duration` | integer | 否 | 3600 | 最大会话时长 |

### 窗口类型说明

| 类型 | 说明 | 特点 |
|------|------|------|
| `tumbling` | 滚动窗口 | 固定大小，无重叠 |
| `sliding` | 滑动窗口 | 可重叠，平滑统计 |
| `session` | 会话窗口 | 按活动分组 |
| `global` | 全局窗口 | 所有数据一个窗口 |

### 触发方式说明

| 方式 | 说明 | 适用场景 |
|------|------|----------|
| `time` | 时间触发 | 固定周期输出 |
| `count` | 数量触发 | 数据量驱动 |
| `time_or_count` | 时间或数量 | 灵活触发 |
| `custom` | 自定义 | 复杂逻辑 |

## JSON 配置示例

### 示例 1: 滚动窗口（5分钟）

```json
{
  "name": "tumbling_window_5min",
  "description": "5分钟滚动窗口分组",
  "enabled": true,
  "node_type": "window",
  "window_type": "tumbling",
  "tumbling": {
    "size": 300,
    "offset": 0
  },
  "window_key": {
    "fields": ["event.biz_id", "event.strategy_id"],
    "separator": "|"
  },
  "time_field": "event.time",
  "use_processing_time": false,
  "trigger": {
    "trigger_type": "time",
    "time_interval": 300
  },
  "output_mode": "on_close",
  "include_window_info": true,
  "window_start_field": "_window_start",
  "window_end_field": "_window_end",
  "storage_backend": "redis",
  "max_windows": 1000,
  "execution": {
    "timeout": 60
  }
}
```

### 示例 2: 滑动窗口（10分钟窗口，1分钟滑动）

```json
{
  "name": "sliding_window_10min",
  "description": "10分钟滑动窗口，每分钟计算一次",
  "enabled": true,
  "node_type": "window",
  "window_type": "sliding",
  "sliding": {
    "size": 600,
    "slide": 60
  },
  "window_key": {
    "fields": ["event.dimensions.host", "event.metric_name"],
    "separator": ":"
  },
  "time_field": "event.time",
  "trigger": {
    "trigger_type": "time_or_count",
    "time_interval": 60,
    "count_threshold": 1000,
    "early_trigger_enabled": true,
    "early_trigger_interval": 10
  },
  "late_data": {
    "allowed_lateness": 60,
    "late_data_action": "update",
    "side_output_field": "_late_events"
  },
  "output_mode": "stream",
  "include_window_info": true,
  "storage_backend": "redis",
  "max_windows": 5000,
  "execution": {
    "timeout": 120
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 会话窗口（告警会话分组）

```json
{
  "name": "session_window_alert",
  "description": "按告警会话分组，5分钟无活动则关闭会话",
  "enabled": true,
  "node_type": "window",
  "window_type": "session",
  "session": {
    "gap": 300,
    "max_duration": 7200
  },
  "window_key": {
    "fields": [
      "event.biz_id",
      "event.strategy_id",
      "event.dimensions.host"
    ],
    "separator": "|"
  },
  "time_field": "event.time",
  "use_processing_time": false,
  "trigger": {
    "trigger_type": "time",
    "time_interval": 30,
    "early_trigger_enabled": false
  },
  "late_data": {
    "allowed_lateness": 120,
    "late_data_action": "side_output",
    "side_output_field": "_late_alerts"
  },
  "output_mode": "on_close",
  "include_window_info": true,
  "window_start_field": "session_start",
  "window_end_field": "session_end",
  "storage_backend": "redis",
  "max_windows": 10000,
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
    "timeout": 180
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **周期统计**：每5分钟统计一次告警数量
2. **趋势分析**：滑动窗口计算指标趋势
3. **会话分组**：将连续告警归为同一会话
4. **数据缓冲**：缓冲数据后批量处理
5. **实时聚合**：实时聚合窗口内的数据
6. **延迟处理**：等待数据完整后处理
7. **数据对齐**：将不同来源的数据对齐到相同窗口

## 注意事项

1. **窗口类型选择**：
   - 滚动窗口最简单，无重叠
   - 滑动窗口适合平滑统计
   - 会话窗口适合按活动分组

2. **窗口大小**：
   - 窗口过大会增加延迟和内存
   - 窗口过小可能导致统计不准
   - 根据业务需求选择合适大小

3. **滑动间隔**：
   - 滑动窗口的slide应小于size
   - 间隔越小输出越频繁
   - 注意计算资源消耗

4. **时间字段**：
   - 优先使用事件时间（event time）
   - 处理时间（processing time）可能不准确
   - 确保时间字段格式正确

5. **迟到数据**：
   - 配置合理的 `allowed_lateness`
   - 迟到数据可以更新窗口或侧输出
   - 注意迟到数据对结果的影响

6. **存储选择**：
   - Redis支持分布式窗口
   - Memory适合单实例
   - 注意窗口状态的大小

7. **最大窗口数**：
   - `max_windows` 限制并行窗口
   - 超过限制会丢弃最旧窗口
   - 根据内存情况调整

8. **与聚合节点配合**：
   - 窗口节点常与Aggregate配合使用
   - 窗口提供分组，聚合提供计算

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：过滤后再分窗口
  - Transform（转换节点）：转换后分窗口

- **下游节点**：
  - Aggregate（聚合节点）：窗口内聚合
  - Router（路由节点）：基于窗口路由
  - Storage（存储节点）：存储窗口结果

### 典型组合模式

1. **Filter → Window → Aggregate**
   - 过滤 → 分窗口 → 聚合

2. **Window → Aggregate → Storage**
   - 分窗口 → 聚合 → 存储

3. **Transform → Window → Router**
   - 转换 → 分窗口 → 路由

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
