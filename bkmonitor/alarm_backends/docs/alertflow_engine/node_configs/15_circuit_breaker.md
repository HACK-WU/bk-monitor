# CircuitBreaker Node Configuration (熔断节点配置)

## 节点类型
- **NodeType**: `circuit_breaker`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 当下游节点或服务故障时自动熔断，保护系统稳定性

## 配置 Schema

### CircuitBreakerNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class CircuitState(str, Enum):
    """熔断状态"""
    CLOSED = "closed"           # 关闭（正常）
    OPEN = "open"               # 打开（熔断中）
    HALF_OPEN = "half_open"     # 半开（恢复探测）


class CircuitBreakerStrategy(str, Enum):
    """熔断策略"""
    ERROR_COUNT = "error_count"       # 错误计数
    ERROR_RATE = "error_rate"         # 错误率
    SLOW_CALL_RATE = "slow_call_rate" # 慢调用率
    CONSECUTIVE = "consecutive"       # 连续失败


class FallbackAction(str, Enum):
    """降级动作"""
    DROP = "drop"               # 丢弃
    PASS = "pass"               # 直接通过
    CACHE = "cache"             # 使用缓存
    FALLBACK_NODE = "fallback_node"  # 降级节点
    QUEUE = "queue"             # 队列等待


class CircuitBreakerThresholdSerializer(serializers.Serializer):
    """熔断阈值配置"""
    # 错误计数阈值
    error_count_threshold = serializers.IntegerField(
        default=5,
        min_value=1,
        help_text="触发熔断的错误次数阈值"
    )
    
    # 错误率阈值
    error_rate_threshold = serializers.FloatField(
        default=0.5,
        min_value=0.0,
        max_value=1.0,
        help_text="触发熔断的错误率阈值（0-1）"
    )
    
    # 慢调用阈值
    slow_call_duration = serializers.IntegerField(
        default=5000,
        help_text="判定为慢调用的耗时阈值（毫秒）"
    )
    slow_call_rate_threshold = serializers.FloatField(
        default=0.5,
        min_value=0.0,
        max_value=1.0,
        help_text="触发熔断的慢调用率阈值（0-1）"
    )
    
    # 最小请求数
    minimum_requests = serializers.IntegerField(
        default=10,
        min_value=1,
        help_text="计算错误率的最小请求数"
    )


class CircuitBreakerTimingSerializer(serializers.Serializer):
    """熔断时间配置"""
    # 统计窗口
    sliding_window_size = serializers.IntegerField(
        default=10,
        min_value=1,
        help_text="滑动窗口大小（请求数或秒数）"
    )
    sliding_window_type = serializers.ChoiceField(
        choices=[("count", "请求数"), ("time", "时间")],
        default="count",
        help_text="滑动窗口类型"
    )
    
    # 熔断时长
    open_duration = serializers.IntegerField(
        default=60,
        min_value=1,
        help_text="熔断持续时间（秒）"
    )
    
    # 半开状态配置
    half_open_requests = serializers.IntegerField(
        default=3,
        min_value=1,
        help_text="半开状态允许的探测请求数"
    )
    half_open_success_threshold = serializers.IntegerField(
        default=2,
        min_value=1,
        help_text="半开状态恢复所需的成功请求数"
    )


class FallbackConfigSerializer(serializers.Serializer):
    """降级配置"""
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in FallbackAction],
        default="drop",
        help_text="降级动作"
    )
    fallback_node_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="降级节点ID（action=fallback_node时使用）"
    )
    cache_key_template = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="缓存键模板（action=cache时使用）"
    )
    cache_ttl = serializers.IntegerField(
        default=300,
        help_text="缓存TTL（秒）"
    )
    queue_timeout = serializers.IntegerField(
        default=30,
        help_text="队列等待超时（秒，action=queue时使用）"
    )


class CircuitBreakerNodeConfigSerializer(BaseNodeConfigSerializer):
    """熔断节点配置"""
    node_type = serializers.CharField(default="circuit_breaker", read_only=True)
    
    # 熔断策略
    strategy = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in CircuitBreakerStrategy],
        default="error_count",
        help_text="熔断策略"
    )
    
    # 监控目标
    target_node = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="被保护的目标节点ID"
    )
    target_service = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="被保护的目标服务名"
    )
    
    # 熔断阈值
    threshold = CircuitBreakerThresholdSerializer(help_text="熔断阈值配置")
    
    # 时间配置
    timing = CircuitBreakerTimingSerializer(help_text="熔断时间配置")
    
    # 降级配置
    fallback = FallbackConfigSerializer(help_text="降级配置")
    
    # 熔断键（用于细粒度熔断）
    circuit_key_fields = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="熔断键字段列表（用于按维度独立熔断）"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="熔断状态存储后端"
    )
    
    # 事件通知
    notify_on_state_change = serializers.BooleanField(
        default=True,
        help_text="状态变化时是否发送通知"
    )
    notify_channels = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知渠道列表"
    )
    
    def validate(self, attrs):
        if not attrs.get('target_node') and not attrs.get('target_service'):
            raise serializers.ValidationError(
                "必须指定target_node或target_service"
            )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "circuit_breaker" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `strategy` | string | 否 | "error_count" | 熔断策略 |
| `target_node` | string | 否 | null | 目标节点ID |
| `target_service` | string | 否 | null | 目标服务名 |
| `threshold` | object | 是 | - | 熔断阈值配置 |
| `timing` | object | 是 | - | 时间配置 |
| `fallback` | object | 是 | - | 降级配置 |
| `circuit_key_fields` | array | 否 | [] | 熔断键字段 |
| `storage_backend` | string | 否 | "redis" | 存储后端 |

### 熔断阈值配置 (CircuitBreakerThreshold)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `error_count_threshold` | integer | 否 | 5 | 错误次数阈值 |
| `error_rate_threshold` | float | 否 | 0.5 | 错误率阈值 |
| `slow_call_duration` | integer | 否 | 5000 | 慢调用判定阈值（ms） |
| `slow_call_rate_threshold` | float | 否 | 0.5 | 慢调用率阈值 |
| `minimum_requests` | integer | 否 | 10 | 最小请求数 |

### 熔断时间配置 (CircuitBreakerTiming)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `sliding_window_size` | integer | 否 | 10 | 滑动窗口大小 |
| `sliding_window_type` | string | 否 | "count" | 窗口类型 |
| `open_duration` | integer | 否 | 60 | 熔断持续时间 |
| `half_open_requests` | integer | 否 | 3 | 半开状态请求数 |
| `half_open_success_threshold` | integer | 否 | 2 | 半开恢复阈值 |

### 降级配置 (FallbackConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `action` | string | 否 | "drop" | 降级动作 |
| `fallback_node_id` | string | 否 | null | 降级节点ID |
| `cache_key_template` | string | 否 | null | 缓存键模板 |
| `cache_ttl` | integer | 否 | 300 | 缓存TTL |
| `queue_timeout` | integer | 否 | 30 | 队列等待超时 |

### 熔断策略说明

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `error_count` | 错误次数达到阈值触发 | 简单场景 |
| `error_rate` | 错误率达到阈值触发 | 高流量场景 |
| `slow_call_rate` | 慢调用率达到阈值触发 | 性能敏感场景 |
| `consecutive` | 连续失败触发 | 严格保护场景 |

### 降级动作说明

| 动作 | 说明 | 使用场景 |
|------|------|----------|
| `drop` | 直接丢弃请求 | 非关键业务 |
| `pass` | 跳过熔断保护 | 紧急放行 |
| `cache` | 返回缓存结果 | 数据查询场景 |
| `fallback_node` | 走降级节点 | 有备用方案 |
| `queue` | 排队等待 | 可延迟处理 |

## JSON 配置示例

### 示例 1: 基于错误计数的熔断

```json
{
  "name": "notification_circuit_breaker",
  "description": "通知服务熔断保护，5次错误后熔断",
  "enabled": true,
  "node_type": "circuit_breaker",
  "strategy": "error_count",
  "target_node": "notification_node",
  "threshold": {
    "error_count_threshold": 5,
    "minimum_requests": 3
  },
  "timing": {
    "sliding_window_size": 10,
    "sliding_window_type": "count",
    "open_duration": 60,
    "half_open_requests": 3,
    "half_open_success_threshold": 2
  },
  "fallback": {
    "action": "queue",
    "queue_timeout": 60
  },
  "storage_backend": "redis",
  "notify_on_state_change": true,
  "notify_channels": ["weixin"],
  "execution": {
    "timeout": 5
  }
}
```

### 示例 2: 基于错误率的细粒度熔断

```json
{
  "name": "api_circuit_breaker",
  "description": "外部API熔断，按业务ID独立熔断",
  "enabled": true,
  "node_type": "circuit_breaker",
  "strategy": "error_rate",
  "target_service": "external_api",
  "threshold": {
    "error_rate_threshold": 0.3,
    "minimum_requests": 20
  },
  "timing": {
    "sliding_window_size": 60,
    "sliding_window_type": "time",
    "open_duration": 120,
    "half_open_requests": 5,
    "half_open_success_threshold": 3
  },
  "fallback": {
    "action": "cache",
    "cache_key_template": "api_fallback:{{ biz_id }}:{{ api_name }}",
    "cache_ttl": 600
  },
  "circuit_key_fields": ["event.biz_id", "event.api_name"],
  "storage_backend": "redis",
  "notify_on_state_change": true,
  "notify_channels": ["weixin", "mail"],
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 慢调用熔断与降级节点

```json
{
  "name": "slow_call_circuit_breaker",
  "description": "慢调用熔断，超时请求走降级节点",
  "enabled": true,
  "node_type": "circuit_breaker",
  "strategy": "slow_call_rate",
  "target_node": "enrichment_node",
  "threshold": {
    "slow_call_duration": 3000,
    "slow_call_rate_threshold": 0.4,
    "minimum_requests": 10
  },
  "timing": {
    "sliding_window_size": 30,
    "sliding_window_type": "time",
    "open_duration": 90,
    "half_open_requests": 5,
    "half_open_success_threshold": 4
  },
  "fallback": {
    "action": "fallback_node",
    "fallback_node_id": "simple_enrichment_node"
  },
  "circuit_key_fields": ["event.data_source"],
  "storage_backend": "redis",
  "notify_on_state_change": true,
  "notify_channels": ["wecom_bot"],
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.priority",
        "operator": "eq",
        "value": "critical"
      }
    ]
  },
  "execution": {
    "timeout": 5
  },
  "error_handling": {
    "on_error": "fallback",
    "log_error": true
  }
}
```

## 使用场景

1. **通知服务保护**：通知服务故障时自动熔断，防止告警积压
2. **外部API防护**：第三方API不可用时快速失败
3. **数据库保护**：数据库慢查询过多时熔断
4. **微服务调用**：上游服务故障时熔断，防止级联失败
5. **资源限流**：通过熔断实现过载保护
6. **灰度发布保护**：新版本错误率过高时自动熔断
7. **多租户隔离**：按租户独立熔断，避免互相影响

## 注意事项

1. **阈值设置**：
   - 阈值过低可能导致频繁熔断
   - 阈值过高可能无法及时保护
   - `minimum_requests` 避免少量请求触发熔断

2. **时间窗口**：
   - `count` 类型按请求数统计，适合稳定流量
   - `time` 类型按时间统计，适合流量波动场景
   - `open_duration` 不宜过短，避免频繁状态切换

3. **半开状态**：
   - 半开状态允许少量请求探测恢复
   - `half_open_success_threshold` 决定恢复条件
   - 探测失败会重新进入熔断状态

4. **降级策略**：
   - `drop` 适合非关键业务
   - `cache` 需要提前预热缓存
   - `fallback_node` 需要配置可用的降级节点

5. **细粒度熔断**：
   - `circuit_key_fields` 可实现按维度独立熔断
   - 维度过细可能导致状态存储过多
   - 建议只选择关键维度字段

6. **状态存储**：
   - Redis支持分布式部署
   - Memory适合单实例，重启后状态丢失
   - 高并发场景建议使用Redis

7. **监控告警**：
   - 建议开启 `notify_on_state_change`
   - 熔断状态变化应及时通知运维
   - 可配合监控指标观察熔断情况

## 相关节点

- **上游节点**：
  - Router（路由节点）：路由到熔断保护的节点
  - Filter（过滤节点）：过滤后再走熔断

- **下游节点**：
  - 被保护的目标节点（Notification、Action等）
  - 降级节点（当熔断触发时）

### 典型组合模式

1. **CircuitBreaker → Notification**
   - 熔断 → 通知节点

2. **Router → CircuitBreaker → [API_A | API_B]**
   - 路由 → 熔断 → 多个API

3. **CircuitBreaker[fallback] → FallbackNode**
   - 熔断降级 → 降级节点

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
