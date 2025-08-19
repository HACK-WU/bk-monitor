"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import base64
import os
from pathlib import Path

import yaml
from django.utils.translation import gettext as _

from core.errors.plugin import PluginParseError
from monitor_web.plugin.constant import OS_TYPE_TO_DIRNAME, ParamMode
from monitor_web.plugin.manager.base import PluginManager
from monitor_web.plugin.serializers import ScriptSerializer


class ScriptPluginManager(PluginManager):
    """
    脚本 插件
    """

    templates_dirname = "script_templates"
    serializer_class = ScriptSerializer

    # 获取采集脚本文件
    def fetch_collector_file(self):
        """
        file_config={
            "linux": {
                "filename": "collector.sh",
                "script_content_base64": "xxx"
            },
            "windows": {
                "filename": "collector.bat",
                "script_content_base64": "xxx"
            }
        }
        :return:
        """
        file_dict = {}
        for os_type, script_info in list(self.version.config.file_config.items()):
            if script_info:
                file_dict[os_type] = [
                    {
                        "file_name": script_info["filename"],
                        "file_content": base64.b64decode(script_info["script_content_base64"]),
                    }
                ]
        return file_dict

    def make_package(self, **kwargs):
        kwargs.update(dict(add_files=self.fetch_collector_file()))
        return super().make_package(**kwargs)

    def _get_debug_config_context(self, config_version, info_version, param, target_nodes):
        specific_version = self.plugin.get_version(config_version, info_version)
        config_json = specific_version.config.config_json

        collector_data = param["collector"]
        plugin_data = param.get("plugin", {})

        context = {
            "env.yaml": {},
            "bkmonitorbeat_debug.yaml": collector_data,
        }
        user_files = []

        cmd_args = ""

        dms_insert_params = {}

        # 节点管理base64识别前缀
        nodeman_base64_file_prefix = "$NODEMAN_BASE64_PREFIX$"

        for param in config_json:
            param_name = param["name"]
            param_mode = param["mode"]
            param_value = plugin_data.get(param_name)

            if param_value is None:
                continue

            if param["type"] == "file":
                user_files.append(
                    {"filename": param_value.get("filename"), "file_base64": param_value.get("file_base64")}
                )
                context["{{file" + str(len(user_files)) + "}}"] = {
                    f"file{len(user_files)}_content": nodeman_base64_file_prefix + param_value.get("file_base64", ""),
                    f"file{len(user_files)}": param_value.get("filename"),
                }
                # 改写参数值为 etc/xxx.yy
                param_value = "etc/" + param_value.get("filename")

            if param_mode == ParamMode.ENV:
                context["env.yaml"][param_name] = param_value

            elif param_mode == ParamMode.OPT_CMD:
                if param["type"] == "switch":
                    if param_value == "true":
                        cmd_args += f"{param_name} "
                elif param_value:
                    cmd_args += f"{param_name} {param_value} "

            elif param_mode == ParamMode.POS_CMD:
                # 位置参数，直接将参数值拼接进去
                cmd_args += f"{param_value} "

            elif param_mode == ParamMode.DMS_INSERT:
                # 维度注入参数，更新至labels的模板中
                for dms_key, dms_value in list(param_value.items()):
                    if param["type"] == "host":
                        dms_insert_params[dms_key] = "{{ " + f"cmdb_instance.host.{dms_value} or '-'" + " }}"
                    elif param["type"] == "service":
                        dms_insert_params[dms_key] = (
                            "{{ " + f"cmdb_instance.service.labels['{dms_value}'] or '-'" + " }}"
                        )
                    elif param["type"] == "custom":
                        # 自定义维度k， v 注入
                        dms_insert_params[dms_key] = dms_value

        context["env.yaml"]["cmd_args"] = cmd_args

        if dms_insert_params:
            collector_data.update(
                {"labels": {"$for": "cmdb_instance.scope", "$item": "scope", "$body": {**dms_insert_params}}}
            )

        return context

    def get_deploy_steps_params(self, plugin_version, param, target_nodes):
        """
        生成插件部署步骤参数配置，包含环境变量配置和命令行参数组装逻辑

        参数:
            plugin_version: 插件版本对象，包含版本信息和配置模板
            param: 参数字典，包含插件参数(plugin)和采集器参数(collector)
            target_nodes: 目标节点列表，未在当前方法中直接使用，保留作为扩展参数

        返回值:
            list: 部署步骤配置列表，包含两个元素：
                1. 插件部署步骤配置字典
                2. 采集器部署步骤配置字典
            配置结构包含ID、类型、插件元数据、配置模板和上下文参数等信息

        该方法实现以下核心功能：
        1. 命令行参数(cmd_args)的动态组装
        2. 文件参数的base64编码处理及路径转换
        3. 环境变量上下文(env_context)的构建
        4. 部署步骤模板的动态填充
        """
        cmd_args = ""
        plugin_params = param["plugin"]
        collector_params = param["collector"]
        collector_params["command"] = (
            f"{{{{ step_data.{self.plugin.plugin_id}.control_info.setup_path }}}}/{{{{ step_data.{self.plugin.plugin_id}.control_info.start_cmd }}}}"
        )
        env_context = {}
        user_files = []

        # 节点管理base64识别前缀
        nodeman_base64_file_prefix = "$NODEMAN_BASE64_PREFIX$"

        # 参数处理核心逻辑：
        # 1. 遍历插件配置参数定义
        # 2. 根据参数类型和模式进行分类处理
        # 3. 构建环境变量上下文和命令行参数
        for param in plugin_version.config.config_json:
            param_name = param["name"]
            param_mode = param["mode"]
            param_value = plugin_params.get(param_name)

            if param_value is None:
                continue

            # 文件参数特殊处理：
            # - 记录文件元数据
            # - 构建base64编码上下文
            # - 转换文件路径为etc/xxx.yy格式
            if param["type"] == "file":
                user_files.append(
                    {"filename": param_value.get("filename"), "file_base64": param_value.get("file_base64")}
                )
                env_context[f"file{len(user_files)}"] = param_value.get("filename")
                env_context[f"file{len(user_files)}_content"] = nodeman_base64_file_prefix + param_value.get(
                    "file_base64", ""
                )
                # 改写参数值为 etc/xxx.yy
                param_value = "etc/" + param_value.get("filename")

            # 环境变量模式参数处理：
            # 直接写入环境上下文
            if param_mode == ParamMode.ENV:
                env_context[param_name] = param_value

            # 命令行选项参数处理：
            # - 开关类型参数特殊处理
            # - 普通参数采用键值对格式
            elif param_mode == ParamMode.OPT_CMD:
                if param["type"] == "switch":
                    if param_value == "true":
                        cmd_args += f"{param_name} "
                elif param_value:
                    cmd_args += f"{param_name} {param_value} "

            # 位置参数处理：
            # 直接拼接参数值到命令行
            elif param_mode == ParamMode.POS_CMD:
                # 位置参数，直接将参数值拼接进去
                cmd_args += f"{param_value} "

        # 最终将命令行参数注入环境上下文
        env_context["cmd_args"] = cmd_args

        # 构建部署步骤模板：
        # 1. 主插件部署步骤
        # 2. 采集器部署步骤
        deploy_steps = [
            {
                "id": self.plugin.plugin_id,
                "type": "PLUGIN",
                "config": {
                    "plugin_name": self.plugin.plugin_id,
                    "plugin_version": plugin_version.version,
                    "config_templates": [
                        {
                            "name": "env.yaml",
                            "version": str(plugin_version.config_version),
                        }
                    ],
                },
                "params": {"context": env_context},
            },
            self._get_bkmonitorbeat_deploy_step("bkmonitorbeat_script.conf", {"context": collector_params}),
        ]

        # 动态添加用户文件配置模板：
        # 为每个上传文件生成对应的配置模板项
        for index, file in enumerate(user_files):
            deploy_steps[0]["config"]["config_templates"].append(
                {
                    "name": "{{file" + str(index + 1) + "}}",
                    "version": str(plugin_version.config_version),
                    "content": "{{file" + str(index + 1) + "_content}}",
                }
            )
        return deploy_steps

    def _get_collector_json(self, plugin_params: dict[str, bytes]):
        meta_dict = yaml.load(plugin_params["meta.yaml"], Loader=yaml.FullLoader)

        if "scripts" not in meta_dict:
            raise PluginParseError({"msg": _("无法解析脚本内容")})

        collector_json = {}
        for os_name, file_info in list(meta_dict["scripts"].items()):
            script_path = os.path.join(
                self.plugin.plugin_id, OS_TYPE_TO_DIRNAME[os_name], self.plugin.plugin_id, file_info["filename"]
            )

            script_content = self._decode_file(self.plugin_configs[Path(script_path)])
            collector_json[os_name] = {
                "filename": file_info["filename"],
                "type": file_info["type"],
                "script_content_base64": base64.b64encode(script_content.encode("utf-8")),
            }

        return collector_json
