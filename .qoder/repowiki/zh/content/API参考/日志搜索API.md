# 日志搜索API

<cite>
**本文档引用的文件**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py)
- [urls.py](file://bklog/apps/log_search/urls.py)
- [serializers.py](file://bklog/apps/log_search/serializers.py)
- [models.py](file://bklog/apps/log_search/models.py)
- [search_handlers_esquery.py](file://bklog/apps/log_search/handlers/search/search_handlers_esquery.py)
- [constants.py](file://bklog/apps/log_search/constants.py)
- [async_export_handlers.py](file://bklog/apps/log_search/handlers/search/async_export_handlers.py)
- [base.py](file://bklog/apps/log_unifyquery/handler/base.py)
</cite>

## 目录
1. [索引集管理](#索引集管理)
2. [检索查询](#检索查询)
3. [字段分析](#字段分析)
4. [聚合统计](#聚合统计)
5. [认证与权限控制](#认证与权限控制)
6. [异步导出功能](#异步导出功能)
7. [错误处理机制](#错误处理机制)

## 索引集管理

索引集管理API提供了对用户有权限的索引集列表的访问。通过该API，用户可以获取其在特定空间下的所有索引集信息。

### 获取索引集列表

**HTTP方法**: `GET`

**URL路径**: `/search/index_set/`

**请求参数**:
- `space_uid` (String): 空间唯一标识
- `is_group` (Boolean): 是否分组展示，默认为`false`

**响应格式**:
```json
{
    "message": "",
    "code": 0,
    "data": [
        {
            "index_set_id": 1,
            "index_set_name": "索引集名称",
            "scenario_id": "接入场景",
            "scenario_name": "接入场景名称",
            "storage_cluster_id": "存储集群ID",
            "indices": [
                {
                    "result_table_id": "结果表id",
                    "result_table_name": "结果表名称"
                }
            ],
            "time_field": "dtEventTimeStamp",
            "time_field_type": "date",
            "time_field_unit": "microsecond",
            "tags": [{"name": "test", "color": "xxx"}],
            "is_favorite": true
        }
    ],
    "result": true
}
```

**示例请求**:
```http
GET /search/index_set/?space_uid=space-123&is_group=false
```

**示例响应**:
```json
{
    "message": "",
    "code": 0,
    "data": [
        {
            "index_set_id": 1,
            "index_set_name": "应用日志",
            "scenario_id": "log",
            "scenario_name": "采集接入",
            "storage_cluster_id": 1,
            "indices": [
                {
                    "result_table_id": "2_bklog.0001",
                    "result_table_name": "应用日志表"
                }
            ],
            "time_field": "dtEventTimeStamp",
            "time_field_type": "date",
            "time_field_unit": "microsecond",
            "tags": [],
            "is_favorite": false
        }
    ],
    "result": true
}
```

**Section sources**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py#L174-L256)

## 检索查询

检索查询API提供了全文检索、条件过滤等功能，支持多种查询条件和分页参数。

### 执行全文检索

**HTTP方法**: `POST`

**URL路径**: `/search/index_set/{index_set_id}/search/`

**请求参数**:
- `start_time` (String): 开始时间
- `end_time` (String): 结束时间
- `time_range` (String): 时间标识符 ["15m", "30m", "1h", "4h", "12h", "1d", "customized"]
- `keyword` (String): 搜索关键字
- `ip_chooser` (Json): IP列表
- `addition` (Json): 搜索条件
- `begin` (Int): 起始位置
- `size` (Int): 条数
- `aggs` (Dict): ES的聚合参数（非必填，默认为{}）

**请求体结构**:
```json
{
    "start_time": "2019-06-11 00:00:00",
    "end_time": "2019-06-12 11:11:11",
    "time_range": "customized",
    "keyword": "error",
    "ip_chooser": {
        "modules": [
            {
                "bk_obj_id": "module",
                "bk_inst_id": 4
            }
        ],
        "ips": "127.0.0.1, 127.0.0.2"
    },
    "addition": [
        {
            "key": "ip",
            "method": "is",
            "value": "127.0.0.1",
            "condition": "and",
            "type": "field"
        }
    ],
    "begin": 0,
    "size": 15
}
```

**响应格式**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "total": 100,
        "took": 0.29,
        "list": [
            {
                "srcDataId": "2087",
                "dtEventTimeStamp": 1534825132000,
                "moduleName": "公共组件->consul",
                "log": "is_cluster</em>-COMMON: ok",
                "sequence": 1,
                "dtEventTime": "2018-08-21 04:18:52",
                "timestamp": 1534825132,
                "serverIp": "127.0.0.1",
                "errorCode": "0",
                "gseIndex": 152358,
                "dstDataId": "2087",
                "worldId": "-1",
                "logTime": "2018-08-21 12:18:52",
                "path": "/tmp/health_check.log",
                "platId": 0,
                "localTime": "2018-08-21 04:18:00"
            }
        ],
        "fields": {
            "agent": {
                "max_length": 101
            },
            "bytes": {
                "max_length": 4
            }
        }
    },
    "result": true
}
```

**示例请求**:
```http
POST /search/index_set/1/search/
Content-Type: application/json

{
    "start_time": "2019-06-11 00:00:00",
    "end_time": "2019-06-12 11:11:11",
    "time_range": "customized",
    "keyword": "error",
    "ip_chooser": {
        "modules": [
            {
                "bk_obj_id": "module",
                "bk_inst_id": 4
            }
        ],
        "ips": "127.0.0.1, 127.0.0.2"
    },
    "addition": [
        {
            "key": "ip",
            "method": "is",
            "value": "127.0.0.1",
            "condition": "and",
            "type": "field"
        }
    ],
    "begin": 0,
    "size": 15
}
```

**示例响应**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "total": 50,
        "took": 0.15,
        "list": [
            {
                "srcDataId": "2087",
                "dtEventTimeStamp": 1534825132000,
                "moduleName": "公共组件->consul",
                "log": "error occurred",
                "sequence": 1,
                "dtEventTime": "2018-08-21 04:18:52",
                "timestamp": 1534825132,
                "serverIp": "127.0.0.1",
                "errorCode": "500",
                "gseIndex": 152358,
                "dstDataId": "2087",
                "worldId": "-1",
                "logTime": "2018-08-21 12:18:52",
                "path": "/tmp/error.log",
                "platId": 0,
                "localTime": "2018-08-21 04:18:00"
            }
        ],
        "fields": {
            "log": {
                "max_length": 200
            },
            "errorCode": {
                "max_length": 3
            }
        }
    },
    "result": true
}
```

**Section sources**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py#L280-L378)
- [serializers.py](file://bklog/apps/log_search/serializers.py#L286-L334)

## 字段分析

字段分析API提供了对索引集字段的详细信息查询，包括字段名称、类型、是否可显示等。

### 获取字段信息

**HTTP方法**: `GET`

**URL路径**: `/search/index_set/{index_set_id}/fields/`

**请求参数**:
- `start_time` (String): 开始时间（非必填）
- `end_time` (String): 结束时间（非必填）
- `scope` (String): 类型 ["default", "search_context"]
- `is_realtime` (Boolean): 是否实时
- `custom_indices` (String): 自定义索引

**响应格式**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "config": [
            {
                "name": "bcs_web_console",
                "is_active": true
            },
            {
                "name": "bkmonitor",
                "is_active": true
            },
            {
                "name": "ip_topo_switch",
                "is_active": true
            },
            {
                "name": "async_export",
                "is_active": true,
                "extra": {
                    "fields": ["dtEventTimeStamp", "serverIp", "gseIndex", "iterationIndex"],
                    "usable_reason": ""
                }
            },
            {
                "name": "context_and_realtime",
                "is_active": true,
                "extra": {
                    "reason": ""
                }
            },
            {
                "name": "trace",
                "is_active": true,
                "extra": {
                    "field": "trace_id",
                    "index_set_name": "test_stag_oltp"
                }
            }
        ],
        "display_fields": ["dtEventTimeStamp", "log"],
        "fields": [
            {
                "field_name": "log",
                "field_alias": "日志",
                "field_type": "text",
                "is_display": true,
                "is_editable": true,
                "description": "日志",
                "es_doc_values": false
            },
            {
                "field_name": "dtEventTimeStamp",
                "field_alias": "时间",
                "field_type": "date",
                "is_display": true,
                "is_editable": true,
                "description": "描述",
                "es_doc_values": true
            }
        ],
        "sort_list": [
            ["aaa", "desc"],
            ["bbb", "asc"]
        ]
    },
    "result": true
}
```

**示例请求**:
```http
GET /search/index_set/1/fields/?scope=search_context
```

**示例响应**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "config": [
            {
                "name": "bcs_web_console",
                "is_active": true
            },
            {
                "name": "bkmonitor",
                "is_active": true
            },
            {
                "name": "ip_topo_switch",
                "is_active": true
            },
            {
                "name": "async_export",
                "is_active": true,
                "extra": {
                    "fields": ["dtEventTimeStamp", "serverIp", "gseIndex", "iterationIndex"],
                    "usable_reason": ""
                }
            },
            {
                "name": "context_and_realtime",
                "is_active": true,
                "extra": {
                    "reason": ""
                }
            },
            {
                "name": "trace",
                "is_active": true,
                "extra": {
                    "field": "trace_id",
                    "index_set_name": "test_stag_oltp"
                }
            }
        ],
        "display_fields": ["dtEventTimeStamp", "log"],
        "fields": [
            {
                "field_name": "log",
                "field_alias": "日志",
                "field_type": "text",
                "is_display": true,
                "is_editable": true,
                "description": "日志内容",
                "es_doc_values": false
            },
            {
                "field_name": "dtEventTimeStamp",
                "field_alias": "时间",
                "field_type": "date",
                "is_display": true,
                "is_editable": true,
                "description": "事件时间戳",
                "es_doc_values": true
            }
        ],
        "sort_list": [
            ["dtEventTimeStamp", "desc"]
        ]
    },
    "result": true
}
```

**Section sources**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py#L974-L1104)
- [serializers.py](file://bklog/apps/log_search/serializers.py#L342-L349)

## 聚合统计

聚合统计API提供了对日志数据的聚合分析功能，支持terms和date_histogram两种聚合方式。

### Terms聚合

**HTTP方法**: `POST`

**URL路径**: `/search/index_set/{index_set_id}/aggs/terms`

**请求参数**:
- `field` (String): 聚合字段
- `size` (Int): 返回结果数量

**请求体结构**:
```json
{
    "field": "errorCode",
    "size": 10
}
```

**响应格式**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "buckets": [
            {
                "key": "500",
                "doc_count": 150
            },
            {
                "key": "404",
                "doc_count": 80
            }
        ]
    },
    "result": true
}
```

**示例请求**:
```http
POST /search/index_set/1/aggs/terms
Content-Type: application/json

{
    "field": "errorCode",
    "size": 10
}
```

**示例响应**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "buckets": [
            {
                "key": "500",
                "doc_count": 150
            },
            {
                "key": "404",
                "doc_count": 80
            },
            {
                "key": "200",
                "doc_count": 500
            }
        ]
    },
    "result": true
}
```

### Date Histogram聚合

**HTTP方法**: `POST`

**URL路径**: `/search/index_set/{index_set_id}/aggs/date_histogram`

**请求参数**:
- `interval` (String): 聚合间隔 ["1m", "5m", "1h", "1d"]
- `field` (String): 时间字段

**请求体结构**:
```json
{
    "interval": "1h",
    "field": "dtEventTimeStamp"
}
```

**响应格式**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "buckets": [
            {
                "key_as_string": "2019-06-11T00:00:00.000Z",
                "key": 1560211200000,
                "doc_count": 25
            },
            {
                "key_as_string": "2019-06-11T01:00:00.000Z",
                "key": 1560214800000,
                "doc_count": 30
            }
        ]
    },
    "result": true
}
```

**示例请求**:
```http
POST /search/index_set/1/aggs/date_histogram
Content-Type: application/json

{
    "interval": "1h",
    "field": "dtEventTimeStamp"
}
```

**示例响应**:
```json
{
    "message": "",
    "code": 0,
    "data": {
        "buckets": [
            {
                "key_as_string": "2019-06-11T00:00:00.000Z",
                "key": 1560211200000,
                "doc_count": 25
            },
            {
                "key_as_string": "2019-06-11T01:00:00.000Z",
                "key": 1560214800000,
                "doc_count": 30
            },
            {
                "key_as_string": "2019-06-11T02:00:00.000Z",
                "key": 1560218400000,
                "doc_count": 20
            }
        ]
    },
    "result": true
}
```

**Section sources**
- [instance.py](file://bklog/apps/log_audit/instance.py#L150-L151)
- [serializers.py](file://bklog/apps/log_search/serializers.py)

## 认证与权限控制

日志搜索API采用API网关鉴权和IAM资源权限进行认证和权限控制。

### API网关鉴权

API网关鉴权通过在请求头中添加特定的认证信息来实现。系统会验证请求来源的应用是否在白名单中。

**认证流程**:
1. 请求到达API网关
2. API网关验证应用代码（bk_app_code）是否在白名单中
3. 如果应用在白名单中，则跳过IAM权限检查
4. 如果应用不在白名单中，则进行IAM权限检查

### IAM资源权限

IAM资源权限控制基于蓝鲸权限中心，通过Action和Resource进行权限管理。

**权限定义**:
- **Action**: SEARCH_LOG - 搜索日志权限
- **Resource**: INDICES - 索引集资源

**权限检查**:
```python
def get_permissions(self):
    if settings.BKAPP_IS_BKLOG_API:
        auth_info = Permission.get_auth_info(self.request, raise_exception=False)
        if auth_info and auth_info["bk_app_code"] in settings.ESQUERY_WHITE_LIST:
            return []
    
    if self.action in ["search", "context", "tailf", "export", "fields"]:
        return [InstanceActionPermission([ActionEnum.SEARCH_LOG], ResourceEnum.INDICES)]
```

**权限验证流程**:
1. 系统首先检查是否为后台部署模式
2. 如果是后台部署模式，检查应用是否在ESQUERY白名单中
3. 如果应用在白名单中，则不需要进行IAM权限检查
4. 对于需要权限的API操作，系统会检查用户是否具有SEARCH_LOG操作权限
5. 权限检查通过后，用户才能访问相应的API

**Section sources**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py#L133-L172)
- [models.py](file://bklog/apps/log_search/models.py)

## 异步导出功能

异步导出功能允许用户提交导出任务，并在后台处理完成后通过通知获取结果。

### 创建导出任务

**HTTP方法**: `POST`

**URL路径**: `/search/index_set/{index_set_id}/async_export/`

**请求参数**:
- `bk_biz_id` (Int): 业务id
- `keyword` (String): 搜索关键字
- `time_range` (String): 时间范围
- `start_time` (String): 起始时间
- `end_time` (String): 结束时间
- `host_scopes` (Dict): 检索模块ip等信息
- `begin` (Int): 检索开始 offset
- `size` (Int): 检索结果大小
- `interval` (String): 匹配规则
- `isTrusted` (Boolean): 是否可信

**请求体结构**:
```json
{
    "bk_biz_id": "215",
    "keyword": "*",
    "time_range": "5m",
    "start_time": "2021-06-08 11:02:21",
    "end_time": "2021-06-08 11:07:21",
    "host_scopes": {
        "modules": [],
        "ips": ""
    },
    "addition": [],
    "begin": 0,
    "size": 188,
    "interval": "auto",
    "isTrusted": true
}
```

**响应格式**:
```json
{
    "result": true,
    "data": {
        "task_id": 1,
        "prompt": "任务提交成功，预估等待时间{time}分钟,系统处理后将通过{notify_type_name}通知，请留意！"
    },
    "code": 0,
    "message": ""
}
```

**示例请求**:
```http
POST /search/index_set/1/async_export/
Content-Type: application/json

{
    "bk_biz_id": "215",
    "keyword": "*",
    "time_range": "5m",
    "start_time": "2021-06-08 11:02:21",
    "end_time": "2021-06-08 11:07:21",
    "host_scopes": {
        "modules": [],
        "ips": ""
    },
    "addition": [],
    "begin": 0,
    "size": 188,
    "interval": "auto",
    "isTrusted": true
}
```

**示例响应**:
```json
{
    "result": true,
    "data": {
        "task_id": 1,
        "prompt": "任务提交成功，预估等待时间2分钟,系统处理后将通过邮件通知，请留意！"
    },
    "code": 0,
    "message": ""
}
```

### 查询导出状态

**HTTP方法**: `GET`

**URL路径**: `/search/index_set/{index_set_id}/export_history/`

**请求参数**:
- `page` (Int): 当前页
- `pagesize` (Int): 页面大小
- `show_all` (Boolean): 是否展示所有历史
- `bk_biz_id` (Int): 业务id

**响应格式**:
```json
{
    "result": true,
    "data": {
        "total": 10,
        "list": [
            {
                "id": 1,
                "log_index_set_id": 1,
                "search_dict": "",
                "start_time": "",
                "end_time": "",
                "export_type": "",
                "export_status": "",
                "error_msg": "",
                "download_url": "",
                "export_pkg_name": "",
                "export_pkg_size": 1,
                "export_created_at": "",
                "export_created_by": "",
                "export_completed_at": "",
                "download_able": true,
                "retry_able": true
            }
        ]
    },
    "code": 0,
    "message": ""
}
```

**示例请求**:
```http
GET /search/index_set/1/export_history/?page=1&pagesize=10&show_all=false&bk_biz_id=215
```

**示例响应**:
```json
{
    "result": true,
    "data": {
        "total": 1,
        "list": [
            {
                "id": 1,
                "log_index_set_id": 1,
                "search_dict": "{\"keyword\": \"*\", \"time_range\": \"5m\"}",
                "start_time": "2021-06-08 11:02:21",
                "end_time": "2021-06-08 11:07:21",
                "export_type": "async",
                "export_status": "success",
                "error_msg": "",
                "download_url": "https://example.com/download/1.zip",
                "export_pkg_name": "export_1.zip",
                "export_pkg_size": 5,
                "export_created_at": "2021-06-08 11:08:00",
                "export_created_by": "admin",
                "export_completed_at": "2021-06-08 11:10:00",
                "download_able": true,
                "retry_able": false
            }
        ]
    },
    "code": 0,
    "message": ""
}
```

**Section sources**
- [search_views.py](file://bklog/apps/log_search/views/search_views.py#L730-L816)
- [async_export_handlers.py](file://bklog/apps/log_search/handlers/search/async_export_handlers.py)

## 错误处理机制

日志搜索API提供了完善的错误处理机制，能够识别和处理各种常见的错误情况。

### 常见错误码

| 错误码 | 错误信息 | 解决方案 |
|--------|---------|---------|
| INDEX_SET_NOT_EXISTED | 索引集不存在 | 检查索引集ID是否正确，确认索引集是否存在 |
| QUERY_SYNTAX_ERROR | 查询语法错误 | 检查查询语句的语法，确保符合Lucene查询语法规范 |
| SEARCH_EXCEED_MAX_SIZE | 查询数量超出限制 | 减少查询的size参数，或使用分页查询 |
| PRE_CHECK_ASYNC_EXPORT | 异步导出预检查失败 | 检查查询条件是否有效，确认索引集状态正常 |
| MISS_ASYNC_EXPORT | 缺少异步导出必需字段 | 确保查询包含了异步导出必需的字段，如时间戳、IP等 |
| BASE_SEARCH_INDEX_SET_EXCEPTION | 索引集异常 | 检查索引集配置，确认索引集状态是否正常 |

### 错误处理流程

1. **异常捕获**: 系统在执行查询时会捕获各种异常
2. **错误分类**: 根据异常类型进行分类处理
3. **错误信息返回**: 将错误信息以标准格式返回给客户端
4. **日志记录**: 记录错误日志，便于后续排查

**错误响应格式**:
```json
{
    "result": false,
    "data": null,
    "code": 10001,
    "message": "索引集不存在"
}
```

**错误处理示例**:
```python
def search(self, request, index_set_id=None):
    try:
        data = self.params_valid(SearchAttrSerializer)
        # 执行搜索逻辑
        result = search_handler.search()
        return Response(result)
    except BaseSearchIndexSetException as e:
        return Response({
            "result": False,
            "data": None,
            "code": 10001,
            "message": "索引集不存在"
        })
    except ESQuerySyntaxException as e:
        return Response({
            "result": False,
            "data": None,
            "code": 10002,
            "message": "查询语法错误"
        })
    except Exception as e:
        logger.exception("搜索异常: %s", e)
        return Response({
            "result": False,
            "data": None,
            "code": 500,
            "message": "服务器内部错误"
        })
```

**Section sources**
- [constants.py](file://bklog/apps/log_search/constants.py)
- [exceptions.py](file://bklog/apps/log_search/exceptions.py)