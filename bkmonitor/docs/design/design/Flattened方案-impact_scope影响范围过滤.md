
# 方案：自定义 Flattened Field 类实现 impact_scope 影响范围过滤

## 一、背景

当前 `IssueDocument` 中 `impact_scope` 字段的 ES 映射为：

```python
impact_scope = field.Object(enabled=False)
```

`enabled=False` 意味着 ES **只存储 `_source`，不建立任何索引**，无法对 `impact_scope` 内部的子字段进行查询、过滤、聚合。

为支持按影响范围维度（如 `host`、`cluster`、`pod` 等）过滤 Issue 列表，需要将 `impact_scope` 改为可索引的类型。

## 二、问题：elasticsearch-dsl 7.4.1 不支持 Flattened

项目使用的 `elasticsearch-dsl==7.4.1`，其 `field` 模块**没有内置 `Flattened` 类型**。

ES 7.3+ 原生支持 `flattened` 映射类型，但 `elasticsearch-dsl-py 7.4.1` 未提供对应的 Python 类。

当前 `field` 模块支持的类型列表：

```
Object, Nested, Date, Text, SearchAsYouType, Keyword, Boolean, Float,
SparseVector, Integer, Ip, Binary, GeoPoint, GeoShape, Completion,
Percolator, RangeField, IntegerRange, FloatRange, LongRange, DoubleRange,
DateRange, IpRange, Join, TokenCount, Murmur3
```

**没有 `Flattened`。**

## 三、方案：自定义 Flattened Field 子类

### 3.1 原理

`elasticsearch-dsl` 的 `Field` 基类通过 `name` 类属性映射到 ES 的字段类型。只需定义一个子类并设置 `name = "flattened"` 即可，ES 会正确识别该映射类型。

### 3.2 代码实现

#### 3.2.1 定义 Flattened 类

在 `bkmonitor/documents/base.py` 中新增（与已有的自定义 `Date` 类放在一起）：

```python
from elasticsearch_dsl import field

class Flattened(field.Field):
    """ES 7.3+ flattened 类型，elasticsearch-dsl 7.x 未内置。
    
    将整个对象的所有叶子节点值扁平化为 keyword 统一索引，
    适用于动态 key 的对象（如 impact_scope）。
    """
    name = "flattened"
```

#### 3.2.2 修改 IssueDocument 映射

在 `bkmonitor/documents/issue.py` 中：

```python
from bkmonitor.documents.base import BaseDocument, BulkActionType, Date, Flattened

class IssueDocument(BaseDocument):
    # ... 其他字段 ...
    
    # 改前
    # impact_scope = field.Object(enabled=False)
    
    # 改后
    impact_scope = Flattened()
```

#### 3.2.3 查询层改造

在 `packages/fta_web/issue/handlers/issue.py` 的 `IssueQueryHandler` 中，override `parse_condition_item` 方法，处理两种影响范围过滤：

```python
from elasticsearch_dsl import Q

class IssueQueryHandler(BaseBizQueryHandler):

    def parse_condition_item(self, condition: dict) -> Q:
        key = condition["key"]

        if key == "impact_dimensions":
            # 维度级过滤 → exists 查询
            should_clauses = [
                Q("exists", field=f"impact_scope.{dim}")
                for dim in condition["value"]
            ]
            return Q("bool", should=should_clauses, minimum_should_match=1)

        if key.startswith("impact_scope."):
            # 实例 ID 级过滤 → terms 查询
            parts = key.split(".", 2)  # ["impact_scope", "host", "bk_host_id"]
            if len(parts) == 3:
                dimension, id_field = parts[1], parts[2]
                es_field = f"impact_scope.{dimension}.instance_list.{id_field}"
                values = [str(v) for v in condition["value"]]
                return Q("terms", **{es_field: values})

        return super().parse_condition_item(condition)
```

通过 `conditions` 机制统一处理，与现有架构一致，无需新增独立参数。

### 3.3 写入端

**零改动**。`_build_impact_scope()` 返回的 dict 结构完全兼容 Flattened 类型。

### 3.4 读取端

**零改动**。`_source` 中存储的原始 JSON 不受映射类型影响，`clean_document` 中的 `enrich_impact_scope` 逻辑不变。

## 四、Flattened 类型特性说明

### 4.1 支持的查询方式

| 查询类型 | 示例 | 说明 |
|---------|------|------|
| `exists` | `{"exists": {"field": "impact_scope.host"}}` | 判断是否包含 `host` 维度 |
| `term` | `{"term": {"impact_scope.host.instance_list.bk_host_id": "9185731"}}` | 按实例 ID 精确匹配（注意：值为 keyword 类型，必须传字符串） |
| `terms` | `{"terms": {"impact_scope.host.instance_list.bk_host_id": ["9185731", "10692392"]}}` | 多值精确匹配（OR 语义） |
| `prefix` | `{"prefix": {"impact_scope": "host"}}` | 前缀匹配 |

### 4.2 各维度实例 ID 字段映射

Flattened 类型会将 `impact_scope` 中所有叶子值扁平化为 keyword 索引。每个维度的 `instance_list` 中有不同的 ID 字段，过滤时需要按对应的 ID 字段查询：

| 维度 key | ID 字段名 | ES 查询路径 | 值类型 | 示例值 | condition |
|---------|----------|------------|--------|--------|-----------|
| `set` | `set_id` | `impact_scope.set.instance_list.set_id` | string | `"5179871"` | `or` |
| `host` | `bk_host_id` | `impact_scope.host.instance_list.bk_host_id` | string* | `"9185731"` | `or` |
| `service_instances` | `bk_service_instance_id` | `impact_scope.service_instances.instance_list.bk_service_instance_id` | string* | `"12345"` | `or` |
| `cluster` | `bcs_cluster_id` | `impact_scope.cluster.instance_list.bcs_cluster_id` | string | `"BCS-K8S-00001"` | `or` |
| `node` | `node` | `impact_scope.node.instance_list.node` | string | `"node-01"` | `and`（集群）+ `or`（节点） |
| `service` | `service` | `impact_scope.service.instance_list.service` | string | `"svc-01"` | `and`（集群）+ `or`（服务） |
| `pod` | `pod` | `impact_scope.pod.instance_list.pod` | string | `"pod-01"` | `and`（集群）+ `or`（Pod） |
| `apm_app` | `app_name` | `impact_scope.apm_app.instance_list.app_name` | string | `"my-app"` | `or`（query_string + tags） |
| `apm_service` | `service_name` | `impact_scope.apm_service.instance_list.service_name` | string | `"my-svc"` | `or`（event.target + tags） |

> **⚠️ 重要**：Flattened 类型将所有叶子值索引为 keyword（字符串），即使原始数据中 `bk_host_id` 是整数 `9185731`，查询时也**必须传字符串** `"9185731"`。后端需要在构建查询时统一将 value 转为字符串。

### 4.3 不支持的查询方式

| 查询类型 | 原因 |
|---------|------|
| `range` | 所有值都被索引为 keyword，无法做数值范围比较 |
| `nested agg` | 不支持 nested 聚合 |
| `highlight` | 不支持高亮 |

### 4.4 `exists` 查询的注意事项

`exists: impact_scope.host` 检查的是 `host` 下面是否有**非空叶子值**，而不仅仅是 key 是否存在。

- `"host": {"count": 3, "instance_list": [...]}` → `exists` 返回 `true` ✅
- `"host": {}` → `exists` 返回 `false`（空对象无叶子值）
- 在我们的场景中这是**正确行为**：空的维度数据不应被视为"有影响范围"

## 五、接口参数设计

影响范围过滤支持两个层级：
- **维度级过滤**：过滤出包含某个维度类型的 Issue（如"有主机影响范围的 Issue"）→ 使用 `exists` 查询
- **实例 ID 级过滤**：过滤出影响了某个具体实例的 Issue（如"影响了 bk_host_id=9185731 的 Issue"）→ 使用 `term`/`terms` 查询

### 5.1 维度级过滤（通过 conditions 传递）

#### 请求示例

**过滤包含 host 维度的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_dimensions",
            "value": ["host"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

**过滤包含 host 或 cluster 维度的 Issue（OR 语义）：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_dimensions",
            "value": ["host", "cluster"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

#### 生成的 ES DSL

```json
{
    "query": {
        "bool": {
            "filter": [
                {"terms": {"bk_biz_id": ["2"]}},
                {
                    "bool": {
                        "should": [
                            {"exists": {"field": "impact_scope.host"}},
                            {"exists": {"field": "impact_scope.cluster"}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            ]
        }
    }
}
```

#### 实现方式

在 `IssueQueryHandler` 中拦截 `impact_dimensions` key，转换为 `exists` 查询：

```python
def parse_condition_item(self, condition: dict) -> Q:
    if condition["key"] == "impact_dimensions":
        should_clauses = [
            Q("exists", field=f"impact_scope.{dim}")
            for dim in condition["value"]
        ]
        return Q("bool", should=should_clauses, minimum_should_match=1)
    return super().parse_condition_item(condition)
```

### 5.2 实例 ID 级精确过滤（通过 conditions 传递）

按具体实例 ID 过滤，conditions 的 key 格式为 `impact_scope.{维度}.{ID字段名}`，后端自动映射为 ES 查询路径 `impact_scope.{维度}.instance_list.{ID字段名}`。

#### 请求示例

**过滤影响了 bk_host_id=9185731 的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.host.bk_host_id",
            "value": ["9185731"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

**过滤影响了多台主机中任一台的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.host.bk_host_id",
            "value": ["9185731", "10692392"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

**过滤影响了某个 set 的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.set.set_id",
            "value": ["5179871"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

**过滤影响了某个 K8S 集群的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.cluster.bcs_cluster_id",
            "value": ["BCS-K8S-00001"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

**过滤影响了某个 APM 服务的 Issue：**

```json
POST /api/v1/issue/search/
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.apm_service.service_name",
            "value": ["order-svc"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

#### 生成的 ES DSL

以 `impact_scope.host.bk_host_id` 为例：

```json
{
    "query": {
        "bool": {
            "filter": [
                {"terms": {"bk_biz_id": ["2"]}},
                {"terms": {"impact_scope.host.instance_list.bk_host_id": ["9185731", "10692392"]}}
            ]
        }
    }
}
```

#### 实现方式

在 `IssueQueryHandler` 中拦截 `impact_scope.*` 前缀的 key，自动插入 `instance_list` 层级并转为 `terms` 查询：

```python
def parse_condition_item(self, condition: dict) -> Q:
    key = condition["key"]

    if key == "impact_dimensions":
        # 维度级过滤 → exists 查询
        should_clauses = [
            Q("exists", field=f"impact_scope.{dim}")
            for dim in condition["value"]
        ]
        return Q("bool", should=should_clauses, minimum_should_match=1)

    if key.startswith("impact_scope."):
        # 实例 ID 级过滤 → terms 查询
        # key: "impact_scope.host.bk_host_id"
        # → ES field: "impact_scope.host.instance_list.bk_host_id"
        parts = key.split(".", 2)  # ["impact_scope", "host", "bk_host_id"]
        if len(parts) == 3:
            dimension, id_field = parts[1], parts[2]
            es_field = f"impact_scope.{dimension}.instance_list.{id_field}"
            # Flattened 类型所有值为 keyword，统一转字符串
            values = [str(v) for v in condition["value"]]
            return Q("terms", **{es_field: values})

    return super().parse_condition_item(condition)
```

### 5.3 组合使用示例

维度级过滤和实例 ID 级过滤可以组合使用，也可以与其他 conditions 组合：

```json
POST /api/v1/issue/search/
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
    "page_size": 20,
    "show_aggs": true
}
```

#### 生成的 ES DSL

```json
{
    "query": {
        "bool": {
            "filter": [
                {"terms": {"bk_biz_id": ["2"]}},
                {"terms": {"priority": ["P0", "P1"]}},
                {"terms": {"impact_scope.host.instance_list.bk_host_id": ["9185731"]}}
            ]
        }
    },
    "sort": [{"update_time": {"order": "desc"}}]
}
```

### 5.4 conditions key 与 ES 查询路径映射总表

| conditions key | ES 查询字段 | 查询类型 | condition | 说明 |
|---------------|------------|---------|-----------|------|
| `impact_dimensions` | `impact_scope.{dim}` | `exists` | - | 维度级：判断是否包含某维度 |
| `impact_scope.set.set_id` | `impact_scope.set.instance_list.set_id` | `terms` | `or` | 按 Set ID 过滤 |
| `impact_scope.host.bk_host_id` | `impact_scope.host.instance_list.bk_host_id` | `terms` | `or` | 按主机 ID 过滤 |
| `impact_scope.service_instances.bk_service_instance_id` | `impact_scope.service_instances.instance_list.bk_service_instance_id` | `terms` | `or` | 按服务实例 ID 过滤 |
| `impact_scope.cluster.bcs_cluster_id` | `impact_scope.cluster.instance_list.bcs_cluster_id` | `terms` | `or` | 按 BCS 集群 ID 过滤 |
| `impact_scope.node.node` | `impact_scope.node.instance_list.node` | `terms` | `and`(集群) + `or`(节点) | 按 K8S 节点名过滤，需同时满足集群条件 |
| `impact_scope.service.service` | `impact_scope.service.instance_list.service` | `terms` | `and`(集群) + `or`(服务) | 按 K8S Service 名过滤，需同时满足集群条件 |
| `impact_scope.pod.pod` | `impact_scope.pod.instance_list.pod` | `terms` | `and`(集群) + `or`(Pod) | 按 K8S Pod 名过滤，需同时满足集群条件 |
| `impact_scope.apm_app.app_name` | `impact_scope.apm_app.instance_list.app_name` | query_string + terms | `or` | 按 APM 应用名过滤，event.target 走 query_string 前缀匹配 |
| `impact_scope.apm_service.service_name` | `impact_scope.apm_service.instance_list.service_name` | terms | `or` | 按 APM 服务名过滤 |

> **⚠️ 注意**：Flattened 类型所有值都是 keyword（字符串），即使原始数据中 `bk_host_id` 是整数 `9185731`，查询时 value 也必须传字符串 `"9185731"`。后端在 `parse_condition_item` 中统一做 `str(v)` 转换。

## 六、可用的影响范围维度 key

来自 `ImpactScopeDimension` 枚举定义（`constants/issue.py`）：

| key | 中文名 | 说明 |
|-----|--------|------|
| `set` | 集群 | CMDB 集群（Set） |
| `host` | 主机 | CMDB 主机 |
| `service_instances` | 服务实例 | CMDB 服务实例 |
| `cluster` | bcs集群 | K8S BCS 集群 |
| `node` | node | K8S 节点 |
| `service` | service | K8S Service |
| `pod` | pod | K8S Pod |
| `app` | app | APM 应用 |
| `apm_service` | apm_service | APM 服务 |

## 七、索引迁移

### 7.1 映射变更性质

`enabled=False`（Object）→ `flattened` 是**映射不兼容变更**，无法通过 `PUT mapping` 直接更新。

### 7.2 迁移方式

#### 方式 A：Rollover（推荐，项目已有 rollover 机制）

1. 更新 index template，将 `impact_scope` 映射改为 `flattened`
2. 手动触发 rollover 创建新索引
3. 新数据自动写入新索引（`impact_scope` 可查询）
4. 旧索引保持不变（旧索引的 `impact_scope` 仍不可查询，但 `_source` 数据完整）

**优点**：零停机、零风险
**缺点**：旧索引中的 Issue 无法按 `impact_scope` 过滤，需等数据自然过期

#### 方式 B：Reindex

1. 创建新索引（新映射）
2. `POST _reindex` 将旧数据迁移到新索引
3. 切换别名

**优点**：全量数据立即可查询
**缺点**：需要停写或双写，有一定风险

### 7.3 建议

优先使用 **方式 A（Rollover）**，因为：
- Issue 是持续产生的，旧数据会自然过期
- 零停机、零风险
- 与项目现有的索引管理机制一致

## 八、完整改动文件清单

| 文件 | 改动内容 |
|------|----------|
| `bkmonitor/documents/base.py` | 新增 `Flattened(field.Field)` 自定义类 |
| `bkmonitor/documents/issue.py` | `impact_scope` 从 `field.Object(enabled=False)` 改为 `Flattened()` |
| `packages/fta_web/issue/handlers/issue.py` | `parse_condition_item` 中处理 `impact_dimensions` 和 `impact_scope.*` 前缀的 conditions |

**写入端（`issue_tasks.py`、`issue_processor.py`）零改动。**

## 九、impact_scope 数据结构参考

以下是 `_build_impact_scope()` 函数实际输出的数据结构（来自 `issue_tasks.py`）：

```json
{
    "impact_scope": {
        "set": {
            "count": 3,
            "display_name": "集群",
            "instance_list": [
                {
                    "set_id": "5179871",
                    "display_name": "kihan-test/bcs-node-module",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_topo_node", "tags.bk_topo_node"],
                            "value": "set|5179871",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "set_id": "5017605",
                    "display_name": "蓝鲸PaaS平台/BCS-K8S-40340",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_topo_node", "tags.bk_topo_node"],
                            "value": "set|5017605",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "set_id": "5043076",
                    "display_name": "DB数据库生产环境/db.es.es",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_topo_node", "tags.bk_topo_node"],
                            "value": "set|5043076",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": null
        },
        "host": {
            "count": 3,
            "display_name": "主机",
            "instance_list": [
                {
                    "bk_host_id": 9185731,
                    "display_name": "21.249.64.16",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_host_id", "tags.bk_host_id"],
                            "value": "9185731",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "bk_host_id": 10692392,
                    "display_name": "21.186.179.6",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_host_id", "tags.bk_host_id"],
                            "value": "10692392",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "bk_host_id": 1804751,
                    "display_name": "11.181.33.209",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_host_id", "tags.bk_host_id"],
                            "value": "1804751",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "/performance/detail/{bk_host_id}"
        },
        "service_instances": {
            "count": 2,
            "display_name": "服务实例",
            "instance_list": [
                {
                    "bk_service_instance_id": 12345,
                    "display_name": "mysql_exporter(21.249.64.16)",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_service_instance_id", "tags.bk_service_instance_id", "tags.bk_target_service_instance_id"],
                            "value": "12345",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "bk_service_instance_id": 67890,
                    "display_name": "node_exporter(21.186.179.6)",
                    "alert_query_fields": [
                        {
                            "keys": ["event.bk_service_instance_id", "tags.bk_service_instance_id", "tags.bk_target_service_instance_id"],
                            "value": "67890",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": null
        },
        "cluster": {
            "count": 1,
            "display_name": "bcs集群",
            "instance_list": [
                {
                    "bcs_cluster_id": "BCS-K8S-00001",
                    "display_name": "生产集群(BCS-K8S-00001)",
                    "alert_query_fields": [
                        {
                            "keys": ["tags.bcs_cluster_id"],
                            "value": "BCS-K8S-00001",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview"
        },
        "node": {
            "count": 2,
            "display_name": "node",
            "instance_list": [
                {
                    "bcs_cluster_id": "BCS-K8S-00001",
                    "node": "node-01",
                    "display_name": "BCS-K8S-00001/node-01",
                    "alert_query_fields": [
                        {
                            "keys": ["tags.bcs_cluster_id"],
                            "value": "BCS-K8S-00001",
                            "condition": "and"
                        },
                        {
                            "keys": ["event.target", "tags.node", "tags.node_name"],
                            "value": "node-01",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "bcs_cluster_id": "BCS-K8S-00001",
                    "node": "node-02",
                    "display_name": "BCS-K8S-00001/node-02",
                    "alert_query_fields": [
                        {
                            "keys": ["tags.bcs_cluster_id"],
                            "value": "BCS-K8S-00001",
                            "condition": "and"
                        },
                        {
                            "keys": ["event.target", "tags.node", "tags.node_name"],
                            "value": "node-02",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&filter-node_name={node}&dashboardId=node&sceneId=kubernetes&sceneType=detail"
        },
        "apm_app": {
            "count": 1,
            "display_name": "apm_app",
            "instance_list": [
                {
                    "app_name": "my-app",
                    "bk_biz_id": 2,
                    "display_name": "my-app",
                    "alert_query_fields": [
                        {
                            "keys": ["query_string"],
                            "value": "event.target:my-app\\:*",
                            "condition": "or"
                        },
                        {
                            "keys": ["tags.app_name"],
                            "value": "my-app",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "?bizId={bk_biz_id}#/apm/application?filter-app_name={app_name}"
        },
        "apm_service": {
            "count": 2,
            "display_name": "apm_service",
            "instance_list": [
                {
                    "app_name": "my-app",
                    "service_name": "order-svc",
                    "bk_biz_id": 2,
                    "display_name": "my-app/order-svc",
                    "alert_query_fields": [
                        {
                            "keys": ["event.target"],
                            "value": "my-app:order-svc",
                            "condition": "or"
                        },
                        {
                            "keys": ["tags.service_name"],
                            "value": "order-svc",
                            "condition": "or"
                        }
                    ]
                },
                {
                    "app_name": "my-app",
                    "service_name": "pay-svc",
                    "bk_biz_id": 2,
                    "display_name": "my-app/pay-svc",
                    "alert_query_fields": [
                        {
                            "keys": ["event.target"],
                            "value": "my-app:pay-svc",
                            "condition": "or"
                        },
                        {
                            "keys": ["tags.service_name"],
                            "value": "pay-svc",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "?bizId={bk_biz_id}#/apm/service?filter-app_name={app_name}&filter-service_name={service_name}"
        }
    }
}
```

Flattened 类型会将上述结构的所有叶子值扁平化为 keyword 索引：
- 支持 `exists` 查询判断是否包含某个维度 key
- 支持 `term`/`terms` 查询按具体实例 ID 精确过滤
- **注意**：所有值（包括整数如 `bk_host_id: 9185731`）都被索引为字符串 `"9185731"`，查询时必须传字符串

每个实例的 `alert_query_fields` 字段用于前端反查关联告警：
- `keys`：告警文档中可查询的字段路径列表
- `value`：后端已渲染好的查询值（如 `set|5017605`、`my-app:order-svc`）
- `condition`：同一组内 keys 之间的逻辑关系，`or` 为任一命中即匹配，`and` 为必须同时满足
- K8S 维度（node/service/pod）中 `condition: "and"` 的组表示集群过滤条件，必须与节点/服务/Pod 条件同时满足，避免跨集群误匹配
- `apm_app` 的 `query_string` 类型使用 Lucene query_string 语法（如 `event.target:my-app\:*`），`\:` 转义冒号使 `*` 作为通配符生效，实现前缀匹配

## 十、与方案 A（冗余 Keyword 字段）的对比

| 维度 | Flattened 方案 | 冗余 Keyword 方案 |
|------|---------------|------------------|
| 写入端改动 | ✅ 零改动 | ⚠️ 需同步维护 `impact_dimensions` |
| 数据一致性 | ✅ 无冗余字段 | ⚠️ 需保证冗余字段与 `impact_scope` 同步 |
| 聚合支持 | ❌ 不支持按维度聚合 | ✅ 支持 `terms` 聚合 |
| 查询方式 | `exists` + `term`/`terms` 查询 | `terms` 查询 |
| 索引迁移 | ⚠️ 需要 rollover/reindex | ⚠️ 需要 rollover + 存量回填 |
| 代码改动量 | 小（~4 个文件） | 中（~5 个文件 + 迁移脚本） |
