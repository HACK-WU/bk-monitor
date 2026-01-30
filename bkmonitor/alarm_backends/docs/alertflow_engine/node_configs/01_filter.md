# Filter Node Configuration (过滤节点配置)

## 节点类型
- **NodeType**: `filter`
- **分类**: DATA_PROCESSING (数据处理类)
- **功能**: 根据条件筛选事件，支持多种匹配模式

## 配置 Schema

### FilterNodeConfigSerializer

```python
from rest_framework import serializers


class MatchOperator(str, Enum):
    """匹配操作符"""
    EQ = "eq"           # 等于
    NE = "ne"           # 不等于
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    IN = "in"           # 在列表中
    NOT_IN = "not_in"   # 不在列表中
    CONTAINS = "contains"       # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    REGEX = "regex"     # 正则匹配
    EXISTS = "exists"   # 字段存在
    NOT_EXISTS = "not_exists"  # 字段不存在


class FilterConditionSerializer(serializers.Serializer):
    """单个过滤条件"""
    field = serializers.CharField(help_text="字段路径，支持嵌套")
    operator = serializers.ChoiceField(choices=[(e.value, e.name) for e in MatchOperator], help_text="匹配操作符")
    value = serializers.JSONField(default=None, required=False, help_text="匹配值")
    case_sensitive = serializers.BooleanField(default=True, help_text="是否区分大小写")


class FilterNodeConfigSerializer(BaseNodeConfigSerializer):
    """过滤节点配置"""
    node_type = serializers.CharField(default="filter", read_only=True)
    match_mode = serializers.ChoiceField(choices=[("all", "all"), ("any", "any")], default="all", help_text="匹配模式")
    conditions = FilterConditionSerializer(many=True, required=False, help_text="简单条件列表")
    condition_groups = ConditionGroupSerializer(required=False, allow_null=True, help_text="复杂条件组")
    invert = serializers.BooleanField(default=False, help_text="反转匹配结果")
    drop_on_match = serializers.BooleanField(default=True, help_text="匹配时丢弃")
```

## 配置字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "filter" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `match_mode` | string | 否 | "all" | 匹配模式：all(所有条件) / any(任一条件) |
| `conditions` | array | 否 | - | 简单条件列表 |
| `condition_groups` | object | 否 | null | 复杂条件组（与conditions二选一） |
| `invert` | boolean | 否 | false | 反转匹配结果 |
| `drop_on_match` | boolean | 否 | true | 匹配时丢弃事件 |

## JSON 配置示例

### 示例 1: 监控告警过滤

```json
{
  "name": "severity_filter",
  "description": "过滤低级别告警",
  "enabled": true,
  "node_type": "filter",
  "match_mode": "all",
  "conditions": [
    {
      "field": "event.severity",
      "operator": "gte",
      "value": 3
    },
    {
      "field": "event.status",
      "operator": "ne",
      "value": "resolved"
    }
  ],
  "execution": {
    "timeout": 10
  }
}
```

### 示例 2: 日志级别过滤（复杂条件组）

```json
{
  "name": "error_log_filter",
  "description": "只保留 ERROR 和 FATAL 级别日志",
  "node_type": "filter",
  "condition_groups": {
    "logic": "or",
    "conditions": [
      {
        "field": "log.level",
        "operator": "eq",
        "value": "ERROR"
      },
      {
        "field": "log.level",
        "operator": "eq",
        "value": "FATAL"
      }
    ]
  },
  "invert": false,
  "drop_on_match": true
}
```

### 示例 3: 正则匹配过滤

```json
{
  "name": "test_env_filter",
  "description": "过滤测试环境事件",
  "node_type": "filter",
  "match_mode": "any",
  "conditions": [
    {
      "field": "event.host",
      "operator": "regex",
      "value": "^test-.*",
      "case_sensitive": false
    },
    {
      "field": "event.tags.environment",
      "operator": "in",
      "value": ["test", "dev", "staging"]
    }
  ],
  "drop_on_match": true
}
```

## 使用场景

1. **告警级别过滤**：过滤低级别告警，只处理重要告警
2. **环境过滤**：区分生产/测试环境，不同环境不同处理策略
3. **状态过滤**：过滤已恢复的告警，避免重复处理
4. **白名单/黑名单**：基于IP、主机名等字段实现白名单或黑名单
5. **日志过滤**：根据日志级别、关键字过滤日志事件

## 注意事项

1. `conditions` 和 `condition_groups` 二选一，不能同时使用
2. `invert=true` 会反转最终匹配结果
3. `drop_on_match=true` 时匹配的事件会被丢弃，不再继续流转
4. 正则表达式匹配性能相对较低，谨慎使用
5. `case_sensitive` 仅对字符串类型字段有效
