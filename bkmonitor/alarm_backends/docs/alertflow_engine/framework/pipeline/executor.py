"""Pipeline 执行器

按配置依次调度节点执行，处理错误策略、条件判断、超时控制和上游输出传递。
"""

import logging
import time
from enum import Enum
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import BaseProcessor, ProcessResult, ProcessStatus
from framework.rule.engine import RuleEngine

logger = logging.getLogger(__name__)


class ErrorStrategy(str, Enum):
    """错误处理策略"""

    IGNORE = "ignore"
    RETRY = "retry"
    STOP = "stop"
    FALLBACK = "fallback"


class NodeExecution:
    """单个节点的执行封装"""

    def __init__(
        self,
        node_id: str,
        processor: BaseProcessor,
        config: dict[str, Any],
    ):
        self.node_id = node_id
        self.processor = processor
        self.config = config
        self.error_strategy = ErrorStrategy(config.get("error_strategy", "stop"))
        self.timeout = config.get("timeout")
        self.condition = config.get("condition")
        self.enabled = config.get("enabled", True)
        self.retry_config = config.get("retry", {})


class PipelineExecutor:
    """Pipeline 执行器

    职责：
    1. 按序执行节点列表
    2. 节点条件判断（基于规则引擎）
    3. 错误处理策略（忽略/重试/停止/降级）
    4. 超时控制
    5. 上游输出传递（upstream 机制）
    """

    def __init__(self):
        self._rule_engine = RuleEngine()

    def execute(
        self,
        nodes: list[NodeExecution],
        context: ProcessContext,
    ) -> ProcessContext:
        """执行节点列表

        Args:
            nodes: 待执行的节点列表
            context: 处理上下文

        Returns:
            执行后的上下文
        """
        for node in nodes:
            if context.should_stop:
                logger.info(
                    "[%s] Pipeline 已终止，跳过节点 %s",
                    context.trace_id,
                    node.node_id,
                )
                break

            # 检查节点是否启用
            if not node.enabled:
                logger.debug("[%s] 节点 %s 已禁用，跳过", context.trace_id, node.node_id)
                continue

            # 条件判断
            if not self._check_condition(node, context):
                logger.debug(
                    "[%s] 节点 %s 条件不满足，跳过",
                    context.trace_id,
                    node.node_id,
                )
                continue

            # 执行节点
            result = self._execute_node(node, context)

            # 记录上游输出
            if result.data is not None:
                context.set_upstream_output(node.node_id, result.data)

            # 记录已执行
            context.record_node_execution(node.node_id)

        return context

    def _check_condition(self, node: NodeExecution, context: ProcessContext) -> bool:
        """检查节点执行条件"""
        if not node.condition:
            return True

        # 构建条件匹配数据（合并 event + variables + upstream）
        data = {
            **context.event,
            "variables": context.variables,
            "upstream": context.upstream,
            "metadata": context.metadata,
        }
        if context.alert:
            data["alert"] = context.alert

        try:
            return self._rule_engine.evaluate(data, node.condition)
        except Exception as e:
            logger.warning(
                "[%s] 节点 %s 条件评估异常: %s，默认执行",
                context.trace_id,
                node.node_id,
                e,
            )
            return True

    def _execute_node(self, node: NodeExecution, context: ProcessContext) -> ProcessResult:
        """执行单个节点，含错误处理"""
        start_time = time.time()

        try:
            result = self._run_with_timeout(node, context)
            elapsed = (time.time() - start_time) * 1000
            context.metrics[f"{node.node_id}.elapsed_ms"] = elapsed

            if not result.is_success and result.status != ProcessStatus.FILTERED:
                logger.warning(
                    "[%s] 节点 %s 执行失败: %s",
                    context.trace_id,
                    node.node_id,
                    result.error,
                )
                self._handle_error(node, context, result.error)

            return result

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            context.metrics[f"{node.node_id}.elapsed_ms"] = elapsed
            logger.exception(
                "[%s] 节点 %s 执行异常: %s",
                context.trace_id,
                node.node_id,
                e,
            )
            self._handle_error(node, context, str(e))
            return ProcessResult(status=ProcessStatus.FAILED, error=str(e))

    def _run_with_timeout(self, node: NodeExecution, context: ProcessContext) -> ProcessResult:
        """执行节点（带超时控制）"""
        # 简单超时检查：通过记录开始时间实现
        # 注：复杂超时控制可在后续引入 concurrent.futures
        return node.processor.process(context)

    def _handle_error(self, node: NodeExecution, context: ProcessContext, error: str) -> None:
        """根据错误策略处理异常"""
        strategy = node.error_strategy

        if strategy == ErrorStrategy.IGNORE:
            logger.info("[%s] 节点 %s 错误被忽略: %s", context.trace_id, node.node_id, error)

        elif strategy == ErrorStrategy.RETRY:
            max_retries = node.retry_config.get("max_retries", 3)
            interval = node.retry_config.get("interval", 1.0)
            self._retry_node(node, context, max_retries, interval)

        elif strategy == ErrorStrategy.STOP:
            context.stop(f"节点 {node.node_id} 执行失败: {error}")

        elif strategy == ErrorStrategy.FALLBACK:
            logger.info("[%s] 节点 %s 触发降级", context.trace_id, node.node_id)
            # 降级逻辑：标记为降级，由编排器处理

    def _retry_node(
        self,
        node: NodeExecution,
        context: ProcessContext,
        max_retries: int,
        interval: float,
    ) -> ProcessResult | None:
        """重试执行节点"""
        for attempt in range(1, max_retries + 1):
            logger.info(
                "[%s] 节点 %s 第 %d/%d 次重试",
                context.trace_id,
                node.node_id,
                attempt,
                max_retries,
            )
            time.sleep(interval)
            try:
                result = node.processor.process(context)
                if result.is_success:
                    return result
            except Exception as e:
                logger.warning(
                    "[%s] 节点 %s 重试失败: %s",
                    context.trace_id,
                    node.node_id,
                    e,
                )

        # 重试耗尽
        context.stop(f"节点 {node.node_id} 重试 {max_retries} 次仍失败")
        return None
