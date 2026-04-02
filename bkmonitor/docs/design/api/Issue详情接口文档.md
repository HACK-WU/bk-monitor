# Issue 详情接口文档

> **版本**: v1.0  
> **更新时间**: 2026-03-23

---

## 接口概览

Issue 详情页包含以下接口：**（本文重点对接的是issue/detail接口）**

| 接口名称 | 请求方式 | 接口地址 | 说明 |
|----------|----------|----------|------|
| Issue 详情查询 | POST | `/fta/issue/issue/detail` | 获取 Issue 完整信息（含趋势统计） |
| Issue 告警查询 | POST | `/fta/issue/alert/search` | 参考告警搜索，通过 alert_ids 过滤 |
| Issue 活动日志 | POST | `/fta/issue/issue/activity` | 获取 Issue 活动记录 |
| Issue 历史 | POST | `/fta/issue/issue/history` | 获取同策略的历史 Issue |

---

## 1. Issue 详情查询

### 接口信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Issue 详情查询 |
| **请求方式** | POST |
| **接口地址** | `/fta/issue/issue/detail` |
| **内容类型** | application/json |

### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `id` | `string` | 是 | — | Issue ID |
| `bk_biz_id` | `int` | 是 | — | 业务 ID（用于权限校验） |
| `start_time` | `int` | 否 | `first_alert_time` | 趋势图开始时间（秒级时间戳） |
| `end_time` | `int` | 否 | `last_alert_time` 或当前时间 | 趋势图结束时间（秒级时间戳） |

### 请求示例

```json
POST /fta/issue/issue/detail

{
  "id": "1741420800a3b7c9d2",
  "bk_biz_id": 2
}
```

### 响应结构

```json
{
  "result": true,
  "code": 200,
  "message": "OK",
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
    "alert_count": 86,
    "alert_ids": ["alert_id_1", "alert_id_2", "alert_id_3"],
    "latest_alert_id": "alert_id_1",
    "earliest_alert_id": "alert_id_86",
    "first_alert_time": 1741420790,
    "last_alert_time": 1741507200,
    "create_time": 1741420800,
    "update_time": 1741510000,
    "resolved_time": null,
    "is_resolved": false,
    "duration": "1d 1h",
    "impact_scope": {...},
    "aggregate_config": {...},
    "dimension_summary": [...],
    "trend": [...]
  }
}
```

### 响应字段说明

#### 基本信息字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `string` | Issue 唯一标识 |
| `name` | `string` | Issue 名称（策略名称） |
| `anomaly_message` | `string` | 异常信息描述，用于页面主标题 |
| `status` | `string` | 状态枚举值：`pending_review` / `unresolved` / `resolved` / `archived` |
| `status_display` | `string` | 状态中文名：待审核 / 未解决 / 已解决 / 归档 |
| `is_regression` | `bool` | 是否为回归 Issue。`true` 显示 `[回归]` 标签，`false` 显示 `[新]` 标签 |
| `priority` | `string` | 优先级枚举值：`P0` / `P1` / `P2` |
| `priority_display` | `string` | 优先级中文名：高 / 中 / 低 |
| `assignee` | `string[]` | 负责人用户名列表，空数组表示未指派 |
| `strategy_id` | `string` | 关联策略 ID |
| `strategy_name` | `string` | 策略名称 |
| `bk_biz_id` | `string` | 所属业务 ID |
| `bk_biz_name` | `string` | 业务名称 |
| `labels` | `string[]` | 标签列表 |

#### 告警关联字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `alert_count` | `int` | 关联告警总数 |
| `alert_ids` | `string[]` | 全部关联告警的 ID 列表 |
| `latest_alert_id` | `string` | 最新告警 ID，用于点击跳转到最新告警详情 |
| `earliest_alert_id` | `string` | 最早告警 ID，用于点击跳转到最早告警详情 |

#### 时间字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `first_alert_time` | `int` | 首条关联告警时间（秒级时间戳） |
| `last_alert_time` | `int` | 最近关联告警时间（秒级时间戳） |
| `create_time` | `int` | 创建时间（秒级时间戳） |
| `update_time` | `int` | 最近更新时间（秒级时间戳） |
| `resolved_time` | `int \| null` | 解决时间，仅已解决状态有值 |
| `is_resolved` | `bool` | 是否已解决 |
| `duration` | `string` | 存活时长，人类可读格式（如 `"1d 1h"`、`"30min"`） |

#### impact_scope 影响范围

```json
{
  "cluster": {
    "count": 1,
    "display_name": "集群",
    "instance_list": [
      {"bcs_cluster_id": "BCS-K8s-5234", "display_name": "BCS-K8s-5234"}
    ],
    "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview"
  },
  "pod": {
    "count": 30,
    "display_name": "Pod",
    "instance_list": [
      {"bcs_cluster_id": "BCS-K8s-5234", "pod": "lobby-7534534532323lfse345", "display_name": "BCS-K8s-5234/lobby-7534534532323lfse345"}
    ],
    "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&filter-pod_name={pod}&dashboardId=pod&sceneId=kubernetes&sceneType=detail"
  }
}
```

**维度字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | `int` | 该维度受影响实例总数 |
| `display_name` | `string` | 维度中文名称（如"集群"、"主机"、"Pod"） |
| `instance_list` | `object[]` | 实例列表，最多 50 条，每项含 `display_name` 用于展示 |
| `link_tpl` | `string \| null` | 跳转链接模板，支持占位符替换 |

**支持的维度**：

| 维度 key | display_name | instance_list 元素字段 |
|----------|--------------|------------------------|
| `set` | 集群 | `set_id`, `display_name` |
| `host` | 主机 | `bk_host_id`, `display_name` |
| `service_instances` | 服务实例 | `bk_service_instance_id`, `display_name` |
| `cluster` | bcs集群 | `bcs_cluster_id`, `display_name` |
| `node` | node | `bcs_cluster_id`, `node`, `display_name` |
| `service` | service | `bcs_cluster_id`, `service`, `display_name` |
| `pod` | pod | `bcs_cluster_id`, `pod`, `display_name` |
| `app` | app | `app_name`, `bk_biz_id`, `display_name` |
| `apm_service` | apm_service | `app_name`, `service_name`, `bk_biz_id`, `display_name` |

#### aggregate_config 聚合配置

```json
{
  "aggregate_dimensions": ["bk_target_ip"],
  "conditions": [],
  "alert_levels": [1, 2]
}
```

#### dimension_summary 维度统计

维度统计模块用于展示告警在各维度上的分布情况，帮助用户快速了解问题影响范围。数据来源于告警的 `dimensions` 字段聚合统计。

```json
{
  "dimension_summary": [
    {
      "dimension_key": "bk_target_ip",
      "dimension_name": "主机IP",
      "total_count": 86,
      "items": [
        {"value": "10.0.0.1", "count": 30, "percentage": 34.88},
        {"value": "10.0.0.2", "count": 20, "percentage": 23.26},
        {"value": "10.0.0.3", "count": 15, "percentage": 17.44},
        {"value": "10.0.0.4", "count": 12, "percentage": 13.95},
        {"value": "10.0.0.5", "count": 8, "percentage": 9.30},
        {"value": "其他", "count": 1, "percentage": 1.16}
      ]
    }
  ]
}
```

**dimension_summary 数组元素字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `dimension_key` | `string` | 维度字段名，对应 alert.dimensions 中的 key |
| `dimension_name` | `string` | 维度显示名称（中文），来源于告警 dimensions 的 display_key |
| `total_count` | `int` | 该维度在所有告警中出现的总次数 |
| `items` | `object[]` | 维度值分布列表（Top5 + 其他） |

**items 数组元素字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `value` | `string` | 维度值，前端直接使用该字段展示；聚合剩余项时值为翻译后的 `"其他"` |
| `count` | `int` | 该值出现次数 |
| `percentage` | `float` | 占比百分比（保留2位小数） |

**前端渲染说明**：
- 每个维度渲染为一组进度条，按 `percentage` 显示占比
- 最多展示 Top5 + 其他
- `value` 直接作为展示文本

#### trend 趋势统计

> **注意**：此接口返回的 trend 格式与设计文档中的格式不一致，是**故意设计**的。前端请按此接口返回的数组格式渲染，设计文档中的格式仅供参考。

趋势图数据，按状态分组统计：

```json
{
  "trend": [
    {
      "data": [
        [1773619200000, 1],
        [1773705600000, 1],
        [1773792000000, 1]
      ],
      "display_name": "未恢复",
      "name": "ABNORMAL"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0]
      ],
      "display_name": "已恢复",
      "name": "RECOVERED"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0]
      ],
      "display_name": "已失效",
      "name": "CLOSED"
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | `[int, int][]` | 时间序列数据，格式为 `[[毫秒时间戳, 数量], ...]` |
| `display_name` | `string` | 状态中文名：未恢复 / 已恢复 / 已失效 |
| `name` | `string` | 状态枚举值：`ABNORMAL` / `RECOVERED` / `CLOSED` |

**前端渲染说明**：
- 使用堆叠柱状图展示
- 红色：未恢复 (ABNORMAL)
- 绿色：已恢复 (RECOVERED)
- 黄色：已失效 (CLOSED)

---

## 2. Issue 告警查询

### 接口信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Issue 告警查询 |
| **请求方式** | POST |
| **接口地址** | `/fta/issue/alert/search` |
| **内容类型** | application/json |

### 功能说明

查询指定 Issue 关联的告警数据，用于 Issue 详情页中**检索栏搜索、翻页、排序**等交互场景的局部刷新。

返回内容包括：告警 ID 列表（分页）、告警趋势图、维度统计、最新/最早告警 ID。

> **与 detail 接口的关系**：`detail` 接口返回 Issue 完整信息（含元数据 + 动态数据），本接口仅返回动态数据部分，用于用户操作检索栏后的局部刷新，无需重新加载整个详情页。

### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `bk_biz_id` | `int` | 是 | — | 业务 ID |
| `issue_id` | `string` | 是 | — | Issue ID |
| `start_time` | `int` | 是 | — | 开始时间（秒级时间戳） |
| `end_time` | `int` | 是 | — | 结束时间（秒级时间戳） |
| `conditions` | `object[]` | 否 | `[]` | 搜索条件，格式同告警中心搜索栏，详见下方说明 |
| `query_string` | `string` | 否 | `""` | 查询字符串（支持 Lucene 语法） |
| `page` | `int` | 否 | `1` | 页码，从 1 开始 |
| `page_size` | `int` | 否 | `100` | 每页数量，范围 1~1000 |
| `ordering` | `string[]` | 否 | `[]` | 排序字段列表，前缀 `-` 表示降序。为空时使用默认排序 |

#### conditions 格式说明

`conditions` 数组中每个元素的结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | `string` | 过滤字段名，如 `severity`、`status`、`assignee` 等 |
| `value` | `any[]` | 过滤值列表 |
| `method` | `string` | 匹配方式：`eq`（等于）、`neq`（不等于）、`include`（包含）、`exclude`（不包含） |

#### ordering 排序说明

- 字段名前加 `-` 表示降序，不加前缀表示升序
- 支持的排序字段：`status`、`severity`、`create_time`、`seq_id` 等
- 为空时使用默认排序：`["status", "-create_time", "-seq_id"]`

### 请求示例

#### 基础查询（首次加载）

```json
POST /fta/issue/alert/search
{
  "bk_biz_id": 2,
  "issue_id": "1741420800a3b7c9d2",
  "start_time": 1741334400,
  "end_time": 1741420800,
  "conditions": [],
  "query_string": "",
  "page": 1,
  "page_size": 100,
  "ordering": []
}
```

#### 带条件过滤 + 自定义排序

```json
POST /fta/issue/alert/search
{
  "bk_biz_id": 2,
  "issue_id": "1741420800a3b7c9d2",
  "start_time": 1741334400,
  "end_time": 1741420800,
  "conditions": [
    {"key": "severity", "value": [1], "method": "eq"}
  ],
  "query_string": "",
  "page": 1,
  "page_size": 100,
  "ordering": ["-severity", "-create_time"]
}
```

#### 翻页查询

```json
POST /fta/issue/alert/search
{
  "bk_biz_id": 2,
  "issue_id": "1741420800a3b7c9d2",
  "start_time": 1741334400,
  "end_time": 1741420800,
  "conditions": [],
  "query_string": "",
  "page": 2,
  "page_size": 100,
  "ordering": []
}
```

### 响应结构

```json
{
  "result": true,
  "code": 200,
  "message": "OK",
  "data": {
    "issue_id": "1741420800a3b7c9d2",
    "latest_alert_id": "17414208001234abcd",
    "earliest_alert_id": "17413344005678efgh",
    "alert_ids": [
      "17414208001234abcd",
      "17414100009876dcba",
      "17413344005678efgh"
    ],
    "total": 86,
    "alert_count": 86,
    "trend": [
      {
        "data": [[1773619200000, 1], [1773705600000, 3]],
        "display_name": "未恢复",
        "name": "ABNORMAL"
      },
      {
        "data": [[1773619200000, 0], [1773705600000, 1]],
        "display_name": "已恢复",
        "name": "RECOVERED"
      },
      {
        "data": [[1773619200000, 0], [1773705600000, 0]],
        "display_name": "已失效",
        "name": "CLOSED"
      }
    ],
    "dimension_summary": [
      {
        "dimension_key": "bk_target_ip",
        "dimension_name": "主机IP",
        "total_count": 86,
        "items": [
          {"value": "10.0.0.1", "count": 30, "percentage": 34.88},
          {"value": "10.0.0.2", "count": 20, "percentage": 23.26},
          {"value": "10.0.0.3", "count": 15, "percentage": 17.44},
          {"value": "10.0.0.4", "count": 12, "percentage": 13.95},
          {"value": "10.0.0.5", "count": 8, "percentage": 9.30},
          {"value": "其他", "count": 1, "percentage": 1.16}
        ]
      }
    ]
  }
}
```

### 响应字段说明

#### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `issue_id` | `string` | 当前查询的 Issue ID（与请求参数一致） |
| `latest_alert_id` | `string` | 最新告警 ID（按时间倒序第一条），用于"最新告警"跳转 |
| `earliest_alert_id` | `string` | 最早告警 ID（按时间正序第一条），用于"最早告警"跳转 |
| `alert_ids` | `string[]` | 当前页的告警 ID 列表，按排序规则排列 |
| `total` | `int` | 符合条件的告警总数（用于分页计算） |
| `alert_count` | `int` | 告警总数，与 `total` 一致（对齐 detail 接口字段命名） |
| `trend` | `object[]` | 告警趋势图数据，格式同 detail 接口 |
| `dimension_summary` | `object[]` | 维度统计数据，格式同 detail 接口 |

#### trend 趋势图

格式与 detail 接口完全一致，参见 [trend 趋势统计](#trend-趋势统计)。

**前端渲染说明**：
- 使用堆叠柱状图展示
- 红色：未恢复 (ABNORMAL)
- 绿色：已恢复 (RECOVERED)
- 黄色：已失效 (CLOSED)

#### dimension_summary 维度统计

格式与 detail 接口完全一致，参见 [dimension_summary 维度统计](#dimension_summary-维度统计)。

**前端渲染说明**：
- 每个维度渲染为一组进度条，按 `percentage` 显示占比
- 最多展示 Top5 + 其他
- `value` 直接作为展示文本

### 前端使用场景

| 场景 | 操作 | 参数变化 |
|------|------|----------|
| **首次加载** | 详情页打开后，使用 detail 接口返回的数据即可，无需调用本接口 | — |
| **检索栏搜索** | 用户输入搜索条件后点击搜索 | `conditions` / `query_string` 变化，`page` 重置为 1 |
| **切换时间范围** | 用户修改时间选择器 | `start_time` / `end_time` 变化，`page` 重置为 1 |
| **翻页** | 用户点击下一页 | `page` 变化，其他参数不变 |
| **排序** | 用户点击列表表头排序 | `ordering` 变化，`page` 重置为 1 |

> **注意**：`issue_id` 由前端从 detail 接口获取后传入，无需用户手动输入。检索栏的 UI 交互复用告警中心组件，`issue_id` 的过滤由后端自动处理，前端无需在 `conditions` 中手动添加 `issue_id` 条件。

---

## 3. Issue 活动日志

**接口地址**：`POST /fta/issue/issue/activity`

获取 Issue 的操作活动记录，包括评论、状态变更、负责人变更等。

---

## 4. Issue 历史

**接口地址**：`POST /fta/issue/issue/history`

获取同策略下的历史 Issue 列表，帮助用户了解该策略的历史告警情况。

---

## 页面加载策略

详情页采用分层加载策略：

### 第一阶段（页面骨架）

**并行请求**：

| 接口 | 说明 |
|------|------|
| `POST /fta/issue/issue/detail` | 页面头部、基本信息、趋势统计、告警ID列表 |
| `POST /fta/issue/issue/activity` | 问题活动记录 |

### 第二阶段

用户交互触发：

| 触发场景 | 调用接口 |
|----------|----------|
| 使用检索栏搜索告警 | `POST /fta/issue/alert/search` |
| 手动点击历史 Issue 区域 | `POST /fta/issue/issue/history` |

---

## 设计稿字段映射

### 页面头部

| 设计稿元素 | 对应字段 | 说明 |
|-----------|----------|------|
| 主标题 | `anomaly_message` | 如 `NulpointerException` |
| 副标题 | `name` | 如 `异常登录日志告警` |
| 回归/新标签 | `is_regression` | `true` 显示 `[回归]`，`false` 显示 `[新]` |

### 基本信息模块

| 设计稿元素 | 对应字段 | 可编辑 |
|-----------|----------|:------:|
| 优先级 | `priority` / `priority_display` | ✅ |
| 负责人 | `assignee` | ✅ |
| 影响范围 | `impact_scope` | ❌ |
| 最后出现时间 | `last_alert_time` | ❌ |
| 最早发生时间 | `first_alert_time` | ❌ |
| 标记为已解决按钮 | 调用 `ResolveIssueResource` | — |

### 趋势图模块

| 设计稿元素 | 对应字段 | 说明 |
|-----------|----------|------|
| 告警事件数量 | `alert_count` | 关联告警总数 |
| 堆叠柱状图 | `trend` | 三条时间序列 |
| 维度统计 | `dimension_summary` | 维度分布图，Top5 + 其他 |

### 告警列表模块

| 设计稿元素 | 数据来源                          | 说明                |
|-----------|-------------------------------|-------------------|
| 最新告警 | `/fta/alert/v2/alert/detail/` | 点击跳转告警详情,传递告警ID参数 |
| 最早告警 | `/fta/alert/v2/alert/detail/` | 点击跳转告警详情，传递告警ID参数 |
| 告警列表 | `/fta/alert/v2/alert/search/` | 点击搜索告警列表，传递告警ID参数 |

