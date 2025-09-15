# AI Agent Configuration Management

<cite>
**Referenced Files in This Document**   
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L298)
- [settings.py](file://bkmonitor/settings.py#L0-L72)
- [test_agent_config.py](file://bkmonitor/ai_whale/tests/test_agent_config.py#L0-L28)
- [apps.py](file://bkmonitor/ai_whale/apps.py#L0-L5)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Configuration Architecture](#configuration-architecture)
3. [Core Configuration Components](#core-configuration-components)
4. [Environment Variables and Settings](#environment-variables-and-settings)
5. [Agent Configuration Management](#agent-configuration-management)
6. [Feature Toggles and Gray Release](#feature-toggles-and-gray-release)
7. [Configuration Examples](#configuration-examples)
8. [Troubleshooting Guide](#troubleshooting-guide)

## Introduction
This document provides comprehensive documentation for the AI Agent configuration management system within the BlueKing Monitor platform. The system enables flexible configuration of AI agents, including environment variables, feature toggles, and gray release settings. The documentation covers all configuration options, recommended settings for different deployment scenarios, and troubleshooting guidance for configuration-related issues.

**Section sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L298)

## Configuration Architecture
The AI Agent configuration management system follows a layered architecture that integrates with the BlueKing platform's configuration framework. The system uses Django settings as the primary configuration source, supplemented by environment variables and API-based configuration retrieval.

``mermaid
graph TD
A["Environment Variables<br/>BKAPP_SETTINGS_*"] --> B["settings.py"]
C["config/{env}.py"] --> B
D["config/role/{role}.py"] --> B
B --> E["AIDevInterface"]
F["AIDEV Platform API"] --> E
E --> G["AI Agent Services"]
H["Local Command Handlers"] --> G
I["Metrics Reporter"] --> G
```

**Diagram sources**
- [settings.py](file://bkmonitor/settings.py#L0-L72)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)

**Section sources**
- [settings.py](file://bkmonitor/settings.py#L0-L72)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)

## Core Configuration Components

### AIDevInterface Class
The `AIDevInterface` class serves as the central configuration and integration point for AI Agent functionality. It manages connections to the AIDEV platform and provides methods for agent configuration retrieval and session management.

``mermaid
classDiagram
class AIDevInterface {
+app_code : str
+app_secret : str
+metrics_reporter : AIMetricsReporter
+api_client : BKAidevApi
+local_command_processor : LocalCommandProcessor
+__init__(app_code, app_secret, metrics_reporter)
+get_agent_info(agent_code) dict
+create_chat_session(params, username) dict
+retrieve_chat_session(session_code) dict
+list_chat_sessions(username) dict
+destroy_chat_session(session_code) dict
+update_chat_session(session_code, params) dict
+rename_chat_session(session_code) dict
+rename_chat_session_by_user_question(session_code) dict
+create_chat_session_content(params) dict
+get_chat_session_contents(session_code) dict
+destroy_chat_session_content(id) dict
+batch_delete_session_contents(params) dict
+update_chat_session_content(params) dict
+create_chat_completion(session_code, execute_kwargs, agent_code, username, temperature, switch_agent_by_scene) dict
}
class BKAidevApi {
+get_client(app_code, app_secret) BKAidevApi
}
class LocalCommandProcessor {
+has_local_handler(command) bool
+process_command(command_data) str
}
class AIMetricsReporter {
+requests_total : Counter
+requests_cost : Histogram
}
AIDevInterface --> BKAidevApi : "uses"
AIDevInterface --> LocalCommandProcessor : "uses"
AIDevInterface --> AIMetricsReporter : "uses"
```

**Diagram sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)

**Section sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)

## Environment Variables and Settings
The configuration system supports multiple sources for settings, with environment variables taking precedence. The settings are loaded in a specific order to allow for environment-specific and role-specific configurations.

### Settings Loading Order
1. `config.default` - Default configuration
2. `blueapps.patch` - Platform patches
3. `config.{env}` - Environment-specific configuration (dev, stag, prod)
4. `config.role.{role}` - Role-specific configuration

### Key Configuration Variables
**AIDEV Agent Configuration**
- `AIDEV_AGENT_APP_CODE`: Application code for AIDEV platform authentication
- `AIDEV_AGENT_APP_SECRET`: Application secret for AIDEV platform authentication
- `AIDEV_AGENT_LLM_DEFAULT_TEMPERATURE`: Default temperature setting for LLM responses
- `ENABLE_AI_RENAME`: Feature toggle for AI-powered session renaming

**System Configuration**
- `RUN_MODE`: Application runtime mode (DEVELOP, TESTING, PRODUCTION)
- `ENVIRONMENT`: Environment type (development, testing, production)
- `ROLE`: Server role (e.g., backend, frontend, worker)

``mermaid
flowchart TD
A["Environment Variables<br/>BKAPP_SETTINGS_*"] --> B["Parse Settings"]
C["config.default"] --> B
B --> D["config.{env}"]
D --> E["config.role.{role}"]
E --> F["Final Settings"]
G["Local Settings<br/>(local_settings.py)"] --> F
F --> H["Initialize<br/>AIDevInterface"]
H --> I["AI Agent Services"]
```

**Diagram sources**
- [settings.py](file://bkmonitor/settings.py#L0-L72)

**Section sources**
- [settings.py](file://bkmonitor/settings.py#L0-L72)

## Agent Configuration Management
The system provides a comprehensive API for managing AI Agent configurations, allowing for dynamic agent selection based on scenarios and user contexts.

### Agent Configuration Retrieval
The `get_agent_info` method retrieves agent configuration from the AIDEV platform, with automatic filtering of sensitive prompt settings:

```python
def get_agent_info(self, agent_code):
    """Retrieve agent configuration information; remove data['prompt_setting'] field"""
    res = self.api_client.api.retrieve_agent_config(path_params={"agent_code": agent_code})
    try:
        data = res.get("data", {}) if isinstance(res, dict) else None
        if isinstance(data, dict) and "prompt_setting" in data:
            # TODO: Remove after AIDEV platform enhancement to avoid prompt leakage
            del data["prompt_setting"]
    except Exception as e:
        logger.warning("get_agent_info: failed to strip prompt_setting: %s", e)
    return res
```

### Agent Switching Logic
The system supports automatic agent switching based on the request scenario, enabling context-aware AI interactions:

``mermaid
sequenceDiagram
participant Client as "Client Application"
participant Resource as "CreateChatCompletionResource"
participant Interface as "AIDevInterface"
participant Platform as "AIDEV Platform"
Client->>Resource : POST /api/chat/completion
Resource->>Resource : get_agent_code_by_scenario_route()
Resource->>Resource : Compare with default agent code
alt Agent Switch Required
Resource->>Resource : Set switch_agent_by_scene = True
Resource->>Interface : create_chat_completion(...)
Interface->>Platform : build_agent(agent_code, switch_agent_by_scene=True)
Platform-->>Interface : AgentInstance
Interface-->>Resource : Response
else No Switch Needed
Resource->>Interface : create_chat_completion(...)
Interface->>Platform : build_agent(default_agent_code)
Platform-->>Interface : AgentInstance
Interface-->>Resource : Response
end
Resource-->>Client : Chat Response
```

**Diagram sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L236-L297)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L191-L213)

**Section sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L236-L297)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L191-L213)

## Feature Toggles and Gray Release
The system implements feature toggles and supports gray release strategies through configuration settings and conditional logic.

### Feature Toggle Implementation
The `ENABLE_AI_RENAME` setting controls whether AI-powered session renaming is enabled:

```python
class RenameChatSessionResource(Resource):
    @ai_metrics_decorator(ai_metrics_reporter=metrics_reporter)
    def perform_request(self, validated_request_data):
        session_code = validated_request_data.get("session_code")
        logger.info("RenameChatSessionResource: try to rename session->[%s]", session_code)

        if settings.ENABLE_AI_RENAME:
            return aidev_interface.rename_chat_session(session_code=session_code)
        else:
            return aidev_interface.rename_chat_session_by_user_question(session_code=session_code)
```

### Gray Release Strategy
The system supports gradual feature rollout through configuration-based routing:

``mermaid
flowchart TD
A["Incoming Request"] --> B{"Feature Flag<br/>ENABLE_AI_RENAME"}
B --> |True| C["Use AI-powered<br/>Session Renaming"]
B --> |False| D["Use User Question<br/>as Session Title"]
C --> E["Enhanced User Experience"]
D --> F["Basic Functionality"]
E --> G["Monitor Performance<br/>and User Feedback"]
F --> G
G --> H{"Evaluate Metrics<br/>and Feedback"}
H --> |Positive| I["Enable for<br/>All Users"]
H --> |Negative| J["Fix Issues<br/>and Iterate"]
I --> K["Update<br/>ENABLE_AI_RENAME=True"]
J --> L["Improve Feature"]
```

**Diagram sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L236-L297)

**Section sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L236-L297)

## Configuration Examples

### Development Environment Configuration (config/dev.py)
```python
# AIDEV Agent Configuration
AIDEV_AGENT_APP_CODE = "aidev-dev"
AIDEV_AGENT_APP_SECRET = "dev-secret-key-12345"
AIDEV_AGENT_LLM_DEFAULT_TEMPERATURE = 0.7
ENABLE_AI_RENAME = False

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'bk_monitor_dev',
        'USER': 'root',
        'PASSWORD': '',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}

# Debug Settings
DEBUG = True
RUN_MODE = "DEVELOP"
```

### Production Environment Configuration (config/prod.py)
```python
# AIDEV Agent Configuration
AIDEV_AGENT_APP_CODE = "aidev-prod"
AIDEV_AGENT_APP_SECRET = os.getenv("AIDEV_AGENT_APP_SECRET")
AIDEV_AGENT_LLM_DEFAULT_TEMPERATURE = 0.3
ENABLE_AI_RENAME = True

# Database Configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'bk_monitor_prod',
        'USER': 'monitor_user',
        'PASSWORD': os.getenv("DB_PASSWORD"),
        'HOST': os.getenv("DB_HOST", "db.prod.example.com"),
        'PORT': '3306',
    }
}

# Security Settings
DEBUG = False
RUN_MODE = "PRODUCTION"
SECURE_SSL_REDIRECT = True
```

### Role-Specific Configuration (config/role/backend.py)
```python
# Backend-specific settings
CELERY_BROKER_URL = "redis://redis-backend:6379/0"
CELERY_RESULT_BACKEND = "redis://redis-backend:6379/1"

# API Rate Limiting
API_RATE_LIMIT = "1000/hour"

# Monitoring Settings
MONITORING_ENABLED = True
METRICS_EXPORT_PORT = 9091

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis-backend:6379/2',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

**Section sources**
- [settings.py](file://bkmonitor/settings.py#L0-L72)

## Troubleshooting Guide

### Common Configuration Issues

**Issue 1: Agent Authentication Failure**
- **Symptoms**: 401 Unauthorized errors when accessing AIDEV platform
- **Causes**: 
  - Incorrect `AIDEV_AGENT_APP_CODE` or `AIDEV_AGENT_APP_SECRET`
  - Environment variables not properly set
  - Secret stored in plain text in configuration files
- **Solutions**:
  - Verify credentials with the AIDEV platform administrator
  - Use environment variables for secrets in production
  - Check settings loading order and precedence

**Issue 2: Feature Toggle Not Working**
- **Symptoms**: Expected feature behavior not appearing despite configuration
- **Causes**:
  - Settings not reloaded after configuration change
  - Caching of configuration values
  - Incorrect settings file being loaded
- **Solutions**:
  - Restart application to reload settings
  - Verify the correct environment and role configuration files are being used
  - Check for typos in setting names

**Issue 3: Agent Switching Not Functioning**
- **Symptoms**: Always using default agent regardless of scenario
- **Causes**:
  - `get_agent_code_by_scenario_route()` not implemented correctly
  - Default agent code incorrectly set
  - Logic error in agent switching condition
- **Solutions**:
  - Verify the scenario routing logic
  - Check logging to confirm agent code determination
  - Test with explicit agent code parameter

### Diagnostic Commands
```bash
# Check current environment settings
python manage.py shell -c "from django.conf import settings; print(settings.AIDEV_AGENT_APP_CODE)"

# Verify settings loading order
python manage.py shell -c "import os; print([k for k in os.environ.keys() if k.startswith('BKAPP_SETTINGS')])"

# Test agent configuration retrieval
python manage.py shell -c "
from ai_agent.core.aidev_interface import AIDevInterface
from django.conf import settings
interface = AIDevInterface(settings.AIDEV_AGENT_APP_CODE, settings.AIDEV_AGENT_APP_SECRET)
print(interface.get_agent_info('aidev-metadata'))
"
```

**Section sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L214)
- [settings.py](file://bkmonitor/settings.py#L0-L72)