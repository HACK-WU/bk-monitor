# API参考

<cite>
**本文档中引用的文件**   
- [bk_log.yaml](file://bklog/docs/apidocs/bk_log.yaml)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml)
- [urls.py](file://bklog/bklog/urls.py)
- [search_views.py](file://bklog/apps/log_search/views/search_views.py)
- [collector_views.py](file://bklog/apps/log_databus/views/collector_views.py)
- [log_search/urls.py](file://bklog/apps/log_search/urls.py)
- [log_databus/urls.py](file://bklog/apps/log_databus/urls.py)
- [iam/urls.py](file://bklog/apps/iam/urls.py)
- [log_trace/urls.py](file://bklog/apps/log_trace/urls.py)
- [log_extract/urls.py](file://bklog/apps/log_extract/urls.py)
</cite>

## 目录
1. [简介](#简介)
2. [API版本控制](#api版本控制)
3. [认证与授权](#认证与授权)
4. [API网关配置](#api网关配置)
5. [功能模块](#功能模块)
   1. [日志搜索](#日志搜索)
   2. [日志采集](#日志采集)
   3. [权限管理](#权限管理)
   4. [链路追踪](#链路追踪)
   5. [日志提取](#日志提取)
6. [错误处理](#错误处理)
7. [API使用示例](#api使用示例)

## 简介

蓝鲸日志平台（BK-LOG）提供了一套完整的API接口，用于日志的搜索、采集、分析和管理。本API参考文档详细描述了平台中所有公开的API端点，按照功能模块进行组织，包括日志搜索、日志采集、权限管理等核心功能。

API设计遵循RESTful原则，提供标准化的HTTP接口，支持JSON格式的数据交换。通过这些API，开发者可以集成日志平台的功能到自己的应用中，实现自动化日志管理、监控告警、数据分析等场景。

平台通过API网关统一管理所有API端点，提供统一的认证、限流、监控等能力。API网关配置在`support-files/apigw/`目录下的YAML文件中定义，确保了API的安全性和稳定性。

**Section sources**
- [bk_log.yaml](file://bklog/docs/apidocs/bk_log.yaml)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml)

## API版本控制

蓝鲸日志平台采用语义化版本控制策略，API版本号遵循`主版本号.次版本号.修订号`的格式。当前API版本为`0.0.1`，定义在`definition.yaml`文件中。

```yaml
release:
  version: 0.0.1
  title: "init version"
  comment: "init version"
```

平台支持API版本的向后兼容性保证。当API配置更新时，需要更新版本号才能发布新的资源版本。SDK版本号与API版本号保持一致，确保调用方能够正确使用API。

API端点通过URL路径中的版本标识进行版本控制，所有API均以`/api/v1/`作为基础路径。这种设计允许平台在未来引入不兼容的变更时，通过新的版本号（如`/api/v2/`）提供服务，同时保持旧版本API的可用性。

**Section sources**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml)

## 认证与授权

蓝鲸日志平台采用蓝鲸API网关进行统一的认证和授权管理。API调用需要通过蓝鲸认证系统验证应用和用户的合法性。

### 认证机制

API网关要求所有请求必须包含有效的蓝鲸认证信息。认证信息可以通过请求头`X-Bkapi-Authorization`传递，不建议通过请求参数传递。在`definition.yaml`中配置了相关安全策略：

```yaml
allow_auth_from_params: false
allow_delete_sensitive_params: false
```

这表示网关不允许从请求参数中获取认证信息，并且不会删除请求中的敏感认证参数，提高了API调用的安全性。

### IAM权限控制

平台集成了蓝鲸IAM（身份和访问管理）系统，实现细粒度的权限控制。不同的API操作需要相应的权限才能执行，主要权限类型包括：

- `SEARCH_LOG`: 搜索日志权限
- `VIEW_COLLECTION`: 查看采集项权限
- `MANAGE_COLLECTION`: 管理采集项权限
- `CREATE_COLLECTION`: 创建采集项权限

在代码实现中，通过装饰器和权限类进行权限验证。例如，在`search_views.py`中：

```python
def get_permissions(self):
    if self.action in ["search", "context", "tailf", "export"]:
        return [InstanceActionPermission([ActionEnum.SEARCH_LOG], ResourceEnum.INDICES)]
```

这表示执行搜索、上下文查看、实时日志和导出等操作需要`SEARCH_LOG`权限。

API网关还配置了主动授权规则，为特定应用授予访问权限。例如，监控系统`bk_monitorv3`被授予了网关级别的访问权限：

```yaml
- bk_app_code: bk_monitorv3
  grant_dimension: "gateway"
```

**Section sources**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml)
- [search_views.py](file://bklog/apps/log_search/views/search_views.py)
- [collector_views.py](file://bklog/apps/log_databus/views/collector_views.py)

## API网关配置

API网关是蓝鲸日志平台的入口，负责路由、认证、限流等核心功能。网关配置主要在`support-files/apigw/`目录下的YAML文件中定义。

### 网关基本信息

在`definition.yaml`中定义了网关的基本信息：

```yaml
apigateway:
  description: "蓝鲸日志平台API网关"
  description_en: "BK-LOG API Gateway"
  is_public: true
  api_type: 1
  maintainers: {{ settings.APIGW_MANAGERS }}
```

这表明网关是公开的，任何人都可以查看资源文档和申请权限，维护人员由系统配置决定。

### 代理配置

网关通过代理配置将请求转发到后端服务：

```yaml
stage:
  name: "prod"
  description: "生产环境"
  proxy_http:
    timeout: 60
    upstreams:
      loadbalance: "roundrobin"
      hosts:
        - host: "{{ settings.BK_BKLOG_API_HOST }}"
          weight: 100
```

生产环境的超时时间为60秒，采用轮询负载均衡策略，后端服务地址由系统配置决定。

### 资源文档

API资源文档通过`resource_docs`配置项指定：

```yaml
resource_docs:
  basedir: "support-files/apigw/apidocs/"
```

文档目录包含中文和英文版本，支持国际化访问。

**Section sources**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml)

## 功能模块

### 日志搜索

日志搜索模块提供强大的日志查询和分析功能，支持全文检索、上下文查看、实时日志等功能。

#### API端点

根据`urls.py`和`search_views.py`的配置，日志搜索模块的主要API端点包括：

```python
router.register(r"search/index_set", search_views.SearchViewSet, basename="search")
router.register(r"search/index_set", aggs_views.AggsViewSet, basename="aggs")
router.register(r"search/favorite", favorite_search_views.FavoriteViewSet, basename="favorite")
```

#### 主要功能

1. **索引集列表**: 获取用户有权限的索引集列表
   - 路径: `/api/v1/search/index_set/`
   - 方法: GET
   - 权限: `SEARCH_LOG`

2. **日志搜索**: 在指定索引集中搜索日志
   - 路径: `/api/v1/search/index_set/{index_set_id}/search/`
   - 方法: POST
   - 功能: 支持复杂的查询条件、聚合分析、字段过滤等

3. **上下文查看**: 查看指定日志的上下文
   - 路径: `/api/v1/search/index_set/{index_set_id}/context/`
   - 方法: POST
   - 功能: 显示目标日志前后的相关日志，便于问题排查

4. **实时日志**: 实时查看日志流
   - 路径: `/api/v1/search/index_set/{index_set_id}/tail_f/`
   - 方法: POST
   - 功能: 类似于`tail -f`命令，实时显示新产生的日志

5. **检索历史**: 管理用户的搜索历史
   - 路径: `/api/v1/search/index_set/history/`
   - 方法: GET/POST
   - 功能: 记录和查询用户的搜索历史，支持历史搜索的复用

**Section sources**
- [log_search/urls.py](file://bklog/apps/log_search/urls.py)
- [search_views.py](file://bklog/apps/log_search/views/search_views.py)

### 日志采集

日志采集模块负责配置和管理日志采集任务，支持多种采集场景和数据源。

#### API端点

根据`urls.py`和`collector_views.py`的配置，日志采集模块的主要API端点包括：

```python
router.register(r"collectors", collector_views.CollectorViewSet, basename="collectors")
router.register(r"collector_plugins", collector_plugin_views.CollectorPluginViewSet, basename="collector_plugins")
router.register(r"storage", storage_views.StorageViewSet, basename="databus_storage")
```

#### 主要功能

1. **采集项管理**: 创建、更新、删除和查询采集项
   - 路径: `/api/v1/databus/collectors/`
   - 方法: POST/GET/PUT/DELETE
   - 权限: `CREATE_COLLECTION`（创建），`MANAGE_COLLECTION`（管理）

2. **采集插件**: 管理采集插件，支持插件化采集
   - 路径: `/api/v1/databus/collector_plugins/`
   - 方法: POST/PUT
   - 功能: 创建和更新采集插件，实现采集逻辑的复用

3. **存储管理**: 管理日志存储集群
   - 路径: `/api/v1/databus/storage/`
   - 方法: POST/GET/PUT/DELETE
   - 功能: 配置Elasticsearch等存储后端，管理存储集群

4. **任务状态**: 查询采集任务的执行状态
   - 路径: `/api/v1/databus/collectors/{collector_config_id}/task_status/`
   - 方法: GET
   - 功能: 监控采集任务的运行情况，及时发现和处理异常

5. **连通性测试**: 测试存储集群的连通性
   - 路径: `/api/v1/databus/storage/connectivity_detect/`
   - 方法: POST
   - 功能: 验证存储集群是否可达，确保采集配置的正确性

**Section sources**
- [log_databus/urls.py](file://bklog/apps/log_databus/urls.py)
- [collector_views.py](file://bklog/apps/log_databus/views/collector_views.py)

### 权限管理

权限管理模块基于蓝鲸IAM系统，提供细粒度的访问控制。

#### API端点

权限管理的API端点主要在`iam/urls.py`中定义：

```python
router.register(r"meta", meta.MetaViewSet, basename="meta")
urlpatterns = [re_path(r"^", include(router.urls)), re_path(r"^resource/$", dispatcher.as_view([login_exempt]))]
```

#### 主要功能

1. **资源提供者**: 为IAM系统提供资源定义
   - `CollectionResourceProvider`: 采集项资源
   - `EsSourceResourceProvider`: ES数据源资源
   - `IndicesResourceProvider`: 索引资源

2. **权限分发**: 通过ResourceApiDispatcher将资源请求分发到相应的资源提供者
   ```python
   dispatcher = resources.ResourceApiDispatcher(Permission.get_iam_client(settings.BK_APP_TENANT_ID), settings.BK_IAM_SYSTEM_ID)
   dispatcher.register("collection", CollectionResourceProvider())
   ```

3. **元数据管理**: 提供权限系统的元数据信息
   - 路径: `/api/v1/iam/meta/`
   - 方法: GET
   - 功能: 查询权限系统支持的操作和资源类型

**Section sources**
- [iam/urls.py](file://bklog/apps/iam/urls.py)

### 链路追踪

链路追踪模块提供分布式系统的调用链路分析功能。

#### API端点

链路追踪的API端点在`log_trace/urls.py`中定义：

```python
router.register(r"index_set", trace_views.TraceViewSet, basename="trace")
```

#### 主要功能

1. **追踪数据查询**: 在索引集中查询链路追踪数据
   - 路径: `/api/v1/trace/index_set/{index_set_id}/`
   - 方法: GET/POST
   - 功能: 支持按服务、接口、响应时间等条件查询调用链路

2. **调用链路可视化**: 提供调用链路的图形化展示
   - 支持展示服务间的调用关系、调用耗时、错误率等指标
   - 帮助开发者快速定位性能瓶颈和故障点

**Section sources**
- [log_trace/urls.py](file://bklog/apps/log_trace/urls.py)

### 日志提取

日志提取模块提供日志的结构化提取和分析功能。

#### API端点

日志提取的API端点在`log_extract/urls.py`中定义：

```python
router.register(r"explorer", explorer_views.ExplorerViewSet, basename="explorer")
router.register(r"strategies", strategies_views.StrategiesViewSet, basename="strategies")
router.register(r"tasks", tasks_views.TasksViewSet, basename="tasks")
router.register(r"links", links_views.LinksViewSet, basename="links")
```

#### 主要功能

1. **日志探索**: 交互式地探索和分析日志数据
   - 路径: `/api/v1/log_extract/explorer/`
   - 方法: GET/POST
   - 功能: 提供可视化的日志分析界面，支持拖拽式操作

2. **提取策略**: 定义日志提取的规则和策略
   - 路径: `/api/v1/log_extract/strategies/`
   - 方法: POST/GET/PUT/DELETE
   - 功能: 配置正则表达式、分隔符等提取规则，将非结构化日志转换为结构化数据

3. **提取任务**: 管理日志提取任务的执行
   - 路径: `/api/v1/log_extract/tasks/`
   - 方法: GET/POST
   - 功能: 启动、停止和监控提取任务，确保数据处理的及时性

4. **数据关联**: 建立不同日志数据之间的关联关系
   - 路径: `/api/v1/log_extract/links/`
   - 方法: POST/GET
   - 功能: 通过唯一标识符关联不同系统的日志，实现端到端的问题追踪

**Section sources**
- [log_extract/urls.py](file://bklog/apps/log_extract/urls.py)

## 错误处理

蓝鲸日志平台采用统一的错误处理策略，确保API调用者能够清晰地了解错误原因并进行相应的处理。

### 错误码规范

API响应遵循统一的格式，包含`code`、`message`和`data`三个字段：

```json
{
    "code": 0,
    "message": "",
    "data": {}
}
```

- `code`: 错误码，0表示成功，非0表示错误
- `message`: 错误信息，提供详细的错误描述
- `data`: 返回数据，成功时包含实际数据，失败时可能为空

### 常见错误码

1. **认证相关错误**
   - `1300001`: 认证信息无效
   - `1300002`: 应用未授权
   - `1300003`: 用户未授权

2. **权限相关错误**
   - `1300101`: 无权访问资源
   - `1300102`: 无权执行操作
   - `1300103`: 资源权限不足

3. **参数相关错误**
   - `1300201`: 参数缺失
   - `1300202`: 参数格式错误
   - `1300203`: 参数值无效

4. **资源相关错误**
   - `1300301`: 资源不存在
   - `1300302`: 资源已存在
   - `1300303`: 资源状态错误

5. **系统相关错误**
   - `1300401`: 系统内部错误
   - `1300402`: 服务不可用
   - `1300403`: 请求超时

### 错误处理最佳实践

1. **客户端应检查`code`字段**，只有当`code`为0时才处理`data`中的数据
2. **记录详细的错误信息**，便于问题排查和用户支持
3. **提供用户友好的错误提示**，避免直接暴露技术细节
4. **实现重试机制**，对于临时性错误（如网络超时）进行重试
5. **监控错误码的分布**，及时发现和解决系统性问题

**Section sources**
- [bk_log.yaml](file://bklog/docs/apidocs/bk_log.yaml)

## API使用示例

### 使用curl调用API

#### 获取索引集列表

```bash
curl -X GET \
  https://api.example.com/api/v1/search/index_set/ \
  -H 'X-Bkapi-Authorization: {"bk_app_code": "your_app_code", "bk_app_secret": "your_app_secret"}' \
  -H 'Content-Type: application/json'
```

#### 搜索日志

```bash
curl -X POST \
  https://api.example.com/api/v1/search/index_set/1/search/ \
  -H 'X-Bkapi-Authorization: {"bk_app_code": "your_app_code", "bk_app_secret": "your_app_secret"}' \
  -H 'Content-Type: application/json' \
  -d '{
    "keyword": "error",
    "start_time": "2023-01-01 00:00:00",
    "end_time": "2023-01-01 23:59:59",
    "ip_list": ["127.0.0.1"]
  }'
```

#### 创建采集项

```bash
curl -X POST \
  https://api.example.com/api/v1/databus/collectors/ \
  -H 'X-Bkapi-Authorization: {"bk_app_code": "your_app_code", "bk_app_secret": "your_app_secret"}' \
  -H 'Content-Type: application/json' \
  -d '{
    "collector_config_name": "my_collector",
    "collector_scenario_id": "row",
    "category_id": "application",
    "target_object_type": "HOST",
    "target_node_type": "TOPO",
    "target_nodes": [
      {
        "id": 123,
        "bk_inst_id": 123,
        "bk_obj_id": "module"
      }
    ],
    "data_link_id": 1
  }'
```

### 使用Python客户端

```python
import requests
import json

class BKLogClient:
    def __init__(self, base_url, app_code, app_secret):
        self.base_url = base_url
        self.auth_header = {
            'X-Bkapi-Authorization': json.dumps({
                'bk_app_code': app_code,
                'bk_app_secret': app_secret
            }),
            'Content-Type': 'application/json'
        }
    
    def get_index_sets(self):
        """获取索引集列表"""
        url = f"{self.base_url}/api/v1/search/index_set/"
        response = requests.get(url, headers=self.auth_header)
        return response.json()
    
    def search_logs(self, index_set_id, keyword, start_time, end_time):
        """搜索日志"""
        url = f"{self.base_url}/api/v1/search/index_set/{index_set_id}/search/"
        data = {
            "keyword": keyword,
            "start_time": start_time,
            "end_time": end_time
        }
        response = requests.post(url, headers=self.auth_header, json=data)
        return response.json()
    
    def create_collector(self, collector_config):
        """创建采集项"""
        url = f"{self.base_url}/api/v1/databus/collectors/"
        response = requests.post(url, headers=self.auth_header, json=collector_config)
        return response.json()

# 使用示例
client = BKLogClient(
    base_url="https://api.example.com",
    app_code="your_app_code",
    app_secret="your_app_secret"
)

# 获取索引集
index_sets = client.get_index_sets()
print(f"找到 {len(index_sets['data'])} 个索引集")

# 搜索日志
logs = client.search_logs(
    index_set_id=1,
    keyword="error",
    start_time="2023-01-01 00:00:00",
    end_time="2023-01-01 23:59:59"
)
print(f"找到 {len(logs['data']['list'])} 条日志")
```

**Section sources**
- [bk_log.yaml](file://bklog/docs/apidocs/bk_log.yaml)
- [search_views.py](file://bklog/apps/log_search/views/search_views.py)
- [collector_views.py](file://bklog/apps/log_databus/views/collector_views.py)