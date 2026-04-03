# Issue 详情接口设计文档

> **关联文档**：[Issues 模块技术设计.md](./Issues%20模块技术设计.md) | [Issue 列表接口设计.md](Issues列表接口设计.md) | [Issue详情页设计稿.md](./mockups/Issue详情页设计稿.md) | [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md)

---

## 1. 接口总览

Issue 详情页按设计稿包含以下模块和对应接口：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        页面头部 (Title)                                  │
│   ← IssueDetailResource                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                        检索栏 (Search)                                  │
│   ← 复用告警中心 alert/search（通过 conditions 传入 issue_id）          │
├───────────────────────────────┬─────────────────────────────────────────┤
│                               │                                         │
│    告警趋势统计 (Trend)       │     基本信息               │
│    ← alert/date_histogram    │     ← IssueDetailResource                │
│    （复用告警中心接口）        │                                         │
│                               │     操作：                               │
│    维度统计 (dimension)       │     ← AssignIssueResource               │
│    ← alert/top_n             │     ← ResolveIssueResource              │
│    （复用告警中心接口）        │     ← UpdateIssuePriorityResource       │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                               │                                         │
│    告警列表 (Alert List)      │     问题活动 (Activity)                  │
│    ← alert/search            │     ← IssueActivityResource             │
│    （复用告警中心接口）        │     ← CommentIssueResource             │
│                               │                                         │
│                               ├─────────────────────────────────────────┤
│                               │                                         │
│                               │     历史 Issue                          │
│                               │     ← IssueHistoryResource             │
│                               │                                         │
└───────────────────────────────┴─────────────────────────────────────────┘
```

> **关键变更**：Issue 详情页的动态数据（趋势图、维度统计、告警列表等）复用告警中心现有接口，通过 `conditions` 传入 `issue_id` 过滤条件。详见 [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md)。

### 1.1 接口清单

| 接口名 | Resource 类名 | HTTP | endpoint | 对应模块 | 说明 |
|--------|---------------|------|----------|----------|------|
| **Issue 详情** | `IssueDetailResource` | POST | `issue/detail` | 基本信息 | 获取 Issue 元数据（状态、优先级、负责人、影响范围等），**不再返回告警动态数据** |
| **告警趋势图** | `AlertDateHistogramResource` | POST | `alert/date_histogram` | 趋势图 | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| **维度统计** | `AlertTopNResource` | POST | `alert/top_n` | 维度统计 | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| **告警搜索** | `AlertSearchResource` | POST | `alert/search` | 告警列表 + 最新/最早告警 | 复用告警中心接口，通过 `conditions` 传入 `issue_id` |
| **Issue 活动日志** | `IssueActivityResource` | POST | `issue/activity` | 问题活动 | 查询 IssueActivityDocument，含 operator_display_name 翻译 |
| **Issue 历史** | `IssueHistoryResource` | POST | `issue/history` | 历史 Issue | 同策略的历史 Issue 列表 |

### 废弃接口

| 接口名 | endpoint | 说明 |
|--------|----------|------|
| ~~Issue 告警查询~~ | ~~`/fta/issue/alert/search`~~ | **已废弃**，功能由告警中心现有接口替代 |

### 1.2 页面加载策略

详情页采用**分层加载**策略，详见 [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md)：

```
第一阶段（全部并行，无依赖）── 立即执行 ──┐
  ├─ POST issue/detail              → Issue 元数据
  ├─ POST issue/activity            → 问题活动记录
  ├─ POST alert/date_histogram      → 趋势图（时间范围来自 Issue 列表页）
  ├─ POST alert/search（最新告警）   → ordering: ["-create_time"], page_size: 1
  └─ POST alert/search（最早告警）   → ordering: ["create_time"], page_size: 1
                                        ──┘

第二阶段（依赖 issue/detail）── 等待 detail 返回后执行 ──┐
  └─ POST alert/top_n               → 维度统计（需要 aggregate_dimensions）
                                        ──┘

第三阶段（用户交互触发）── 按需请求 ──┐
  ├─ POST alert/search（告警列表）   → 用户点击告警列表 Tab 时加载（page_size: 100）
  └─ POST issue/history             → 用户点击历史 Issue 区域
                                  ──┘
```

**设计原则**：
- 第一阶段 5 个接口全部并行，无任何依赖，`issue_id` 和 `start_time`/`end_time` 均来自 Issue 列表页传入的路由参数
- 第二阶段 `alert/top_n` 必须等待 `issue/detail` 返回，因为需要 `aggregate_config.aggregate_dimensions` 作为 `fields` 参数
- 第三阶段告警列表仅在用户点击告警列表 Tab 时触发（`page_size: 100`，无分页）
- 检索栏复用告警搜索能力，前端在 `conditions` 中自动注入 `issue_id` 过滤条件

**关于操作类接口**：操作类接口（assign/resolve/update_priority/comment）属于用户操作触发，不纳入页面加载阶段，按需调用即可。

---

## 2. Issue 详情接口

> 对应设计稿模块：**页面头部** + **基本信息**

### 2.1 实现状态概览

基于 `IssueQueryHandler` 现有实现分析，各字段实现状态如下：

| 字段 | 状态 | 实现来源 | 说明 |
|------|------|----------|------|
| 基本字段（id/name/status/priority/assignee 等） | ✅ 已实现 | `IssueQueryHandler.clean_document` | 完整提取 Issue 基本信息字段 |
| `duration` | ✅ 已实现 | `clean_document` | 根据 create_time/resolved_time 自动计算 |
| `status_display` / `priority_display` | ✅ 已实现 | `clean_document` | 状态/优先级中文翻译 |
| `impact_scope` | ✅ 已实现 | `clean_document` | 已添加 `display_name` 翻译 |
| `aggregate_config` | ✅ 已实现 | `clean_document` | 直接透传聚合配置 |
| `anomaly_message` | ✅ 已实现 | `_fill_anomaly_message` | 查询最新告警的 description |

**以下字段已废弃，不再从 detail 接口返回**（改用告警中心现有接口）：

| 废弃字段 | 替代方案 | 说明 |
|----------|----------|------|
| `alert_count` | `alert/search` 的 `total` 字段 | 关联告警总数 |
| `trend` | `alert/date_histogram` | 三段式趋势图 |
| `dimension_summary` | `alert/top_n` | 维度分布统计 |
| `alert_ids` | `alert/search` | 告警 ID 列表 |
| `latest_alert_id` | `alert/search`（ordering: `"-create_time"`, page_size: 1） | 最新告警 |
| `earliest_alert_id` | `alert/search`（ordering: `"create_time"`, page_size: 1） | 最早告警 |

### 2.2 IssueDetailResource

```python
class IssueDetailResource(Resource):
    """获取单个 Issue 的元数据信息（不包含告警动态数据）"""

    class RequestSerializer(serializers.Serializer):
        id = IssueIDField(label="Issue ID")
        bk_biz_id = serializers.IntegerField(label="业务ID", required=True)

    def perform_request(self, validated_request_data):
        """
        获取 Issue 元数据的处理流程：
        
        1. 查询 Issue 基本信息（复用 IssueQueryHandler.clean_document）
        2. 返回 Issue 元数据，不包含告警动态数据
        
        注意：告警动态数据（趋势图、维度统计、告警列表等）由前端调用告警中心现有接口获取
        """
        issue_id = validated_request_data["id"]
        bk_biz_id = validated_request_data["bk_biz_id"]

        # 1. 查询 Issue 基本信息
        issue = _get_issue_or_raise(issue_id, bk_biz_id=bk_biz_id)
        result = IssueQueryHandler.clean_document(issue)

        # 注意：不再返回以下字段，由前端调用告警中心接口获取
        # - alert_count: 使用 alert/search 的 total 字段
        # - trend: 使用 alert/date_histogram
        # - dimension_summary: 使用 alert/top_n
        # - alert_ids: 使用 alert/search
        # - latest_alert_id: 使用 alert/search（ordering: "-create_time", page_size: 1）
        # - earliest_alert_id: 使用 alert/search（ordering: "create_time", page_size: 1）

        return result
```

### 2.3 请求参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | Issue ID |
| `bk_biz_id` | `int` | 是 | 业务 ID（用于权限校验） |

### 2.4 返回值结构

```json
{
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
  },
  "aggregate_config": {
    "aggregate_dimensions": ["bk_target_ip", "bk_cloud_id"],
    "conditions": [],
    "alert_levels": [1, 2]
  }
}
```

> **注意**：以下字段已废弃，不再从此接口返回：
> - `alert_count` → 使用 `alert/search` 的 `total` 字段
> - `alert_ids` → 使用 `alert/search`
> - `latest_alert_id` → 使用 `alert/search`（`ordering: ["-create_time"]`, `page_size: 1`）
> - `earliest_alert_id` → 使用 `alert/search`（`ordering: ["create_time"]`, `page_size: 1`）
> - `dimension_summary` → 使用 `alert/top_n`
> - `trend` → 使用 `alert/date_histogram`

### 2.5 设计稿模块对应关系

| 设计稿字段 | 接口字段 | 说明 |
|-----------|---------|------|
| 标题（主） | `anomaly_message` | 如 `NulpointerException` |
| 标题（副） | `name` | 如 `异常登录日志告警`，使用策略名称 |
| 回归/新标签 | `is_regression` | `true` 显示 `[回归]` 标签，`false` 显示 `[新]` 标签 |
| 优先级 | `priority` / `priority_display` | 可编辑，下拉选择 |
| 负责人 | `assignee` | 可编辑，人员选择器 |
| 影响范围 | `impact_scope` | 只读，详情见下方说明 |
| 最后出现时间 | `last_alert_time` | 相对时间显示（如 `15s ago`） |
| 最早发生时间 | `first_alert_time` | 相对时间显示（如 `8months ago`） |
| 标记为已解决 | 调用 `ResolveIssueResource` | 按钮操作，非本接口返回字段 |

**以下字段由前端调用告警中心接口获取**：

| 设计稿字段 | 数据来源 | 说明 |
|-----------|---------|------|
| 堆叠柱状图 | `alert/date_histogram` | 3 条时间序列（ABNORMAL / RECOVERED / CLOSED） |
| 告警事件数量 | `alert/search` 的 `total` | 关联告警总数 |
| 维度统计 | `alert/top_n` | 维度分布图，Top5 + 其他 |
| 最新告警ID | `alert/search`（`ordering: ["-create_time"]`, `page_size: 1`） | 用于点击跳转到最新告警详情 |
| 最早告警ID | `alert/search`（`ordering: ["create_time"]`, `page_size: 1`） | 用于点击跳转到最早告警详情 |
| 告警列表 | `alert/search`（`page_size: 100`） | 用户点击告警列表 Tab 时加载 |

### 2.6 impact_scope 说明

设计稿中的**影响范围**模块用于展示 Issue 影响的具体实例列表。

**数据来源**：`IssueDocument.impact_scope` 字段。

> **重要澄清**：该字段在 Issue 创建时由聚合处理器 `IssueAggregationProcessor._build_impact_scope()` 方法从告警中提取并写入，存储在 Issue 文档中，**无需实时查询告警**。

**数据结构**：

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

**实现说明**：

`IssueQueryHandler.clean_document` 方法会调用 `add_dimension_display_name()` 为每个维度补充 `display_name` 字段（若缺失）：

```python
# bkmonitor/packages/fta_web/issue/handlers/issue.py

def add_dimension_display_name(impact_scope: dict) -> dict:
    """为 impact_scope 中每个维度添加 display_name 字段"""
    for dimension_key, dimension_data in impact_scope.items():
        if isinstance(dimension_data, dict):
            dimension_data["display_name"] = ImpactScopeDimension.get_display_name(dimension_key)
    return impact_scope
```

> **说明**：每个维度对象包含 `display_name` 字段，用于前端显示维度名称。

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

**前端渲染逻辑**：
- 根据 `impact_scope` 中的维度动态渲染进度条
- `count` 用于计算占比，`instance_list` 用于 Tooltip 显示
- `link_tpl` 用于点击跳转

### 2.7 trend 趋势统计说明（已废弃）

> **废弃说明**：`trend` 字段已从 detail 接口移除，前端应调用 `POST /fta/alert/v2/alert/date_histogram/` 接口获取趋势数据。
>
> 调用方式：通过 `conditions` 传入 `issue_id` 过滤条件。
>
> 详见 [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md) 第 4.2 节。

### 2.8 dimension_summary 维度统计说明（已废弃）

> **废弃说明**：`dimension_summary` 字段已从 detail 接口移除，前端应调用 `POST /fta/alert/v2/alert/top_n/` 接口获取维度统计数据。
>
> 调用方式：
> 1. 从 detail 接口响应中获取 `aggregate_config.aggregate_dimensions`
> 2. 转换维度字段名（内置字段不加前缀，自定义字段加 `tags.` 前缀）
> 3. 通过 `conditions` 传入 `issue_id` 过滤条件，`fields` 传入维度列表
>
> 详见 [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md) 第 4.3 节和 6.4 节。

### 2.9 alert_ids 告警ID列表说明（已废弃）

> **废弃说明**：`alert_ids`、`latest_alert_id`、`earliest_alert_id` 字段已从 detail 接口移除，前端应调用 `POST /fta/alert/v2/alert/search/` 接口获取。
>
> 获取方式：
> - **最新告警**：`ordering: ["-create_time"]`, `page_size: 1`
> - **最早告警**：`ordering: ["create_time"]`, `page_size: 1`
> - **告警列表**：`page_size: 100`（用户点击告警列表 Tab 时加载）
>
> 详见 [Issue详情页接口调用流程.md](../api/Issue详情页接口调用流程.md) 第 4.4 节。

### 2.10 合并查询实现方案（已废弃）

> **废弃说明**：此实现方案已废弃，不再需要。前端应直接调用告警中心现有接口获取动态数据。

---

## 3. 路由注册

```python
# fta_web/issue/views.py

class IssueViewSet(ResourceViewSet):
    resource_routes = [
        # 查询类
        ResourceRoute("POST", IssueDetailResource, endpoint="detail"),
        ResourceRoute("POST", IssueActivityResource, endpoint="activity"),
        ResourceRoute("POST", IssueHistoryResource, endpoint="history"),
    ]
```

> **注意**：`IssueSearchAlertResource` 已废弃移除，告警查询功能由告警中心现有接口替代。
