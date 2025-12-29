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

from django.conf import settings
from django.core import signals

from alarm_backends.core.cluster import get_cluster
from alarm_backends.management.base.loaders import load_handler_cls
from alarm_backends.management.base.service_discovery import ConsulServiceDiscoveryMixin
from alarm_backends.management.commands.run_service import Command as ServiceCommand

logger = logging.getLogger(__name__)


class Command(ServiceCommand, ConsulServiceDiscoveryMixin):
    """
    带服务发现功能的告警后台服务启动命令

    继承自 ServiceCommand 和 ConsulServiceDiscoveryMixin，在基础服务功能上增加了：
    - Consul 服务注册与发现
    - 服务健康检查
    - 服务优雅上下线

    适用于需要在集群中被其他服务发现的后台服务
    """

    __COMMAND_NAME__ = __name__.split(".")[-1]

    def __init__(self, *args, **kwargs):
        """
        初始化带服务发现功能的命令实例

        参数:
            *args: 位置参数
            **kwargs: 关键字参数

        执行步骤:
        1. 调用父类 ServiceCommand 的初始化方法
        2. 调用 ConsulServiceDiscoveryMixin 的初始化方法
        3. 构建服务在 Consul 中的注册路径前缀
           格式: {APP_CODE}_{PLATFORM}_{ENVIRONMENT}_{CLUSTER_NAME}/{COMMAND_NAME}
           示例: bk-monitor_enterprise_production_default/run_discovery_service
        """
        super().__init__(*args, **kwargs)
        ConsulServiceDiscoveryMixin.__init__(self, *args, **kwargs)
        # 构建 Consul 服务注册路径前缀，用于服务分组和隔离
        self._PATH_PREFIX_ = f"{settings.APP_CODE}_{settings.PLATFORM}_{settings.ENVIRONMENT}_{get_cluster().name}/{self.__COMMAND_NAME__}"

    def on_start(self, *args, **kwargs):
        """
        服务启动钩子，负责服务注册和业务处理器启动

        参数:
            *args: 位置参数，传递给业务处理器
            **kwargs: 关键字参数，传递给业务处理器

        执行流程:
        1. 完善服务注册路径，添加具体服务类型后缀
        2. 发送 Django request_started 信号
        3. 动态加载对应的业务处理器类
        4. 向 Consul 注册服务实例
        5. 实例化并启动业务处理器
        6. 发送 request_finished 信号

        异常处理:
        - 加载处理器失败：记录日志并抛出异常
        - 执行处理器失败：记录日志，如果异常标记为 always_raise 则抛出
        """
        # 在路径前缀后追加服务类型，形成完整的服务注册路径
        # 例如: bk-monitor_enterprise_production_default/run_discovery_service-access
        self._PATH_PREFIX_ = f"{self._PATH_PREFIX_}-{self._SERVICE_TYPE_}"
        try:
            # 发送请求开始信号，通知 Django 框架
            signals.request_started.send(sender=self.__class__, environ=kwargs)
            # 根据服务类型和处理器类型动态加载对应的处理器类
            handler_cls = load_handler_cls(self._SERVICE_TYPE_, self._HANDLER_TYPE_)
        except Exception:  # noqa
            # 处理器加载失败，记录详细错误信息
            logger.exception(
                f"Error loading Handler, service_type({self._SERVICE_TYPE_}), handler_type({self._HANDLER_TYPE_})"
            )
            raise
        else:
            try:
                # 向 Consul 注册当前服务实例，使其可被其他服务发现
                self.register()
                # 实例化处理器，传入当前服务实例以便处理器访问服务发现功能
                handler = handler_cls(service=self, *args, **kwargs)
                # 启动处理器，执行具体业务逻辑
                handler.handle()
            except Exception as exc:
                # 检查异常是否需要强制抛出（某些关键异常必须中断服务）
                always_raise = getattr(exc, "always_raise", False)
                if always_raise:
                    raise exc
                # 记录处理器执行异常，但不中断服务
                logger.exception(
                    f"Error executing Handler, service_type({self._SERVICE_TYPE_}), handler_type({self._HANDLER_TYPE_})"
                )
            finally:
                # 无论成功或失败，都发送请求结束信号
                signals.request_finished.send(sender=self.__class__)

    def on_destroy(self, *args, **kwargs):
        """
        服务销毁钩子，负责服务注销

        参数:
            *args: 位置参数（未使用）
            **kwargs: 关键字参数（未使用）

        执行步骤:
        1. 从 Consul 注销当前服务实例
        2. 确保服务优雅下线，不再接收新的请求

        该方法在服务退出前被调用，保证服务实例从服务发现中心移除
        """
        # 从 Consul 注销服务，防止其他服务继续发现和调用已停止的实例
        self.unregister()
