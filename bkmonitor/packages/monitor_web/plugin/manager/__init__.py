"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

"""
插件管理
"""


import os

from django.utils.translation import gettext as _

from bkmonitor.utils.user import get_global_user
from monitor_web.commons.file_manager import PluginFileManager
from monitor_web.models.plugin import CollectorPluginMeta
from monitor_web.plugin.manager.base import PluginManager
from monitor_web.plugin.manager.built_in import BuiltInPluginManager
from monitor_web.plugin.manager.datadog import (
    DataDogPluginFileManager,
    DataDogPluginManager,
)
from monitor_web.plugin.manager.exporter import (
    ExporterPluginFileManager,
    ExporterPluginManager,
)
from monitor_web.plugin.manager.jmx import JMXPluginManager
from monitor_web.plugin.manager.k8s import K8sPluginManager
from monitor_web.plugin.manager.log import LogPluginManager
from monitor_web.plugin.manager.process import ProcessPluginManager
from monitor_web.plugin.manager.pushgateway import PushgatewayPluginManager
from monitor_web.plugin.manager.script import ScriptPluginManager
from monitor_web.plugin.manager.snmp import SNMPPluginManager
from monitor_web.plugin.manager.snmp_trap import SNMPTrapPluginManager

# 当前支持的插件类型
SUPPORTED_PLUGINS = {
    CollectorPluginMeta.PluginType.BUILT_IN: BuiltInPluginManager,
    CollectorPluginMeta.PluginType.DATADOG: DataDogPluginManager,
    CollectorPluginMeta.PluginType.EXPORTER: ExporterPluginManager,
    CollectorPluginMeta.PluginType.JMX: JMXPluginManager,
    CollectorPluginMeta.PluginType.SCRIPT: ScriptPluginManager,
    CollectorPluginMeta.PluginType.PUSHGATEWAY: PushgatewayPluginManager,
    CollectorPluginMeta.PluginType.LOG: LogPluginManager,
    CollectorPluginMeta.PluginType.SNMP_TRAP: SNMPTrapPluginManager,
    CollectorPluginMeta.PluginType.PROCESS: ProcessPluginManager,
    CollectorPluginMeta.PluginType.SNMP: SNMPPluginManager,
    CollectorPluginMeta.PluginType.K8S: K8sPluginManager,
}

FILE_PLUGINS_FACTORY = {
    CollectorPluginMeta.PluginType.BUILT_IN: PluginFileManager,
    CollectorPluginMeta.PluginType.DATADOG: DataDogPluginFileManager,
    CollectorPluginMeta.PluginType.EXPORTER: ExporterPluginFileManager,
    CollectorPluginMeta.PluginType.JMX: PluginFileManager,
    CollectorPluginMeta.PluginType.SCRIPT: PluginFileManager,
    CollectorPluginMeta.PluginType.PUSHGATEWAY: PluginFileManager,
    CollectorPluginMeta.PluginType.SNMP: PluginFileManager,
}


class PluginManagerFactory:
    @classmethod
    def get_manager(
        cls,
        bk_tenant_id=None,
        plugin: str | CollectorPluginMeta = None,
        plugin_type: str = None,
        operator="",
        tmp_path=None,
        plugin_configs=None,
    ) -> PluginManager:
        """
        根据插件标识或元数据获取对应类型的插件管理对象

        :param plugin: 插件标识符plugin_id为str或者int类型或CollectorPluginMeta元数据对象。当传入plugin_id时，
                       若对应元数据不存在会自动创建新实例
        :type plugin: Union[int, CollectorPluginMeta]
        :param plugin_type: 插件类型标识字符串，当plugin参数为整型ID时必须提供
        :type plugin_type: str
        :param operator: 操作者标识，默认为空字符串。当未指定时会自动获取全局用户作为操作者
        :type operator: str
        :param tmp_path: 临时文件路径，如果指定则必须存在有效目录路径
        :type tmp_path: str
        :return: 特定插件类型的PluginManager实例
        :rtype: PluginManager
        :raises IOError: 当指定的tmp_path路径不存在时抛出
        :raises KeyError: 当插件类型不在支持列表SUPPORTED_PLUGINS中时抛出
        """
        # 检查临时路径是否存在，若提供且不存在则抛出异常
        if (tmp_path and not os.path.exists(tmp_path)) and not plugin_configs:
            raise OSError(_("文件夹不存在：%s ，或指标插件配置不存在：plugin_configs") % tmp_path)

        # 处理插件元数据：当输入为ID时尝试查询数据库，不存在则创建新实例
        if not isinstance(plugin, CollectorPluginMeta):
            if not bk_tenant_id:
                raise ValueError("bk_tenant_id is required when PluginManagerFactory.get_manager")

            plugin_id = plugin
            try:
                plugin = CollectorPluginMeta.objects.get(bk_tenant_id=bk_tenant_id, plugin_id=plugin)
            except CollectorPluginMeta.DoesNotExist:
                plugin = CollectorPluginMeta(bk_tenant_id=bk_tenant_id, plugin_id=plugin_id, plugin_type=plugin_type)

        # 验证插件类型合法性
        plugin_type = plugin.plugin_type
        if plugin_type not in SUPPORTED_PLUGINS:
            raise KeyError(f"Unsupported plugin type: {plugin_type}")

        # 根据类型获取对应的管理器类
        plugin_manager_cls = SUPPORTED_PLUGINS[plugin_type]

        # 自动填充操作者信息
        if not operator:
            operator = get_global_user()

        # 实例化具体的插件管理器
        return plugin_manager_cls(plugin, operator, tmp_path, plugin_configs)


class PluginFileManagerFactory:
    @classmethod
    def get_manager(cls, plugin_type=None):
        """
        :param plugin_type:
        :rtype: PluginFileManager
        """
        return FILE_PLUGINS_FACTORY[plugin_type]
