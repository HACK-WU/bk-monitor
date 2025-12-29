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

from alarm_backends.core.alert import Alert
from alarm_backends.service.alert.manager.checker.base import BaseChecker
from alarm_backends.service.converge.shield.shielder import AlertShieldConfigShielder
from alarm_backends.service.fta_action.tasks import create_actions
from bkmonitor.documents import AlertLog

logger = logging.getLogger("alert.manager")


class ShieldStatusChecker(BaseChecker):
    """
    屏蔽状态检测
    """

    def __init__(self, alerts: list[Alert]):
        super().__init__(alerts)  # 初始化父类
        self.unshielded_actions = []  # 存储未屏蔽的动作
        self.need_notify_alerts = []  # 存储需要通知的告警ID
        self.alerts_dict = {alert.id: alert for alert in self.alerts}  # 将告警列表转换为字典，便于快速查找

    def check_all(self):
        super().check_all()  # 调用父类的check_all方法

        if self.unshielded_actions:  # 如果有未屏蔽的动作
            self.push_actions()  # 推送这些动作

    def add_unshield_action(self, alert: Alert, notice_relation: dict = None):
        """
        添加解除屏蔽通知动作

        参数:
            alert: 告警对象
            notice_relation: 通知配置关联信息，包含config_id和relation_id

        执行流程:
        1. 校验通知配置有效性（config_id和relation_id必须存在）
        2. 获取告警的历史处理记录，判断上次通知是否被屏蔽
        3. 仅当上次通知被屏蔽时，才创建解除屏蔽通知动作
        4. 更新告警的周期处理记录，记录本次通知状态
        """
        # 校验通知配置有效性
        if not notice_relation:
            return

        config_id = notice_relation.get("config_id")
        relation_id = notice_relation.get("id")
        if not (config_id and relation_id):
            return

        # 获取告警的历史处理记录
        cycle_handle_record = alert.get_extra_info("cycle_handle_record", {})
        handle_record = cycle_handle_record.get(str(relation_id))
        if not handle_record:
            # 从数据库获取最近一次的通知记录
            handle_record = alert.get_latest_interval_record(config_id=config_id, relation_id=str(relation_id)) or {}

        # 仅当上次通知被屏蔽时，才发送解除屏蔽通知
        if handle_record and not handle_record.get("is_shielded"):
            logger.info(
                "[ignore unshielded action] alert(%s) strategy(%s) 最近一次通知没有被屏蔽, 无需发送接触屏蔽通知",
                alert.id,
                alert.strategy_id,
            )
            return

        # 创建解除屏蔽通知动作
        execute_times = handle_record.get("execute_times", 0)
        self.unshielded_actions.append(
            {
                "strategy_id": alert.strategy_id,
                "signal": alert.status.lower(),
                "alert_ids": [alert.id],
                "severity": alert.severity,
                "relation_id": relation_id,
                "is_unshielded": True,
                "execute_times": execute_times,
            }
        )

        # 更新告警的周期处理记录
        cycle_handle_record.update(
            {
                str(relation_id): {
                    "last_time": int(time.time()),
                    "is_shielded": False,
                    "latest_anomaly_time": alert.latest_time,
                    "execute_times": execute_times + 1,
                }
            }
        )
        alert.update_extra_info("cycle_handle_record", cycle_handle_record)
        self.need_notify_alerts.append(alert.id)
        logger.info("[push unshielded action] alert(%s) strategy(%s)", alert.id, alert.strategy_id)

    def check(self, alert: Alert):
        """
        检测告警屏蔽状态并处理解除屏蔽通知

        执行流程:
        1. 检查告警是否匹配屏蔽规则
        2. 处理解除屏蔽场景的通知逻辑
        3. 更新告警的屏蔽状态和剩余时间
        """
        # 检查是否匹配屏蔽规则
        shield_obj = AlertShieldConfigShielder(alert.to_document())
        match_shield = shield_obj.is_matched()
        notice_relation = alert.strategy.get("notice", {}) if alert.strategy else None

        # 处理解除屏蔽场景：告警从屏蔽状态变为非屏蔽时发送通知
        if not match_shield:
            if alert.is_shielded:
                if alert.is_recovering():
                    # 恢复期的告警忽略解除屏蔽通知
                    alert.update_extra_info("ignore_unshield_notice", True)
                    logger.info(
                        "[ignore push action] alert(%s) strategy(%s) 告警处于恢复期", alert.id, alert.strategy_id
                    )
                else:
                    # 推送解除屏蔽通知
                    self.add_unshield_action(alert, notice_relation)
            else:
                # 处理延迟的解除屏蔽通知
                if alert.get_extra_info("need_unshield_notice"):
                    self.add_unshield_action(alert, notice_relation)
                    alert.extra_info.pop("need_unshield_notice", False)

        # 更新告警的屏蔽状态
        shield_left_time = shield_obj.get_shield_left_time()
        shield_ids = shield_obj.list_shield_ids()
        alert.set("shield_id", shield_ids)
        alert.set("is_shielded", match_shield)
        alert.set("shield_left_time", shield_left_time)

    def push_actions(self):
        new_actions = []  # 存储需要推送的新动作
        qos_actions = 0  # 存储被QOS放弃执行的数量
        noticed_alerts = []  # 存储已经发送过通知的告警ID
        qos_alerts = []  # 存储被QOS的告警ID
        current_count = 0  # 当前计数器

        for action in self.unshielded_actions:  # 遍历未屏蔽的动作
            alert_id = action["alert_ids"][0]  # 获取告警ID
            if alert_id in noticed_alerts:  # 如果告警ID已经存在于已发送过通知的列表中
                continue  # 直接跳过

            alert = self.alerts_dict.get(alert_id)  # 获取告警对象
            try:
                is_qos, current_count = alert.qos_calc(action["signal"])  # 计算QOS
                if not is_qos:  # 如果没有达到QOS阈值
                    new_actions.append(action)  # 将动作添加到新动作列表中
                else:  # 如果达到QOS阈值
                    qos_actions += 1  # 增加QOS放弃执行的数量
                    qos_alerts.append(alert_id)  # 将告警ID添加到被QOS的列表中
                    logger.info(
                        "[action qos triggered] alert(%s) strategy(%s) signal(%s) severity(%s) qos_count: %s",
                        alert_id,
                        action["strategy_id"],
                        action["signal"],
                        action["severity"],
                        current_count,
                    )
            except BaseException as error:  # 如果发生异常
                logger.exception(
                    "[push actions error] alert(%s) strategy(%s) reason: %s", alert_id, action["strategy_id"], error
                )

        if qos_alerts:  # 如果有被QOS的事件
            qos_log = Alert.create_qos_log(qos_alerts, current_count, qos_actions)  # 创建QOS日志
            AlertLog.bulk_create([qos_log])  # 批量创建QOS日志

        for action in new_actions:  # 遍历新动作列表
            create_actions.delay(**action)  # 异步推送动作
            logger.info("[push actions] alert(%s) strategy(%s)", action["alert_ids"][0], action["strategy_id"])
