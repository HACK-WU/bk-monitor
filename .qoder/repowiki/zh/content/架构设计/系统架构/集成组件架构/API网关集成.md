# API网关集成

<cite>
**本文档引用的文件**   
- [apigw.py](file://bklog/apps/middleware/apigw.py)
- [views.py](file://bklog/apps/esb/views.py)
- [urls.py](file://bklog/apps/esb/urls.py)
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml)
- [sync_apigw.py](file://bklog/apps/api/management/commands/sync_apigw.py)
- [esb.py](file://bklog/blueking/component/apis/esb.py)
- [api_token_middleware.py](file://bklog/apps/middleware/api_token_middleware.py)
</cite>

## 目录
1. [引言](#引言)
2. [API网关配置](#api网关配置)
3. [请求认证机制](#请求认证机制)
4. [参数校验与流量控制](#参数校验与流量控制)
5. [ESB组件实现](#esb组件实现)
6. [API资源映射](#api资源映射)
7. [安全防护策略](#安全防护策略)
8. [API调用示例](#api调用示例)
9. [常见错误代码解析](#常见错误代码解析)
10. [总结](#总结)

## 引言
BK-LOG通过蓝鲸API网关对外提供服务，实现了统一的API管理、认证授权和流量控制。本文档系统化说明BK-LOG如何通过API网关集成，详细解释apigw中间件的请求认证、参数校验和流量控制机制，描述ESB组件如何实现内部API的外部暴露，包括接口注册、版本管理和访问控制。

## API网关配置

```mermaid
graph TD
A[API网关配置] --> B[definition.yaml]
A --> C[resources.yaml]
B --> D[网关基本信息]
B --> E[环境信息]
B --> F[权限配置]
C --> G[API资源定义]
C --> H[后端服务映射]
C --> I[认证配置]
C --> J[流量控制]
```

**图示来源**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml)

**章节来源**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml#L1-L138)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L1-L800)

## 请求认证机制

```mermaid
sequenceDiagram
participant Client as 客户端
participant APIGW as API网关
participant Middleware as apigw中间件
participant Backend as 后端服务
Client->>APIGW : 发送API请求
APIGW->>Middleware : 验证JWT令牌
Middleware->>Middleware : 解码JWT头部
Middleware->>Middleware : 获取公钥提供者
Middleware->>Middleware : 验证令牌签名
alt 令牌有效
Middleware-->>APIGW : 认证成功
APIGW->>Backend : 转发请求
else 令牌无效
Middleware-->>Client : 返回401错误
end
```

**图示来源**
- [apigw.py](file://bklog/apps/middleware/apigw.py#L22-L125)

**章节来源**
- [apigw.py](file://bklog/apps/middleware/apigw.py#L22-L125)

## 参数校验与流量控制

```mermaid
flowchart TD
A[API请求] --> B{请求方法}
B --> |GET| C[从query_params获取参数]
B --> |POST/PUT/DELETE| D[从request.data获取参数]
C --> E[参数重组]
D --> E
E --> F{是否需要校验}
F --> |是| G[调用params_valid校验]
F --> |否| H[直接处理]
G --> I[校验通过]
I --> J[处理业务逻辑]
H --> J
J --> K[返回响应]
```

**图示来源**
- [views.py](file://bklog/apps/esb/views.py#L111-L122)

**章节来源**
- [views.py](file://bklog/apps/esb/views.py#L111-L122)

## ESB组件实现

```mermaid
classDiagram
class LogESBViewSet {
+check_permissions(request)
+call(request)
+request_params_regroup(query_params, method_get)
}
class MetaESBViewSet {
+get_permissions()
+call(request)
+convert_params_to_esb_params(params, is_get)
}
class WeWorkViewSet {
+create_chat(request)
}
LogESBViewSet --> APIViewSet : "继承"
MetaESBViewSet --> APIViewSet : "继承"
WeWorkViewSet --> APIViewSet : "继承"
APIViewSet --> ViewSet : "继承"
```

**图示来源**
- [views.py](file://bklog/apps/esb/views.py#L41-L212)
- [urls.py](file://bklog/apps/esb/urls.py#L28-L37)

**章节来源**
- [views.py](file://bklog/apps/esb/views.py#L41-L212)
- [urls.py](file://bklog/apps/esb/urls.py#L28-L37)

## API资源映射

```mermaid
graph TD
A[API网关资源] --> B[resources.yaml]
B --> C[资源路径]
B --> D[操作ID]
B --> E[描述]
B --> F[后端配置]
F --> G[方法]
F --> H[路径]
F --> I[超时]
B --> J[认证配置]
J --> K[用户验证]
J --> L[应用验证]
J --> M[资源权限]
B --> N[插件配置]
N --> O[限流插件]
subgraph "后端服务"
P[/api/v1/esquery/search/]
Q[/api/v1/index_set/]
R[/api/v1/databus/collectors/]
end
C --> P
C --> Q
C --> R
```

**图示来源**
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L8-L800)

**章节来源**
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L8-L800)

## 安全防护策略

```mermaid
flowchart TD
A[安全防护策略] --> B[认证配置]
B --> C[用户验证]
B --> D[应用验证]
B --> E[资源权限]
A --> F[流量控制]
F --> G[默认限流]
G --> H[令牌: 200]
G --> I[周期: 1秒]
F --> J[特殊应用限流]
J --> K[令牌: 10000]
J --> L[周期: 60秒]
A --> M[防刷机制]
M --> N[基于IP的限制]
M --> O[基于应用的限制]
A --> P[敏感参数处理]
P --> Q[删除敏感参数]
P --> R[头部转换]
```

**图示来源**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml#L23-L29)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L25-L34)

**章节来源**
- [definition.yaml](file://bklog/support-files/apigw/definition.yaml#L23-L29)
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L25-L34)

## API调用示例

```mermaid
sequenceDiagram
participant Client as 客户端
participant APIGW as API网关
participant BKLOG as BK-LOG服务
Client->>APIGW : POST /esquery_search/
APIGW->>APIGW : 验证JWT令牌
APIGW->>APIGW : 检查应用权限
APIGW->>APIGW : 应用限流规则
APIGW->>BKLOG : 转发到 /api/v1/esquery/search/
BKLOG->>BKLOG : 处理搜索请求
BKLOG-->>APIGW : 返回搜索结果
APIGW-->>Client : 返回JSON响应
Note over Client,BKLOG : 请求示例 : {<br/> "index_set_id" : "123",<br/> "keyword" : "error",<br/> "start_time" : "2023-01-01",<br/> "end_time" : "2023-01-02"<br/>}
```

**图示来源**
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L8-L18)
- [views.py](file://bklog/apps/esb/views.py#L117-L122)

**章节来源**
- [resources.yaml](file://bklog/support-files/apigw/resources.yaml#L8-L18)
- [views.py](file://bklog/apps/esb/views.py#L117-L122)

## 常见错误代码解析

```mermaid
stateDiagram-v2
[*] --> 请求处理
请求处理 --> 认证失败 : 401
请求处理 --> 权限不足 : 403
请求处理 --> 资源不存在 : 404
请求处理 --> 方法不允许 : 405
请求处理 --> 请求过快 : 429
请求处理 --> 服务器错误 : 500
认证失败 --> 重新认证
权限不足 --> 申请权限
资源不存在 --> 检查路径
方法不允许 --> 检查方法
请求过快 --> 降低频率
服务器错误 --> 重试或联系管理员
重新认证 --> 请求处理
申请权限 --> 请求处理
检查路径 --> 请求处理
检查方法 --> 请求处理
降低频率 --> 请求处理
重试或联系管理员 --> 请求处理
```

**图示来源**
- [views.py](file://bklog/apps/esb/views.py#L81-L88)
- [exceptions.py](file://bklog/apps/esb/exceptions.py)

**章节来源**
- [views.py](file://bklog/apps/esb/views.py#L81-L88)

## 总结
BK-LOG通过蓝鲸API网关实现了完整的API服务集成，包括请求认证、参数校验、流量控制和安全防护等机制。通过ESB组件实现了内部API的外部暴露，通过resources.yaml文件定义了API资源映射关系。系统提供了完善的认证授权机制和流量控制策略，确保了API服务的安全性和稳定性。