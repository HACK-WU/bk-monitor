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

### 2.1 IssueDetailResource

```python
class IssueDetailResource(Resource):
    """获取单个 Issue 的完整信息，包含告警趋势统计"""

    class RequestSerializer(serializers.Serializer):
        id = IssueIDField(label="Issue ID")
        bk_biz_id = serializers.IntegerField(label="业务ID", required=True)
        start_time = serializers.IntegerField(label="开始时间", required=False)
        end_time = serializers.IntegerField(label="结束时间", required=False)

    def perform_request(self, validated_request_data):
        # ...existing code...
        pass
```

### 2.2 请求参数

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

### 2.5 impact_scope 说明

设计稿中的**维度统计**模块（主机、云区域 ID 进度条）实际对应 **影响范围**。

**数据来源**：从告警的 `dimensions` 字段中获取相关维度信息，而非从 `IssueDocument.impact_scope` 字段。

**数据结构**：

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
  "cluster": {
    "count": 1,
    "display_name": "集群",
    "instance_list": [
      {"bcs_cluster_id": "BCS-K8S-12345", "display_name": "生产集群"}
    ],
    "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview"
  }
}
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

### 2.6 trend 趋势统计说明

趋势图数据复用 `AlertQueryHandler.date_histogram` 方法，通过 ES 聚合从 `AlertDocument` 实时计算获取。

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

**复用方式**：
```python
from fta_web.alert.handlers.alert import AlertQueryHandler

def _build_trend(self, issue_id: str, start_time: int, end_time: int) -> list:
    """
    构建告警趋势数据
    
    复用 AlertQueryHandler.date_histogram 方法，按 status 分组统计：
    - ABNORMAL: 未恢复（红色）
    - RECOVERED: 已恢复（绿色）
    - CLOSED: 已失效（黄色）
    """
    handler = AlertQueryHandler(
        start_time=start_time,
        end_time=end_time,
        conditions=[{"key": "issue_id", "value": [issue_id], "method": "eq"}]
    )
    
    # 调用 date_histogram，默认按 status 分组
    result = handler.date_histogram(interval="auto")
    # ...existing code...
    pass
```

> **说明**：`AlertQueryHandler.date_histogram` 已实现三段式聚合 + 滚动累加逻辑，直接复用即可。

### 2.7 dimension_summary 维度统计说明

维度统计模块用于展示告警在各维度上的分布情况，帮助用户快速了解问题影响范围。

**数据来源**：从告警的 `dimensions` 字段中聚合统计获取。

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

**聚合策略**：

1. 从 `AlertDocument` 批量获取所有告警的 `dimensions` 字段
2. 遍历每个维度 key，统计各 value 的出现次数
3. 按 count 降序排列，取 Top5
4. 其余归入 `"其他"` 分类（后端使用 `_("其他")` 进行国际化翻译）
5. 计算各项占比百分比

**实现示例**：

```python
def _build_dimension_summary(self, alert_ids: list[str]) -> list[dict]:
    """
    构建维度统计数据
    
    构建维度统计数据
    
    告警的 dimensions 字段结构为 list[dict]，每个元素包含：
    - key: 维度字段名（如 bk_target_ip）
    - value: 维度值（如 10.0.0.1）
    - display_key: 维度展示名（如 主机IP），告警生成阶段已填充
    - display_value: 维度值展示文本，告警生成阶段已填充
    
    因此无需额外的维度名称映射表，直接使用 display_key / display_value 即可。
    """
    # {dim_key: {"display_key": str, "values": {value: {"display_value": str, "count": int}}}}
    dimension_map = {}
    
    for alert in alerts:
        for dim in alert.dimensions:
            dim_key = dim["key"]
            dim_value = dim["value"]
            display_key = dim.get("display_key", dim_key)
            display_value = dim.get("display_value", dim_value)
            
            if dim_key not in dimension_map:
                dimension_map[dim_key] = {"display_key": display_key, "values": {}}
            
            entry = dimension_map[dim_key]["values"]
            if dim_value not in entry:
                entry[dim_value] = {"display_value": display_value, "count": 0}
            entry[dim_value]["count"] += 1
    
    result = []
    for dim_key, dim_info in dimension_map.items():
        value_counts = dim_info["values"]
        # 排序并取 Top5
        sorted_items = sorted(value_counts.items(), key=lambda x: x[1]["count"], reverse=True)
        top5 = sorted_items[:5]
        others = sorted_items[5:]
        
        total = sum(v["count"] for v in value_counts.values())
        items = []
        
        for value, info in top5:
            items.append({
                "value": value,
                "count": info["count"],
                "percentage": round(info["count"] / total * 100, 2)
            })
        
        if others:
            others_count = sum(info["count"] for _, info in others)
            items.append({
                "value": _("其他"),
                "count": others_count,
                "percentage": round(others_count / total * 100, 2)
            })
        
        result.append({
            "dimension_key": dim_key,
            "dimension_name": dim_info["display_key"],
            "total_count": total,
            "items": items
        })
    
    return result
```

**前端渲染逻辑**：

```
维度统计
├── 主机IP (共 86 次)
│   ┌─────────────────────────────────────┐
│   │ ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 10.0.0.1 (30次, 34.88%)
│   │ █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 10.0.0.2 (20次, 23.26%)
│   │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 10.0.0.3 (15次, 17.44%)
│   │ ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 10.0.0.4 (12次, 13.95%)
│   │ ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 10.0.0.5 (8次, 9.30%)
│   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 其他 (1次, 1.16%)
│   └─────────────────────────────────────┘
```

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
