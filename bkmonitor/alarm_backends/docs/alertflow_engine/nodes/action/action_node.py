"""Action 动作节点

支持自动化动作触发，如自愈操作、作业平台任务等。
"""

import logging
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


class ActionExecutor:
    """动作执行器基类"""

    action_type: str = ""

    def execute(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        """执行动作，返回执行结果"""
        raise NotImplementedError


class HTTPCallbackExecutor(ActionExecutor):
    """HTTP 回调动作"""

    action_type = "http_callback"

    def execute(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        url = config.get("url", "")
        method = config.get("method", "POST")
        # TODO: 对接 HTTP 请求
        logger.info("[%s] 执行 HTTP 回调: %s %s", context.trace_id, method, url)
        return {"action": "http_callback", "url": url, "status": "executed"}


class JobExecutor(ActionExecutor):
    """作业平台任务"""

    action_type = "job"

    def execute(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        job_id = config.get("job_id", "")
        bk_biz_id = config.get("bk_biz_id", context.event.get("bk_biz_id", 0))
        # TODO: 对接作业平台 API
        logger.info("[%s] 执行作业平台任务: job_id=%s, biz=%s", context.trace_id, job_id, bk_biz_id)
        return {"action": "job", "job_id": job_id, "status": "executed"}


class ScriptExecutor(ActionExecutor):
    """脚本执行"""

    action_type = "script"

    def execute(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        script_name = config.get("script_name", "")
        logger.info("[%s] 执行脚本: %s", context.trace_id, script_name)
        return {"action": "script", "script_name": script_name, "status": "executed"}


_EXECUTOR_MAP: dict[str, type] = {
    "http_callback": HTTPCallbackExecutor,
    "job": JobExecutor,
    "script": ScriptExecutor,
}


@register_processor
class ActionNode(BaseNode):
    """动作节点

    配置示例:
    {
        "actions": [
            {
                "type": "http_callback",
                "url": "http://example.com/callback",
                "method": "POST"
            },
            {
                "type": "job",
                "job_id": "job_001",
                "bk_biz_id": 2
            }
        ]
    }
    """

    name = "action"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._actions = config.get("actions", [])

    def process(self, context: ProcessContext) -> ProcessResult:
        results = []
        success_count = 0

        for action_config in self._actions:
            action_type = action_config.get("type", "")
            executor_class = _EXECUTOR_MAP.get(action_type)

            if not executor_class:
                logger.warning("[%s] 未知动作类型: %s", context.trace_id, action_type)
                results.append({"type": action_type, "success": False, "error": "未知动作类型"})
                continue

            try:
                executor = executor_class()
                result = executor.execute(context, action_config)
                results.append({"type": action_type, "success": True, "result": result})
                success_count += 1
            except Exception as e:
                logger.error("[%s] 动作 %s 执行异常: %s", context.trace_id, action_type, e)
                results.append({"type": action_type, "success": False, "error": str(e)})

        return ProcessResult(
            status=ProcessStatus.SUCCESS if success_count > 0 else ProcessStatus.FAILED,
            data={"actions": results, "success_count": success_count},
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["http_callback", "job", "script"],
                            },
                        },
                    },
                },
            },
        }
