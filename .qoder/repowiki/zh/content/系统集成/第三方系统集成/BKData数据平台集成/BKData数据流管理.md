# BKData数据流管理

<cite>
**本文档引用的文件**   
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L1-L142)
- [dataflow_handler.py](file://bklog/apps/log_clustering/handlers/dataflow/dataflow_handler.py#L122-L146)
- [data_cls.py](file://bklog/apps/log_clustering/handlers/dataflow/data_cls.py#L22-L477)
- [constants.py](file://bklog/apps/log_clustering/handlers/dataflow/constants.py#L53-L68)
- [pre_treat_flow.json](file://bklog/templates/flow/pre_treat_flow.json#L1-L128)
- [after_treat_flow.json](file://bklog/templates/flow/after_treat_flow.json#L1-L432)
</cite>

## 目录
1. [简介](#简介)
2. [核心数据流操作功能](#核心数据流操作功能)
3. [数据流监控能力](#数据流监控能力)
4. [数据流配置管理功能](#数据流配置管理功能)
5. [数据流备份能力](#数据流备份能力)
6. [数据流全生命周期管理示例](#数据流全生命周期管理示例)
7. [总结](#总结)

## 简介
BKData数据流管理提供了一套完整的数据流操作接口，用于创建、启动、停止、重启、监控和配置数据流。这些功能主要通过bkdata_dataflow.py文件中的BkDataDataFlowApi类实现，支持数据流的全生命周期管理。数据流在日志聚类、实时处理等场景中发挥着重要作用，通过定义数据处理流程，实现从数据源到目标存储的自动化处理。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L29-L142)

## 核心数据流操作功能

### create_flow接口创建数据流
`create_flow`接口用于创建新的数据流。该接口通过POST请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/create/"发送创建请求，需要提供数据流的节点配置、名称和项目ID等参数。创建数据流是数据处理流程的第一步，为后续的数据处理提供基础架构。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L42-L51)

### start_flow接口启动数据流
`start_flow`接口用于启动已创建的数据流。该接口通过POST请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/start/"发送启动请求，需要指定数据流ID。启动数据流后，数据处理流程开始执行，从数据源读取数据并按照预定义的节点配置进行处理。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L52-L60)

### stop_flow接口停止数据流
`stop_flow`接口用于停止正在运行的数据流。该接口通过POST请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/stop/"发送停止请求，需要指定数据流ID。停止数据流会中断数据处理流程，但不会删除数据流配置，可以随时重新启动。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L61-L69)

### restart_flow接口重启数据流
`restart_flow`接口用于重启数据流。该接口通过POST请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/restart/"发送重启请求，需要指定数据流ID。重启数据流会先停止再启动数据流，适用于需要重新加载配置或恢复异常状态的场景。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L70-L78)
- [dataflow_handler.py](file://bklog/apps/log_clustering/handlers/dataflow/dataflow_handler.py#L132-L146)

## 数据流监控能力

### get_flow_graph接口获取数据流拓扑结构
`get_flow_graph`接口用于获取数据流的拓扑结构。该接口通过GET请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/graph/"发送请求，返回数据流的节点连接关系和配置信息。通过拓扑结构可以直观地了解数据流的处理流程和节点间的数据流向。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L79-L88)

### get_dataflow接口获取数据流信息
`get_dataflow`接口用于获取数据流的详细信息。该接口通过GET请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/"发送请求，返回数据流的状态、配置和运行信息。这些信息对于监控数据流的健康状态和性能表现至关重要。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L110-L119)

### get_latest_deploy_data接口获取最新部署信息
`get_latest_deploy_data`接口用于获取数据流的最新部署信息。该接口通过GET请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/latest_deploy_data/"发送请求，返回数据流最近一次部署的配置和状态。这些信息有助于了解数据流的变更历史和当前部署状态。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L100-L109)

## 数据流配置管理功能

### add_flow_nodes接口添加节点
`add_flow_nodes`接口用于向现有数据流中添加新的处理节点。该接口通过POST请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/nodes/"发送请求，需要指定数据流ID和新节点的配置。添加节点可以扩展数据流的处理能力，例如增加数据过滤、转换或聚合等处理步骤。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L89-L98)

### patch_flow_nodes接口更新节点
`patch_flow_nodes`接口用于更新数据流中现有节点的配置。该接口通过PATCH请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/nodes/{node_id}/"发送请求，需要指定数据流ID、节点ID和更新的配置。更新节点配置可以调整数据处理逻辑，而无需重新创建整个数据流。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L120-L129)

## 数据流备份能力

### export_flow接口导出数据流
`export_flow`接口用于导出数据流的配置。该接口通过GET请求向DATAFLOW_APIGATEWAY_ROOT + "flow/flows/{flow_id}/export/"发送请求，返回数据流的完整配置信息。导出的数据流配置可以用于备份、迁移或在其他环境中复用，确保数据处理流程的一致性。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L32-L41)
- [dataflow_handler.py](file://bklog/apps/log_clustering/handlers/dataflow/dataflow_handler.py#L122-L130)

## 数据流全生命周期管理示例

以下是一个完整的数据流全生命周期管理示例，展示了从创建、配置、启动、监控到销毁的完整流程：

1. **创建数据流**：使用`create_flow`接口创建一个新的数据流，定义初始的节点配置。
2. **配置数据流**：使用`add_flow_nodes`接口添加必要的处理节点，使用`patch_flow_nodes`接口调整节点配置。
3. **启动数据流**：使用`start_flow`接口启动数据流，开始数据处理。
4. **监控数据流**：使用`get_flow_graph`、`get_dataflow`和`get_latest_deploy_data`接口监控数据流的状态和性能。
5. **维护数据流**：根据监控结果，使用`stop_flow`、`start_flow`或`restart_flow`接口进行必要的维护操作。
6. **备份数据流**：使用`export_flow`接口导出数据流配置，用于备份或迁移。
7. **销毁数据流**：在数据流不再需要时，可以通过平台提供的删除功能将其销毁。

这个示例展示了BKData数据流管理功能的完整应用，通过这些接口的组合使用，可以实现灵活、可靠的数据处理流程管理。

**Section sources**
- [bkdata_dataflow.py](file://bklog/apps/api/modules/bkdata_dataflow.py#L29-L142)
- [dataflow_handler.py](file://bklog/apps/log_clustering/handlers/dataflow/dataflow_handler.py#L122-L146)

## 总结
BKData数据流管理提供了一套全面的接口，支持数据流的创建、启动、停止、重启、监控、配置和备份等操作。这些功能通过bkdata_dataflow.py文件中的BkDataDataFlowApi类实现，为数据处理流程的全生命周期管理提供了强大的支持。通过合理使用这些接口，可以构建高效、可靠的数据处理系统，满足各种业务需求。