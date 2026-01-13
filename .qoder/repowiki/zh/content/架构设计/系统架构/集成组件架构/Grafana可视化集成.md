# Grafana可视化集成

<cite>
**本文档引用的文件**
- [data_source.py](file://bklog/apps/grafana/data_source.py)
- [provisioning.py](file://bklog/apps/grafana/provisioning.py)
- [permissions.py](file://bklog/apps/grafana/permissions.py)
- [views.py](file://bklog/bk_dataview/grafana/views.py)
- [client.py](file://bklog/bk_dataview/grafana/client.py)
- [provisioning.py](file://bklog/bk_dataview/grafana/provisioning.py)
- [authentication.py](file://bklog/apps/grafana/authentication.py)
- [model.py](file://bklog/apps/grafana/model.py)
- [urls.py](file://bklog/apps/grafana/urls.py)
</cite>

## 目录
1. [引言](#引言)
2. [数据源自动配置机制](#数据源自动配置机制)
3. [仪表盘预置方案](#仪表盘预置方案)
4. [权限同步机制](#权限同步机制)
5. [高可用部署考虑](#高可用部署考虑)
6. [性能监控指标](#性能监控指标)
7. [故障恢复策略](#故障恢复策略)
8. [实际部署案例](#实际部署案例)

## 引言
BK-LOG与Grafana的集成实现了日志数据的可视化展示，通过自动化配置和权限同步机制，为用户提供了一站式的日志分析解决方案。本集成文档详细阐述了BK-LOG如何实现与Grafana的无缝集成，包括数据源自动配置、仪表盘预置、权限同步等核心功能。

## 数据源自动配置机制
BK-LOG通过自定义ES数据源配置机制，实现了Elasticsearch数据源的动态创建和认证信息注入。系统通过`CustomIndexSetESDataSource`类将日志索引集转换为Grafana兼容的数据源格式。

```mermaid
classDiagram
class CustomIndexSetESDataSource {
+str space_uid
+int index_set_id
+str index_set_name
+str time_field
+str token
+get_token(space_uid) str
+list(space_uid) List[CustomIndexSetESDataSource]
+generate_datasource_name(scenario_id, index_set_name) str
+to_datasource() Datasource
+list_datasource(bk_biz_id) List[Datasource]
}
class Datasource {
+str name
+str type
+str url
+str access
+bool isDefault
+int orgId
+Dict jsonData
+Dict secureJsonData
}
CustomIndexSetESDataSource --> Datasource : "转换为"
```

**图示来源**
- [data_source.py](file://bklog/apps/grafana/data_source.py#L46-L127)

**本节来源**
- [data_source.py](file://bklog/apps/grafana/data_source.py#L46-L152)

## 仪表盘预置方案
BK-LOG采用基于Provisioning的仪表盘预置方案，通过模板管理和批量部署流程实现标准化日志分析仪表盘的自动化部署。系统通过`SimpleProvisioning`类从配置文件目录中读取仪表盘定义并批量注入。

```mermaid
flowchart TD
Start([开始]) --> ReadConfig["读取配置文件目录"]
ReadConfig --> CheckPath{"PROVISIONING_PATH存在?"}
CheckPath --> |否| ReturnEmpty["返回空列表"]
CheckPath --> |是| FindFiles["查找*.yaml/*.yml文件"]
FindFiles --> ParseYAML["解析YAML配置"]
ParseYAML --> ExpandVars["展开环境变量"]
ExpandVars --> ProcessDashboards["处理仪表盘配置"]
ProcessDashboards --> FindJSON["查找*.json仪表盘文件"]
FindJSON --> ReadJSON["读取JSON文件"]
ReadJSON --> ParseJSON["解析JSON内容"]
ParseJSON --> CreateDashboard["创建Dashboard对象"]
CreateDashboard --> Collect["收集所有仪表盘"]
Collect --> End([结束])
```

**图示来源**
- [provisioning.py](file://bklog/bk_dataview/grafana/provisioning.py#L85-L124)

**本节来源**
- [provisioning.py](file://bklog/bk_dataview/grafana/provisioning.py#L85-L124)

## 权限同步机制
BK-LOG通过权限同步机制确保Grafana视图访问与BK-LOG权限体系保持一致。系统通过`BizPermission`类实现业务权限控制，将BK-LOG的权限映射到Grafana的角色体系中。

```mermaid
sequenceDiagram
participant User as "用户"
participant BKLOG as "BK-LOG"
participant Grafana as "Grafana"
User->>BKLOG : 访问请求
BKLOG->>BKLOG : 验证用户权限
alt 超级用户
BKLOG-->>Grafana : 返回Admin角色
else 普通用户
BKLOG->>BKLOG : 检查MANAGE_DASHBOARD权限
alt 有管理权限
BKLOG-->>Grafana : 返回Editor角色
else 无管理权限
BKLOG-->>Grafana : 返回Editor角色
end
end
Grafana->>User : 基于角色的访问控制
```

**图示来源**
- [permissions.py](file://bklog/apps/grafana/permissions.py#L28-L47)

**本节来源**
- [permissions.py](file://bklog/apps/grafana/permissions.py#L28-L47)

## 高可用部署考虑
BK-LOG的Grafana集成在高可用部署方面进行了全面考虑，包括数据库独立部署、缓存机制和负载均衡配置。系统通过独立的MySQL数据库存储Grafana元数据，确保数据持久性和可恢复性。

```mermaid
graph TB
subgraph "前端层"
LB[负载均衡器]
CDN[CDN网络]
end
subgraph "应用层"
Grafana1[Grafana实例1]
Grafana2[Grafana实例2]
Grafana3[Grafana实例3]
end
subgraph "数据层"
Redis[(Redis缓存)]
MySQL[(MySQL数据库)]
end
LB --> Grafana1
LB --> Grafana2
LB --> Grafana3
Grafana1 --> Redis
Grafana2 --> Redis
Grafana3 --> Redis
Grafana1 --> MySQL
Grafana2 --> MySQL
Grafana3 --> MySQL
```

**图示来源**
- [0001_grafana_20201113-0000_mysql.sql](file://bklog/support-files/sql/0001_grafana_20201113-0000_mysql.sql#L1)
- [provisioning.py](file://bklog/bk_dataview/grafana/provisioning.py)

**本节来源**
- [0001_grafana_20201113-0000_mysql.sql](file://bklog/support-files/sql/0001_grafana_20201113-0000_mysql.sql#L1)

## 性能监控指标
BK-LOG集成的Grafana系统监控关键性能指标，包括JVM内存使用、文件系统状态和查询性能。系统通过ES查询接口收集Elasticsearch集群的运行时指标。

```mermaid
erDiagram
PERFORMANCE_METRICS {
string metric_name PK
string metric_type
string es_field_name
string description
timestamp created_at
timestamp updated_at
}
JVM_MEMORY {
string jvm_mem_non_heap_used PK
string gauge
string jvm.mem.non_heap_used_in_bytes
string "非堆内存使用量"
}
JVM_MEMORY ||--o{ PERFORMANCE_METRICS : "属于"
FILE_SYSTEM {
string elasticsearch_fs_total_total_in_bytes PK
string gauge
string fs.total.total_in_bytes
string "文件系统总容量"
}
FILE_SYSTEM ||--o{ PERFORMANCE_METRICS : "属于"
THREADS {
string jvm_threads_count PK
string gauge
string jvm.threads.count
string "线程数量"
}
THREADS ||--o{ PERFORMANCE_METRICS : "属于"
```

**图示来源**
- [es.py](file://bklog/apps/log_measure/utils/es.py#L326-L337)

**本节来源**
- [es.py](file://bklog/apps/log_measure/utils/es.py#L326-L337)

## 故障恢复策略
BK-LOG的Grafana集成实现了完善的故障恢复策略，包括数据源自动重建、仪表盘重新注入和缓存失效处理。系统通过定期检查和同步机制确保配置的一致性。

```mermaid
stateDiagram-v2
[*] --> Normal
Normal --> Failure : "检测到故障"
Failure --> DataRecovery : "启动恢复流程"
DataRecovery --> CheckDatasources : "检查数据源状态"
CheckDatasources --> CreateMissing : "创建缺失的数据源"
CreateMissing --> UpdateExisting : "更新现有的数据源"
UpdateExisting --> DeleteOrphaned : "删除孤立的数据源"
DeleteOrphaned --> CheckDashboards : "检查仪表盘状态"
CheckDashboards --> InjectMissing : "注入缺失的仪表盘"
InjectMissing --> UpdateCache : "更新组织缓存"
UpdateCache --> Normal : "恢复完成"
note right of Failure
故障可能由以下原因引起：
- Grafana实例重启
- 配置数据库损坏
- 网络分区
end note
```

**图示来源**
- [provisioning.py](file://bklog/apps/grafana/provisioning.py#L55-L98)
- [views.py](file://bklog/bk_dataview/grafana/views.py#L117-L142)

**本节来源**
- [provisioning.py](file://bklog/apps/grafana/provisioning.py#L55-L98)
- [views.py](file://bklog/bk_dataview/grafana/views.py#L117-L142)

## 实际部署案例
在实际部署中，BK-LOG的Grafana集成通过自动化脚本和配置管理工具实现快速部署。系统通过特性开关控制功能启用，确保平滑的升级和回滚能力。

```mermaid
flowchart LR
A[部署准备] --> B[环境检查]
B --> C[数据库初始化]
C --> D[配置文件生成]
D --> E[启动Grafana服务]
E --> F[等待服务就绪]
F --> G[执行Provisioning]
G --> H[验证数据源]
H --> I[验证仪表盘]
I --> J[权限同步]
J --> K[健康检查]
K --> L[部署完成]
style A fill:#f9f,stroke:#333
style L fill:#bbf,stroke:#333
```

**图示来源**
- [provisioning.py](file://bklog/apps/grafana/provisioning.py)
- [views.py](file://bklog/bk_dataview/grafana/views.py)

**本节来源**
- [provisioning.py](file://bklog/apps/grafana/provisioning.py)
- [views.py](file://bklog/bk_dataview/grafana/views.py)