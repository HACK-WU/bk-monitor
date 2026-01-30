# Incident Node Configuration (故障事件节点配置)

## 节点类型
- **NodeType**: `incident`
- **分类**: ACTION (动作类)
- **功能**: 创建或更新故障事件（Incident），支持告警聚合和事件管理

## 配置 Schema

### IncidentNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class IncidentAction(str, Enum):
    """事件动作"""
    CREATE = "create"           # 创建事件
    UPDATE = "update"           # 更新事件
    MERGE = "merge"             # 合并事件
    CLOSE = "close"             # 关闭事件
    AUTO = "auto"               # 自动选择


class IncidentPriority(str, Enum):
    """事件优先级"""
    P1 = "P1"   # 最高优先级
    P2 = "P2"   # 高优先级
    P3 = "P3"   # 中优先级
    P4 = "P4"   # 低优先级
    P5 = "P5"   # 最低优先级


class IncidentStatus(str, Enum):
    """事件状态"""
    NEW = "new"                 # 新建
    ACKNOWLEDGED = "acknowledged"  # 已确认
    IN_PROGRESS = "in_progress"   # 处理中
    RESOLVED = "resolved"       # 已解决
    CLOSED = "closed"           # 已关闭


class IncidentGroupingSerializer(serializers.Serializer):
    """事件分组配置"""
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用分组"
    )
    grouping_fields = serializers.ListField(
        child=serializers.CharField(),
        help_text="分组字段列表"
    )
    grouping_window = serializers.IntegerField(
        default=3600,
        help_text="分组时间窗口（秒）"
    )
    max_alerts_per_incident = serializers.IntegerField(
        default=100,
        help_text="每个事件最大告警数"
    )


class IncidentMappingSerializer(serializers.Serializer):
    """事件字段映射"""
    title_template = serializers.CharField(
        default="{{ alert_name }} - {{ target }}",
        help_text="事件标题模板"
    )
    description_template = serializers.CharField(
        required=False,
        help_text="事件描述模板"
    )
    priority_mapping = serializers.DictField(
        default=dict,
        help_text="优先级映射（severity -> priority）"
    )
    custom_fields = serializers.DictField(
        default=dict,
        help_text="自定义字段映射"
    )


class IncidentNotificationSerializer(serializers.Serializer):
    """事件通知配置"""
    notify_on_create = serializers.BooleanField(
        default=True,
        help_text="创建时通知"
    )
    notify_on_update = serializers.BooleanField(
        default=False,
        help_text="更新时通知"
    )
    notify_on_close = serializers.BooleanField(
        default=True,
        help_text="关闭时通知"
    )
    notify_channels = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知渠道列表"
    )
    notify_roles = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知角色列表"
    )


class ITSMIntegrationSerializer(serializers.Serializer):
    """ITSM集成配置"""
    enabled = serializers.BooleanField(
        default=False,
        help_text="是否启用ITSM集成"
    )
    itsm_type = serializers.ChoiceField(
        choices=[
            ("bk_itsm", "蓝鲸ITSM"),
            ("servicenow", "ServiceNow"),
            ("jira", "Jira"),
            ("custom", "自定义"),
        ],
        default="bk_itsm",
        help_text="ITSM系统类型"
    )
    service_id = serializers.CharField(
        required=False,
        help_text="ITSM服务ID"
    )
    catalog_id = serializers.CharField(
        required=False,
        help_text="ITSM服务目录ID"
    )
    field_mapping = serializers.DictField(
        default=dict,
        help_text="字段映射配置"
    )


class IncidentNodeConfigSerializer(BaseNodeConfigSerializer):
    """故障事件节点配置"""
    node_type = serializers.CharField(default="incident", read_only=True)
    
    # 事件动作
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in IncidentAction],
        default="auto",
        help_text="事件动作"
    )
    
    # 事件分组配置
    grouping = IncidentGroupingSerializer(
        required=False,
        help_text="事件分组配置"
    )
    
    # 字段映射
    mapping = IncidentMappingSerializer(
        required=False,
        help_text="字段映射配置"
    )
    
    # 默认优先级
    default_priority = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in IncidentPriority],
        default="P3",
        help_text="默认优先级"
    )
    
    # 默认状态
    default_status = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in IncidentStatus],
        default="new",
        help_text="默认状态"
    )
    
    # 自动关闭配置
    auto_close = serializers.BooleanField(
        default=True,
        help_text="所有告警恢复时是否自动关闭事件"
    )
    auto_close_delay = serializers.IntegerField(
        default=300,
        help_text="自动关闭延迟时间（秒）"
    )
    
    # 通知配置
    notification = IncidentNotificationSerializer(
        required=False,
        help_text="事件通知配置"
    )
    
    # ITSM集成
    itsm = ITSMIntegrationSerializer(
        required=False,
        help_text="ITSM集成配置"
    )
    
    # 事件ID生成
    incident_id_template = serializers.CharField(
        default="INC-{{ biz_id }}-{{ timestamp }}",
        help_text="事件ID模板"
    )
    
    # 关联告警字段
    related_alerts_field = serializers.CharField(
        default="related_alerts",
        help_text="关联告警字段名"
    )
    
    # 事件输出字段
    incident_id_output_field = serializers.CharField(
        default="_incident_id",
        help_text="事件ID输出字段"
    )
    
    # 去重配置
    dedupe_enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用事件去重"
    )
    dedupe_key_fields = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="去重键字段列表"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("mysql", "MySQL"), ("elasticsearch", "Elasticsearch")],
        default="mysql",
        help_text="事件存储后端"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "incident" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `action` | string | 否 | "auto" | 事件动作 |
| `default_priority` | string | 否 | "P3" | 默认优先级 |
| `default_status` | string | 否 | "new" | 默认状态 |
| `auto_close` | boolean | 否 | true | 自动关闭 |
| `dedupe_enabled` | boolean | 否 | true | 启用去重 |

### 事件分组配置 (IncidentGrouping)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | boolean | 否 | true | 启用分组 |
| `grouping_fields` | array | 是 | - | 分组字段 |
| `grouping_window` | integer | 否 | 3600 | 时间窗口 |
| `max_alerts_per_incident` | integer | 否 | 100 | 最大告警数 |

### 字段映射配置 (IncidentMapping)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title_template` | string | 否 | 标题模板 |
| `description_template` | string | 否 | 描述模板 |
| `priority_mapping` | object | 否 | 优先级映射 |
| `custom_fields` | object | 否 | 自定义字段 |

### ITSM集成配置 (ITSMIntegration)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enabled` | boolean | 否 | 启用ITSM |
| `itsm_type` | string | 否 | ITSM类型 |
| `service_id` | string | 否 | 服务ID |
| `field_mapping` | object | 否 | 字段映射 |

### 事件动作说明

| 动作 | 说明 | 使用场景 |
|------|------|----------|
| `create` | 创建新事件 | 新告警到达 |
| `update` | 更新现有事件 | 追加告警 |
| `merge` | 合并到现有事件 | 相似告警合并 |
| `close` | 关闭事件 | 告警恢复 |
| `auto` | 自动选择 | 智能判断 |

### 事件优先级说明

| 优先级 | 说明 | SLA要求 |
|--------|------|---------|
| `P1` | 最高优先级 | 即时响应 |
| `P2` | 高优先级 | 30分钟内响应 |
| `P3` | 中优先级 | 2小时内响应 |
| `P4` | 低优先级 | 8小时内响应 |
| `P5` | 最低优先级 | 下个工作日 |

## JSON 配置示例

### 示例 1: 基础事件创建

```json
{
  "name": "basic_incident",
  "description": "基础故障事件创建",
  "enabled": true,
  "node_type": "incident",
  "action": "auto",
  "grouping": {
    "enabled": true,
    "grouping_fields": ["event.biz_id", "event.strategy_id"],
    "grouping_window": 3600,
    "max_alerts_per_incident": 100
  },
  "mapping": {
    "title_template": "[{{ event.severity_display }}] {{ event.alert_name }} - {{ event.target }}",
    "description_template": "告警目标: {{ event.target }}\n当前值: {{ event.current_value }}\n触发时间: {{ event.time }}",
    "priority_mapping": {
      "1": "P1",
      "2": "P2",
      "3": "P3"
    }
  },
  "default_priority": "P3",
  "default_status": "new",
  "auto_close": true,
  "auto_close_delay": 300,
  "notification": {
    "notify_on_create": true,
    "notify_on_close": true,
    "notify_channels": ["weixin"],
    "notify_roles": ["operator"]
  },
  "storage_backend": "mysql",
  "execution": {
    "timeout": 60
  }
}
```

### 示例 2: ITSM集成配置

```json
{
  "name": "itsm_incident",
  "description": "与蓝鲸ITSM集成的事件管理",
  "enabled": true,
  "node_type": "incident",
  "action": "auto",
  "grouping": {
    "enabled": true,
    "grouping_fields": [
      "event.biz_id",
      "event.alert_name",
      "event.dimensions.cluster"
    ],
    "grouping_window": 1800,
    "max_alerts_per_incident": 50
  },
  "mapping": {
    "title_template": "【故障】{{ event.biz_name }} - {{ event.alert_name }}",
    "description_template": "## 故障概况\n- **业务**: {{ event.biz_name }}\n- **告警名称**: {{ event.alert_name }}\n- **影响范围**: {{ event.target }}\n- **触发时间**: {{ event.time }}\n\n## 告警详情\n{{ event.description }}",
    "priority_mapping": {
      "1": "P1",
      "2": "P2",
      "3": "P3"
    },
    "custom_fields": {
      "biz_id": "{{ event.biz_id }}",
      "strategy_id": "{{ event.strategy_id }}",
      "alert_count": "{{ related_alerts | length }}"
    }
  },
  "itsm": {
    "enabled": true,
    "itsm_type": "bk_itsm",
    "service_id": "12345",
    "catalog_id": "incident_catalog",
    "field_mapping": {
      "title": "title",
      "description": "description",
      "priority": "urgency",
      "biz_id": "bk_biz_id"
    }
  },
  "notification": {
    "notify_on_create": true,
    "notify_on_update": true,
    "notify_on_close": true,
    "notify_channels": ["weixin", "mail"],
    "notify_roles": ["operator", "team_lead"]
  },
  "auto_close": true,
  "auto_close_delay": 600,
  "dedupe_enabled": true,
  "dedupe_key_fields": ["event.biz_id", "event.strategy_id", "event.target"],
  "storage_backend": "mysql",
  "execution": {
    "timeout": 120
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 高级事件聚合

```json
{
  "name": "advanced_incident",
  "description": "高级事件聚合配置",
  "enabled": true,
  "node_type": "incident",
  "action": "auto",
  "grouping": {
    "enabled": true,
    "grouping_fields": [
      "event.biz_id",
      "event.environment",
      "event.dimensions.service"
    ],
    "grouping_window": 7200,
    "max_alerts_per_incident": 200
  },
  "mapping": {
    "title_template": "[{{ event.environment | upper }}] {{ event.biz_name }} 服务故障 - {{ event.dimensions.service }}",
    "description_template": "### 故障影响\n- 环境: {{ event.environment }}\n- 服务: {{ event.dimensions.service }}\n- 告警数: {{ related_alerts | length }}\n- 首次告警: {{ first_alert_time }}\n- 最新告警: {{ last_alert_time }}\n\n### 受影响目标\n{% for target in affected_targets[:10] %}\n- {{ target }}\n{% endfor %}\n{% if affected_targets | length > 10 %}\n... 等共 {{ affected_targets | length }} 个目标\n{% endif %}",
    "priority_mapping": {
      "1": "P1",
      "2": "P1",
      "3": "P2"
    },
    "custom_fields": {
      "environment": "{{ event.environment }}",
      "service": "{{ event.dimensions.service }}",
      "affected_count": "{{ affected_targets | length }}",
      "alert_ids": "{{ related_alerts | map(attribute='alert_id') | join(',') }}"
    }
  },
  "default_priority": "P2",
  "default_status": "new",
  "auto_close": true,
  "auto_close_delay": 1800,
  "notification": {
    "notify_on_create": true,
    "notify_on_update": false,
    "notify_on_close": true,
    "notify_channels": ["weixin", "mail", "sms"],
    "notify_roles": ["sre", "service_owner"]
  },
  "itsm": {
    "enabled": false
  },
  "incident_id_template": "INC-{{ biz_id }}-{{ environment }}-{{ timestamp }}",
  "related_alerts_field": "alerts",
  "incident_id_output_field": "_incident_id",
  "dedupe_enabled": true,
  "dedupe_key_fields": [
    "event.biz_id",
    "event.environment",
    "event.dimensions.service"
  ],
  "storage_backend": "elasticsearch",
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      },
      {
        "field": "event.severity",
        "operator": "gte",
        "value": 4
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

1. **告警聚合**：将相关告警聚合为单个事件
2. **工单创建**：自动创建ITSM工单
3. **故障管理**：统一管理故障事件生命周期
4. **影响分析**：分析故障影响范围
5. **SLA管理**：基于优先级管理响应时间
6. **趋势分析**：分析故障事件趋势
7. **报告生成**：生成故障报告

## 注意事项

1. **分组策略**：
   - 选择合适的分组字段
   - 分组窗口不宜过长
   - 限制每个事件的告警数

2. **优先级映射**：
   - 合理映射告警级别到事件优先级
   - 考虑业务重要性
   - 遵循SLA要求

3. **ITSM集成**：
   - 确保字段映射正确
   - 测试工单创建流程
   - 注意API调用频率

4. **自动关闭**：
   - 设置合理的延迟时间
   - 避免误关闭仍在处理的事件
   - 考虑人工确认机制

5. **去重配置**：
   - 选择合适的去重键
   - 避免创建重复事件
   - 注意去重窗口设置

6. **通知配置**：
   - 创建时通知相关人员
   - 关闭时发送总结
   - 避免过度通知

7. **存储选择**：
   - MySQL适合结构化存储
   - ES适合检索和分析
   - 考虑数据保留策略

8. **模板设计**：
   - 标题简洁明了
   - 描述包含必要信息
   - 支持Markdown格式

## 相关节点

- **上游节点**：
  - Converge（收敛节点）：收敛后创建事件
  - Dedupe（去重节点）：去重后创建事件
  - Filter（过滤节点）：过滤后创建事件

- **下游节点**：
  - Notification（通知节点）：事件通知
  - Webhook（回调节点）：触发外部系统
  - Storage（存储节点）：存储事件详情

### 典型组合模式

1. **Converge → Incident → Notification**
   - 收敛 → 创建事件 → 通知

2. **Filter → Incident → Webhook**
   - 过滤 → 创建事件 → 外部回调

3. **Dedupe → Incident → Storage**
   - 去重 → 创建事件 → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
