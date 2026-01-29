"""
TsDetect 基础测试

验证库的基本功能。
"""

import os
import sys

import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tsdetect.algorithms.ring_ratio import SimpleRingRatioAlgorithm, create_simple_ring_ratio
from tsdetect.algorithms.threshold import ThresholdAlgorithm, create_threshold_algorithm
from tsdetect.algorithms.year_round import SimpleYearRoundAlgorithm
from tsdetect.core.base import BaseAnomalyPoint, SimpleDataPoint
from tsdetect.core.exceptions import InvalidAlgorithmConfig
from tsdetect.units.base import NoOpUnitConverter, SimpleUnitConverter


class TestSimpleDataPoint:
    """测试 SimpleDataPoint"""

    def test_create_with_dict(self):
        """测试使用字典创建数据点"""
        dp = SimpleDataPoint(
            {
                "value": 95.0,
                "timestamp": 1234567890,
                "unit": "%",
                "dimensions": {"ip": "127.0.0.1"},
            }
        )

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
        config = [
            [
                {"method": "gte", "threshold": 90},
                {"method": "lte", "threshold": 100},
            ]
        ]
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


class TestBatchDetection:
    """批量检测测试 - 使用大量数据点验证算法稳定性"""

    def test_threshold_batch_detection(self):
        """测试阈值算法批量检测"""
        algo = create_threshold_algorithm(threshold=50, method="gt")

        # 生成 1000 个数据点
        data_points = [SimpleDataPoint(value=i % 100, timestamp=1234567890 + i * 60) for i in range(1000)]

        results = list(algo.detect_records(data_points))

        # 验证：value > 50 的应该被检测为异常（51-99 每个周期 49 个）
        # 1000 个点中，每 100 个有 49 个异常（51-99），共 10 个周期 = 490 个异常
        assert len(results) == 490

        # 验证所有异常点的值都 > 50
        for anomaly in results:
            assert anomaly.value > 50

    def test_threshold_range_batch(self):
        """测试范围阈值批量检测"""
        # 检测 40 <= value <= 60 的范围
        config = [
            [
                {"method": "gte", "threshold": 40},
                {"method": "lte", "threshold": 60},
            ]
        ]
        algo = ThresholdAlgorithm(config=config)

        # 生成 500 个随机分布的数据点
        import random

        random.seed(42)  # 固定种子保证可重复

        data_points = [SimpleDataPoint(value=random.uniform(0, 100), timestamp=1234567890 + i * 60) for i in range(500)]

        results = list(algo.detect_records(data_points))

        # 验证所有检测到的异常点都在范围内
        for anomaly in results:
            assert 40 <= anomaly.value <= 60

    def test_sequential_data_points(self):
        """测试顺序时间戳数据点"""
        algo = create_threshold_algorithm(threshold=80, method="gte")

        # 模拟一天的分钟级数据（1440 个点）
        base_time = 1700000000
        data_points = []

        for i in range(1440):
            # 模拟一个周期性的负载曲线（正弦波 + 噪声）
            import math

            hour_of_day = (i / 60) % 24
            # 白天（9-18点）负载高，晚上低
            base_load = 50 + 30 * math.sin((hour_of_day - 6) * math.pi / 12)
            noise = (i * 7 % 20) - 10  # 伪随机噪声
            value = max(0, min(100, base_load + noise))

            data_points.append(SimpleDataPoint(value=value, timestamp=base_time + i * 60))

        results = list(algo.detect_records(data_points))

        # 应该有一定数量的高负载异常
        assert len(results) > 0
        assert all(r.value >= 80 for r in results)


class TestBoundaryConditions:
    """边界条件测试"""

    def test_zero_value(self):
        """测试零值"""
        algo = create_threshold_algorithm(threshold=0, method="eq")

        dp_zero = SimpleDataPoint(value=0, timestamp=1234567890)
        dp_nonzero = SimpleDataPoint(value=0.001, timestamp=1234567890)

        assert len(algo.detect(dp_zero)) == 1
        assert len(algo.detect(dp_nonzero)) == 0

    def test_negative_value(self):
        """测试负值"""
        algo = create_threshold_algorithm(threshold=-10, method="lt")

        dp_neg = SimpleDataPoint(value=-15, timestamp=1234567890)
        dp_pos = SimpleDataPoint(value=5, timestamp=1234567890)

        assert len(algo.detect(dp_neg)) == 1
        assert len(algo.detect(dp_pos)) == 0

    def test_very_large_value(self):
        """测试极大值"""
        algo = create_threshold_algorithm(threshold=1e15, method="gt")

        dp_large = SimpleDataPoint(value=1e16, timestamp=1234567890)
        dp_small = SimpleDataPoint(value=1e14, timestamp=1234567890)

        assert len(algo.detect(dp_large)) == 1
        assert len(algo.detect(dp_small)) == 0

    def test_very_small_value(self):
        """测试极小值（精度测试）"""
        algo = create_threshold_algorithm(threshold=0.0001, method="lt")

        dp_tiny = SimpleDataPoint(value=0.00001, timestamp=1234567890)
        dp_normal = SimpleDataPoint(value=0.001, timestamp=1234567890)

        assert len(algo.detect(dp_tiny)) == 1
        assert len(algo.detect(dp_normal)) == 0

    def test_float_precision(self):
        """测试浮点精度边界"""
        # 测试 value == 0.1 + 0.2 是否等于 0.3（浮点精度问题）
        algo = create_threshold_algorithm(threshold=0.3, method="gte")

        # 0.1 + 0.2 在浮点数中不精确等于 0.3
        dp = SimpleDataPoint(value=0.1 + 0.2, timestamp=1234567890)
        results = algo.detect(dp)

        # 应该能正确检测
        assert len(results) == 1

    def test_timestamp_boundaries(self):
        """测试时间戳边界"""
        algo = create_threshold_algorithm(threshold=50, method="gt")

        # 测试各种时间戳
        timestamps = [
            0,  # Unix 纪元
            1,  # 最小正时间戳
            2147483647,  # 32位最大值
            1700000000,  # 正常时间戳
        ]

        for ts in timestamps:
            dp = SimpleDataPoint(value=60, timestamp=ts)
            results = algo.detect(dp)
            assert len(results) == 1
            assert results[0].timestamp == ts

    def test_empty_dimensions(self):
        """测试空维度"""
        dp = SimpleDataPoint(value=50, timestamp=1234567890, dimensions={})
        algo = create_threshold_algorithm(threshold=40, method="gt")

        results = algo.detect(dp)
        assert len(results) == 1

    def test_complex_dimensions(self):
        """测试复杂维度"""
        dp = SimpleDataPoint(
            value=50,
            timestamp=1234567890,
            dimensions={
                "ip": "192.168.1.1",
                "host": "server-001",
                "cluster": "prod-east",
                "service": "api-gateway",
                "instance_id": "i-12345678",
            },
        )
        algo = create_threshold_algorithm(threshold=40, method="gt")

        results = algo.detect(dp)
        assert len(results) == 1
        assert results[0].dimensions == dp.dimensions


class TestAmplitudeAlgorithms:
    """振幅算法测试"""

    def test_ring_ratio_amplitude_creation(self):
        """测试环比振幅算法创建"""
        from tsdetect.algorithms.amplitude import create_ring_ratio_amplitude

        algo = create_ring_ratio_amplitude(ratio=0.2, shock=10, threshold=100, agg_interval=60)

        assert algo.validated_config["ratio"] == 0.2
        assert algo.validated_config["shock"] == 10
        assert algo.validated_config["threshold"] == 100

    def test_year_round_amplitude_creation(self):
        """测试同比振幅算法创建"""
        from tsdetect.algorithms.amplitude import create_year_round_amplitude

        algo = create_year_round_amplitude(ratio=0.3, shock=5, days=7, method="avg", agg_interval=300)

        assert algo.validated_config["ratio"] == 0.3
        assert algo.validated_config["shock"] == 5
        assert algo.validated_config["days"] == 7
        assert algo.validated_config["method"] == "avg"

    def test_amplitude_history_offsets(self):
        """测试振幅算法历史偏移"""
        from tsdetect.algorithms.amplitude import RingRatioAmplitudeAlgorithm, YearRoundAmplitudeAlgorithm

        # 环比振幅需要前一个周期的数据
        ring_algo = RingRatioAmplitudeAlgorithm(config={"ratio": 0.2, "shock": 10, "threshold": 100}, agg_interval=60)
        offsets = ring_algo.get_history_offsets()
        assert 60 in offsets  # 包含前一个聚合周期

        # 同比振幅需要：1 个前一周期 + N 天 × 2（同一时刻 + 前一周期）
        year_algo = YearRoundAmplitudeAlgorithm(config={"ratio": 0.2, "shock": 5, "days": 7}, agg_interval=60)
        offsets = year_algo.get_history_offsets()
        # 1 + 7 * 2 = 15 个偏移
        assert len(offsets) == 15


class TestIntelligentAlgorithm:
    """智能检测算法测试"""

    def test_intelligent_algorithm_creation(self):
        """测试智能检测算法创建"""
        from tsdetect.algorithms.intelligent import create_intelligent_algorithm

        algo = create_intelligent_algorithm(use_sdk=True, args={"sensitivity": 50, "anomaly_type": "upper"})

        assert algo.validated_config["use_sdk"] == True
        assert algo.validated_config["args"]["sensitivity"] == 50
        assert algo.validated_config["args"]["anomaly_type"] == "upper"

    def test_intelligent_algorithm_with_mock_sdk(self):
        """测试使用模拟 SDK 的智能检测"""
        from tsdetect.algorithms.intelligent import MockSDKClient, SimpleIntelligentAlgorithm

        sdk_client = MockSDKClient()
        algo = SimpleIntelligentAlgorithm(config={"sensitivity": 50, "anomaly_type": "both"}, sdk_client=sdk_client)

        # 模拟检测
        dp = SimpleDataPoint(value=100, timestamp=1234567890, dimensions={"host": "server1"})

        # MockSDKClient 会返回固定的预测结果
        results = algo.detect(dp)
        # 结果取决于 MockSDKClient 的实现
        assert isinstance(results, list)


class TestPerformance:
    """性能测试"""

    def test_large_batch_performance(self):
        """测试大批量数据检测性能"""
        import time

        algo = create_threshold_algorithm(threshold=50, method="gt")

        # 生成 10000 个数据点
        data_points = [SimpleDataPoint(value=i % 100, timestamp=1234567890 + i * 60) for i in range(10000)]

        start_time = time.time()
        results = list(algo.detect_records(data_points))
        elapsed_time = time.time() - start_time

        # 验证结果正确性
        assert len(results) == 4900  # 每 100 个有 49 个异常（51-99），100 个周期

        # 性能断言：10000 个点应该在 1 秒内完成
        assert elapsed_time < 1.0, f"批量检测耗时 {elapsed_time:.2f}s，超过预期"

    def test_multiple_conditions_performance(self):
        """测试多条件检测性能"""
        import time

        # 创建复杂的多条件配置
        config = [
            [{"method": "gte", "threshold": 0}, {"method": "lt", "threshold": 20}],
            [{"method": "gte", "threshold": 40}, {"method": "lt", "threshold": 60}],
            [{"method": "gte", "threshold": 80}, {"method": "lte", "threshold": 100}],
        ]
        algo = ThresholdAlgorithm(config=config)

        # 生成 5000 个数据点
        data_points = [SimpleDataPoint(value=i % 100, timestamp=1234567890 + i * 60) for i in range(5000)]

        start_time = time.time()
        results = list(algo.detect_records(data_points))
        elapsed_time = time.time() - start_time

        # 验证结果：0-19(20个) + 40-59(20个) + 80-99(20个) = 60 个/周期
        # 5000 / 100 = 50 个完整周期
        expected_per_cycle = 20 + 20 + 20
        expected_total = expected_per_cycle * 50
        assert len(results) == expected_total

        # 性能断言
        assert elapsed_time < 1.0, f"多条件检测耗时 {elapsed_time:.2f}s，超过预期"

    def test_unit_conversion_performance(self):
        """测试带单位转换的检测性能"""
        import time

        converter = SimpleUnitConverter()
        algo = create_threshold_algorithm(threshold=1024, method="gt")

        # 生成带单位的数据点
        units = ["B", "KB", "MB", "GB"]
        data_points = [
            SimpleDataPoint(value=(i % 100) * 100, timestamp=1234567890 + i * 60, unit=units[i % 4])
            for i in range(5000)
        ]

        start_time = time.time()
        results = list(algo.detect_records(data_points))
        elapsed_time = time.time() - start_time

        # 性能断言
        assert elapsed_time < 2.0, f"带单位转换检测耗时 {elapsed_time:.2f}s，超过预期"


class TestEdgeCases:
    """边缘场景测试"""

    def test_single_point_detection(self):
        """测试单个数据点检测"""
        algo = create_threshold_algorithm(threshold=50, method="gt")

        dp = SimpleDataPoint(value=60, timestamp=1234567890)
        results = algo.detect(dp)

        assert len(results) == 1

    def test_all_normal_data(self):
        """测试全部正常数据（无异常）"""
        algo = create_threshold_algorithm(threshold=100, method="gt")

        # 所有数据点都在阈值以下
        data_points = [SimpleDataPoint(value=i, timestamp=1234567890 + i * 60) for i in range(100)]

        results = list(algo.detect_records(data_points))
        assert len(results) == 0

    def test_all_anomaly_data(self):
        """测试全部异常数据"""
        algo = create_threshold_algorithm(threshold=0, method="gt")

        # 所有数据点都超过阈值
        data_points = [SimpleDataPoint(value=i + 1, timestamp=1234567890 + i * 60) for i in range(100)]

        results = list(algo.detect_records(data_points))
        assert len(results) == 100

    def test_alternating_anomaly(self):
        """测试交替异常数据"""
        algo = create_threshold_algorithm(threshold=50, method="gte")

        # 交替正常和异常
        data_points = [
            SimpleDataPoint(value=100 if i % 2 == 0 else 0, timestamp=1234567890 + i * 60) for i in range(100)
        ]

        results = list(algo.detect_records(data_points))
        assert len(results) == 50  # 一半是异常

    def test_spike_detection(self):
        """测试尖峰检测"""
        algo = create_threshold_algorithm(threshold=90, method="gt")

        # 大部分正常，偶尔尖峰
        data_points = []
        for i in range(1000):
            value = 50.0  # 基准值
            if i % 100 == 50:  # 每 100 个点有一个尖峰
                value = 95.0
            data_points.append(SimpleDataPoint(value=value, timestamp=1234567890 + i * 60))

        results = list(algo.detect_records(data_points))
        assert len(results) == 10  # 10 个尖峰

    def test_gradual_increase(self):
        """测试渐进增长数据"""
        algo = create_threshold_algorithm(threshold=500, method="gte")

        # 值从 0 渐进增长到 1000
        data_points = [SimpleDataPoint(value=i, timestamp=1234567890 + i * 60) for i in range(1001)]

        results = list(algo.detect_records(data_points))
        # value >= 500 的点：500, 501, ..., 1000 = 501 个
        assert len(results) == 501


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
