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
import json
import logging
import re
import time
from datetime import datetime

from django.utils.translation import gettext as _

from api.itsm.default import TokenVerifyResource
from bkmonitor.action.serializers import (
    ActionConfigDetailSlz,
    ActionPluginSlz,
    BatchCreateDataSerializer,
    GetCreateParamsSerializer,
)
from bkmonitor.documents import AlertLog
from bkmonitor.documents.alert import AlertDocument
from bkmonitor.documents.base import BulkActionType
from bkmonitor.models.fta import ActionConfig, ActionInstance, ActionPlugin
from bkmonitor.utils.common_utils import count_md5
from bkmonitor.utils.template import CustomTemplateRenderer, Jinja2Renderer
from bkmonitor.utils.user import get_user_display_name
from bkmonitor.views import serializers
from constants.action import ActionSignal
from core.drf_resource import Resource

try:
    # 后台接口，需要引用后台代码
    from alarm_backends.core.cache.key import FTA_ACTION_LIST_KEY
    from alarm_backends.core.context import ActionContext
    from alarm_backends.service.fta_action.utils import PushActionProcessor
except BaseException:
    FTA_ACTION_LIST_KEY = None

logger = logging.getLogger(__name__)


class ITSMCallbackResource(Resource):
    """
    获取所有的响应事件插件
    """

    ACTION_ID_MATCH = re.compile(r"\(\s*([\w\|]+)\s*\)")

    class RequestSerializer(serializers.Serializer):
        sn = serializers.CharField(required=True, label="工单号")
        title = serializers.CharField(required=True, label="工单标题")
        updated_by = serializers.CharField(required=True, label="更新人")
        approve_result = serializers.BooleanField(required=True, label="审批结果")
        token = serializers.CharField(required=True, label="校验token")

    def perform_request(self, validated_request_data):
        """
        处理ITSM系统的审批回调请求

        参数:
            validated_request_data: 经过序列化验证的请求数据字典，包含以下字段：
                - sn: 工单号（字符串）
                - title: 工单标题（字符串），格式包含动作实例ID，如"[告警异常防御审批] (action_id)"
                - updated_by: 更新人（字符串）
                - approve_result: 审批结果（布尔值），True表示通过，False表示拒绝
                - token: 校验token（字符串），用于验证回调请求的合法性

        返回值:
            字典类型，包含以下字段：
                - result: 布尔值，表示处理是否成功
                - message: 字符串，返回处理结果的描述信息

        该方法实现ITSM审批回调的完整处理流程：
        1. 验证回调请求的token合法性（防止非法请求）
        2. 从工单标题中提取动作实例ID
        3. 查询对应的动作实例对象
        4. 将审批结果推送到异步队列进行后续处理
        5. 返回处理结果给ITSM系统
        """
        # 步骤1: 调用ITSM的TokenVerify接口验证token的有效性
        # 防止非法的回调请求，确保只有ITSM系统能够触发回调
        verify_data = TokenVerifyResource().request({"token": validated_request_data["token"]})
        if not verify_data.get("is_valid", False):
            # token验证失败，返回错误信息
            return {"message": "Error Token", "result": False}

        # 步骤2: 获取所有动作实例的查询集
        queryset = ActionInstance.objects.all()

        # 步骤3: 使用正则表达式从工单标题中提取动作实例ID
        # 工单标题格式示例: "[告警异常防御审批]:是否继续执行套餐【xxx】 (12345)"
        # ACTION_ID_MATCH正则: r"\(\s*([\w\|]+)\s*\)" 用于匹配括号中的ID
        action_id = self.ACTION_ID_MATCH.findall(validated_request_data["title"])
        if not action_id:
            # 标题格式不正确，无法提取ID
            return {"message": "Error ticket", "result": False}

        # 步骤4: 根据提取的ID查询对应的动作实例
        try:
            action_inst = queryset.get(id=action_id[0])
        except ActionInstance.DoesNotExist:
            # 动作实例不存在，返回错误信息
            return dict(message=_("对应的ID{}不存在").format(action_id), result=False)

        # 步骤5: 将审批回调内容推送到异步执行队列
        # 通过消息队列异步处理审批结果，避免阻塞ITSM的回调请求
        # callback_func="approve_callback" 指定调用动作实例的approve_callback方法
        # kwargs传递完整的审批结果数据（包括sn、审批人、审批结果等）
        PushActionProcessor.push_action_to_execute_queue(
            action_inst, callback_func="approve_callback", kwargs=validated_request_data
        )

        # 步骤6: 返回成功响应给ITSM系统
        return dict(result=True, message="success")


class BatchCreateActionResource(Resource):
    """
    创建任务接口
    """

    class RequestSerializer(BatchCreateDataSerializer):
        creator = serializers.CharField(required=True, label="执行人")

    def perform_request(self, validated_request_data):
        operate_data_list = validated_request_data["operate_data_list"]
        creator = validated_request_data["creator"]
        generate_uuid = count_md5([json.dumps(operate_data_list), int(datetime.now().timestamp())])
        action_plugins = {
            str(plugin["id"]): plugin for plugin in ActionPluginSlz(instance=ActionPlugin.objects.all(), many=True).data
        }
        action_logs = []
        handled_alerts = []
        alert_ids = []
        for operate_data in operate_data_list:
            alert_ids = operate_data["alert_ids"]
            alerts = AlertDocument.mget(ids=alert_ids)
            if not alerts:
                continue
            for action_config in operate_data["action_configs"]:
                action = ActionInstance.objects.create(
                    signal=ActionSignal.MANUAL,
                    strategy_id=alerts[0].strategy_id or 0,
                    alert_level=alerts[0].severity,
                    alerts=alert_ids,
                    action_config_id=action_config["config_id"],
                    action_config=action_config,
                    action_plugin=action_plugins.get(str(action_config["plugin_id"])),
                    bk_biz_id=validated_request_data["bk_biz_id"],
                    assignee=[creator],
                    generate_uuid=generate_uuid,
                )

                display_name = get_user_display_name(creator)
                action_logs.append(
                    AlertLog(
                        **dict(
                            op_type=AlertLog.OpType.ACTION,
                            alert_id=action.alerts,
                            description=_("{creator}通过页面创建{plugin_name}任务【{action_name}】进行告警处理").format(
                                plugin_name=action_config.get("plugin_name", _("手动处理")),
                                creator=display_name,
                                action_name=action_config.get("name"),
                            ),
                            time=int(time.time()),
                            create_time=int(time.time()),
                            event_id=f"{int(action.create_time.timestamp())}{action.id}",
                            operator=creator,
                        )
                    )
                )

            handled_alerts = [
                AlertDocument(
                    id=alert.id, is_handled=True, assignee=list(set([man for man in alert.assignee] + [creator]))
                )
                for alert in alerts
            ]
        actions = PushActionProcessor.push_actions_to_queue(generate_uuid, alerts)
        # 更新告警状态和流转日志
        AlertLog.bulk_create(action_logs)
        AlertDocument.bulk_create(handled_alerts, action=BulkActionType.UPDATE)

        return {"actions": list(actions), "alert_ids": alert_ids}


class GetActionParamsByConfigResource(Resource):
    """
    根据配置获取动作参数的资源类

    用于根据传入的配置ID列表、动作配置及告警信息，
    渲染并返回可用于执行的具体动作配置参数。
    """

    RequestSerializer = GetCreateParamsSerializer

    def jinja_render(self, template_value, alert_context):
        """
        使用Jinja2模板引擎递归渲染模板内容

        参数:
            template_value (Union[str, dict, list]): 待渲染的模板内容，可以是字符串、字典或列表
            alert_context (dict): 告警上下文字典，提供给模板使用的变量环境

        返回值:
            Union[str, dict, list]: 渲染后的结果，类型与输入一致
        """
        # 如果是字符串，则直接进行Jinja2渲染
        if isinstance(template_value, str):
            return Jinja2Renderer.render(template_value, alert_context) or template_value
        # 如果是字典，则递归渲染每个键值对
        if isinstance(template_value, dict):
            render_value = {}
            for key, value in template_value.items():
                render_value[key] = self.jinja_render(value, alert_context)
            return render_value
        # 如果是列表，则递归渲染每个元素
        if isinstance(template_value, list):
            return [self.jinja_render(value, alert_context) for value in template_value]
        # 其他情况原样返回
        return template_value

    def perform_request(self, validated_request_data):
        """
        执行主业务逻辑，处理请求数据并生成最终的动作配置参数

        参数:
            validated_request_data (dict): 经过验证的请求数据，包括：
                - config_ids: 配置项ID列表
                - action_configs: 动作配置列表（可选）
                - action_id: 动作实例ID（可选）
                - alert_ids: 告警ID列表

        返回值:
            dict: 包含处理结果和渲染后动作配置的响应数据
        """
        # 获取请求中的关键参数
        config_ids = validated_request_data.get("config_ids")
        action_configs = validated_request_data.get("action_configs", [])
        action_id = validated_request_data.get("action_id")

        # 若提供了config_ids，则从数据库中查询对应的详细配置
        if config_ids:
            action_configs = ActionConfigDetailSlz(ActionConfig.objects.filter(id__in=config_ids), many=True).data

        # 查询关联的告警文档
        alerts = AlertDocument.mget(validated_request_data["alert_ids"])

        # 尝试获取指定的动作实例
        action = None
        if action_id:
            try:
                action = ActionInstance.objects.get(id=action_id)
            except ActionInstance.DoesNotExist:
                logger.info("action(%s) not exist", action_id)

        # 对每一条动作配置进行上下文构建和模板渲染
        for action_config in action_configs:
            context_inputs = action_config["execute_config"].get("context_inputs", {})
            alert_context = ActionContext(
                action=action, alerts=alerts, use_alert_snap=True, dynamic_kwargs=context_inputs
            ).get_dictionary()

            # 初始化自定义模板渲染器（此处content为空仅初始化）
            CustomTemplateRenderer.render(content="", context=alert_context)

            # 保存原始模板详情，并渲染新的模板详情
            action_config["execute_config"]["origin_template_detail"] = copy.deepcopy(
                action_config["execute_config"]["template_detail"]
            )
            action_config["execute_config"]["template_detail"] = self.jinja_render(
                action_config["execute_config"]["template_detail"], alert_context
            )

            # 添加告警ID和过滤后的字符串类型的告警上下文到配置中
            action_config["alert_ids"] = validated_request_data["alert_ids"]
            action_config["alert_context"] = {
                key: value for key, value in alert_context.items() if isinstance(value, str)
            }

        # 返回成功标志和处理后的动作配置列表
        return {"result": True, "action_configs": action_configs}
