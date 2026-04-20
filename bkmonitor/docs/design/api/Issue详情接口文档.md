# Issue 详情接口文档

> **版本**: v2.1  
> **更新时间**: 2026-04-03  
> **变更说明**: `issue/detail` 接口不再返回告警动态数据（`alert_count`、`trend`、`dimension_summary`、`alert_ids` 等），改由前端调用告警中心现有接口获取。`/fta/issue/alert/search` 接口已废弃。

---

## 接口概览

Issue 详情页包含以下接口：**（本文重点对接的是 issue/detail 接口）**

| 接口名称 | 请求方式 | 接口地址 | 说明 |
|----------|----------|----------|------|
| Issue 详情查询 | POST | `/fta/issue/issue/detail` | 获取 Issue 元数据（**不再返回告警动态数据**） |
| 告警趋势图 | POST | `/fta/alert/v2/alert/date_histogram/` | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| 维度统计 | POST | `/fta/alert/v2/alert/top_n/` | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| 告警搜索 | POST | `/fta/alert/v2/alert/search/` | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| Issue 活动日志 | POST | `/fta/issue/issue/activity` | 获取 Issue 活动记录 |
| Issue 历史 | POST | `/fta/issue/issue/history` | 获取同策略的历史 Issue |

### 废弃接口

| 接口名称 | 请求方式 | 接口地址 | 说明 |
|----------|----------|----------|------|
| ~~Issue 告警查询~~ | ~~POST~~ | ~~`/fta/issue/alert/search`~~ | **已废弃**，功能由告警中心现有接口替代 |

> **详细调用流程**：参见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md)

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
    "first_alert_time": 1741420790,
    "last_alert_time": 1741507200,
    "create_time": 1741420800,
    "update_time": 1741510000,
    "resolved_time": null,
    "is_resolved": false,
    "duration": "1d 1h",
    "impact_scope": {...},
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
  "aggregate_dimensions": [
    {"field": "bk_target_ip", "display_name": "目标IP"},
    {"field": "bk_cloud_id", "display_name": "采集器云区域ID"}
  ],
  "conditions": [],
  "alert_levels": [1, 2]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `aggregate_dimensions` | `object[]` | 聚合维度列表，每项含 `field`（字段名）和 `display_name`（维度展示名称），用于 `alert/top_n` 接口的 `fields` 参数和维度统计展示 |
| `aggregate_dimensions[].field` | `string` | 维度字段名（已去除 `tags.` 前缀），用于构建 `top_n` 接口的 `fields` 参数 |
| `aggregate_dimensions[].display_name` | `string` | 维度中文展示名称，用于前端维度统计模块的标题展示 |
| `conditions` | `object[]` | 聚合条件 |
| `alert_levels` | `int[]` | 告警级别列表 |

> **前端使用说明**：
> - 维度统计模块的展示名称直接使用 `display_name` 字段，无需前端维护映射表
> - 构建 `top_n` 接口的 `fields` 参数时，需根据 `field` 判断是否加 `tags.` 前缀（内置字段不加前缀，自定义字段加 `tags.` 前缀），详见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md) 第 6.4 节

---

## 2. 告警趋势图（复用告警中心接口）

> **接口地址**：`POST /fta/alert/v2/alert/date_histogram/`
>
> **调用方式**：通过 `conditions` 传入 `issue_id` 过滤条件。
>
> **详细说明**：参见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md) 第 4.2 节。

### 请求示例

```json
POST /fta/alert/v2/alert/date_histogram/

{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "interval": "auto"
}
```

---

## 3. 维度统计（复用告警中心接口）

> **接口地址**：`POST /fta/alert/v2/alert/top_n/`
>
> **调用方式**：
> 1. 从 detail 接口获取 `aggregate_config.aggregate_dimensions`（每项含 `field` 和 `display_name`）
> 2. 使用 `display_name` 作为维度展示名称
> 3. 提取 `field`，转换维度字段名（内置字段不加前缀，自定义字段加 `tags.` 前缀）构建 `top_n` 的 `fields` 参数
> 4. 通过 `conditions` 传入 `issue_id` 过滤条件
>
> **详细说明**：参见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md) 第 4.3 节。

### 请求示例

```json
POST /fta/alert/v2/alert/top_n/

{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "fields": ["tags.bk_target_ip", "bk_cloud_id"],
  "size": 5
}
```

---

## 4. 告警搜索（复用告警中心接口）

> **接口地址**：`POST /fta/alert/v2/alert/search/`
>
> **调用方式**：通过 `conditions` 传入 `issue_id` 过滤条件。
>
> **详细说明**：参见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md) 第 4.4 节。

### 使用场景

| 场景 | ordering | page_size | 说明 |
|------|----------|-----------|------|
| 最新告警 | `["-create_time"]` | 1 | 获取最新告警 ID |
| 最早告警 | `["create_time"]` | 1 | 获取最早告警 ID |
| 告警列表 | `[]` | 100 | 用户点击告警列表 Tab 时加载 |

### 请求示例（最新告警）

```json
POST /fta/alert/v2/alert/search/

{
  "bk_biz_ids": [2],
  "conditions": [
    {"key": "issue_id", "value": ["1741420800a3b7c9d2"], "method": "eq"}
  ],
  "start_time": 1741420790,
  "end_time": 1741507200,
  "ordering": ["-create_time"],
  "page": 1,
  "page_size": 1
}
```

---

## 5. Issue 活动日志

**接口地址**：`POST /fta/issue/issue/activity`

获取 Issue 的操作活动记录，包括评论、状态变更、负责人变更等。

---

## 6. Issue 历史

**接口地址**：`POST /fta/issue/issue/history`

获取同策略下的历史 Issue 列表，帮助用户了解该策略的历史告警情况。

---

## 页面加载策略

详情页采用分层加载策略，详见 [Issue详情页接口调用流程.md](./Issue详情页接口调用流程.md)：

### 第一阶段（全部并行，无依赖）

**立即执行**：

| 接口 | 说明 |
|------|------|
| `POST /fta/issue/issue/detail` | Issue 元数据 |
| `POST /fta/issue/issue/activity` | 问题活动记录 |
| `POST /fta/alert/v2/alert/date_histogram/` | 趋势图 |
| `POST /fta/alert/v2/alert/search/`（最新告警） | ordering: `["-create_time"]`, page_size: 1 |
| `POST /fta/alert/v2/alert/search/`（最早告警） | ordering: `["create_time"]`, page_size: 1 |

### 第二阶段（依赖 issue/detail）

**等待 detail 返回后执行**：

| 接口 | 说明 |
|------|------|
| `POST /fta/alert/v2/alert/top_n/` | 维度统计（需要 `aggregate_dimensions`） |

### 第三阶段（用户交互触发）

| 触发场景 | 调用接口 |
|----------|----------|
| 点击告警列表 Tab | `POST /fta/alert/v2/alert/search/`（page_size: 100） |
| 点击历史 Issue 区域 | `POST /fta/issue/issue/history` |

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

| 设计稿元素 | 数据来源 | 说明 |
|-----------|----------|------|
| 告警事件数量 | `alert/search` 的 `total` | 关联告警总数 |
| 堆叠柱状图 | `alert/date_histogram` | 三条时间序列 |

### 维度统计模块

| 设计稿元素 | 数据来源 | 说明 |
|-----------|----------|------|
| 维度展示名称 | `issue/detail` 的 `aggregate_dimensions[].display_name` | 直接使用，无需前端维护映射表 |
| 维度分布进度条 | `alert/top_n` | Top5 + 其他，前端计算百分比 |

### 告警列表模块

| 设计稿元素 | 数据来源 | 说明 |
|-----------|----------|------|
| 最新告警 | `alert/search`（ordering: `"-create_time"`, page_size: 1） | 点击跳转告警详情 |
| 最早告警 | `alert/search`（ordering: `"create_time"`, page_size: 1） | 点击跳转告警详情 |
| 告警列表 | `alert/search`（page_size: 100） | 用户点击告警列表 Tab 时加载 |

---

## 废弃接口说明

### ~~Issue 告警查询~~（已废弃）

> **废弃说明**：`/fta/issue/alert/search` 接口已废弃，功能由告警中心现有接口替代。
>
> **替代方案**：
> - 趋势图 → `POST /fta/alert/v2/alert/date_histogram/`
> - 维度统计 → `POST /fta/alert/v2/alert/top_n/`
> - 告警列表 → `POST /fta/alert/v2/alert/search/`
>
> 所有接口通过 `conditions` 传入 `issue_id` 过滤条件即可复用告警中心现有能力。
