# drf_resource模块开发指南

<cite>
**本文档引用的文件**
- [base.py](file://bkmonitor/core/drf_resource/base.py)
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py)
- [routers.py](file://bkmonitor/core/drf_resource/routers.py)
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md)
</cite>

## 目录
1. [简介](#简介)
2. [核心概念](#核心概念)
3. [使用方法](#使用方法)
4. [调用方式](#调用方式)
5. [最佳实践](#最佳实践)
6. [常见问题解答](#常见问题解答)

## 简介
`drf_resource`模块是蓝鲸监控平台中用于构建RESTful API的核心组件，它基于Django REST Framework（DRF）进行封装，提供了一套简洁、高效的API开发模式。该模块通过将业务逻辑与视图分离，实现了代码的高内聚、低耦合，极大地提升了开发效率和代码可维护性。

**本文档引用的文件**
- [base.py](file://bkmonitor/core/drf_resource/base.py)
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py)
- [routers.py](file://bkmonitor/core/drf_resource/routers.py)

## 核心概念

### Resource
`Resource`是drf_resource模块的核心类，代表一个独立的业务处理单元。它负责接收请求数据，执行业务逻辑，并返回处理结果。`Resource`类通过继承`Resource`基类来实现自定义功能。

``mermaid
classDiagram
class Resource {
+RequestSerializer : Serializer
+ResponseSerializer : Serializer
+serializers_module : Module
+many_request_data : bool
+many_response_data : bool
+support_data_collect : bool
+__init__(context)
+request(request_data, **kwargs)
+bulk_request(request_data_iterable, ignore_exceptions)
+delay(request_data, **kwargs)
+apply_async(request_data, **kwargs)
+perform_request(validated_request_data)
+validate_request_data(request_data)
+validate_response_data(response_data)
}
Resource <|-- CustomResource : 继承
```

**图示来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L66-L310)

**本节来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L66-L310)

### Serializer
`Serializer`用于定义`Resource`的输入和输出数据格式。通过声明`RequestSerializer`和`ResponseSerializer`，可以实现请求参数的自动校验和响应数据的格式化。

``mermaid
classDiagram
class Serializer {
+Meta : Class
+fields : List
+validate()
+create()
+update()
}
class RequestSerializer {
+new_username : CharField
}
class ResponseSerializer {
+id : IntegerField
+username : CharField
+last_login : DateTimeField
}
Serializer <|-- RequestSerializer
Serializer <|-- ResponseSerializer
```

**图示来源**
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md#L37-L52)

**本节来源**
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md#L37-L52)

### ResourceViewSet
`ResourceViewSet`是用于定义API视图的类，它通过声明`resource_routes`来配置路由规则。每个`ResourceRoute`对应一个API端点。

``mermaid
classDiagram
class ResourceViewSet {
+resource_routes : List[ResourceRoute]
+filter_backends : List
+pagination_class : Class
+resource_mapping : Dict
+get_serializer_class()
+get_queryset()
+generate_endpoint()
}
class ResourceRoute {
+method : str
+resource_class : Resource
+endpoint : str
+pk_field : str
+enable_paginate : bool
+content_encoding : str
+decorators : List
}
ResourceViewSet <|-- CustomViewSet : 继承
ResourceRoute "1" --> "1" Resource : 使用
```

**图示来源**
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py#L61-L112)

**本节来源**
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py#L61-L112)

### ResourceRouter
`ResourceRouter`是用于注册和管理`ResourceViewSet`的路由类。它提供了`register`和`register_module`方法来注册单个或整个模块的视图集。

``mermaid
classDiagram
class ResourceRouter {
+register(prefix, viewset, basename)
+register_module(viewset_module)
+get_default_basename(viewset)
+_init_resource_viewset(viewset)
}
ResourceRouter <|-- DefaultRouter : 继承
```

**图示来源**
- [routers.py](file://bkmonitor/core/drf_resource/routers.py#L19-L54)

**本节来源**
- [routers.py](file://bkmonitor/core/drf_resource/routers.py#L19-L54)

## 使用方法

### 新建Resource
创建一个新的`Resource`需要继承`Resource`基类，并实现`perform_request`方法。

```python
from core.drf_resource import Resource
from rest_framework import serializers

class UpdateUserInfoResource(Resource):
    """更新用户信息"""
    
    def perform_request(self, validated_request_data):
        # 实现业务逻辑
        return {"status": "success"}
```

**本节来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L66-L310)

### 声明Serializer
可以在`Resource`类内部声明`RequestSerializer`和`ResponseSerializer`，或者使用独立的Serializer类。

```python
from rest_framework import serializers

class UpdateUserInfoRequestSerializer(serializers.Serializer):
    new_username = serializers.CharField(label="新用户名", max_length=12, min_length=6)

class UpdateUserInfoResource(Resource):
    RequestSerializer = UpdateUserInfoRequestSerializer
    ResponseSerializer = UpdateUserInfoResponseSerializer
    
    def perform_request(self, validated_request_data):
        # 业务逻辑
        pass
```

**本节来源**
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md#L54-L86)

### 路由配置
通过`ResourceViewSet`和`ResourceRouter`来配置API路由。

```python
from core.drf_resource.viewsets import ResourceRoute, ResourceViewSet
from core.drf_resource.routers import ResourceRouter
from example.app0.resources import UpdateUserInfoResource

class UserInfoViewSet(ResourceViewSet):
    resource_routes = [
        ResourceRoute("POST", UpdateUserInfoResource, endpoint="info"),
        ResourceRoute("PUT", UpdateUserInfoResource, pk_field="user_id"),
    ]

# 在urls.py中
router = ResourceRouter()
router.register_module(views)
urlpatterns = router.urls
```

**本节来源**
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py#L61-L112)
- [routers.py](file://bkmonitor/core/drf_resource/routers.py#L19-L54)

## 调用方式

### 批量请求
使用`bulk_request`方法可以实现基于多线程的批量并发请求。

```python
resource = UpdateUserInfoResource()
requests = [
    {"new_username": "user1"},
    {"new_username": "user2"},
    {"new_username": "user3"}
]
results = resource.bulk_request(requests)
```

**本节来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L200-L240)

### 统一入口调用
可以通过`request`方法或直接调用实例来执行`Resource`。

```python
# 方式一：使用request方法
resource = UpdateUserInfoResource()
result = resource.request({"new_username": "BlueKing"})

# 方式二：直接调用实例
result = resource({"new_username": "BlueKing"})
```

**本节来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L250-L270)

## 最佳实践

### 响应格式
`Resource`的返回值应遵循统一的格式，建议使用`ResponseSerializer`来定义响应结构。

```python
# 推荐
class PermissionResource(Resource):
    def perform_request(self, validated_request_data):
        return {"has_permission": True}

# 不推荐
class BadPermissionResource(Resource):
    def perform_request(self, validated_request_data):
        return True
```

**本节来源**
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md#L123-L167)

### 异步任务
对于耗时较长的操作，可以使用`delay`或`apply_async`方法执行异步任务。

```python
resource = UpdateUserInfoResource()
async_result = resource.delay({"new_username": "BlueKing"})
task_id = async_result["task_id"]
```

**本节来源**
- [base.py](file://bkmonitor/core/drf_resource/base.py#L280-L300)

## 常见问题解答

### 如何处理多条数据？
当需要返回多条数据时，需要在`Resource`类中声明`many_response_data = True`。

```python
class UserListResource(Resource):
    many_response_data = True
    
    def perform_request(self, validated_request_data):
        # 返回QuerySet或列表
        return User.objects.all()
```

**本节来源**
- [drf_resource模块的使用.md](file://wiki/drf_resource模块的使用.md#L123-L167)

### 如何实现分页？
在`ResourceRoute`中设置`enable_paginate=True`即可启用分页功能。

```python
ResourceRoute("GET", UserListResource, enable_paginate=True)
```

**本节来源**
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py#L61-L112)

### 如何处理主键参数？
使用`pk_field`参数可以将URL中的主键传递给`Resource`。

```python
ResourceRoute("PUT", UpdateUserInfoResource, pk_field="user_id")
```

**本节来源**
- [viewsets.py](file://bkmonitor/core/drf_resource/viewsets.py#L61-L112)