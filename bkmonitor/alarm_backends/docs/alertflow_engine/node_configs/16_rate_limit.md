# RateLimit Node Configuration (限流节点配置)

## 节点类型
- **NodeType**: `rate_limit`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 限制事件处理速率，防止系统过载，支持多种限流算法

## 配置 Schema

### RateLimitNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class RateLimitAlgorithm(str, Enum):
    """限流算法"""
    TOKEN_BUCKET = "token_bucket"       # 令牌桶
    SLIDING_WINDOW = "sliding_window"   # 滑动窗口
    FIXED_WINDOW = "fixed_window"       # 固定窗口
    LEAKY_BUCKET = "leaky_bucket"       # 漏桶


class RateLimitAction(str, Enum):
    """限流触发动作"""
    DROP = "drop"           # 丢弃
    DELAY = "delay"         # 延迟处理
    QUEUE = "queue"         # 放入队列
    SAMPLE = "sample"       # 采样通过
    REJECT = "reject"       # 拒绝并返回错误


class RateLimitScope(str, Enum):
    """限流范围"""
    GLOBAL = "global"       # 全局限流
    PER_KEY = "per_key"     # 按键限流
    PER_BIZ = "per_biz"     # 按业务限流
    PER_STRATEGY = "per_strategy"  # 按策略限流


class TokenBucketConfigSerializer(serializers.Serializer):
    """令牌桶配置"""
    capacity = serializers.IntegerField(
        min_value=1,
        help_text="令牌桶容量"
    )
    refill_rate = serializers.IntegerField(
        min_value=1,
        help_text="令牌填充速率（个/秒）"
    )
    initial_tokens = serializers.IntegerField(
        default=None,
        required=False,
        allow_null=True,
        help_text="初始令牌数（默认等于容量）"
    )


class SlidingWindowConfigSerializer(serializers.Serializer):
    """滑动窗口配置"""
    window_size = serializers.IntegerField(
        min_value=1,
        help_text="窗口大小（秒）"
    )
    max_requests = serializers.IntegerField(
        min_value=1,
        help_text="窗口内最大请求数"
    )
    precision = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="精度（秒），影响内存占用"
    )


class FixedWindowConfigSerializer(serializers.Serializer):
    """固定窗口配置"""
    window_size = serializers.IntegerField(
        min_value=1,
        help_text="窗口大小（秒）"
    )
    max_requests = serializers.IntegerField(
        min_value=1,
        help_text="窗口内最大请求数"
    )


class LeakyBucketConfigSerializer(serializers.Serializer):
    """漏桶配置"""
    capacity = serializers.IntegerField(
        min_value=1,
        help_text="桶容量"
    )
    leak_rate = serializers.IntegerField(
        min_value=1,
        help_text="漏出速率（个/秒）"
    )


class RateLimitKeyConfigSerializer(serializers.Serializer):
    """限流键配置"""
    fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="限流键字段列表"
    )
    separator = serializers.CharField(
        default=":",
        help_text="字段分隔符"
    )
    hash_key = serializers.BooleanField(
        default=True,
        help_text="是否哈希限流键"
    )


class RateLimitNodeConfigSerializer(BaseNodeConfigSerializer):
    """限流节点配置"""
    node_type = serializers.CharField(default="rate_limit", read_only=True)
    
    # 限流算法
    algorithm = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RateLimitAlgorithm],
        default="token_bucket",
        help_text="限流算法"
    )
    
    # 限流范围
    scope = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RateLimitScope],
        default="global",
        help_text="限流范围"
    )
    
    # 限流键配置（scope=per_key时使用）
    rate_limit_key = RateLimitKeyConfigSerializer(
        required=False,
        allow_null=True,
        help_text="限流键配置"
    )
    
    # 算法配置
    token_bucket = TokenBucketConfigSerializer(
        required=False,
        allow_null=True,
        help_text="令牌桶配置"
    )
    sliding_window = SlidingWindowConfigSerializer(
        required=False,
        allow_null=True,
        help_text="滑动窗口配置"
    )
    fixed_window = FixedWindowConfigSerializer(
        required=False,
        allow_null=True,
        help_text="固定窗口配置"
    )
    leaky_bucket = LeakyBucketConfigSerializer(
        required=False,
        allow_null=True,
        help_text="漏桶配置"
    )
    
    # 触发动作
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RateLimitAction],
        default="drop",
        help_text="限流触发动作"
    )
    
    # 延迟配置（action=delay时使用）
    delay_max_seconds = serializers.IntegerField(
        default=60,
        help_text="最大延迟时间（秒）"
    )
    
    # 队列配置（action=queue时使用）
    queue_size = serializers.IntegerField(
        default=1000,
        help_text="队列大小"
    )
    queue_timeout = serializers.IntegerField(
        default=300,
        help_text="队列等待超时（秒）"
    )
    
    # 采样配置（action=sample时使用）
    sample_rate = serializers.FloatField(
        default=0.1,
        min_value=0.0,
        max_value=1.0,
        help_text="采样率（0-1）"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="限流状态存储后端"
    )
    
    # 限流标记
    mark_limited = serializers.BooleanField(
        default=True,
        help_text="是否在事件中标记限流状态"
    )
    mark_field = serializers.CharField(
        default="_rate_limited",
        help_text="限流标记字段名"
    )
    
    # 限流日志
    log_limited_events = serializers.BooleanField(
        default=True,
        help_text="是否记录被限流的事件"
    )
    
    def validate(self, attrs):
        algorithm = attrs.get('algorithm')
        if algorithm == 'token_bucket' and not attrs.get('token_bucket'):
            raise serializers.ValidationError(
                "algorithm=token_bucket时必须配置token_bucket参数"
            )
        if algorithm == 'sliding_window' and not attrs.get('sliding_window'):
            raise serializers.ValidationError(
                "algorithm=sliding_window时必须配置sliding_window参数"
            )
        if algorithm == 'fixed_window' and not attrs.get('fixed_window'):
            raise serializers.ValidationError(
                "algorithm=fixed_window时必须配置fixed_window参数"
            )
        if algorithm == 'leaky_bucket' and not attrs.get('leaky_bucket'):
            raise serializers.ValidationError(
                "algorithm=leaky_bucket时必须配置leaky_bucket参数"
            )
        
        scope = attrs.get('scope')
        if scope == 'per_key' and not attrs.get('rate_limit_key'):
            raise serializers.ValidationError(
                "scope=per_key时必须配置rate_limit_key参数"
            )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "rate_limit" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `algorithm` | string | 否 | "token_bucket" | 限流算法 |
| `scope` | string | 否 | "global" | 限流范围 |
| `action` | string | 否 | "drop" | 限流触发动作 |
| `storage_backend` | string | 否 | "redis" | 存储后端 |
| `mark_limited` | boolean | 否 | true | 标记限流状态 |
| `log_limited_events` | boolean | 否 | true | 记录限流日志 |

### 令牌桶配置 (TokenBucketConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `capacity` | integer | 是 | - | 令牌桶容量 |
| `refill_rate` | integer | 是 | - | 填充速率（个/秒） |
| `initial_tokens` | integer | 否 | capacity | 初始令牌数 |

### 滑动窗口配置 (SlidingWindowConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `window_size` | integer | 是 | - | 窗口大小（秒） |
| `max_requests` | integer | 是 | - | 最大请求数 |
| `precision` | integer | 否 | 1 | 精度（秒） |

### 固定窗口配置 (FixedWindowConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `window_size` | integer | 是 | - | 窗口大小（秒） |
| `max_requests` | integer | 是 | - | 最大请求数 |

### 漏桶配置 (LeakyBucketConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `capacity` | integer | 是 | - | 桶容量 |
| `leak_rate` | integer | 是 | - | 漏出速率（个/秒） |

### 限流算法说明

| 算法 | 说明 | 特点 |
|------|------|------|
| `token_bucket` | 令牌桶 | 允许突发流量，平滑限流 |
| `sliding_window` | 滑动窗口 | 精确计数，无边界问题 |
| `fixed_window` | 固定窗口 | 简单高效，有边界突发 |
| `leaky_bucket` | 漏桶 | 平滑输出，严格限速 |

### 限流范围说明

| 范围 | 说明 | 限流粒度 |
|------|------|----------|
| `global` | 全局限流 | 所有事件共享配额 |
| `per_key` | 按键限流 | 按配置字段独立限流 |
| `per_biz` | 按业务限流 | 按业务ID独立限流 |
| `per_strategy` | 按策略限流 | 按策略ID独立限流 |

### 限流动作说明

| 动作 | 说明 | 适用场景 |
|------|------|----------|
| `drop` | 丢弃 | 非关键事件 |
| `delay` | 延迟 | 可延迟处理的事件 |
| `queue` | 队列 | 需要保证最终处理 |
| `sample` | 采样 | 数据量大但可抽样 |
| `reject` | 拒绝 | 需要返回错误信息 |

## JSON 配置示例

### 示例 1: 令牌桶全局限流

```json
{
  "name": "global_rate_limit",
  "description": "全局限流，每秒最多处理100条告警",
  "enabled": true,
  "node_type": "rate_limit",
  "algorithm": "token_bucket",
  "scope": "global",
  "token_bucket": {
    "capacity": 200,
    "refill_rate": 100,
    "initial_tokens": 100
  },
  "action": "drop",
  "storage_backend": "redis",
  "mark_limited": true,
  "mark_field": "_rate_limited",
  "log_limited_events": true,
  "execution": {
    "timeout": 5
  }
}
```

### 示例 2: 按业务滑动窗口限流

```json
{
  "name": "per_biz_rate_limit",
  "description": "按业务限流，每业务每分钟最多1000条告警",
  "enabled": true,
  "node_type": "rate_limit",
  "algorithm": "sliding_window",
  "scope": "per_biz",
  "sliding_window": {
    "window_size": 60,
    "max_requests": 1000,
    "precision": 1
  },
  "action": "queue",
  "queue_size": 5000,
  "queue_timeout": 300,
  "storage_backend": "redis",
  "mark_limited": true,
  "log_limited_events": true,
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 多维度限流与采样

```json
{
  "name": "multi_dimension_rate_limit",
  "description": "按策略+主机维度限流，超限后采样通过",
  "enabled": true,
  "node_type": "rate_limit",
  "algorithm": "fixed_window",
  "scope": "per_key",
  "rate_limit_key": {
    "fields": ["event.strategy_id", "event.dimensions.host"],
    "separator": ":",
    "hash_key": true
  },
  "fixed_window": {
    "window_size": 60,
    "max_requests": 100
  },
  "action": "sample",
  "sample_rate": 0.1,
  "storage_backend": "redis",
  "mark_limited": true,
  "mark_field": "_sampled",
  "log_limited_events": true,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.severity",
        "operator": "eq",
        "value": 1
      },
      {
        "field": "event.skip_rate_limit",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 5
  },
  "error_handling": {
    "on_error": "pass",
    "log_error": true
  }
}
```

## 使用场景

1. **全局流量控制**：限制整体告警处理速率，保护下游系统
2. **业务配额管理**：不同业务分配不同的告警处理配额
3. **告警风暴防护**：突发大量告警时限流保护
4. **资源隔离**：防止单一策略或主机耗尽系统资源
5. **平滑流量**：使用漏桶算法平滑输出到下游
6. **采样分析**：对超量告警进行采样保留
7. **队列削峰**：高峰期排队等待，低峰期消化积压

## 注意事项

1. **算法选择**：
   - 令牌桶适合允许突发流量的场景
   - 滑动窗口计数精确，内存占用较大
   - 固定窗口简单但有边界突发问题
   - 漏桶输出最平滑但响应延迟

2. **参数配置**：
   - `capacity` 决定突发处理能力
   - `refill_rate/leak_rate` 决定长期处理速率
   - `window_size` 影响限流粒度

3. **动作选择**：
   - `drop` 最简单但会丢失数据
   - `delay` 需要考虑延迟对业务影响
   - `queue` 需要合理设置队列大小
   - `sample` 适合统计分析场景

4. **存储选择**：
   - Redis支持分布式限流
   - Memory仅单实例有效
   - 高并发场景建议使用Redis Lua脚本

5. **限流键设计**：
   - 粒度过细会产生大量限流状态
   - 粒度过粗可能无法有效隔离
   - 建议使用哈希减少存储

6. **跳过条件**：
   - 致命告警通常应跳过限流
   - 可配置 `skip_condition` 实现

7. **监控观察**：
   - 关注被限流的事件数量
   - 观察队列长度和延迟
   - 及时调整限流参数

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再限流
  - Router（路由节点）：路由到不同限流策略

- **下游节点**：
  - Converge（收敛节点）：限流后收敛
  - Notification（通知节点）：限流后通知
  - Storage（存储节点）：存储限流后的事件

### 典型组合模式

1. **RateLimit → Converge → Notification**
   - 限流 → 收敛 → 通知

2. **Filter → RateLimit → [多分支]**
   - 过滤 → 限流 → 分支处理

3. **RateLimit[queue] → Notification**
   - 限流排队 → 通知

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
