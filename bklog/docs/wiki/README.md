# BKLOG 技术Wiki 📚

> 包含代码解析的深度技术文档，帮助你快速理解核心实现

---

## 📋 文档导航

### 一、API统一调用层 ✅ (8/8 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-DataAPI核心实现](./api/01-DataAPI核心实现.md) | ✅ 已生成 | HTTP请求封装、`__call__`入口、`_send_request`核心逻辑 |
| [02-钩子函数机制](./api/02-钩子函数机制.md) | ✅ 已生成 | `before_request`/`after_request`设计、ESB认证注入 |
| [03-重试机制详解](./api/03-重试机制详解.md) | ✅ 已生成 | `DataApiRetryClass`实现、异常触发重试、结果校验重试 |
| [04-并发请求封装](./api/04-并发请求封装.md) | ✅ 已生成 | `bulk_request`分页并发、`batch_request`切片并发 |
| [05-DRF适配器](./api/05-DRF适配器.md) | ✅ 已生成 | `DataDRFAPISet`自动生成CRUD、动态方法生成 |
| [06-API并发请求详解](./api/06-API并发请求详解.md) | ✅ 已生成 | `bulk_request`/`batch_request`完整实现、OpenTelemetry上下文传递 |
| [06-多租户架构](./api/06-多租户架构.md) | ✅ 已生成 | bk_tenant_id处理、biz_to_tenant_getter工厂 |
| [07-数据平台集成](./api/07-数据平台集成.md) | ✅ 已生成 | DataID创建、清洗管理、BKData API封装、权限认证 |

### 二、ES查询底层封装 ✅ (6/6 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-EsQuery主入口实现](./log_esquery/01-EsQuery主入口实现.md) | ✅ 已生成 | search/dsl/mapping/scroll方法、`_optimizer`初始化 |
| [02-多场景策略模式](./log_esquery/02-多场景策略模式.md) | ✅ 已生成 | LOG/BKDATA/ES三种场景、`QueryClient`工厂 |
| [03-DSL构建器详解](./log_esquery/03-DSL构建器详解.md) | ✅ 已生成 | `DslBuilder`、QueryStringBuilder、QueryFilterBuilder |
| [04-索引优化策略](./log_esquery/04-索引优化策略.md) | ✅ 已生成 | `QueryIndexOptimizer`、时间范围索引压缩 |
| [05-ES多场景策略详解](./log_esquery/05-ES多场景策略详解.md) | ✅ 已生成 | `QueryClientTemplate`、三种客户端实现详解 |
| [06-QoS限流实现](./log_esquery/06-QoS限流实现.md) | ✅ 已生成 | `QosThrottle`、Redis ZSet滑动窗口 |

### 三、日志检索核心 ✅ (9/9 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-SearchHandler核心实现](./log_search/01-SearchHandler核心实现.md) | ✅ 已生成 | 初始化流程、search入口、`_multi_search`多集群 |
| [02-预查询优化机制](./log_search/02-预查询优化机制.md) | ✅ 已生成 | `PRE_SEARCH_SECONDS`、降序/升序策略 |
| [03-聚合分析实现](./log_search/03-聚合分析实现.md) | ✅ 已生成 | Terms/DateHistogram聚合、DSL构建、结果解析 |
| [04-滚动分页实现](./log_search/04-滚动分页实现.md) | ✅ 已生成 | `_scroll`方法、scroll_id管理、触发条件 |
| [05-高亮实现](./log_search/05-高亮实现.md) | ✅ 已生成 | `_init_highlight`、`<mark>`标签、Object字段处理 |
| [06-OPERATORS映射详解](./log_search/06-OPERATORS映射详解.md) | ✅ 已生成 | 字段类型操作符映射表、OperatorEnum定义 |
| [07-特性开关架构](./log_search/07-特性开关架构.md) | ✅ 已生成 | `FeatureToggleObject`应用 |
| [08-索引集管理](./log_search/08-索引集管理.md) | ✅ 已生成 | LogIndexSet模型、IndexSetHandler处理器 |
| [09-字段统计分析](./log_search/09-字段统计分析.md) | ✅ 已生成 | TopK统计、去重计数、数值分布、FieldViewSet |

### 四、数据管道模块 ✅ (9/9 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-CollectorHandler采集管理](./log_databus/01-CollectorHandler采集管理.md) | ✅ 已生成 | `RETRIEVE_CHAIN`责任链、start/stop生命周期 |
| [02-Kafka消费实现](./log_databus/02-Kafka消费实现.md) | ✅ 已生成 | `KafkaConsumerHandle`、SSL/SASL安全协议 |
| [03-采集任务调度](./log_databus/03-采集任务调度.md) | ✅ 已生成 | `@periodic_task`、`@share_lock`分布式锁 |
| [04-ETL处理策略](./log_databus/04-ETL处理策略.md) | ✅ 已生成 | 四种清洗策略、`EtlStorage`工厂、V4数据链路 |
| [05-ES存储管理](./log_databus/05-ES存储管理.md) | ✅ 已生成 | `StorageHandler`、连通性检测 |
| [05-清洗策略模式详解](./log_databus/05-清洗策略模式详解.md) | ✅ 已生成 | 四种清洗策略详细实现、EtlStorage工厂类 |
| [06-异步任务设计](./log_databus/06-异步任务设计.md) | ✅ 已生成 | Celery任务架构、@periodic_task/@high_priority_task |
| [07-容器采集实现](./log_databus/07-容器采集实现.md) | ✅ 已生成 | K8sCollectorHandler、Bcs工具类、CRD配置下发 |
| [08-节点管理集成](./log_databus/08-节点管理集成.md) | ✅ 已生成 | NodeApi/TransferApi封装、订阅创建、主机采集下发 |

### 五、分布式追踪 ✅ (4/4 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-OpenTelemetry集成](./log_trace/01-OpenTelemetry集成.md) | ✅ 已生成 | `BluekingInstrumentor`、各组件埋点 |
| [02-Trace查询实现](./log_trace/02-Trace查询实现.md) | ✅ 已生成 | `Proto`抽象基类、LogTrace/OtlpTrace协议、Span树构建 |
| [03-调用链树构建](./log_trace/03-调用链树构建.md) | ✅ 已生成 | `build_tree`递归算法、父子关系建立 |
| [04-懒加载Span处理器](./log_trace/04-懒加载Span处理器.md) | ✅ 已生成 | `LazyBatchSpanProcessor`延迟启动线程 |

### 六、AI助手模块 ✅ (5/5 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-日志智能解读](./ai_assistant/01-日志智能解读.md) | ✅ 已生成 | `ChatHandler.interpret_log`、Prompt模板、上下文截取 |
| [02-流式响应实现](./ai_assistant/02-流式响应实现.md) | ✅ 已生成 | SSE流式响应机制、StreamingHttpResponse、指标监控 |
| [03-本地命令处理器](./ai_assistant/03-本地命令处理器.md) | ✅ 已生成 | 装饰器注册模式、`LocalCommandRegistry`、命令分发机制 |
| [04-上下文智能清理](./ai_assistant/04-上下文智能清理.md) | ✅ 已生成 | 日志上下文清理逻辑 |
| [05-AI检索助手实现](./ai_assistant/05-AI检索助手实现.md) | ✅ 已生成 | ChatHandler/AIDevInterface、本地命令处理器、指标上报、MCP认证 |

### 七、权限管理模块 ✅ (3/4)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-IAM权限控制](./iam/01-IAM权限控制.md) | ✅ 已生成 | `Permission`核心类、`ActionEnum`动作、DRF权限插件 |
| [02-V1V2兼容机制](./iam/02-V1V2兼容机制.md) | ✅ 已生成 | `CompatibleIAM`策略合并、表达式转换、迁移命令 |
| 03-DRF权限插件 | ⏳ 待生成 | 详细权限类解析 |
| [04-资源路径注入](./iam/04-资源路径注入.md) | ✅ 已生成 | `_bk_iam_path_`计算 |

### 八、公共组件层 (0/3)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| 01-IPv6双栈适配 | ⏳ 待生成 | `adapt_ipv6.py` |
| 02-Token工厂模式 | ⏳ 待生成 | `TokenHandlerFactory` |
| 03-ITSM审批集成 | ⏳ 待生成 | `ExternalPermission`模型 |

### 九、基础设施层 ✅ (4/4 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [01-多租户架构](./infrastructure/01-多租户架构.md) | ✅ 已生成 | `bk_tenant_id`获取传递、线程本地存储、前端TenantManager |
| [02-Redis缓存机制](./infrastructure/02-Redis缓存机制.md) | ✅ 已生成 | `using_cache`装饰器、`RedisLock`分布式锁 |
| [03-时间处理工具](./infrastructure/03-时间处理工具.md) | ✅ 已生成 | `timeformat_to_timestamp`转换、`generate_time_range`范围生成、时区处理 |
| [04-存储集群管理](./infrastructure/04-存储集群管理.md) | ✅ 已生成 | ES版本兼容、`StorageClusterRecord`集群切换、多集群查询 |

### 十、设计模式总结 ✅ (4/4 完成)
| 文档 | 状态 | 核心内容 |
|------|------|----------|
| [责任链模式应用](./patterns/责任链模式应用.md) | ✅ 已生成 | `RETRIEVE_CHAIN`、CollectorHandler链式处理 |
| [策略模式应用](./patterns/策略模式应用.md) | ✅ 已生成 | QueryClient/EtlStorage/Proto三种策略模式 |
| [工厂模式应用](./patterns/工厂模式应用.md) | ✅ 已生成 | EtlStorage/Proto/QueryClient工厂类 |
| [设计模式总结](./patterns/04-设计模式总结.md) | ✅ 已生成 | 策略/工厂/模板方法/责任链/建造者/装饰器六大模式 |

---

## 📊 文档统计

**已生成**: **50** 篇核心技术文档
**待生成**: **4** 篇文档

| 模块 | 已生成 | 待生成 | 总计 |
|-----|--------|--------|------|
| api | 8 | 0 | 8 |
| log_esquery | 6 | 0 | 6 |
| log_search | 9 | 0 | 9 |
| log_databus | 9 | 0 | 9 |
| log_trace | 4 | 0 | 4 |
| ai_assistant | 5 | 0 | 5 |
| iam | 3 | 1 | 4 |
| log_commons | 0 | 3 | 3 |
| infrastructure | 4 | 0 | 4 |
| patterns | 4 | 0 | 4 |

---

## 🗺️ 学习路径建议

### 📖 第1周：基础层
建议顺序：`api` → `log_esquery` → `infrastructure/01-多租户架构`

### 🔍 第2周：核心业务
建议顺序：`log_search` → `log_databus`

### 🔗 第3周：扩展能力
建议顺序：`log_trace` → `iam`

### 🔧 第4周：基础设施与模式
建议顺序：`infrastructure/02-Redis缓存机制` → `patterns`

---

## 📝 文档特点

- ✅ **完整代码片段**（标注源文件行号）
- 📊 **Mermaid流程图/类图**可视化
- 💡 **设计要点**深度解析
- 🔗 **Wiki式文档互联**

---

## 🎯 重点推荐阅读

**新手入门必读**:
1. [DataAPI核心实现](./api/01-DataAPI核心实现.md) - 理解系统API调用基础
2. [ES多场景策略详解](./log_esquery/05-ES多场景策略详解.md) - 理解查询场景架构
3. [SearchHandler核心实现](./log_search/01-SearchHandler核心实现.md) - 理解日志检索核心

**进阶深入学习**:
1. [ETL处理策略](./log_databus/04-ETL处理策略.md) - 理解数据清洗架构
2. [Trace查询实现](./log_trace/02-Trace查询实现.md) - 理解分布式追踪
3. [懒加载Span处理器](./log_trace/04-懒加载Span处理器.md) - 理解OpenTelemetry线程优化
4. [IAM权限控制](./iam/01-IAM权限控制.md) - 理解权限系统设计

**架构设计参考**:
1. [多租户架构](./infrastructure/01-多租户架构.md) - 理解多租户实现
2. [Redis缓存机制](./infrastructure/02-Redis缓存机制.md) - 理解缓存与锁设计
3. [CollectorHandler采集管理](./log_databus/01-CollectorHandler采集管理.md) - 理解责任链模式
4. [策略模式应用](./patterns/策略模式应用.md) - 理解QueryClient/EtlStorage策略设计
5. [工厂模式应用](./patterns/工厂模式应用.md) - 理解动态类加载工厂

---

**文档版本**: v2.0
**更新日期**: 2026-04-30
**源码项目**: `bklog` 蓝鲸日志平台