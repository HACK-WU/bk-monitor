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
from alarm_backends.core.storage.kafka import KafkaQueue
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
from core.errors.alarm_backends import LockError
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
        将事件检测结果推送到Redis缓存，用于告警恢复判断

        该方法负责将通过过滤和优先级检查的事件记录写入Redis检测结果缓存。
        Detect模块和Alert模块会读取这些缓存数据来判断告警是否恢复。

        执行步骤:
            1. 遍历事件记录，过滤掉被保留/被抑制的事件
            2. 为每个事件创建CheckResult对象，写入异常标记缓存
            3. 收集每个维度的最新checkpoint时间戳
            4. 批量执行Redis Pipeline命令
            5. 更新各维度的last_checkpoint缓存

        数据流向图:
            record_list (事件记录列表)
                ↓
            ┌─────────────────────────────────────────────────────────┐
            │  过滤条件检查                                            │
            │  - is_retains[item_id] = True (事件被保留)               │
            │  - inhibitions[item_id] = False (事件未被优先级抑制)      │
            └─────────────────────────────────────────────────────────┘
                ↓ (通过过滤)
            ┌─────────────────────────────────────────────────────────┐
            │  CheckResult 检测结果缓存                                 │
            │  - Key: check.result.{strategy_id}.{item_id}.{md5}      │
            │  - Field: {timestamp}|ANOMALY                           │
            │  - Value: event_time                                    │
            └─────────────────────────────────────────────────────────┘
                ↓
            ┌─────────────────────────────────────────────────────────┐
            │  last_checkpoint 缓存                                    │
            │  - 记录每个维度最后一次检测的时间点                         │
            │  - 用于告警恢复时判断数据连续性                            │
            └─────────────────────────────────────────────────────────┘

        注意事项:
            - 必须在PriorityChecker.check_records()之后调用，确保inhibitions已设置
            - 事件数据不设置维度缓存（与时序数据不同）
            - Pipeline批量执行提升Redis写入性能
        """
        # Redis Pipeline对象，用于批量执行命令
        redis_pipeline = None
        # 记录每个维度的最新checkpoint: {(md5, strategy_id, item_id, level): timestamp}
        last_checkpoints = {}

        # ======================== Step1-3: 遍历事件记录，写入检测结果缓存 ========================
        for event_record in self.record_list:
            for item in event_record.items:
                strategy_id = item.strategy.id
                item_id = item.id

                # 过滤条件检查:
                #   1. is_retains[item_id] = False: 事件已被过滤器过滤掉，跳过
                #   2. inhibitions[item_id] = True: 事件被高优先级策略抑制，跳过
                if not event_record.is_retains[item_id] or event_record.inhibitions[item_id]:
                    continue

                timestamp = event_record.event_time
                md5_dimension = event_record.md5_dimension
                # 创建CheckResult对象，封装检测结果的Redis操作
                check_result = CheckResult(strategy_id, item_id, event_record.md5_dimension, event_record.level)

                # 延迟初始化Pipeline，避免无数据时创建不必要的连接
                if redis_pipeline is None:
                    redis_pipeline = check_result.CHECK_RESULT

                try:
                    # Step2: 写入异常标记缓存
                    # Key格式: check.result.{strategy_id}.{item_id}.{md5_dimension}.{level}
                    # Field格式: {timestamp}|ANOMALY
                    # Value: event_time (事件发生时间)
                    name = f"{timestamp}|{ANOMALY_LABEL}"
                    kwargs = {name: event_record.event_time}
                    check_result.add_check_result_cache(**kwargs)

                    # Step3: 收集最新checkpoint时间戳
                    # 用于后续批量更新last_checkpoint缓存
                    md5_dimension_last_point_key = (
                        md5_dimension,
                        strategy_id,
                        item_id,
                        event_record.level,
                    )
                    last_point = last_checkpoints.setdefault(md5_dimension_last_point_key, 0)
                    # 只保留最新的时间戳
                    if last_point < timestamp:
                        last_checkpoints[md5_dimension_last_point_key] = timestamp

                    # 注: 事件数据不设置维度缓存，与时序数据处理不同
                    # check_result.update_key_to_dimension(event_record.raw_data["dimensions"])
                except Exception as e:
                    logger.exception(f"set check result cache error: {e}")

        # ======================== Step4: 批量执行Redis命令 ========================
        if redis_pipeline:
            # 执行Pipeline中累积的所有命令
            # 注: 事件数据不设置维度缓存，因此也不需要设置维度缓存过期时间
            redis_pipeline.execute()

        # ======================== Step5: 更新last_checkpoint缓存 ========================
        # last_checkpoint记录每个维度最后一次检测的时间点
        # Detect模块用于判断数据连续性，Alert模块用于判断告警是否恢复
        for md5_dimension_last_point_key, point_timestamp in list(last_checkpoints.items()):
            try:
                md5_dimension, strategy_id, item_id, level = md5_dimension_last_point_key
                # 更新维度的最后检测点时间戳
                CheckResult.update_last_checkpoint_by_d_md5(strategy_id, item_id, md5_dimension, point_timestamp, level)
            except Exception as e:
                msg = f"set check result cache last_check_point error:{e}"
                logger.exception(msg)
            # 刷新last_checkpoint缓存的过期时间，防止缓存被清理
            CheckResult.expire_last_checkpoint_cache(strategy_id=strategy_id, item_id=item_id)

    def push(self, output_client=None):
        """
        将事件记录推送到Redis异常队列，供Detect模块消费处理

        参数:
            output_client: Redis客户端实例，默认为None时使用内置客户端

        执行步骤:
            1. QoS流控检查 - 防止数据量过大导致系统过载
            2. 推送检测结果 - 将事件推送到检测结果队列
            3. 维度去重检查 - 检测同一维度是否有重复事件，记录告警日志
            4. 优先级抑制检查 - 根据策略优先级决定事件是否被抑制
            5. 数据分组整理 - 按策略ID和监控项ID对事件进行分组
            6. 批量推送Redis - 使用Pipeline批量写入异常队列
            7. 发送信号通知 - 推送异常信号通知Detect模块处理

        数据流向图:
            record_list (事件列表)
                ↓
            ┌─────────────────────────────────────────────────┐
            │  Step1-2: QoS检查 + 推送检测结果                 │
            └─────────────────────────────────────────────────┘
                ↓
            ┌─────────────────────────────────────────────────┐
            │  Step3: 维度去重检查 (按md5_dimension分组)        │
            │  - 同一维度多个事件 → 记录warning日志             │
            └─────────────────────────────────────────────────┘
                ↓
            ┌─────────────────────────────────────────────────┐
            │  Step4: 优先级抑制检查 (PriorityChecker)         │
            │  - 高优先级策略抑制低优先级策略的相同维度事件      │
            └─────────────────────────────────────────────────┘
                ↓
            ┌─────────────────────────────────────────────────┐
            │  Step5: 数据分组整理                             │
            │  - 过滤条件: is_retains[item_id]=True           │
            │             且 inhibitions[item_id]=False       │
            │  - 分组结构: {strategy_id: {item_id: [events]}} │
            └─────────────────────────────────────────────────┘
                ↓
            ┌─────────────────────────────────────────────────┐
            │  Step6-7: Redis批量写入                          │
            │  - ANOMALY_LIST_KEY: 异常事件队列                │
            │  - ANOMALY_SIGNAL_KEY: 异常信号通知队列          │
            └─────────────────────────────────────────────────┘
        """
        # Step1: QoS流控检查，防止系统过载
        self.check_qos()
        # Step2: 推送检测结果到检测结果队列
        self.push_to_check_result()

        # ======================== Step3: 维度去重检查 ========================
        # 按维度(md5_dimension)分组，检测是否存在同一维度的重复事件
        dimension_groups = {}
        for e in self.record_list:
            dimension_groups.setdefault(e.md5_dimension, []).append(e)

        # 如果同一维度存在多个事件，记录告警日志（可能是数据异常或重复上报）
        for dimension, records in dimension_groups.items():
            if len(records) > 1:
                logger.warning(f"the same event has {len(records)} records, record: {records[0].raw_data}")

        # ======================== Step4: 优先级抑制检查 ========================
        # 根据策略优先级判断事件是否被抑制
        # 高优先级策略会抑制低优先级策略的相同维度事件，结果存储在 e.inhibitions[item_id] 中
        PriorityChecker.check_records(self.record_list)

        # ======================== Step5: 数据分组整理 ========================
        # 按策略ID和监控项ID对事件进行分组，便于后续批量推送
        # 数据结构: {strategy_id: {item_id: [event_str, ...]}}
        pending_to_push = {}
        for e in self.record_list:
            # 将事件记录序列化为字符串格式
            data_str = e.to_str()
            for item in e.items:
                strategy_id = item.strategy.id
                item_id = item.id
                # 过滤条件：
                #   1. is_retains[item_id] = True: 事件被保留（未被过滤）
                #   2. inhibitions[item_id] = False: 事件未被优先级抑制
                if e.is_retains[item_id] and not e.inhibitions[item_id]:
                    pending_to_push.setdefault(strategy_id, {}).setdefault(item_id, []).append(data_str)

        # ======================== Step6: 批量推送到Redis异常队列 ========================
        # 收集需要通知的异常信号（格式: "strategy_id.item_id"）
        anomaly_signal_list = []
        # 使用Pipeline批量操作，提升Redis写入性能
        client = output_client or key.ANOMALY_LIST_KEY.client
        pipeline = client.pipeline()

        for strategy_id, item_to_event_record in list(pending_to_push.items()):
            # 统计推送的事件总数，用于监控指标上报
            record_count = sum([len(records) for records in item_to_event_record.values()])
            metrics.ACCESS_PROCESS_PUSH_DATA_COUNT.labels(metrics.TOTAL_TAG, "event").inc(record_count)

            for item_id, event_list in list(item_to_event_record.items()):
                # 构建Redis队列Key: access.data.anomaly_list.{strategy_id}.{item_id}
                queue_key = key.ANOMALY_LIST_KEY.get_key(strategy_id=strategy_id, item_id=item_id)
                # 使用LPUSH将事件批量推入队列头部（Detect模块从尾部RPOP消费）
                pipeline.lpush(queue_key, *event_list)
                # 记录异常信号，用于通知Detect模块有新数据到达
                anomaly_signal_list.append(f"{strategy_id}.{item_id}")
                # 设置队列过期时间，防止数据堆积
                pipeline.expire(queue_key, key.ANOMALY_LIST_KEY.ttl)

        # 执行Pipeline中的所有命令
        pipeline.execute()

        # ======================== Step7: 发送异常信号通知 ========================
        # 向信号队列推送通知，告知Detect模块有新的异常数据需要处理
        if anomaly_signal_list:
            client = output_client or key.ANOMALY_SIGNAL_KEY.client
            # 推送异常信号到通知队列: access.data.anomaly_signal
            client.lpush(key.ANOMALY_SIGNAL_KEY.get_key(), *anomaly_signal_list)
            client.expire(key.ANOMALY_SIGNAL_KEY.get_key(), key.ANOMALY_SIGNAL_KEY.ttl)

        logger.info("push %s event_record to match queue finished(%s)", self.__class__.__name__, len(self.record_list))


class AccessCustomEventGlobalProcess(BaseAccessEventProcess):
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
        根据事件类型实例化数据
        :param raw_data: 原始数据
        :return: 实例化后的数据
        """

        # 获取告警类型
        alarms = raw_data.get("value")
        if alarms:
            alarm_type = alarms[0]["extra"]["type"]
        else:
            alarm_type = self.fetch_custom_event_alarm_type(raw_data)

        # 根据告警类型分配实例化方法
        if alarm_type in self.OPENED_WHITE_LIST:
            if alarm_type == self.TYPE_PING:
                if settings.ENABLE_PING_ALARM:
                    return PingEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_AGENT:
                if settings.ENABLE_AGENT_ALARM:
                    return AgentEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_COREFILE:
                return CorefileEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_DISK_FULL:
                return DiskFullEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_DISK_READONLY:
                return DiskReadonlyEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_OOM:
                return OOMEvent(raw_data, self.strategies)
            elif alarm_type == self.TYPE_GSE_CUSTOM_STR_EVENT:
                return GseCustomStrEventRecord(raw_data, self.strategies)
            elif alarm_type == self.TYPE_GSE_PROCESS_EVENT:
                return GseProcessEventRecord(raw_data, self.strategies)

    def pull(self):
        """
        从 Kafka 拉取原始事件数据并生成事件记录

        参数:
            无（使用实例属性 self.data_id, self.topic）

        返回值:
            无（结果存储在 self.record_list 中）

        执行步骤:
            1. 校验 topic 是否存在
            2. 根据集群名称构建 Kafka 消费组前缀
            3. 获取分布式锁，确保同一 data_id 不会被多个 worker 同时处理
            4. 从 Kafka 批量拉取消息（最多 MAX_RETRIEVE_NUMBER 条）
            5. 如果拉取数量达到上限，异步发布新任务继续消费
            6. 解析每条消息，根据事件类型实例化对应的 EventRecord
            7. 对有效记录进行展平处理（flat），存入 record_list

        数据流:
            Kafka Topic --> 原始消息 --> JSON解析 --> EventRecord实例化
                       --> check()校验 --> flat()展平 --> self.record_list
        """

        from alarm_backends.service.access.tasks import run_access_event_handler

        record_list = []

        # ==================== 步骤1: Topic 校验 ====================
        if not self.topic:
            logger.warning(f"[access] dataid:({self.data_id}) no topic")
            return

        # ==================== 步骤2: 构建消费组前缀 ====================
        # 消费组前缀格式: {cluster_name}.access.event.{data_id}
        # 用于 Kafka 消费组的命名，确保不同集群的消费组隔离
        cluster_name = get_cluster().name
        if cluster_name == "default":
            group_prefix = f"access.event.{self.data_id}"
        else:
            group_prefix = f"{cluster_name}.access.event.{self.data_id}"

        try:
            kafka_queue = self.get_kafka_queue(topic=self.topic, group_prefix=group_prefix)

            # ==================== 步骤3: 分布式锁保护 ====================
            # 使用 service_lock 确保同一 data_id 在同一时刻只有一个 worker 处理
            # 避免多个 worker 同时消费同一 topic 导致的重复处理问题
            try:
                with service_lock(ACCESS_EVENT_LOCKS, data_id=self.data_id):
                    # 加锁成功，拉取数据
                    # ==================== 步骤4: 批量拉取消息 ====================
                    result = kafka_queue.take(count=MAX_RETRIEVE_NUMBER, timeout=1)
                    # 数据拉取结束，释放锁
            except LockError:
                # 加锁失败，说明有其他 worker 正在处理，当前任务稍后重试
                logger.info(f"[get service lock fail] access event dataid:({self.data_id}). will process later")
                return
            except Exception as e:
                logger.exception(f"[process error] access event dataid:({self.data_id}) reason：{e}")
                return

            # ==================== 步骤5: 判断是否需要继续消费 ====================
            # 如果本次拉取的消息数量刚好等于上限，说明 Kafka 中可能还有更多数据
            # 此时异步发布一个新任务继续消费，实现背压控制
            if len(result) == MAX_RETRIEVE_NUMBER:
                run_access_event_handler.delay(data_id=self.data_id, topic=self.topic)

            # ==================== 步骤6-7: 消息解析与记录生成 ====================
            for m in result:
                if not m:
                    continue
                try:
                    # GSE格式变动的临时兼容方案：
                    # 判断消息结尾是否多了 \x00（空字符）或 \n（换行符），多了先去掉
                    data = json.loads(m[:-1] if m[-1] == "\x00" or m[-1] == "\n" else m)

                    # 根据事件类型（如 OOM、进程异常、自定义事件等）实例化对应的 EventRecord
                    event_record = self._instantiate_by_event_type(data)

                    # 校验记录有效性，并展平（一条原始数据可能产生多条记录）
                    if event_record and event_record.check():
                        record_list.extend(event_record.flat())
                except Exception as e:
                    logger.exception("topic(%s) loads alarm(%s) failed, %s", self.topic, m, e)

            # 将本次拉取解析的记录追加到实例的 record_list 中
            self.record_list.extend(record_list)
        except Exception as e:
            logger.exception("topic(%s) poll alarm failed, %s", self.topic, e)

        # 记录拉取数据量的监控指标
        metrics.ACCESS_EVENT_PROCESS_PULL_DATA_COUNT.labels(self.data_id).inc(len(record_list))
        logger.info("topic(%s) poll alarm list(%s)", self.topic, len(record_list))

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
