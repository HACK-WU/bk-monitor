# Shield Node Configuration (屏蔽节点配置)

## 节点类型
- **NodeType**: `shield`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 基于屏蔽规则过滤告警，支持维护窗口、策略屏蔽等多种屏蔽类型

## 配置 Schema

### ShieldNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class ShieldType(str, Enum):
    """屏蔽类型"""
    SCOPE = "scope"             # 范围屏蔽
    STRATEGY = "strategy"       # 策略屏蔽
    EVENT = "event"             # 事件屏蔽
    ALERT = "alert"             # 告警屏蔽
    DIMENSION = "dimension"     # 维度屏蔽


class ShieldCategory(str, Enum):
    """屏蔽分类"""
    MAINTENANCE = "maintenance"     # 维护窗口
    TEMPORARY = "temporary"         # 临时屏蔽
    PERMANENT = "permanent"         # 永久屏蔽
    BUSINESS = "business"           # 业务屏蔽


class ShieldScope(str, Enum):
    """屏蔽范围"""
    BIZ = "biz"                 # 业务级
    HOST = "host"               # 主机级
    SERVICE = "service"         # 服务级
    INSTANCE = "instance"       # 实例级
    TOPO = "topo"               # 拓扑级


class ShieldTimeRangeSerializer(serializers.Serializer):
    """屏蔽时间范围配置"""
    type = serializers.ChoiceField(
        choices=[("once", "单次"), ("periodic", "周期")],
        default="once",
        help_text="时间范围类型"
    )
    begin_time = serializers.DateTimeField(
        required=False,
        help_text="开始时间"
    )
    end_time = serializers.DateTimeField(
        required=False,
        help_text="结束时间"
    )
    # 周期配置
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        help_text="周期重复的星期（0=周一，6=周日）"
    )
    start_time = serializers.CharField(
        required=False,
        help_text="每天开始时间（HH:MM格式）"
    )
    stop_time = serializers.CharField(
        required=False,
        help_text="每天结束时间（HH:MM格式）"
    )


class ShieldConditionSerializer(serializers.Serializer):
    """屏蔽条件配置"""
    field = serializers.CharField(help_text="条件字段")
    operator = serializers.ChoiceField(
        choices=[
            ("eq", "等于"),
            ("ne", "不等于"),
            ("in", "在列表中"),
            ("not_in", "不在列表中"),
            ("regex", "正则匹配"),
            ("contains", "包含"),
        ],
        help_text="条件操作符"
    )
    value = serializers.JSONField(help_text="条件值")


class ShieldDimensionSerializer(serializers.Serializer):
    """屏蔽维度配置"""
    dimension_key = serializers.CharField(help_text="维度键名")
    dimension_value = serializers.JSONField(help_text="维度值（支持单值或列表）")


class ShieldRuleSerializer(serializers.Serializer):
    """屏蔽规则配置"""
    id = serializers.CharField(
        required=False,
        help_text="规则ID（用于关联外部屏蔽配置）"
    )
    name = serializers.CharField(help_text="规则名称")
    description = serializers.CharField(
        default="",
        required=False,
        help_text="规则描述"
    )
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用"
    )
    
    # 屏蔽类型和分类
    shield_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ShieldType],
        help_text="屏蔽类型"
    )
    category = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ShieldCategory],
        default="temporary",
        help_text="屏蔽分类"
    )
    
    # 屏蔽范围
    scope = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ShieldScope],
        required=False,
        help_text="屏蔽范围（shield_type=scope时使用）"
    )
    scope_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="范围ID列表"
    )
    
    # 屏蔽条件
    conditions = ShieldConditionSerializer(
        many=True,
        required=False,
        help_text="屏蔽条件列表"
    )
    conditions_logic = serializers.ChoiceField(
        choices=[("and", "AND"), ("or", "OR")],
        default="and",
        help_text="条件组合逻辑"
    )
    
    # 维度屏蔽
    dimensions = ShieldDimensionSerializer(
        many=True,
        required=False,
        help_text="屏蔽维度配置"
    )
    
    # 时间范围
    time_range = ShieldTimeRangeSerializer(
        required=False,
        help_text="屏蔽时间范围"
    )
    
    # 优先级
    priority = serializers.IntegerField(
        default=0,
        help_text="规则优先级"
    )


class ShieldNodeConfigSerializer(BaseNodeConfigSerializer):
    """屏蔽节点配置"""
    node_type = serializers.CharField(default="shield", read_only=True)
    
    # 屏蔽规则列表
    rules = ShieldRuleSerializer(many=True, required=False, help_text="屏蔽规则列表")
    
    # 是否加载外部屏蔽配置
    load_external_shields = serializers.BooleanField(
        default=True,
        help_text="是否加载外部屏蔽配置（从数据库）"
    )
    
    # 外部屏蔽配置过滤
    external_shield_filter = serializers.DictField(
        default=dict,
        required=False,
        help_text="外部屏蔽配置过滤条件"
    )
    
    # 屏蔽匹配模式
    match_mode = serializers.ChoiceField(
        choices=[("first", "首个匹配"), ("all", "所有匹配")],
        default="first",
        help_text="屏蔽匹配模式"
    )
    
    # 屏蔽动作
    shield_action = serializers.ChoiceField(
        choices=[
            ("drop", "丢弃"),
            ("mark", "标记继续"),
            ("suppress", "抑制通知"),
        ],
        default="drop",
        help_text="屏蔽动作"
    )
    
    # 屏蔽标记字段
    shield_mark_field = serializers.CharField(
        default="is_shielded",
        help_text="屏蔽标记字段名"
    )
    shield_reason_field = serializers.CharField(
        default="shield_reason",
        help_text="屏蔽原因字段名"
    )
    
    # 缓存配置
    cache_enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用屏蔽规则缓存"
    )
    cache_ttl = serializers.IntegerField(
        default=60,
        help_text="缓存TTL（秒）"
    )
    
    # 日志记录
    log_shielded_events = serializers.BooleanField(
        default=True,
        help_text="是否记录被屏蔽的事件"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "shield" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `rules` | array | 否 | [] | 屏蔽规则列表 |
| `load_external_shields` | boolean | 否 | true | 加载外部屏蔽 |
| `match_mode` | string | 否 | "first" | 匹配模式 |
| `shield_action` | string | 否 | "drop" | 屏蔽动作 |
| `shield_mark_field` | string | 否 | "is_shielded" | 屏蔽标记字段 |
| `cache_enabled` | boolean | 否 | true | 启用缓存 |
| `log_shielded_events` | boolean | 否 | true | 记录日志 |

### 屏蔽规则字段 (ShieldRule)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | string | 否 | - | 规则ID |
| `name` | string | 是 | - | 规则名称 |
| `description` | string | 否 | "" | 规则描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `shield_type` | string | 是 | - | 屏蔽类型 |
| `category` | string | 否 | "temporary" | 屏蔽分类 |
| `scope` | string | 否 | - | 屏蔽范围 |
| `scope_ids` | array | 否 | - | 范围ID列表 |
| `conditions` | array | 否 | [] | 条件列表 |
| `dimensions` | array | 否 | [] | 维度配置 |
| `time_range` | object | 否 | - | 时间范围 |
| `priority` | integer | 否 | 0 | 优先级 |

### 屏蔽时间范围 (ShieldTimeRange)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 否 | once(单次)/periodic(周期) |
| `begin_time` | datetime | 否 | 开始时间 |
| `end_time` | datetime | 否 | 结束时间 |
| `weekdays` | array | 否 | 周期重复星期 |
| `start_time` | string | 否 | 每天开始时间 |
| `stop_time` | string | 否 | 每天结束时间 |

### 屏蔽类型说明

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `scope` | 范围屏蔽 | 按业务/主机/服务范围屏蔽 |
| `strategy` | 策略屏蔽 | 屏蔽特定策略的告警 |
| `event` | 事件屏蔽 | 屏蔽特定事件 |
| `alert` | 告警屏蔽 | 屏蔽特定告警 |
| `dimension` | 维度屏蔽 | 按维度组合屏蔽 |

### 屏蔽分类说明

| 分类 | 说明 | 典型场景 |
|------|------|----------|
| `maintenance` | 维护窗口 | 系统维护期间 |
| `temporary` | 临时屏蔽 | 临时忽略某些告警 |
| `permanent` | 永久屏蔽 | 长期屏蔽已知问题 |
| `business` | 业务屏蔽 | 业务特殊需求 |

### 屏蔽动作说明

| 动作 | 说明 | 事件处理 |
|------|------|----------|
| `drop` | 丢弃 | 直接丢弃，不继续处理 |
| `mark` | 标记 | 标记后继续流转 |
| `suppress` | 抑制 | 继续处理但不发送通知 |

## JSON 配置示例

### 示例 1: 维护窗口屏蔽

```json
{
  "name": "maintenance_shield",
  "description": "维护窗口屏蔽，每周二凌晨2-6点屏蔽所有告警",
  "enabled": true,
  "node_type": "shield",
  "rules": [
    {
      "name": "weekly_maintenance",
      "description": "每周二凌晨维护窗口",
      "enabled": true,
      "shield_type": "scope",
      "category": "maintenance",
      "scope": "biz",
      "scope_ids": ["100", "101", "102"],
      "time_range": {
        "type": "periodic",
        "weekdays": [1],
        "start_time": "02:00",
        "stop_time": "06:00"
      },
      "priority": 100
    }
  ],
  "load_external_shields": true,
  "shield_action": "drop",
  "cache_enabled": true,
  "cache_ttl": 60,
  "log_shielded_events": true,
  "execution": {
    "timeout": 10
  }
}
```

### 示例 2: 多条件策略屏蔽

```json
{
  "name": "strategy_shield",
  "description": "屏蔽特定策略在测试环境的告警",
  "enabled": true,
  "node_type": "shield",
  "rules": [
    {
      "name": "test_env_shield",
      "description": "测试环境屏蔽",
      "enabled": true,
      "shield_type": "strategy",
      "category": "business",
      "conditions": [
        {
          "field": "event.environment",
          "operator": "in",
          "value": ["test", "dev", "staging"]
        }
      ],
      "conditions_logic": "and",
      "priority": 50
    },
    {
      "name": "specific_strategy_shield",
      "description": "屏蔽特定策略",
      "enabled": true,
      "shield_type": "strategy",
      "category": "temporary",
      "conditions": [
        {
          "field": "event.strategy_id",
          "operator": "in",
          "value": [1001, 1002, 1003]
        },
        {
          "field": "event.severity",
          "operator": "ne",
          "value": 1
        }
      ],
      "conditions_logic": "and",
      "time_range": {
        "type": "once",
        "begin_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-01-31T23:59:59Z"
      },
      "priority": 30
    }
  ],
  "load_external_shields": false,
  "match_mode": "first",
  "shield_action": "mark",
  "shield_mark_field": "is_shielded",
  "shield_reason_field": "shield_reason",
  "cache_enabled": true,
  "log_shielded_events": true,
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 维度屏蔽与外部配置集成

```json
{
  "name": "dimension_shield",
  "description": "按维度屏蔽，并加载外部屏蔽配置",
  "enabled": true,
  "node_type": "shield",
  "rules": [
    {
      "name": "host_dimension_shield",
      "description": "屏蔽特定主机的告警",
      "enabled": true,
      "shield_type": "dimension",
      "category": "maintenance",
      "dimensions": [
        {
          "dimension_key": "host",
          "dimension_value": ["192.168.1.100", "192.168.1.101"]
        },
        {
          "dimension_key": "cluster",
          "dimension_value": "maintenance_cluster"
        }
      ],
      "time_range": {
        "type": "once",
        "begin_time": "2024-01-15T00:00:00Z",
        "end_time": "2024-01-15T08:00:00Z"
      },
      "priority": 80
    },
    {
      "name": "service_shield",
      "description": "屏蔽特定服务的低级别告警",
      "enabled": true,
      "shield_type": "scope",
      "category": "business",
      "scope": "service",
      "scope_ids": ["web-service", "api-gateway"],
      "conditions": [
        {
          "field": "event.severity",
          "operator": "in",
          "value": [3, 4, 5]
        }
      ],
      "priority": 60
    }
  ],
  "load_external_shields": true,
  "external_shield_filter": {
    "is_enabled": true,
    "biz_id__in": [100, 101]
  },
  "match_mode": "all",
  "shield_action": "suppress",
  "shield_mark_field": "is_shielded",
  "shield_reason_field": "shield_info",
  "cache_enabled": true,
  "cache_ttl": 120,
  "log_shielded_events": true,
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.severity",
        "operator": "eq",
        "value": 1
      }
    ]
  },
  "execution": {
    "timeout": 15
  },
  "error_handling": {
    "on_error": "pass",
    "log_error": true
  }
}
```

## 使用场景

1. **维护窗口**：系统维护期间自动屏蔽告警
2. **测试环境屏蔽**：屏蔽测试/开发环境的告警
3. **策略临时屏蔽**：临时禁用某个策略的告警
4. **主机维护**：特定主机维护时屏蔽相关告警
5. **业务屏蔽**：业务特殊需求，屏蔽特定业务告警
6. **低级别过滤**：屏蔽低级别告警，只关注重要告警
7. **周期性屏蔽**：定期维护窗口的周期性屏蔽

## 注意事项

1. **规则优先级**：
   - 优先级数值越大越先匹配
   - `match_mode=first` 时，匹配首个规则后停止
   - `match_mode=all` 时，匹配所有规则

2. **外部配置加载**：
   - `load_external_shields=true` 会从数据库加载屏蔽配置
   - 可通过 `external_shield_filter` 过滤外部配置
   - 外部配置与内部规则合并使用

3. **时间范围**：
   - `once` 类型为一次性屏蔽
   - `periodic` 类型为周期性屏蔽
   - 周期屏蔽需配置 `weekdays`、`start_time`、`stop_time`

4. **屏蔽动作选择**：
   - `drop`：直接丢弃，适合完全不需要处理的场景
   - `mark`：标记后继续，便于后续统计和审计
   - `suppress`：抑制通知但记录告警

5. **缓存配置**：
   - 建议启用缓存提高性能
   - `cache_ttl` 不宜过长，影响配置更新及时性
   - 缓存失效后会重新加载规则

6. **跳过条件**：
   - 建议致命告警跳过屏蔽检查
   - 通过 `skip_condition` 配置跳过逻辑

7. **日志记录**：
   - `log_shielded_events=true` 记录所有被屏蔽的事件
   - 便于事后审计和问题排查

8. **性能考虑**：
   - 规则数量过多会影响性能
   - 条件匹配尽量使用简单操作符
   - 正则匹配性能相对较低

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再屏蔽
  - Enrichment（丰富化节点）：补充屏蔽判断所需字段
  - Transform（转换节点）：标准化字段后屏蔽

- **下游节点**：
  - Router（路由节点）：屏蔽后路由
  - Converge（收敛节点）：屏蔽后收敛
  - Notification（通知节点）：屏蔽后通知
  - Storage（存储节点）：存储屏蔽记录

### 典型组合模式

1. **Filter → Shield → Notification**
   - 过滤 → 屏蔽 → 通知

2. **Enrichment → Shield → Router**
   - 丰富 → 屏蔽 → 路由

3. **Shield[mark] → Converge → Storage**
   - 屏蔽标记 → 收敛 → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
