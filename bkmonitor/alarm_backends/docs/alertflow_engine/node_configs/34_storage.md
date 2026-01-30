# Storage Node Configuration (存储节点配置)

## 节点类型
- **NodeType**: `storage`
- **分类**: STORAGE (存储类)
- **功能**: 将事件数据持久化存储到指定存储后端

## 配置 Schema

### StorageNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class StorageBackend(str, Enum):
    """存储后端"""
    ELASTICSEARCH = "elasticsearch"   # ES
    MYSQL = "mysql"                   # MySQL
    REDIS = "redis"                   # Redis
    KAFKA = "kafka"                   # Kafka
    MONGODB = "mongodb"               # MongoDB
    INFLUXDB = "influxdb"             # InfluxDB
    CLICKHOUSE = "clickhouse"         # ClickHouse
    VICTORIA_METRICS = "victoria_metrics"  # VictoriaMetrics


class StorageMode(str, Enum):
    """存储模式"""
    INSERT = "insert"           # 插入
    UPSERT = "upsert"           # 更新或插入
    UPDATE = "update"           # 更新
    APPEND = "append"           # 追加


class FieldMappingSerializer(serializers.Serializer):
    """字段映射配置"""
    source_field = serializers.CharField(help_text="源字段路径")
    target_field = serializers.CharField(help_text="目标字段名")
    field_type = serializers.ChoiceField(
        choices=[
            ("string", "字符串"),
            ("integer", "整数"),
            ("float", "浮点数"),
            ("boolean", "布尔"),
            ("datetime", "日期时间"),
            ("json", "JSON"),
        ],
        default="string",
        required=False,
        help_text="字段类型"
    )
    default_value = serializers.JSONField(
        default=None,
        required=False,
        help_text="默认值"
    )


class ElasticsearchConfigSerializer(serializers.Serializer):
    """Elasticsearch配置"""
    hosts = serializers.ListField(
        child=serializers.CharField(),
        help_text="ES节点列表"
    )
    index_pattern = serializers.CharField(
        help_text="索引名模式（支持模板变量和日期格式）"
    )
    doc_type = serializers.CharField(
        default="_doc",
        help_text="文档类型"
    )
    id_field = serializers.CharField(
        required=False,
        help_text="文档ID字段"
    )
    # 认证
    username = serializers.CharField(
        required=False,
        help_text="用户名"
    )
    password = serializers.CharField(
        required=False,
        help_text="密码"
    )
    # 批量配置
    bulk_size = serializers.IntegerField(
        default=100,
        help_text="批量写入大小"
    )
    flush_interval = serializers.IntegerField(
        default=5,
        help_text="刷新间隔（秒）"
    )


class MySQLConfigSerializer(serializers.Serializer):
    """MySQL配置"""
    connection_name = serializers.CharField(help_text="连接名称")
    database = serializers.CharField(help_text="数据库名")
    table = serializers.CharField(help_text="表名")
    primary_key = serializers.CharField(
        required=False,
        help_text="主键字段"
    )
    # 批量配置
    batch_size = serializers.IntegerField(
        default=100,
        help_text="批量写入大小"
    )


class KafkaConfigSerializer(serializers.Serializer):
    """Kafka配置"""
    bootstrap_servers = serializers.ListField(
        child=serializers.CharField(),
        help_text="Kafka服务器列表"
    )
    topic = serializers.CharField(help_text="Topic名称")
    key_field = serializers.CharField(
        required=False,
        help_text="消息Key字段"
    )
    partition_field = serializers.CharField(
        required=False,
        help_text="分区字段"
    )
    # 序列化
    value_serializer = serializers.ChoiceField(
        choices=[("json", "JSON"), ("avro", "Avro")],
        default="json",
        help_text="值序列化方式"
    )
    # 认证
    security_protocol = serializers.CharField(
        default="PLAINTEXT",
        required=False,
        help_text="安全协议"
    )


class RedisConfigSerializer(serializers.Serializer):
    """Redis配置"""
    connection_name = serializers.CharField(
        default="default",
        help_text="连接名称"
    )
    key_template = serializers.CharField(help_text="Key模板")
    data_type = serializers.ChoiceField(
        choices=[
            ("string", "字符串"),
            ("hash", "哈希"),
            ("list", "列表"),
            ("set", "集合"),
            ("zset", "有序集合"),
            ("stream", "流"),
        ],
        default="hash",
        help_text="数据类型"
    )
    ttl = serializers.IntegerField(
        default=86400,
        help_text="过期时间（秒）"
    )
    # 有序集合配置
    score_field = serializers.CharField(
        required=False,
        help_text="分数字段（data_type=zset时使用）"
    )


class VictoriaMetricsConfigSerializer(serializers.Serializer):
    """VictoriaMetrics配置"""
    url = serializers.CharField(
        help_text="VictoriaMetrics写入URL（如 http://vm:8428/api/v1/write）"
    )
    # 认证配置
    username = serializers.CharField(
        required=False,
        help_text="用户名（Basic Auth）"
    )
    password = serializers.CharField(
        required=False,
        help_text="密码（Basic Auth）"
    )
    bearer_token = serializers.CharField(
        required=False,
        help_text="Bearer Token认证"
    )
    # 指标配置
    metric_name_field = serializers.CharField(
        default="event.metric_name",
        help_text="指标名称字段路径"
    )
    metric_name_prefix = serializers.CharField(
        default="",
        required=False,
        help_text="指标名称前缀"
    )
    value_field = serializers.CharField(
        default="event.current_value",
        help_text="指标值字段路径"
    )
    timestamp_field = serializers.CharField(
        default="event.time",
        help_text="时间戳字段路径"
    )
    # 标签配置
    label_fields = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="作为标签的字段列表"
    )
    extra_labels = serializers.DictField(
        default=dict,
        required=False,
        help_text="额外的静态标签"
    )
    # 批量配置
    batch_size = serializers.IntegerField(
        default=100,
        help_text="批量写入大小"
    )
    flush_interval = serializers.IntegerField(
        default=5,
        help_text="刷新间隔（秒）"
    )
    # 数据格式
    write_format = serializers.ChoiceField(
        choices=[
            ("prometheus", "Prometheus格式"),
            ("influx", "InfluxDB行协议"),
            ("json", "JSON格式"),
        ],
        default="prometheus",
        help_text="写入数据格式"
    )
    # 连接配置
    timeout = serializers.IntegerField(
        default=30,
        help_text="请求超时时间（秒）"
    )
    max_connections = serializers.IntegerField(
        default=10,
        help_text="最大连接数"
    )


class StorageNodeConfigSerializer(BaseNodeConfigSerializer):
    """存储节点配置"""
    node_type = serializers.CharField(default="storage", read_only=True)
    
    # 存储后端
    backend = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in StorageBackend],
        help_text="存储后端类型"
    )
    
    # 存储模式
    mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in StorageMode],
        default="insert",
        help_text="存储模式"
    )
    
    # 字段映射
    field_mappings = FieldMappingSerializer(
        many=True,
        required=False,
        help_text="字段映射配置"
    )
    
    # 存储全部字段
    store_all_fields = serializers.BooleanField(
        default=True,
        help_text="是否存储所有字段"
    )
    
    # 排除字段
    exclude_fields = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="排除的字段列表"
    )
    
    # 后端配置
    elasticsearch = ElasticsearchConfigSerializer(
        required=False,
        help_text="Elasticsearch配置"
    )
    mysql = MySQLConfigSerializer(
        required=False,
        help_text="MySQL配置"
    )
    kafka = KafkaConfigSerializer(
        required=False,
        help_text="Kafka配置"
    )
    redis = RedisConfigSerializer(
        required=False,
        help_text="Redis配置"
    )
    victoria_metrics = VictoriaMetricsConfigSerializer(
        required=False,
        help_text="VictoriaMetrics配置"
    )
    
    # 重试配置
    retry_enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用重试"
    )
    retry_count = serializers.IntegerField(
        default=3,
        help_text="重试次数"
    )
    retry_interval = serializers.IntegerField(
        default=5,
        help_text="重试间隔（秒）"
    )
    
    # 失败处理
    on_failure = serializers.ChoiceField(
        choices=[
            ("drop", "丢弃"),
            ("dlq", "死信队列"),
            ("log", "记录日志"),
        ],
        default="log",
        help_text="失败处理方式"
    )
    dlq_topic = serializers.CharField(
        required=False,
        help_text="死信队列Topic"
    )
    
    def validate(self, attrs):
        backend = attrs.get('backend')
        if backend == 'elasticsearch' and not attrs.get('elasticsearch'):
            raise serializers.ValidationError(
                "backend=elasticsearch时必须配置elasticsearch参数"
            )
        if backend == 'mysql' and not attrs.get('mysql'):
            raise serializers.ValidationError(
                "backend=mysql时必须配置mysql参数"
            )
        if backend == 'kafka' and not attrs.get('kafka'):
            raise serializers.ValidationError(
                "backend=kafka时必须配置kafka参数"
            )
        if backend == 'redis' and not attrs.get('redis'):
            raise serializers.ValidationError(
                "backend=redis时必须配置redis参数"
            )
        if backend == 'victoria_metrics' and not attrs.get('victoria_metrics'):
            raise serializers.ValidationError(
                "backend=victoria_metrics时必须配置victoria_metrics参数"
            )
        return attrs
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "storage" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `backend` | string | 是 | - | 存储后端类型 |
| `mode` | string | 否 | "insert" | 存储模式 |
| `field_mappings` | array | 否 | [] | 字段映射 |
| `store_all_fields` | boolean | 否 | true | 存储所有字段 |
| `exclude_fields` | array | 否 | [] | 排除字段 |
| `retry_enabled` | boolean | 否 | true | 启用重试 |
| `on_failure` | string | 否 | "log" | 失败处理 |

### Elasticsearch配置

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `hosts` | array | 是 | - | ES节点列表 |
| `index_pattern` | string | 是 | - | 索引名模式 |
| `doc_type` | string | 否 | "_doc" | 文档类型 |
| `id_field` | string | 否 | - | 文档ID字段 |
| `bulk_size` | integer | 否 | 100 | 批量大小 |
| `flush_interval` | integer | 否 | 5 | 刷新间隔 |

### MySQL配置

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `connection_name` | string | 是 | 连接名称 |
| `database` | string | 是 | 数据库名 |
| `table` | string | 是 | 表名 |
| `primary_key` | string | 否 | 主键字段 |
| `batch_size` | integer | 否 | 批量大小 |

### Kafka配置

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `bootstrap_servers` | array | 是 | 服务器列表 |
| `topic` | string | 是 | Topic名称 |
| `key_field` | string | 否 | 消息Key字段 |
| `value_serializer` | string | 否 | 序列化方式 |

### Redis配置

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `connection_name` | string | 否 | "default" | 连接名称 |
| `key_template` | string | 是 | - | Key模板 |
| `data_type` | string | 否 | "hash" | 数据类型 |
| `ttl` | integer | 否 | 86400 | 过期时间 |

### VictoriaMetrics配置

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `url` | string | 是 | - | 写入URL |
| `username` | string | 否 | - | Basic Auth用户名 |
| `password` | string | 否 | - | Basic Auth密码 |
| `bearer_token` | string | 否 | - | Bearer Token |
| `metric_name_field` | string | 否 | "event.metric_name" | 指标名称字段 |
| `metric_name_prefix` | string | 否 | "" | 指标名称前缀 |
| `value_field` | string | 否 | "event.current_value" | 指标值字段 |
| `timestamp_field` | string | 否 | "event.time" | 时间戳字段 |
| `label_fields` | array | 否 | [] | 标签字段列表 |
| `extra_labels` | object | 否 | {} | 额外静态标签 |
| `batch_size` | integer | 否 | 100 | 批量写入大小 |
| `flush_interval` | integer | 否 | 5 | 刷新间隔（秒） |
| `write_format` | string | 否 | "prometheus" | 写入格式 |
| `timeout` | integer | 否 | 30 | 请求超时（秒） |
| `max_connections` | integer | 否 | 10 | 最大连接数 |

### 存储后端说明

| 后端 | 说明 | 适用场景 |
|------|------|----------|
| `elasticsearch` | 全文搜索引擎 | 告警日志、检索分析 |
| `mysql` | 关系数据库 | 结构化数据存储 |
| `redis` | 内存数据库 | 缓存、实时状态 |
| `kafka` | 消息队列 | 事件流转、解耦 |
| `mongodb` | 文档数据库 | 灵活结构存储 |
| `influxdb` | 时序数据库 | 指标时序存储 |
| `clickhouse` | 列式数据库 | 大数据分析 |
| `victoria_metrics` | 高性能时序库 | 大规模指标存储、Prometheus兼容 |

## JSON 配置示例

### 示例 1: Elasticsearch存储

```json
{
  "name": "alert_es_storage",
  "description": "告警事件存储到Elasticsearch",
  "enabled": true,
  "node_type": "storage",
  "backend": "elasticsearch",
  "mode": "insert",
  "elasticsearch": {
    "hosts": ["http://es-node1:9200", "http://es-node2:9200"],
    "index_pattern": "bk_monitor_alert_{{ event.biz_id }}_{{ now | date('YYYY.MM.DD') }}",
    "doc_type": "_doc",
    "id_field": "event.alert_id",
    "username": "${ES_USERNAME}",
    "password": "${ES_PASSWORD}",
    "bulk_size": 200,
    "flush_interval": 3
  },
  "field_mappings": [
    {
      "source_field": "event.alert_id",
      "target_field": "alert_id",
      "field_type": "string"
    },
    {
      "source_field": "event.time",
      "target_field": "@timestamp",
      "field_type": "datetime"
    },
    {
      "source_field": "event.severity",
      "target_field": "severity",
      "field_type": "integer"
    }
  ],
  "store_all_fields": true,
  "exclude_fields": ["_internal", "_temp"],
  "retry_enabled": true,
  "retry_count": 3,
  "on_failure": "dlq",
  "dlq_topic": "alert_storage_dlq",
  "execution": {
    "timeout": 60
  }
}
```

### 示例 2: Kafka消息队列存储

```json
{
  "name": "alert_kafka_storage",
  "description": "告警事件发送到Kafka供下游消费",
  "enabled": true,
  "node_type": "storage",
  "backend": "kafka",
  "mode": "append",
  "kafka": {
    "bootstrap_servers": ["kafka1:9092", "kafka2:9092", "kafka3:9092"],
    "topic": "bk_monitor_alerts",
    "key_field": "event.alert_id",
    "partition_field": "event.biz_id",
    "value_serializer": "json",
    "security_protocol": "SASL_PLAINTEXT"
  },
  "store_all_fields": true,
  "exclude_fields": ["_route_path", "_internal"],
  "retry_enabled": true,
  "retry_count": 5,
  "retry_interval": 2,
  "on_failure": "log",
  "execution": {
    "timeout": 30
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: VictoriaMetrics时序存储

```json
{
  "name": "alert_vm_metrics",
  "description": "告警指标存储到VictoriaMetrics",
  "enabled": true,
  "node_type": "storage",
  "backend": "victoria_metrics",
  "mode": "insert",
  "victoria_metrics": {
    "url": "http://victoria-metrics:8428/api/v1/write",
    "username": "${VM_USERNAME}",
    "password": "${VM_PASSWORD}",
    "metric_name_field": "event.metric_name",
    "metric_name_prefix": "bkmonitor_alert_",
    "value_field": "event.current_value",
    "timestamp_field": "event.time",
    "label_fields": [
      "event.biz_id",
      "event.strategy_id",
      "event.dimensions.host",
      "event.dimensions.service",
      "event.severity"
    ],
    "extra_labels": {
      "source": "bkmonitor",
      "env": "production"
    },
    "batch_size": 500,
    "flush_interval": 3,
    "write_format": "prometheus",
    "timeout": 30,
    "max_connections": 20
  },
  "retry_enabled": true,
  "retry_count": 3,
  "retry_interval": 2,
  "on_failure": "dlq",
  "dlq_topic": "vm_storage_dlq",
  "execution": {
    "timeout": 60
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 4: Redis缓存存储

```json
{
  "name": "alert_redis_cache",
  "description": "告警状态缓存到Redis",
  "enabled": true,
  "node_type": "storage",
  "backend": "redis",
  "mode": "upsert",
  "redis": {
    "connection_name": "default",
    "key_template": "alert:{{ event.biz_id }}:{{ event.strategy_id }}:{{ event.dimensions_md5 }}",
    "data_type": "hash",
    "ttl": 86400
  },
  "field_mappings": [
    {
      "source_field": "event.alert_id",
      "target_field": "alert_id"
    },
    {
      "source_field": "event.status",
      "target_field": "status"
    },
    {
      "source_field": "event.severity",
      "target_field": "severity",
      "field_type": "integer"
    },
    {
      "source_field": "event.current_value",
      "target_field": "current_value",
      "field_type": "float"
    },
    {
      "source_field": "event.time",
      "target_field": "last_update_time"
    },
    {
      "source_field": "event.target",
      "target_field": "target"
    }
  ],
  "store_all_fields": false,
  "retry_enabled": true,
  "retry_count": 2,
  "retry_interval": 1,
  "on_failure": "log",
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
    "timeout": 10
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **告警归档**：将告警事件存储到ES供查询分析
2. **状态缓存**：缓存告警状态到Redis供快速查询
3. **事件流转**：通过Kafka将事件发送到下游系统
4. **数据同步**：同步告警数据到数据仓库
5. **审计记录**：存储完整的告警处理记录
6. **指标存储**：将指标数据存储到时序数据库（InfluxDB/VictoriaMetrics）
7. **报表数据**：存储聚合数据供报表使用
8. **Prometheus兼容**：通过VictoriaMetrics实现与Prometheus生态集成

## 注意事项

1. **索引模式**：
   - ES索引支持日期格式，如 `_YYYY.MM.DD`
   - 合理分片避免单索引过大
   - 建议使用别名管理索引

2. **批量写入**：
   - 调整 `bulk_size` 平衡延迟和吞吐
   - `flush_interval` 控制最大延迟
   - 大批量可能导致内存压力

3. **字段映射**：
   - `field_mappings` 可自定义映射
   - `store_all_fields=true` 存储所有字段
   - `exclude_fields` 排除不需要的字段

4. **失败处理**：
   - `dlq` 死信队列保证数据不丢失
   - `log` 仅记录便于排查
   - `drop` 直接丢弃适合非关键数据

5. **Redis存储**：
   - 合理设置 `ttl` 避免内存溢出
   - `hash` 类型适合多字段存储
   - `zset` 适合需要排序的场景

6. **Kafka配置**：
   - 选择合适的分区策略
   - 注意序列化一致性
   - 配置适当的重试机制

7. **VictoriaMetrics配置**：
   - 支持Prometheus格式、InfluxDB行协议、JSON格式
   - 合理配置 `label_fields` 作为指标维度
   - `metric_name_prefix` 统一指标命名空间
   - 注意标签基数避免高基数问题
   - 支持集群模式（vminsert地址）

8. **性能优化**：
   - 批量写入提高吞吐
   - 异步写入减少延迟
   - 合理设置超时时间

## 相关节点

- **上游节点**：
  - Transform（转换节点）：转换后存储
  - Aggregate（聚合节点）：聚合结果存储
  - Filter（过滤节点）：过滤后存储

- **下游节点**：
  - Log（日志节点）：记录存储日志
  - Callback（回调节点）：存储后回调

### 典型组合模式

1. **Transform → Storage[ES]**
   - 转换 → ES存储

2. **Aggregate → Storage[MySQL]**
   - 聚合 → MySQL存储

3. **Router → [Storage_A | Storage_B]**
   - 路由 → 不同存储

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
