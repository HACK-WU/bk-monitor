"""端到端集成测试

验证从事件输入到通知输出的全链路 Pipeline 执行。
"""

import unittest

from framework.pipeline.context import ProcessContext
from framework.pipeline.orchestrator import PipelineOrchestrator
from framework.processor.base import BaseProcessor
from framework.processor.registry import ProcessorRegistry
from nodes.filter.filter_node import FilterNode
from nodes.enrichment.enrichment_node import EnrichmentNode
from nodes.shield.shield_node import ShieldNode
from nodes.notification.notification_node import NotificationNode


class TestScenario1StandardAlertFlow(unittest.TestCase):
    """场景1：标准告警流程

    事件输入 → 丰富化 → 过滤 → 屏蔽检查 → 通知
    """

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        # 注册所有需要的节点（部分节点通过 @register_processor 自动注册，
        # 但因为测试隔离需要清空后重新注册）
        self.registry.register(FilterNode)
        self.registry.register(EnrichmentNode)
        self.registry.register(ShieldNode)
        self.registry.register(NotificationNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_standard_flow(self):
        """完整告警流程：丰富化 → 过滤 → 屏蔽检查 → 通知"""
        config = {
            "id": "standard_alert",
            "name": "标准告警流程",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "丰富化",
                    "processors": [
                        {
                            "id": "enrich_1",
                            "type": "enrichment",
                            "config": {
                                "enrichments": [
                                    {
                                        "type": "static",
                                        "config": {"static_values": {"team": "ops"}},
                                    },
                                ],
                            },
                        },
                    ],
                },
                {
                    "name": "过滤",
                    "processors": [
                        {
                            "id": "filter_1",
                            "type": "filter",
                            "config": {
                                "mode": "all",
                                "rules": [
                                    {
                                        "logic": "and",
                                        "conditions": [
                                            {"field": "severity", "operator": "gte", "value": 2},
                                        ],
                                    },
                                ],
                            },
                        },
                    ],
                },
                {
                    "name": "屏蔽检查",
                    "processors": [
                        {
                            "id": "shield_1",
                            "type": "shield",
                            "config": {"shield_rules": []},
                        },
                    ],
                },
                {
                    "name": "通知",
                    "processors": [
                        {
                            "id": "notify_1",
                            "type": "notification",
                            "config": {
                                "channels": [
                                    {"type": "email", "receivers": ["admin@example.com"]},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute(
            "standard_alert",
            event={
                "severity": 3,
                "name": "disk_usage_high",
                "ip": "10.0.0.1",
            },
        )

        # 验证：所有 4 个节点都应执行
        self.assertEqual(len(ctx.executed_nodes), 4)
        self.assertIn("enrich_1", ctx.executed_nodes)
        self.assertIn("filter_1", ctx.executed_nodes)
        self.assertIn("shield_1", ctx.executed_nodes)
        self.assertIn("notify_1", ctx.executed_nodes)

        # 验证：丰富化数据已注入
        self.assertEqual(ctx.event["team"], "ops")

        # 验证：Pipeline 未被终止
        self.assertFalse(ctx.should_stop)

        # 验证：trace_id 和性能指标存在
        self.assertIsNotNone(ctx.trace_id)
        self.assertIn("total_elapsed_ms", ctx.metrics)


class TestScenario2FilteredEvent(unittest.TestCase):
    """场景2：被过滤的事件

    事件输入 → 过滤(不匹配) → Pipeline 终止
    """

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(FilterNode)
        self.registry.register(NotificationNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_event_filtered(self):
        config = {
            "id": "filtered_flow",
            "name": "过滤测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "过滤",
                    "processors": [
                        {
                            "id": "filter_1",
                            "type": "filter",
                            "config": {
                                "mode": "all",
                                "rules": [
                                    {
                                        "logic": "and",
                                        "conditions": [
                                            {"field": "severity", "operator": "gte", "value": 5},
                                        ],
                                    },
                                ],
                            },
                        },
                    ],
                },
                {
                    "name": "通知",
                    "processors": [
                        {
                            "id": "notify_1",
                            "type": "notification",
                            "config": {
                                "channels": [
                                    {"type": "email", "receivers": ["admin@example.com"]},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("filtered_flow", event={"severity": 2})

        # 验证：过滤节点执行了
        self.assertIn("filter_1", ctx.executed_nodes)
        # 验证：通知节点未执行（被终止）
        self.assertNotIn("notify_1", ctx.executed_nodes)
        # 验证：Pipeline 已终止
        self.assertTrue(ctx.should_stop)


class TestScenario3ConditionalExecution(unittest.TestCase):
    """场景3：条件执行

    根据事件属性决定是否执行某些节点
    """

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(EnrichmentNode)
        self.registry.register(NotificationNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_conditional_node_executed(self):
        """条件满足时节点执行"""
        config = {
            "id": "conditional_flow",
            "name": "条件执行测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "条件通知",
                    "processors": [
                        {
                            "id": "notify_critical",
                            "type": "notification",
                            "condition": {
                                "logic": "and",
                                "conditions": [
                                    {"field": "severity", "operator": "gte", "value": 3},
                                ],
                            },
                            "config": {
                                "channels": [
                                    {"type": "email", "receivers": ["critical@example.com"]},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)

        # severity=3，条件满足
        ctx = self.orchestrator.execute("conditional_flow", event={"severity": 3})
        self.assertIn("notify_critical", ctx.executed_nodes)

    def test_conditional_node_skipped(self):
        """条件不满足时节点跳过"""
        config = {
            "id": "conditional_skip",
            "name": "条件跳过测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "条件通知",
                    "processors": [
                        {
                            "id": "notify_critical",
                            "type": "notification",
                            "condition": {
                                "logic": "and",
                                "conditions": [
                                    {"field": "severity", "operator": "gte", "value": 3},
                                ],
                            },
                            "config": {
                                "channels": [
                                    {"type": "email", "receivers": ["critical@example.com"]},
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)

        # severity=1，条件不满足
        ctx = self.orchestrator.execute("conditional_skip", event={"severity": 1})
        self.assertNotIn("notify_critical", ctx.executed_nodes)


class TestScenario4ErrorHandling(unittest.TestCase):
    """场景4：节点异常降级

    某节点执行异常 → 错误策略触发 → 降级/停止
    """

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()

        # 注册一个会抛异常的处理器
        class BrokenProcessor(BaseProcessor):
            name = "broken"
            version = "1.0.0"

            def initialize(self, config):
                pass

            def process(self, context):
                raise RuntimeError("模拟异常")

        self.registry.register(BrokenProcessor)
        self.registry.register(NotificationNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_error_strategy_stop(self):
        """stop 策略终止 Pipeline"""
        config = {
            "id": "error_stop",
            "name": "错误停止测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage",
                    "processors": [
                        {
                            "id": "broken_1",
                            "type": "broken",
                            "error_strategy": "stop",
                            "config": {},
                        },
                        {
                            "id": "notify_1",
                            "type": "notification",
                            "config": {"channels": []},
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("error_stop", event={})
        self.assertTrue(ctx.should_stop)
        self.assertNotIn("notify_1", ctx.executed_nodes)

    def test_error_strategy_ignore(self):
        """ignore 策略忽略错误，继续执行"""
        config = {
            "id": "error_ignore",
            "name": "错误忽略测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage",
                    "processors": [
                        {
                            "id": "broken_1",
                            "type": "broken",
                            "error_strategy": "ignore",
                            "config": {},
                        },
                        {
                            "id": "notify_1",
                            "type": "notification",
                            "config": {"channels": [{"type": "email", "receivers": ["a@b.com"]}]},
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("error_ignore", event={})
        # ignore 后继续执行
        self.assertIn("notify_1", ctx.executed_nodes)


class TestScenario5UpstreamOutput(unittest.TestCase):
    """场景5：上游输出传递

    验证节点间通过 upstream 传递数据
    """

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(FilterNode)
        self.registry.register(EnrichmentNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_upstream_data_flow(self):
        config = {
            "id": "upstream_test",
            "name": "上游输出测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [
                        {
                            "id": "enrich_1",
                            "type": "enrichment",
                            "config": {
                                "enrichments": [
                                    {"type": "static", "config": {"static_values": {"team": "ops"}}},
                                ],
                            },
                        },
                    ],
                },
                {
                    "name": "stage_2",
                    "processors": [
                        {
                            "id": "filter_1",
                            "type": "filter",
                            "config": {
                                "mode": "all",
                                "rules": [
                                    {
                                        "logic": "and",
                                        "conditions": [
                                            {"field": "severity", "operator": "gte", "value": 1},
                                        ],
                                    },
                                ],
                            },
                        },
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("upstream_test", event={"severity": 3})

        # 验证 enrich_1 的输出存在于 upstream
        self.assertIn("enrich_1", ctx.upstream)
        self.assertEqual(ctx.upstream["enrich_1"]["team"], "ops")

        # 验证 filter_1 的输出存在于 upstream
        self.assertIn("filter_1", ctx.upstream)
        self.assertTrue(ctx.upstream["filter_1"]["matched"])

        # 验证所有节点都已执行
        self.assertEqual(len(ctx.executed_nodes), 2)


class TestTraceIdPropagation(unittest.TestCase):
    """trace_id 全链路追踪测试"""

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(EnrichmentNode)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_trace_id_consistent(self):
        """验证 trace_id 在整个 Pipeline 执行中保持一致"""
        config = {
            "id": "trace_test",
            "name": "追踪测试",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage",
                    "processors": [
                        {"id": "enrich_1", "type": "enrichment", "config": {"enrichments": []}},
                    ],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)

        # 自定义 trace_id
        ctx = ProcessContext(trace_id="custom_trace_123", event={})
        result = self.orchestrator.execute("trace_test", context=ctx)
        self.assertEqual(result.trace_id, "custom_trace_123")


if __name__ == "__main__":
    unittest.main()
