# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

This is the `scripts/` directory of the **bkmonitor** (BlueKing Monitor) Django project. It contains standalone utility scripts, operational tooling, development helpers, and unit-test infrastructure. These scripts are not part of the main Django application tree; they are invoked directly or pasted into a Django shell.

## Directory Structure

- **`unittest/`** — Docker-based unit-test infrastructure
  - `Dockerfile`: multi-stage image based on `python:3.11-bullseye`, installs MySQL/Redis, sets `DJANGO_CONF_MODULE=conf.worker.development.enterprise`
  - `entrypoint.sh`: container entrypoint
  - `local_settings.py`: database settings copied into the image at build time
  - `parse_test_output.py`: parses `pytest.log`, `testcase.log`, and `coverage.log` to extract pass/fail/error counts and coverage percentages
- **`dev/`** — Development environment templates
  - `run.sh`: installs deps and starts `supervisord` with runserver + optional Celery workers
  - `supervisord.conf`: supervisord config for runserver, celery worker, celery beat, and code-server
  - `local_settings.py.tpl`: template for DB credentials (reads from env vars)
- **`develop/`** — Environment variable templates
  - `env.sh`: exports common Django/Celery env vars for worker development
  - `local_settings_tpl.py`: another local settings template for development
- **`manage/`** — Data-management utilities
  - `plugin_data_info.py`: exports collector-plugin metadata (data IDs, result tables, VM mappings) to JSON or Excel via `openpyxl`
- **`builtin_solutions/`** — Built-in monitoring shell scripts
  - `disk_clean_for_linux.sh`, `topn_cpu.sh`, `topn_mem.sh`

## Standalone Scripts

Scripts in the root of `scripts/` are typically run inside a Django shell (`python manage.py shell_plus`) or as one-off commands.

| Script | Purpose | Invocation |
|--------|---------|------------|
| `cleanup_data_id.py` | Idempotently disable a `data_id`: disables its `DataSource`, disables linked `ResultTable`s, and deletes GSE routes. Safe to rerun. | Paste functions into Django shell; call `cleanup_data_id(1500001)` or `cleanup_data_ids([...])` |
| `retry_action_script.py` | Retry failed `webhook`/`message_queue` FTA actions by ID. Updates status to `RETRYING` and re-queues them. | Paste into Django shell; call `retry_action_ids([12345, ...])` |
| `query_unused_bk_data_id_by_kafka.py` | Query unused `bk_data_id`s in specified Kafka clusters and output CSVs (`{prefix}_bkgse.csv`, `{prefix}_bkdata.csv`). Matches deleted BCS clusters, soft-deleted custom events/TS tables, and disabled flat-batch result tables. | Paste into Django shell; call `query_unused_bk_data_id_by_kafka(["kafka.example.com"])` |
| `manage/plugin_data_info.py` | Export plugin data info. | Paste into Django shell; call `get_plugin_infos()` then `save_to_json(...)` or `json_to_excel(...)` |
| `add_py_license_header.py` | Recursively add Tencent license header to `.py` files. | `python scripts/add_py_license_header.py header.txt scripts ".*\.py$"` |
| `add_jscss_license_header.sh` | Add license header to `.js`/`.css` files. | Run directly |
| `convert_yaml.py` | Convert API gateway YAML definitions to JSON, YAML, or Swagger format. | `python scripts/convert_yaml.py -s source.yaml -t ./ -f json` |
| `influxdb_checker.py` | Collect InfluxDB database stats (disk usage, series count, measurements) and write `influxdb_info.json`. | Run directly (expects `bk-monitor-influxdb:8086`) |
| `udp_echo_server.py` | Simple UDP echo server for testing. | Run directly |

## Testing

### Docker Test Image

From the repo root:

```bash
make build-test-image
docker run -it mirrors.tencent.com/bkmonitorv3/bkmonitor-test:latest bash
```

Inside the container:

```bash
pip install --no-cache-dir -r requirements_test.txt

# Setup databases
mysql -e 'CREATE DATABASE `bk_monitor_saas` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;'
mysql -e 'CREATE DATABASE `bk_monitor_api` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;'

# Migrate
env DJANGO_CONF_MODULE="" BKAPP_DEPLOY_ENV="web" python manage.py migrate || true
env DJANGO_CONF_MODULE="" BKAPP_DEPLOY_ENV="web" python manage.py migrate || true
```

### Running Tests

```bash
# pytest
pytest alarm_backends/tests 2>&1 | tee pytest.log || true

# Django test runner
python manage.py test alarm_backends.tests 2>&1 | tee testcase.log || true
```

### Parsing Results

```bash
python scripts/unittest/parse_test_output.py "$(pwd)/pytest.log"
python scripts/unittest/parse_test_output.py "$(pwd)/testcase.log"
```

### Coverage

```bash
COVERAGE_SOURCE="alarm_backends,bkmonitor/data_source"
COVERAGE_OMIT_PATH="*/test/*,*/virtualenv/*,*/venv/*,*/migrations/*,*/mock_data/*,*/tests/*"

coverage run --parallel-mode --source="$COVERAGE_SOURCE" --omit="$COVERAGE_OMIT_PATH" -m pytest alarm_backends/tests bkmonitor/data_source/tests 2>&1 | tee pytest.log || true
coverage run --parallel-mode --source="$COVERAGE_SOURCE" --omit="$COVERAGE_OMIT_PATH" ./manage.py test alarm_backends.tests bkmonitor.data_source.tests 2>&1 | tee testcase.log || true

coverage combine
coverage report --sort=cover | tee coverage.log
coverage html  # optional, outputs to htmlcov/

python scripts/unittest/parse_test_output.py "$(pwd)/coverage.log"
```

## Important Conventions

- Most operational scripts are designed to be **pasted into a Django shell** (`python manage.py shell_plus`) rather than run as standalone commands. They import Django models directly and rely on the ORM.
- `cleanup_data_id.py` and `retry_action_script.py` are designed to be **idempotent and safe to rerun**.
- When modifying `unittest/Dockerfile` or `unittest/local_settings.py`, remember the image is built from the repo root via `make build-test-image`.
