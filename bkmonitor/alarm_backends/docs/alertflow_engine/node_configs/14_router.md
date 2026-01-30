# Router Node Configuration (路由节点配置)

## 节点类型
- **NodeType**: `router`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 根据条件将事件路由到不同的下游节点或Pipeline分支

## 配置 Schema

### RouterNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class RouterMode(str, Enum):
    """路由模式"""
    FIRST_MATCH = "first_match"   # 匹配第一个满足条件的路由
    ALL_MATCH = "all_match"       # 匹配所有满足条件的路由
    WEIGHTED = "weighted"         # 加权随机路由
    ROUND_ROBIN = "round_robin"   # 轮询路由


class RouteConditionSerializer(serializers.Serializer):
    """路由条件"""
    field = serializers.CharField(help_text="条件字段路径")
    operator = serializers.ChoiceField(
        choices=[
            ("eq", "等于"),
            ("ne", "不等于"),
            ("gt", "大于"),
            ("gte", "大于等于"),
            ("lt", "小于"),
            ("lte", "小于等于"),
            ("in", "在列表中"),
            ("not_in", "不在列表中"),
            ("contains", "包含"),
            ("regex", "正则匹配"),
            ("exists", "字段存在"),
        ],
        help_text="比较操作符"
    )
    value = serializers.JSONField(
        default=None,
        required=False,
        help_text="比较值"
    )


class RouteConditionGroupSerializer(serializers.Serializer):
    """路由条件组"""
    logic = serializers.ChoiceField(
        choices=[("and", "AND"), ("or", "OR")],
        default="and",
        help_text="条件组合逻辑"
    )
    conditions = RouteConditionSerializer(many=True, help_text="条件列表")


class RouteRuleSerializer(serializers.Serializer):
    """路由规则"""
    name = serializers.CharField(help_text="路由规则名称")
    description = serializers.CharField(
        default="",
        required=False,
        help_text="规则描述"
    )
    priority = serializers.IntegerField(
        default=0,
        help_text="优先级（数值越大优先级越高）"
    )
    
    # 路由条件
    condition = RouteConditionGroupSerializer(
        required=False,
        allow_null=True,
        help_text="路由条件（不设置则为默认路由）"
    )
    
    # 目标配置
    target_node = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="目标节点ID"
    )
    target_pipeline = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="目标Pipeline ID"
    )
    target_stage = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="目标Stage ID"
    )
    
    # 权重（weighted模式使用）
    weight = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="路由权重（weighted模式使用）"
    )
    
    # 数据转换
    transform_data = serializers.DictField(
        default=dict,
        required=False,
        help_text="路由前的数据转换"
    )
    
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用此路由规则"
    )


class RouterNodeConfigSerializer(BaseNodeConfigSerializer):
    """路由节点配置"""
    node_type = serializers.CharField(default="router", read_only=True)
    
    # 路由模式
    mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RouterMode],
        default="first_match",
        help_text="路由模式"
    )
    
    # 路由规则列表
    routes = RouteRuleSerializer(many=True, help_text="路由规则列表")
    
    # 默认路由
    default_route = serializers.CharField(
        default=None,
        required=False,
        allow_null=True,
        help_text="默认路由目标（无规则匹配时使用）"
    )
    
    # 是否允许丢弃
    allow_drop = serializers.BooleanField(
        default=False,
        help_text="无匹配路由时是否允许丢弃事件"
    )
    
    # 路由追踪
    trace_route = serializers.BooleanField(
        default=True,
        help_text="是否在事件中记录路由路径"
    )
    
    # 路由字段
    route_field = serializers.CharField(
        default="_route_path",
        help_text="存储路由路径的字段名"
    )
    
    def validate_routes(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要配置一条路由规则")
        return value
    
    def validate(self, attrs):
        if not attrs.get('default_route') and not attrs.get('allow_drop'):
            # 检查是否有无条件的默认路由
            has_default = any(
                not r.get('condition') for r in attrs.get('routes', [])
            )
            if not has_default:
                raise serializers.ValidationError(
                    "必须配置default_route或allow_drop=true，或添加无条件路由规则"
                )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "router" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `mode` | string | 否 | "first_match" | 路由模式 |
| `routes` | array | 是 | - | 路由规则列表 |
| `default_route` | string | 否 | null | 默认路由目标 |
| `allow_drop` | boolean | 否 | false | 允许丢弃无匹配事件 |
| `trace_route` | boolean | 否 | true | 记录路由路径 |
| `route_field` | string | 否 | "_route_path" | 路由路径字段 |

### 路由规则字段 (RouteRule)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 规则名称 |
| `description` | string | 否 | "" | 规则描述 |
| `priority` | integer | 否 | 0 | 优先级 |
| `condition` | object | 否 | null | 路由条件 |
| `target_node` | string | 否 | null | 目标节点ID |
| `target_pipeline` | string | 否 | null | 目标Pipeline ID |
| `target_stage` | string | 否 | null | 目标Stage ID |
| `weight` | integer | 否 | 1 | 路由权重 |
| `transform_data` | object | 否 | {} | 数据转换 |
| `enabled` | boolean | 否 | true | 是否启用 |

### 路由条件组字段 (RouteConditionGroup)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `logic` | string | 否 | "and" | 逻辑组合：and/or |
| `conditions` | array | 是 | - | 条件列表 |

### 路由条件字段 (RouteCondition)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `field` | string | 是 | 字段路径 |
| `operator` | string | 是 | 操作符 |
| `value` | any | 否 | 比较值 |

### 路由模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `first_match` | 匹配第一个满足条件的规则后停止 | 互斥条件路由 |
| `all_match` | 匹配所有满足条件的规则（多播） | 需要多分支并行处理 |
| `weighted` | 按权重随机选择路由 | 流量分流、灰度发布 |
| `round_robin` | 轮询选择路由 | 负载均衡 |

### 操作符说明

| 操作符 | 说明 | 示例值 |
|--------|------|--------|
| `eq` | 等于 | `"error"` |
| `ne` | 不等于 | `"info"` |
| `gt` | 大于 | `100` |
| `gte` | 大于等于 | `3` |
| `lt` | 小于 | `50` |
| `lte` | 小于等于 | `1` |
| `in` | 在列表中 | `["error", "fatal"]` |
| `not_in` | 不在列表中 | `["debug", "info"]` |
| `contains` | 包含子串 | `"timeout"` |
| `regex` | 正则匹配 | `"^prod-.*"` |
| `exists` | 字段存在 | `true` |

## JSON 配置示例

### 示例 1: 基于告警级别的分级路由

```json
{
  "name": "severity_router",
  "description": "根据告警级别路由到不同处理流程",
  "enabled": true,
  "node_type": "router",
  "mode": "first_match",
  "routes": [
    {
      "name": "critical_route",
      "description": "致命告警走紧急处理流程",
      "priority": 100,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "eq",
            "value": 1
          }
        ]
      },
      "target_pipeline": "critical_alert_pipeline",
      "enabled": true
    },
    {
      "name": "warning_route",
      "description": "警告告警走普通处理流程",
      "priority": 50,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "in",
            "value": [2, 3]
          }
        ]
      },
      "target_pipeline": "warning_alert_pipeline",
      "enabled": true
    },
    {
      "name": "info_route",
      "description": "提示级别告警仅记录",
      "priority": 10,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "gte",
            "value": 4
          }
        ]
      },
      "target_node": "log_only_node",
      "enabled": true
    }
  ],
  "default_route": "default_pipeline",
  "trace_route": true,
  "execution": {
    "timeout": 5
  }
}
```

### 示例 2: 多条件组合与多播路由

```json
{
  "name": "multi_condition_router",
  "description": "复杂条件路由，支持多播到多个目标",
  "enabled": true,
  "node_type": "router",
  "mode": "all_match",
  "routes": [
    {
      "name": "production_critical",
      "description": "生产环境致命告警",
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
            "operator": "lte",
            "value": 2
          }
        ]
      },
      "target_pipeline": "oncall_notification",
      "transform_data": {
        "add_fields": {
          "urgent": true,
          "notification_channel": "phone"
        }
      },
      "enabled": true
    },
    {
      "name": "audit_log",
      "description": "所有告警都记录审计日志",
      "priority": 0,
      "target_node": "audit_logger",
      "enabled": true
    },
    {
      "name": "metrics_export",
      "description": "导出告警指标",
      "priority": 0,
      "condition": {
        "logic": "or",
        "conditions": [
          {
            "field": "event.type",
            "operator": "eq",
            "value": "metric_alert"
          },
          {
            "field": "event.has_metric",
            "operator": "eq",
            "value": true
          }
        ]
      },
      "target_node": "metrics_exporter",
      "enabled": true
    }
  ],
  "allow_drop": false,
  "trace_route": true,
  "route_field": "_routed_to",
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 加权路由与灰度发布

```json
{
  "name": "canary_router",
  "description": "灰度发布路由，按权重分流到新旧处理流程",
  "enabled": true,
  "node_type": "router",
  "mode": "weighted",
  "routes": [
    {
      "name": "new_pipeline_canary",
      "description": "新处理流程（灰度10%）",
      "weight": 10,
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.biz_id",
            "operator": "in",
            "value": [100, 101, 102]
          }
        ]
      },
      "target_pipeline": "alert_pipeline_v2",
      "transform_data": {
        "add_fields": {
          "_canary": true,
          "_pipeline_version": "v2"
        }
      },
      "enabled": true
    },
    {
      "name": "stable_pipeline",
      "description": "稳定版处理流程（90%）",
      "weight": 90,
      "target_pipeline": "alert_pipeline_v1",
      "transform_data": {
        "add_fields": {
          "_canary": false,
          "_pipeline_version": "v1"
        }
      },
      "enabled": true
    }
  ],
  "trace_route": true,
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.skip_routing",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 5
  },
  "error_handling": {
    "on_error": "fallback",
    "fallback_route": "alert_pipeline_v1"
  }
}
```

## 使用场景

1. **告警分级处理**：根据告警级别路由到不同的处理流程
2. **环境隔离**：生产/测试/开发环境的告警分开处理
3. **业务路由**：不同业务线的告警路由到各自的处理Team
4. **灰度发布**：新版本Pipeline的灰度测试
5. **流量分流**：将告警流量分发到多个处理节点
6. **多渠道通知**：同一告警同时路由到多个通知渠道
7. **条件过滤**：基于复杂条件决定告警的处理路径

## 注意事项

1. **路由顺序**：
   - `first_match`模式下按priority降序匹配
   - 相同优先级按配置顺序匹配
   - 建议明确设置priority避免歧义

2. **默认路由**：
   - 必须配置`default_route`或`allow_drop=true`
   - 或添加一条无条件的路由规则作为兜底

3. **性能考虑**：
   - 条件数量过多会影响性能
   - 正则匹配相对较慢，谨慎使用
   - `all_match`模式会遍历所有规则

4. **多播路由**：
   - `all_match`模式下可能产生多个事件副本
   - 注意下游节点的幂等性处理

5. **加权路由**：
   - 权重为相对值，所有启用规则的权重之和为基准
   - 适合做灰度发布和负载均衡

6. **数据转换**：
   - `transform_data`在路由前执行
   - 可用于添加路由标记或修改事件属性

7. **错误处理**：
   - 建议配置`fallback_route`作为错误时的降级路由
   - `trace_route=true`有助于问题排查

8. **条件表达式**：
   - 字段路径支持嵌套，如`event.dimensions.host`
   - `exists`操作符用于检查字段是否存在

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再路由
  - Transform（转换节点）：转换后基于新字段路由
  - Enrichment（丰富化节点）：丰富数据后路由
  - Dedupe（去重节点）：去重后路由

- **下游节点**：
  - 根据路由规则配置，可路由到任意节点或Pipeline
  - 常见下游：Notification、Action、Storage等

### 典型组合模式

1. **Filter → Dedupe → Router → [多分支]**
   - 过滤 → 去重 → 路由 → 分支处理

2. **Enrichment → Router → [Notification | Action | Storage]**
   - 丰富 → 路由 → 通知/动作/存储

3. **Transform → Router → [Pipeline_A | Pipeline_B]**
   - 转换 → 路由 → 不同Pipeline

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
