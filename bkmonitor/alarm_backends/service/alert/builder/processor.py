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
import time

from django.utils.translation import gettext as _
from elasticsearch.helpers import BulkIndexError

from alarm_backends.constants import CONST_MINUTES
from alarm_backends.core.alert import Alert, Event
from alarm_backends.core.alert.alert import AlertUIDManager
from alarm_backends.core.cache.assign import AssignCacheManager
from alarm_backends.core.cache.key import ALERT_UPDATE_LOCK
from alarm_backends.core.circuit_breaking.manager import AlertBuilderCircuitBreakingManager
from alarm_backends.core.lock.service_lock import multi_service_lock
from alarm_backends.service.alert.enricher import AlertEnrichFactory, EventEnrichFactory
from alarm_backends.service.alert.manager.tasks import send_check_task
from alarm_backends.service.alert.processor import BaseAlertProcessor
from bkmonitor.documents import AlertLog, EventDocument
from bkmonitor.documents.base import BulkActionType
from constants.action import AssignMode
from constants.alert import EventStatus
from core.prometheus import metrics


class AlertBuilder(BaseAlertProcessor):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("alert.builder")
        circuit_breaking_manager = AlertBuilderCircuitBreakingManager()
        self.circuit_breaking_manager = circuit_breaking_manager

    def get_unexpired_events(self, events: list[Event]):
        """
        先判断关联事件是否已经过期
        """
        current_alerts = self.get_current_alerts(events)
        unexpired_events = []
        expired_events = []
        for event in events:
            alert: Alert = current_alerts.get(event.dedupe_md5)
            expired_time = alert.end_time - CONST_MINUTES if alert and alert.end_time else None
            if event.is_dropped() or event.is_expired(expired_time):
                # 如果事件已经被丢弃，或者已经过期，则不需要处理
                expired_events.append(event)
                self.logger.info(
                    "[event drop] event(%s) strategy(%s) is dropped or expired(%s), skip build alert",
                    event.event_id,
                    event.strategy_id,
                    expired_time,
                )
                continue
            unexpired_events.append(event)

        return unexpired_events

    def get_current_alerts(self, events: list[Event]):
        """
        获取关联事件对应的告警缓存内容
        """
        events_dedupe_md5_list = set({event.dedupe_md5 for event in events})
        if not events_dedupe_md5_list:
            return {}

        cached_alerts = self.list_alerts_content_from_cache(events)
        return {alert.dedupe_md5: alert for alert in cached_alerts}

    def dedupe_events_to_alerts(self, events: list[Event]):
        """
        事件去重并构建告警对象（核心聚合方法）

        参数:
            events (list[Event]): 待处理的事件列表

        返回值:
            list[Alert]: 构建并保存成功的告警对象列表

        执行流程:
        1. 过滤过期事件
        2. 分布式锁控制：防止并发修改同一告警
        3. 构建告警：加锁成功的事件构建告警并持久化
        4. 延迟重试：加锁失败的事件延后5秒重新投递
        5. 信号发送：触发告警通知和周期检测任务
        """

        def _report_latency(report_events):
            """上报事件处理延迟指标"""
            latency_logged = False
            for event in report_events:
                latency = event.get_process_latency()
                if not latency:
                    continue
                # 上报触发延迟指标
                trigger_latency = latency.get("trigger_latency", 0)
                if trigger_latency > 0:
                    metrics.ALERT_PROCESS_LATENCY.labels(
                        bk_data_id=event.data_id,
                        topic=event.topic,
                        strategy_id=metrics.TOTAL_TAG,
                    ).observe(trigger_latency)
                    # 记录超过60秒的大延迟告警
                    if trigger_latency > 60 and not latency_logged:
                        self.logger.warning(
                            "[trigger to alert.builder]big latency %s,  strategy(%s)",
                            trigger_latency,
                            event.strategy_id,
                        )
                        latency_logged = True
                # 上报接入层到告警处理的延迟
                if latency.get("access_latency"):
                    metrics.ACCESS_TO_ALERT_PROCESS_LATENCY.labels(
                        bk_data_id=event.data_id,
                        topic=event.topic,
                        strategy_id=metrics.TOTAL_TAG,
                    ).observe(latency["access_latency"])

        # 步骤1: 过滤过期事件
        events = self.get_unexpired_events(events)
        if not events:
            return []

        # 步骤2: 准备分布式锁（基于dedupe_md5）
        lock_keys = [ALERT_UPDATE_LOCK.get_key(dedupe_md5=event.dedupe_md5) for event in events]

        # 使用多服务锁机制防止并发修改同一告警
        with multi_service_lock(ALERT_UPDATE_LOCK, lock_keys) as lock:
            success_locked_events = []
            fail_locked_events = []

            # 区分加锁成功和失败的事件
            for event in events:
                if lock.is_locked(ALERT_UPDATE_LOCK.get_key(dedupe_md5=event.dedupe_md5)):
                    success_locked_events.append(event)
                else:
                    fail_locked_events.append(event)

            # 上报成功锁定事件的延迟统计
            _report_latency(success_locked_events)

            # 步骤3: 构建告警（仅处理加锁成功的事件）
            alerts = self.build_alerts(success_locked_events)
            alerts = self.enrich_alerts(alerts)
            update_count, finished_count = self.update_alert_cache(alerts)
            self.logger.info(
                "[alert.builder update alert cache]: updated(%s), finished(%s)", update_count, finished_count
            )

            snapshot_count = self.update_alert_snapshot(alerts)
            self.logger.info("[alert.builder update alert snapshot]: %s", snapshot_count)

            # 步骤4: 延迟重试（加锁失败的事件延后5秒重新投递）
            if fail_locked_events:
                from alarm_backends.service.alert.builder.tasks import (
                    dedupe_events_to_alerts,
                )

                dedupe_events_to_alerts.apply_async(
                    kwargs={
                        "events": fail_locked_events,
                    },
                    countdown=5,
                )
                self.logger.info(
                    "[alert.builder locked] %s alerts is locked, retry in 5s: %s",
                    len(fail_locked_events),
                    ",".join([event.dedupe_md5 for event in fail_locked_events]),
                )

            # 强制插入或更新告警到数据库
            alerts = self.save_alerts(alerts, action=BulkActionType.UPSERT, force_save=True)

        # TODO: 这里需要清理保存失败的告警的 Redis 缓存，否则会导致DB和 Redis 不一致

        # 步骤5: 记录日志、发送信号、触发周期检测
        self.save_alert_logs(alerts)
        self.send_periodic_check_task(alerts)

        # 发送满足条件的告警信号通知
        alerts_to_send_signal = [alert for alert in alerts if alert.should_send_signal()]
        self.send_signal(alerts_to_send_signal)

        # 统计推送数据量
        for alert in alerts:
            metrics.ALERT_PROCESS_PUSH_DATA_COUNT.labels(
                bk_data_id=alert.data_id,
                topic=alert.data_topic,
                strategy_id=metrics.TOTAL_TAG,
                is_saved="1" if alert.should_refresh_db() else "0",
            ).inc()

        return alerts

    def handle(self, events: list[Event]):
        """
        告警事件处理的核心流程

        参数:
            events (list[Event]): 待处理的原始事件列表

        返回值:
            list[Alert]: 去重聚合后的告警对象列表

        执行流程:
        1. 事件丰富：补充策略配置、CMDB信息、维度数据等上下文信息
        2. 持久化存储：批量保存事件到Elasticsearch，过滤保存失败的事件
        3. 告警聚合：将事件按告警ID去重聚合，更新告警状态到Redis缓存
        """
        # 步骤1: 丰富事件上下文信息
        events = self.enrich_events(events)
        # 步骤2: 保存事件到ES，返回成功保存的事件
        events = self.save_events(events)
        # 步骤3: 事件去重聚合为告警，更新Redis缓存
        alerts = self.dedupe_events_to_alerts(events)
        return alerts

    def send_periodic_check_task(self, alerts: list[Alert]):
        """
        对于新产生告警，立马触发一次状态检查。因为周期检测任务是1分钟跑一次，对于监控周期小于1分钟告警来说可能不够及时
        """
        alerts_params = [
            {
                "id": alert.id,
                "strategy_id": alert.strategy_id,
            }
            for alert in alerts
            if alert.is_new() and alert.strategy_id
        ]
        # 利用send_check_task 创建[alert.manager]延时任务
        send_check_task(alerts=alerts_params, run_immediately=False)
        self.logger.info("[alert.builder -> alert.manager] alerts: %s", ", ".join([str(alert.id) for alert in alerts]))

    def enrich_alerts(self, alerts: list[Alert]):
        """
        告警丰富
        注意：只需要对新产生的告警进行丰富
        """
        start_time = time.time()

        factory = AlertEnrichFactory(alerts)
        alerts = factory.enrich()
        AssignCacheManager.clear()

        self.logger.info(
            "[alert.builder enrich alerts] finished, total(%s), elapsed(%.3f)", len(alerts), time.time() - start_time
        )
        return alerts

    def enrich_events(self, events: list[Event]):
        """
        事件丰富处理，为告警事件补充完整的上下文信息

        参数:
            events (list[Event]): 待丰富的事件列表

        返回值:
            list[Event]: 丰富后的事件列表（包含被丢弃的事件）

        执行流程:
        1. 通过EventEnrichFactory工厂类批量丰富事件（补充策略、维度、目标等信息）
        2. 统计并记录被丢弃的事件数量和处理耗时
        3. 为每个被丢弃的事件上报丢弃指标到监控系统
        """

        start_time = time.time()

        # 步骤1: 批量丰富事件，补充策略配置、CMDB信息等上下文
        factory = EventEnrichFactory(events)
        events = factory.enrich()

        # 步骤2: 记录丰富结果统计信息
        self.logger.info(
            "[alert.builder enrich event] finished, dropped(%d/%d), cost: (%.3f)",
            len([e for e in events if e.is_dropped()]),
            len(events),
            time.time() - start_time,
        )

        # 步骤3: 为被丢弃的事件上报指标（用于监控丢弃率）
        for event in events:
            if event.is_dropped():
                metrics.ALERT_PROCESS_DROP_EVENT_COUNT.labels(
                    bk_data_id=event.data_id, topic=event.topic, strategy_id=metrics.TOTAL_TAG
                ).inc()

        return events

    def save_events(self, events: list[Event]) -> list[Event]:
        """
        批量保存告警事件到Elasticsearch

        参数:
            events (list[Event]): 待保存的事件列表

        返回值:
            list[Event]: 成功保存到ES的事件列表

        执行流程:
        1. 内存去重：过滤掉已丢弃和重复ID的事件
        2. 批量写入：将事件文档批量写入Elasticsearch
        3. 异常处理：捕获并分类处理保存失败的事件（409冲突/类型不匹配）
        4. 统计上报：记录保存成功、重复、失败的事件数量和耗时
        5. 返回过滤：仅返回成功保存的事件供后续处理
        """
        if not events:
            return []
        dedupe_events = []
        # 步骤1: 内存去重，过滤已丢弃和重复ID的事件
        exist_uids = set()
        for event in events:
            if event.is_dropped() or event.id in exist_uids:
                continue
            dedupe_events.append(event)
            exist_uids.add(event.id)

        # 转换为ES文档格式
        event_documents = [event.to_document() for event in dedupe_events]

        # 初始化错误统计
        error_uids = set()
        conflict_error_events_count = len(events) - len(dedupe_events)  # 内存去重数量
        other_error_events_count = 0  # 其他错误数量

        start_time = time.time()
        # 步骤2: 批量写入Elasticsearch
        try:
            EventDocument.bulk_create(event_documents)
        except BulkIndexError as e:
            # 步骤3: 处理批量写入异常，分类统计错误原因
            for err in e.errors:
                error_uids.add(err["create"]["_id"])
                if err["create"]["status"] == 409:
                    # 409冲突：ES中已存在相同ID，通常由poller拉取窗口重叠导致
                    conflict_error_events_count += 1
                else:
                    # 其他错误：通常是数据类型与ES mapping不匹配（如在KeyWord字段存入Object）
                    self.logger.error("[alert.builder save events ERROR] detail: %s", err)
                    other_error_events_count += 1

        created_events_count = len(event_documents) - len(error_uids)

        # 步骤4: 记录保存结果统计信息
        self.logger.info(
            "[alert.builder save event to ES] finished: total(%d), created(%d), duplicate(%d), failed(%d), cost: %.3f",
            len(events),
            created_events_count,
            conflict_error_events_count,
            other_error_events_count,
            time.time() - start_time,
        )

        # 步骤5: 返回成功保存的事件列表
        return [event for event in dedupe_events if event.id not in error_uids]

    def alert_qos_handle(self, alert: Alert):
        if not alert.is_blocked:
            # 对于未被流控的告警，只检查熔断规则
            circuit_breaking_blocked = False
            if self.circuit_breaking_manager:
                circuit_breaking_blocked = alert.check_circuit_breaking(self.circuit_breaking_manager)

            if circuit_breaking_blocked:
                # 告警触发熔断规则，需要流控, 结束当前告警。
                alert.update_qos_status(True)
                now_time = int(time.time())
                alert.set_end_status(
                    status=EventStatus.CLOSED,
                    op_type=AlertLog.OpType.ALERT_QOS,
                    description="告警命中熔断规则，被流控关闭",
                    end_time=now_time,
                    event_id=now_time,
                )
                self.logger.info(
                    f"[circuit breaking] [alert.builder] exists alert({alert.id}) strategy({alert.strategy_id}) "
                    f"is blocked by circuit breaking rules"
                )

            return alert

        # 对于已被流控的告警，先检查熔断规则状态
        circuit_breaking_blocked = False
        if self.circuit_breaking_manager:
            circuit_breaking_blocked = alert.check_circuit_breaking(self.circuit_breaking_manager)

        if circuit_breaking_blocked:
            self.logger.debug(f"[circuit breaking] [alert.builder] alert({alert.id}) still blocked by circuit breaking")
            return alert

        # 熔断规则未命中，继续检查QoS状态
        qos_result = alert.qos_check()
        if qos_result["is_blocked"]:
            # 仍被QoS流控
            return alert
        else:
            # 不满足熔断条件了，关闭当前告警，接下来直接产生一条新的告警
            self.logger.info("[alert.builder qos] alert(%s) will be closed: %s ", alert.id, qos_result["message"])
            alert.set_end_status(
                status=EventStatus.CLOSED,
                op_type=AlertLog.OpType.CLOSE,
                description=_("{message}, 当前告警关闭").format(message=qos_result["message"]),
                end_time=int(time.time()),
            )
            return alert

    def build_alerts(self, events: list[Event]) -> list[Alert]:
        """
        根据事件构建或更新告警对象

        参数:
            events (list[Event]): 待处理的事件列表

        返回值:
            list[Alert]: 新创建或更新的告警对象列表

        执行流程:
        1. 获取存量告警：根据事件的dedupe_md5从Redis缓存中查询已存在的告警
        2. 事件遍历处理：
           - 存量告警：QoS判定、级别比较、状态更新
           - 新告警：从异常事件创建新告警对象
        3. UID初始化：为新创建的告警分配全局唯一ID
        4. 统计上报：记录新建告警数、熔断流控数等指标
        """
        if not events:
            return []

        # 步骤1: 根据dedupe_md5获取已存在的告警（从Redis缓存）
        current_alerts = self.get_current_alerts(events)
        new_alerts = {}
        # 步骤2: 遍历事件，逐个更新或创建告警
        for event in events:
            alert: Alert = current_alerts.get(event.dedupe_md5)
            if alert and alert.is_abnormal():
                # 存量告警处理：告警已存在且处于未恢复状态
                # QoS判定：如果满足服务质量解除条件，则关闭当前告警
                alert = self.alert_qos_handle(alert)
                if alert.status == EventStatus.CLOSED:
                    # QoS解除，关闭旧告警并创建新告警
                    new_alerts[alert.id] = alert
                    alert = Alert.from_event(event, circuit_breaking_manager=self.circuit_breaking_manager)
                else:
                    if alert.severity > event.severity and alert.severity_source != AssignMode.BY_RULE:
                        # 场景1：新事件级别更高，且告警级别非人工分派
                        # 关闭低级别告警，创建高级别新告警
                        alert.set_end_status(
                            status=EventStatus.CLOSED,
                            op_type=AlertLog.OpType.CLOSE,
                            description=_("存在更高级别的告警，告警关闭"),
                            end_time=max(event.time, alert.latest_time),
                            event_id=event.id,
                        )
                        new_alerts[alert.id] = alert
                        alert = Alert.from_event(event, circuit_breaking_manager=self.circuit_breaking_manager)
                    elif alert.event_severity < event.severity:
                        # 场景2：告警关联的事件级别高于新事件
                        # 丢弃低级别事件，记录日志
                        alert.add_log(
                            op_type=AlertLog.OpType.EVENT_DROP,
                            event_id=event.id,
                            description=event.description,
                            time=event.time,
                            severity=event.severity,
                        )
                        event.drop()
                    else:
                        # 场景3：级别相同或其他情况，更新告警内容
                        alert.update(event)

            else:
                # 新告警处理：无存量告警或告警已关闭
                if not event.is_abnormal():
                    # 跳过非异常事件（无需创建告警）
                    continue
                alert = Alert.from_event(event=event, circuit_breaking_manager=self.circuit_breaking_manager)
                self.logger.info(
                    "[alert.builder] event(%s) -> new alert(%s)",
                    event.event_id,
                    alert.id,
                )

            # 回写到缓存，用于后续事件继续更新同一告警
            current_alerts[event.dedupe_md5] = alert
            new_alerts[alert.id] = alert

        alerts = list(new_alerts.values())

        # 步骤3: 为新创建的告警初始化全局唯一ID
        alerts_to_init = [alert for alert in alerts if alert.is_new()]
        AlertUIDManager.preload_pool(len(alerts_to_init))
        for alert in alerts_to_init:
            alert.init_uid()

        # 步骤4: 统计并记录告警构建结果
        circuit_breaking_count = len([alert for alert in alerts_to_init if alert.is_blocked])
        self.logger.info(
            "[alert.builder build alerts] finished, new/total(%d/%d), circuit_breaking(%d)",
            len(alerts_to_init),
            len(alerts),
            circuit_breaking_count,
        )

        return alerts

    def process(self, events: list[Event] = None):
        """
        事件处理主入口
        """
        if not events:
            return
        self.handle(events)
