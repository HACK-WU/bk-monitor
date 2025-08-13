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
import json
import logging
import time
from collections import defaultdict
from typing import Dict, List, Union

from django.utils.translation import gettext as _

from api.cmdb.define import Host, Module, Set
from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.utils.range import load_condition_instance
from constants.action import ActionPluginType, AssignMode, UserGroupType
from constants.alert import EVENT_SEVERITY_DICT
from drf_resource import api
from drf_resource.utils.common import count_md5

logger = logging.getLogger("fta_action.run")


class UpgradeRuleMatch:
    """
    升级适配
    """

    def __init__(self, upgrade_config):
        self.upgrade_config = upgrade_config
        self.is_upgrade = False

    @property
    def is_upgrade_enable(self):
        return self.upgrade_config.get("is_enabled", False)

    def need_upgrade(self, notice_interval, last_group_index=None):
        # 判断是否已经达到了升级的条件
        if not self.is_upgrade_enable:
            # 不需要升级的或者告警为空，直接返回False
            return False
        upgrade_interval = self.upgrade_config.get("upgrade_interval", 0) * 60
        if upgrade_interval <= notice_interval:
            # 时间间隔满足了之后, 判断是否已经全部通知完
            _, group_index = self.get_upgrade_user_group(last_group_index)
            return group_index != last_group_index
        return False

    def get_upgrade_user_group(self, last_group_index=None, need_upgrade=True):
        """
        获取时间间隔已经满足的情况下是否还有关注人未通知
        :param last_group_index: 上一次的通知记录
        :param need_upgrade: 是否满足间隔条件
        :return:
        """
        upgrade_user_groups = self.upgrade_config.get("user_groups", [])
        if last_group_index is None and need_upgrade:
            # 第一次升级，返回第一组
            self.is_upgrade = True
            return [upgrade_user_groups[0]], 0
        if need_upgrade and last_group_index + 1 < len(upgrade_user_groups):
            # 如果升级之后再次超过升级事件，且存在下一个告警组， 则直接通知下一组成员
            self.is_upgrade = True
            group_index = last_group_index + 1
            return [upgrade_user_groups[group_index]], group_index
        return [], last_group_index


class AssignRuleMatch:
    """分派规则适配"""

    def __init__(self, assign_rule: Dict, assign_rule_snap=None, alert: AlertDocument = None):
        """
        初始化分派规则适配对象

        :param assign_rule: 分派规则字典，包含规则ID和条件等信息
        :param assign_rule_snap: 分派规则的快照，默认为None
        :param alert: 告警文档对象，默认为None
        """
        self.assign_rule = assign_rule
        self.assign_rule_snap = assign_rule_snap or {}
        self.dimension_check = None
        # 解析维度条件以初始化self.dimension_check
        self.parse_dimension_conditions()
        self.alert = alert

    def parse_dimension_conditions(self):
        """
        解析配置的条件信息，将其组织成或(and)和与(or)条件组
        以便于后续的条件检查

        example:
        >> "conditions": [
                {"field": "status", "value": "active", "operator": "==", "condition": "and"},
                {"field": "type", "value": "user", "operator": "==", "condition": "and"},
                {"field": "age", "value": 18, "operator": ">=", "condition": "or"},
                {"field": "status", "value": "inactive", "operator": "==", "condition": "and"},
                {"field": "type", "value": "admin", "operator": "==", "condition": "and"}
            ]
        >> #解析后
        >> or_cond = [
            [
                {"field": "status", "value": "active", "operator": "==", "condition": "and"},
                {"field": "type", "value": "user", "operator": "==", "condition": "and"}
            ],
            [
                {"field": "age", "value": 18, "operator": ">=", "condition": "or"},
                {"field": "status", "value": "inactive", "operator": "==", "condition": "and"},
                {"field": "type", "value": "admin", "operator": "==", "condition": "and"}
            ]
        ]
        """
        or_cond = []
        and_cond = []
        # 遍历规则中的所有条件，根据条件的逻辑关系（and/or）进行分组
        for condition in self.assign_rule["conditions"]:
            if condition.get("condition") == "or" and and_cond:
                # 如果遇到'or'条件且已有'and'条件组，则将当前'and'条件组添加到'or'条件组中，并重置'and'条件组
                or_cond.append(and_cond)
                and_cond = []
            # 将条件添加到'and'条件组中
            and_cond.append(condition)
        # 如果还有剩余的'and'条件组，则将其添加到'or'条件组中
        if and_cond:
            or_cond.append(and_cond)
        # 加载条件实例，准备进行条件检查
        self.dimension_check = load_condition_instance(or_cond, False)

    def assign_group(self):
        return {"group_id": self.assign_rule["assign_group_id"]}

    @property
    def rule_id(self):
        return self.assign_rule.get("id")

    @property
    def snap_rule_id(self):
        if self.assign_rule_snap:
            return self.assign_rule_snap.get("id")

    @property
    def is_changed(self):
        # 如果是新增规则，则认为规则已发生变化。
        # 否则对当前规则和新增规则进行md5比较，如果不一致则认为规则已发生变化。
        if self.is_new:
            return True
        # 比较分派的用户组和分派条件
        new_rule_md5 = count_md5(
            {
                "user_groups": self.assign_rule["user_groups"],
                "conditions": self.assign_rule["conditions"],
            }
        )
        snap_rule_md5 = count_md5(
            {
                "user_groups": self.assign_rule_snap["user_groups"],
                "conditions": self.assign_rule_snap["conditions"],
            }
        )
        return new_rule_md5 != snap_rule_md5

    @property
    def is_new(self):
        """
        是否为新增规则。
        快照的来源是从告警中获取的，而告警中的快照是重新适配成功后存入的，
        所以如果快照id为空，说明这个告警从来没被适配过，则认为当前规则是新增规则。
        又如果快照id与当前规则ID不一致，则说明当前规则是新增规则。
        """
        if self.snap_rule_id is None:
            return True
        return self.snap_rule_id and self.rule_id and self.snap_rule_id != self.rule_id

    def is_matched(self, dimensions) -> bool:
        """
        当前规则是否适配
        :param dimensions: 告警维度信息
        :return:
        """
        # 判断告警的分派规则是否发生了变化，改变则重新适配，否则直接适配成功。
        if self.is_changed:
            # 如果为新或者发生了变化，需要重新适配
            return self.dimension_check.is_match(dimensions)
        return True

    @property
    def user_groups(self):
        if not self.notice_action:
            # 如果没有通知配置，直接返回
            return []
        return self.assign_rule.get("user_groups", [])

    @property
    def notice_action(self):
        for action in self.assign_rule["actions"]:
            if not action.get("is_enabled"):
                logger.info("assign notice(%s) is not enabled", self.rule_id)
                continue
            if action["action_type"] == ActionPluginType.NOTICE:
                # 当有通知插件，并且开启了，才进行通知
                return action
        return {}

    @property
    def itsm_action(self):
        for action in self.assign_rule["actions"]:
            if action["action_type"] == ActionPluginType.ITSM and action.get("action_id"):
                return action

    @property
    def upgrade_rule(self):
        return UpgradeRuleMatch(self.notice_action.get("upgrade_config", {}))

    @property
    def additional_tags(self):
        return self.assign_rule.get("additional_tags", [])

    @property
    def alert_severity(self):
        return self.assign_rule.get("alert_severity", 0)

    @property
    def alert_duration(self):
        if self.alert:
            return self.alert.duration
        return 0

    @property
    def need_upgrade(self):
        current_time = int(time.time())

        last_upgrade_time = self.assign_rule_snap.get("last_upgrade_time", current_time)
        last_group_index = self.assign_rule_snap.get("last_group_index")
        latest_upgrade_interval = current_time - last_upgrade_time
        return self.upgrade_rule.need_upgrade(latest_upgrade_interval or self.alert_duration, last_group_index)

    def get_upgrade_user_group(self):
        """
        获取升级告警通知组
        :return:n
        """

        if not self.need_upgrade:
            # 不需要升级的情况下且从来没有过升级通知, 直接返回空
            return []

        last_group_index = self.assign_rule_snap.get("last_group_index")
        notice_groups, current_group_index = self.upgrade_rule.get_upgrade_user_group(
            last_group_index, self.need_upgrade
        )
        if last_group_index == current_group_index:
            # 如果已经完全升级通知了，则表示全部知会给升级负责人
            return []
        self.assign_rule["last_group_index"] = current_group_index
        self.assign_rule["last_upgrade_time"] = int(time.time())
        logger.info(
            "alert(%s) upgraded by rule(%s), current group index(%s), last_group_index(%s), last_upgrade_time(%s)",
            self.alert.id,
            self.assign_rule["id"],
            current_group_index,
            self.assign_rule_snap.get("last_group_index"),
            self.assign_rule_snap.get("last_upgrade_time"),
        )
        return notice_groups

    def notice_user_groups(self):
        """
        告警负责人
        """
        if not self.notice_action:
            # 没有通知事件，忽略
            return []
        return self.user_groups

    @property
    def user_type(self):
        """
        告警关注人
        """
        return self.assign_rule.get("user_type", UserGroupType.MAIN)


class AlertAssignMatchManager:
    """
    告警分派管理(SaaS调试分派规则时使用)
    主要功能：
    1. 告警分派匹配前的数据准备，比如组装告警为维度信息
    2. 告警分派匹配
    3. 整理匹配到分派规则和告警信息
    """

    def __init__(
        self,
        alert: AlertDocument,
        notice_users: List = None,
        group_rules: List[Dict] = None,
        assign_mode: List[str] = None,
        notice_type=None,
        cmdb_attrs: Dict[str, Union[Host, Set, Module]] = None,
    ):
        """
        :param alert: 告警
        :param notice_users: 通知人员（告警负责人）
        :param group_rules: 指定的分派规则, 以优先级从高到低排序
        :param assign_mode: 分派模式，仅通知、仅分派规则、通知+分派规则
        :param notice_type: 通知类型
        :param cmdb_attrs: CMDB相关的维度信息
        """
        self.alert = alert
        self.origin_severity = alert.severity
        # 仅通知情况下
        self.origin_notice_users_object = None
        self.notice_users = notice_users or []
        # 针对存量的数据，默认为通知+分派规则
        self.assign_mode = assign_mode or [AssignMode.ONLY_NOTICE, AssignMode.BY_RULE]
        self.notice_type = notice_type
        # 转换CMDB相关的维度信息，后续将会更新到告警维度中
        self.cmdb_dimensions = self.get_match_cmdb_dimensions(cmdb_attrs)
        # 获取当前告警的维度，用于后续匹配分派规则
        self.dimensions = self.get_match_dimensions()
        extra_info = self.alert.extra_info.to_dict() if self.alert.extra_info else {}
        # 获取到分派规则快照，如果该告警曾经匹配到过分派规则，会将该规则记录下来，作为快照。
        # 后续需要再次匹配时，可以直接通过该快照进行对比，从而避免重复匹配
        self.rule_snaps = extra_info.get("rule_snaps") or {}
        self.bk_biz_id = self.alert.event.bk_biz_id
        # 指定的分派规则, 以优先级从高到低排序
        self.group_rules = group_rules or []
        # 匹配到的规则
        self.matched_rules: List[AssignRuleMatch] = []
        # 匹配到的规则对应的告警信息
        self.matched_rule_info = {
            "notice_upgrade_user_groups": [],  # 通知升级负责人
            "follow_groups": [],  # 关注人
            "notice_appointees": [],  # 指定的通知人
            "itsm_actions": {},  # ITSM事件
            "severity": 0,  # 告警等级
            "additional_tags": [],  # 附加的标签
            "rule_snaps": {},  # 规则快照
            "group_info": {},  # 告警组信息
        }
        self.severity_source = ""

    def get_match_cmdb_dimensions(self, cmdb_attrs: Dict[str, Union[Host, Set, Module]]):
        """
        获取CMDB相关的维度信息

        根据提供的CMDB属性信息，提取并构建CMDB维度数据。

        example:
        >> {"host": Host, "sets": Sets, "modules": Modules}
        >> #处理后。。。
        >> {"host.key1":[attr1,attr2,...],"host.key2":[attr1,attr2,...],
            "set.key1":[attr1,attr2,...],"set.key2":[attr1,attr2,...],
            "module.key1"[attr1,attr2,...],"host.key2":[attr1,attr2,...],
           }

        参数:
        cmdb_attrs (dict): 包含CMDB相关信息的字典，包括主机、业务集和模块的属性。

        返回:
        dict: 包含CMDB维度信息的字典，键为维度名称，值为该维度下的属性值列表。
        """
        # 如果提供的CMDB属性为空，则直接返回空字典
        if not cmdb_attrs:
            return {}

        # 从CMDB属性中提取主机信息
        host = cmdb_attrs["host"]
        # 如果不存在主机，也不会存在拓扑信息，直接返回
        if not host:
            return {}

        # 初始化CMDB维度字典，使用defaultdict以方便后续操作
        cmdb_dimensions = defaultdict(list)

        # 遍历主机的属性，并将其添加到CMDB维度中
        for attr_key, attr_value in host.get_attrs().items():
            cmdb_dimensions[f"host.{attr_key}"].append(attr_value)

        # 遍历业务集，并将每个业务集的属性添加到CMDB维度中
        for biz_set in cmdb_attrs["sets"]:
            # 如果当前缓存获取的信息不正确，忽略属性，避免直接报错
            if not biz_set:
                continue
            for attr_key, attr_value in biz_set.get_attrs().items():
                cmdb_dimensions[f"set.{attr_key}"].append(attr_value)

        # 遍历模块，并将每个模块的属性添加到CMDB维度中
        for biz_module in cmdb_attrs["modules"]:
            # 如果当前缓存获取的信息不正确，忽略属性，避免直接报错
            if not biz_module:
                continue
            for attr_key, attr_value in biz_module.get_attrs().items():
                cmdb_dimensions[f"module.{attr_key}"].append(attr_value)

        # 返回构建好的CMDB维度信息
        return cmdb_dimensions

    def get_match_dimensions(self):
        """
        获取当前告警的维度
        :return:
        """
        # 第一部分： 告警的属性字段
        dimensions = {
            # 获取都插件ID
            "alert.event_source": getattr(self.alert.event, "plugin_id", None),
            # 告警策略
            "alert.scenario": self.alert.strategy["scenario"] if self.alert.strategy else "",
            # 告警策略ID
            "alert.strategy_id": str(self.alert.strategy["id"]) if self.alert.strategy else "",
            # 告警名称
            "alert.name": self.alert.alert_name,
            # 告警指标
            "alert.metric": [m for m in self.alert.event.metric],
            # 告警标签
            "alert.labels": list(getattr(self.alert, "labels", [])),
            "labels": list(getattr(self.alert, "labels", [])),
            # 是否存在通知对象
            "is_empty_users": "true" if not self.notice_users else "false",
            # 通知用户
            "notice_users": self.notice_users,
            # 告警IP
            "ip": getattr(self.alert.event, "ip", None),
            # 告警云区域ID
            "bk_cloud_id": str(self.alert.event.bk_cloud_id) if hasattr(self.alert.event, "bk_cloud_id") else None,
            # 新增bk_host_id 用以匹配动态分组
            "bk_host_id": str(self.alert.event.bk_host_id) if hasattr(self.alert.event, "bk_host_id") else None,
        }
        # 第二部分： 告警维度
        alert_dimensions = [d.to_dict() for d in self.alert.dimensions]
        dimensions.update(
            {d["key"][5:] if d["key"].startswith("tags.") else d["key"]: d.get("value", "") for d in alert_dimensions}
        )
        origin_alarm_dimensions = self.alert.origin_alarm["data"]["dimensions"] if self.alert.origin_alarm else {}
        dimensions.update(origin_alarm_dimensions)

        # 第三部分： 第三方接入告警，直接使用tags内容
        alert_tags = [d.to_dict() for d in self.alert.event.tags]
        dimensions.update({f'tags.{d["key"]}': d.get("value", "") for d in alert_tags})

        # 第四部分： cmdb相关的节点属性
        dimensions.update(self.cmdb_dimensions)

        return dimensions

    def get_host_ids_by_dynamic_groups(self, dynamic_group_ids):
        """
        根据动态分组ID获取主机ID列表。

        该函数通过调用CMDB接口，批量执行动态分组，从而获取属于这些动态分组的所有主机ID，
        并以列表形式返回。这种方式能够高效地获取大量主机ID，且只依赖于CMDB系统的API调用。

        参数:
        dynamic_group_ids (list): 动态分组ID列表，用于指定需要获取主机ID的动态分组。

        返回:
        list: 主机ID列表，包含所有属于指定动态分组的主机ID。
        """
        # 初始化主机ID集合，使用集合来去重
        host_ids = set()

        # 调用CMDB接口，批量执行动态分组获取主机
        dynamic_group_hosts = api.cmdb.batch_execute_dynamic_group(
            bk_biz_id=self.bk_biz_id, ids=dynamic_group_ids, bk_obj_id="host"
        )

        # 遍历每个动态分组的主机列表
        for dynamic_group_host in dynamic_group_hosts.values():
            for host in dynamic_group_host:
                # 将主机ID添加到集合中，自动去重
                host_ids.add(host.bk_host_id)

        # 返回主机ID列表，将集合转换为列表
        return list(host_ids)

    def get_matched_rules(self) -> List[AssignRuleMatch]:
        """
        适配分派规则, 通过api获取动态分组，适用于SaaS调试预览，后台实现基于缓存重写
        :return: 匹配的规则列表
        """
        # 初始化匹配成功的匹配对象列表
        matched_rules: List[AssignRuleMatch] = []
        # # 检查是否需要按规则分派
        if AssignMode.BY_RULE not in self.assign_mode:
            # 如果不需要分派的，不要进行规则匹配
            return matched_rules
        # 遍历所有规则组
        for rules in self.group_rules:
            # 遍历规则组中的每一条规则
            for rule in rules:
                # 检查规则是否启用
                if not rule.get("is_enabled"):
                    # 没有开启的直接返回
                    continue
                # 动态分组转换,根据动态分组ID获取主机ID列表,并修改字段名称为bk_host_id
                for condition in rule["conditions"]:
                    # 当条件是动态分组时，通过API获取对应的主机ID
                    if condition["field"] == "dynamic_group":
                        condition["value"] = self.get_host_ids_by_dynamic_groups(condition["value"])
                        condition["field"] = "bk_host_id"
                # 创建规则匹配对象
                rule_match_obj = AssignRuleMatch(rule, self.rule_snaps.get(str(rule.get("id", ""))), self.alert)
                # 规则匹配
                if rule_match_obj.is_matched(dimensions=self.dimensions):
                    # 如果匹配，添加到匹配的规则列表中
                    matched_rules.append(rule_match_obj)
            # 规则组传入时已经优先级从高到底排序
            # 如果存在匹配到高优先级的规则组时，优先级低的规则组不再匹配。
            if matched_rules:
                break
        # 返回匹配对象列表
        return matched_rules

    def get_itsm_actions(self):
        """
        获取流程的规则对应的通知组
        """
        itsm_user_groups = defaultdict(list)
        for rule_obj in self.matched_rules:
            if not rule_obj.itsm_action:
                continue
            itsm_user_groups[rule_obj.itsm_action["id"]].extend(rule_obj.user_groups)
        return itsm_user_groups

    def get_notice_user_groups(self):
        """
        获取适配的规则对应的通知组
        """
        notice_user_groups = []
        for rule_obj in self.matched_rules:
            rule_user_groups = [group_id for group_id in rule_obj.user_groups if group_id not in notice_user_groups]
            notice_user_groups.extend(rule_user_groups)
        return set(notice_user_groups)

    @property
    def severity(self):
        return self.matched_rule_info["severity"]

    @property
    def additional_tags(self):
        return self.matched_rule_info["additional_tags"]

    @property
    def new_rule_snaps(self):
        return self.matched_rule_info["rule_snaps"]

    @property
    def matched_group_info(self):
        return self.matched_rule_info["group_info"]

    def get_matched_rule_info(self):
        """
        整理匹配到的规则和告警信息。

        此方法遍历所有匹配的规则对象，收集通知用户组、关注组、ITSM用户组、所有告警级别、附加标签和规则快照信息。
        它还根据通知类型决定是否获取升级用户组，并处理用户组的去重和更新。
        """
        # 如果没有匹配的规则，则不执行任何操作
        if not self.matched_rules:
            return

        # 初始化通知用户组、关注组、ITSM用户组、所有告警级别、附加标签和新规则快照的空容器
        notice_user_groups = []
        follow_groups = []
        itsm_user_groups = defaultdict(list)
        all_severity = []
        additional_tags = []
        new_rule_snaps = {}

        # 遍历所有匹配的规则对象
        for rule_obj in self.matched_rules:
            # 将规则对象的附加标签添加到总附加标签列表中
            additional_tags.extend(rule_obj.additional_tags)
            # 将规则对象的告警级别添加到所有告警级别列表中，如果规则对象的告警级别未设置，则使用当前告警的级别
            all_severity.append(rule_obj.alert_severity or self.alert.severity)

            # 当有升级变动的时候才真正进行升级获取和记录
            user_groups = rule_obj.get_upgrade_user_group() if self.notice_type == "upgrade" else rule_obj.user_groups

            # 根据规则对象的用户类型，将用户组添加到相应的列表中
            if rule_obj.user_type == UserGroupType.FOLLOWER:
                follow_groups.extend([group_id for group_id in user_groups if group_id not in follow_groups])
            else:
                new_groups = [group_id for group_id in user_groups if group_id not in notice_user_groups]
                notice_user_groups.extend(new_groups)

            # 更新规则快照并将其添加到新规则快照字典中
            rule_obj.assign_rule_snap.update(rule_obj.assign_rule)
            new_rule_snaps[str(rule_obj.rule_id)] = rule_obj.assign_rule_snap

            # 如果规则对象包含ITSM操作，则将用户组添加到相应的ITSM操作ID下
            if rule_obj.itsm_action:
                itsm_user_groups[rule_obj.itsm_action["action_id"]].extend(rule_obj.user_groups)

        # 构建匹配规则信息字典，包含通知用户组、关注组、ITSM操作、最小告警级别、附加标签和规则快照信息
        self.matched_rule_info = {
            "notice_appointees": notice_user_groups,
            "follow_groups": follow_groups,
            "itsm_actions": {action_id: user_groups for action_id, user_groups in itsm_user_groups.items()},
            "severity": min(all_severity),
            "additional_tags": additional_tags,
            "rule_snaps": new_rule_snaps,
            # 组名取一个即可
            "group_info": {
                "group_id": self.matched_rules[0].assign_rule["assign_group_id"],
                "group_name": self.matched_rules[0].assign_rule.get("group_name", ""),
            },
        }

    def run_match(self):
        """
        执行规则适配
        """
        # 获取匹配的规则列表
        self.matched_rules: List[AssignRuleMatch] = self.get_matched_rules()

        # 整理匹配到的规则
        if self.matched_rules:
            # 计算所有匹配规则中的最大告警严重性
            assign_severity = max([rule_obj.alert_severity for rule_obj in self.matched_rules])

            # 根据计算出的严重性设置严重性来源
            self.severity_source = AssignMode.BY_RULE if assign_severity > 0 else ""

            # 整理匹配到的规则的以及告警信息
            self.get_matched_rule_info()

            # 更新告警的严重性，如果匹配的规则中有指定严重性，则使用规则指定的严重性
            self.alert.severity = self.matched_rule_info["severity"] or self.alert.severity

            # 更新告警的额外信息，包括严重性来源和规则快照
            self.alert.extra_info["severity_source"] = self.severity_source
            # 更新分派规则快照
            self.alert.extra_info["rule_snaps"] = self.matched_rule_info["rule_snaps"]

            # 更新分派标签
            self.update_assign_tags()

    def get_alert_log(self):
        """
        获取告警分派流水日志
        """
        if not self.matched_rules:
            # 如果没有适配到告警规则，忽略
            return
        current_time = int(time.time())
        if self.severity and self.severity != self.origin_severity:
            logger.info(
                "Change alert(%s) severity from %s to %s by rule", self.alert.id, self.origin_severity, self.severity
            )
            content = _("告警适配到自动分派规则组${}$, 级别由【{}】调整至【{}】").format(
                self.matched_group_info["group_name"],
                EVENT_SEVERITY_DICT.get(self.origin_severity, self.origin_severity),
                EVENT_SEVERITY_DICT.get(self.severity, self.severity),
            )
        else:
            content = _("告警适配到自动分派规则组${}$, 级别维持【{}】不变").format(
                self.matched_group_info["group_name"],
                EVENT_SEVERITY_DICT.get(self.origin_severity, self.origin_severity),
                EVENT_SEVERITY_DICT.get(self.severity, self.severity),
            )
        description = {
            "text": content,
            # ?bizId={bk_biz_id}#/alarm-dispatch?group_id={group_id}
            "router_info": {
                "router_name": "alarm-dispatch",
                "params": {"biz_id": self.bk_biz_id, "group_id": self.matched_group_info["group_id"]},
            },
            "action_plugin_type": "assign",
        }
        alert_log = dict(
            op_type=AlertLog.OpType.ACTION,
            event_id=current_time,
            alert_id=self.alert.id,
            severity=self.severity,
            description=json.dumps(description),
            create_time=current_time,
            time=current_time,
        )
        return alert_log

    def update_assign_tags(self):
        """
        更新分派的tags
        :return:
        """
        assign_tags = {item["key"]: item for item in self.alert.assign_tags}
        additional_tags = {item["key"]: item for item in self.matched_rule_info["additional_tags"]}
        assign_tags.update(additional_tags)
        self.alert.assign_tags = list(assign_tags.values())
