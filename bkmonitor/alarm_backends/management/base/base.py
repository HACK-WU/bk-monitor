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
import signal
import sys
import time

import six
from django.conf import settings
from django.core.management.base import BaseCommand as DjangoBaseCommand
from django.db import close_old_connections

from alarm_backends.core.cluster import filter_bk_biz_ids, get_cluster
from alarm_backends.management.base import dispatch, protocol, service_discovery
from bkmonitor import models

logger = logging.getLogger(__name__)


class BaseCommand(DjangoBaseCommand, protocol.AbstractLifecycleMixin, protocol.AbstractWorker):
    """
    基础命令类，提供可扩展的生命周期管理和信号处理功能

    功能特性:
    1. 支持最小执行间隔控制
    2. 提供最大运行周期和运行时长限制
    3. 实现完整的生命周期钩子系统
    4. 支持信号中断处理

    生命周期流程:
    on_create() -> on_start() -> on_stop() -> on_destroy()
    """

    # options
    _MIN_INTERVAL_ = 1  # seconds
    _MAX_CYCLES_ = 10000
    _MAX_UPTIME_ = 3600  # seconds

    # status
    __CYCLES__ = 0
    __EXC_INFO__ = None
    __LAST_TIMESTAMP__ = None
    __SHUTDOWN_RECEIVED__ = False
    __UPTIME__ = time.time()

    def add_arguments(self, parser):
        """
        添加命令行参数

        参数:
            parser: 参数解析器对象

        支持参数:
        --min-interval: 最小执行间隔(秒)
        --max-cycles: 最大运行周期数
        --max-uptime: 最大运行时长(秒)
        --pdb: 启用调试模式
        """
        super().add_arguments(parser)
        parser.add_argument(
            "--min-interval",
            type=int,
            default=1,
        )
        parser.add_argument(
            "--max-cycles",
            type=int,
            default=1000,
        )
        parser.add_argument(
            "--max-uptime",
            type=int,
            default=3600,
        )
        parser.add_argument(
            "--pdb",
            type=int,
            default=0,
        )

    def _onsignal(self, signum, frame):
        """
        信号处理回调函数

        参数:
            signum: 信号编号
            frame: 当前堆栈帧
        """
        self.__SHUTDOWN_RECEIVED__ = True
        logger.info("shutdown received.")

    def break_loop(self):
        """
        检查循环是否需要终止

        返回值:
            布尔值表示是否需要终止循环
        """
        if self.__SHUTDOWN_RECEIVED__:
            return True
        else:
            self.__CYCLES__ += 1

    def can_continue(self):
        """
        检查并控制循环执行条件

        功能:
        1. 检查关闭标志
        2. 处理异常状态
        3. 控制最小执行间隔
        4. 检查最大运行周期和时长限制
        """
        if self.__SHUTDOWN_RECEIVED__ or self.__EXC_INFO__ is not None:
            return False

        if isinstance(self.__LAST_TIMESTAMP__, float):
            interval = time.time() - self.__LAST_TIMESTAMP__
            if interval < self._MIN_INTERVAL_:
                time.sleep(self._MIN_INTERVAL_ - interval)
        self.__LAST_TIMESTAMP__ = time.time()

        return True

    def execute(self, *args, **options):
        """
        执行命令入口方法

        参数:
            *args: 位置参数
            **options: 命令选项参数
        """
        if options.get("pdb"):
            import pdb

            pdb.set_trace()

        super().execute(*args, **options)

    def handle(self, *args, **options):
        """
        主处理逻辑

        参数:
            *args: 位置参数
            **options: 命令选项参数

        核心流程:
        1. 注册信号处理函数
        2. 初始化生命周期钩子
        3. 执行主循环
        4. 处理异常和退出条件
        """
        signal.signal(signal.SIGTERM, self._onsignal)
        signal.signal(signal.SIGINT, self._onsignal)

        for option, value in six.iteritems(options):
            if option not in ("no_color", "pythonpath", "settings", "traceback", "verbosity") and value is not None:
                attr = f"_{option.upper()}_"
                setattr(self, attr, options[option])

        self.on_create(*args)

        while self.can_continue():
            try:
                self.on_start(*args)
                self.on_stop(*args)
            except Exception as e:
                self.__EXC_INFO__ = (e.__class__, None, sys.exc_info()[2])
            finally:
                self.__CYCLES__ += 1
                if self.__CYCLES__ >= self._MAX_CYCLES_:
                    logger.info("maximum cycles reached.")
                    break
                if time.time() - self.__UPTIME__ >= self._MAX_UPTIME_:
                    logger.info("maximum uptime reached.")
                    break

        self.on_destroy(*args)

        if self.__EXC_INFO__ is not None:
            six.reraise(*self.__EXC_INFO__)

    def on_start(self, *args, **kwargs):
        """
        生命周期钩子方法：启动阶段
        子类可重写此方法实现启动逻辑
        """
        pass

    def on_create(self, *args, **kwargs):
        """
        生命周期钩子方法：创建阶段
        子类可重写此方法实现初始化逻辑
        """
        close_old_connections()

    def on_stop(self, *args, **kwargs):
        """
        生命周期钩子方法：停止阶段
        子类可重写此方法实现停止逻辑
        """
        pass

    def on_destroy(self, *args, **kwargs):
        """
        生命周期钩子方法：销毁阶段
        子类可重写此方法实现清理逻辑
        """
        pass


class ConsulDispatchCommand(dispatch.DefaultDispatchMixin, service_discovery.ConsulServiceDiscoveryMixin, BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--path-prefix",
        )
        parser.add_argument(
            "--session-ttl",
            type=int,
            default=60,
        )

    __COMMAND_NAME__ = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._PATH_PREFIX_ = f"{settings.APP_CODE}_{settings.PLATFORM}_{settings.ENVIRONMENT}_{get_cluster().name}/{self.__COMMAND_NAME__}"

    def dispatch(self):
        self.register()

        hosts, instances = self.query_for_instances()
        hosts_targets, instance_targets = self.dispatch_for_instance(hosts, instances)
        self.update_registration_info(instance_targets)

        return hosts_targets, instance_targets

    def dispatch_status(self):
        registry = dict(self._registry)

        result = []
        for host_addr, instances in six.iteritems(registry):
            for instance in instances:
                path = "/".join([self._PATH_PREFIX_, host_addr, instance])
                info = self.get_registration_info(path)
                if info:
                    result.append((f"{host_addr}/{instance}", info))

        return result

    def on_destroy(self, *args, **kwargs):
        self.unregister()

    def query_host_targets(self):
        data = list(models.StrategyModel.objects.filter(is_enabled=True).values_list("bk_biz_id", flat=True).distinct())
        data.extend(settings.BKMONITOR_WORKER_INCLUDE_LIST)
        data = filter_bk_biz_ids(data)
        data.sort()
        return data
