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
from copy import deepcopy
from importlib import import_module

import jmespath
from django.conf import settings
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from alarm_backends.service.fta_action import (
    ActionAlreadyFinishedError,
    BaseActionProcessor,
)
from bkmonitor.models import ActionPlugin
from bkmonitor.utils.template import Jinja2Renderer, NoticeRowRenderer
from constants.action import ActionStatus, FailureType
from core.drf_resource.exceptions import CustomException
from core.errors.alarm_backends import EmptyAssigneeError
from core.errors.api import BKAPIError
from core.errors.iam import APIPermissionDeniedError

logger = logging.getLogger("fta_action.run")


class ActionProcessor(BaseActionProcessor):
    """
    通用处理器
    """

    def __init__(self, action_id, alerts=None):
        super().__init__(action_id, alerts=alerts)
        self.execute_config = self.action_config["execute_config"]
        self.backend_config = self.action.action_plugin.get("backend_config", {})
        self.function_config = {item["function"]: item for item in self.backend_config}
        logger.info("load common.ActionProcessor for action(%s) finished", action_id)

    @cached_property
    def inputs(self):
        """
        准备并返回执行任务所需的输入参数

        该方法主要完成以下工作：
        1. 渲染模板配置参数（支持Jinja2语法）
        2. 格式化模板参数为列表和字典两种形式
        3. 构造完整的执行参数字典，包含业务信息、操作人、平台地址等

        返回值:
            dict: 包含所有执行所需参数的字典，结构如下：
                - operator: 操作人，优先使用通知接收人，否则使用任务负责人
                - execute_config: 执行配置，包含格式化后的模板详情
                - bk_biz_id: 业务ID
                - action_name: 任务名称（带前缀）
                - bk_paas_inner_host: 内网PAAS地址
                - bk_paas_host: 外网PAAS地址
                - 其他公共参数（来自ActionPlugin.PUBLIC_PARAMS）

        异常处理:
            如果模板渲染失败，记录错误日志并设置任务状态为失败，然后抛出异常终止执行
        """
        template_detail = self.execute_config["template_detail"]
        try:
            template_detail = self.jinja_render(template_detail)
        except BaseException as error:
            logger.error("Format execute params error %s", str(error))
            self.set_finished(ActionStatus.FAILURE, message=_("获取任务参数异常，错误信息：{}").format(str(error)))
            # 直接设置为结束，抛出异常，终止整个执行
            raise

        # 将模板详情转换为列表格式，便于前端展示和处理
        template_detail_list = [{"key": key, "value": value} for key, value in template_detail.items()]
        execute_config = deepcopy(self.execute_config)
        execute_config["template_detail"] = template_detail_list
        execute_config["template_detail_dict"] = template_detail

        # 构造最终的参数字典
        params = {
            "operator": self.notice_receivers[0] if self.notice_receivers else self.action.assignee,
            "execute_config": execute_config,
            "bk_biz_id": self.action.bk_biz_id,
            "action_name": _("[故障自愈]-{}").format(self.action_config.get("name")),
            "bk_paas_inner_host": settings.BK_COMPONENT_API_URL.rstrip("/"),
            "bk_paas_host": settings.BK_PAAS_HOST.rstrip("/"),
        }
        params.update(ActionPlugin.PUBLIC_PARAMS)
        return params

    def execute(self, failed_times=0):
        """
        执行处理动作的核心入口方法

        参数:
            failed_times: int，失败重试次数，默认为0
                         用于记录当前执行是第几次重试

        返回值:
            执行函数的返回结果，具体类型取决于backend_config中配置的执行函数
            通常返回执行状态或结果数据

        异常:
            ActionAlreadyFinishedError: 当动作状态不在可执行状态列表中时抛出

        该方法实现完整的动作执行流程，包含：
        1. 执行前状态校验（确保动作处于可执行状态）
        2. 标记开始执行并发送通知
        3. 后端配置有效性检查
        4. 动态获取并调用配置的执行函数
        """

        # ========== Step 1: 执行前状态校验 ==========
        # 只有在可执行状态下的任务才能执行
        # CAN_EXECUTE_STATUS通常包含: WAITING（等待中）、RUNNING（运行中）、FAILURE（失败可重试）等状态
        # 已完成（SUCCESS）或已终止（SKIPPED）的任务不允许再次执行
        if self.action.status not in ActionStatus.CAN_EXECUTE_STATUS:
            raise ActionAlreadyFinishedError(_("当前任务状态不可执行"))

        # ========== Step 2: 标记开始执行并发送通知 ==========
        # 执行入口，需要发送自愈开始通知
        # 该方法会：
        # 1. 发送动作开始执行的通知（如果是首次执行）
        # 2. 设置超时回调（如果配置了超时时间）
        # 3. 更新动作状态为RUNNING，并增加执行次数
        self.set_start_to_execute()

        # ========== Step 3: 后端配置有效性检查 ==========
        # backend_config为空表示未配置执行后端或配置异常
        # 这种情况下无法继续执行，直接标记为失败
        if not self.backend_config:
            self.set_finished(ActionStatus.FAILURE, message="unknown execute function")

        # ========== Step 4: 获取执行函数名称 ==========
        # backend_config是一个配置列表，第一个元素包含执行函数的配置信息
        # 配置格式示例: [{"function": "execute_webhook", "params": {...}}]
        # 执行函数为配置参数的第一个元素的function字段
        execute_func = getattr(self, self.backend_config[0]["function"])

        # ========== Step 5: 执行函数存在性检查 ==========
        # 如果通过getattr获取不到对应的方法（返回None）
        # 说明配置的函数名不存在或拼写错误，标记为失败
        if not execute_func:
            self.set_finished(ActionStatus.FAILURE, message="unknown execute function")

        # ========== Step 6: 调用执行函数 ==========
        # 动态调用配置的执行函数，实现不同类型动作的执行逻辑
        # 常见的执行函数包括:
        # - execute_webhook: 执行Webhook回调
        # - execute_notice: 执行通知发送
        # - execute_job: 执行作业平台任务
        # - execute_sops: 执行标准运维流程
        # todo 没有传入参数，后续无法获取到服务ID，也无法获取到inputs参数
        return execute_func()

    def jinja_render(self, template_value):
        """
        对传入的模板值进行Jinja2渲染处理，支持字符串、字典和列表类型的递归渲染

        参数:
            template_value: 待渲染的模板内容，可以是字符串、字典或列表类型

        返回值:
            渲染后的内容，类型与输入保持一致

        该方法实现以下功能：
        1. 使用Jinja2引擎对模板内容进行渲染
        2. 支持嵌套数据结构（字典、列表）的递归渲染
        3. 处理默认内容模板并将其渲染结果存储到上下文环境中
        """
        # 渲染默认内容模板，并通过NoticeRowRenderer进一步处理得到告警内容
        user_content = Jinja2Renderer.render(self.context.get("default_content_template", ""), self.context)
        alarm_content = NoticeRowRenderer.render(user_content, self.context)
        self.context["user_content"] = alarm_content

        # 根据template_value的不同类型进行相应的渲染处理
        if isinstance(template_value, str):
            return Jinja2Renderer.render(template_value, self.context)
        if isinstance(template_value, dict):
            render_value = {}
            for key, value in template_value.items():
                render_value[key] = self.jinja_render(value)
            return render_value
        if isinstance(template_value, list):
            return [self.jinja_render(value) for value in template_value]
        return template_value

    def create_task(self, **kwargs):
        """
        创建任务阶段
        """
        task_config = self.function_config.get("create_task")
        return self.run_node_task(task_config, **kwargs)

    def schedule(self, **kwargs):
        """轮询"""
        # 只有在可执行状态下的任务才能执行
        if self.action.status not in ActionStatus.CAN_EXECUTE_STATUS:
            raise ActionAlreadyFinishedError(_("当前任务状态不可执行"))

        task_config = self.function_config.get("schedule")
        return self.run_node_task(task_config, **kwargs)

    def run_node_task(self, config, **kwargs):
        """
        执行节点任务的核心方法，支持任务执行、轮询调度和流程流转

        参数:
            config: dict，节点配置信息，包含以下关键字段：
                - function: str，执行函数名称
                - name: str，当前步骤名称
                - finished_rule: dict，任务完成判断规则
                - success_rule: dict，任务成功判断规则
                - need_schedule: bool，是否需要轮询调度
                - schedule_timedelta: int，轮询间隔时间（秒）
                - next_function: str，下一个执行函数名称
                - need_insert_log: bool，是否需要插入日志
                - log_template: str，日志模板
            **kwargs: 传递给执行函数的额外参数

        返回值:
            outputs: dict，节点执行的输出结果
            包含任务执行状态、返回数据等信息

        异常:
            ActionAlreadyFinishedError: 当动作状态不在可执行状态列表中时抛出

        该方法实现完整的节点任务执行流程，包含：
        1. 执行前状态校验
        2. 执行次数统计和日志记录
        3. 任务执行和异常处理（权限、API、自定义异常、框架异常）
        4. 任务完成状态判断（成功/失败）
        5. 轮询调度机制（未完成任务）
        6. 流程流转控制（下一节点）
        """

        # ========== Step 1: 执行前状态校验 ==========
        # 只有在可执行状态下的任务才能执行
        # 防止已完成或已终止的任务被重复执行
        if self.action.status not in ActionStatus.CAN_EXECUTE_STATUS:
            raise ActionAlreadyFinishedError(_("当前任务状态不可执行"))

        # ========== Step 2: 执行次数统计 ==========
        # 为每个节点维护独立的执行次数计数器
        # 格式: node_execute_times_{function_name}
        # 用于监控节点执行情况和失败重试控制
        node_execute_times_key = "node_execute_times_{}".format(config.get("function", "execute"))
        self.action.outputs[node_execute_times_key] = self.action.outputs.get(node_execute_times_key, 0) + 1

        # ========== Step 3: 记录执行日志 ==========
        # 获取当前步骤名称（如"创建作业任务"、"查询任务状态"等）
        current_step_name = config.get("name")
        # 插入动作日志，记录执行参数便于问题排查
        self.insert_action_log(current_step_name, _("执行任务参数： %s") % kwargs)

        # ========== Step 4: 执行节点任务并处理异常 ==========
        try:
            # 调用实际的请求执行方法，与第三方系统交互
            # 如调用作业平台API、标准运维API等
            outputs = self.run_request_action(config, **kwargs)

        except (APIPermissionDeniedError, BKAPIError, CustomException) as error:
            # ===== 异常类型1: API权限错误、API调用错误、自定义业务异常 =====
            # 这类异常通常是由于：
            # - 当前告警负责人无权限执行操作
            # - API接口返回错误（参数错误、服务异常等）
            # - 业务逻辑校验失败
            self.set_finished(
                to_status=ActionStatus.FAILURE,
                message=_("以当前告警负责人[{}]执行{}时, 接口返回{}").format(
                    ",".join(self.action.assignee), current_step_name, str(error)
                ),
                retry_func=config.get("function", "execute"),  # 设置重试函数
                kwargs=kwargs,  # 保存重试参数
            )
            return

        except EmptyAssigneeError as error:
            # ===== 异常类型2: 负责人为空异常 =====
            # 当告警没有负责人时，无法执行需要负责人身份的操作
            # 如作业平台任务需要指定执行人
            self.set_finished(
                to_status=ActionStatus.FAILURE,
                message=_("执行{}出错，{}").format(current_step_name, str(error)),
                retry_func=config.get("function", "execute"),
                kwargs=kwargs,
            )
            return

        except BaseException as exc:
            # ===== 异常类型3: 未预期的框架异常 =====
            # 捕获所有其他异常，防止任务执行中断
            # 出现异常的时候，当前节点执行三次重新推入队列执行
            logger.exception(str(exc))

            # 将节点执行次数传递给重试逻辑，用于控制重试次数
            kwargs["node_execute_times"] = self.action.outputs.get(node_execute_times_key, 1)
            self.set_finished(
                ActionStatus.FAILURE,
                failure_type=FailureType.FRAMEWORK_CODE,  # 标记为框架代码异常
                message=_("执行{}: {}").format(current_step_name, str(exc)),
                retry_func=config.get("function", "execute"),
                kwargs=kwargs,
            )
            return

        # ========== Step 5: 更新动作输出结果 ==========
        # 将节点执行结果合并到动作的outputs字段中
        # 用于后续节点使用或结果展示
        self.update_action_outputs(outputs)

        # ========== Step 6: 判断任务是否完成 ==========
        # 根据配置的finished_rule规则判断任务是否已完成
        # 例如: {"key": "is_finished", "value": True}
        if self.is_action_finished(outputs, config.get("finished_rule")):
            # ===== 任务已完成，判断成功或失败 =====

            # 根据配置的success_rule规则判断任务是否成功
            # 例如: {"key": "status", "value": "SUCCESS"}
            if self.is_action_success(outputs, config.get("success_rule")):
                # 任务执行成功，标记为成功状态
                self.set_finished(ActionStatus.SUCCESS)
            else:
                # 任务执行失败，记录失败原因并支持重试
                self.set_finished(
                    ActionStatus.FAILURE,
                    message=_("{}阶段出错，第三方任务返回执行失败: {}").format(
                        current_step_name, outputs.get("message")
                    ),
                    retry_func=config.get("function", "execute"),
                    kwargs=kwargs,
                )
            return outputs

        # ========== Step 7: 轮询调度机制 ==========
        # 如果任务未完成且需要轮询（如异步任务需要定期查询状态）
        if config.get("need_schedule"):
            # 当前阶段未结束，还需要轮询
            # 获取轮询间隔时间，默认5秒
            schedule_timedelta = config.get("schedule_timedelta", 5)

            # 注册延迟回调，在指定时间后继续轮询任务状态
            # 回调函数通常为schedule相关方法，如schedule_job_task
            self.wait_callback(
                config.get("function", "schedule"),  # 轮询函数名
                {"pre_node_outputs": outputs},  # 传递上一次的输出结果
                delta_seconds=schedule_timedelta,  # 延迟时间
            )
            return outputs

        # ========== Step 8: 流程流转控制 ==========
        # 如果配置了下一个执行函数，则继续执行流程
        if config.get("next_function"):
            # 当前节点已经结束，插入节点日志
            # 根据配置决定是否需要在告警详情中插入日志
            if config.get("need_insert_log"):
                self.action.insert_alert_log(
                    content_template=config.get("log_template", ""),  # 日志模板
                    notice_way_display=self.notice_way_display,  # 通知方式显示名称
                )

            # 注册延迟回调，2秒后执行下一个节点
            # 短暂延迟确保当前节点状态已持久化
            self.wait_callback(
                config.get("next_function"),  # 下一个执行函数名
                {"pre_node_outputs": outputs},  # 传递当前节点的输出结果
                delta_seconds=2,
            )
            return outputs

        # ========== Step 9: 流程结束 ==========
        # 如果没有配置轮询和下一个函数，说明流程已完成
        # 标记动作为成功状态
        self.set_finished(ActionStatus.SUCCESS)
        return outputs

    def run_request_action(self, request_schema, **kwargs):
        """
        执行URL请求，动态加载资源类并调用第三方API接口

        参数:
            request_schema: dict，请求配置模式，包含以下关键字段：
                - resource_module: str，资源模块路径（如"api.bk_job.default"）
                - resource_class: str，资源类名称（如"FastExecuteScriptResource"）
                - inputs: list，输入参数映射配置列表
                - init_kwargs: dict，资源类初始化参数
                - request_data_mapping: dict，请求数据映射字典
                - outputs: list，输出结果映射配置列表
            **kwargs: 额外的上下文参数，用于JMESPath表达式搜索和数据填充

        返回值:
            outputs: dict，解码后的输出结果字典
            包含从第三方API响应中提取和转换的数据
            如果模块导入失败或资源类不存在，返回空字典 {}

        该方法实现动态API调用流程，包含：
        1. 动态导入资源模块
        2. 验证资源类存在性
        3. 构建请求输入参数（JMESPath搜索 + 固定映射）
        4. 实例化资源类并发起请求
        5. 解码和转换响应输出
        """

        # ========== Step 1: 动态导入资源模块 ==========
        # 根据配置的模块路径动态导入资源模块
        # 例如: "api.bk_job.default" -> 导入作业平台API模块
        # 例如: "api.sops.default" -> 导入标准运维API模块
        # 例如："api.common.default" -> 导入通用API模块
        try:
            resource_module = import_module(request_schema["resource_module"])
        except ImportError as err:
            # 模块导入失败，记录异常日志并返回空字典
            # 可能原因：模块路径错误、依赖缺失、模块不存在
            logger.exception(err)
            return {}

        # ========== Step 2: 验证资源类存在性 ==========
        # 获取资源类名称（如"FastExecuteScriptResource"）
        source_class = request_schema["resource_class"]

        # 检查模块中是否存在指定的资源类
        # 防止配置错误导致的AttributeError异常
        if not hasattr(resource_module, source_class):
            return {}

        # ========== Step 3: 获取资源类对象 ==========
        # 从模块中获取资源类的引用
        # 该类通常继承自Resource基类，实现了request方法
        request_class = getattr(resource_module, source_class)

        # ========== Step 4: 构建请求输入参数 ==========
        # 使用JMESPath表达式从上下文中搜索和提取数据
        # inputs配置示例: [{"key": "bk_biz_id", "path": "alert.bk_biz_id"}]
        # 会从kwargs中根据path提取数据，并映射到key字段
        inputs = self.jmespath_search_data(inputs=request_schema.get("inputs", []), **kwargs)

        # 更新固定的通用参数
        # assignee: 告警负责人列表，用于API调用时的执行人身份
        # action_plugin_key: 动作插件标识，用于区分不同的插件类型
        inputs.update(
            {
                "assignee": self.action.assignee if self.action.assignee else [],
                "action_plugin_key": self.action.action_plugin["plugin_key"]
                or self.action.action_plugin["plugin_type"],
            }
        )

        # 合并配置中的静态请求数据映射
        # request_data_mapping示例: {"operator": "admin", "timeout": 300}
        # 用于添加固定的请求参数或覆盖默认值
        inputs.update(request_schema.get("request_data_mapping", {}))

        # ========== Step 5: 实例化资源类并发起请求 ==========
        # 使用init_kwargs初始化资源类（如设置超时时间、重试次数等）
        # 调用request方法发起实际的API请求
        # 将响应结果包装在data字典的response字段中
        data = {"response": request_class(**request_schema.get("init_kwargs", {})).request(**inputs)}

        # ========== Step 6: 解码和转换响应输出 ==========
        # 使用JMESPath表达式从响应中提取所需字段
        # outputs配置示例: [{"key": "job_instance_id", "path": "response.data.job_instance_id"}]
        # 将第三方API的响应数据转换为标准化的输出格式
        outputs = self.decode_request_outputs(output_templates=request_schema.get("outputs", []), **data)

        return outputs

    def decode_request_outputs(self, output_templates, **kwargs):
        """
        解析请求的输出
        :param output_templates: 输出参数模板
        :param kwargs:
        :return:
        """
        kwargs.update(self.inputs)
        outputs = {}
        for output_template in output_templates:
            kwargs.update(outputs)
            format_type = output_template.get("format", "jmespath")
            key = output_template["key"]
            value = output_template["value"]
            outputs[key] = (
                Jinja2Renderer.render(value, kwargs) if format_type == "jinja2" else jmespath.search(value, kwargs)
            )
        return outputs

    def jmespath_search_data(self, inputs, **kwargs):
        """
        jmespath解析请求输入数据
        """
        kwargs.update(self.inputs)
        return {
            item["key"]: jmespath.search(item["value"], kwargs) if item.get("format") == "jmespath" else item["value"]
            for item in inputs
        }
