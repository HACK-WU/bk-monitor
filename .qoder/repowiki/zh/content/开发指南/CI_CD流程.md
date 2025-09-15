# CI/CD Process

<cite>
**Referenced Files in This Document**   
- [pytest.yml](file://bkmonitor\.github\workflows\pytest.yml)
- [release.sh](file://bkmonitor\bin\release.sh)
- [constants.py](file://bkmonitor\as_code\constants.py)
- [plugin.py](file://bkmonitor\packages\monitor_web\models\plugin.py)
- [base.py](file://bkmonitor\packages\monitor_web\plugin\manager\base.py)
- [pack.sh](file://bkmonitor\version\pack.sh)
- [unittest.yml](file://ai_agent\.github\workflows\unittest.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*
- [codecov.yml](file://ai_agent\.github\workflows\codecov.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*
- [aidev_interface.py](file://ai_agent\core\aidev_interface.py) - *AI agent core interface*
- [metrics_reporter.py](file://ai_agent\services\metrics_reporter.py) - *AI agent metrics reporting*
- [parse_test_output.py](file://bkmonitor\scripts\unittest\parse_test_output.py) - *Test output parsing utility*
</cite>

## Update Summary
**Changes Made**   
- Added new section on AI Agent CI/CD workflows for unittest and code coverage
- Updated CI/CD process overview to include AI agent testing
- Added new workflow diagrams for AI agent testing and coverage reporting
- Updated referenced files list to include new workflow configuration files
- Enhanced fault diagnosis section with AI agent-specific failure scenarios

## Table of Contents
1. [CI/CD Process Overview](#cicd-process-overview)
2. [GitHub Actions Workflow Configuration](#github-actions-workflow-configuration)
3. [Version Release Process](#version-release-process)
4. [Automated Script Usage](#automated-script-usage)
5. [Fault Diagnosis Guide](#fault-diagnosis-guide)

## CI/CD Process Overview

This project uses GitHub Actions as its CI/CD tool, implementing automated testing, code quality checks, building, and deployment processes. When code is pushed to the master branch or a pull request targeting the master branch is created, the CI/CD process is automatically triggered. The process includes environment preparation, dependency installation, database migration, and automated testing to ensure code quality and system stability.

The system has been enhanced with dedicated CI/CD workflows for AI agent development, including unit testing and code coverage reporting specific to the AI agent components.

**Section sources**
- [pytest.yml](file://bkmonitor\.github\workflows\pytest.yml)
- [unittest.yml](file://ai_agent\.github\workflows\unittest.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*
- [codecov.yml](file://ai_agent\.github\workflows\codecov.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*

## GitHub Actions Workflow Configuration

### Workflow Trigger Conditions

GitHub Actions workflow configuration file `pytest.yml` defines the trigger conditions and execution logic for the CI/CD process. This workflow is triggered under two conditions:
- When code is pushed to the master branch
- When a pull request targeting the master branch is created

``mermaid
flowchart TD
A["Code Commit/PR Creation"] --> B{Branch is<br/>master?}
B --> |Yes| C["Trigger CI/CD Process"]
B --> |No| D["No Trigger"]
```

**Diagram sources**
- [pytest.yml](file://bkmonitor\.github\workflows\pytest.yml#L4-L10)

### Workflow Execution Logic

The CI/CD workflow runs in a self-hosted environment using Python 3.6. The workflow contains multiple steps, each executing a specific task:

``mermaid
flowchart TD
A["Set Timezone"] --> B["Checkout Code"]
B --> C["Setup Python Environment"]
C --> D["Initialize MySQL"]
D --> E["Configure MySQL"]
E --> F["Install Dependencies"]
F --> G["Database Migration"]
G --> H["Run pytest Tests"]
```

**Diagram sources**
- [pytest.yml](file://bkmonitor\.github\workflows\pytest.yml#L12-L68)

#### Detailed Execution Steps

1. **Set Timezone**: Configure the workflow execution environment timezone to Asia/Shanghai
2. **Checkout Code**: Use actions/checkout@v2 action to checkout repository code
3. **Setup Python Environment**: Use actions/setup-python@v2 action to set up Python 3.6 environment
4. **Initialize MySQL**: Create MySQL runtime directory and start MySQL service
5. **Configure MySQL**: Create development databases saas_dev and backend_dev, and set root user permissions
6. **Install Dependencies**: Upgrade pip, merge requirements.txt and requirements_test.txt files, and install all dependency packages
7. **Database Migration**: Execute Django database migration command to create necessary database table structures
8. **Run Tests**: Use pytest framework to run unit tests for alarm_backends and query_api modules, and generate code coverage reports

**Section sources**
- [pytest.yml](file://bkmonitor\.github\workflows\pytest.yml#L12-L68)

### AI Agent Testing Workflows

New workflows have been added specifically for AI agent development and testing:

#### Unit Testing Workflow

The `unittest.yml` workflow is dedicated to testing the AI agent components. It runs tests for the ai_agent module and its integration with the main application.

``mermaid
flowchart TD
A["AI Agent Unit Test Workflow"] --> B["Checkout Code"]
B --> C["Setup Python Environment"]
C --> D["Install Dependencies"]
D --> E["Run AI Agent Tests"]
E --> F["Parse Test Results"]
F --> G["Report Test Outcomes"]
```

**Diagram sources**
- [unittest.yml](file://ai_agent\.github\workflows\unittest.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*
- [aidev_interface.py](file://ai_agent\core\aidev_interface.py#L1-L24)
- [test_agent_config.py](file://bkmonitor\ai_whale\tests\test_agent_config.py#L1-L28)

#### Code Coverage Workflow

The `codecov.yml` workflow handles code coverage reporting for AI agent development, integrating with the coverage.py tool to measure test coverage.

``mermaid
flowchart TD
A["Code Coverage Workflow"] --> B["Checkout Code"]
B --> C["Setup Python Environment"]
C --> D["Install Dependencies"]
D --> E["Run Coverage Tests"]
E --> F["Generate Coverage Report"]
F --> G["Upload to Codecov"]
```

**Diagram sources**
- [codecov.yml](file://ai_agent\.github\workflows\codecov.yml) - *Added in commit 36a5d5fe1872c9f4f2c91d26f0ccd02eae50db1d*
- [parse_test_output.py](file://bkmonitor\scripts\unittest\parse_test_output.py#L0-L84)
- [metrics_reporter.py](file://ai_agent\services\metrics_reporter.py#L393-L416)

## Version Release Process

### Version Number Management

The project uses a dual version number management mechanism, including configuration version number (config_version) and information version number (info_version). Version number management is primarily implemented through the `PluginVersionHistory` model, with different version states including RELEASE (released), DEBUG (debug), and UNREGISTER (unregistered).

``mermaid
classDiagram
class PluginVersionHistory {
+int config_version
+int info_version
+str stage
+bool is_packaged
+str version_log
+save()
}
class Plugin {
+get_version(config_version, info_version)
+get_release_ver_by_config_ver(config_version)
+get_debug_version(config_version)
+rollback_version_status(config_version)
+current_version
+release_version
}
Plugin --> PluginVersionHistory : "Has multiple"
```

**Diagram sources**
- [plugin.py](file://bkmonitor\packages\monitor_web\models\plugin.py#L134-L226)

#### Version Retrieval Methods

- `get_version(config_version, info_version)`: Retrieve a specific version based on the specified configuration version number and information version number
- `get_release_ver_by_config_ver(config_version)`: Retrieve the latest released version based on the configuration version number
- `get_debug_version(config_version)`: Retrieve the debug version or release version for the specified configuration version number
- `current_version`: Property to retrieve the current version (prioritizes release version, returns latest draft if none)

**Section sources**
- [plugin.py](file://bkmonitor\packages\monitor_web\models\plugin.py#L192-L226)

### Release Branch Creation

The project does not use the traditional release branch model but instead implements the release process through version state management. When a new version needs to be released, the system creates a new version record and sets its state to RELEASE. This approach avoids the complexity of creating and maintaining independent release branches, simplifying the release process.

``mermaid
flowchart TD
A["Create New Version"] --> B["Set Version State to RELEASE"]
B --> C["Update Version Number"]
C --> D["Save Version Record"]
D --> E["Release Complete"]
```

**Diagram sources**
- [k8s.py](file://bkmonitor\packages\monitor_web\plugin\manager\k8s.py#L43-L74)

### Release Package Generation

The release package generation process is primarily coordinated by the `release.sh` script and related Python code. The release package contains application code, configuration files, and dependencies, managed by Supervisor for process control.

#### Release Package Build Process

1. Adjust file locations, moving API documentation to the kernel_api directory
2. Select the appropriate Supervisor configuration file based on the release environment (community/enterprise edition)
3. Render package configuration files, injecting version numbers and environment information
4. Remove unnecessary files such as tests and documentation
5. Generate the final release package

``mermaid
flowchart TD
A["Start Build"] --> B["Adjust File Locations"]
B --> C["Select Supervisor Configuration"]
C --> D["Render Configuration Files"]
D --> E["Remove Unnecessary Files"]
E --> F["Generate Release Package"]
F --> G["Build Complete"]
```

**Diagram sources**
- [pack.sh](file://bkmonitor\version\pack.sh#L0-L84)

## Automated Script Usage

### release.sh Script

The `release.sh` script is the core automation script for version release, responsible for switching deployment modes and reloading Supervisor configuration.

#### Script Functionality

- Switch deployment mode (lite or stable)
- Update Supervisor configuration files
- Reload Supervisor configuration to apply changes

#### Usage

```bash
#!/bin/bash
# Switch to stable mode (default)
./bin/release.sh

# Switch to lite mode
./bin/release.sh lite
```

#### Script Logic

``mermaid
flowchart TD
A["Execute release.sh"] --> B{"Parameter is lite?"}
B --> |Yes| C["Use lite configuration file"]
B --> |No| D["Use stable configuration file"]
C --> E["Update Supervisor Configuration"]
D --> E
E --> F["Reload Supervisor"]
F --> G["Output Switch Information"]
```

**Diagram sources**
- [release.sh](file://bkmonitor\bin\release.sh#L0-L18)

#### Parameter Description

- No parameter: Switch to stable mode
- lite: Switch to lite mode (lightweight deployment)

**Section sources**
- [release.sh](file://bkmonitor\bin\release.sh#L0-L18)

## Fault Diagnosis Guide

### CI Failure Common Causes

#### Database Configuration Issues

MySQL initialization and configuration in the CI process are common failure points. Possible causes include:
- MySQL service failed to start properly
- Database permission configuration errors
- Database migration command execution failure

Solutions:
1. Check MySQL service status
2. Verify database user permission settings
3. Confirm correctness of database migration scripts

#### Dependency Installation Issues

Dependency package installation failure can prevent subsequent steps from executing. Common causes:
- Network connectivity issues causing package download failure
- Dependency version conflicts
- Private package repository access permission issues

Solutions:
1. Check network connectivity
2. Verify integrity of requirements files
3. Confirm access credentials for private package repositories

#### Test Failures

Unit test failure is the most common issue in CI processes. Possible causes:
- Code logic errors
- Outdated test cases
- Behavior inconsistencies due to environment differences

Solutions:
1. Review detailed test output logs
2. Reproduce the issue in a local environment
3. Fix code or update test cases

#### AI Agent Testing Failures

Specific to the new AI agent workflows, additional failure points include:
- AI agent interface integration issues
- Metrics reporting configuration problems
- LLM service connectivity issues

Solutions:
1. Verify AI agent interface implementation
2. Check metrics reporter configuration
3. Test LLM service connectivity

**Section sources**
- [aidev_interface.py](file://ai_agent\core\aidev_interface.py#L191-L213)
- [metrics_reporter.py](file://ai_agent\services\metrics_reporter.py#L393-L416)
- [parse_test_output.py](file://bkmonitor\scripts\unittest\parse_test_output.py#L0-L84)

### CI/CD Process Monitoring

The project monitors CI/CD process status through event handlers, primarily focusing on the following states:

``mermaid
stateDiagram-v2
[*] --> Queued
Queued --> Running : Start Execution
Running --> Success : Complete
Running --> Failure : Error
Running --> Terminated : Manual Stop
Running --> Timeout : Queue Timeout
Success --> [*]
Failure --> [*]
Terminated --> [*]
Timeout --> [*]
```

**Diagram sources**
- [constants.py](file://bkmonitor\packages\monitor_web\data_explorer\event\constants.py#L608-L650)

#### Status Code Description

- **QUEUE**: Task waiting in queue for execution
- **RUNNING**: Task currently running
- **SUCCEED**: Task completed successfully
- **FAILED**: Task execution failed
- **TERMINATE**: Task manually terminated
- **QUEUE_TIMEOUT**: Queue timeout

### Exception Handling Mechanism

When a release process encounters an exception, the system performs a rollback operation to ensure consistency of system state:

``mermaid
flowchart TD
A["Release Start"] --> B["Execute Release Operations"]
B --> C{"Success?"}
C --> |Yes| D["Complete Release"]
C --> |No| E["Record Error Log"]
E --> F["Execute Version Status Rollback"]
F --> G["Throw Exception"]
```

**Diagram sources**
- [base.py](file://bkmonitor\packages\monitor_web\plugin\manager\base.py#L983-L1013)

#### Rollback Logic

When a release fails, the system calls the `rollback_version_status` method to update the version state from RELEASE to UNREGISTER, preventing the system from using incomplete or erroneous version configurations.

**Section sources**
- [base.py](file://bkmonitor\packages\monitor_web\plugin\manager\base.py#L983-L1013)