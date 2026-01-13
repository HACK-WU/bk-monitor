# API网关集成

<cite>
**本文档引用的文件**   
- [definition.yaml](file://support-files/apigw/definition.yaml)
- [resources.yaml](file://support-files/apigw/resources.yaml)
- [apigw.py](file://apps/middleware/apigw.py)
- [middlewares.py](file://apps/middlewares.py)
- [default.py](file://config/default.py)
- [sync_apigw.py](file://apps/api/management/commands/sync_apigw.py)
- [convert_apigw_yaml.py](file://scripts/convert_apigw_yaml.py)
- [bk_log.yaml](file://docs/apidocs/bk_log.yaml)
</cite>

## 目录
1. [API网关配置](#api网关配置)
2. [鉴权机制](#鉴权机制)
3. [请求限流策略](#请求限流策略)
4. [YAML配置文件结构](#yaml配置文件结构)
5. [核心API调用示例](#核心api调用示例)
6. [多环境配置管理](#多环境配置管理)
7. [API版本管理与向后兼容性](#api版本管理与向后兼容性)

## API网关配置

API网关配置主要通过`support-files/apigw/`目录下的`definition.yaml`和`resources.yaml`两个文件进行定义。`definition.yaml`文件定义了网关的基本信息、环境信息、权限授予等全局配置，而`resources.yaml`文件则定义了具体的API资源路由。

网关的基本配置在`definition.yaml`中定义，包括网关描述、是否公开、维护人员等信息。网关的环境配置定义了生产环境的代理设置，包括超时时间和后端服务的负载均衡配置。通过`grant_permissions`配置项，网关可以主动向指定的应用授予访问权限，支持按网关维度或资源维度进行授权。

API资源的同步通过`apps/api/management/commands/sync_apigw.py`中的管理命令实现，该命令会依次执行网关配置同步、环境同步、资源同步、文档同步、版本发布和权限授予等操作，确保网关配置的完整性和一致性。

**Section sources**
- [definition.yaml](file://support-files/apigw/definition.yaml#L1-L138)
- [resources.yaml](file://support-files/apigw/resources.yaml#L1-L3112)
- [sync_apigw.py](file://apps/api/management/commands/sync_apigw.py#L23-L50)

## 鉴权机制

系统实现了基于JWT的API网关鉴权机制，通过`apps/middleware/apigw.py`中的中间件进行处理。鉴权机制支持多种场景，包括内部网关、外部网关和新内部网关，通过不同的公钥进行验证。

鉴权流程首先通过`CustomCachePublicKeyProvider`类根据请求头中的`Is-External`字段和网关名称确定使用的公钥。对于外部网关请求，使用`EXTERNAL_APIGW_PUBLIC_KEY`；对于新内部网关请求，使用`NEW_INTERNAL_APIGW_PUBLIC_KEY`；其他情况则使用默认的公钥提供者。

`ApiGatewayJWTProvider`类负责JWT令牌的解析和验证，从请求的`X-Bkapi-Authorization`头中提取JWT令牌，使用相应的公钥进行解码验证。验证通过后，将解码后的JWT信息存储在请求对象中，供后续的业务逻辑使用。

相关的公钥配置在`config/default.py`中通过环境变量进行设置，包括`EXTERNAL_APIGW_PUBLIC_KEY`、`NEW_INTERNAL_APIGW_NAME`和`NEW_INTERNAL_APIGW_PUBLIC_KEY`等，支持灵活的配置管理。

**Section sources**
- [apigw.py](file://apps/middleware/apigw.py#L60-L124)
- [middlewares.py](file://apps/middlewares.py#L213-L232)
- [default.py](file://config/default.py#L1124-L1131)

## 请求限流策略

API网关通过插件机制实现了请求限流策略，在`resources.yaml`文件中为特定的API资源配置了`bk-rate-limit`插件。限流策略基于令牌桶算法实现，可以针对不同的应用设置不同的限流规则。

在`resources.yaml`中，`esquery_search`、`esquery_dsl`和`esquery_scroll`等查询接口都配置了限流策略。默认情况下，每个应用每秒最多允许200个请求；对于`bkmonitorv3`应用，每分钟最多允许10000个请求。这种分级的限流策略既能保证系统的稳定性，又能满足监控等关键应用的高并发需求。

限流配置以YAML格式定义在`pluginConfigs`字段中，通过`rates`键指定不同应用的限流规则。`__default`表示默认的限流规则，其他键名对应具体的应用代码。每个限流规则包含`tokens`（令牌数量）和`period`（时间周期）两个参数，共同决定了限流的严格程度。

**Section sources**
- [resources.yaml](file://support-files/apigw/resources.yaml#L25-L34)
- [qos.py](file://apps/log_esquery/qos.py#L104-L144)

## YAML配置文件结构

API网关的配置主要由两个YAML文件组成：`definition.yaml`和`resources.yaml`。`definition.yaml`文件定义了网关的全局配置，包括版本信息、网关基本信息、环境配置、权限授予和相关应用等。

`definition.yaml`的结构包括：
- `spec_version`：配置文件版本号
- `release`：发布版本信息，包括版本号、标题和描述
- `apigateway`：网关基本信息，如描述、是否公开、维护人员等
- `stage`：环境配置，包括代理设置和超时时间
- `grant_permissions`：主动授权配置，指定哪些应用可以访问网关资源
- `related_apps`：关联应用，指定可以通过网关API操作网关数据的应用
- `resource_docs`：资源文档路径，指定API文档的存放位置

`resources.yaml`文件定义了具体的API资源，采用Swagger 2.0格式。每个资源包含路径、HTTP方法、操作ID、描述、标签和网关特定配置。网关特定配置包括：
- `isPublic`：资源是否公开
- `allowApplyPermission`：是否允许申请权限
- `backend`：后端服务配置，包括方法、路径和超时时间
- `pluginConfigs`：插件配置，如限流策略
- `authConfig`：认证配置，包括用户验证、应用验证和资源权限验证

**Section sources**
- [definition.yaml](file://support-files/apigw/definition.yaml#L1-L138)
- [resources.yaml](file://support-files/apigw/resources.yaml#L1-L3112)

## 核心API调用示例

系统通过API网关暴露了多个核心API，用于日志查询、采集项管理、存储管理等功能。以下是一些核心API的调用示例。

### 日志查询API
日志查询API通过`/esquery_search/`路径暴露，支持POST方法。请求头需要包含`X-Bkapi-Authorization`，其中包含JWT令牌。请求体包含查询参数，如索引集ID、查询字符串、时间范围等。

```json
{
  "indices": ["index_set_123"],
  "query_string": "*",
  "start_time": "2023-01-01 00:00:00",
  "end_time": "2023-01-01 01:00:00"
}
```

响应结构包含查询结果、状态码、消息和结果标志：
```json
{
  "result": true,
  "code": 0,
  "message": "",
  "data": {
    "list": [...],
    "total": 100
  }
}
```

### 采集项管理API
采集项管理API通过`/databus_collectors/`路径暴露，支持创建、更新、删除和查询采集项。创建采集项的请求示例如下：

```json
{
  "collector_config_name": "my_collector",
  "category_id": "linux",
  "target_object_type": "HOST",
  "target_node_type": "TOPO",
  "target_nodes": [{"bk_inst_id": 123, "bk_obj_id": "module"}]
}
```

### 存储管理API
存储管理API通过`/databus_storage/`路径暴露，支持创建、更新和删除存储集群。创建存储集群的请求示例如下：

```json
{
  "cluster_name": "es_cluster_1",
  "domain_name": "es.example.com",
  "port": 9200,
  "schema": "http",
  "auth_info": {
    "username": "admin",
    "password": "password"
  }
}
```

**Section sources**
- [resources.yaml](file://support-files/apigw/resources.yaml#L8-L24)
- [bk_log.yaml](file://docs/apidocs/bk_log.yaml#L3-L1502)
- [views.py](file://apps/grafana/views.py#L235-L266)

## 多环境配置管理

系统支持开发、测试和生产环境的多环境配置管理，通过环境变量和配置文件实现。环境相关的配置在`config/`目录下的`dev.py`、`stag.py`和`prod.py`文件中定义，分别对应开发、预发布和生产环境。

环境变量在`default.py`中通过`os.getenv()`函数读取，支持灵活的配置管理。例如，`USE_NEW_MONITOR_APIGATEWAY`、`EXTERNAL_APIGW_PUBLIC_KEY`等配置项都通过环境变量设置，可以在不同环境中使用不同的值。

API网关的同步命令`sync_apigw.py`会根据`settings.SYNC_APIGATEWAY_ENABLED`配置决定是否执行同步操作，这使得在开发和测试环境中可以禁用网关同步，避免影响生产环境。

通过`definition.yaml`中的`stage`配置，可以为不同环境设置不同的代理配置。例如，生产环境可以指向生产后端服务，而开发环境可以指向开发后端服务，实现环境隔离。

**Section sources**
- [default.py](file://config/default.py#L1121-L1319)
- [dev.py](file://config/dev.py)
- [stag.py](file://config/stag.py)
- [prod.py](file://config/prod.py)
- [sync_apigw.py](file://apps/api/management/commands/sync_apigw.py#L30-L31)

## API版本管理与向后兼容性

API版本管理通过`definition.yaml`文件中的`release`配置实现。每次更新API资源时，需要递增`version`字段的值，这将触发新的网关版本发布。版本号与SDK版本号保持一致，便于调用方管理和升级。

为了保证向后兼容性，系统采用了多种策略：
1. **API路径版本化**：在API路径中包含版本号，如`/v2/bk_log/esquery_search/`，允许新旧版本共存
2. **废弃标记**：在API定义中使用`is_hidden: True`标记已废弃的API，但仍保持其可用性
3. **参数兼容**：新增API参数时，确保旧的请求参数仍然有效，新增参数为可选
4. **响应兼容**：保持响应结构的稳定性，新增字段不影响旧的解析逻辑

`convert_apigw_yaml.py`脚本用于将`bk_log.yaml`中的API定义转换为网关可用的Swagger格式，支持JSON、YAML和Swagger等多种输出格式。该脚本通过命令行参数指定输入文件、输出目录和输出格式，便于自动化集成。

通过`grant_permissions`配置，可以为特定应用授予访问特定资源的权限，支持按网关维度或资源维度进行授权。这种细粒度的权限控制有助于实现平滑的版本过渡，可以在新版本上线后逐步迁移应用。

**Section sources**
- [definition.yaml](file://support-files/apigw/definition.yaml#L5-L12)
- [bk_log.yaml](file://docs/apidocs/bk_log.yaml#L22-L23)
- [convert_apigw_yaml.py](file://scripts/convert_apigw_yaml.py#L24-L132)