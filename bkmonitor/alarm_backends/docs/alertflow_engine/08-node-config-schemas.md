# 节点配置数据结构

> 返回 [目录](./README.md)

### 设计理念

### 配置即数据

AlertFlow Engine 遵循“**配置即数据**”的设计原则：

1. **节点可复用**：每个节点可以在不同项目中直接使用
2. **配置驱动**：不同项目只需根据自己的数据格式适配节点配置
3. **声明式执行**：配置完成后，节点根据配置自动处理
4. **强类型约束**：每个节点预定义好配置的数据结构，通过 DRF Serializer 进行验证

```
项目A              项目B              项目C
   │                  │                  │
   ▼                  ▼                  ▼
┌─────────┐      ┌─────────┐      ┌─────────┐
│ 配置 A  │      │ 配置 B  │      │ 配置 C  │
│ (JSON)  │      │ (JSON)  │      │ (JSON)  │
└────┬────┘      └────┬────┘      └────┬────┘
     │                │                │
     └────────────────┼────────────────┘
                      ▼
            ┌─────────────────┐
            │   通用节点实现    │
            │ (FilterNode等)  │
            └─────────────────┘
```

### 配置层次结构

```
PipelineConfig (Pipeline 配置)
├── id, name, version, scenario
├── global_config (全局配置)
└── stages[] (阶段列表)
    └── StageConfig (阶段配置)
        ├── name, type, condition
        └── processors[] (处理器列表)
            └── ProcessorConfig (处理器配置)
                ├── processor_type (节点类型标识)
                ├── node_config (节点专属配置)
                │   └── FilterNodeConfig / EnrichmentNodeConfig / ...
                └── execution_config (执行配置)
```

### 节点抽象接口

每个节点都暴露三个抽象接口，用户可以根据这些接口组装配置：

```
┌───────────────────────────────────────────────────┐
│                   IProcessor                       │
├────────────────┬────────────────┬────────────────┤
│ get_config_schema │ get_input_schema │ get_output_schema│
│  配置格式定义     │  输入数据格式    │   输出数据格式   │
└────────────────┴────────────────┴────────────────┘
```

| 接口 | 用途 |
|------|------|
| `get_config_schema()` | 返回 DRF Serializer，定义节点的配置格式 |
| `get_input_schema()` | 返回 DRF Serializer，定义节点期望的输入数据格式 |
| `get_output_schema()` | 返回 DRF Serializer，定义节点产生的输出数据格式 |

**配置传递机制**：

```
上一个节点                    下一个节点
┌────────────────┐              ┌────────────────┐
│  FilterNode    │              │ EnrichmentNode │
│                │              │                │
│ output_schema ──────────────► input_schema   │
│                │  context     │                │
└────────────────┘  传递       └────────────────┘

配置中可以引用上游节点的输出：
{{ $upstream.node_name.field }}
```

---

## 基础配置模型

### 节点分类体系

节点按功能分为 6 大类：

```python
class NodeCategory(str, Enum):
    """节点分类枚举"""
    DATA_PROCESSING = "data_processing"    # 数据处理类
    DETECTION = "detection"                # 检测类
    FLOW_CONTROL = "flow_control"          # 流控类
    ALERT_LIFECYCLE = "alert_lifecycle"    # 告警生命周期类
    ACTION = "action"                      # 动作类
    STORAGE = "storage"                    # 存储类
```

**节点分类架构图**：

```
┌───────────────────────────────────────────────────────────────┐
│                        NodeCategory                             │
├──────────┬─────────┬──────────┬─────────────┬────────┬────────┤
│   DATA    │ DETECT  │   FLOW   │    ALERT    │ ACTION │STORAGE│
│PROCESSING│   ION   │  CONTROL │  LIFECYCLE  │        │        │
├──────────┼─────────┼──────────┼─────────────┼────────┼────────┤
│ FILTER   │THRESHOLD│ ROUTER   │ SHIELD      │NOTIFY  │STORAGE│
│ TRANSFORM│ ANOMALY │BREAKER   │ SUPPRESS    │ACTION  │ QUERY │
│ENRICHMENT│BASELINE │RATE_LIMIT│ RECOVERY    │WEBHOOK │  LOG  │
│AGGREGATE │ TREND   │ DEDUPE   │ ESCALATION  │INCIDENT│METRIC │
│ WINDOW   │CORRELAT │CONVERGE  │ ACKNOWLEDGE │CALLBACK│        │
│ SAMPLE   │   ION   │ DELAY    │ SEVERITY    │        │        │
│ SPLIT    │         │  FORK    │             │        │        │
│  JOIN    │         │ MERGE    │             │        │        │
└──────────┴─────────┴──────────┴─────────────┴────────┴────────┘
```

### 节点类型枚举

```python
class NodeType(str, Enum):
    """节点类型枚举 - 按分类组织"""
    
    # ==================== 数据处理类 (DATA_PROCESSING) ====================
    FILTER = "filter"              # 过滤节点
    TRANSFORM = "transform"        # 转换节点
    ENRICHMENT = "enrichment"      # 丰富化节点
    AGGREGATE = "aggregate"        # 聚合节点
    WINDOW = "window"              # 窗口节点
    SAMPLE = "sample"              # 采样节点
    SPLIT = "split"                # 分裂节点
    JOIN = "join"                  # 关联节点
    
    # ==================== 检测类 (DETECTION) ====================
    THRESHOLD = "threshold"        # 阈值检测节点
    ANOMALY = "anomaly"            # 异常检测节点
    BASELINE = "baseline"          # 基线检测节点
    TREND = "trend"                # 趋势检测节点
    CORRELATION = "correlation"    # 关联检测节点
    
    # ==================== 流控类 (FLOW_CONTROL) ====================
    ROUTER = "router"              # 路由节点
    CIRCUIT_BREAKER = "circuit_breaker"  # 熔断节点
    RATE_LIMIT = "rate_limit"      # 限流节点
    DEDUPE = "dedupe"              # 去重节点
    CONVERGE = "converge"          # 收敛节点
    DELAY = "delay"                # 延迟节点
    FORK = "fork"                  # 分叉节点
    MERGE = "merge"                # 合并节点
    
    # ==================== 告警生命周期类 (ALERT_LIFECYCLE) ====================
    SHIELD = "shield"              # 屏蔽节点
    SUPPRESS = "suppress"          # 抑制节点
    RECOVERY = "recovery"          # 恢复节点
    ESCALATION = "escalation"      # 升级节点
    ACKNOWLEDGE = "acknowledge"    # 确认节点
    SEVERITY = "severity"          # 级别调整节点
    NO_MONITOR = "no_monitor"      # 不监控节点
    
    # ==================== 动作类 (ACTION) ====================
    NOTIFICATION = "notification"  # 通知节点
    ACTION = "action"              # 自动化动作节点
    WEBHOOK = "webhook"            # Webhook 节点
    INCIDENT = "incident"          # 故障事件节点
    CALLBACK = "callback"          # 回调节点
    
    # ==================== 存储类 (STORAGE) ====================
    STORAGE = "storage"            # 存储节点
    QUERY = "query"                # 查询节点
    LOG = "log"                    # 日志节点
    METRIC = "metric"              # 指标生成节点


# 节点类型与分类的映射关系
NODE_CATEGORY_MAPPING: Dict[NodeType, NodeCategory] = {
    # 数据处理类
    NodeType.FILTER: NodeCategory.DATA_PROCESSING,
    NodeType.TRANSFORM: NodeCategory.DATA_PROCESSING,
    NodeType.ENRICHMENT: NodeCategory.DATA_PROCESSING,
    NodeType.AGGREGATE: NodeCategory.DATA_PROCESSING,
    NodeType.WINDOW: NodeCategory.DATA_PROCESSING,
    NodeType.SAMPLE: NodeCategory.DATA_PROCESSING,
    NodeType.SPLIT: NodeCategory.DATA_PROCESSING,
    NodeType.JOIN: NodeCategory.DATA_PROCESSING,
    
    # 检测类
    NodeType.THRESHOLD: NodeCategory.DETECTION,
    NodeType.ANOMALY: NodeCategory.DETECTION,
    NodeType.BASELINE: NodeCategory.DETECTION,
    NodeType.TREND: NodeCategory.DETECTION,
    NodeType.CORRELATION: NodeCategory.DETECTION,
    
    # 流控类
    NodeType.ROUTER: NodeCategory.FLOW_CONTROL,
    NodeType.CIRCUIT_BREAKER: NodeCategory.FLOW_CONTROL,
    NodeType.RATE_LIMIT: NodeCategory.FLOW_CONTROL,
    NodeType.DEDUPE: NodeCategory.FLOW_CONTROL,
    NodeType.CONVERGE: NodeCategory.FLOW_CONTROL,
    NodeType.DELAY: NodeCategory.FLOW_CONTROL,
    NodeType.FORK: NodeCategory.FLOW_CONTROL,
    NodeType.MERGE: NodeCategory.FLOW_CONTROL,
    
    # 告警生命周期类
    NodeType.SHIELD: NodeCategory.ALERT_LIFECYCLE,
    NodeType.SUPPRESS: NodeCategory.ALERT_LIFECYCLE,
    NodeType.RECOVERY: NodeCategory.ALERT_LIFECYCLE,
    NodeType.ESCALATION: NodeCategory.ALERT_LIFECYCLE,
    NodeType.ACKNOWLEDGE: NodeCategory.ALERT_LIFECYCLE,
    NodeType.SEVERITY: NodeCategory.ALERT_LIFECYCLE,
    NodeType.NO_MONITOR: NodeCategory.ALERT_LIFECYCLE,
    
    # 动作类
    NodeType.NOTIFICATION: NodeCategory.ACTION,
    NodeType.ACTION: NodeCategory.ACTION,
    NodeType.WEBHOOK: NodeCategory.ACTION,
    NodeType.INCIDENT: NodeCategory.ACTION,
    NodeType.CALLBACK: NodeCategory.ACTION,
    
    # 存储类
    NodeType.STORAGE: NodeCategory.STORAGE,
    NodeType.QUERY: NodeCategory.STORAGE,
    NodeType.LOG: NodeCategory.STORAGE,
    NodeType.METRIC: NodeCategory.STORAGE,
}
```

### 节点分类说明

| 分类 | 说明 | 包含节点 |
|------|------|----------|
| **DATA_PROCESSING** | 数据处理类：负责数据的过滤、转换、丰富和聚合 | filter, transform, enrichment, aggregate, window, sample, split, join |
| **DETECTION** | 检测类：负责异常检测、阈值判断、趋势分析 | threshold, anomaly, baseline, trend, correlation |
| **FLOW_CONTROL** | 流控类：负责流量控制、路由、去重、收敛 | router, circuit_breaker, rate_limit, dedupe, converge, delay, fork, merge |
| **ALERT_LIFECYCLE** | 告警生命周期类：负责告警的屏蔽、恢复、升级 | shield, suppress, recovery, escalation, acknowledge, severity, no_monitor |
| **ACTION** | 动作类：负责执行通知、自动化动作 | notification, action, webhook, incident, callback |
| **STORAGE** | 存储类：负责数据存储、查询、日志记录 | storage, query, log, metric |

### 执行配置 (ExecutionConfigSerializer)

所有节点通用的执行配置：

```python
from rest_framework import serializers


class ExecutionConfigSerializer(serializers.Serializer):
    """执行配置 - 所有节点通用"""
    timeout = serializers.IntegerField(default=30, min_value=1, max_value=600, help_text="执行超时时间（秒）")
    retry_enabled = serializers.BooleanField(default=True, help_text="是否启用重试")
    retry_max_attempts = serializers.IntegerField(default=3, min_value=1, max_value=10, help_text="最大重试次数")
    retry_delay = serializers.FloatField(default=1.0, min_value=0.1, max_value=60.0, help_text="重试间隔（秒）")
    retry_backoff_multiplier = serializers.FloatField(default=2.0, min_value=1.0, max_value=5.0, help_text="重试退避倍数")
    async_execution = serializers.BooleanField(default=False, help_text="是否异步执行")
```

**JSON Schema:**

```json
{
  "type": "object",
  "properties": {
    "timeout": { "type": "integer", "default": 30, "minimum": 1, "maximum": 600 },
    "retry_enabled": { "type": "boolean", "default": true },
    "retry_max_attempts": { "type": "integer", "default": 3, "minimum": 1, "maximum": 10 },
    "retry_delay": { "type": "number", "default": 1.0, "minimum": 0.1, "maximum": 60.0 },
    "retry_backoff_multiplier": { "type": "number", "default": 2.0, "minimum": 1.0, "maximum": 5.0 },
    "async_execution": { "type": "boolean", "default": false }
  }
}
```

### 错误处理配置 (ErrorHandlingConfigSerializer)

所有节点通用的错误处理配置：

```python
class ErrorHandlingConfigSerializer(serializers.Serializer):
    """错误处理配置 - 所有节点通用"""
    on_error = serializers.ChoiceField(
        choices=[("continue", "continue"), ("stop", "stop"), ("skip", "skip"), ("fallback", "fallback")],
        default="continue",
        help_text="错误时动作：continue=继续执行, stop=停止Pipeline, skip=跳过当前节点, fallback=使用降级值"
    )
    fallback_value = serializers.JSONField(required=False, allow_null=True, help_text="降级返回值（on_error=fallback时生效）")
    log_error = serializers.BooleanField(default=True, help_text="是否记录错误日志")
    error_field = serializers.CharField(default="_error", required=False, help_text="错误信息存储字段")
```

**JSON Schema:**

```json
{
  "type": "object",
  "properties": {
    "on_error": { "type": "string", "enum": ["continue", "stop", "skip", "fallback"], "default": "continue" },
    "fallback_value": { "type": ["object", "array", "string", "number", "boolean", "null"] },
    "log_error": { "type": "boolean", "default": true },
    "error_field": { "type": "string", "default": "_error" }
  }
}
```

### 节点配置基类 (BaseNodeConfigSerializer)

```python
from rest_framework import serializers


class BaseNodeConfigSerializer(serializers.Serializer):
    """节点配置基类 - 所有节点配置必须继承此类"""
    
    name = serializers.CharField(min_length=1, max_length=128, help_text="节点实例名称")
    description = serializers.CharField(default="", max_length=512, required=False, help_text="节点描述")
    enabled = serializers.BooleanField(default=True, help_text="是否启用")
    execution = ExecutionConfigSerializer(required=False, help_text="执行配置")
    error_handling = ErrorHandlingConfigSerializer(required=False, help_text="错误处理配置")
    skip_condition = ConditionGroupSerializer(required=False, allow_null=True, help_text="跳过条件，满足时跳过该节点")
    
    def validate(self, attrs):
        """DRF 的验证方法，禁止未定义的字段"""
        return attrs
```

**说明**：
- `error_handling`：统一的错误处理策略，确保节点执行失败时有明确的处理方式
- `skip_condition`：支持条件执行，满足条件时跳过该节点，提高灵活性

---

## 过滤节点配置 (FilterNodeConfigSerializer)

过滤节点用于根据条件筛选事件，支持多种匹配模式。

### 数据结构定义

```python
from rest_framework import serializers


class MatchOperator(str, Enum):
    """匹配操作符"""
    EQ = "eq"           # 等于
    NE = "ne"           # 不等于
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    IN = "in"           # 在列表中
    NOT_IN = "not_in"   # 不在列表中
    CONTAINS = "contains"       # 包含
    NOT_CONTAINS = "not_contains"  # 不包含
    REGEX = "regex"     # 正则匹配
    EXISTS = "exists"   # 字段存在
    NOT_EXISTS = "not_exists"  # 字段不存在


class FilterConditionSerializer(serializers.Serializer):
    """单个过滤条件"""
    field = serializers.CharField(help_text="字段路径，支持嵌套")
    operator = serializers.ChoiceField(choices=[(e.value, e.name) for e in MatchOperator], help_text="匹配操作符")
    value = serializers.JSONField(default=None, required=False, help_text="匹配值")
    case_sensitive = serializers.BooleanField(default=True, help_text="是否区分大小写")


class ConditionGroupSerializer(serializers.Serializer):
    """条件组 - 支持 AND/OR 组合"""
    logic = serializers.ChoiceField(choices=[("and", "AND"), ("or", "OR")], default="and", help_text="条件组合逻辑")
    conditions = serializers.ListField(help_text="条件列表")


class FilterNodeConfigSerializer(BaseNodeConfigSerializer):
    """过滤节点配置"""
    node_type = serializers.CharField(default="filter", read_only=True)
    match_mode = serializers.ChoiceField(choices=[("all", "all"), ("any", "any")], default="all", help_text="匹配模式")
    conditions = FilterConditionSerializer(many=True, required=False, help_text="简单条件列表")
    condition_groups = ConditionGroupSerializer(required=False, allow_null=True, help_text="复杂条件组")
    invert = serializers.BooleanField(default=False, help_text="反转匹配结果")
    drop_on_match = serializers.BooleanField(default=True, help_text="匹配时丢弃")
```

### JSON 配置示例

**示例 1: 监控告警过滤**

```json
{
  "name": "severity_filter",
  "description": "过滤低级别告警",
  "enabled": true,
  "node_type": "filter",
  "match_mode": "all",
  "conditions": [
    {
      "field": "event.severity",
      "operator": "gte",
      "value": 3
    },
    {
      "field": "event.status",
      "operator": "ne",
      "value": "resolved"
    }
  ],
  "execution": {
    "timeout": 10
  }
}
```

**示例 2: 日志级别过滤（复杂条件组）**

```json
{
  "name": "error_log_filter",
  "description": "只保留 ERROR 和 FATAL 级别日志",
  "node_type": "filter",
  "condition_groups": {
    "logic": "or",
    "conditions": [
      {
        "field": "log.level",
        "operator": "eq",
        "value": "ERROR"
      },
      {
        "field": "log.level",
        "operator": "eq",
        "value": "FATAL"
      }
    ]
  },
  "invert": true,
  "drop_on_match": false
}
```

---

## 丰富化节点配置 (EnrichmentNodeConfigSerializer)

丰富化节点用于从外部数据源获取额外信息，并添加到事件数据中。

### 数据结构定义

```python
from rest_framework import serializers


class DataSourceType(str, Enum):
    """数据源类型"""
    CMDB = "cmdb"           # 配置管理数据库
    CACHE = "cache"         # Redis 缓存
    DATABASE = "database"   # 关系数据库
    HTTP = "http"           # HTTP API
    STATIC = "static"       # 静态映射


class FieldMappingSerializer(serializers.Serializer):
    """字段映射配置"""
    source_field = serializers.CharField(help_text="源字段路径")
    target_field = serializers.CharField(help_text="目标字段路径")
    default_value = serializers.JSONField(default=None, required=False, help_text="默认值")
    transform = serializers.CharField(default=None, required=False, allow_null=True, help_text="转换表达式")


class DataSourceConfigSerializer(serializers.Serializer):
    """数据源配置"""
    type = serializers.ChoiceField(choices=[(e.value, e.name) for e in DataSourceType], help_text="数据源类型")
    
    # HTTP 数据源
    url = serializers.CharField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=[("GET", "GET"), ("POST", "POST")], default="GET", required=False)
    headers = serializers.DictField(default=dict, required=False)
    params_template = serializers.DictField(required=False, allow_null=True)
    response_path = serializers.CharField(required=False, allow_null=True)
    
    # CMDB 数据源
    cmdb_object_type = serializers.CharField(required=False, allow_null=True)
    cmdb_lookup_field = serializers.CharField(required=False, allow_null=True)
    
    # Cache 数据源
    cache_key_template = serializers.CharField(required=False, allow_null=True)
    cache_ttl = serializers.IntegerField(default=300, required=False)
    
    # Database 数据源
    db_connection = serializers.CharField(required=False, allow_null=True)
    db_query = serializers.CharField(required=False, allow_null=True)
    
    # Static 数据源
    static_mapping = serializers.DictField(required=False, allow_null=True)


class EnrichmentNodeConfigSerializer(BaseNodeConfigSerializer):
    """丰富化节点配置"""
    node_type = serializers.CharField(default="enrichment", read_only=True)
    lookup_field = serializers.CharField(help_text="查询字段路径")
    data_source = DataSourceConfigSerializer(help_text="数据源配置")
    field_mappings = FieldMappingSerializer(many=True, help_text="字段映射")
    fail_on_missing = serializers.BooleanField(default=False, help_text="无数据时是否失败")
    cache_enabled = serializers.BooleanField(default=True, help_text="是否启用缓存")
    cache_ttl = serializers.IntegerField(default=300, min_value=0, help_text="缓存TTL")
    
    def validate_field_mappings(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个字段映射")
        return value
```

### JSON 配置示例

**示例 1: CMDB 主机信息丰富**

```json
{
  "name": "host_enrichment",
  "description": "从 CMDB 获取主机详细信息",
  "node_type": "enrichment",
  "lookup_field": "event.ip",
  "data_source": {
    "type": "cmdb",
    "cmdb_object_type": "host",
    "cmdb_lookup_field": "bk_host_innerip"
  },
  "field_mappings": [
    {
      "source_field": "bk_cloud_id",
      "target_field": "event.cloud_id"
    },
    {
      "source_field": "bk_biz_id",
      "target_field": "event.biz_id"
    },
    {
      "source_field": "bk_host_name",
      "target_field": "event.host_name",
      "default_value": "unknown"
    }
  ],
  "fail_on_missing": false,
  "cache_enabled": true,
  "cache_ttl": 600
}
```

**示例 2: HTTP API 丰富**

```json
{
  "name": "user_info_enrichment",
  "description": "从用户服务获取用户信息",
  "node_type": "enrichment",
  "lookup_field": "event.user_id",
  "data_source": {
    "type": "http",
    "url": "http://user-service/api/v1/users/{user_id}",
    "method": "GET",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}"
    },
    "response_path": "data"
  },
  "field_mappings": [
    {
      "source_field": "name",
      "target_field": "event.user_name"
    },
    {
      "source_field": "department",
      "target_field": "event.department"
    }
  ]
}
```

---

## 熔断节点配置 (CircuitBreakerNodeConfigSerializer)

熔断节点用于防止系统过载，当错误率超过阈值时自动熔断。

### 数据结构定义

```python
from rest_framework import serializers


class CircuitBreakerNodeConfigSerializer(BaseNodeConfigSerializer):
    """熔断节点配置"""
    node_type = serializers.CharField(default="circuit_breaker", read_only=True)
    
    # 熔断键配置
    breaker_key_template = serializers.CharField(help_text="熔断键模板")
    
    # 阈值配置
    failure_threshold = serializers.IntegerField(default=5, min_value=1, max_value=1000, help_text="失败次数阈值")
    failure_rate_threshold = serializers.FloatField(default=0.5, min_value=0.0, max_value=1.0, help_text="失败率阈值")
    success_threshold = serializers.IntegerField(default=3, min_value=1, max_value=100, help_text="恢复所需成功次数")
    
    # 时间窗口配置
    window_size = serializers.IntegerField(default=60, min_value=10, max_value=3600, help_text="滑动窗口大小（秒）")
    open_duration = serializers.IntegerField(default=30, min_value=5, max_value=600, help_text="熔断持续时间（秒）")
    
    # 行为配置
    on_open_action = serializers.ChoiceField(
        choices=[("drop", "drop"), ("fallback", "fallback"), ("queue", "queue")], 
        default="drop", 
        help_text="熔断时动作"
    )
    fallback_value = serializers.DictField(default=None, required=False, allow_null=True, help_text="降级返回值")
```

### JSON 配置示例

**示例 1: 策略级别熔断**

```json
{
  "name": "strategy_circuit_breaker",
  "description": "按策略ID进行熔断控制",
  "node_type": "circuit_breaker",
  "breaker_key_template": "strategy:{event.strategy_id}",
  "failure_threshold": 10,
  "failure_rate_threshold": 0.6,
  "success_threshold": 5,
  "window_size": 120,
  "open_duration": 60,
  "on_open_action": "drop"
}
```

**示例 2: 服务级别熔断（带降级）**

```json
{
  "name": "service_circuit_breaker",
  "description": "按服务名进行熔断，熔断时返回默认值",
  "node_type": "circuit_breaker",
  "breaker_key_template": "service:{event.service_name}",
  "failure_threshold": 20,
  "failure_rate_threshold": 0.7,
  "window_size": 60,
  "open_duration": 30,
  "on_open_action": "fallback",
  "fallback_value": {
    "status": "degraded",
    "message": "Service is temporarily unavailable"
  }
}
```

---

## 屏蔽节点配置 (ShieldNodeConfigSerializer)

屏蔽节点用于根据屏蔽规则阻止特定事件的处理。

### 数据结构定义

```python
from rest_framework import serializers


class ShieldScope(str, Enum):
    """屏蔽范围"""
    GLOBAL = "global"
    BIZ = "biz"
    STRATEGY = "strategy"
    HOST = "host"
    DIMENSION = "dimension"


class TimeRangeSerializer(serializers.Serializer):
    """时间范围"""
    start_time = serializers.CharField(help_text="开始时间（HH:MM）")
    end_time = serializers.CharField(help_text="结束时间（HH:MM）")
    timezone = serializers.CharField(default="Asia/Shanghai", help_text="时区")
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), 
        default=[0, 1, 2, 3, 4, 5, 6], 
        help_text="生效星期"
    )


class ShieldRuleSerializer(serializers.Serializer):
    """屏蔽规则"""
    id = serializers.CharField()
    name = serializers.CharField()
    scope = serializers.ChoiceField(choices=[(e.value, e.name) for e in ShieldScope])
    match_conditions = FilterConditionSerializer(many=True)
    time_range = TimeRangeSerializer(required=False, allow_null=True)
    enabled = serializers.BooleanField(default=True)
    priority = serializers.IntegerField(default=0, min_value=0, max_value=100)


class ShieldNodeConfigSerializer(BaseNodeConfigSerializer):
    """屏蔽节点配置"""
    node_type = serializers.CharField(default="shield", read_only=True)
    rules_source = serializers.ChoiceField(
        choices=[("config", "config"), ("database", "database"), ("api", "api")], 
        default="config"
    )
    rules = ShieldRuleSerializer(many=True, required=False)
    rules_query = serializers.CharField(required=False, allow_null=True)
    rules_cache_ttl = serializers.IntegerField(default=60, min_value=0)
    log_shielded = serializers.BooleanField(default=True)
    shield_reason_field = serializers.CharField(default="shield_reason")
```

### JSON 配置示例

**示例 1: 配置文件定义屏蔽规则**

```json
{
  "name": "maintenance_shield",
  "description": "维护窗口屏蔽",
  "node_type": "shield",
  "rules_source": "config",
  "rules": [
    {
      "id": "maintenance_window_1",
      "name": "每周日凌晨维护窗口",
      "scope": "global",
      "match_conditions": [
        {
          "field": "event.biz_id",
          "operator": "in",
          "value": [1, 2, 3]
        }
      ],
      "time_range": {
        "start_time": "02:00",
        "end_time": "06:00",
        "weekdays": [6]
      },
      "priority": 100
    },
    {
      "id": "host_shield_1",
      "name": "特定主机屏蔽",
      "scope": "host",
      "match_conditions": [
        {
          "field": "event.ip",
          "operator": "eq",
          "value": "10.0.0.100"
        }
      ]
    }
  ],
  "log_shielded": true
}
```

**示例 2: 从数据库加载屏蔽规则**

```json
{
  "name": "dynamic_shield",
  "description": "动态屏蔽规则",
  "node_type": "shield",
  "rules_source": "database",
  "rules_query": "SELECT * FROM shield_rules WHERE enabled = true",
  "rules_cache_ttl": 30
}
```

---

## 收敛节点配置 (ConvergeNodeConfigSerializer)

收敛节点用于合并相似的告警事件，减少告警噪音。

### 数据结构定义

```python
from rest_framework import serializers


class ConvergeStrategy(str, Enum):
    """收敛策略"""
    FIRST = "first"
    LAST = "last"
    MERGE = "merge"
    COUNT = "count"
    AGGREGATE = "aggregate"


class AggregateFunction(str, Enum):
    """聚合函数"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"


class ConvergeWindowSerializer(serializers.Serializer):
    """收敛窗口配置"""
    type = serializers.ChoiceField(
        choices=[("fixed", "fixed"), ("sliding", "sliding"), ("session", "session")], 
        default="fixed"
    )
    size = serializers.IntegerField(min_value=1, max_value=86400, help_text="窗口大小（秒）")
    session_gap = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class AggregateFieldSerializer(serializers.Serializer):
    """聚合字段配置"""
    source_field = serializers.CharField()
    target_field = serializers.CharField()
    function = serializers.ChoiceField(choices=[(e.value, e.name) for e in AggregateFunction])


class MergeStrategy(str, Enum):
    """字段合并策略"""
    FIRST = "first"       # 取第一个值
    LAST = "last"         # 取最后一个值
    LIST = "list"         # 收集为列表
    SUM = "sum"           # 求和
    MAX = "max"           # 取最大值
    MIN = "min"           # 取最小值
    AVG = "avg"           # 取平均值
    CONCAT = "concat"     # 字符串拼接


class ConvergeMergeRuleSerializer(serializers.Serializer):
    """收敛合并规则 - 定义收敛后各字段如何合并"""
    field = serializers.CharField(help_text="字段路径")
    merge_strategy = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in MergeStrategy],
        default=MergeStrategy.FIRST.value,
        help_text="合并策略"
    )
    separator = serializers.CharField(default=",", required=False, help_text="拼接分隔符（concat策略时生效）")
    max_list_size = serializers.IntegerField(default=100, min_value=1, max_value=1000, required=False, help_text="列表最大长度（list策略时生效）")


class ConvergeNodeConfigSerializer(BaseNodeConfigSerializer):
    """收敛节点配置"""
    node_type = serializers.CharField(default="converge", read_only=True)
    converge_key_fields = serializers.ListField(child=serializers.CharField(), help_text="收敛键字段")
    converge_key_template = serializers.CharField(required=False, allow_null=True, help_text="收敛键模板")
    strategy = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ConvergeStrategy], 
        default=ConvergeStrategy.FIRST.value,
        help_text="收敛策略：first=取首条, last=取末条, merge=合并, count=计数, aggregate=聚合"
    )
    window = ConvergeWindowSerializer(help_text="收敛窗口配置")
    aggregate_fields = AggregateFieldSerializer(many=True, required=False, help_text="聚合字段配置（strategy=aggregate时生效）")
    merge_rules = ConvergeMergeRuleSerializer(many=True, required=False, default=list, help_text="字段合并规则（strategy=merge时生效）")
    max_converge_count = serializers.IntegerField(default=100, min_value=1, max_value=10000, help_text="最大收敛数量")
    emit_on_window_close = serializers.BooleanField(default=True, help_text="窗口关闭时输出")
    emit_interval = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="定期输出间隔（秒）")
    
    def validate_converge_key_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个收敛键字段")
        return value
```

### JSON 配置示例

**示例 1: 策略+主机收敛**

```json
{
  "name": "alert_converge",
  "description": "相同策略和主机的告警收敛",
  "node_type": "converge",
  "converge_key_fields": [
    "event.strategy_id",
    "event.ip"
  ],
  "strategy": "count",
  "window": {
    "type": "fixed",
    "size": 60
  },
  "max_converge_count": 100,
  "emit_on_window_close": true
}
```

**示例 2: 滑动窗口聚合**

```json
{
  "name": "metric_aggregate",
  "description": "指标聚合收敛",
  "node_type": "converge",
  "converge_key_template": "{event.metric_name}:{event.dimension_hash}",
  "strategy": "aggregate",
  "window": {
    "type": "sliding",
    "size": 300
  },
  "aggregate_fields": [
    {
      "source_field": "event.value",
      "target_field": "aggregated.avg_value",
      "function": "avg"
    },
    {
      "source_field": "event.value",
      "target_field": "aggregated.max_value",
      "function": "max"
    },
    {
      "source_field": "event.value",
      "target_field": "aggregated.count",
      "function": "count"
    }
  ]
}
```

---

## 限流节点配置 (RateLimitNodeConfigSerializer)

限流节点用于控制事件处理的速率，防止下游系统过载。

### 数据结构定义

```python
from rest_framework import serializers


class RateLimitAlgorithm(str, Enum):
    """限流算法"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    LEAKY_BUCKET = "leaky_bucket"


class RateLimitNodeConfigSerializer(BaseNodeConfigSerializer):
    """限流节点配置"""
    node_type = serializers.CharField(default="rate_limit", read_only=True)
    rate_limit_key_template = serializers.CharField(help_text="限流键模板")
    algorithm = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RateLimitAlgorithm], 
        default=RateLimitAlgorithm.TOKEN_BUCKET.value
    )
    limit = serializers.IntegerField(min_value=1, help_text="限流阈值")
    window = serializers.IntegerField(default=60, min_value=1, max_value=86400, help_text="时间窗口（秒）")
    burst = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="突发容量")
    refill_rate = serializers.FloatField(required=False, allow_null=True, min_value=0.1, help_text="令牌填充速率")
    on_limit_action = serializers.ChoiceField(
        choices=[("drop", "drop"), ("queue", "queue"), ("delay", "delay")], 
        default="drop"
    )
    queue_size = serializers.IntegerField(default=1000, min_value=1)
    delay_max = serializers.IntegerField(default=30, min_value=1, max_value=300)
```

### JSON 配置示例

**示例 1: 策略级别限流**

```json
{
  "name": "strategy_rate_limit",
  "description": "每个策略每分钟最多 100 条告警",
  "node_type": "rate_limit",
  "rate_limit_key_template": "strategy:{event.strategy_id}",
  "algorithm": "sliding_window",
  "limit": 100,
  "window": 60,
  "on_limit_action": "drop"
}
```

**示例 2: 令牌桶限流（支持突发）**

```json
{
  "name": "notification_rate_limit",
  "description": "通知限流，支持突发",
  "node_type": "rate_limit",
  "rate_limit_key_template": "notification:{event.biz_id}",
  "algorithm": "token_bucket",
  "limit": 50,
  "window": 60,
  "burst": 100,
  "refill_rate": 0.8,
  "on_limit_action": "queue",
  "queue_size": 500
}
```

---

## 通知节点配置 (NotificationNodeConfigSerializer)

通知节点用于发送告警通知，支持多种通知渠道。

### 数据结构定义

```python
from rest_framework import serializers


class NotificationChannel(str, Enum):
    """通知渠道"""
    EMAIL = "email"
    SMS = "sms"
    VOICE = "voice"
    WECHAT = "wechat"
    WEWORK = "wework"
    SLACK = "slack"
    WEBHOOK = "webhook"
    DINGDING = "dingding"


class RecipientSource(str, Enum):
    """收件人来源"""
    STATIC = "static"
    FIELD = "field"
    CMDB = "cmdb"
    API = "api"


class RecipientConfigSerializer(serializers.Serializer):
    """收件人配置"""
    source = serializers.ChoiceField(choices=[(e.value, e.name) for e in RecipientSource])
    static_recipients = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    field_path = serializers.CharField(required=False, allow_null=True)
    cmdb_role = serializers.CharField(required=False, allow_null=True)


class TemplateConfigSerializer(serializers.Serializer):
    """消息模板配置"""
    title_template = serializers.CharField(help_text="标题模板")
    content_template = serializers.CharField(help_text="内容模板")
    template_format = serializers.ChoiceField(
        choices=[("text", "text"), ("html", "html"), ("markdown", "markdown")], 
        default="text",
        help_text="模板格式"
    )


class NotificationFrequencyControlSerializer(serializers.Serializer):
    """通知频率控制配置"""
    enabled = serializers.BooleanField(default=True, help_text="是否启用频率控制")
    frequency_key_fields = serializers.ListField(
        child=serializers.CharField(),
        default=["event.strategy_id", "event.target"],
        help_text="频率控制键字段"
    )
    max_notifications_per_window = serializers.IntegerField(default=5, min_value=1, max_value=100, help_text="窗口内最大通知次数")
    window_size = serializers.IntegerField(default=3600, min_value=60, max_value=86400, help_text="控制窗口大小（秒）")
    on_exceed_action = serializers.ChoiceField(
        choices=[("drop", "drop"), ("queue", "queue"), ("summarize", "summarize")],
        default="drop",
        help_text="超出限制后的动作：drop=丢弃, queue=队列等待, summarize=汇总发送"
    )
    summarize_interval = serializers.IntegerField(
        default=3600, 
        min_value=60, 
        required=False,
        help_text="汇总发送间隔（秒，on_exceed_action=summarize时生效）"
    )


class NotificationNodeConfigSerializer(BaseNodeConfigSerializer):
    """通知节点配置"""
    node_type = serializers.CharField(default="notification", read_only=True)
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=[(e.value, e.name) for e in NotificationChannel]),
        help_text="通知渠道"
    )
    recipients = RecipientConfigSerializer(help_text="收件人配置")
    template = TemplateConfigSerializer(help_text="消息模板")
    send_on_recovery = serializers.BooleanField(default=True, help_text="是否在恢复时发送通知")
    merge_notifications = serializers.BooleanField(default=False, help_text="是否合并通知")
    merge_window = serializers.IntegerField(default=60, min_value=1, help_text="合并窗口（秒）")
    retry_on_failure = serializers.BooleanField(default=True, help_text="失败时重试")
    max_retries = serializers.IntegerField(default=3, min_value=1, max_value=10, help_text="最大重试次数")
    frequency_control = NotificationFrequencyControlSerializer(required=False, allow_null=True, help_text="频率控制配置")
    
    def validate_channels(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个通知渠道")
        return value
```

### JSON 配置示例

**示例 1: 多渠道通知**

```json
{
  "name": "alert_notification",
  "description": "告警多渠道通知",
  "node_type": "notification",
  "channels": ["wework", "email"],
  "recipients": {
    "source": "cmdb",
    "cmdb_role": "operator"
  },
  "template": {
    "title_template": "[{{ event.severity_display }}] {{ event.alert_name }}",
    "content_template": "告警详情:\n- 策略: {{ event.strategy_name }}\n- 目标: {{ event.target }}\n- 时间: {{ event.time | format_datetime }}\n- 当前值: {{ event.current_value }}",
    "template_format": "markdown"
  },
  "send_on_recovery": true,
  "merge_notifications": true,
  "merge_window": 120
}
```

**示例 2: Webhook 通知**

```json
{
  "name": "webhook_notification",
  "description": "Webhook 告警推送",
  "node_type": "notification",
  "channels": ["webhook"],
  "recipients": {
    "source": "static",
    "static_recipients": [
      "https://ops.example.com/api/alerts"
    ]
  },
  "template": {
    "title_template": "{{ event.alert_name }}",
    "content_template": "{{ event | tojson }}",
    "template_format": "text"
  }
}
```

---

## 动作节点配置 (ActionNodeConfigSerializer)

动作节点用于触发自动化动作，如调用 Job 作业、SOPS 流程等。

### 数据结构定义

```python
from rest_framework import serializers


class ActionType(str, Enum):
    """动作类型"""
    JOB = "job"
    SOPS = "sops"
    WEBHOOK = "webhook"
    ITSM = "itsm"
    SCRIPT = "script"


class ActionParamConfigSerializer(serializers.Serializer):
    """动作参数配置"""
    name = serializers.CharField()
    value = serializers.JSONField(default=None, required=False, allow_null=True)
    value_template = serializers.CharField(required=False, allow_null=True)
    required = serializers.BooleanField(default=True)


class ActionNodeConfigSerializer(BaseNodeConfigSerializer):
    """动作节点配置"""
    node_type = serializers.CharField(default="action", read_only=True)
    action_type = serializers.ChoiceField(choices=[(e.value, e.name) for e in ActionType])
    action_id = serializers.CharField()
    params = ActionParamConfigSerializer(many=True, required=False)
    execute_condition = ConditionGroupSerializer(required=False, allow_null=True)
    wait_for_completion = serializers.BooleanField(default=False)
    completion_timeout = serializers.IntegerField(default=300, min_value=1, max_value=3600)
    on_failure = serializers.ChoiceField(
        choices=[("ignore", "ignore"), ("fail", "fail"), ("retry", "retry")], 
        default="ignore"
    )
```

### JSON 配置示例

**示例 1: 自动重启服务**

```json
{
  "name": "auto_restart_service",
  "description": "服务异常时自动重启",
  "node_type": "action",
  "action_type": "job",
  "action_id": "12345",
  "params": [
    {
      "name": "bk_biz_id",
      "value_template": "{event.biz_id}"
    },
    {
      "name": "ip",
      "value_template": "{event.ip}"
    },
    {
      "name": "service_name",
      "value_template": "{event.service_name}"
    }
  ],
  "execute_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.severity",
        "operator": "gte",
        "value": 4
      },
      {
        "field": "event.action_enabled",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "wait_for_completion": true,
  "completion_timeout": 120,
  "on_failure": "retry"
}
```

**示例 2: 创建 ITSM 工单**

```json
{
  "name": "create_incident",
  "description": "高级别告警创建工单",
  "node_type": "action",
  "action_type": "itsm",
  "action_id": "incident_template_v1",
  "params": [
    {
      "name": "title",
      "value_template": "[告警] {event.alert_name}"
    },
    {
      "name": "priority",
      "value_template": "{event.severity}"
    },
    {
      "name": "description",
      "value_template": "告警详情: {event.content}"
    }
  ],
  "execute_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.severity",
        "operator": "gte",
        "value": 4
      }
    ]
  },
  "wait_for_completion": false
}
```

---

## 去重节点配置 (DedupeNodeConfigSerializer)

去重节点用于识别和过滤重复事件。

### 数据结构定义

```python
from rest_framework import serializers


class DedupeNodeConfigSerializer(BaseNodeConfigSerializer):
    """去重节点配置"""
    node_type = serializers.CharField(default="dedupe", read_only=True)
    dedupe_key_fields = serializers.ListField(child=serializers.CharField(), help_text="去重键字段")
    dedupe_key_template = serializers.CharField(required=False, allow_null=True)
    dedupe_window = serializers.IntegerField(default=300, min_value=1, max_value=86400, help_text="去重时间窗口")
    on_duplicate = serializers.ChoiceField(
        choices=[("drop", "drop"), ("update", "update"), ("merge", "merge")], 
        default="drop"
    )
    update_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    
    def validate_dedupe_key_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个去重键字段")
        return value
```

### JSON 配置示例

```json
{
  "name": "alert_dedupe",
  "description": "告警去重",
  "node_type": "dedupe",
  "dedupe_key_fields": [
    "event.strategy_id",
    "event.dimension_hash"
  ],
  "dedupe_window": 600,
  "on_duplicate": "update",
  "update_fields": [
    "event.current_value",
    "event.update_time"
  ]
}
```

---

## 转换节点配置 (TransformNodeConfigSerializer)

转换节点用于数据格式转换和字段映射。

### 数据结构定义

```python
from rest_framework import serializers


class TransformOperation(str, Enum):
    """转换操作类型"""
    RENAME = "rename"
    COPY = "copy"
    DELETE = "delete"
    SET = "set"
    TEMPLATE = "template"
    JMESPATH = "jmespath"
    JSONLOGIC = "jsonlogic"


class TransformRuleSerializer(serializers.Serializer):
    """转换规则"""
    operation = serializers.ChoiceField(choices=[(e.value, e.name) for e in TransformOperation])
    source_field = serializers.CharField(required=False, allow_null=True)
    target_field = serializers.CharField(required=False, allow_null=True)
    value = serializers.JSONField(required=False, allow_null=True)
    template = serializers.CharField(required=False, allow_null=True)
    expression = serializers.CharField(required=False, allow_null=True)


class TransformNodeConfigSerializer(BaseNodeConfigSerializer):
    """转换节点配置"""
    node_type = serializers.CharField(default="transform", read_only=True)
    rules = TransformRuleSerializer(many=True, help_text="转换规则列表")
    fail_on_error = serializers.BooleanField(default=False)
    preserve_original = serializers.BooleanField(default=True)
    
    def validate_rules(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一条转换规则")
        return value
```

### JSON 配置示例

```json
{
  "name": "data_transform",
  "description": "数据格式转换",
  "node_type": "transform",
  "rules": [
    {
      "operation": "rename",
      "source_field": "event.host_ip",
      "target_field": "event.ip"
    },
    {
      "operation": "set",
      "target_field": "event.source",
      "value": "bk_monitor"
    },
    {
      "operation": "template",
      "target_field": "event.display_name",
      "template": "{{ event.alert_name }} - {{ event.target }}"
    },
    {
      "operation": "jmespath",
      "source_field": "event.dimensions",
      "target_field": "event.dimension_hash",
      "expression": "join('-', sort(keys(@)))"
    }
  ],
  "fail_on_error": false,
  "preserve_original": true
}
```

---

## 路由节点配置 (RouterNodeConfigSerializer)

路由节点用于根据条件将事件路由到不同的处理分支。

### 数据结构定义

```python
from rest_framework import serializers


class RouteRuleSerializer(serializers.Serializer):
    """路由规则"""
    name = serializers.CharField()
    condition = ConditionGroupSerializer()
    target_stage = serializers.CharField()
    priority = serializers.IntegerField(default=0, min_value=0, max_value=100)


class RouterNodeConfigSerializer(BaseNodeConfigSerializer):
    """路由节点配置"""
    node_type = serializers.CharField(default="router", read_only=True)
    routes = RouteRuleSerializer(many=True, help_text="路由规则列表")
    default_stage = serializers.CharField(required=False, allow_null=True)
    match_mode = serializers.ChoiceField(choices=[("first", "first"), ("all", "all")], default="first")
    
    def validate_routes(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一条路由规则")
        return value
```

### JSON 配置示例

```json
{
  "name": "severity_router",
  "description": "按告警级别路由",
  "node_type": "router",
  "routes": [
    {
      "name": "critical_route",
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
      "target_stage": "critical_handling",
      "priority": 100
    },
    {
      "name": "warning_route",
      "condition": {
        "logic": "and",
        "conditions": [
          {
            "field": "event.severity",
            "operator": "eq",
            "value": 3
          }
        ]
      },
      "target_stage": "warning_handling",
      "priority": 50
    }
  ],
  "default_stage": "normal_handling",
  "match_mode": "first"
}
```

---

## 节点注册与配置验证

### 节点类型注册表

```python
from typing import Type, Dict
from rest_framework import serializers


class NodeConfigRegistry:
    """节点配置注册表"""
    
    _configs: Dict[NodeType, Type[serializers.Serializer]] = {
        # 数据处理类节点
        NodeType.FILTER: FilterNodeConfigSerializer,
        NodeType.TRANSFORM: TransformNodeConfigSerializer,
        NodeType.ENRICHMENT: EnrichmentNodeConfigSerializer,
        NodeType.AGGREGATE: AggregateNodeConfigSerializer,
        NodeType.WINDOW: WindowNodeConfigSerializer,
        NodeType.SAMPLE: SampleNodeConfigSerializer,
        NodeType.SPLIT: SplitNodeConfigSerializer,
        NodeType.JOIN: JoinNodeConfigSerializer,
        
        # 检测类节点
        NodeType.THRESHOLD: ThresholdNodeConfigSerializer,
        NodeType.ANOMALY: AnomalyNodeConfigSerializer,
        NodeType.BASELINE: BaselineNodeConfigSerializer,
        NodeType.TREND: TrendNodeConfigSerializer,
        NodeType.CORRELATION: CorrelationNodeConfigSerializer,
        
        # 流程控制类节点
        NodeType.ROUTER: RouterNodeConfigSerializer,
        NodeType.CIRCUIT_BREAKER: CircuitBreakerNodeConfigSerializer,
        NodeType.RATE_LIMIT: RateLimitNodeConfigSerializer,
        NodeType.DEDUPE: DedupeNodeConfigSerializer,
        NodeType.CONVERGE: ConvergeNodeConfigSerializer,
        NodeType.DELAY: DelayNodeConfigSerializer,
        NodeType.FORK: ForkNodeConfigSerializer,
        NodeType.MERGE: MergeNodeConfigSerializer,
        
        # 告警生命周期类节点
        NodeType.SHIELD: ShieldNodeConfigSerializer,
        NodeType.SUPPRESS: SuppressNodeConfigSerializer,
        NodeType.RECOVERY: RecoveryNodeConfigSerializer,
        NodeType.ESCALATION: EscalationNodeConfigSerializer,
        NodeType.ACKNOWLEDGE: AcknowledgeNodeConfigSerializer,
        NodeType.SEVERITY: SeverityNodeConfigSerializer,
        NodeType.NO_MONITOR: NoMonitorNodeConfigSerializer,
        
        # 动作类节点
        NodeType.NOTIFICATION: NotificationNodeConfigSerializer,
        NodeType.ACTION: ActionNodeConfigSerializer,
        NodeType.WEBHOOK: WebhookNodeConfigSerializer,
        NodeType.INCIDENT: IncidentNodeConfigSerializer,
        NodeType.CALLBACK: CallbackNodeConfigSerializer,
        
        # 存储类节点
        NodeType.STORAGE: StorageNodeConfigSerializer,
        NodeType.QUERY: QueryNodeConfigSerializer,
        NodeType.LOG: LogNodeConfigSerializer,
        NodeType.METRIC: MetricNodeConfigSerializer,
    }
    
    @classmethod
    def get_config_class(cls, node_type: NodeType) -> Type[serializers.Serializer]:
        """获取节点配置序列化器类"""
        if node_type not in cls._configs:
            raise ValueError(f"Unknown node type: {node_type}")
        return cls._configs[node_type]
    
    @classmethod
    def validate_config(cls, node_type: NodeType, config: Dict) -> Dict:
        """验证并解析节点配置"""
        serializer_class = cls.get_config_class(node_type)
        serializer = serializer_class(data=config)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
    
    @classmethod
    def register(cls, node_type: NodeType, config_class: Type[serializers.Serializer]):
        """注册自定义节点配置序列化器类"""
        cls._configs[node_type] = config_class
```

### 配置验证示例

```python
# 使用示例
config_dict = {
    "name": "my_filter",
    "description": "过滤低级别告警",
    "match_mode": "all",
    "conditions": [
        {"field": "event.severity", "operator": "gte", "value": 3}
    ]
}

# 验证配置
try:
    validated_config = NodeConfigRegistry.validate_config(
        NodeType.FILTER, 
        config_dict
    )
    print(f"配置验证成功: {validated_config['name']}")
except serializers.ValidationError as e:
    print(f"配置验证失败: {e.detail}")
```

---

## 完整 Pipeline 配置示例

```json
{
  "id": "alert_pipeline_v1",
  "name": "标准告警处理流水线",
  "version": "1.0.0",
  "description": "完整的告警处理流程",
  "scenario": "monitoring",
  "enabled": true,
  "global_config": {
    "default_timeout": 30,
    "trace_enabled": true,
    "metrics_enabled": true
  },
  "stages": [
    {
      "name": "preprocessing",
      "type": "sequential",
      "processors": [
        {
          "node_type": "transform",
          "name": "data_normalize",
          "rules": [
            {
              "operation": "rename",
              "source_field": "raw_event.ip",
              "target_field": "event.ip"
            },
            {
              "operation": "set",
              "target_field": "event.source",
              "value": "bk_monitor"
            }
          ]
        },
        {
          "node_type": "enrichment",
          "name": "host_enrichment",
          "lookup_field": "event.ip",
          "data_source": {
            "type": "cmdb",
            "cmdb_object_type": "host"
          },
          "field_mappings": [
            {
              "source_field": "bk_biz_id",
              "target_field": "event.biz_id"
            }
          ]
        }
      ]
    },
    {
      "name": "filtering",
      "type": "sequential",
      "processors": [
        {
          "node_type": "dedupe",
          "name": "alert_dedupe",
          "dedupe_key_fields": ["event.strategy_id", "event.dimension_hash"],
          "dedupe_window": 300
        },
        {
          "node_type": "filter",
          "name": "severity_filter",
          "match_mode": "all",
          "conditions": [
            {
              "field": "event.severity",
              "operator": "gte",
              "value": 2
            }
          ]
        },
        {
          "node_type": "shield",
          "name": "maintenance_shield",
          "rules_source": "database",
          "rules_cache_ttl": 60
        }
      ]
    },
    {
      "name": "flow_control",
      "type": "sequential",
      "processors": [
        {
          "node_type": "circuit_breaker",
          "name": "strategy_breaker",
          "breaker_key_template": "strategy:{event.strategy_id}",
          "failure_threshold": 10,
          "window_size": 60
        },
        {
          "node_type": "rate_limit",
          "name": "strategy_rate_limit",
          "rate_limit_key_template": "strategy:{event.strategy_id}",
          "limit": 100,
          "window": 60
        }
      ]
    },
    {
      "name": "converging",
      "type": "sequential",
      "processors": [
        {
          "node_type": "converge",
          "name": "alert_converge",
          "converge_key_fields": ["event.strategy_id", "event.ip"],
          "strategy": "count",
          "window": {
            "type": "fixed",
            "size": 60
          }
        }
      ]
    },
    {
      "name": "routing",
      "type": "conditional",
      "processors": [
        {
          "node_type": "router",
          "name": "severity_router",
          "routes": [
            {
              "name": "critical",
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
              "target_stage": "critical_handling"
            }
          ],
          "default_stage": "normal_handling"
        }
      ]
    },
    {
      "name": "critical_handling",
      "type": "parallel",
      "processors": [
        {
          "node_type": "notification",
          "name": "emergency_notification",
          "channels": ["voice", "sms", "wework"],
          "recipients": {
            "source": "cmdb",
            "cmdb_role": "operator"
          },
          "template": {
            "title_template": "[紧急] {{ event.alert_name }}",
            "content_template": "紧急告警，请立即处理！"
          }
        },
        {
          "node_type": "action",
          "name": "auto_recovery",
          "action_type": "job",
          "action_id": "auto_recovery_job",
          "params": [
            {
              "name": "bk_biz_id",
              "value_template": "{event.biz_id}"
            }
          ]
        }
      ]
    },
    {
      "name": "normal_handling",
      "type": "sequential",
      "processors": [
        {
          "node_type": "notification",
          "name": "normal_notification",
          "channels": ["wework", "email"],
          "recipients": {
            "source": "cmdb",
            "cmdb_role": "operator"
          },
          "template": {
            "title_template": "[{{ event.severity_display }}] {{ event.alert_name }}",
            "content_template": "告警详情..."
          }
        }
      ]
    }
  ],
  "error_handling": {
    "on_error": "continue",
    "log_errors": true,
    "retry_failed": true
  },
  "metrics_config": {
    "enabled": true,
    "export_interval": 60
  }
}
```

---

## 节点类型汇总表

| 节点类型 | 配置类 | 用途 |
|---------|-------|------|
| filter | FilterNodeConfigSerializer | 条件过滤 |
| enrichment | EnrichmentNodeConfigSerializer | 数据丰富 |
| circuit_breaker | CircuitBreakerNodeConfigSerializer | 熔断保护 |
| shield | ShieldNodeConfigSerializer | 屏蔽规则 |
| converge | ConvergeNodeConfigSerializer | 告警收敛 |
| rate_limit | RateLimitNodeConfigSerializer | 限流控制 |
| notification | NotificationNodeConfigSerializer | 通知发送 |
| action | ActionNodeConfigSerializer | 自动化动作 |
| dedupe | DedupeNodeConfigSerializer | 去重 |
| transform | TransformNodeConfigSerializer | 数据转换 |
| router | RouterNodeConfigSerializer | 条件路由 |

> 更多节点配置请参阅 [扩展节点配置数据结构](./09-extended-node-configs.md)

---

**上一篇**: [第三方库使用](./07-third-party-libs.md) | **下一篇**: [扩展节点配置](./09-extended-node-configs.md)

---

> 返回 [目录](./README.md)
