"""处理器框架模块

提供 BaseProcessor 抽象基类、ProcessorRegistry 注册中心和 ProcessorFactory 工厂类。
"""

from framework.processor.base import BaseProcessor, ProcessResult
from framework.processor.registry import ProcessorRegistry, register_processor
from framework.processor.factory import ProcessorFactory

__all__ = [
    "BaseProcessor",
    "ProcessResult",
    "ProcessorRegistry",
    "ProcessorFactory",
    "register_processor",
]
