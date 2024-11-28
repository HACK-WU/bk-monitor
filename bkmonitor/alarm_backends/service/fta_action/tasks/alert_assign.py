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
from collections import defaultdict
from typing import List

from alarm_backends.core.cache.assign import AssignCacheManager
from alarm_backends.core.context import ActionContext
from alarm_backends.service.fta_action import AlertAssignee
from bkmonitor.action.alert_assign import (
    AlertAssignMatchManager,
    AssignRuleMatch,
    UpgradeRuleMatch,
)
from bkmonitor.documents import AlertDocument
from constants.action import ActionNoticeType, AssignMode, UserGroupType

logger = logging.getLogger("fta_action.run")


class BackendAssignMatchManager(AlertAssignMatchManager):
    """
    后台告警分派管理
    """

    def __init__(
            self,
            alert: AlertDocument,
            notice_users=None,
            group_rules: list = None,
            assign_mode=None,
            notice_type=None,
            cmdb_attrs=None,
    ):
        """
        :param alert: 告警
        :param notice_users: 通知人员
        :param group_rules: 指定的分派规则, 以优先级降序排列
        """
        if cmdb_attrs is None:
            action_context = ActionContext(action=None, alerts=[alert], use_alert_snap=True)
            cmdb_attrs = {
                "host": action_context.target.host,
                "sets": action_context.target.sets,
                "modules": action_context.target.modules,
            }
        super(BackendAssignMatchManager, self).__init__(
            alert, notice_users, group_rules, assign_mode, notice_type, cmdb_attrs
        )

    def get_matched_rules(self) -> List[AssignRuleMatch]:
        """
        适配分派规则, 后台通过缓存获取
        :return: 返回匹配的分派规则列表
        """
        # 初始化匹配的规则列表为空
        matched_rules = []
        # 检查是否有分派模式且包含按规则分派的情况
        if self.assign_mode is None or AssignMode.BY_RULE not in self.assign_mode:
            # 如果没有分派规则或者当前配置不需要分派的情况下，不做分派适配
            return matched_rules
        # 遍历每个优先级ID，从高到低
        for priority_id in AssignCacheManager.get_assign_priority_by_biz_id(self.bk_biz_id):
            # 获取当前优先级下的分派组
            groups = AssignCacheManager.get_assign_groups_by_priority(self.bk_biz_id, priority_id)
            # 初始化当前优先级下的分派规则列表为空
            group_rules = []
            # 遍历每个分派组
            for group_id in groups:
                # 将当前分派组的规则添加到分派规则列表中
                group_rules.extend(AssignCacheManager.get_assign_rules_by_group(self.bk_biz_id, group_id))
            # 遍历每个分派规则
            for rule in group_rules:
                # 创建分派规则匹配对象
                rule_match_obj = AssignRuleMatch(rule, self.rule_snaps.get(str(rule["id"])), self.alert)
                # 检查规则是否匹配给定的维度
                if rule_match_obj.is_matched(dimensions=self.dimensions):
                    # 如果规则匹配，则添加到匹配的规则列表中
                    matched_rules.append(rule_match_obj)
            # 如果在当前优先级下找到了匹配的规则，停止后续优先级的检查
            if matched_rules:
                break
        # 返回匹配的规则列表
        return matched_rules


class AlertAssigneeManager:
    """
    告警处理通知人管理模块
    """

    def __init__(
            self,
            alert: AlertDocument,
            notice_user_groups: List = None,
            assign_mode: AssignMode = None,
            upgrade_config=None,
            notice_type: ActionNoticeType = None,
            user_type: UserGroupType = UserGroupType.MAIN,
            new_alert=False,
    ):
        """
        1、初始化基本属性：设置告警对象、通知用户组、分派模式、通知类型、用户类型和是否为新告警。
        2、初始化升级规则匹配对象：根据传入的升级配置初始化 UpgradeRuleMatch 对象。
        3、获取通知对象：根据通知类型（升级通知或默认通知）获取相应的通知对象。
        4、初始化匹配状态：设置匹配状态和匹配的告警组ID。
        5、获取告警分派管理对象：根据分派模式获取告警分派管理对象，并完成告警分派工作
        5、获取通知负责人对象：根据分派模式获取通知负责人对象。
        
        :param alert: 告警
        :param notice_user_groups: 通知用户组(告警组)
        :param assign_mode: 分派模式
        :param upgrade_config: 通知升级规则
        :param notice_type: 通知类型
        :param user_type: 用户类型
        :param new_alert: 是否为新告警
        """
        self._is_new = new_alert  # 标记是否为新告警
        self.alert = alert  # 初始化告警对象
        # 设置默认的分派模式为仅通知，也就是默认通知,后续会根据分派模式获取到对应的通知人员
        self.assign_mode = assign_mode or [AssignMode.ONLY_NOTICE]
        self.notice_type = notice_type  # 设置通知类型
        self.upgrade_rule = UpgradeRuleMatch(upgrade_config=upgrade_config or {})  # 初始化升级规则匹配对象
        self.user_type = user_type  # 设置用户类型

        # 获取到告警升级或者默认通知的通知对象
        if self.notice_type == ActionNoticeType.UPGRADE:
            # 获取告警升级通知对象
            self.origin_notice_users_object: AlertAssignee = self.get_origin_supervisor_object()
        else:
            # 获取非告警升级通知对象
            self.origin_notice_users_object: AlertAssignee = self.get_origin_notice_users_object(
                notice_user_groups or [])  # 否则使用原始的通知人员对象

        self.matched_group: List[AssignRuleMatch] = None  # 匹配的告警组ID
        self.is_matched = False  # 初始化匹配状态为未匹配
        # 获取告警分派管理对象，如果是默认通知，则返回None。否则会更新matched_group的值
        self.match_manager: BackendAssignMatchManager = self.get_match_manager()
        # 获取告警分派的通知负责人对象，如果是默认通知，则返回None
        self.notice_appointees_object: AlertAssignee = self.get_notice_appointees_object()
        self._is_new = new_alert  # 再次设置是否为新告警，可能是为了确保属性的正确性

    def get_match_manager(self):
        """
        生成告警分派管理对象
        :return:
        """
        # 如果分派模式中不包含按规则分派，则不需要匹配管理器
        if AssignMode.BY_RULE not in self.assign_mode:
            self.match_manager = None
            logger.info(
                "[ignore assign match] alert(%s) assign_mode(%s)",
                self.alert.id,
                self.assign_mode,
            )
            return

        # 需要获取所有的通知人员信息，包含chatID
        manager = BackendAssignMatchManager(
            self.alert,
            self.get_origin_notice_all_receivers(),
            assign_mode=self.assign_mode,
            notice_type=self.notice_type,
        )
        manager.run_match()  # 执行匹配逻辑
        if manager.matched_rules:  # 如果有匹配的规则
            self.is_matched = True  # 更新匹配状态为已匹配
        # 获取匹配的告警组
        self.matched_group = manager.matched_group_info.get("group_id")
        logger.info(
            "[%s assign match] finished: alert(%s), strategy(%s), matched_rule(%s), "
            "assign_rule_id(%s), assign_mode(%s)",
            "alert.builder" if self._is_new else "create actions",
            self.alert.id,
            str(self.alert.strategy["id"]) if self.alert.strategy else 0,
            len(manager.matched_rules),
            self.matched_group,
            self.assign_mode,
        )
        return manager  # 返回告警分派管理对象

    def get_notify_info(self, user_type=UserGroupType.MAIN):
        """
        获取通知渠道和通知人员信息
        """
        notify_configs = defaultdict(list)  # 初始化一个默认字典，用于存储通知配置
        # 匹配成功往往意味着就是有分派负责人
        if self.is_matched:
            # 如果适配到了，直接发送给分派的负责人
            if self.notice_appointees_object:
                self.notice_appointees_object.get_notice_receivers(notify_configs=notify_configs,
                                                                   user_type=user_type)
        elif self.origin_notice_users_object:  # 如果没有匹配成功，但有默认通知人员
            # 有默认通知的话，就加上默认通知人员
            self.origin_notice_users_object.get_notice_receivers(notify_configs=notify_configs, user_type=user_type)
        return notify_configs  # 返回通知配置信息

    def get_appointee_notify_info(self, notify_configs=None):
        """
        获取告警负责人的通知信息
        """
        notify_configs = notify_configs or defaultdict(list)  # 如果未提供通知配置，则初始化一个默认字典
        if self.is_matched:  # 如果当前规则匹配成功
            # 如果适配到了，直接发送给分派的负责人
            if self.notice_appointees_object:
                self.notice_appointees_object.add_appointee_to_notify_group(notify_configs=notify_configs)
        elif self.origin_notice_users_object:  # 如果没有匹配成功，但有默认通知人员
            # 有默认通知的话，就加上默认通知人员
            self.origin_notice_users_object.add_appointee_to_notify_group(notify_configs=notify_configs)
        return notify_configs  # 返回更新后的通知配置信息

    def get_assignees(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        获取对应的通知人员 包含指派的通知人员 和 设置的通知人员
        """
        if self.is_matched:  # 如果当前已经有分派适配
            # 只返回指派的人员
            return self.get_notice_appointees(by_group, user_type)
        else:
            # 否则返回设置的通知人员
            return self.get_origin_notice_receivers(by_group, user_type)

    @property
    def itsm_actions(self):
        if self.match_manager:  # 如果存在匹配管理器
            # 返回匹配规则中的ITSM动作
            return self.match_manager.matched_rule_info["itsm_actions"]
        return {}  # 如果不存在匹配管理器，则返回空字典

    def get_appointees(self, action_id=None, user_type=UserGroupType.MAIN):
        """
        # 获取分派的负责人
        """
        if action_id and action_id in self.itsm_actions:
            # 根据对应的动作配置找到负责人
            return AlertAssignee(self.alert, self.itsm_actions[action_id]).get_assignee_by_user_groups(
                user_type=user_type
            )

        return self.get_assignees(user_type=user_type)

    def get_supervisors(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        获取当前运行的升级人员
        """
        if not self.is_matched:
            # 如果没有适配到规则，用默认通知的关注人信息
            return self.get_origin_notice_supervisors(by_group, user_type=user_type)

        if self.notice_appointees_object:
            return self.notice_appointees_object.get_assignee_by_user_groups(by_group, user_type=user_type)
        return None

    def get_notice_appointees(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        获取分派的人员信息
        """
        # 获取通知分派的人员
        if self.notice_appointees_object:
            return self.notice_appointees_object.get_assignee_by_user_groups(by_group, user_type)
        return {} if by_group else []

    def get_notice_appointees_object(self):
        """
        获取通知分派人的获取对象
        :return:
        """
        if not self.is_matched:
            # 没有适配到，直接返回
            return
        matched_info = self.match_manager.matched_rule_info
        return AlertAssignee(self.alert, matched_info["notice_appointees"], matched_info["follow_groups"])

    def get_origin_notice_receivers(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        获取默认通知的所有接受人员
        """
        # 如果原始通知用户对象不存在，则根据by_group参数返回空字典或空列表
        if self.origin_notice_users_object is None:
            return {} if by_group else []
        # 否则，调用原始通知用户对象的get_assignee_by_user_groups方法获取接受人员
        return self.origin_notice_users_object.get_assignee_by_user_groups(by_group, user_type=user_type)

    def get_origin_notice_all_receivers(self):
        """
        获取所有的原始告警的接收人员，包含机器人会话ID
        """
        # 如果原始通知用户对象不存在，则返回空字典
        if self.origin_notice_users_object is None:
            return {}
        # 否则，调用原始通知用户对象的get_notice_receivers方法获取所有接收人员
        return self.origin_notice_users_object.get_notice_receivers()

    def get_origin_supervisor_object(self):
        """
        获取原升级告警关注人员
        """
        # 如果通知类型不是UPGRADE或者分配模式中不包含ONLY_NOTICE，则返回None
        if self.notice_type != ActionNoticeType.UPGRADE or AssignMode.ONLY_NOTICE not in self.assign_mode:
            return None
        # 获取当前时间戳
        current_time = int(time.time())
        # 从告警的额外信息中获取升级通知的相关信息
        upgrade_notice = self.alert.extra_info.to_dict().get("upgrade_notice", {})
        last_group_index = upgrade_notice.get("last_group_index")
        last_upgrade_time = upgrade_notice.get("last_upgrade_time", current_time)
        # 计算距离上次升级的时间间隔
        latest_upgrade_interval = current_time - last_upgrade_time
        alert_duration = self.alert.duration or 0
        # 判断是否需要升级
        need_upgrade = self.upgrade_rule.need_upgrade(latest_upgrade_interval or alert_duration)
        if not need_upgrade:
            return None
        # 如果需要升级，获取新的用户组索引和用户组列表
        user_groups, current_group_index = self.upgrade_rule.get_upgrade_user_group(last_group_index, need_upgrade)
        # 如果当前用户组索引与上次不同，更新告警的额外信息并记录日志
        if current_group_index != last_group_index:
            logger.info(
                "[alert upgrade] alert(%s) current_group_index(%s), last_group_index(%s), last_upgrade_time(%s)",
                self.alert.id,
                current_group_index,
                last_group_index,
                last_upgrade_time,
            )
            self.alert.extra_info["upgrade_notice"] = {
                "last_group_index": current_group_index,
                "last_upgrade_time": current_time,
            }
        # 如果用户类型是FOLLOWER，则将用户组列表赋值给follow_groups，并清空user_groups
        follow_groups = []
        if self.user_type == UserGroupType.FOLLOWER:
            follow_groups = user_groups
            user_groups = []
        # 返回AlertAssignee对象
        return AlertAssignee(self.alert, user_groups=user_groups, follow_groups=follow_groups)

    def get_origin_notice_supervisors(self, by_group=False, user_type=UserGroupType.MAIN):
        """
        获取默认通知的关注人员
        """
        # 如果没有设置通知，则根据by_group参数返回空字典或空列表
        empty_supervisors = {} if by_group else []
        if not self.origin_notice_users_object:
            return empty_supervisors
        # 否则，调用原始通知用户对象的get_assignee_by_user_groups方法获取关注人员
        return self.origin_notice_users_object.get_assignee_by_user_groups(by_group, user_type=user_type)

    def get_origin_notice_users_object(self, user_groups):
        """
        获取仅通知的
        :param user_groups: 告警组
        :return:
        """
        # 如果分配模式中不包含ONLY_NOTICE，则返回None
        if AssignMode.ONLY_NOTICE not in self.assign_mode:
            return None
        # 如果用户类型是FOLLOWER(关注人)，则将用户组列表赋值给follow_groups，并清空user_groups
        follow_groups = []
        if self.user_type == UserGroupType.FOLLOWER:
            follow_groups = user_groups
            user_groups = []
        # 返回AlertAssignee对象
        return AlertAssignee(self.alert, user_groups=user_groups, follow_groups=follow_groups)
