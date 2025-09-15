# AI Whale Feature Guide

<cite>
**Referenced Files in This Document**   
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py)
- [apps.py](file://bkmonitor/ai_whale/apps.py)
- [urls.py](file://bkmonitor/ai_whale/urls.py)
- [test_switch_agent_by_command.py](file://bkmonitor/ai_whale/tests/resources/test_switch_agent_by_command.py)
- [test_agent_config.py](file://bkmonitor/ai_whale/tests/test_agent_config.py)
- [__init__.py](file://ai_agent/llm/__init__.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [API Interfaces](#api-interfaces)
7. [Integration Patterns](#integration-patterns)
8. [Configuration and Gray Release](#configuration-and-gray-release)
9. [Session Persistence Behavior](#session-persistence-behavior)
10. [Troubleshooting Guide](#troubleshooting-guide)

## Introduction
The AI Whale feature is an intelligent assistant system integrated within the BlueKing Monitor platform, designed to provide conversational AI capabilities for monitoring and operational tasks. It enables users to interact with monitoring systems through natural language, execute commands, and receive intelligent responses. The system supports local command processing, metrics collection, agent switching based on scenarios or commands, and session management. This documentation provides a comprehensive guide to the AI Whale feature, covering its purpose, implementation details, user interface components, API interfaces, integration patterns, configuration options, and troubleshooting guidance.

## Project Structure
The AI Whale feature is organized within the `bkmonitor` directory of the repository, with core AI agent functionality located in the `ai_agent` module. The structure follows a modular design with clear separation of concerns between core services, local command handling, metrics reporting, and integration with the main application.

``mermaid
graph TD
subgraph "AI Agent Core"
AIDEV[aidev_interface.py]
LLM[llm/__init__.py]
UTILS[utils.py]
end
subgraph "AI Agent Services"
COMMAND[local_command_handler.py]
METRICS[metrics_reporter.py]
end
subgraph "AI Whale Integration"
RESOURCES[ai_whale/resources/resources.py]
VIEWS[ai_whale/views.py]
URLS[ai_whale/urls.py]
APPS[ai_whale/apps.py]
end
AIDEV --> COMMAND
AIDEV --> METRICS
RESOURCES --> AIDEV
VIEWS --> RESOURCES
URLS --> VIEWS
```

**Diagram sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py)
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py)
- [urls.py](file://bkmonitor/ai_whale/urls.py)

**Section sources**
- [ai_agent](file://ai_agent)
- [bkmonitor/ai_whale](file://bkmonitor/ai_whale)

## Core Components
The AI Whale system consists of several core components that work together to provide intelligent assistant capabilities. The main components include the AIDevInterface for external API communication, LocalCommandHandler for processing local commands, MetricsReporter for collecting usage metrics, and the resource layer that exposes these capabilities through REST APIs.

The system follows a layered architecture where higher-level components depend on lower-level services. The AIDevInterface serves as the central coordinator, integrating with both local command processors and external AI services. Metrics collection is implemented through decorators that wrap API endpoints, providing non-intrusive monitoring of system performance and usage patterns.

**Section sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L200)
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py#L0-L100)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L0-L100)

## Architecture Overview
The AI Whale architecture follows a service-oriented design pattern with clear separation between the interface layer, business logic layer, and data access layer. The system integrates with the AIDEV platform for advanced AI capabilities while providing local command processing for immediate responses.

``mermaid
graph TD
Client[Client Application] --> API[REST API Layer]
API --> Resource[Resource Layer]
Resource --> AIDev[AIDevInterface]
subgraph "AI Whale System"
Resource
AIDev
AIDev --> LocalCommand[LocalCommandProcessor]
AIDev --> ExternalAPI[AIDEV Platform API]
AIDev --> Metrics[MetricsReporter]
Metrics --> Prometheus[Prometheus Metrics]
end
style Client fill:#f9f,stroke:#333
style API fill:#bbf,stroke:#333
style Resource fill:#bbf,stroke:#333
style AIDev fill:#f96,stroke:#333
style LocalCommand fill:#6f9,stroke:#333
style ExternalAPI fill:#69f,stroke:#333
style Metrics fill:#96f,stroke:#333
style Prometheus fill:#f66,stroke:#333
```

**Diagram sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L50)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L50)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L0-L50)

## Detailed Component Analysis

### Local Command Handler Analysis
The LocalCommandHandler system provides a registry-based mechanism for processing local commands within the AI Whale feature. It allows for dynamic registration of command handlers through decorators and provides a processor to execute these commands based on incoming requests.

``mermaid
classDiagram
class LocalCommandRegistry {
+_handlers : dict[str, type[CommandHandler]]
+register(command : str, handler_class : type[CommandHandler]) void
+get_handler(command : str) type[CommandHandler] | None
+has_handler(command : str) bool
+list_commands() list
}
class LocalCommandProcessor {
-_handler_instances : dict[str, CommandHandler]
+has_local_handler(command : str) bool
+process_command(command_data : dict) str
}
class CommandHandler {
+command : str
+process_content(context : list[dict]) str
}
LocalCommandRegistry --> CommandHandler : registers
LocalCommandProcessor --> LocalCommandRegistry : uses
LocalCommandProcessor --> CommandHandler : instantiates
```

**Diagram sources**
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py#L0-L100)

**Section sources**
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py#L0-L118)

### Metrics Reporter Analysis
The MetricsReporter component provides comprehensive monitoring capabilities for AI Whale interactions, tracking request metrics, processing times, and streaming response statistics. It uses a decorator pattern to instrument API endpoints and provides specialized handling for streaming responses.

``mermaid
sequenceDiagram
participant Client as "Client"
participant Resource as "Resource"
participant Reporter as "AIMetricsReporter"
participant Tracker as "StreamingMetricsTracker"
Client->>Resource : API Request
Resource->>Reporter : report_request(STARTED)
Resource->>Resource : Execute Business Logic
alt Streaming Response
Resource->>Tracker : Create StreamingMetricsTracker
Resource->>Tracker : on_first_chunk()
Resource->>Tracker : on_chunk_yield() * N
Resource->>Tracker : on_streaming_complete()
Reporter->>Prometheus : Report COMPLETED metrics
else Non-Streaming Response
Resource->>Reporter : report_request(SUCCESS)
end
Reporter->>Prometheus : Report metrics
Resource->>Client : Response
```

**Diagram sources**
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L0-L200)

**Section sources**
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L0-L417)

## API Interfaces
The AI Whale feature exposes its functionality through a set of REST API endpoints that follow Django REST framework patterns. These endpoints are organized around key operations such as session management, content creation, and chat completion.

``mermaid
flowchart TD
A[/chat/] --> B[CreateChatSessionResource]
A --> C[UpdateChatSessionResource]
A --> D[RenameChatSessionResource]
A --> E[CreateChatSessionContentResource]
A --> F[CreateChatCompletionResource]
A --> G[GetAgentInfoResource]
B --> H[Creates new chat session]
C --> I[Updates session properties]
D --> J[Renames session using AI or user input]
E --> K[Adds content to existing session]
F --> L[Creates chat completion with streaming support]
G --> M[Retrieves agent configuration information]
```

**Diagram sources**
- [urls.py](file://bkmonitor/ai_whale/urls.py#L0-L19)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L300)

**Section sources**
- [urls.py](file://bkmonitor/ai_whale/urls.py#L0-L19)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L300)

## Integration Patterns
The AI Whale system employs several integration patterns to connect with external services and internal components. The primary integration is with the AIDEV platform for advanced AI capabilities, while also providing local command processing for immediate responses.

The system uses a factory pattern through the AgentInstanceFactory to create agent instances based on different configurations. It also implements a strategy pattern for agent switching, allowing different mechanisms (scene-based or command-based) to determine which agent should handle a request.

``mermaid
graph TD
A[Client Request] --> B{Streaming?}
B --> |Yes| C[EnhancedStreamingResponseWrapper]
B --> |No| D[Direct Response]
C --> E[StreamingMetricsTracker]
E --> F[AIMetricsReporter]
F --> G[Prometheus]
A --> H[ai_enhanced_streaming_metrics]
H --> I[AIDevInterface]
I --> J{Agent Switch Needed?}
J --> |Yes| K[Switch Agent]
J --> |No| L[Use Default Agent]
I --> M[External AIDEV API]
I --> N[Local Command Processor]
```

**Diagram sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L200)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L200-L417)
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L300)

**Section sources**
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L200)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L200-L417)

## Configuration and Gray Release
The AI Whale feature supports several configuration options that enable gray release strategies and flexible behavior customization. These configurations are primarily managed through Django settings and can be modified without code changes.

### Configuration Settings
The system utilizes the following key configuration settings:

**:AIDEV_AGENT_APP_CODE**
- Default: Value from Django settings
- Purpose: Specifies the default agent code to use when none is provided
- Used in: Session creation, agent information retrieval

**:AIDEV_AGENT_APP_SECRET**
- Default: Value from Django settings
- Purpose: Authentication secret for the AIDEV platform API
- Used in: AIDevInterface initialization

**:AIDEV_AGENT_LLM_DEFAULT_TEMPERATURE**
- Default: Not explicitly defined (falls back to LLMConfig default of 0)
- Purpose: Controls the randomness of LLM responses
- Range: 0 (deterministic) to 1 (creative)
- Used in: Chat completion requests

**:ENABLE_AI_RENAME**
- Default: Not explicitly defined in code
- Purpose: Determines whether to use AI-powered session renaming or user question-based renaming
- When True: Uses AI to summarize and rename sessions
- When False: Uses the first user question as the session title
- Used in: RenameChatSessionResource

**:AIDEV_SCENE_AGENT_CODE_MAPPING**
- Default: Not defined (empty mapping)
- Purpose: Maps specific scenarios to dedicated agent codes
- Format: Dictionary mapping scenario identifiers to agent codes
- Used in: get_agent_code_by_scenario_route function

**:AIDEV_COMMAND_AGENT_MAPPING**
- Default: Not defined (empty mapping)
- Purpose: Maps specific commands to dedicated agent codes
- Format: Dictionary mapping command names to agent codes
- Used in: Command-based agent switching

### Gray Release Implementation
The system supports gray release through several mechanisms:

1. **Feature Toggle**: The `ENABLE_AI_RENAME` setting acts as a feature toggle for AI-powered session renaming.
2. **Agent Routing**: The scene and command-based agent mappings allow for gradual rollout of specialized agents.
3. **Default Fallback**: When no specific agent is configured for a scenario or command, the system falls back to the default agent.

``mermaid
flowchart TD
A[Incoming Request] --> B{Has Command?}
B --> |Yes| C{Command in AIDEV_COMMAND_AGENT_MAPPING?}
C --> |Yes| D[Route to Mapped Agent]
C --> |No| E{Has Scenario?}
E --> |Yes| F{Scenario in AIDEV_SCENE_AGENT_CODE_MAPPING?}
F --> |Yes| G[Route to Mapped Agent]
F --> |No| H[Use Default Agent]
E --> |No| H
B --> |No| E
H --> I[Process Request]
```

**Section sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L268-L297)
- [test_switch_agent_by_command.py](file://bkmonitor/ai_whale/tests/resources/test_switch_agent_by_command.py#L26-L69)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L191-L213)

## Session Persistence Behavior
The AI Whale system implements session persistence through the AIDEV platform's chat session management capabilities. Sessions are identified by unique session codes and maintain their state across interactions.

### Session Lifecycle
1. **Creation**: Sessions are created through the CreateChatSessionResource, which generates a unique session code and initializes the session state.
2. **Content Management**: Session content is managed through the CreateChatSessionContentResource, which adds messages to the session context.
3. **Interaction**: Chat completions are generated through the CreateChatCompletionResource, which processes the entire session context to generate responses.
4. **Renaming**: Sessions can be renamed either through AI summarization or by using the first user question.
5. **Update**: Session properties can be modified through the UpdateChatSessionResource.
6. **Termination**: Sessions can be destroyed when no longer needed.

### Session Data Flow
``mermaid
sequenceDiagram
participant User as "User"
participant Frontend as "Frontend"
participant Backend as "Backend"
participant AIDEV as "AIDEV Platform"
User->>Frontend : Start New Chat
Frontend->>Backend : Create Session Request
Backend->>AIDEV : create_chat_session API Call
AIDEV-->>Backend : Session Created Response
Backend-->>Frontend : Session Code
Frontend-->>User : Chat Interface
User->>Frontend : Send Message
Frontend->>Backend : Add Content Request
Backend->>AIDEV : create_chat_session_content API Call
AIDEV-->>Backend : Content Added Response
Backend-->>Frontend : Confirmation
Frontend->>Backend : Chat Completion Request
Backend->>AIDEV : get_chat_session_context API Call
AIDEV-->>Backend : Full Session Context
Backend->>AIDEV : create_chat_completion API Call
AIDEV-->>Backend : Streaming Response
Backend-->>Frontend : Stream Response
Frontend-->>User : Display Response
```

**Section sources**
- [resources.py](file://bkmonitor/ai_whale/resources/resources.py#L0-L300)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L49-L77)

## Troubleshooting Guide
This section provides guidance for diagnosing and resolving common issues with the AI Whale feature.

### Common Issues and Solutions

**:No local handler found for command**
- **Symptoms**: Error message "No local handler found for command: {command}"
- **Causes**: 
  - Command handler not registered with @local_command_handler decorator
  - Typo in command name
  - Module containing handler not imported
- **Solutions**:
  - Ensure the command handler class is decorated with @local_command_handler("command_name")
  - Verify the command name matches exactly
  - Check that the module is imported in the application startup

**:Failed to process command**
- **Symptoms**: Error message "Failed to process command {command}"
- **Causes**:
  - Exception in the process_content method
  - Invalid context data structure
  - External service failure
- **Solutions**:
  - Check application logs for detailed error information
  - Validate the context data structure matches expectations
  - Implement proper error handling in the command handler

**:Streaming response setup timeout**
- **Symptoms**: Long delay before streaming response begins
- **Causes**:
  - High latency to AIDEV platform
  - Complex prompt processing
  - Resource constraints
- **Solutions**:
  - Monitor the setup_duration metric in Prometheus
  - Optimize agent configuration
  - Check network connectivity to AIDEV platform

**:Agent switching not working**
- **Symptoms**: Requests are not routed to expected agents
- **Causes**:
  - Incorrect configuration in AIDEV_COMMAND_AGENT_MAPPING or AIDEV_SCENE_AGENT_CODE_MAPPING
  - Missing switch_agent_by_scene parameter
  - Cache issues
- **Solutions**:
  - Verify mapping configurations are correct
  - Ensure switch_agent_by_scene flag is set when needed
  - Restart application to clear any cached configurations

### Diagnostic Commands
The following commands can be used to diagnose AI Whale issues:

**:List all registered commands**
```python
from ai_agent.services.local_command_handler import LocalCommandRegistry
print(LocalCommandRegistry.list_commands())
```

**:Check agent configuration**
```python
from aidev_agent.api import BKAidevApi
client = BKAidevApi.get_client()
config = client.api.retrieve_agent_config(path_params={"agent_code": "your-agent-code"})
print(config)
```

**:Test metrics reporting**
```python
from ai_agent.services.metrics_reporter import AIMetricsReporter
from django.conf import settings

# Assuming metrics are available
reporter = AIMetricsReporter(requests_total=your_counter, requests_cost=your_histogram)
reporter.report_request(
    resource_name="TestResource",
    status="success",
    duration=0.1,
    agent_code=settings.AIDEV_AGENT_APP_CODE
)
```

**Section sources**
- [local_command_handler.py](file://ai_agent/services/local_command_handler.py#L100-L118)
- [metrics_reporter.py](file://ai_agent/services/metrics_reporter.py#L0-L100)
- [aidev_interface.py](file://ai_agent/core/aidev_interface.py#L0-L50)
- [test_agent_config.py](file://bkmonitor/ai_whale/tests/test_agent_config.py#L0-L28)
- [test_switch_agent_by_command.py](file://bkmonitor/ai_whale/tests/resources/test_switch_agent_by_command.py#L0-L30)