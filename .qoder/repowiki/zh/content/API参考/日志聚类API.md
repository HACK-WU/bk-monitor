# 日志聚类API

<cite>
**本文档中引用的文件**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)
- [clustering_config_views.py](file://bklog/apps/log_clustering/views/clustering_config_views.py)
- [clustering_monitor_views.py](file://bklog/apps/log_clustering/views/clustering_monitor_views.py)
- [models.py](file://bklog/apps/log_clustering/models.py)
- [serializers.py](file://bklog/apps/log_clustering/serializers.py)
- [urls.py](file://bklog/apps/log_clustering/urls.py)
- [constants.py](file://bklog/apps/log_clustering/constants.py)
- [log_clustering.py](file://bklog/apps/log_measure/handlers/metric_collectors/log_clustering.py)
- [clustering_mail.html](file://bklog/templates/clustering_subscription/clustering_mail.html)
- [clustering_wechat.md](file://bklog/templates/clustering_subscription/clustering_wechat.md)
</cite>

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构概述](#架构概述)
5. [详细组件分析](#详细组件分析)
6. [依赖分析](#依赖分析)
7. [性能考虑](#性能考虑)
8. [故障排除指南](#故障排除指南)
9. [结论](#结论)

## 简介
本文档详细描述了日志聚类分析API的功能，涵盖聚类配置管理、模式识别、特征提取、订阅通知等接口。文档说明了如何创建和管理聚类任务，包括时间窗口、相似度阈值、算法选择等参数设置。同时，文档化了聚类结果查询API，包括模式列表、样本日志、趋势分析等数据结构，并解释了聚类监控告警的配置方式和通知策略。此外，还提供了聚类效果评估相关的API说明，如准确率、召回率等指标查询，以及聚类模型训练、更新和版本管理的接口文档。

## 项目结构
日志聚类功能主要位于`bklog/apps/log_clustering/`目录下，包含处理程序、视图、模型、序列化器和URL配置。该模块与其他组件如监控、度量收集和通知系统集成，形成完整的日志聚类分析解决方案。

```mermaid
graph TD
subgraph "日志聚类模块"
ConfigHandler["聚类配置处理器"]
MonitorHandler["聚类监控处理器"]
Views["视图层"]
Models["数据模型"]
Serializers["序列化器"]
URLs["URL路由"]
end
subgraph "外部依赖"
Metrics["度量收集"]
Templates["通知模板"]
Monitor["监控系统"]
end
ConfigHandler --> Models
MonitorHandler --> Models
Views --> ConfigHandler
Views --> MonitorHandler
Views --> Serializers
Serializers --> Models
MonitorHandler --> Metrics
MonitorHandler --> Templates
MonitorHandler --> Monitor
```

**Diagram sources**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)
- [models.py](file://bklog/apps/log_clustering/models.py)

**Section sources**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)

## 核心组件
日志聚类系统的核心组件包括聚类配置管理、聚类执行引擎、模式识别、特征提取、订阅通知和效果评估。这些组件协同工作，实现从原始日志到可操作洞察的转换过程。

**Section sources**
- [models.py](file://bklog/apps/log_clustering/models.py)
- [serializers.py](file://bklog/apps/log_clustering/serializers.py)

## 架构概述
日志聚类系统采用分层架构，包括数据接入层、处理层、存储层和应用层。系统通过配置驱动的方式，支持多种聚类算法和参数设置，能够灵活适应不同的日志分析需求。

```mermaid
graph TB
subgraph "应用层"
API["REST API接口"]
UI["用户界面"]
end
subgraph "处理层"
Config["聚类配置管理"]
Engine["聚类执行引擎"]
Monitor["监控告警"]
Evaluate["效果评估"]
end
subgraph "存储层"
DB[(数据库)]
Cache[(缓存)]
ES[(Elasticsearch)]
end
subgraph "数据接入层"
LogAgent["日志代理"]
DataBus["数据总线"]
end
UI --> API
API --> Config
API --> Engine
API --> Monitor
API --> Evaluate
Config --> DB
Engine --> ES
Engine --> Cache
Monitor --> DB
Evaluate --> DB
LogAgent --> DataBus
DataBus --> Engine
```

**Diagram sources**
- [urls.py](file://bklog/apps/log_clustering/urls.py)
- [views/clustering_config_views.py](file://bklog/apps/log_clustering/views/clustering_config_views.py)
- [handlers/clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)

## 详细组件分析

### 聚类配置管理分析
聚类配置管理组件负责创建、更新和删除聚类任务的配置。配置包括时间窗口、相似度阈值、算法选择等关键参数，这些参数直接影响聚类结果的质量和性能。

#### 类图
```mermaid
classDiagram
class ClusteringConfig {
+int index_set_id
+str log_pre_treat_rules
+float max_dist_list
+int predefined_varibles
+int delimeter
+str delimeter_regex
+int is_case_sensitive
+int clustering_fields
+str bk_biz_id
+str source_rt
+str clustered_rt
+str unclustered_rt
+str flow_config
+int task_id
+str task_status
+datetime created_at
+str created_by
+datetime updated_at
+str updated_by
+update_config(config_data)
+validate_config()
+get_algorithm_params()
}
class ClusteringSubscription {
+int config_id
+list receivers
+list notice_types
+str notice_group_id
+bool is_enabled
+create_subscription()
+update_subscription()
+send_notification()
}
class ClusteringRemark {
+int config_id
+str strategy_id
+bool strategy_enabled
+str source_app_code
+str remark_content
+datetime created_at
+str created_by
}
ClusteringConfig --> ClusteringSubscription : "has one"
ClusteringConfig --> ClusteringRemark : "has many"
```

**Diagram sources**
- [models.py](file://bklog/apps/log_clustering/models.py)
- [serializers.py](file://bklog/apps/log_clustering/serializers.py)

**Section sources**
- [models.py](file://bklog/apps/log_clustering/models.py)
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)

### 聚类监控告警分析
聚类监控告警组件负责监控聚类任务的执行状态，并在异常情况下发送通知。该组件与通知系统集成，支持多种通知渠道，如邮件、企业微信等。

#### 序列图
```mermaid
sequenceDiagram
participant API as "API请求"
participant Handler as "ClusteringMonitorHandler"
participant Model as "ClusteringConfig"
participant Task as "聚类任务"
participant Notice as "通知系统"
API->>Handler : 创建监控配置
Handler->>Model : 验证配置参数
Model-->>Handler : 配置验证结果
Handler->>Task : 启动聚类任务
Task-->>Handler : 任务状态更新
Handler->>Handler : 检查任务状态
alt 任务失败
Handler->>Notice : 发送告警通知
Notice-->>Handler : 通知发送结果
end
Handler-->>API : 返回监控配置结果
```

**Diagram sources**
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)
- [clustering_monitor_views.py](file://bklog/apps/log_clustering/views/clustering_monitor_views.py)

**Section sources**
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)
- [clustering_monitor_views.py](file://bklog/apps/log_clustering/views/clustering_monitor_views.py)

### 聚类效果评估分析
聚类效果评估组件提供API接口，用于查询聚类结果的准确率、召回率等指标。这些指标帮助用户评估聚类算法的性能，并指导参数调优。

#### 流程图
```mermaid
flowchart TD
Start([开始]) --> ValidateInput["验证输入参数"]
ValidateInput --> InputValid{"参数有效?"}
InputValid --> |否| ReturnError["返回错误响应"]
InputValid --> |是| QueryMetrics["查询度量数据"]
QueryMetrics --> MetricsFound{"找到指标?"}
MetricsFound --> |否| CalculateMetrics["计算评估指标"]
MetricsFound --> |是| UseCachedMetrics["使用缓存指标"]
CalculateMetrics --> StoreMetrics["存储计算结果"]
StoreMetrics --> ReturnResult["返回评估结果"]
UseCachedMetrics --> ReturnResult
ReturnResult --> End([结束])
ReturnError --> End
```

**Diagram sources**
- [log_clustering.py](file://bklog/apps/log_measure/handlers/metric_collectors/log_clustering.py)
- [constants.py](file://bklog/apps/log_clustering/constants.py)

**Section sources**
- [log_clustering.py](file://bklog/apps/log_measure/handlers/metric_collectors/log_clustering.py)

## 依赖分析
日志聚类系统依赖于多个内部和外部组件，包括Elasticsearch用于日志存储和检索，监控系统用于任务状态跟踪，通知系统用于告警发送，以及配置管理系统用于参数管理。

```mermaid
graph TD
Clustering["日志聚类"]
Elasticsearch["Elasticsearch"]
Monitor["监控系统"]
Notification["通知系统"]
Config["配置管理"]
Auth["认证系统"]
Cache["缓存系统"]
Clustering --> Elasticsearch
Clustering --> Monitor
Clustering --> Notification
Clustering --> Config
Clustering --> Auth
Clustering --> Cache
```

**Diagram sources**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)

**Section sources**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)

## 性能考虑
日志聚类系统的性能受多个因素影响，包括日志量、时间窗口大小、相似度阈值和算法复杂度。系统通过缓存、异步处理和分布式计算等技术优化性能，确保在大规模日志数据上的高效处理。

## 故障排除指南
当遇到聚类任务失败或性能问题时，应首先检查配置参数是否正确，然后查看任务日志以确定具体错误原因。常见的问题包括Elasticsearch连接失败、内存不足和算法参数设置不当。

**Section sources**
- [clustering_config.py](file://bklog/apps/log_clustering/handlers/clustering_config.py)
- [clustering_monitor.py](file://bklog/apps/log_clustering/handlers/clustering_monitor.py)

## 结论
日志聚类API提供了一套完整的日志分析解决方案，从配置管理到结果评估，涵盖了日志聚类分析的各个方面。通过灵活的配置选项和强大的监控告警功能，系统能够满足不同场景下的日志分析需求。