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
import time
from collections import defaultdict

from django.utils.translation import gettext as _

from api.cmdb.define import Host, Set, Module
from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.utils.common_utils import count_md5
from bkmonitor.utils.range import load_condition_instance
from bkmonitor.utils.range.conditions import OrCondition, OrCondList, AndCondList
from constants.action import ActionPluginType, AssignMode, UserGroupType
from constants.alert import EVENT_SEVERITY_DICT
from core.drf_resource import api

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

    def __init__(self, assign_rule: dict, assign_rule_snap=None, alert: AlertDocument = None):
        """
        初始化分派规则适配对象

        :param assign_rule: 分派规则字典，包含规则ID和条件等信息
        :param assign_rule_snap: 分派规则的快照，默认为None
        :param alert: 告警文档对象，默认为None
        """
        self.assign_rule = assign_rule
        self.assign_rule_snap = assign_rule_snap or {}
        self.dimension_check: OrCondition | None = None
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
        # 初始化或条件组和临时与条件组
        or_cond: OrCondList = []
        and_cond: AndCondList = []

        # 遍历规则中的所有条件，根据条件的逻辑关系（and/or）进行分组
        for condition in self.assign_rule["conditions"]:
            # 当遇到OR条件且当前存在AND条件组时
            # 将当前AND条件组提交到OR条件组并重置
            if condition.get("condition") == "or" and and_cond:
                # 如果遇到'or'条件且已有'and'条件组，则将当前'and'条件组添加到'or'条件组中，并重置'and'条件组
                or_cond.append(and_cond)
                and_cond = []

            # 将当前条件添加到临时AND条件组
            and_cond.append(condition)

        # 如果还有剩余的'and'条件组，则将其添加到'or'条件组中
        if and_cond:
            or_cond.append(and_cond)

        # 加载条件实例，准备进行条件检查
        self.dimension_check: OrCondition = load_condition_instance(or_cond, False)

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

    def is_matched(self, dimensions: dict) -> bool:
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
        notice_users: list = None,
        group_rules: list[dict] = None,
        assign_mode: list[str] = None,
        notice_type=None,
        cmdb_attrs: dict[str, Host | Set | Module] = None,
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
        self.matched_rules: list[AssignRuleMatch] = []
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

    def get_match_cmdb_dimensions(self, cmdb_attrs: dict[str, Host | Set | Module]) -> dict[str, list]:
        """
        获取CMDB相关的维度信息

        根据提供的CMDB属性信息，提取并构建CMDB维度数据。
        支持主机、业务集、模块三级拓扑结构的属性提取，生成扁平化的维度字典。

        参数:
            cmdb_attrs (dict): 包含CMDB相关信息的字典，格式为：
                {
                    "host": Host对象（必填）,
                    "sets": Set对象列表（可为空）,
                    "modules": Module对象列表（可为空）
                }

        返回:
            dict: CMDB维度字典，键为维度路径（如"host.key"），值为属性值列表
                示例格式：
                {
                    "host.key1": [attr1, attr2],
                    "set.key1": [attr3, attr4],
                    "module.key2": [attr5]
                }

        处理流程：
        1. 空值校验：当输入为空或无主机信息时返回空字典
        2. 初始化默认字典：使用defaultdict处理维度聚合
        3. 属性提取：逐层遍历主机、业务集、模块的属性
        4. 维度构建：将嵌套结构转换为扁平化的维度键值对
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

    def get_match_dimensions(self) -> dict:
        """
        获取当前告警的匹配维度信息，整合多数据源维度属性

        该方法聚合了四类维度数据：
        1. 告警基础属性字段
        2. 结构化维度数据
        3. 第三方系统标签
        4. CMDB拓扑属性

        返回示例：
        {
            # 告警基础属性
            "alert.event_source": "bk_monitor_log",
            "alert.scenario": "host_process",
            "alert.strategy_id": "10101",
            "alert.name": "CPU 使用率过高",
            "alert.metric": ["cpu_usage", "load1"],
            "alert.labels": ["scope:app", "env:prod"],
            "labels": ["scope:app", "env:prod"],
            "is_empty_users": "false",
            "notice_users": {
                "mail": ["alice@example.com", "bob@example.com"],
                "wecom": ["alice", "bob"],
                "chat_id": ["wxid_xxx"]
            },
            "ip": "10.0.0.12",
            "bk_cloud_id": "2",
            "bk_host_id": "2000123456",

            # 维度对象（alert.dimensions）展开后合并的键值
            "bk_target_ip": "10.0.0.12",
            "process.name": "mysqld",
            "env": "prod",              # 注意：如果维度 key 为 "tags.env" 会被转成 "env"

            # 原始告警维度（origin_alarm.data.dimensions）并入
            "k8s_cluster_id": "BCS-K8S-00001",
            "pod_name": "payment-api-7b9d4f7dcf-s2k8x",

            # 事件标签（alert.event.tags），以 "tags." 前缀写入
            "tags.env": "prod",
            "tags.service": "payment",
            "tags.region": "gz",

            # CMDB 属性（来自 host/sets/modules），值为列表
            "host.bk_host_innerip": ["10.0.0.12"],
            "host.os_type": ["LINUX"],
            "host.bk_biz_name": ["在线支付"],
            "set.bk_set_name": ["支付集群"],
            "module.bk_module_name": ["payment-api"],
            "module.bk_module_id": ["12345"]
        }


        """
        # 第一部分： 告警的属性字段
        # 构建基础维度字典，包含告警核心属性和上下文信息
        dimensions = {
            # 获取事件源插件ID
            "alert.event_source": getattr(self.alert.event, "plugin_id", None),
            # 告警策略场景类型
            "alert.scenario": self.alert.strategy["scenario"] if self.alert.strategy else "",
            # 告警策略唯一标识
            "alert.strategy_id": str(self.alert.strategy["id"]) if self.alert.strategy else "",
            # 告警名称
            "alert.name": self.alert.alert_name,
            # 指标列表
            "alert.metric": [m for m in self.alert.event.metric],
            # 标签列表
            "alert.labels": list(getattr(self.alert, "labels", [])),
            "labels": list(getattr(self.alert, "labels", [])),
            # 通知用户空值标志
            "is_empty_users": "true" if not self.notice_users else "false",
            # 通知用户列表
            "notice_users": self.notice_users,
            # 告警IP地址
            "ip": getattr(self.alert.event, "ip", None),
            # 云区域ID
            "bk_cloud_id": str(self.alert.event.bk_cloud_id) if hasattr(self.alert.event, "bk_cloud_id") else None,
            # 主机唯一标识
            "bk_host_id": str(self.alert.event.bk_host_id) if hasattr(self.alert.event, "bk_host_id") else None,
        }

        # 第二部分： 告警维度处理
        # 将维度对象列表转换为字典结构并合并到主维度
        alert_dimensions = [d.to_dict() for d in self.alert.dimensions]
        dimensions.update(
            {d["key"][5:] if d["key"].startswith("tags.") else d["key"]: d.get("value", "") for d in alert_dimensions}
        )
        # 合并原始告警维度数据
        origin_alarm_dimensions = self.alert.origin_alarm["data"]["dimensions"] if self.alert.origin_alarm else {}
        dimensions.update(origin_alarm_dimensions)

        # 第三部分： 第三方标签处理
        # 解析事件标签并以tags.前缀格式合并到维度
        alert_tags = [d.to_dict() for d in self.alert.event.tags]
        dimensions.update({f"tags.{d['key']}": d.get("value", "") for d in alert_tags})

        # 第四部分： CMDB属性集成
        # 合并从CMDB获取的节点维度属性
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

    def get_matched_rules(self) -> list[AssignRuleMatch]:
        """
        适配分派规则，通过API获取动态分组，适用于SaaS调试预览，后台实现基于缓存重写

        参数:
            self: AssignRuleMatcher实例对象，包含以下关键属性:
                - assign_mode: 分派模式集合，用于判断是否需要规则分派
                - group_rules: 分组规则列表，包含多个规则组
                - dimensions: 匹配维度数据
                - alert: 告警对象
                - rule_snaps: 规则快照字典

        返回值:
            List[AssignRuleMatch]: 匹配成功的规则对象列表，按优先级排序

          返回示例：
        matched_rules = [
            AssignRuleMatch(
                assign_rule={
                    "id": 2001,
                    "is_enabled": True,
                    "assign_group_id": 3001,
                    "group_name": "数据库告警组",
                    "user_groups": [101, 102],
                    "user_type": "main",
                    "actions": [
                        # 通知动作（含升级配置）
                        {
                            "action_type": "notice",
                            "is_enabled": True,
                            "upgrade_config": {
                                "is_enabled": True,
                                "upgrade_interval": 30,  # 分钟
                                "user_groups": [201, 202, 203],
                            },
                        },
                        # ITSM 动作（同时包含 id 与 action_id，兼容不同聚合逻辑）
                        {
                            "action_type": "itsm",
                            "is_enabled": True,
                            "id": 50011,                         # 规则内动作记录ID
                            "action_id": "ITSMSvc-CreateTicket", # 流程服务配置ID
                        },
                    ],
                    "conditions": [
                        {"field": "alert.scenario", "value": "host_process", "operator": "==", "condition": "and"},
                        {"field": "bk_host_id", "value": ["12345", "67890"], "operator": "in", "condition": "and"},
                    ],
                    "additional_tags": [
                        {"key": "dispatch.bk_group", "value": "DB"},
                    ],
                    "alert_severity": 3,
                },
                assign_rule_snap={
                    "id": 2001,
                    "user_groups": [101, 102],
                    "conditions": [
                        {"field": "alert.scenario", "value": "host_process", "operator": "==", "condition": "and"},
                        {"field": "bk_host_id", "value": ["12345", "67890"], "operator": "in", "condition": "and"},
                    ],
                    "last_group_index": 0,
                    "last_upgrade_time": 1720000000,
                },
                alert=AlertDocument(...),
            )
        ]


        处理流程:
        1. 模式检查：若未启用规则分派模式直接返回空列表
        2. 动态分组转换：将动态分组条件转换为主机关联ID
        3. 规则匹配：逐条验证规则匹配性
        4. 优先级控制：遇到高优先级匹配结果后终止后续处理
        """
        # 初始化匹配成功的匹配对象列表
        matched_rules: list[AssignRuleMatch] = []

        # 检查是否需要按规则分派
        if AssignMode.BY_RULE not in self.assign_mode:
            # 非规则分派模式直接返回空列表
            return matched_rules

        # 规则匹配主循环
        for rules in self.group_rules:
            for rule in rules:
                # 跳过未启用规则
                if not rule.get("is_enabled"):
                    continue

                # 动态分组转换处理
                for condition in rule["conditions"]:
                    # 将动态分组条件转换为主机关联ID
                    if condition["field"] == "dynamic_group":
                        condition["value"] = self.get_host_ids_by_dynamic_groups(condition["value"])
                        condition["field"] = "bk_host_id"

                # 创建规则匹配对象
                rule_match_obj = AssignRuleMatch(rule, self.rule_snaps.get(str(rule.get("id", ""))), self.alert)

                # 执行规则匹配判断
                if rule_match_obj.is_matched(dimensions=self.dimensions):
                    matched_rules.append(rule_match_obj)

            # 优先级控制逻辑
            # 规则组按优先级降序排列，遇到匹配结果后终止处理
            if matched_rules:
                break

        # 返回最终匹配结果
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


        返回示例：
        matched_rule_info = {
            # 通知负责人用户组ID列表（去重后）
            "notice_appointees": [101, 102, 105],

            # 关注组ID列表（去重后）
            "follow_groups": [201, 202],

            # ITSM操作配置字典
            # key: ITSM action_id（流程服务配置ID）
            # value: 该ITSM操作关联的用户组ID列表
            "itsm_actions": {
                "ITSMSvc-CreateTicket": [101, 102],
                "ITSMSvc-ApprovalFlow": [105]
            },

            # 告警级别（取所有匹配规则中的最小值）
            # 1-致命, 2-预警, 3-提醒
            "severity": 2,

            # 附加标签列表
            "additional_tags": [
                {"key": "dispatch.bk_group", "value": "DB"},
                {"key": "dispatch.team", "value": "backend"},
                {"key": "priority", "value": "high"}
            ],

            # 规则快照字典
            # key: 规则ID（字符串格式）
            # value: 规则的完整快照信息
            "rule_snaps": {
                "2001": {
                    "id": 2001,
                    "assign_group_id": 3001,
                    "group_name": "数据库告警组",
                    "user_groups": [101, 102],
                    "user_type": "main",
                    "conditions": [
                        {
                            "field": "alert.scenario",
                            "value": "host_process",
                            "operator": "==",
                            "condition": "and"
                        },
                        {
                            "field": "bk_host_id",
                            "value": ["12345", "67890"],
                            "operator": "in",
                            "condition": "and"
                        }
                    ],
                    "actions": [
                        {
                            "action_type": "notice",
                            "is_enabled": True,
                            "upgrade_config": {
                                "is_enabled": True,
                                "upgrade_interval": 30,
                                "user_groups": [201, 202, 203]
                            }
                        }
                    ],
                    "additional_tags": [
                        {"key": "dispatch.bk_group", "value": "DB"}
                    ],
                    "alert_severity": 2,
                    # 升级相关字段（如果发生过升级）
                    "last_group_index": 0,
                    "last_upgrade_time": 1720000000
                }
            },

            # 告警组信息（取第一个匹配规则的组信息）
            "group_info": {
                "group_id": 3001,
                "group_name": "数据库告警组"
            }
        }

        主要功能：
        1. 收集所有匹配规则的相关信息（通知组、关注组、ITSM操作等）
        2. 根据通知类型处理用户组获取逻辑
        3. 构建完整的匹配规则信息字典供后续使用
        """
        # 如果没有匹配的规则，则不执行任何操作
        if not self.matched_rules:
            return

        # 初始化通知用户组、关注组、ITSM用户组、所有告警级别、附加标签和新规则快照的空容器
        notice_user_groups = []
        follow_groups = []

        # itsm_user_groups 数据示例
        # {
        #     "action_id": ["user_group_id1", "user_group_id2"],
        # }
        itsm_user_groups = defaultdict(list)
        all_severity = []
        additional_tags = []
        new_rule_snaps = {}

        # 遍历所有匹配的规则对象
        for rule_obj in self.matched_rules:  # type: AssignRuleMatch
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
        self.matched_rules: list[AssignRuleMatch] = self.get_matched_rules()

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

        生成告警分派操作的流水日志记录，用于追踪告警级别变更和规则匹配情况。
        该日志会记录告警适配到的分派规则组信息以及级别调整详情。

        返回:
            dict: 告警日志字典，包含以下字段：
                - op_type: 操作类型（ACTION）
                - event_id: 事件ID（当前时间戳）
                - alert_id: 告警ID
                - severity: 告警级别
                - description: 日志描述（JSON格式）
                - create_time: 创建时间
                - time: 时间戳
            None: 当没有匹配到规则时返回None

        日志示例:
        {
            "op_type": "ACTION",
            "event_id": 1720000000,
            "alert_id": "abc123.1720000000.456.789.1",
            "severity": 2,
            "description": {
                "text": "告警适配到自动分派规则组数据库告警组, 级别由【提醒】调整至【预警】",
                "router_info": {
                    "router_name": "alarm-dispatch",
                    "params": {"biz_id": 2, "group_id": 3001}
                },
                "action_plugin_type": "assign"
            },
            "create_time": 1720000000,
            "time": 1720000000
        }

        处理流程:
        1. 检查是否有匹配的规则，无规则则直接返回
        2. 比较告警级别是否发生变化，生成对应的日志内容
        3. 构建包含路由信息的日志描述
        4. 组装完整的告警日志字典并返回
        """
        # 如果没有适配到告警规则，直接返回None，不生成日志
        if not self.matched_rules:
            return

        # 获取当前时间戳，用于日志记录
        current_time = int(time.time())

        # 判断告警级别是否发生变化，生成相应的日志内容
        if self.severity and self.severity != self.origin_severity:
            # 告警级别发生变化时，记录变更信息到日志
            logger.info(
                "Change alert(%s) severity from %s to %s by rule", self.alert.id, self.origin_severity, self.severity
            )
            # 生成级别调整的提示文本
            # 格式：告警适配到自动分派规则组{组名}, 级别由【原级别】调整至【新级别】
            content = _("告警适配到自动分派规则组${}$, 级别由【{}】调整至【{}】").format(
                self.matched_group_info["group_name"],
                EVENT_SEVERITY_DICT.get(self.origin_severity, self.origin_severity),
                EVENT_SEVERITY_DICT.get(self.severity, self.severity),
            )
        else:
            # 告警级别未发生变化时，生成级别维持不变的提示文本
            # 格式：告警适配到自动分派规则组{组名}, 级别维持【当前级别】不变
            content = _("告警适配到自动分派规则组${}$, 级别维持【{}】不变").format(
                self.matched_group_info["group_name"],
                EVENT_SEVERITY_DICT.get(self.origin_severity, self.origin_severity),
                EVENT_SEVERITY_DICT.get(self.severity, self.severity),
            )

        # 构建日志描述对象，包含文本内容、路由信息和插件类型
        description = {
            # 日志显示的文本内容
            "text": content,
            # 前端路由信息，用于跳转到告警分派页面
            # 路由格式：?bizId={bk_biz_id}#/alarm-dispatch?group_id={group_id}
            "router_info": {
                "router_name": "alarm-dispatch",  # 路由名称
                "params": {"biz_id": self.bk_biz_id, "group_id": self.matched_group_info["group_id"]},  # 路由参数
            },
            # 动作插件类型标识
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

        # 返回构建好的告警日志
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
