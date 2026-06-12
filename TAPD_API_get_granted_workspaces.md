# TAPD 开放平台 API - 获取应用已授权项目

> 原文档地址: https://o.tapd.woa.com/document/api-doc/API%E6%96%87%E6%A1%A3/api_reference/workspace/get_granted_workspaces.html

## 接口信息

| 项           | 内容                                                            |
|--------------|-----------------------------------------------------------------|
| **接口名称** | 获取应用已授权项目                                              |
| **接口路径** | `/app_auth/get_granted_workspaces`                              |
| **完整 URL** | `http://apiv2.tapd.woa.com/app_auth/get_granted_workspaces`     |
| **请求方式** | GET                                                             |
| **支持格式** | JSON / XML（默认 JSON）                                         |
| **请求数限制** | 默认返回 30 条。可通过传 `limit` 参数设置，最大取 200。也可以传 `page` 参数翻页。 |

## SDK 方法名

- **Node.js**: `getGrantedWorkspaces`
- **Python**: `get_granted_workspaces`
- **Golang**: `GetGrantedWorkspaces`

---

## 请求参数

| 参数名       | 必选 | 类型     | 说明     |
|--------------|------|----------|----------|
| `workspace_id` | 否   | `integer` | 项目 ID，用于筛选指定项目是否已授权 |
| `type`         | 否   | `integer` | 安装类型：`0` 应用商店安装，`1` 测试安装，`2` 插件安装 |
| `created`      | 否   | `datetime`| 创建时间，支持时间查询 |
| `limit`        | 否   | `integer` | 设置返回数量限制，默认为 `30`，最大 `200` |
| `page`         | 否   | `integer` | 返回当前数量限制下第 N 页的数据，默认为 `1`（第一页） |
| `order`        | 否   | `string`  | 排序规则，格式：`字段名 ASC` 或 `字段名 DESC`，需要使用 URL encode。例如按创建时间逆序：`order=created%20desc` |
| `fields`       | 否   | `string`  | 设置获取的字段，多个字段间以逗号 `,` 隔开 |

---

## 调用示例

### 1. 获取应用已授权项目列表

#### Curl - Basic Auth

```bash
curl -u 'api_user:api_password' \
  'http://apiv2.tapd.woa.com/app_auth/get_granted_workspaces'
```

#### Curl - OAuth Access Token

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'http://apiv2.tapd.woa.com/app_auth/get_granted_workspaces'
```

#### 返回结果

```json
{
    "status": 1,
    "data": {
        "list": [
            {
                "OpenOrganizationApp": {
                    "workspace_id": "10104801",
                    "type": "1",
                    "created": "2024-04-02 16:10:30"
                }
            },
            {
                "OpenOrganizationApp": {
                    "workspace_id": "10093721",
                    "type": "1",
                    "created": "2023-06-15 20:00:15"
                }
            },
            {
                "OpenOrganizationApp": {
                    "workspace_id": "10028191",
                    "type": "1",
                    "created": "2023-06-15 20:00:13"
                }
            }
        ],
        "pager": {
            "count": 3,
            "page": 1,
            "limit": 30
        }
    },
    "info": "success"
}
```

---

### 2. 检查项目是否已授权

#### Curl - Basic Auth

```bash
curl -u 'api_user:api_password' \
  'http://apiv2.tapd.woa.com/app_auth/get_granted_workspaces?workspace_id=10104801'
```

#### Curl - OAuth Access Token

```bash
curl -H 'Authorization: Bearer ACCESS_TOKEN' \
  'http://apiv2.tapd.woa.com/app_auth/get_granted_workspaces?workspace_id=10104801'
```

#### 返回结果

```json
{
    "status": 1,
    "data": {
        "list": [
            {
                "OpenOrganizationApp": {
                    "workspace_id": "10104801",
                    "type": "1",
                    "created": "2024-04-02 16:10:30"
                }
            }
        ],
        "pager": {
            "count": 1,
            "page": 1,
            "limit": 30
        }
    },
    "info": "success"
}
```

---

## 返回字段说明

| 字段           | 说明                                |
|----------------|-------------------------------------|
| `workspace_id` | 项目 ID                             |
| `type`         | 安装类型：`0` 应用商店安装，`1` 测试安装，`2` 插件安装 |
| `created`      | 授权创建时间                        |

---

## 响应结构说明

- **status**: 状态码，`1` 表示成功
- **data.list**: 授权项目列表，每一项为 `OpenOrganizationApp` 对象
- **data.pager**: 分页信息
  - `count`: 总条数
  - `page`: 当前页码
  - `limit`: 每页条数
- **info**: 响应描述信息，成功时为 `"success"`
