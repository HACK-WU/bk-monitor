"""Filter 过滤节点

基于规则引擎的事件过滤，不满足条件的事件将终止 Pipeline 执行。
"""

import logging
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from framework.rule.engine import RuleEngine
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


@register_processor
class FilterNode(BaseNode):
    """过滤节点

    根据配置的条件规则对事件进行过滤：
    - 匹配通过：继续执行后续节点
    - 匹配失败：标记 context.should_stop = True，终止 Pipeline

    配置示例:
    {
        "mode": "all",  // "all"=全部满足, "any"=任意满足
        "rules": [
            {
                "logic": "and",
                "conditions": [
                    {"field": "severity", "operator": "gte", "value": 2},
                    {"field": "labels.env", "operator": "eq", "value": "production"}
                ]
            }
        ]
    }
    """

    name = "filter"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._rule_engine = RuleEngine()
        self._mode = config.get("mode", "all")
        self._rules = config.get("rules", [])

    def process(self, context: ProcessContext) -> ProcessResult:
        """执行过滤逻辑"""
        if not self._rules:
            return ProcessResult(
                status=ProcessStatus.SUCCESS,
                data={"matched": True, "reason": "无过滤规则"},
            )

        # 构建匹配数据
        data = {**context.event}
        if context.alert:
            data["alert"] = context.alert
        data["variables"] = context.variables

        # 执行匹配
        if self._mode == "any":
            matched = self._rule_engine.evaluate_any(data, self._rules)
        else:
            matched = self._rule_engine.evaluate_all(data, self._rules)

        if matched:
            logger.debug("[%s] 过滤通过 (mode=%s)", context.trace_id, self._mode)
            return ProcessResult(
                status=ProcessStatus.SUCCESS,
                data={"matched": True},
            )
        else:
            logger.info("[%s] 事件被过滤 (mode=%s)", context.trace_id, self._mode)
            context.stop("事件未通过过滤条件")
            return ProcessResult(
                status=ProcessStatus.FILTERED,
                data={"matched": False},
                message="事件未通过过滤条件",
            )

    def validate_config(self, config: dict[str, Any]) -> bool:
        mode = config.get("mode", "all")
        if mode not in ("all", "any"):
            return False
        rules = config.get("rules", [])
        if not isinstance(rules, list):
            return False
        return True

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["all", "any"], "default": "all"},
                "rules": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "过滤规则列表，每项为 ConditionGroup 格式",
                },
            },
        }
