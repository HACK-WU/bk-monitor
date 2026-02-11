"""条件定义

定义操作符枚举、逻辑组合方式和条件数据结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Operator(str, Enum):
    """条件操作符"""

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    INCLUDE = "include"
    EXCLUDE = "exclude"
    REGEX = "regex"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    EXISTS = "exists"


class LogicOperator(str, Enum):
    """逻辑组合操作符"""

    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class Condition:
    """单个条件表达式

    Attributes:
        field: 匹配字段路径（支持点分隔，如 "labels.env"）
        operator: 操作符
        value: 期望值
    """

    field: str
    operator: Operator
    value: Any

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Condition":
        return cls(
            field=data["field"],
            operator=Operator(data["operator"]),
            value=data["value"],
        )


@dataclass
class ConditionGroup:
    """条件组 - 支持逻辑组合和嵌套

    Attributes:
        logic: 逻辑操作符（AND/OR/NOT）
        conditions: 条件列表（可包含 Condition 或嵌套的 ConditionGroup）
    """

    logic: LogicOperator = LogicOperator.AND
    conditions: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "logic": self.logic.value,
            "conditions": [c.to_dict() if hasattr(c, "to_dict") else c for c in self.conditions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConditionGroup":
        logic = LogicOperator(data.get("logic", "and"))
        conditions = []
        for item in data.get("conditions", []):
            if "logic" in item:
                conditions.append(cls.from_dict(item))
            else:
                conditions.append(Condition.from_dict(item))
        return cls(logic=logic, conditions=conditions)
