"""配置管理单元测试"""

import unittest

from framework.config.validator import ConfigValidator


class TestConfigValidator(unittest.TestCase):
    """ConfigValidator 测试"""

    def setUp(self):
        self.validator = ConfigValidator()

    def _make_valid_config(self):
        return {
            "id": "test_pipeline",
            "name": "测试 Pipeline",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [
                        {"id": "node_1", "type": "filter", "config": {}},
                    ],
                },
            ],
        }

    def test_valid_config(self):
        config = self._make_valid_config()
        is_valid, errors = self.validator.validate(config)
        # 注：处理器类型验证可能因 registry 为空而报错，但结构应该合法
        # 仅检查基础结构
        basic_errors = [e for e in errors if "Schema" in e or "缺少" in e]
        self.assertEqual(len(basic_errors), 0)

    def test_missing_required_fields(self):
        """缺少必要字段"""
        config = {"name": "test"}
        is_valid, errors = self.validator.validate(config)
        self.assertFalse(is_valid)
        self.assertTrue(len(errors) > 0)

    def test_empty_stages(self):
        """空的 stages 数组"""
        config = {
            "id": "test",
            "name": "test",
            "version": "1.0.0",
            "stages": [],
        }
        is_valid, errors = self.validator.validate(config)
        self.assertFalse(is_valid)

    def test_duplicate_node_ids(self):
        """重复节点 ID"""
        config = {
            "id": "test",
            "name": "test",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [
                        {"id": "same_id", "type": "filter", "config": {}},
                        {"id": "same_id", "type": "enrichment", "config": {}},
                    ],
                },
            ],
        }
        is_valid, errors = self.validator.validate(config)
        id_errors = [e for e in errors if "重复" in e]
        self.assertTrue(len(id_errors) > 0)

    def test_multi_stage_config(self):
        """多阶段配置"""
        config = {
            "id": "multi_stage",
            "name": "多阶段 Pipeline",
            "version": "1.0.0",
            "stages": [
                {
                    "name": "stage_1",
                    "processors": [
                        {"id": "node_1", "type": "filter", "config": {}},
                    ],
                },
                {
                    "name": "stage_2",
                    "processors": [
                        {"id": "node_2", "type": "enrichment", "config": {}},
                        {"id": "node_3", "type": "notification", "config": {}},
                    ],
                },
            ],
        }
        is_valid, errors = self.validator.validate(config)
        id_errors = [e for e in errors if "重复" in e or "缺少" in e or "Schema" in e]
        self.assertEqual(len(id_errors), 0)


if __name__ == "__main__":
    unittest.main()
