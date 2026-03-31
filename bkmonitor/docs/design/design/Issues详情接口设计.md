# Issue 详情接口设计文档

> **关联文档**：[Issues 模块技术设计.md](./Issues%20模块技术设计.md) | [Issue 列表接口设计.md](Issues列表接口设计.md) | [Issue详情页设计稿.md](./mockups/Issue详情页设计稿.md)

---

## 1. 接口总览

Issue 详情页按设计稿包含以下模块和对应接口：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        页面头部 (Title)                                  │
│   ← IssueDetailResource                                                │
├─────────────────────────────────────────────────────────────────────────┤
│                        检索栏 (Search)                                  │
│   ← IssueSearchAlertResource（复用告警搜索，限定 issue_id）              │
├───────────────────────────────┬─────────────────────────────────────────┤
│                               │                                         │
│    告警趋势统计 (Trend)       │     基本信息               │
│    ← IssueDetailResource     │     ← IssueDetailResource                │
│                               │                                         │
│    维度统计 (dimension_summary)      │     操作：                               │
│    ← IssueDetailResource       │     ← AssignIssueResource               │
│                               │     ← ResolveIssueResource              │
│    告警ID列表                 │     ← UpdateIssuePriorityResource       │
│    ← alert_ids 字段          │                                         │
│                               │                                         │
├───────────────────────────────┼─────────────────────────────────────────┤
│                               │                                         │
│    告警列表 (Alert List)      │     问题活动 (Activity)                  │
│    ← IssueSearchAlertRes.    │     ← IssueActivityResource             │
│    (检索栏搜索)               │     ← CommentIssueResource             │
│                               │                                         │
│                               ├─────────────────────────────────────────┤
│                               │                                         │
│                               │     历史 Issue                          │
│                               │     ← IssueHistoryResource             │
│                               │                                         │
└───────────────────────────────┴─────────────────────────────────────────┘
```

### 1.1 接口清单

| 接口名 | Resource 类名             | HTTP | endpoint | 对应模块  | 说明                          |
|--------|-------------------------|------|----------|-------|-----------------------------|
| **Issue 详情** | `IssueDetailResource`   | GET | `issue/detail` | 基本信息 + 趋势 | 获取 Issue 完整信息，含告警趋势统计       |
| **Issue 告警查询** | `IssueSearchAlertResource` | POST | `alert/search` | 检索栏   | 复用 AlertQueryHandler 搜索能力，自动注入 issue_id 过滤条件 |
| **Issue 活动日志** | `IssueActivityResource` | POST | `issue/activity` | 问题活动  | 查询 IssueActivityDocument，含 operator_display_name 翻译 |
| **Issue 历史** | `IssueHistoryResource`  | POST | `issue/history` | 历史 Issue | 同策略的历史 Issue 列表             |

### 1.2 页面加载策略

详情页采用**分层加载**策略：

```
第一阶段（页面骨架）── 并行请求 ──┐
  ├─ GET  issue/detail              → 头部 + 基本信息 + 趋势图 + 告警ID列表
  └─ POST issue/activity            → 问题活动记录
                                  ──┘

第二阶段（用户交互触发）── 按需请求 ──┐
  ├─ POST alert/search         → 用户使用检索栏搜索告警（参考告警搜索）
  └─ POST issue/history             → 用户手动点击历史 Issue 区域
                                  ──┘
```

**设计原则**：
- 第一阶段接口数量控制在 **2 个**，保证首屏加载速度
- 第二阶段接口采用**懒加载**，用户滚动到对应区域或使用检索栏时才触发
- 检索栏复用告警搜索能力，通过 `IssueSearchAlertResource` 自动注入 `issue_id` 过滤条件

**关于操作类接口**：操作类接口（assign/resolve/update_priority/comment）属于用户操作触发，不纳入页面加载阶段，按需调用即可。

**关于告警详情**：点击最新/最早告警时，前端自主调用告警详情接口（已实现），无需后端额外支持。

---

## 2. Issue 详情接口

> 对应设计稿模块：**页面头部** + **基本信息** + **告警趋势统计**

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
| `alert_count` | ✅ 已实现 | `_fill_anomaly_message` | 同时在查询中统计 |
| `trend`（三段式） | ⚠️ 需调整 | 复用 `AlertQueryHandler.date_histogram` | 当前列表接口只返回 ABNORMAL 状态 |
| `dimension_summary` | ❌ 需新增 | 从 `AlertDocument.dimensions` 聚合 | 需实现维度分布统计 |
| `alert_ids` | ❌ 需新增 | 从 `AlertDocument` 批量查询 | 需实现告警 ID 列表查询 |
| `latest_alert_id` | ❌ 需新增 | 从 alert_ids 中提取 | 按时间排序后的最新/最早告警 |
| `earliest_alert_id` | ❌ 需新增 | 从 alert_ids 中提取 | 按时间排序后的最新/最早告警 |

### 2.2 IssueDetailResource

```python
class IssueDetailResource(Resource):
    """获取单个 Issue 的完整信息，包含告警趋势统计"""

    class RequestSerializer(serializers.Serializer):
        id = IssueIDField(label="Issue ID")
        bk_biz_id = serializers.IntegerField(label="业务ID", required=True)
        start_time = serializers.IntegerField(label="开始时间", required=False)
        end_time = serializers.IntegerField(label="结束时间", required=False)

    def perform_request(self, validated_request_data):
        """
        获取 Issue 详情的完整处理流程：
        
        1. 查询 Issue 基本信息（复用 IssueQueryHandler.clean_document）
        2. 确定时间范围（start_time/end_time 或 first_alert_time/last_alert_time）
        3. 并行查询扩展信息：
           - trend: 复用 IssueAlertDateHistogramResultResource（≤7天直接请求，>7天时间分片）
           - dimension_summary + alert_ids: 同一次查询获取维度分布和告警ID列表
        4. 合并结果返回
        """
        issue_id = validated_request_data["id"]
        bk_biz_id = validated_request_data["bk_biz_id"]
        start_time = validated_request_data.get("start_time")
        end_time = validated_request_data.get("end_time")

        # 1. 查询 Issue 基本信息
        issue = _get_issue_or_raise(issue_id, bk_biz_id=bk_biz_id)
        result = IssueQueryHandler.clean_document(issue)

        # 2. 确定时间范围
        first_alert_time = result.get("first_alert_time")
        last_alert_time = result.get("last_alert_time")
        start_time = start_time or first_alert_time
        end_time = end_time or last_alert_time or int(time.time())

        # 3. 并行查询扩展信息（后台线程）
        fill_result = {}
        fill_thread = threading.Thread(
            target=self._build_dimension_and_alert_ids,
            args=(issue_id, start_time, end_time, fill_result),
        )
        fill_thread.start()

        # 4. 查询趋势图（≤7天直接请求，>7天时间分片）
        result["trend"] = self._build_trend(issue_id, start_time, end_time)

        # 5. 等待后台线程完成
        fill_thread.join()

        # 6. 合并维度统计和告警ID信息
        result["dimension_summary"] = fill_result.get("dimension_summary", [])
        result["alert_ids"] = fill_result.get("alert_ids", [])
        result["latest_alert_id"] = fill_result.get("latest_alert_id")
        result["earliest_alert_id"] = fill_result.get("earliest_alert_id")

        # 7. 补充 alert_count（若 anomaly_message 查询未返回）
        if not result.get("alert_count"):
            result["alert_count"] = len(result.get("alert_ids", []))

        return result
```

### 2.3 请求参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `str` | 是 | Issue ID |
| `bk_biz_id` | `int` | 是 | 业务 ID（用于权限校验） |
| `start_time` | `int` | 否 | 趋势图开始时间，默认为 `first_alert_time` |
| `end_time` | `int` | 否 | 趋势图结束时间，默认为 `last_alert_time` 或当前时间 |

### 2.3 返回值结构

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
  "alert_count": 86,
  "alert_ids": ["alert_id_1", "alert_id_2", "alert_id_3", ...],
  "latest_alert_id": "alert_id_1",
  "earliest_alert_id": "alert_id_86",
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
    "aggregate_dimensions": ["bk_target_ip"],
    "conditions": [],
    "alert_levels": [1, 2]
  },
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
  ],
  "trend": [
    {
      "data": [
        [1773619200000, 1],
        [1773705600000, 1],
        [1773792000000, 1],
        [1773878400000, 1],
        [1773964800000, 4],
        [1774051200000, 7],
        [1774137600000, 7],
        [1774224000000, 320]
      ],
      "display_name": "未恢复",
      "name": "ABNORMAL"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0],
        [1773878400000, 0],
        [1773964800000, 0],
        [1774051200000, 0],
        [1774137600000, 0],
        [1774224000000, 0]
      ],
      "display_name": "已恢复",
      "name": "RECOVERED"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0],
        [1773878400000, 0],
        [1773964800000, 0],
        [1774051200000, 0],
        [1774137600000, 0],
        [1774224000000, 0]
      ],
      "display_name": "已失效",
      "name": "CLOSED"
    }
  ]
}
```

### 2.4 设计稿模块对应关系

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
| 堆叠柱状图 | `trend` | 3 条时间序列（ABNORMAL / RECOVERED / CLOSED） |
| 告警事件：86 | `alert_count` | 关联告警总数 |
| 告警ID列表 | `alert_ids` | 全部关联告警的 ID 列表 |
| 最新告警ID | `latest_alert_id` | 用于点击跳转到最新告警详情 |
| 最早告警ID | `earliest_alert_id` | 用于点击跳转到最早告警详情 |
| 维度统计 | `dimension_summary` | 维度分布图，Top5 + 其他，详情见下方说明 |

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

### 2.7 trend 趋势统计说明

趋势图数据复用 `IssueAlertDateHistogramResultResource`，与列表接口 `add_alert_trend` 保持一致。

**实现方案**：

```python
def _build_trend(self, issue_id: str, start_time: int, end_time: int) -> list[dict]:
    """
    构建告警趋势数据
    
    复用 IssueAlertDateHistogramResultResource，返回三段式趋势：
    - ABNORMAL: 未恢复（存量快照）
    - RECOVERED: 已恢复
    - CLOSED: 已失效
    
    参数:
        issue_id: Issue ID
        start_time: 开始时间戳（秒）
        end_time: 结束时间戳（秒）
    
    返回值:
        list[dict]，每个元素包含：
        - name: 状态枚举值（ABNORMAL/RECOVERED/CLOSED）
        - display_name: 状态显示名称（未恢复/已恢复/已失效）
        - data: 时间序列数据 [[毫秒时间戳, 数量], ...]
    """
    from fta_web.issue.resources import IssueAlertDateHistogramResultResource
    
    # 计算聚合间隔
    interval = calculate_agg_interval(start_time, end_time)
    
    # ≤7天直接单次请求，>7天走时间分片并行查询
    SLICED_THRESHOLD = 7 * 24 * 60 * 60  # 7天
    
    if (end_time - start_time) <= SLICED_THRESHOLD:
        result = IssueAlertDateHistogramResultResource().request(
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            conditions=[{"key": "issue_id", "value": [issue_id], "method": "eq"}],
            group_by=["status"],  # 按 status 分组获取三段式趋势
        )
    else:
        result = IssueAlertDateHistogramResultResource.sliced_date_histogram(
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            handler_kwargs={
                "conditions": [{"key": "issue_id", "value": [issue_id], "method": "eq"}],
            },
            group_by=["status"],
        )
    
    # 转换为前端所需格式
    status_display = {
        "ABNORMAL": "未恢复",
        "RECOVERED": "已恢复",
        "CLOSED": "已失效",
    }
    
    trend = []
    # date_histogram 返回格式：{(): {"ABNORMAL": {...}, "RECOVERED": {...}, "CLOSED": {...}}}
    status_series = result.get((), {})
    
    for status in ["ABNORMAL", "RECOVERED", "CLOSED"]:
        ts_map = status_series.get(status, {})
        trend.append({
            "name": status,
            "display_name": status_display.get(status, status),
            "data": sorted([[ts, count] for ts, count in ts_map.items()]),
        })
    
    return trend
```

> **说明**：
> - 复用 `IssueAlertDateHistogramResultResource`，与列表接口保持一致
> - `group_by=["status"]` 返回三段式趋势数据
> - 时间跨度 ≤7 天直接单次请求，>7 天走时间分片并行查询

**返回格式**：

```json
{
  "trend": [
    {
      "data": [
        [1773619200000, 1],
        [1773705600000, 1],
        [1773792000000, 1],
        [1773878400000, 1],
        [1773964800000, 4],
        [1774051200000, 7],
        [1774137600000, 7],
        [1774224000000, 320]
      ],
      "display_name": "未恢复",
      "name": "ABNORMAL"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0],
        [1773878400000, 0],
        [1773964800000, 0],
        [1774051200000, 0],
        [1774137600000, 0],
        [1774224000000, 0]
      ],
      "display_name": "已恢复",
      "name": "RECOVERED"
    },
    {
      "data": [
        [1773619200000, 0],
        [1773705600000, 0],
        [1773792000000, 0],
        [1773878400000, 0],
        [1773964800000, 0],
        [1774051200000, 0],
        [1774137600000, 0],
        [1774224000000, 0]
      ],
      "display_name": "已失效",
      "name": "CLOSED"
    }
  ]
}
```

**字段说明**：
- `data`: 时间序列数据，格式为 `[[毫秒时间戳, 数量], ...]`
- `display_name`: 状态显示名称（中文）：未恢复 / 已恢复 / 已失效
- `name`: 状态枚举值（ABNORMAL / RECOVERED / CLOSED）

### 2.8 dimension_summary 维度统计说明

维度统计模块用于展示告警在各维度上的分布情况，帮助用户快速了解问题影响范围。

**数据来源**：从 `AlertDocument.dimensions` 字段中聚合统计获取。

> **注意**：`impact_scope` 和 `dimension_summary` 是两个不同的概念：
> - `impact_scope`：Issue 影响的具体实例列表（存储在 IssueDocument 中）
> - `dimension_summary`：告警在各维度上的分布统计（实时从 AlertDocument 聚合）

**返回格式**：

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

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `dimension_key` | `str` | 维度字段名，对应 alert.dimensions 中的 key |
| `dimension_name` | `str` | 维度显示名称（中文） |
| `total_count` | `int` | 该维度在所有告警中出现的总次数 |
| `items` | `list` | 维度值分布列表（Top5 + 其他） |

**items 数组元素**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `value` | `str` | 维度值，前端直接使用该字段展示；聚合剩余项时值为翻译后的 `"其他"` |
| `count` | `int` | 该值出现次数 |
| `percentage` | `float` | 占比百分比（保留2位小数） |

### 2.9 alert_ids 告警ID列表说明

告警ID列表用于支持前端跳转到最新/最早告警详情，以及提供告警列表查询的基础数据。

**数据来源**：从 `AlertDocument` 批量查询获取（与 dimension_summary 合并查询）。

**返回字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `alert_ids` | `list[str]` | 全部关联告警的 ID 列表 |
| `latest_alert_id` | `str` \| `None` | 最新告警 ID（按 begin_time 降序） |
| `earliest_alert_id` | `str` \| `None` | 最早告警 ID（按 begin_time 升序） |

### 2.10 合并查询实现方案

`dimension_summary` 和 `alert_ids` 通过同一次 ES 查询获取，在后台线程中执行：

```python
def _build_dimension_and_alert_ids(
    self, issue_id: str, start_time: int, end_time: int, fill_result: dict
) -> None:
    """
    后台线程：一次查询同时获取维度统计和告警ID列表
    
    参数:
        issue_id: Issue ID
        start_time: 开始时间戳（秒）
        end_time: 结束时间戳（秒）
        fill_result: 输出参数，用于存储结果
    
    输出:
        fill_result["dimension_summary"]: 维度统计列表
        fill_result["alert_ids"]: 告警ID列表
        fill_result["latest_alert_id"]: 最新告警ID
        fill_result["earliest_alert_id"]: 最早告警ID
    """
    from collections import defaultdict
    from bkmonitor.documents.alert import AlertDocument
    
    # 查询该 Issue 关联的所有告警
    search_object = AlertDocument.search(start_time=start_time, end_time=end_time)
    search_object = search_object.filter("term", issue_id=issue_id)
    search_object = search_object.source(["id", "begin_time", "dimensions"])
    
    # 聚合维度统计 + 收集告警ID
    dimension_map = defaultdict(lambda: {"display_key": "", "values": defaultdict(int)})
    alerts = []
    
    for hit in search_object.scan():
        doc = hit.to_dict()
        
        # 收集告警 ID 和时间
        alerts.append({
            "id": doc.get("id"),
            "begin_time": doc.get("begin_time"),
        })
        
        # 聚合维度统计
        dimensions = doc.get("dimensions", [])
        for dim in dimensions:
            dim_key = dim.get("key")
            display_key = dim.get("display_key", dim_key)
            display_value = dim.get("display_value", dim.get("value"))
            
            if dim_key not in dimension_map:
                dimension_map[dim_key]["display_key"] = display_key
            
            dimension_map[dim_key]["values"][display_value] += 1
    
    # 构建 dimension_summary
    dimension_summary = []
    for dim_key, dim_info in dimension_map.items():
        value_counts = dim_info["values"]
        total = sum(value_counts.values())
        
        sorted_items = sorted(value_counts.items(), key=lambda x: x[1], reverse=True)
        top5 = sorted_items[:5]
        others = sorted_items[5:]
        
        items = [
            {"value": value, "count": count, "percentage": round(count / total * 100, 2)}
            for value, count in top5
        ]
        
        if others:
            others_count = sum(count for _, count in others)
            items.append({
                "value": "其他",
                "count": others_count,
                "percentage": round(others_count / total * 100, 2),
            })
        
        dimension_summary.append({
            "dimension_key": dim_key,
            "dimension_name": dim_info["display_key"],
            "total_count": total,
            "items": items,
        })
    
    # 构建 alert_ids 信息
    if alerts:
        alerts.sort(key=lambda x: x.get("begin_time", 0))
        alert_ids = [a["id"] for a in alerts]
        latest_alert_id = alerts[-1]["id"]
        earliest_alert_id = alerts[0]["id"]
    else:
        alert_ids = []
        latest_alert_id = None
        earliest_alert_id = None
    
    # 写入结果
    fill_result["dimension_summary"] = dimension_summary
    fill_result["alert_ids"] = alert_ids
    fill_result["latest_alert_id"] = latest_alert_id
    fill_result["earliest_alert_id"] = earliest_alert_id
```

> **优化说明**：
> - 维度统计和告警 ID 列表合并为一次 ES 查询，减少网络开销
> - 使用后台线程并行执行，不阻塞趋势图查询
> - 趋势图查询和维度统计并行进行，整体响应时间取决于较慢的那个

---

## 3. 路由注册

```python
# fta_web/issue/views.py

class IssueViewSet(ResourceViewSet):
    resource_routes = [
        # 查询类
        ResourceRoute("GET", IssueDetailResource, endpoint="detail"),
        ResourceRoute("POST", IssueSearchAlertResource, endpoint="alert/search"),
        ResourceRoute("POST", IssueActivityResource, endpoint="activity"),
        ResourceRoute("POST", IssueHistoryResource, endpoint="history"),
    ]
```
