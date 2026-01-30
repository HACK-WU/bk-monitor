# Notification Node Configuration (通知节点配置)

## 节点类型
- **NodeType**: `notification`
- **分类**: ACTION (动作类)
- **功能**: 发送告警通知，支持多种通知渠道和模板配置

## 配置 Schema

### NotificationNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class NotifyChannel(str, Enum):
    """通知渠道"""
    WEIXIN = "weixin"           # 企业微信
    MAIL = "mail"               # 邮件
    SMS = "sms"                 # 短信
    VOICE = "voice"             # 语音电话
    WECOM_BOT = "wecom_bot"     # 企业微信机器人
    WEBHOOK = "webhook"         # Webhook
    SLACK = "slack"             # Slack
    DINGTALK = "dingtalk"       # 钉钉
    FEISHU = "feishu"           # 飞书
    CUSTOM = "custom"           # 自定义渠道


class NotifyPhase(str, Enum):
    """通知阶段"""
    FIRING = "firing"           # 告警触发时
    RECOVERED = "recovered"     # 告警恢复时
    ACK = "ack"                 # 告警确认时
    CLOSED = "closed"           # 告警关闭时


class ReceiverType(str, Enum):
    """接收人类型"""
    USER = "user"               # 用户
    GROUP = "group"             # 用户组
    ROLE = "role"               # 角色
    DUTY = "duty"               # 轮值组
    DYNAMIC = "dynamic"         # 动态获取


class ReceiverConfigSerializer(serializers.Serializer):
    """接收人配置"""
    type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ReceiverType],
        help_text="接收人类型"
    )
    id = serializers.CharField(
        required=False,
        help_text="接收人ID（type=user/group/role/duty时使用）"
    )
    field = serializers.CharField(
        required=False,
        help_text="动态字段路径（type=dynamic时使用）"
    )
    fallback = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="备选接收人列表"
    )


class ChannelConfigSerializer(serializers.Serializer):
    """通知渠道配置"""
    channel = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in NotifyChannel],
        help_text="通知渠道"
    )
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用该渠道"
    )
    
    # 模板配置
    title_template = serializers.CharField(
        required=False,
        help_text="标题模板"
    )
    content_template = serializers.CharField(
        required=False,
        help_text="内容模板"
    )
    
    # 渠道特定配置
    webhook_url = serializers.CharField(
        required=False,
        help_text="Webhook URL（channel=webhook/wecom_bot时使用）"
    )
    mentioned_list = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="@提醒列表（机器人通知使用）"
    )
    
    # 优先级和限制
    priority = serializers.IntegerField(
        default=0,
        help_text="发送优先级"
    )
    rate_limit = serializers.IntegerField(
        default=0,
        help_text="发送频率限制（条/分钟，0=不限制）"
    )


class NotifyPhaseConfigSerializer(serializers.Serializer):
    """通知阶段配置"""
    phase = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in NotifyPhase],
        help_text="通知阶段"
    )
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用该阶段通知"
    )
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="该阶段使用的渠道列表（为空则使用全局配置）"
    )
    template_id = serializers.CharField(
        required=False,
        help_text="该阶段使用的模板ID"
    )


class NotificationNodeConfigSerializer(BaseNodeConfigSerializer):
    """通知节点配置"""
    node_type = serializers.CharField(default="notification", read_only=True)
    
    # 通知渠道配置
    channels = ChannelConfigSerializer(many=True, help_text="通知渠道配置列表")
    
    # 接收人配置
    receivers = ReceiverConfigSerializer(many=True, help_text="接收人配置列表")
    
    # 通知阶段配置
    notify_phases = NotifyPhaseConfigSerializer(
        many=True,
        required=False,
        help_text="通知阶段配置"
    )
    
    # 默认模板
    default_title_template = serializers.CharField(
        default="[{{ severity_display }}] {{ alert_name }} - {{ target }}",
        help_text="默认标题模板"
    )
    default_content_template = serializers.CharField(
        default=None,
        required=False,
        allow_null=True,
        help_text="默认内容模板"
    )
    
    # 模板引擎
    template_engine = serializers.ChoiceField(
        choices=[("jinja2", "Jinja2"), ("django", "Django")],
        default="jinja2",
        help_text="模板引擎类型"
    )
    
    # 告警聚合通知
    aggregate_notifications = serializers.BooleanField(
        default=False,
        help_text="是否聚合多条告警为一条通知"
    )
    aggregate_window = serializers.IntegerField(
        default=60,
        help_text="聚合窗口（秒）"
    )
    aggregate_max_count = serializers.IntegerField(
        default=10,
        help_text="单次聚合最大告警数"
    )
    
    # 重试配置
    retry_enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用发送重试"
    )
    retry_count = serializers.IntegerField(
        default=3,
        help_text="最大重试次数"
    )
    retry_interval = serializers.IntegerField(
        default=60,
        help_text="重试间隔（秒）"
    )
    
    # 发送限制
    global_rate_limit = serializers.IntegerField(
        default=0,
        help_text="全局发送频率限制（条/分钟，0=不限制）"
    )
    
    # 免打扰配置
    silence_config = serializers.DictField(
        default=dict,
        required=False,
        help_text="免打扰时段配置"
    )
    
    def validate_channels(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一个通知渠道")
        return value
    
    def validate_receivers(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少配置一个接收人")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "notification" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `channels` | array | 是 | - | 通知渠道配置 |
| `receivers` | array | 是 | - | 接收人配置 |
| `notify_phases` | array | 否 | - | 通知阶段配置 |
| `default_title_template` | string | 否 | 见默认 | 默认标题模板 |
| `default_content_template` | string | 否 | null | 默认内容模板 |
| `template_engine` | string | 否 | "jinja2" | 模板引擎 |
| `aggregate_notifications` | boolean | 否 | false | 聚合通知 |
| `aggregate_window` | integer | 否 | 60 | 聚合窗口 |
| `retry_enabled` | boolean | 否 | true | 启用重试 |
| `retry_count` | integer | 否 | 3 | 重试次数 |
| `global_rate_limit` | integer | 否 | 0 | 全局限流 |

### 通知渠道配置 (ChannelConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `channel` | string | 是 | - | 渠道类型 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `title_template` | string | 否 | - | 标题模板 |
| `content_template` | string | 否 | - | 内容模板 |
| `webhook_url` | string | 否 | - | Webhook URL |
| `mentioned_list` | array | 否 | - | @提醒列表 |
| `priority` | integer | 否 | 0 | 优先级 |
| `rate_limit` | integer | 否 | 0 | 频率限制 |

### 接收人配置 (ReceiverConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 接收人类型 |
| `id` | string | 否 | 接收人ID |
| `field` | string | 否 | 动态字段路径 |
| `fallback` | array | 否 | 备选接收人 |

### 通知阶段配置 (NotifyPhaseConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `phase` | string | 是 | 通知阶段 |
| `enabled` | boolean | 否 | 是否启用 |
| `channels` | array | 否 | 使用的渠道 |
| `template_id` | string | 否 | 模板ID |

### 通知渠道类型

| 渠道 | 说明 | 特殊配置 |
|------|------|----------|
| `weixin` | 企业微信应用消息 | - |
| `mail` | 邮件 | - |
| `sms` | 短信 | - |
| `voice` | 语音电话 | - |
| `wecom_bot` | 企业微信机器人 | webhook_url |
| `webhook` | 通用Webhook | webhook_url |
| `slack` | Slack | webhook_url |
| `dingtalk` | 钉钉 | webhook_url |
| `feishu` | 飞书 | webhook_url |
| `custom` | 自定义 | - |

### 接收人类型说明

| 类型 | 说明 | id格式 |
|------|------|--------|
| `user` | 指定用户 | 用户名 |
| `group` | 用户组 | 组ID |
| `role` | 角色 | 角色ID |
| `duty` | 轮值组 | 轮值组ID |
| `dynamic` | 动态获取 | - |

### 通知阶段说明

| 阶段 | 说明 | 触发时机 |
|------|------|----------|
| `firing` | 触发通知 | 告警产生时 |
| `recovered` | 恢复通知 | 告警恢复时 |
| `ack` | 确认通知 | 告警被确认时 |
| `closed` | 关闭通知 | 告警被关闭时 |

## JSON 配置示例

### 示例 1: 多渠道告警通知

```json
{
  "name": "multi_channel_notification",
  "description": "多渠道告警通知，根据级别选择不同渠道",
  "enabled": true,
  "node_type": "notification",
  "channels": [
    {
      "channel": "weixin",
      "enabled": true,
      "title_template": "[{{ event.severity_display }}] {{ event.alert_name }}",
      "content_template": "告警目标：{{ event.target }}\n当前值：{{ event.current_value }}\n触发时间：{{ event.time | datetime }}\n\n{{ event.description }}",
      "priority": 10
    },
    {
      "channel": "mail",
      "enabled": true,
      "title_template": "[蓝鲸监控] {{ event.alert_name }} - {{ event.target }}",
      "priority": 5
    },
    {
      "channel": "sms",
      "enabled": true,
      "content_template": "[{{ event.severity_display }}]{{ event.alert_name }}，目标：{{ event.target }}，当前值：{{ event.current_value }}",
      "priority": 1
    }
  ],
  "receivers": [
    {
      "type": "role",
      "id": "operator",
      "fallback": ["admin"]
    },
    {
      "type": "dynamic",
      "field": "event.operator"
    }
  ],
  "notify_phases": [
    {
      "phase": "firing",
      "enabled": true,
      "channels": ["weixin", "mail", "sms"]
    },
    {
      "phase": "recovered",
      "enabled": true,
      "channels": ["weixin", "mail"]
    }
  ],
  "retry_enabled": true,
  "retry_count": 3,
  "retry_interval": 60,
  "execution": {
    "timeout": 30
  }
}
```

### 示例 2: 企业微信机器人通知

```json
{
  "name": "wecom_bot_notification",
  "description": "企业微信机器人告警通知",
  "enabled": true,
  "node_type": "notification",
  "channels": [
    {
      "channel": "wecom_bot",
      "enabled": true,
      "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${WECOM_BOT_KEY}",
      "title_template": "## {{ event.severity_display }} {{ event.alert_name }}",
      "content_template": "**告警详情**\n> 目标：<font color=\"warning\">{{ event.target }}</font>\n> 当前值：{{ event.current_value }}\n> 触发时间：{{ event.time | datetime }}\n> 策略ID：{{ event.strategy_id }}\n\n[查看详情]({{ event.alert_url }})",
      "mentioned_list": ["@all"],
      "priority": 10
    }
  ],
  "receivers": [
    {
      "type": "group",
      "id": "ops_team"
    }
  ],
  "notify_phases": [
    {
      "phase": "firing",
      "enabled": true
    },
    {
      "phase": "recovered",
      "enabled": true,
      "template_id": "recovery_template"
    }
  ],
  "default_title_template": "[{{ event.severity_display }}] {{ event.alert_name }}",
  "template_engine": "jinja2",
  "global_rate_limit": 60,
  "execution": {
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 聚合通知与免打扰配置

```json
{
  "name": "aggregated_notification",
  "description": "聚合多条告警为一条通知，支持免打扰时段",
  "enabled": true,
  "node_type": "notification",
  "channels": [
    {
      "channel": "mail",
      "enabled": true,
      "title_template": "[告警汇总] {{ aggregate_count }}条告警待处理",
      "content_template": "以下告警需要您关注：\n\n{% for alert in alerts %}\n{{ loop.index }}. [{{ alert.severity_display }}] {{ alert.alert_name }}\n   目标：{{ alert.target }}\n   时间：{{ alert.time | datetime }}\n{% endfor %}\n\n请及时处理，详情请登录监控平台查看。",
      "priority": 10
    },
    {
      "channel": "weixin",
      "enabled": true,
      "title_template": "告警汇总（{{ aggregate_count }}条）",
      "priority": 5
    }
  ],
  "receivers": [
    {
      "type": "duty",
      "id": "oncall_group",
      "fallback": ["admin", "backup_admin"]
    }
  ],
  "notify_phases": [
    {
      "phase": "firing",
      "enabled": true,
      "channels": ["mail", "weixin"]
    }
  ],
  "aggregate_notifications": true,
  "aggregate_window": 300,
  "aggregate_max_count": 20,
  "retry_enabled": true,
  "retry_count": 3,
  "retry_interval": 120,
  "global_rate_limit": 10,
  "silence_config": {
    "enabled": true,
    "periods": [
      {
        "start_time": "23:00",
        "end_time": "08:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "channels": ["voice", "sms"],
        "action": "delay"
      }
    ],
    "severity_override": [1]
  },
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 60
  },
  "error_handling": {
    "on_error": "retry",
    "max_retries": 3,
    "log_error": true
  }
}
```

## 使用场景

1. **多渠道告警通知**：根据告警级别和时间段选择不同通知渠道
2. **机器人群通知**：通过企业微信/钉钉/飞书机器人发送到群组
3. **轮值通知**：根据轮值表动态选择通知接收人
4. **告警聚合通知**：将短时间内的多条告警聚合为一条通知
5. **分级通知**：致命告警电话通知，普通告警邮件通知
6. **免打扰设置**：夜间时段延迟或禁止部分通知
7. **恢复通知**：告警恢复时发送恢复通知

## 注意事项

1. **渠道配置**：
   - Webhook类渠道需配置正确的URL
   - 敏感信息（如Key）应使用环境变量
   - 每个渠道可有独立的模板和限流配置

2. **模板语法**：
   - 默认使用Jinja2模板引擎
   - 支持过滤器如 `datetime`、`default` 等
   - 聚合通知时可使用 `alerts` 列表变量

3. **接收人配置**：
   - 建议配置 `fallback` 备选接收人
   - `dynamic` 类型从告警字段动态获取
   - 轮值组会自动解析当前值班人

4. **频率限制**：
   - `rate_limit` 按渠道独立限制
   - `global_rate_limit` 全局限制
   - 被限流的通知会被丢弃或延迟

5. **重试机制**：
   - 发送失败会自动重试
   - 重试间隔建议60秒以上
   - 连续失败会触发告警

6. **免打扰配置**：
   - `severity_override` 指定不受免打扰影响的级别
   - `action` 可选 `delay`(延迟) 或 `skip`(跳过)

7. **聚合通知**：
   - 适合高频告警场景
   - 注意设置合理的 `aggregate_max_count`
   - 聚合模板需处理列表数据

8. **性能考虑**：
   - 外部API调用可能超时
   - 合理设置 `timeout`
   - 高并发时注意限流配置

## 相关节点

- **上游节点**：
  - Converge（收敛节点）：收敛后再通知
  - Router（路由节点）：路由到不同通知节点
  - Dedupe（去重节点）：去重后通知
  - Severity（级别节点）：调整级别后通知

- **下游节点**：
  - Storage（存储节点）：存储通知记录
  - Log（日志节点）：记录通知日志
  - Callback（回调节点）：通知后触发回调

### 典型组合模式

1. **Filter → Dedupe → Converge → Notification**
   - 过滤 → 去重 → 收敛 → 通知

2. **Router → [Notification_A | Notification_B]**
   - 路由 → 不同通知配置

3. **Severity → Notification → Storage**
   - 级别调整 → 通知 → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
