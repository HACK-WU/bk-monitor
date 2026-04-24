# Issue Top-N 接口文档

> **版本**: v1.4
> **更新时间**: 2026-04-24
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
| `bk_biz_ids` | `int[]` | 是 | - | 业务 ID 列表，用于权限过滤 |
| `fields` | `string[]` | 是 | - | 需要统计的字段列表（详见下方 fields 说明） |
| `size` | `int` | 否 | `10` | 每个字段返回的 Top N 数量（最大 10000） |
| `start_time` | `int` | 否 | - | 开始时间戳（秒级） |
| `end_time` | `int` | 否 | - | 结束时间戳（秒级） |
| `need_time_partition` | `bool` | 否 | `true` | 是否需要时间分片（>7 天自动分片） |
| `status` | `string[]` | 否 | - | 状态过滤 |
| `priority` | `string[]` | 否 | - | 优先级过滤 |
| `assignee` | `string[]` | 否 | - | 负责人过滤 |
| `conditions` | `object[]` | 否 | `[]` | 高级过滤条件 |
| `query_string` | `string` | 否 | `""` | 查询字符串 |

---

## fields 字段说明

### 枚举值说明

#### status

| 值 | 说明 |
|------|------|
| `pending_review` | 待审核 |
| `unresolved` | 未解决 |
| `resolved` | 已解决 |
| `archived` | 归档 |

#### priority

| 值 | 说明 |
|------|------|
| `P0` | 高优先级 |
| `P1` | 中优先级 |
| `P2` | 低优先级 |

### 可用字段

| 字段 | 说明 | name 翻译 |
|------|------|-----------|
| `status` | 状态 | 自动翻译为中文（未解决、待审核等） |
| `priority` | 优先级 | 自动翻译为中文（高、中、低） |
| `assignee` | 负责人（空字符串表示未指派） | 不翻译，直接展示 |
| `strategy_id` | 策略 ID | 翻译为策略名称 |
| `strategy_name` | 策略名称 | 不翻译，直接展示 |
| `bk_biz_id` | 业务 ID | 翻译为业务名称 |
| `labels` | 标签（多值字段） | 不翻译，直接展示 |
| `is_regression` | 是否回归 | 不翻译，直接展示 |
| `tags.*` | 自定义标签（如 `tags.service`） | 不翻译，直接展示 |
| `id` | Issue ID（返回最新 N 个，见特殊说明） | name = id |
| `impact_dimensions` | 影响范围维度统计（见特殊说明） | 自动翻译为中文名 |
| `impact_scope.{维度}.{ID字段}` | 影响范围实例统计（见特殊说明） | 自动翻译为展示名 |

### 特殊字段说明

#### 1. `id` 字段

按 `create_time` 降序返回最新的 N 个 Issue，而非聚合统计。每个 Issue 的 `count` 固定为 1，`name` 与 `id` 保持一致。

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
    "bucket_count": 10,
    "buckets": [
        {"id": "1744291200a1b2c3d4", "name": "1744291200a1b2c3d4", "count": 1},
        {"id": "1744291100b2c3d4e5", "name": "1744291100b2c3d4e5", "count": 1}
    ]
}
```

#### 2. `impact_dimensions` 字段

统计 Issue 包含的影响范围维度分布。维度固定为 9 个，`size` 参数无效，始终返回全部维度。

| 维度值 | 中文名 |
|--------|--------|
| `set` | 集群 |
| `host` | 主机 |
| `service_instances` | 服务实例 |
| `cluster` | bcs集群 |
| `node` | node |
| `service` | service |
| `pod` | pod |
| `apm_app` | apm_app |
| `apm_service` | apm_service |

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
    "bucket_count": 9,
    "buckets": [
        {"id": "host", "name": "主机", "count": 150},
        {"id": "cluster", "name": "bcs集群", "count": 80},
        {"id": "set", "name": "集群", "count": 60}
    ]
}
```

#### 3. `impact_scope.{维度}.{ID字段}` 字段

统计各维度下具体实例的 Issue 分布，`name` 会自动翻译为展示名（翻译失败时返回原始 ID 值）。

**字段格式**：`impact_scope.{dimension}.{id_field}`

**维度与 ID 字段映射表**：

| 维度 | ID 字段 | 示例字段 | name 翻译示例 |
|------|---------|----------|--------------|
| `set` | `set_id` | `impact_scope.set.set_id` | `5017605` → `蓝鲸PaaS平台/BCS-K8S-40340` |
| `host` | `bk_host_id` | `impact_scope.host.bk_host_id` | `1001` → `192.168.1.101` |
| `service_instances` | `bk_service_instance_id` | `impact_scope.service_instances.bk_service_instance_id` | `2001` → `服务实例名` |
| `cluster` | `bcs_cluster_id` | `impact_scope.cluster.bcs_cluster_id` | `BCS-K8S-26322` → `TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)` |
| `node` | `node` | `impact_scope.node.node` | `10.0.0.1` → `node-10.0.0.1` |
| `service` | `service` | `impact_scope.service.service` | `svc-name` → `svc-name` |
| `pod` | `pod` | `impact_scope.pod.pod` | `pod-xxx` → `pod-xxx` |
| `apm_app` | `app_name` | `impact_scope.apm_app.app_name` | `my-app` → `我的应用` |
| `apm_service` | `service_name` | `impact_scope.apm_service.service_name` | `my-service` → `我的服务` |

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
        {"id": "1001", "name": "192.168.1.101", "count": 25},
        {"id": "1002", "name": "192.168.1.102", "count": 18}
    ]
}
```

---

## 响应结构

### 响应体

```json
{
    "doc_count": 150,
    "fields": [
        {
            "field": "status",
            "is_char": false,
            "bucket_count": 4,
            "buckets": [
                {
                    "id": "unresolved",
                    "name": "未解决",
                    "count": 80
                }
            ]
        }
    ]
}
```

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_count` | `int` | 符合条件的 Issue 总数 |
| `fields` | `object[]` | 各字段的统计结果数组 |

### fields 数组单项

| 字段 | 类型 | 说明 |
|------|------|------|
| `field` | `string` | 字段名 |
| `is_char` | `bool` | 是否为字符字段 |
| `bucket_count` | `int` | 桶数量（实际返回的 bucket 数量） |
| `buckets` | `object[]` | 桶数组，按 count 降序排列 |

### buckets 数组单项

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | 桶 ID（字段原始值） |
| `name` | `string` | 桶名称（翻译后的展示名，未翻译时与 id 相同） |
| `count` | `int` | 该桶的文档数量 |

---

## 完整响应示例

```json
{
    "doc_count": 12,
    "fields": [
        {
            "field": "status",
            "is_char": false,
            "bucket_count": 4,
            "buckets": [
                {"id": "pending_review", "name": "待审核", "count": 4},
                {"id": "unresolved", "name": "未解决", "count": 4},
                {"id": "resolved", "name": "已解决", "count": 3},
                {"id": "archived", "name": "归档", "count": 1}
            ]
        },
        {
            "field": "priority",
            "is_char": false,
            "bucket_count": 3,
            "buckets": [
                {"id": "P0", "name": "高", "count": 10},
                {"id": "P1", "name": "中", "count": 8},
                {"id": "P2", "name": "低", "count": 6}
            ]
        },
        {
            "field": "strategy_name",
            "is_char": true,
            "bucket_count": 12,
            "buckets": [
                {"id": "\"APM 服务响应超时\"", "name": "APM 服务响应超时", "count": 1},
                {"id": "\"Elasticsearch 集群 Yellow 状态\"", "name": "Elasticsearch 集群 Yellow 状态", "count": 1},
                {"id": "\"K8S Pod 频繁重启\"", "name": "K8S Pod 频繁重启", "count": 1}
            ]
        },
        {
            "field": "impact_dimensions",
            "is_char": false,
            "bucket_count": 6,
            "buckets": [
                {"id": "host", "name": "主机", "count": 5},
                {"id": "set", "name": "集群", "count": 3},
                {"id": "service_instances", "name": "服务实例", "count": 3},
                {"id": "cluster", "name": "bcs集群", "count": 2},
                {"id": "pod", "name": "pod", "count": 2},
                {"id": "apm_service", "name": "apm_service", "count": 1}
            ]
        },
        {
            "field": "impact_scope.set.set_id",
            "is_char": true,
            "bucket_count": 2,
            "buckets": [
                {"id": "\"5017605\"", "name": "蓝鲸PaaS平台/BCS-K8S-40340", "count": 3},
                {"id": "\"5070644\"", "name": "kihan-test/bcs-tke-test-BCS-K8S-41797", "count": 3}
            ]
        },
        {
            "field": "impact_scope.host.bk_host_id",
            "is_char": true,
            "bucket_count": 3,
            "buckets": [
                {"id": "\"10692392\"", "name": "21.186.179.6", "count": 5},
                {"id": "\"9185731\"", "name": "21.249.64.16", "count": 5},
                {"id": "\"1804751\"", "name": "11.181.33.209", "count": 3}
            ]
        },
        {
            "field": "impact_scope.cluster.bcs_cluster_id",
            "is_char": true,
            "bucket_count": 2,
            "buckets": [
                {"id": "\"BCS-K8S-26322\"", "name": "TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)", "count": 2},
                {"id": "\"BCS-K8S-41193\"", "name": "南京三集群-业务安全-V1.26.1(BCS-K8S-41193)", "count": 2}
            ]
        }
    ]
}
```

---

## 特殊说明

### 空值处理

- `assignee` 为空字符串时，展示为"未指派"
- 某字段无数据时，`buckets` 为空数组
- 无符合条件的 Issue 时，`doc_count` 为 0

### 时间分片

当 `need_time_partition: true` 且时间范围 > 7 天时，后端自动按天切分查询并合并结果，返回格式与单次查询一致。

---

## 性能建议

| 场景 | 建议 |
|------|------|
| 单次查询字段数 | ≤ 5 个 |
| size 最大值 | 10000 |
| 时间范围 > 7 天 | 启用 `need_time_partition` |
| 高频调用 | 考虑前端缓存（TTL: 30s） |

---

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-04-16 | 初始版本 |
| v1.1 | 2026-04-16 | 补充特殊字段设计：`id`、`impact_dimensions`、`impact_scope.{维度}.{ID字段}` |
| v1.3 | 2026-04-16 | 移除 top_n_result 接口；id 字段 name 与 id 保持一致；impact_scope 维度和 ID 字段由前端指定 |
| v1.4 | 2026-04-24 | status 枚举 rejected 改为 archived；补充 impact_dimensions/impact_scope 翻译说明；精简文档，重点介绍 fields 参数 |

---

**文档结束**
