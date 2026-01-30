# Recovery Node Configuration (恢复节点配置)

## 节点类型
- **NodeType**: `recovery`
- **分类**: ALERT_LIFECYCLE (告警生命周期类)
- **功能**: 处理告警恢复逻辑，检测告警是否已恢复并更新状态

## 配置 Schema

### RecoveryNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class RecoveryMode(str, Enum):
    """恢复模式"""
    AUTO = "auto"               # 自动恢复（基于检测）
    MANUAL = "manual"           # 手动恢复（需确认）
    TIMEOUT = "timeout"         # 超时自动恢复
    CONDITION = "condition"     # 条件恢复


class RecoveryTrigger(str, Enum):
    """恢复触发方式"""
    METRIC_NORMAL = "metric_normal"   # 指标恢复正常
    NO_DATA = "no_data"               # 无数据超时
    EXTERNAL = "external"             # 外部触发
    ACKNOWLEDGE = "acknowledge"       # 确认后恢复
    SCHEDULED = "scheduled"           # 定时恢复


class RecoveryConditionSerializer(serializers.Serializer):
    """恢复条件配置"""
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
        ],
        help_text="条件操作符"
    )
    value = serializers.JSONField(help_text="条件值")


class RecoveryCheckSerializer(serializers.Serializer):
    """恢复检查配置"""
    check_type = serializers.ChoiceField(
        choices=[
            ("metric", "指标检查"),
            ("api", "API检查"),
            ("ping", "Ping检查"),
            ("custom", "自定义检查"),
        ],
        help_text="检查类型"
    )
    check_interval = serializers.IntegerField(
        default=60,
        min_value=10,
        help_text="检查间隔（秒）"
    )
    check_count = serializers.IntegerField(
        default=3,
        min_value=1,
        help_text="连续检查成功次数"
    )
    check_config = serializers.DictField(
        default=dict,
        help_text="检查配置（根据check_type不同）"
    )


class RecoveryNotificationSerializer(serializers.Serializer):
    """恢复通知配置"""
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否发送恢复通知"
    )
    channels = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="通知渠道列表"
    )
    template_id = serializers.CharField(
        required=False,
        help_text="恢复通知模板ID"
    )
    delay = serializers.IntegerField(
        default=0,
        help_text="延迟发送时间（秒）"
    )


class RecoveryNodeConfigSerializer(BaseNodeConfigSerializer):
    """恢复节点配置"""
    node_type = serializers.CharField(default="recovery", read_only=True)
    
    # 恢复模式
    mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RecoveryMode],
        default="auto",
        help_text="恢复模式"
    )
    
    # 恢复触发方式
    trigger = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RecoveryTrigger],
        default="metric_normal",
        help_text="恢复触发方式"
    )
    
    # 恢复条件
    conditions = RecoveryConditionSerializer(
        many=True,
        required=False,
        help_text="恢复条件列表"
    )
    conditions_logic = serializers.ChoiceField(
        choices=[("and", "AND"), ("or", "OR")],
        default="and",
        help_text="条件组合逻辑"
    )
    
    # 恢复检查配置
    recovery_check = RecoveryCheckSerializer(
        required=False,
        help_text="恢复检查配置"
    )
    
    # 超时配置
    timeout_recovery = serializers.IntegerField(
        default=0,
        help_text="超时自动恢复时间（秒），0表示不启用"
    )
    
    # 连续正常次数
    consecutive_count = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="连续检测正常的次数后才恢复"
    )
    
    # 恢复窗口
    recovery_window = serializers.IntegerField(
        default=300,
        help_text="恢复窗口期（秒），窗口内再次异常会取消恢复"
    )
    
    # 恢复通知
    notification = RecoveryNotificationSerializer(
        required=False,
        help_text="恢复通知配置"
    )
    
    # 状态更新
    update_alert_status = serializers.BooleanField(
        default=True,
        help_text="是否更新告警状态"
    )
    target_status = serializers.ChoiceField(
        choices=[
            ("RECOVERED", "已恢复"),
            ("CLOSED", "已关闭"),
        ],
        default="RECOVERED",
        help_text="目标状态"
    )
    
    # 关联动作
    close_related_actions = serializers.BooleanField(
        default=True,
        help_text="是否关闭关联的处理动作"
    )
    
    # 恢复原因记录
    record_reason = serializers.BooleanField(
        default=True,
        help_text="是否记录恢复原因"
    )
    reason_field = serializers.CharField(
        default="recovery_reason",
        help_text="恢复原因字段名"
    )
    
    # 存储配置
    storage_backend = serializers.ChoiceField(
        choices=[("redis", "Redis"), ("memory", "Memory")],
        default="redis",
        help_text="恢复状态存储后端"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "recovery" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `mode` | string | 否 | "auto" | 恢复模式 |
| `trigger` | string | 否 | "metric_normal" | 触发方式 |
| `conditions` | array | 否 | [] | 恢复条件 |
| `timeout_recovery` | integer | 否 | 0 | 超时恢复时间 |
| `consecutive_count` | integer | 否 | 1 | 连续正常次数 |
| `recovery_window` | integer | 否 | 300 | 恢复窗口期 |
| `update_alert_status` | boolean | 否 | true | 更新告警状态 |

### 恢复检查配置 (RecoveryCheck)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `check_type` | string | 是 | - | 检查类型 |
| `check_interval` | integer | 否 | 60 | 检查间隔 |
| `check_count` | integer | 否 | 3 | 成功次数 |
| `check_config` | object | 否 | {} | 检查配置 |

### 恢复通知配置 (RecoveryNotification)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | boolean | 否 | true | 是否通知 |
| `channels` | array | 否 | [] | 通知渠道 |
| `template_id` | string | 否 | - | 模板ID |
| `delay` | integer | 否 | 0 | 延迟发送 |

### 恢复模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `auto` | 自动检测恢复 | 指标类告警 |
| `manual` | 人工确认恢复 | 需要验证的告警 |
| `timeout` | 超时自动恢复 | 无数据场景 |
| `condition` | 条件满足恢复 | 复杂判断场景 |

### 触发方式说明

| 触发方式 | 说明 | 检测机制 |
|----------|------|----------|
| `metric_normal` | 指标恢复正常 | 检测指标值 |
| `no_data` | 无数据超时 | 超时未收到数据 |
| `external` | 外部触发 | API/事件触发 |
| `acknowledge` | 确认后恢复 | 人工确认 |
| `scheduled` | 定时恢复 | 按时间自动恢复 |

## JSON 配置示例

### 示例 1: 基于指标的自动恢复

```json
{
  "name": "metric_recovery",
  "description": "基于指标值自动恢复告警",
  "enabled": true,
  "node_type": "recovery",
  "mode": "auto",
  "trigger": "metric_normal",
  "conditions": [
    {
      "field": "event.current_value",
      "operator": "lt",
      "value": 80
    }
  ],
  "consecutive_count": 3,
  "recovery_window": 300,
  "notification": {
    "enabled": true,
    "channels": ["weixin", "mail"],
    "delay": 60
  },
  "update_alert_status": true,
  "target_status": "RECOVERED",
  "close_related_actions": true,
  "record_reason": true,
  "storage_backend": "redis",
  "execution": {
    "timeout": 30
  }
}
```

### 示例 2: 超时自动恢复配置

```json
{
  "name": "timeout_recovery",
  "description": "无数据超时自动恢复",
  "enabled": true,
  "node_type": "recovery",
  "mode": "timeout",
  "trigger": "no_data",
  "timeout_recovery": 3600,
  "recovery_check": {
    "check_type": "metric",
    "check_interval": 60,
    "check_count": 3,
    "check_config": {
      "metric_name": "{{ event.metric_name }}",
      "dimensions": "{{ event.dimensions }}",
      "threshold": "{{ event.threshold }}"
    }
  },
  "notification": {
    "enabled": true,
    "channels": ["weixin"],
    "template_id": "timeout_recovery_template",
    "delay": 0
  },
  "update_alert_status": true,
  "target_status": "RECOVERED",
  "record_reason": true,
  "reason_field": "recovery_info",
  "storage_backend": "redis",
  "execution": {
    "timeout": 60
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 多条件复合恢复

```json
{
  "name": "complex_recovery",
  "description": "多条件复合恢复判断",
  "enabled": true,
  "node_type": "recovery",
  "mode": "condition",
  "trigger": "metric_normal",
  "conditions": [
    {
      "field": "event.current_value",
      "operator": "lt",
      "value": 80
    },
    {
      "field": "event.duration",
      "operator": "gte",
      "value": 300
    },
    {
      "field": "event.status",
      "operator": "eq",
      "value": "ABNORMAL"
    }
  ],
  "conditions_logic": "and",
  "recovery_check": {
    "check_type": "api",
    "check_interval": 30,
    "check_count": 5,
    "check_config": {
      "api_url": "http://monitor-api/health/{{ event.target }}",
      "expected_status": 200,
      "timeout": 10
    }
  },
  "consecutive_count": 5,
  "recovery_window": 600,
  "notification": {
    "enabled": true,
    "channels": ["weixin", "mail", "sms"],
    "template_id": "complex_recovery_template",
    "delay": 120
  },
  "update_alert_status": true,
  "target_status": "RECOVERED",
  "close_related_actions": true,
  "record_reason": true,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.skip_recovery",
        "operator": "eq",
        "value": true
      },
      {
        "field": "event.manual_close",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 120
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **指标恢复检测**：CPU/内存等指标降到阈值以下自动恢复
2. **服务健康检查**：服务恢复正常后自动关闭告警
3. **超时自动恢复**：长时间无数据后自动恢复告警
4. **多条件复合恢复**：多个指标同时正常才恢复
5. **外部触发恢复**：通过API或事件触发恢复
6. **定时恢复**：在特定时间自动恢复告警
7. **确认后恢复**：人工确认问题解决后恢复

## 注意事项

1. **恢复窗口期**：
   - `recovery_window` 内再次异常会取消恢复
   - 避免抖动导致的频繁恢复/告警
   - 建议设置合理的窗口期（如5-10分钟）

2. **连续检测次数**：
   - `consecutive_count` 防止误判
   - 建议至少设置3次以上
   - 结合检测间隔综合考虑

3. **恢复通知**：
   - 建议启用恢复通知闭环告警流程
   - 可设置延迟发送避免抖动
   - 恢复通知应简洁明了

4. **状态更新**：
   - `update_alert_status=true` 确保告警状态同步
   - 注意与其他系统的状态一致性

5. **关联动作**：
   - `close_related_actions=true` 关闭相关自愈动作
   - 避免恢复后仍执行不必要的动作

6. **超时恢复**：
   - 超时恢复适合无数据场景
   - 注意设置合理的超时时间
   - 避免误恢复仍在异常的告警

7. **存储选择**：
   - Redis支持分布式部署
   - 恢复状态需要持久化

8. **错误处理**：
   - 恢复失败不应阻塞告警流程
   - 建议配置 `on_error: continue`

## 相关节点

- **上游节点**：
  - Shield（屏蔽节点）：屏蔽判断后检查恢复
  - Action（动作节点）：自愈执行后检查恢复
  - Notification（通知节点）：通知后检查恢复

- **下游节点**：
  - Notification（通知节点）：发送恢复通知
  - Storage（存储节点）：存储恢复记录
  - Callback（回调节点）：恢复后回调

### 典型组合模式

1. **Action → Recovery → Notification**
   - 自愈 → 恢复检查 → 恢复通知

2. **Detection → Recovery → Storage**
   - 检测 → 恢复判断 → 存储

3. **Shield → Recovery → Callback**
   - 屏蔽 → 恢复 → 回调

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
