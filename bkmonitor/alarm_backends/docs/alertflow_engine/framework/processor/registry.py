"""处理器注册中心

基于单例模式的处理器注册表，支持处理器的注册、查询和列举。
提供 @register_processor 装饰器用于自动注册处理器类。
"""

import logging
import threading
from typing import Optional

from framework.processor.base import BaseProcessor

logger = logging.getLogger(__name__)


class ProcessorRegistry:
    """处理器注册中心（线程安全的单例模式）"""

    _instance: Optional["ProcessorRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProcessorRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._registry: dict[str, dict[str, type[BaseProcessor]]] = {}
        return cls._instance

    def register(self, processor_class: type[BaseProcessor]) -> type[BaseProcessor]:
        """注册处理器类

        Args:
            processor_class: 继承自 BaseProcessor 的处理器类

        Returns:
            原始的处理器类（支持装饰器链）

        Raises:
            TypeError: 非 BaseProcessor 子类
            ValueError: 重复注册同名同版本的处理器
        """
        if not (isinstance(processor_class, type) and issubclass(processor_class, BaseProcessor)):
            raise TypeError(f"{processor_class} 必须是 BaseProcessor 的子类")

        # 通过临时实例获取 name/version（property 属性需要实例访问）
        # 这里使用类属性的约定：子类也可以定义为类属性而非 property
        name = getattr(processor_class, "name", None)
        version = getattr(processor_class, "version", None)

        # 如果是 property，则需要尝试从类定义中获取默认值
        if isinstance(name, property) or name is None:
            raise ValueError(f"{processor_class.__name__} 必须定义 name 属性")
        if isinstance(version, property) or version is None:
            raise ValueError(f"{processor_class.__name__} 必须定义 version 属性")

        if name not in self._registry:
            self._registry[name] = {}

        if version in self._registry[name]:
            existing = self._registry[name][version]
            raise ValueError(
                f"处理器 '{name}' v{version} 已注册为 {existing.__name__}，无法再注册 {processor_class.__name__}"
            )

        self._registry[name][version] = processor_class
        logger.info("注册处理器: %s v%s -> %s", name, version, processor_class.__name__)
        return processor_class

    def get(self, name: str, version: str | None = None) -> type[BaseProcessor]:
        """获取处理器类

        Args:
            name: 处理器名称
            version: 版本号，为 None 时返回最新版本

        Raises:
            KeyError: 处理器未注册
        """
        if name not in self._registry:
            raise KeyError(f"处理器 '{name}' 未注册，可用: {list(self._registry.keys())}")

        versions = self._registry[name]
        if version is not None:
            if version not in versions:
                raise KeyError(f"处理器 '{name}' 无版本 '{version}'，可用: {list(versions.keys())}")
            return versions[version]

        # 返回最新版本（按字符串排序取最后一个）
        latest_version = sorted(versions.keys())[-1]
        return versions[latest_version]

    def list_all(self) -> dict[str, dict[str, str]]:
        """列出所有已注册处理器

        Returns:
            {name: {version: class_name, ...}, ...}
        """
        return {name: {ver: cls.__name__ for ver, cls in versions.items()} for name, versions in self._registry.items()}

    def unregister(self, name: str, version: str | None = None) -> None:
        """取消注册处理器（主要用于测试）"""
        if name in self._registry:
            if version:
                self._registry[name].pop(version, None)
                if not self._registry[name]:
                    del self._registry[name]
            else:
                del self._registry[name]

    def clear(self) -> None:
        """清空注册表（仅用于测试）"""
        self._registry.clear()

    @property
    def count(self) -> int:
        """已注册处理器总数"""
        return sum(len(v) for v in self._registry.values())


def register_processor(cls: type[BaseProcessor]) -> type[BaseProcessor]:
    """处理器注册装饰器

    用法:
        @register_processor
        class MyProcessor(BaseProcessor):
            name = "my_processor"
            version = "1.0.0"
    """
    ProcessorRegistry().register(cls)
    return cls
