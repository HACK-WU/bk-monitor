# Converge Node Configuration (收敛节点配置)

## 节点类型
- **NodeType**: `converge`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 对相似告警进行收敛，减少告警数量，支持多种收敛策略

## 配置 Schema

### ConvergeNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class ConvergeType(str, Enum):
    """收敛类型"""
    ACTION = "action"           # 处理动作收敛
    DEFENSE = "defense"         # 防御性收敛（告警风暴）
    BUSINESS = "business"       # 业务维度收敛
    COLLECT = "collect"         # 汇总收敛


class ConvergeFunc(str, Enum):
    """收敛函数"""
    SKIP_WHEN_SUCCESS = "skip_when_success"       # 成功时跳过
    SKIP_WHEN_PROCEED = "skip_when_proceed"       # 执行中跳过
    WAIT_WHEN_PROCEED = "wait_when_proceed"       # 执行中等待
    COLLECT = "collect"                           # 汇总收敛
    COLLECT_ALARM = "collect_alarm"               # 告警汇总收敛
    DEFENSE = "defense"                           # 防御收敛


class ConvergeDimensionSerializer(serializers.Serializer):
    """收敛维度配置"""
    fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="收敛维度字段列表"
    )
    hash_dimension = serializers.BooleanField(
        default=True,
        help_text="是否对维度值进行哈希"
    )


class ConvergeConditionSerializer(serializers.Serializer):
    """收敛条件配置"""
    field = serializers.CharField(help_text="条件字段")
    operator = serializers.ChoiceField(
        choices=[
            ("eq", "等于"),
            ("ne", "不等于"),
            ("in", "在列表中"),
            ("not_in", "不在列表中"),
            ("regex", "正则匹配"),
        ],
        help_text="条件操作符"
    )
    value = serializers.JSONField(help_text="条件值")


class ConvergeWindowSerializer(serializers.Serializer):
    """收敛时间窗口配置"""
    duration = serializers.IntegerField(
        min_value=1,
        help_text="收敛窗口时长（秒）"
    )
    count = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="窗口内触发收敛的最小数量"
    )
    slide_interval = serializers.IntegerField(
        default=None,
        required=False,
        allow_null=True,
        help_text="滑动窗口间隔（秒）"
    )


class ConvergeActionSerializer(serializers.Serializer):
    """收敛后的动作配置"""
    action_type = serializers.ChoiceField(
        choices=[
            ("drop", "丢弃"),
            ("pass", "通过"),
            ("aggregate", "聚合"),
            ("delay", "延迟"),
            ("notify", "通知"),
        ],
        help_text="收敛动作类型"
    )
    aggregate_fields = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="聚合字段（action_type=aggregate时使用）"
    )
    delay_seconds = serializers.IntegerField(
        default=0,
        required=False,
        help_text="延迟时间（action_type=delay时使用）"
    )
    notify_template = serializers.CharField(
        default=None,
        required=False,
        allow_null=True,
        help_text="通知模板（action_type=notify时使用）"
    )


class ConvergeNodeConfigSerializer(BaseNodeConfigSerializer):
    """收敛节点配置"""
    node_type = serializers.CharField(default="converge", read_only=True)
    
    # 收敛类型
    converge_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ConvergeType],
        default="action",
        help_text="收敛类型"
    )
    
    # 收敛函数
    converge_func = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ConvergeFunc],
        help_text="收敛函数"
    )
    
    # 收敛维度
    dimension = ConvergeDimensionSerializer(help_text="收敛维度配置")
    
    # 收敛条件
    conditions = ConvergeConditionSerializer(
        many=True,
        required=False,
        help_text="收敛条件列表"
    )
    
    # 时间窗口
    window = ConvergeWindowSerializer(help_text="收敛时间窗口")
    
    # 收敛动作
    converge_action = ConvergeActionSerializer(
        required=False,
        help_text="收敛后的动作配置"
    )
    
    # 是否需要确认
    need_biz_converge = serializers.BooleanField(
        default=True,
        help_text="是否需要业务收敛确认"
    )
    
    # 子收敛配置
    sub_converge_config = serializers.DictField(
        default=dict,
        required=False,
        help_text="子收敛配置（用于多级收敛）"
    )
    
    # 收敛实例ID生成
    converge_id_template = serializers.CharField(
        default="{{ biz_id }}_{{ strategy_id }}_{{ dimension_hash }}",
        help_text="收敛实例ID模板"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="收敛状态存储后端"
    )
    
    # 缓存过期
    cache_ttl = serializers.IntegerField(
        default=86400,
        help_text="收敛缓存过期时间（秒）"
    )
    
    def validate(self, attrs):
        converge_func = attrs.get('converge_func')
        converge_action = attrs.get('converge_action')
        
        if converge_func == 'collect' and not converge_action:
            attrs['converge_action'] = {'action_type': 'aggregate'}
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "converge" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `converge_type` | string | 否 | "action" | 收敛类型 |
| `converge_func` | string | 是 | - | 收敛函数 |
| `dimension` | object | 是 | - | 收敛维度配置 |
| `conditions` | array | 否 | [] | 收敛条件列表 |
| `window` | object | 是 | - | 时间窗口配置 |
| `converge_action` | object | 否 | null | 收敛动作配置 |
| `need_biz_converge` | boolean | 否 | true | 需要业务收敛确认 |
| `sub_converge_config` | object | 否 | {} | 子收敛配置 |
| `converge_id_template` | string | 否 | 见默认 | 收敛ID模板 |
| `storage_backend` | string | 否 | "redis" | 存储后端 |
| `cache_ttl` | integer | 否 | 86400 | 缓存过期时间 |

### 收敛维度配置 (ConvergeDimension)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `fields` | array | 是 | - | 维度字段列表 |
| `hash_dimension` | boolean | 否 | true | 是否哈希维度值 |

### 时间窗口配置 (ConvergeWindow)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `duration` | integer | 是 | - | 窗口时长（秒） |
| `count` | integer | 否 | 1 | 触发收敛的最小数量 |
| `slide_interval` | integer | 否 | null | 滑动间隔 |

### 收敛动作配置 (ConvergeAction)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `action_type` | string | 是 | - | 动作类型 |
| `aggregate_fields` | array | 否 | - | 聚合字段 |
| `delay_seconds` | integer | 否 | 0 | 延迟时间 |
| `notify_template` | string | 否 | null | 通知模板 |

### 收敛类型说明

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `action` | 处理动作收敛 | 通知、自愈等动作的收敛 |
| `defense` | 防御性收敛 | 告警风暴防护 |
| `business` | 业务维度收敛 | 按业务维度汇总告警 |
| `collect` | 汇总收敛 | 定时汇总收敛 |

### 收敛函数说明

| 函数 | 说明 | 行为 |
|------|------|------|
| `skip_when_success` | 成功时跳过 | 相同维度成功后，跳过后续告警 |
| `skip_when_proceed` | 执行中跳过 | 正在处理时，跳过新的告警 |
| `wait_when_proceed` | 执行中等待 | 正在处理时，等待处理完成 |
| `collect` | 汇总收敛 | 收集窗口内告警后统一处理 |
| `collect_alarm` | 告警汇总收敛 | 专门用于告警的汇总收敛 |
| `defense` | 防御收敛 | 触发阈值后启动防御模式 |

### 动作类型说明

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `drop` | 丢弃 | 直接丢弃被收敛的告警 |
| `pass` | 通过 | 标记后继续传递 |
| `aggregate` | 聚合 | 聚合多条告警为一条 |
| `delay` | 延迟 | 延迟处理 |
| `notify` | 通知 | 发送收敛通知 |

## JSON 配置示例

### 示例 1: 通知动作收敛

```json
{
  "name": "notification_converge",
  "description": "通知收敛，相同告警5分钟内只发送一次",
  "enabled": true,
  "node_type": "converge",
  "converge_type": "action",
  "converge_func": "skip_when_success",
  "dimension": {
    "fields": [
      "event.strategy_id",
      "event.biz_id",
      "event.dimensions.host"
    ],
    "hash_dimension": true
  },
  "window": {
    "duration": 300,
    "count": 1
  },
  "converge_action": {
    "action_type": "drop"
  },
  "need_biz_converge": true,
  "storage_backend": "redis",
  "cache_ttl": 600,
  "execution": {
    "timeout": 10
  }
}
```

### 示例 2: 告警风暴防御收敛

```json
{
  "name": "alert_storm_defense",
  "description": "告警风暴防护，1分钟内超过100条相同告警触发防御收敛",
  "enabled": true,
  "node_type": "converge",
  "converge_type": "defense",
  "converge_func": "defense",
  "dimension": {
    "fields": [
      "event.biz_id",
      "event.strategy_id"
    ],
    "hash_dimension": true
  },
  "conditions": [
    {
      "field": "event.severity",
      "operator": "in",
      "value": [1, 2, 3]
    }
  ],
  "window": {
    "duration": 60,
    "count": 100
  },
  "converge_action": {
    "action_type": "aggregate",
    "aggregate_fields": [
      "event.alert_name",
      "event.target"
    ]
  },
  "converge_id_template": "defense_{{ biz_id }}_{{ strategy_id }}",
  "need_biz_converge": false,
  "storage_backend": "redis",
  "cache_ttl": 3600,
  "execution": {
    "timeout": 15
  },
  "error_handling": {
    "on_error": "pass",
    "log_error": true
  }
}
```

### 示例 3: 业务维度汇总收敛

```json
{
  "name": "business_collect_converge",
  "description": "按业务维度汇总收敛，每10分钟汇总一次同类告警",
  "enabled": true,
  "node_type": "converge",
  "converge_type": "collect",
  "converge_func": "collect_alarm",
  "dimension": {
    "fields": [
      "event.biz_id",
      "event.alert_name",
      "event.dimensions.cluster"
    ],
    "hash_dimension": true
  },
  "conditions": [
    {
      "field": "event.status",
      "operator": "eq",
      "value": "ABNORMAL"
    },
    {
      "field": "event.is_shielded",
      "operator": "ne",
      "value": true
    }
  ],
  "window": {
    "duration": 600,
    "count": 2,
    "slide_interval": 60
  },
  "converge_action": {
    "action_type": "aggregate",
    "aggregate_fields": [
      "event.target",
      "event.dimensions.host",
      "event.current_value"
    ]
  },
  "sub_converge_config": {
    "enabled": true,
    "sub_dimension": ["event.dimensions.host"],
    "sub_window": 120
  },
  "need_biz_converge": true,
  "converge_id_template": "collect_{{ biz_id }}_{{ alert_name }}_{{ dimension_hash }}",
  "storage_backend": "redis",
  "cache_ttl": 86400,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.skip_converge",
        "operator": "eq",
        "value": true
      },
      {
        "field": "event.severity",
        "operator": "eq",
        "value": 1
      }
    ]
  },
  "execution": {
    "timeout": 30,
    "retry_enabled": true,
    "retry_max_attempts": 2
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true,
    "fallback_action": "pass_through"
  }
}
```

## 使用场景

1. **通知收敛**：同一告警短时间内只发送一次通知，避免通知轰炸
2. **告警风暴防护**：检测到告警风暴时自动启动防御，聚合大量告警
3. **业务汇总**：按业务维度定时汇总告警，生成告警报告
4. **自愈动作收敛**：防止自愈脚本重复执行
5. **工单收敛**：相同问题只创建一个工单
6. **消息聚合**：将多条相关消息聚合为一条发送
7. **梯度收敛**：根据告警数量动态调整收敛策略

## 注意事项

1. **收敛维度选择**：
   - 维度字段应能唯一标识一组需要收敛的告警
   - 维度过细会导致收敛效果不明显
   - 维度过粗可能导致不相关告警被收敛

2. **时间窗口设置**：
   - 窗口过短可能无法有效收敛
   - 窗口过长会增加告警延迟
   - 滑动窗口适合连续监控场景

3. **阈值设置**：
   - `window.count` 设置触发收敛的最小数量
   - 防御收敛的阈值不宜过低，避免误触发

4. **与现有系统集成**：
   - 本节点可与现有的 `ConvergeProcessor` 配合使用
   - `need_biz_converge` 控制是否需要业务层收敛确认

5. **存储选择**：
   - Redis适合分布式部署，支持持久化
   - Memory适合单实例，性能更高

6. **多级收敛**：
   - 使用 `sub_converge_config` 配置子收敛
   - 可实现先按主机收敛，再按集群收敛

7. **性能考虑**：
   - 大量告警时Redis可能成为瓶颈
   - 合理设置 `cache_ttl` 避免内存溢出
   - 收敛计算可能增加处理延迟

8. **错误处理**：
   - 建议配置 `fallback_action: pass_through`
   - 收敛失败时不应阻塞告警流程

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤无效告警
  - Dedupe（去重节点）：去重后再收敛
  - Enrichment（丰富化节点）：补充收敛维度信息
  - Transform（转换节点）：标准化字段后收敛

- **下游节点**：
  - Router（路由节点）：收敛后路由分发
  - Notification（通知节点）：发送收敛后的告警
  - Action（动作节点）：执行自愈动作
  - Storage（存储节点）：存储收敛结果

### 典型组合模式

1. **Filter → Dedupe → Converge → Notification**
   - 过滤 → 去重 → 收敛 → 通知

2. **Enrichment → Converge → Router → [多渠道]**
   - 丰富 → 收敛 → 路由 → 多渠道处理

3. **Transform → Converge → Action → Recovery**
   - 转换 → 收敛 → 动作 → 恢复

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
