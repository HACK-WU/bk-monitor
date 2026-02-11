"""处理器框架单元测试"""

import unittest
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import BaseProcessor, ProcessResult, ProcessStatus
from framework.processor.registry import ProcessorRegistry, register_processor
from framework.processor.factory import ProcessorFactory


class MockProcessor(BaseProcessor):
    """测试用 Mock 处理器"""

    name = "mock_processor"
    version = "1.0.0"

    def __init__(self):
        self._config = {}
        self._initialized = False

    def initialize(self, config: dict[str, Any]) -> None:
        self._config = config
        self._initialized = True

    def process(self, context: ProcessContext) -> ProcessResult:
        context.variables["mock_executed"] = True
        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data={"message": "mock processed"},
        )

    def validate_config(self, config: dict[str, Any]) -> bool:
        return True


class MockProcessorV2(BaseProcessor):
    """测试用 v2 Mock 处理器"""

    name = "mock_processor"
    version = "2.0.0"

    def initialize(self, config: dict[str, Any]) -> None:
        pass

    def process(self, context: ProcessContext) -> ProcessResult:
        return ProcessResult(status=ProcessStatus.SUCCESS, data={"version": "2.0.0"})


class TestProcessResult(unittest.TestCase):
    """ProcessResult 测试"""

    def test_default_success(self):
        result = ProcessResult()
        self.assertTrue(result.is_success)
        self.assertFalse(result.is_filtered)
        self.assertIsNone(result.error)

    def test_failed_status(self):
        result = ProcessResult(status=ProcessStatus.FAILED, error="something wrong")
        self.assertFalse(result.is_success)
        self.assertEqual(result.error, "something wrong")

    def test_filtered_status(self):
        result = ProcessResult(status=ProcessStatus.FILTERED)
        self.assertTrue(result.is_filtered)
        self.assertFalse(result.is_success)


class TestProcessorRegistry(unittest.TestCase):
    """ProcessorRegistry 测试"""

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()

    def tearDown(self):
        self.registry.clear()

    def test_register_and_get(self):
        self.registry.register(MockProcessor)
        cls = self.registry.get("mock_processor")
        self.assertEqual(cls, MockProcessor)

    def test_register_multiple_versions(self):
        self.registry.register(MockProcessor)
        self.registry.register(MockProcessorV2)

        v1 = self.registry.get("mock_processor", "1.0.0")
        v2 = self.registry.get("mock_processor", "2.0.0")
        self.assertEqual(v1, MockProcessor)
        self.assertEqual(v2, MockProcessorV2)

    def test_get_latest_version(self):
        self.registry.register(MockProcessor)
        self.registry.register(MockProcessorV2)
        latest = self.registry.get("mock_processor")
        self.assertEqual(latest, MockProcessorV2)

    def test_register_duplicate_raises(self):
        self.registry.register(MockProcessor)
        with self.assertRaises(ValueError):
            self.registry.register(MockProcessor)

    def test_get_unregistered_raises(self):
        with self.assertRaises(KeyError):
            self.registry.get("nonexistent")

    def test_list_all(self):
        self.registry.register(MockProcessor)
        all_processors = self.registry.list_all()
        self.assertIn("mock_processor", all_processors)
        self.assertIn("1.0.0", all_processors["mock_processor"])

    def test_unregister(self):
        self.registry.register(MockProcessor)
        self.registry.unregister("mock_processor", "1.0.0")
        with self.assertRaises(KeyError):
            self.registry.get("mock_processor")

    def test_count(self):
        self.registry.register(MockProcessor)
        self.registry.register(MockProcessorV2)
        self.assertEqual(self.registry.count, 2)

    def test_register_non_iprocessor_raises(self):
        with self.assertRaises(TypeError):
            self.registry.register(str)


class TestProcessorFactory(unittest.TestCase):
    """ProcessorFactory 测试"""

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()
        self.registry.register(MockProcessor)
        self.factory = ProcessorFactory(self.registry)

    def tearDown(self):
        self.registry.clear()

    def test_create(self):
        processor = self.factory.create("mock_processor", config={"key": "value"})
        self.assertIsInstance(processor, MockProcessor)
        self.assertTrue(processor._initialized)

    def test_create_from_node_config(self):
        node_config = {
            "id": "node_001",
            "type": "mock_processor",
            "config": {"key": "value"},
        }
        processor = self.factory.create_from_node_config(node_config)
        self.assertIsInstance(processor, MockProcessor)

    def test_create_unregistered_raises(self):
        with self.assertRaises(KeyError):
            self.factory.create("nonexistent")


class TestRegisterDecorator(unittest.TestCase):
    """@register_processor 装饰器测试"""

    def setUp(self):
        self.registry = ProcessorRegistry()
        self.registry.clear()

    def tearDown(self):
        self.registry.clear()

    def test_decorator_registers(self):
        @register_processor
        class DecoratedProcessor(BaseProcessor):
            name = "decorated"
            version = "1.0.0"

            def initialize(self, config):
                pass

            def process(self, context):
                return ProcessResult()

        cls = self.registry.get("decorated")
        self.assertEqual(cls, DecoratedProcessor)


if __name__ == "__main__":
    unittest.main()
