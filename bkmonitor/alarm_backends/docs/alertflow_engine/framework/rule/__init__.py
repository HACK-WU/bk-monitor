"""规则引擎模块

提供基于 jsonLogic 的条件匹配能力。
"""

from framework.rule.condition import Condition, LogicOperator, Operator
from framework.rule.matcher import ConditionMatcher
from framework.rule.engine import RuleEngine

__all__ = [
    "Condition",
    "LogicOperator",
    "Operator",
    "ConditionMatcher",
    "RuleEngine",
]
