# Issue 告警查询接口设计文档

> **关联文档**：[Issues详情接口设计.md](Issues详情接口设计.md) | [Issue详情接口文档.md](../api/Issue详情接口文档.md)

---

## 1. 接口说明

对应设计稿模块：**检索栏 + 告警列表 + 趋势图 + 维度统计**

接口地址：`POST /fta/issue/alert/search`

本接口用于**刷新 Issue 详情页中的动态数据**。当用户在检索栏中输入条件、切换时间范围时，通过本接口重新查询并返回更新后的告警列表、趋势图、维度统计等数据。

| 维度 | 说明 |
|------|------|
| **定位** | 刷新 Issue 详情中除元数据外的动态数据（告警列表 + 趋势图 + 维度统计 + 聚合统计等） |
| **搜索范围** | 单个 Issue 关联的告警子集（`AlertDocument` 中 `issue_id` 等于当前 Issue ID 的告警） |
| **不是** | 搜索整个告警中心的所有告警 |
| **交互方式** | 检索栏 UI 模式与告警中心保持一致，但功能本质不同 |
| **使用场景** | 用户在 Issue 详情页使用检索栏过滤/搜索时，局部刷新动态数据 |

---

## 2. 设计决策：独立 Resource + 复用告警搜索核心逻辑

**方案选择**：新建 `IssueSearchAlertResource`，内部复用 `AlertQueryHandler` 的搜索能力。

理由：
1. Issue 告警查询挂载在 Issue 模块路由下（`/fta/issue/alert/search`），需要独立的 Resource 注册
2. 核心搜索逻辑（过滤、条件查询）复用现有 `AlertQueryHandler`
3. 通过 `issue_id` 参数自动注入 `conditions`，对前端透明
4. 返回值与 Issue 详情接口的动态数据部分一致（去掉 Issue 元数据），用于局部刷新

---

## 3. IssueSearchAlertResource

```python
class IssueSearchAlertResource(Resource):
    """查询 Issue 关联告警的动态数据，用于刷新 Issue 详情页"""

    class RequestSerializer(serializers.Serializer):
        bk_biz_id = serializers.IntegerField(label="业务ID", required=True)
        issue_id = IssueIDField(label="Issue ID")
        conditions = SearchConditionSerializer(label="搜索条件", many=True, default=[])
        query_string = serializers.CharField(label="查询字符串", default="", allow_blank=True)
        start_time = serializers.IntegerField(label="开始时间")
        end_time = serializers.IntegerField(label="结束时间")
        page = serializers.IntegerField(label="页码", default=1, min_value=1)
        page_size = serializers.IntegerField(label="每页数量", default=100, min_value=1, max_value=1000)
        ordering = serializers.ListField(label="排序字段", child=serializers.CharField(), default=[])

    def perform_request(self, validated_request_data):
        # 具体实现见开发阶段
        pass
```

---

## 4. 请求参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `bk_biz_id` | `int` | 是 | — | 业务 ID（用于权限校验） |
| `issue_id` | `str` | 是 | — | Issue ID，自动注入为 `conditions` 中的 `issue_id` 过滤条件 |
| `conditions` | `list` | 否 | `[]` | 搜索条件，格式同告警搜索 |
| `query_string` | `str` | 否 | `""` | 查询字符串 |
| `start_time` | `int` | 是 | — | 开始时间（秒级时间戳） |
| `end_time` | `int` | 是 | — | 结束时间（秒级时间戳） |
| `page` | `int` | 否 | `1` | 页码，最小值为 1 |
| `page_size` | `int` | 否 | `100` | 每页数量，范围 1~1000，默认 100 |
| `ordering` | `list[str]` | 否 | `[]` | 排序字段列表，前缀 `-` 表示降序。为空时使用默认排序：`["status", "-create_time", "-seq_id"]` |

---

## 5. 返回值结构

返回 Issue 详情中除元数据外的动态数据，用于局部刷新详情页：

```json
{
  "issue_id": "1741420800a3b7c9d2",
  "latest_alert_id": "17414208001234abcd",
  "earliest_alert_id": "17413344005678efgh",
  "alert_ids": ["17414208001234abcd", "17413344005678efgh", ...],
  "alert_count": 86,
  "trend": [
    {
      "data": [[1773619200000, 1], [1773705600000, 3], ...],
      "display_name": "未恢复",
      "name": "ABNORMAL"
    },
    {
      "data": [[1773619200000, 0], [1773705600000, 1], ...],
      "display_name": "已恢复",
      "name": "RECOVERED"
    },
    {
      "data": [[1773619200000, 0], [1773705600000, 0], ...],
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
        {"value": "其他", "count": 1, "percentage": 1.16}
      ]
    }
  ]
}
```

### 5.1 返回值字段说明

| 字段 | 类型 | 说明                                        |
|------|------|-------------------------------------------|
| `issue_id` | `str` | 当前查询的 Issue ID                            |
| `latest_alert_id` | `str` | 最新告警 ID（按时间倒序第一条）                         |
| `earliest_alert_id` | `str` | 最早告警 ID（按时间正序第一条）                         |
| `alert_ids` | `list[str]` | 当前条件下的告警 ID 列表（分页返回）                      |
| `alert_count` | `int` | 符合条件的告警总数（用于分页计算）                          |
| `trend` | `list` | 告警趋势图数据（ABNORMAL / RECOVERED / CLOSED 三条时间序列） |
| `dimension_summary` | `list` | 维度统计数据（Top5 + 其他）                         |

> **与 Issue 详情接口的关系**：本接口返回的 `alert_ids`、`trend`、`dimension_summary`、`alert_count` 字段含义与 Issue 详情接口一致，用于替换详情页中对应模块的数据。
>
> **不返回 `aggs` 和 `overview`**：Issue 详情页的告警列表不需要独立的聚合统计和总览面板，这些功能由 Issue 列表页承担。

---

## 6. 前端调用方式

### 6.1 检索栏搜索（刷新动态数据）

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

### 6.2 带条件过滤

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

### 6.3 最新/最早告警

`latest_alert_id` 和 `earliest_alert_id` 已通过 `detail` 接口返回，前端点击时直接调用告警详情接口（已实现），无需本接口支持。

---

## 7. 检索栏 UI 模式

设计稿中检索栏支持 **UI 模式切换**，与告警中心保持一致：

- 检索栏的 `UI 模式`、`添加条件`、`搜索` 等交互逻辑复用告警中心组件
- `issue_id` 作为 Resource 层参数，自动注入 `conditions`，前端无需手动添加
- 用户添加的额外条件通过 `conditions` 参数追加

---

## 8. 后端实现要点

### 8.1 注册 issue_id 查询字段

在 `AlertQueryTransformer.query_fields` 中注册 `issue_id` 字段：

```python
# fta_web/alert/handlers/alert.py

class AlertQueryTransformer(BaseQueryTransformer):
    query_fields = [
        # ... existing fields ...
        QueryField("issue_id", _lazy("Issue ID")),
    ]
```

### 8.2 路由注册

```python
# fta_web/issue/views.py

class IssueViewSet(ResourceViewSet):
    resource_routes = [
        # ... existing routes ...
        ResourceRoute("POST", IssueSearchAlertResource, endpoint="alert/search"),
    ]
```

### 8.3 IssueSearchAlertResource 实现方案

#### 核心思路

复用 `AlertQueryHandler` 的搜索能力，将 `issue_id` 自动注入为 `conditions`，传入分页和排序参数，调用 `handler.search()` 时不启用 `show_overview` 和 `show_aggs`，仅返回告警列表 + 趋势图 + 维度统计。

#### perform_request 实现流程

```python
def perform_request(self, validated_request_data):
    bk_biz_id = validated_request_data["bk_biz_id"]
    issue_id = validated_request_data["issue_id"]
    page = validated_request_data.get("page", 1)
    page_size = validated_request_data.get("page_size", 100)
    ordering = validated_request_data.get("ordering", [])

    # 1. 将 issue_id 注入到 conditions 中
    conditions = validated_request_data.get("conditions", [])
    conditions.append({"key": "issue_id", "value": [issue_id], "method": "eq"})

    # 2. 构造 AlertQueryHandler，传入分页和排序参数
    handler = AlertQueryHandler(
        bk_biz_ids=[bk_biz_id],
        start_time=validated_request_data["start_time"],
        end_time=validated_request_data["end_time"],
        conditions=conditions,
        query_string=validated_request_data.get("query_string", ""),
        page=page,
        page_size=page_size,
        ordering=ordering,
    )

    # 3. 调用 search()，不启用 show_overview 和 show_aggs
    result = handler.search(show_overview=False, show_aggs=False)
    # result 包含 {"alerts": [...], "total": N}

    # 4. 提取告警 ID 列表，以及最新/最早告警 ID
    alerts = result["alerts"]
    alert_ids = [alert["id"] for alert in alerts]
    latest_alert_id = get_latest_alert_id(handler, ...)
    earliest_alert_id = get_earliest_alert_id(handler, ...)

    # 5. 构建趋势图数据（复用 date_histogram）
    trend = build_trend_data(handler, ...)

    # 6. 构建维度统计数据
    dimension_summary = build_dimension_summary(handler, ...)

    return {
        "issue_id": issue_id,
        "latest_alert_id": latest_alert_id,
        "earliest_alert_id": earliest_alert_id,
        "alert_ids": alert_ids,
        "alert_count": result["total"],
        "trend": trend,
        "dimension_summary": dimension_summary,
    }
```

#### 分页与排序的实现依赖

分页和排序能力由 `BaseQueryHandler` 基类提供，无需额外开发：

- **分页**：`BaseQueryHandler.add_pagination()` 根据 `page` 和 `page_size` 计算 ES 的 `from/size` 偏移量
- **排序**：`BaseQueryHandler.add_ordering()` 将 `ordering` 列表转换为 ES 的 `sort` 参数，支持 `-field` 降序语法
- **默认排序**：`AlertQueryHandler.__init__()` 中当 `ordering` 为空时，使用默认排序 `["status", "-create_time", "-seq_id"]`

#### 不返回 aggs/overview 的实现方式

`AlertQueryHandler.search()` 方法已支持 `show_overview` 和 `show_aggs` 参数控制：

```python
# AlertQueryHandler.search() 现有逻辑
def search(self, show_overview=False, show_aggs=False, show_dsl=False):
    # ...
    result = {"alerts": alerts, "total": search_result.hits.total.value}
    if show_overview:
        result["overview"] = self.handle_overview(search_result)
    if show_aggs:
        result["aggs"] = self.handle_aggs(search_result)
    # ...
```

在 `IssueSearchAlertResource.perform_request()` 中调用 `handler.search(show_overview=False, show_aggs=False)` 即可，返回值中自然不包含 `aggs` 和 `overview` 字段。

---

## 9. 开发任务

| Task | 内容 | 优先级 |
|------|------|--------|
| **Task A** | `AlertQueryTransformer` 追加 `issue_id` QueryField | P0 |
| **Task B** | `IssueSearchAlertResource` 实现 | P0 |
| **Task C** | `IssueViewSet` 路由注册 `alert/search` endpoint | P0 |

---

## 10. 调用流程

```mermaid
sequenceDiagram
    participant FE as 前端
    participant View as IssueViewSet
    participant Res as IssueSearchAlertResource
    participant Handler as AlertQueryHandler
    participant ES as Elasticsearch

    FE->>View: POST /fta/issue/alert/search<br/>{bk_biz_id: 2, issue_id: "xxx", ...}
    View->>Res: perform_request()
    Res->>Res: 注入 issue_id 到 conditions
    Res->>Handler: AlertQueryHandler(**params)
    Handler->>ES: AlertDocument.search()<br/>.filter("term", issue_id=xxx)<br/>.sort(...).slice(page, page_size)
    ES-->>Handler: 告警列表（分页）
    Handler-->>Res: {alerts, total}
    Res->>Res: 提取 alert_ids + latest/earliest
    Res->>Res: 构建 trend + dimension_summary
    Res-->>FE: {issue_id, alert_ids,<br/>latest_alert_id, earliest_alert_id,<br/>alert_count, trend, dimension_summary}
```
