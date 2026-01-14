"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from bkmonitor.models import UserGroup
from bkmonitor.strategy.new_strategy import Action, Detect
from constants.action import ActionSignal
from core.drf_resource import Resource, resource
from core.drf_resource.viewsets import ResourceRoute, ResourceViewSet


class SaveStrategyResource(Resource):
    def perform_request(self, validated_request_data):
        actions = validated_request_data.pop("actions", [])
        if not actions:
            raise ValidationError(_("actions 列表不能为空"))

        serializer = Action.Serializer(data=actions, many=True)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data[0]

        signal = [ActionSignal.ABNORMAL, ActionSignal.NO_DATA]

        action_config = action.get("config", {})

        if action_config.get("send_recovery_alarm"):
            signal.append(ActionSignal.RECOVERED)

        notice = {
            "user_groups": action["notice_group_ids"],
            "signal": signal,
            "options": {
                "converge_config": {
                    "need_biz_converge": True,
                },
            },
            "config": {
                "notify_interval": int(action_config.get("alarm_interval", 120)) * 60,
                "interval_notify_mode": "standard",
                "template": [
                    {
                        "signal": ActionSignal.ABNORMAL,
                        "message_tmpl": action["notice_template"].get("anomaly_template", ""),
                        "title_tmpl": "{{business.bk_biz_name}} - {{alarm.name}}{{alarm.display_type}}",
                    },
                    {
                        "signal": ActionSignal.RECOVERED,
                        "message_tmpl": action["notice_template"].get("recovery_template", ""),
                        "title_tmpl": "{{business.bk_biz_name}} - {{alarm.name}}{{alarm.display_type}}",
                    },
                    {
                        "signal": ActionSignal.CLOSED,
                        "message_tmpl": action["notice_template"].get("anomaly_template", ""),
                        "title_tmpl": "{{business.bk_biz_name}} - {{alarm.name}}{{alarm.display_type}}",
                    },
                ],
            },
        }

        validated_request_data["notice"] = notice

        webhook_actions = []
        for group in UserGroup.objects.filter(id__in=action["notice_group_ids"]):
            if group.webhook_action_id:
                webhook_actions.append(
                    {
                        "config_id": group.webhook_action_id,
                        "signal": [
                            ActionSignal.ABNORMAL,
                            ActionSignal.NO_DATA,
                            ActionSignal.RECOVERED,
                            ActionSignal.CLOSED,
                        ],
                        "user_groups": action["notice_group_ids"],
                        "options": {
                            "converge_config": {
                                "is_enabled": False,
                            }
                        },
                    }
                )
        validated_request_data["actions"] = webhook_actions

        # 处理生效时间
        detects = validated_request_data.pop("detects", [])
        detect_serializer = Detect.Serializer(data=detects, many=True)
        detect_serializer.is_valid(raise_exception=True)

        detects = detect_serializer.validated_data
        for detect in detects:
            # 补充 uptime 默认值，同时固定 time_range 取值，支持传入日历字段
            uptime = detect["trigger_config"].get("uptime", {})
            uptime["time_ranges"] = [
                {
                    "start": action_config.get("alarm_start_time", "00:00:00"),
                    "end": action_config.get("alarm_end_time", "23:59:59"),
                }
            ]
            if "calendars" not in uptime:
                uptime["calendars"] = []
            detect["trigger_config"]["uptime"] = uptime

        validated_request_data["detects"] = detects

        return resource.strategies.save_strategy_v2(validated_request_data)


class SearchStrategyResource(Resource):
    """
    策略查询资源类
    将 V2 版本策略数据转换为兼容旧版 API 的格式返回
    """

    def perform_request(self, validated_request_data):
        """
        执行策略列表查询请求，并将 V2 格式的响应数据转换为兼容旧版 API 的格式

        参数:
            validated_request_data: dict，经过验证的请求参数，包含查询条件（如 bk_biz_id、scenario 等）

        返回值:
            dict，包含以下字段：
                - strategy_config_list: 策略配置列表（已转换为旧版 actions 格式）
                - notice_group_list: 通知组列表（从 user_group_list 字段转换而来）
                - 其他原始返回字段

        数据流转换图:
            V2 API 响应格式                          返回的兼容格式
            ┌─────────────────────┐                ┌─────────────────────┐
            │ user_group_list     │  ──转换──>     │ notice_group_list   │
            │   - user_group_id   │                │   - notice_group_id │
            │   - user_group_name │                │   - notice_group_name│
            └─────────────────────┘                └─────────────────────┘

            ┌─────────────────────┐                ┌─────────────────────┐
            │ strategy.notice     │  ──转换──>     │ strategy.actions    │
            │   - config_id       │                │   - id              │
            │   - user_groups     │                │   - notice_group_ids│
            │   - signal          │                │   - config          │
            │   - config.template │                │   - notice_template │
            └─────────────────────┘                └─────────────────────┘
        """
        # Step 1: 调用 V2 版本 API 获取策略列表
        result = resource.strategies.get_strategy_list_v2(validated_request_data)

        # Step 2: 将 user_group_list 转换为旧版 notice_group_list 格式
        # 字段映射: user_group_id -> notice_group_id, user_group_name -> notice_group_name
        result["notice_group_list"] = [
            {
                "notice_group_id": group["user_group_id"],
                "notice_group_name": group["user_group_name"],
                "count": group["count"],
            }
            for group in result["user_group_list"]
        ]

        # Step 3: 遍历每个策略，将 notice 配置转换为旧版 actions 格式
        for strategy in result["strategy_config_list"]:
            # 移除 V2 版本的 actions 字段（webhook 动作），避免与转换后的 actions 冲突
            strategy.pop("actions", None)
            # 提取并移除 notice 配置，用于构建旧版 actions
            notice = strategy.pop("notice")

            # Step 3.1: 从通知模板列表中提取异常和恢复通知模板
            anomaly_template = None
            recovery_template = None
            for template in notice["config"].get("template", ""):
                if template["signal"] == ActionSignal.ABNORMAL:
                    anomaly_template = template
                elif template["signal"] == ActionSignal.RECOVERED:
                    recovery_template = template

            # Step 3.2: 构建旧版 actions 格式
            # 将 V2 的 notice 配置重组为兼容旧版 API 的 actions 列表
            strategy["actions"] = [
                {
                    "id": notice["config_id"],  # 通知配置 ID
                    "type": "notice",  # 动作类型固定为 notice
                    "config": {
                        # 告警生效时间范围（从 options 中提取，默认全天）
                        "alarm_start_time": notice["options"].get("start_time", "00:00:00"),
                        "alarm_end_time": notice["options"].get("end_time", "23:59:59"),
                        # 告警通知间隔（V2 存储秒数，旧版使用分钟，需要除以 60）
                        "alarm_interval": notice["config"].get("notify_interval", 7200) // 60,
                        # 是否发送恢复通知（检查 signal 列表中是否包含 RECOVERED）
                        "send_recovery_alarm": ActionSignal.RECOVERED in notice["signal"],
                    },
                    "notice_group_ids": notice["user_groups"],  # 通知组 ID 列表
                    "notice_template": {
                        # 异常通知模板内容
                        "anomaly_template": anomaly_template["message_tmpl"] if anomaly_template else "",
                        # 恢复通知模板内容
                        "recovery_template": recovery_template["message_tmpl"] if recovery_template else "",
                    },
                }
            ]

        return result


class AlarmStrategyV2ViewSet(ResourceViewSet):
    """
    新版告警策略API
    """

    resource_routes = [
        ResourceRoute("POST", SearchStrategyResource, endpoint="search"),
        ResourceRoute("POST", SaveStrategyResource, endpoint="save"),
        ResourceRoute("POST", resource.strategies.delete_strategy_config, endpoint="delete"),
        ResourceRoute("POST", resource.strategies.update_partial_strategy_v2, endpoint="update_bulk"),
    ]
