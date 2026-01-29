# AlertFlow Engine 设计文档

基于配置的数据流处理框架，封装告警处理全流程，支持通过配置灵活编排处理节点。

## 文档目录

| 文档 | 说明 |
|------|------|
| [01-overview.md](./01-overview.md) | **产品概述** - 核心功能、技术栈选择 |
| [02-architecture.md](./02-architecture.md) | **技术架构设计** - 系统架构、模块划分、数据流、核心数据结构、节点执行模式、多协议支持 |
| [03-implementation.md](./03-implementation.md) | **实现细节** - 目录结构、关键代码、技术实现计划、集成点 |
| [04-observability.md](./04-observability.md) | **可观测性设计** - ES索引设计、日志记录、故障排查接口 |
| [05-configuration.md](./05-configuration.md) | **配置管理设计** - 配置方式、命令行工具、REST API、数据结构 |
| [06-summary.md](./06-summary.md) | **架构设计总结** - 核心决策、技术栈总结、最佳实践 |
| [07-third-party-libs.md](./07-third-party-libs.md) | **第三方库使用** - jsonLogic、Redis限流、structlog、pydantic等 |
| [08-node-config-schemas.md](./08-node-config-schemas.md) | **节点配置数据结构** - 配置即数据、基础节点类型的完整配置Schema定义 |
| [09-extended-node-configs.md](./09-extended-node-configs.md) | **扩展节点配置** - 检测类、流控类、告警生命周期类、存储类节点配置 |

## 快速导航

### 核心概念
- [系统架构图](./02-architecture.md#系统架构)
- [数据流设计](./02-architecture.md#数据流设计)
- [处理器接口](./02-architecture.md#处理器接口)
- [输入输出 Schema 接口](./02-architecture.md#输入输出-schema-接口)
- [配置传递机制](./02-architecture.md#配置传递机制)

### 分布式执行
- [节点执行模式](./02-architecture.md#节点执行模式)
- [多协议支持架构](./02-architecture.md#多协议支持架构)
- [协议选择决策](./02-architecture.md#协议选择决策流程)

### 配置与管理
- [Pipeline 配置示例](./02-architecture.md#pipeline-配置示例)
- [配置管理命令](./05-configuration.md#配置管理命令)
- [REST API 接口](./05-configuration.md#rest-api-接口)

### 节点配置数据结构
- [配置即数据设计理念](./08-node-config-schemas.md#设计理念)
- [节点抽象接口](./08-node-config-schemas.md#节点抽象接口)
- [节点分类体系](./08-node-config-schemas.md#节点分类体系)
- [过滤节点配置](./08-node-config-schemas.md#过滤节点配置-filternodeconfig)
- [丰富化节点配置](./08-node-config-schemas.md#丰富化节点配置-enrichmentnodeconfig)
- [收敛节点配置](./08-node-config-schemas.md#收敛节点配置-convergenodeconfig)
- [通知节点配置](./08-node-config-schemas.md#通知节点配置-notificationnodeconfig)
- [完整Pipeline配置示例](./08-node-config-schemas.md#完整-pipeline-配置示例)

### 扩展节点配置
- [数据处理类节点](./09-extended-node-configs.md#数据处理类节点-data_processing)
- [检测类节点](./09-extended-node-configs.md#检测类节点-detection)
- [流控类节点](./09-extended-node-configs.md#流控类节点-flow_control)
- [告警生命周期类节点](./09-extended-node-configs.md#告警生命周期类节点-alert_lifecycle)
- [动作类节点](./09-extended-node-configs.md#动作类节点-action)
- [存储类节点](./09-extended-node-configs.md#存储类节点-storage)

### 可观测性
- [Elasticsearch 索引设计](./04-observability.md#elasticsearch-索引设计)
- [故障排查接口](./04-observability.md#故障排查接口)

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| 编程语言 | Python 3.10+ |
| Web 框架 | Django + DRF |
| 数据存储 | Redis / ElasticSearch / PostgreSQL |
| 消息队列 | Kafka |
| 分布式通信 | HTTP / gRPC / Kafka（多协议支持） |
| 配置格式 | JSON / YAML |

## 核心特性

- **配置即数据**：每个节点预定义好配置数据结构，不同项目只需提供配置即可复用节点
- **节点抽象接口**：每个节点暴露 `get_config_schema()`、`get_input_schema()`、`get_output_schema()` 接口
- **配置传递**：上一个节点的输出可传递给下一个节点，支持 `{{ $upstream.node_name.field }}` 语法
- **多协议支持**：HTTP、gRPC、Kafka 三种通信协议可根据场景灵活选择
- **可插拔架构**：协议适配器工厂模式，支持注册自定义协议
- **混合部署**：同一 Pipeline 中可混用多种协议
- **安全通信**：支持 TLS/mTLS、SASL/SSL 等安全机制
- **完整可观测性**：trace_id 链路追踪、ES 日志存储、故障回溯
- **强类型约束**：基于 Pydantic 的配置验证，错误在加载时即可发现

## 相关链接

- 原始完整文档：[alertFlowEngine.md](../../alertFlowEngine.md)
