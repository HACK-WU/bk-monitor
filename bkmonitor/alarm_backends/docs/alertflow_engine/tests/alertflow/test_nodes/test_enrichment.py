"""EnrichmentNode 单元测试"""

import unittest

from framework.pipeline.context import ProcessContext
from nodes.enrichment.enrichment_node import EnrichmentNode


class TestEnrichmentNode(unittest.TestCase):
    def _make_node(self, config):
        node = EnrichmentNode()
        node.initialize(config)
        return node

    def test_static_enrichment(self):
        """静态值注入"""
        node = self._make_node(
            {
                "enrichments": [
                    {"type": "static", "config": {"static_values": {"team": "ops", "region": "cn"}}},
                ],
            }
        )
        ctx = ProcessContext(event={"severity": 3})
        result = node.process(ctx)

        self.assertTrue(result.is_success)
        self.assertEqual(ctx.event["team"], "ops")
        self.assertEqual(ctx.event["region"], "cn")

    def test_custom_mapping(self):
        """自定义字段映射"""
        node = self._make_node(
            {
                "enrichments": [
                    {"type": "custom", "config": {"mapping": {"env": "labels.environment"}}},
                ],
            }
        )
        ctx = ProcessContext(event={"labels": {"environment": "production"}})
        result = node.process(ctx)

        self.assertTrue(result.is_success)
        self.assertEqual(ctx.event["env"], "production")

    def test_tag_enrichment(self):
        """标签补充"""
        node = self._make_node(
            {
                "enrichments": [
                    {"type": "tag", "config": {"tags": {"priority": "high", "source": "monitor"}}},
                ],
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)

        self.assertTrue(result.is_success)
        self.assertEqual(ctx.event["tags"]["priority"], "high")

    def test_fallback_values(self):
        """降级默认值"""
        node = self._make_node(
            {
                "enrichments": [],
                "fallback_values": {"team": "unknown", "region": "default"},
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)

        self.assertEqual(ctx.event["team"], "unknown")
        self.assertEqual(ctx.event["region"], "default")

    def test_multiple_enrichments(self):
        """多个丰富化类型组合"""
        node = self._make_node(
            {
                "enrichments": [
                    {"type": "static", "config": {"static_values": {"team": "ops"}}},
                    {"type": "tag", "config": {"tags": {"level": "critical"}}},
                ],
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)

        self.assertEqual(ctx.event["team"], "ops")
        self.assertEqual(ctx.event["tags"]["level"], "critical")

    def test_unknown_type_skipped(self):
        """未知丰富化类型被跳过"""
        node = self._make_node(
            {
                "enrichments": [
                    {"type": "nonexistent", "config": {}},
                ],
            }
        )
        ctx = ProcessContext(event={})
        result = node.process(ctx)
        self.assertTrue(result.is_success)


if __name__ == "__main__":
    unittest.main()
