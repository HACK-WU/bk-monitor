"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import copy
import inspect
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime

import jmespath
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from alarm_backends.core.cache.action_config import ActionConfigCacheManager
from alarm_backends.core.context import ActionContext
from alarm_backends.core.i18n import i18n
from api.itsm.default import (
    CreateFastApprovalTicketResource,
    TicketApproveResultResource,
    TicketRevokeResource,
)
from bkmonitor.db_routers import backend_alert_router
from bkmonitor.documents import AlertDocument, AlertLog, EventDocument
from bkmonitor.models.fta import ActionInstance, ActionInstanceLog
from bkmonitor.utils.send import ChannelBkchatSender, Sender
from bkmonitor.utils.template import AlarmNoticeTemplate, Jinja2Renderer
from bkmonitor.utils.tenant import bk_biz_id_to_bk_tenant_id
from constants.action import (
    ACTION_DISPLAY_STATUS_DICT,
    ACTION_STATUS_DICT,
    DEMO_CONTEXT,
    NOTIFY_STEP_ACTION_SIGNAL_MAPPING,
    STATUS_NOTIFY_DICT,
    ActionLogLevel,
    ActionPluginType,
    ActionSignal,
    ActionStatus,
    FailureType,
    NoticeChannel,
    NoticeType,
    NoticeWay,
    NotifyStep,
)

from .utils import (
    AlertAssignee,
    PushActionProcessor,
    get_notice_display_mapping,
    need_poll,
)

logger = logging.getLogger("fta_action.run")


class ActionAlreadyFinishedError(BaseException):
    """
    已经结束
    """

    def __init__(self, *args, **kwargs):
        pass


class BaseActionProcessor:
    """
    Action 处理器
    {
        "action_id": instance_id,
        "run_times": run_times,
        "module": callback_module,
        "function": callback_func,
    }
    """

    NOTICE_SENDER = {NoticeChannel.BK_CHAT: ChannelBkchatSender}

    def __init__(self, action_id, alerts=None):
        """
        初始化告警处理动作处理器

        参数:
            action_id: 处理动作实例ID，用于从数据库加载ActionInstance对象
            alerts: 告警列表，可选参数，用于关联当前处理动作涉及的告警

        该方法完成以下初始化流程：
        1. 加载处理动作实例并设置国际化和租户信息
        2. 初始化重试相关参数（重试次数、最大重试次数、重试间隔）
        3. 加载并验证处理套餐配置（支持缓存配置和快照配置）
        4. 处理套餐禁用/删除场景（首次执行直接失败，执行中任务使用快照）
        5. 加载策略通知配置和执行配置（超时设置、失败重试配置）
        6. 构建上下文并初始化通知接收人信息
        7. 判断任务是否已结束
        """
        # 1. 加载处理动作实例并设置基础信息
        self.action = ActionInstance.objects.get(id=action_id)
        # 设置当前业务的国际化语言环境
        i18n.set_biz(self.action.bk_biz_id)
        # 将业务ID转换为租户ID，用于多租户场景
        self.bk_tenant_id = bk_biz_id_to_bk_tenant_id(self.action.bk_biz_id)
        # 关联的告警列表
        self.alerts = alerts

        # 2. 初始化重试相关参数
        self.retry_times = 0  # 当前重试次数
        self.max_retry_times = 0  # 最大重试次数
        self.retry_interval = 0  # 重试间隔（秒）
        self.is_finished = False  # 任务是否已结束标志
        self.notify_config = None  # 通知配置

        # 3. 加载处理套餐配置
        # 优先从缓存中获取处理套餐配置
        self.action_config = ActionConfigCacheManager.get_action_config_by_id(self.action.action_config_id)
        # 对于演示(DEMO)和手动(MANUAL)信号，直接使用动作实例中的配置
        if self.action.signal in [ActionSignal.DEMO, ActionSignal.MANUAL]:
            self.action_config = self.action.action_config

        # 4. 处理套餐禁用或删除的场景
        if self.action_config.get("is_enabled", False) is False and self.action.signal != ActionSignal.DEMO:
            # 对于首次执行或通知/Webhook类型的插件，直接标记为失败
            if self.action.execute_times == 0 or self.action.action_plugin["plugin_type"] in [
                ActionPluginType.NOTICE,
                ActionPluginType.WEBHOOK,
            ]:
                self.set_finished(ActionStatus.FAILURE, message=_("当前处理套餐配置已被停用或删除，按失败处理"))
                raise ActionAlreadyFinishedError(_("当前处理套餐配置已被停用或删除，按失败处理"))
            # 对于已经在执行中的任务，使用动作实例中保存的配置快照继续执行
            self.action_config = self.action.action_config

        # 5. 加载策略通知配置
        # TODO: 非策略产生的告警(告警来源非监控) 支持通过告警分派进行通知
        if self.action.strategy:
            self.notify_config = self.action.strategy.get("notice")

        # 6. 解析执行配置
        self.execute_config = self.action_config.get("execute_config", {})
        # 超时设置（秒）
        self.timeout_setting = self.execute_config.get("timeout")
        # 失败重试配置
        self.failed_retry = self.execute_config.get("failed_retry", {})
        # 最大重试次数（-1表示不限制）
        self.max_retry_times = int(self.failed_retry.get("max_retry_times", -1))
        # 重试间隔（秒）
        self.retry_interval = int(self.failed_retry.get("retry_interval", 0))

        # 7. 从动作输出中获取当前的重试次数
        self.retry_times = self.action.outputs.get("retry_times", 0)

        # 8. 构建上下文信息（包含告警、目标、策略等完整信息）
        self.context = self.get_context()

        # 9. 初始化通知接收人信息
        # 优先使用上下文中的通知接收人，否则使用动作的分配人
        self.notice_receivers = self.context.get("notice_receiver") or self.action.assignee
        # 确保通知接收人为列表格式
        self.notice_receivers = (
            self.notice_receivers if isinstance(self.notice_receivers, list) else [self.notice_receivers]
        )
        # 获取通知方式的显示名称（如：邮件、短信、企业微信等）
        self.notice_way_display = get_notice_display_mapping(self.context.get("notice_way", ""))

        # 10. 判断任务是否已经结束
        self.is_finished = self.action.status in ActionStatus.END_STATUS

        logger.info("load BaseActionProcessor for action(%s) finished", action_id)

    def get_context(self):
        """
        获取上下文
        :return:
        """
        if self.action.signal == ActionSignal.DEMO:
            # 如果是调试任务，则设置样例参数
            demo_context = copy.deepcopy(DEMO_CONTEXT)

            event = EventDocument(**{"bk_biz_id": 2, "ip": "127.0.0.1", "bk_cloud_id": 0})
            alert = AlertDocument(
                **{
                    "event": event,
                    "severity": 1,
                    "begin_time": int(time.time()),
                    "create_time": int(time.time()),
                    "latest_time": int(time.time()),
                    "duration": 60,
                    "common_dimensions": {},
                    "extra_info": {"strategy": {}},
                }
            )
            demo_context.update({"alert": alert})
            return demo_context
        return ActionContext(self.action, alerts=self.alerts).get_dictionary()

    @property
    def inputs(self):
        """
        输入数据
        """
        raise NotImplementedError

    def execute(self, failed_times=0):
        """
        执行入口
        :param failed_times: 执行失败的次数
        :return:
        """
        raise NotImplementedError

    def wait_callback(self, callback_func, kwargs=None, delta_seconds=0):
        """
        等待回调或者轮询

        该方法用于将当前动作任务延迟一段时间后重新推入执行队列，实现异步回调或轮询机制。
        主要用于需要等待外部系统响应或定时检查任务状态的场景。

        参数:
            callback_func: str, 回调函数名称，将在延迟后被调用
            kwargs: dict, 可选，传递给回调函数的关键字参数，默认为空字典
            delta_seconds: int, 延迟执行的秒数，默认为0（立即执行）

        返回值:
            None

        执行流程:
        1. 初始化回调参数字典
        2. 获取回调函数所在的模块路径
        3. 记录延迟执行日志
        4. 将动作任务推入执行队列并设置延迟时间

        使用场景:
        - 轮询第三方系统任务状态（如作业平台、标准运维）
        - 等待超时后执行下一步操作
        - 实现异步任务的流程编排
        """
        # 步骤1: 初始化回调参数，确保kwargs为字典类型
        kwargs = kwargs or {}

        # 步骤2: 获取回调函数所在的模块路径
        # 优先使用类属性CALLBACK_MODULE，如果不存在则通过栈帧动态获取调用者模块
        callback_module = getattr(self, "CALLBACK_MODULE", "")
        if not callback_module:
            try:
                # 通过inspect获取调用栈，找到调用者所在的模块名称
                # stack()[1][0] 表示获取上一层调用栈的帧对象
                callback_module = inspect.getmodule(inspect.stack()[1][0]).__name__
            except BaseException as error:
                # 如果获取模块失败，记录异常日志但不中断流程
                logger.exception("inspect module error %s", str(error))

        # 步骤3: 记录延迟执行的日志信息
        # 格式: $动作ID delay to run 模块名.回调函数名 wait(延迟秒数)
        logger.info("$%s delay to run %s.%s wait(%s)", self.action.id, callback_module, callback_func, delta_seconds)

        # 步骤4: 将动作任务推入Celery执行队列
        # countdown参数指定延迟执行的秒数
        # callback_func指定延迟后要调用的函数名
        # kwargs包含传递给回调函数的参数
        PushActionProcessor.push_action_to_execute_queue(
            self.action, countdown=delta_seconds, callback_func=callback_func, kwargs=kwargs
        )

    def create_approve_ticket(self, **kwargs):
        """
        创建ITSM工单
        """

        content_template = AlarmNoticeTemplate.get_template("notice/fta_action/itsm_ticket_content.jinja")
        approve_content = Jinja2Renderer.render(content_template, self.context)
        ticket_data = {
            "creator": "fta-system",
            "fields": [
                {
                    "key": "title",
                    "value": _("[告警异常防御审批]:是否继续执行套餐【{}】").format(self.action_config["name"]),
                },
                {"key": "APPROVER", "value": ",".join(self.action.assignee)},
                {"key": "APPROVAL_CONTENT", "value": approve_content},
            ],
            "meta": {"callback_url": os.path.join(settings.BK_PAAS_INNER_HOST, "fta/action/instances/callback/")},
        }
        try:
            approve_info = CreateFastApprovalTicketResource().request(**ticket_data)
        except BaseException as error:
            self.set_finished(
                ActionStatus.FAILURE, message=_("创建异常防御审批单据失败,错误信息：{}").format(str(error))
            )
            return
        # 创建快速审批单据并且记录审批信息
        self.update_action_outputs({"approve_info": approve_info})

        # 创建快速审批单据后设置一个30分钟超时任务
        self.wait_callback("approve_timeout_callback", approve_info, delta_seconds=60 * 30)

        # 每隔1分钟之后获取记录
        self.wait_callback("get_approve_result", approve_info, delta_seconds=60)

        self.action.insert_alert_log(notice_way_display=self.notice_way_display)

    def get_approve_result(self, **kwargs):
        """
        获取审批结果 同意：推入队列，直接执行 拒绝
        """
        if self.action.status != ActionStatus.WAITING:
            logger.info("current status %s is forbidden to run", self.action.status)
            return

        sn = kwargs.get("sn") or self.action.outputs.get("approve_info", {}).get("sn")
        try:
            approve_result = TicketApproveResultResource().request(**{"sn": [sn]})[0]
        except BaseException as error:
            logger.exception("get approve result error : %s, request sn: %s", error, sn)
            self.set_finished(
                ActionStatus.FAILURE, message=_("获取异常防御审批结果出错，错误信息：{}").format(str(error))
            )
        else:
            self.approve_callback(**approve_result)

    def approve_callback(self, **kwargs):
        if self.action.status != ActionStatus.WAITING:
            logger.info("current status %s is forbidden to run", self.action.status)
            return

        approve_result = kwargs
        if approve_result["current_status"] == "RUNNING":
            # 还在执行中, 等待五分钟之后再次获取结果
            self.wait_callback("get_approve_result", {"sn": approve_result["sn"]}, delta_seconds=60)
            return
        if approve_result["current_status"] == "FINISHED" and approve_result["approve_result"] is True:
            # 结束并且通过的，直接入到执行队列
            self.update_action_status(ActionStatus.RUNNING)
            self.wait_callback("execute")
            self.insert_action_log(
                step_name=_("异常防御审批通过"),
                action_log=_("{}审批通过，继续执行处理动作，工单详情<a target = 'blank' href='{}'>{}<a/>").format(
                    approve_result["updated_by"], approve_result["sn"], approve_result["ticket_url"]
                ),
                level=ActionLogLevel.INFO,
            )
            return
        self.set_finished(
            ActionStatus.SKIPPED, message=_("审批不通过，忽略执行，审批人{}").format(approve_result["updated_by"])
        )

    def get_action_info(self, callback_module, callback_func, kwargs):
        return {
            "id": self.action.id,
            "failed_times": 0,
            "module": callback_module,
            "function": callback_func,
            "kwargs": kwargs,
        }

    def insert_action_log(self, step_name, action_log, level=ActionLogLevel.DEBUG):
        """
        记录操作事件日志
        """
        if getattr(settings, "INSERT_ACTION_LOG", False):
            ActionInstanceLog.objects.create(
                action_instance_id=self.action.id, step_name=step_name, content=action_log, level=level
            )

    def insert_alert_log(self, description=None):
        if self.action.parent_action_id or not self.action.alerts:
            # 如果为子任务，直接不插入日志记录
            return
        status_display = ACTION_DISPLAY_STATUS_DICT.get(self.action.status)
        if self.action.status == ActionStatus.FAILURE:
            status_display = _("{}, 失败原因：{}").format(status_display, self.action.ex_data.get("message", "--"))
        if description is None:
            description = json.dumps(
                self.action.get_content(
                    **{
                        "notice_way_display": get_notice_display_mapping(self.context.get("notice_way")),
                        "status_display": status_display,
                        "action_name": self.action.action_config.get("name", ""),
                    }
                )
            )

        action_log = dict(
            op_type=AlertLog.OpType.ACTION,
            alert_id=self.action.alerts,
            description=description,
            time=int(time.time()),
            create_time=int(time.time()),
            event_id=f"{int(self.action.create_time.timestamp())}{self.action.id}",
        )
        AlertLog.bulk_create([AlertLog(**action_log)])

    def set_start_to_execute(self):
        """
        标记开始执行处理动作任务

        该方法在处理动作正式执行前被调用，负责完成以下核心工作：
        1. 发送执行开始通知（仅首次执行时）
        2. 设置超时回调机制（针对非通知/Webhook类型的插件）
        3. 更新动作状态为RUNNING并记录执行信息

        执行流程：
        - 首次执行（retry_times=0）：发送开始通知，设置超时回调
        - 重试执行：跳过开始通知，直接更新状态
        - 通知/Webhook类型：不设置超时回调

        注意事项：
        - 通知发送失败不会阻塞任务执行
        - 超时回调仅在配置了timeout_setting时生效
        - 执行次数和重试次数会同步递增
        """
        # ========== Step 1: 发送自愈开始通知 ==========
        execute_notify_result = None
        if getattr(self, "retry_times", 0) == 0:
            # 判断是否为首次执行（重试次数为0）
            # 仅在首次执行时发送开始通知，避免重试时重复通知
            execute_notify_result = self.notify(NotifyStep.BEGIN)

        # ========== Step 2: 设置超时回调机制 ==========
        if STATUS_NOTIFY_DICT.get(self.action.status) == NotifyStep.BEGIN:
            # 验证当前动作状态是否处于开始执行阶段
            # STATUS_NOTIFY_DICT: 状态与通知步骤的映射关系
            try:
                if (
                    self.action.action_plugin.get("plugin_type")
                    not in [
                        ActionPluginType.NOTICE,
                        ActionPluginType.WEBHOOK,
                    ]
                    and self.timeout_setting
                ):
                    # 超时回调设置条件：
                    # 1. 插件类型不是通知(NOTICE)或Webhook类型
                    #    - 通知和Webhook通常是即时操作，不需要超时控制
                    # 2. 配置了超时时间(timeout_setting不为空)
                    #
                    # 设置延迟回调任务，在超时时间后执行timeout_callback方法
                    # 如果任务在超时前完成，该回调会被忽略（在timeout_callback中判断状态）
                    self.wait_callback(callback_func="timeout_callback", delta_seconds=self.timeout_setting)
            except BaseException as error:
                # 超时回调设置失败不应阻塞任务执行
                # 仅记录异常日志，继续后续流程
                logger.exception("run action: send notify error %s, action %s", error, self.action.id)

        # ========== Step 3: 更新动作状态和执行信息 ==========
        self.update_action_status(
            ActionStatus.RUNNING,  # 将动作状态更新为"执行中"
            **{
                "execute_times": self.action.execute_times + 1,  # 执行次数递增
                "outputs": {
                    # 输出信息包含以下关键数据：
                    "retry_times": self.retry_times + 1,  # 重试次数递增（首次执行时从0变为1）
                    "execute_notify_result": execute_notify_result
                    if execute_notify_result
                    else {},  # 开始通知的发送结果
                    "target_info": self.get_target_info_from_ctx(),  # 从上下文提取目标信息（业务、主机、策略等）
                },
            },
        )

    def get_target_info_from_ctx(self):
        """获取目标信息"""
        action_instance = self.action
        action_ctx = self.context
        target = action_ctx["target"]
        try:
            target_info = {
                "bk_biz_name": target.business.bk_biz_name,
                "bk_target_display": action_ctx["alarm"].target_display,
                "dimensions": [d.to_dict() for d in action_ctx["alarm"].new_dimensions.values()],
                "strategy_name": action_instance.strategy.get("name") or "--",
                "operate_target_string": action_ctx["action_instance"].operate_target_string,
            }
        except BaseException as error:
            logger.info("get targe info failed: %s", str(error))
            return {}
        try:
            host = target.host
        except BaseException as error:
            logger.info("get target host for alert %s error: %s", action_instance.alerts, str(error))
            host = None

        target_info.update(
            dict(
                bk_set_ids=host.bk_set_ids,
                bk_set_names=host.set_string,
                bk_module_ids=host.bk_module_ids,
                bk_module_names=host.module_string,
            )
            if host
            else {}
        )
        return target_info

    def is_action_finished(self, outputs: list, finished_rule):
        """
        根据配置的条件来判断任务是否结束
        """
        if not finished_rule:
            return False

        return self.business_rule_validate(outputs, finished_rule)

    def is_node_finished(self, outputs: list, finished_rule):
        """
        根据配置的条件来判断某一个步骤是否结束
        """
        if not finished_rule:
            return True

        return self.business_rule_validate(outputs, finished_rule)

    def is_action_success(self, outputs: list, success_rule):
        """
        根据配置的条件来判断任务是否成功
        """
        if not success_rule:
            return True

        return self.business_rule_validate(outputs, success_rule)

    @staticmethod
    def business_rule_validate(params, rule):
        """ "
        条件判断
        """

        logger.info("business rule validate params %s, rule %s", params, rule)

        if rule["method"] == "equal":
            return jmespath.search(rule["key"], params) == rule["value"]

        if rule["method"] == "in":
            return jmespath.search(rule["key"], params) in rule["value"]

        if rule["method"] == "not in":
            return jmespath.search(rule["key"], params) not in rule["value"]

        return False

    def set_finished(
        self, to_status, failure_type="", message=_("执行任务成功"), retry_func="execute", kwargs=None, end_time=None
    ):
        """
        设置任务结束状态并处理后续流程

        该方法是任务生命周期管理的核心方法，负责处理任务结束时的各种场景，包括：
        - 失败重试机制（普通重试和框架异常重试）
        - 超时回调设置
        - 任务状态更新
        - 执行日志记录
        - 告警日志插入
        - 执行结果通知

        参数:
            to_status: str, 目标结束状态，必须是ActionStatus.END_STATUS中的值
            failure_type: str, 可选，失败类型，如FailureType.TIMEOUT、FailureType.FRAMEWORK_CODE等
            message: str, 结束日志信息，默认为"执行任务成功"
            retry_func: str, 重试时要调用的函数名，默认为"execute"
            kwargs: dict, 可选，重试时传递给回调函数的参数
            end_time: datetime, 可选，任务结束时间，默认为当前UTC时间

        返回值:
            None

        执行流程:
        1. 验证目标状态是否为合法的结束状态
        2. 判断是否需要普通重试（失败且未超时且未达最大重试次数）
        3. 判断是否需要框架异常重试（框架代码异常且节点执行次数<3）
        4. 确认任务真正结束，更新状态并发送通知
        """
        # 步骤1: 验证目标状态的合法性
        # 只有END_STATUS中的状态才能作为结束状态（如SUCCESS、FAILURE等）
        if to_status not in ActionStatus.END_STATUS:
            logger.info("destination status %s is not in end status list", to_status)
            return

        # 步骤2: 处理普通失败重试逻辑
        # 重试条件：
        # - 目标状态为FAILURE（失败）
        # - 失败类型不是TIMEOUT（超时失败不重试）
        # - 当前重试次数未达到最大重试次数限制
        if (
            to_status == ActionStatus.FAILURE
            and failure_type != FailureType.TIMEOUT
            and self.retry_times < self.max_retry_times
        ):
            # 当执行失败的时候，需要进行重试
            # 此处存在的问题： 重试从哪里开始，譬如标准运维的重试，很有可能需要调用重试的接口，
            # 目前延用自愈以前的方式通过通完全重试的方法来进行重试

            # 如果是首次重试且配置了超时时间，则设置超时回调
            # 超时回调会在指定时间后触发，用于处理任务执行超时的情况
            if self.retry_times == 0 and self.timeout_setting:
                self.wait_callback(callback_func="timeout_callback", delta_seconds=self.timeout_setting)

            # 标记任务未结束，准备进行重试
            self.is_finished = False
            # 将重试任务推入队列，延迟retry_interval秒后执行
            self.wait_callback(retry_func, delta_seconds=self.retry_interval, kwargs=kwargs)
            return

        # 步骤3: 处理框架代码异常的特殊重试逻辑
        # 框架异常重试条件：
        # - 失败类型为FRAMEWORK_CODE（框架代码异常，如Python运行时错误）
        # - 当前节点执行次数少于3次（每个节点最多重试3次）
        # - 未设置ignore_error标志（允许重试）
        if (
            failure_type == FailureType.FRAMEWORK_CODE
            and kwargs.get("node_execute_times", 0) < 3
            and kwargs.get("ignore_error", False) is False
        ):
            # 如果是自愈系统异常并且当前说节点执行次数少于3次，继续重试
            self.is_finished = False
            # 框架异常重试间隔固定为5秒
            self.wait_callback(retry_func, delta_seconds=5, kwargs=kwargs)
            # 保存当前的outputs数据，记录节点执行次数
            self.action.save(update_fields=["outputs"])
            return

        # 步骤4: 确认任务真正结束，执行结束流程
        self.is_finished = True

        # 步骤4.1: 更新任务状态到数据库
        # 任务结束的时候，需要发送通知
        self.update_action_status(
            to_status=to_status,  # 最终状态（SUCCESS或FAILURE）
            failure_type=failure_type,  # 失败类型
            end_time=end_time or datetime.now(tz=timezone.utc),  # 结束时间
            need_poll=need_poll(self.action),  # 是否需要轮询
            ex_data={"message": message},  # 附加消息数据
        )

        # 步骤4.2: 插入任务执行日志
        # 根据结束状态确定日志级别：失败为ERROR，成功为INFO
        level = ActionLogLevel.ERROR if to_status == ActionStatus.FAILURE else ActionLogLevel.INFO
        self.insert_action_log(
            step_name=_("第{}次任务执行结束".format(self.retry_times)),
            action_log=_("执行{}: {}").format(ACTION_STATUS_DICT.get(to_status), message),
            level=level,
        )

        # 步骤4.3: 将执行结果插入到告警日志中
        # 用于在告警详情页面展示处理动作的执行记录
        self.action.insert_alert_log(notice_way_display=getattr(self, "notice_way_display", ""))

        # 步骤4.4: 发送执行结果通知（仅非通知类插件需要发送）
        # 通知类插件本身就是发送通知的，不需要再发送执行结果通知
        if self.action.action_plugin.get("plugin_type") != ActionPluginType.NOTICE:
            # 根据任务结束状态发送对应的通知（成功通知或失败通知）
            # need_update_context=True 表示需要更新通知上下文数据
            notify_result = self.notify(STATUS_NOTIFY_DICT.get(to_status), need_update_context=True)

            # 如果通知发送成功，将通知结果记录到action的outputs中
            if notify_result:
                # 获取已有的通知结果记录，如果不存在则初始化为空字典
                execute_notify_result = self.action.outputs.get("execute_notify_result") or {}
                # 合并本次通知结果
                execute_notify_result.update(notify_result)
                # 更新到action的outputs中，用于后续查询和展示
                self.update_action_outputs(outputs={"execute_notify_result": execute_notify_result})

    def update_action_status(self, to_status, failure_type="", **kwargs):
        """
        更新任务状态
        :param from_status:前置状态
        :param to_status:后置状态
        :param failure_type:失败类型
        :return:
        """
        with transaction.atomic(using=backend_alert_router):
            try:
                locked_action = ActionInstance.objects.select_for_update().get(pk=self.action.id)
            except ActionInstance.DoesNotExist:
                return None
            locked_action.status = to_status
            locked_action.failure_type = failure_type
            for key, value in kwargs.items():
                # 其他需要跟新的参数，直接刷新
                setattr(locked_action, key, value)
            locked_action.save(using=backend_alert_router)
            # 刷新当前的事件记录
            self.action = locked_action

    def update_action_outputs(self, outputs):
        """
        更新用户的输出
        :param outputs:
        :return:
        """
        if not isinstance(outputs, dict):
            # 没有输出参数列表，直接返回
            return

        with transaction.atomic(using=backend_alert_router):
            try:
                locked_action = ActionInstance.objects.select_for_update().get(pk=self.action.id)
            except ActionInstance.DoesNotExist:
                return None
            if locked_action.outputs:
                locked_action.outputs.update(outputs)
            else:
                locked_action.outputs = outputs
            outputs.update(locked_action.outputs)
            locked_action.save(using=backend_alert_router)
            self.action = locked_action

    def notify(self, notify_step, need_update_context=False):
        """
        根据处理动作的执行阶段发送相应的通知消息

        参数:
            notify_step: NotifyStep枚举值，表示通知发送的阶段
                        - NotifyStep.BEGIN: 开始执行通知
                        - NotifyStep.SUCCESS: 执行成功通知
                        - NotifyStep.FAILURE: 执行失败通知
            need_update_context: bool，是否需要重新获取上下文信息
                                默认False使用缓存的self.context
                                True时会调用self.get_context()获取最新数据

        返回值:
            dict: 通知发送结果字典，格式为 {notify_step: {notice_way: [result_list]}}
                 例如: {NotifyStep.BEGIN: {'weixin': [{'result': 'success'}]}}
            None: 当不需要发送通知时返回None

        该方法实现完整的多渠道通知发送流程，包含：
        1. 通知必要性检查（是否需要发送通知）
        2. 获取通知接收人信息（按通知方式分组）
        3. 解析通知渠道和方式（支持新旧格式兼容）
        4. 构建通知发送器并发送消息
        5. 特殊处理语音通知（逐个接收人发送）
        """

        # ========== Step 1: 检查是否需要发送通知 ==========
        if self.no_need_notify(notify_step):
            # 不需要通知的场景：
            # 1. 插件类型为通知类型（NOTICE）- 避免重复通知
            # 2. 未配置通知策略（notify_config为空）
            # 3. 当前通知步骤未在策略信号列表中
            return

        # ========== Step 2: 获取通知接收人信息 ==========
        # 通过AlertAssignee类根据告警信息和用户组配置获取接收人列表
        # 返回格式: {notice_way: [receivers], 'wxbot_mention_users': [...]}
        notify_info = AlertAssignee(self.context["alert"], self.notify_config["user_groups"]).get_notice_receivers(
            NoticeType.ACTION_NOTICE, notify_step
        )

        # 初始化通知结果收集器，使用defaultdict自动创建列表
        notice_result = defaultdict(list)

        # ========== Step 3: 处理企业微信机器人@用户功能 ==========
        # TODO: 企业微信机器人通知@用户功能待完善
        # 从通知信息中提取需要@的用户列表（仅取第一个元素）
        wxbot_mention_users = notify_info.pop("wxbot_mention_users", [])
        if wxbot_mention_users:
            wxbot_mention_users = wxbot_mention_users[0]

        # ========== Step 4: 遍历各通知方式并发送消息 ==========
        for notice_way, notice_receivers in notify_info.items():
            # ========== Step 4.1: 解析通知渠道和方式 ==========
            try:
                # 新格式: "channel|notice_way" (例如: "bkchat|weixin")
                # channel: 通知渠道（如bkchat）
                # notice_way: 具体通知方式（如weixin、mail、sms等）
                channel, notice_way = notice_way.split("|")
            except ValueError:
                # 旧格式兼容: 直接是通知方式，没有渠道前缀
                # 这种情况下channel为空字符串，使用默认发送器
                channel = ""
                notice_way = notice_way

            # ========== Step 4.2: 构建模板路径 ==========
            # 标题模板路径（固定格式）
            title_template_path = f"notice/fta_action/{notice_way}_title.jinja"
            # 内容模板路径（根据通知方式选择markdown或普通格式）
            # MD_SUPPORTED_NOTICE_WAYS: 支持Markdown格式的通知方式列表
            content_template_path = "notice/fta_action/{notice_way}_content.jinja".format(
                notice_way="markdown" if notice_way in settings.MD_SUPPORTED_NOTICE_WAYS else notice_way
            )

            # ========== Step 4.3: 创建通知发送器实例 ==========
            # 根据渠道选择对应的发送器类（如企业微信使用ChannelBkchatSender）
            # 默认使用通用Sender类
            sender_class = self.NOTICE_SENDER.get(channel, Sender)
            notify_sender = sender_class(
                context=self.get_context()
                if need_update_context
                else self.context,  # 上下文数据（包含告警、目标等信息）
                title_template_path=title_template_path,  # 标题模板路径
                content_template_path=content_template_path,  # 内容模板路径
                notice_type=NoticeType.ACTION_NOTICE,  # 通知类型：处理动作通知
                bk_tenant_id=self.bk_tenant_id,  # 租户ID（用于多租户场景）
            )

            # 设置企业微信机器人需要@的用户列表
            notify_sender.mentioned_users = wxbot_mention_users

            # ========== Step 4.4: 发送通知消息 ==========
            if notice_way != NoticeWay.VOICE:
                # 非语音通知：批量发送给所有接收人
                # 大多数通知方式（邮件、短信、企业微信等）支持一次发送给多个接收人
                notice_result[notice_way].append(
                    notify_sender.send(
                        notice_way,  # 通知方式
                        notice_receivers=notice_receivers,  # 接收人列表
                        action_plugin=self.action.action_plugin["plugin_type"],  # 插件类型
                    )
                )
                continue

            # ========== Step 4.5: 语音通知特殊处理 ==========
            # 语音通知需要逐个接收人发送（电话呼叫的特性）
            for notice_receiver in notice_receivers:
                notice_result[notice_way].append(
                    notify_sender.send(
                        notice_way,  # 通知方式：语音
                        notice_receivers=notice_receiver,  # 单个接收人
                        action_plugin=self.action.action_plugin["plugin_type"],  # 插件类型
                    )
                )

        # ========== Step 5: 返回通知发送结果 ==========
        # 返回格式: {notify_step: {notice_way: [result_list]}}
        # 便于调用方追踪各通知方式的发送结果
        return {notify_step: notice_result}

    def no_need_notify(self, notify_step=NotifyStep.BEGIN):
        # 通知类型的响应事件，作为事件处理
        # 没有处理套餐配置的，不做通知
        # 没有通知套餐的，不做通知

        if self.action_config.get("plugin_type") == ActionPluginType.NOTICE:
            # 当为通知套餐的时候， 不需要发送执行通知
            return True

        if not self.notify_config:
            # 通知配置不存在的时候，不需要发送执行通知
            return True

        notify_step_signal = NOTIFY_STEP_ACTION_SIGNAL_MAPPING.get(int(notify_step))
        if self.notify_config and notify_step_signal not in self.notify_config["signal"]:
            # 当前处理阶段不需要发送通知
            return True

        return False

    def timeout_callback(self):
        """
        超时任务回调处理方法

        功能说明:
            当动作执行超过配置的最大时长时，由定时任务触发此回调方法，
            将任务标记为失败状态并记录超时原因

        执行流程:
            1. 检查任务当前状态是否已结束
            2. 若未结束则将任务设置为超时失败状态

        应用场景:
            - 防止任务无限期挂起占用系统资源
            - 为用户提供明确的超时失败反馈
            - 触发后续的失败处理流程（如通知、重试等）

        注意事项:
            - 超时时长由套餐配置中的 execute_config.timeout 字段决定
            - 超时检查由定时任务 check_timeout_actions 周期性执行
            - 已结束的任务不会被重复处理
        """
        # ==================== 步骤1: 检查任务状态 ====================
        # 判断任务是否已经处于结束状态（成功/失败/跳过等）
        # 避免对已完成的任务进行重复处理
        if self.action.status in ActionStatus.END_STATUS:
            # 任务已经结束，直接返回，不做任何处理
            return

        # ==================== 步骤2: 设置超时失败状态 ====================
        # 将任务标记为失败，并记录详细的超时信息
        self.set_finished(
            ActionStatus.FAILURE,  # 设置任务状态为失败
            message=_(  # 生成国际化的失败消息
                "处理执行时间超过套餐配置的最大时长{}分钟, 按失败处理"
            ).format(self.timeout_setting // 60),  # 将秒数转换为分钟数显示
            failure_type=FailureType.TIMEOUT,  # 标记失败类型为超时
        )

    def approve_timeout_callback(self, **kwargs):
        """
        审批超时任务回调
        """
        if self.action.status != ActionStatus.WAITING:
            return
        sn = kwargs.get("sn") or self.action.outputs.get("approve_info", {}).get("sn")
        try:
            TicketRevokeResource().request(
                {
                    "sn": sn,
                    "operator": "fta-system",
                    "action_message": _("异常防御审批执行时间套餐配置30分钟, 按忽略处理"),
                }
            )
            self.set_finished(ActionStatus.SKIPPED, message=_("异常防御审批执行时间套餐配置30分钟, 按忽略处理"))
        except BaseException as error:
            self.set_finished(
                ActionStatus.FAILURE,
                message=_("异常防御审批执行时间套餐配置30分钟, 撤回单据失败，错误信息：{}").format(str(error)),
            )
