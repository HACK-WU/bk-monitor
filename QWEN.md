# Qwen Code Context for bk-monitor

## Language
所有的输出使用中文

## Mermaid
所有的输出不要带行号

## Comment
1. 为代码生成注释时，请使用中文注释。
2. 为代码注释时，在函数或方法的下面简要概括代码的执行步骤，例如
```python
def process_view(self, request, callback, callback_args, callback_kwargs):
    """
    处理视图请求的CSRF验证中间件逻辑

    参数:
        request: HttpRequest对象，包含请求元数据和状态信息
        callback: 视图函数对象，可能带有csrf_exempt装饰器标记
        callback_args: 视图函数的位置参数元组
        callback_kwargs: 视图函数的关键字参数字典

    返回值:
        None表示继续中间件链处理
        中间件响应对象（由_accept/_reject方法生成）表示终止请求处理

    该方法实现完整的CSRF攻击防护流程，包含：
    1. 安全方法放行（GET/HEAD/OPTIONS/TRACE）
    2. 双重提交Cookie验证机制
    3. HTTPS请求的严格来源验证（Origin/Referer检查）
    4. CSRF Token有效性验证
    """
    pass
```

## Project Overview

This is the **BlueKing Monitor (bk-monitor)** platform, a comprehensive monitoring solution developed by Tencent BlueKing. Its primary purpose is to provide data collection, large-scale data processing, alerting, and extensibility for monitoring various system and application metrics.

Key aspects:
- It's designed to integrate deeply with the BlueKing ecosystem (PaaS, CMDB, Job, etc.) to form a monitoring closed-loop.
- It targets different monitoring scenarios like host monitoring and service probing.
- It supports custom data reporting via HTTP/SDK and integration with open-source tools like Prometheus Exporters.

The main project directory is `/root/bk-monitor`, and the core Django application code resides in `/root/bk-monitor/bkmonitor`.

### Main Technologies

- **Language:** Python (Django Framework)
- **Build/Dependency Tool:** `uv` (for managing dependencies in groups: default, aidev, test, dev)
- **Frontend Build:** Webpack (managed via `npm`/`pnpm` in `bkmonitor/webpack`)
- **Code Quality:** Ruff (for linting and formatting), pre-commit hooks
- **Testing:** pytest
- **Documentation:** Markdown files in `docs/` and `bkmonitor/docs/`

## Codebase Structure

Based on `docs/overview/code_framework.md` and exploration:

1.  **Root (`/root/bk-monitor/`):**
    - Contains top-level documentation (`README.md`), configuration (`pyproject.toml`, `.pre-commit-config.yaml`), and main directories.
    - `bkmonitor/`: The core Django application.
    - `docs/`: Project-wide documentation.
    - `scripts/`: General scripts.
    - Other directories like `ai_agent/`, `bklog/` for specific components.
2.  **Core Application (`/root/bk-monitor/bkmonitor/`):**
    - `settings.py`, `manage.py`, `urls.py`: Standard Django entry points.
    - `config/`: Environment-specific Django settings (dev, stag, prod) and role-based settings.
    - `web/`: **Note:** This directory was not found, suggesting the structure in `docs/overview/code_framework.md` might be outdated or refers to a different part of the application.
    - `monitor_web/`, `alarm_backends/`, `apm/`, etc.: Specific modules for different functionalities (web UI backend, alerting, application performance monitoring).
    - `core/`: Framework-level utilities.
    - `models/`: Database models.
    - `resource/`: Business logic layer, often interacting with adapters.
    - `adapter/`: Wrappers for external dependencies (e.g., CMDB, Job).
    - `api/`: API service implementations.
    - `static/`, `templates/`: Frontend assets and templates.
    - `tests/`: Unit and integration tests.
    - `webpack/`: Frontend source code and build configuration.
    - `Makefile`: Defines build and packaging commands.

## Building and Running

### Local Development Environment

Based on `/root/bk-monitor/bkmonitor/README.md`:

1.  **Dependency Management (using `uv`):**
    - The project relies on `uv` for fast dependency management.
    - Dependencies are defined in `bkmonitor/pyproject.toml` and grouped (default, aidev, test, dev).
    - Create a virtual environment:
        ```bash
        cd /root/bk-monitor/bkmonitor
        uv venv --seed # Creates .venv
        source .venv/bin/activate # Activate the virtual environment
        ```
    - Install dependencies (e.g., for development and testing):
        ```bash
        uv sync --all-groups # Installs all dependencies
        # Or install specific groups:
        # uv sync # Default group
        # uv sync --group test # Test dependencies
        # uv sync --group dev # Dev dependencies
        ```

2.  **Code Quality (using `ruff` and `pre-commit`):**
    - `ruff` handles linting and formatting. Configuration is in `pyproject.toml`.
    - `pre-commit` hooks (configured in `.pre-commit-config.yaml`) enforce code quality checks (including `ruff`) on commit.
    - Setup pre-commit:
        ```bash
        # After installing dev dependencies
        pre-commit install
        ```

3.  **Running Unit Tests (using `pytest`):**
    - Execute tests:
        ```bash
        # After installing test dependencies
        pytest # Run tests from /root/bk-monitor/bkmonitor
        ```

### Running the Application

- The main entry point is `bkmonitor/manage.py`.
- Standard Django commands apply:
    ```bash
    cd /root/bk-monitor/bkmonitor
    # source .venv/bin/activate # Ensure virtual environment is active
    python manage.py runserver # Starts the development server
    python manage.py migrate # Applies database migrations
    python manage.py collectstatic # Collects static files
    ```

### Building Frontend Assets

The frontend code is in `bkmonitor/webpack/`.

- Install frontend dependencies and build using the Makefile:
    ```bash
    cd /root/bk-monitor/bkmonitor
    make npm-install # Installs dependencies (pnpm/npm)
    make webpack-build # Builds the frontend
    make webpack-copy # Copies built assets to static/
    ```

### Packaging

- Packaging commands are defined in `bkmonitor/Makefile`:
    ```bash
    cd /root/bk-monitor/bkmonitor
    make webpack-package # Packages frontend assets
    make build-clean # (Placeholder) Calls version/pack.sh for full packaging
    ```

## Development Conventions

Inferred from the codebase and configuration files:

- **Python Code Style:**
    - Enforced by `ruff` with a line length of 120 characters (`pyproject.toml`).
    - Uses Black compatibility profile for `isort` (`pyproject.toml`).
    - Specific ignores are defined for `flake8` and `ruff` (`pyproject.toml`).
- **Pre-commit Hooks:** Mandatory use of `pre-commit` to ensure code quality before commits.
- **Testing:** Unit tests are written using `pytest` and located alongside the code in `tests/` directories or files.
- **Configuration:**
    - Django settings are modularized in `bkmonitor/config/`, loaded based on environment (`dev`, `stag`, `prod`) and role.
    - Environment variables prefixed with `BKAPP_SETTINGS_` can override settings at runtime.
    - Local development settings can be placed in `bkmonitor/config/local_settings.py` (ignored by version control).
- **Documentation:** Written in Markdown and located in `docs/` directories.