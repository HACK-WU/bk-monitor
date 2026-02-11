"""Shield 屏蔽节点

基于时间范围和维度匹配的告警屏蔽。
"""

import logging
from datetime import datetime
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from framework.rule.engine import RuleEngine
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


@register_processor
class ShieldNode(BaseNode):
    """屏蔽节点

    从配置中加载屏蔽规则，支持：
    1. 时间范围屏蔽：在指定时间段内屏蔽告警
    2. 维度匹配屏蔽：匹配指定维度条件的告警被屏蔽

    配置示例:
    {
        "shield_rules": [
            {
                "id": "shield_001",
                "type": "time_range",
                "begin_time": "2024-01-01 00:00:00",
                "end_time": "2024-01-02 00:00:00",
                "description": "维护窗口"
            },
            {
                "id": "shield_002",
                "type": "dimension",
                "conditions": {
                    "logic": "and",
                    "conditions": [
                        {"field": "labels.env", "operator": "eq", "value": "staging"}
                    ]
                }
            }
        ]
    }
    """

    name = "shield"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._shield_rules = config.get("shield_rules", [])
        self._rule_engine = RuleEngine()

    def process(self, context: ProcessContext) -> ProcessResult:
        for rule in self._shield_rules:
            shielded, reason = self._check_rule(rule, context)
            if shielded:
                logger.info(
                    "[%s] 事件被屏蔽 (rule=%s, reason=%s)",
                    context.trace_id,
                    rule.get("id", ""),
                    reason,
                )
                context.stop(f"事件被屏蔽: {reason}")
                return ProcessResult(
                    status=ProcessStatus.FILTERED,
                    data={"shielded": True, "shield_rule_id": rule.get("id"), "reason": reason},
                    message=reason,
                )

        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"shielded": False},
        )

    def _check_rule(self, rule: dict[str, Any], context: ProcessContext) -> tuple:
        """检查单条屏蔽规则，返回 (是否屏蔽, 原因)"""
        rule_type = rule.get("type", "dimension")

        if rule_type == "time_range":
            return self._check_time_range(rule)
        elif rule_type == "dimension":
            return self._check_dimension(rule, context)
        return False, ""

    def _check_time_range(self, rule: dict[str, Any]) -> tuple:
        """时间范围屏蔽"""
        now = datetime.now()
        begin_str = rule.get("begin_time", "")
        end_str = rule.get("end_time", "")

        try:
            begin = datetime.strptime(begin_str, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
            if begin <= now <= end:
                return True, f"时间范围屏蔽 [{begin_str} ~ {end_str}]"
        except (ValueError, TypeError):
            logger.warning("屏蔽规则时间格式错误: %s ~ %s", begin_str, end_str)

        return False, ""

    def _check_dimension(self, rule: dict[str, Any], context: ProcessContext) -> tuple:
        """维度匹配屏蔽"""
        conditions = rule.get("conditions")
        if not conditions:
            return False, ""

        data = {**context.event}
        if context.alert:
            data["alert"] = context.alert

        if self._rule_engine.evaluate(data, conditions):
            return True, f"维度匹配屏蔽 (rule={rule.get('id', '')})"
        return False, ""

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shield_rules": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"type": "string", "enum": ["time_range", "dimension"]},
                            "begin_time": {"type": "string"},
                            "end_time": {"type": "string"},
                            "conditions": {"type": "object"},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
        }
