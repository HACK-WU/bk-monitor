"""RateLimit 限流节点

基于 Redis 的分布式限流，支持滑动窗口、固定窗口和令牌桶算法。
"""

import logging
import time
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)

# 滑动窗口限流 Lua 脚本
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- 移除窗口外的记录
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- 获取当前窗口内的请求数
local count = redis.call('ZCARD', key)

if count < limit then
    -- 未超限，添加当前请求
    redis.call('ZADD', key, now, now .. '-' .. math.random(100000))
    redis.call('EXPIRE', key, window)
    return 0
else
    return 1
end
"""

# 固定窗口限流 Lua 脚本
FIXED_WINDOW_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end

if count > limit then
    return 1
else
    return 0
end
"""


class RateLimiter:
    """限流器基类"""

    def is_limited(self, redis_client, key: str, config: dict[str, Any]) -> bool:
        raise NotImplementedError


class SlidingWindowLimiter(RateLimiter):
    """滑动窗口限流"""

    def is_limited(self, redis_client, key: str, config: dict[str, Any]) -> bool:
        window = config.get("window", 60)
        limit = config.get("limit", 100)
        now = time.time()

        try:
            result = redis_client.eval(SLIDING_WINDOW_LUA, 1, key, window, limit, now)
            return bool(result)
        except Exception as e:
            logger.error("滑动窗口限流执行异常: %s", e)
            return False


class FixedWindowLimiter(RateLimiter):
    """固定窗口限流"""

    def is_limited(self, redis_client, key: str, config: dict[str, Any]) -> bool:
        window = config.get("window", 60)
        limit = config.get("limit", 100)

        try:
            result = redis_client.eval(FIXED_WINDOW_LUA, 1, key, limit, window)
            return bool(result)
        except Exception as e:
            logger.error("固定窗口限流执行异常: %s", e)
            return False


class TokenBucketLimiter(RateLimiter):
    """令牌桶限流（基于 Redis 实现）"""

    def is_limited(self, redis_client, key: str, config: dict[str, Any]) -> bool:
        rate = config.get("rate", 10)  # 每秒产生的令牌数
        capacity = config.get("capacity", 100)  # 桶容量
        now = time.time()

        try:
            pipe = redis_client.pipeline()
            tokens_key = f"{key}:tokens"
            ts_key = f"{key}:ts"

            last_ts = redis_client.get(ts_key)
            if last_ts is None:
                # 初始化
                pipe.set(tokens_key, capacity - 1)
                pipe.set(ts_key, now)
                pipe.execute()
                return False

            elapsed = now - float(last_ts)
            new_tokens = elapsed * rate
            current_tokens = float(redis_client.get(tokens_key) or 0)
            tokens = min(capacity, current_tokens + new_tokens)

            if tokens >= 1:
                pipe.set(tokens_key, tokens - 1)
                pipe.set(ts_key, now)
                pipe.execute()
                return False
            else:
                pipe.set(ts_key, now)
                pipe.execute()
                return True

        except Exception as e:
            logger.error("令牌桶限流执行异常: %s", e)
            return False


_LIMITER_MAP: dict[str, type] = {
    "sliding_window": SlidingWindowLimiter,
    "fixed_window": FixedWindowLimiter,
    "token_bucket": TokenBucketLimiter,
}


@register_processor
class RateLimitNode(BaseNode):
    """限流节点

    配置示例:
    {
        "strategy": "sliding_window",
        "key_template": "rate_limit:{strategy_id}:{ip}",
        "window": 60,
        "limit": 100,
        "rate": 10,
        "capacity": 100
    }
    """

    name = "rate_limit"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._strategy = config.get("strategy", "sliding_window")
        self._key_template = config.get("key_template", "rate_limit:{pipeline_id}")
        self._limiter_config = config
        self._redis_client = None

        limiter_class = _LIMITER_MAP.get(self._strategy)
        if not limiter_class:
            raise ValueError(f"不支持的限流策略: {self._strategy}")
        self._limiter = limiter_class()

    def _get_redis_client(self):
        """懒加载 Redis 客户端"""
        if self._redis_client is None:
            try:
                import redis

                self._redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
            except ImportError:
                logger.error("需要安装 redis: pip install redis")
                raise
        return self._redis_client

    def _build_key(self, context: ProcessContext) -> str:
        """根据模板和上下文构建限流 key"""
        key = self._key_template
        # 替换模板变量
        replacements = {
            "pipeline_id": context.pipeline_id,
            "trace_id": context.trace_id,
        }
        # 从事件数据中提取变量
        replacements.update(context.event)
        for var, val in replacements.items():
            key = key.replace(f"{{{var}}}", str(val))
        return key

    def process(self, context: ProcessContext) -> ProcessResult:
        key = self._build_key(context)

        try:
            client = self._get_redis_client()
            limited = self._limiter.is_limited(client, key, self._limiter_config)
        except Exception as e:
            # Redis 不可用时降级：不限流，记录告警
            logger.error("[%s] Redis 不可用，限流降级: %s", context.trace_id, e)
            limited = False

        context.metrics["rate_limited"] = limited

        if limited:
            logger.info("[%s] 事件被限流 (key=%s)", context.trace_id, key)
            context.stop("事件被限流")
            return ProcessResult(
                status=ProcessStatus.FILTERED,
                data={"limited": True, "key": key},
                message="事件被限流",
            )

        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"limited": False, "key": key},
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "enum": ["sliding_window", "fixed_window", "token_bucket"],
                    "default": "sliding_window",
                },
                "key_template": {"type": "string"},
                "window": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1},
                "rate": {"type": "number", "minimum": 0.1},
                "capacity": {"type": "integer", "minimum": 1},
            },
        }
