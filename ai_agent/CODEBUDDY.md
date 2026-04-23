# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## Project Overview

**bk-monitor** is the BlueKing Monitor platform by Tencent. The `ai_agent/` directory is a shared Python package that provides AI agent integration (LLM access, chat completions, metrics, MCP auth) for the `bkmonitor` and `bklog` Django applications. It is consumed via symlink — not installed as a package.

```bash
# From the repo root, create symlinks:
ln -s "$(pwd)/ai_agent" bkmonitor/ai_agent
ln -s "$(pwd)/ai_agent" bklog/ai_agent
```

## Commands

### Linting & Formatting

```bash
# Lint (from repo root)
ruff check ai_agent/

# Format
ruff format ai_agent/

# Pre-commit (runs ruff + sensitive IP check + commit message check)
pre-commit run --all-files
```

Configuration is in `/root/bk-monitor-learn/pyproject.toml`: line-length=120, target Python 3.10+.

### Testing

There are no dedicated tests for `ai_agent/`. Tests live in the consumer projects:

```bash
# bklog tests (from bklog/ directory)
make unittest    # runs sh ./scripts/unit_test.sh

# CI uses Django test runner:
python manage.py test apps.tests
```

The CI workflow (`.github/workflows/unittest.yml`) runs on Python 3.11.10 and creates the `ai_agent` symlink automatically.

## Architecture

### ai_agent Package Structure

```
ai_agent/
├── utils.py                          # Langfuse callbacks, streaming helpers, get_username()
├── core/
│   ├── aidev_interface.py            # AIDevInterface: main API to BKAidev platform
│   └── custom_config_manager.py      # MCP auth (ieod/open), token caching via Django cache
├── llm/
│   └── __init__.py                   # Multi-provider LLM factory (Zhipu, Hunyuan, DeepSeek, SiliconFlow, BlueKing)
└── services/
    ├── local_command_handler.py      # Decorator-based command registry pattern
    └── metrics_reporter.py           # Prometheus metrics + streaming response tracking
```

### Key Design Patterns

**AIDevInterface** (`core/aidev_interface.py`): Central facade wrapping the BKAidev platform API. Handles agent info, session CRUD, message CRUD, and chat completions (streaming/non-streaming). Uses `AgentInstanceFactory` with `CommonQAAgent` from the `aidev_agent` SDK.

**CustomConfigManager** (`core/custom_config_manager.py`): Extends `AgentConfigManager` from `aidev_agent`. Two auth modes:
- **ieod** (internal): BKOAUTH with `bk_ticket`, 180-day token, refresh when <1 day left
- **open** (external): SSM with `bk_token`, 12-hour token, refresh when <1 hour left
Token caching uses Django's cache framework.

**LocalCommandHandler** (`services/local_command_handler.py`): `@local_command_handler("name")` decorator registers handler classes in `LocalCommandRegistry`. `LocalCommandProcessor` dispatches commands to registered handlers before delegating to the platform.

**MetricsReporter** (`services/metrics_reporter.py`): `AIMetricsReporter` for request counts/latencies with Prometheus labels (agent_code, resource_name, status, username, command). `StreamingMetricsTracker` + `EnhancedStreamingResponseWrapper` wrap Django streaming generators. Use `@ai_metrics_decorator` on Resource methods and `@ai_enhanced_streaming_metrics` for streaming endpoints.

**LLM Module** (`llm/__init__.py`): Returns `ChatOpenAI` (LangChain-compatible) instances. Provider mapping: `zhipu` (GLM-4-Plus/Air), `hunyuan` (hunyuan-turbo), `deepseek` (deepseek-chat), `siliconflow` (DeepSeek-V3), `blueking` (internal gateway).

### External Dependencies

- `aidev_agent`: BKAidev Agent SDK (agent factory, config manager, chat execution)
- `langchain_openai`: LangChain OpenAI integration
- `langfuse`: LLM observability/tracing
- `blueapps`: BlueKing Django app framework (request provider)
- `bkoauth`/`ssm`: BlueKing auth utilities
- `prometheus_client`: Metrics instrumentation
- Django cache & settings

## Code Style

- Follow Google Python Style Guide; PEP 8 enforced via `ruff`
- Docstrings in reStructuredText format (Sphinx-compatible)
- No wildcard imports (`from module import *`)
- Maximum line length: 120 characters
- Target Python: 3.10+ (ruff), 3.11+ (CI)
- Naming: `snake_case` variables/functions, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- Pre-commit hooks check for: ruff lint/format, merge conflicts, private keys, sensitive IPs, commit message format
