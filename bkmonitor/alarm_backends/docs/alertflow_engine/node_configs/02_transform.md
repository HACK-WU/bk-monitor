# Transform Node Configuration (转换节点配置)

## 节点类型
- **NodeType**: `transform`
- **分类**: DATA_PROCESSING (数据处理类)
- **功能**: 转换事件数据字段，支持重命名、计算、删除等操作

## 配置 Schema

### TransformNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class TransformOperation(str, Enum):
    """转换操作类型"""
    RENAME = "rename"      # 字段重命名
    COPY = "copy"          # 字段复制
    DELETE = "delete"      # 字段删除
    SET = "set"            # 字段设置固定值
    TEMPLATE = "template"  # 模板渲染
    JMESPATH = "jmespath"  # JMESPath 表达式
    JSONLOGIC = "jsonlogic"  # JSONLogic 表达式


class TransformRuleSerializer(serializers.Serializer):
    """转换规则"""
    operation = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in TransformOperation],
        help_text="转换操作类型"
    )
    source_field = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="源字段路径（用于 rename/copy/jmespath 等操作）"
    )
    target_field = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="目标字段路径"
    )
    value = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="固定值（用于 set 操作）"
    )
    template = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="模板字符串（用于 template 操作）"
    )
    expression = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="表达式（用于 jmespath/jsonlogic 操作）"
    )


class TransformNodeConfigSerializer(BaseNodeConfigSerializer):
    """转换节点配置"""
    node_type = serializers.CharField(default="transform", read_only=True)
    
    # 转换规则列表
    rules = TransformRuleSerializer(many=True, help_text="转换规则列表")
    
    # 错误处理
    fail_on_error = serializers.BooleanField(
        default=False,
        help_text="转换出错时是否失败（False=跳过错误规则继续执行）"
    )
    
    # 原始数据保留
    preserve_original = serializers.BooleanField(
        default=True,
        help_text="是否保留原始字段（False=删除源字段）"
    )
    
    def validate_rules(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一条转换规则")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "transform" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `rules` | array | 是 | - | 转换规则列表 |
| `fail_on_error` | boolean | 否 | false | 转换出错时是否失败 |
| `preserve_original` | boolean | 否 | true | 是否保留原始字段 |

### 转换规则字段 (TransformRule)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `operation` | string | 是 | 转换操作：rename/copy/delete/set/template/jmespath/jsonlogic |
| `source_field` | string | 否 | 源字段路径（用于 rename/copy/jmespath） |
| `target_field` | string | 否 | 目标字段路径 |
| `value` | any | 否 | 固定值（用于 set 操作） |
| `template` | string | 否 | 模板字符串（用于 template 操作） |
| `expression` | string | 否 | 表达式（用于 jmespath/jsonlogic） |

### 转换操作类型说明

| 操作 | 说明 | 必需字段 |
|------|------|----------|
| `rename` | 字段重命名 | source_field, target_field |
| `copy` | 字段复制 | source_field, target_field |
| `delete` | 字段删除 | source_field |
| `set` | 设置固定值 | target_field, value |
| `template` | 模板渲染 | target_field, template |
| `jmespath` | JMESPath 表达式 | source_field, target_field, expression |
| `jsonlogic` | JSONLogic 表达式 | target_field, expression |

## JSON 配置示例

### 示例 1: 字段重命名和设置

```json
{
  "name": "normalize_event",
  "description": "标准化事件字段",
  "enabled": true,
  "node_type": "transform",
  "rules": [
    {
      "operation": "rename",
      "source_field": "event.host_ip",
      "target_field": "event.ip"
    },
    {
      "operation": "rename",
      "source_field": "event.alert_title",
      "target_field": "event.alert_name"
    },
    {
      "operation": "set",
      "target_field": "event.source",
      "value": "bk_monitor"
    },
    {
      "operation": "set",
      "target_field": "event.processed_time",
      "value": "{{ now() }}"
    }
  ],
  "fail_on_error": false,
  "preserve_original": false
}
```

### 示例 2: 模板渲染和表达式计算

```json
{
  "name": "enrich_display_fields",
  "description": "丰富展示字段",
  "enabled": true,
  "node_type": "transform",
  "rules": [
    {
      "operation": "template",
      "target_field": "event.display_name",
      "template": "[{{ event.severity_display }}] {{ event.alert_name }} - {{ event.target }}"
    },
    {
      "operation": "template",
      "target_field": "event.alert_url",
      "template": "https://monitor.example.com/alerts/{{ event.alert_id }}"
    },
    {
      "operation": "jmespath",
      "source_field": "event.dimensions",
      "target_field": "event.dimension_hash",
      "expression": "join('-', sort(keys(@)))"
    },
    {
      "operation": "jmespath",
      "source_field": "event.tags",
      "target_field": "event.tag_list",
      "expression": "keys(@)"
    }
  ],
  "fail_on_error": false,
  "preserve_original": true
}
```

### 示例 3: 复杂数据转换

```json
{
  "name": "complex_transform",
  "description": "复杂数据转换和清理",
  "enabled": true,
  "node_type": "transform",
  "rules": [
    {
      "operation": "copy",
      "source_field": "event.raw_value",
      "target_field": "event.original_value"
    },
    {
      "operation": "jmespath",
      "source_field": "event.metrics",
      "target_field": "event.cpu_usage",
      "expression": "cpu.usage_percent"
    },
    {
      "operation": "jmespath",
      "source_field": "event.metrics",
      "target_field": "event.memory_usage",
      "expression": "memory.used_percent"
    },
    {
      "operation": "delete",
      "source_field": "event.temp_data"
    },
    {
      "operation": "delete",
      "source_field": "event.internal_fields"
    },
    {
      "operation": "template",
      "target_field": "event.summary",
      "template": "主机 {{ event.hostname }} CPU使用率 {{ event.cpu_usage }}%, 内存使用率 {{ event.memory_usage }}%"
    }
  ],
  "fail_on_error": true,
  "preserve_original": true,
  "execution": {
    "timeout": 30,
    "retry_enabled": true,
    "retry_max_attempts": 3
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **字段标准化**：统一不同数据源的字段命名，如将 `host_ip` 重命名为 `ip`
2. **数据清理**：删除临时字段或敏感信息字段
3. **字段计算**：使用 JMESPath 或 JSONLogic 从复杂结构中提取或计算新字段
4. **展示字段生成**：使用模板生成友好的展示文本，如告警标题、摘要等
5. **数据复制备份**：在修改字段前先复制原始值用于审计
6. **字段格式转换**：将数组、对象等复杂结构转换为字符串或哈希值
7. **默认值设置**：为缺失字段设置默认值

## 注意事项

1. **规则顺序**：转换规则按配置顺序依次执行，后续规则可以引用前面规则生成的字段
2. **字段路径**：支持嵌套字段路径，如 `event.dimensions.hostname`
3. **模板语法**：template 操作支持 Jinja2 模板语法
4. **JMESPath 表达式**：需要熟悉 JMESPath 语法，推荐先在在线工具测试
5. **错误处理**：
   - `fail_on_error=false`：单个规则失败时跳过该规则继续执行
   - `fail_on_error=true`：任何规则失败都中断整个转换
6. **原始字段保留**：
   - `preserve_original=true`：保留源字段（rename/copy 操作）
   - `preserve_original=false`：删除源字段（rename 操作变为移动）
7. **性能考虑**：复杂的 JMESPath/JSONLogic 表达式可能影响性能，谨慎使用
8. **字段冲突**：如果目标字段已存在，会被覆盖

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再转换，提高效率
  - Enrichment（丰富化节点）：先丰富数据再进行格式转换
  
- **下游节点**：
  - Router（路由节点）：基于转换后的字段进行路由
  - Notification（通知节点）：使用转换后的展示字段发送通知
  - Storage（存储节点）：存储转换后的标准化数据

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
