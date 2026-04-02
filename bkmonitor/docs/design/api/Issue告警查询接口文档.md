# Issue 告警查询接口文档

> **版本**: v1.0  
> **更新时间**: 2026-04-02  
> **关联文档**：[Issue详情接口文档.md](Issue详情接口文档.md)

---

## 接口信息

| 项目 | 值 |
|------|-----|
| **接口名称** | Issue 告警查询 |
| **请求方式** | POST |
| **接口地址** | `/fta/issue/alert/search` |
| **内容类型** | application/json |

---

## 功能说明

查询指定 Issue 关联的告警数据，用于 Issue 详情页中**检索栏搜索、翻页、排序**等交互场景的局部刷新。

返回内容包括：告警 ID 列表（分页）、告警趋势图、维度统计、最新/最早告警 ID。

> **与 detail 接口的关系**：
> - `detail` 接口返回 Issue 完整信息（元数据 + 动态数据），用于**首次加载**
> - 本接口仅返回动态数据部分，用于用户操作检索栏后的**局部刷新**，无需重新加载整个详情页

---

## 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|------|------|
| `bk_biz_id` | `int` | 是 | — | 业务 ID |
| `issue_id` | `string` | 是 | — | Issue ID |
| `start_time` | `int` | 是 | — | 开始时间（秒级时间戳） |
| `end_time` | `int` | 是 | — | 结束时间（秒级时间戳） |
| `conditions` | `object[]` | 否 | `[]` | 搜索条件，格式同告警中心搜索栏，详见下方说明 |
| `query_string` | `string` | 否 | `""` | 查询字符串（支持 Lucene 语法） |
| `page` | `int` | 否 | `1` | 页码，从 1 开始 |
| `page_size` | `int` | 否 | `100` | 每页数量，范围 1~1000 |
| `ordering` | `string[]` | 否 | `["status", "-create_time", "-seq_id"]` | 排序字段列表，前缀 `-` 表示降序。为空时使用默认排序 |

### conditions 格式说明

`conditions` 数组中每个元素的结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | `string` | 过滤字段名，如 `severity`、`status`、`assignee` 等 |
| `value` | `any[]` | 过滤值列表 |
| `method` | `string` | 匹配方式：`eq`（等于）、`neq`（不等于）、`include`（包含）、`exclude`（不包含） |

### ordering 排序说明

- 字段名前加 `-` 表示降序，不加前缀表示升序
- 支持的排序字段：`status`、`severity`、`create_time`、`seq_id` 等
- 为空时使用默认排序：`["status", "-create_time", "-seq_id"]`
- 这里按照默认排序即可

> **注意**：`issue_id` 的过滤由后端自动处理，前端**无需**在 `conditions` 中手动添加 `issue_id` 条件。

---

## 请求示例

### 基础查询（首次加载）

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

### 带条件过滤 + 自定义排序

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

### 翻页查询

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

---

## 响应结构

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
    "alert_count": 86,
    "trend": [
      {
        "data": [
          [1773619200000, 1],
          [1773705600000, 3],
          [1773792000000, 2]
        ],
        "display_name": "未恢复",
        "name": "ABNORMAL"
      },
      {
        "data": [
          [1773619200000, 0],
          [1773705600000, 1],
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

---

## 响应字段说明

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `issue_id` | `string` | 当前查询的 Issue ID（与请求参数一致） |
| `latest_alert_id` | `string` | 最新告警 ID（按时间倒序第一条），用于"最新告警"跳转 |
| `earliest_alert_id` | `string` | 最早告警 ID（按时间正序第一条），用于"最早告警"跳转 |
| `alert_ids` | `string[]` | **当前页**的告警 ID 列表，按排序规则排列 |
| `alert_count` | `int` | 符合条件的告警总数（用于分页计算） |
| `trend` | `object[]` | 告警趋势图数据 |
| `dimension_summary` | `object[]` | 维度统计数据 |

### trend 趋势图

按告警状态分组的时间序列数据，用于渲染堆叠柱状图。

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

### dimension_summary 维度统计

展示告警在各维度上的分布情况，帮助用户快速了解问题影响范围。

**dimension_summary 数组元素字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `dimension_key` | `string` | 维度字段名 |
| `dimension_name` | `string` | 维度显示名称（中文），如"主机IP" |
| `total_count` | `int` | 该维度在所有告警中出现的总次数 |
| `items` | `object[]` | 维度值分布列表（Top5 + 其他） |

**items 数组元素字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `value` | `string` | 维度值，直接用于展示；聚合剩余项时值为 `"其他"` |
| `count` | `int` | 该值出现次数 |
| `percentage` | `float` | 占比百分比（保留2位小数） |

**前端渲染说明**：
- 每个维度渲染为一组进度条，按 `percentage` 显示占比
- 最多展示 Top5 + 其他
- `value` 直接作为展示文本

---

## 前端使用场景

| 场景 | 操作                                     | 参数变化                                          |
|------|----------------------------------------|-----------------------------------------------|
| **首次加载** | 详情页打开后，使用 detail 接口返回的数据即可，**无需调用本接口** | —                                             |
| **检索栏搜索** | 用户输入搜索条件后点击搜索                          | `conditions` / `query_string` 变化，`page` 重置为 1 |
| **切换时间范围** | 用户修改时间选择器                              | `start_time` / `end_time` 变化，`page` 重置为 1     |
| **翻页** | -无操作，使用默认值                             | -                                             |
| **排序** | -无操作，使用默认值                             | -                                             |

---

## 分页说明

| 项目 | 说明 |
|------|------|
| **总数** | 使用 `alert_count` 字段计算总页数：`Math.ceil(alert_count / page_size)` |
| **当前页数据** | `alert_ids` 为当前页的告警 ID 列表 |
| **空结果** | `alert_count` 为 0 时，`alert_ids` 为空数组 |

---

## 注意事项

1. **`issue_id` 来源**：由前端从 `detail` 接口获取后传入，无需用户手动输入
2. **检索栏复用**：检索栏的 UI 交互复用告警中心组件，`issue_id` 的过滤由后端自动处理
3. **`latest_alert_id` / `earliest_alert_id`**：不受分页影响，始终返回全局最新/最早告警 ID
4. **`alert_ids` 是 ID 列表**：不是完整的告警对象，如需告警详情请调用告警详情接口
5. **`trend` 和 `dimension_summary`**：格式与 detail 接口完全一致，可直接替换详情页中对应模块的数据
