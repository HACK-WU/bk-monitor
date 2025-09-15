# APM Monitoring

<cite>
**Referenced Files in This Document**   
- [config.py](file://bkmonitor\apm\models\config.py) - *Original configuration model*
- [platform_config.py](file://bkmonitor\apm\core\platform_config.py) - *Platform-level configuration*
- [base.py](file://bkmonitor\apm\core\discover\base.py) - *Base discovery logic*
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py) - *Updated query handling with performance optimization*
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py) - *Updated trace query implementation*
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py) - *Precalculation processor*
- [storage.py](file://bkmonitor\apm\core\discover\precalculation\storage.py) - *Storage configuration and schema*
- [resources.py](file://bkmonitor\packages\apm_web\trace\resources.py) - *Web interface resources*
- [global_config.py](file://bkmonitor\bkmonitor\define\global_config.py) - *Global system configuration*
</cite>

## Update Summary
**Changes Made**   
- Updated the "Performance Analysis of Practical Tips" section to include the new multi-threaded query optimization
- Added details about the `ThreadPool.map_ignore_exception` method used for parallel field value queries
- Enhanced the "APM Data Storage Structure and Query Methods" section with updated query performance information
- Updated file references to reflect the recent performance optimization changes in query handling
- Maintained all existing architectural descriptions as the core data model and storage structure remain unchanged

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)

## Introduction
This document provides a comprehensive introduction to the Application Performance Monitoring (APM) functionality within the BlueKing monitoring platform. The document details APM's core capabilities, including automatic application topology discovery, performance metrics collection, distributed tracing, data storage, and querying. Through code implementation analysis, this document explains how APM automatically constructs call relationships between applications, collects key performance metrics such as response time, throughput, and error rate, and generates and displays complete call chains. Additionally, the document covers APM data storage structures, query methods, configuration examples, and typical usage scenarios, aiming to provide users with a comprehensive and in-depth APM functionality usage and diagnostic guide.

## Project Structure
The APM functionality is primarily located in the `bkmonitor/apm` directory, with a structure that clearly separates core logic, data models, management commands, and utility classes. The `core` directory contains core business logic such as topology discovery (`discover`) and query processing (`handlers/query`). The `models` directory defines data models related to APM, such as application configurations, data sources, and topology instances. The `utils` directory provides basic utility functions. The `packages/apm_web` directory contains the user-facing web interface and resource APIs responsible for presenting backend data to users.

``mermaid
graph TD
A[apm] --> B[core]
A --> C[models]
A --> D[utils]
A --> E[task]
A --> F[tests]
B --> G[discover]
B --> H[handlers]
B --> I[platform_config]
G --> J[precalculation]
H --> K[query]
C --> L[application.py]
C --> M[config.py]
C --> N[datasource.py]
C --> O[topo.py]
K --> P[base.py]
K --> Q[origin_trace_query.py]
K --> R[trace_query.py]
```

**Diagram sources**
- [apm module structure](file://bkmonitor\apm)

## Core Components
The core components of the APM system revolve around data collection, processing, storage, and querying. Core components include:
*   **Topology Discoverer (Discover)**: Responsible for analyzing raw trace data to automatically identify applications, services, and components and construct call topology relationships.
*   **Pre-calculation Processor (PrecalculateProcessor)**: Aggregates and pre-calculates raw trace data, generating metric data with trace summary information to improve query performance.
*   **Query Handler (Query Handler)**: Provides multiple query interfaces to efficiently retrieve both raw trace data and pre-calculated data.
*   **Data Models (Models)**: Defines data structures for core entities such as applications, configurations, and data sources.
*   **Platform Configuration (PlatformConfig)**: Manages global configurations for APM, such as built-in metric definitions and default attribute filtering rules.

**Section sources**
- [config.py](file://bkmonitor\apm\models\config.py#L0-L199)
- [platform_config.py](file://bkmonitor\apm\core\platform_config.py#L0-L200)
- [base.py](file://bkmonitor\apm\core\discover\base.py#L0-L200)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L0-L200)

## Architecture Overview
The APM system's overall architecture follows a data flow processing pattern. First, probes collect application trace data and report it. The system uses the **Topology Discoverer** to analyze this data and construct application topology. Simultaneously, the **Pre-calculation Processor** aggregates trace data, calculates summary information for traces (such as total duration, error count, number of services), and stores the results in Elasticsearch. When a user initiates a query, the **Query Handler** selects whether to query summary data from pre-calculated storage for high performance or detailed span information from raw data storage based on the request type. The `packages/apm_web` module acts as the frontend interface, displaying query results to users in the form of charts and lists.

``mermaid
graph LR
A[Application Probe] --> |Report Trace Data| B[Raw Data Storage]
B --> C[Topology Discoverer]
B --> D[Pre-calculation Processor]
C --> E[Application Topology]
D --> F[Pre-calculated Storage]
G[User Query] --> H[Query Handler]
H --> |Query Summary| F
H --> |Query Details| B
H --> I[Application Topology]
H --> J[Performance Metrics]
F --> K[packages/apm_web]
B --> K
E --> K
J --> K
K --> L[User Interface]
```

**Diagram sources**
- [apm module structure](file://bkmonitor\apm)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L0-L200)

## Detailed Component Analysis

### Application Topology Discovery Mechanism
Application topology discovery is a core APM function that automatically constructs call relationship diagrams between applications by analyzing span information in distributed trace data. This functionality is implemented by the `DiscoverBase` base class and a series of specific discoverers.

**Implementation Principles**:
1.  **Rule-driven**: The system defines a set of `ApmTopoDiscoverRule` rules that identify different service types (such as HTTP services, databases, message queues) based on OpenTelemetry semantic conventions (e.g., `http.method`, `db.system`).
2.  **Instance Key Extraction**: For each span, the system extracts an `instance_key` from `resource` and `attributes` based on its associated rule. This key is crucial for uniquely identifying a service instance; for example, a database instance's `instance_key` might be composed of attributes like `db.system` and `net.peer.name`.
3.  **Topology Construction**: The system traverses all spans, grouping them by `instance_key` to identify different service instances. By analyzing parent-child relationships between spans (`parent_span_id`), it constructs call chains between service instances, ultimately forming a complete application topology graph.

``mermaid
classDiagram
class ApmTopoDiscoverRule {
+TOPO_SERVICE : str
+TOPO_COMPONENT : str
+APM_TOPO_CATEGORY_HTTP : str
+APM_TOPO_CATEGORY_RPC : str
+APM_TOPO_CATEGORY_DB : str
+predicate_key : str
+instance_key : str
+topo_kind : str
}
class DiscoverBase {
<<abstract>>
+bk_biz_id : int
+app_name : str
+get_rules() : list[ApmTopoDiscoverRuleCls]
+get_topo_instance_key() : str
+exists_field() : bool
}
class ApmApplication {
+bk_biz_id : int
+app_name : str
+app_alias : str
}
ApmApplication --> DiscoverBase : "Initialization"
DiscoverBase --> ApmTopoDiscoverRule : "Query"
```

**Section sources**
- [base.py](file://bkmonitor\apm\core\discover\base.py#L0-L200)
- [config.py](file://bkmonitor\apm\models\config.py#L0-L199)

### Performance Metrics Collection Methods
The APM system collects performance metrics through two methods: real-time calculation from raw trace data and generation of aggregated metrics through pre-calculation tasks.

**Key Metrics**:
*   **Response Time**: Obtained by calculating the difference between a span's `end_time` and `start_time`. Aggregated metrics such as `bk_apm_duration_sum` (total duration) and `bk_apm_duration_bucket` (duration distribution) are generated by the pre-calculation processor.
*   **Throughput**: Measured by counting the number of spans within a unit of time. The `bk_apm_count` metric records the number of traces, while `bk_apm_total` records the total number of spans.
*   **Error Rate**: Determined by checking if a span's `status.code` is `ERROR` to identify failed requests. The `error_count` field records the number of error spans within a single trace.

**Collection Process**:
1.  **Built-in Metric Definition**: The `PlatformConfig` class's `list_metric_config` method defines calculation rules for all built-in metrics.
2.  **Pre-calculation Aggregation**: The `PrecalculateProcessor` accumulates total duration, counts errors, and calculates maximum/minimum durations while processing traces, storing these aggregated results as new documents in pre-calculated storage.

``mermaid
flowchart TD
A[Raw Span Data] --> B{Determine Span Type}
B --> |HTTP Request| C[Calculate Response Time]
B --> |Database Call| D[Calculate DB Duration]
B --> |Message Queue| E[Calculate Message Processing Duration]
C --> F[Accumulate Total Duration]
D --> F
E --> F
A --> G{Check Status Code}
G --> |Success| H[Normal Count]
G --> |Failure| I[Error Count+1]
F --> J[Generate Aggregated Metrics]
I --> J
J --> K[Store in Pre-calculated ES]
```

**Section sources**
- [platform_config.py](file://bkmonitor\apm\core\platform_config.py#L143-L177)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)

### Distributed Tracing Functionality
Distributed tracing functionality allows users to view the complete call chain of a single request within a microservices architecture. APM provides two query modes: original trace query and optimized trace query.

**Call Chain Generation and Display**:
1.  **Original Query (`OriginTraceQuery`)**: Directly queries raw span data. It first retrieves all related spans based on the Trace ID, then the `PrecalculateProcessor.get_trace_info` method organizes these spans into a tree-structured call chain diagram and calculates information such as entry service and call hierarchy.
2.  **Optimized Query (`TraceQuery`)**: Queries summary data from pre-calculated storage. This method is faster and suitable for displaying trace summary information (such as Trace ID, total duration, error status) on list pages. When a user clicks on a trace to view details, the system uses the original query mode to retrieve the complete list of spans.

**Sequence Diagram**:
``mermaid
sequenceDiagram
participant User as User
participant Web as apm_web
participant Query as TraceQuery
participant Storage as Pre-calculated Storage
User->>Web : Request to view Trace list
Web->>Query : query_list()
Query->>Storage : Query summary data (trace_id, trace_duration, error)
Storage-->>Query : Return summary data
Query-->>Web : Return data
Web-->>User : Display Trace list
User->>Web : Click on a Trace to view details
Web->>Query : query_by_trace_ids() or query_list() (original)
Query->>Storage : Query complete Span data
Storage-->>Query : Return complete Span
Query-->>Web : Return complete call chain
Web-->>User : Display complete call chain diagram
```

**Section sources**
- [origin_trace_query.py](file://bkmonitor\apm\core\handlers\query\origin_trace_query.py#L0-L105)
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L0-L200)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)

### APM Data Storage Structure and Query Methods
APM data is primarily stored in Elasticsearch, divided into raw data and pre-calculated data.

**Storage Structure**:
*   **Raw Data**: Stores complete OTLP-formatted span data, including all `resource`, `attributes`, and `events` information. It has a large data volume and relatively lower query performance.
*   **Pre-calculated Data**: Stores trace summary information generated by the `PrecalculateProcessor`. Its data structure is defined by `PrecalculateStorageConfig.TABLE_SCHEMA`, containing fields such as `trace_id`, `app_name`, `trace_duration`, `error_count`, `service_count`, and `root_service`. This structure significantly reduces data volume and improves the performance of aggregate queries.

**Query Methods**:
*   **Query Builder (`QueryConfigBuilder`)**: APM uses `QueryConfigBuilder` to build query statements. It encapsulates the underlying UnifyQuery API, providing chainable methods such as `filter`, `order_by`, and `values`.
*   **Query Handler (`BaseQuery`)**: The `BaseQuery` class is the base class for all queries, defining common query methods like `time_range_queryset` for setting time ranges and `_get_q` for obtaining query builder instances.
*   **Data Source Configuration**: During queries, the `_datasource_configs` dictionary determines which data source (raw log or custom time series) and result table (Result Table) to use.

``mermaid
classDiagram
class BaseQuery {
+bk_biz_id : int
+app_name : str
+retention : int
+_datasource_configs : dict
+q : QueryConfigBuilder
+log_q : QueryConfigBuilder
+metric_q : QueryConfigBuilder
+time_range_queryset() : UnifyQuerySet
+_get_table_id() : str
}
class QueryConfigBuilder {
+table() : self
+filter() : self
+order_by() : self
+values() : self
+time_field() : self
}
class UnifyQuerySet {
+start_time() : self
+end_time() : self
+add_query() : self
+first() : dict
+limit() : self
}
BaseQuery --> QueryConfigBuilder : "Uses"
BaseQuery --> UnifyQuerySet : "Uses"
```

**Section sources**
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L0-L200)
- [builder.py](file://bkmonitor\apm\core\handlers\query\builder.py#L0-L12)
- [storage.py](file://bkmonitor\apm\core\discover\precalculation\storage.py#L0-L433)

### Performance Analysis of Practical Tips
*   **Utilize Pre-calculated Data**: When performing large-scale performance analysis (e.g., viewing QPS trends over the past hour), prioritize queries based on pre-calculated data to achieve faster response times.
*   **Use Filters Appropriately**: When querying traces, use filters like `status_code` or `error` to quickly locate erroneous requests.
*   **Focus on Entry Services**: Analyze `root_service` and `root_service_category` to quickly identify the source of performance bottlenecks.
*   **Analyze Call Hierarchy**: The `hierarchy_count` field reflects the depth of the call chain; an excessively deep call chain could be a sign of performance issues.
*   **Leverage Multi-threaded Query Optimization**: The system uses `ThreadPool.map_ignore_exception` in the `_query_option_values` method to perform parallel queries for multiple fields, significantly reducing the latency of retrieving field option values. This optimization allows the system to handle multiple field queries concurrently instead of sequentially, improving overall query responsiveness.

## Dependency Analysis
The APM system depends on several internal and external components.

``mermaid
graph TD
A[APM] --> B[metadata]
A --> C[core.drf_resource]
A --> D[constants]
A --> E[opentelemetry]
A --> F[bkmonitor.utils]
A --> G[django]
B --> H[ESStorage]
C --> I[api]
D --> J[DataSourceLabel]
D --> K[DataTypeLabel]
E --> L[SpanAttributes]
F --> M[ThreadPool]
F --> N[common_utils]
G --> O[models]
G --> P[Q]
```

**Diagram sources**
- [apm module structure](file://bkmonitor\apm)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L0-L200)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)

## Performance Considerations
*   **Pre-calculation**: By moving expensive aggregation calculations (such as calculating total trace duration and error count) to the data write phase, query performance is greatly enhanced.
*   **Sharding and Routing**: `PrecalculateStorage` uses the `RendezvousHash` algorithm to evenly distribute data across multiple Elasticsearch indexes based on business ID and application name, avoiding performance bottlenecks caused by a single oversized index.
*   **Asynchronous Processing**: Uses `ThreadPool` for parallel processing; for example, in the `PrecalculateProcessor.handle` method, multiple traces are processed in parallel, improving data processing efficiency.
*   **Query Latency Optimization**: The recent update introduced multi-threaded processing in the `_query_option_values` method of `BaseQuery` to reduce the latency of retrieving field option values. By using `ThreadPool.map_ignore_exception`, the system can concurrently query multiple fields instead of sequentially, significantly improving the responsiveness of trace search operations.

**Section sources**
- [storage.py](file://bkmonitor\apm\core\discover\precalculation\storage.py#L0-L433)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L0-L200)

## Troubleshooting Guide
*   **Issue**: Unable to discover application topology.
    *   **Check**: Confirm that the probe is correctly installed and reporting data. Verify that the rules in `ApmTopoDiscoverRule` match the span attributes of the application.
*   **Issue**: Querying trace data is slow.
    *   **Check**: Confirm if a large-scale raw data query is being performed. It is recommended to use pre-calculated data for preliminary analysis. Check the performance and resource usage of the Elasticsearch cluster.
*   **Issue**: Pre-calculated data is not being generated.
    *   **Check**: Confirm that the `PrecalculateStorage` configuration is correct and that Elasticsearch storage is available. Check the logs related to `PrecalculateProcessor` for any errors.

**Section sources**
- [base.py](file://bkmonitor\apm\core\discover\base.py#L0-L200)
- [processor.py](file://bkmonitor\apm\core\discover\precalculation\processor.py#L0-L200)
- [storage.py](file://bkmonitor\apm\core\discover\precalculation\storage.py#L0-L433)

## Conclusion
This document provides a detailed analysis of the APM functionality implementation in the BlueKing monitoring platform. APM offers users a powerful application performance monitoring solution through automated topology discovery, efficient pre-calculation aggregation, and flexible query interfaces. Understanding its underlying data storage structure and query methods helps users more effectively utilize APM for performance issue diagnosis and analysis. Through proper configuration and usage, APM can significantly enhance the observability of microservices architectures.