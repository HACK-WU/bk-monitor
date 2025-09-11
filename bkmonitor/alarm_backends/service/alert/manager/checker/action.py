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
import math
import time

from alarm_backends.core.alert import Alert
from alarm_backends.core.cache.action_config import ActionConfigCacheManager
from alarm_backends.service.alert.manager.checker.base import BaseChecker
from alarm_backends.service.fta_action.tasks import create_interval_actions
from constants.action import ActionSignal, IntervalNotifyMode

logger = logging.getLogger("alert.manager")


class ActionHandleChecker(BaseChecker):
    """
    通知以及告警处理相关的状态检测
    """

    def check(self, alert: Alert):
        """
        执行告警异常通知处理检测的核心逻辑

        参数:
            alert: Alert对象，包含告警的完整上下文信息
                - is_handled: 告警处理状态标识
                - strategy: 告警策略配置字典
                - strategy_id: 策略唯一标识符
                - severity: 告警严重程度
                - latest_time: 最新异常时间戳
                - get_extra_info(): 获取扩展信息方法
                - update_extra_info(): 更新扩展信息方法
                - get_latest_interval_record(): 获取最近间隔记录方法

        返回值:
            None: 始终返回None，通过side effect修改alert对象状态

        处理流程概要：
        1.告警没有被处理过的，告警告警没有策略的，直接返回，不进行处理
        2.获取到异常的action配置
        3.循环处理action配置
            - 获取action的处理记录，不存在处理记录则跳过
            - 获取action的config配置，根据config配置，判断当前是否符合处理时间间隔要求，不符合跳过
            - 创建周期性告警处理action（异步）
            - 更新action处理记录
        4.更新告警的处理记录

        """
        # todo 为什么没处理要跳过？
        if not alert.is_handled:
            # 预检阶段1：跳过未处理告警的周期检测
            return

        if not alert.strategy:
            # 预检阶段2：跳过无策略配置的告警
            return

        # 收集通知配置
        notice_relation = alert.strategy.get("notice", {})
        # 获取到异常动作配置
        actions = [action for action in alert.strategy.get("actions", []) if ActionSignal.ABNORMAL in action["signal"]]
        if notice_relation:
            actions.append(notice_relation)

        # 获取周期处理记录
        cycle_handle_record = alert.get_extra_info("cycle_handle_record", {})
        # 如果不是无数据，也判断为异常
        signal = ActionSignal.NO_DATA if alert.is_no_data() else ActionSignal.ABNORMAL

        # 处理每个动作配置
        for action in actions:
            action_id = str(action["id"])
            relation_record = cycle_handle_record.get(action_id)
            if not relation_record:
                # 尝试从历史记录中获取
                relation_record = alert.get_latest_interval_record(action["config_id"], action_id)
            # todo 为什么没有处理记录要跳过？
            if not relation_record:
                continue

            # 获取动作配置
            action_config = ActionConfigCacheManager.get_action_config_by_id(action["config_id"])
            if not self.check_interval_matched_actions(relation_record, action_config, alert):
                continue

            # 创建周期任务
            execute_times = relation_record["execute_times"]
            create_interval_actions.delay(
                alert.strategy_id,
                signal,
                [alert.id],
                severity=alert.severity,
                action_id=int(action_id),
                execute_times=execute_times,
            )

            # 更新周期处理记录
            cycle_handle_record.update(
                {
                    str(action_id): {
                        "last_time": int(time.time()),
                        "is_shielded": alert.is_shielded,
                        "latest_anomaly_time": alert.latest_time,
                        "execute_times": execute_times + 1,
                    }
                }
            )
            alert.update_extra_info("cycle_handle_record", cycle_handle_record)

    def check_interval_matched_actions(self, last_execute_info, action_config, alert: Alert):
        """
        判断周期间隔是否已经达到，用于控制告警动作的执行频率

        参数:
            last_execute_info: dict 上次执行信息，包含以下键值：
                - execute_times: int 已执行次数
                - last_time: int 上次执行时间戳
                - latest_anomaly_time: int 最新异常时间戳
            action_config: dict 动作配置对象，包含执行配置模板
            alert: AlertObject 告警对象，包含以下属性：
                - id: 告警记录ID
                - strategy_id: 关联策略ID
                - latest_time: 当前最新异常时间戳

        返回值:
            bool 表示是否满足周期执行条件：
                True: 满足周期间隔且通过重复检测
                False: 不满足条件或发生异常

        处理流程：
        1. 从动作配置中提取执行模板（捕获配置缺失异常）
        2. 计算当前应执行间隔（基于执行次数）
        3. 验证时间间隔条件：
           - 间隔必须大于0
           - 当前时间必须超过上次执行时间+间隔
        4. 检查异常时间戳是否重复（避免相同异常点重复通知）
        5. 通过所有验证后记录执行日志
        """
        try:
            # 提取执行配置模板
            execute_config = action_config["execute_config"]["template_detail"]
        except (KeyError, TypeError) as error:
            # 配置缺失或格式错误时记录异常日志
            logger.error(
                "[check_interval_matched_actions] alert(%s) strategy(%s) error %s",
                alert.id,
                alert.strategy_id,
                str(error),
            )
            return False

        # 计算当前执行间隔（单位：秒）
        notify_interval = self.calc_action_interval(execute_config, last_execute_info["execute_times"])
        # 时间间隔条件验证：
        # 1. 间隔必须大于0
        # 2. 当前时间必须超过上次执行时间+间隔，防止过早触发
        if notify_interval <= 0 or last_execute_info["last_time"] + notify_interval > int(time.time()):
            return False

        # 异常时间戳重复检测：
        # 如果最新异常时间早于等于上次执行记录的异常时间
        # 说明是重复异常点，避免重复通知
        if last_execute_info.get("latest_anomaly_time", 0) >= alert.latest_time:
            return False

        # 通过所有验证条件，记录执行日志
        logger.info(
            "[Send Task: create interval action] alert(%s) strategy(%s) last_execute_info: (%s), notify_interval: (%s)",
            alert.id,
            alert.strategy_id,
            last_execute_info,
            notify_interval,
        )
        return True

    @staticmethod
    def calc_action_interval(execute_config, execute_times):
        """
        计算周期任务间隔时间（单位由配置决定）

        参数:
            execute_config: dict类型，执行配置字典，包含以下可选键值：
                - need_poll: bool类型，是否需要轮询（默认True）
                - notify_interval: int类型，基础通知间隔时间（默认0）
                - interval_notify_mode: 间隔通知模式（默认IntervalNotifyMode.STANDARD）
            execute_times: int类型，当前执行次数（从1开始计数）

        返回值:
            int类型，计算得到的间隔时间（单位与配置一致），返回0表示无需等待

        执行流程说明：
        1. 快速失败机制：当配置显式禁用轮询时直接返回0
        2. 基础间隔获取：安全读取配置值并进行类型防护
        3. 动态间隔计算：根据通知模式应用不同的增长算法
        4. 指数退避处理：在递增模式下使用2的幂次增长算法
        """
        if execute_config.get("need_poll", True) is False:
            # 跳过间隔计算直接返回0
            return 0

        try:
            # 获取基础通知间隔时间并进行类型安全转换
            notify_interval = int(execute_config.get("notify_interval", 0))
        except TypeError:
            # 类型转换失败时使用默认值0
            notify_interval = 0

        # 获取间隔通知模式并应用对应计算策略
        interval_notify_mode = execute_config.get("interval_notify_mode", IntervalNotifyMode.STANDARD)
        if interval_notify_mode == IntervalNotifyMode.INCREASING:
            # 指数增长模式：间隔时间随执行次数指数级递增（2^(n-1)倍增长）
            notify_interval = int(notify_interval * math.pow(2, execute_times - 1))
        return notify_interval
