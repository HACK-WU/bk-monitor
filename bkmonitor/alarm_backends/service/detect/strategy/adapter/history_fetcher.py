"""
HistoryFetcher 适配器

将原系统的 HistoryPointFetcher 适配为 TsDetect 的 IHistoryFetcher 接口。
"""

import functools
import json
import logging
from typing import Any, TYPE_CHECKING

from tsdetect.core.interfaces import IDataPoint, IHistoryFetcher

if TYPE_CHECKING:
    pass

logger = logging.getLogger("detect")


class HistoryFetcherAdapter(IHistoryFetcher):
    """
    历史数据获取器适配器

    封装原系统的 Redis 缓存逻辑，实现 TsDetect 的 IHistoryFetcher 接口。
    """

    def __init__(self, item, cache_key_class=None):
        """
        初始化适配器

        Args:
            item: 原系统的 item 对象，包含策略和数据源信息
            cache_key_class: 缓存 key 类（默认使用 alarm_backends.core.cache.key.HISTORY_DATA_KEY）
        """
        self.item = item
        self._cache_key_class = cache_key_class
        self._local_storage: dict[str, dict[str, Any]] = {}
        self._default_value: float | None = None

    @property
    def cache_key(self):
        """获取缓存 key 类"""
        if self._cache_key_class is None:
            from alarm_backends.core.cache import key

            self._cache_key_class = key.HISTORY_DATA_KEY
        return self._cache_key_class

    @property
    def client(self):
        """获取 Redis 客户端"""
        return self.cache_key.client

    def set_default(self, value: float):
        """
        设置默认值

        当历史数据不存在时使用此默认值。

        Args:
            value: 默认值
        """
        self._default_value = value

    def fetch(self, data_point: IDataPoint, offsets: list[int]) -> list[IDataPoint | None]:
        """
        获取历史数据点

        Args:
            data_point: 当前数据点
            offsets: 时间偏移量列表（秒）

        Returns:
            历史数据点列表，与 offsets 一一对应
        """
        results = []

        for offset in offsets:
            history_timestamp = data_point.timestamp - offset
            history_point = self._fetch_single(data_point, history_timestamp)
            results.append(history_point)

        return results

    def batch_fetch(self, data_points: list[IDataPoint], offsets: list[int]) -> dict[str, list[IDataPoint | None]]:
        """
        批量获取历史数据点

        Args:
            data_points: 当前数据点列表
            offsets: 时间偏移量列表

        Returns:
            字典，key 为 record_id，value 为历史数据点列表
        """
        result = {}

        # 预加载所有需要的历史数据
        self._preload_history(data_points, offsets)

        # 获取每个数据点的历史数据
        for dp in data_points:
            history_points = self.fetch(dp, offsets)
            result[dp.record_id] = history_points

        return result

    def _preload_history(self, data_points: list[IDataPoint], offsets: list[int]):
        """
        预加载历史数据到本地缓存

        Args:
            data_points: 数据点列表
            offsets: 偏移量列表
        """
        if not data_points:
            return

        # 收集所有需要的时间戳
        timestamps_needed = set()
        for dp in data_points:
            for offset in offsets:
                timestamps_needed.add(dp.timestamp - offset)

        # 批量加载
        for ts in timestamps_needed:
            history_key = self._get_history_key(ts)
            if history_key not in self._local_storage:
                try:
                    data = self.client.hgetall(history_key)
                    self._local_storage[history_key] = data
                except Exception as e:
                    logger.warning(f"Failed to load history data: {e}")
                    self._local_storage[history_key] = {}

    def _fetch_single(self, data_point: IDataPoint, history_timestamp: int) -> IDataPoint | None:
        """
        获取单个历史数据点

        Args:
            data_point: 当前数据点
            history_timestamp: 历史时间戳

        Returns:
            历史数据点，不存在返回 None
        """
        history_key = self._get_history_key(history_timestamp)

        # 先从本地缓存获取
        if history_key not in self._local_storage:
            try:
                self._local_storage[history_key] = self.client.hgetall(history_key)
            except Exception as e:
                logger.warning(f"Failed to fetch history data: {e}")
                self._local_storage[history_key] = {}

        # 获取对应维度的数据
        dimension_key = data_point.record_id.split(".")[0]
        raw_data = self._local_storage[history_key].get(dimension_key)

        if not raw_data:
            if self._default_value is not None:
                return self._create_default_point(data_point, history_timestamp)
            return None

        # 解析数据并创建 DataPoint
        try:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode("utf-8")
            data = json.loads(raw_data)
            return self._create_data_point(data)
        except Exception as e:
            logger.warning(f"Failed to parse history data: {e}")
            return None

    def _get_history_key(self, timestamp: int) -> str:
        """
        生成历史数据的缓存 key

        Args:
            timestamp: 时间戳

        Returns:
            缓存 key
        """
        return self.cache_key.get_key(strategy_id=self.item.strategy.id, item_id=self.item.id, timestamp=timestamp)

    def _create_data_point(self, data: dict[str, Any]) -> IDataPoint:
        """
        从数据字典创建 DataPoint

        Args:
            data: 数据字典

        Returns:
            DataPoint 对象
        """
        from alarm_backends.service.detect import DataPoint
        from alarm_backends.service.detect.strategy.adapter.data_point import DataPointAdapter

        original = DataPoint(data, self.item)
        return DataPointAdapter(original)

    def _create_default_point(self, data_point: IDataPoint, history_timestamp: int) -> IDataPoint:
        """
        创建默认值的数据点

        Args:
            data_point: 当前数据点
            history_timestamp: 历史时间戳

        Returns:
            使用默认值的数据点
        """
        from alarm_backends.service.detect import DataPoint
        from alarm_backends.service.detect.strategy.adapter.data_point import DataPointAdapter

        original = DataPoint({"value": self._default_value, "time": history_timestamp}, self.item)
        return DataPointAdapter(original)

    def publish_history_points(self, history_points: list[IDataPoint]):
        """
        发布历史数据到缓存

        Args:
            history_points: 历史数据点列表
        """
        if not history_points:
            return

        pipeline = self.client.pipeline(transaction=False)
        history_key_maker = functools.partial(
            self.cache_key.get_key, strategy_id=self.item.strategy.id, item_id=self.item.id
        )

        # 按时间戳分组
        history_points_map: dict[int, dict[str, str]] = {}
        for point in history_points:
            ts = point.timestamp
            if ts not in history_points_map:
                history_points_map[ts] = {}

            dimension_key = point.record_id.split(".")[0]
            history_points_map[ts][dimension_key] = json.dumps(point.as_dict())

        # 写入 Redis
        for timestamp, points_map in history_points_map.items():
            history_key = history_key_maker(timestamp=timestamp)
            pipeline.hmset(history_key, points_map)
            pipeline.expire(history_key, self.cache_key.ttl)

        pipeline.execute()

    def clear_local_storage(self):
        """清除本地缓存"""
        self._local_storage.clear()


class InMemoryHistoryFetcher(IHistoryFetcher):
    """
    内存历史数据获取器

    用于测试场景，从内存中获取历史数据。
    """

    def __init__(self, history_data: dict[int, IDataPoint] | None = None):
        """
        初始化内存获取器

        Args:
            history_data: 历史数据字典，key 为时间戳偏移
        """
        self._history_data = history_data or {}

    def add_history(self, offset: int, data_point: IDataPoint):
        """
        添加历史数据

        Args:
            offset: 时间偏移（秒）
            data_point: 历史数据点
        """
        self._history_data[offset] = data_point

    def fetch(self, data_point: IDataPoint, offsets: list[int]) -> list[IDataPoint | None]:
        """获取历史数据点"""
        results = []
        for offset in offsets:
            history_point = self._history_data.get(offset)
            results.append(history_point)
        return results

    def batch_fetch(self, data_points: list[IDataPoint], offsets: list[int]) -> dict[str, list[IDataPoint | None]]:
        """批量获取历史数据点"""
        result = {}
        for dp in data_points:
            result[dp.record_id] = self.fetch(dp, offsets)
        return result
