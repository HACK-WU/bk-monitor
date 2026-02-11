"""条件匹配器

支持 14 种操作符和嵌套逻辑组合的条件匹配。
"""

import re
from typing import Any

from framework.rule.condition import (
    Condition,
    ConditionGroup,
    LogicOperator,
    Operator,
)


def _resolve_field(data: dict[str, Any], field_path: str) -> Any:
    """解析嵌套字段路径，如 "labels.env" -> data["labels"]["env"]"""
    keys = field_path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list | tuple) and key.isdigit():
            idx = int(key)
            value = value[idx] if idx < len(value) else None
        else:
            return None
        if value is None:
            return None
    return value


class ConditionMatcher:
    """条件匹配器

    支持对字典数据进行条件匹配，包含 14 种操作符和 AND/OR/NOT 逻辑组合。
    """

    # 操作符 -> 匹配函数映射
    _OPERATORS = {}

    def __init__(self):
        self._register_operators()

    def _register_operators(self):
        """注册内置操作符"""
        self._OPERATORS = {
            Operator.EQ: self._op_eq,
            Operator.NEQ: self._op_neq,
            Operator.GT: self._op_gt,
            Operator.GTE: self._op_gte,
            Operator.LT: self._op_lt,
            Operator.LTE: self._op_lte,
            Operator.IN: self._op_in,
            Operator.NOT_IN: self._op_not_in,
            Operator.INCLUDE: self._op_include,
            Operator.EXCLUDE: self._op_exclude,
            Operator.REGEX: self._op_regex,
            Operator.STARTSWITH: self._op_startswith,
            Operator.ENDSWITH: self._op_endswith,
            Operator.EXISTS: self._op_exists,
        }

    def match(self, data: dict[str, Any], condition) -> bool:
        """执行条件匹配

        Args:
            data: 待匹配的数据字典
            condition: Condition 或 ConditionGroup 实例

        Returns:
            是否匹配
        """
        if isinstance(condition, ConditionGroup):
            return self._match_group(data, condition)
        elif isinstance(condition, Condition):
            return self._match_condition(data, condition)
        elif isinstance(condition, dict):
            # 兼容字典格式
            if "logic" in condition:
                return self._match_group(data, ConditionGroup.from_dict(condition))
            else:
                return self._match_condition(data, Condition.from_dict(condition))
        return False

    def _match_condition(self, data: dict[str, Any], condition: Condition) -> bool:
        """匹配单个条件"""
        # EXISTS 操作符特殊处理
        if condition.operator == Operator.EXISTS:
            actual = _resolve_field(data, condition.field)
            return self._op_exists(actual, condition.value)

        actual = _resolve_field(data, condition.field)
        op_func = self._OPERATORS.get(condition.operator)
        if op_func is None:
            raise ValueError(f"不支持的操作符: {condition.operator}")
        return op_func(actual, condition.value)

    def _match_group(self, data: dict[str, Any], group: ConditionGroup) -> bool:
        """匹配条件组"""
        if not group.conditions:
            return True

        if group.logic == LogicOperator.AND:
            return all(self.match(data, c) for c in group.conditions)
        elif group.logic == LogicOperator.OR:
            return any(self.match(data, c) for c in group.conditions)
        elif group.logic == LogicOperator.NOT:
            # NOT 对第一个条件取反
            return not self.match(data, group.conditions[0])

        return False

    # ===== 操作符实现 =====

    @staticmethod
    def _op_eq(actual: Any, expected: Any) -> bool:
        return actual == expected

    @staticmethod
    def _op_neq(actual: Any, expected: Any) -> bool:
        return actual != expected

    @staticmethod
    def _op_gt(actual: Any, expected: Any) -> bool:
        try:
            return actual > expected
        except TypeError:
            return False

    @staticmethod
    def _op_gte(actual: Any, expected: Any) -> bool:
        try:
            return actual >= expected
        except TypeError:
            return False

    @staticmethod
    def _op_lt(actual: Any, expected: Any) -> bool:
        try:
            return actual < expected
        except TypeError:
            return False

    @staticmethod
    def _op_lte(actual: Any, expected: Any) -> bool:
        try:
            return actual <= expected
        except TypeError:
            return False

    @staticmethod
    def _op_in(actual: Any, expected: Any) -> bool:
        """actual 在 expected 列表中"""
        if not isinstance(expected, list | tuple | set):
            return False
        return actual in expected

    @staticmethod
    def _op_not_in(actual: Any, expected: Any) -> bool:
        """actual 不在 expected 列表中"""
        if not isinstance(expected, list | tuple | set):
            return True
        return actual not in expected

    @staticmethod
    def _op_include(actual: Any, expected: Any) -> bool:
        """actual 包含 expected（字符串包含或列表包含）"""
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, list | tuple | set):
            return expected in actual
        return False

    @staticmethod
    def _op_exclude(actual: Any, expected: Any) -> bool:
        """actual 不包含 expected"""
        if isinstance(actual, str) and isinstance(expected, str):
            return expected not in actual
        if isinstance(actual, list | tuple | set):
            return expected not in actual
        return True

    @staticmethod
    def _op_regex(actual: Any, expected: Any) -> bool:
        """正则匹配"""
        if actual is None:
            return False
        try:
            return bool(re.search(str(expected), str(actual)))
        except re.error:
            return False

    @staticmethod
    def _op_startswith(actual: Any, expected: Any) -> bool:
        if actual is None:
            return False
        return str(actual).startswith(str(expected))

    @staticmethod
    def _op_endswith(actual: Any, expected: Any) -> bool:
        if actual is None:
            return False
        return str(actual).endswith(str(expected))

    @staticmethod
    def _op_exists(actual: Any, expected: Any) -> bool:
        """字段是否存在（expected=True 表示要求存在）"""
        exists = actual is not None
        return exists if expected else not exists
