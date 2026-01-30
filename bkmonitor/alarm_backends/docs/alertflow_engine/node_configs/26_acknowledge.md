# Acknowledge Node Configuration (确认节点配置)

## 节点类型
- **NodeType**: `acknowledge`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 告警确认处理，记录确认人、确认时间和确认备注

## 配置 Schema

### AcknowledgeNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class AckSource(str, Enum):
    """确认来源"""
    MANUAL = "manual"           # 人工确认
    AUTO = "auto"               # 自动确认
    API = "api"                 # API确认
    WEBHOOK = "webhook"         # Webhook确认
    ITSM = "itsm"               # ITSM系统确认


class AckAction(str, Enum):
    """确认动作"""
    ACKNOWLEDGE = "acknowledge"   # 确认
    UNACKNOWLEDGE = "unacknowledge"  # 取消确认
    REASSIGN = "reassign"         # 重新分配


class AckNotificationSerializer(serializers.Serializer):
    """确认通知配置"""
    notify_on_ack = serializers.BooleanField(
        default=True,
        help_text="确认时是否发送通知"
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
    notification_template = serializers.CharField(
        required=False,
        help_text="通知模板ID"
    )


class AutoAckConfigSerializer(serializers.Serializer):
    """自动确认配置"""
    enabled = serializers.BooleanField(
        default=False,
        help_text="是否启用自动确认"
    )
    conditions = serializers.ListField(
        child=serializers.DictField(),
        default=list,
        help_text="自动确认条件列表"
    )
    auto_ack_message = serializers.CharField(
        default="系统自动确认",
        help_text="自动确认备注"
    )
    delay_seconds = serializers.IntegerField(
        default=0,
        help_text="延迟确认时间（秒）"
    )


class AckTimeoutConfigSerializer(serializers.Serializer):
    """确认超时配置"""
    enabled = serializers.BooleanField(
        default=False,
        help_text="是否启用确认超时"
    )
    timeout_seconds = serializers.IntegerField(
        default=3600,
        help_text="确认超时时间（秒）"
    )
    timeout_action = serializers.ChoiceField(
        choices=[
            ("escalate", "升级"),
            ("auto_ack", "自动确认"),
            ("notify", "通知"),
        ],
        default="escalate",
        help_text="超时动作"
    )


class AcknowledgeNodeConfigSerializer(BaseNodeConfigSerializer):
    """确认节点配置"""
    node_type = serializers.CharField(default="acknowledge", read_only=True)
    
    # 确认动作
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AckAction],
        default="acknowledge",
        help_text="确认动作"
    )
    
    # 确认来源字段
    source_field = serializers.CharField(
        default="ack_source",
        help_text="确认来源字段名"
    )
    
    # 确认人字段
    ack_user_field = serializers.CharField(
        default="event.ack_user",
        help_text="确认人字段路径"
    )
    
    # 确认备注字段
    ack_message_field = serializers.CharField(
        default="event.ack_message",
        help_text="确认备注字段路径"
    )
    
    # 确认时间字段
    ack_time_field = serializers.CharField(
        default="ack_time",
        help_text="确认时间字段名"
    )
    
    # 确认状态字段
    ack_status_field = serializers.CharField(
        default="is_acknowledged",
        help_text="确认状态字段名"
    )
    
    # 确认通知配置
    notification = AckNotificationSerializer(
        required=False,
        help_text="确认通知配置"
    )
    
    # 自动确认配置
    auto_ack = AutoAckConfigSerializer(
        required=False,
        help_text="自动确认配置"
    )
    
    # 确认超时配置
    timeout = AckTimeoutConfigSerializer(
        required=False,
        help_text="确认超时配置"
    )
    
    # 确认历史记录
    record_history = serializers.BooleanField(
        default=True,
        help_text="是否记录确认历史"
    )
    history_field = serializers.CharField(
        default="ack_history",
        help_text="确认历史字段名"
    )
    
    # 允许重新分配
    allow_reassign = serializers.BooleanField(
        default=True,
        help_text="是否允许重新分配"
    )
    reassign_roles = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="可重新分配的角色列表"
    )
    
    # 确认权限
    require_permission = serializers.BooleanField(
        default=True,
        help_text="是否需要确认权限"
    )
    allowed_roles = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="允许确认的角色列表"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("mysql", "MySQL")],
        default="redis",
        help_text="确认状态存储后端"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "acknowledge" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `action` | string | 否 | "acknowledge" | 确认动作 |
| `ack_user_field` | string | 否 | "event.ack_user" | 确认人字段 |
| `ack_message_field` | string | 否 | "event.ack_message" | 备注字段 |
| `record_history` | boolean | 否 | true | 记录历史 |
| `allow_reassign` | boolean | 否 | true | 允许重分配 |
| `require_permission` | boolean | 否 | true | 需要权限 |

### 确认通知配置 (AckNotification)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `notify_on_ack` | boolean | 否 | true | 确认时通知 |
| `notify_channels` | array | 否 | [] | 通知渠道 |
| `notify_roles` | array | 否 | [] | 通知角色 |
| `notification_template` | string | 否 | - | 通知模板 |

### 自动确认配置 (AutoAckConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | boolean | 否 | false | 启用自动确认 |
| `conditions` | array | 否 | [] | 确认条件 |
| `auto_ack_message` | string | 否 | "系统自动确认" | 自动确认备注 |
| `delay_seconds` | integer | 否 | 0 | 延迟时间 |

### 确认超时配置 (AckTimeoutConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | boolean | 否 | false | 启用超时 |
| `timeout_seconds` | integer | 否 | 3600 | 超时时间 |
| `timeout_action` | string | 否 | "escalate" | 超时动作 |

### 确认动作说明

| 动作 | 说明 | 效果 |
|------|------|------|
| `acknowledge` | 确认 | 标记告警已确认 |
| `unacknowledge` | 取消确认 | 取消确认状态 |
| `reassign` | 重新分配 | 分配给其他人 |

### 确认来源说明

| 来源 | 说明 | 场景 |
|------|------|------|
| `manual` | 人工确认 | 通过页面确认 |
| `auto` | 自动确认 | 满足条件自动确认 |
| `api` | API确认 | 通过API调用确认 |
| `webhook` | Webhook确认 | 外部系统回调 |
| `itsm` | ITSM确认 | ITSM工单系统同步 |

## JSON 配置示例

### 示例 1: 基础告警确认

```json
{
  "name": "basic_acknowledge",
  "description": "基础告警确认处理",
  "enabled": true,
  "node_type": "acknowledge",
  "action": "acknowledge",
  "ack_user_field": "event.ack_user",
  "ack_message_field": "event.ack_message",
  "ack_time_field": "ack_time",
  "ack_status_field": "is_acknowledged",
  "notification": {
    "notify_on_ack": true,
    "notify_channels": ["weixin"],
    "notify_roles": ["operator", "team_lead"],
    "notification_template": "ack_notification_template"
  },
  "record_history": true,
  "history_field": "ack_history",
  "require_permission": true,
  "allowed_roles": ["operator", "admin"],
  "storage_backend": "redis",
  "execution": {
    "timeout": 30
  }
}
```

### 示例 2: 自动确认配置

```json
{
  "name": "auto_acknowledge",
  "description": "满足条件自动确认告警",
  "enabled": true,
  "node_type": "acknowledge",
  "action": "acknowledge",
  "auto_ack": {
    "enabled": true,
    "conditions": [
      {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "gte",
            "value": 3
          },
          {
            "field": "event.auto_ack_enabled",
            "operator": "eq",
            "value": true
          }
        ]
      }
    ],
    "auto_ack_message": "低级别告警自动确认",
    "delay_seconds": 60
  },
  "source_field": "ack_source",
  "notification": {
    "notify_on_ack": false
  },
  "record_history": true,
  "storage_backend": "redis",
  "execution": {
    "timeout": 30
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 确认超时与重分配

```json
{
  "name": "timeout_acknowledge",
  "description": "带超时和重分配功能的确认",
  "enabled": true,
  "node_type": "acknowledge",
  "action": "acknowledge",
  "ack_user_field": "event.ack_user",
  "ack_message_field": "event.ack_message",
  "timeout": {
    "enabled": true,
    "timeout_seconds": 1800,
    "timeout_action": "escalate"
  },
  "notification": {
    "notify_on_ack": true,
    "notify_channels": ["weixin", "mail"],
    "notify_roles": ["operator", "supervisor"],
    "notification_template": "ack_with_timeout_template"
  },
  "allow_reassign": true,
  "reassign_roles": ["senior_operator", "team_lead", "ops_manager"],
  "record_history": true,
  "history_field": "acknowledgement_log",
  "require_permission": true,
  "allowed_roles": ["operator", "senior_operator", "admin"],
  "storage_backend": "mysql",
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      },
      {
        "field": "event.status",
        "operator": "eq",
        "value": "RECOVERED"
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

1. **人工确认**：运维人员确认已收到告警
2. **自动确认**：低级别告警自动确认
3. **超时处理**：未确认告警超时升级
4. **责任分配**：确认并分配处理责任人
5. **审计追踪**：记录完整的确认历史
6. **ITSM集成**：与工单系统同步确认状态
7. **批量确认**：批量确认多个相似告警

## 注意事项

1. **确认权限**：
   - 建议启用 `require_permission`
   - 明确允许确认的角色列表
   - 防止越权操作

2. **自动确认**：
   - 自动确认适合低级别告警
   - 配置合理的条件避免误确认
   - 可设置延迟防止抖动

3. **确认超时**：
   - 超时后可升级或自动确认
   - 超时时间根据SLA设置
   - 及时通知避免遗漏

4. **历史记录**：
   - 建议开启 `record_history`
   - 便于审计和问题追溯
   - 注意存储空间占用

5. **重新分配**：
   - 明确可分配的角色列表
   - 分配后通知相关人员
   - 记录分配历史

6. **通知配置**：
   - 确认后通知相关人员
   - 避免过度通知
   - 选择合适的通知渠道

7. **存储选择**：
   - Redis适合短期状态
   - MySQL适合长期记录
   - 根据审计需求选择

8. **与其他节点配合**：
   - 确认状态影响升级判断
   - 确认后可触发后续流程
   - 注意状态同步

## 相关节点

- **上游节点**：
  - Notification（通知节点）：通知后等待确认
  - Escalation（升级节点）：升级后确认
  - Router（路由节点）：路由到确认流程

- **下游节点**：
  - Escalation（升级节点）：未确认时升级
  - Action（动作节点）：确认后执行动作
  - Recovery（恢复节点）：确认后检查恢复

### 典型组合模式

1. **Notification → Acknowledge → Escalation**
   - 通知 → 确认 → 升级（如未确认）

2. **Router → Acknowledge → Action**
   - 路由 → 确认 → 执行动作

3. **Acknowledge → Recovery → Storage**
   - 确认 → 恢复检查 → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
