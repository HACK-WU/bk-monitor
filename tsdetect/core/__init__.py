# -*- coding: utf-8 -*-
"""
TsDetect 核心模块

包含基础数据结构、算法基类和接口定义。
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

__all__ = [
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
