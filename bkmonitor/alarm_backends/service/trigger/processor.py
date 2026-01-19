"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import json
import logging
import time

from alarm_backends.core.alert.adapter import MonitorEventAdapter
from alarm_backends.core.cache.key import ANOMALY_LIST_KEY, ANOMALY_SIGNAL_KEY
from alarm_backends.core.control.strategy import Strategy
from alarm_backends.service.trigger.checker import AnomalyChecker
from core.errors.alarm_backends import StrategyNotFound
from core.prometheus import metrics

logger = logging.getLogger("trigger")


class TriggerProcessor:
    # 单次处理量(默认为全量处理)
    MAX_PROCESS_COUNT = 0

    def __init__(self, strategy_id, item_id):
        self.strategy_id = int(strategy_id)
        self.item_id = int(item_id)
        self.anomaly_list_key = ANOMALY_LIST_KEY.get_key(strategy_id=self.strategy_id, item_id=self.item_id)
        self.anomaly_points = []
        self.anomaly_records = []
        self.event_records = []
        # 策略快照数据
        self._strategy_snapshots = {}
        self.strategy = Strategy(self.strategy_id)

    def get_strategy_snapshot(self, key):
        """
        获取配置快照
        """
        try:
            # 查询对应的key快照是否存在
            return self._strategy_snapshots[key]
        except KeyError:
            # 如果查不到内存快照，则查询redis
            snapshot = Strategy.get_strategy_snapshot_by_key(key, self.strategy_id)
            if not snapshot:
                raise StrategyNotFound({"key": key})
            self._strategy_snapshots[key] = snapshot
            return snapshot

    def pull(self):
        """
        从Redis异常队列中拉取待处理的异常数据点

        该方法实现从 ANOMALY_LIST_KEY 队列拉取异常点并进行预处理，支持批量拉取和分批处理机制。

        执行步骤:
            1. 使用 lrange 从队列尾部拉取最多 MAX_PROCESS_COUNT 条数据
            2. 翻转列表，确保按时间从旧到新的顺序处理
            3. 若拉取到数据，更新 Prometheus 指标计数
            4. 使用 ltrim 删除已拉取的数据，实现"消费即删除"
            5. 若拉取数量达到上限，延迟推送信号到 ANOMALY_SIGNAL_KEY 触发下次处理
            6. 记录日志（info/warning 级别）

        数据流线图:
            ┌─────────────────────────────────────────────────────────────────┐
            │               ANOMALY_LIST_KEY (Redis List)                     │
            │  ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐      │
            │  │ old  │  ... │  ... │  ... │  ... │  ... │  ... │ new  │      │
            │  └──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘      │
            │                                       ◄──────────────────┤      │
            │                                       lrange(-N, -1) 拉取尾部   │
            └─────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  self.anomaly_points.reverse()  # 翻转为时间升序                 │
            │  [new, ..., old]  →  [old, ..., new]                            │
            └─────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  ltrim(0, -len-1)  # 删除已拉取的数据（从右侧裁剪）               │
            │  ┌──────┬──────┬──────┬──────┐                                  │
            │  │ old  │  ... │  ... │  ... │  (剩余未处理数据)                 │
            │  └──────┴──────┴──────┴──────┘                                  │
            └─────────────────────────────────────────────────────────────────┘
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
            ┌─────────────────────────┐   ┌─────────────────────────┐
            │ len == MAX_PROCESS_COUNT│   │ len < MAX_PROCESS_COUNT │
            │ 队列未拉完               │   │ 队列已拉空               │
            │                         │   │                         │
            │ delay rpush 信号        │   │ 等待下次触发             │
            │ (1秒后继续处理)          │   │                         │
            └─────────────────────────┘   └─────────────────────────┘
        """
        # Step 1: 从队列尾部拉取数据（lrange 返回指定范围的元素，-N 到 -1 表示最后 N 个元素）
        self.anomaly_points = ANOMALY_LIST_KEY.client.lrange(self.anomaly_list_key, -self.MAX_PROCESS_COUNT, -1)
        # Step 2: 翻转列表，将数据按照时间从旧到新的顺序排列，确保先产生的异常先处理
        self.anomaly_points.reverse()
        if self.anomaly_points:
            # Step 3: 更新 Prometheus 指标，记录本次拉取的数据量
            metrics.TRIGGER_PROCESS_PULL_DATA_COUNT.labels(strategy_id=metrics.TOTAL_TAG).inc(len(self.anomaly_points))
            # Step 4: 使用 ltrim 裁剪队列，删除已拉取的数据（保留索引 0 到 -(len+1) 的元素，即删除尾部已拉取的部分）
            ANOMALY_LIST_KEY.client.ltrim(self.anomaly_list_key, 0, -len(self.anomaly_points) - 1)
            # Step 5: 判断是否还有未拉取的数据
            if len(self.anomaly_points) == self.MAX_PROCESS_COUNT:
                # 拉取到的数量等于最大数量，说明队列中可能还有剩余数据，延迟1秒后推送信号触发下次处理
                signal_key = f"{self.strategy_id}.{self.item_id}"
                ANOMALY_SIGNAL_KEY.client.delay("rpush", ANOMALY_SIGNAL_KEY.get_key(), signal_key, delay=1)
                logger.info(
                    f"[pull anomaly record] strategy({self.strategy_id}), item({self.item_id}) pull {len(self.anomaly_points)} record."
                    "queue has data, process next time"
                )
            else:
                # Step 6: 队列数据已全部拉取完毕，记录日志
                logger.info(
                    f"[pull anomaly record] strategy({self.strategy_id}), item({self.item_id}) pull {len(self.anomaly_points)} record"
                )
        else:
            # 队列为空，记录警告日志（可能是信号误触发或数据已被其他进程消费）
            logger.warning(
                f"[pull anomaly record] strategy({self.strategy_id}), item({self.item_id}) pull {len(self.anomaly_points)} record"
            )

    def push_event_to_kafka(self, event_records):
        """
        将触发的告警事件推送到Kafka消息队列

        参数:
            event_records: list[dict], 事件记录列表，每个元素结构如下:
                {
                    "event_record": {
                        "data": {"detect_time": 1234567890, ...},  # 检测数据
                        "strategy_snapshot_key": "snapshot_xxx",   # 策略快照Key
                        ...
                    }
                }

        执行步骤:
            1. 遍历事件记录，计算处理延迟并转换为标准事件格式
            2. 记录处理延迟指标，延迟超过60秒记录告警日志
            3. 批量推送事件到Kafka
            4. 事件数超过1000时记录溢出指标

        数据流线图:
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 1: 遍历事件记录，计算延迟并适配格式                              │
            │  - 计算 latency = current_time - detect_time                        │
            │  - 使用 MonitorEventAdapter 转换为标准事件格式                        │
            │  - 追踪批次内最大延迟 (max_latency)                                   │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 2: 记录处理延迟指标                                            │
            │  - 始终记录 TRIGGER_PROCESS_LATENCY 指标                             │
            │  - max_latency > 60s 时:                                            │
            │    ├── 记录 warning 日志                                            │
            │    └── 记录 PROCESS_BIG_LATENCY 指标（含业务和策略标签）               │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 3: 批量推送到Kafka                                             │
            │  MonitorEventAdapter.push_to_kafka(events)                          │
            └─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
            ┌─────────────────────────────────────────────────────────────────────┐
            │  Step 4: 溢出监控                                                    │
            │  - 事件数 > 1000 时记录 PROCESS_OVER_FLOW 指标                        │
            │  - 用于监控单批次事件量异常情况                                        │
            └─────────────────────────────────────────────────────────────────────┘
        """
        events = []
        current_time = time.time()
        max_latency = 0

        # Step 1: 遍历事件记录，计算延迟并转换为标准事件格式
        for record in event_records:
            event_record = record["event_record"]
            detect_time = event_record.get("data", {}).get("detect_time")

            # 计算从检测到触发的处理延迟，追踪批次内最大延迟
            if detect_time:
                latency = current_time - event_record["data"]["detect_time"]
                if latency > max_latency:
                    max_latency = latency

            # 使用适配器将事件记录转换为Kafka消息格式
            adapter = MonitorEventAdapter(
                record=record["event_record"],
                strategy=self.get_strategy_snapshot(record["event_record"]["strategy_snapshot_key"]),
            )
            events.append(adapter.adapt())

        # Step 2: 记录处理延迟指标（用于监控告警处理链路性能）
        metrics.TRIGGER_PROCESS_LATENCY.labels(strategy_id=metrics.TOTAL_TAG).observe(max_latency)

        # 延迟超过60秒，记录告警日志和详细指标（帮助定位性能瓶颈）
        if max_latency > 60:
            logger.warning(
                "[detect to trigger]big latency %s,  strategy(%s)",
                max_latency,
                self.strategy_id,
            )
            metrics.PROCESS_BIG_LATENCY.labels(
                strategy_id=self.strategy_id,
                module="detect_trigger",
                bk_biz_id=self.strategy.bk_biz_id,
                strategy_name=self.strategy.name,
            ).observe(max_latency)

        # Step 3: 批量推送事件到Kafka，供下游消费处理
        MonitorEventAdapter.push_to_kafka(events=events)

        # Step 4: 单批次事件量超过1000，记录溢出指标（用于容量预警）
        if len(events) > 1000:
            metrics.PROCESS_OVER_FLOW.labels(
                module="trigger",
                strategy_id=self.strategy_id,
                bk_biz_id=self.strategy.bk_biz_id,
                strategy_name=self.strategy.name,
            ).inc(len(events))

    def push(self):
        # 推送事件记录到输出队列
        if self.event_records:
            self.push_event_to_kafka(self.event_records)
            logger.info(
                f"[process result collect] strategy({self.strategy_id}), item({self.item_id}) finish."
                f"push {len(self.anomaly_records)} AnomalyRecord, {len(self.event_records)} Event"
            )
            metrics.TRIGGER_PROCESS_PUSH_DATA_COUNT.labels(strategy_id=metrics.TOTAL_TAG).inc(len(self.event_records))

        self.anomaly_points = []
        self.anomaly_records = []
        self.event_records = []

    def process(self):
        self.pull()

        in_alarm_time, message = self.strategy.in_alarm_time()
        if not in_alarm_time:
            logger.info("[trigger] strategy(%s) not in alarm time: %s, skipped", self.strategy_id, message)
        else:
            for point in self.anomaly_points:
                try:
                    self.process_point(point)
                except Exception as e:
                    error_message = f"[process error] strategy({self.strategy_id}), item({self.item_id}) reason: {e} \norigin data: {point}"
                    logger.exception(error_message)

        self.push()

    def process_point(self, point):
        """
        处理单个异常数据点，执行触发检测并生成异常记录和事件记录

        参数:
            point: str, JSON格式的异常数据点字符串

        返回值:
            通过 checker.check() 返回 (anomaly_records, event_record):
            - anomaly_records: list[AnomalyRecord], 异常记录ORM对象列表
            - event_record: dict|None, 触发的事件记录，未触发时为None

        point 数据结构示例:
        {
          "data": {
            "record_id": "55a76cf628e46c04a052f4e19bdb9dbf.1569246480", # {dimensions_md5}.{timestamp}
            "value": 91.5,
            "values": {
              "timestamp": 1569246480,
              "cpu_usage": 91.5
            },
            "dimensions": {
              "ip": "10.0.1.100",
              "bk_cloud_id": "0"
            },
            "time": 1569246480
          },
          "anomaly": {
            "1": {
              "anomaly_message": "CPU使用率 >= 90.0%, 当前值91.5%",
              "anomaly_id": "55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.1",
              "anomaly_time": "2019-09-23 18:48:00"
            },
            "2": {
              "anomaly_message": "CPU使用率 >= 80.0%, 当前值91.5%",
              "anomaly_id": "55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.2",
              "anomaly_time": "2019-09-23 18:48:00"
            }
          },
          "strategy_snapshot_key": "cache.strategy.snapshot.1001.1569200000",
          "trigger": {
            "level": "1",
            # `anomaly_id`: 格式为 `{dimensions_md5}.{timestamp}.{strategy_id}.{item_id}.{level}`
            "anomaly_ids": [
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246360.1001.37.1",
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246420.1001.37.1",
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.1"
            ]
          },
          "context": {}
        }

        anomaly_records 数据结构示例 (list[AnomalyRecord]):
        [
          AnomalyRecord(
            anomaly_id="55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.1",
            source_time="2019-09-23 18:48:00",        # MySQL时间格式
            strategy_id=1001,
            origin_alarm={
              "data": {...},                          # 原始数据点
              "anomaly": {...}                        # 异常信息
            },
            event_id=""
          ),
          AnomalyRecord(
            anomaly_id="55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.2",
            ...
          )
        ]

        event_record 数据结构示例 (触发时返回dict，未触发返回None):
        {
          "data": {                                   # 原始数据点信息
            "record_id": "55a76cf628e46c04a052f4e19bdb9dbf.1569246480",
            "value": 91.5,
            "values": {"timestamp": 1569246480, "cpu_usage": 91.5},
            "dimensions": {"ip": "10.0.1.100", "bk_cloud_id": "0"},
            "time": 1569246480
          },
          "anomaly": {                                # 各级别异常信息
            "1": {"anomaly_message": "...", "anomaly_id": "...", "anomaly_time": "..."},
            "2": {"anomaly_message": "...", "anomaly_id": "...", "anomaly_time": "..."}
          },
          "strategy_snapshot_key": "cache.strategy.snapshot.1001.1569200000",
          "context": {},
          "trigger": {                                # 触发信息（由checker生成）
            "level": "1",                             # 触发的告警级别
            "anomaly_ids": [                          # 检测窗口内的异常ID列表
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246360.1001.37.1",
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246420.1001.37.1",
              "55a76cf628e46c04a052f4e19bdb9dbf.1569246480.1001.37.1"
            ]
          }
        }
        """
        point = json.loads(point)
        strategy = self.get_strategy_snapshot(point["strategy_snapshot_key"])
        checker = AnomalyChecker(point, strategy, self.item_id)
        anomaly_records, event_record = checker.check()

        # 暂存结果，最后批量保存
        if event_record:
            self.event_records.append({"anomaly_records": anomaly_records, "event_record": event_record})
        else:
            self.anomaly_records.extend(anomaly_records)
