"""规则引擎入口

提供高级 API，支持加载规则配置并执行匹配。
"""

import logging
from typing import Any

from framework.rule.condition import Condition, ConditionGroup, LogicOperator
from framework.rule.matcher import ConditionMatcher

logger = logging.getLogger(__name__)


class RuleEngine:
    """规则引擎

    提供统一的规则加载和匹配入口，支持：
    - 从字典配置加载条件
    - 对数据执行条件匹配
    - 批量规则评估
    """

    def __init__(self):
        self._matcher = ConditionMatcher()

    def evaluate(self, data: dict[str, Any], rule: dict[str, Any]) -> bool:
        """评估单条规则

        Args:
            data: 待匹配数据
            rule: 规则配置，格式为 ConditionGroup 字典

        Returns:
            是否匹配

        规则格式示例:
        {
            "logic": "and",
            "conditions": [
                {"field": "severity", "operator": "gte", "value": 2},
                {"field": "labels.env", "operator": "eq", "value": "production"}
            ]
        }
        """
        condition = self._parse_rule(rule)
        return self._matcher.match(data, condition)

    def evaluate_any(self, data: dict[str, Any], rules: list[dict[str, Any]]) -> bool:
        """评估多条规则，任意一条匹配即返回 True"""
        return any(self.evaluate(data, rule) for rule in rules)

    def evaluate_all(self, data: dict[str, Any], rules: list[dict[str, Any]]) -> bool:
        """评估多条规则，全部匹配才返回 True"""
        return all(self.evaluate(data, rule) for rule in rules)

    def find_matching_rules(self, data: dict[str, Any], rules: list[dict[str, Any]]) -> list[int]:
        """找出所有匹配的规则索引"""
        return [i for i, rule in enumerate(rules) if self.evaluate(data, rule)]

    def _parse_rule(self, rule: dict[str, Any]) -> Any:
        """解析规则配置为条件对象"""
        if "logic" in rule:
            return ConditionGroup.from_dict(rule)
        elif "field" in rule:
            return Condition.from_dict(rule)
        else:
            # 简单键值对格式: {"severity": 2} -> eq 条件
            conditions = [Condition(field=k, operator="eq", value=v) for k, v in rule.items()]
            if len(conditions) == 1:
                return conditions[0]
            return ConditionGroup(logic=LogicOperator.AND, conditions=conditions)
