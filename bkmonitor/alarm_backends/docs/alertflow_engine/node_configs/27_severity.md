# Severity Node Configuration (级别调整节点配置)

## 节点类型
- **NodeType**: `severity`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 动态调整告警级别，支持基于条件的级别升降

## 配置 Schema

### SeverityNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class SeverityLevel(int, Enum):
    """告警级别"""
    FATAL = 1       # 致命
    WARNING = 2     # 预警
    REMIND = 3      # 提醒


class SeverityAction(str, Enum):
    """级别调整动作"""
    SET = "set"           # 直接设置
    UPGRADE = "upgrade"   # 升级
    DOWNGRADE = "downgrade"  # 降级
    DYNAMIC = "dynamic"   # 动态计算


class SeverityRuleSerializer(serializers.Serializer):
    """级别调整规则"""
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
        help_text="规则优先级（数值越大优先级越高）"
    )
    
    # 匹配条件
    condition = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="匹配条件"
    )
    
    # 级别调整动作
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in SeverityAction],
        help_text="调整动作"
    )
    
    # 目标级别（action=set时使用）
    target_severity = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=3,
        help_text="目标级别（1=致命，2=预警，3=提醒）"
    )
    
    # 级别增量（action=upgrade/downgrade时使用）
    severity_delta = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="级别调整幅度"
    )
    
    # 动态计算表达式（action=dynamic时使用）
    severity_expression = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="级别计算表达式"
    )


class SeverityMappingSerializer(serializers.Serializer):
    """级别映射配置"""
    source_field = serializers.CharField(help_text="源字段路径")
    mapping = serializers.DictField(help_text="映射关系")
    default_severity = serializers.IntegerField(
        default=3,
        help_text="默认级别"
    )


class SeverityNodeConfigSerializer(BaseNodeConfigSerializer):
    """级别调整节点配置"""
    node_type = serializers.CharField(default="severity", read_only=True)
    
    # 级别调整规则
    rules = SeverityRuleSerializer(many=True, help_text="级别调整规则列表")
    
    # 级别映射（快捷配置）
    severity_mapping = SeverityMappingSerializer(
        required=False,
        allow_null=True,
        help_text="级别映射配置"
    )
    
    # 默认级别
    default_severity = serializers.IntegerField(
        default=3,
        min_value=1,
        max_value=3,
        help_text="无规则匹配时的默认级别"
    )
    
    # 级别边界
    min_severity = serializers.IntegerField(
        default=1,
        min_value=1,
        max_value=3,
        help_text="最高级别（最小值，1=致命）"
    )
    max_severity = serializers.IntegerField(
        default=3,
        min_value=1,
        max_value=3,
        help_text="最低级别（最大值，3=提醒）"
    )
    
    # 原始级别保留
    preserve_original = serializers.BooleanField(
        default=True,
        help_text="是否保留原始级别"
    )
    original_severity_field = serializers.CharField(
        default="original_severity",
        help_text="保存原始级别的字段名"
    )
    
    # 级别变更记录
    track_changes = serializers.BooleanField(
        default=True,
        help_text="是否记录级别变更"
    )
    change_reason_field = serializers.CharField(
        default="severity_change_reason",
        help_text="变更原因字段名"
    )
    
    def validate_rules(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一条级别调整规则")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "severity" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `rules` | array | 是 | - | 级别调整规则列表 |
| `severity_mapping` | object | 否 | null | 级别映射配置 |
| `default_severity` | integer | 否 | 3 | 默认级别 |
| `min_severity` | integer | 否 | 1 | 最高级别（最小值） |
| `max_severity` | integer | 否 | 3 | 最低级别（最大值） |
| `preserve_original` | boolean | 否 | true | 保留原始级别 |
| `track_changes` | boolean | 否 | true | 记录变更 |

### 级别调整规则 (SeverityRule)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `description` | string | 否 | "" | 规则描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `priority` | integer | 否 | 0 | 优先级 |
| `condition` | object | 否 | null | 匹配条件 |
| `action` | string | 是 | - | 调整动作 |
| `target_severity` | integer | 否 | - | 目标级别 |
| `severity_delta` | integer | 否 | 1 | 调整幅度 |
| `severity_expression` | string | 否 | - | 计算表达式 |

### 级别映射配置 (SeverityMapping)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_field` | string | 是 | 源字段路径 |
| `mapping` | object | 是 | 映射关系 |
| `default_severity` | integer | 否 | 默认级别 |

### 告警级别说明

| 级别 | 数值 | 说明 | 典型场景 |
|------|------|------|----------|
| 致命 | 1 | 最高级别 | 服务不可用、数据丢失 |
| 预警 | 2 | 中等级别 | 性能下降、资源紧张 |
| 提醒 | 3 | 最低级别 | 信息提示、轻微异常 |

### 调整动作说明

| 动作 | 说明 | 参数 |
|------|------|------|
| `set` | 直接设置为指定级别 | target_severity |
| `upgrade` | 提升级别 | severity_delta |
| `downgrade` | 降低级别 | severity_delta |
| `dynamic` | 动态计算级别 | severity_expression |

## JSON 配置示例

### 示例 1: 基于条件的级别调整

```json
{
  "name": "condition_severity",
  "description": "根据告警条件动态调整级别",
  "enabled": true,
  "node_type": "severity",
  "rules": [
    {
      "name": "production_upgrade",
      "description": "生产环境告警升级为致命",
      "enabled": true,
      "priority": 100,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.environment",
            "operator": "eq",
            "value": "production"
          },
          {
            "field": "event.severity",
            "operator": "gte",
            "value": 2
          }
        ]
      },
      "action": "set",
      "target_severity": 1
    },
    {
      "name": "test_downgrade",
      "description": "测试环境告警降级",
      "enabled": true,
      "priority": 80,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.environment",
            "operator": "in",
            "value": ["test", "dev"]
          }
        ]
      },
      "action": "downgrade",
      "severity_delta": 1
    },
    {
      "name": "high_frequency_upgrade",
      "description": "高频告警升级",
      "enabled": true,
      "priority": 60,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.occurrence_count",
            "operator": "gte",
            "value": 10
          }
        ]
      },
      "action": "upgrade",
      "severity_delta": 1
    }
  ],
  "default_severity": 3,
  "min_severity": 1,
  "max_severity": 3,
  "preserve_original": true,
  "track_changes": true,
  "execution": {
    "timeout": 5
  }
}
```

### 示例 2: 级别映射配置

```json
{
  "name": "mapping_severity",
  "description": "基于外部级别字段映射告警级别",
  "enabled": true,
  "node_type": "severity",
  "severity_mapping": {
    "source_field": "event.external_severity",
    "mapping": {
      "critical": 1,
      "high": 1,
      "medium": 2,
      "low": 3,
      "info": 3
    },
    "default_severity": 2
  },
  "rules": [
    {
      "name": "vip_customer_upgrade",
      "description": "VIP客户告警升级",
      "enabled": true,
      "priority": 100,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.customer_level",
            "operator": "eq",
            "value": "vip"
          }
        ]
      },
      "action": "upgrade",
      "severity_delta": 1
    }
  ],
  "default_severity": 3,
  "preserve_original": true,
  "original_severity_field": "original_severity",
  "track_changes": true,
  "change_reason_field": "severity_change_reason",
  "execution": {
    "timeout": 5
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 动态级别计算

```json
{
  "name": "dynamic_severity",
  "description": "基于告警指标动态计算级别",
  "enabled": true,
  "node_type": "severity",
  "rules": [
    {
      "name": "cpu_severity",
      "description": "CPU使用率级别计算",
      "enabled": true,
      "priority": 100,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.metric_name",
            "operator": "eq",
            "value": "cpu_usage"
          }
        ]
      },
      "action": "dynamic",
      "severity_expression": "1 if event.current_value >= 95 else (2 if event.current_value >= 80 else 3)"
    },
    {
      "name": "memory_severity",
      "description": "内存使用率级别计算",
      "enabled": true,
      "priority": 90,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.metric_name",
            "operator": "eq",
            "value": "memory_usage"
          }
        ]
      },
      "action": "dynamic",
      "severity_expression": "1 if event.current_value >= 90 else (2 if event.current_value >= 70 else 3)"
    },
    {
      "name": "disk_severity",
      "description": "磁盘使用率级别计算",
      "enabled": true,
      "priority": 80,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.metric_name",
            "operator": "regex",
            "value": "^disk_.*_usage$"
          }
        ]
      },
      "action": "dynamic",
      "severity_expression": "1 if event.current_value >= 98 else (2 if event.current_value >= 90 else 3)"
    },
    {
      "name": "default_rule",
      "description": "默认规则",
      "enabled": true,
      "priority": 0,
      "action": "set",
      "target_severity": 3
    }
  ],
  "default_severity": 3,
  "min_severity": 1,
  "max_severity": 3,
  "preserve_original": true,
  "original_severity_field": "raw_severity",
  "track_changes": true,
  "change_reason_field": "severity_adjusted_by",
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.skip_severity_adjust",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "preserve",
    "log_error": true
  }
}
```

## 使用场景

1. **环境级别差异化**：生产环境告警自动升级，测试环境降级
2. **VIP客户升级**：VIP客户的告警自动提升级别
3. **指标阈值级别**：根据指标值动态计算告警级别
4. **外部级别映射**：将第三方系统的级别映射到本系统
5. **高频告警升级**：频繁触发的告警自动升级
6. **时段级别调整**：夜间或周末告警降级
7. **业务重要性调整**：核心业务告警升级

## 注意事项

1. **规则优先级**：
   - 优先级数值越大越先匹配
   - 匹配首个规则后停止（除非配置为全部匹配）

2. **级别边界**：
   - `min_severity` 限制最高可升级到的级别
   - `max_severity` 限制最低可降级到的级别
   - 防止级别越界

3. **原始级别保留**：
   - 建议开启 `preserve_original`
   - 便于审计和问题排查

4. **动态表达式**：
   - 支持Python语法的条件表达式
   - 可访问 `event` 对象的字段
   - 表达式求值失败会使用默认级别

5. **级别映射**：
   - `severity_mapping` 提供快捷配置
   - 映射优先于规则匹配
   - 未匹配的值使用 `default_severity`

6. **变更追踪**：
   - `track_changes=true` 记录调整原因
   - 便于后续审计和分析

7. **性能考虑**：
   - 规则数量不宜过多
   - 条件匹配应尽量简单
   - 动态表达式会有额外计算开销

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：过滤后调整级别
  - Enrichment（丰富化节点）：补充信息后调整级别
  - Transform（转换节点）：转换字段后调整级别

- **下游节点**：
  - Router（路由节点）：基于新级别路由
  - Notification（通知节点）：按级别选择通知方式
  - Converge（收敛节点）：收敛调整后的告警

### 典型组合模式

1. **Enrichment → Severity → Router**
   - 丰富 → 级别调整 → 路由

2. **Filter → Severity → Notification**
   - 过滤 → 级别调整 → 通知

3. **Transform → Severity → Converge**
   - 转换 → 级别调整 → 收敛

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
