# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is the `metadata` Django app within **bkmonitor** (BlueKing Monitor). It manages monitoring metadata including data sources, result tables, storage configurations, BCS cluster info, and data links to BKBase.

- **Python version**: 3.11 (strictly `==3.11.*`)
- **Django version**: 4.2.27
- **Dependency manager**: `uv` (not pip)
- **Parent project**: See `/root/bk-monitor-learn/bkmonitor/CODEBUDDY.md` for monorep-level guidance

## Common Commands

### Testing

Tests for metadata are located in `metadata/tests/` and are configured in `pyproject.toml` under `[tool.pytest.ini_options]`.

```bash
# Run all metadata tests
pytest metadata/tests

# Run a specific test file
pytest metadata/tests/test_models.py

# Run a specific test
pytest metadata/tests/test_models.py::test_some_function

# Run with coverage
pytest --cov=metadata metadata/tests
```

Pytest automatically sets the following environment variables (defined in `pyproject.toml`):
- `DJANGO_CONF_MODULE=conf.worker.development.community`
- `BKAPP_DEPLOY_PLATFORM=community`
- `USE_DYNAMIC_SETTINGS=0`
- `django_find_project=false`
- `BK_MONITOR_APP_CODE=bk_monitorv3`
- `BK_MONITOR_APP_SECRET=secret`

### Django Management Commands

The `metadata/management/commands/` directory contains many operational commands. Key ones include:

```bash
# Initialize space types
python manage.py init_space_type

# Initialize space data
python manage.py init_space_data

# Check data link health
python manage.py check_datalink_health

# Sync BCS space
python manage.py sync_bcs_space

# Sync CMDB space
python manage.py sync_cmdb_space

# Query data ID by MQ
python manage.py query_data_id_by_mq

# Query disabled data IDs
python manage.py query_disabled_data_id

# Refresh InfluxDB router
python manage.py refresh_influxdb_router

# Clean old Consul config
python manage.py clean_old_consul_config
```

### Celery Tasks

Metadata has periodic Celery tasks defined in `metadata/task/tasks.py`. They run on the `celery_metadata_task_worker` queue. Key tasks include:

- `refresh_custom_report_config`
- `refresh_custom_log_report_config`
- `refresh_entity_definition_to_redis`
- `sync_metadata`

## Architecture

### App Structure

```
metadata/
├── models/              # Django ORM models
│   ├── data_source.py   # DataSource, DataSourceOption, DataSourceResultTable
│   ├── result_table.py  # ResultTable, ResultTableField, ResultTableOption, etc.
│   ├── storage.py       # ClusterInfo, ESStorage, InfluxDBStorage, KafkaStorage, etc.
│   ├── influxdb_cluster.py  # InfluxDBClusterInfo, InfluxDBHostInfo
│   ├── custom_report/   # EventGroup, TimeSeriesGroup, LogGroup
│   ├── bcs/             # BCSClusterInfo, ServiceMonitorInfo, PodMonitorInfo
│   ├── space/           # Space, SpaceType, SpaceDataSource, SpaceResource
│   ├── data_link/       # DataLink, DataLink configs (bridge to BKBase)
│   ├── vm/              # AccessVMRecord, SpaceVMInfo
│   ├── es_snapshot.py   # ES snapshot models
│   ├── bkdata.py        # BkBaseResultTable
│   └── constants.py     # Model-level constants
├── resources/           # core.drf_resource Resources (business logic)
│   ├── resources.py     # Main metadata resources
│   ├── cluster.py       # Cluster-related resources
│   ├── space.py         # Space-related resources
│   ├── bkdata_link.py   # BKBase data link resources
│   ├── datalink_operation.py  # Data link operations
│   ├── log_datalink.py  # Log data link resources
│   ├── entity_relation.py  # Entity relation resources
│   └── vm.py            # VM storage resources
├── service/             # Service layer (business logic helpers)
│   ├── sync_metadata.py # sync_kafka_metadata, sync_vm_metadata
│   ├── storage_details.py
│   ├── vm_storage.py
│   └── space_redis.py
├── task/                # Celery tasks and background jobs
│   ├── tasks.py         # Celery task definitions
│   ├── config_refresh.py
│   ├── custom_report.py
│   ├── bcs.py
│   ├── bkbase.py
│   ├── sync_space.py
│   └── datalink.py
├── utils/               # Utility modules
│   ├── consul_tools.py  # Consul operations
│   ├── redis_tools.py   # Redis operations
│   ├── es_tools.py      # Elasticsearch helpers
│   ├── influxdb_tools.py
│   ├── bcs.py           # BCS helpers
│   └── bkbase.py        # BKBase helpers
├── tests/               # Test suite
├── management/commands/ # Django management commands
├── config.py            # App-specific config (Consul paths, data ID ranges)
├── signals.py           # Django signals (pre_delete, post_save)
└── health_check.py      # Scenario-based health checks
```

### Key Models

#### DataSource (`metadata/models/data_source.py`)

Represents a monitoring data source. Key fields:
- `bk_data_id`: Unique data source ID (allocated by GSE, range 1100000-2097151)
- `data_name`: Human-readable name
- `etl_config`: ETL configuration name
- `mq_cluster_id`: Associated Kafka/Redis cluster
- `bk_tenant_id`: Tenant ID (multi-tenant)

Built-in data IDs (1100000-1199999) are reserved for system use. User-defined IDs start at 1200000 (or 1500000 for v3.2).

#### ResultTable (`metadata/models/result_table.py`)

Represents a logical result table. Key concepts:
- `table_id`: Unique identifier (e.g., `system.cpu_summary`)
- `schema_type`: `free`, `dynamic`, or `fixed`
- `REAL_STORAGE_DICT`: Maps cluster types to storage model classes

#### Storage Models (`metadata/models/storage.py`)

Storage implementations:
- `ESStorage`: Elasticsearch storage
- `InfluxDBStorage`: InfluxDB storage
- `KafkaStorage`: Kafka storage
- `RedisStorage`: Redis storage
- `DorisStorage`: Doris storage
- `BkDataStorage`: BKBase storage
- `ClusterInfo`: Storage cluster metadata

#### Space Models (`metadata/models/space/`)

Space (multi-tenant/workspace) management:
- `Space`: Space definition
- `SpaceType`: Space type (e.g., business, project)
- `SpaceDataSource`: Space-to-data-source mapping
- `SpaceResource`: Space resources

#### Data Link Models (`metadata/models/data_link/`)

Bridge to BKBase data link platform. See `metadata/models/data_link/README.md` for detailed documentation.

Core models:
- `DataLink`: Orchestrates a complete data link
- `DataIdConfig`: BKBase DataId component config
- `ResultTableConfig`: BKBase ResultTable component config
- `VMStorageBindingConfig`: VM storage binding
- `ESStorageBindingConfig`: ES storage binding
- `DataBusConfig`: DataBus component config
- `ConditionalSinkConfig`: Conditional routing sink

### Data Link Architecture

The data link module (`metadata/models/data_link/`) is the bridge between bkmonitor and BKBase (BlueKing Base / 蓝鲸计算平台).

Key concepts:
- **DataLink**: Represents a complete data pipeline strategy
- **Strategy**: Determines how components are assembled (e.g., `BK_STANDARD_V2_TIME_SERIES`, `BK_LOG`, `BCS_FEDERAL_SUBSET_TIME_SERIES`)
- **Components**: DataId, ResultTable, StorageBinding, DataBus, ConditionalSink
- **Namespace**: `bkmonitor` (time series) or `bklog` (logs)

A typical time-series link:
```
DataId -> DataBus -> VMStorageBinding -> ResultTable + VMStorageCluster
```

A log link:
```
DataId -> DataBus -> ESStorageBinding -> ResultTable + ESCluster
                -> DorisStorageBinding -> ResultTable + DorisCluster
```

### Signals (`metadata/signals.py`)

Django signals registered:
- `pre_delete` on `DataSource`: Cleans up Consul config
- `pre_delete` on `InfluxDBStorage`: Cleans up InfluxDB router in Consul
- `post_save` on `InfluxDBHostInfo`: Refreshes Consul and Redis cluster config

Signals are skipped in `development` environment.

### Consul and Redis Usage

Metadata heavily uses Consul for configuration distribution and Redis for caching.

- **Consul paths** are defined in `metadata/config.py`:
  - `CONSUL_PATH`: `{APP_CODE}_{PLATFORM}_{ENVIRONMENT}/metadata`
  - `CONSUL_SERVICE_PATH`: `{APP_CODE}_{PLATFORM}_{ENVIRONMENT}/service`
  - `CONSUL_DATA_ID_PATH_FORMAT`: Path template for data ID configs
  - `CONSUL_TRANSFER_PATH`: Transfer service config path

- **Redis** utilities are in `metadata/utils/redis_tools.py`:
  - `RedisTools`: Generic Redis operations
  - `bkbase_redis_client`: BKBase-specific Redis client

### Data ID Allocation Rules

From `metadata/README.md`:

- **Range**: 1048576 ~ 2097151 (allocated by GSE)
- **Reserved**: 1048576 ~ 1099999
- **Built-in**: 1100000 ~ 1199999 (system data sources)
- **User-defined (v3.1)**: 1200000 ~ 1499999
- **User-defined (v3.2)**: 1500000 ~ 2097151

Built-in data IDs include:
- `1100000`: Global alert reporting
- `1100001`: Collector heartbeat (global)
- `1100002`: Collector heartbeat (per task)
- `1100003`: Ping server data
- `1100004`: bkmonitorproxy heartbeat
- `1100005`: pingserver data

### Multi-Tenancy

Metadata supports multi-tenancy via `bk_tenant_id`:
- Most models have a `bk_tenant_id` field
- `data_name + bk_tenant_id` is a composite unique key on `DataSource`
- `ENABLE_MULTI_TENANT_MODE` setting controls tenant behavior
- Default tenant ID is defined in `constants.common.DEFAULT_TENANT_ID`

### Health Checks (`metadata/health_check.py`)

Scenario-based health checks for different data scenes:
- `CUSTOM_METRIC`: Custom metrics by `bk_data_id`
- `CUSTOM_EVENT`: Custom events by `bk_data_id`
- `UPTIME_CHECK`: Uptime checks by `bk_biz_id`
- `HOST_PROCESS`: Host/process metrics by `bk_biz_id`
- `BCS`: Container monitoring by `bcs_cluster_id`
- `APM`: APM by `bk_biz_id` and `app_name`

## Important Conventions

- **Line length**: 120 characters (Ruff config, inherited from parent project)
- **Database**: Backend apps use `monitor_api` database (see parent `CODEBUDDY.md` for routing rules)
- **Transactions**: Strategy assembly in data link uses `transaction.atomic` to avoid partial config writes
- **Idempotency**: Prefer `update_or_create` when creating data link components
- **Deletion order**: Data link components must be deleted in reverse dependency order
- **Logging**: Use `logging.getLogger("metadata")` for metadata-specific logs
- **Imports**: Be careful with circular imports in `models/__init__.py`; some model references are set lazily in `apps.py:ready()`