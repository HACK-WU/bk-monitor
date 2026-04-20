# Issue 详情页接口调用流程

> **版本**: v3.0
> **更新时间**: 2026-04-02
> **变更说明**: 调整调用流程——趋势图、最新/最早告警与 detail 并行执行（时间范围由 Issue 列表页传入），维度统计仍依赖 detail 返回的聚合维度，告警列表改为用户点击时按需加载（`page_size: 100`，无分页）。`/fta/issue/alert/search` 接口废弃。

---

## 一、接口总览

Issue 详情页由以下接口协同完成数据获取：

| 接口 | 地址                                         | 职责 | 来源 |
|------|--------------------------------------------|------|------|
| Issue 详情 | `POST /fta/issue/issue/detail`             | Issue 元数据（状态、优先级、负责人、影响范围等） | Issue 模块（新建） |
| 告警趋势图 | `POST /fta/alert/v2/alert/date_histogram/` | 告警分布直方图 | 告警中心（现有） |
| 维度统计 | `POST /fta/alert/v2/alert/top_n/`          | 维度 Top N 聚合 | 告警中心（现有） |
| 告警搜索 | `POST /fta/alert/v2/alert/search/`         | 告警列表（按需加载） + 最新/最早告警 | 告警中心（现有） |
| 告警详情 | `GET /fta/alert/v2/alert/detail/`          | 单条告警详情（默认展示最新告警） | 告警中心（现有） |
| 问题活动 | `POST /fta/issue/issue/activities`         | Issue 活动日志 | Issue 模块（现有） |
| 历史 Issue | `POST /fta/issue/issue/history`            | 同策略历史 Issue | Issue 模块（现有） |

### 废弃接口

| 接口 | 地址 | 说明 |
|------|------|------|
| ~~Issue 告警查询~~ | ~~`POST /fta/issue/alert/search`~~ | **已废弃**，功能由告警中心现有接口替代 |

---

## 二、接口职责划分

### 2.1 `/fta/issue/issue/detail` — 仅返回 Issue 元数据

**只返回 Issue 自身的静态/元数据，不返回任何告警相关的动态数据。**

返回字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Issue ID |
| `name` | `string` | Issue 名称 |
| `anomaly_message` | `string` | 异常信息描述 |
| `status` / `status_display` | `string` | 状态 |
| `is_regression` | `bool` | 是否回归 |
| `priority` / `priority_display` | `string` | 优先级 |
| `assignee` | `string[]` | 负责人列表 |
| `strategy_id` / `strategy_name` | `string` | 关联策略 |
| `bk_biz_id` / `bk_biz_name` | `string` | 业务 |
| `labels` | `string[]` | 标签 |
| `first_alert_time` | `int` | 首条告警时间（秒级时间戳） |
| `last_alert_time` | `int` | 最近告警时间（秒级时间戳） |
| `create_time` | `int` | 创建时间 |
| `update_time` | `int` | 更新时间 |
| `resolved_time` | `int \| null` | 解决时间 |
| `is_resolved` | `bool` | 是否已解决 |
| `duration` | `string` | 存活时长 |
| `impact_scope` | `object` | 影响范围 |
| `aggregate_config` | `object` | 聚合配置（含 `aggregate_dimensions`，每项含 `field` 和 `display_name`） |

**不再返回的字段**：`alert_ids`、`latest_alert_id`、`earliest_alert_id`、`alert_count`、`dimension_summary`、`trend`

### 2.2 告警中心现有接口 — 提供告警动态数据

所有告警相关的动态数据，通过 `conditions` 传入 `issue_id` 过滤条件，复用告警中心现有接口：

| 数据模块 | 接口 | 过滤方式 |
|---------|------|---------|
| 趋势图 | `POST /fta/alert/v2/alert/date_histogram/` | `conditions: [{"key": "issue_id", "value": ["xxx"], "method": "eq"}]` |
| 维度统计 | `POST /fta/alert/v2/alert/top_n/` | 同上 |
| 告警列表 | `POST /fta/alert/v2/alert/search/` | 同上 |
| 最新告警 | `POST /fta/alert/v2/alert/search/` | 同上 + `ordering: ["-create_time"]` + `page_size: 1` |
| 最早告警 | `POST /fta/alert/v2/alert/search/` | 同上 + `ordering: ["create_time"]` + `page_size: 1` |

> **技术说明**：`AlertDocument` 已有 `issue_id = field.Keyword()` 字段，`conditions` 的处理逻辑（`add_conditions` → `parse_condition_item`）直接将 `key` 作为 ES 字段名构建 `terms` 查询，无需在 `AlertQueryTransformer.query_fields` 中注册 `issue_id`。

---

## 三、调用流程与依赖关系

### 3.1 前置条件：Issue 列表页传入参数

从 Issue 列表页跳转到详情页时，URL 或路由参数中需要携带以下信息：

| 参数 | 来源 | 说明 |
|------|------|------|
| `issue_id` | Issue 列表页选中的 Issue ID | 所有接口的核心标识 |
| `bk_biz_id` | Issue 列表页的业务 ID | 业务过滤 |
| `start_time` | Issue 列表页的时间选择器起始值 | 告警接口的时间范围 |
| `end_time` | Issue 列表页的时间选择器结束值 | 告警接口的时间范围 |

> **关键**：`start_time` / `end_time` 直接复用 Issue 列表页的时间范围，不需要等 detail 接口返回。

### 3.2 调用阶段说明

#### 第一阶段：并行请求（页面打开立即执行）

页面打开后，**立即并行**发起以下 5 个请求（所有参数均来自 Issue 列表页传入，无需等待任何接口返回）：

| 接口                                         | 依赖 | 说明 |
|--------------------------------------------|------|------|
| `POST /fta/issue/issue/detail`             | 无 | 获取 Issue 元数据 |
| `POST /fta/issue/issue/activities`         | 无 | 获取问题活动日志 |
| `POST /fta/alert/v2/alert/date_histogram/` | 无（时间来自列表页） | 趋势图 |
| `POST /fta/alert/v2/alert/search/`         | 无（时间来自列表页） | 最新告警（`ordering: ["-create_time"]`, `page_size: 1`） |
| `POST /fta/alert/v2/alert/search/`         | 无（时间来自列表页） | 最早告警（`ordering: ["create_time"]`, `page_size: 1`） |

**此阶段可渲染**：页面头部（标题、状态标签）、基本信息面板、问题活动时间线、趋势图、最新/最早告警标签。

#### 第二阶段：依赖 detail 的请求（维度统计）

**必须等待 `issue/detail` 返回后**，从响应中提取 `aggregate_dimensions`，再发起维度统计请求：

| 参数 | 来源字段 | 用途 |
|------|---------|------|
| `aggregate_dimensions` | `data.aggregate_config.aggregate_dimensions` | 提取每项的 `field` 用于 top_n 接口的 `fields` 参数，`display_name` 用于维度展示名称 |

| 接口 | 依赖 | 说明 |
|------|------|------|
| `POST /fta/alert/v2/alert/top_n/` | `issue/detail` 的 `aggregate_dimensions` | 维度统计 |

#### 第三阶段：用户交互触发

| 触发场景 | 调用接口 | 说明 |
|----------|---------|------|
| **点击告警列表 Tab** | `alert/search` | `page_size: 100`，一次性加载，无分页 |
| 检索栏搜索 | `alert/date_histogram` + `alert/top_n` + `alert/search` | `conditions` / `query_string` 变化 |
| 切换时间范围 | `alert/date_histogram` + `alert/top_n` + `alert/search` | `start_time` / `end_time` 变化 |
| 告警列表排序 | `alert/search` | `ordering` 变化 |
| 点击历史 Issue | `POST /fta/issue/issue/history` | — |

> **注意**：告警列表不再有翻页操作，`page_size` 固定为 100，当前页面无分页按钮。


---

## 四、各接口请求/响应详情

### 4.1 Issue 详情 — `POST /fta/issue/issue/detail`

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `id` | `string` | 是 | Issue ID |
| `bk_biz_id` | `int` | 是 | 业务 ID |

#### 请求示例

```json
{
  "id": "1741420800a3b7c9d2",
  "bk_biz_id": 2
}
```

#### 响应示例

```json
{
  "result": true,
  "code": 200,
  "data": {
    "id": "1741420800a3b7c9d2",
    "name": "异常登录日志告警",
    "anomaly_message": "NulpointerException",
    "status": "unresolved",
    "status_display": "未解决",
    "is_regression": true,
    "priority": "P0",
    "priority_display": "高",
    "assignee": ["carrielu", "nekzhang"],
    "strategy_id": "1001",
    "strategy_name": "异常登录日志告警",
    "bk_biz_id": "2",
    "bk_biz_name": "蓝鲸",
    "labels": ["主机监控"],
    "first_alert_time": 1741420790,
    "last_alert_time": 1741507200,
    "create_time": 1741420800,
    "update_time": 1741510000,
    "resolved_time": null,
    "is_resolved": false,
    "duration": "1d 1h",
    "impact_scope": {
      "cluster": {
        "count": 1,
        "display_name": "集群",
        "instance_list": [{"bcs_cluster_id": "BCS-K8s-5234", "display_name": "BCS-K8s-5234"}]
      }
    },
    "aggregate_config": {
      "aggregate_dimensions": [
        {"field": "bk_target_ip", "display_name": "目标IP"},
        {"field": "bk_cloud_id", "display_name": "采集器云区域ID"}
      ],
      "conditions": [],
      "alert_levels": [1, 2]
    }
  }
}
```

### 4.2 告警趋势图 — `POST /fta/alert/v2/alert/date_histogram/`

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `bk_biz_ids` | `int[]` | 否 | 业务 ID 列表 |
| `conditions` | `object[]` | 是 | **必须包含 `issue_id` 过滤条件** |
| `query_string` | `string` | 否 | 查询字符串 |
| `start_time` | `int` | 是 | 开始时间（秒级时间戳） |
| `end_time` | `int` | 是 | 结束时间（秒级时间戳） |
| `interval` | `string` | 否 | 聚合周期，默认 `"auto"` |

#### 请求示例

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "query_string": "",
  "start_time": 1741420790,
  "end_time": 1741507200,
  "interval": "auto"
}
```

#### 响应示例

```json
{
  "result": true,
  "code": 200,
  "data": {
    "series": [
      {
        "data": [[1741420800000, 3], [1741507200000, 5]],
        "name": "ABNORMAL",
        "display_name": "未恢复"
      },
      {
        "data": [[1741420800000, 1], [1741507200000, 2]],
        "name": "RECOVERED",
        "display_name": "已恢复"
      },
      {
        "data": [[1741420800000, 0], [1741507200000, 1]],
        "name": "CLOSED",
        "display_name": "已关闭"
      }
    ],
    "unit": ""
  }
}
```

> **注意**：返回格式为 `{"series": [...], "unit": ""}`，其中 `series[*].data` 是 `[[毫秒时间戳, 数量], ...]` 的二维数组。

### 4.3 维度统计 — `POST /fta/alert/v2/alert/top_n/` （可以参考告警分析的计算方式）

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `bk_biz_ids` | `int[]` | 否 | 业务 ID 列表 |
| `conditions` | `object[]` | 是 | **必须包含 `issue_id` 过滤条件** |
| `query_string` | `string` | 否 | 查询字符串 |
| `start_time` | `int` | 是 | 开始时间 |
| `end_time` | `int` | 是 | 结束时间 |
| `fields` | `string[]` | 是 | 统计维度字段列表，**来源于 detail 返回的 `aggregate_config.aggregate_dimensions[].field`**（需根据白名单判断是否加 `tags.` 前缀） |
| `size` | `int` | 否 | 每个维度的桶数量，默认 10，建议设为 5（Top5） |

#### 请求示例

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "query_string": "",
  "start_time": 1741420790,
  "end_time": 1741507200,
  "fields": ["tags.bk_target_ip", "bk_cloud_id"],
  "size": 5
}
```

> **注意**：维度字段是否需要加 `tags.` 前缀，取决于该字段是否在**内置字段白名单**中。白名单中的字段（如 `bk_cloud_id`、`ip`、`bk_host_id`、`severity` 等）直接使用原始名称；不在白名单中的自定义维度（如 `bk_target_ip`、`device_name` 等）需要加 `tags.` 前缀。完整白名单和转换函数详见 **6.4 维度字段名映射**。

#### 响应示例

```json
{
  "result": true,
  "code": 200,
  "data": {
    "doc_count": 86,
    "fields": [
      {
        "field": "tags.bk_target_ip",
        "is_char": true,
        "bucket_count": 12,
        "buckets": [
          {"id": "\"10.0.0.1\"", "name": "10.0.0.1", "count": 30},
          {"id": "\"10.0.0.2\"", "name": "10.0.0.2", "count": 20},
          {"id": "\"10.0.0.3\"", "name": "10.0.0.3", "count": 15},
          {"id": "\"10.0.0.4\"", "name": "10.0.0.4", "count": 12},
          {"id": "\"10.0.0.5\"", "name": "10.0.0.5", "count": 8}
        ]
      }
    ]
  }
}
```

#### 前端适配说明

`top_n` 接口的返回格式与设计稿中 `dimension_summary` 的格式有差异，前端需要做以下适配：

| 适配项 | 说明 | 处理方式 |
|--------|------|---------|
| **百分比** | 接口不返回 `percentage` | 前端根据 `doc_count`（总数）和 `bucket.count` 计算：`percentage = count / doc_count * 100` |
| **"其他"聚合** | 接口只返回 Top N 桶 | 前端计算：`其他.count = doc_count - sum(buckets[*].count)`，若 > 0 则追加"其他"项 |
| **维度中文名** | 接口不返回维度中文名 | 直接使用 `issue/detail` 返回的 `aggregate_dimensions[].display_name` |
| **字符字段引号** | `is_char=true` 的字段，`id` 会被加上双引号 | 前端使用 `name` 字段展示，`id` 字段用于检索栏过滤 |

### 4.4 告警列表 — `POST /fta/alert/v2/alert/search/`

#### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `bk_biz_ids` | `int[]` | 否 | 业务 ID 列表 |
| `conditions` | `object[]` | 是 | **必须包含 `issue_id` 过滤条件** |
| `query_string` | `string` | 否 | 查询字符串 |
| `start_time` | `int` | 是 | 开始时间 |
| `end_time` | `int` | 是 | 结束时间 |
| `ordering` | `string[]` | 否 | 排序字段 |
| `page` | `int` | 否 | 页码，默认 1 |
| `page_size` | `int` | 否 | 每页大小，默认 10 |
| `show_overview` | `bool` | 否 | 是否展示总览统计，默认 true |
| `show_aggs` | `bool` | 否 | 是否展示聚合统计，默认 true |

#### 告警列表请求示例（用户点击告警列表 Tab 时触发）

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "query_string": "",
  "start_time": 1741420790,
  "end_time": 1741507200,
  "ordering": [],
  "page": 1,
  "page_size": 100,
  "show_overview": true,
  "show_aggs": false
}
```

> **注意**：告警列表 `page_size` 固定为 100，一次性加载，当前页面无分页按钮。

#### 最新告警请求示例

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "ordering": ["-create_time"],
  "page": 1,
  "page_size": 1,
  "show_overview": false,
  "show_aggs": false
}
```

#### 最早告警请求示例

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "ordering": ["create_time"],
  "page": 1,
  "page_size": 1,
  "show_overview": false,
  "show_aggs": false
}
```

---

## 五、设计稿字段映射（完整版）

### 页面头部

| 设计稿元素 | 数据来源 | 字段 |
|-----------|---------|------|
| 主标题 | `issue/detail` | `anomaly_message` |
| 副标题 | `issue/detail` | `name` |
| 回归/新标签 | `issue/detail` | `is_regression` |

### 趋势图模块

| 设计稿元素 | 数据来源 | 字段 |
|-----------|---------|------|
| 告警事件数量 | `alert/search`（最新告警或告警列表） | `data.total`（关联告警总数） |
| 堆叠柱状图 | `alert/date_histogram` | `series` |

### 维度统计模块

| 设计稿元素 | 数据来源 | 字段 |
|-----------|---------|------|
| 维度分布进度条 | `alert/top_n` | `fields[*].buckets`（前端计算百分比和"其他"） |
| 维度中文名 | `issue/detail` 的 `aggregate_dimensions[].display_name` | 直接使用，无需前端映射 |

### 基本信息模块

| 设计稿元素 | 数据来源 | 字段 | 可编辑 |
|-----------|---------|------|:------:|
| 优先级 | `issue/detail` | `priority` / `priority_display` | ✅ |
| 负责人 | `issue/detail` | `assignee` | ✅ |
| 影响范围 | `issue/detail` | `impact_scope` | ❌ |
| 最后出现时间 | `issue/detail` | `last_alert_time` | ❌ |
| 最早发生时间 | `issue/detail` | `first_alert_time` | ❌ |
| 标记为已解决 | 调用 `ResolveIssueResource` | — | — |

### 告警列表模块

| 设计稿元素 | 数据来源 | 说明 |
|-----------|---------|------|
| 最新的告警 | `alert/search`（`ordering: ["-create_time"]`, `page_size: 1`） | 第一阶段立即请求，取返回列表第一条 |
| 最早的告警 | `alert/search`（`ordering: ["create_time"]`, `page_size: 1`） | 第一阶段立即请求，取返回列表第一条 |
| 告警列表 | `alert/search`（`page_size: 100`） | **用户点击告警列表 Tab 时才加载**，一次性加载最多 100 条，无分页 |

### 问题活动模块

| 设计稿元素 | 数据来源 | 字段 |
|-----------|---------|------|
| 活动时间线 | `issue/activity` | 活动日志列表 |

### 历史 Issue 模块

| 设计稿元素 | 数据来源 | 字段 |
|-----------|---------|------|
| 历史 Issue 列表 | history（用户交互触发） | Issue 列表 |

---

## 六、关键约束与注意事项

### 6.1 调用顺序约束

```
第一阶段（全部并行，无依赖）：
  POST /fta/issue/issue/detail
  POST /fta/issue/issue/activity
  POST /fta/alert/v2/alert/date_histogram/（趋势图）
  POST /fta/alert/v2/alert/search/（最新告警）
  POST /fta/alert/v2/alert/search/（最早告警）

第二阶段（依赖 issue/detail）：
  POST /fta/alert/v2/alert/top_n/（维度统计）—— 需要 aggregate_dimensions

第三阶段（用户点击触发）：
  POST /fta/alert/v2/alert/search/（告警列表）—— 用户点击告警列表 Tab 时才执行
```

**核心约束**：
- 第一阶段 5 个接口全部并行，**无任何依赖**，`issue_id` 和 `start_time`/`end_time` 均来自 Issue 列表页传入的路由参数
- `alert/top_n` 必须等待 `issue/detail` 返回后才能发起，因为需要 `aggregate_config.aggregate_dimensions` 作为 `fields` 参数
- `alert/search`（告警列表）不在页面加载时执行，仅在用户点击告警列表 Tab 时触发

### 6.2 时间范围策略

| 场景 | `start_time` | `end_time` |
|------|-------------|----------|
| 首次加载 | **Issue 列表页时间选择器的起始值**（路由参数传入） | **Issue 列表页时间选择器的结束值**（路由参数传入） |
| 用户切换时间选择器 | 时间选择器的起始值 | 时间选择器的结束值 |

### 6.3 检索栏搜索

用户在检索栏输入条件后，`conditions` 数组需要**同时包含** `issue_id` 过滤和用户输入的条件：

```json
{
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"},
    {"key": "severity", "value": [1], "method": "eq"},
    {"key": "status", "value": ["ABNORMAL"], "method": "eq"}
  ]
}
```

`issue_id` 条件由前端自动注入，用户无感知。

### 6.4 维度字段名映射

`aggregate_config.aggregate_dimensions` 现已从 `string[]` 变更为 `object[]`，每个元素包含 `field` 和 `display_name`。`field` 用于构建 `top_n` 接口的 `fields` 参数，`display_name` 直接用于前端展示维度中文名称。

#### 前端使用方式

1. **维度展示名称**：直接使用 `aggregate_dimensions[].display_name`，无需前端维护映射表
2. **构建 top_n 请求**：从 `aggregate_dimensions[].field` 提取字段名，再根据内置字段白名单判断是否加 `tags.` 前缀

#### 判断规则

告警系统中有一批**内置字段**，它们在 ES 中有独立的存储位置（如顶层字段 `severity`、`status`，或 `event.*` 下的字段 `event.ip`、`event.bk_cloud_id` 等）。这些字段在 `top_n` 接口中**直接使用原始名称**即可，后端会自动映射到正确的 ES 字段。

其余不在内置字段列表中的维度，都是策略配置的**自定义聚合维度**，存储在 `event.tags` 嵌套结构中，必须加 `tags.` 前缀。

#### 内置字段白名单（不需要加 `tags.` 前缀）

前端可硬编码以下白名单集合：

```javascript
// 告警内置字段白名单 —— 这些字段在 top_n 接口中直接使用，不加 tags. 前缀
const ALERT_BUILTIN_FIELDS = new Set([
  'bk_biz_id',                // 业务ID → event.bk_biz_id
  'ip',                        // 目标IP → event.ip
  'ipv6',                      // 目标IPv6 → event.ipv6
  'bk_host_id',               // 主机ID → event.bk_host_id
  'bk_cloud_id',              // 目标云区域ID → event.bk_cloud_id
  'bk_service_instance_id',   // 目标服务实例ID → event.bk_service_instance_id
  'bk_topo_node',             // 目标节点 → event.bk_topo_node
  'target_type',               // 告警目标类型 → event.target_type
  'target',                    // 告警目标 → event.target
  'category',                  // 分类 → event.category
  'data_type',                 // 数据类型 → event.data_type
]);
```

#### 完整示例

假设 `detail` 接口返回的 `aggregate_config.aggregate_dimensions` 为：

```json
[
  {"field": "bk_cloud_id", "display_name": "采集器云区域ID"},
  {"field": "bk_target_ip", "display_name": "目标IP"},
  {"field": "device_name", "display_name": "设备名"}
]
```

| 维度名 | display_name | 是否内置字段 | `top_n` 的 `fields` 参数值 |
|--------|-------------|:----------:|--------------------------|
| `bk_cloud_id` | 采集器云区域ID | ✅ 是 | `bk_cloud_id` |
| `bk_target_ip` | 目标IP | ❌ 否 | `tags.bk_target_ip` |
| `device_name` | 设备名 | ❌ 否 | `tags.device_name` |

最终请求：

```json
{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "fields": ["bk_cloud_id", "tags.bk_target_ip", "tags.device_name"],
  "size": 5
}
```
