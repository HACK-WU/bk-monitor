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

from django.conf import settings

from alarm_backends.cluster import TargetType
from alarm_backends.core.cache import clear_mem_cache, key
from alarm_backends.core.cache.key import ACCESS_EVENT_LOCKS
from alarm_backends.core.cache.strategy import StrategyCacheManager
from alarm_backends.core.cluster import get_cluster
from alarm_backends.core.control.strategy import Strategy
from alarm_backends.core.detect_result import ANOMALY_LABEL, CheckResult
from alarm_backends.core.lock.service_lock import service_lock
from alarm_backends.core.storage.kafka_v2 import KafkaQueueV2 as KafkaQueue
from alarm_backends.service.access.base import BaseAccessProcess
from alarm_backends.service.access.data.filters import HostStatusFilter, RangeFilter
from alarm_backends.service.access.event.filters import ConditionFilter, ExpireFilter
from alarm_backends.service.access.event.qos import QoSMixin
from alarm_backends.service.access.event.records import (
    AgentEvent,
    CorefileEvent,
    DiskFullEvent,
    DiskReadonlyEvent,
    GseProcessEventRecord,
    OOMEvent,
    PingEvent,
)
from alarm_backends.service.access.event.records.custom_event import (
    GseCustomStrEventRecord,
)
from alarm_backends.service.access.priority import PriorityChecker
from constants.common import DEFAULT_TENANT_ID
from constants.strategy import MAX_RETRIEVE_NUMBER
from core.drf_resource import api
from core.prometheus import metrics

logger = logging.getLogger("access.event")


class BaseAccessEventProcess(BaseAccessProcess, QoSMixin):
    def __init__(self):
        super().__init__()
        self.strategies = {}

        self.add_filter(ExpireFilter())
        self.add_filter(HostStatusFilter())
        self.add_filter(RangeFilter())
        self.add_filter(ConditionFilter())

    def post_handle(self):
        # 释放主机信息本地内存
        clear_mem_cache("host_cache")

    def pull(self):
        """
        Pull raw data and generate record.
        """
        raise NotImplementedError("pull must be implemented by BaseAccessEventProcess subclasses")

    def push_to_check_result(self):
        """
        将事件记录推送到检测结果缓存

        该方法将通过过滤器的事件记录缓存到Redis，用于后续的告警检测和收敛处理，包含：
        1. 缓存异常检测结果（时间戳+异常标签）
        2. 记录每个维度的最后检测点时间戳
        3. 批量执行Redis操作以提高性能
        4. 更新检测点缓存并设置过期时间

        ┌─────────────────────────────────────────────────────────────────┐
        │                    push_to_check_result()                       │
        └─────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │  Redis Key: CHECK_RESULT_{strategy_id}_{item_id}_{md5}_{level}  │
        │  内容: {"timestamp|ANOMALY": event_time, ...}                    │
        └─────────────────────────────────────────────────────────────────┘
                                      │
                      ┌───────────────┴───────────────┐
                      ▼                               ▼
        ┌─────────────────────────┐     ┌─────────────────────────────────┐
        │    Detect 检测模块        │    │       Trigger 触发模块            │
        │  读取检测结果，聚合判断     │     │  根据last_checkpoint判断告警恢复   │
        └─────────────────────────┘     └─────────────────────────────────┘
        """
        # Redis Pipeline对象，用于批量执行Redis命令，提高性能
        redis_pipeline = None
        # 存储每个维度的最后检测点时间戳，key为(md5_dimension, strategy_id, item_id, level)元组
        last_checkpoints = {}

        # 遍历所有事件记录
        for event_record in self.record_list:
            # 遍历事件关联的所有监控项
            for item in event_record.items:
                strategy_id = item.strategy.id
                item_id = item.id
                # 跳过已被过滤或抑制的事件
                if not event_record.is_retains[item_id] or event_record.inhibitions[item_id]:
                    continue

                # 获取事件时间戳和维度哈希值
                timestamp = event_record.event_time
                md5_dimension = event_record.md5_dimension
                # 创建检测结果对象，用于操作Redis缓存
                check_result = CheckResult(strategy_id, item_id, event_record.md5_dimension, event_record.level)

                # 初始化Redis Pipeline（仅首次）
                if redis_pipeline is None:
                    redis_pipeline = check_result.CHECK_RESULT

                try:
                    # 1. 缓存异常检测结果：格式为 "时间戳|ANOMALY" -> 事件时间
                    # 用于记录该维度在某个时间点发生了异常
                    name = f"{timestamp}|{ANOMALY_LABEL}"
                    kwargs = {name: event_record.event_time}
                    check_result.add_check_result_cache(**kwargs)

                    # 2. 记录该维度的最后检测点时间戳
                    # 使用元组作为key，确保每个维度+策略+监控项+级别的组合唯一
                    md5_dimension_last_point_key = (
                        md5_dimension,
                        strategy_id,
                        item_id,
                        event_record.level,
                    )
                    # 获取当前记录的最后检测点，不存在则默认为0
                    last_point = last_checkpoints.setdefault(md5_dimension_last_point_key, 0)
                    # 只保留最新的时间戳
                    if last_point < timestamp:
                        last_checkpoints[md5_dimension_last_point_key] = timestamp

                    # 3. 事件数据不设置维度缓存（与指标数据不同，事件数据的维度缓存无实际意义）
                    # check_result.update_key_to_dimension(event_record.raw_data["dimensions"])
                except Exception as e:
                    logger.exception(f"set check result cache error: {e}")

        # 批量执行所有Redis命令
        if redis_pipeline:
            # 事件数据不需要设置维度缓存的过期时间
            # check_result.expire_key_to_dimension()
            redis_pipeline.execute()

        # 更新每个维度的最后检测点到Redis
        for md5_dimension_last_point_key, point_timestamp in list(last_checkpoints.items()):
            try:
                # 解构元组获取各个参数
                md5_dimension, strategy_id, item_id, level = md5_dimension_last_point_key
                # 更新最后检测点缓存，用于判断数据是否过期或重复
                CheckResult.update_last_checkpoint_by_d_md5(strategy_id, item_id, md5_dimension, point_timestamp, level)
            except Exception as e:
                msg = f"set check result cache last_check_point error:{e}"
                logger.exception(msg)
            # 设置检测点缓存的过期时间，避免Redis内存无限增长
            CheckResult.expire_last_checkpoint_cache(strategy_id=strategy_id, item_id=item_id)

    def push(self, output_client=None):
        """
        将事件记录推送到Redis队列中，供后续检测模块消费

        参数:
            output_client: 可选的Redis客户端，用于测试或特殊场景

        该方法实现完整的事件推送流程，包含：
        1. QoS流控检查，防止事件洪泛
        2. 将事件结果推送到检测结果缓存
        3. 按维度分组去重，避免重复事件
        4. 优先级检查，确保高优先级事件优先处理
        5. 按策略ID和监控项ID分组，批量推送到Redis队列
        6. 发送异常信号，触发后续检测流程
        """
        # 执行QoS流控检查，防止事件过载
        self.check_qos()
        # 将事件推送到检测结果缓存，用于告警恢复判断
        self.push_to_check_result()

        # 按维度(md5_dimension)分组，检测是否存在重复事件
        # md5_dimension是事件维度的哈希值，相同维度的事件应该只有一条
        dimension_groups = {}
        for e in self.record_list:
            dimension_groups.setdefault(e.md5_dimension, []).append(e)

        # 检查是否存在相同维度的多个事件记录，这通常是异常情况
        for dimension, records in dimension_groups.items():
            if len(records) > 1:
                logger.warning(f"the same event has {len(records)} records, record: {records[0].raw_data}")

        # 进行优先级检查，为事件标记优先级，高优先级事件会被优先处理
        PriorityChecker.check_records(self.record_list)

        # 第一步：按策略ID和监控项ID分组待推送的事件
        # 数据结构: {strategy_id: {item_id: [event_str1, event_str2, ...]}}
        pending_to_push = {}
        for e in self.record_list:
            # 将事件记录序列化为字符串
            data_str = e.to_str()
            # 遍历事件关联的所有监控项
            for item in e.items:
                strategy_id = item.strategy.id
                item_id = item.id
                # 只推送需要保留且未被抑制的事件
                # is_retains: 事件是否需要保留（未被过滤）
                # inhibitions: 事件是否被抑制（被其他规则抑制）
                if e.is_retains[item_id] and not e.inhibitions[item_id]:
                    pending_to_push.setdefault(strategy_id, {}).setdefault(item_id, []).append(data_str)

        # 第二步：使用Redis Pipeline批量推送事件到队列
        # Pipeline可以减少网络往返次数，提高性能
        anomaly_signal_list = []
        client = output_client or key.ANOMALY_LIST_KEY.client
        pipeline = client.pipeline()
        for strategy_id, item_to_event_record in list(pending_to_push.items()):
            # 统计当前策略的事件总数，用于监控指标
            record_count = sum([len(records) for records in item_to_event_record.values()])
            metrics.ACCESS_PROCESS_PUSH_DATA_COUNT.labels(metrics.TOTAL_TAG, "event").inc(record_count)
            # 遍历每个监控项，将事件推送到对应的队列
            for item_id, event_list in list(item_to_event_record.items()):
                # 生成队列Key: ANOMALY_LIST_{strategy_id}_{item_id}
                queue_key = key.ANOMALY_LIST_KEY.get_key(strategy_id=strategy_id, item_id=item_id)
                # 使用lpush将事件列表推送到Redis列表头部
                pipeline.lpush(queue_key, *event_list)
                # 记录异常信号，用于通知检测模块有新事件到达
                anomaly_signal_list.append(f"{strategy_id}.{item_id}")
                # 设置队列过期时间，避免队列堆积
                pipeline.expire(queue_key, key.ANOMALY_LIST_KEY.ttl)
        # 批量执行所有Redis命令
        pipeline.execute()

        # 如果有异常信号，推送到信号队列，触发检测流程
        if anomaly_signal_list:
            client = output_client or key.ANOMALY_SIGNAL_KEY.client
            # 将所有异常信号推送到统一的信号队列
            client.lpush(key.ANOMALY_SIGNAL_KEY.get_key(), *anomaly_signal_list)
            # 设置信号队列的过期时间
            client.expire(key.ANOMALY_SIGNAL_KEY.get_key(), key.ANOMALY_SIGNAL_KEY.ttl)

        logger.info("push %s event_record to match queue finished(%s)", self.__class__.__name__, len(self.record_list))


class AccessCustomEventGlobalProcessV2(BaseAccessEventProcess):
    TYPE_OS_RESTART = 0
    TYPE_CLOCK_UNSYNC = 1
    TYPE_AGENT = 2
    TYPE_DISK_READONLY = 3
    TYPE_PORT_MISSING = 4
    TYPE_PROCESS_MISSING = 5
    TYPE_DISK_FULL = 6
    TYPE_COREFILE = 7
    TYPE_PING = 8
    TYPE_OOM = 9
    TYPE_GSE_CUSTOM_STR_EVENT = 100
    TYPE_GSE_PROCESS_EVENT = 101

    OPENED_WHITE_LIST = [
        TYPE_AGENT,
        TYPE_DISK_READONLY,
        TYPE_DISK_FULL,
        TYPE_COREFILE,
        TYPE_PING,
        TYPE_OOM,
        TYPE_GSE_CUSTOM_STR_EVENT,
        TYPE_GSE_PROCESS_EVENT,
    ]

    # kafka 客户端缓存，单个进程共用一套缓存
    _kafka_queues = {}

    @classmethod
    def get_kafka_queue(cls, topic, group_prefix):
        """
        Kafka客户端缓存
        """
        queue_key = (topic, group_prefix)
        if queue_key not in cls._kafka_queues:
            kafka_queue = KafkaQueue.get_common_kafka_queue()
            kafka_queue.set_topic(topic, group_prefix=group_prefix)
            cls._kafka_queues[queue_key] = kafka_queue
        return cls._kafka_queues[queue_key]

    def __init__(self, data_id=None, topic=None):
        super().__init__()

        self.data_id = data_id
        if not topic:
            # 获取topic信息
            topic_info = api.metadata.get_data_id(
                bk_tenant_id=DEFAULT_TENANT_ID, bk_data_id=self.data_id, with_rt_info=False
            )
            self.topic = topic_info["mq_config"]["storage_config"]["topic"]
        else:
            self.topic = topic

        self.strategies = {}

        # gse基础事件、自定义字符型、进程托管事件策略ID列表缓存
        gse_base_event_strategy = StrategyCacheManager.get_gse_alarm_strategy_ids()
        self.process_strategies(gse_base_event_strategy)

    def process_strategies(self, strategies):
        """
        处理策略信息
        """
        for biz_id, strategy_id_list in list(strategies.items()):
            # 过滤出集群需要处理的业务ID
            if not get_cluster().match(TargetType.biz, biz_id):
                continue

            for strategy_id in strategy_id_list:
                self.strategies.setdefault(int(biz_id), {})[strategy_id] = Strategy(strategy_id)

    def fetch_custom_event_alarm_type(self, raw_data):
        """
        判断自定义事件上报的告警类型
        :param raw_data: 事件数据
        :return: alarm_type
        """
        if self.data_id == settings.GSE_CUSTOM_EVENT_DATAID:
            return self.TYPE_GSE_CUSTOM_STR_EVENT
        if settings.GSE_PROCESS_REPORT_DATAID == raw_data["data_id"]:
            return self.TYPE_GSE_PROCESS_EVENT

    def _instantiate_by_event_type(self, raw_data):
        """
        根据事件类型实例化对应的事件记录对象

        参数:
            raw_data: dict, 原始事件数据，包含告警信息
                - GSE基础告警格式: {"value": [{"extra": {"type": 6, ...}, ...}], ...}
                - 自定义事件格式: {"data_id": xxx, ...}

        返回值:
            事件记录对象实例，可能的类型包括:
            - PingEvent: Ping异常事件 (type=8)
            - AgentEvent: Agent心跳丢失事件 (type=2)
            - CorefileEvent: Corefile异常事件 (type=7)
            - DiskFullEvent: 磁盘写满事件 (type=6)
            - DiskReadonlyEvent: 磁盘只读事件 (type=3)
            - OOMEvent: OOM内存溢出事件 (type=9)
            - GseCustomStrEventRecord: 自定义字符型事件 (type=100)
            - GseProcessEventRecord: 进程托管事件 (type=101)
            - None: 未知类型或未开启的告警类型

        该方法实现事件类型的路由分发，包含：
        1. 从原始数据中解析告警类型（优先从value字段获取，否则根据data_id判断）
        2. 检查告警类型是否在已开启的白名单中
        3. 部分事件类型（Ping/Agent）需要额外检查功能开关
        4. 根据类型实例化对应的事件记录类
        """

        # Step 1: 获取告警类型
        # GSE基础告警数据结构: value字段包含告警详情列表，从中提取type
        # 自定义事件数据结构: 无value字段，需要通过data_id判断类型
        alarms = raw_data.get("value")
        if alarms:
            alarm_type = alarms[0]["extra"]["type"]
        else:
            alarm_type = self.fetch_custom_event_alarm_type(raw_data)

        # Step 2: 根据告警类型路由到对应的事件类进行实例化
        # 只处理白名单中的事件类型，其他类型直接忽略（返回None）
        if alarm_type in self.OPENED_WHITE_LIST:
            # Ping异常事件: 需要检查ENABLE_PING_ALARM开关
            if alarm_type == self.TYPE_PING:
                if settings.ENABLE_PING_ALARM:
                    return PingEvent(raw_data, self.strategies)
            # Agent心跳丢失事件: 需要检查ENABLE_AGENT_ALARM开关
            elif alarm_type == self.TYPE_AGENT:
                if settings.ENABLE_AGENT_ALARM:
                    return AgentEvent(raw_data, self.strategies)
            # Corefile异常事件: 进程崩溃产生的core dump文件
            elif alarm_type == self.TYPE_COREFILE:
                return CorefileEvent(raw_data, self.strategies)
            # 磁盘写满事件: 磁盘使用率超过阈值
            elif alarm_type == self.TYPE_DISK_FULL:
                return DiskFullEvent(raw_data, self.strategies)
            # 磁盘只读事件: 磁盘变为只读状态
            elif alarm_type == self.TYPE_DISK_READONLY:
                return DiskReadonlyEvent(raw_data, self.strategies)
            # OOM事件: 系统内存溢出导致进程被杀
            elif alarm_type == self.TYPE_OOM:
                return OOMEvent(raw_data, self.strategies)
            # 自定义字符型事件: 用户通过SDK/API上报的自定义事件
            elif alarm_type == self.TYPE_GSE_CUSTOM_STR_EVENT:
                return GseCustomStrEventRecord(raw_data, self.strategies)
            # 进程托管事件: GSE进程托管模块上报的进程状态变化事件
            elif alarm_type == self.TYPE_GSE_PROCESS_EVENT:
                return GseProcessEventRecord(raw_data, self.strategies)

    def _pull_from_redis(self, max_records=MAX_RETRIEVE_NUMBER):
        data_channel = key.EVENT_LIST_KEY.get_key(data_id=self.data_id)
        client = key.DATA_LIST_KEY.client

        total_events = client.llen(data_channel)
        # 如果队列中事件数量超过1亿条，则记录日志，并进行清理
        # 有损，但需要保证整体服务依赖redis稳定
        if total_events > 10**7:
            logger.warning(
                f"[access event] data_id({self.data_id}) has {total_events} events, cleaning up! drop all events."
            )
            client.delete(data_channel)
            return []

        offset = min([total_events, max_records])
        if offset == 0:
            logger.info(f"[access event] data_id({self.data_id}) 暂无待检测事件")
            return []

        try:
            records = client.lrange(data_channel, -offset, -1)
        except UnicodeDecodeError as e:
            logger.error(
                "drop events: data_id(%s) topic(%s) poll alarm list(%s) from redis failed: %s",
                self.data_id,
                self.topic,
                offset,
                e,
            )
            client.ltrim(data_channel, 0, -offset - 1)
            return self._pull_from_redis(max_records=max_records)

        logger.info("data_id(%s) topic(%s) poll alarm list(%s) from redis", self.data_id, self.topic, len(records))
        if records:
            client.ltrim(data_channel, 0, -offset - 1)
        if offset == MAX_RETRIEVE_NUMBER:
            # 队列中时间量级超过单次处理上限。
            logger.info("data_id(%s) topic(%s) run_access_event_handler_v2 immediately", self.data_id, self.topic)
            from alarm_backends.service.access.tasks import run_access_event_handler_v2

            run_access_event_handler_v2.delay(self.data_id)
        return records

    def get_pull_type(self):
        # group_prefix
        cluster_name = get_cluster().name
        if cluster_name == "default":
            group_prefix = f"access.event.{self.data_id}"
        else:
            group_prefix = f"{cluster_name}.access.event.{self.data_id}"

        kafka_queue = self.get_kafka_queue(topic=self.topic, group_prefix=group_prefix)
        return "kafka" if kafka_queue.has_assigned_partitions() else "redis"

    def pull(self):
        """
        从Redis拉取原始事件数据并生成事件记录对象

        该方法实现事件数据的完整拉取和解析流程，包含：
        1. Topic有效性检查
        2. 分布式锁保护的Redis数据拉取
        3. GSE事件数据的JSON解析（兼容格式变动）
        4. 根据事件类型实例化对应的事件对象
        5. 事件有效性校验和扁平化处理
        6. 统计指标上报

        处理流程:
        - 使用分布式锁防止同一data_id的并发处理
        - 兼容GSE格式变动：自动清理末尾的\x00或\n字符
        - 支持多种事件类型：基础告警、自定义事件、进程事件等
        - 扁平化处理：将嵌套的事件数据展开为多条记录

        record_list数据结构示例:
        [
            AgentEvent(
                raw_data={
                    "_time_": "2019-10-17 13:53:53",
                    "_type_": 2,
                    "_bizid_": 2,
                    "_cloudid_": 0,
                    "_server_": "127.0.0.1",
                    "_host_": "127.0.0.1",
                    "_agent_id_": "0:127.0.0.1",
                    "_title_": "AGENT心跳丢失",
                    "strategy": Strategy(31),
                    "dimensions": {
                        "bk_target_ip": "127.0.0.1",
                        "bk_target_cloud_id": "0",
                        "agent_version": "1.0"
                    }
                },
                is_retains={1: True},
                inhibitions={1: False}
            ),
            DiskFullEvent(
                raw_data={
                    "_time_": "2019-10-17 13:53:53",
                    "_type_": 6,
                    "_bizid_": 2,
                    "_cloudid_": 0,
                    "_server_": "127.0.0.1",
                    "_host_": "127.0.0.1",
                    "_title_": "磁盘写满",
                    "_extra_": {
                        "disk": "/",
                        "free": 7,
                        "used_percent": 93,
                        "file_system": "/dev/vda1",
                        "fstype": "ext4"
                    },
                    "strategy": Strategy(32),
                    "dimensions": {
                        "bk_target_ip": "127.0.0.1",
                        "bk_target_cloud_id": "0",
                        "disk": "/",
                        "file_system": "/dev/vda1"
                    }
                },
                is_retains={1: True},
                inhibitions={1: False}
            )
        ]
        """
        record_list = []

        # 检查Topic配置是否存在
        if not self.topic:
            logger.warning(f"[access] dataid:({self.data_id}) no topic")
            return

        # 使用分布式锁从Redis拉取数据，防止多实例重复处理
        with service_lock(ACCESS_EVENT_LOCKS, data_id=f"{self.data_id}-[redis]"):
            result = self._pull_from_redis()

        # 遍历拉取到的原始事件数据
        for m in result:
            if not m:
                continue
            try:
                # GSE格式变动的临时兼容方案：判断一下结尾是否多了\n符号，多了先去掉
                # 清理末尾的空字符(\x00)或换行符(\n)，确保JSON解析正常
                data = json.loads(m[:-1] if m[-1] == "\x00" or m[-1] == "\n" else m)

                # 根据事件类型实例化对应的事件对象（AgentEvent、DiskEvent、ProcessEvent等）
                event_record = self._instantiate_by_event_type(data)

                # 校验事件有效性并扁平化为多条记录
                if event_record and event_record.check():
                    record_list.extend(event_record.flat())
            except Exception as e:
                logger.exception("topic(%s) loads alarm(%s) failed, %s", self.topic, m, e)

        # 将解析后的事件记录添加到实例的记录列表中
        self.record_list.extend(record_list)

        # 上报拉取到的事件数量指标
        metrics.ACCESS_EVENT_PROCESS_PULL_DATA_COUNT.labels(self.data_id).inc(len(record_list))

    def process(self):
        with metrics.ACCESS_EVENT_PROCESS_TIME.labels(data_id=self.data_id).time():
            if not self.strategies:
                logger.info("no strategy to process")
                exc = None
            else:
                exc = super().process()

        metrics.ACCESS_EVENT_PROCESS_COUNT.labels(
            data_id=self.data_id,
            status=metrics.StatusEnum.from_exc(exc),
            exception=exc,
        ).inc()
