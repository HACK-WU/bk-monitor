# -*- coding: utf-8 -*-
"""
TsDetect 基础测试

验证库的基本功能。
"""

import pytest
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tsdetect.core.base import SimpleDataPoint, BaseAnomalyPoint
from tsdetect.core.exceptions import InvalidAlgorithmConfig, InvalidDataPoint
from tsdetect.algorithms.threshold import ThresholdAlgorithm, create_threshold_algorithm
from tsdetect.algorithms.ring_ratio import SimpleRingRatioAlgorithm, create_simple_ring_ratio
from tsdetect.algorithms.year_round import SimpleYearRoundAlgorithm
from tsdetect.units.base import SimpleUnitConverter, NoOpUnitConverter


class TestSimpleDataPoint:
    """测试 SimpleDataPoint"""
    
    def test_create_with_dict(self):
        """测试使用字典创建数据点"""
        dp = SimpleDataPoint({
            "value": 95.0,
            "timestamp": 1234567890,
            "unit": "%",
            "dimensions": {"ip": "127.0.0.1"},
        })
        
        assert dp.value == 95.0
        assert dp.timestamp == 1234567890
        assert dp.unit == "%"
        assert dp.dimensions == {"ip": "127.0.0.1"}
    
    def test_create_with_params(self):
        """测试使用参数创建数据点"""
        dp = SimpleDataPoint(
            value=80.0,
            timestamp=1234567890,
            unit="MB",
            dimensions={"host": "server1"},
        )
        
        assert dp.value == 80.0
        assert dp.timestamp == 1234567890
        assert dp.unit == "MB"
    
    def test_record_id_generation(self):
        """测试 record_id 生成"""
        dp = SimpleDataPoint(
            value=50.0,
            timestamp=1234567890,
            dimensions={"ip": "127.0.0.1"},
        )
        
        record_id = dp.record_id
        assert record_id is not None
        assert "1234567890" in record_id
    
    def test_as_dict(self):
        """测试转换为字典"""
        data = {
            "value": 95.0,
            "timestamp": 1234567890,
            "unit": "%",
        }
        dp = SimpleDataPoint(data)
        
        result = dp.as_dict()
        assert result["value"] == 95.0
        assert result["timestamp"] == 1234567890


class TestThresholdAlgorithm:
    """测试阈值检测算法"""
    
    def test_simple_threshold_gt(self):
        """测试大于阈值检测"""
        algo = create_threshold_algorithm(threshold=90, method="gt")
        
        # 超过阈值
        dp1 = SimpleDataPoint(value=95.0, timestamp=1234567890)
        result1 = algo.detect(dp1)
        assert len(result1) == 1
        assert result1[0].is_anomaly
        
        # 未超过阈值
        dp2 = SimpleDataPoint(value=85.0, timestamp=1234567890)
        result2 = algo.detect(dp2)
        assert len(result2) == 0
    
    def test_simple_threshold_lt(self):
        """测试小于阈值检测"""
        algo = create_threshold_algorithm(threshold=50, method="lt")
        
        # 低于阈值
        dp1 = SimpleDataPoint(value=30.0, timestamp=1234567890)
        result1 = algo.detect(dp1)
        assert len(result1) == 1
        
        # 未低于阈值
        dp2 = SimpleDataPoint(value=60.0, timestamp=1234567890)
        result2 = algo.detect(dp2)
        assert len(result2) == 0
    
    def test_threshold_with_multiple_conditions(self):
        """测试多条件阈值检测"""
        # 90 <= value <= 100
        config = [[
            {"method": "gte", "threshold": 90},
            {"method": "lte", "threshold": 100},
        ]]
        algo = ThresholdAlgorithm(config=config)
        
        # 在范围内
        dp1 = SimpleDataPoint(value=95.0, timestamp=1234567890)
        result1 = algo.detect(dp1)
        assert len(result1) == 1
        
        # 低于范围
        dp2 = SimpleDataPoint(value=85.0, timestamp=1234567890)
        result2 = algo.detect(dp2)
        assert len(result2) == 0
        
        # 高于范围
        dp3 = SimpleDataPoint(value=105.0, timestamp=1234567890)
        result3 = algo.detect(dp3)
        assert len(result3) == 0
    
    def test_invalid_config(self):
        """测试无效配置"""
        with pytest.raises(InvalidAlgorithmConfig):
            ThresholdAlgorithm(config={"thresholds": []})
        
        with pytest.raises(InvalidAlgorithmConfig):
            ThresholdAlgorithm(config=[[{"method": "invalid", "threshold": 90}]])


class TestSimpleRingRatio:
    """测试简易环比算法"""
    
    def test_create_algorithm(self):
        """测试创建环比算法"""
        algo = create_simple_ring_ratio(floor=20, ceil=20, agg_interval=60)
        
        assert algo.validated_config["floor"] == 20
        assert algo.validated_config["ceil"] == 20
        assert algo.agg_interval == 60
    
    def test_history_offsets(self):
        """测试历史偏移计算"""
        algo = create_simple_ring_ratio(floor=20, agg_interval=60)
        
        offsets = algo.get_history_offsets()
        assert offsets == [60]
    
    def test_invalid_config(self):
        """测试无效配置"""
        with pytest.raises(InvalidAlgorithmConfig):
            SimpleRingRatioAlgorithm(config={})  # 缺少 floor 和 ceil


class TestSimpleYearRound:
    """测试简易同比算法"""
    
    def test_history_offsets(self):
        """测试历史偏移（一周）"""
        algo = SimpleYearRoundAlgorithm(config={"floor": 20})
        
        offsets = algo.get_history_offsets()
        assert offsets == [604800]  # 一周的秒数


class TestUnitConverter:
    """测试单位转换器"""
    
    def test_no_op_converter(self):
        """测试无操作转换器"""
        converter = NoOpUnitConverter()
        
        assert converter.convert(100, "MB", "KB") == 100
        assert converter.convert_to_min(100, "MB") == 100
        
        value, unit = converter.auto_convert(100, "MB")
        assert value == 100
        assert unit == "MB"
    
    def test_simple_converter_bytes(self):
        """测试字节转换"""
        converter = SimpleUnitConverter()
        
        # KB 转 B
        result = converter.convert(1, "KB", "B")
        assert result == 1024
        
        # MB 转 KB
        result = converter.convert(1, "MB", "KB")
        assert result == 1024
    
    def test_simple_converter_auto(self):
        """测试自动转换"""
        converter = SimpleUnitConverter()
        
        # 1024 B 应该转换为 1 KB
        value, unit = converter.auto_convert(1024, "B")
        assert value == 1.0
        assert unit == "KB"
        
        # 1048576 B 应该转换为 1 MB
        value, unit = converter.auto_convert(1048576, "B")
        assert value == 1.0
        assert unit == "MB"


class TestAnomalyPoint:
    """测试异常数据点"""
    
    def test_create_anomaly_point(self):
        """测试创建异常点"""
        dp = SimpleDataPoint(value=95.0, timestamp=1234567890)
        
        # 创建一个简单的检测器对象
        class MockDetector:
            pass
        
        detector = MockDetector()
        
        anomaly = BaseAnomalyPoint(
            data_point=dp,
            detector=detector,
            anomaly_message="Test anomaly",
        )
        
        assert anomaly.value == 95.0
        assert anomaly.timestamp == 1234567890
        assert anomaly.anomaly_message == "Test anomaly"
        assert anomaly.is_anomaly
    
    def test_anomaly_as_dict(self):
        """测试异常点转换为字典"""
        dp = SimpleDataPoint(value=95.0, timestamp=1234567890)
        
        class MockDetector:
            pass
        
        anomaly = BaseAnomalyPoint(
            data_point=dp,
            detector=MockDetector(),
            anomaly_message="Test",
        )
        
        result = anomaly.as_dict()
        assert "data" in result
        assert "anomaly" in result
        assert result["anomaly"]["anomaly_message"] == "Test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
