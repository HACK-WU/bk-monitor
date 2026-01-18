# -*- coding: utf-8 -*-
"""
TsDetect - 时序数据异常检测库

一个通用的时序数据异常检测库，提供多种检测算法：
- 静态阈值检测
- 同比/环比检测
- 智能检测
- 离群检测

使用示例：
    from tsdetect import ThresholdAlgorithm, SimpleDataPoint

    dp = SimpleDataPoint({"value": 95.0, "timestamp": 1234567890, "unit": "%"})
    algo = ThresholdAlgorithm({"threshold": 90, "method": "gt"})
    result = algo.detect(dp)
"""

from tsdetect.core.base import BaseAnomalyPoint, BaseDataPoint, SimpleDataPoint
from tsdetect.core.algorithms import (
    BaseAlgorithm,
    BaseAlgorithmCollection,
    ExpressionDetector,
    RangeRatioAlgorithm,
)
from tsdetect.core.exceptions import (
    TsDetectError,
    InvalidAlgorithmConfig,
    InvalidDataPoint,
    DetectionError,
)
from tsdetect.core.interfaces import (
    IDataPoint,
    IHistoryFetcher,
    ITemplateEngine,
    IUnitConverter,
)

__version__ = "0.1.0"
__all__ = [
    # 版本
    "__version__",
    # 基类
    "BaseDataPoint",
    "SimpleDataPoint",
    "BaseAnomalyPoint",
    "BaseAlgorithm",
    "BaseAlgorithmCollection",
    "ExpressionDetector",
    "RangeRatioAlgorithm",
    # 接口
    "IDataPoint",
    "IHistoryFetcher",
    "ITemplateEngine",
    "IUnitConverter",
    # 异常
    "TsDetectError",
    "InvalidAlgorithmConfig",
    "InvalidDataPoint",
    "DetectionError",
]
