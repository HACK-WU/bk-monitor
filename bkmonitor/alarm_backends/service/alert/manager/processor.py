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

from alarm_backends.core.alert import Alert, Event
from alarm_backends.core.alert.alert import AlertKey
from alarm_backends.core.cache import clear_mem_cache
from alarm_backends.core.cache.key import ALERT_UPDATE_LOCK
from alarm_backends.core.lock.service_lock import multi_service_lock
from alarm_backends.service.alert.manager.checker.ack import AckChecker
from alarm_backends.service.alert.manager.checker.action import ActionHandleChecker
from alarm_backends.service.alert.manager.checker.close import CloseStatusChecker
from alarm_backends.service.alert.manager.checker.next import NextStatusChecker
from alarm_backends.service.alert.manager.checker.recover import RecoverStatusChecker
from alarm_backends.service.alert.manager.checker.shield import ShieldStatusChecker
from alarm_backends.service.alert.manager.checker.upgrade import UpgradeChecker
from alarm_backends.service.alert.processor import BaseAlertProcessor
from bkmonitor.documents import AlertDocument
from bkmonitor.documents.base import BulkActionType
from core.prometheus import metrics

INSTALLED_CHECKERS = (
    NextStatusChecker,
    CloseStatusChecker,
    RecoverStatusChecker,
    ShieldStatusChecker,
    AckChecker,
    UpgradeChecker,
    ActionHandleChecker,
)


class AlertManager(BaseAlertProcessor):
    def __init__(self, alert_keys: list[AlertKey]):
        super().__init__()
        self.logger = logging.getLogger("alert.manager")
        self.alert_keys = alert_keys

    def fetch_alerts(self) -> list[Alert]:
        # 1. 根据告警ID，从ES拉出数据
        alerts = Alert.mget(self.alert_keys)

        # 2. 补充用户修改字段，这些字段只有在ES是最准的，需要刷进去
        fields = [
            "id",
            "assignee",
            "is_handled",
            "handle_stage",
            "is_ack",
            "is_ack_noticed",
            "ack_operator",
            "appointee",
            "supervisor",
            "extra_info",
        ]
        alert_docs = {
            alert_doc.id: alert_doc
            for alert_doc in AlertDocument.mget(
                ids=[alert.id for alert in alerts],
                fields=fields,
            )
        }
        for alert in alerts:
            if alert.id in alert_docs:
                for field in fields:
                    if field == "extra_info":
                        # 以DB为主，同时合并check阶段新增内容
                        extra_info = getattr(alert_docs[alert.id], field, None)
                        alert.data[field] = alert.data.get(field) or {}
                        alert.data[field].update(extra_info.to_dict() if extra_info else {})
                    else:
                        alert.data[field] = getattr(alert_docs[alert.id], field, None)
        return alerts

    def process(self):
        """
        处理入口

        参数:
            无

        返回值:
            None 表示处理流程正常结束（可能包含部分失败操作）
            当无告警需要处理时直接返回

        处理流程包含以下核心阶段：
        1. 告警数据获取与预校验
        2. 分布式锁资源申请与竞争处理
        3. 异常状态告警检测与处理
        4. 告警数据持久化存储（ES）
        5. 操作日志记录与事件通知
        6. 指标监控上报与缓存清理
        7. 终止状态告警的特殊处理
        """
        alerts = self.fetch_alerts()
        if not alerts:
            return

        # 生成分布式锁键值列表
        lock_keys = [ALERT_UPDATE_LOCK.get_key(dedupe_md5=alert.dedupe_md5) for alert in alerts]

        with multi_service_lock(ALERT_UPDATE_LOCK, lock_keys) as lock:
            # 第一阶段：分布式锁竞争处理
            # 尝试获取所有告警对应的锁资源，分离成功/失败对象
            locked_alerts = []
            fail_locked_alert_ids = []
            for alert in alerts:
                if lock.is_locked(ALERT_UPDATE_LOCK.get_key(dedupe_md5=alert.dedupe_md5)):
                    locked_alerts.append(alert)
                else:
                    fail_locked_alert_ids.append(alert.id)

            # 第二阶段：告警状态分类处理
            # 根据异常状态将加锁成功的告警分为两类：
            # - 需要完整处理流程的异常告警
            # - 可直接更新的正常状态告警
            alerts_to_check = []
            alerts_to_update_directly = []
            for alert in locked_alerts:
                if alert.is_abnormal():
                    alerts_to_check.append(alert)
                else:
                    alerts_to_update_directly.append(alert)

            # 第三阶段：核心处理逻辑执行
            # 包含异常检测、状态转换、关联关系维护等复杂操作
            alerts_to_check = self.handle(alerts_to_check)

            # 第四阶段：加锁失败告警处理
            # 记录日志并推迟到下个处理周期，保证数据一致性
            if fail_locked_alert_ids:
                self.logger.info(
                    "[alert.manager get lock error] total(%s) is locked, will try later: %s",
                    len(fail_locked_alert_ids),
                    ", ".join(fail_locked_alert_ids),
                )

            # 第五阶段：数据持久化操作
            # 强制写入ES存储，确保处理结果持久化
            saved_alerts = self.save_alerts(alerts_to_check, action=BulkActionType.UPSERT, force_save=True)

        # 第六阶段：操作日志记录
        # 记录告警状态变更的完整审计日志
        self.save_alert_logs(saved_alerts)

        # 第七阶段：事件通知系统
        # 触发下游订阅系统的信号接收器
        self.send_signal(saved_alerts)

        # 第八阶段：监控指标上报
        # 按策略ID和状态标签统计告警处理量
        for alert in saved_alerts:
            metrics.ALERT_MANAGE_PUSH_DATA_COUNT.labels(strategy_id=metrics.TOTAL_TAG, signal=alert.status).inc()

        # 第九阶段：缓存清理操作
        # 清除主机相关缓存以保证数据新鲜度
        clear_mem_cache("host_cache")

        # 第十阶段：终止状态告警处理
        # 特殊场景下处理处于终结状态的快照告警
        if alerts_to_update_directly:
            self.logger.info("[refresh alert es] refresh ES directly: %s", alerts_to_update_directly)
            self.save_alerts(alerts_to_update_directly, action=BulkActionType.UPSERT, force_save=True)

    def handle(self, alerts: list[Alert]):
        """
        处理告警对象的完整性校验与状态持久化流程

        参数:
            alerts: Alert对象列表，包含待处理的告警数据集合
                   每个Alert对象应包含完整的事件特征(dedupe_md5)和状态标识(id)

        返回值:
            List[Alert]: 经过校验和状态同步处理后的告警对象列表
                        包含更新后的缓存状态和快照记录

        该方法实现告警生命周期管理的核心流程：
        1. 告警规则校验：通过注册检查器进行多维度验证
        2. 缓存状态同步：基于特征指纹的增量更新机制
        3. 快照持久化：维护告警状态的历史记录
        """
        # #### 需要检测的告警，处理开始
        # 2. 再处理 DB 和 Redis 缓存中存在的告警
        # 执行已注册的告警检查器链，进行规则校验
        # 每个checker_cls实例会处理所有告警对象
        for checker_cls in INSTALLED_CHECKERS:
            checker = checker_cls(alerts=alerts)
            checker.check_all()

        # 3. 更新缓存，只更新当前dedupe_md5的alert_id和需要更新的alert_id一致的部分，或者cache不存在的部分
        # 构建缓存状态映射表：通过dedupe_md5快速定位有效告警
        active_alerts = self.list_alerts_content_from_cache(
            [Event(data=alert.top_event, do_clean=False) for alert in alerts]
        )
        active_alerts_mapping = {alert.dedupe_md5: alert.id for alert in active_alerts}

        # 执行缓存增量更新：仅处理状态变更或首次出现的告警
        # 返回值包含更新成功数和完成总数
        update_count, finished_count = self.update_alert_cache(
            [
                alert
                for alert in alerts
                if alert.dedupe_md5 not in active_alerts_mapping or active_alerts_mapping[alert.dedupe_md5] == alert.id
            ]
        )
        self.logger.info("[alert.manager update alert cache]: updated(%s), finished(%s)", update_count, finished_count)

        # 4. 再把最新的内容刷回快照
        # 将当前告警状态持久化到快照存储
        snapshot_count = self.update_alert_snapshot(alerts)
        self.logger.info("[alert.manager update alert snapshot]: %s", snapshot_count)

        return alerts
