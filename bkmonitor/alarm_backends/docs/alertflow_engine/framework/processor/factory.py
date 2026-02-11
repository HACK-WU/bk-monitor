"""处理器工厂

根据名称和配置创建处理器实例。
"""

import logging
from typing import Any

from framework.processor.base import BaseProcessor
from framework.processor.registry import ProcessorRegistry

logger = logging.getLogger(__name__)


class ProcessorFactory:
    """处理器工厂类

    负责根据处理器名称和配置创建已初始化的处理器实例。
    """

    def __init__(self, registry: ProcessorRegistry | None = None):
        self._registry = registry or ProcessorRegistry()

    def create(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        version: str | None = None,
    ) -> BaseProcessor:
        """创建并初始化处理器实例

        Args:
            name: 处理器名称
            config: 处理器配置
            version: 处理器版本，为 None 时使用最新版本

        Returns:
            已初始化的处理器实例

        Raises:
            KeyError: 处理器未注册
            ValueError: 配置验证失败
        """
        config = config or {}

        processor_class = self._registry.get(name, version)
        processor = processor_class()

        # 验证配置
        if not processor.validate_config(config):
            raise ValueError(f"处理器 '{name}' 配置验证失败: {config}")

        # 初始化
        processor.initialize(config)
        logger.debug("创建处理器: %s v%s", name, version or "latest")
        return processor

    def create_from_node_config(self, node_config: dict[str, Any]) -> BaseProcessor:
        """根据 Pipeline 节点配置创建处理器

        节点配置格式:
        {
            "id": "node_001",
            "type": "filter",
            "version": "1.0.0",  // 可选
            "config": { ... }
        }
        """
        name = node_config["type"]
        version = node_config.get("version")
        config = node_config.get("config", {})
        return self.create(name, config, version)
