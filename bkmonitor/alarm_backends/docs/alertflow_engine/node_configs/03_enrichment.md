# Enrichment Node Configuration (丰富化节点配置)

## 节点类型
- **NodeType**: `enrichment`
- **分类**: DATA_PROCESSING (数据处理类)
- **功能**: 从外部数据源获取额外信息并添加到事件数据中

## 配置 Schema

### EnrichmentNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class DataSourceType(str, Enum):
    """数据源类型"""
    CMDB = "cmdb"           # 配置管理数据库
    CACHE = "cache"         # Redis 缓存
    DATABASE = "database"   # 关系数据库
    HTTP = "http"           # HTTP API
    STATIC = "static"       # 静态映射


class FieldMappingSerializer(serializers.Serializer):
    """字段映射配置"""
    source_field = serializers.CharField(help_text="源字段路径（数据源返回的字段）")
    target_field = serializers.CharField(help_text="目标字段路径（添加到事件的字段）")
    default_value = serializers.JSONField(
        default=None,
        required=False,
        help_text="默认值（数据源无数据时使用）"
    )
    transform = serializers.CharField(
        default=None,
        required=False,
        allow_null=True,
        help_text="转换表达式（对源字段进行转换）"
    )


class DataSourceConfigSerializer(serializers.Serializer):
    """数据源配置"""
    type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in DataSourceType],
        help_text="数据源类型"
    )
    
    # HTTP 数据源
    url = serializers.CharField(required=False, allow_null=True, help_text="HTTP API URL（支持模板变量）")
    method = serializers.ChoiceField(
        choices=[("GET", "GET"), ("POST", "POST")],
        default="GET",
        required=False,
        help_text="HTTP 请求方法"
    )
    headers = serializers.DictField(default=dict, required=False, help_text="HTTP 请求头")
    params_template = serializers.DictField(required=False, allow_null=True, help_text="请求参数模板")
    response_path = serializers.CharField(required=False, allow_null=True, help_text="响应数据路径（JSONPath）")
    
    # CMDB 数据源
    cmdb_object_type = serializers.CharField(required=False, allow_null=True, help_text="CMDB 对象类型")
    cmdb_lookup_field = serializers.CharField(required=False, allow_null=True, help_text="CMDB 查询字段")
    
    # Cache 数据源
    cache_key_template = serializers.CharField(required=False, allow_null=True, help_text="缓存键模板")
    cache_ttl = serializers.IntegerField(default=300, required=False, help_text="缓存 TTL（秒）")
    
    # Database 数据源
    db_connection = serializers.CharField(required=False, allow_null=True, help_text="数据库连接名")
    db_query = serializers.CharField(required=False, allow_null=True, help_text="SQL 查询语句")
    
    # Static 数据源
    static_mapping = serializers.DictField(required=False, allow_null=True, help_text="静态映射表")


class EnrichmentNodeConfigSerializer(BaseNodeConfigSerializer):
    """丰富化节点配置"""
    node_type = serializers.CharField(default="enrichment", read_only=True)
    
    # 查询配置
    lookup_field = serializers.CharField(help_text="查询字段路径（从事件中提取用于查询的值）")
    
    # 数据源配置
    data_source = DataSourceConfigSerializer(help_text="数据源配置")
    
    # 字段映射
    field_mappings = FieldMappingSerializer(many=True, help_text="字段映射列表")
    
    # 错误处理
    fail_on_missing = serializers.BooleanField(
        default=False,
        help_text="无数据时是否失败（False=使用默认值或跳过）"
    )
    
    # 缓存配置
    cache_enabled = serializers.BooleanField(default=True, help_text="是否启用缓存")
    cache_ttl = serializers.IntegerField(
        default=300,
        min_value=0,
        help_text="缓存 TTL（秒）"
    )
    
    def validate_field_mappings(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个字段映射")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "enrichment" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `lookup_field` | string | 是 | - | 查询字段路径 |
| `data_source` | object | 是 | - | 数据源配置 |
| `field_mappings` | array | 是 | - | 字段映射列表 |
| `fail_on_missing` | boolean | 否 | false | 无数据时是否失败 |
| `cache_enabled` | boolean | 否 | true | 是否启用缓存 |
| `cache_ttl` | integer | 否 | 300 | 缓存 TTL（秒） |

### 数据源配置字段 (DataSourceConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 数据源类型：cmdb/cache/database/http/static |
| `url` | string | 否 | HTTP API URL（type=http 时必填） |
| `method` | string | 否 | HTTP 请求方法（GET/POST） |
| `headers` | object | 否 | HTTP 请求头 |
| `params_template` | object | 否 | 请求参数模板 |
| `response_path` | string | 否 | 响应数据路径 |
| `cmdb_object_type` | string | 否 | CMDB 对象类型（type=cmdb 时必填） |
| `cmdb_lookup_field` | string | 否 | CMDB 查询字段 |
| `cache_key_template` | string | 否 | 缓存键模板（type=cache 时必填） |
| `cache_ttl` | integer | 否 | 缓存 TTL |
| `db_connection` | string | 否 | 数据库连接名（type=database 时必填） |
| `db_query` | string | 否 | SQL 查询语句 |
| `static_mapping` | object | 否 | 静态映射表（type=static 时必填） |

### 字段映射配置 (FieldMapping)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_field` | string | 是 | 源字段路径（数据源返回的字段） |
| `target_field` | string | 是 | 目标字段路径（添加到事件的字段） |
| `default_value` | any | 否 | 默认值（数据源无数据时使用） |
| `transform` | string | 否 | 转换表达式 |

### 数据源类型说明

| 类型 | 说明 | 关键字段 |
|------|------|----------|
| `cmdb` | 从 CMDB 获取配置数据 | cmdb_object_type, cmdb_lookup_field |
| `cache` | 从 Redis 缓存获取 | cache_key_template, cache_ttl |
| `database` | 从数据库查询 | db_connection, db_query |
| `http` | 从 HTTP API 获取 | url, method, headers |
| `static` | 静态映射表 | static_mapping |

## JSON 配置示例

### 示例 1: CMDB 主机信息丰富

```json
{
  "name": "host_enrichment",
  "description": "从 CMDB 获取主机详细信息",
  "enabled": true,
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
    },
    {
      "source_field": "operator",
      "target_field": "event.operator",
      "default_value": []
    },
    {
      "source_field": "bk_os_type",
      "target_field": "event.os_type",
      "default_value": "linux"
    }
  ],
  "fail_on_missing": false,
  "cache_enabled": true,
  "cache_ttl": 600
}
```

### 示例 2: HTTP API 用户信息丰富

```json
{
  "name": "user_info_enrichment",
  "description": "从用户服务获取用户信息",
  "enabled": true,
  "node_type": "enrichment",
  "lookup_field": "event.user_id",
  "data_source": {
    "type": "http",
    "url": "http://user-service/api/v1/users/{user_id}",
    "method": "GET",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "Content-Type": "application/json"
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
    },
    {
      "source_field": "email",
      "target_field": "event.user_email",
      "default_value": ""
    },
    {
      "source_field": "phone",
      "target_field": "event.user_phone"
    }
  ],
  "fail_on_missing": false,
  "cache_enabled": true,
  "cache_ttl": 300
}
```

### 示例 3: Redis 缓存和静态映射

```json
{
  "name": "service_metadata_enrichment",
  "description": "服务元数据丰富（缓存+静态映射）",
  "enabled": true,
  "node_type": "enrichment",
  "lookup_field": "event.service_name",
  "data_source": {
    "type": "cache",
    "cache_key_template": "service:metadata:{event.service_name}",
    "cache_ttl": 600
  },
  "field_mappings": [
    {
      "source_field": "service_owner",
      "target_field": "event.owner"
    },
    {
      "source_field": "service_tier",
      "target_field": "event.tier",
      "default_value": "standard"
    },
    {
      "source_field": "sla_level",
      "target_field": "event.sla",
      "default_value": 99.5
    }
  ],
  "fail_on_missing": false,
  "cache_enabled": true,
  "cache_ttl": 300,
  "execution": {
    "timeout": 10,
    "retry_enabled": true,
    "retry_max_attempts": 2
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **主机信息丰富**：从 CMDB 获取主机的业务、云区、负责人等信息
2. **用户信息扩展**：从用户服务获取用户姓名、部门、联系方式等
3. **服务元数据添加**：添加服务的 SLA 等级、负责团队、优先级等信息
4. **地理位置丰富**：根据 IP 地址查询地理位置、运营商等信息
5. **配置信息补充**：从配置中心获取应用的配置参数、版本信息等
6. **告警上下文添加**：添加业务上下文、环境信息、关联资源等
7. **历史数据查询**：从数据库查询历史告警次数、最近故障等

## 注意事项

1. **数据源选择**：
   - CMDB：适合获取主机、业务、模块等配置数据
   - HTTP：适合调用第三方 API 服务
   - Cache：适合高频查询的数据，需提前写入缓存
   - Database：适合复杂查询逻辑，但注意性能影响
   - Static：适合小量静态数据映射

2. **性能优化**：
   - 强烈建议启用缓存（`cache_enabled=true`）
   - 根据数据更新频率设置合理的 `cache_ttl`
   - HTTP 请求需设置较短的 timeout，防止阻塞
   - Database 查询应加索引，避免全表扫描

3. **错误处理**：
   - `fail_on_missing=false`：查询失败时使用默认值或跳过
   - `fail_on_missing=true`：查询失败时整个节点失败
   - 建议为所有字段设置 `default_value`

4. **字段映射**：
   - `source_field` 支持嵌套路径，如 `data.user.name`
   - `target_field` 应使用标准的字段命名约定
   - 可使用 `transform` 进行字段转换（支持 JMESPath）

5. **URL 模板变量**：
   - HTTP URL 支持模板变量，如 `{user_id}`、`{event.ip}`
   - 变量会从 `lookup_field` 指定的字段中提取

6. **安全性**：
   - HTTP 请求应使用 HTTPS
   - 敏感信息（如 Token）应使用环境变量 `${VAR_NAME}`
   - Database 查询应防止 SQL 注入

7. **数据一致性**：
   - CMDB 数据可能延迟同步，注意缓存时间
   - 外部 API 可能返回空值或错误，需处理好异常情况

8. **测试建议**：
   - 先在测试环境验证数据源连接
   - 检查字段映射是否正确
   - 验证默认值是否合理

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再丰富，减少不必要的查询
  - Transform（转换节点）：先转换字段再查询丰富
  
- **下游节点**：
  - Transform（转换节点）：对丰富后的数据进行进一步格式化
  - Router（路由节点）：基于丰富后的字段进行路由决策
  - Notification（通知节点）：使用丰富后的字段发送通知
  - Storage（存储节点）：存储完整的丰富数据

### 典型组合模式

1. **Filter → Enrichment → Transform → Notification**
   - 过滤 → 丰富 → 转换 → 通知
   
2. **Enrichment → Router → [Multiple Paths]**
   - 丰富 → 路由 → 不同处理路径
   
3. **Transform → Enrichment → Enrichment → Storage**
   - 转换 → 多次丰富 → 存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
