"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import abc
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import chain

from rest_framework import serializers
from api.cmdb.define import Host, Set, Module
from bkmonitor.action.alert_assign import AlertAssignMatchManager
from bkmonitor.action.serializers import (
    AssignGroupSlz,
    AssignRuleSlz,
    BatchAssignRulesSlz,
    BatchSaveAssignRulesSlz,
)
from bkmonitor.documents import AlertDocument
from bkmonitor.models import AlertAssignGroup, AlertAssignRule
from bkmonitor.utils.common_utils import count_md5
from constants.action import ASSIGN_CONDITION_KEYS, AssignMode
from core.drf_resource import Resource, api
from fta_web.alert.handlers.alert import AlertQueryHandler
from fta_web.alert.handlers.translator import MetricTranslator
from fta_web.constants import GLOBAL_BIZ_ID

logger = logging.getLogger("root")


class BatchUpdateResource(Resource, metaclass=abc.ABCMeta):
    class RequestSerializer(BatchSaveAssignRulesSlz):
        assign_group_id = serializers.IntegerField(label="规则组ID", required=True)
        name = serializers.CharField(label="规则组名称", required=False)
        settings = serializers.JSONField(label="属性配置", default={}, required=False)

    def perform_request(self, validated_request_data):
        new_rules = []
        existed_rules = []
        group_id = validated_request_data["assign_group_id"]
        for rule in validated_request_data["rules"]:
            rule_id = rule.pop("id", None)
            if rule_id:
                existed_rules.append(rule_id)
                AlertAssignRule.objects.filter(id=rule_id, assign_group_id=group_id).update(**rule)
                continue
            new_rules.append(AlertAssignRule(**rule))
        aborted_rules = list(
            AlertAssignRule.objects.filter(assign_group_id=group_id)
            .exclude(id__in=existed_rules)
            .values_list("id", flat=True)
        )
        if aborted_rules:
            # 删除掉已有的废弃的规则
            AlertAssignRule.objects.filter(assign_group_id=group_id, id__in=aborted_rules).delete()

        AlertAssignRule.objects.bulk_create(new_rules)

        new_rules = AlertAssignRule.objects.filter(assign_group_id=group_id).values_list("id", flat=True)
        group = AlertAssignGroup.objects.get(id=group_id)
        group.name = validated_request_data.get("group_name") or group.name
        group.priority = validated_request_data.get("priority") or group.priority
        group.settings = validated_request_data.get("settings", {})
        group.hash = ""
        group.snippet = ""
        group.save()
        return {
            "bk_biz_id": validated_request_data["bk_biz_id"],
            "assign_group_id": group_id,
            "rules": list(new_rules),
            "aborted_rules": aborted_rules,
        }


class MatchDebugResource(Resource, metaclass=abc.ABCMeta):
    def __init__(self):
        super().__init__()
        self.hosts: dict[str, Host] | None = None
        self.sets: dict[str, Set] | None = None
        self.modules: dict[str, Module] | None = None

    class RequestSerializer(BatchAssignRulesSlz):
        exclude_groups = serializers.ListField(label="排除的规则组", child=serializers.IntegerField(), default=[])
        days = serializers.IntegerField(label="调试周期", default=7)
        start_time = serializers.IntegerField(label="调试开始时间", default=0)
        end_time = serializers.IntegerField(label="调试结束时间", default=0)
        max_alert_count = serializers.IntegerField(label="调试告警数量", default=1000)

    @staticmethod
    def compare_rules(group_id, debug_rules):
        """
        对比需要debug的规则是否发生了变化
        如果debug rules中存在新增的规则，则表示发生了变化
        如果是已经存在，则对比当前规则和现有规则的md5值，如果不一致，则表示发生了变化
        """
        # 获取到当前规则组下的已经存在的规则
        existed_rules = {
            rule["id"]: rule
            for rule in AssignRuleSlz(instance=AlertAssignRule.objects.filter(assign_group_id=group_id), many=True).data
        }
        for rule in debug_rules:
            if not rule.get("id") or rule["id"] not in existed_rules:
                # 如果不存在DB，则表示发生了变化
                rule.update(is_changed=True)
                continue
            rule_md5 = count_md5(rule)
            rule_db_md5 = count_md5(existed_rules[rule["id"]])
            if rule_md5 != rule_db_md5:
                rule.update(is_changed=True)
            else:
                rule.update(is_changed=False)

    @staticmethod
    def get_cmdb_attributes(bk_biz_id) -> tuple[dict[str, Host], dict[str, Set], dict[str, Module]]:
        """
        获取指定业务ID下的CMDB基础属性信息

        参数:
            bk_biz_id (int/str): 业务ID，用于定位CMDB中的业务范围

        返回值:
            Tuple[Dict[str, Host], Dict[str, Set], Dict[str, Module]]:
            包含三个字典的元组：
            - 主机字典：key为字符串格式的主机ID，value为Host对象
            - 集群字典：key为字符串格式的集群ID，value为Set对象
            - 模块字典：key为字符串格式的模块ID，value为Module对象

        该函数通过CMDB接口获取业务下的基础拓扑数据，构建三个维度的映射关系：
        1. 主机维度：通过topo节点获取全量主机
        2. 集群维度：获取业务下所有集群
        3. 模块维度：获取业务下所有模块
        """

        # 构建主机ID到Host对象的映射关系
        # 使用bk_host_id或host_id作为主键，确保兼容不同数据源
        hosts: dict[str, Host] = {
            str(host.bk_host_id or host.host_id): host for host in api.cmdb.get_host_by_topo_node(bk_biz_id=bk_biz_id)
        }

        # 构建集群ID到Set对象的映射关系
        # 通过bk_set_id进行字符串化存储，保证键值统一性
        sets: dict[str, Set] = {str(bk_set.bk_set_id): bk_set for bk_set in api.cmdb.get_set(bk_biz_id=bk_biz_id)}

        # 构建模块ID到Module对象的映射关系
        # 通过bk_module_id进行字符串化存储，保证键值统一性
        modules: dict[str, Module] = {
            str(bk_module.bk_module_id): bk_module for bk_module in api.cmdb.get_module(bk_biz_id=bk_biz_id)
        }

        return hosts, sets, modules

    def get_alert_cmdb_attributes(self, alert):
        """
        根据告警信息获取CMDB属性

        当没有可用的主机信息时，直接返回None

        参数:
        - alert: 告警对象，包含事件信息

        返回:
        - alert_cmdb_attributes: 包含主机、集群和模块信息的字典，如果无法获取则为None
        """
        if not self.hosts:
            return None
        try:
            # 尝试根据主机ID获取主机信息
            host: Host = self.hosts.get(str(alert.event.bk_host_id))
            if not host:
                # 如果根据主机ID未找到主机信息，尝试根据IP和云区域ID组合获取
                host = self.hosts.get(f"{alert.event.ip}|{alert.event.bk_cloud_id}")
        except Exception as error:
            # 非主机的可能会抛出异常
            logger.info("[match_debug]get debug host info failed: %s", str(error))
            return None
        if not host:
            return None
        sets = []
        modules = []
        alert_cmdb_attributes = {"host": host, "sets": sets, "modules": modules}
        for bk_set_id in host.bk_set_ids:
            # 根据集合ID获取集合信息
            biz_set: Set = self.sets.get(str(bk_set_id))
            if biz_set:
                sets.append(biz_set)

        for bk_module_id in host.bk_module_ids:
            # 根据模块ID获取模块信息
            biz_module: Module = self.modules.get(str(bk_module_id))
            if biz_module:
                modules.append(biz_module)
        return alert_cmdb_attributes

    def perform_request(self, validated_request_data):
        """
        告警分派规则调试接口

        参数:
            validated_request_data (dict): 经过验证的请求数据，包含以下字段：
                - bk_biz_id (int): 业务ID
                - max_alert_count (int): 最大告警数量
                - days (int): 查询时间范围（天数）
                - start_time (int): 查询起始时间戳
                - end_time (int): 查询结束时间戳
                - assign_group_id (int): 待调试的规则组ID
                - group_name (str): 规则组名称
                - priority (int): 规则组优先级
                - exclude_groups (list): 需排除的规则组列表
                - rules (list): 待调试的规则列表

        返回值:
            list: 包含规则组匹配结果的响应数据，每个元素包含：
                - group_id (int): 规则组ID
                - alerts_count (int): 匹配告警数量
                - group_name (str): 规则组名称
                - priority (int): 规则组优先级
                - rules (list): 包含匹配结果的规则列表

        执行流程:
            1. 提取业务ID并获取CMDB属性
            2. 构建告警查询条件并获取原始告警数据
            3. 加载并处理所有规则组数据
            4. 执行告警与规则的匹配逻辑
            5. 翻译指标并构建响应数据
        """
        # 提取请求数据中的业务ID
        bk_biz_id = validated_request_data["bk_biz_id"]

        # 获取主机属性|集群属性|模块属性
        self.hosts, self.sets, self.modules = self.get_cmdb_attributes(validated_request_data["bk_biz_id"])

        # step1 获取最近1周内产生的前1000条告警数据，所有数据默认为abnormal
        current_time = datetime.now()
        search_params = {
            "bk_biz_ids": [bk_biz_id],
            "page_size": validated_request_data["max_alert_count"],
            "ordering": ["-create_time"],
            "start_time": validated_request_data["start_time"]
            or int((current_time - timedelta(days=validated_request_data["days"])).timestamp()),
            "end_time": validated_request_data["end_time"] or int(current_time.timestamp()),
        }
        handler = AlertQueryHandler(**search_params)

        # 执行原始告警数据查询并转换为文档对象
        search_result, _ = handler.search_raw()
        # 将告警数据转为AlertDocument告警对象
        alerts = [AlertDocument(**hit.to_dict()) for hit in search_result]

        # step2 获取当前DB存储的所有规则，并替换掉当前的告警规则
        # 2.1 获取到所有的规则组内容
        group_id = validated_request_data.get("assign_group_id", 0)
        group_name = validated_request_data.get("group_name", "")
        priority = validated_request_data.get("priority", 0)
        exclude_groups = validated_request_data.get("exclude_groups") or []

        # 查询所有业务相关的规则组并应用排除过滤
        groups_queryset = AlertAssignGroup.objects.filter(bk_biz_id__in=[bk_biz_id, GLOBAL_BIZ_ID]).order_by(
            "-priority"
        )

        # 过滤掉不需要的规则组
        if exclude_groups:
            groups_queryset = groups_queryset.exclude(id__in=validated_request_data["exclude_groups"])

        # 序列化规则组数据并清理冗余字段
        groups = {group["id"]: group for group in AssignGroupSlz(instance=groups_queryset, many=True).data}
        # 去掉ID字段
        for group in groups.values():
            group.pop("id", None)

        # 初始化规则存储结构并处理待调试规则
        group_rules = defaultdict(list)
        priority_rules = defaultdict(list)
        if group_id:
            self.compare_rules(group_id, validated_request_data["rules"])
            group_rules[group_id] = validated_request_data["rules"]
            groups[group_id]["priority"] = priority
            groups[group_id]["name"] = group_name
            # 添加当前分派规则
            priority_rules[priority] = validated_request_data["rules"]

        # 2.2 获取到所有的不属于当前规则组的规则
        rules_queryset = AlertAssignRule.objects.filter(bk_biz_id__in=[bk_biz_id, GLOBAL_BIZ_ID]).exclude(
            assign_group_id=group_id
        )
        # 再次过滤掉不需要的规则
        if exclude_groups or group_id:
            exclude_groups.append(group_id)
            rules_queryset = rules_queryset.exclude(assign_group_id__in=exclude_groups)
        # 拿到不属于当期规则组的规则
        rules = AssignRuleSlz(instance=rules_queryset, many=True).data

        # 2.3 通过优先级和组名进行排序
        for rule in rules:
            rule["alerts"] = []
            rule.update(groups[rule["assign_group_id"]])
            priority_rules[rule["priority"]].append(rule)
            group_rules[rule["assign_group_id"]].append(rule)
        for rule in validated_request_data["rules"]:
            rule["alerts"] = []

        # 按优先级排序规则组
        sorted_priorities = sorted(priority_rules.keys(), reverse=True)
        # 按照优先级排序存储的分派规则
        sorted_priority_rules = [priority_rules[sorted_priority] for sorted_priority in sorted_priorities]

        # step3 对告警进行规则适配 ?? 是否需要后台任务支持
        matched_alerts = []
        # 按优先级排序并存储的匹配到的告警分派规则组
        matched_group_alerts = defaultdict(list)
        for alert in alerts:
            origin_severity = alert.severity
            alert_manager = AlertAssignMatchManager(
                alert,
                notice_users=alert.assignee,
                group_rules=sorted_priority_rules,
                assign_mode=[AssignMode.BY_RULE],
                # 获取到当前告警的CMDB属性： {"host": host, "sets": sets, "modules": modules}
                # 告警分派规则中，匹配条件可以使用CMDB属性，后续会将这些熟悉添加到告警中，作为所有告警共同维度
                cmdb_attrs=self.get_alert_cmdb_attributes(alert),
            )
            # 匹配告警，如果匹配，则更新alert告警信息
            alert_manager.run_match()
            if not alert_manager.matched_rules:
                continue

            # 构建告警详情信息
            alert_info = {
                "id": alert.id,
                "origin_severity": origin_severity,
                "severity": alert.severity,
                "alert_name": alert.alert_name,
                "content": getattr(alert.event, "description", ""),
                "metrics": [{"id": metric_id} for metric_id in alert.event.metric],
            }

            # 记录匹配结果
            for matched_rule in alert_manager.matched_rules:
                alert_dict = alert.to_dict()
                alert_dict["origin_severity"] = origin_severity
                matched_rule.assign_rule["alerts"].append(alert_info)
            matched_group_alerts[alert_manager.matched_group_info["group_id"]].append(alert)
            matched_alerts.append(alert_info)

        # 执行指标翻译操作
        MetricTranslator(bk_biz_ids=[bk_biz_id]).translate_from_dict(
            list(chain(*[alert["metrics"] for alert in matched_alerts])), "id", "name"
        )
        # step4 返回所有的规则信息
        response_data = []
        for sorted_priority in sorted_priorities:
            for rule_group_id, rules in group_rules.items():
                group_info = groups.get(rule_group_id, {})
                if group_info["priority"] != sorted_priority:
                    continue
                response_data.append(
                    {
                        "group_id": rule_group_id,
                        "alerts_count": len(matched_group_alerts.get(rule_group_id, [])),
                        "group_name": group_info.get("name", rule_group_id),
                        "priority": group_info.get("priority", 0),
                        "rules": rules,
                    }
                )
        return response_data


class GetAssignConditionKeysResource(Resource, metaclass=abc.ABCMeta):
    def perform_request(self, validated_request_data):
        assign_condition_keys = []
        for key, display_key in ASSIGN_CONDITION_KEYS.items():
            assign_condition_keys.append({"key": key, "display_key": display_key})
        return assign_condition_keys


class SearchObjectAttributeResource(Resource, metaclass=abc.ABCMeta):
    class RequestSerializer(serializers.Serializer):
        bk_biz_id = serializers.IntegerField(label="业务ID", required=True)
        bk_obj_id = serializers.CharField(label="模型ID", required=True)

    def perform_request(self, validated_request_data):
        return api.cmdb.search_object_attribute(validated_request_data)
