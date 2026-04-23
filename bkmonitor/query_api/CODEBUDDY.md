# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Overview

`query_api` is a Django app within bkmonitor that acts as the data query proxy. It provides `Resource` classes consumed by `kernel_api` views to execute time-series SQL queries and Elasticsearch DSL queries against underlying storage. It does not expose its own URL routes.

## Testing

Run tests from the project root (`bkmonitor/`):

```bash
# Run all query_api tests
pytest query_api

# Run with coverage
pytest --cov=query_api -vv query_api

# Run a specific test file
pytest query_api/tests/test_resource.py
pytest query_api/tests/test_influxdb_drivers.py
pytest query_api/tests/test_client_pool.py

# Run a single test
pytest query_api/tests/test_resource.py::test_get_ts_data_resource
```

`query_api/tests/conftest.py` manually bootstraps Django settings when running outside the standard pytest suites.

## Architecture

### Entry Points (`resources.py`)

The module exposes two `core.drf_resource.Resource` classes:

- **`GetTSDataResource`**: Accepts a `sql` string. Delegates to `load_driver_by_sql(sql)` in `drivers/proxy.py`, which returns a driver instance whose `.query()` method executes the query and returns `{"list": [...], "totalRecords": N, "timetaken": ..., "device": ...}`.
- **`GetEsDataResource`**: Accepts `index_name`/`index_names`, `doc_type`, `query_body`, and `datasource_info`. Creates an ES client via `metadata.utils.es_tools.get_client_by_datasource_info` and calls `search()` directly.

These Resources are wired into HTTP endpoints by `kernel_api/views/query.py`, not by this app.

### SQL Parsing (`sql_parse/`)

- **`SQLStatement`** (`sql_parse/statement.py`): Wraps `sqlparse` to extract structured components (`select_items`, `result_table`, `where_token`, `group_items`, `order_items`, `limit_item`, `slimit_item`) from a single SELECT statement. It tokenizes the query and exposes `refresh_token()` for re-parsing after mutations.
- **`sql_parse/__init__.py`**: Patches `sqlparse.keywords.KEYWORDS` at import time to recognize InfluxQL-specific tokens (`SLIMIT`, `SOFFSET`).

### Driver Loading (`drivers/`)

- **`DriverProxy`** (`drivers/proxy.py`): Validates that the SQL has SELECT items, resolves the result table string against `metadata.models.ResultTable`, checks that `default_storage` is configured, then dynamically imports `query_api.drivers.<default_storage>` and calls its `load_driver(parsed_sql)` function.
- **Current storage support**: Only `influxdb` is implemented.

### InfluxDB Driver (`drivers/influxdb/`)

`InfluxDBDriver` (defined in `drivers/influxdb/client.py`) subclasses `DriverProxy` and performs extensive SQL-to-InfluxQL transformation:

1. **Metadata lookup**: Fetches physical storage info via `ResultTable.get_result_table_storage_info(table_id, ClusterInfo.TYPE_INFLUXDB)` to get the real database, retention policy, and table name.
2. **Biz filter injection**: Automatically injects `bk_biz_id = <biz_id>` into the WHERE clause for non-custom time-series result tables (detected via `TimeSeriesGroup`).
3. **Free schema handling**: For `SCHEMA_TYPE_FREE` tables, converts the selected metric field name into a filter on `metric_name` and rewrites the select to `metric_value`.
4. **Dialect translation**:
   - `AVG` → `MEAN`
   - `minuteX` → `time(Xm)` in SELECT, GROUP BY, and ORDER BY
   - `LIKE` / `NOT LIKE` → `=~` / `!~` with regex-escaped values
   - Time aliases (`'1h'`, `'today'`) converted to nanosecond timestamps
   - Millisecond timestamps padded to nanoseconds
   - Result table token replaced with `"<rp>".<table>`
5. **Safety limits**: Enforces `MAX_LIMIT = 50000` on both `LIMIT` and `SLIMIT`. Missing `SLIMIT` is auto-injected.
6. **Query execution**: Uses a shared `ClientPoolManage` (`pool`) to get or create an `InfluxDBClient`. The driver switches user if `auth_info` is present, then queries InfluxDB with `epoch="ms"`.
7. **Result formatting**: Flattens InfluxDB series into a list of dicts, renames adapter-mapped group fields back to their original names, and preserves the original `minuteX` field alias on the `time` column.

### Connection Pool (`drivers/client_pool.py`)

`ClientPoolManage` is an LRU client pool keyed by a factory-defined `client_key`. When the pool exceeds `max_poll_size`, the oldest client is evicted and closed. `InfluxDBClientFactory` keys clients by `host:port` and passes through standard `InfluxDBClient` kwargs.

### Exceptions (`exceptions.py`)

All query errors extend `QueryExceptions` and carry a string `error_code`:

- `ResultTableNotExist` (`01`)
- `StorageResultTableNotExist` (`02`)
- `QueryTimeOut` (`03`)
- `QueryForbidden` (`04`)
- `SQLSyntaxError` (`06`)
- `StorageNotSupported` (`07`)
- `TimeFieldError` (`08`)

## Important Conventions

- This module is **storage-driver pluggable**: adding a new backend requires creating `query_api/drivers/<storage_name>/` with a `load_driver(sql_statement)` function that returns a queryable driver object.
- SQL mutations are done in-place on the `sqlparse` token tree via `SQLStatement._replace_token`. After mutation, call `refresh_token()` if you need `SQLStatement` to re-extract clauses.
- `query_api` depends heavily on `metadata.models.ResultTable` and `metadata.models.ClusterInfo` for routing queries to the correct physical storage.
