"""规则引擎单元测试"""

import unittest

from framework.rule.condition import Condition, ConditionGroup, LogicOperator, Operator
from framework.rule.matcher import ConditionMatcher
from framework.rule.engine import RuleEngine


class TestConditionModel(unittest.TestCase):
    """条件数据结构测试"""

    def test_condition_to_dict(self):
        c = Condition(field="severity", operator=Operator.GTE, value=2)
        d = c.to_dict()
        self.assertEqual(d["field"], "severity")
        self.assertEqual(d["operator"], "gte")
        self.assertEqual(d["value"], 2)

    def test_condition_from_dict(self):
        c = Condition.from_dict({"field": "env", "operator": "eq", "value": "prod"})
        self.assertEqual(c.field, "env")
        self.assertEqual(c.operator, Operator.EQ)

    def test_condition_group_nested(self):
        group = ConditionGroup.from_dict(
            {
                "logic": "or",
                "conditions": [
                    {"field": "a", "operator": "eq", "value": 1},
                    {
                        "logic": "and",
                        "conditions": [
                            {"field": "b", "operator": "gt", "value": 10},
                            {"field": "c", "operator": "lt", "value": 100},
                        ],
                    },
                ],
            }
        )
        self.assertEqual(group.logic, LogicOperator.OR)
        self.assertEqual(len(group.conditions), 2)
        self.assertIsInstance(group.conditions[1], ConditionGroup)


class TestConditionMatcher(unittest.TestCase):
    """ConditionMatcher 操作符测试"""

    def setUp(self):
        self.matcher = ConditionMatcher()
        self.data = {
            "severity": 3,
            "name": "disk_full",
            "ip": "10.0.0.1",
            "labels": {"env": "production", "team": "ops"},
            "tags": ["critical", "disk"],
        }

    def test_eq(self):
        c = Condition(field="severity", operator=Operator.EQ, value=3)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_neq(self):
        c = Condition(field="severity", operator=Operator.NEQ, value=1)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_gt(self):
        c = Condition(field="severity", operator=Operator.GT, value=2)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_gte(self):
        c = Condition(field="severity", operator=Operator.GTE, value=3)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_lt(self):
        c = Condition(field="severity", operator=Operator.LT, value=5)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_lte(self):
        c = Condition(field="severity", operator=Operator.LTE, value=3)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_in(self):
        c = Condition(field="severity", operator=Operator.IN, value=[1, 2, 3])
        self.assertTrue(self.matcher.match(self.data, c))

    def test_not_in(self):
        c = Condition(field="severity", operator=Operator.NOT_IN, value=[1, 2])
        self.assertTrue(self.matcher.match(self.data, c))

    def test_include_string(self):
        c = Condition(field="name", operator=Operator.INCLUDE, value="disk")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_include_list(self):
        c = Condition(field="tags", operator=Operator.INCLUDE, value="critical")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_exclude(self):
        c = Condition(field="name", operator=Operator.EXCLUDE, value="memory")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_regex(self):
        c = Condition(field="ip", operator=Operator.REGEX, value=r"^10\.\d+\.\d+\.\d+$")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_startswith(self):
        c = Condition(field="ip", operator=Operator.STARTSWITH, value="10.")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_endswith(self):
        c = Condition(field="name", operator=Operator.ENDSWITH, value="_full")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_exists_true(self):
        c = Condition(field="severity", operator=Operator.EXISTS, value=True)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_exists_false(self):
        c = Condition(field="nonexistent", operator=Operator.EXISTS, value=False)
        self.assertTrue(self.matcher.match(self.data, c))

    def test_nested_field(self):
        c = Condition(field="labels.env", operator=Operator.EQ, value="production")
        self.assertTrue(self.matcher.match(self.data, c))

    def test_and_group(self):
        group = ConditionGroup(
            logic=LogicOperator.AND,
            conditions=[
                Condition(field="severity", operator=Operator.GTE, value=2),
                Condition(field="labels.env", operator=Operator.EQ, value="production"),
            ],
        )
        self.assertTrue(self.matcher.match(self.data, group))

    def test_or_group(self):
        group = ConditionGroup(
            logic=LogicOperator.OR,
            conditions=[
                Condition(field="severity", operator=Operator.EQ, value=999),
                Condition(field="labels.env", operator=Operator.EQ, value="production"),
            ],
        )
        self.assertTrue(self.matcher.match(self.data, group))

    def test_not_group(self):
        group = ConditionGroup(
            logic=LogicOperator.NOT,
            conditions=[
                Condition(field="severity", operator=Operator.EQ, value=999),
            ],
        )
        self.assertTrue(self.matcher.match(self.data, group))

    def test_dict_format(self):
        """测试字典格式的条件匹配"""
        cond_dict = {"field": "severity", "operator": "gte", "value": 2}
        self.assertTrue(self.matcher.match(self.data, cond_dict))

    def test_dict_group_format(self):
        group_dict = {
            "logic": "and",
            "conditions": [
                {"field": "severity", "operator": "gte", "value": 2},
                {"field": "labels.env", "operator": "eq", "value": "production"},
            ],
        }
        self.assertTrue(self.matcher.match(self.data, group_dict))


class TestRuleEngine(unittest.TestCase):
    """RuleEngine 测试"""

    def setUp(self):
        self.engine = RuleEngine()
        self.data = {
            "severity": 3,
            "labels": {"env": "production"},
            "ip": "10.0.0.1",
        }

    def test_evaluate_single_rule(self):
        rule = {
            "logic": "and",
            "conditions": [
                {"field": "severity", "operator": "gte", "value": 2},
            ],
        }
        self.assertTrue(self.engine.evaluate(self.data, rule))

    def test_evaluate_any(self):
        rules = [
            {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 999}]},
            {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 3}]},
        ]
        self.assertTrue(self.engine.evaluate_any(self.data, rules))

    def test_evaluate_all(self):
        rules = [
            {"logic": "and", "conditions": [{"field": "severity", "operator": "gte", "value": 1}]},
            {"logic": "and", "conditions": [{"field": "severity", "operator": "lte", "value": 5}]},
        ]
        self.assertTrue(self.engine.evaluate_all(self.data, rules))

    def test_find_matching_rules(self):
        rules = [
            {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 999}]},
            {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 3}]},
            {"logic": "and", "conditions": [{"field": "severity", "operator": "gte", "value": 1}]},
        ]
        matched = self.engine.find_matching_rules(self.data, rules)
        self.assertEqual(matched, [1, 2])


if __name__ == "__main__":
    unittest.main()
