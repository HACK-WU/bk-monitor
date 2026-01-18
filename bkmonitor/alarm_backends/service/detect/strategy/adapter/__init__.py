"""
TsDetect 适配器层

提供与 bk-monitor 原系统的适配，实现向后兼容。
"""

from alarm_backends.service.detect.strategy.adapter.data_point import (
    DataPointAdapter,
    AnomalyPointAdapter,
)
from alarm_backends.service.detect.strategy.adapter.history_fetcher import (
    HistoryFetcherAdapter,
)
from alarm_backends.service.detect.strategy.adapter.unit_converter import (
    BkMonitorUnitConverter,
)
from alarm_backends.service.detect.strategy.adapter.template_engine import (
    DjangoTemplateEngine,
)

__all__ = [
    "DataPointAdapter",
    "AnomalyPointAdapter",
    "HistoryFetcherAdapter",
    "BkMonitorUnitConverter",
    "DjangoTemplateEngine",
]
