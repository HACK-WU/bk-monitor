# bklog 子模块迁移价值评估报告

> 评估范围：`log_esquery`、`grafana`、`log_trace`、`tgpa` 四个 Django App
> 评估标准：通用性、复用价值、独立性、接口稳定性、代码质量（各 1-5 分，满分 25）
> 排除规则：`__init__.py`、`apps.py`、`models`、`migrations`、`tests`、`resources.py`、`serializers.py`、`admin.py`、`urls.py`、`views.py`

---

## 1. 总览表

| 模块 | 文件 | 行数 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|------|------|--------|----------|--------|------------|----------|------|------|
| **log_esquery** | `query_builder_logic.py` | 738 | 5 | 5 | 4 | 4 | 5 | **23** | 值得迁移 |
| **log_esquery** | `dsl_builder.py` | 194 | 4 | 5 | 4 | 4 | 5 | **22** | 值得迁移 |
| **log_esquery** | `es_client.py` | 122 | 5 | 5 | 5 | 5 | 4 | **24** | 值得迁移 |
| **log_esquery** | `QueryClientTemplate.py` | 104 | 4 | 4 | 5 | 4 | 4 | **21** | 值得迁移 |
| **log_esquery** | `query_time_builder.py` | 151 | 4 | 4 | 3 | 4 | 4 | **19** | 值得迁移 |
| **log_esquery** | `query_index_optimizer.py` | 137 | 4 | 4 | 3 | 4 | 4 | **19** | 值得迁移 |
| **log_esquery** | `esquery.py` | 404 | 3 | 4 | 2 | 4 | 4 | **17** | 有条件迁移 |
| **log_esquery** | `qos.py` | 144 | 4 | 4 | 3 | 3 | 4 | **18** | 值得迁移 |
| **log_esquery** | `exceptions.py` | 244 | 3 | 3 | 5 | 4 | 4 | **19** | 值得迁移 |
| **log_esquery** | `type_constants.py` | 44 | 3 | 3 | 5 | 5 | 4 | **20** | 值得迁移 |
| **log_esquery** | `query_filter_builder.py` | 47 | 3 | 3 | 4 | 4 | 4 | **18** | 值得迁移 |
| **log_esquery** | `query_sort_builder.py` | 44 | 3 | 3 | 4 | 4 | 4 | **18** | 值得迁移 |
| **log_esquery** | `query_string_builder.py` | 53 | 3 | 3 | 4 | 4 | 4 | **18** | 值得迁移 |
| **log_esquery** | `QueryClient.py` | 52 | 3 | 3 | 3 | 4 | 4 | **17** | 有条件迁移 |
| **log_esquery** | `QueryClientEs.py` | 228 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **log_esquery** | `QueryClientLog.py` | 333 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **log_esquery** | `QueryClientBkData.py` | 264 | 2 | 2 | 2 | 3 | 4 | **13** | 不迁移 |
| **log_esquery** | `version_checker.py` | 61 | 3 | 2 | 4 | 3 | 3 | **15** | 有条件迁移 |
| **log_esquery** | `constants.py` | 32 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **log_esquery** | `metrics.py` | 21 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **log_esquery** | `permission.py` | 30 | 1 | 1 | 5 | 3 | 2 | **12** | 不迁移 |
| **log_trace** | `proto.py` | 277 | 4 | 4 | 3 | 4 | 4 | **19** | 值得迁移 |
| **log_trace** | `log.py` | 400 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **log_trace** | `otlp.py` | 452 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **log_trace** | `trace_field_handlers.py` | 347 | 3 | 3 | 3 | 3 | 3 | **15** | 有条件迁移 |
| **log_trace** | `trace_handlers.py` | 56 | 2 | 2 | 3 | 3 | 3 | **13** | 不迁移 |
| **log_trace** | `constants.py` | 142 | 3 | 3 | 4 | 4 | 3 | **17** | 有条件迁移 |
| **log_trace** | `exceptions.py` | 47 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **log_trace** | `trace_config_handlers.py` | 62 | 2 | 2 | 2 | 3 | 3 | **12** | 不迁移 |
| **log_trace** | `elastic.py` | 135 | 3 | 3 | 3 | 3 | 3 | **15** | 有条件迁移 |
| **grafana** | `query.py` | 824 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **grafana** | `data_source.py` | 353 | 3 | 3 | 2 | 3 | 4 | **15** | 有条件迁移 |
| **grafana** | `provisioning.py` | 126 | 3 | 3 | 2 | 3 | 3 | **14** | 不迁移 |
| **grafana** | `authentication.py` | 29 | 3 | 2 | 5 | 4 | 3 | **17** | 有条件迁移 |
| **grafana** | `permissions.py` | 52 | 2 | 2 | 3 | 3 | 3 | **13** | 不迁移 |
| **grafana** | `constants.py` | 47 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **grafana** | `exceptions.py` | 59 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **grafana** | `home_dashboard.py` | 130 | 2 | 2 | 4 | 3 | 3 | **14** | 不迁移 |
| **grafana** | `monitor.py` | 38 | 1 | 1 | 2 | 3 | 3 | **10** | 不迁移 |
| **grafana** | `model.py` | 28 | 1 | 1 | 5 | 4 | 3 | **14** | 不迁移 |
| **grafana** | `utils.py` | 21 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **tgpa** | `decrypt.py` | 181 | 4 | 4 | 4 | 4 | 5 | **21** | 值得迁移 |
| **tgpa** | `base.py` | 470 | 3 | 3 | 3 | 3 | 4 | **16** | 有条件迁移 |
| **tgpa** | `constants.py` | 337 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **tgpa** | `exceptions.py` | 34 | 2 | 2 | 5 | 4 | 3 | **16** | 有条件迁移 |
| **tgpa** | `report.py` | 336 | 2 | 2 | 2 | 3 | 3 | **12** | 不迁移 |
| **tgpa** | `task.py` | 287 | 2 | 2 | 2 | 3 | 3 | **12** | 不迁移 |
| **tgpa** | `tasks.py` | 407 | 1 | 1 | 1 | 3 | 3 | **9** | 不迁移 |

---

## 2. 值得迁移目标详细分析（总分 >= 18）

### 2.1 es_client.py -- ES 客户端工具集（24 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 5 | ES 客户端创建、Socket 连通性检测、版本适配，任何 ES 项目通用 |
| 复用价值 | 5 | 支持 ES5/6/7+ 多版本自动适配，IPv4/IPv6 双栈，直接复用 |
| 独立性 | 5 | 仅依赖 elasticsearch 官方库，无业务耦合 |
| 接口稳定性 | 5 | 函数签名清晰稳定，三个独立工具函数 |
| 代码质量 | 4 | 结构清晰，异常处理完善，IPv6 兼容逻辑优雅 |

**核心设计：**
- `get_es_client()` -- 根据 ES 版本号自动选择 ES5/ES6/ES7+ 客户端，支持 IPv6 地址自动加方括号
- `es_socket_ping()` -- Socket 层面的 ES 连通性检测，IPv4/IPv6 双栈回退
- `es_client_ping()` -- ES 客户端层面的 Ping 检测，含认证异常处理

**迁移范围：**
- 单文件迁移，`get_es_client` + `es_socket_ping` + `es_client_ping` 三个函数
- 需携带 `exceptions.py` 中的 `EsClientAuthenticatorException`、`EsClientHostPortException`、`EsClientSocketException`

**跨项目使用场景：**
- 任何需要连接 ES 的 Python 项目
- 监控系统的 ES 数据采集
- 日志分析平台的 ES 客户端初始化
- 多版本 ES 集群的统一接入层

---

### 2.2 query_builder_logic.py -- ES DSL 查询构建引擎（23 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 5 | 完整的 ES Bool Query DSL 构建引擎，支持 20+ 种操作符 |
| 复用价值 | 5 | 策略模式实现的操作符体系，可直接用于任何 ES 查询场景 |
| 独立性 | 4 | 依赖 elasticsearch_dsl 和 luqum，但无业务 model 耦合 |
| 接口稳定性 | 4 | 类层次设计稳定，新增操作符不影响现有接口 |
| 代码质量 | 5 | 策略模式 + 工厂模式，类型注解完善，扩展性极佳 |

**核心设计：**
- `BoolQueryOperation` -- 抽象基类，定义操作符的 `op()` 和 `to_querystring()` 接口
- 20+ 具体操作符实现：`Is`、`IsNot`、`IsOneOf`、`Gt`、`Gte`、`Lt`、`Lte`、`Contains`、`EqWildCard` 等
- `EsQueryBuilder` -- 静态方法集合，构建 match_phrase、wildcard、range、exists 等查询
- `Dsl` -- 顶层 DSL 组装器，将 query_string、filter、range 组合为完整的 bool query
- `NestedFieldQueryTransformer` -- 基于 luqum 的 nested 字段查询转换器

**迁移范围：**
- 主文件 `query_builder_logic.py`（738 行）
- 依赖 `constants.py` 中的 `WILDCARD_PATTERN`、`WILDCARD_QUERY`
- 依赖 `exceptions.py` 中的 `BaseSearchDslException`
- 可选依赖：`apps.log_search.constants` 中的 `ES_RESERVED_CHARACTERS`、`FieldDataTypeEnum`

**跨项目使用场景：**
- 任何需要动态构建 ES 查询的系统
- 可视化查询构建器的后端实现
- API 网关的 ES 查询代理层
- 数据分析平台的条件过滤引擎

---

### 2.3 dsl_builder.py -- DSL 构建器门面（22 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | DSL 构建的顶层封装，整合查询、过滤、排序、聚合 |
| 复用价值 | 5 | 一站式 DSL 构建，开发者无需了解底层细节 |
| 独立性 | 4 | 依赖 query_builder_logic，但无业务耦合 |
| 接口稳定性 | 4 | 构造函数参数设计合理，属性访问稳定 |
| 代码质量 | 5 | 门面模式应用得当，代码简洁清晰 |

**核心设计：**
- `DslBuilder` 类 -- 接收 search_string、filter_dict_list、time_range_dict、sort_tuple 等参数
- 内部调用 `Dsl` 类组装 query bool 结构
- 支持 search_after 分页、slice 分片搜索、collapse 去重
- 支持 aggs 聚合透传、highlight 高亮透传

**迁移范围：**
- 主文件 `dsl_builder.py`（194 行）
- 依赖 `query_builder_logic.py`

**跨项目使用场景：**
- ES 查询 API 服务
- 日志检索系统的查询层
- 数据导出工具的查询构建

---

### 2.4 QueryClientTemplate.py -- ES 查询客户端模板（21 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | 定义 ES 客户端的统一接口模板 |
| 复用价值 | 4 | 模板方法模式，新场景只需继承实现 |
| 独立性 | 5 | 仅依赖 elasticsearch 异常类，无业务耦合 |
| 接口稳定性 | 4 | 抽象接口稳定，扩展点明确 |
| 代码质量 | 4 | 模板方法模式实现规范，超时处理统一 |

**核心设计：**
- 定义 `query()`、`mapping()`、`es_route()` 三个抽象接口
- `catch_timeout_raise()` -- 统一处理 ES5/6/7+ 的超时异常
- `add_analyzer_details()` -- 为 mapping 结果补充自定义分词器信息

**迁移范围：**
- 主文件 `QueryClientTemplate.py`（104 行）
- 依赖 `exceptions.py` 中的 `EsTimeoutException`

**跨项目使用场景：**
- 需要对接多种 ES 数据源的系统
- ES 客户端的抽象层设计参考

---

### 2.5 decrypt.py -- 文件解密处理器框架（21 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | 通用的文件解密框架，支持多种加密算法 |
| 复用价值 | 4 | 抽象基类 + 具体实现，可直接复用或扩展 |
| 独立性 | 4 | 仅依赖标准库和 FeatureToggle 配置 |
| 接口稳定性 | 4 | 接口设计清晰，`decrypt()` 和 `decrypt_file()` 分离 |
| 代码质量 | 5 | ABC 抽象类、分块解密、明文检测、临时文件安全处理 |

**核心设计：**
- `BaseDecryptHandler` -- 抽象基类，定义 `decrypt(data)` 和 `decrypt_file(file_path)` 接口
- `XorDecryptHandler` -- 异或解密实现，支持分块处理（8KB）、明文自动检测（可打印字符比例阈值 90%）、未加密前缀跳过
- `get_decrypt_handler(bk_biz_id)` -- 工厂函数，根据业务 ID 从 FeatureToggle 配置动态获取解密处理器
- `DECRYPT_HANDLER_TYPE_MAP` -- 处理器类型注册表，支持扩展新的加密算法

**迁移范围：**
- 主文件 `decrypt.py`（181 行）
- 可选依赖 `apps.feature_toggle` 配置模块

**跨项目使用场景：**
- 文件上传/下载系统的加解密层
- 日志采集 agent 的文件解密
- 数据导入工具的加密文件处理
- 任何需要可插拔解密策略的系统

---

### 2.6 type_constants.py -- ES 查询类型定义（20 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 3 | ES 查询相关的类型别名定义 |
| 复用价值 | 3 | 提供类型安全，提升代码可读性 |
| 独立性 | 5 | 完全独立，仅使用 typing 标准库 |
| 接口稳定性 | 5 | 类型定义稳定不变 |
| 代码质量 | 4 | 类型别名命名规范，覆盖 ES 查询常用数据结构 |

**迁移范围：** 单文件 44 行，零依赖

---

### 2.7 exceptions.py (log_esquery) -- ES 查询异常体系（19 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 3 | ES 查询相关的异常定义 |
| 复用价值 | 3 | 异常层次清晰，可作为异常设计参考 |
| 独立性 | 5 | 仅依赖 BaseException 基类 |
| 接口稳定性 | 4 | 异常码和消息模板稳定 |
| 代码质量 | 4 | 分组清晰（权限/场景/时间/版本/客户端/查询），错误码体系完整 |

**迁移范围：** 主文件 244 行，依赖 `apps.exceptions.BaseException`

---

### 2.8 query_time_builder.py -- ES 时间范围构建器（19 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | ES 时间范围查询构建，支持多种时间字段类型 |
| 复用价值 | 4 | 处理 date/date_nanos/long 三种时间字段类型 |
| 独立性 | 3 | 依赖 TransferApi 获取存储保留时间 |
| 接口稳定性 | 4 | 构造函数参数稳定 |
| 代码质量 | 4 | 时间序列化逻辑清晰，支持缓存 |

**迁移范围：** 主文件 151 行，需剥离 `get_storage_retention_time` 对 TransferApi 的依赖

---

### 2.9 query_index_optimizer.py -- ES 索引时间分区优化器（19 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | 按时间范围优化 ES 索引选择，减少查询开销 |
| 复用价值 | 4 | 日志类 ES 索引普遍按日期分区，通用性强 |
| 独立性 | 3 | 依赖 Scenario model 和 arrow/dateutil |
| 接口稳定性 | 4 | 构造函数和 index 属性稳定 |
| 代码质量 | 4 | 索引长度限制（2000 字符）的优雅降级策略 |

**迁移范围：** 主文件 137 行，需剥离对 `Scenario` model 的直接引用

---

### 2.10 proto.py -- Trace 协议抽象基类（19 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | Trace 协议的抽象层设计，支持多种 trace 格式 |
| 复用价值 | 4 | 策略模式 + 工厂模式，新增协议只需继承 |
| 独立性 | 3 | 依赖 SearchHandler 和 AggsHandlers |
| 接口稳定性 | 4 | 抽象接口定义清晰 |
| 代码质量 | 4 | `judge_trace_type` 自动识别 trace 类型，`match_field` 字段匹配 |

**迁移范围：** 主文件 277 行，需携带 `constants.py` 中的 `TraceProto` 枚举

---

### 2.11 qos.py -- ES 查询 QoS 限流器（18 分）

**五维评分：**

| 维度 | 分数 | 说明 |
|------|------|------|
| 通用性 | 4 | 基于 Redis 的滑动窗口限流，通用性强 |
| 复用价值 | 4 | QosThrottle 可直接作为 DRF 限流类使用 |
| 独立性 | 3 | 依赖 Redis、Django settings、DRF throttling |
| 接口稳定性 | 3 | 与 BKLOG 配置强耦合 |
| 代码质量 | 4 | 滑动窗口 + ZSet 实现，自动恢复机制 |

**迁移范围：** 主文件 144 行，需参数化配置项

---

### 2.12 query_filter_builder.py / query_sort_builder.py / query_string_builder.py（各 18 分）

这三个 Builder 类结构相似，均为 ES 查询参数的预处理器：

- **query_filter_builder.py**（47 行）-- 过滤条件标准化，提取 field/operator/value/condition/type
- **query_sort_builder.py**（44 行）-- 排序条件标准化，支持 asc/desc
- **query_string_builder.py**（53 行）-- 查询字符串处理，HTML 转码 + 特殊字符检测 + 通配符包裹

**共同特点：** 小而精的 Builder 类，单一职责，零业务耦合，可作为 Builder 模式的教学参考。

---

## 3. 有条件迁移目标（总分 15-17）

| 文件 | 总分 | 条件说明 |
|------|------|----------|
| `esquery.py` | 17 | 需剥离对 Scenario/Space model 的依赖，提取核心 search/scroll/dsl 方法 |
| `QueryClient.py` | 17 | 工厂模式实现，需将 Scenario 映射改为配置化 |
| `constants.py` (log_esquery) | 16 | 业务常量，需参数化 |
| `metrics.py` (log_esquery) | 16 | Prometheus 指标定义，可作为指标设计参考 |
| `QueryClientEs.py` | 15 | 需剥离 TransferApi 依赖，保留 ES 连接和查询核心逻辑 |
| `QueryClientLog.py` | 15 | 同上，额外需剥离 CollectorConfig model 依赖 |
| `version_checker.py` | 15 | ES 版本检测，可作为 HTTP 探活参考 |
| `constants.py` (log_trace) | 17 | Trace 协议常量和映射定义，可作为 trace 字段映射参考 |
| `exceptions.py` (log_trace) | 16 | Trace 异常定义，结构清晰 |
| `elastic.py` | 15 | OpenTelemetry ES 集成，需确认 otel 版本兼容性 |
| `proto/log.py` | 15 | Log Trace 协议实现，依赖 SearchHandler |
| `proto/otlp.py` | 15 | OTLP Trace 协议实现，Jaeger 格式转换逻辑有参考价值 |
| `trace_field_handlers.py` | 15 | Trace 字段处理，映射适配器模式有参考价值 |
| `authentication.py` (grafana) | 17 | NoCsrf 认证类，DRF 扩展参考 |
| `constants.py` (grafana) | 16 | Grafana 集成常量 |
| `exceptions.py` (grafana) | 16 | Grafana 异常定义 |
| `utils.py` (grafana) | 16 | XNDJSON 解析器，DRF Parser 扩展参考 |
| `query.py` (grafana) | 15 | Grafana 查询处理器，聚合和时间序列格式化逻辑有参考价值 |
| `data_source.py` (grafana) | 15 | 自定义 ES 数据源，Grafana DataSource 适配模式有参考价值 |
| `base.py` (tgpa) | 16 | 文件处理框架，下载/解压/解密/处理流程有参考价值 |
| `constants.py` (tgpa) | 16 | TGPA 任务常量和枚举定义 |
| `exceptions.py` (tgpa) | 16 | TGPA 异常定义 |

---

## 4. 不迁移模块说明

| 文件 | 总分 | 不迁移原因 |
|------|------|------------|
| `QueryClientBkData.py` | 13 | 深度耦合 BkDataQueryApi/BkDataMetaApi/BkDataStorekitApi，剥离成本高于收益 |
| `permission.py` (log_esquery) | 12 | 空壳类，仅继承 Permission，无实际逻辑 |
| `trace_handlers.py` | 13 | 纯委托类，56 行全部是对 Proto 的转发调用 |
| `trace_config_handlers.py` | 12 | 深度耦合 Grafana 和 LogIndexSet model |
| `permissions.py` (grafana) | 13 | 耦合 IAM 权限体系和 GrafanaRole |
| `provisioning.py` | 14 | 耦合 Grafana Provisioning 框架和 TraceDatasourceMap model |
| `home_dashboard.py` | 14 | 硬编码的 Grafana 首页面板配置，纯展示逻辑 |
| `monitor.py` | 10 | 仅 38 行，单个 API 调用封装 |
| `model.py` (grafana) | 14 | Django Model，按规则排除 |
| `report.py` (tgpa) | 12 | 深度耦合 TGPAReport model 和 QueryClientBkData |
| `task.py` (tgpa) | 12 | 深度耦合 TGPATask model 和 TGPATaskApi |
| `tasks.py` | 9 | Celery 定时任务编排，强耦合 Django model 和业务流程 |

---

## 5. 设计参考索引

以下模块虽未达到迁移阈值，但其设计模式和实现思路具有参考价值：

### 5.1 架构模式参考

| 模式 | 参考文件 | 关键设计 |
|------|----------|----------|
| **策略模式** | `query_builder_logic.py` | `BoolQueryOperation` 基类 + 20+ 操作符子类，`get_op()` 工厂方法 |
| **模板方法** | `QueryClientTemplate.py` | 定义 `query()`/`mapping()`/`es_route()` 抽象接口 |
| **工厂模式** | `QueryClient.py` | 根据 scenario_id 动态加载客户端类 |
| **Builder 模式** | `query_filter_builder.py` / `query_sort_builder.py` / `query_string_builder.py` | 单一职责的参数构建器 |
| **门面模式** | `dsl_builder.py` | 封装底层 DSL 构建复杂度 |
| **策略+工厂** | `proto.py` | `judge_trace_type()` 自动识别 + `get_proto()` 动态加载 |
| **适配器模式** | `data_source.py` / `ESBodyAdapter` | Grafana ES7 语法与日志检索语法的适配 |
| **装饰器模式** | `elastic.py` | OpenTelemetry ES 集成，wrapt 函数包装 |

### 5.2 通用工具参考

| 功能 | 参考文件 | 关键实现 |
|------|----------|----------|
| **ES 多版本兼容** | `es_client.py` | ES5/6/7+ 客户端自动选择 |
| **IPv4/IPv6 双栈** | `es_client.py` | `ipaddress` 模块检测 + 方括号处理 |
| **滑动窗口限流** | `qos.py` | Redis ZSet + 时间窗口 + 自动恢复 |
| **分块文件解密** | `decrypt.py` | 8KB 分块、明文检测、临时文件安全处理 |
| **嵌套 ZIP 解压** | `base.py` | 递归解压 + 路径穿越防护 + 最大迭代限制 |
| **NDJSON 解析** | `utils.py` (grafana) | DRF BaseParser 扩展 |
| **时间序列格式化** | `query.py` (grafana) | `_format_time_series()` Grafana TimeSeries 格式转换 |
| **Jaeger 格式转换** | `otlp.py` / `log.py` | OTLP/Log Trace 到 Jaeger 格式的完整转换 |
| **索引时间优化** | `query_index_optimizer.py` | 按日期范围裁剪索引，长度限制降级 |
| **批量并发执行** | 多处使用 `MultiExecuteFunc` | 线程池并发执行多个查询 |

### 5.3 异常体系参考

| 层次 | 参考文件 | 设计要点 |
|------|----------|----------|
| **模块级基类** | `exceptions.py` (各模块) | `MODULE_CODE` + `BaseException` 继承 |
| **错误码体系** | `exceptions.py` (log_esquery) | 分组编号：911-权限、921-场景、931-时间、941-版本、950-客户端、961-查询 |
| **消息模板** | 各 exceptions.py | `_()` 国际化 + `{param}` 参数化 |

---

## 6. 总结

**统计概览：**
- 总评估文件：49 个
- 值得迁移（>=18）：13 个文件，约 1,766 行
- 有条件迁移（15-17）：22 个文件，约 4,800 行
- 不迁移：14 个文件，约 2,100 行

**最高价值模块 TOP 5：**
1. `es_client.py`（24 分）-- ES 客户端工具集，零业务耦合，直接复用
2. `query_builder_logic.py`（23 分）-- ES DSL 构建引擎，策略模式典范
3. `dsl_builder.py`（22 分）-- DSL 构建门面，一站式查询构建
4. `QueryClientTemplate.py`（21 分）-- 客户端模板，模板方法模式
5. `decrypt.py`（21 分）-- 解密处理器框架，可插拔设计

**迁移建议：**
- 优先迁移 `es_client.py` + `query_builder_logic.py` + `dsl_builder.py`，这三者构成完整的 ES 查询构建工具链
- `decrypt.py` 可独立迁移，作为文件解密的通用框架
- 有条件迁移的文件建议在 CodeHub 中重构后再整合，剥离业务耦合后价值更高
