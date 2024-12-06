# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""
import logging
import time
from typing import List

from alarm_backends.core.alert import Alert
from alarm_backends.service.alert.manager.checker.base import BaseChecker
from alarm_backends.service.converge.shield.shielder import AlertShieldConfigShielder
from alarm_backends.service.fta_action.tasks import create_actions
from bkmonitor.documents import AlertLog

logger = logging.getLogger("alert.manager")

"""
这个类ShieldStatusChecker主要用于检测和处理告警的屏蔽状态。以下是它的主要功能和职责：
主要功能
初始化：
    接收一个告警列表，并将其存储为字典以方便快速查找。
    初始化未屏蔽动作列表、需要通知的告警ID列表等。
    
屏蔽状态检查：
    对每个告警进行屏蔽状态的检查。
    判断告警是否匹配屏蔽规则，并更新告警的屏蔽状态和相关信息。
    
处理未屏蔽动作：
    收集所有未屏蔽的动作，并在适当的时候推送这些动作。
    处理告警的周期处理记录，确保正确记录每次通知的状态。
    
QoS（服务质量）控制：
    在推送动作之前进行QoS计算，以确保不会因为过多的通知而影响系统性能。
    记录被QOS策略放弃执行的告警，并生成相应的日志。
    
异步任务：
    使用异步任务队列来推送未屏蔽的动作，以提高系统的响应速度和可靠性。

主要职责
    维护告警的屏蔽状态：跟踪每个告警是否被屏蔽以及屏蔽的剩余时间。
    触发解除屏蔽通知：当一个原本被屏蔽的告警不再满足屏蔽条件时，发送解除屏蔽的通知。
    避免重复通知：通过记录已发送的通知，防止对同一个告警进行重复通知。
    优化通知效率：通过QoS控制机制，确保在高负载情况下仍能高效且准确地发送重要告警。
"""

class ShieldStatusChecker(BaseChecker):
    """
    屏蔽状态检测
    """

    def __init__(self, alerts: List[Alert]):
        super().__init__(alerts)  # 初始化父类
        self.unshielded_actions = []  # 存储未屏蔽的动作
        self.need_notify_alerts = []  # 存储需要通知的告警ID
        self.alerts_dict = {alert.id: alert for alert in self.alerts}  # 将告警列表转换为字典，便于快速查找

    def check_all(self):
        super().check_all()  # 调用父类的check_all方法

        if self.unshielded_actions:  # 如果有未屏蔽的动作
            self.push_actions()  # 推送这些动作

    def add_unshield_action(self, alert: Alert, notice_relation: dict = None):
        # 没有关联通知配置，则不用通知
        if not notice_relation:
            return

        # 获取关联的处理套餐
        config_id = notice_relation.get("config_id") # 获取配置ID
        # 获取到关联的通知
        relation_id = notice_relation.get("id")
        # 如果关联的处理套餐和通知都没有获取到，则不用通知
        if not (config_id and relation_id):
            return

        cycle_handle_record = alert.get_extra_info("cycle_handle_record", {})  # 获取告警的周期处理记录
        # 获取当前关联的notice的处理记录
        handle_record = cycle_handle_record.get(str(relation_id))
        if not handle_record:  # 如果处理记录不存在
            handle_record = alert.get_latest_interval_record(config_id=config_id, relation_id=str(relation_id)) or {}  # 从数据库获取最近一次的通知记录

        if handle_record and not handle_record.get("is_shielded"):  # 如果最近一次通知没有被屏蔽
            logger.info("[ignore unshielded action] alert(%s) strategy(%s) 最近一次通知没有被屏蔽, 无需发送接触屏蔽通知", alert.id, alert.strategy_id)
            return  # 直接返回，无需发送解除屏蔽通知

        execute_times = handle_record.get("execute_times", 0)  # 获取执行次数
        self.unshielded_actions.append({  # 将未屏蔽的动作添加到列表中
            "strategy_id": alert.strategy_id,
            "signal": alert.status.lower(),
            "alert_ids": [alert.id],
            "severity": alert.severity,
            "relation_id": relation_id,
            "is_unshielded": True,
            "execute_times": execute_times,
        })

        # 更新告警通知处理记录
        cycle_handle_record.update({
            str(relation_id): {
                "last_time": int(time.time()),
                "is_shielded": False,
                "latest_anomaly_time": alert.latest_time,
                "execute_times": execute_times + 1,
            }
        })
        alert.update_extra_info("cycle_handle_record", cycle_handle_record)  # 更新告警的额外信息
        self.need_notify_alerts.append(alert.id)  # 将告警ID添加到需要通知的列表中
        logger.info("[push unshielded action] alert(%s) strategy(%s)", alert.id, alert.strategy_id)

    def check(self, alert: Alert):
        shield_obj = AlertShieldConfigShielder(alert.to_document())  # 创建屏蔽对象
        # 检查是否被需要屏蔽：如果存在屏蔽配置，或者被全局屏蔽，则需要被屏蔽
        match_shield = shield_obj.is_matched()
        # 获取到关联的通知配置
        notice_relation = alert.strategy.get("notice", {}) if alert.strategy else None

        # 不需要屏蔽则发送告警通知
        if not match_shield:
            # 根据告警是否处于屏蔽中，进行不同的操作
            if alert.is_shielded:  # 如果告警处于屏蔽中
                if alert.is_recovering():  # 如果告警处于恢复期
                    alert.update_extra_info("ignore_unshield_notice", True)  # 设置忽略解除屏蔽通知的标记
                    logger.info("[ignore push action] alert(%s) strategy(%s) 告警处于恢复期", alert.id, alert.strategy_id)
                else:  # 如果告警不处于恢复期
                    self.add_unshield_action(alert, notice_relation)  # 推送解除屏蔽通知
            else:  # 如果告警处于未屏蔽状态
                if alert.get_extra_info("need_unshield_notice"):  # 如果需要通知
                    self.add_unshield_action(alert, notice_relation)  # 发送一次通知
                    alert.extra_info.pop("need_unshield_notice", False)  # 移除通知标记

        shield_left_time = shield_obj.get_shield_left_time()  # 获取剩余屏蔽时间
        shield_ids = shield_obj.list_shield_ids()  # 获取屏蔽ID列表
        alert.set("shield_id", shield_ids)  # 更新告警文档中的屏蔽ID
        alert.set("is_shielded", match_shield)  # 更新告警文档中的屏蔽状态
        alert.set("shield_left_time", shield_left_time)  # 更新告警文档中的剩余屏蔽时间

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
                    logger.info("[action qos triggered] alert(%s) strategy(%s) signal(%s) severity(%s) qos_count: %s", alert_id, action["strategy_id"], action["signal"], action["severity"], current_count)
            except BaseException as error:  # 如果发生异常
                logger.exception("[push actions error] alert(%s) strategy(%s) reason: %s", alert_id, action["strategy_id"], error)

        if qos_alerts:  # 如果有被QOS的事件
            qos_log = Alert.create_qos_log(qos_alerts, current_count, qos_actions)  # 创建QOS日志
            AlertLog.bulk_create([qos_log])  # 批量创建QOS日志

        for action in new_actions:  # 遍历新动作列表
            create_actions.delay(**action)  # 异步推送动作
            logger.info("[push actions] alert(%s) strategy(%s)", action["alert_ids"][0], action["strategy_id"])
