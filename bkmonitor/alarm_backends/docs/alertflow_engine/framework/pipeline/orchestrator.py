"""Pipeline 编排器

负责加载配置、实例化节点、编排执行流程，管理多个 Pipeline 实例。
"""

import logging
from typing import Any

from framework.config.loader import ConfigLoader
from framework.config.manager import ConfigManager
from framework.config.validator import ConfigValidator
from framework.pipeline.context import ProcessContext
from framework.pipeline.executor import NodeExecution, PipelineExecutor
from framework.processor.factory import ProcessorFactory
from framework.processor.registry import ProcessorRegistry

logger = logging.getLogger(__name__)


class PipelineDefinition:
    """Pipeline 定义，保存解析后的配置和实例化的节点"""

    def __init__(self, pipeline_id: str, config: dict[str, Any]):
        self.pipeline_id = pipeline_id
        self.config = config
        self.name = config.get("name", "")
        self.version = config.get("version", "")
        self.enabled = config.get("enabled", True)
        self.stages: list[list[NodeExecution]] = []

    def is_enabled(self) -> bool:
        return self.enabled


class PipelineOrchestrator:
    """Pipeline 编排器

    职责：
    1. 加载和解析 Pipeline 配置
    2. 实例化所有节点
    3. 管理多个 Pipeline
    4. 驱动 Pipeline 执行
    5. 支持热加载
    """

    def __init__(
        self,
        registry: ProcessorRegistry | None = None,
        config_manager: ConfigManager | None = None,
    ):
        self._registry = registry or ProcessorRegistry()
        self._factory = ProcessorFactory(self._registry)
        self._config_manager = config_manager or ConfigManager()
        self._loader = ConfigLoader()
        self._validator = ConfigValidator()
        self._executor = PipelineExecutor()

        # 已加载的 Pipeline: pipeline_id -> PipelineDefinition
        self._pipelines: dict[str, PipelineDefinition] = {}

    def load_pipeline(self, config: dict[str, Any]) -> PipelineDefinition:
        """从配置字典加载 Pipeline

        Args:
            config: Pipeline 配置字典

        Returns:
            PipelineDefinition 实例
        """
        # 验证配置
        is_valid, errors = self._validator.validate(config)
        if not is_valid:
            raise ValueError(f"Pipeline 配置验证失败: {'; '.join(errors)}")

        pipeline_id = config["id"]
        definition = PipelineDefinition(pipeline_id, config)

        # 解析每个 Stage 的节点
        for stage_config in config.get("stages", []):
            if not stage_config.get("enabled", True):
                continue

            stage_nodes = []
            for proc_config in stage_config.get("processors", []):
                if not proc_config.get("enabled", True):
                    continue

                # 通过工厂创建处理器实例
                processor = self._factory.create_from_node_config(proc_config)
                node = NodeExecution(
                    node_id=proc_config["id"],
                    processor=processor,
                    config=proc_config,
                )
                stage_nodes.append(node)

            if stage_nodes:
                definition.stages.append(stage_nodes)

        self._pipelines[pipeline_id] = definition
        logger.info(
            "加载 Pipeline: %s v%s (%d 个阶段, %d 个节点)",
            pipeline_id,
            definition.version,
            len(definition.stages),
            sum(len(s) for s in definition.stages),
        )
        return definition

    def load_from_file(self, file_path: str) -> PipelineDefinition:
        """从文件加载 Pipeline"""
        config = self._loader.load_from_file(file_path)
        return self.load_pipeline(config)

    def load_from_db(self, pipeline_id: str) -> PipelineDefinition:
        """从数据库加载 Pipeline"""
        config = self._config_manager.get(pipeline_id)
        return self.load_pipeline(config)

    def execute(
        self,
        pipeline_id: str,
        context: ProcessContext | None = None,
        event: dict[str, Any] | None = None,
    ) -> ProcessContext:
        """执行指定 Pipeline

        Args:
            pipeline_id: Pipeline ID
            context: 已有上下文（可选）
            event: 原始事件数据（与 context 二选一）

        Returns:
            执行后的 ProcessContext
        """
        definition = self._pipelines.get(pipeline_id)
        if not definition:
            raise KeyError(f"Pipeline '{pipeline_id}' 未加载")

        if not definition.is_enabled():
            raise RuntimeError(f"Pipeline '{pipeline_id}' 已禁用")

        # 构建上下文
        if context is None:
            context = ProcessContext(pipeline_id=pipeline_id, event=event or {})
        else:
            context.pipeline_id = pipeline_id

        logger.info("[%s] 开始执行 Pipeline: %s", context.trace_id, pipeline_id)
        start_time = __import__("time").time()

        # 按 Stage 依次执行
        for stage_idx, stage_nodes in enumerate(definition.stages):
            if context.should_stop:
                break

            logger.debug(
                "[%s] 执行 Stage %d (%d 个节点)",
                context.trace_id,
                stage_idx,
                len(stage_nodes),
            )
            self._executor.execute(stage_nodes, context)

        elapsed = (__import__("time").time() - start_time) * 1000
        context.metrics["total_elapsed_ms"] = elapsed

        logger.info(
            "[%s] Pipeline %s 执行完成, 耗时 %.2fms, 执行节点: %s",
            context.trace_id,
            pipeline_id,
            elapsed,
            context.executed_nodes,
        )
        return context

    def reload_pipeline(self, pipeline_id: str) -> PipelineDefinition:
        """热加载 Pipeline（清除旧实例，从数据库重新加载）"""
        # 清理旧的处理器资源
        if pipeline_id in self._pipelines:
            old = self._pipelines[pipeline_id]
            for stage in old.stages:
                for node in stage:
                    try:
                        node.processor.cleanup()
                    except Exception as e:
                        logger.warning("节点 %s 清理失败: %s", node.node_id, e)

        # 重新加载配置
        config = self._config_manager.reload(pipeline_id)
        return self.load_pipeline(config)

    def get_pipeline(self, pipeline_id: str) -> PipelineDefinition | None:
        """获取已加载的 Pipeline 定义"""
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> dict[str, dict[str, Any]]:
        """列出所有已加载的 Pipeline"""
        return {
            pid: {
                "name": defn.name,
                "version": defn.version,
                "enabled": defn.enabled,
                "stages": len(defn.stages),
                "nodes": sum(len(s) for s in defn.stages),
            }
            for pid, defn in self._pipelines.items()
        }

    def unload_pipeline(self, pipeline_id: str) -> None:
        """卸载 Pipeline"""
        if pipeline_id in self._pipelines:
            defn = self._pipelines.pop(pipeline_id)
            for stage in defn.stages:
                for node in stage:
                    try:
                        node.processor.cleanup()
                    except Exception:
                        pass
            logger.info("卸载 Pipeline: %s", pipeline_id)
