"""配置验证器

基于 jsonschema 进行 Pipeline 配置的结构验证。
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Pipeline 配置的 JSON Schema
PIPELINE_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "version", "stages"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "name": {"type": "string", "minLength": 1},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "description": {"type": "string"},
        "scenario": {"type": "string", "enum": ["alert", "event", "custom"]},
        "enabled": {"type": "boolean"},
        "stages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "processors"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["sequential", "parallel", "conditional"],
                        "default": "sequential",
                    },
                    "processors": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["id", "type"],
                            "properties": {
                                "id": {"type": "string"},
                                "type": {"type": "string"},
                                "version": {"type": "string"},
                                "config": {"type": "object"},
                                "condition": {"type": "object"},
                                "enabled": {"type": "boolean", "default": True},
                                "error_strategy": {
                                    "type": "string",
                                    "enum": ["ignore", "retry", "stop", "fallback"],
                                    "default": "stop",
                                },
                                "timeout": {"type": "integer", "minimum": 1},
                                "retry": {
                                    "type": "object",
                                    "properties": {
                                        "max_retries": {"type": "integer", "minimum": 1, "maximum": 10},
                                        "interval": {"type": "number", "minimum": 0.1},
                                    },
                                },
                            },
                        },
                    },
                    "enabled": {"type": "boolean", "default": True},
                    "timeout": {"type": "integer", "minimum": 1},
                },
            },
        },
        "global_config": {"type": "object"},
        "error_handling": {
            "type": "object",
            "properties": {
                "default_strategy": {
                    "type": "string",
                    "enum": ["ignore", "retry", "stop", "fallback"],
                },
                "max_retries": {"type": "integer"},
                "retry_interval": {"type": "number"},
            },
        },
    },
}


class ConfigValidator:
    """Pipeline 配置验证器

    支持：
    1. jsonschema 结构验证
    2. 节点引用完整性验证
    3. 处理器类型可用性验证
    """

    def validate(self, config: dict[str, Any]) -> tuple[bool, list[str]]:
        """验证 Pipeline 配置

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # 1. Schema 结构验证
        schema_errors = self._validate_schema(config)
        errors.extend(schema_errors)

        # 结构不合法则跳过后续验证
        if schema_errors:
            return False, errors

        # 2. 节点 ID 唯一性验证
        id_errors = self._validate_unique_ids(config)
        errors.extend(id_errors)

        # 3. 节点类型可用性验证
        type_errors = self._validate_processor_types(config)
        errors.extend(type_errors)

        return len(errors) == 0, errors

    def _validate_schema(self, config: dict[str, Any]) -> list[str]:
        """jsonschema 结构验证"""
        try:
            import jsonschema

            jsonschema.validate(instance=config, schema=PIPELINE_CONFIG_SCHEMA)
            return []
        except jsonschema.ValidationError as e:
            return [f"Schema 验证失败: {e.message} (路径: {'/'.join(str(p) for p in e.absolute_path)})"]
        except ImportError:
            # jsonschema 未安装时进行基础验证
            return self._basic_validate(config)

    def _basic_validate(self, config: dict[str, Any]) -> list[str]:
        """基础验证（不依赖 jsonschema）"""
        errors = []
        for field in ("id", "name", "version", "stages"):
            if field not in config:
                errors.append(f"缺少必要字段: {field}")
        if "stages" in config:
            if not isinstance(config["stages"], list) or len(config["stages"]) == 0:
                errors.append("stages 必须是非空数组")
        return errors

    def _validate_unique_ids(self, config: dict[str, Any]) -> list[str]:
        """验证所有节点 ID 的唯一性"""
        errors = []
        seen_ids = set()
        for stage in config.get("stages", []):
            for proc in stage.get("processors", []):
                proc_id = proc.get("id", "")
                if proc_id in seen_ids:
                    errors.append(f"节点 ID 重复: {proc_id}")
                seen_ids.add(proc_id)
        return errors

    def _validate_processor_types(self, config: dict[str, Any]) -> list[str]:
        """验证处理器类型是否已注册"""
        errors = []
        try:
            from framework.processor.registry import ProcessorRegistry

            registry = ProcessorRegistry()

            for stage in config.get("stages", []):
                for proc in stage.get("processors", []):
                    proc_type = proc.get("type", "")
                    try:
                        registry.get(proc_type, proc.get("version"))
                    except KeyError:
                        errors.append(f"未注册的处理器类型: {proc_type}")
        except ImportError:
            logger.warning("ProcessorRegistry 不可用，跳过处理器类型验证")
        return errors
