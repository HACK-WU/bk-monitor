# Action Node Configuration (自动化动作节点配置)

## 节点类型
- **NodeType**: `action`
- **分类**: ACTION (动作类)
- **功能**: 执行自动化处理动作，如重启服务、执行脚本、调用API等自愈操作

## 配置 Schema

### ActionNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class ActionType(str, Enum):
    """动作类型"""
    JOB = "job"                 # 作业平台任务
    SCRIPT = "script"          # 脚本执行
    API = "api"                 # API调用
    HTTP = "http"               # HTTP请求
    PLUGIN = "plugin"           # 插件执行
    WORKFLOW = "workflow"       # 工作流
    KUBERNETES = "kubernetes"   # K8s操作


class ExecuteMode(str, Enum):
    """执行模式"""
    SYNC = "sync"       # 同步执行
    ASYNC = "async"     # 异步执行
    FIRE_AND_FORGET = "fire_and_forget"  # 仅触发不等待


class TargetScope(str, Enum):
    """目标范围"""
    ALERT_TARGET = "alert_target"   # 告警目标
    CUSTOM = "custom"               # 自定义目标
    CMDB = "cmdb"                   # CMDB查询


class JobConfigSerializer(serializers.Serializer):
    """作业平台配置"""
    job_id = serializers.IntegerField(help_text="作业ID")
    bk_biz_id = serializers.IntegerField(help_text="业务ID")
    job_params = serializers.DictField(
        default=dict,
        required=False,
        help_text="作业参数"
    )
    ip_list_template = serializers.CharField(
        required=False,
        help_text="IP列表模板"
    )
    timeout = serializers.IntegerField(
        default=3600,
        help_text="超时时间（秒）"
    )


class ScriptConfigSerializer(serializers.Serializer):
    """脚本执行配置"""
    script_content = serializers.CharField(
        required=False,
        help_text="脚本内容"
    )
    script_id = serializers.IntegerField(
        required=False,
        help_text="脚本ID（从作业平台）"
    )
    script_type = serializers.ChoiceField(
        choices=[
            ("shell", "Shell"),
            ("python", "Python"),
            ("powershell", "PowerShell"),
            ("bat", "Batch"),
        ],
        default="shell",
        help_text="脚本类型"
    )
    script_params = serializers.CharField(
        default="",
        required=False,
        help_text="脚本参数（支持模板变量）"
    )
    account = serializers.CharField(
        default="root",
        help_text="执行账号"
    )
    timeout = serializers.IntegerField(
        default=600,
        help_text="超时时间（秒）"
    )


class ApiConfigSerializer(serializers.Serializer):
    """API调用配置"""
    api_name = serializers.CharField(help_text="API名称")
    api_module = serializers.CharField(
        default="default",
        help_text="API模块"
    )
    api_params = serializers.DictField(
        default=dict,
        required=False,
        help_text="API参数（支持模板变量）"
    )


class TargetConfigSerializer(serializers.Serializer):
    """目标配置"""
    scope = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in TargetScope],
        default="alert_target",
        help_text="目标范围"
    )
    # 告警目标提取
    target_field = serializers.CharField(
        default="event.target",
        required=False,
        help_text="目标字段路径"
    )
    # 自定义目标
    custom_targets = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="自定义目标列表"
    )
    # CMDB查询
    cmdb_query = serializers.DictField(
        required=False,
        help_text="CMDB查询条件"
    )


class ApprovalConfigSerializer(serializers.Serializer):
    """审批配置"""
    enabled = serializers.BooleanField(
        default=False,
        help_text="是否需要审批"
    )
    approvers = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="审批人列表"
    )
    approval_timeout = serializers.IntegerField(
        default=3600,
        help_text="审批超时（秒）"
    )
    auto_approve_on_timeout = serializers.BooleanField(
        default=False,
        help_text="超时是否自动通过"
    )


class ActionNodeConfigSerializer(BaseNodeConfigSerializer):
    """自动化动作节点配置"""
    node_type = serializers.CharField(default="action", read_only=True)
    
    # 动作类型
    action_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ActionType],
        help_text="动作类型"
    )
    
    # 动作名称
    action_name = serializers.CharField(help_text="动作名称（用于展示）")
    
    # 执行模式
    execute_mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ExecuteMode],
        default="async",
        help_text="执行模式"
    )
    
    # 目标配置
    target = TargetConfigSerializer(
        required=False,
        help_text="执行目标配置"
    )
    
    # 作业配置
    job_config = JobConfigSerializer(
        required=False,
        allow_null=True,
        help_text="作业平台配置（action_type=job时使用）"
    )
    
    # 脚本配置
    script_config = ScriptConfigSerializer(
        required=False,
        allow_null=True,
        help_text="脚本执行配置（action_type=script时使用）"
    )
    
    # API配置
    api_config = ApiConfigSerializer(
        required=False,
        allow_null=True,
        help_text="API调用配置（action_type=api时使用）"
    )
    
    # 审批配置
    approval = ApprovalConfigSerializer(
        required=False,
        help_text="审批配置"
    )
    
    # 执行条件
    execute_conditions = serializers.DictField(
        default=dict,
        required=False,
        help_text="执行前置条件"
    )
    
    # 防重复执行
    dedupe_enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用去重（防止重复执行）"
    )
    dedupe_key_fields = serializers.ListField(
        child=serializers.CharField(),
        default=["event.alert_id"],
        help_text="去重键字段"
    )
    dedupe_window = serializers.IntegerField(
        default=3600,
        help_text="去重时间窗口（秒）"
    )
    
    # 执行限制
    max_concurrent = serializers.IntegerField(
        default=10,
        help_text="最大并发执行数"
    )
    max_daily_executions = serializers.IntegerField(
        default=100,
        help_text="每日最大执行次数"
    )
    
    # 结果处理
    result_field = serializers.CharField(
        default="_action_result",
        help_text="结果存储字段"
    )
    wait_for_result = serializers.BooleanField(
        default=True,
        help_text="是否等待执行结果"
    )
    result_timeout = serializers.IntegerField(
        default=3600,
        help_text="结果等待超时（秒）"
    )
    
    def validate(self, attrs):
        action_type = attrs.get('action_type')
        if action_type == 'job' and not attrs.get('job_config'):
            raise serializers.ValidationError(
                "action_type=job时必须配置job_config"
            )
        if action_type == 'script' and not attrs.get('script_config'):
            raise serializers.ValidationError(
                "action_type=script时必须配置script_config"
            )
        if action_type == 'api' and not attrs.get('api_config'):
            raise serializers.ValidationError(
                "action_type=api时必须配置api_config"
            )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "action" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `action_type` | string | 是 | - | 动作类型 |
| `action_name` | string | 是 | - | 动作名称 |
| `execute_mode` | string | 否 | "async" | 执行模式 |
| `target` | object | 否 | - | 目标配置 |
| `approval` | object | 否 | - | 审批配置 |
| `dedupe_enabled` | boolean | 否 | true | 启用去重 |
| `max_concurrent` | integer | 否 | 10 | 最大并发 |
| `wait_for_result` | boolean | 否 | true | 等待结果 |

### 作业平台配置 (JobConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `job_id` | integer | 是 | - | 作业ID |
| `bk_biz_id` | integer | 是 | - | 业务ID |
| `job_params` | object | 否 | {} | 作业参数 |
| `ip_list_template` | string | 否 | - | IP列表模板 |
| `timeout` | integer | 否 | 3600 | 超时时间 |

### 脚本执行配置 (ScriptConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `script_content` | string | 否 | - | 脚本内容 |
| `script_id` | integer | 否 | - | 脚本ID |
| `script_type` | string | 否 | "shell" | 脚本类型 |
| `script_params` | string | 否 | "" | 脚本参数 |
| `account` | string | 否 | "root" | 执行账号 |
| `timeout` | integer | 否 | 600 | 超时时间 |

### API调用配置 (ApiConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `api_name` | string | 是 | API名称 |
| `api_module` | string | 否 | API模块 |
| `api_params` | object | 否 | API参数 |

### 动作类型说明

| 类型 | 说明 | 配置项 |
|------|------|--------|
| `job` | 作业平台任务 | job_config |
| `script` | 脚本执行 | script_config |
| `api` | API调用 | api_config |
| `http` | HTTP请求 | 同webhook |
| `plugin` | 插件执行 | plugin_config |
| `workflow` | 工作流 | workflow_config |
| `kubernetes` | K8s操作 | k8s_config |

### 执行模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `sync` | 同步执行 | 快速任务，需要立即获取结果 |
| `async` | 异步执行 | 长时间任务，可后台运行 |
| `fire_and_forget` | 仅触发 | 不关心执行结果 |

### 目标范围说明

| 范围 | 说明 | 使用场景 |
|------|------|----------|
| `alert_target` | 告警目标 | 针对告警涉及的目标执行 |
| `custom` | 自定义目标 | 指定固定目标列表 |
| `cmdb` | CMDB查询 | 动态查询CMDB获取目标 |

## JSON 配置示例

### 示例 1: 作业平台任务执行

```json
{
  "name": "restart_service_action",
  "description": "重启服务自愈动作",
  "enabled": true,
  "node_type": "action",
  "action_type": "job",
  "action_name": "重启服务",
  "execute_mode": "async",
  "target": {
    "scope": "alert_target",
    "target_field": "event.target"
  },
  "job_config": {
    "job_id": 12345,
    "bk_biz_id": 100,
    "job_params": {
      "service_name": "{{ event.dimensions.service }}",
      "action": "restart"
    },
    "ip_list_template": "{{ event.target }}",
    "timeout": 600
  },
  "approval": {
    "enabled": true,
    "approvers": ["admin", "ops_lead"],
    "approval_timeout": 1800,
    "auto_approve_on_timeout": false
  },
  "dedupe_enabled": true,
  "dedupe_key_fields": ["event.alert_id", "event.target"],
  "dedupe_window": 3600,
  "max_concurrent": 5,
  "max_daily_executions": 50,
  "wait_for_result": true,
  "result_timeout": 600,
  "execution": {
    "timeout": 900
  }
}
```

### 示例 2: 脚本执行自愈

```json
{
  "name": "cleanup_disk_action",
  "description": "磁盘清理自愈脚本",
  "enabled": true,
  "node_type": "action",
  "action_type": "script",
  "action_name": "磁盘清理",
  "execute_mode": "sync",
  "target": {
    "scope": "alert_target",
    "target_field": "event.dimensions.host"
  },
  "script_config": {
    "script_type": "shell",
    "script_content": "#!/bin/bash\n# 磁盘清理脚本\nDISK_PATH=\"{{ event.dimensions.disk_path }}\"\nTHRESHOLD=80\n\n# 清理日志文件\nfind ${DISK_PATH}/logs -type f -mtime +7 -delete\n\n# 清理临时文件\nfind ${DISK_PATH}/tmp -type f -mtime +1 -delete\n\n# 检查清理后的使用率\nUSAGE=$(df ${DISK_PATH} | tail -1 | awk '{print $5}' | sed 's/%//')\nif [ $USAGE -lt $THRESHOLD ]; then\n    echo \"清理成功，当前使用率: ${USAGE}%\"\n    exit 0\nelse\n    echo \"清理后使用率仍然较高: ${USAGE}%\"\n    exit 1\nfi",
    "script_params": "",
    "account": "root",
    "timeout": 300
  },
  "execute_conditions": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.metric_name",
        "operator": "eq",
        "value": "disk_usage"
      },
      {
        "field": "event.current_value",
        "operator": "gte",
        "value": 90
      }
    ]
  },
  "dedupe_enabled": true,
  "dedupe_key_fields": ["event.dimensions.host", "event.dimensions.disk_path"],
  "dedupe_window": 1800,
  "max_concurrent": 10,
  "wait_for_result": true,
  "result_timeout": 300,
  "result_field": "_cleanup_result",
  "execution": {
    "timeout": 600
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: API调用与审批流程

```json
{
  "name": "scale_service_action",
  "description": "服务扩容自愈动作",
  "enabled": true,
  "node_type": "action",
  "action_type": "api",
  "action_name": "服务扩容",
  "execute_mode": "async",
  "target": {
    "scope": "cmdb",
    "cmdb_query": {
      "bk_obj_id": "service",
      "condition": {
        "service_name": "{{ event.dimensions.service }}"
      }
    }
  },
  "api_config": {
    "api_name": "scale_service",
    "api_module": "bcs",
    "api_params": {
      "cluster_id": "{{ event.dimensions.cluster_id }}",
      "namespace": "{{ event.dimensions.namespace }}",
      "deployment": "{{ event.dimensions.deployment }}",
      "replicas": "{{ event.current_replicas + 2 }}",
      "reason": "自动扩容 - 触发告警: {{ event.alert_name }}"
    }
  },
  "approval": {
    "enabled": true,
    "approvers": ["k8s_admin", "sre_team"],
    "approval_timeout": 900,
    "auto_approve_on_timeout": false
  },
  "execute_conditions": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.dimensions.cluster_type",
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
  "dedupe_enabled": true,
  "dedupe_key_fields": [
    "event.dimensions.cluster_id",
    "event.dimensions.deployment"
  ],
  "dedupe_window": 7200,
  "max_concurrent": 3,
  "max_daily_executions": 10,
  "wait_for_result": true,
  "result_timeout": 1800,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      },
      {
        "field": "event.auto_heal_disabled",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 3600
  },
  "error_handling": {
    "on_error": "notify",
    "notify_channels": ["weixin"],
    "log_error": true
  }
}
```

## 使用场景

1. **服务重启**：自动重启故障服务
2. **磁盘清理**：磁盘使用率过高时自动清理
3. **服务扩容**：负载过高时自动扩容
4. **配置刷新**：配置异常时自动重载
5. **进程拉起**：进程挂掉时自动拉起
6. **网络修复**：网络异常时自动诊断修复
7. **数据备份**：数据异常时触发紧急备份

## 注意事项

1. **执行安全**：
   - 敏感操作建议启用审批
   - 生产环境需谨慎配置
   - 建议限制最大执行次数

2. **防重复执行**：
   - 强烈建议启用 `dedupe_enabled`
   - 合理配置去重键和时间窗口
   - 避免同一问题多次执行自愈

3. **执行模式**：
   - `sync` 模式会阻塞Pipeline
   - `async` 模式适合长时间任务
   - `fire_and_forget` 不保证执行结果

4. **超时配置**：
   - 合理设置各级超时
   - `result_timeout` < `execution.timeout`
   - 考虑网络延迟和任务耗时

5. **审批流程**：
   - 高危操作建议开启审批
   - 配置合理的审批超时
   - 注意审批人的可用性

6. **目标选择**：
   - `alert_target` 最常用
   - CMDB查询可实现动态目标
   - 注意目标数量限制

7. **结果处理**：
   - `wait_for_result=true` 可获取执行结果
   - 结果会写入 `result_field` 字段
   - 可供下游节点使用

8. **错误处理**：
   - 建议配置 `on_error: notify`
   - 自愈失败应及时通知
   - 记录详细日志便于排查

## 相关节点

- **上游节点**：
  - Shield（屏蔽节点）：屏蔽判断后执行
  - Severity（级别节点）：级别调整后执行
  - Converge（收敛节点）：收敛后执行

- **下游节点**：
  - Recovery（恢复节点）：自愈后恢复检查
  - Notification（通知节点）：通知执行结果
  - Storage（存储节点）：存储执行记录

### 典型组合模式

1. **Shield → Severity → Action → Notification**
   - 屏蔽 → 级别 → 自愈 → 通知

2. **Converge → Action → Recovery**
   - 收敛 → 自愈 → 恢复检查

3. **Router → [Action_A | Action_B]**
   - 路由 → 不同自愈动作

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
