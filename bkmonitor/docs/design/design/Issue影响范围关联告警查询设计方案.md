# Issue 影响范围关联告警查询设计方案

## 一、背景

Issue 的 `impact_scope` 字段记录了告警聚合后的影响范围（主机、集群、Pod 等）。前端在 Issue 列表/详情页中需要展示"关联告警"——即该影响范围内的实例当前有哪些告警。

由于 `impact_scope` 中的实例 ID 与 `AlertDocument` 中的索引字段并非简单的一一对应（不同维度走不同的 ES 字段路径，且部分字段在 `event.tags` nested 结构中），前端无法直接用实例 ID 构造告警查询条件。

因此，需要在后端为 `impact_scope` 的每个实例预渲染 `alert_query_fields`，前端拿到后可直接组装为告警列表接口的 `conditions` 参数。

## 二、方案概述

1. **后端定义映射表**：在 `ImpactScopeDimension.ALERT_QUERY_MAPPING` 中声明每个影响范围维度对应的告警查询字段和值模板
2. **后端预渲染**：`enrich_impact_scope()` 在返回 impact_scope 时，将映射表中的模板用实例实际值替换，生成 `alert_query_fields`
3. **前端直用**：前端拿到 `alert_query_fields` 后，将其展开为告警列表接口的 `conditions` 格式，即可查询关联告警

## 三、映射配置设计

### 3.1 配置结构

定义在 `bkmonitor/constants/issue.py` 的 `ImpactScopeDimension.ALERT_QUERY_MAPPING` 中：

```python
ALERT_QUERY_MAPPING = {
    "impact_scope.{dimension}": [
        {
            "keys": ["event.xxx", "tags.yyy"],  # AlertDocument 中可查询的字段列表（或关系）
            "value_tpl": "{field}",              # 值模板，{field} 对应 instance_list 中的字段名
            "condition": "or",                   # 同组 keys 间逻辑关系，"or" 或 "and"
        },
        # ... 可以有多组，组间也是"或"关系
    ],
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `keys` | `list[str]` | AlertDocument 中可查询的字段列表。同组内根据 `condition` 决定逻辑关系 |
| `value_tpl` | `str` | 值模板，`{field}` 占位符会被实例中对应字段的实际值替换 |
| `condition` | `str` | 同组 keys 之间的逻辑关系：`"or"`（任一命中即匹配）或 `"and"`（必须同时满足） |

**key 前缀约定：**

- `event.XXX` → 走顶层 `term`/`terms` 查询
- `tags.XXX` → 走 `event.tags` nested 查询

### 3.2 完整映射表

```python
ALERT_QUERY_MAPPING = {
    # set 集群：set_id 在 ES 中以 "set|{set_id}" 形式存储于 bk_topo_node
    "impact_scope.set": [
        {
            "keys": ["event.bk_topo_node", "tags.bk_topo_node"],
            "value_tpl": "set|{set_id}",
            "condition": "or",
        },
    ],
    # host 主机
    "impact_scope.host": [
        {
            "keys": ["event.bk_host_id", "tags.bk_host_id"],
            "value_tpl": "{bk_host_id}",
            "condition": "or",
        },
    ],
    # service_instances 服务实例
    "impact_scope.service_instances": [
        {
            "keys": [
                "event.bk_service_instance_id",
                "tags.bk_service_instance_id",
                "tags.bk_target_service_instance_id",
            ],
            "value_tpl": "{bk_service_instance_id}",
            "condition": "or",
        },
    ],
    # cluster BCS 集群：bcs_cluster_id 仅存在于 event.tags
    "impact_scope.cluster": [
        {
            "keys": ["tags.bcs_cluster_id"],
            "value_tpl": "{bcs_cluster_id}",
            "condition": "or",
        },
    ],
    # node K8S 节点：需同时满足集群过滤（and），避免跨集群同名节点误匹配
    "impact_scope.node": [
        {
            "keys": ["tags.bcs_cluster_id"],
            "value_tpl": "{bcs_cluster_id}",
            "condition": "and",
        },
        {
            "keys": ["event.target", "tags.node", "tags.node_name"],
            "value_tpl": "{node}",
            "condition": "or",
        },
    ],
    # service K8S 服务：需同时满足集群过滤（and），避免跨集群同名 service 误匹配
    "impact_scope.service": [
        {
            "keys": ["tags.bcs_cluster_id"],
            "value_tpl": "{bcs_cluster_id}",
            "condition": "and",
        },
        {
            "keys": ["event.target", "tags.service", "tags.service_name"],
            "value_tpl": "{service}",
            "condition": "or",
        },
    ],
    # pod K8S Pod：需同时满足集群过滤（and），避免跨集群同名 pod 误匹配
    "impact_scope.pod": [
        {
            "keys": ["tags.bcs_cluster_id"],
            "value_tpl": "{bcs_cluster_id}",
            "condition": "and",
        },
        {
            "keys": ["event.target", "tags.pod", "tags.pod_name"],
            "value_tpl": "{pod}",
            "condition": "or",
        },
    ],
    # apm_app APM 应用：event.target 需前缀匹配，使用 query_string 语法
    # query_string 中 \: 转义冒号，* 作为通配符，渲染示例：event.target:nf\:*
    "impact_scope.apm_app": [
        {
            "keys": ["query_string"],
            "value_tpl": "event.target:{app_name}\\:*",
            "condition": "or",
        },
        {
            "keys": ["tags.app_name"],
            "value_tpl": "{app_name}",
            "condition": "or",
        },
    ],
    # apm_service APM 服务：event.target 需完整匹配，tags.service_name 精确匹配
    "impact_scope.apm_service": [
        {
            "keys": ["event.target"],
            "value_tpl": "{app_name}:{service_name}",
            "condition": "or",
        },
        {
            "keys": ["tags.service_name"],
            "value_tpl": "{service_name}",
            "condition": "or",
        },
    ],
}
```

## 四、接口返回结构

### 4.1 Issue 列表/详情接口中 impact_scope 的完整结构

```json
{
    "impact_scope": {
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
                }
            ],
            "link_tpl": "/performance/detail/{bk_host_id}"
        },
        "node": {
            "count": 1,
            "display_name": "node",
            "instance_list": [
                {
                    "bcs_cluster_id": "BCS-K8S-26322",
                    "node": "21.249.64.16",
                    "display_name": "BCS-K8S-26322/21.249.64.16",
                    "alert_query_fields": [
                        {
                            "keys": ["tags.bcs_cluster_id"],
                            "value": "BCS-K8S-26322",
                            "condition": "and"
                        },
                        {
                            "keys": ["event.target", "tags.node", "tags.node_name"],
                            "value": "21.249.64.16",
                            "condition": "or"
                        }
                    ]
                }
            ],
            "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&filter-node_name={node}&dashboardId=node&sceneId=kubernetes&sceneType=detail"
        },
        "apm_service": {
            "count": 1,
            "display_name": "apm_service",
            "instance_list": [
                {
                    "app_name": "nf",
                    "service_name": "nf.pushsvr",
                    "bk_biz_id": 5016913,
                    "display_name": "nf/nf.pushsvr",
                    "alert_query_fields": [
                        {
                            "keys": ["event.target"],
                            "value": "nf:nf.pushsvr",
                            "condition": "or"
                        },
                        {
                            "keys": ["tags.service_name"],
                            "value": "nf.pushsvr",
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

## 五、前端使用指南

### 5.1 alert_query_fields 结构说明

每个实例的 `alert_query_fields` 是一个数组，数组内各元素之间为**"或"关系**（任一命中即匹配该实例的关联告警）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `keys` | `string[]` | AlertDocument 中可查询的字段列表，同组内逻辑关系由 `condition` 决定 |
| `value` | `string` | 后端已渲染好的查询值，直接使用即可 |
| `condition` | `string` | 同组 keys 之间的逻辑关系：`"or"`（任一命中即匹配）或 `"and"`（必须同时满足） |

**condition 使用场景：**
- `"or"`（默认）：同组内任一 key 命中即匹配，适用于同一实例 ID 可能存储在不同字段的场景
- `"and"`：同组内所有 key 必须同时满足，适用于 K8S 维度（node/service/pod）的集群过滤条件——必须先匹配到正确的集群，再匹配节点/服务/Pod 名称，避免跨集群误匹配

### 5.2 转换为告警列表接口 conditions

告警列表接口的 `conditions` 标准格式为：

```json
{
    "key": "字段名",
    "value": ["值1", "值2"],
    "method": "eq",
    "condition": "or"
}
```

**展开规则**：每个 `key` 生成一条独立的 condition，相同 key 的 value 合并为一个数组。

### 5.3 转换示例

**简单维度（condition: "or"）**：

alert_query_fields：

```json
[
    {
        "keys": ["event.bk_host_id", "tags.bk_host_id"],
        "value": "9185731",
        "condition": "or"
    }
]
```

展开后的 conditions（同组内 keys 为"或"关系，各自独立生成 condition）：

```json
[
    {
        "key": "event.bk_host_id",
        "value": ["9185731"],
        "method": "eq",
        "condition": "or"
    },
    {
        "key": "tags.bk_host_id",
        "value": ["9185731"],
        "method": "eq",
        "condition": "or"
    }
]
```

**K8S 维度（含 condition: "and" 集群过滤）**：

alert_query_fields：

```json
[
    {
        "keys": ["tags.bcs_cluster_id"],
        "value": "BCS-K8S-26322",
        "condition": "and"
    },
    {
        "keys": ["event.target", "tags.node", "tags.node_name"],
        "value": "21.249.64.16",
        "condition": "or"
    }
]
```

展开后的 conditions：

```json
[
    {
        "key": "tags.bcs_cluster_id",
        "value": ["BCS-K8S-26322"],
        "method": "eq",
        "condition": "and"
    },
    {
        "key": "event.target",
        "value": ["21.249.64.16"],
        "method": "eq",
        "condition": "or"
    },
    {
        "key": "tags.node",
        "value": ["21.249.64.16"],
        "method": "eq",
        "condition": "or"
    },
    {
        "key": "tags.node_name",
        "value": ["21.249.64.16"],
        "method": "eq",
        "condition": "or"
    }
]
```

> `condition: "and"` 的集群条件与 `condition: "or"` 的节点条件之间，由后端组合为 `bool(must=[cluster_filter], should=[node_filters])` 结构。

### 5.4 多实例合并查询

当查询某个维度下所有实例的关联告警时，将多个实例的相同 key 的 value 合并：

实例 1：`{"keys": ["event.bk_host_id", "tags.bk_host_id"], "value": "9185731", "condition": "or"}`

实例 2：`{"keys": ["event.bk_host_id", "tags.bk_host_id"], "value": "10692392", "condition": "or"}`

合并结果：

```json
[
    {
        "key": "event.bk_host_id",
        "value": ["9185731", "10692392"],
        "method": "eq",
        "condition": "or"
    },
    {
        "key": "tags.bk_host_id",
        "value": ["9185731", "10692392"],
        "method": "eq",
        "condition": "or"
    }
]
```


### 5.5 注意事项

1. **value 已预渲染**：后端已将占位符替换为实例的实际值（如 `set|5017605`、`nf:nf.pushsvr`），前端无需做任何值转换
2. **所有 condition 之间是"或"关系**：告警命中任一字段即视为该维度的关联告警
3. **跨维度查询需合并 conditions**：将各维度的 conditions 合并到同一个请求即可，接口层面的 conditions 之间默认也是"或"关系
4. **condition 字段控制同组 keys 间的逻辑**：`"or"` 表示同组内任一命中即可，`"and"` 表示必须同时满足（K8S 维度的集群过滤）
5. **apm_app 的 `query_string` 类型**：`keys` 为 `["query_string"]` 时，`value` 是 Lucene query_string 表达式（如 `event.target:nf\:*`），需后端走 `query_string` 查询而非 term 查询
6. **告警查询接口无需改动**——`AlertQueryHandler.parse_condition_item()` 已支持 `event.*` 顶层查询和 `tags.*` nested 查询