"""Converge 收敛节点

支持计数收敛、时长收敛和间隔收敛。收敛状态存储在 Redis。
"""

import hashlib
import logging
import time
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


class ConvergeStrategy:
    """收敛策略基类"""

    def should_converge(
        self, redis_client, converge_key: str, config: dict[str, Any], context: ProcessContext
    ) -> tuple:
        """返回 (是否收敛, 收敛信息)"""
        raise NotImplementedError


class CountConverge(ConvergeStrategy):
    """计数收敛：同一维度达到阈值后才发送通知"""

    def should_converge(self, redis_client, converge_key: str, config: dict[str, Any], context: ProcessContext):
        threshold = config.get("threshold", 3)
        window = config.get("window", 300)

        try:
            count_key = f"converge:count:{converge_key}"
            count = redis_client.incr(count_key)
            if count == 1:
                redis_client.expire(count_key, window)

            if count < threshold:
                return True, f"计数收敛: {count}/{threshold}"
            elif count == threshold:
                return False, f"计数达到阈值: {count}/{threshold}，放行"
            else:
                # 超过阈值后，每 threshold 次放行一次
                if count % threshold == 0:
                    return False, f"周期放行: {count}"
                return True, f"计数收敛: {count}"
        except Exception as e:
            logger.error("计数收敛异常: %s", e)
            return False, "收敛异常，默认放行"


class DurationConverge(ConvergeStrategy):
    """时长收敛：持续一段时间后才发送通知"""

    def should_converge(self, redis_client, converge_key: str, config: dict[str, Any], context: ProcessContext):
        duration = config.get("duration", 60)

        try:
            first_key = f"converge:first:{converge_key}"
            first_time = redis_client.get(first_key)

            if first_time is None:
                redis_client.set(first_key, time.time(), ex=duration * 2)
                return True, f"时长收敛: 首次出现，等待 {duration}s"

            elapsed = time.time() - float(first_time)
            if elapsed >= duration:
                redis_client.delete(first_key)
                return False, f"持续时间 {elapsed:.0f}s >= {duration}s，放行"
            return True, f"时长收敛: 已持续 {elapsed:.0f}s / {duration}s"
        except Exception as e:
            logger.error("时长收敛异常: %s", e)
            return False, "收敛异常，默认放行"


class IntervalConverge(ConvergeStrategy):
    """间隔收敛：控制通知发送间隔"""

    def should_converge(self, redis_client, converge_key: str, config: dict[str, Any], context: ProcessContext):
        interval = config.get("interval", 300)

        try:
            last_key = f"converge:last:{converge_key}"
            last_time = redis_client.get(last_key)

            if last_time is None:
                redis_client.set(last_key, time.time(), ex=interval * 2)
                return False, "首次通知，放行"

            elapsed = time.time() - float(last_time)
            if elapsed >= interval:
                redis_client.set(last_key, time.time(), ex=interval * 2)
                return False, f"距上次通知 {elapsed:.0f}s >= {interval}s，放行"
            return True, f"间隔收敛: 距上次通知 {elapsed:.0f}s / {interval}s"
        except Exception as e:
            logger.error("间隔收敛异常: %s", e)
            return False, "收敛异常，默认放行"


_CONVERGE_MAP: dict[str, type] = {
    "count": CountConverge,
    "duration": DurationConverge,
    "interval": IntervalConverge,
}


@register_processor
class ConvergeNode(BaseNode):
    """收敛节点

    配置示例:
    {
        "converge_type": "count",
        "dimensions": ["strategy_id", "ip", "bk_biz_id"],
        "threshold": 3,
        "window": 300,
        "duration": 60,
        "interval": 300
    }
    """

    name = "converge"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._converge_type = config.get("converge_type", "count")
        self._dimensions = config.get("dimensions", [])
        self._converge_config = config
        self._redis_client = None

        strategy_class = _CONVERGE_MAP.get(self._converge_type)
        if not strategy_class:
            raise ValueError(f"不支持的收敛类型: {self._converge_type}")
        self._strategy = strategy_class()

    def _get_redis_client(self):
        if self._redis_client is None:
            try:
                import redis

                self._redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
            except ImportError:
                raise ImportError("需要安装 redis: pip install redis")
        return self._redis_client

    def _build_converge_key(self, context: ProcessContext) -> str:
        """根据维度构建收敛 key"""
        parts = []
        for dim in self._dimensions:
            value = context.event.get(dim, "")
            parts.append(f"{dim}={value}")
        raw = "|".join(parts) if parts else context.pipeline_id
        return hashlib.md5(raw.encode()).hexdigest()

    def process(self, context: ProcessContext) -> ProcessResult:
        converge_key = self._build_converge_key(context)

        try:
            client = self._get_redis_client()
            converged, reason = self._strategy.should_converge(client, converge_key, self._converge_config, context)
        except Exception as e:
            logger.error("[%s] 收敛处理异常，默认放行: %s", context.trace_id, e)
            converged = False
            reason = "收敛异常，默认放行"

        context.metrics["converged"] = converged

        if converged:
            logger.info("[%s] 事件被收敛: %s", context.trace_id, reason)
            context.stop(reason)
            return ProcessResult(
                status=ProcessStatus.FILTERED,
                data={"converged": True, "reason": reason, "converge_key": converge_key},
                message=reason,
            )

        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"converged": False, "reason": reason, "converge_key": converge_key},
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["converge_type"],
            "properties": {
                "converge_type": {"type": "string", "enum": ["count", "duration", "interval"]},
                "dimensions": {"type": "array", "items": {"type": "string"}},
                "threshold": {"type": "integer", "minimum": 1},
                "window": {"type": "integer", "minimum": 1},
                "duration": {"type": "integer", "minimum": 1},
                "interval": {"type": "integer", "minimum": 1},
            },
        }
