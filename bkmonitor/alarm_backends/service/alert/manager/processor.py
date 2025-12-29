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
        """
        从ES获取告警对象并补充用户操作字段

        返回值:
            告警对象列表，已合并ES中的用户操作数据

        执行流程:
        1. 从Redis缓存批量获取告警快照数据
        2. 从ES查询用户操作字段（分配人、确认状态等）
        3. 将ES中的用户操作数据合并到告警对象中
        """
        # 从Redis缓存批量获取告警快照
        alerts = Alert.mget(self.alert_keys)

        # 定义需要从ES同步的用户操作字段（以ES为准）
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

        # 批量查询ES中的用户操作字段
        alert_docs = {
            alert_doc.id: alert_doc
            for alert_doc in AlertDocument.mget(
                ids=[alert.id for alert in alerts],
                fields=fields,
            )
        }

        # 将ES数据合并到告警对象
        for alert in alerts:
            if alert.id in alert_docs:
                for field in fields:
                    if field == "extra_info":
                        # extra_info特殊处理：合并ES数据和check阶段新增数据
                        extra_info = getattr(alert_docs[alert.id], field, None)
                        alert.data[field] = alert.data.get(field) or {}
                        alert.data[field].update(extra_info.to_dict() if extra_info else {})
                    else:
                        # 其他字段直接覆盖为ES中的值
                        alert.data[field] = getattr(alert_docs[alert.id], field, None)
        return alerts

    def process(self):
        """
        告警管理处理主流程

        执行流程:
        1. 获取待处理告警并加分布式锁
        2. 按异常状态分类：异常告警执行完整检测流程，正常告警直接更新
        3. 持久化存储、记录日志、发送信号通知
        4. 上报监控指标并清理缓存
        """
        alerts = self.fetch_alerts()
        if not alerts:
            return

        lock_keys = [ALERT_UPDATE_LOCK.get_key(dedupe_md5=alert.dedupe_md5) for alert in alerts]

        with multi_service_lock(ALERT_UPDATE_LOCK, lock_keys) as lock:
            # 分离加锁成功和失败的告警
            locked_alerts = []
            fail_locked_alert_ids = []
            for alert in alerts:
                if lock.is_locked(ALERT_UPDATE_LOCK.get_key(dedupe_md5=alert.dedupe_md5)):
                    locked_alerts.append(alert)
                else:
                    fail_locked_alert_ids.append(alert.id)

            # 按异常状态分类：异常告警需要完整检测流程，正常告警可直接更新
            alerts_to_check = []
            alerts_to_update_directly = []
            for alert in locked_alerts:
                if alert.is_abnormal():
                    alerts_to_check.append(alert)
                else:
                    alerts_to_update_directly.append(alert)

            # 执行核心检测逻辑（状态转换、屏蔽检测、升级检测等）
            alerts_to_check = self.handle(alerts_to_check)

            # 加锁失败的告警延后处理
            if fail_locked_alert_ids:
                self.logger.info(
                    "[alert.manager get lock error] total(%s) is locked, will try later: %s",
                    len(fail_locked_alert_ids),
                    ", ".join(fail_locked_alert_ids),
                )

            # 持久化到ES
            saved_alerts = self.save_alerts(alerts_to_check, action=BulkActionType.UPSERT, force_save=True)

        # 记录操作日志
        self.save_alert_logs(saved_alerts)

        # 发送信号通知下游系统
        self.send_signal(saved_alerts)

        # 上报监控指标
        for alert in saved_alerts:
            metrics.ALERT_MANAGE_PUSH_DATA_COUNT.labels(strategy_id=metrics.TOTAL_TAG, signal=alert.status).inc()

        # 清理主机缓存
        clear_mem_cache("host_cache")

        # 处理终止状态的告警（直接更新ES）
        if alerts_to_update_directly:
            self.logger.info("[refresh alert es] refresh ES directly: %s", alerts_to_update_directly)
            self.save_alerts(alerts_to_update_directly, action=BulkActionType.UPSERT, force_save=True)

    def handle(self, alerts: list[Alert]):
        """
        告警检测与状态同步处理

        参数:
            alerts: 待处理的告警对象列表

        返回值:
            处理后的告警对象列表

        执行流程:
        1. 执行检查器链（状态转换、屏蔽检测、升级检测等）
        2. 增量更新Redis缓存（仅更新状态变更的告警）
        3. 持久化告警快照到存储
        """
        # 执行已注册的检查器链（NextStatus、CloseStatus、RecoverStatus、Shield、Ack、Upgrade、ActionHandle）
        for checker_cls in INSTALLED_CHECKERS:
            checker = checker_cls(alerts=alerts)
            checker.check_all()

        # 构建缓存映射表，用于判断告警是否需要更新
        active_alerts = self.list_alerts_content_from_cache(
            [Event(data=alert.top_event, do_clean=False) for alert in alerts]
        )
        active_alerts_mapping = {alert.dedupe_md5: alert.id for alert in active_alerts}

        # 增量更新缓存：仅更新状态变更或首次出现的告警
        update_count, finished_count = self.update_alert_cache(
            [
                alert
                for alert in alerts
                if alert.dedupe_md5 not in active_alerts_mapping or active_alerts_mapping[alert.dedupe_md5] == alert.id
            ]
        )
        self.logger.info("[alert.manager update alert cache]: updated(%s), finished(%s)", update_count, finished_count)

        # 持久化告警快照
        snapshot_count = self.update_alert_snapshot(alerts)
        self.logger.info("[alert.manager update alert snapshot]: %s", snapshot_count)

        return alerts
