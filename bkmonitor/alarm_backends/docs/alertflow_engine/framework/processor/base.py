"""处理器抽象基类和结果类

定义所有处理节点必须实现的统一接口规范。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from framework.pipeline.context import ProcessContext


class ProcessStatus(str, Enum):
    """处理结果状态"""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    FILTERED = "filtered"


@dataclass
class ProcessResult:
    """处理器执行结果

    Attributes:
        status: 执行状态
        data: 输出数据
        error: 错误信息
        metrics: 性能指标（耗时、计数等）
        message: 附加消息
    """

    status: ProcessStatus = ProcessStatus.SUCCESS
    data: dict[str, Any] | None = None
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == ProcessStatus.SUCCESS

    @property
    def is_filtered(self) -> bool:
        return self.status == ProcessStatus.FILTERED


class BaseProcessor(ABC):
    """处理器抽象基类

    定义节点必须实现的核心接口：
    1. 数据处理接口: process()
    2. 配置接口: initialize(), validate_config(), get_config_schema()
    3. Schema 接口: get_input_schema(), get_output_schema()
    4. 元数据接口: name, version
    5. 生命周期接口: cleanup()
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """处理器唯一名称"""

    @property
    @abstractmethod
    def version(self) -> str:
        """处理器版本号"""

    @abstractmethod
    def initialize(self, config: dict[str, Any]) -> None:
        """根据配置初始化处理器"""

    @abstractmethod
    def process(self, context: "ProcessContext") -> ProcessResult:
        """核心处理方法，接收上下文并返回处理结果"""

    def validate_config(self, config: dict[str, Any]) -> bool:
        """验证配置合法性，默认返回 True"""
        return True

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """返回处理器配置的 JSON Schema"""
        return {}

    @classmethod
    def get_input_schema(cls) -> dict[str, Any]:
        """返回期望的输入数据 Schema"""
        return {}

    @classmethod
    def get_output_schema(cls) -> dict[str, Any]:
        """返回输出数据 Schema"""
        return {}

    def cleanup(self) -> None:
        """资源清理，处理器销毁时调用"""
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} version={self.version}>"
