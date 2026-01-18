"""
UnitConverter 适配器

将原系统的 core.unit 适配为 TsDetect 的 IUnitConverter 接口。
"""

import logging

from django.conf import settings

from tsdetect.core.interfaces import IUnitConverter

logger = logging.getLogger("detect")


class BkMonitorUnitConverter(IUnitConverter):
    """
    蓝鲸监控单位转换器适配器

    封装原系统的 core.unit 模块，实现 TsDetect 的 IUnitConverter 接口。
    """

    def __init__(self, default_decimal: int = None):
        """
        初始化适配器

        Args:
            default_decimal: 默认小数位数，None 则使用 settings.POINT_PRECISION
        """
        self._default_decimal = default_decimal

    @property
    def default_decimal(self) -> int:
        """获取默认小数位数"""
        if self._default_decimal is not None:
            return self._default_decimal
        return getattr(settings, "POINT_PRECISION", 2)

    def _load_unit(self, unit: str):
        """
        加载单位对象

        Args:
            unit: 单位字符串

        Returns:
            单位对象
        """
        from core.unit import load_unit

        return load_unit(unit)

    def convert(self, value: float, from_unit: str, to_unit: str | None = None) -> float:
        """
        单位转换

        Args:
            value: 原始值
            from_unit: 原始单位
            to_unit: 目标单位（暂不支持，预留接口）

        Returns:
            转换后的值
        """
        if not from_unit:
            return value

        try:
            unit = self._load_unit(from_unit)
            # 使用原系统的转换方法
            converted_value, _ = unit.fn.auto_convert(value, decimal=self.default_decimal)
            return converted_value
        except Exception as e:
            logger.warning(f"Unit conversion failed: {e}")
            return value

    def auto_convert(self, value: float, unit: str, decimal: int = None) -> tuple[float, str]:
        """
        自动选择最佳单位进行转换

        Args:
            value: 原始值
            unit: 原始单位
            decimal: 小数位数

        Returns:
            (转换后的值, 单位后缀)
        """
        if decimal is None:
            decimal = self.default_decimal

        if not unit:
            return round(value, decimal), ""

        try:
            unit_obj = self._load_unit(unit)
            converted_value, suffix = unit_obj.fn.auto_convert(value, decimal=decimal)
            return converted_value, suffix
        except Exception as e:
            logger.warning(f"Auto convert failed: {e}")
            return round(value, decimal), unit

    def convert_to_min(self, value: float, unit: str, target_unit: str | None = None) -> float:
        """
        转换为最小单位（用于数值比较）

        这是原系统 unit_convert_min 函数的封装。

        Args:
            value: 原始值
            unit: 原始单位
            target_unit: 目标单位类型（可选）

        Returns:
            转换后的值
        """
        from alarm_backends.templatetags.unit import unit_convert_min

        try:
            return unit_convert_min(value, unit, target_unit)
        except Exception as e:
            logger.warning(f"Convert to min failed: {e}")
            return value

    def get_unit_suffix(self, unit: str) -> str:
        """
        获取单位后缀

        Args:
            unit: 单位

        Returns:
            单位后缀字符串
        """
        if not unit:
            return ""

        try:
            unit_obj = self._load_unit(unit)
            return unit_obj.suffix or unit
        except Exception:
            return unit


def get_unit_auto_convert_func():
    """
    获取单位自动转换函数

    用于模板渲染上下文。

    Returns:
        unit_auto_convert 函数
    """
    from alarm_backends.templatetags.unit import unit_auto_convert

    return unit_auto_convert


def get_unit_convert_min_func():
    """
    获取单位最小值转换函数

    用于表达式上下文。

    Returns:
        unit_convert_min 函数
    """
    from alarm_backends.templatetags.unit import unit_convert_min

    return unit_convert_min
