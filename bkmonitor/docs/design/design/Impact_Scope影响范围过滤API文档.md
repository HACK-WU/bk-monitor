# Impact Scope 影响范围过滤 — 前端 API 文档

## 接口地址

`POST /api/v1/issue/search/`

## 过滤方式

影响范围过滤通过 `conditions` 参数传递，支持两个层级：

| 层级 | 用途 | conditions key 格式 | 说明 |
|------|------|-------------------|------|
| **维度级** | 过滤包含某类维度的 Issue | `impact_dimensions` | 如"有主机影响范围的 Issue" |
| **实例级** | 过滤影响了某个具体实例的 Issue | `impact_scope.{维度}.{ID字段}` | 如"影响了某台主机的 Issue" |

---

## 一、维度级过滤

判断 Issue 是否包含某个维度类型的影响范围。

### 参数格式

```json
{
    "key": "impact_dimensions",
    "value": ["维度key1", "维度key2"],
    "method": "eq"
}
```

- `value` 为维度 key 数组，多个维度之间为 **OR** 关系（包含任一即命中）

### 请求示例

**过滤包含 host 或 cluster 维度的 Issue：**

```json
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

---

## 二、实例 ID 级过滤

按具体实例 ID 精确过滤 Issue。

### 参数格式

```json
{
    "key": "impact_scope.{维度key}.{ID字段名}",
    "value": ["实例ID1", "实例ID2"],
    "method": "eq"
}
```

- `value` 为实例 ID 数组，多个 ID 之间为 **OR** 关系（匹配任一即命中）
- **⚠️ 所有 value 必须传字符串类型**，即使原始数据是整数（如 `bk_host_id`），也需要传 `"9185731"` 而非 `9185731`

### ⚠️ conditions key 是动态构建的

**重要**：`impact_scope.host.bk_host_id` 中的 `host` 和 `bk_host_id` 都不是固定值，需要根据 `impact_scope` 的实际结构动态获取：

| 部分 | 来源 | 说明 |
|------|------|------|
| `host` | `impact_scope` 对象的第一层 key | 维度名称，如 `set`、`host`、`cluster`、`apm_service` 等 |
| `bk_host_id` | `instance_list` 元素的第一个 key（除 `display_name` 外） | 该维度的实例 ID 字段名 |

**构建规则**：
1. 从 `impact_scope` 对象中获取维度 key（如 `host`）
2. 从该维度的 `instance_list` 数组中取第一个元素
3. 获取该元素中除 `display_name` 外的第一个 key 作为 ID 字段名
4. 组合成 `impact_scope.{维度key}.{ID字段名}`

**示例说明**：

```json
{
    "impact_scope": {
        "host": {
            "count": 3,
            "display_name": "主机",
            "instance_list": [
                {"bk_host_id": 9185731, "display_name": "21.249.64.16"},
                {"bk_host_id": 10692392, "display_name": "21.186.179.6"}
            ],
            "link_tpl": "/performance/detail/{bk_host_id}"
        },
        "cluster": {
            "count": 2,
            "display_name": "bcs集群",
            "instance_list": [
                {"bcs_cluster_id": "BCS-K8S-26322", "display_name": "测试集群"},
                {"bcs_cluster_id": "BCS-K8S-41193", "display_name": "生产集群"}
            ],
            "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}"
        },
        "apm_service": {
            "count": 1,
            "display_name": "apm_service",
            "instance_list": [
                {"app_name": "nf", "service_name": "nf.pushsvr", "bk_biz_id": 5016913, "display_name": "nf/nf.pushsvr"}
            ],
            "link_tpl": "?bizId={bk_biz_id}#/apm/service?..."
        }
    }
}
```

根据上述结构，各维度的 conditions key 如下：

| 维度 | ID 字段名（从 instance_list 元素获取） | conditions key |
|------|----------------------------------------|----------------|
| `host` | `bk_host_id` | `impact_scope.host.bk_host_id` |
| `cluster` | `bcs_cluster_id` | `impact_scope.cluster.bcs_cluster_id` |
| `apm_service` | `app_name`（第一个非 display_name 字段） | `impact_scope.apm_service.app_name` |

> **注意**：`apm_service` 维度的 `instance_list` 元素包含多个 ID 字段（`app_name`、`service_name`、`bk_biz_id`），取第一个非 `display_name` 字段作为 ID 字段名。

### 请求示例

**过滤影响了指定主机的 Issue：**

```json
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

**过滤影响了指定 BCS 集群的 Issue：**

```json
{
    "bk_biz_ids": [2],
    "conditions": [
        {
            "key": "impact_scope.cluster.bcs_cluster_id",
            "value": ["BCS-K8S-26322", "BCS-K8S-41193"],
            "method": "eq"
        }
    ],
    "page": 1,
    "page_size": 20
}
```

---

## 三、可用的 conditions key 一览

> **重要**：以下 conditions key 中的维度名称和 ID 字段名均为**动态获取**，需根据 `impact_scope` 实际结构构建。表中示例仅供参考，实际使用时请根据数据结构动态拼接。

### 维度级

| key | value 示例 | 说明 |
|-----|-----------|------|
| `impact_dimensions` | `["host"]` / `["host", "cluster"]` | 过滤包含指定维度的 Issue，多值 OR |

### 实例级

| conditions key | value 示例 | 说明 |
|---------------|-----------|------|
| `impact_scope.set.set_id` | `["5179871"]` | 按 CMDB 集群（Set）ID 过滤 |
| `impact_scope.host.bk_host_id` | `["9185731"]` | 按主机 ID 过滤 |
| `impact_scope.service_instances.bk_service_instance_id` | `["12345"]` | 按服务实例 ID 过滤 |
| `impact_scope.cluster.bcs_cluster_id` | `["BCS-K8S-00001"]` | 按 BCS 集群 ID 过滤 |
| `impact_scope.node.node` | `["node-01"]` | 按 K8S 节点名过滤 |
| `impact_scope.service.service` | `["svc-01"]` | 按 K8S Service 名过滤 |
| `impact_scope.pod.pod` | `["pod-01"]` | 按 K8S Pod 名过滤 |
| `impact_scope.apm_app.app_name` | `["my-app"]` | 按 APM 应用名过滤 |
| `impact_scope.apm_service.app_name` | `["nf"]` | 按 APM 应用名过滤（取 instance_list 元素的第一个非 display_name 字段） |

> **构建方式**：`impact_scope.{维度key}.{instance_list元素的ID字段名}`

---

## 四、可用的维度 key 枚举

| 维度 key | 中文名 | 适用场景 |
|---------|--------|---------|
| `set` | 集群 | CMDB 集群 |
| `host` | 主机 | CMDB 主机 |
| `service_instances` | 服务实例 | CMDB 服务实例 |
| `cluster` | BCS集群 | K8S BCS 集群 |
| `node` | Node | K8S 节点 |
| `service` | Service | K8S Service |
| `pod` | Pod | K8S Pod |
| `apm_app` | APM应用 | APM 应用 |
| `apm_service` | APM服务 | APM 服务 |

---

## 五、组合使用

影响范围过滤可与其他 conditions（如 `priority`、`status` 等）自由组合，所有 conditions 之间为 **AND** 关系。

```json
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

---

## 六、注意事项

1. **value 必须为字符串数组**：所有实例级过滤的 value 都必须传字符串，后端会统一做类型转换，但前端应确保传入字符串以避免类型不匹配。
2. **维度级过滤为 OR 语义**：`impact_dimensions` 的 value 中多个维度是"包含任一即命中"。
3. **实例级过滤为 OR 语义**：同一个 condition 中多个实例 ID 是"匹配任一即命中"。
4. **多个 conditions 之间为 AND 语义**：不同 condition 项之间是"同时满足"。

---

## 七、IssueDocument impact_scope 字段示例

以下是 IssueDocument 中 `impact_scope` 字段的完整结构示例：

```json
{
    "impact_scope": {
        "set": {
            "count": 3,
            "display_name": "集群",
            "instance_list": [
                {"set_id": "5179871", "display_name": "kihan-test/bcs-node-module"},
                {"set_id": "5017605", "display_name": "蓝鲸PaaS平台/BCS-K8S-40340"},
                {"set_id": "5043076", "display_name": "DB数据库生产环境/db.es.es"}
            ],
            "link_tpl": null
        },
        "host": {
            "count": 3,
            "display_name": "主机",
            "instance_list": [
                {"bk_host_id": 9185731, "display_name": "21.249.64.16"},
                {"bk_host_id": 10692392, "display_name": "21.186.179.6"},
                {"bk_host_id": 1804751, "display_name": "11.181.33.209"}
            ],
            "link_tpl": "/performance/detail/{bk_host_id}"
        },
        "service_instances": {
            "count": 1,
            "display_name": "服务实例",
            "instance_list": [
                {"bk_service_instance_id": 14041299, "display_name": "11.181.33.209_es-es_datanode_9200"}
            ],
            "link_tpl": null
        },
        "cluster": {
            "count": 3,
            "display_name": "bcs集群",
            "instance_list": [
                {"bcs_cluster_id": "BCS-K8S-26322", "display_name": "TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)"},
                {"bcs_cluster_id": "BCS-K8S-41193", "display_name": "南京三集群-业务安全-V1.26.1(BCS-K8S-41193)"},
                {"bcs_cluster_id": "BCS-K8S-41797", "display_name": "kihan-test-gz-0611(BCS-K8S-41797)"}
            ],
            "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview"
        },
        "apm_service": {
            "count": 1,
            "display_name": "apm_service",
            "instance_list": [
                {"app_name": "nf", "service_name": "nf.pushsvr", "bk_biz_id": 5016913, "display_name": "nf/nf.pushsvr"}
            ],
            "link_tpl": "?bizId={bk_biz_id}#/apm/service?filter-app_name={app_name}&filter-service_name={service_name}"
        }
    }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | `int` | 该维度受影响实例总数（去重后） |
| `display_name` | `string` | 维度的中文展示名称 |
| `instance_list` | `object[]` | 实例列表，最多 50 条 |
| `link_tpl` | `string \| null` | 前端跳转链接模板，支持占位符替换 |

### 各维度 instance_list 元素字段

> **重要**：以下 ID 字段名为 `instance_list` 元素中除 `display_name` 外的字段名称，需从实际数据中动态获取。

| 维度 key | ID 字段 | 说明 |
|---------|---------|------|
| `set` | `set_id` | CMDB 集群 ID |
| `host` | `bk_host_id` | 主机 ID |
| `service_instances` | `bk_service_instance_id` | 服务实例 ID |
| `cluster` | `bcs_cluster_id` | BCS 集群 ID |
| `node` | `node` | K8S 节点名 |
| `service` | `service` | K8S Service 名 |
| `pod` | `pod` | K8S Pod 名 |
| `apm_app` | `app_name` | APM 应用名 |
| `apm_service` | `app_name`, `service_name` | APM 应用名和服务名（取第一个非 display_name 字段） |

> **注意**：
> - 每个维度都是可选的，仅当存在对应类型的影响范围时才返回
> - `cluster`/`node`/`service`/`pod` 互斥：多集群时返回 `cluster`，单集群时返回 `node`/`service`/`pod`
> - `apm_app`/`apm_service` 互斥：多应用时返回 `apm_app`，单应用时返回 `apm_service`
> - 若 Issue 无任何影响范围信息，`impact_scope` 为空对象 `{}`
