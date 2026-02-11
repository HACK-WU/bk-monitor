"""FilterNode 单元测试"""

import unittest

from framework.pipeline.context import ProcessContext
from framework.processor.registry import ProcessorRegistry
from nodes.filter.filter_node import FilterNode


class TestFilterNode(unittest.TestCase):
    def setUp(self):
        self.registry = ProcessorRegistry()

    def _make_node(self, config):
        node = FilterNode()
        node.initialize(config)
        return node

    def test_no_rules_passes(self):
        """无规则时直接通过"""
        node = self._make_node({"rules": []})
        ctx = ProcessContext(event={"severity": 1})
        result = node.process(ctx)
        self.assertTrue(result.is_success)
        self.assertTrue(result.data["matched"])

    def test_all_mode_match(self):
        """all 模式 - 全部规则匹配"""
        node = self._make_node(
            {
                "mode": "all",
                "rules": [
                    {
                        "logic": "and",
                        "conditions": [
                            {"field": "severity", "operator": "gte", "value": 2},
                        ],
                    },
                    {
                        "logic": "and",
                        "conditions": [
                            {"field": "labels.env", "operator": "eq", "value": "production"},
                        ],
                    },
                ],
            }
        )
        ctx = ProcessContext(event={"severity": 3, "labels": {"env": "production"}})
        result = node.process(ctx)
        self.assertTrue(result.is_success)
        self.assertFalse(ctx.should_stop)

    def test_all_mode_no_match(self):
        """all 模式 - 部分规则不匹配"""
        node = self._make_node(
            {
                "mode": "all",
                "rules": [
                    {"logic": "and", "conditions": [{"field": "severity", "operator": "gte", "value": 5}]},
                ],
            }
        )
        ctx = ProcessContext(event={"severity": 2})
        result = node.process(ctx)
        self.assertTrue(result.is_filtered)
        self.assertTrue(ctx.should_stop)

    def test_any_mode_match(self):
        """any 模式 - 任意一条规则匹配"""
        node = self._make_node(
            {
                "mode": "any",
                "rules": [
                    {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 999}]},
                    {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 3}]},
                ],
            }
        )
        ctx = ProcessContext(event={"severity": 3})
        result = node.process(ctx)
        self.assertTrue(result.is_success)

    def test_any_mode_no_match(self):
        """any 模式 - 所有规则不匹配"""
        node = self._make_node(
            {
                "mode": "any",
                "rules": [
                    {"logic": "and", "conditions": [{"field": "severity", "operator": "eq", "value": 999}]},
                ],
            }
        )
        ctx = ProcessContext(event={"severity": 1})
        result = node.process(ctx)
        self.assertTrue(result.is_filtered)

    def test_validate_config(self):
        node = FilterNode()
        self.assertTrue(node.validate_config({"mode": "all", "rules": []}))
        self.assertTrue(node.validate_config({"mode": "any", "rules": []}))
        self.assertFalse(node.validate_config({"mode": "invalid"}))
        self.assertFalse(node.validate_config({"rules": "not_a_list"}))


if __name__ == "__main__":
    unittest.main()
