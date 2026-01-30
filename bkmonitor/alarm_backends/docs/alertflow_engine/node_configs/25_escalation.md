# Escalation Node Configuration (升级节点配置)

## 节点类型
- **NodeType**: `escalation`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 告警升级处理，超时未处理时自动升级通知人员或提高告警级别

## 配置 Schema

### EscalationNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class EscalationType(str, Enum):
    """升级类型"""
    TIMEOUT = "timeout"           # 超时升级
    NO_ACK = "no_ack"             # 未确认升级
    NO_RESOLVE = "no_resolve"     # 未解决升级
    SEVERITY = "severity"         # 级别升级
    MANUAL = "manual"             # 手动升级


class EscalationAction(str, Enum):
    """升级动作"""
    NOTIFY = "notify"             # 通知升级
    SEVERITY_UP = "severity_up"   # 提升级别
    REASSIGN = "reassign"         # 重新分配
    CALLBACK = "callback"         # 触发回调


class EscalationLevelSerializer(serializers.Serializer):
    """升级层级配置"""
    level = serializers.IntegerField(
        min_value=1,
        help_text="升级层级（1为第一级）"
    )
    name = serializers.CharField(help_text="层级名称")
    
    # 触发条件
    trigger_after = serializers.IntegerField(
        help_text="距离上一级多久后触发（秒）"
    )
    
    # 通知配置
    notify_roles = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知角色列表"
    )
    notify_users = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知用户列表"
    )
    notify_channels = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知渠道列表"
    )
    
    # 升级动作
    actions = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[(e.value, e.name) for e in EscalationAction]
        ),
        default=["notify"],
        help_text="升级动作列表"
    )
    
    # 级别调整
    severity_delta = serializers.IntegerField(
        default=0,
        help_text="级别调整幅度（负数表示升级）"
    )
    
    # 重新分配
    reassign_to = serializers.CharField(
        required=False,
        help_text="重新分配给（角色或用户）"
    )
    
    # 回调配置
    callback_config = serializers.DictField(
        default=dict,
        required=False,
        help_text="回调配置"
    )


class EscalationPolicySerializer(serializers.Serializer):
    """升级策略配置"""
    name = serializers.CharField(help_text="策略名称")
    description = serializers.CharField(
        default="",
        required=False,
        help_text="策略描述"
    )
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用"
    )
    
    # 升级类型
    escalation_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in EscalationType],
        help_text="升级类型"
    )
    
    # 适用条件
    apply_condition = serializers.DictField(
        default=dict,
        required=False,
        help_text="策略适用条件"
    )
    
    # 升级层级
    levels = EscalationLevelSerializer(many=True, help_text="升级层级列表")
    
    # 最大升级次数
    max_escalations = serializers.IntegerField(
        default=3,
        help_text="最大升级次数"
    )
    
    # 升级间隔
    min_interval = serializers.IntegerField(
        default=300,
        help_text="最小升级间隔（秒）"
    )


class EscalationNodeConfigSerializer(BaseNodeConfigSerializer):
    """升级节点配置"""
    node_type = serializers.CharField(default="escalation", read_only=True)
    
    # 升级策略
    policies = EscalationPolicySerializer(many=True, help_text="升级策略列表")
    
    # 默认策略
    default_policy = serializers.CharField(
        required=False,
        help_text="默认策略名称"
    )
    
    # 全局配置
    global_timeout = serializers.IntegerField(
        default=3600,
        help_text="全局超时时间（秒）"
    )
    
    # 升级检查间隔
    check_interval = serializers.IntegerField(
        default=60,
        help_text="升级检查间隔（秒）"
    )
    
    # 排除条件
    exclude_conditions = serializers.ListField(
        child=serializers.DictField(),
        default=list,
        help_text="排除升级的条件列表"
    )
    
    # 升级记录
    record_escalation = serializers.BooleanField(
        default=True,
        help_text="是否记录升级历史"
    )
    escalation_field = serializers.CharField(
        default="escalation_history",
        help_text="升级历史字段名"
    )
    
    # 当前升级级别字段
    current_level_field = serializers.CharField(
        default="escalation_level",
        help_text="当前升级级别字段名"
    )
    
    # 通知模板
    notification_templates = serializers.DictField(
        default=dict,
        help_text="各级别的通知模板配置"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("mysql", "MySQL")],
        default="redis",
        help_text="升级状态存储后端"
    )
    
    def validate_policies(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一条升级策略")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "escalation" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `policies` | array | 是 | - | 升级策略列表 |
| `default_policy` | string | 否 | - | 默认策略 |
| `global_timeout` | integer | 否 | 3600 | 全局超时 |
| `check_interval` | integer | 否 | 60 | 检查间隔 |
| `record_escalation` | boolean | 否 | true | 记录升级历史 |

### 升级策略配置 (EscalationPolicy)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 策略名称 |
| `escalation_type` | string | 是 | - | 升级类型 |
| `apply_condition` | object | 否 | {} | 适用条件 |
| `levels` | array | 是 | - | 升级层级 |
| `max_escalations` | integer | 否 | 3 | 最大升级次数 |
| `min_interval` | integer | 否 | 300 | 最小间隔 |

### 升级层级配置 (EscalationLevel)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `level` | integer | 是 | - | 层级号 |
| `name` | string | 是 | - | 层级名称 |
| `trigger_after` | integer | 是 | - | 触发时间 |
| `notify_roles` | array | 否 | [] | 通知角色 |
| `notify_users` | array | 否 | [] | 通知用户 |
| `notify_channels` | array | 否 | [] | 通知渠道 |
| `actions` | array | 否 | ["notify"] | 升级动作 |
| `severity_delta` | integer | 否 | 0 | 级别调整 |

### 升级类型说明

| 类型 | 说明 | 触发条件 |
|------|------|----------|
| `timeout` | 超时升级 | 告警存在超过指定时间 |
| `no_ack` | 未确认升级 | 告警未被确认 |
| `no_resolve` | 未解决升级 | 告警未被解决 |
| `severity` | 级别升级 | 达到级别条件 |
| `manual` | 手动升级 | 人工触发 |

### 升级动作说明

| 动作 | 说明 | 效果 |
|------|------|------|
| `notify` | 通知升级 | 通知更高级别人员 |
| `severity_up` | 提升级别 | 提高告警严重程度 |
| `reassign` | 重新分配 | 分配给其他处理人 |
| `callback` | 触发回调 | 调用外部系统 |

## JSON 配置示例

### 示例 1: 超时分级升级

```json
{
  "name": "timeout_escalation",
  "description": "超时未处理自动升级通知",
  "enabled": true,
  "node_type": "escalation",
  "policies": [
    {
      "name": "default_escalation",
      "description": "默认超时升级策略",
      "enabled": true,
      "escalation_type": "timeout",
      "levels": [
        {
          "level": 1,
          "name": "一线运维",
          "trigger_after": 900,
          "notify_roles": ["operator"],
          "notify_channels": ["weixin"],
          "actions": ["notify"]
        },
        {
          "level": 2,
          "name": "二线运维",
          "trigger_after": 1800,
          "notify_roles": ["senior_operator", "team_lead"],
          "notify_channels": ["weixin", "sms"],
          "actions": ["notify", "severity_up"],
          "severity_delta": -1
        },
        {
          "level": 3,
          "name": "运维经理",
          "trigger_after": 3600,
          "notify_roles": ["ops_manager"],
          "notify_users": ["manager@example.com"],
          "notify_channels": ["weixin", "sms", "voice"],
          "actions": ["notify", "severity_up"],
          "severity_delta": -1
        }
      ],
      "max_escalations": 3,
      "min_interval": 600
    }
  ],
  "default_policy": "default_escalation",
  "global_timeout": 86400,
  "check_interval": 60,
  "record_escalation": true,
  "storage_backend": "redis",
  "execution": {
    "timeout": 60
  }
}
```

### 示例 2: 条件化升级策略

```json
{
  "name": "conditional_escalation",
  "description": "基于告警级别和业务的条件化升级",
  "enabled": true,
  "node_type": "escalation",
  "policies": [
    {
      "name": "critical_escalation",
      "description": "致命告警快速升级",
      "enabled": true,
      "escalation_type": "no_ack",
      "apply_condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "eq",
            "value": 1
          }
        ]
      },
      "levels": [
        {
          "level": 1,
          "name": "值班人员",
          "trigger_after": 300,
          "notify_roles": ["oncall"],
          "notify_channels": ["voice", "sms"],
          "actions": ["notify"]
        },
        {
          "level": 2,
          "name": "技术负责人",
          "trigger_after": 600,
          "notify_roles": ["tech_lead"],
          "notify_channels": ["voice", "sms", "weixin"],
          "actions": ["notify", "reassign"],
          "reassign_to": "tech_lead"
        }
      ],
      "max_escalations": 2,
      "min_interval": 300
    },
    {
      "name": "normal_escalation",
      "description": "普通告警标准升级",
      "enabled": true,
      "escalation_type": "timeout",
      "apply_condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "gte",
            "value": 2
          }
        ]
      },
      "levels": [
        {
          "level": 1,
          "name": "运维人员",
          "trigger_after": 1800,
          "notify_roles": ["operator"],
          "notify_channels": ["weixin"],
          "actions": ["notify"]
        },
        {
          "level": 2,
          "name": "运维主管",
          "trigger_after": 3600,
          "notify_roles": ["ops_supervisor"],
          "notify_channels": ["weixin", "mail"],
          "actions": ["notify"]
        }
      ],
      "max_escalations": 2,
      "min_interval": 900
    }
  ],
  "global_timeout": 86400,
  "check_interval": 60,
  "exclude_conditions": [
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
  ],
  "record_escalation": true,
  "escalation_field": "escalation_log",
  "current_level_field": "current_escalation_level",
  "notification_templates": {
    "1": "escalation_level1_template",
    "2": "escalation_level2_template",
    "3": "escalation_level3_template"
  },
  "storage_backend": "redis",
  "execution": {
    "timeout": 120
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 复合升级策略（带回调）

```json
{
  "name": "complex_escalation",
  "description": "复合升级策略，包含回调和重分配",
  "enabled": true,
  "node_type": "escalation",
  "policies": [
    {
      "name": "production_escalation",
      "description": "生产环境升级策略",
      "enabled": true,
      "escalation_type": "no_resolve",
      "apply_condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.environment",
            "operator": "eq",
            "value": "production"
          },
          {
            "field": "event.biz_importance",
            "operator": "in",
            "value": ["high", "critical"]
          }
        ]
      },
      "levels": [
        {
          "level": 1,
          "name": "一线支持",
          "trigger_after": 600,
          "notify_roles": ["l1_support"],
          "notify_channels": ["weixin", "sms"],
          "actions": ["notify", "callback"],
          "callback_config": {
            "url": "http://itsm/api/ticket/update",
            "method": "POST",
            "body": {
              "ticket_id": "{{ event.ticket_id }}",
              "status": "escalated",
              "level": 1
            }
          }
        },
        {
          "level": 2,
          "name": "二线专家",
          "trigger_after": 1200,
          "notify_roles": ["l2_expert"],
          "notify_channels": ["voice", "sms", "weixin"],
          "actions": ["notify", "severity_up", "reassign", "callback"],
          "severity_delta": -1,
          "reassign_to": "l2_expert",
          "callback_config": {
            "url": "http://itsm/api/ticket/escalate",
            "method": "POST",
            "body": {
              "ticket_id": "{{ event.ticket_id }}",
              "escalate_to": "l2_team",
              "priority": "high"
            }
          }
        },
        {
          "level": 3,
          "name": "管理层",
          "trigger_after": 2400,
          "notify_roles": ["management"],
          "notify_users": ["cto@example.com", "vp_ops@example.com"],
          "notify_channels": ["voice", "sms", "weixin", "mail"],
          "actions": ["notify", "callback"],
          "callback_config": {
            "url": "http://incident-management/api/major_incident",
            "method": "POST",
            "body": {
              "alert_id": "{{ event.alert_id }}",
              "severity": "major",
              "notify_stakeholders": true
            }
          }
        }
      ],
      "max_escalations": 3,
      "min_interval": 300
    }
  ],
  "default_policy": "production_escalation",
  "global_timeout": 172800,
  "check_interval": 30,
  "exclude_conditions": [
    {
      "field": "event.is_acknowledged",
      "operator": "eq",
      "value": true
    }
  ],
  "record_escalation": true,
  "storage_backend": "mysql",
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.skip_escalation",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 180
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true,
    "notify_on_error": true
  }
}
```

## 使用场景

1. **超时升级**：告警超过指定时间未处理自动升级
2. **未确认升级**：告警未被确认时逐级升级
3. **未解决升级**：告警长时间未解决自动升级
4. **分级通知**：根据处理时长通知不同级别人员
5. **自动重分配**：超时后自动重新分配处理人
6. **级别提升**：长时间未处理自动提升告警级别
7. **ITSM集成**：升级时自动更新工单状态

## 注意事项

1. **升级层级设计**：
   - 层级数量不宜过多（建议3-5级）
   - 每级触发时间应递增
   - 明确各级的处理责任

2. **通知配置**：
   - 高级别升级建议使用语音/短信
   - 避免过度通知造成疲劳
   - 注意非工作时间的通知策略

3. **检查间隔**：
   - `check_interval` 影响升级及时性
   - 间隔过短会增加系统负载
   - 建议30-60秒

4. **排除条件**：
   - 已恢复/已确认的告警不应升级
   - 被屏蔽的告警不应升级
   - 合理配置 `exclude_conditions`

5. **回调配置**：
   - 回调失败不应阻塞升级流程
   - 配置合理的超时时间
   - 记录回调结果便于排查

6. **存储选择**：
   - Redis适合短期状态存储
   - MySQL适合长期升级记录
   - 考虑升级历史的保留需求

7. **最大升级次数**：
   - `max_escalations` 防止无限升级
   - 达到上限后应有兜底处理
   - 建议配置告警通知

8. **与其他节点配合**：
   - 升级前应检查告警状态
   - 升级后可触发额外通知
   - 注意与收敛节点的配合

## 相关节点

- **上游节点**：
  - Shield（屏蔽节点）：屏蔽后检查升级
  - Acknowledge（确认节点）：确认状态影响升级
  - Recovery（恢复节点）：恢复状态影响升级

- **下游节点**：
  - Notification（通知节点）：发送升级通知
  - Webhook（回调节点）：触发外部系统
  - Storage（存储节点）：存储升级记录

### 典型组合模式

1. **Shield → Escalation → Notification**
   - 屏蔽 → 升级检查 → 通知

2. **Acknowledge → Escalation → Webhook**
   - 确认 → 升级 → 外部回调

3. **Recovery → Escalation → Storage**
   - 恢复 → 升级（如未恢复） → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
