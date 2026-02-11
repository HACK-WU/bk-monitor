"""structlog 配置与封装

统一的结构化日志配置，输出 JSON 格式日志。
"""

import logging
import sys
from typing import Any


def configure_logging(
    level: str = "INFO",
    json_format: bool = True,
    log_file: str | None = None,
) -> None:
    """配置结构化日志

    Args:
        level: 日志级别
        json_format: 是否使用 JSON 格式输出
        log_file: 日志文件路径（可选）
    """
    try:
        import structlog

        # 处理器链
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
        ]

        if json_format:
            processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
        else:
            processors.append(structlog.dev.ConsoleRenderer())

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    except ImportError:
        # structlog 未安装时使用标准 logging
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        logging.getLogger(__name__).warning("structlog 未安装，使用标准 logging")


def get_logger(name: str = "") -> Any:
    """获取结构化 logger"""
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)


def bind_context(**kwargs) -> None:
    """绑定上下文变量到当前协程/线程"""
    try:
        import structlog

        structlog.contextvars.bind_contextvars(**kwargs)
    except (ImportError, AttributeError):
        pass


def unbind_context(*keys: str) -> None:
    """移除上下文变量"""
    try:
        import structlog

        structlog.contextvars.unbind_contextvars(*keys)
    except (ImportError, AttributeError):
        pass
