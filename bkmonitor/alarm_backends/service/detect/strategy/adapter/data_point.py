"""
DataPoint 适配器

将原系统的 DataPoint 适配为 TsDetect 的 IDataPoint 接口。
"""

from typing import Any, TYPE_CHECKING

from tsdetect.core.interfaces import IDataPoint
from tsdetect.core.base import BaseAnomalyPoint

if TYPE_CHECKING:
    from alarm_backends.service.detect import DataPoint, AnomalyDataPoint


class DataPointAdapter(IDataPoint):
    """
    DataPoint 适配器

    将原系统的 DataPoint 适配为 TsDetect 的 IDataPoint 接口，
    同时保留对原始对象的访问能力。
    """

    def __init__(self, original: "DataPoint"):
        """
        初始化适配器

        Args:
            original: 原系统的 DataPoint 对象
        """
        self._original = original

    @property
    def value(self) -> float:
        """获取数据点值"""
        return float(self._original.value)

    @property
    def timestamp(self) -> int:
        """获取时间戳"""
        return int(self._original.timestamp)

    @property
    def unit(self) -> str:
        """获取单位"""
        return self._original.unit or ""

    @property
    def dimensions(self) -> dict[str, Any]:
        """获取维度信息"""
        return getattr(self._original, "dimensions", {})

    @property
    def record_id(self) -> str:
        """获取记录唯一标识"""
        return self._original.record_id

    @property
    def item(self):
        """获取原始 item 对象"""
        return self._original.item

    @property
    def values(self) -> dict[str, Any]:
        """获取所有指标值"""
        return getattr(self._original, "values", {})

    @property
    def original(self) -> "DataPoint":
        """
        访问原始 DataPoint 对象

        用于需要原始对象特性的场景。
        """
        return self._original

    def as_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return self._original.as_dict()

    def __getattr__(self, name: str) -> Any:
        """
        代理其他属性访问到原始对象

        支持访问原始 DataPoint 的所有属性。
        """
        return getattr(self._original, name)

    def __str__(self) -> str:
        return str(self._original)

    def __repr__(self) -> str:
        return f"<DataPointAdapter {self.record_id}:{self.value}>"


class AnomalyPointAdapter:
    """
    异常点适配器

    将 TsDetect 的 BaseAnomalyPoint 适配回原系统的 AnomalyDataPoint 格式。
    """

    def __init__(
        self,
        tsdetect_anomaly: BaseAnomalyPoint,
        original_data_point: "DataPoint",
        original_detector: Any,
    ):
        """
        初始化适配器

        Args:
            tsdetect_anomaly: TsDetect 的异常点对象
            original_data_point: 原始 DataPoint 对象
            original_detector: 原始检测器对象
        """
        self._tsdetect_anomaly = tsdetect_anomaly
        self._original_data_point = original_data_point
        self._original_detector = original_detector

    def to_original(self) -> "AnomalyDataPoint":
        """
        转换为原系统的 AnomalyDataPoint

        Returns:
            原系统格式的异常点对象
        """
        from alarm_backends.service.detect import AnomalyDataPoint

        anomaly = AnomalyDataPoint(
            data_point=self._original_data_point,
            detector=self._original_detector,
        )
        anomaly.anomaly_message = self._tsdetect_anomaly.anomaly_message
        anomaly.anomaly_time = self._tsdetect_anomaly.anomaly_time
        anomaly.context = self._tsdetect_anomaly.context

        # 复制子检测器
        for child in self._tsdetect_anomaly.child_detectors:
            anomaly.child_detector.append(child)

        return anomaly

    @classmethod
    def from_tsdetect_anomalies(
        cls,
        anomalies: list,
        original_data_point: "DataPoint",
        original_detector: Any,
    ) -> list:
        """
        批量转换异常点

        Args:
            anomalies: TsDetect 异常点列表
            original_data_point: 原始 DataPoint
            original_detector: 原始检测器

        Returns:
            原系统格式的异常点列表
        """
        result = []
        for anomaly in anomalies:
            adapter = cls(anomaly, original_data_point, original_detector)
            result.append(adapter.to_original())
        return result


def adapt_data_point(data_point: "DataPoint") -> DataPointAdapter:
    """
    快捷函数：适配 DataPoint

    Args:
        data_point: 原系统的 DataPoint

    Returns:
        适配后的 DataPointAdapter
    """
    return DataPointAdapter(data_point)


def adapt_data_points(data_points: list) -> list:
    """
    快捷函数：批量适配 DataPoint

    Args:
        data_points: 原系统的 DataPoint 列表

    Returns:
        适配后的 DataPointAdapter 列表
    """
    return [DataPointAdapter(dp) for dp in data_points]
