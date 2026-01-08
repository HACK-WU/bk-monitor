"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import itertools
import logging
import os
import signal
import socket
import time
import uuid
from collections import defaultdict

from django.conf import settings
import kafka
from kafka.consumer.fetcher import ConsumerRecord

from alarm_backends.core.cache import key
from alarm_backends.service.access.tasks import run_access_event_handler_v2
from bkmonitor.utils.common_utils import safe_int
from bkmonitor.utils.thread_backend import InheritParentThread
from constants.common import DEFAULT_TENANT_ID
from constants.strategy import MAX_RETRIEVE_NUMBER
from core.drf_resource import api


logger = logging.getLogger("access.event")


def always_retry(wait):
    def decorator(func):
        def wrapper(*args, **kwargs):
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.exception(f"alert handler error: {func.__name__}: {e}")
                    time.sleep(wait)

        return wrapper

    return decorator


class EventPoller:
    def __init__(self):
        self.topics_map = {}
        self.pod_id = socket.gethostname().rsplit("-", 1)[-1] or str(uuid.uuid4())[:8]
        self.refresh()
        self.should_exit = False
        self.consumer = None
        self.polled_info = defaultdict(int)

    def get_consumer(self):
        if self.consumer is None:
            self.consumer = self.create_consumer()
        return self.consumer

    def create_consumer(self):
        """
        创建Kafka消费者实例，用于从事件Topic拉取告警事件数据

        返回值:
            kafka.KafkaConsumer: 已订阅事件Topic的Kafka消费者实例

        数据流向图:
            Kafka Broker
                │
                ▼
            ┌────────────────────────────────────────────────────────────────┐
            │  KafkaConsumer (消费者组: {APP_CODE}.access.event)              │
            │  ┌──────────────────────────────────────────────────────────┐  │
            │  │ 分区分配策略: RoundRobin (轮询均衡分配)                    │  │
            │  │ 偏移量重置: latest (从最新消息开始消费)                    │  │
            │  │ 自动提交: 由配置决定                                      │  │
            │  └──────────────────────────────────────────────────────────┘  │
            └────────────────────────────────────────────────────────────────┘
                │
                ▼ (订阅topics_map中的所有Topic)
            ┌────────────────────────────────────────────────────────────────┐
            │  事件Topic列表:                                                │
            │  - GSE基础告警Topic (GSE_BASE_ALARM_DATAID)                    │
            │  - 自定义事件Topic (GSE_CUSTOM_EVENT_DATAID)                   │
            │  - 进程上报Topic (GSE_PROCESS_REPORT_DATAID)                   │
            └────────────────────────────────────────────────────────────────┘

        配置项说明:
            - bootstrap_servers: Kafka集群地址列表
            - group_id: 消费者组ID，同组消费者共享分区
            - client_id: 客户端标识，用于日志和监控追踪
            - enable_auto_commit: 是否自动提交偏移量
            - session_timeout_ms: 会话超时时间(30秒)，超时则触发Rebalance
            - max_partition_fetch_bytes: 单次拉取最大字节数(5MB)
            - partition_assignment_strategy: 分区分配策略(RoundRobin轮询)
            - auto_offset_reset: 无有效偏移量时的重置策略(latest从最新开始)
        """
        # 构建消费者组名称: {APP_CODE}.access.event
        group_name = f"{settings.APP_CODE}.access.event"

        # 创建Kafka消费者实例
        consumer = kafka.KafkaConsumer(
            # Kafka集群连接地址列表
            bootstrap_servers=[f"{host}:{settings.KAFKA_PORT}" for host in settings.KAFKA_HOST],
            # 消费者组ID，同组消费者共享Topic分区，实现负载均衡
            group_id=group_name,
            # 客户端ID，格式: {group_name}-{pod_id}，便于追踪和调试
            client_id=f"{group_name}-{self.pod_id}",
            # 偏移量自动提交开关，由配置决定
            enable_auto_commit=settings.KAFKA_AUTO_COMMIT,
            # 会话超时30秒，超时未发送心跳则被踢出消费者组触发Rebalance
            session_timeout_ms=30000,
            # 单分区单次拉取最大5MB，增大批量拉取能力提升吞吐量
            max_partition_fetch_bytes=1024 * 1024 * 5,
            # 分区分配策略: RoundRobin轮询，均衡分配分区到各消费者
            partition_assignment_strategy=[kafka.coordinator.assignors.roundrobin.RoundRobinPartitionAssignor],
            # 无有效偏移量时从最新消息开始消费，避免重复处理历史数据
            auto_offset_reset="latest",
        )

        # 订阅topics_map中的所有事件Topic
        consumer.subscribe(list(self.topics_map.keys()))
        return consumer

    def poll_once(self) -> list[ConsumerRecord]:
        """
        执行一次Kafka消息拉取操作

        返回值:
            List[ConsumerRecord]: 从Kafka拉取的消息列表，每个元素是一个ConsumerRecord对象，
                                  包含topic、partition、offset、value等属性

        执行步骤:
            1. 获取或创建Kafka消费者实例
            2. 从已订阅的Topic中批量拉取消息
            3. 将多分区消息合并为单一列表返回

        数据流向图:
            Kafka Broker (多分区)
                │
                ▼ poll(timeout_ms=500, max_records=MAX_RETRIEVE_NUMBER)
            ┌─────────────────────────────────────────────────────────────┐
            │  records: Dict[TopicPartition, List[ConsumerRecord]]        │
            │  {                                                          │
            │    TopicPartition(topic='event_topic', partition=0): [...], │
            │    TopicPartition(topic='event_topic', partition=1): [...], │
            │  }                                                          │
            └─────────────────────────────────────────────────────────────┘
                │
                ▼ itertools.chain.from_iterable(展平多分区消息)
            ┌─────────────────────────────────────────────────────────────┐
            │  messages: List[ConsumerRecord]                             │
            │  [record1, record2, record3, ...]                           │
            └─────────────────────────────────────────────────────────────┘
                │
                ▼ 返回给调用方
            start() 方法 → 按topic分类 → push_to_redis()

        参数说明:
            - timeout_ms=500: 拉取超时500毫秒，避免长时间阻塞
            - max_records=MAX_RETRIEVE_NUMBER: 单次最大拉取记录数，控制内存和处理压力
        """
        # 步骤1: 获取Kafka消费者实例(懒加载模式)
        consumer = self.get_consumer()
        logger.debug(f"[start event poller] topics: {consumer.subscription()}, pod_id: {self.pod_id}")

        # 步骤2: 批量拉取消息，超时500ms，最多拉取MAX_RETRIEVE_NUMBER条
        # 返回值是 Dict[TopicPartition, List[ConsumerRecord]] 结构
        # records 数据结构示例:
        # {
        #     TopicPartition(topic='0bkmonitor_10010', partition=0): [
        #         ConsumerRecord(topic='0bkmonitor_10010', partition=0, offset=12345,
        #                        key=None, value=b'{"data": [...], "time": 1704700000}'),
        #         ConsumerRecord(topic='0bkmonitor_10010', partition=0, offset=12346,
        #                        key=None, value=b'{"data": [...], "time": 1704700001}'),
        #     ],
        #     TopicPartition(topic='0bkmonitor_10010', partition=1): [
        #         ConsumerRecord(topic='0bkmonitor_10010', partition=1, offset=67890,
        #                        key=None, value=b'{"data": [...], "time": 1704700002}'),
        #     ],
        # }
        # ConsumerRecord = collections.namedtuple("ConsumerRecord",
        #     ["topic", "partition", "offset", "timestamp", "timestamp_type",
        #      "key", "value", "headers", "checksum", "serialized_key_size", "serialized_value_size", "serialized_header_size"])
        records = consumer.poll(500, max_records=MAX_RETRIEVE_NUMBER)

        # 步骤3: 将多分区的消息列表展平为单一列表
        # records.values() 返回各分区的消息列表，chain.from_iterable 将其合并
        messages = list(itertools.chain.from_iterable(records.values()))

        logger.debug(f"[event poller] pulled {len(messages)}, pod_id: {self.pod_id}")
        return messages

    def close(self):
        if self.consumer is not None:
            try:
                # 先尝试正常唤醒消费者线程
                self.consumer.wakeup()
                # 确保关闭前完成所有pending操作
                self.consumer.commit()
            except Exception as e:
                logger.warning(f"[event poller] consumer wakeup/commit failed: {e}")
            finally:
                try:
                    self.consumer.close()
                except Exception as e:
                    logger.exception(f"[event poller] consumer close failed: {e}")
                self.consumer = None

    def _stop(self, signum, frame):
        logger.info(f"[event poller] received signal {signum}, shutting down...")
        self.should_exit = True
        self.close()  # 确保信号处理也调用增强版的close

    def __del__(self):
        self.should_exit = True

    @always_retry(10)
    def kick_task(self):
        """
        周期性触发事件处理任务的调度循环

        执行流程:
        1. 每5秒检查一次Redis信号通道
        2. 获取待处理的data_id列表
        3. 为每个data_id异步投递处理任务
        4. 清空本轮轮询统计信息

        数据流向图:
            ┌─────────────────────────────────────────────────────────────────┐
            │                 kick_task() 调度循环                             │
            │                 (后台线程，周期5秒)                               │
            ├─────────────────────────────────────────────────────────────────┤
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ while True 死循环                                            ││
            │  │    │                                                          ││
            │  │    ▼                                                          ││
            │  │  ┌─────────────────────────────────────────────────────────┐││
            │  │  │ 1. 时间间隔控制                                          │││
            │  │  │    if time.time() - check_time < 5.0:                    │││
            │  │  │        sleep(1)  ──► 每1秒检查一次，等待满5秒             │││
            │  │  └─────────────────────────────────────────────────────────┘││
            │  │              │                                               ││
            │  │              ▼                                               ││
            │  │  ┌─────────────────────────────────────────────────────────┐││
            │  │  │ 2. 获取Redis信号通道的data_id集合                        │││
            │  │  │    signal_channel = "bkmonitor:access:event:signal"      │││
            │  │  │    signals = client.smembers(signal_channel)             │││
            │  │  │    ──► 返回Set类型: {10010, 10011, ...}                  │││
            │  │  └─────────────────────────────────────────────────────────┘││
            │  │              │                                               ││
            │  │              ▼                                               ││
            │  │  ┌─────────────────────────────────────────────────────────┐││
            │  │  │ 3. 遍历data_id，投递Celery任务                           │││
            │  │  │    for data_id in signals:                               │││
            │  │  │        run_access_event_handler_v2.delay(data_id)        │││
            │  │  │        ──► 异步处理该data_id的告警列表                     │││
            │  │  │        ──► 记录日志: 包含data_id、pod_id、告警数量等       │││
            │  │  └─────────────────────────────────────────────────────────┘││
            │  │              │                                               ││
            │  │              ▼                                               ││
            │  │  ┌─────────────────────────────────────────────────────────┐││
            │  │  │ 4. 重置状态                                              │││
            │  │  │    check_time = time.time()  ──► 重置检查时间           │││
            │  │  │    polled_info.clear()        ──► 清空本轮统计信息      │││
            │  │  └─────────────────────────────────────────────────────────┘││
            │  │              │                                               ││
            │  │              └──► 返回步骤1，循环执行                         ││
            │  └─────────────────────────────────────────────────────────────┘│
            └─────────────────────────────────────────────────────────────────┘

        关键数据结构:
            - signals (Set): Redis集合，存储待处理的data_id列表
            - polled_info (defaultdict[int, int]): 记录每个data_id本轮轮询的告警数量
        """
        # 初始化检查时间戳，用于控制轮询间隔
        check_time = time.time()
        while True:
            # 步骤1: 等待5秒间隔，避免频繁轮询Redis
            # 使用sleep(1)而不是直接sleep(5)，可以更快响应should_exit信号
            if time.time() - check_time < 5.0:
                time.sleep(1)

            # 步骤2: 从Redis信号通道获取待处理的data_id集合
            # EVENT_SIGNAL_KEY: Redis中存储待处理data_id的集合键
            # signals: 返回Set类型，包含需要处理告警的data_id列表
            client = key.EVENT_SIGNAL_KEY.client
            signal_channel = key.EVENT_SIGNAL_KEY.get_key()
            signals: set[str] = client.smembers(signal_channel)

            # 步骤3: 为每个data_id异步投递Celery任务
            # run_access_event_handler_v2.delay: 异步投递Celery任务
            # 该任务会从Redis EVENT_LIST_KEY中获取告警列表并进行处理
            for data_id in signals:
                run_access_event_handler_v2.delay(data_id)
                logger.info(
                    "[access event poller] data_id(%s) pod_id(%s) push alarm list(%s) to redis %s",
                    data_id,
                    self.pod_id,
                    self.polled_info[data_id],
                    key.EVENT_LIST_KEY.get_key(data_id=data_id),
                )

            # 步骤4: 重置检查时间并清空轮询统计信息
            # polled_info: 记录每个data_id本轮从Kafka拉取的告警数量
            # 清空统计信息后，下一轮会重新开始计数
            check_time = time.time()
            self.polled_info.clear()

    def start(self):
        """
        启动事件轮询器主循环，持续从Kafka拉取事件并推送到Redis

        执行步骤:
            1. 注册系统信号处理器(SIGTERM/SIGINT)，支持优雅退出
            2. 启动后台线程kick_task，周期性触发事件处理任务
            3. 进入主循环，持续执行:
               a. 调用poll_once()从Kafka批量拉取消息
               b. 将消息按topic分类聚合
               c. 将各topic的消息批量推送到Redis
            4. 收到退出信号或发生KeyboardInterrupt时，关闭消费者并退出

        数据流向图:
            ┌─────────────────────────────────────────────────────────────────┐
            │                     start() 主循环                              │
            ├─────────────────────────────────────────────────────────────────┤
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 1. 信号注册                                                 ││
            │  │    SIGTERM ──┬──► _stop() ──► should_exit=True              ││
            │  │    SIGINT  ──┘                                              ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      │
            │                          ▼                                      │
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 2. 后台线程启动                                             ││
            │  │    kick_task线程 ──► 每5秒检查Redis信号 ──► 投递Celery任务   ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      │
            │                          ▼                                      │
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 3. 主循环 (while not should_exit)                           ││
            │  │    ┌─────────────────────────────────────────────────────┐  ││
            │  │    │ poll_once()                                         │  ││
            │  │    │    │                                                │  ││
            │  │    │    ▼                                                │  ││
            │  │    │ messages: [ConsumerRecord, ...]                     │  ││
            │  │    │    │                                                │  ││
            │  │    │    ▼ (按topic分类聚合)                              │  ││
            │  │    │ topic_data: {                                       │  ││
            │  │    │   "topic_a": [data1, data2, ...],                   │  ││
            │  │    │   "topic_b": [data3, data4, ...],                   │  ││
            │  │    │ }                                                   │  ││
            │  │    │    │                                                │  ││
            │  │    │    ▼ (遍历推送到Redis)                              │  ││
            │  │    │ push_to_redis(topic, data_list)                     │  ││
            │  │    └─────────────────────────────────────────────────────┘  ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      │
            │                          ▼ (should_exit=True)                   │
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 4. 清理退出                                                 ││
            │  │    close() ──► 提交偏移量 ──► 关闭Kafka消费者               ││
            │  └─────────────────────────────────────────────────────────────┘│
            └─────────────────────────────────────────────────────────────────┘

        异常处理:
            - KeyboardInterrupt: 设置should_exit=True，触发优雅退出
            - 其他Exception: 记录日志后继续循环，保证服务高可用
        """
        # 步骤1: 注册系统信号处理器，支持优雅退出
        # SIGTERM: kill命令默认信号，容器/进程管理器常用
        # SIGINT: Ctrl+C中断信号
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)

        # 步骤2: 启动后台任务调度线程(消费者)
        # kick_task线程负责周期性检查Redis信号通道，触发Celery异步处理任务
        kick_task = InheritParentThread(target=self.kick_task)
        kick_task.start()

        # 步骤3: 进入主循环，持续拉取和推送事件数据
        while not self.should_exit:
            try:
                topic_data = {}

                # 步骤3a: 从Kafka批量拉取消息
                messages = self.poll_once()

                # 步骤3b: 将消息按topic分类聚合
                # 同一topic的消息聚合后批量推送，减少Redis操作次数
                # message的属性:
                #   ["topic", "partition", "offset", "timestamp", "timestamp_type",
                #    "key", "value", "headers", "checksum", "serialized_key_size", "serialized_value_size",
                #    "serialized_header_size"]
                for message in messages:
                    topic = message.topic
                    data = message.value
                    if topic not in topic_data:
                        topic_data[topic] = []
                    topic_data[topic].append(data)

                # 步骤3c: 遍历各topic，批量推送数据到Redis
                for topic, data_list in topic_data.items():
                    if data_list:
                        try:
                            self.push_to_redis(topic, data_list)
                        except KeyboardInterrupt:
                            # 推送过程中收到中断信号，标记退出
                            self.should_exit = True
                        except Exception:
                            # 单个topic推送失败不影响其他topic，继续处理
                            continue
            except KeyboardInterrupt:
                # 主循环收到中断信号，标记退出
                self.should_exit = True
            except Exception as e:
                # 其他异常记录日志后继续循环，保证服务高可用
                logger.exception(f"[event poller] start poll error: {e}")

        # 步骤4: 退出循环后，关闭Kafka消费者并清理资源
        self.close()

    def send_signal(self, data_id):
        client = key.EVENT_SIGNAL_KEY.client
        signal_channel = key.EVENT_SIGNAL_KEY.get_key()
        client.sadd(signal_channel, data_id)
        client.expire(signal_channel, key.EVENT_SIGNAL_KEY.ttl)

    def push_to_redis(self, topic, messages):
        """
        将Kafka拉取的告警事件消息批量推送到Redis队列

        参数:
            topic (str): Kafka主题名称，对应某个数据源的事件Topic
            messages (List[str]): 告警事件消息列表，每个元素为序列化的事件JSON字符串

        返回值:
            None

        执行步骤:
            1. 清理消息尾部字符(移除\x00和\n等特殊字符)
            2. 根据topic获取对应的data_id
            3. 获取Redis客户端和数据通道
            4. 将消息批量推送到Redis列表左侧(lpush)
            5. 设置Redis键的过期时间
            6. 向Redis信号通道添加data_id，触发处理任务
            7. 更新轮询统计信息

        数据流向图:
            ┌─────────────────────────────────────────────────────────────────┐
            │                   push_to_redis() 推送流程                       │
            ├─────────────────────────────────────────────────────────────────┤
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 输入: topic="event_topic", messages=[msg1, msg2, msg3]      ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 1. 消息清理                                                 ││
            │  │    移除消息尾部的\x00和\n等特殊字符                          ││
            │  │    messages = [m[:-1] if m[-1] in ["\\x00", "\\n"] else m  ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 2. 获取映射关系                                             ││
            │  │    data_id = self.topics_map[topic]                        ││
            │  │    ──► 根据topic查找对应的data_id                           ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 3. 获取Redis连接和通道                                      ││
            │  │    data_channel = EVENT_LIST_KEY.get_key(data_id=data_id)  ││
            │  │    ──► 格式: "bkmonitor:access:event:list:{data_id}"        ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 4. 批量推送到Redis左侧                                      ││
            │  │    lpush(data_channel, *messages)                          ││
            │  │    ──► 新消息从左侧推入，右侧为旧消息                        ││
            │  │    ──► 拉取时从右侧取出，实现FIFO队列                       ││
            │  │    Redis队列状态:                                          ││
            │  │    ┌──────────────────────────────────────────────┐        ││
            │  │    │ 左侧(lpush入口) │ ... │ msg1 │ msg2 │ msg3 │        ││
            │  │    └──────────────────────────────────────────────┘        ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 5. 设置过期时间                                             ││
            │  │    expire(data_channel, EVENT_LIST_KEY.ttl)                 ││
            │  │    ──► 避免Redis内存泄漏，过期自动删除                      ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 6. 发送触发信号                                             ││
            │  │    send_signal(data_id)                                     ││
            │  │    ──► 将data_id添加到Redis信号通道                          ││
            │  │    ──► kick_task线程检测到信号后投递Celery任务                ││
            │  └─────────────────────────────────────────────────────────────┘│
            │                          │                                      ││
            │                          ▼                                      ││
            │  ┌─────────────────────────────────────────────────────────────┐│
            │  │ 7. 更新统计信息                                             ││
            │  │    polled_info[data_id] += len(messages)                     ││
            │  │    ──► 记录本轮轮询该data_id推送的告警数量                   ││
            │  └─────────────────────────────────────────────────────────────┘│
            └─────────────────────────────────────────────────────────────────┘

        关键设计:
            - 使用lpush从左侧推入，_pull_from_redis使用lrange从右侧拉取，实现FIFO队列
            - 设置过期时间防止Redis内存泄漏
            - 通过信号机制触发异步处理，实现解耦
        """
        # 空消息列表直接返回，避免无效的Redis操作
        if not messages:
            return

        # 清理消息尾部的特殊字符(\x00: C语言字符串结束符, \n: 换行符)
        # 这些字符可能来自数据源的序列化问题，需要清理以避免后续解析错误
        messages = [m[:-1] if m[-1] == "\x00" or m[-1] == "\n" else m for m in messages]

        # 根据Kafka topic查找对应的数据ID
        # topics_map: {topic: data_id} 的映射关系
        data_id = self.topics_map[topic]

        # 获取Redis客户端和数据通道
        # EVENT_LIST_KEY: 告警事件列表的Redis键前缀
        # data_channel: 具体的Redis键，格式为 "bkmonitor:access:event:list:{data_id}"
        redis_client = key.EVENT_LIST_KEY.client
        data_channel = key.EVENT_LIST_KEY.get_key(data_id=data_id)

        # 将消息批量推送到Redis列表左侧
        # lpush: 从列表左侧插入新消息，右侧为旧消息
        # 配合_pull_from_redis的lrange从右侧拉取，实现FIFO先进先出队列
        redis_client.lpush(data_channel, *messages)

        # 设置Redis键的过期时间，避免内存泄漏
        # 即使消息未被及时处理，过期后也会自动清理
        redis_client.expire(data_channel, key.EVENT_LIST_KEY.ttl)

        # 向Redis信号通道添加data_id，触发处理任务
        # kick_task线程会检测到这个信号，并投递Celery异步任务处理该data_id的告警列表
        self.send_signal(data_id)

        # 更新轮询统计信息，记录本轮推送的告警数量
        # polled_info: defaultdict(int), 记录每个data_id本轮轮询推送的告警数量
        # 这个信息会被kick_task使用，用于日志记录
        self.polled_info[data_id] += len(messages)

        # 记录调试日志，便于追踪数据流向
        logger.debug(
            "data_id(%s) topic(%s) pod_id(%s) push alarm list(%s) to redis %s",
            data_id,
            topic,
            self.pod_id,
            len(messages),
            data_channel,
        )

    def refresh(self):
        self.topics_map = {}
        DISABLE_EVENT_DATAID = os.getenv("DISABLE_EVENT_DATAID", "0")
        disabled_data_ids = {safe_int(i) for i in DISABLE_EVENT_DATAID.split(",")}
        data_ids = {
            settings.GSE_BASE_ALARM_DATAID,
            settings.GSE_CUSTOM_EVENT_DATAID,
            settings.GSE_PROCESS_REPORT_DATAID,
        } - disabled_data_ids
        for data_id in data_ids:
            topic_info = api.metadata.get_data_id(
                bk_tenant_id=DEFAULT_TENANT_ID, bk_data_id=data_id, with_rt_info=False
            )
            self.topics_map[topic_info["mq_config"]["storage_config"]["topic"]] = data_id
