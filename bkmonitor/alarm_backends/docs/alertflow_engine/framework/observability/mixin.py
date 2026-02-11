"""ObservabilityMixin

为节点提供统一的可观测性能力：自动记录节点开始/成功/失败。
"""

import logging
import time

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus

logger = logging.getLogger(__name__)


class ObservabilityMixin:
    """可观测性 Mixin

    集成到节点基类后，自动记录：
    1. 节点开始执行
    2. 节点执行成功（含耗时）
    3. 节点执行失败（含异常信息）
    """

    def process_with_observability(self, context: ProcessContext) -> ProcessResult:
        """带可观测性的处理方法包装"""
        node_name = getattr(self, "name", self.__class__.__name__)
        trace_id = context.trace_id

        logger.info(
            "node_start",
            extra={
                "trace_id": trace_id,
                "pipeline_id": context.pipeline_id,
                "node": node_name,
            },
        )

        start_time = time.time()

        try:
            # 调用实际的 process 方法
            result = self.process(context)
            elapsed_ms = (time.time() - start_time) * 1000

            log_data = {
                "trace_id": trace_id,
                "pipeline_id": context.pipeline_id,
                "node": node_name,
                "status": result.status.value,
                "elapsed_ms": round(elapsed_ms, 2),
            }

            if result.is_success:
                logger.info("node_success", extra=log_data)
            elif result.status == ProcessStatus.FILTERED:
                logger.info("node_filtered", extra={**log_data, "message": result.message})
            else:
                logger.warning("node_failed", extra={**log_data, "error": result.error})

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.exception(
                "node_exception",
                extra={
                    "trace_id": trace_id,
                    "pipeline_id": context.pipeline_id,
                    "node": node_name,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": str(e),
                },
            )
            raise
