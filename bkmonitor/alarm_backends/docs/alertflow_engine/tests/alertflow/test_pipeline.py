"""ProcessContext 与 Pipeline 执行测试"""

import unittest
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.pipeline.executor import NodeExecution, PipelineExecutor
from framework.processor.base import BaseProcessor, ProcessResult, ProcessStatus
from framework.processor.registry import ProcessorRegistry
from framework.pipeline.orchestrator import PipelineOrchestrator


# ===== Mock 处理器 =====


class PassThroughProcessor(BaseProcessor):
    name = "pass_through"
    version = "1.0.0"

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config

    def process(self, context: ProcessContext) -> ProcessResult:
        context.variables["pass_through"] = True
        return ProcessResult(status=ProcessStatus.SUCCESS, data={"passed": True})


class StopProcessor(BaseProcessor):
    name = "stop_processor"
    version = "1.0.0"

    def initialize(self, config: dict[str, Any]) -> None:
        pass

    def process(self, context: ProcessContext) -> ProcessResult:
        context.stop("手动终止")
        return ProcessResult(status=ProcessStatus.FILTERED, message="stopped")


class ErrorProcessor(BaseProcessor):
    name = "error_processor"
    version = "1.0.0"

    def initialize(self, config: dict[str, Any]) -> None:
        pass

    def process(self, context: ProcessContext) -> ProcessResult:
        raise RuntimeError("模拟处理异常")


class CounterProcessor(BaseProcessor):
    name = "counter"
    version = "1.0.0"
    call_count = 0

    def initialize(self, config: dict[str, Any]) -> None:
        CounterProcessor.call_count = 0

    def process(self, context: ProcessContext) -> ProcessResult:
        CounterProcessor.call_count += 1
        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"count": CounterProcessor.call_count},
        )


# ===== 测试 =====


class TestProcessContext(unittest.TestCase):
    """ProcessContext 测试"""

    def test_default_values(self):
        ctx = ProcessContext()
        self.assertIsNotNone(ctx.trace_id)
        self.assertEqual(ctx.pipeline_id, "")
        self.assertEqual(ctx.event, {})
        self.assertFalse(ctx.should_stop)
        self.assertEqual(ctx.executed_nodes, [])

    def test_upstream_output(self):
        ctx = ProcessContext()
        ctx.set_upstream_output("node_1", {"result": "ok"})
        self.assertEqual(ctx.get_upstream_output("node_1"), {"result": "ok"})
        self.assertIsNone(ctx.get_upstream_output("nonexistent"))

    def test_upstream_field_nested(self):
        ctx = ProcessContext()
        ctx.set_upstream_output("node_1", {"result": {"matched": True, "count": 5}})
        self.assertTrue(ctx.get_upstream_field("node_1", "result.matched"))
        self.assertEqual(ctx.get_upstream_field("node_1", "result.count"), 5)
        self.assertIsNone(ctx.get_upstream_field("node_1", "result.nonexistent"))

    def test_stop(self):
        ctx = ProcessContext()
        ctx.stop("test reason")
        self.assertTrue(ctx.should_stop)
        self.assertEqual(ctx.error, "test reason")

    def test_record_node_execution(self):
        ctx = ProcessContext()
        ctx.record_node_execution("node_1")
        ctx.record_node_execution("node_2")
        self.assertEqual(ctx.executed_nodes, ["node_1", "node_2"])

    def test_serialization(self):
        ctx = ProcessContext(
            pipeline_id="test_pipeline",
            event={"severity": 3},
            variables={"key": "value"},
        )
        d = ctx.to_dict()
        self.assertEqual(d["pipeline_id"], "test_pipeline")

        json_str = ctx.to_json()
        ctx2 = ProcessContext.from_json(json_str)
        self.assertEqual(ctx2.pipeline_id, "test_pipeline")
        self.assertEqual(ctx2.event["severity"], 3)

    def test_clone(self):
        ctx = ProcessContext(event={"a": 1})
        ctx2 = ctx.clone()
        ctx2.event["a"] = 999
        self.assertEqual(ctx.event["a"], 1)

    def test_elapsed_ms(self):
        ctx = ProcessContext()
        self.assertGreaterEqual(ctx.elapsed_ms, 0)


class TestPipelineExecutor(unittest.TestCase):
    """PipelineExecutor 测试"""

    def setUp(self):
        self.executor = PipelineExecutor()

    def _make_node(self, processor, node_id="node_1", error_strategy="stop", condition=None):
        processor.initialize({})
        return NodeExecution(
            node_id=node_id,
            processor=processor,
            config={
                "error_strategy": error_strategy,
                "condition": condition,
                "enabled": True,
            },
        )

    def test_execute_single_node(self):
        node = self._make_node(PassThroughProcessor(), "pass_1")
        ctx = ProcessContext(event={"test": True})
        result = self.executor.execute([node], ctx)
        self.assertTrue(result.variables.get("pass_through"))
        self.assertIn("pass_1", result.executed_nodes)

    def test_execute_multiple_nodes(self):
        node1 = self._make_node(PassThroughProcessor(), "pass_1")
        CounterProcessor.call_count = 0
        counter = CounterProcessor()
        counter.initialize({})
        node2 = NodeExecution("counter_1", counter, {"error_strategy": "stop", "enabled": True})

        ctx = ProcessContext()
        result = self.executor.execute([node1, node2], ctx)
        self.assertEqual(len(result.executed_nodes), 2)

    def test_stop_propagation(self):
        """测试 should_stop 终止后续节点"""
        stop_node = self._make_node(StopProcessor(), "stop_1")
        pass_node = self._make_node(PassThroughProcessor(), "pass_1")

        ctx = ProcessContext()
        result = self.executor.execute([stop_node, pass_node], ctx)
        self.assertTrue(result.should_stop)
        self.assertIn("stop_1", result.executed_nodes)
        self.assertNotIn("pass_1", result.executed_nodes)

    def test_error_strategy_stop(self):
        """测试错误策略: stop"""
        error_node = self._make_node(ErrorProcessor(), "error_1", "stop")
        pass_node = self._make_node(PassThroughProcessor(), "pass_1")

        ctx = ProcessContext()
        result = self.executor.execute([error_node, pass_node], ctx)
        self.assertTrue(result.should_stop)

    def test_error_strategy_ignore(self):
        """测试错误策略: ignore"""
        error_node = self._make_node(ErrorProcessor(), "error_1", "ignore")
        pass_node = self._make_node(PassThroughProcessor(), "pass_1")

        ctx = ProcessContext()
        result = self.executor.execute([error_node, pass_node], ctx)
        # ignore 策略下，后续节点应继续执行
        self.assertIn("pass_1", result.executed_nodes)

    def test_disabled_node_skipped(self):
        """测试禁用节点被跳过"""
        proc = PassThroughProcessor()
        proc.initialize({})
        node = NodeExecution("disabled_1", proc, {"enabled": False})

        ctx = ProcessContext()
        result = self.executor.execute([node], ctx)
        self.assertNotIn("disabled_1", result.executed_nodes)

    def test_conditional_execution(self):
        """测试条件执行"""
        node = self._make_node(
            PassThroughProcessor(),
            "cond_1",
            condition={
                "logic": "and",
                "conditions": [
                    {"field": "severity", "operator": "gte", "value": 3},
                ],
            },
        )
        # 满足条件
        ctx = ProcessContext(event={"severity": 3})
        result = self.executor.execute([node], ctx)
        self.assertIn("cond_1", result.executed_nodes)

        # 不满足条件
        ctx2 = ProcessContext(event={"severity": 1})
        result2 = self.executor.execute([node], ctx2)
        self.assertNotIn("cond_1", result2.executed_nodes)

    def test_upstream_output(self):
        """测试上游输出传递"""
        node = self._make_node(PassThroughProcessor(), "pass_1")
        ctx = ProcessContext()
        result = self.executor.execute([node], ctx)
        self.assertIn("pass_1", result.upstream)
        self.assertEqual(result.upstream["pass_1"]["passed"], True)


class TestPipelineOrchestrator(unittest.TestCase):
    """PipelineOrchestrator 测试"""

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(PassThroughProcessor)
        self.registry.register(CounterProcessor)
        self.orchestrator = PipelineOrchestrator(registry=self.registry)

    def tearDown(self):
        self.registry.clear()

    def _make_config(self):
        return {
            "id": "test_pipeline",
            "name": "测试 Pipeline",
            "version": "1.0.0",
            "scenario": "alert",
            "enabled": True,
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [
                        {"id": "pass_1", "type": "pass_through", "config": {}},
                        {"id": "counter_1", "type": "counter", "config": {}},
                    ],
                },
            ],
        }

    def test_load_and_execute(self):
        config = self._make_config()
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("test_pipeline", event={"test": True})

        self.assertIn("pass_1", ctx.executed_nodes)
        self.assertIn("counter_1", ctx.executed_nodes)
        self.assertIn("total_elapsed_ms", ctx.metrics)

    def test_load_disabled_pipeline_raises(self):
        config = self._make_config()
        config["enabled"] = False
        self.orchestrator.load_pipeline(config)

        with self.assertRaises(RuntimeError):
            self.orchestrator.execute("test_pipeline")

    def test_execute_unloaded_raises(self):
        with self.assertRaises(KeyError):
            self.orchestrator.execute("nonexistent")

    def test_list_pipelines(self):
        self.orchestrator.load_pipeline(self._make_config())
        pipelines = self.orchestrator.list_pipelines()
        self.assertIn("test_pipeline", pipelines)
        self.assertEqual(pipelines["test_pipeline"]["version"], "1.0.0")

    def test_unload_pipeline(self):
        self.orchestrator.load_pipeline(self._make_config())
        self.orchestrator.unload_pipeline("test_pipeline")
        self.assertIsNone(self.orchestrator.get_pipeline("test_pipeline"))

    def test_multi_stage_execution(self):
        config = {
            "id": "multi_stage",
            "name": "多阶段 Pipeline",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [{"id": "pass_1", "type": "pass_through", "config": {}}],
                },
                {
                    "name": "stage_2",
                    "processors": [{"id": "counter_1", "type": "counter", "config": {}}],
                },
            ],
        }
        self.orchestrator.load_pipeline(config)
        ctx = self.orchestrator.execute("multi_stage", event={})
        self.assertEqual(len(ctx.executed_nodes), 2)


if __name__ == "__main__":
    unittest.main()
