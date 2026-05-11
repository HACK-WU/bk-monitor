# BKLOG 技术Wiki 文档目录规划

> 本目录规划了 bklog 项目技术Wiki的文档结构，每个文档包含核心代码解析和实现原理。

---

## 📚 Wiki 总索引

```
docs/wiki/
├── README.md                    # Wiki索引页（导航入口）
│
├── api/                         # API统一调用层
│   ├── 01-DataAPI核心实现.md
│   ├── 02-钩子函数机制.md
│   ├── 03-重试机制详解.md
│   ├── 04-并发请求封装.md
│   ├── 05-DRF风格API集合.md
│   └── 06-多租户架构.md
│
├── log_esquery/                 # ES查询底层封装
│   ├── 01-EsQuery主入口实现.md
│   ├── 02-多场景策略模式.md
│   ├── 03-DSL构建器详解.md
│   ├── 04-索引优化策略.md
│   ├── 05-ES版本适配.md
│   └── 06-QoS限流实现.md
│
├── log_search/                  # 日志检索核心
│   ├── 01-SearchHandler核心实现.md
│   ├── 02-预查询优化机制.md
│   ├── 03-多集群查询合并.md
│   ├── 04-滚动分页实现.md
│   ├── 05-OPERATORS映射详解.md
│   ├── 06-聚合处理器.md
│   └── 07-特性开关架构.md
│
├── log_databus/                 # 数据管道模块
│   ├── 01-CollectorHandler采集管理.md
│   ├── 02-清洗策略模式.md
│   ├── 03-责任链检索机制.md
│   ├── 04-Kafka消费者实现.md
│   ├── 05-ES存储管理.md
│   └── 06-异步任务设计.md
│
├── log_trace/                   # 分布式追踪
│   ├── 01-OpenTelemetry集成.md
│   ├── 02-协议适配器模式.md
│   ├── 03-调用链树构建.md
│   └── 04-懒加载Span处理器.md
│
├── ai_assistant/                # AI助手模块
│   ├── 01-日志智能解读.md
│   ├── 02-流式响应实现.md
│   ├── 03-本地命令处理器.md
│   └── 04-上下文智能清理.md
│
├── iam/                         # 权限管理模块
│   ├── 01-Permission核心类.md
│   ├── 02-V1V2兼容机制.md
│   ├── 03-DRF权限插件.md
│   └── 04-资源路径注入.md
│
├── log_commons/                 # 公共组件层
│   ├── 01-IPv6双栈适配.md
│   ├── 02-Token工厂模式.md
│   └── 03-ITSM审批集成.md
│
├── infrastructure/              # 基础设施层
│   ├── 01-Celery任务设计.md
│   ├── 02-Redis缓存机制.md
│   ├── 03-分布式锁实现.md
│   └── 04-ES连接池管理.md
│
└── patterns/                    # 设计模式总结
    ├── 策略模式应用.md
    ├── 工厂模式应用.md
    ├── 责任链模式应用.md
    └── Builder模式应用.md
```

---

## 📋 各文档详细内容规划

---

## 一、api/ 模块（6个文档）

### 1. `01-DataAPI核心实现.md`

**聚焦**：`apps/api/base.py` 的 `DataAPI` 类

**内容大纲**：
```markdown
## 1. DataAPI 类定位
   - 在整个系统中的作用
   - 与 DataResponse、DataApiRetryClass 的关系图

## 2. __init__() 初始化
   - 核心参数详解（url/method/module/before_request/after_request/cache_time）
   - 完整代码片段（行号200-275）
   - 参数设计意图解析

## 3. __call__() 主入口
   - 调用流程图
   - 完整代码片段（行号277-319）
   - raw参数的处理逻辑

## 4. _send_request() 核心逻辑
   - 缓存检查流程
   - 重试机制触发条件
   - 完整代码片段（行号332-480）
   - finally块的日志记录设计

## 5. _send() 底层HTTP发送
   - headers构建（含ESB认证）
   - cookies处理
   - 文件上传支持
   - 完整代码片段（行号509-600）

## 6. 设计要点总结
   - 钩子函数注入点
   - 缓存命中判断
   - 超时处理策略
```

---

### 2. `02-钩子函数机制.md`

**聚焦**：`before_request` 和 `after_request` 钩子

**内容大纲**：
```markdown
## 1. 钩子函数设计意图
   - 模板方法模式的应用
   - 解耦请求预处理和响应后处理

## 2. before_request 调用点
   - 代码位置：base.py:332-345
   - 典型实现示例（modules/utils.py）
   - ESB认证信息注入完整代码
   - add_esb_info_before_request() 源码解析

## 3. after_request 调用点
   - 代码位置：base.py:406-418
   - 响应数据清洗示例
   - 蓝鲸格式返回码处理

## 4. 实战案例：CCApi的钩子应用
   - cc.py中的before_request配置
   - biz_to_tenant_getter() 多租户ID转换代码

## 5. 如何自定义钩子
   - 编写指南
   - 最佳实践
```

---

### 3. `03-重试机制详解.md`

**聚焦**：`DataApiRetryClass` 类

**内容大纲**：
```markdown
## 1. 重试机制设计背景
   - 网络抖动、服务暂时不可用场景

## 2. DataApiRetryClass 类结构
   - 完整代码片段（行号108-174）
   - 核心属性解析：
     - stop_max_attempt_number
     - fail_exceptions
     - fail_check_functions

## 3. 两类重试触发方式
   - 异常触发重试：retry_on_exception()
   - 结果校验重试：retry_on_result()
   - 对比代码示例

## 4. 重试策略配置示例
   - CCApi的重试配置
   - BkDataQueryApi的重试配置
   - 实际使用代码

## 5. check_result_is_true() 函数
   - 源码解析（行号176-181）
   - 与fail_check_functions配合

## 6. 重试与超时的关系
   - 超时异常是否触发重试
   - 重试次数与超时时间的权衡
```

---

### 4. `04-并发请求封装.md`

**聚焦**：`bulk_request()` 和 `batch_request()`

**内容大纲**：
```markdown
## 1. 并发请求场景
   - 分页遍历全量数据
   - 大批量数据处理

## 2. bulk_request() 分页并发
   - 完整代码片段（行号676-741）
   - 参数详解：
     - get_data: 从响应提取数据函数
     - get_count: 获取总数函数
     - page_size: 分页大小
   - 自动分页逻辑解析
   - ThreadPool并发实现

## 3. batch_request() 切片并发
   - 完整代码片段（行号632-674）
   - chunk_key与chunk_values配合
   - 切片策略解析

## 4. thread_activate_request() 线程封装
   - 代码片段（行号743-769）
   - OpenTelemetry上下文传递
   - 为什么需要线程安全封装

## 5. 实战案例
   - CCApi.list_biz_hosts批量主机查询
   - BkDataMetaApi批量结果表获取

## 6. 性能考量
   - 线程数控制
   - 内存占用优化
```

---

### 5. `05-DRF风格API集合.md`

**聚焦**：`DataDRFAPISet` 类

**内容大纲**：
```markdown
## 1. DataDRFAPISet 设计灵感
   - 借鉴Django REST Framework
   - 自动生成CRUD方法

## 2. 类结构解析
   - 完整代码片段（行号804-904）
   - BASE_ACTIONS定义
   - primary_key参数作用

## 3. __getattr__() 动态方法生成
   - 如何根据action名称返回DataAPI
   - to_url()路径拼接逻辑

## 4. DRFActionAPI 定义
   - detail参数（实例/列表操作）
   - url_path参数（自定义路径）
   - method参数（HTTP方法）
   - 完整代码片段（行号788-801）

## 5. 实战案例：BkDataMetaApi
   - result_tables的DataDRFAPISet配置
   - custom_config的扩展action
   - 使用示例代码

## 6. 如何扩展自定义Action
   - 编写指南
   - 最佳实践
```

---

### 6. `06-多租户架构.md`

**聚焦**：多租户ID处理机制

**内容大纲**：
```markdown
## 1. 多租户架构背景
   - 蓝鲸平台的多租户设计

## 2. bk_tenant_id 注入点
   - _send()中的headers构建（行号541-553）
   - 完整代码片段解析

## 3. 动态获取租户ID
   - bk_tenant_id参数支持函数
   - get_request_tenant_id()实现

## 4. biz_to_tenant_getter()
   - modules/utils.py完整代码（行号361-381）
   - 业务ID到租户ID转换逻辑

## 5. space_to_tenant_getter()
   - 完整代码（行号384-405）
   - 空间UID到租户ID转换

## 6. 多租户数据隔离
   - 各模块如何使用多租户机制
   - 实际案例
```

---

## 二、log_esquery/ 模块（6个文档）

### 1. `01-EsQuery主入口实现.md`

**聚焦**：`apps/log_esquery/esquery/esquery.py` 的 `EsQuery` 类

**内容大纲**：
```markdown
## 1. EsQuery 类定位
   - ES查询的主入口
   - 与QueryClient、DslBuilder的关系

## 2. __init__() 初始化
   - 核心参数：index_set_id、scenario_id
   - _optimizer初始化流程
   - 完整代码片段

## 3. search() 核心查询方法
   - 完整代码片段（核心实现）
   - 查询参数处理流程
   - 调用QueryClient.execute()

## 4. dsl() DSL直接查询
   - 参数校验
   - 直接执行ES DSL

## 5. mapping() 字段映射获取
   - 如何获取ES索引mapping
   - 字段类型解析

## 6. scroll() 滚动查询
   - 大结果集分批获取
   - scroll_id管理

## 7. indices() 索引列表
   - 获取可用索引
```

---

### 2. `02-多场景策略模式.md`

**聚焦**：`QueryClient` 工厂类及三种客户端实现

**内容大纲**：
```markdown
## 1. 三种查询场景
   - LOG：蓝鲸采集
   - BKDATA：数据平台
   - ES：第三方ES集群

## 2. QueryClient 工厂类
   - 完整代码片段（QueryClient.py）
   - scenario_id映射字典
   - import_string动态导入

## 3. QueryClientTemplate 抽象基类
   - 定义统一接口
   - catch_timeout_raise超时捕获
   - 完整代码片段

## 4. QueryClientLog 实现
   - 如何通过TransferApi获取集群信息
   - 核心代码解析
   - 预览最新日志

## 5. QueryClientBkData 实现
   - 通过BkDataQueryApi查询
   - 与数据平台的交互

## 6. QueryClientEs 实现
   - 直接连接ES集群
   - 集群信息获取

## 7. 场景选择逻辑
   - 如何根据索引集配置选择客户端
```

---

### 3. `03-DSL构建器详解.md`

**聚焦**：`DslBuilder` 及各Builder组件

**内容大纲**：
```markdown
## 1. DSL构建架构
   - Builder模式的应用
   - 各组件关系图

## 2. DslBuilder 主构建器
   - 完整代码片段（dsl_builder.py）
   - 组合各Builder的逻辑

## 3. QueryStringBuilder 查询字符串
   - Lucene语法处理
   - HTML转码
   - 通配符处理
   - 完整代码片段

## 4. QueryFilterBuilder 过滤条件
   - filter参数规范化
   - 多字段过滤逻辑

## 5. QueryTimeBuilder 时间范围
   - date/long类型时间字段
   - 时间单位转换
   - 完整代码片段

## 6. QuerySortBuilder 排序
   - 多字段排序
   - _score排序支持

## 7. Dsl 最终组装类
   - bool.filter结构
   - 完整query DSL生成
```

---

### 4. `04-索引优化策略.md`

**聚焦**：`QueryIndexOptimizer`

**内容大纲**：
```markdown
## 1. 索引优化背景
   - 避免全索引扫描
   - 减少ES集群压力

## 2. QueryIndexOptimizer 类
   - 完整代码片段（query_index_optimizer.py）
   - 核心方法解析

## 3. 时间范围判断逻辑
   - 单日查询：index_YYYYMMDD*
   - 15日内查询：按日期展开
   - 单月查询：index_YYYYMM*
   - 多月查询：最近6个月

## 4. 索引压缩缓存
   - COMPRESS_INDICES_CACHE_KEY_LENGTH
   - MD5哈希处理长索引名

## 5. 性能效果分析
   - 查询耗时对比
   - ES负载降低
```

---

### 5. `05-ES版本适配.md`

**聚焦**：`get_es_client()` 函数

**内容大纲**：
```markdown
## 1. ES版本兼容需求
   - ES 5.x/6.x/7.x API差异

## 2. get_es_client() 函数
   - 完整代码片段（es_client.py）
   - 版本号判断逻辑
   - 客户端类选择

## 3. 多版本客户端库
   - elasticsearch（默认7.x）
   - elasticsearch5
   - elasticsearch6

## 4. 连接参数处理
   - hosts/username/password/port
   - IPv6地址支持
   - SSL/TLS配置

## 5. es_socket_ping() 连通性检测
   - Socket连接测试
   - IPv4/IPv6支持
   - 完整代码片段

## 6. EsVersionChecker 版本检测
   - HTTP请求获取版本号
   - 缓存机制
```

---

### 6. `06-QoS限流实现.md`

**聚焦**：`QosThrottle` 类

**内容大纲**：
```markdown
## 1. QoS限流背景
   - 保护ES集群
   - 防止滥用

## 2. QosThrottle 类
   - 完整代码片段（qos.py）
   - DRF throttle基类继承

## 3. Redis ZSet 滑动窗口
   - zadd添加请求记录
   - zremrangebyscore清理过期记录
   - zcard统计窗口内请求数

## 4. 限流对象标识
   - 索引集ID
   - indices列表

## 5. 配置参数
   - BKLOG_QOS_USE开关
   - BKLOG_QOS_LIMIT阈值
   - BKLOG_QOS_LIMIT_WINDOW窗口时间

## 6. 超限处理
   - 设置_limit标记
   - 返回429状态码
```

---

## 三、log_search/ 模块（7个文档）

### 1. `01-SearchHandler核心实现.md`

**聚焦**：`search_handlers_esquery.py` 的 `SearchHandler` 类

**内容大纲**：
```markdown
## 1. SearchHandler 定位
   - 日志检索的核心处理器
   - 与ViewSet、EsQuery的关系

## 2. __init__() 初始化流程
   - 完整代码片段（行号167-352）
   - 关键参数解析：
     - index_set_id
     - time_field
     - query_string
     - highlight
     - sort_list
   - 各组件初始化顺序图

## 3. search() 核心查询入口
   - 完整代码片段（行号643-711）
   - 预查询判断逻辑
   - 调用_multi_search()

## 4. _multi_search() 多集群查询
   - 完整代码片段（行号800-899）
   - 预查询模式与正常模式
   - 结果合并与排序

## 5. _deal_query_result() 结果处理
   - 脱敏处理
   - 字段长度分析
   - 保存检索历史

## 6. fields() 字段信息获取
   - 多种功能配置检查
   - mapping缓存

## 7. get_sort_group() 排序构建
   - time_field + gseIndex + iterationIndex
```

---

### 2. `02-预查询优化机制.md`

**聚焦**：预查询（pre-search）逻辑

**内容大纲**：
```markdown
## 1. 预查询设计意图
   - 大时间范围查询优化
   - 快速定位目标日志

## 2. PRE_SEARCH_SECONDS 配置
   - 默认预查询时间窗口
   - 如何根据场景调整

## 3. 预查询触发条件
   - 时间范围判断
   - 完整代码片段

## 4. 降序查询策略
   - 从结束时间往前查
   - 代码实现解析

## 5. 升序查询策略
   - 从开始时间往后查
   - 代码实现解析

## 6. 结果不足处理
   - 判断逻辑
   - 回退到全量查询

## 7. 性能效果分析
   - 查询耗时对比
```

---

### 3. `03-多集群查询合并.md`

**聚焦**：`StorageClusterRecord` 和 `MultiExecuteFunc`

**内容大纲**：
```markdown
## 1. 多集群查询场景
   - ES集群切换
   - 历史数据保留

## 2. StorageClusterRecord 模型
   - 记录历史存储集群
   - 字段定义
   - 完整代码片段

## 3. MultiExecuteFunc 并发执行
   - ThreadPool并发查询
   - 完整代码片段
   - 如何获取历史集群列表

## 4. 结果合并策略
   - 按时间排序
   - 去重处理

## 5. 集群切换流程
   - 新集群启用
   - 旧集群记录

## 6. 实战案例
   - 存储迁移场景
```

---

### 4. `04-滚动分页实现.md`

**聚焦**：`_scroll()` 方法

**内容大纲**：
```markdown
## 1. 滚动分页触发条件
   - MAX_RESULT_WINDOW（10000）
   - 异步导出场景

## 2. _scroll() 方法实现
   - 完整代码片段
   - scroll_id管理
   - SCROLL有效期（1m/5m）

## 3. scroll API参数
   - scroll参数
   - size参数
   - body构建

## 4. 分批获取逻辑
   - 循环获取直到结果为空
   - 内存控制

## 5. clear_scroll() 清理
   - 释放ES资源
   - 代码实现

## 6. 异步导出使用
   - ASYNC_EXPORT_SCROLL配置
   - 与Celery任务配合
```

---

### 5. `05-OPERATORS映射详解.md`

**聚焦**：`constants.py` 的 OPERATORS 映射表

**内容大纲**：
```markdown
## 1. OPERATORS 映射表定位
   - 字段类型到查询操作符的映射
   - 前端查询构建器依赖

## 2. 完整映射表代码
   - 行号1658-1732完整代码
   - 各字段类型支持的操作符

## 3. 各操作符含义
   - EQ_WILDCARD：精确匹配（通配符）
   - NE_WILDCARD：排除匹配
   - EXISTS：字段存在
   - CONTAINS：包含
   - LT/LTE/GT/GTE：数值比较
   - IS_TRUE/IS_FALSE：布尔值

## 4. OperatorEnum 枚举定义
   - 行号1605-1655完整代码
   - 每个操作符的id/name/is_positive

## 5. 前端如何使用
   - 字段类型判断
   - 操作符列表生成

## 6. 后端如何使用
   - DSL构建时的操作符转换
```

---

### 6. `06-聚合处理器.md`

**聚焦**：`aggs_handlers.py`

**内容大纲**：
```markdown
## 1. AggsHandlers 定位
   - ES聚合查询封装

## 2. terms() Terms聚合
   - 完整代码片段（行号74-92）
   - 参数解析
   - DSL构建

## 3. date_histogram() 时间柱状图
   - 完整代码片段
   - interval参数
   - time_zone处理

## 4. _build_terms_aggs() DSL构建
   - 完整代码片段
   - aggregation结构

## 5. _build_terms_bucket() 桶构建
   - 单桶结构
   - 子聚合支持

## 6. 聚合结果处理
   - buckets解析
   - 前端图表数据转换
```

---

### 7. `07-特性开关架构.md`

**聚焦**：`FeatureToggleObject` 在 log_search 中的应用

**内容大纲**：
```markdown
## 1. 特性开关设计意图
   - 灰度发布
   - 功能开关

## 2. DIRECT_ESQUERY_SEARCH
   - 直接调用EsQuery
   - 绕过API网关
   - 代码使用位置

## 3. UNIFY_QUERY_SEARCH
   - 调用统一查询服务
   - 代码使用位置

## 4. LOG_DESENSITIZE
   - 脱敏功能开关
   - 代码使用位置

## 5. FeatureToggleObject.switch()
   - 完整代码片段
   - 业务白名单/黑名单

## 6. 如何新增特性开关
   - 配置指南
   - 代码集成
```

---

## 四、log_databus/ 模块（6个文档）

### 1. `01-CollectorHandler采集管理.md`

**聚焦**：`handlers/collector/base.py`

**内容大纲**：
```markdown
## 1. CollectorHandler 定位
   - 采集项管理的核心处理器

## 2. custom_create() 自定义创建
   - 完整代码片段
   - 参数处理流程
   - 调用BkDataDatabusApi

## 3. start() 启动采集
   - 完整代码片段
   - 节点管理订阅
   - GSE采集器下发

## 4. stop() 停止采集
   - 完整代码片段
   - 取消订阅
   - 清理配置

## 5. retrieve() 获取详情
   - RETRIEVE_CHAIN责任链调用
   - 完整代码片段

## 6. HostCollectorHandler vs K8sCollectorHandler
   - 物理机采集实现
   - 容器采集实现
```

---

### 2. `02-清洗策略模式.md`

**聚焦**：`handlers/etl_storage/`

**内容大纲**：
```markdown
## 1. 四种清洗策略
   - BK_LOG_TEXT：直接入库
   - BK_LOG_JSON：JSON解析
   - BK_LOG_DELIMITER：分隔符解析
   - BK_LOG_REGEXP：正则解析

## 2. EtlStorage 工厂类
   - 完整代码片段（base.py）
   - get_instance()动态导入
   - mapping字典设计

## 3. BkLogTextEtlStorage 实现
   - 文本直接入库逻辑
   - 完整代码片段

## 4. BkLogJsonEtlStorage 实现
   - JSON字段解析
   - etl_params配置
   - 完整代码片段

## 5. BkLogDelimiterEtlStorage 实现
   - 分隔符配置
   - 字段映射

## 6. BkLogRegexpEtlStorage 实现
   - 正则表达式配置
   - 字段提取

## 7. update_or_create_result_table()
   - 结果表创建逻辑
   - TransferApi调用
```

---

### 3. `03-责任链检索机制.md`

**聚焦**：`RETRIEVE_CHAIN`

**内容大纲**：
```markdown
## 1. 责任链设计意图
   - 采集配置信息补全
   - 每个节点职责单一

## 2. RETRIEVE_CHAIN 定义
   - 完整代码片段
   - 链节点列表：
     - set_itsm_info
     - set_split_rule
     - set_target
     - set_default_field
     - complement_metadata_info
     - complement_nodeman_info
     - fields_is_empty
     - deal_time
     - add_container_configs
     - encode_yaml_config

## 3. 各节点实现解析
   - 每个节点的完整代码
   - 输入输出数据流

## 4. retrieve() 调用逻辑
   - 链式调用代码
   - context数据传递

## 5. 如何扩展责任链
   - 新增节点指南
```

---

### 4. `04-Kafka消费者实现.md`

**聚焦**：`handlers/kafka.py`

**内容大纲**：
```markdown
## 1. KafkaConsumerHandle 定位
   - Kafka数据预览
   - 消息消费封装

## 2. __init__() 初始化
   - 完整代码片段
   - 参数解析：
     - server/port/topic
     - username/password
     - is_ssl_verify/sasl_mechanism

## 3. 安全协议选择逻辑
   - PLAINTEXT/SASL_PLAINTEXT/SSL/SASL_SSL
   - 代码解析

## 4. get_latest_log() 获取最新消息
   - 完整代码片段
   - 分区偏移量定位
   - 批量获取10条

## 5. KafkaConsumer 配置
   - auto_offset_reset
   - enable_auto_commit
   - consumer_timeout_ms

## 6. SSL/SASL 配置
   - ssl_cafile/certfile/keyfile
   - sasl_plain_username/password
```

---

### 5. `05-ES存储管理.md`

**聚焦**：`handlers/storage.py`

**内容大纲**：
```markdown
## 1. StorageHandler 定位
   - ES集群配置管理

## 2. create() 集群创建
   - 完整代码片段
   - 参数处理
   - 连通性检测

## 3. update() 集群更新
   - 配置修改
   - 热更新逻辑

## 4. connectivity_detect() 连通性检测
   - 完整代码片段
   - es_socket_ping调用
   - 结果判断

## 5. list_node_attrs() 获取节点属性
   - ES节点信息查询
   - 冷热节点识别

## 6. get_hot_warm_node_info() 冷热数据配置
   - hot节点标识
   - warm节点标识
   - 数据分层策略

## 7. sync_storage_capacity() 容量同步
   - 定时任务调用
   - 存储使用统计
```

---

### 6. `06-异步任务设计.md`

**聚焦**：`tasks/collector.py`

**内容大纲**：
```markdown
## 1. Celery任务架构
   - 定时任务 vs 高优先级任务

## 2. collector_status() 定时巡检
   - @periodic_task装饰器
   - run_every=crontab配置
   - 完整代码片段
   - 24小时未入库采集项检测

## 3. sync_storage_capacity() 容量同步
   - 每小时执行
   - ES集群容量统计

## 4. review_bkdata_data_id() BKBase同步
   - 每日执行
   - 未同步data_id重试

## 5. create_container_release() 高优先级任务
   - @high_priority_task装饰器
   - 容器采集配置下发
   - 完整代码片段

## 6. update_collector_storage_config() 存储配置更新
   - 即时执行
   - 采集项存储修改

## 7. @share_lock 分布式锁
   - 防止定时任务重复执行
   - TTL配置
```

---

## 五、log_trace/ 模块（4个文档）

### 1. `01-OpenTelemetry集成.md`

**聚焦**：`trace/__init__.py`

**内容大纲**：
```markdown
## 1. BluekingInstrumentor 总控
   - 统一管理所有组件埋点

## 2. instrument() 初始化
   - 完整代码片段
   - 各Instrumentor注册

## 3. DjangoInstrumentor 埋点
   - django_request_hook()
   - django_response_hook()
   - 请求参数记录

## 4. BkElasticsearchInstrumentor 埋点
   - _wrap_perform_request()
   - ES查询语句记录

## 5. RequestsInstrumentor 埋点
   - requests_callback()
   - 蓝鲸格式返回码处理

## 6. CeleryInstrumentor 埋点
   - 任务执行追踪

## 7. OTLPSpanExporter 配置
   - OTLP后端地址
   - 导出策略
```

---

### 2. `02-协议适配器模式.md`

**聚焦**：`handlers/proto/`

**内容大纲**：
```markdown
## 1. Proto 抽象基类
   - 完整代码片段（proto.py）
   - 定义统一接口
   - MUST_MATCH_FIELDS判断

## 2. judge_trace_type() 协议识别
   - 自动判断ES索引中Trace类型
   - 完整代码片段

## 3. get_proto() 获取处理器
   - 根据类型返回实例

## 4. LogTrace 实现
   - 完整代码片段（log.py）
   - traceID字段
   - build_tree()调用链构建

## 5. OtlpTrace 实现
   - 完整代码片段（otlp.py）
   - trace_id字段
   - _transform_to_jaeger()

## 6. 字段映射差异
   - Log vs OTLP字段对比表
```

---

### 3. `03-调用链树构建.md`

**聚焦**：`build_tree()` 方法

**内容大纲**：
```markdown
## 1. build_tree() 设计意图
   - 构建Span父子关系
   - 支持双向查找

## 2. build_tree() 完整实现
   - 完整代码片段（log.py）
   - 递归构建逻辑

## 3. Span数据结构
   - spanID/parentSpanID
   - startTime/duration
   - operationName

## 4. 父子关系判断
   - parentSpanID匹配
   - 根节点识别

## 5. _transform_to_jaeger() 转换
   - Jaeger格式输出
   - 前端统一展示

## 6. 多线程查询
   - multi_search_trace()
   - 批量Trace查询
```

---

### 4. `04-懒加载Span处理器.md`

**聚焦**：`LazyBatchSpanProcessor`

**内容大纲**：
```markdown
## 1. 懒加载设计意图
   - 避免空请求时资源浪费
   - 优化线程启动

## 2. LazyBatchSpanProcessor 实现
   - 继承BatchSpanProcessor
   - 完整代码片段

## 3. on_end() 懒加载触发
   - 首次请求时启动工作线程
   - 代码解析

## 4. 与BatchSpanProcessor对比
   - 原生实现的问题
   - 懒加载的优势

## 5. worker线程管理
   - daemon=True配置
   - 批量导出策略
```

---

## 六、ai_assistant/ 模块（4个文档）

### 1. `01-日志智能解读.md`

**聚焦**：`ChatHandler.interpret_log()`

**内容大纲**：
```markdown
## 1. interpret_log() 定位
   - AI日志解读的核心逻辑

## 2. 完整实现代码
   - handlers/chat.py完整片段
   - FeatureToggle开关判断
   - Prompt配置获取

## 3. 消息列表构造
   - System消息构建
   - 用户消息注入日志
   - 上下文截取

## 4. call_chat_completion() LLM调用
   - 流式vs同步模式
   - model参数
   - 完整代码片段

## 5. SSE流式响应
   - StreamingHttpResponse
   - headers配置

## 6. Prompt模板解析
   - constants.py模板
   - 占位符注入
```

---

### 2. `02-流式响应实现.md`

**聚焦**：SSE流式响应机制

**内容大纲**：
```markdown
## 1. SSE流式响应设计
   - 实时返回AI生成内容

## 2. StreamingHttpResponse 构建
   - content_type配置
   - headers配置（Cache-Control/X-Accel-Buffering）
   - 完整代码片段

## 3. ChatCompletionViewSet 流式会话
   - views.py完整实现
   - aidev_interface调用

## 4. 流式数据解析
   - chunk处理
   - delta内容提取

## 5. 前端对接
   - EventSource API
   - 消息处理

## 6. 错误处理
   - 流式错误传递
```

---

### 3. `03-本地命令处理器.md`

**聚焦**：`local_command_handlers.py`

**内容大纲**：
```markdown
## 1. 本地命令处理器设计
   - 装饰器注册模式

## 2. LogAnalysisCommandHandler
   - @local_command_handler("log_analysis")
   - process_content()完整实现
   - 日志上下文获取
   - 重复字段清理

## 3. QuerystringGenerateCommandHandler
   - @local_command_handler("querystring_generate")
   - 查询语句生成
   - 字段信息获取

## 4. CommandHandler 基类
   - 抽象接口定义

## 5. 如何扩展命令
   - 编写新处理器指南
   - 装饰器使用

## 6. 命令注册机制
   - handlers字典
   - 动态查找
```

---

### 4. `04-上下文智能清理.md`

**聚焦**：日志上下文清理逻辑

**内容大纲**：
```markdown
## 1. 上下文清理设计意图
   - 精简上下文信息
   - 控制内容长度

## 2. 排除系统内置字段
   - __data_label/gseIndex/time等
   - 完整字段列表

## 3. 重复KV清理
   - 与原始日志对比
   - 去重逻辑代码

## 4. 内容长度控制
   - 128K上下文限制
   - 动态截取策略

## 5. process_content() 完整实现
   - 代码片段解析

## 6. Jinja2模板渲染
   - 最终上下文构建
```

---

## 七、iam/ 模块（4个文档）

### 1. `01-Permission核心类.md`

**聚焦**：`handlers/permission.py`

**内容大纲**：
```markdown
## 1. Permission 类定位
   - 权限中心鉴权封装主类

## 2. is_allowed() 单次权限校验
   - 完整代码片段
   - Request对象构建
   - CompatibleIAM调用

## 3. batch_is_allowed() 批量权限校验
   - 完整代码片段
   - 批量请求构建
   - Demo业务豁免注入

## 4. get_apply_url() 权限申请跳转
   - 完整代码片段
   - 申请数据构建
   - 跳转URL生成

## 5. is_demo_biz_resource() Demo判断
   - Demo业务ID判断
   - 豁免逻辑

## 6. is_allowed_by_biz() 业务权限判断
   - 业务层权限快捷方法
```

---

### 2. `02-V1V2兼容机制.md`

**聚焦**：`handlers/compatible.py`

**内容大纲**：
```markdown
## 1. V1V2兼容背景
   - 权限系统版本升级
   - 平滑迁移需求

## 2. CompatibleIAM 类
   - 继承iam.IAM
   - 完整代码片段

## 3. _do_policy_query() 策略查询
   - V1/V2策略合并
   - OR运算逻辑
   - 完整代码片段

## 4. _patch_policy_expression() 表达式转换
   - biz.id → space.id
   - 资源路径适配

## 5. GlobalConfig 兼容开关
   - 配置读取
   - 动态启用

## 6. 迁移命令 iam_upgrade_action_v2
   - 策略迁移逻辑
   - 多线程批量授权
```

---

### 3. `03-DRF权限插件.md`

**聚焦**：`handlers/drf.py`

**内容大纲**：
```markdown
## 1. DRF权限插件体系
   - 与ViewSet配合使用

## 2. IAMPermission 基类
   - has_permission()
   - has_object_permission()
   - 完整代码片段

## 3. BusinessActionPermission
   - 从请求提取bk_biz_id
   - space_uid处理
   - 完整代码片段

## 4. InstanceActionPermission
   - 从URL kwargs提取实例ID
   - 完整代码片段

## 5. BatchIAMPermission
   - 批量实例权限校验
   - 完整代码片段

## 6. insert_permission_field() 装饰器
   - 响应数据批量插入权限字段
   - 前端按钮控制使用
   - 完整代码片段
```

---

### 4. `04-资源路径注入.md`

**聚焦**：`_bk_iam_path_` 计算

**内容大纲**：
```markdown
## 1. 资源路径设计意图
   - 子资源继承业务层权限
   - 层级权限判断

## 2. ResourceMeta.create_simple_instance()
   - 完整代码片段（resources.py）
   - _bk_iam_path_计算逻辑

## 3. 路径格式
   - /{Business.id},{bk_biz_id}/
   - 多层级路径拼接

## 4. 各资源的路径注入
   - CollectionResourceProvider
   - IndicesResourceProvider
   - EsSourceResourceProvider

## 5. ResourceApiDispatcher 回调处理
   - IAM资源查询回调
   - path过滤支持

## 6. 资源拓扑结构
   - 监控平台与日志平台关系
```

---

## 八、log_commons/ 模块（3个文档）

### 1. `01-IPv6双栈适配.md`

**聚焦**：`adapt_ipv6.py`

**内容大纲**：
```markdown
## 1. IPv6适配背景
   - DHCP环境主机标识问题

## 2. get_ip_field() IP版本判断
   - ipaddress.ip_address自动识别
   - 完整代码片段
   - v4/v6字段映射

## 3. fill_bk_host_id() 主机ID填充
   - DHCP环境使用bk_host_id
   - 完整代码片段
   - CCApi调用

## 4. fill_ip_and_cloud_id() IP填充
   - 非DHCP环境使用ip + bk_cloud_id
   - 完整代码片段

## 5. ENABLE_DHCP 配置
   - settings配置
   - 环境切换逻辑

## 6. 使用场景
   - log_extract调用
   - log_databus调用
```

---

### 2. `02-Token工厂模式.md`

**聚焦**：`token.py`

**内容大纲**：
```markdown
## 1. Token工厂设计
   - 支持多种Token类型

## 2. BaseTokenHandler 抽象基类
   - 定义标准流程
   - 完整代码片段
   - generate_or_get_token()

## 3. CodeccTokenHandler 实现
   - CODECC类型Token
   - 完整代码片段

## 4. TokenHandlerFactory 工厂类
   - _HANDLERS映射字典
   - get_handler()动态获取
   - 完整代码片段

## 5. 如何扩展新Token类型
   - 新增Handler类
   - 注册到工厂

## 6. Token复用机制
   - 避免重复创建
   - 有效期管理
```

---

### 3. `03-ITSM审批集成.md`

**聚焦**：`ExternalPermission` 模型

**内容大纲**：
```markdown
## 1. ITSM审批设计
   - 外部权限申请流程
   - 审批追溯

## 2. ExternalPermission.create_approval_ticket()
   - 完整代码片段（models.py）
   - ticket_data构建
   - BkItsmApi.create_ticket()

## 3. callback_url 回调处理
   - 审批结果回调
   - 状态更新逻辑

## 4. ExternalPermissionApplyRecord 模型
   - 申请记录存储
   - 与权限实体分离

## 5. 权限状态校验
   - 时间有效性
   - 授权人权限校验
   - get_status()实现

## 6. ITSM配置
   - ITSM_EXTERNAL_PERMISSION_SERVICE_ID
   - 流程配置
```

---

## 九、infrastructure/ 模块（4个文档）

### 1. `01-Celery任务设计.md`

**聚焦**：Celery配置与任务实现

**内容大纲**：
```markdown
## 1. Celery配置要点
   - config/default.py完整配置
   - CELERYD_CONCURRENCY
   - CELERY_TASK_SERIALIZER

## 2. @periodic_task 定时任务
   - run_every=crontab配置
   - 使用示例代码

## 3. @high_priority_task 高优先级
   - 即时响应任务
   - 队列配置

## 4. @share_lock 分布式锁
   - TTL配置
   - 防重复执行
   - 完整装饰器代码

## 5. django_celery_beat 数据库调度
   - 动态任务配置
   - 管理界面

## 6. 任务模块分布
   - 各模块tasks.py列表
```

---

### 2. `02-Redis缓存机制.md`

**聚焦**：`apps/utils/cache.py`

**内容大纲**：
```markdown
## 1. Redis配置
   - 单机模式配置
   - Sentinel哨兵模式配置
   - 完整配置代码

## 2. using_cache() 缓存装饰器
   - 完整代码片段
   - duration参数
   - key构建逻辑

## 3. 预定义缓存时长
   - cache_half_minute
   - cache_one_minute
   - cache_five_minute
   - cache_one_hour
   - cache_one_day

## 4. 数据压缩支持
   - zlib.compress
   - 压缩触发条件

## 5. MD5哈希key
   - 长key处理
   - 哈希逻辑

## 6. using_caches() 批量缓存
   - 批量获取
   - 代码实现
```

---

### 3. `03-分布式锁实现.md`

**聚焦**：`apps/utils/lock.py`

**内容大纲**：
```markdown
## 1. RedisLock 类
   - SET NX实现
   - 完整代码片段
   - acquire()/release()

## 2. service_lock() 上下文管理器
   - 完整代码片段
   - with语句使用
   - 自动释放

## 3. share_lock() 装饰器
   - 定时任务防重复
   - TTL参数
   - 标识参数
   - 完整代码片段

## 4. 锁超时处理
   - TTL过期自动释放
   - 防止死锁

## 5. 使用场景
   - 定时任务保护
   - 关键资源保护
```

---

### 4. `04-ES连接池管理.md`

**聚焦**：ES客户端连接管理

**内容大纲**：
```markdown
## 1. ES连接配置
   - hosts配置
   - 认证配置

## 2. 连接池机制
   - Elasticsearch内部连接池
   - 最大连接数

## 3. get_es_client() 实现细节
   - 版本选择
   - 连接参数处理
   - 完整代码片段

## 4. 连接健康检查
   - es_socket_ping()
   - 定期检查

## 5. 连接超时处理
   - timeout参数
   - 重试策略

## 6. 多集群连接
   - 集群配置存储
   - 动态连接
```

---

## 十、patterns/ 设计模式总结（4个文档）

### 1. `策略模式应用.md`

**聚焦**：项目中策略模式的三个应用

**内容大纲**：
```markdown
## 1. 策略模式原理
   - GoF定义
   - 适用场景

## 2. log_esquery/QueryClient 应用
   - 三种查询场景策略
   - 完整代码解析
   - 扩展方式

## 3. log_databus/EtlStorage 应用
   - 四种清洗策略
   - 完整代码解析
   - 扩展方式

## 4. log_trace/Proto 应用
   - 两种协议策略
   - 完整代码解析

## 5. 策略模式优势
   - 开闭原则
   - 易于扩展
```

---

### 2. `工厂模式应用.md`

**聚焦**：项目中工厂模式的应用

**内容大纲**：
```markdown
## 1. 工厂模式原理
   - GoF定义

## 2. api/DataAPI 应用
   - HTTP请求对象工厂

## 3. log_commons/TokenHandlerFactory 应用
   - Token处理器工厂
   - 完整代码解析

## 4. log_databus/EtlStorage.get_instance() 应用
   - 清洗策略工厂

## 5. 工厂模式优势
   - 解耦创建逻辑
```

---

### 3. `责任链模式应用.md`

**聚焦**：项目中责任链模式的应用

**内容大纲**：
```markdown
## 1. 责任链模式原理
   - GoF定义

## 2. log_databus/RETRIEVE_CHAIN 应用
   - 采集配置补全链
   - 完整代码解析
   - 各节点职责

## 3. 责任链优势
   - 单一职责
   - 易于扩展

## 4. 如何设计责任链
   - 节点设计原则
   - 数据传递方式
```

---

### 4. `Builder模式应用.md`

**聚焦**：项目中Builder模式的应用

**内容大纲**：
```markdown
## 1. Builder模式原理
   - GoF定义

## 2. log_esquery/DslBuilder 应用
   - DSL链式构建
   - 各Builder组件
   - 完整代码解析

## 3. Builder优势
   - 复杂对象构建
   - 分步构建

## 4. 链式调用设计
   - 参数传递
   - 最终组装
```

---

## 📊 文档统计

| 模块 | 文档数 | 聚焦内容 |
|-----|-------|---------|
| api | 6 | DataAPI、钩子、重试、并发、DRF集合、多租户 |
| log_esquery | 6 | EsQuery、策略、DSL、索引优化、版本、QoS |
| log_search | 7 | SearchHandler、预查询、多集群、滚动、OPERATORS、聚合、特性开关 |
| log_databus | 6 | 采集、清洗、责任链、Kafka、存储、异步任务 |
| log_trace | 4 | OTel、协议适配、调用链、懒加载 |
| ai_assistant | 4 | 日志解读、流式、命令处理器、上下文清理 |
| iam | 4 | Permission、V1V2、DRF插件、资源路径 |
| log_commons | 3 | IPv6、Token工厂、ITSM |
| infrastructure | 4 | Celery、Redis、分布式锁、ES连接 |
| patterns | 4 | 策略、工厂、责任链、Builder |
| **总计** | **44** | - |

---

## 📝 文档模板

每个文档遵循统一模板：

```markdown
# [标题]

> 聚焦：[核心类/函数]
> 文件路径：apps/[模块]/[文件].py

## 1. [主题]定位
   - 在模块中的作用
   - 与其他组件的关系图

## 2. 核心实现
   - 完整代码片段（含行号）
   - 关键参数解析

## 3. 执行流程
   - 流程图（Mermaid）
   - 步骤解析

## 4. 设计要点
   - 设计意图
   - 技术亮点

## 5. 如何扩展
   - 扩展指南
   - 最佳实践

## 6. 相关文档
   - 链接到其他Wiki文档
```

---

## ✅ 确认事项

请确认以下内容：

1. **文档数量**：44个文档，是否合适？
2. **内容深度**：每个文档聚焦核心类/函数，包含完整代码解析
3. **模块覆盖**：是否遗漏关键模块？
4. **文档结构**：是否需要调整？

确认后我将启动多个Agent并行生成这些文档。