"""CircuitBreaker 熔断节点

实现 open/closed/half-open 三态熔断机制。
"""

import logging
import time
from enum import Enum
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """熔断状态"""

    CLOSED = "closed"  # 正常（闭合）
    OPEN = "open"  # 熔断（断开）
    HALF_OPEN = "half_open"  # 半开（探测）


class CircuitBreaker:
    """熔断器

    状态转换：
    CLOSED -> OPEN: 失败次数达到阈值
    OPEN -> HALF_OPEN: 冷却时间到达
    HALF_OPEN -> CLOSED: 探测成功
    HALF_OPEN -> OPEN: 探测失败
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """获取当前状态（含自动过渡到 HALF_OPEN）"""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("熔断器进入 HALF_OPEN 状态")
        return self._state

    def allow_request(self) -> bool:
        """检查是否允许请求通过"""
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.OPEN:
            return False
        elif current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False

    def record_success(self) -> None:
        """记录成功"""
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("熔断器恢复到 CLOSED 状态")
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("熔断器探测失败，回到 OPEN 状态")
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "失败次数 %d 达到阈值 %d，熔断器进入 OPEN 状态",
                    self._failure_count,
                    self.failure_threshold,
                )


@register_processor
class CircuitBreakerNode(BaseNode):
    """熔断节点

    检查当前熔断状态，决定是否允许事件通过。

    配置示例:
    {
        "key": "strategy_{strategy_id}",
        "failure_threshold": 5,
        "recovery_timeout": 60,
        "half_open_max_calls": 3
    }
    """

    name = "circuit_breaker"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._breaker = CircuitBreaker(
            failure_threshold=config.get("failure_threshold", 5),
            recovery_timeout=config.get("recovery_timeout", 60),
            half_open_max_calls=config.get("half_open_max_calls", 3),
        )

    def process(self, context: ProcessContext) -> ProcessResult:
        state = self._breaker.state

        if not self._breaker.allow_request():
            logger.info(
                "[%s] 熔断器已打开 (state=%s)，事件被拦截",
                context.trace_id,
                state.value,
            )
            context.stop(f"熔断器已打开: {state.value}")
            return ProcessResult(
                status=ProcessStatus.FILTERED,
                data={"circuit_state": state.value, "allowed": False},
                message="熔断器已打开",
            )

        # 记录成功通过
        self._breaker.record_success()

        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"circuit_state": state.value, "allowed": True},
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "failure_threshold": {"type": "integer", "minimum": 1, "default": 5},
                "recovery_timeout": {"type": "integer", "minimum": 1, "default": 60},
                "half_open_max_calls": {"type": "integer", "minimum": 1, "default": 3},
            },
        }
