"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import calendar
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytz
from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext as _

from alarm_backends.core.cache.cmdb.host import HostManager
from alarm_backends.core.cache.cmdb.module import ModuleManager
from alarm_backends.core.cache.key import ALERT_DETECT_RESULT
from alarm_backends.core.context import ActionContext
from alarm_backends.core.context.utils import (
    get_business_roles,
    get_notice_display_mapping,
)
from alarm_backends.core.i18n import i18n
from alarm_backends.service.converge.dimension import DimensionCalculator
from alarm_backends.service.converge.tasks import run_converge
from api.cmdb.define import Host
from bkmonitor.documents import ActionInstanceDocument, AlertDocument
from bkmonitor.models import ActionInstance, DutyArrange, DutyPlan, UserGroup
from bkmonitor.utils import time_tools
from bkmonitor.utils.tenant import bk_biz_id_to_bk_tenant_id
from constants.action import (
    ACTION_DISPLAY_STATUS_DICT,
    ActionNoticeType,
    ActionPluginType,
    ActionStatus,
    ConvergeType,
    NoticeChannel,
    NoticeType,
    NoticeWay,
    UserGroupType,
)

logger = logging.getLogger("fta_action.run")


class PushActionProcessor:
    @classmethod
    def push_actions_to_queue(
        cls, generate_uuid, alerts=None, is_shielded=False, need_noise_reduce=False, notice_config=None
    ):
        """
        推送处理事件至收敛队列

        参数:
            cls: 类对象自身（类方法隐式参数）
            generate_uuid: 字符串，唯一任务标识符，用于关联主任务与子任务
            alerts: 告警对象列表，待处理的告警事件集合（默认None）
            is_shielded: 布尔值，是否处于告警屏蔽状态（默认False）
            need_noise_reduce: 布尔值，是否需要执行降噪处理（默认False）
            notice_config: 通知配置字典，包含通知方式等元数据（默认None）

        返回值:
            列表，包含所有推送至队列的动作实例ID列表

        该方法实现事件收敛队列推送的核心流程：
        1. 异常情况快速失败处理（无告警/被屏蔽/需降噪）
        2. 父任务驱动的子任务创建机制
        3. 降噪过滤处理
        4. 将actions推送至收敛队列
        """

        # 处理无告警场景的快速失败逻辑
        if not alerts:
            logger.info(
                "[create actions]skip to create sub action for generate_uuid(%s) because of no alert",
                generate_uuid,
            )
            return []

        # 处理告警屏蔽和降噪需求的场景
        if is_shielded or need_noise_reduce:
            logger.info(
                "[create actions]alert(%s) is shielded(%s) or need_noise_reduce(%s), "
                "skip to create sub action for generate_uuid(%s)",
                alerts[0].id,
                is_shielded,
                need_noise_reduce,
                generate_uuid,
            )
        else:
            # 父任务驱动的子任务创建流程
            for action_instance in ActionInstance.objects.filter(generate_uuid=generate_uuid, is_parent_action=True):
                # 有父任务的事件，先需要创建对应的子任务
                sub_actions = action_instance.create_sub_actions()
                logger.info(
                    "[create actions]create sub notice actions %s for parent action(%s), exclude_notice_ways(%s)",
                    len(sub_actions),
                    action_instance.id,
                    "|".join(action_instance.inputs.get("exlude_notice_ways") or []),
                )

        # 构建待推送的动作实例查询集
        action_instances = ActionInstance.objects.filter(generate_uuid=generate_uuid)
        if need_noise_reduce:
            action_instances = action_instances.filter(is_parent_action=False)
        action_instances = list(action_instances)

        # 将actions推送至收敛队列
        cls.push_actions_to_converge_queue(action_instances, {generate_uuid: alerts}, notice_config)
        return [action.id for action in action_instances]

    @classmethod
    def push_actions_to_converge_queue(
        cls,
        action_instances: list[ActionInstance],
        action_alert_relations: dict[str, AlertDocument],
        notice_config=None,
    ):
        """
        推送告警至收敛汇总队列并根据配置执行收敛策略

        参数:
            action_instances: 可迭代的动作实例集合，包含告警处理策略信息
            action_alert_relations: 字典结构，键为动作实例UUID，值为对应的告警对象列表
            notice_config: 可选的通知策略配置，默认为None

        返回值:
            无显式返回值，通过异步任务推送结果到消息队列

        处理流程：
        1. 遍历所有动作实例进行收敛配置解析
            - 动作类型是语音通知则跳过收敛流程，直接推送到执行队列
            -非语音通知则计算,用于维度维度匹配的key-value,并存到缓存中
            -执行收敛逻辑（异步）
        """

        for action_instance in action_instances:
            converge_config = None
            alerts = action_alert_relations[action_instance.generate_uuid]

            # 处理非语音通知的收敛配置解析
            if action_instance.inputs.get("notice_way") != NoticeWay.VOICE:
                # 语音通知直接跳过收敛流程
                # 从策略配置中匹配防御规则
                # TODO 处理无策略配置时的告警推送逻辑
                strategy = action_instance.strategy
                if strategy:
                    for action in strategy.get("actions", []) + [strategy.get("notice")]:
                        if action and action["id"] == action_instance.strategy_relation_id:
                            converge_config = action["options"].get("converge_config")

                # 当动作策略未配置收敛时，尝试使用默认通知配置
                if (
                    not converge_config
                    and action_instance.action_plugin.get("plugin_type") == ActionPluginType.NOTICE
                    and notice_config
                ):
                    converge_config = notice_config.get("options", {}).get("converge_config")

            # 无收敛配置时直接推送到执行队列
            if not converge_config:
                cls.push_action_to_execute_queue(action_instance, alerts)
                continue

            # 收敛维度计算与异步任务提交
            # 1. 使用DimensionCalculator计算收敛维度
            # 2. 通过celery异步执行收敛任务
            # 3. 记录日志包含关键调试信息
            converge_info = DimensionCalculator(
                action_instance, converge_config=converge_config, alerts=alerts
            ).calc_dimension()
            task_id = run_converge.apply_async(
                args=(
                    converge_config,
                    action_instance.id,
                    ConvergeType.ACTION,
                    converge_info["converge_context"],
                    [alert.to_dict() for alert in alerts],
                ),
                countdown=3,
            )
            logger.info(
                "[push_actions_to_converge_queue] push action(%s) to converge queue, converge_config %s,  task id %s",
                action_instance.id,
                converge_config,
                task_id,
            )

    @classmethod
    def push_action_to_execute_queue(
        cls, action_instance, alerts=None, countdown=0, callback_func="execute", kwargs=None
    ):
        """
        直接推送告警到执行队列（支持多种动作类型异步执行）

        参数:
            cls: 类方法装饰器参数
            action_instance: 动作实例对象，包含动作ID和插件类型信息
            alerts: 告警快照数据（可选），用于动作执行时的上下文
            countdown: 延迟执行时间（秒），控制任务调度延迟
            callback_func: 回调函数名称，默认为"execute"
            kwargs: 扩展参数字典（可选），传递额外执行参数

        返回值:
            None（通过异步任务执行，不直接返回结果）

        该方法实现告警动作的异步调度流程：
        1. 构建动作执行上下文信息
        2. 根据插件类型路由到不同执行通道
        3. 异步任务持久化到消息队列
        4. 记录调度日志用于后续追踪
        """
        from alarm_backends.service.fta_action.tasks import dispatch_action_task

        # 构建基础动作信息字典
        action_info = {"id": action_instance.id, "function": callback_func, "alerts": alerts}
        if kwargs:
            # 合并扩展参数到动作信息
            action_info.update({"kwargs": kwargs})

        # 获取动作插件类型
        plugin_type = action_instance.action_plugin["plugin_type"]
        task_id = dispatch_action_task(plugin_type, action_info, countdown=countdown)
        logger.info(
            "[create actions]push queue(execute): action(%s) (%s), alerts(%s), task_id(%s)",
            action_instance.id,
            plugin_type,
            action_instance.alerts,
            task_id,
        )


def to_document(action_instance: ActionInstance, current_time, alerts=None):
    """
    转存ES格式
    """
    create_timestamp = int(action_instance.create_time.timestamp())
    last_update_time = action_instance.end_time or current_time

    last_update_timestamp = int(last_update_time.timestamp())

    action_status = (
        action_instance.status if action_instance.status in ActionStatus.END_STATUS else ActionStatus.RUNNING
    )
    notice_way = action_instance.inputs.get("notice_way")
    notice_way = ",".join(notice_way) if isinstance(notice_way, list) else notice_way
    notice_way_display = get_notice_display_mapping(notice_way)
    notice_receiver = action_instance.inputs.get("notice_receiver") or []
    operator = notice_receiver if isinstance(notice_receiver, list) else [notice_receiver]
    status_display = ACTION_DISPLAY_STATUS_DICT.get(action_status)
    if action_status == ActionStatus.FAILURE:
        status_display = _("{}, 失败原因：{}").format(status_display, action_instance.ex_data.get("message", "--"))

    converge_info = getattr(action_instance, "converge_info", {})
    action_info = dict(
        bk_tenant_id=bk_biz_id_to_bk_tenant_id(action_instance.bk_biz_id),
        id=f"{create_timestamp}{action_instance.id}",
        raw_id=action_instance.id,
        create_time=create_timestamp,
        update_time=int(action_instance.update_time.timestamp()),
        signal=action_instance.signal,
        strategy_id=action_instance.strategy_id,
        alert_level=int(action_instance.alert_level),
        alert_id=list(set(action_instance.alerts)),
        # 针对非结束状态的中间状态统一归为执行中
        status=action_status,
        ex_data=action_instance.ex_data,
        content=action_instance.get_content(
            **{
                "notice_way_display": notice_way_display,
                "status_display": status_display,
                "action_name": action_instance.action_config.get("name", ""),
            }
        ),
        bk_biz_id=action_instance.bk_biz_id,
        action_config=action_instance.action_config,
        action_config_id=action_instance.action_config_id,
        action_name=action_instance.action_config.get("name", ""),
        action_plugin=action_instance.action_plugin,
        action_plugin_type=action_instance.action_plugin.get("plugin_key", ""),
        outputs=action_instance.outputs,
        inputs=action_instance.inputs,
        operator=operator or action_instance.assignee,
        duration=max(last_update_timestamp - create_timestamp, 0),
        end_time=int(action_instance.end_time.timestamp()) if action_instance.end_time else None,
        is_parent_action=action_instance.is_parent_action,
        parent_action_id=action_instance.parent_action_id,
        op_type=ActionInstanceDocument.OpType.ACTION,
        execute_times=action_instance.execute_times,
        failure_type=action_instance.failure_type,
        converge_id=converge_info.get("converge_id") or action_instance.inputs.get("converge_id", 0),
        is_converge_primary=converge_info.get("is_primary", False),
    )
    try:
        target_info = get_target_info_from_ctx(action_instance, alerts)
    except BaseException as error:
        target_info = action_instance.outputs.get("target_info", {})
        logger.debug("get_target_info_from_ctx failed %s action_id %s", error, action_instance.id)

    if action_info["action_plugin_type"] == ActionPluginType.NOTICE:
        target_info["operate_target_string"] = notice_way_display
    action_info.update(target_info)
    converge_info = getattr(action_instance, "converge_info", {})
    action_info.update(converge_info)
    return ActionInstanceDocument(**action_info)


def get_target_info_from_ctx(action_instance: ActionInstance, alerts: list[AlertDocument]):
    """获取目标信息"""
    if action_instance.outputs.get("target_info"):
        return action_instance.outputs["target_info"]

    action_ctx = ActionContext(action_instance, alerts=alerts, use_alert_snap=True)
    target = action_ctx.target
    target_info = {
        "bk_biz_name": target.business.bk_biz_name,
        "bk_target_display": action_ctx.alarm.target_display,
        "dimensions": [d.to_dict() for d in action_ctx.alarm.new_dimensions.values()],
        "strategy_name": action_instance.strategy.get("name") or "--",
        "operate_target_string": action_ctx.action_instance.operate_target_string,
    }
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
    logger.debug("get_target_info_from_ctx, target_info %s, action_id %s", target_info, action_instance.id)
    return target_info


def need_poll(action_instance: ActionInstance):
    """
    查询当前策略当前维度的检测结果缓存
    :param action_instance: 事件
    :return:
    """
    if (
        len(action_instance.alerts) != 1
        or (action_instance.parent_action_id > 0)
        or action_instance.inputs.get("notice_type") == ActionNoticeType.UPGRADE
    ):
        # 只有单告警动作才会存在周期通知
        # 子任务也不需要创建周期通知
        # 升级的通知也不会周期通知
        return False

    try:
        execute_config = action_instance.action_config["execute_config"]["template_detail"]
    except BaseException as error:
        logger.exception("get action config error : %s", str(error))
        return False

    if execute_config.get("need_poll", False) is False and action_instance.is_parent_action is False:
        # 非通知类的没有设置轮询，直接返回False
        return False

    detect_level = ALERT_DETECT_RESULT.client.get(ALERT_DETECT_RESULT.get_key(alert_id=action_instance.alerts[0]))
    if detect_level:
        # 当状态是异常的时候，才会反复发送通知, 记录下一次执行时间，并将信息写入缓存
        return True
    logger.info(
        "action %s(%s) clear interval because detect result of strategy(%s) is False",
        action_instance.name,
        action_instance.id,
        action_instance.strategy_id,
    )
    return False


class AlertAssignee:
    """
    告警负责人
    """

    def __init__(self, alert: AlertDocument, user_groups, follow_groups=None):
        """
        :param alert: 告警
        :param user_groups:  主要负责人组
        :param follow_groups:  关注负责人组
        """
        self.alert = alert  # 初始化告警实例
        self.user_groups = user_groups  # 主要负责人组
        self.follow_groups = follow_groups or []  # 初始化关注责任人组
        # 获取该业务下告警主机的负责人或所在模块负责人
        self.biz_group_users = self.get_biz_group_users()
        # 所有组用户的默认字典，格式为{组ID: [用户ID, ...]}
        self.all_group_users = defaultdict(list)
        # 微信机器人及用户的默认字典，
        self.wxbot_mention_users = defaultdict(list)
        # 获取告警组中的值班人员，结果会根据告警ID存在self.all_group_users中
        self.get_all_group_users()

    @staticmethod
    def get_notify_item(notify_configs, bk_biz_id):
        """
        获取当前时间内的通知配置
        :param notify_configs: 通知配置列表
        :param bk_biz_id: 业务ID
        :return: 当前时间内的通知配置项
        """
        # 设置业务时区
        i18n.set_biz(bk_biz_id)
        now_time = time_tools.strftime_local(datetime.now(), _format="%H:%M")  # 获取当前本地时间
        notify_item = None  # 初始化通知配置项为空
        for config in notify_configs:  # 遍历所有通知配置
            # 通知时间段有多个，需要逐一进行遍历
            alarm_start_time, alarm_end_time = config.get("time_range", "00:00--23:59").split("--")
            alarm_start_time = alarm_start_time.strip()[:5]  # 去除开始时间的空白并截取前5个字符
            alarm_end_time = alarm_end_time.strip()[:5]  # 去除结束时间的空白并截取前5个字符

            if alarm_start_time <= alarm_end_time:  # 如果开始时间小于等于结束时间，属于同一天的情况
                if alarm_start_time <= now_time <= alarm_end_time:  # 如果当前时间在通知时间段内
                    notify_item = config  # 设置通知配置项为当前配置
                    break  # 跳出循环
            elif alarm_start_time <= now_time or now_time <= alarm_end_time:  # 如果开始时间大于结束时间，属于跨天的情况
                notify_item = config  # 设置通知配置项为当前配置
                break  # 跳出循环
        if notify_item:  # 如果找到了通知配置项
            for notify_config in notify_item["notify_config"]:  # 遍历通知配置项中的每个配置
                # 转换一下数据格式为最新支持的数据类型
                UserGroup.translate_notice_ways(notify_config)
        return notify_item  # 返回找到的通知配置项

    def get_group_notify_configs(self, notice_type, user_type) -> dict:
        """
        获取通知组对应的通知方式配置信息

        参数:
            notice_type (str): 通知类型标识符
                - "alert_notice": 告警通知配置
                - "action_notice": 执行通知配置
            user_type (UserGroupType): 用户组类型枚举值
                用于区分主用户组(MAIN)和关注组(FOLLOW)

        返回值:
            defaultdict(dict): 用户组通知配置字典，结构示例：
                {
                    group_id: {
                        "notice_way": [...],  # 通知方式列表
                        "mention_users": [...]  # 提及用户列表
                    }
                }

        执行流程说明:
        1. 根据用户类型选择主用户组或关注组
        2. 查询数据库获取用户组对象集合
        3. 遍历用户组构建通知配置字典：
           - 提取指定通知类型配置项
           - 获取组内提及用户列表
        """
        group_notify_items = defaultdict(dict)
        user_groups = self.user_groups if user_type == UserGroupType.MAIN else self.follow_groups

        # 查询用户组对象并构建通知配置
        for user_group in UserGroup.objects.filter(id__in=user_groups):
            group_notify_items[user_group.id] = {
                "notice_way": self.get_notify_item(getattr(user_group, notice_type, []), self.alert.event.bk_biz_id),
                "mention_users": self.get_group_mention_users(user_group),
            }

        return group_notify_items

    def get_all_group_users(self):
        """
        获取所有的用户组信息
        """
        # 统一获取信息，可以合并处理
        user_groups = list(set(self.user_groups + self.follow_groups))

        if not user_groups:
            # 如果告警组不存在，忽略
            return
        # 获取需要轮值的人员,人员信息会根据告警组ID存放在self.all_group_users中
        self.get_group_users_with_duty(user_groups)
        # 获取不需要轮值的人员
        self.get_group_users_without_duty(user_groups)

    def get_group_users_without_duty(self, user_groups):
        """
        获取不带轮值功能的用户组中的所有用户。

        本函数通过用户组ID过滤出非轮值用户组，递归解析用户组成员关系，
        构建完整的用户列表集合。包含直接用户和嵌套用户组的展开用户。

        参数:
            user_groups (List[int]): 用户组ID列表，用于限定查询范围

        返回:
            Dict[int, List[str]]: 用户组ID到用户名列表的映射字典
                key: 用户组ID(int)
                value: 用户名列表(str)

        执行流程:
        1. 过滤出need_duty=False的用户组
        2. 按ID排序遍历职责安排记录
        3. 处理两种用户类型：
           - 用户组类型：递归展开获取所有成员
           - 直接用户类型：添加到结果集
        4. 维护去重后的用户名列表
        """
        # 筛选出不需要轮值的用户组
        # 使用values_list优化查询，仅获取ID字段
        no_duty_groups = list(
            UserGroup.objects.filter(id__in=user_groups, need_duty=False).values_list("id", flat=True)
        )

        # 遍历职责安排记录
        # 按ID排序确保处理顺序一致性
        for duty in DutyArrange.objects.filter(user_group_id__in=no_duty_groups).order_by("id"):
            # 获取当前用户组的用户容器
            group_users: list = self.all_group_users[duty.user_group_id]

            # 非轮值组且已有数据时跳过后续处理
            if duty.user_group_id in no_duty_groups and group_users:
                continue

            # 解析职责中的用户配置
            for user in duty.users:
                # 用户组类型处理分支
                # 处理嵌套用户组的递归展开
                if user["type"] == "group":
                    # 获取业务用户组成员并去重添加
                    for username in self.biz_group_users.get(user["id"]) or []:
                        if username not in group_users:
                            group_users.append(username)

                # 直接用户类型处理分支
                elif user["type"] == "user" and user["id"] not in group_users:
                    # 添加独立用户到结果集
                    group_users.append(user["id"])

    def get_group_mention_users(self, user_group: UserGroup):
        """
        获取用户组对应的提醒人员列表和chat_id

        参数:
            user_group (UserGroup): 用户组对象，包含以下关键属性：
                - mention_type (int): 提及类型标识（0表示默认提及）
                - mention_list (List[Dict]): 提及对象列表，格式为[{"type": "group/user", "id": "唯一标识"}]
                - channels (List[str]): 通知渠道列表（包含WX_BOT等渠道标识）

        返回值:
            List[str]: 提醒用户列表，包含去重的用户名字符串

        执行流程说明：
        1. 默认提及处理：当提及类型为0且提及列表为空时，设置默认提及所有用户
           - 特殊处理企业微信机器人渠道，若存在其他渠道且不含机器人则清空提及列表
        2. 提及对象解析：
           - 组类型处理：支持"all"全组标识和具体业务组ID
           - 个人类型处理：直接添加指定用户ID
           - 自动去重机制：确保用户名在列表中唯一存在
        """
        mention_users = []  # 初始化提醒用户列表
        mention_list = user_group.mention_list  # 获取用户组的提及列表
        # 如果提及类型为0且提及列表为空，则设置提及列表为包含所有用户的默认值
        if user_group.mention_type == 0 and not user_group.mention_list:
            mention_list = [{"type": "group", "id": "all"}]
            # 如果已经设置了channels并且没有企业微信机器人，直接设置为空
            if user_group.channels and NoticeChannel.WX_BOT not in user_group.channels:
                mention_list = []

        # 提及对象解析与用户收集
        for user in mention_list:
            if user["type"] == "group":
                if user["id"] == "all":
                    # 处理全组提及：从全组用户映射中获取对应用户列表
                    mention_users.extend(self.all_group_users.get(user_group.id, []))
                    continue

                # 处理业务组提及：遍历指定业务组用户并去重添加
                for username in self.biz_group_users.get(user["id"]) or []:
                    if username not in mention_users:
                        mention_users.append(username)
            elif user["type"] == "user":
                # 处理个人提及：直接添加指定用户（确保唯一性）
                if user["id"] not in mention_users:
                    mention_users.append(user["id"])

        return mention_users  # 返回最终去重后的提醒用户列表

    def get_group_users_with_duty(self, user_groups):
        """
        获取需要轮值的用户及其值班计划信息

        参数:
            user_groups: 可迭代对象，包含待查询的用户组ID列表

        返回值:
            None: 当user_groups为空时直接返回
            通过self.get_group_duty_users处理用户数据，实际返回值由该方法决定

        执行流程:
        1. 输入校验：若无用户组则终止处理
        2. 查询需要轮值的用户组基本信息（时区、ID、值班规则）
        3. 获取当前时间，筛选有效值班计划（按规则分组存储）
        4. 为每个有有效值班计划的用户组获取具体值班人员
        """
        if not user_groups:  # 如果没有用户组，直接返回
            return

        # 查询需要轮值的用户组基本信息
        duty_groups = UserGroup.objects.filter(id__in=user_groups, need_duty=True).only("timezone", "id", "duty_rules")

        # 初始化值班计划字典：{用户组ID: {规则ID: [值班计划列表]}}
        group_duty_plans = defaultdict(dict)

        # 处理有效值班计划并组织数据结构
        for group in duty_groups:
            now = time_tools.datetime2str(datetime.now(tz=pytz.timezone(group.timezone)))
            # 筛选当前时间范围内的有效值班计划并按顺序排序
            # 一个告警组中可以配置多个轮值组，轮值组可以配置多个轮值规则
            valid_plans = DutyPlan.objects.filter(
                user_group_id=group.id, is_effective=1, start_time__lte=now, finished_time__gte=now
            ).order_by("order")

            # 按值班规则ID分组存储计划
            for duty_plan in valid_plans:
                rule_id = duty_plan.duty_rule_id
                group_duty_plans[group.id].setdefault(rule_id, []).append(duty_plan)

        # 处理用户组值班人员信息
        for group in duty_groups:
            # 跳过无有效值班计划的用户组
            if group.id not in group_duty_plans:
                continue

            # 获取当前用户组的值班人员信息
            self.get_group_duty_users(group, group_duty_plans[group.id])

    def get_group_duty_users(self, group: UserGroup, group_duty_plans: dict[int, list[DutyPlan]]):
        """
        获取当前用户组的值班用户列表并更新组内用户缓存

        参数:
            group: 用户组对象，包含duty_rules(值班规则ID列表)和timezone(时区信息)
            group_duty_plans: 组值班计划字典，键为规则ID，值为对应的值班计划列表

        返回值:
            None: 无显式返回值，通过日志记录匹配结果并更新self.all_group_users

        执行流程:
        1. 遍历用户组关联的所有值班规则
        2. 筛选存在有效值班计划的规则
        3. 基于当前时间判断计划有效性
        4. 处理用户组嵌套关系，合并用户列表
        5. 记录匹配成功的规则信息
        """
        # 遍历用户组的值班规则
        for rule_id in group.duty_rules:
            is_rule_matched = False  # 标记当前规则是否匹配成功

            # 检查规则ID是否存在于值班计划中
            if rule_id not in group_duty_plans:
                continue

            # 获取带时区信息的当前时间
            alert_time = datetime.now(tz=pytz.timezone(group.timezone))

            # 处理当前规则下的所有值班计划
            for duty_plan in group_duty_plans[rule_id]:
                # 跳过未生效的值班计划
                if not duty_plan.is_active_plan(data_time=time_tools.datetime2str(alert_time)):
                    continue

                # 标记规则匹配成功并获取用户组
                is_rule_matched = True
                group_users: list[str] = self.all_group_users[duty_plan.user_group_id]

                # 处理值班计划中的用户列表
                for user in duty_plan.users:
                    # 处理用户组类型用户
                    if user["type"] == "group":
                        for username in self.biz_group_users.get(user["id"]) or []:
                            if username not in group_users:
                                group_users.append(username)

                    # 处理个人用户类型
                    elif user["type"] == "user" and user["id"] not in group_users:
                        group_users.append(user["id"])
            if is_rule_matched and group.duty_notice.get("hit_first_duty", True):
                # 适配到了对应的轮值规则，中止
                logger.info("user group (%s) matched duty rule(%s) for alert(%s)", group.id, rule_id, self.alert.id)

    def get_assignee_by_user_groups(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        根据配置的用户组获取对应的处理人员
        """
        if by_group:
            return self.all_group_users
        all_assignee = []
        user_groups = self.user_groups if user_type == UserGroupType.MAIN else self.follow_groups
        for group_id in user_groups:
            for user in self.all_group_users[group_id]:
                if user not in all_assignee:
                    all_assignee.append(user)
        return all_assignee

    def get_notice_receivers(
        self,
        notice_type=NoticeType.ALERT_NOTICE,
        notice_phase=None,
        notify_configs=None,
        user_type=UserGroupType.MAIN,
    ):
        """
        根据用户组和告警获取通知方式和对应的处理人元信息

        参数:
            notice_type: 通知类型枚举值，默认为告警通知类型
                        可选值: NoticeType.ALERT_NOTICE(告警通知), NoticeType.ACTION_NOTICE(执行通知)
            notice_phase: 通知阶段配置，用于匹配通知规则的阶段条件
                         当notice_type为ACTION_NOTICE时使用phase字段匹配
            notify_configs: 已有的通知配置字典，用于累积通知接收人信息
                           默认值为None时初始化为空的defaultdict(list)
            user_type: 用户组类型枚举值，默认为主通知组类型
                      可选值: UserGroupType.MAIN(主组), UserGroupType.BACKUP(备用组)等

        返回示例:
          {
                # 微信通知接收人列表
                "weixin": ["admin", "user1", "user2"],

                # 邮件通知接收人列表
                "email": ["admin@example.com", "user1@example.com"],

                # 短信通知接收人列表
                "sms": ["admin", "user3"],

                # 电话通知接收人列表（按用户组分组）
                "voice": [
                    ["admin", "user1"],      # 第一个用户组
                    ["user2", "user3"]       # 第二个用户组
                ],

                # 蓝鲸信息流子渠道：企业微信机器人
                # 这里的 key 是 "bkchat|wxwork-bot"，value 是对应子渠道的接收人 id
                "bkchat|wxwork-bot": ["wxbot_user_1", "wxbot_user_2"],

                # 蓝鲸信息流子渠道：邮件（通过 BKChat 下发邮件）
                "bkchat|mail": ["notify@example.com"],

                # 如果有配置 @ 用户
                "wxbot_mention_users": [
                    {
                        # 例如：发给 wxbot_user_1 时，要在消息里@ admin 和 user1
                        "wxbot_user_1": ["admin", "user1"],
                    }
                ],
            }


        执行流程:
        1. 从用户组获取基础通知配置（通过get_group_notify_configs方法）
        2. 处理电话通知的特殊逻辑（用户列表去重存储）
        3. 解析企业微信通知配置（包含@用户映射处理）
        4. 处理默认通知逻辑（无指定接收人时使用用户组成员）
        5. 清理空的wxbot_mention_users字段
        """

        # ========== 步骤1: 获取用户组通知配置 ==========
        # 根据通知类型和用户组类型，从用户组配置中获取对应时间段的通知渠道信息
        # 返回格式: {group_id: {"notice_way": {...}, "mention_users": [...]}}
        group_notify_items = self.get_group_notify_configs(notice_type, user_type)

        # ========== 步骤2: 初始化通知配置字典 ==========
        # 如果没有传入已有配置，则创建一个新的defaultdict，键为通知方式，值为接收人列表
        notify_configs = notify_configs or defaultdict(list)

        # 确定当前通知阶段：如果未指定则使用告警级别作为默认值
        # 例如：告警级别可能是 "1"(致命), "2"(预警), "3"(提醒)
        notice_phase = notice_phase or self.alert.severity

        # 根据通知类型确定阶段匹配的字段名
        # 告警通知使用"level"字段，执行通知使用"phase"字段
        notice_item_phase_key = "level" if notice_type == NoticeType.ALERT_NOTICE else "phase"

        # 初始化企业微信机器人@用户列表（用于存储需要@的用户映射关系）
        notify_configs["wxbot_mention_users"] = notify_configs.get("wxbot_mention_users", [])

        # ========== 步骤3: 遍历用户组通知配置，构建完整的通知接收人列表 ==========
        for group_id, notify_info in group_notify_items.items():
            # 提取当前用户组的通知方式配置和需要@的用户列表
            notify_item = notify_info["notice_way"]
            mention_users = notify_info["mention_users"]

            # 如果该用户组没有配置通知方式，跳过处理
            if not notify_item:
                continue

            # 获取当前用户组的所有成员列表
            # 格式: ["user1", "user2", "user3"]
            group_users = self.all_group_users.get(group_id, [])

            # 初始化当前阶段匹配的通知方式列表
            notice_ways = []

            # ========== 步骤3.1: 匹配当前阶段的通知方式配置 ==========
            # 遍历通知配置项，找到与当前阶段（告警级别或执行阶段）匹配的配置
            # notify_config示例: [{"level": "1", "notice_ways": [{"name": "weixin", "receivers": [...]}]}]
            for notify_config_item in notify_item["notify_config"]:
                if notice_phase == notify_config_item[notice_item_phase_key]:
                    # 找到匹配的阶段配置，提取通知方式列表
                    notice_ways = notify_config_item.get("notice_ways")

            # ========== 步骤3.2: 处理每种通知方式的接收人 ==========
            for notice_way in notice_ways:
                # 获取通知方式类型，如: "weixin"(微信), "email"(邮件), "voice"(电话)等
                notice_way_type = notice_way["name"]

                # ========== 特殊处理1: 电话通知 ==========
                # 电话通知需要按用户组整体存储，避免重复拨打
                # 存储格式: {"voice": [["user1", "user2"], ["user3", "user4"]]}
                if notice_way_type == NoticeWay.VOICE:
                    # 检查当前用户组是否已添加，避免重复
                    if group_users not in notify_configs[notice_way_type]:
                        notify_configs[notice_way_type].append(group_users)
                    continue

                # ========== 特殊处理2: 有明确指定接收人的通知方式 ==========
                if notice_way.get("receivers"):
                    # ========== 特殊处理2.1: BKChat渠道（蓝鲸聊天工具） ==========
                    # BKChat支持多种子渠道，格式为 "子渠道类型|接收人ID"
                    # 例如: "wxwork|user123" 表示通过企业微信发送给user123
                    if notice_way_type == NoticeWay.BK_CHAT:
                        for receiver in notice_way["receivers"]:
                            try:
                                # 尝试解析子渠道类型和接收人ID
                                real_notice_way, receiver_id = receiver.split("|")
                            except ValueError:
                                # 如果解析失败（没有"|"分隔符），直接作为普通接收人处理
                                notify_configs[notice_way_type].append(receiver)
                                continue
                            # 按"bkchat|子渠道"的格式存储接收人
                            # 例如: {"bkchat|wxwork": ["user123", "user456"]}
                            notify_configs[f"{notice_way_type}|{real_notice_way}"].append(receiver_id)
                    else:
                        # ========== 特殊处理2.2: 普通通知方式（微信、邮件等） ==========
                        # 过滤掉已存在的接收人，避免重复通知
                        receivers = [
                            receiver
                            for receiver in notice_way["receivers"]
                            if receiver not in notify_configs[notice_way_type]
                        ]

                        # 将新的接收人添加到通知配置中
                        if receivers:
                            notify_configs[notice_way_type].extend(receivers)

                        # ========== 处理企业微信机器人@用户功能 ==========
                        # 如果配置了需要@的用户，记录每个接收人对应需要@的用户列表
                        # 用于在企业微信群消息中@特定用户
                        if mention_users:
                            for receiver in notice_way["receivers"]:
                                # self.wxbot_mention_users格式: {"receiver1": ["mention_user1", "mention_user2"]}
                                self.wxbot_mention_users[receiver].extend(mention_users)
                    continue

                # ========== 默认处理: 无指定接收人时使用用户组全体成员 ==========
                # 当通知方式没有指定具体接收人时，默认通知该用户组的所有成员
                for group_user in group_users:
                    # 去重检查：避免同一用户被重复添加
                    if group_user not in notify_configs[notice_way_type]:
                        notify_configs[notice_way_type].append(group_user)

        # ========== 步骤4: 处理企业微信机器人@用户映射关系 ==========
        # 如果存在需要@的用户映射，将其添加到通知配置中
        # 格式: {"wxbot_mention_users": [{"receiver1": ["user1", "user2"]}]}
        if self.wxbot_mention_users:
            notify_configs["wxbot_mention_users"].append(self.wxbot_mention_users)

        # ========== 步骤5: 清理空的@用户字段 ==========
        # 如果最终没有需要@的用户，移除该字段以保持数据整洁
        if not notify_configs["wxbot_mention_users"]:
            notify_configs.pop("wxbot_mention_users")

        # 返回完整的通知配置字典
        return notify_configs

    def add_appointee_to_notify_group(self, notify_configs):
        """
        添加分派负责人至通知组
        :param notify_configs: 通知内容
        :return:
        """
        appointee = list(self.alert.appointee)
        if not appointee:
            return notify_configs

        for notice_way, users in notify_configs.items():
            if notice_way in [NoticeWay.WX_BOT, "wxbot_mention_users"]:
                continue
            if notice_way == NoticeWay.VOICE:
                # 如果是语音通知，判断整个列表是否存在
                if appointee not in users:
                    users.append(appointee)
                continue
            # 其他情况下，直接添加个人用户至列表中
            for user in appointee:
                if user not in users:
                    users.append(user)
        return notify_configs

    def get_biz_group_users(self):
        """
        通过业务信息获取对应的角色人员信息

        参数:
            无

        返回值:
            dict: 包含业务对应的角色人员信息的字典，包含以下键值对：
                - 原始业务角色信息键值对（来自get_business_roles）
                - operator: 主机负责人列表（可能为空）
                - bk_bak_operator: 主机备份负责人列表（可能为空）

        执行流程:
            1. 获取基础业务角色信息
            2. 确保必要角色键存在（operator/bk_bak_operator）
            3. 根据监控目标类型判断是否需要补充主机负责人信息
            4. 异常安全地获取并更新主机负责人信息
        """
        # 获取基础业务角色信息
        group_users = get_business_roles(self.alert.event.bk_biz_id)

        # 确保必要角色键存在，避免后续访问时KeyError
        # 添加空列表作为默认值，保证字典结构完整性
        group_users.update(
            {
                "operator": [],
                "bk_bak_operator": [],
            }
        )

        try:
            # 检查监控目标类型
            # 如果没有监控对象，则不需要获取负责人信息，直接返回当前的group_users
            if not self.alert.event.target_type:
                return group_users

            host = HostManager.get_by_id(
                bk_tenant_id=str(self.alert.bk_tenant_id), bk_host_id=getattr(self.alert.event, "bk_host_id", "")
            )
            for operator_attr in ["operator", "bk_bak_operator"]:
                group_users[operator_attr] = self.get_host_operator(host, operator_attr)
        except AttributeError:
            # 容错处理：当主机信息或负责人字段不存在时
            # 忽略AttributeError异常，保持原有空列表结构
            pass

        # 返回最终组装完成的业务角色用户信息
        return group_users

    @classmethod
    def get_host_operator(cls, host: Host | None, operator_attr="operator"):
        """
        获取主机负责人，如果没有则尝试获取第一个模块负责人
        :param host: 主机
        :return: list
        """
        if not host:
            return []
        return getattr(host, operator_attr, []) or cls.get_host_module_operator(host)

    @classmethod
    def get_host_module_operator(cls, host: Host, operator_attr="operator"):
        """
        获取主机第一个模块的负责人
        :param operator_attr: 模块负责人类型
                operator: 主机负责人
                bk_bak_operator： 主机备份人
        :param host: 主机
        :return: 人员列表
        """
        bk_biz_id: int = host.bk_biz_id
        bk_tenant_id = bk_biz_id_to_bk_tenant_id(bk_biz_id)

        modules = ModuleManager.mget(bk_tenant_id=bk_tenant_id, bk_module_ids=host.bk_module_ids)
        for module in modules.values():
            return getattr(module, operator_attr, [])
        return []


class DutyCalendar:
    @classmethod
    def get_end_time(cls, end_date, handover_time):
        try:
            [hour, minute] = handover_time.split(":")
            hour = int(hour)
            minute = int(minute)
        except BaseException as error:
            logger.exception("[get_handover_time] split handover_time(%s) error, %s", handover_time, str(error))
            hour, minute = 0, 0
        end_time = datetime(year=end_date.year, month=end_date.month, day=end_date.day, hour=hour, minute=minute)
        return datetime.fromtimestamp(end_time.timestamp(), tz=timezone.utc)

    @staticmethod
    def get_daily_rotation_end_time(begin_time: datetime, handoff_time):
        begin_time = time_tools.localtime(begin_time)
        handover_time = handoff_time["time"]
        if handover_time > time_tools.strftime_local(begin_time, "%H:%M"):
            end_date = begin_time.date()
        else:
            end_date = (begin_time + timedelta(days=1)).date()
        return DutyCalendar.get_end_time(end_date, handover_time)

    @staticmethod
    def get_weekly_rotation_end_time(begin_time: datetime, handoff_time):
        begin_time = time_tools.localtime(begin_time)
        begin_week_day = begin_time.isoweekday()
        handover_date = handoff_time["date"]
        handover_time = handoff_time["time"]
        if handover_date > begin_week_day:
            end_date = (begin_time + timedelta(days=handover_date - begin_week_day)).date()
        elif handover_date == begin_week_day and handover_time > time_tools.strftime_local(begin_time, "%H:%M"):
            end_date = begin_time.date()
        else:
            end_date = (begin_time + timedelta(days=handover_date + 7 - begin_week_day)).date()
        return DutyCalendar.get_end_time(end_date, handover_time)

    @staticmethod
    def get_monthly_rotation_end_time(begin_time: datetime, handoff_time):
        begin_time = time_tools.localtime(begin_time)
        begin_month_day = begin_time.day
        handover_date = handoff_time["date"]
        handover_time = handoff_time["time"]
        _, max_current_month_day = calendar.monthrange(begin_time.year, begin_time.month)

        if max_current_month_day >= handover_date > begin_month_day:
            handover_date = min(handover_date, max_current_month_day)
            end_date = (begin_time + timedelta(days=(handover_date - begin_month_day))).date()
        elif handover_date == begin_month_day and handover_time > time_tools.strftime_local(begin_time, "%H:%M"):
            end_date = begin_time.date()
        else:
            next_month = begin_time.date() + relativedelta(months=1)
            _, max_month_day = calendar.monthrange(next_month.year, next_month.month)
            handover_date = min(handover_date, max_month_day)
            end_date = datetime(next_month.year, next_month.month, handover_date)
        return DutyCalendar.get_end_time(end_date, handover_time)
