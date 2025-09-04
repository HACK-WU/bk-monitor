# drf\_resource模块的使用

## 新建 Resource

在 `resources.py` 文件中，引入 `Resource`，并在 `perform_request` 函数中编写业务逻辑。

    from bk_resource import Resource
    from blueapps.utils.request_provider import get_local_request
    ​
    ​
    class UpdateUserInfoResource(Resource):
        """更新用户信息"""
    ​
        def perform_request(self, validated_request_data):
            # 获取 Request 对象
            request = get_local_request()
            # 获取 User 对象
            user = request.user
            # 获取新用户名并更新
            new_username = validated_request_data.get("new_username")
            if not new_username or len(new_username) != 12:
                raise Exception("用户名不合法")
            user.username = new_username
            user.save()
            # 响应信息
            return {
                "id": user.id,
                "username": user.username,
                "last_login": user.last_login,
            }

### 声明 Serializer

在 2.1 中，我们新建了一个更新用户信息的业务逻辑，但这里会出现的问题是，并没有对用户输入做校验，无法确定输入的用户名是否合法，在响应时直接返回 JSON，也不利于格式化输出，在这里，可以使用 Serializer 辅助进行输入校验和输出校验

在 `serializers.py` 文件中，新建 `UpdateUserInfoRequestSerializer` 和 `UpdateUserInfoResponseSerializer`，并完成输入和输出校验逻辑

    from django.contrib.auth import get_user_model
    from rest_framework import serializers
    ​
    USER_MODEL = get_user_model()
    ​
    ​
    class UpdateUserInfoRequestSerializer(serializers.Serializer):
        new_username = serializers.CharField(label="新用户名", max_length=12, min_length=6)
    ​
    ​
    class UpdateUserInfoResponseSerializer(serializers.ModelSerializer):
        class Meta:
            model = USER_MODEL
            fields = ["id", "username", "last_login"]

在 Resource 中声明 Serializer

    from bk_resource import Resource
    from blueapps.utils.request_provider import get_local_request
    from example.app0.serializers import UpdateUserInfoRequestSerializer, UpdateUserInfoResponseSerializer
    ​
    ​
    class UpdateUserInfoResource(Resource):
        """更新用户信息"""
    ​
        # 声明输入输出使用的 Serializer
        # 声明 RequestSerializer 后，所有请求都会自动校验，validated_request_data 可以直接获取校验完成的数据
        RequestSerializer = UpdateUserInfoRequestSerializer
        # 声明 ResponseSerializer 后，所有输出会自动校验
        ResponseSerializer = UpdateUserInfoResponseSerializer
    ​
        def perform_request(self, validated_request_data):
            # 获取 Request 对象
            request = get_local_request()
            # 获取 User 对象
            user = request.user
            # 获取新用户名并更新
            new_username = validated_request_data["new_username"]
            user.username = new_username
            user.save()
            # 可以直接返回 User 对象，会按照 Serializer 自动格式化为对应的内容，当然，直接返回对应的字典格式也是可以的
            return user

## 路由使用

### 声明 ResourceViewSet

在 BkResource 中，对 `views` 做了进一步的封装，可以理解为，`Resource` 就是常规 DRF 框架中，`ViewSet` 中的每一个方法（如list, retrieve)，按照如下指引，可以快速声明路由。

在 `views.py` 文件中，声明使用到的路由信息

    from bk_resource import resource
    from bk_resource.viewsets import ResourceRoute, ResourceViewSet
    from example.app0.resources import UpdateUserInfoResource
    ​
    ​
    # 声明 ViewSet，其中，ViewSet前方的内容会成为 url 的一部分
    class UserViewSet(ResourceViewSet):
        # 声明所有方法
        # Resource 会自动查找所有的子类并添加到 resource 中
        # 映射关系为 underscore_to_camel; 即 UpdateUserInfo => update_user_info
        resource_routes = [
            # 在这一条路由中，example.app0 为 APP 名，update_user_info 为 app0 下 resources.py 文件中的 UpdateUserInfoResource 对象
            # endpoint 不填写时默认为空，映射为根路由
            ResourceRoute("POST", resource.example.app0.update_user_info, endpoint="info"),
            # 我们也可以使用常规的方式进行声明，但不推荐
            ResourceRoute("POST", UpdateUserInfoResource),
            # 如果我们涉及到了 RestFul 标准的更新、删除类型，则可以使用 pk_field 声明，会自动将 pk 添加到 validated_request_data 中
            ResourceRoute("PUT", UpdateUserInfoResource, pk_field="user_id"),
        ]

在 `urls.py` 文件中，增加 `urlpatterns`

    from bk_resource.routers import ResourceRouter
    from example.app0 import views
    ​
    router = ResourceRouter()
    router.register_module(views)
    ​
    # 这里实际声明的 urls 为 ["/user/info/", "/user/", "/user/{pk}/]
    urlpatterns = router.urls

> Resource

## Resource 响应内容

Resource的返回值应只有唯一一种格式，即ResponseSerializer规定好的格式。建议所有作为API接口暴露的Resource提供ResponseSerializer，以生成完整的API文档

### 数据格式

在使用 blueapps 的统一 Renderer 的情况下，响应内容由 result,message,data,code 组成，Resource 返回值只需要关注数据本身，即 data 的内容，其余内容会由 Renderer 处理

    {
      "code": 0,
      "result": true,
      "message": "success",
      "data": {
        "username": "BlueKing"
      }
    }

## Resource 响应值

### 单条数据

1.  符合 ResponseSerializer 格式的 dict 对象
2.  ORM Model 对象（必须提供 ResponseSerializer 且 ResponseSerializer 继承自 ModelSerializer ）
3.  单个字段，如 `bool` / `dict` / `list` / `str`

原则上，Resource 不允许只返回单个数字或字符串，因为这样不符合 Restful 的接口规范，必须将数据包装成 dict 后再返回。例如：

    from bk_resource import Resource
    ​
    ​
    # 错误
    class PermissionResource(Resource):
        def perform_request(self, validated_request_data):
            return True
    ​
    ​
    # 正确
    class AnotherPermissionResource(Resource):
        def perform_request(self, validated_request_data):
            return {"has_permission": True}

### 多条数据

返回多条数据时，需要在 Resource 类中声明 `many_response_data = True`

1.  一个列表，列表中的每一个元素是符合 ResponseSerializer 格式的 dict 对象
2.  ORM Model QuerySet（必须提供 ResponseSerializer 且 ResponseSerializer 继承自 ModelSerializer）

### 示例

#### 返回 ORM Model

    from bk_resource import Resource
    from rest_framework import serializers
    from example.app0.models import UserInfo
    ​
    ​
    class UserInfoResource(Resource):
        class RequestSerializer(serializers.Serializer):
            username = serializers.CharField(required=True)
    ​
        class ResponseSerializer(serializers.ModelSerializer):
            class Meta:
                model = UserInfo
                fields = '__all__'
    ​
        def perform_request(self, validated_request_data):
            user = UserInfo.objects.get(username=validated_request_data["username"])
            return user

## Serializer 使用

### Serializer 的内嵌定义风格 （推荐使用）

若 Serializer 无复用性，则可写为内嵌类

    from bk_resource import Resource
    from rest_framework import serializers
    ​
    ​
    class UpdateUserInfoResource(Resource):
        class RequestSerializer(serializers.Serializer):
            first_name = serializers.CharField(required=True, label="名")
            last_name = serializers.CharField(required=True, label="姓")
    ​
        class ResponseSerializer(serializers.Serializer):
            full_name = serializers.CharField(required=True, label="全名")
    ​
        def perform_request(self, validated_request_data):
            full_name = "{first_name} {last_name}".format(**validated_request_data)
            return {"full_name": full_name}

### Serializer 的声明定义风格

若 Serializer 具有复用性，可以导入后进行声明

    from bk_resource import Resource
    from example.app0.serializers import UpdateUserInfoRequestSerializer, UpdateUserInfoResponseSerializer
    ​
    ​
    class UpdateUserInfoResource(Resource):
        RequestSerializer = UpdateUserInfoRequestSerializer
        ResponseSerializer = UpdateUserInfoResponseSerializer
    ​
        def perform_request(self, validated_request_data):
            new_username = validated_request_data["new_username"]
            return {"new_username": new_username}

### Serializer 的自动查找

通过配置 Resource 的 `serializers_module` 属性，Resource 将自动查找命名规则匹配的 RequestSerializer 和 ResponseSerializer，当 resources.py 中定义了大量 Resource 时，这种引入方法则显得更加优雅。(需要注意的是，此类方法定义的 Serializer 无法自动注册为 Swagger 的请求与响应示例) 命名规则：Resource 名称去掉 `Resource` 字符串后，拼接 `RequestSerializer`/`ResponseSerializer` ，具体可以查看 `bk_resource.base.Resource._search_serializer_class` 的逻辑

    import abc
    from bk_resource import Resource
    from example.app0 import serializers
    ​
    ​
    class QuickStartResource(Resource, abc.ABC):
        serializers_module = serializers
    ​
    ​
    class NameGeneratorResource(QuickStartResource):
        def perform_request(self, validated_request_data):
            full_name = "{first_name} {last_name}".format(**validated_request_data)
            return {"full_name": full_name}

## Resource 的调用

### 导入对应 Resource 后调用

若需要在代码中调用 Resource 的业务逻辑，先创建对应的 resource 实例，再调用其 request 方法，并传入请求参数

    from example.app0.resources import UpdateUserInfoResource
    ​
    update_user_info = UpdateUserInfoResource()
    ​
    # 传入字典类型参数
    update_user_info.request({"new_username": "BlueKing"})
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}
    ​
    # 传入Kwargs类型参数
    update_user_info.request(new_username="BlueKing")
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}

除了调用 `request` 方法外，也可以直接调用类本身

    from example.app0.resources import UpdateUserInfoResource
    ​
    update_user_info = UpdateUserInfoResource()
    ​
    # 传入字典类型参数
    update_user_info({"new_username": "BlueKing"})
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}
    ​
    # 传入Kwargs类型参数
    update_user_info(new_username="BlueKing")
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}

若需要在代码中调用 Resource 的业务逻辑，先创建对应的 resource 实例，再调用其 request 方法，并传入请求参数

### 导入 resource 统一入口后调用

在应用启动后，按照规范注册的所有的 Resource 类，都会被自动挂载到 `resource` 上，可以直接进行调用。 这里的转换规则为，`resource.{包名}.{小写下划线分割的类名}`，如果有多层包，都需要写出来，即 `resource.{包名}.{包名}.…….{包名}.{小写下划线分割的类名}`，类名的转换规则可以查看 `bk_resource.management.root.ResourceShortcut._setup`

    from bk_resource import resource
    ​
    # 传入字典类型参数
    resource.app0.update_user_info({"new_username": "BlueKing"})
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}
    ​
    # 传入Kwargs类型参数
    resource.app0.update_user_info(new_username="BlueKing")
    # {"id": 1, "username": "BlueKing", "last_login": "2022-01-01 00:00:00"}

## Resource 的批量请求

Resource 提供了 `bulk_request` 方法，基于多线程实现的批量请求方法，对于执行 I/O 密集型的业务逻辑特别有效。

    # 声明 Resource
    ​
    import requests
    from bk_resource import Resource
    ​
    ​
    class IoIntensiveResource(Resource):
        def perform_request(self, validated_request_data):
            result = requests.get('https://bk.tencent.com/', params=validated_request_data)
            return result.json()



    # 实际调用
    ​
    params_list = [
        {"id", 1},
        {"id", 2},
        {"id", 3},
        {"id", 4},
        # ...   
    ]
    ​
    resource = IoIntensiveResource()
    ​
    # 错误的做法
    result = []
    for params in params_list:
        result.append(resource(params))
    ​
    # 正确的做法
    result = resource.bulk_request(params_list)

## ResourceViewSet

自定义的ViewSet类通过继承ResourceViewSet类实现。 在 drf\_non\_orm 中，视图函数已被高度抽象为基于 `ResourceRoute` 类的配置。 因此，原则上，ViewSet 类不应定义任何的视图函数，但仍支持部分原有属性配置，如鉴权配置 `permission_classes`。

    from bk_resource import resource
    from bk_resource.viewsets import ResourceRoute, ResourceViewSet
    from example.app0.resources import UpdateUserInfoResource
    ​
    ​
    # 声明 ViewSet，其中，ViewSet前方的内容会成为 url 的一部分
    class UserInfoViewSet(ResourceViewSet):
        # 声明所有方法
        # Resource 会自动查找所有的子类并添加到 resource 中
        # 映射关系为 underscore_to_camel; 即 UpdateUserInfo => update_user_info
        resource_routes = [
            # 在这一条路由中，app0 为 APP 名，update_user_info 为 app0 下 resources.py 文件中的 UpdateUserInfoResource 对象
            # endpoint 不填写时默认为空，映射为根路由
            ResourceRoute("POST", resource.app0.update_user_info, endpoint="info"),
            # 我们也可以使用常规的方式进行声明，但不推荐
            ResourceRoute("POST", UpdateUserInfoResource),
            # 如果我们涉及到了 RestFul 标准的更新、删除类型，则可以使用 pk_field 声明，会自动将 pk 添加到 validated_request_data 中
            ResourceRoute("PUT", UpdateUserInfoResource, pk_field="user_id"),
        ]

## ResourceRoute

目前，ResourceRoute支持以下属性配置：

*   `method`: 请求方法，目前支持GET, POST, PUT, PATCH, DELETE
*   `resource_class`: 需要调用的Resource类
*   `endpoint`: 定义追加的url后缀，如在`TestViewSet`中定义了一个`endpoint`为`my_endpoint`的`ResourceRoute`，则访问链接为`.../test/my_endpoint/` ，若不定义`endpoint`，则为`.../test/`
*   `enable_paginate`: 是否启动分页功能，当对应的`Resource`配置了`many_response_data = True`才有效

## ResourceRouter 使用

基于 `rest_framework.routers.DefaultRouter` 扩展的Router。

与 DefaultRouter 相比，增加了导入整个 views 模块的函数 `register_module`，通过自动扫描 ViewSet 类，并根据 ViewSet 名称动态增加 url，免去逐个为 ViewSet 定义 url 的麻烦。

    from bk_resource.routers import ResourceRouter
    from example.app0 import views
    ​
    router = ResourceRouter()
    router.register_module(views)
    ​
    urlpatterns = router.urls

> BKAPIResource

# APIResource

APIResource将一个API接口封装为Resource，便于调用

    class APIResource(ApiResourceProtocol, CacheResource, metaclass=abc.ABCMeta)

**主要方法和属性：**

`module`：模块名，主要用于调试

`TIMEOUT`请求超时时间

`url_keys`用于path参数的映射

`def request(self, request_data=None, **kwargs):`

调用父类`Resource`请求流程(校验请求参数-处理逻辑-验证返回数据)

`def perform_request(self, validated_request_data):`

发起http请求，可以识别非GET请求中的文件数据。

1.  `def build_request_data(self, validated_request_data):`

    请求前对请求参数做处理
2.  `def build_url(self, validated_request_data):`

    拼接最终URL
3.  `def build_header(self, validated_request_data):`

    在请求前构造请求头
4.  `def before_request(self, kwargs):`

    对于非GET请求，如果不存在文件数据则按照JSON方式请求，否则分开传参，可以由此方啊做最后的处理。
5.  `def parse_response(self, response: requests.Response):`

    在提供数据给`response_serializer`之前，对数据作最后的处理。尝试解析json数据，返回数据的`data`部分。

# BkApiResource

`class BkApiResource(APIResource, abc.ABC):`

基于`APiResource`在请求时携带鉴权信息，并对返回数据做鉴权认证。

1.  `method = "GET"`：请求方法默认为GET
2.  `bkapi_header_authorization`：api头部鉴权
3.  `platform_authorization`：平台鉴权

**样例：**

定义API

    # api/bk_community/default.py
    ​
    import abc
    ​
    from bk_resource import BkApiResource
    from django.utils.translation import gettext_lazy
    ​
    ​
    class CommunityResource(BkApiResource, abc.ABC):
       base_url = "https://bk.tencent.com/s-mart/forum"
       module_name = "bk_community"
    ​
    ​
    class TopicsResource(CommunityResource):
       name = gettext_lazy("查询论坛主题")
       method = "GET"
       action = "/topics/"

调用API：

    from bk_resource import api
    ​
    api.bk_community.topics(keyword="test", page=1, page_size=1)

实际请求`url`为`https://bk.tencent.com/s-mart/forum/topics/?page=1&page_size=10&keyword=test`

**path参数**

如果接口中存在path参数则可以按照以下方式进行编写

    class TopicsResource(CommunityResource):
        name = gettext_lazy("查询模块")
        method = "GET"
        action = "/forum/topics/{topic_id}"
        url_keys = ["topic_id"]

调用API：

    from bk_resource import api

    api.bk_community.topics(keyword="test", topic_id=2002)

实际请求url为`https://bk.tencent.com/s-mart/forum/topics/1002/?keyword=test`

**其他**

因为`BkApiResource`继承于`Resource`，因此可以使用`Resource`相关功能，如可以重写`RequestSerializer`和`ResponseSerializer`属性对请求参数和返回数据进行校验和处理。
