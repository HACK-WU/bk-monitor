# Trace Query API

<cite>
**Referenced Files in This Document**   
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py)
- [builder.py](file://bkmonitor\apm\core\handlers\query\builder.py)
- [proxy.py](file://bkmonitor\apm\core\handlers\query\proxy.py)
- [unify_query/builder.py](file://bkmonitor\bkmonitor\data_source\unify_query\builder.py)
- [storage.py](file://bkmonitor\apm\core\discover\precalculation\storage.py)
- [apm.py](file://bkmonitor\constants\apm.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Core Components](#core-components)
3. [TraceQuery Class and Inheritance](#tracequery-class-and-inheritance)
4. [Key Methods of TraceQuery](#key-methods-of-tracequery)
5. [Query Pipeline and Data Flow](#query-pipeline-and-data-flow)
6. [Performance Implications of time_align=False](#performance-implications-of-time_alignfalse)
7. [Practical Usage Examples](#practical-usage-examples)
8. [Performance Best Practices](#performance-best-practices)

## Introduction
The Trace Query API is a critical component of the distributed tracing system within the monitoring platform, designed to enable efficient querying of trace data across distributed applications. This API provides a structured interface for retrieving trace information, supporting operations such as list queries, simple info retrieval, and complex filtering. The system is built on a layered architecture that abstracts the underlying data storage and query execution mechanisms, allowing for flexible integration with various data sources. The primary purpose of this API is to support observability by enabling developers and operators to analyze application performance, diagnose issues, and understand system behavior through detailed trace data. The API is designed with performance and scalability in mind, incorporating features such as time range optimization, efficient filtering, and pagination to handle large volumes of trace data.

## Core Components

The Trace Query API consists of several core components that work together to provide a comprehensive querying capability. At the heart of the system is the `TraceQuery` class, which serves as the main interface for trace data retrieval. This class inherits from `BaseQuery`, establishing a consistent pattern for query operations across different data types. The query execution is powered by the `UnifyQuerySet` and `QueryConfigBuilder` classes, which form the foundation of the query pipeline. These components work in concert to build, optimize, and execute queries against the underlying data storage. The system also integrates with the precalculation storage mechanism, which organizes trace data into multiple result tables for efficient retrieval. The `QueryProxy` class acts as a facade, providing a unified interface to different query modes and handling cross-application trace relationships. Together, these components create a robust and flexible system for distributed trace querying that balances performance, functionality, and ease of use.

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L1-L212)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L1-L378)
- [proxy.py](file://bkmonitor\apm\core\handlers\query\proxy.py#L1-L319)

## TraceQuery Class and Inheritance

``mermaid
classDiagram
class BaseQuery {
+int bk_biz_id
+str app_name
+int retention
+dict overwrite_datasource_configs
+USING_LOG : tuple[str, str]
+USING_METRIC : tuple[str, str]
+DEFAULT_DATASOURCE_CONFIGS : dict[str, dict[str, Any]]
+TIME_PADDING : int
+TIME_FIELD_ACCURACY : int
+DEFAULT_TIME_FIELD : str
+KEY_REPLACE_FIELDS : dict[str, str]
+__init__(bk_biz_id, app_name, retention, overwrite_datasource_configs)
+_get_table_id(datasource_type) str
+_get_q(datasource_type) QueryConfigBuilder
+q() QueryConfigBuilder
+log_q() QueryConfigBuilder
+metric_q() QueryConfigBuilder
+time_range_queryset(start_time, end_time, using_scope) UnifyQuerySet
+_query_option_values(start_time, end_time, fields, q, limit) dict[str, list[str]]
+_collect_option_values(q, queryset, field, option_values) void
+_get_data_page(q, queryset, select_fields, count_field, offset, limit) types.Page
+_translate_field(field) str
+_build_filters(filters) Q
+_add_logic_filter(q, field, value) Q
+_get_time_range(retention, start_time, end_time) tuple[int, int]
+build_query_q(filters, query_string) QueryConfigBuilder
+_query_field_topk(q, start_time, end_time, field, limit) list[dict[str, Any]]
+_query_total(q, start_time, end_time) int
+_query_field_aggregated_value(q, start_time, end_time, field, method) int | float
+query_graph_config(start_time, end_time, field, filters, query_string) dict
}
class TraceQuery {
+str DEFAULT_TIME_FIELD
+dict KEY_PREFIX_TRANSLATE_FIELDS
+dict KEY_REPLACE_FIELDS
+_get_select_fields(exclude_fields) list[str]
+build_app_filter() Q
+build_query_q(filters, query_string) QueryConfigBuilder
+_get_ebpf_application() ApmApplication | None
+query_list(start_time, end_time, offset, limit, filters, exclude_fields, query_string, sort) tuple[list[dict[str, Any]], int]
+query_relation_by_trace_id(trace_id, start_time, end_time) dict[str, Any] | None
+query_latest(trace_id) dict[str, Any] | None
+_translate_field(field) str
+_add_logic_filter(q, field, value) Q
+query_by_trace_ids(result_table_ids, trace_ids, retention, start_time, end_time) list[dict[str, Any]]
+query_simple_info(start_time, end_time, offset, limit) tuple[list[dict[str, Any]], int]
+query_field_topk(start_time, end_time, field, limit, filters, query_string) list[dict[str, Any]]
+query_field_aggregated_value(start_time, end_time, field, method, filters, query_string) int | float
+query_option_values(datasource_type, start_time, end_time, fields, limit, filters, query_string) dict[str, list[str]]
}
BaseQuery <|-- TraceQuery
```

**Diagram sources**
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L1-L378)
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L1-L212)

**Section sources**
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L1-L378)
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L1-L212)

## Key Methods of TraceQuery

### query_list Method
The `query_list` method is the primary interface for retrieving a paginated list of traces that match specified criteria. This method accepts parameters for time range, pagination (offset and limit), filtering conditions, field exclusion, query strings, and sorting. It begins by determining the fields to select based on the `exclude_fields` parameter, using the `_get_select_fields` method to compute the complete set of fields from the precalculation storage schema. The method then creates a `UnifyQuerySet` with the specified time range and constructs a `QueryConfigBuilder` using the `build_query_q` method, which incorporates both the provided filters and the application-specific filter. The query is ordered according to the provided sort parameters or defaults to descending order by the `DEFAULT_TIME_FIELD` ("min_start_time"). The `_get_data_page` method is used to execute the query and return both the data and total count. This method is optimized for performance by leveraging the underlying query pipeline and pagination mechanisms.

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L61-L92)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L320-L340)

### query_simple_info Method
The `query_simple_info` method provides a streamlined interface for retrieving basic trace information with minimal overhead. This method is specifically designed to return a reduced set of fields that are commonly needed for trace overviews, including trace ID, application name, error status, trace duration, and root service category. By limiting the selected fields to only these essential attributes, the method optimizes query performance and reduces network payload. The implementation creates a `UnifyQuerySet` with the specified time range and applies the application filter to ensure data isolation. The query is ordered by the default time field in descending order to return the most recent traces first. This method is particularly useful for scenarios where a high-level view of trace data is sufficient, such as in trace list displays or summary dashboards.

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L153-L180)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L320-L340)

### build_query_q Method
The `build_query_q` method is responsible for constructing the query configuration that defines the filtering and search criteria for trace queries. This method extends the base implementation by adding an application-specific filter to ensure that queries are scoped to the correct business and application context. It first calls the parent class's `build_query_q` method to process the provided filters and query string, then applies an additional filter using the `build_app_filter` method. This ensures that all queries are automatically constrained to the specified business ID and application name, providing data isolation and security. The method returns a `QueryConfigBuilder` instance that can be further modified with additional query parameters such as ordering, grouping, or aggregation. This approach allows for flexible query construction while maintaining consistent application scoping across all query operations.

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L45-L55)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L360-L370)

## Query Pipeline and Data Flow

``mermaid
sequenceDiagram
participant Client as "Client Application"
participant TraceQuery as "TraceQuery"
participant BaseQuery as "BaseQuery"
participant QueryConfigBuilder as "QueryConfigBuilder"
participant UnifyQuerySet as "UnifyQuerySet"
participant Storage as "Data Storage"
Client->>TraceQuery : query_list(start_time, end_time, offset, limit, filters, ...)
TraceQuery->>TraceQuery : _get_select_fields(exclude_fields)
TraceQuery->>BaseQuery : time_range_queryset(start_time, end_time)
BaseQuery->>UnifyQuerySet : Create UnifyQuerySet with time range
UnifyQuerySet->>UnifyQuerySet : Set time_align=False
TraceQuery->>TraceQuery : build_query_q(filters, query_string)
TraceQuery->>BaseQuery : build_query_q(filters, query_string)
BaseQuery->>BaseQuery : _build_filters(filters)
BaseQuery->>FilterOperator : get_handler(operator)
FilterOperator-->>BaseQuery : Return filter handler
BaseQuery->>QueryConfigBuilder : Apply filters to QueryConfigBuilder
QueryConfigBuilder-->>TraceQuery : Return configured builder
TraceQuery->>QueryConfigBuilder : Add order_by clause
TraceQuery->>BaseQuery : _get_data_page(q, queryset, select_fields, OtlpKey.TRACE_ID, offset, limit)
BaseQuery->>UnifyQuerySet : Add query to queryset
UnifyQuerySet->>UnifyQuerySet : Apply offset and limit
UnifyQuerySet->>Storage : Execute query
Storage-->>UnifyQuerySet : Return query results
UnifyQuerySet-->>BaseQuery : Return data and total
BaseQuery-->>TraceQuery : Return page_data
TraceQuery-->>Client : Return (data, total)
```

**Diagram sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L61-L92)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L320-L340)
- [unify_query/builder.py](file://bkmonitor\bkmonitor\data_source\unify_query\builder.py#L102-L163)

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L61-L92)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L320-L340)

## Performance Implications of time_align=False

The `time_align=False` setting in the `time_range_queryset` method has significant performance implications for the Trace Query API. This setting controls whether the query time range is aligned to aggregation intervals, which affects both query performance and result accuracy. When `time_align=False`, the query uses the exact time range specified by the caller without adjusting the end time to align with aggregation boundaries. This approach provides more precise results that reflect the actual data within the specified time window, which is particularly important for trace queries where temporal accuracy is critical.

The primary performance benefit of `time_align=False` is reduced query latency. By avoiding time alignment, the system can execute queries directly against the specified time range without the overhead of calculating aligned boundaries or potentially retrieving additional data outside the requested range. This is especially advantageous in real-time monitoring scenarios where users expect immediate responses to their queries. The documentation explicitly states that this setting is used because "Tracing retrieval scenarios have high real-time requirements, and time alignment causes the end timestamp to move forward; here, consistent with event retrieval, time is not aligned by default."

However, this setting also has implications for caching and query optimization. Without time alignment, identical queries with slightly different time ranges may not benefit from query result caching, potentially leading to repeated execution of similar queries. Additionally, some storage backends may be optimized for aligned time ranges, so disabling alignment could prevent the use of certain performance optimizations at the storage layer. The trade-off is deliberate, prioritizing query precision and low latency over potential caching benefits, which aligns with the real-time nature of distributed tracing analysis.

**Section sources**
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L280-L290)

## Practical Usage Examples

### Basic Trace List Query
```python
# Initialize TraceQuery instance
trace_query = TraceQuery(bk_biz_id=123, app_name="my-app", retention=30)

# Query traces from the last hour with pagination
start_time = int(time.time()) - 3600  # 1 hour ago
end_time = int(time.time())
offset = 0
limit = 50

# Execute query
traces, total_count = trace_query.query_list(
    start_time=start_time,
    end_time=end_time,
    offset=offset,
    limit=limit,
    sort=["min_start_time desc"]
)

print(f"Retrieved {len(traces)} traces out of {total_count} total")
for trace in traces:
    print(f"Trace ID: {trace['trace_id']}, Duration: {trace['trace_duration']}ms, Error: {trace['error']}")
```

### Filtered Query with Query String
```python
# Query traces with specific criteria
filters = [
    {
        "key": "error",
        "value": [True],
        "operator": "equal"
    },
    {
        "key": "root_service_category",
        "value": ["web"],
        "operator": "equal"
    }
]

# Use query string for complex filtering
query_string = 'trace_duration:>1000 AND root_span_name:"/api/users"'

traces, total = trace_query.query_list(
    start_time=start_time,
    end_time=end_time,
    offset=0,
    limit=20,
    filters=filters,
    query_string=query_string
)

print(f"Found {total} slow error traces in web services")
```

### Simple Info Query for Dashboard
```python
# Efficiently retrieve basic trace information for a dashboard
simple_traces, total = trace_query.query_simple_info(
    start_time=start_time,
    end_time=end_time,
    offset=0,
    limit=100
)

# Process results for display
error_count = sum(1 for trace in simple_traces if trace["error"])
avg_duration = sum(trace["trace_duration"] for trace in simple_traces) / len(simple_traces) if simple_traces else 0

print(f"Dashboard stats: {total} traces, {error_count} errors, avg duration: {avg_duration:.2f}ms")
```

### Cross-Application Trace Relationship Query
```python
# Find cross-application relationships for a specific trace
trace_id = "abc123-def456-ghi789"
relation = trace_query.query_relation_by_trace_id(
    trace_id=trace_id,
    start_time=start_time,
    end_time=end_time
)

if relation:
    print(f"Trace {trace_id} has cross-application relationship:")
    print(f"  Business: {relation['bk_biz_id']} ({relation['biz_name']})")
    print(f"  Application: {relation['app_name']}")
    print(f"  App ID: {relation['bk_app_code']}")
else:
    print(f"No cross-application relationships found for trace {trace_id}")
```

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L61-L180)
- [proxy.py](file://bkmonitor\apm\core\handlers\query\proxy.py#L225-L254)

## Performance Best Practices

### Optimize Query Time Ranges
Always specify appropriate time ranges for queries to minimize the amount of data scanned. The system automatically applies time padding (5 seconds by default) to account for timing discrepancies, but overly broad time ranges can significantly impact performance. For real-time monitoring, limit queries to recent time windows (e.g., last 15 minutes, last hour). For historical analysis, consider breaking large time ranges into smaller chunks and processing them sequentially.

### Use Field Exclusion Strategically
When calling `query_list`, use the `exclude_fields` parameter to remove unnecessary fields from the response. This reduces both query execution time and network payload. For list views, consider excluding detailed fields like collections or nested objects that are only needed when viewing individual trace details.

### Leverage Simple Info Queries
Use `query_simple_info` instead of `query_list` when only basic trace information is needed. This method is optimized to retrieve only essential fields (trace_id, app_name, error, trace_duration, root_service_category), resulting in faster query execution and smaller response sizes.

### Implement Proper Pagination
Always use offset and limit parameters to paginate results, especially when expecting large result sets. Avoid retrieving all data at once, as this can overwhelm both the server and client. Implement infinite scrolling or page-based navigation in client applications.

### Optimize Filtering
Apply the most restrictive filters first to reduce the dataset early in the query pipeline. Use exact match filters (equal) when possible, as they are generally more efficient than range or pattern matching queries. Combine multiple filters to narrow down results progressively.

### Minimize Query String Complexity
While query strings provide powerful filtering capabilities, complex expressions can impact performance. For frequently used queries, consider using structured filters instead of query strings, as they can be more efficiently optimized by the query engine.

### Cache Frequent Queries
Implement client-side caching for queries that are likely to be repeated with the same parameters. This is particularly effective for dashboards and monitoring views that refresh at regular intervals.

### Monitor Query Performance
Regularly review query performance metrics and optimize slow queries. The system logs query execution details, which can be analyzed to identify bottlenecks and optimize query patterns.

**Section sources**
- [trace_query.py](file://bkmonitor\apm\core\handlers\query\trace_query.py#L61-L180)
- [base.py](file://bkmonitor\apm\core\handlers\query\base.py#L280-L290)
- [unify_query/builder.py](file://bkmonitor\bkmonitor\data_source\unify_query\builder.py#L478-L546)