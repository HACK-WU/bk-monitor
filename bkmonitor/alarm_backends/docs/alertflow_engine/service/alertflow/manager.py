"""Pipeline 管理服务封装"""

import logging
from typing import Any

from framework.config.manager import ConfigManager
from framework.pipeline.context import ProcessContext
from framework.pipeline.orchestrator import PipelineOrchestrator
from framework.observability.manager import ObservabilityManager
from framework.processor.registry import ProcessorRegistry

logger = logging.getLogger(__name__)


class PipelineService:
    """Pipeline CRUD 和执行管理

    封装 ConfigManager 和 PipelineOrchestrator，为 API 视图层提供统一接口。
    """

    def __init__(self):
        self._config_manager = ConfigManager()
        self._orchestrator = PipelineOrchestrator()
        self._observability = ObservabilityManager()

    def create_pipeline(self, config: dict[str, Any], created_by: str = "") -> dict[str, Any]:
        """创建 Pipeline"""
        pipeline = self._config_manager.create(config, created_by=created_by)
        return {
            "pipeline_id": pipeline.pipeline_id,
            "name": pipeline.name,
            "version": pipeline.version,
        }

    def update_pipeline(
        self,
        pipeline_id: str,
        config: dict[str, Any],
        change_reason: str = "",
        updated_by: str = "",
    ) -> dict[str, Any]:
        """更新 Pipeline"""
        pipeline = self._config_manager.update(
            pipeline_id,
            config,
            change_reason=change_reason,
            updated_by=updated_by,
        )
        # 如果 Pipeline 已加载，触发热加载
        if self._orchestrator.get_pipeline(pipeline_id):
            self._orchestrator.reload_pipeline(pipeline_id)
        return {
            "pipeline_id": pipeline.pipeline_id,
            "version": pipeline.version,
        }

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        """获取 Pipeline 详情"""
        return self._config_manager.get(pipeline_id)

    def list_pipelines(self, scenario: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]:
        """列出 Pipeline"""
        return self._config_manager.list_pipelines(scenario=scenario, enabled=enabled)

    def delete_pipeline(self, pipeline_id: str) -> None:
        """删除 Pipeline"""
        self._orchestrator.unload_pipeline(pipeline_id)
        self._config_manager.delete(pipeline_id)

    def validate_pipeline(self, config: dict[str, Any]) -> dict[str, Any]:
        """验证配置"""
        from framework.config.validator import ConfigValidator

        validator = ConfigValidator()
        is_valid, errors = validator.validate(config)
        return {"valid": is_valid, "errors": errors}

    def test_pipeline(
        self,
        pipeline_id: str,
        event: dict[str, Any],
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """测试 Pipeline（Dry Run）"""
        # 确保 Pipeline 已加载
        if not self._orchestrator.get_pipeline(pipeline_id):
            self._orchestrator.load_from_db(pipeline_id)

        context = ProcessContext(
            pipeline_id=pipeline_id,
            event=event,
            variables=variables or {},
        )
        result_context = self._orchestrator.execute(pipeline_id, context)
        return result_context.to_dict()

    def get_versions(self, pipeline_id: str) -> list[dict[str, Any]]:
        """获取版本历史"""
        return self._config_manager.get_versions(pipeline_id)

    def rollback(self, pipeline_id: str, version: str, rolled_by: str = "") -> dict[str, Any]:
        """回滚到指定版本"""
        pipeline = self._config_manager.rollback(pipeline_id, version, rolled_by=rolled_by)
        return {"pipeline_id": pipeline.pipeline_id, "version": pipeline.version}

    def get_node_types(self) -> dict[str, Any]:
        """获取所有可用节点类型"""
        registry = ProcessorRegistry()
        return registry.list_all()

    def get_node_schema(self, node_type: str) -> dict[str, Any]:
        """获取节点配置 Schema"""
        registry = ProcessorRegistry()
        processor_class = registry.get(node_type)
        return {
            "config_schema": processor_class.get_config_schema(),
            "input_schema": processor_class.get_input_schema(),
            "output_schema": processor_class.get_output_schema(),
        }

    def query_trace(self, trace_id: str) -> dict[str, Any]:
        """根据 trace_id 查询执行链路"""
        return self._observability.query_by_trace_id(trace_id)
