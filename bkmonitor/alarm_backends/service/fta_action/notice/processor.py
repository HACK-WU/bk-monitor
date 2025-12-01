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
import random
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from alarm_backends.core.cache.key import (
    FTA_NOTICE_COLLECT_KEY,
    FTA_NOTICE_COLLECT_LOCK,
    NOTICE_VOICE_COLLECT_KEY,
)
from alarm_backends.core.lock.service_lock import service_lock
from alarm_backends.service.fta_action import ActionAlreadyFinishedError
from alarm_backends.service.fta_action.common import BaseActionProcessor
from bkmonitor.models import ActionInstance
from bkmonitor.utils.send import Sender
from constants.action import (
    ActionSignal,
    ActionStatus,
    FailureType,
    IntervalNotifyMode,
    NoticeWay,
)
from core.errors.alarm_backends import LockError

logger = logging.getLogger("fta_action.run")


class ActionProcessor(BaseActionProcessor):
    """通知处理器"""

    def __init__(self, action_id, alerts=None):
        super().__init__(action_id, alerts)
        self.notice_way = self.context.get("notice_way", "")
        self.notify_actions = []
        self.is_collect_notice = False

        # 非主任务的时候
        try:
            self.receiver_action_mapping = (
                self.get_same_notice_way_actions() if not self.action.is_parent_action else []
            )
        except LockError as error:
            self.wait_callback("execute", delta_seconds=5)
            raise error

        self.notify_item = self.execute_config["template_detail"]
        self.notify_config = self.action.inputs.get("notify_info")
        self.notify_interval = self.notify_item["notify_interval"]
        # 重试模式
        self.interval_notify_mode = self.notify_item["interval_notify_mode"]

    def get_same_notice_way_actions(self):
        """
        获取当前通知方式的所有actions
        :return:
        """
        if self.context["notice_way"] == NoticeWay.VOICE:
            # 如果是语音通知，不走汇总逻辑
            self.notify_actions = [self.action.id]
            # 语音告警的通知人员应该为所有人
            self.notice_receivers = self.action.inputs.get("notice_receiver") or self.notice_receivers

            voice_receivers = ",".join(self.notice_receivers)
            return {voice_receivers: self.action.id}

        collect_params = {
            # 汇总
            "notice_way": self.context["collect_ctx"].group_notice_way,
            "action_signal": self.action.signal,
            "alert_id": "_".join(self.action.alerts or []),
        }
        collect_key = FTA_NOTICE_COLLECT_KEY.get_key(**collect_params)
        with service_lock(FTA_NOTICE_COLLECT_LOCK, **collect_params):
            client = FTA_NOTICE_COLLECT_KEY.client
            data: dict[bytes, bytes] = client.hgetall(collect_key)
            if not data and self.action.is_parent_action is False:
                logger.info("$%s have already finished, no data found in collect_key(%s)", self.action.id, collect_key)
                raise ActionAlreadyFinishedError(_("当前告警通知已经汇总发送"))
            data: dict[str, str] = {
                (key.decode() if isinstance(key, bytes) else key): (
                    value.decode() if isinstance(value, bytes) else value
                )
                for key, value in data.items()
            }
            self.notice_receivers = list(data.keys())
            self.notify_actions = list(data.values())
            if str(self.action.id) not in self.notify_actions:
                # 如果当前的处理记录不在获取的缓存中，忽略发送
                logger.info("$%s maybe have finished by other actions", self.action.id)
                raise ActionAlreadyFinishedError("当前告警通知已经汇总发送")

            self.is_collect_notice = True

            # 针对获取到的用户信息进行清除
            for receiver in self.notice_receivers:
                client.hdel(collect_key, receiver)
        logger.info("send notice[%s]: %s by action %s", collect_key, self.notify_actions, self.action.id)
        return data

    def execute(self):
        # 只有在可执行状态下的任务才能执行
        if self.action.status in ActionStatus.CAN_EXECUTE_STATUS:
            # 执行入口，需要发送自愈通知
            self.set_start_to_execute()

            if not self.backend_config:
                self.set_finished(ActionStatus.FAILURE, message="unknown execute function")

        self.execute_notify()

    def execute_notify(self):
        """
        执行通知
        """
        if self.action.status in ActionStatus.END_STATUS and self.is_collect_notice is False:
            # 当前告警已经结束并且没有其他通知内容， 直接结束
            logger.info(f"-- notice_action action {self.action.name}({self.action.id}) is already finished !!")
            return

        logger.info(f"--begin notice_action action {self.action.name}({self.notify_actions}) ")

        if self.action.is_parent_action:
            # 更新当前任务状态
            end_time = datetime.now(timezone.utc)
            if settings.GLOBAL_SHIELD_ENABLED:
                # 全局屏蔽的情况下，需要对结束时间做打散特殊处理
                delay_time = int(self.action.strategy_id) % 10
                delay_time += random.choice(list(range(-delay_time, delay_time)))
                end_time += timedelta(minutes=delay_time)
            self.set_finished(
                ActionStatus.SKIPPED if self.action.is_empty_notice else ActionStatus.SUCCESS, end_time=end_time
            )
            return

        # 通知人及回调都为空
        if not self.notify_config:
            # 如果没有通知配置，直接返回
            self.set_finished(ActionStatus.FAILURE, failure_type=FailureType.EXECUTE_ERROR, message=_("通知配置为空"))
            return

        try:
            self.notify_handle()
        except BaseException as error:
            self.set_finished(
                ActionStatus.FAILURE,
                failure_type=FailureType.EXECUTE_ERROR,
                message=str(error),
                retry_func="execute_notify",
            )
            logger.exception(
                f"--execute {self.notice_way}_notice_action action {self.action.name}({self.action.id}) error"
            )

        logger.info(f"--end notice_action action {self.action.name}({self.action.id})")

    def calc_notify_interval(self):
        """
        计算当前的发送通知时间
        1、间隔式  interval
        2、递增式 increasing
        """
        if self.interval_notify_mode == IntervalNotifyMode.INCREASING:
            return (self.action.execute_times + 1) * self.notify_interval

        return self.notify_interval

    def notify_handle(self):
        """
        根据当前的状态发送不同的通知
        """

        level = str(self.action.alert_level)

        if not self.notice_way:
            # 没有通知方式，不做通知
            logger.info(
                f"-- notice_action action {self.action.name}({self.action.id}) failed because of no notify config of level({level}) !!"
            )

            self.set_finished(
                ActionStatus.FAILURE,
                failure_type=FailureType.EXECUTE_ERROR,
                message=_("当前级别[{}]通知类型为空").format(level),
            )
            return

        action_signal = (
            self.action.signal
            if self.action.signal not in [ActionSignal.MANUAL, ActionSignal.NO_DATA]
            else ActionSignal.ABNORMAL
        )
        msg_type = "markdown" if self.notice_way in settings.MD_SUPPORTED_NOTICE_WAYS else self.notice_way

        title_template_path = f"notice/{action_signal}/action/{self.notice_way}_title.jinja"
        content_template_path = f"notice/{action_signal}/action/{msg_type}_content.jinja"
        channel = self.context.get("notice_channel")
        # 发送通知, 根据不同的通知渠道，选择不同的发送通知类
        sender_class = self.NOTICE_SENDER.get(channel, Sender)
        notify_sender = sender_class(
            bk_tenant_id=self.bk_tenant_id,
            context=self.context,
            title_template_path=title_template_path,
            content_template_path=content_template_path,
        )

        need_send, collect_action_id = self.need_send_notice(self.notice_way)
        if need_send:
            notice_results = notify_sender.send(
                self.notice_way,
                notice_receivers=self.notice_receivers,
            )
        else:
            notice_results = {
                ",".join(self.notice_receivers): {
                    "result": False,
                    "failure_type": FailureType.SYSTEM_ABORT,
                    "message": _(
                        "语音告警告被通知套餐（{}）防御收敛，防御原因：相同通知人在两分钟内同维度告警只能接收一次电话告警"
                    ).format(collect_action_id),
                }
            }
        notify_content_outputs = {
            "title": notify_sender.title,
            "message": notify_sender.content,
        }
        self.update_action_notice_result(notice_results, notify_content_outputs)
        self.is_finished = True

    def update_action_notice_result(self, notice_results: dict, notify_content_outputs):
        """
        更新处理动作的通知结果
        """
        succeed_actions = []
        succeed_message = _("发送通知成功")

        failed_actions = []
        failed_message = _("发送失败")
        failure_type = FailureType.EXECUTE_ERROR
        for receiver, notice_result in notice_results.items():
            related_action = self.receiver_action_mapping.get(receiver)
            if not related_action:
                continue
            if notice_result["result"]:
                succeed_actions.append(related_action)
                succeed_message = notice_result.get("message") or succeed_message
            else:
                failed_actions.append(related_action)
                failed_message = notice_result.get("message") or failed_message
                failure_type = notice_result.get("failure_type") or failure_type

        if succeed_actions:
            ActionInstance.objects.filter(id__in=succeed_actions).update(
                **{
                    "status": ActionStatus.SUCCESS,
                    "end_time": datetime.now(tz=timezone.utc),
                    "ex_data": {"message": succeed_message},
                    "outputs": notify_content_outputs,
                }
            )

        if failed_actions:
            ActionInstance.objects.filter(id__in=failed_actions).update(
                **{
                    "status": ActionStatus.FAILURE,
                    "failure_type": failure_type,
                    "end_time": datetime.now(tz=timezone.utc),
                    "ex_data": {"message": failed_message},
                    "outputs": notify_content_outputs,
                }
            )

    def need_send_notice(self, notice_way):
        """
        判断是否需要发送通知（主要用于语音告警防御收敛）

        参数:
            notice_way: 通知方式，如语音、短信、邮件等

        返回值:
            tuple: (是否需要发送, 收敛的动作ID)
                - 第一个元素为布尔值，True表示需要发送，False表示被收敛
                - 第二个元素为字符串或None，当被收敛时返回收敛的动作ID，否则返回None

        该方法实现语音告警的防御收敛机制，防止短时间内重复发送语音告警：
        1. 非语音通知直接放行
        2. 提取告警的公共维度信息，构建维度哈希
        3. 基于告警信号、业务ID、告警级别、维度哈希、策略ID和接收人构建唯一标识
        4. 使用Redis的SET NX命令实现分布式锁，确保相同维度的语音告警在TTL时间内只发送一次
        5. 如果设置成功则允许发送，否则返回已存在的动作ID表示被收敛
        """
        # 1. 非语音通知直接放行，无需收敛
        if notice_way != NoticeWay.VOICE:
            return True, None

        # 2. 提取告警的公共维度信息，构建维度哈希用于标识相同维度的告警
        try:
            # 将告警的公共维度转换为 "key_value" 格式的列表，并序列化为JSON字符串
            common_dimensions = json.dumps(
                [
                    "{}_{}".format(d["key"], d["value"])
                    for d in self.context["alert"].common_dimensions
                    if d.get("value")
                ]
            )
        except AttributeError as error:
            # 如果获取维度信息失败，记录错误日志并使用空字符串
            logger.error("Get common_dimension of alert[{}] error: %s", self.context["alert"], str(error))
            common_dimensions = ""

        # 3. 构建语音告警的唯一标识标签，用于防御收敛
        labels = {
            "signal": self.action.signal,  # 告警信号类型（如异常、恢复等）
            "notice_way": NoticeWay.VOICE,  # 通知方式固定为语音
            "bk_biz_id": self.action.bk_biz_id,  # 业务ID
            "level": self.action.alert_level,  # 告警级别
            "dimension_hash": common_dimensions,  # 维度哈希，用于标识相同维度的告警
            "strategy_id": self.action.strategy_id,  # 策略ID
        }
        client = NOTICE_VOICE_COLLECT_KEY.client

        # 4. 添加接收人信息到标签中，确保相同接收人的告警被收敛
        labels["receiver"] = self.notice_receivers
        collect_key = NOTICE_VOICE_COLLECT_KEY.get_key(**labels)

        # 5. 使用Redis的SET NX命令尝试设置收敛键，如果设置成功说明是首次发送
        # ex: 设置过期时间为TTL（默认2分钟）
        # nx: 仅当键不存在时才设置，实现分布式锁的效果
        if client.set(collect_key, self.action.es_action_id, ex=NOTICE_VOICE_COLLECT_KEY.ttl, nx=True):
            return True, None

        # 6. 如果设置失败，说明在TTL时间内已有相同维度的语音告警发送过，需要收敛
        collect_action_id = client.get(collect_key)
        logger.info(
            f"action({self.action.id}) voice alarm skip, voice alarm by action({collect_action_id}) {NOTICE_VOICE_COLLECT_KEY.ttl} second age"
        )

        return False, collect_action_id
