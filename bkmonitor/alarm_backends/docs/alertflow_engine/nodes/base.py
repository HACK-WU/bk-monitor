"""节点通用基类

为所有预置节点提供统一的基类，封装通用行为。
"""

import logging
from typing import Any

from framework.processor.base import BaseProcessor

logger = logging.getLogger(__name__)


class BaseNode(BaseProcessor):
    """节点通用基类

    在 BaseProcessor 基础上增加：
    - 配置存储
    - 通用日志记录
    - 默认配置验证
    """

    # 子类必须覆盖
    name: str = ""
    version: str = "1.0.0"

    def __init__(self):
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化节点配置"""
        self._config = config or {}
        self.on_initialize(config)

    def on_initialize(self, config: dict[str, Any]) -> None:
        """子类自定义初始化逻辑（可选覆盖）"""
        pass

    @property
    def config(self) -> dict[str, Any]:
        return self._config
