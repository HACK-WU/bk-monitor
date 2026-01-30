# Dedupe Node Configuration (去重节点配置)

## 节点类型
- **NodeType**: `dedupe`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 基于去重键去除重复事件，防止重复告警

## 配置 Schema

### DedupeNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class DedupeStrategy(str, Enum):
    """去重策略"""
    FIRST = "first"       # 保留第一条
    LAST = "last"         # 保留最后一条
    MERGE = "merge"       # 合并所有重复项
    COUNT = "count"       # 计数并保留最后一条


class DedupeScope(str, Enum):
    """去重范围"""
    GLOBAL = "global"     # 全局去重
    WINDOW = "window"     # 时间窗口内去重
    SESSION = "session"   # 会话内去重


class DedupeKeyConfigSerializer(serializers.Serializer):
    """去重键配置"""
    fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="用于生成去重键的字段列表，支持嵌套路径如 event.dimensions.host"
    )
    separator = serializers.CharField(
        default="|",
        help_text="字段值之间的分隔符"
    )
    hash_key = serializers.BooleanField(
        default=True,
        help_text="是否对生成的键进行哈希处理"
    )
    ignore_case = serializers.BooleanField(
        default=False,
        help_text="字符串字段是否忽略大小写"
    )


class DedupeWindowConfigSerializer(serializers.Serializer):
    """去重时间窗口配置"""
    duration = serializers.IntegerField(
        min_value=1,
        help_text="时间窗口长度（秒）"
    )
    slide_interval = serializers.IntegerField(
        default=None,
        required=False,
        allow_null=True,
        help_text="滑动间隔（秒），不设置则为固定窗口"
    )


class DedupeMergeConfigSerializer(serializers.Serializer):
    """合并策略配置（strategy=merge时使用）"""
    count_field = serializers.CharField(
        default="dedupe_count",
        help_text="存储重复计数的目标字段"
    )
    first_time_field = serializers.CharField(
        default="first_occurrence_time",
        help_text="存储首次出现时间的字段"
    )
    last_time_field = serializers.CharField(
        default="last_occurrence_time",
        help_text="存储最后出现时间的字段"
    )
    merge_fields = serializers.DictField(
        default=dict,
        required=False,
        help_text="自定义字段合并规则，如 {'values': 'append', 'severity': 'max'}"
    )


class DedupeNodeConfigSerializer(BaseNodeConfigSerializer):
    """去重节点配置"""
    node_type = serializers.CharField(default="dedupe", read_only=True)
    
    # 去重键配置
    dedupe_key = DedupeKeyConfigSerializer(help_text="去重键配置")
    
    # 去重策略
    strategy = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in DedupeStrategy],
        default="first",
        help_text="去重策略：first(保留首条)/last(保留末条)/merge(合并)/count(计数)"
    )
    
    # 去重范围
    scope = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in DedupeScope],
        default="window",
        help_text="去重范围：global(全局)/window(时间窗口)/session(会话)"
    )
    
    # 时间窗口配置
    window = DedupeWindowConfigSerializer(
        required=False,
        allow_null=True,
        help_text="时间窗口配置（scope=window时必填）"
    )
    
    # 合并配置
    merge_config = DedupeMergeConfigSerializer(
        required=False,
        allow_null=True,
        help_text="合并策略配置（strategy=merge时使用）"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="去重状态存储后端"
    )
    
    # 缓存过期
    cache_ttl = serializers.IntegerField(
        default=3600,
        min_value=60,
        help_text="去重缓存过期时间（秒）"
    )
    
    # 输出控制
    output_duplicates = serializers.BooleanField(
        default=False,
        help_text="是否输出被去重的事件（标记为duplicate=true）"
    )
    
    def validate(self, attrs):
        if attrs.get('scope') == 'window' and not attrs.get('window'):
            raise serializers.ValidationError("scope=window时必须配置window参数")
        if attrs.get('strategy') == 'merge' and not attrs.get('merge_config'):
            attrs['merge_config'] = {}  # 使用默认合并配置
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "dedupe" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `dedupe_key` | object | 是 | - | 去重键配置 |
| `strategy` | string | 否 | "first" | 去重策略 |
| `scope` | string | 否 | "window" | 去重范围 |
| `window` | object | 否 | null | 时间窗口配置 |
| `merge_config` | object | 否 | null | 合并策略配置 |
| `storage_backend` | string | 否 | "redis" | 存储后端 |
| `cache_ttl` | integer | 否 | 3600 | 缓存过期时间 |
| `output_duplicates` | boolean | 否 | false | 是否输出重复事件 |

### 去重键配置 (DedupeKeyConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `fields` | array | 是 | - | 生成去重键的字段列表 |
| `separator` | string | 否 | "\|" | 字段值分隔符 |
| `hash_key` | boolean | 否 | true | 是否哈希处理 |
| `ignore_case` | boolean | 否 | false | 是否忽略大小写 |

### 时间窗口配置 (DedupeWindowConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `duration` | integer | 是 | - | 窗口长度（秒） |
| `slide_interval` | integer | 否 | null | 滑动间隔（秒） |

### 合并配置 (DedupeMergeConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `count_field` | string | 否 | "dedupe_count" | 重复计数字段 |
| `first_time_field` | string | 否 | "first_occurrence_time" | 首次出现时间字段 |
| `last_time_field` | string | 否 | "last_occurrence_time" | 最后出现时间字段 |
| `merge_fields` | object | 否 | {} | 自定义合并规则 |

### 去重策略说明

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `first` | 保留首次出现的事件，丢弃后续重复 | 只关心首次告警的场景 |
| `last` | 保留最后出现的事件，覆盖之前的 | 需要最新状态的场景 |
| `merge` | 合并所有重复事件的信息 | 需要统计重复次数的场景 |
| `count` | 计数并保留最后一条，添加count字段 | 简单计数场景 |

### 去重范围说明

| 范围 | 说明 | 存储要求 |
|------|------|----------|
| `global` | 全局范围去重，无时间限制 | 需要持久化存储 |
| `window` | 在指定时间窗口内去重 | 需要配置window参数 |
| `session` | 在当前处理会话内去重 | 仅内存存储 |

## JSON 配置示例

### 示例 1: 基于告警ID的简单去重

```json
{
  "name": "alert_dedupe",
  "description": "基于告警ID的5分钟窗口去重",
  "enabled": true,
  "node_type": "dedupe",
  "dedupe_key": {
    "fields": ["event.alert_id"],
    "hash_key": false
  },
  "strategy": "first",
  "scope": "window",
  "window": {
    "duration": 300
  },
  "storage_backend": "redis",
  "cache_ttl": 600,
  "output_duplicates": false,
  "execution": {
    "timeout": 5
  }
}
```

### 示例 2: 多维度去重与合并统计

```json
{
  "name": "multi_dimension_dedupe",
  "description": "基于主机IP+告警名称的多维度去重，合并统计重复次数",
  "enabled": true,
  "node_type": "dedupe",
  "dedupe_key": {
    "fields": [
      "event.ip",
      "event.alert_name",
      "event.strategy_id"
    ],
    "separator": "::",
    "hash_key": true,
    "ignore_case": true
  },
  "strategy": "merge",
  "scope": "window",
  "window": {
    "duration": 600,
    "slide_interval": 60
  },
  "merge_config": {
    "count_field": "occurrence_count",
    "first_time_field": "first_alert_time",
    "last_time_field": "last_alert_time",
    "merge_fields": {
      "severity": "max",
      "affected_hosts": "append"
    }
  },
  "storage_backend": "redis",
  "cache_ttl": 1800,
  "output_duplicates": true,
  "execution": {
    "timeout": 10,
    "retry_enabled": true,
    "retry_max_attempts": 2
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 全局去重（持久化场景）

```json
{
  "name": "global_dedupe",
  "description": "全局级别去重，用于防止重复工单创建",
  "enabled": true,
  "node_type": "dedupe",
  "dedupe_key": {
    "fields": [
      "event.biz_id",
      "event.strategy_id",
      "event.dimensions.host",
      "event.dimensions.service"
    ],
    "separator": "|",
    "hash_key": true
  },
  "strategy": "count",
  "scope": "global",
  "storage_backend": "redis",
  "cache_ttl": 86400,
  "output_duplicates": true,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.status",
        "operator": "eq",
        "value": "RECOVERED"
      },
      {
        "field": "event.is_ack",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "skip",
    "log_error": true,
    "fallback_action": "pass_through"
  }
}
```

## 使用场景

1. **告警风暴抑制**：同一告警短时间内大量产生时，只保留第一条或合并统计
2. **重复工单防护**：防止同一问题创建多个重复工单
3. **日志去重**：对重复的日志告警进行去重，减少存储和处理压力
4. **状态更新合并**：将同一资源的多次状态更新合并为一条
5. **通知去重**：防止对同一问题发送重复通知
6. **指标聚合**：对相同维度的指标事件进行聚合统计
7. **事件降噪**：减少下游系统的处理负载

## 注意事项

1. **去重键选择**：
   - 选择能唯一标识事件的字段组合
   - 避免选择可能变化的字段（如时间戳）
   - 字段过多会降低去重效果

2. **时间窗口设置**：
   - 窗口过短可能导致去重效果不佳
   - 窗口过长会占用更多内存/Redis存储
   - 滑动窗口适合连续监控场景

3. **存储后端选择**：
   - `redis`：适合分布式部署，支持持久化
   - `memory`：适合单实例，性能更高但重启后丢失

4. **合并策略**：
   - `max`：取最大值（适合severity等）
   - `min`：取最小值
   - `append`：追加到列表
   - `sum`：求和

5. **性能考虑**：
   - 哈希键可减少存储空间
   - 合理设置cache_ttl避免内存溢出
   - 高并发场景建议使用Redis

6. **错误处理**：
   - 建议配置`on_error: continue`避免影响告警流程
   - `output_duplicates=true`时可追踪被去重的事件

7. **与其他节点配合**：
   - 通常放在Filter节点之后，减少处理量
   - 可与Converge节点配合使用，实现多级告警收敛

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤无效事件再去重
  - Transform（转换节点）：标准化字段后再生成去重键
  - Enrichment（丰富化节点）：补充维度信息后再去重

- **下游节点**：
  - Converge（收敛节点）：去重后进一步收敛
  - Router（路由节点）：基于去重结果路由
  - Notification（通知节点）：对去重后的告警发送通知

### 典型组合模式

1. **Filter → Dedupe → Converge → Notification**
   - 过滤 → 去重 → 收敛 → 通知

2. **Transform → Dedupe → Router → [分支处理]**
   - 转换 → 去重 → 路由 → 不同处理分支

3. **Enrichment → Dedupe → Severity → Action**
   - 丰富 → 去重 → 级别调整 → 自动化处理

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
