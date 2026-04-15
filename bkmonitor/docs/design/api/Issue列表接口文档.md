# Issue 列表查询接口文档

> **版本**: v1.1  
> **更新时间**: 2026-04-15

---

## 接口信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Issue 列表查询 |
| **请求方式** | POST |
| **接口地址** | `/fta/issue/issue/search` |
| **内容类型** | application/json |

---

## 请求参数

### 参数列表

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `bk_biz_ids` | `int[]` | 否 | `null` | 业务 ID 列表，为空时查询当前用户有权限的所有业务 |
| `status` | `string[]` | 否 | — | 状态过滤，**仅支持虚拟状态**（`MY_ISSUE` / `NO_ASSIGNEE`），可多选 OR 组合。实际状态过滤请使用 `conditions` 参数 |
| `conditions` | `object[]` | 否 | `[]` | 结构化过滤条件（见下方格式说明） |
| `query_string` | `string` | 否 | `""` | 搜索关键词，支持 ES query_string 语法 |
| `start_time` | `int` | 否 | — | 时间范围起点（秒级时间戳）。不传则不做时间下界过滤 |
| `end_time` | `int` | 否 | — | 时间范围终点（秒级时间戳）。不传则不做时间上界过滤 |
| `ordering` | `string[]` | 否 | `[]` | 排序字段列表，前缀 `-` 表示倒序。默认 `["status", "-update_time"]` |
| `page` | `int` | 否 | `1` | 页码，最小值 1 |
| `page_size` | `int` | 否 | `10` | 每页大小，最大 500 |
| `show_aggs` | `bool` | 否 | `true` | 是否返回高级筛选聚合信息 |
| `show_dsl` | `bool` | 否 | `false` | 是否返回 ES DSL 查询语句（用于调试） |
| `trend_start_time` | `int` | 否 | — | 趋势图时间范围起点（秒级时间戳）。用于自定义趋势图展示的时间范围，**不传则默认使用本页 Issue 的实际告警时间边界** |
| `trend_end_time` | `int` | 否 | — | 趋势图时间范围终点（秒级时间戳）。用于自定义趋势图展示的时间范围，**不传则默认使用本页 Issue 的实际告警时间边界** |

> **时间字段说明**：`start_time` / `end_time` 均为 **可选** 参数。Issue 是长期存在的实体，常见场景是查看"所有活跃 Issue"而不限定时间范围。

#### 时间过滤逻辑

| 参数 | 过滤字段 | 说明 |
|------|----------|------|
| `end_time` | `create_time <= end_time` | Issue 创建时间不晚于 `end_time` |
| `start_time` | `resolved_time >= start_time OR resolved_time IS NULL` | Issue 解决时间不早于 `start_time`，或尚未解决 |

> **时间过滤语义**：
> - 传入 `start_time=1741334400, end_time=1741420800`，表示查询"在这个时间范围内活跃的 Issue"
> - 包括：该时间范围内创建的 Issue + 该时间范围内解决的 Issue + 该时间范围内未解决的 Issue
> - 未解决的 Issue（`resolved_time` 为 null）不受 `start_time` 约束，始终可见

##### trend 时间范围说明

- **推荐设置**：`trend_end_time` 应与 `end_time` **保持一致**
- **点数计算规则**：趋势图点数为 `(trend_end_time - trend_start_time) / 3600 + 1`
  - 例如：时间范围为 23 小时，则生成 24 个点
  - 例如：时间范围为 24 小时，则生成 25 个点

---

### status 枚举值（仅支持虚拟状态）

> **重要**：`status` 参数**仅支持虚拟状态**，用于快速筛选场景。实际状态（`pending_review` / `unresolved` / `resolved` / `archived`）请通过 `conditions` 参数过滤。

| 值 | 类型 | 说明 |
|----|------|------|
| `MY_ISSUE` | 虚拟状态 | 我负责的（当前用户为 assignee 的 Issue） |
| `NO_ASSIGNEE` | 虚拟状态 | 未分派的（assignee 为空的 Issue） |

#### 虚拟状态说明

| 虚拟状态 | 等价条件 | 使用场景 |
|----------|----------|----------|
| `MY_ISSUE` | `assignee = 当前用户` | 快速查看"我负责的 Issue" |
| `NO_ASSIGNEE` | `assignee 为空` | 快速查看"未分派的 Issue" |

> **前端使用提示**：
> - `status` 参数仅支持虚拟状态 `MY_ISSUE` 和 `NO_ASSIGNEE`，用于快速筛选场景
> - **实际状态过滤请使用 `conditions` 参数**：`{"key": "status", "value": ["unresolved", "pending_review", "resolved", "archived"], "method": "eq"}`
> - 虚拟状态可组合使用：`status: ["MY_ISSUE", "NO_ASSIGNEE"]` 表示"我负责的或未分派的 Issue"
> - `status` 参数为空数组或不传时，不进行状态过滤，返回所有状态的 Issue

---

### conditions 条件格式

```json
{
  "key": "priority",
  "value": ["P0", "P1"],
  "method": "eq",
  "condition": ""
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | `string` | 匹配字段名（见下方可用字段） |
| `value` | `any[]` | 匹配值列表 |
| `method` | `string` | 匹配方法（见下方 method 枚举） |
| `condition` | `string` | 多条件关系：`and` / `or` / `""`（默认） |

#### 可用的 conditions key

| key | 说明 | 类型 |
|-----|------|------|
| `id` | Issue ID | string |
| `name` | Issue 名称 | string（模糊匹配） |
| `status` | 状态 | string |
| `priority` | 优先级（P0/P1/P2） | string |
| `assignee` | 负责人 | string |
| `strategy_id` | 策略 ID | string |
| `strategy_name` | 策略名称 | string（模糊匹配） |
| `bk_biz_id` | 业务 ID | string |
| `labels` | 标签 | string |
| `is_regression` | 是否回归 | bool |
| `alert_count` | 告警数量 | int |
| `first_alert_time` | 首次告警时间 | int（秒级时间戳） |
| `last_alert_time` | 最近告警时间 | int（秒级时间戳） |
| `create_time` | 创建时间 | int（秒级时间戳） |
| `update_time` | 更新时间 | int（秒级时间戳） |
| `resolved_time` | 解决时间 | int（秒级时间戳） |
| `impact_dimensions` | 影响范围维度过滤 | array | 只包含指定维度类型的 Issue，如 `["host", "cluster"]`，多值 OR 关系 |
| `impact_scope.{维度}.{ID字段}` | 影响范围实例过滤 | array | 按具体实例 ID 精确过滤，如 `impact_scope.host.bk_host_id`，value 传字符串数组 |

#### method 枚举

| 值 | 说明 |
|----|------|
| `eq` | 精确匹配 |
| `neq` | 不等于 |
| `include` | 模糊包含 |
| `exclude` | 模糊排除 |
| `gt` | 大于 |
| `gte` | 大于等于 |
| `lt` | 小于 |
| `lte` | 小于等于 |

---

### 影响范围过滤（impact_scope）

影响范围过滤可通过 `conditions` 参数实现，支持**维度级**和**实例级**两种过滤方式。

#### 1. 维度级过滤（impact_dimensions）

过滤包含指定维度类型的 Issue，判断 Issue 的 `impact_scope` 是否包含某个维度。

```json
{
  "key": "impact_dimensions",
  "value": ["host", "cluster"],
  "method": "eq"
}
```

- `value` 为维度 key 数组，多个维度之间为 **OR** 关系（包含任一即命中）
- 支持的维度 key：`set`、`host`、`service_instances`、`cluster`、`node`、`service`、`pod`、`app`、`apm_service`

**示例**：过滤包含 host 或 cluster 维度的 Issue

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {
      "key": "impact_dimensions",
      "value": ["host", "cluster"],
      "method": "eq"
    }
  ]
}
```

#### 2. 实例级过滤（impact_scope.{维度}.{ID字段}）

按具体实例 ID 精确过滤 Issue。

**参数格式**：

```json
{
  "key": "impact_scope.{维度key}.{ID字段名}",
  "value": ["实例ID1", "实例ID2"],
  "method": "eq"
}
```

**关键说明**：

1. **conditions key 是动态构建的**：`impact_scope.host.bk_host_id` 中的 `host` 和 `bk_host_id` 都不是固定值
2. 维度 key 来源于 `impact_scope` 对象的第一层 key（如 `host`、`cluster`）
3. ID 字段名来源于该维度 `instance_list` 元素的第一个除 `display_name` 外的 key

**可用的 conditions key 示例**：

| 维度 | ID 字段名 | conditions key |
|------|----------|----------------|
| `set` | `set_id` | `impact_scope.set.set_id` |
| `host` | `bk_host_id` | `impact_scope.host.bk_host_id` |
| `service_instances` | `bk_service_instance_id` | `impact_scope.service_instances.bk_service_instance_id` |
| `cluster` | `bcs_cluster_id` | `impact_scope.cluster.bcs_cluster_id` |
| `node` | `node` | `impact_scope.node.node` |
| `service` | `service` | `impact_scope.service.service` |
| `pod` | `pod` | `impact_scope.pod.pod` |
| `apm_service` | `app_name`（第一个非 display_name 字段） | `impact_scope.apm_service.app_name` |

**注意事项**：
- `value` 必须传**字符串数组**，即使原始数据是整数（如 `bk_host_id`），也需要传 `"9185731"` 而非 `9185731`
- 多个实例 ID 之间是 **OR** 关系（匹配任一即命中）

**示例 1**：过滤影响了指定主机的 Issue

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {
      "key": "impact_scope.host.bk_host_id",
      "value": ["9185731", "10692392"],
      "method": "eq"
    }
  ]
}
```

**示例 2**：过滤影响了指定 BCS 集群的 Issue

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {
      "key": "impact_scope.cluster.bcs_cluster_id",
      "value": ["BCS-K8S-26322", "BCS-K8S-41193"],
      "method": "eq"
    }
  ]
}
```

#### 3. 组合使用

影响范围过滤可与其他 conditions 自由组合，所有 conditions 之间为 **AND** 关系。

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {
      "key": "priority",
      "value": ["P0", "P1"],
      "method": "eq"
    },
    {
      "key": "impact_scope.host.bk_host_id",
      "value": ["9185731"],
      "method": "eq"
    }
  ],
  "ordering": ["-update_time"],
  "page": 1,
  "page_size": 20
}
```

---

## 请求示例

### 示例 1：查询未分派的高优先级 Issue

```json
{
  "bk_biz_ids": [2],
  "status": ["NO_ASSIGNEE"],
  "conditions": [
    {"key": "priority", "value": ["P0", "P1"], "method": "eq", "condition": ""}
  ],
  "ordering": ["-update_time"],
  "page": 1,
  "page_size": 20,
  "show_aggs": true
}
```

### 示例 2：带时间范围和关键词搜索（使用 conditions 过滤实际状态）

```json
{
  "bk_biz_ids": [2, 3],
  "conditions": [
    {"key": "status", "value": ["unresolved"], "method": "eq", "condition": ""},
    {"key": "assignee", "value": ["zhangsan"], "method": "eq", "condition": ""}
  ],
  "query_string": "CPU",
  "start_time": 1741334400,
  "end_time": 1741420800,
  "ordering": ["-create_time"],
  "page": 1,
  "page_size": 10
}
```

### 示例 3：查询我负责的 Issue

```json
{
  "status": ["MY_ISSUE"],
  "ordering": ["status", "-update_time"],
  "page": 1,
  "page_size": 20
}
```

### 示例 4：指定趋势图的时间范围

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "priority", "value": ["P0", "P1"], "method": "eq"}
  ],
  "start_time": 1741334400,
  "end_time": 1741420800,
  "trend_start_time": 1741334400,
  "trend_end_time": 1741420800,
  "ordering": ["-update_time"],
  "page": 1,
  "page_size": 20
}
```

> **说明**：`trend_start_time` / `trend_end_time` 用于自定义趋势图展示的时间范围，不传则以默认时间为准。

---

## 响应结构

### 响应体

```json
{
  "result": true,
  "code": 200,
  "message": "OK",
  "data": {
    "issues": [...],
    "total": 128,
    "overview": {...},
    "aggs": [...],
    "dsl": {...}
  }
}
```

### 顶层字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `issues` | `object[]` | Issue 列表 |
| `total` | `int` | 满足查询条件的 Issue 总数 |
| `aggs` | `object[]` | 高级筛选聚合（仅 `show_aggs=true` 时返回） |
| `dsl` | `object` | ES DSL 查询语句（仅 `show_dsl=true` 时返回，用于调试） |

---

### Issue 单项字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Issue 唯一标识（前10位为秒级时间戳 + 8位 UUID hex） |
| `name` | `string` | Issue 名称（回归问题带 `[回归]` 前缀） |
| `status` | `string` | 状态：`pending_review` / `unresolved` / `resolved` / `archived` |
| `status_display` | `string` | 状态中文名 |
| `priority` | `string` | 优先级：`P0` / `P1` / `P2` |
| `priority_display` | `string` | 优先级中文名：高 / 中 / 低 |
| `assignee` | `string[]` | 负责人用户名列表，空数组表示未指派 |
| `is_regression` | `bool` | 是否为回归 Issue |
| `strategy_id` | `string` | 关联策略 ID |
| `strategy_name` | `string` | 策略名称 |
| `bk_biz_id` | `string` | 所属业务 ID |
| `bk_biz_name` | `string` | 业务名称 |
| `labels` | `string[]` | 标签列表 |
| `alert_count` | `int` | 关联告警总数（基于 AlertDocument 实时聚合），等于 `trend` 中所有时间段的告警数量之和 |
| `anomaly_message` | `string` | 异常信息描述，从关联告警的 `description` 字段获取。若无关联告警或描述为空，返回 `"--"` |
| `trend` | `[int, int][]` | 告警时间分布趋势，格式 `[[毫秒时间戳, 数量], ...]`，用于 sparkline 展示 |
| `first_alert_time` | `int` | 首条关联告警时间（秒级时间戳） |
| `last_alert_time` | `int` | 最近关联告警时间（秒级时间戳） |
| `create_time` | `int` | 创建时间（秒级时间戳） |
| `update_time` | `int` | 最近更新时间（秒级时间戳） |
| `resolved_time` | `int \| null` | 解决时间，仅 `resolved` 状态有值，其余为 `null` |
| `is_resolved` | `bool` | 是否已解决，根据 `resolved_time` 是否有值计算：有值则为 `true`，否则为 `false` |
| `duration` | `string` | 存活时长，人类可读格式（如 `"1d 1h"`、`"30min"`） |
| `impact_scope` | `object` | 影响范围快照，支持多维度（set/host/service_instances/cluster/node/service/pod/app/apm_service），见下方结构说明 |
| `aggregate_config` | `object` | 聚合配置快照，含 `aggregate_dimensions` / `conditions` / `alert_levels` |

---

### impact_scope 结构说明

```json
{
  "set": {
    "count": 3,
    "display_name": "集群",
    "instance_list": [
      {"set_id": "5070644", "display_name": "kihan-test/bcs-tke-test-BCS-K8S-41797"},
      {"set_id": "5017605", "display_name": "蓝鲸PaaS平台/BCS-K8S-40340"},
      {"set_id": "5043076", "display_name": "DB数据库生产环境/db.es.es"}
    ],
    "link_tpl": null
  },
  "host": {
    "count": 3,
    "display_name": "主机",
    "instance_list": [
      {"bk_host_id": 9185731,  "display_name": "21.249.64.16"},
      {"bk_host_id": 10692392, "display_name": "21.186.179.6"},
      {"bk_host_id": 1804751,  "display_name": "11.181.33.209"}
    ],
    "link_tpl": "/performance/detail/{bk_host_id}"
  },
  "service_instances": {
    "count": 1,
    "display_name": "服务实例",
    "instance_list": [
      {"bk_service_instance_id": 14041299, "display_name": "11.181.33.209_es-es_datanode_9200"}
    ],
    "link_tpl": null
  },
  "cluster": {
    "count": 3,
    "display_name": "bcs集群",
    "instance_list": [
      {"bcs_cluster_id": "BCS-K8S-26322", "display_name": "TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)"},
      {"bcs_cluster_id": "BCS-K8S-41193", "display_name": "南京三集群-业务安全-V1.26.1(BCS-K8S-41193)"},
      {"bcs_cluster_id": "BCS-K8S-41797", "display_name": "kihan-test-gz-0611(BCS-K8S-41797)"}
    ],
    "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview"
  },
  "apm_service": {
    "count": 1,
    "display_name": "apm_service",
    "instance_list": [
      {"app_name": "nf", "service_name": "nf.pushsvr", "bk_biz_id": 5016913, "display_name": "nf/nf.pushsvr"}
    ],
    "link_tpl": "?bizId={bk_biz_id}#/apm/service?filter-app_name={app_name}&filter-service_name={service_name}"
  }
}
```

#### 维度说明

| 维度 key | 展示名称 | 说明 | instance_list 元素字段 |
|----------|----------|------|------------------------|
| `set` | 集群 | CMDB 集群 | `set_id`, `display_name` |
| `host` | 主机 | 主机 | `bk_host_id`, `display_name` |
| `service_instances` | 服务实例 | 服务实例 | `bk_service_instance_id`, `display_name` |
| `cluster` | bcs集群 | K8S 集群（多集群时） | `bcs_cluster_id`, `display_name` |
| `node` | node | K8S 节点（单集群时） | `bcs_cluster_id`, `node`, `display_name` |
| `service` | service | K8S Service（单集群时） | `bcs_cluster_id`, `service`, `display_name` |
| `pod` | pod | K8S Pod（单集群时） | `bcs_cluster_id`, `pod`, `display_name` |
| `app` | app | APM 应用（多应用时） | `app_name`, `bk_biz_id`, `display_name` |
| `apm_service` | apm_service | APM 服务（单应用时） | `app_name`, `service_name`, `bk_biz_id`, `display_name` |

#### 通用字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | `int` | 该维度受影响实例总数（去重后） |
| `display_name` | `string` | 维度的中文展示名称，由 `ImpactScopeDimension` 枚举提供 |
| `instance_list` | `object[]` | 实例列表，最多 50 条 |
| `link_tpl` | `string \| null` | 前端跳转链接模板，支持占位符替换（如 `{bk_host_id}`） |

#### 前端渲染说明

**`display_name` 字段用于影响范围列的展示**：前端在设计稿"影响范围"列中展示的"集群"、"主机"、"服务实例"等中文名称，直接使用 `display_name` 字段的值。

**设计稿对应示例**：

```
┌─────────────────────────────┐
│       影响范围                │
├─────────────────────────────┤
│  集群: 100                   │  ← display_name="集群", count=100
│  主机: 124                   │  ← display_name="主机", count=124
├─────────────────────────────┤
│  集群: 100                   │  ← display_name="集群"
│  node: 22                    │  ← display_name="node"
│  pod: 30                     │  ← display_name="pod"
└─────────────────────────────┘
```

**前端渲染逻辑**：
1. 遍历 `impact_scope` 对象的每个维度 key（如 `host`、`set`、`cluster` 等）
2. 使用维度数据中的 `display_name` 作为展示名称，`count` 作为数量
3. 按固定顺序展示：`set` > `host` > `service_instances` > `cluster` > `node` > `service` > `pod` > `app` > `apm_service`

> **说明**：
> - 每个维度都是可选的，仅当存在对应类型的影响范围时才返回
> - `cluster`/`node`/`service`/`pod` 互斥：多集群时返回 `cluster`，单集群时返回 `node`/`service`/`pod`
> - `app`/`apm_service` 互斥：多应用时返回 `app`，单应用时返回 `apm_service`
> - 若 Issue 无任何影响范围信息，`impact_scope` 为空对象 `{}`

---

### aggs 结构

```json
[
  {
    "id": "priority",
    "name": "优先级",
    "count": 128,
    "children": [
      {"id": "P0", "name": "高", "count": 15},
      {"id": "P1", "name": "中", "count": 53},
      {"id": "P2", "name": "低", "count": 60}
    ]
  },
  {
    "id": "status",
    "name": "状态",
    "count": 128,
    "children": [
      {"id": "pending_review", "name": "待审核", "count": 30},
      {"id": "unresolved", "name": "未解决", "count": 12},
      {"id": "resolved", "name": "已解决", "count": 80},
      {"id": "archived", "name": "归档", "count": 6}
    ]
  },
  {
    "id": "assignee",
    "name": "负责人",
    "count": 30,
    "children": [
      {"id": "my_assignee", "name": "我负责的", "count": 20},
      {"id": "no_assignee", "name": "未分配", "count": 10}
    ]
  },
  {
    "id": "is_regression",
    "name": "类型",
    "count": 128,
    "children": [
      {"id": "true", "name": "回归问题", "count": 8},
      {"id": "false", "name": "新问题", "count": 120}
    ]
  }
]
```

> **说明**：aggs 覆盖前端筛选面板的四个维度：
> - **priority**：优先级（P0/P1/P2）
> - **status**：状态（pending_review/unresolved/resolved/archived）
> - **assignee**：负责人（使用 `filters` 聚合，只返回「我负责的」和「未分配」两个命名桶，不枚举所有负责人）
> - **is_regression**：类型（true=回归问题，false=新问题）

### aggs 字段前端使用说明

| 字段 | 用途 | 注意事项 |
|------|------|----------|
| `id` | 作为筛选条件的 `key` 值传给后端 | 例如：`{"key": "priority", "value": ["P0"], "method": "eq"}` |
| `name` | 筛选面板的标题展示 | 已翻译为中文，可直接展示 |
| `children[].id` | 作为筛选条件的 `value` 值 | `assignee` 的 `my_assignee` 表示"我负责的"，`no_assignee` 表示"未分配" |
| `children[].name` | 筛选选项的展示名称 | 已翻译为中文，可直接展示 |
| `children[].count` | 该选项对应的 Issue 数量 | 用于展示数量标签 |

#### 前端筛选面板数据来源映射

| 筛选项 | 对应参数 | 筛选方式示例 |
|--------|----------|--------------|
| 优先级 | `conditions` | `conditions: [{"key": "priority", "value": ["P0", "P1"], "method": "eq"}]` |
| 状态 | `conditions` | `conditions: [{"key": "status", "value": ["unresolved", "pending_review"], "method": "eq"}]` |
| 负责人 | `conditions` | `conditions: [{"key": "assignee", "value": ["zhangsan"], "method": "eq"}]` |
| 类型 | `conditions` | `conditions: [{"key": "is_regression", "value": [true], "method": "eq"}]` |
| 我负责的 | `status` | `status: ["MY_ISSUE"]` |
| 未分派的 | `status` | `status: ["NO_ASSIGNEE"]` |

> **注意**：
> - `status` 参数**仅支持虚拟状态** `MY_ISSUE` 和 `NO_ASSIGNEE`，用于快速筛选场景
> - 实际状态（`pending_review` / `unresolved` / `resolved` / `archived`）必须通过 `conditions` 参数过滤

---

## 完整响应示例

```json
{
  "result": true,
  "code": 200,
  "message": "OK",
  "data": {
    "issues": [
      {
        "id": "1741420800a3b7c9d2",
        "name": "主机 CPU 使用率过高",
        "status": "unresolved",
        "status_display": "未解决",
        "priority": "P0",
        "priority_display": "高",
        "assignee": ["zhangsan"],
        "is_regression": false,
        "strategy_id": "1001",
        "strategy_name": "主机 CPU 使用率过高",
        "bk_biz_id": "2",
        "bk_biz_name": "蓝鲸",
        "labels": ["主机监控", "基础设施"],
        "alert_count": 15,
        "anomaly_message": "主机 10.0.0.1 CPU 使用率达到 95%，超过阈值 80%",
        "trend": [
          [1741334400000, 3],
          [1741348800000, 5],
          [1741363200000, 2],
          [1741377600000, 0],
          [1741392000000, 4],
          [1741406400000, 1]
        ],
        "first_alert_time": 1741420790,
        "last_alert_time": 1741507200,
        "create_time": 1741420800,
        "update_time": 1741510000,
        "resolved_time": null,
        "is_resolved": false,
        "duration": "1d 1h",
        "impact_scope": {
          "host": {
            "count": 2,
            "display_name": "主机",
            "instance_list": [
              {"bk_host_id": 1001, "display_name": "10.0.0.1"},
              {"bk_host_id": 1002, "display_name": "10.0.0.2"}
            ],
            "link_tpl": "/performance/detail/{bk_host_id}"
          },
          "service_instances": {
            "count": 3,
            "display_name": "服务实例",
            "instance_list": [
              {"bk_service_instance_id": 2001, "display_name": "service-instance-1"},
              {"bk_service_instance_id": 2002, "display_name": "service-instance-2"},
              {"bk_service_instance_id": 2003, "display_name": "service-instance-3"}
            ],
            "link_tpl": null
          }
        },
        "aggregate_config": {
          "aggregate_dimensions": ["bk_target_ip"],
          "conditions": [],
          "alert_levels": [1, 2]
        }
      }
    ],
    "total": 128,
    "aggs": [
      {
        "id": "priority",
        "name": "优先级",
        "count": 128,
        "children": [
          {"id": "P0", "name": "高", "count": 15},
          {"id": "P1", "name": "中", "count": 53},
          {"id": "P2", "name": "低", "count": 60}
        ]
      },
      {
        "id": "status",
        "name": "状态",
        "count": 128,
        "children": [
          {"id": "pending_review", "name": "待审核", "count": 30},
          {"id": "unresolved", "name": "未解决", "count": 12},
          {"id": "resolved", "name": "已解决", "count": 80},
          {"id": "rejected", "name": "拒绝/无效", "count": 6}
        ]
      },
      {
        "id": "assignee",
        "name": "负责人",
        "count": 30,
        "children": [
          {"id": "my_assignee", "name": "我负责的", "count": 20},
          {"id": "no_assignee", "name": "未分配", "count": 10}
        ]
      },
      {
        "id": "is_regression",
        "name": "类型",
        "count": 128,
        "children": [
          {"id": "true", "name": "回归问题", "count": 8},
          {"id": "false", "name": "新问题", "count": 120}
        ]
      }
    ]
  }
}
```

---

## 字段与设计稿映射说明

本节详细说明接口返回字段在设计稿界面上的对应位置和展示方式，帮助前端开发者快速理解字段用途。

### 设计稿列与字段对应总览

| 设计稿列名 | 对应字段 | 展示方式 | 备注 |
|-----------|----------|----------|------|
| **Issues** | `name` + `anomaly_message` + `is_regression` + `alert_count` | 三行布局：第一行蓝色链接（含回归标识），第二行灰色文字，第三行告警数 | 点击名称弹出详情抽屉 |
| **标签** | `labels` | 标签样式展示 | 独立列，方便排序筛选 |
| **最后出现时间** | `last_alert_time` | 绝对时间 + 相对时间 | 支持排序 |
| **最早发生时间** | `first_alert_time` | 绝对时间 + 相对时间 | 支持排序 |
| **趋势** | `trend` | Sparkline 柱状图 | 悬停显示具体数值 |
| **影响范围** | `impact_scope` | 多行展示，每行一个维度 | 如：集群、主机、Pod 等 |
| **优先级** | `priority` + `priority_display` | 彩色徽章 | 高(红)/中(橙)/低(蓝) |
| **状态** | `status` + `status_display` | 彩色徽章 | 待审核(蓝)/未解决(黄)/已解决(绿) |
| **负责人** | `assignee` | 文字或"未指派" | 点击可修改 |
| **操作** | `is_resolved` | "标为已解决"按钮 | 仅 `is_resolved=false` 时显示 |

### Issues 列详细说明

Issues 列是复合列，包含多个字段信息，展示结构如下：

```
┌─────────────────────────────────────────────────────────┐
│ [回归] 异常登录日志告警                   ← name（蓝色链接，is_regression=true 时显示 [回归] 前缀）
│ NullpointerException                     ← anomaly_message（灰色）
│ 🔔 123                                   ← alert_count（告警数量）
└─────────────────────────────────────────────────────────┘
```

**字段组合规则**：
- 第一行：`name` 字段，蓝色字体，可点击打开详情抽屉
  - 若 `is_regression=true`，名称前自动添加 `[回归]` 前缀，表示为回归类型
  - 若 `is_regression=false`，表示为新创建的 Issue
- 第二行：`anomaly_message` 字段，灰色小字，展示关键堆栈/异常信息
  - 若值为 `"--"`，显示占位符或不展示
- 第三行：`alert_count` 带铃铛图标，展示关联告警数量

### 影响范围列详细说明

`impact_scope` 字段支持多维度，每个维度结构如下：

```json
{
  "host": {
    "count": 2,
    "display_name": "主机",
    "instance_list": [
      {"bk_host_id": 1001, "display_name": "10.0.0.1"},
      {"bk_host_id": 1002, "display_name": "10.0.0.2"}
    ],
    "link_tpl": "/performance/detail/{bk_host_id}"
  },
  "service_instances": {
    "count": 3,
    "display_name": "服务实例",
    "instance_list": [
      {"bk_service_instance_id": 2001, "display_name": "service-instance-1"}
    ],
    "link_tpl": null
  }
}
```

**前端展示逻辑**：
1. 遍历 `impact_scope` 中的所有维度（`set`/`host`/`service_instances`/`cluster`/`node`/`service`/`pod`/`app`/`apm_service`）
2. 每个维度展示一行：`{display_name}: {count}`
3. `display_name` 为维度中文名（如"集群"、"主机"），`count` 为该维度受影响实例总数
4. **`count` 数字使用蓝色 (#3A84FF) 显示，表示可点击**
5. 点击数字后展开抽屉，显示 `instance_list` 中的具体资源列表
6. 若 `link_tpl` 不为 null，可将 `instance_list` 元素字段替换到模板中生成跳转链接

**展示示例**：
```
集群: 100
主机: 124
```

或

```
集群: 100
node: 22
pod: 30
```

### 趋势列详细说明

`trend` 字段格式：`[[毫秒时间戳, 数量], ...]`

**前端渲染逻辑**：
1. 使用 Sparkline 柱状图组件
2. X 轴为时间，Y 轴为告警数量
3. 悬停时显示具体时间点和数量
4. 点击可跳转详情页查看完整趋势图

**示例数据**：
```json
"trend": [
  [1741334400000, 3],
  [1741348800000, 5],
  [1741363200000, 2]
]
```

### 时间字段展示规则

| 字段 | 展示格式 | 示例 |
|------|----------|------|
| `last_alert_time` | 相对时间优先，悬停显示绝对时间 | `15s ago` / `8 months ago` |
| `first_alert_time` | 同上 | `2026-01-04` 悬停显示 `2026-01-04 00:00:00` |

**前端处理建议**：
- 1分钟内：`刚刚`
- 1小时内：`X分钟前`
- 24小时内：`X小时前`
- 7天内：`X天前`
- 超过7天：显示绝对时间 `YYYY-MM-DD`

### 徽章样式映射

#### 优先级徽章

| priority | priority_display | 颜色 |
|----------|------------------|------|
| `P0` | 高 | 红色 (#FF5656) |
| `P1` | 中 | 橙色 (#FF9C01) |
| `P2` | 低 | 蓝色 |

#### 状态徽章

| status | status_display | 颜色 |
|--------|----------------|------|
| `pending_review` | 待审核 | 蓝色 |
| `unresolved` | 未解决 | 黄色/橙色 |
| `resolved` | 已解决 | 绿色 |
| `archived` | 归档 | 灰色 |

### 操作列逻辑

操作列根据 `is_resolved` 字段控制按钮显示：

| is_resolved | 显示内容 |
|-------------|----------|
| `false` | 显示"标为已解决"按钮 |
| `true` | 不显示操作按钮，或显示"已处理"状态 |

**其他操作按钮**（根据需求可扩展）：
- 指派负责人：点击 `assignee` 区域弹出指派弹窗
- 调整优先级：点击优先级徽章弹出下拉选择
- 调整状态：点击状态徽章弹出下拉选择

---

## 附录

### 优先级枚举

| 值 | 中文名 |
|----|--------|
| `P0` | 高 |
| `P1` | 中 |
| `P2` | 低 |

### 状态枚举

| 值 | 中文名 |
|----|--------|
| `pending_review` | 待审核 |
| `unresolved` | 未解决 |
| `resolved` | 已解决 |
| `archived` | 归档 |

### 默认排序规则

当 `ordering` 未传或为空时，默认排序为 `["status", "-update_time"]`：
1. **状态优先**：活跃 Issue（`pending_review` / `unresolved`）排在前面
2. **最近更新**：同状态下按 `update_time` 倒序

### trend 字段说明

- 格式：`[[毫秒时间戳, 告警数量], ...]`
- 时间范围：由 Issue 自身的 `first_alert_time` / `last_alert_time` 决定，展示完整生命周期内的告警分布
- **自定义时间范围**：通过 `trend_start_time` / `trend_end_time` 参数可指定趋势图的时间范围，不传则默认使用本页 Issue 的实际告警时间边界
- 用途：用于前端 sparkline 小图展示
- `alert_count` = `trend` 中所有时间段的告警数量之和

### anomaly_message 字段说明

- **来源**：从关联告警的 `description` 字段获取，取最新一条告警的描述
- **默认值**：若无关联告警或描述为空，返回 `"--"`
- **用途**：展示 Issue 的异常摘要信息，帮助用户快速了解问题内容
- **示例**：
  - 有告警时：`"主机 10.0.0.1 CPU 使用率达到 95%，超过阈值 80%"`
  - 无告警时：`"--"`

### impact_scope 字段说明

- **来源**：从 Issue 创建时聚合的告警维度中提取
- **更新时机**：Issue 创建时固化，不会随后续告警变化
- **支持维度**：
  - `set`：CMDB 集群，从告警维度 `bk_topo_node` 提取
  - `host`：主机，从告警维度 `bk_host_id` / `ip` 提取，最多 50 条
  - `service_instances`：服务实例，从告警维度 `bk_service_instance_id` 提取，最多 50 条
  - `cluster`/`node`/`service`/`pod`：K8S 资源，从告警维度 `bcs_cluster_id` / `node` / `service` / `pod` 提取
  - `app`/`apm_service`：APM 应用/服务，从告警维度 `app_name` / `service_name` 提取
- **link_tpl 字段用途**：前端可将 `instance_list` 元素字段替换到模板中生成跳转链接

### ImpactScopeDimension 维度展示名称

`ImpactScopeDimension` 枚举定义了 `impact_scope` 中各维度的中文展示名称，在接口层为每个维度添加 `display_name` 字段。

| 维度 key | 展示名称 |
|----------|----------|
| `set` | 集群 |
| `host` | 主机 |
| `service_instances` | 服务实例 |
| `cluster` | bcs集群 |
| `node` | node |
| `service` | service |
| `pod` | pod |
| `app` | app |
| `apm_service` | apm_service |
