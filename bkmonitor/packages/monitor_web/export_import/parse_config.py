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
import json
from pathlib import Path

import yaml
from django.utils.translation import gettext as _
from rest_framework.exceptions import ErrorDetail, ValidationError

from bkmonitor.strategy.new_strategy import Strategy
from bkmonitor.utils.request import get_request_tenant_id
from core.errors.plugin import PluginParseError
from monitor_web.export_import.constant import ImportDetailStatus
from monitor_web.models import CollectConfigMeta, CollectorPluginMeta, Signature
from monitor_web.plugin.manager import PluginManagerFactory


class BaseParse:
    def __init__(self, file_path, file_content={}, plugin_configs: dict[Path, bytes] = None):
        self.file_path = file_path
        self.file_content = file_content

        # todo plugin_path 和 plugin_configs 两个参数移动到CollectConfigParse类中
        # todo plugin_configs key 值改为str类型
        self.plugin_path = None
        self.plugin_configs = plugin_configs

    def read_file(self):
        with open(self.file_path) as fs:
            self.file_content = json.loads(fs.read())

    @abc.abstractmethod
    def check_msg(self):
        pass

    def parse_msg(self):
        self.read_file()
        return self.check_msg()


class CollectConfigParse(BaseParse):
    check_field = ["id", "name", "label", "collect_type", "params", "plugin_id", "target_object_type"]

    def only_check_fields(self):
        miss_filed = []
        for filed in self.check_field:
            if not self.file_content.get(filed):
                miss_filed.append(filed)

        if miss_filed:
            return {
                "file_status": ImportDetailStatus.FAILED,
                "name": self.file_content.get("name"),
                "collect_config": self.file_content,
                "error_msg": "miss filed {}".format(",".join(miss_filed)),
            }
        else:
            return {
                "file_status": ImportDetailStatus.SUCCESS,
                "collect_config": self.file_content,
            }

    def check_msg(self):
        """
        检查采集配置文件内容的有效性，并根据条件返回相应的校验结果

        执行步骤：
        1. 校验文件中是否包含必要字段 'name'
        2. 对基础字段进行初步校验（only_check_fields）
        3. 若采集类型为日志或进程，或字段校验失败，则直接返回字段校验结果
        4. 校验插件是否存在，若不存在则返回错误信息
        5. 解析插件信息并构建完整的插件配置数据结构
        6. 若解析成功且存在临时版本信息，则组装插件配置并返回成功状态
        7. 否则返回插件解析的结果（可能是失败信息）

        返回值:
            dict: 包含以下关键字段的字典
                - file_status: 文件校验状态（SUCCESS/FAILED）
                - name: 配置名称（仅在失败时提供）
                - collect_config: 原始采集配置内容
                - error_msg: 错误描述（仅在失败时提供）
                - plugin_config: 插件详细配置信息（仅在成功时提供）
        """
        # 校验文件名是否存在
        if self.file_content.get("name") is None:
            return None

        # 进行基础字段校验
        fields_check_result = self.only_check_fields()

        # 如果是日志/进程类型采集 或 字段校验已失败，则直接返回字段校验结果
        if (
            self.file_content.get("collect_type", "")
            in [CollectConfigMeta.CollectType.LOG, CollectConfigMeta.CollectType.PROCESS]
            or fields_check_result["file_status"] == ImportDetailStatus.FAILED
        ):
            return fields_check_result

        # 获取插件ID并判断插件路径是否存在
        plugin_id = self.file_content.get("plugin_id")
        if not self.get_plugin_path(plugin_id):
            return {
                "file_status": ImportDetailStatus.FAILED,
                "name": self.file_content.get("name"),
                "collect_config": self.file_content,
                "error_msg": _("缺少依赖的插件"),
            }

        # 解析插件信息
        parse_plugin_config = self.parse_plugin_msg(plugin_id)

        # 如果解析出临时版本信息，则构造完整插件配置并返回成功状态
        if parse_plugin_config.get("tmp_version"):
            tmp_version = parse_plugin_config["tmp_version"]
            plugin_config = {}

            # 更新配置与信息部分到插件配置中
            plugin_config.update(tmp_version.config.config2dict())
            plugin_config.update(tmp_version.info.info2dict())

            # 补充其他元信息
            plugin_config.update(
                {
                    "plugin_id": tmp_version.plugin_id,
                    "plugin_type": tmp_version.plugin.plugin_type,
                    "tag": tmp_version.plugin.tag,
                    "label": tmp_version.plugin.label,
                    "signature": Signature(tmp_version.signature).dumps2yaml(),
                    "config_version": tmp_version.config_version,
                    "info_version": tmp_version.info_version,
                    "version_log": tmp_version.version_log,
                    "is_official": tmp_version.is_official,
                    "is_safety": tmp_version.is_safety,
                }
            )

            return {
                "file_status": ImportDetailStatus.SUCCESS,
                "collect_config": self.file_content,
                "plugin_config": plugin_config,
            }
        else:
            # 否则返回插件解析原始结果
            return parse_plugin_config

    def get_meta_path(self, plugin_id: str):
        """
        获取指定插件ID对应的meta.yaml文件路径

        参数:
            plugin_id (str): 插件唯一标识符

        返回值:
            pathlib.Path 或 str: 匹配到的meta.yaml文件路径，未找到则返回空字符串

        该方法遍历已加载的插件配置文件路径，查找符合以下条件的文件：
        1. 路径第一级目录名等于plugin_id
        2. 父目录名为"info"
        3. 文件名为"meta.yaml"
        """
        meta_path = ""
        # 遍历所有已知的插件配置文件路径
        for file_path in self.plugin_configs.keys():
            # 检查路径是否匹配目标插件的meta.yaml文件
            if (
                str(file_path).split("/")[0] == plugin_id
                and file_path.parent.name == "info"
                and file_path.name == "meta.yaml"
            ):
                meta_path = file_path
                break
        return meta_path

    def parse_plugin_msg(self, plugin_id: str):
        meta_path = self.get_meta_path(plugin_id)

        if not meta_path:
            return {
                "file_status": ImportDetailStatus.FAILED,
                "name": self.file_content.get("name"),
                "config": self.file_content,
                "error_msg": _("关联插件信息解析失败，缺少meta.yaml文件"),
            }
        try:
            meta_content = self.plugin_configs[meta_path]
            meta_dict = yaml.load(meta_content, Loader=yaml.FullLoader)
            plugin_type_display = meta_dict.get("plugin_type")
            for name, display_name in CollectorPluginMeta.PLUGIN_TYPE_CHOICES:
                if display_name == plugin_type_display:
                    plugin_type = name
                    break
            else:
                raise PluginParseError({"msg": _("无法解析插件类型")})

            import_manager = PluginManagerFactory.get_manager(
                bk_tenant_id=get_request_tenant_id(),
                plugin=self.file_content.get("plugin_id"),
                plugin_type=plugin_type,
            )
            import_manager.filename_list = self.get_filename_list(plugin_id)
            import_manager.plugin_configs = self.plugin_configs

            # todo info_path 更名为file_info
            info_path = {
                file_path.name: self.plugin_configs[file_path]
                for file_path in import_manager.filename_list
                if file_path.parent.name == "info"
            }

            tmp_version = import_manager.get_tmp_version(info_path=info_path)
            return {"tmp_version": tmp_version}
        except Exception as e:
            return {
                "file_status": ImportDetailStatus.FAILED,
                "name": self.file_content.get("name"),
                "config": self.file_content,
                "error_msg": _("关联插件信息解析失败,{}".format(e)),
            }

    def get_filename_list(self, plugin_id: str) -> list[Path]:
        """获取插件的文件列表"""
        filename_list = []
        for file_path in self.plugin_configs.keys():
            if str(file_path).split("/")[0] == plugin_id:
                filename_list.append(file_path)

        return filename_list

    def get_plugin_path(self, plugin_id) -> bool:
        """
        遍历 self.plugin_configs 查找是否有包含 plugin_id 的路径
        """
        result = False
        for config_path in self.plugin_configs.keys():
            if str(config_path).split("/")[0] == plugin_id:
                result = True
                break
        return result


class StrategyConfigParse(BaseParse):
    def check_msg(self):
        """检查并处理策略配置文件内容，生成校验结果和相关配置数据

        处理流程说明:
            1. 基础校验：检查必须存在的name字段
            2. 配置转换：将v1版策略转换为v2版格式
            3. 配置验证：使用序列化器验证配置有效性
            4. 通知组检查：验证用户组配置完整性
            5. 数据采集：提取采集配置ID信息
        """
        # 前置条件检查：配置文件必须包含name字段
        if self.file_content.get("name") is None:
            return None

        # 初始化返回数据结构（SUCCESS为默认状态）
        return_data = {
            "file_status": ImportDetailStatus.SUCCESS,
            "config": Strategy.convert_v1_to_v2(self.file_content),
            "name": self.file_content.get("name"),
        }

        # 使用序列化器进行配置校验
        serializers = Strategy.Serializer(data=return_data["config"])
        try:
            serializers.is_valid(raise_exception=True)
        except ValidationError as e:
            # 错误信息递归处理函数
            def error_msg(value):
                """处理嵌套的错误信息结构，将错误详情提取到error_list"""
                for k, v in list(value.items()):
                    if isinstance(v, dict):
                        error_msg(v)
                    elif isinstance(v, list) and isinstance(v[0], ErrorDetail):
                        error_list.append(f"{k}{v[0][:-1]}")
                    else:
                        for v_msg in v:
                            error_msg(v_msg)

            # 收集并格式化校验错误信息
            error_list = []
            error_msg(e.detail)
            error_detail = "；".join(error_list)
            return_data.update(file_status=ImportDetailStatus.FAILED, error_msg=error_detail)

        # 检查通知组名称配置
        action_list = return_data["config"]["actions"]
        for action_detail in action_list:
            for notice_detail in action_detail.get("user_group_list", []):
                if notice_detail.get("name") is None:
                    return_data.update(file_status=ImportDetailStatus.FAILED, error_msg=_("缺少通知组名称"))

        # 从查询条件中提取采集配置ID
        bk_collect_config_ids = []
        for query_config in return_data["config"]["items"][0]["query_configs"]:
            agg_condition = query_config.get("agg_condition", [])

            # 处理不同格式的采集配置ID参数
            for condition_msg in agg_condition:
                if "bk_collect_config_id" not in list(condition_msg.values()):
                    continue

                # 处理数组格式和字符串格式的配置值
                if isinstance(condition_msg["value"], list):
                    bk_collect_config_ids.extend(
                        [int(value) for value in condition_msg["value"] if str(value).isdigit()]
                    )
                else:
                    bk_collect_config_id = condition_msg["value"].split("(")[0]
                    bk_collect_config_ids.append(int(bk_collect_config_id))

        return return_data, bk_collect_config_ids


class ViewConfigParse(BaseParse):
    def check_msg(self):
        if self.file_content.get("title") is None:
            return None

        return {
            "file_status": ImportDetailStatus.SUCCESS,
            "config": self.file_content,
            "name": self.file_content.get("title"),
        }
