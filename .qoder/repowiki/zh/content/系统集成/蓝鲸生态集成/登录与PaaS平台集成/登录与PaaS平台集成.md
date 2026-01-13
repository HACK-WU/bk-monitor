# 登录与PaaS平台集成

<cite>
**本文档引用文件**   
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py)
- [bk_paas.py](file://bklog/apps/api/modules/bk_paas.py)
- [user_middleware.py](file://bklog/apps/middleware/user_middleware.py)
- [api_token_middleware.py](file://bklog/apps/middleware/api_token_middleware.py)
- [default.py](file://bklog/config/default.py)
- [domains.py](file://bklog/config/domains.py)
- [base.py](file://bklog/apps/api/base.py)
</cite>

## 目录
1. [简介](#简介)
2. [蓝鲸登录组件集成](#蓝鲸登录组件集成)
3. [PaaS平台集成](#paas平台集成)
4. [用户身份认证机制](#用户身份认证机制)
5. [应用信息获取](#应用信息获取)
6. [开发者账号管理](#开发者账号管理)
7. [单点登录实现](#单点登录实现)
8. [安全配置说明](#安全配置说明)
9. [中间件集成](#中间件集成)
10. [应用初始化集成](#应用初始化集成)

## 简介
本文档详细说明蓝鲸监控系统与蓝鲸登录组件和PaaS平台的集成方式。重点描述用户身份认证、应用信息获取、开发者账号管理等核心功能的实现机制。提供用户登录态验证、用户信息查询、应用配置获取等接口的调用示例和安全配置说明。

## 蓝鲸登录组件集成
蓝鲸登录组件提供了统一的用户身份认证服务，通过API网关与系统进行集成。系统通过`bk_login.py`模块封装了与蓝鲸登录组件的交互接口。

```mermaid
classDiagram
class _BKLoginApi {
+MODULE : string
+use_apigw() : boolean
+_build_url(new_path, old_path) : string
+get_user : DataAPI
+list_tenant : DataAPI
+batch_lookup_virtual_user : DataAPI
+list_department_profiles : DataAPI
}
class DataAPI {
+method : string
+url : string
+module : string
+description : string
+before_request : function
+after_request : function
}
_BKLoginApi --> DataAPI : "包含"
```

**图示来源**
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py#L62-L109)

## PaaS平台集成
PaaS平台集成为系统提供了应用信息获取和管理能力。通过`bk_paas.py`模块，系统可以获取应用信息、查询应用列表等。

```mermaid
classDiagram
class _BKPAASApi {
+MODULE : string
+get_app_info : DataAPI
+get_minimal_app_list : DataAPI
+uni_apps_query_by_id : DataAPI
}
class DataAPI {
+method : string
+url : string
+module : string
+description : string
+before_request : function
+cache_time : int
}
_BKPAASApi --> DataAPI : "包含"
```

**图示来源**
- [bk_paas.py](file://bklog/apps/api/modules/bk_paas.py#L31-L62)

## 用户身份认证机制
系统通过中间件链实现用户身份认证，包括JWT认证、API网关认证和自定义认证等多种方式。

```mermaid
sequenceDiagram
participant Client as "客户端"
participant Middleware as "中间件链"
participant JWT as "JWT认证"
participant ApiGateway as "API网关认证"
participant Custom as "自定义认证"
Client->>Middleware : 发送请求
Middleware->>JWT : 解析X-Bkapi-JWT
JWT-->>Middleware : 获取request.jwt
Middleware->>ApiGateway : 根据jwt获取app对象
ApiGateway-->>Middleware : request.app
Middleware->>ApiGateway : 根据jwt获取user对象
ApiGateway-->>Middleware : request.user
Middleware->>Custom : API Token认证
Custom-->>Middleware : 认证结果
Middleware-->>Client : 处理响应
```

**图示来源**
- [default.py](file://bklog/config/default.py#L136-L141)
- [api_token_middleware.py](file://bklog/apps/middleware/api_token_middleware.py#L22-L39)

## 应用信息获取
系统通过PaaS平台API获取应用部署信息和环境变量，支持缓存机制以提高性能。

```mermaid
flowchart TD
Start([获取应用信息]) --> CheckCache["检查缓存"]
CheckCache --> CacheHit{"缓存命中?"}
CacheHit --> |是| ReturnCache["返回缓存数据"]
CacheHit --> |否| CallAPI["调用PaaS平台API"]
CallAPI --> APIResult{"API调用成功?"}
APIResult --> |否| HandleError["处理错误"]
APIResult --> |是| UpdateCache["更新缓存"]
UpdateCache --> ReturnResult["返回结果"]
HandleError --> ReturnError["返回错误"]
ReturnCache --> End([结束])
ReturnResult --> End
ReturnError --> End
```

**图示来源**
- [bk_paas.py](file://bklog/apps/api/modules/bk_paas.py#L44-L59)
- [base.py](file://bklog/apps/api/base.py#L347-L354)

## 开发者账号管理
系统通过蓝鲸登录组件管理开发者账号，包括用户信息查询、部门信息获取等功能。

```mermaid
classDiagram
class UserLocalMiddleware {
+process_view(request, view, args, kwargs)
+_get_user_info(user)
}
class _BKLoginApi {
+get_user : DataAPI
+list_department_profiles : DataAPI
}
UserLocalMiddleware --> _BKLoginApi : "调用"
UserLocalMiddleware --> UserLocalMiddleware : "注入用户信息"
```

**图示来源**
- [user_middleware.py](file://bklog/apps/middleware/user_middleware.py#L45-L79)
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py#L73-L80)

## 单点登录实现
系统通过蓝鲸登录组件实现单点登录(SSO)，用户在蓝鲸平台登录后可直接访问本系统。

```mermaid
sequenceDiagram
participant User as "用户"
participant BKLogin as "蓝鲸登录"
participant System as "本系统"
User->>BKLogin : 访问蓝鲸平台
BKLogin->>BKLogin : 用户登录认证
BKLogin-->>User : 登录成功
User->>System : 访问系统
System->>BKLogin : 验证登录态
BKLogin-->>System : 返回用户信息
System->>System : 创建会话
System-->>User : 显示系统界面
```

**图示来源**
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py#L73-L80)
- [user_middleware.py](file://bklog/apps/middleware/user_middleware.py#L64-L70)

## 安全配置说明
系统通过多层次的安全配置确保认证过程的安全性，包括API密钥、令牌验证等机制。

```mermaid
classDiagram
class ApiTokenAuthBackend {
+authenticate(request, username, **kwargs)
}
class ApiTokenAuthenticationMiddleware {
+process_view(request, view, *args, **kwargs)
}
class DataAPI {
+get_request_api_headers(params)
+_send(params, timeout, request_id, request_cookies, bk_tenant_id)
}
ApiTokenAuthenticationMiddleware --> ApiTokenAuthBackend : "使用"
ApiTokenAuthenticationMiddleware --> DataAPI : "调用"
DataAPI --> ApiTokenAuthenticationMiddleware : "返回"
```

**图示来源**
- [api_token_middleware.py](file://bklog/apps/middleware/api_token_middleware.py#L10-L39)
- [base.py](file://bklog/apps/api/base.py#L64-L74)

## 中间件集成
系统通过中间件链实现与蓝鲸认证体系的集成，包括JWT解析、用户信息注入等功能。

```mermaid
flowchart TD
A[请求进入] --> B["apps.middleware.apigw.ApiGatewayJWTMiddleware"]
B --> C["apigw_manager.apigw.authentication.ApiGatewayJWTAppMiddleware"]
C --> D["apigw_manager.apigw.authentication.ApiGatewayJWTUserMiddleware"]
D --> E["apps.middleware.api_token_middleware.ApiTokenAuthenticationMiddleware"]
E --> F["apps.middleware.user_middleware.UserLocalMiddleware"]
F --> G[业务处理]
G --> H[响应返回]
```

**图示来源**
- [default.py](file://bklog/config/default.py#L136-L141)
- [user_middleware.py](file://bklog/apps/middleware/user_middleware.py#L45-L70)

## 应用初始化集成
在应用初始化过程中，系统加载蓝鲸认证相关配置，建立与PaaS平台的连接。

```mermaid
sequenceDiagram
participant App as "应用初始化"
participant Config as "配置加载"
participant BKLogin as "蓝鲸登录"
participant BKPAAS as "PaaS平台"
App->>Config : 加载配置文件
Config->>Config : 读取PAAS_API_HOST
Config->>Config : 读取APP_CODE/SECRET_KEY
Config-->>App : 返回配置
App->>BKLogin : 初始化BKLoginApi
App->>BKPAAS : 初始化BKPAASApi
BKLogin-->>App : 初始化完成
BKPAAS-->>App : 初始化完成
App-->>App : 应用启动
```

**图示来源**
- [settings.py](file://bklog/settings.py#L24-L47)
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py#L62-L109)
- [bk_paas.py](file://bklog/apps/api/modules/bk_paas.py#L31-L62)

**章节来源**
- [settings.py](file://bklog/settings.py#L24-L47)
- [bk_login.py](file://bklog/apps/api/modules/bk_login.py#L62-L109)
- [bk_paas.py](file://bklog/apps/api/modules/bk_paas.py#L31-L62)