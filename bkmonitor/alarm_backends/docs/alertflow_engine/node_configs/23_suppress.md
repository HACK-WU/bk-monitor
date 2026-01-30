# Suppress Node Configuration (抑制节点配置)

## 节点类型
- **NodeType**: `suppress`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 抑制低优先级或重复告警，避免告警风暴干扰

## 配置 Schema

### SuppressNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class SuppressType(str, Enum):
    """抑制类型"""
    PARENT_CHILD = "parent_child"     # 父子告警抑制
    SEVERITY = "severity"             # 级别抑制
    DUPLICATE = "duplicate"           # 重复抑制
    DEPENDENCY = "dependency"         # 依赖关系抑制
    CUSTOM = "custom"                 # 自定义抑制


class SuppressAction(str, Enum):
    """抑制动作"""
    DROP = "drop"             # 丢弃
    MARK = "mark"             # 标记
    DELAY = "delay"           # 延迟
    AGGREGATE = "aggregate"   # 聚合


class SuppressRuleSerializer(serializers.Serializer):
    """抑制规则配置"""
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
    priority = serializers.IntegerField(
        default=0,
        help_text="规则优先级"
    )
    
    # 抑制类型
    suppress_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in SuppressType],
        help_text="抑制类型"
    )
    
    # 抑制条件
    condition = serializers.DictField(
        required=False,
        help_text="抑制条件"
    )
    
    # 抑制动作
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in SuppressAction],
        default="mark",
        help_text="抑制动作"
    )
    
    # 延迟时间（action=delay时使用）
    delay_seconds = serializers.IntegerField(
        default=300,
        help_text="延迟时间（秒）"
    )


class ParentChildConfigSerializer(serializers.Serializer):
    """父子告警抑制配置"""
    parent_field = serializers.CharField(
        help_text="父告警标识字段"
    )
    child_field = serializers.CharField(
        help_text="子告警标识字段"
    )
    relationship_type = serializers.ChoiceField(
        choices=[
            ("host_service", "主机-服务"),
            ("cluster_node", "集群-节点"),
            ("topo", "拓扑关系"),
            ("custom", "自定义"),
        ],
        default="custom",
        help_text="关系类型"
    )
    suppress_direction = serializers.ChoiceField(
        choices=[
            ("parent_suppress_child", "父抑制子"),
            ("child_suppress_parent", "子抑制父"),
        ],
        default="parent_suppress_child",
        help_text="抑制方向"
    )
    lookup_window = serializers.IntegerField(
        default=300,
        help_text="查找父/子告警的时间窗口（秒）"
    )


class SeveritySuppressConfigSerializer(serializers.Serializer):
    """级别抑制配置"""
    high_severity_threshold = serializers.IntegerField(
        default=1,
        help_text="高级别阈值（小于等于此值为高级别）"
    )
    suppress_lower = serializers.BooleanField(
        default=True,
        help_text="是否抑制低级别告警"
    )
    same_dimension_only = serializers.BooleanField(
        default=True,
        help_text="是否仅抑制相同维度的告警"
    )
    dimension_fields = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="维度字段列表"
    )


class DependencySuppressConfigSerializer(serializers.Serializer):
    """依赖关系抑制配置"""
    dependency_source = serializers.ChoiceField(
        choices=[
            ("cmdb", "CMDB"),
            ("config", "配置"),
            ("api", "API"),
        ],
        default="cmdb",
        help_text="依赖关系来源"
    )
    dependency_config = serializers.DictField(
        default=dict,
        help_text="依赖关系配置"
    )
    suppress_downstream = serializers.BooleanField(
        default=True,
        help_text="上游故障时抑制下游告警"
    )


class SuppressNodeConfigSerializer(BaseNodeConfigSerializer):
    """抑制节点配置"""
    node_type = serializers.CharField(default="suppress", read_only=True)
    
    # 抑制规则
    rules = SuppressRuleSerializer(many=True, help_text="抑制规则列表")
    
    # 父子告警抑制配置
    parent_child_config = ParentChildConfigSerializer(
        required=False,
        help_text="父子告警抑制配置"
    )
    
    # 级别抑制配置
    severity_config = SeveritySuppressConfigSerializer(
        required=False,
        help_text="级别抑制配置"
    )
    
    # 依赖关系抑制配置
    dependency_config = DependencySuppressConfigSerializer(
        required=False,
        help_text="依赖关系抑制配置"
    )
    
    # 抑制标记
    suppress_mark_field = serializers.CharField(
        default="is_suppressed",
        help_text="抑制标记字段名"
    )
    suppress_reason_field = serializers.CharField(
        default="suppress_reason",
        help_text="抑制原因字段名"
    )
    suppress_by_field = serializers.CharField(
        default="suppressed_by",
        help_text="被谁抑制字段名"
    )
    
    # 时间窗口
    suppress_window = serializers.IntegerField(
        default=300,
        help_text="抑制生效时间窗口（秒）"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="抑制状态存储后端"
    )
    cache_ttl = serializers.IntegerField(
        default=3600,
        help_text="缓存过期时间（秒）"
    )
    
    # 日志记录
    log_suppressed_alerts = serializers.BooleanField(
        default=True,
        help_text="是否记录被抑制的告警"
    )
    
    def validate_rules(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一条抑制规则")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "suppress" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `rules` | array | 是 | - | 抑制规则列表 |
| `suppress_mark_field` | string | 否 | "is_suppressed" | 抑制标记字段 |
| `suppress_window` | integer | 否 | 300 | 抑制时间窗口 |
| `storage_backend` | string | 否 | "redis" | 存储后端 |

### 抑制规则配置 (SuppressRule)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `suppress_type` | string | 是 | - | 抑制类型 |
| `condition` | object | 否 | - | 抑制条件 |
| `action` | string | 否 | "mark" | 抑制动作 |
| `priority` | integer | 否 | 0 | 规则优先级 |

### 父子告警抑制配置 (ParentChildConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_field` | string | 是 | 父告警标识字段 |
| `child_field` | string | 是 | 子告警标识字段 |
| `relationship_type` | string | 否 | 关系类型 |
| `suppress_direction` | string | 否 | 抑制方向 |
| `lookup_window` | integer | 否 | 查找时间窗口 |

### 抑制类型说明

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| `parent_child` | 父子告警抑制 | 主机故障抑制服务告警 |
| `severity` | 级别抑制 | 高级别告警抑制低级别 |
| `duplicate` | 重复抑制 | 相同告警短时间内抑制 |
| `dependency` | 依赖关系抑制 | 上游故障抑制下游告警 |
| `custom` | 自定义抑制 | 基于自定义条件抑制 |

### 抑制动作说明

| 动作 | 说明 | 效果 |
|------|------|------|
| `drop` | 丢弃 | 直接丢弃被抑制告警 |
| `mark` | 标记 | 标记后继续传递 |
| `delay` | 延迟 | 延迟处理 |
| `aggregate` | 聚合 | 聚合到父告警 |

## JSON 配置示例

### 示例 1: 父子告警抑制

```json
{
  "name": "parent_child_suppress",
  "description": "主机故障时抑制服务告警",
  "enabled": true,
  "node_type": "suppress",
  "rules": [
    {
      "name": "host_suppress_service",
      "description": "主机故障抑制服务告警",
      "enabled": true,
      "priority": 100,
      "suppress_type": "parent_child",
      "action": "mark"
    }
  ],
  "parent_child_config": {
    "parent_field": "event.dimensions.host",
    "child_field": "event.dimensions.host",
    "relationship_type": "host_service",
    "suppress_direction": "parent_suppress_child",
    "lookup_window": 300
  },
  "suppress_mark_field": "is_suppressed",
  "suppress_reason_field": "suppress_reason",
  "suppress_by_field": "suppressed_by_alert",
  "suppress_window": 600,
  "storage_backend": "redis",
  "cache_ttl": 3600,
  "log_suppressed_alerts": true,
  "execution": {
    "timeout": 30
  }
}
```

### 示例 2: 级别抑制配置

```json
{
  "name": "severity_suppress",
  "description": "高级别告警抑制同维度低级别告警",
  "enabled": true,
  "node_type": "suppress",
  "rules": [
    {
      "name": "high_suppress_low",
      "description": "高级别抑制低级别",
      "enabled": true,
      "priority": 80,
      "suppress_type": "severity",
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "gte",
            "value": 2
          }
        ]
      },
      "action": "mark"
    }
  ],
  "severity_config": {
    "high_severity_threshold": 1,
    "suppress_lower": true,
    "same_dimension_only": true,
    "dimension_fields": [
      "event.biz_id",
      "event.dimensions.host",
      "event.dimensions.service"
    ]
  },
  "suppress_mark_field": "is_suppressed",
  "suppress_reason_field": "suppress_info",
  "suppress_window": 300,
  "storage_backend": "redis",
  "log_suppressed_alerts": true,
  "execution": {
    "timeout": 30
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 依赖关系抑制

```json
{
  "name": "dependency_suppress",
  "description": "基于CMDB依赖关系的告警抑制",
  "enabled": true,
  "node_type": "suppress",
  "rules": [
    {
      "name": "upstream_suppress_downstream",
      "description": "上游故障抑制下游告警",
      "enabled": true,
      "priority": 100,
      "suppress_type": "dependency",
      "action": "aggregate"
    },
    {
      "name": "duplicate_suppress",
      "description": "重复告警抑制",
      "enabled": true,
      "priority": 50,
      "suppress_type": "duplicate",
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.alert_name",
            "operator": "eq",
            "value": "{{ $existing.alert_name }}"
          },
          {
            "field": "event.target",
            "operator": "eq",
            "value": "{{ $existing.target }}"
          }
        ]
      },
      "action": "mark",
      "delay_seconds": 0
    }
  ],
  "dependency_config": {
    "dependency_source": "cmdb",
    "dependency_config": {
      "bk_obj_id": "service",
      "relation_type": "depend_on"
    },
    "suppress_downstream": true
  },
  "suppress_mark_field": "is_suppressed",
  "suppress_reason_field": "suppress_reason",
  "suppress_by_field": "suppressed_by",
  "suppress_window": 600,
  "storage_backend": "redis",
  "cache_ttl": 7200,
  "log_suppressed_alerts": true,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.severity",
        "operator": "eq",
        "value": 1
      },
      {
        "field": "event.skip_suppress",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 60
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **父子告警抑制**：主机故障时自动抑制该主机上服务的告警
2. **级别抑制**：致命告警存在时抑制同维度的低级别告警
3. **重复告警抑制**：相同告警短时间内重复触发时抑制
4. **依赖关系抑制**：上游服务故障时抑制下游服务告警
5. **集群抑制**：集群故障时抑制节点级别告警
6. **维护期抑制**：维护期间抑制相关告警
7. **根因关联抑制**：找到根因后抑制关联告警

## 注意事项

1. **抑制顺序**：
   - 规则按优先级降序执行
   - 高优先级规则先匹配
   - 匹配成功后根据配置决定是否继续

2. **父子关系**：
   - 需要正确配置父子字段
   - `lookup_window` 决定查找范围
   - 注意循环依赖问题

3. **级别抑制**：
   - `same_dimension_only` 避免误抑制
   - 建议配置明确的维度字段
   - 致命告警通常不被抑制

4. **依赖关系**：
   - CMDB依赖关系需要正确维护
   - 注意依赖链的深度限制
   - 上游判断需要考虑时间窗口

5. **抑制动作**：
   - `drop` 会丢失告警，慎用
   - `mark` 保留告警便于统计
   - `aggregate` 可聚合到父告警

6. **时间窗口**：
   - `suppress_window` 控制抑制有效期
   - 窗口过长可能漏报
   - 窗口过短可能抑制不彻底

7. **存储考虑**：
   - Redis支持分布式抑制判断
   - 注意缓存过期设置
   - 高并发场景注意性能

8. **跳过条件**：
   - 致命告警通常不应被抑制
   - 配置 `skip_condition` 保护重要告警

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：过滤后抑制
  - Severity（级别节点）：级别调整后抑制
  - Enrichment（丰富化节点）：补充依赖信息后抑制

- **下游节点**：
  - Router（路由节点）：抑制后路由
  - Notification（通知节点）：抑制后通知
  - Storage（存储节点）：存储抑制记录

### 典型组合模式

1. **Enrichment → Suppress → Notification**
   - 丰富 → 抑制 → 通知

2. **Severity → Suppress → Router**
   - 级别调整 → 抑制 → 路由

3. **Filter → Suppress → Converge**
   - 过滤 → 抑制 → 收敛

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
