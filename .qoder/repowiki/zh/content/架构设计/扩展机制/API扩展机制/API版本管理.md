# API版本管理

<cite>
**本文档引用的文件**  
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py)
- [docs\api\monitor_v3.yaml](file://bkmonitor\docs\api\monitor_v3.yaml)
- [blueking\component\README.md](file://bkmonitor\blueking\component\README.md)
- [bkmonitor\as_code\constants.py](file://bkmonitor\bkmonitor\as_code\constants.py)
- [packages\monitor_web\strategies\views.py](file://bkmonitor\packages\monitor_web\strategies\views.py)
</cite>

## 目录
1. [引言](#引言)
2. [API版本演进路径与设计考量](#api版本演进路径与设计考量)
3. [各版本差异对比](#各版本差异对比)
4. [基于Django URL路由的版本控制实现](#基于django-url路由的版本控制实现)
5. [版本兼容性处理策略](#版本兼容性处理策略)
6. [策略管理API从v3到v4的升级示例](#策略管理api从v3到v4的升级示例)
7. [API版本选择建议与客户端适配指南](#api版本选择建议与客户端适配指南)

## 引言

蓝鲸监控平台（BlueKing - Monitor）为保障系统的稳定性与可扩展性，采用多版本并行的API管理策略。该策略支持v2、v3、v4等多个主要版本共存，通过清晰的版本控制机制、兼容性保障措施和渐进式升级路径，确保新功能的引入不会破坏现有系统的正常运行。本文档全面阐述bk-monitor系统的API版本管理策略，涵盖版本演进、路由实现、兼容性处理及升级实践，为开发者提供权威的版本使用与迁移指导。

## API版本演进路径与设计考量

bk-monitor系统的API版本经历了从v2到v3再到v4的持续演进过程，每一次升级都伴随着架构优化、功能增强和接口规范化的重大改进。

- **v2版本**：作为早期版本，v2奠定了基础的RESTful API设计模式，提供了核心的监控数据查询、告警管理等功能。其设计注重快速交付和功能覆盖，为后续版本积累了宝贵的实践经验。

- **v3版本**：v3版本引入了模块化的设计思想，通过`INSTALLED_APIS`配置项实现了API的按需加载和灵活组合。该版本强化了权限控制和数据模型的抽象，提升了系统的可维护性和安全性。`register_v3()`函数通过动态导入`kernel_api.views.v3`下的子模块，实现了细粒度的API注册。

- **v4版本**：v4版本是面向未来的一次重大重构。它采用了更简洁、统一的API入口，将所有功能聚合在`/api/v4/`路径下，通过`views.v4`模块进行集中管理。这种设计简化了路由逻辑，降低了客户端的接入复杂度，并为微服务化和API网关的集成提供了更好的支持。

演进的核心设计考量包括：
1.  **向后兼容**：确保旧版本API在新系统中仍能正常工作，避免对现有业务造成冲击。
2.  **性能优化**：通过减少路由层级、优化数据序列化等方式提升API响应速度。
3.  **可维护性**：采用模块化和集中化的管理方式，降低代码复杂度和维护成本。
4.  **可扩展性**：为未来新功能的添加预留清晰的接口和扩展点。

**Section sources**
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py#L66-L104)

## 各版本差异对比

| 对比维度 | v2版本 | v3版本 | v4版本 |
| :--- | :--- | :--- | :--- |
| **请求响应格式** | 基础JSON格式，结构相对简单。 | 采用更规范的响应体结构，包含`result`、`data`、`message`等标准字段，便于客户端解析。 | 在v3的基础上进一步统一，对错误码和成功响应的格式进行了标准化。 |
| **认证机制** | 主要依赖蓝鲸统一登录（bk_login）的Cookie或Token进行认证。 | 增强了基于IAM（身份与访问管理）的细粒度权限控制，支持更复杂的鉴权场景。 | 深度集成IAM，提供更安全、更灵活的权限管理能力，支持基于角色和资源的访问控制。 |
| **功能覆盖** | 覆盖核心监控功能，如数据查询、告警查询。 | 功能大幅扩展，支持更复杂的策略管理、数据源管理、服务发现等。 | 在v3功能基础上，整合了APM（应用性能管理）等高级功能，并提供了更强大的数据处理和分析能力。 |
| **路由结构** | 路由分散，部分API通过`/rest/v2/`等路径暴露。 | 采用模块化路由，通过`/api/v3/{module}/`的路径组织不同功能模块。 | 采用扁平化路由，所有API统一通过`/api/v4/`入口，内部通过资源名区分。 |
| **客户端支持** | SDK主要支持v1和v2版本。 | SDK明确支持v2版本，并通过`set_bk_api_ver("v2")`等方式兼容旧版。 | 鼓励使用最新SDK，直接对接v4版本，享受最佳性能和功能体验。 |

**Section sources**
- [blueking\component\README.md](file://bkmonitor\blueking\component\README.md#L59-L78)
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py#L66-L104)

## 基于Django URL路由的版本控制实现

bk-monitor系统利用Django强大的URL路由机制，通过命名空间（namespace）和版本前缀实现了多版本API的共存。

### 实现机制

1.  **版本注册函数**：系统定义了`register_v2()`、`register_v3()`和`register_v4()`三个独立的函数，分别负责注册不同版本的API。
2.  **版本前缀**：每个版本的API都通过唯一的URL前缀进行区分：
    *   v2: `^api/v2/`
    *   v3: `^api/v3/{module}/`
    *   v4: `^api/v4/`
3.  **命名空间**：在注册路由时，为每个版本指定了独立的命名空间（如`api.v2`、`api.v3.{module}`、`api.v4`），这有助于在Django内部清晰地管理和区分不同版本的视图。
4.  **视图模块映射**：v2和v4版本直接映射到`views.v2`和`views.v4`模块。v3版本则更为灵活，通过`package_contents(ROOT_MODULE_V3)`动态扫描`views.v3`目录下的所有子模块（如`collector`, `meta`等），并根据`INSTALLED_APIS`配置进行选择性注册。

### 核心代码分析

```python
# kernel_api/urls.py 片段

def register_v3():
    ROOT_MODULE_V3 = ROOT_MODULE + ".v3"
    # 动态获取views.v3下的所有子模块
    apis = {m: "{}.{}".format(ROOT_MODULE_V3, m) for m in package_contents(ROOT_MODULE_V3) if m in INSTALLED_APIS}
    for name, sub_module in list(apis.items()):
        # 为每个模块注册带有版本和模块名前缀的URL，并指定命名空间
        urlpattern = register_url(r"^api/v3/%s/" % name, sub_module, namespace="{}.v3.{}".format(API_NAMESPACE, name))
        urlpatterns.append(urlpattern)

def register_v4():
    views_modules = [views.v4]
    # 为v4版本注册统一的URL前缀和命名空间
    urlpatterns.append(register_url(r"^api/v4/", views_modules, f"{API_NAMESPACE}.v4"))

# 在主urlpatterns中调用注册函数
urlpatterns = [
    # ... 其他路由
]

register_v2()
register_v3()
register_v4() # 确保所有版本的API都被注册
```

此机制确保了不同版本的API可以独立开发、测试和部署，互不干扰。

**Diagram sources**
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py#L66-L104)

```mermaid
graph TD
A[HTTP请求] --> B{请求路径匹配?}
B --> |/api/v2/...| C[register_v2]
B --> |/api/v3/{module}/...| D[register_v3]
B --> |/api/v4/...| E[register_v4]
C --> F[调用 views.v2 模块]
D --> G[动态导入 views.v3.{module}]
E --> H[调用 views.v4 模块]
F --> I[返回响应]
G --> I
H --> I
```

**Section sources**
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py#L66-L104)

## 版本兼容性处理策略

为了确保平滑升级和系统稳定，bk-monitor系统实施了严格的版本兼容性处理策略。

### 废弃接口的标记

系统通过`monitor_v3.yaml`文件中的`is_hidden: true`字段来标记已废弃的接口。例如，在该文件中可以找到大量从`/v2/monitor_v3/`路径映射到`/api/v4/`路径的API定义，这些旧路径的`is_hidden`值被设为`true`，表明它们已被隐藏，不推荐新业务使用。

```yaml
# docs/api/monitor_v3.yaml 片段
- api_type: operate
  dest_http_method: POST
  dest_path: /api/v4/application_web/create_application/
  is_hidden: true # 标记为已隐藏/废弃
  label: 【APM】应用创建
  name: apm_create_web_application
  path: /v2/monitor_v3/apm/create_web_application/ # 旧的v2路径
  method: POST
```

### 迁移指南的提供

虽然文档中未直接提供详细的迁移指南文件，但通过`monitor_v3.yaml`文件可以清晰地看到迁移路径。该文件本质上是一个API映射表，明确指出了每一个旧版API（`path`）应该被哪个新版API（`dest_path`）所替代。开发者可以依据此文件进行接口调用的替换。

### 向后兼容的保障措施

系统通过API网关（API Gateway）实现了强大的向后兼容能力。当客户端调用一个已被废弃的v2接口时，API网关会根据`monitor_v3.yaml`中的配置，自动将请求转发（或重定向）到对应的新版v4接口。这种“代理转发”机制保证了即使客户端代码未及时更新，业务请求依然能够成功处理，从而实现了无缝的向后兼容。

**Section sources**
- [docs\api\monitor_v3.yaml](file://bkmonitor\docs\api\monitor_v3.yaml#L2703-L2746)
- [kernel_api\urls.py](file://bkmonitor\kernel_api\urls.py#L66-L104)

## 策略管理API从v3到v4的升级示例

以策略管理API为例，可以清晰地看到从v3到v4的升级过程。

### 接口重构与功能扩展

在`packages\monitor_web\strategies\views.py`中，可以看到大量以`_v2`为后缀的资源函数，如`save_strategy_v2`、`update_partial_strategy_v2`等。这表明v2版本的策略管理接口是直接在视图层实现的。

```python
# packages/monitor_web/strategies/views.py 片段
ResourceRoute("POST", resource.strategies.save_strategy_v2, endpoint="v2/save_strategy"),
ResourceRoute("POST", resource.strategies.update_partial_strategy_v2, endpoint="v2/update_partial_strategy"),
```

而在v4版本中，这些接口被重构和整合。`dest_path`指向`/api/v4/`，意味着策略管理功能被纳入了v4的统一API体系。这通常伴随着：
1.  **接口统一**：将分散的v2接口整合到一个更规范的RESTful资源集合中。
2.  **功能扩展**：在v4中可能新增了批量操作、更复杂的查询条件、与AIOPS的集成等高级功能。
3.  **字段变更**：请求和响应的JSON结构可能进行了优化，例如使用更语义化的字段名，或增加了新的元数据字段。

### 升级实现方式

升级的实现方式是**渐进式替换**：
1.  **并行运行**：v2和v4的策略管理API同时在线。
2.  **网关映射**：通过`monitor_v3.yaml`配置，将对`/v2/monitor_v3/...`的请求映射到`/api/v4/...`。
3.  **客户端迁移**：鼓励新业务直接调用v4接口，老业务逐步将调用点从v2迁移到v4。
4.  **最终下线**：在确认所有业务都已迁移后，可以安全地关闭v2的API端点。

**Section sources**
- [packages\monitor_web\strategies\views.py](file://bkmonitor\packages\monitor_web\strategies\views.py#L115-L136)
- [docs\api\monitor_v3.yaml](file://bkmonitor\docs\api\monitor_v3.yaml#L2703-L2746)

## API版本选择建议与客户端适配指南

### 版本选择建议

*   **新项目**：**强烈推荐使用v4版本**。v4是当前和未来的主推版本，拥有最完整的功能、最佳的性能和最活跃的维护支持。
*   **现有项目**：
    *   如果当前使用v2版本，建议制定迁移计划，逐步将接口调用切换到v4版本。
    *   如果当前使用v3版本，可以根据业务需求评估是否需要升级。v3版本仍受支持，但新功能会优先在v4中提供。

### 客户端适配指南

1.  **使用官方SDK**：优先使用蓝鲸官方提供的SDK，它通常内置了对多版本API的支持和版本切换功能。
2.  **明确指定版本**：在调用API时，务必在请求URL中明确指定版本号（如`/api/v4/strategy/`）。
3.  **查阅最新文档**：始终参考最新的API文档（如`monitor_v3.yaml`或在线文档）来获取v4版本的接口定义。
4.  **处理兼容性**：如果必须调用旧版API，需了解其已被标记为废弃，并计划未来的迁移工作。
5.  **错误处理**：关注API响应中的`result`和`code`字段，以便及时发现因版本不兼容导致的调用失败。

遵循以上建议，开发者可以高效、安全地使用bk-monitor系统的API，充分利用其强大的监控能力。