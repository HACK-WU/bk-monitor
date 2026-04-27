# Issue Top-N 接口文档

> **版本**: v2.0
> **更新时间**: 2026-04-27
> **状态**: 已实现

---

## 接口信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Issue Top-N 统计 |
| **请求方式** | POST |
| **接口地址** | `/fta/issue/issue/top_n` |
| **内容类型** | application/json |

---

## 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `fields` | `string[]` | 否 | `[]` | **需统计的字段列表**（本文重点，详见下方） |
| `size` | `int` | 否 | `10` | 每个字段返回的 Top N 桶数量，最大 10000 |
| `bk_biz_ids` | `int[]` | 否 | `null` | 业务 ID 列表，为空时查询与当前用户相关的 Issue |
| `space_uids` | `string[]` | 否 | `null` | 空间 UID 列表，会自动转换为 bk_biz_ids 并合并 |
| `start_time` | `int` | 否 | - | 开始时间戳（秒级） |
| `end_time` | `int` | 否 | - | 结束时间戳（秒级） |
| `need_time_partition` | `bool` | 否 | `true` | 是否启用时间分片（>7 天自动分片，≤7 天忽略此参数） |
| `status` | `string[]` | 否 | - | 状态过滤，含虚拟状态 `MY_ISSUE`/`NO_ASSIGNEE` |
| `conditions` | `object[]` | 否 | `[]` | 高级过滤条件 |
| `query_string` | `string` | 否 | `""` | ES 查询字符串 |

> **说明**：除 `fields` 外，其余参数（`bk_biz_ids`、`start_time`、`end_time`、`status`、`conditions`、`query_string` 等）的使用方式与 **SearchIssue 接口** 完全一致，此处不再赘述。

---

## fields 参数详解

`fields` 指定需要做 TopN 聚合的字段列表。支持 `+`/`-` 前缀控制桶排序方向（默认按 `count` 降序），如 `+status` 表示升序。

### 可用字段

| 字段 | `is_char` | 说明 |
|------|:---------:|------|
| `id` | `true` | Issue ID |
| `name` | `true` | Issue 名称 |
| `status` | `false` | 状态 |
| `priority` | `false` | 优先级 |
| `assignee` | `false` | 负责人（空字符串表示未指派） |
| `strategy_id` | `false` | 策略 ID |
| `strategy_name` | `true` | 策略名称 |
| `bk_biz_id` | `false` | 业务 ID |
| `labels` | `true` | 标签（数组，ES 自动展开） |
| `is_regression` | `false` | 是否回归 |
| `impact_dimensions` | `false` | 影响范围维度统计（特殊字段，详见下方） |
| `impact_scope.{维度}.{ID字段}` | `true` | 影响范围实例统计（特殊字段，详见下方） |

> **`is_char` 字段说明**：`is_char: true` 的字段，返回的桶 `id` 值会自动包裹双引号（如 `"\"APM 服务响应超时\""`），`name` 不加引号。前端解析 `id` 时需注意去引号。

---

### 特殊字段：`id`

`id` 字段走标准 terms 聚合，与其他字段行为一致。由于 Issue ID 天然唯一，每个桶的 `count` 自然为 1，`name` 与 `id` 保持一致。

**请求示例**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["id"],
    "size": 10
}
```

**响应示例**：
```json
{
    "field": "id",
    "is_char": true,
    "bucket_count": 12,
    "buckets": [
        {"id": "\"1776413724030828eb_issuetest\"", "name": "1776413724030828eb_issuetest", "count": 1},
        {"id": "\"1776413724030828eb_another\"", "name": "1776413724030828eb_another", "count": 1}
    ]
}
```

---

### 特殊字段：`impact_dimensions`

统计 Issue 包含的影响范围维度分布。使用 filters 聚合，仅返回 `count > 0` 的维度，`size` 参数有效（按 count 降序截断）。

**返回的 `id` 格式**：完整维度路径，如 `impact_scope.host.bk_host_id`（由 `ImpactScopeDimension.get_full_dimension()` 生成），而非短维度名。

**可用维度**：

| 短维度名 | 完整维度路径（id 返回值） | 中文名 |
|----------|--------------------------|--------|
| `set` | `impact_scope.set.set_id` | 集群 |
| `host` | `impact_scope.host.bk_host_id` | 主机 |
| `service_instances` | `impact_scope.service_instances.bk_service_instance_id` | 服务实例 |
| `cluster` | `impact_scope.cluster.bcs_cluster_id` | bcs集群 |
| `node` | `impact_scope.node.node` | node |
| `service` | `impact_scope.service.service` | service |
| `pod` | `impact_scope.pod.pod` | pod |
| `apm_app` | `impact_scope.apm_app.app_name` | apm_app |
| `apm_service` | `impact_scope.apm_service.service_name` | apm_service |

**请求示例**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["impact_dimensions"],
    "size": 10
}
```

**响应示例**：
```json
{
    "field": "impact_dimensions",
    "is_char": false,
    "bucket_count": 6,
    "buckets": [
        {"id": "impact_scope.host.bk_host_id", "name": "主机", "count": 150},
        {"id": "impact_scope.cluster.bcs_cluster_id", "name": "bcs集群", "count": 80},
        {"id": "impact_scope.set.set_id", "name": "集群", "count": 60}
    ]
}
```

> **注意**：`bucket_count` 仅统计 `count > 0` 的维度数量，不含 count 为 0 的维度。

---

### 特殊字段：`impact_scope.{维度}.{ID字段}`

统计各维度下具体实例的 Issue 分布。后端通过 top_hits 子聚合提取 `display_name` 用于翻译展示名。

**字段格式**：`impact_scope.{dimension}.{id_field}`

**维度与 ID 字段映射**：

| 维度 | ID 字段 | 完整字段写法 | 翻译来源 |
|------|---------|-------------|---------|
| `set` | `set_id` | `impact_scope.set.set_id` | CMDB 批量查询 |
| `host` | `bk_host_id` | `impact_scope.host.bk_host_id` | CMDB 批量查询 |
| `service_instances` | `bk_service_instance_id` | `impact_scope.service_instances.bk_service_instance_id` | CMDB 批量查询 |
| `cluster` | `bcs_cluster_id` | `impact_scope.cluster.bcs_cluster_id` | 容器平台 API |
| `node` | `node` | `impact_scope.node.node` | 容器平台 API |
| `service` | `service` | `impact_scope.service.service` | 容器平台 API |
| `pod` | `pod` | `impact_scope.pod.pod` | 容器平台 API |
| `apm_app` | `app_name` | `impact_scope.apm_app.app_name` | APM 服务 |
| `apm_service` | `service_name` | `impact_scope.apm_service.service_name` | APM 服务 |

**请求示例**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["impact_scope.host.bk_host_id", "impact_scope.cluster.bcs_cluster_id"],
    "size": 10
}
```

**响应示例**：
```json
{
    "field": "impact_scope.host.bk_host_id",
    "is_char": true,
    "bucket_count": 10,
    "buckets": [
        {"id": "\"1001\"", "name": "192.168.1.101", "count": 25},
        {"id": "\"1002\"", "name": "192.168.1.102", "count": 18}
    ]
}
```

> **翻译降级**：当翻译 API 调用失败时，`name` 降级返回原始 ID 值。

---

## 响应结构

### 响应体

```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 150,
        "fields": [
            {
                "field": "status",
                "is_char": false,
                "bucket_count": 4,
                "buckets": [
                    {"id": "unresolved", "name": "未解决", "count": 80}
                ]
            }
        ]
    }
}
```

### data 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_count` | `int` | 符合条件的 Issue 总数 |
| `fields` | `object[]` | 各字段的统计结果数组 |

### fields 数组单项

| 字段 | 类型 | 说明 |
|------|------|------|
| `field` | `string` | 字段名（与请求中的 fields 元素一致） |
| `is_char` | `bool` | 是否为字符字段（字符字段的桶 `id` 会自动加双引号） |
| `bucket_count` | `int` | 桶基数（字段的**不同值总数**，可能大于实际返回的桶数量，受 `size` 限制） |
| `buckets` | `object[]` | 桶数组，按 count 降序排列，最多返回 `size` 个 |

### buckets 数组单项

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 桶 ID。字符字段（`is_char: true`）自动加双引号 |
| `name` | `string` | 桶展示名（翻译后的值，未配置翻译时与 id 原始值一致） |
| `count` | `int` | 该桶的文档数量 |

---

## 完整请求与响应示例

### 示例 1：统计状态和优先级分布

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["status", "priority"],
    "size": 10,
    "start_time": 1741334400,
    "end_time": 1741420800
}
```

**响应**：
```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 150,
        "fields": [
            {
                "field": "status",
                "is_char": false,
                "bucket_count": 4,
                "buckets": [
                    {"id": "unresolved", "name": "未解决", "count": 80},
                    {"id": "pending_review", "name": "待审核", "count": 40},
                    {"id": "resolved", "name": "已解决", "count": 25},
                    {"id": "archived", "name": "归档", "count": 5}
                ]
            },
            {
                "field": "priority",
                "is_char": false,
                "bucket_count": 3,
                "buckets": [
                    {"id": "P2", "name": "低", "count": 70},
                    {"id": "P1", "name": "中", "count": 60},
                    {"id": "P0", "name": "高", "count": 20}
                ]
            }
        ]
    }
}
```

### 示例 2：统计优先级和负责人分布

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["priority", "assignee"],
    "size": 20
}
```

**响应**：
```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 150,
        "fields": [
            {
                "field": "priority",
                "is_char": false,
                "bucket_count": 3,
                "buckets": [
                    {"id": "P2", "name": "低", "count": 70},
                    {"id": "P1", "name": "中", "count": 60},
                    {"id": "P0", "name": "高", "count": 20}
                ]
            },
            {
                "field": "assignee",
                "is_char": false,
                "bucket_count": 4,
                "buckets": [
                    {"id": "zhangsan", "name": "zhangsan", "count": 50},
                    {"id": "lisi", "name": "lisi", "count": 40},
                    {"id": "", "name": "未指派", "count": 35},
                    {"id": "wangwu", "name": "wangwu", "count": 25}
                ]
            }
        ]
    }
}
```

### 示例 3：统计标签分布（多值字段）

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["labels"],
    "size": 50,
    "start_time": 1740729600,
    "end_time": 1741420800
}
```

**响应**：
```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 100,
        "fields": [
            {
                "field": "labels",
                "is_char": true,
                "bucket_count": 5,
                "buckets": [
                    {"id": "\"网络\"", "name": "网络", "count": 50},
                    {"id": "\"存储\"", "name": "存储", "count": 30},
                    {"id": "\"计算\"", "name": "计算", "count": 20},
                    {"id": "\"数据库\"", "name": "数据库", "count": 15},
                    {"id": "\"中间件\"", "name": "中间件", "count": 10}
                ]
            }
        ]
    }
}
```

### 示例 4：带 conditions 过滤的策略分布

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["strategy_name"],
    "size": 20,
    "status": ["unresolved"],
    "conditions": [
        {
            "key": "priority",
            "value": ["P0", "P1"],
            "method": "include"
        }
    ]
}
```

### 示例 5：长时间范围（自动分片）

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["status", "priority"],
    "size": 10,
    "start_time": 1738339200,
    "end_time": 1741420800,
    "need_time_partition": true
}
```

### 示例 6：统计影响范围维度分布

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["impact_dimensions"],
    "size": 10
}
```

**响应**：
```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 150,
        "fields": [
            {
                "field": "impact_dimensions",
                "is_char": false,
                "bucket_count": 6,
                "buckets": [
                    {"id": "impact_scope.host.bk_host_id", "name": "主机", "count": 150},
                    {"id": "impact_scope.cluster.bcs_cluster_id", "name": "bcs集群", "count": 80},
                    {"id": "impact_scope.set.set_id", "name": "集群", "count": 60}
                ]
            }
        ]
    }
}
```

### 示例 7：统计主机维度的 Top-N 实例

**请求**：
```json
{
    "bk_biz_ids": [2],
    "fields": ["impact_scope.host.bk_host_id"],
    "size": 20
}
```

**响应**：
```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "doc_count": 150,
        "fields": [
            {
                "field": "impact_scope.host.bk_host_id",
                "is_char": true,
                "bucket_count": 45,
                "buckets": [
                    {"id": "\"1001\"", "name": "192.168.1.101", "count": 25},
                    {"id": "\"1002\"", "name": "192.168.1.102", "count": 18},
                    {"id": "\"1003\"", "name": "192.168.1.103", "count": 12}
                ]
            }
        ]
    }
}
```

---
**文档结束**
