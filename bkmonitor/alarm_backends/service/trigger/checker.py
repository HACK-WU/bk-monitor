"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import logging

from django.utils.translation import gettext as _

from alarm_backends.constants import NO_DATA_TAG_DIMENSION
from alarm_backends.core.cache.key import CHECK_RESULT_CACHE_KEY
from alarm_backends.core.control.record_parser import RecordParser
from alarm_backends.core.control.strategy import Strategy
from alarm_backends.core.detect_result import ANOMALY_LABEL
from bkmonitor.models import AnomalyRecord

logger = logging.getLogger("trigger")


class AnomalyChecker:
    """
    异常检测逻辑
    """

    # 检测窗口单位(默认1min)
    DEFAULT_CHECK_WINDOW_UNIT = 60

    def __init__(self, point, strategy, item_id):
        """
        初始化异常检测器

        参数:
            point: 异常数据点，包含以下结构：
                {
                    "data": {"dimensions": {...}, "record_id": "..."},
                    "anomaly": {
                        "<level>": {"anomaly_id": "..."},  # level: 告警级别(1/2/3)
                        ...
                    },
                    "strategy_snapshot_key": "...",
                    "context": {...}
                }
            strategy: 策略配置字典，包含策略ID、监控项、触发条件等完整配置
            item_id: 监控项ID，用于定位策略中的具体监控项

        执行步骤:
            1. 从策略中提取对应的监控项(item)配置
            2. 根据数据点类型(普通/无数据)获取对应的触发配置
            3. 获取检测窗口单位（默认60秒）
            4. 构建告警级别到异常ID的映射字典
            5. 初始化记录解析器，提取维度MD5和数据时间

        数据流线图:
            ┌─────────────────────────────────────────────────────────────────┐
            │                        输入参数                                  │
            │   point (异常点)    strategy (策略)    item_id (监控项ID)        │
            └─────────────────────────────────────────────────────────────────┘
                      │                  │                  │
                      ▼                  ▼                  ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  Step 1: 提取监控项配置                                          │
            │  self.item = Strategy.get_item_in_strategy(strategy, item_id)   │
            └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  Step 2: 判断数据点类型并获取触发配置                             │
            │  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
            │  │ is_no_data_point?   │    │                                 │ │
            │  │  ┌─────┐  ┌─────┐   │    │  trigger_configs 触发配置        │ │
            │  │  │ Yes │  │ No  │   │───▶│  {level: {check_window_size,    │ │
            │  │  └──┬──┘  └──┬──┘   │    │           trigger_count, ...}}  │ │
            │  │     │        │      │    │                                 │ │
            │  │  无数据    普通告警  │    └─────────────────────────────────┘ │
            │  │  配置      配置     │                                        │
            │  └─────────────────────┘                                        │
            └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  Step 3-5: 初始化其他属性                                        │
            │  • check_window_unit: 检测窗口单位(秒)                           │
            │  • anomaly_ids: {level: anomaly_id} 告警级别->异常ID映射         │
            │  • record_parser: 记录解析器                                     │
            │  • dimensions_md5: 维度哈希值(用于去重和缓存)                     │
            │  • source_time: 数据源时间戳                                     │
            └─────────────────────────────────────────────────────────────────┘
        """
        # Step 1: 从策略中提取对应监控项(item)的配置
        self.item = Strategy.get_item_in_strategy(strategy, item_id)
        self.strategy = strategy
        self.strategy_id = strategy["id"]
        self.item_id = item_id
        self.point = point

        # Step 2: 根据数据点类型获取触发配置
        if self.is_no_data_point(point):
            # 无数据告警：从监控项中获取无数据配置，触发配置按无数据级别单独设置
            no_data_configs = Strategy.get_no_data_configs(self.item)
            no_data_level = no_data_configs.pop("level")
            self.trigger_configs = {str(no_data_level): no_data_configs}
        else:
            # 普通告警：从策略中获取各级别的触发配置
            self.trigger_configs = Strategy.get_trigger_configs(self.strategy)

        # Step 3: 获取检测窗口单位（默认60秒，即1分钟）
        self.check_window_unit = Strategy.get_check_window_unit(self.item, self.DEFAULT_CHECK_WINDOW_UNIT)

        # Step 4: 构建告警级别到异常ID的映射字典 {level: anomaly_id}
        self.anomaly_ids = {
            level: anomaly_info["anomaly_id"] for level, anomaly_info in list(self.point["anomaly"].items())
        }

        # Step 5: 初始化记录解析器，提取关键字段作为快捷访问属性
        self.record_parser = RecordParser(point)
        self.dimensions_md5 = self.record_parser.dimensions_md5  # 维度哈希值，用于缓存键和去重
        self.source_time = self.record_parser.source_time  # 数据源时间戳

    @staticmethod
    def is_no_data_point(point):
        """
        :summary: 判断是否是无数据告警生成的异常点
        :param point:
        :return:
        """
        dimensions = point["data"]["dimensions"]
        if NO_DATA_TAG_DIMENSION in dimensions:
            return True
        return False

    def check(self):
        """
        异常点事件触发检测

        返回值:
            tuple: (anomaly_records, event_record)
                - anomaly_records: list[dict], 异常记录列表，用于存储到检测结果缓存
                - event_record: dict|None, 触发的事件记录，None表示未达到触发条件

        执行步骤:
            1. 调用 check_anomaly() 检查是否满足触发条件，返回告警级别和异常时间戳列表
            2. 调用 gen_anomaly_records() 生成异常记录列表（无论是否触发都会生成）
            3. 调用 gen_event_record() 根据触发结果生成事件记录（未触发返回None）
            4. 记录处理结果日志

        数据流线图:
            ┌─────────────────────────────────────────────────────────────────┐
            │                      self.point (异常数据点)                      │
            └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  Step 1: check_anomaly() - 触发条件检测                           │
            │  - 按告警级别(1→2→3)逐级检查                                      │
            │  - 判断检测窗口内异常次数是否 >= trigger_count                      │
            │  返回: (anomaly_level, anomaly_timestamps)                        │
            │        level=0 表示未触发，>0 表示触发的告警级别                     │
            └─────────────────────────────────────────────────────────────────┘
                                         │
                     ┌───────────────────┼───────────────────┐
                     ▼                   ▼                   ▼
            ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
            │ Step 2:         │ │ Step 3:         │ │ Step 4:         │
            │ gen_anomaly_    │ │ gen_event_      │ │ 日志记录        │
            │ records()       │ │ record()        │ │                 │
            │                 │ │                 │ │                 │
            │ 生成异常记录    │ │ level>0时生成   │ │ 记录触发结果    │
            │ (始终执行)      │ │ 事件记录        │ │ 和异常ID        │
            └─────────────────┘ └─────────────────┘ └─────────────────┘
                     │                   │
                     ▼                   ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  返回: (anomaly_records, event_record)                           │
            │  - anomaly_records: 存入 CHECK_RESULT 缓存                       │
            │  - event_record: 非None时推送到 EVENT 队列触发告警生成             │
            └─────────────────────────────────────────────────────────────────┘
        """
        # Step 1: 检查是否满足触发条件，返回触发的告警级别(0=未触发)和异常时间戳列表
        anomaly_level, anomaly_timestamps = self.check_anomaly()
        # Step 2: 生成异常记录列表（用于更新检测结果缓存，无论是否触发都需要）
        anomaly_records = self.gen_anomaly_records()
        # Step 3: 根据触发结果生成事件记录（level=0时返回None）
        event_record = self.gen_event_record(anomaly_level, anomaly_timestamps)

        # Step 4: 记录处理结果日志
        result_message = _(
            "[trigger 处理结果] ({result}) record({record_id}), strategy({strategy_id}), item({item_id})"
        ).format(
            strategy_id=self.strategy_id,
            item_id=self.item_id,
            record_id=self.point["data"]["record_id"],
            result=bool(event_record),
        )
        if event_record:
            # 触发时追加异常ID信息便于追踪
            result_message = f"{result_message}, anomaly({self.anomaly_ids[str(anomaly_level)]})"
        logger.info(result_message)

        return anomaly_records, event_record

    def gen_event_record(self, anomaly_level, anomaly_timestamps):
        """
        生成事件记录，用于推送给event
        :param anomaly_level: 异常级别
        :param anomaly_timestamps: 异常字符串
        """
        if anomaly_level == -1:
            return None
        event_info = {
            "data": self.point["data"],
            "anomaly": self.point["anomaly"],
            "strategy_snapshot_key": self.point["strategy_snapshot_key"],
            "context": self.point.get("context", {}),
            "trigger": {
                "level": str(anomaly_level),
                "anomaly_ids": [
                    f"{self.dimensions_md5}.{timestamp}.{self.strategy_id}.{self.item_id}.{anomaly_level}"
                    for timestamp in anomaly_timestamps
                ],
            },
        }
        return event_info

    def gen_anomaly_records(self) -> list[AnomalyRecord]:
        """
        创建异常记录
        :rtype: list[AnomalyRecord]
        """
        origin_alarm = {
            "data": self.point["data"],
            "anomaly": self.point["anomaly"],
        }
        records = []
        for level, anomaly_info in list(self.point["anomaly"].items()):
            anomaly_record = AnomalyRecord(
                anomaly_id=anomaly_info["anomaly_id"],
                source_time=self.record_parser.mysql_time,
                strategy_id=self.strategy_id,
                origin_alarm=origin_alarm,
                event_id="",
            )
            records.append(anomaly_record)
        return records

    def check_anomaly(self):
        """
        异常检测
        :return 触发告警的告警级别，如果都没触发告警，则返回 -1
        """
        levels = sorted([int(level) for level in list(self.point["anomaly"].keys())])
        # 按照算法级别从高到低判断，如果高级别算法已经触发了，则无需判断低级别
        anomaly_level = -1
        anomaly_timestamps = []
        for level in levels:
            if anomaly_level != -1:
                logger.debug(
                    f"anomaly record ({self.anomaly_ids[str(level)]}) skip trigger because"
                    f"high level anomaly record (level: {anomaly_level}) has been trigger."
                )
                continue
            is_triggered, anomaly_timestamps = self._check_anomaly_by_level(str(level))
            if is_triggered:
                # 高级别算法满足触发条件
                anomaly_level = level
        return anomaly_level, anomaly_timestamps

    def _check_anomaly_by_level(self, level):
        """
        检测某个级别的异常点是否满足触发条件

        参数:
            level: str, 告警级别 ("1"=致命, "2"=预警, "3"=提醒)

        返回值:
            tuple: (is_triggered, anomaly_timestamps)
                - is_triggered: bool, 是否满足触发条件
                - anomaly_timestamps: list[int], 检测窗口内所有异常点的时间戳列表

        触发条件判断逻辑:
            1. 普通告警: 检测窗口内异常次数 >= trigger_count
            2. 无数据告警: 所有检测记录均为异常点，且时间跨度 >= (trigger_count-1) * check_window_unit

        数据流线图:
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 1: 获取触发配置 (trigger_config)                               │
            │  - 优先使用当前级别的配置                                             │
            │  - 未配置时使用兜底配置（所有级别默认一致）                             │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 2: 从Redis有序集合查询检测窗口内的检测结果                       │
            │  - Key: CHECK_RESULT_CACHE_KEY (strategy_id + item_id + md5 + level)│
            │  - 时间范围: [source_time - window_offset, source_time]              │
            │  - window_offset = check_window_size * check_window_unit - 1        │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 3: 统计异常点数量                                              │
            │  - 遍历检测结果，筛选以 ANOMALY_LABEL 结尾的记录                       │
            │  - 收集异常点的时间戳到 anomaly_timestamps 列表                       │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 4: 判断是否触发                                                │
            │  ├── 普通判定: anomaly_times >= trigger_count                        │
            │  └── 无数据特殊判定:                                                 │
            │      - 条件1: 所有检测记录均为异常点 (always_nodata)                   │
            │      - 条件2: 首尾时间差 >= (trigger_count-1) * check_window_unit     │
            └─────────────────────────────────────────────────────────────────────┘
        """
        # Step 1: 获取当前级别的触发配置
        try:
            trigger_config = self.trigger_configs[level]
        except KeyError:
            # 当前级别未配置，尝试使用兜底配置
            trigger_configs = self.trigger_configs.values()
            if not trigger_configs:
                # 完全没有触发配置，记录错误并返回未触发
                logger.error(
                    f"strategy({self.strategy_id}), item({self.item_id}) level({level}) trigger config not exists"
                )
                return False, []

            # 兜底策略：使用任意一个已配置级别的配置（所有级别通常配置一致）
            trigger_config = list(trigger_configs)[0]

        # Step 2: 构建Redis缓存Key，查询检测窗口内的历史检测结果
        check_cache_key = CHECK_RESULT_CACHE_KEY.get_key(
            strategy_id=self.strategy_id,
            item_id=self.item_id,
            dimensions_md5=self.dimensions_md5,
            level=level,
        )
        # 计算检测窗口的时间偏移量（例如: 5个周期 * 60秒 - 1 = 299秒）
        check_window_offset = trigger_config["check_window_size"] * self.check_window_unit - 1
        # 使用zrangebyscore按时间范围查询有序集合，返回 [(label, score), ...] 格式
        check_results = CHECK_RESULT_CACHE_KEY.client.zrangebyscore(
            name=check_cache_key, min=self.source_time - check_window_offset, max=self.source_time, withscores=True
        )

        # Step 3: 遍历检测结果，统计异常点（以ANOMALY_LABEL结尾的记录表示异常）
        anomaly_timestamps = []
        for label, score in check_results:
            if label.endswith(ANOMALY_LABEL):
                # score存储的是数据时间戳，收集所有异常点的时间戳
                anomaly_timestamps.append(int(score))

        # Step 4: 判断是否满足触发条件
        anomaly_times = len(anomaly_timestamps)
        # 普通判定：异常次数达到阈值即触发
        is_triggered = anomaly_times >= trigger_config["trigger_count"]

        # 无数据告警的特殊判定逻辑（补充触发条件）
        if anomaly_times >= 2 and not is_triggered and self.is_no_data_point(self.point):
            # 无数据场景：即使异常次数未达阈值，但满足以下条件也触发:
            # 1. 所有检测记录均为异常点（没有正常数据点穿插）
            # 2. 首尾异常点的时间跨度 >= 预期的最小时间跨度
            start, end = anomaly_timestamps[0], anomaly_timestamps[-1]
            always_nodata = anomaly_times == len(check_results)
            is_triggered = always_nodata and (
                (end - start) >= (trigger_config["trigger_count"] - 1) * self.check_window_unit
            )

        return is_triggered, anomaly_timestamps
