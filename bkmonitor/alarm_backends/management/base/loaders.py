"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import inspect


from alarm_backends.core.handlers import base
from bkmonitor.utils.common_utils import package_contents

# 处理器模块根路径常量
HANDLER_ROOT_MODULE = "alarm_backends.service"


def autodiscover_handlers():
    """
    自动发现并注册服务处理器的工厂函数

    参数:
        无

    返回值:
        dict: 服务类型与处理器类的映射字典，结构示例：
            {
                'service_type': {
                    'celery': CeleryHandlerClass,
                    'process': ProcessHandlerClass
                }
            }

    执行流程：
    1. 遍历HANDLER_ROOT_MODULE下的所有服务类型子模块
    2. 动态导入对应子模块的handler模块
    3. 筛选模块中继承BaseHandler的类
    4. 根据类名后缀(CeleryHandler)区分处理器类型并分类存储
    """
    service_handlers = {}
    # 遍历服务类型子模块
    for service_type in package_contents(HANDLER_ROOT_MODULE):
        pkg = f"{HANDLER_ROOT_MODULE}.{service_type}"
        # 动态查找handler模块
        handler_module = find_related_module(pkg, "handler")
        if handler_module is None:
            continue

        # 筛选模块中的处理器类
        for attr, val in list(handler_module.__dict__.items()):
            # 检查是否为BaseHandler子类
            if inspect.isclass(val) and issubclass(val, base.BaseHandler):
                # 分类存储CeleryHandler和普通处理器
                if attr.endswith("CeleryHandler"):
                    service_handlers.setdefault(service_type, {})["celery"] = val
                else:
                    service_handlers.setdefault(service_type, {})["process"] = val
    return service_handlers


# 全局注册的服务处理器映射表
SERVICE_HANDLERS = autodiscover_handlers()


def load_handler_cls(service_type, handler_type):
    """
    根据服务类型加载对应的处理器类

    参数:
        service_type (str): 服务类型标识符（如'strategy'）
        handler_type (str): 处理器类型标识符（'celery'/'process'）

    返回值:
        class: 继承自BaseHandler的具体处理器类

    异常:
        Exception: 当服务类型或处理器类型不存在时抛出异常
    """
    handlers = SERVICE_HANDLERS.get(service_type)
    if not handlers:
        raise Exception(f"Unknown Service Type({str(service_type)}).")

    if handler_type not in handlers:
        raise Exception(f"Handler Type({str(handler_type)}) is not supported.")

    return handlers.get(handler_type)
