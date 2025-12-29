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

from django.core import signals

from alarm_backends.management.base.base import BaseCommand
from alarm_backends.management.base.loaders import load_handler_cls

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    告警后台服务启动命令基类

    用于启动各种告警后台服务（如 access/detect/trigger/event/action/recovery 等）
    支持两种处理器类型：process（多进程）和 celery（异步任务）
    """

    _SERVICE_TYPE_ = ""  # 服务类型：access/detect/trigger/event/action/recovery/preparation 等
    _HANDLER_TYPE_ = ""  # 处理器类型：process/celery

    def add_arguments(self, parser):
        """
        添加命令行参数

        参数:
            parser: ArgumentParser 对象，用于解析命令行参数

        支持的参数:
            -s/--service-type: 指定要运行的服务类型
            -H/--handler-type: 指定处理器类型（process 或 celery），默认为 process
            args: 额外的位置参数
        """
        super().add_arguments(parser)
        parser.add_argument(
            "-s",
            "--service-type",
            help="Which service to run.",
        )
        parser.add_argument(
            "-H",
            "--handler-type",
            default="process",
            choices=["process", "celery"],
            help="Which handler does the process use?",
        )
        parser.add_argument("args", nargs="*", help="extra args")

    def on_start(self, *args, **kwargs):
        """
        启动服务的核心方法

        参数:
            *args: 位置参数，传递给 handler 构造函数
            **kwargs: 关键字参数，传递给 handler 构造函数

        执行流程:
            1. 发送 Django request_started 信号，通知服务启动
            2. 根据 _SERVICE_TYPE_ 和 _HANDLER_TYPE_ 动态加载对应的 Handler 类
            3. 实例化 Handler 并调用 handle() 方法启动服务
            4. 捕获并记录加载或执行过程中的异常
            5. 发送 request_finished 信号，通知服务结束

        异常处理:
            - 加载 Handler 失败：记录异常日志并重新抛出
            - 执行 Handler 失败：记录异常日志，如果异常标记为 always_raise 则重新抛出
        """
        try:
            # 发送请求开始信号
            signals.request_started.send(sender=self.__class__, environ=kwargs)
            # 动态加载对应的 Handler 类
            handler_cls = load_handler_cls(self._SERVICE_TYPE_, self._HANDLER_TYPE_)
        except Exception:  # noqa
            # Handler 加载失败，记录异常并抛出
            logger.exception(
                f"Error loading Handler, service_type({self._SERVICE_TYPE_}), handler_type({self._HANDLER_TYPE_})"
            )
            raise
        else:
            try:
                # 实例化 Handler 并启动服务
                handler = handler_cls(*args, **kwargs)
                handler.handle()
            except Exception as exc:
                # 检查异常是否需要强制抛出
                always_raise = getattr(exc, "always_raise", False)
                if always_raise:
                    raise exc
                # 记录 Handler 执行异常
                logger.exception(
                    f"Error executing Handler, service_type({self._SERVICE_TYPE_}), handler_type({self._HANDLER_TYPE_})"
                )
            finally:
                # 无论成功或失败，都发送请求结束信号
                signals.request_finished.send(sender=self.__class__)
