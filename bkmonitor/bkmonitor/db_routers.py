"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

Django数据库路由器模块
====================

本模块实现了蓝鲸监控平台的多数据库路由策略，主要功能包括：
1. BackendRouter: 后端应用的数据库路由，将特定应用路由到专用数据库
2. TableVisitCountRouter: 表访问统计路由器，用于监控和记录模型访问频率
3. UsingDB: 动态数据库切换工具，支持装饰器和上下文管理器两种使用方式

路由策略说明：
- 后端应用（monitor_api、metadata、bkmonitor、apm、calendars）使用独立的后端数据库
- 告警相关模型（ActionInstance、ConvergeInstance、ConvergeRelation）可配置独立数据库
- 支持通过线程本地变量动态覆盖数据库路由
- 提供表访问统计功能，便于性能分析和优化
"""

import json
import logging
import os
import time
from collections import defaultdict
from functools import wraps

import settings
from bkmonitor.utils.local import local

logger = logging.getLogger(__name__)

# 后端数据库应用列表：这些应用的模型将被路由到后端专用数据库
backend_db_apps = ["monitor_api", "metadata", "bkmonitor", "apm", "calendars"]

# 后端告警模型列表：这些模型可能使用独立的告警数据库
backend_alert_models = ["ActionInstance", "ConvergeInstance", "ConvergeRelation"]


def is_backend(app_label):
    """
    判断应用是否属于后端应用

    参数:
        app_label: Django应用标签（app_label）

    返回值:
        bool: 如果应用在后端应用列表中返回True，否则返回False
    """
    return app_label in [app for app in backend_db_apps]


# 后端路由器名称：后端应用使用的数据库别名
backend_router = "monitor_api"

# 后端告警路由器名称：根据配置决定告警模型使用的数据库
# 如果后端数据库配置为default，则告警也使用default数据库
# 否则使用独立的backend_alert数据库
if settings.BACKEND_DATABASE_NAME == "default":
    backend_alert_router = "default"
else:
    backend_alert_router = "backend_alert"

# 蓝鲸监控模块标识：用于区分不同的监控服务实例（如web、worker等）
BK_MONITOR_MODULE = os.getenv("BK_MONITOR_MODULE", "default")

# 表访问统计相关全局变量
_table_visit_count_log_time: float = 0  # 上次记录日志的时间戳
_table_visit_count: dict[str, int] = defaultdict(int)  # 表访问次数统计字典，key为模型名称，value为访问次数


class BackendRouter:
    """
    后端数据库路由器

    实现Django多数据库路由策略，将后端应用的数据库操作路由到专用数据库。
    支持通过线程本地变量动态覆盖路由规则，便于在特定场景下临时切换数据库。

    路由规则优先级：
    1. 线程本地变量覆盖（DB_FOR_READ_OVERRIDE/DB_FOR_WRITE_OVERRIDE）
    2. 告警模型特殊路由（backend_alert_router）
    3. 后端应用路由（backend_router）
    4. Django缓存应用路由（backend_router）
    5. 其他情况返回None，由Django默认处理
    """

    def db_for_read(self, model, **hints):
        """
        决定指定模型的读操作应该使用哪个数据库

        参数:
            model: Django Model类对象，表示要执行读操作的模型
            **hints: 额外的提示信息字典，可能包含instance等上下文信息

        返回值:
            str: 数据库别名字符串，指定使用的数据库配置名称
            None: 表示由其他路由器决定，或使用默认数据库

        该方法实现读操作的数据库路由逻辑：
        1. 检查线程本地变量是否有动态路由覆盖配置
        2. 判断是否为告警相关模型，路由到告警数据库
        3. 判断是否为后端应用模型，路由到后端数据库
        4. 判断是否为Django缓存应用，路由到后端数据库
        5. 其他情况返回None，使用默认路由
        """
        # 优先级1: 检查是否有动态路由覆盖（通过UsingDB上下文管理器设置）
        if getattr(local, "DB_FOR_READ_OVERRIDE", []):
            return local.DB_FOR_READ_OVERRIDE[-1]

        # 优先级2: 告警相关模型使用专用的告警数据库
        if model._meta.object_name in backend_alert_models:
            return backend_alert_router

        # 优先级3: 后端应用模型使用后端数据库
        if is_backend(model._meta.app_label):
            return backend_router

        # 优先级4: Django缓存应用使用后端数据库
        if model._meta.app_label == "django_cache":
            return backend_router

        # 优先级5: 其他情况不由此路由器处理
        return None

    def db_for_write(self, model, **hints):
        """
        决定指定模型的写操作应该使用哪个数据库

        参数:
            model: Django Model类对象，表示要执行写操作的模型
            **hints: 额外的提示信息字典，可能包含instance等上下文信息

        返回值:
            str: 数据库别名字符串，指定使用的数据库配置名称
            None: 表示由其他路由器决定，或使用默认数据库

        该方法实现写操作的数据库路由逻辑：
        1. 检查线程本地变量是否有动态路由覆盖配置
        2. 判断是否为告警相关模型，路由到告警数据库
        3. 判断是否为后端应用模型，路由到后端数据库
        4. 判断是否为Django缓存应用，路由到后端数据库
        5. 其他情况返回None，使用默认路由

        注意：写操作路由逻辑与读操作保持一致，确保读写使用同一数据库
        """
        # 优先级1: 检查是否有动态路由覆盖（通过UsingDB上下文管理器设置）
        if getattr(local, "DB_FOR_WRITE_OVERRIDE", []):
            return local.DB_FOR_WRITE_OVERRIDE[-1]

        # 优先级2: 告警相关模型使用专用的告警数据库
        if model._meta.object_name in backend_alert_models:
            return backend_alert_router

        # 优先级3: 后端应用模型使用后端数据库
        if is_backend(model._meta.app_label):
            return backend_router

        # 优先级4: Django缓存应用使用后端数据库
        if model._meta.app_label == "django_cache":
            return backend_router

        # 优先级5: 其他情况不由此路由器处理
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        决定两个对象之间是否允许建立关系（外键、多对多等）

        参数:
            obj1: 第一个模型实例
            obj2: 第二个模型实例
            **hints: 额外的提示信息字典

        返回值:
            True: 明确允许建立关系
            False: 明确禁止建立关系
            None: 不确定，由其他路由器或Django默认规则决定

        该方法实现关系约束逻辑：
        1. 如果两个对象都属于后端应用，允许建立关系
        2. 其他情况返回None，由Django默认处理
        """
        # 同属后端应用的模型之间允许建立关系
        if is_backend(obj1._meta.app_label) and is_backend(obj2._meta.app_label):
            return True

        # 其他情况不做限制，由Django默认处理
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        决定是否允许在指定数据库上执行迁移操作

        参数:
            db: 数据库别名
            app_label: 应用标签
            model_name: 模型名称（可选）
            **hints: 额外的提示信息字典

        返回值:
            True: 明确允许迁移
            False: 明确禁止迁移
            None: 不确定，由其他路由器或Django默认规则决定

        该方法实现迁移控制逻辑：
        1. django_cache应用总是允许迁移（在任何数据库）
        2. 禁止后端应用在default数据库中迁移
        3. backend_alert数据库只允许告警模型迁移
        4. backend数据库只允许后端应用迁移
        5. 禁止在nodeman数据库中迁移
        6. 其他情况返回None，使用Django默认行为
        """
        # 规则1: django_cache应用总是允许迁移（缓存表可以在任何数据库）
        if app_label == "django_cache":
            return True

        # 规则2: 防止后端应用在默认数据库中迁移（避免表结构混乱）
        if db == "default" and is_backend(app_label):
            return False

        # 规则3: 后端告警路由数据库只允许告警相关模型迁移
        if db == backend_alert_router and model_name in backend_alert_models:
            return True

        # 规则4: 后端路由数据库只允许后端应用迁移
        if db == backend_router:
            return is_backend(app_label)

        # 规则5: 禁止在nodeman数据库中进行迁移（nodeman有独立的迁移管理）
        if db in ["nodeman"]:
            return False

        # 规则6: 对于其他情况，返回None让Django使用默认行为
        return None


class TableVisitCountRouter:
    """
    表访问统计路由器

    这是一个纯统计型路由器，不影响实际的数据库路由决策。
    主要功能是记录和统计各个模型的访问频率，用于性能分析和优化。

    统计机制：
    - 在每次读操作时记录模型访问次数
    - 每60秒输出一次统计日志
    - 统计数据包含模型名称、访问次数和模块标识

    注意：此路由器的所有方法都返回None，不影响实际的数据库选择
    """

    def db_for_read(self, model, **hints):
        """
        在读操作时记录表访问统计信息

        参数:
            model: Django Model类对象
            **hints: 额外的提示信息字典

        返回值:
            None: 不影响数据库路由决策，由其他路由器处理

        该方法实现表访问统计逻辑：
        1. 检查是否到达日志输出时间（每60秒）
        2. 如果到达，输出当前统计数据并更新时间戳
        3. 记录当前模型的访问次数
        4. 返回None，不影响实际的数据库路由
        """
        global _table_visit_count_log_time, _table_visit_count

        # 每分钟打印一次表访问次数统计
        now = time.time()
        if _table_visit_count_log_time < now - 60:
            # 更新日志时间戳
            _table_visit_count_log_time = now
            # 输出统计信息：包含访问次数字典和当前模块标识
            logger.info(f"table_visit_count: count: {json.dumps(_table_visit_count)}, module: {BK_MONITOR_MODULE}")

        # 记录当前模型的访问次数（使用模型类名作为key）
        _table_visit_count[model.__name__] += 1

        # 返回None，不影响数据库路由决策
        return None

    def db_for_write(self, model, **hints):
        """
        写操作时不做任何处理

        参数:
            model: Django Model类对象
            **hints: 额外的提示信息字典

        返回值:
            None: 不影响数据库路由决策

        注意：写操作不进行统计，避免影响性能
        """
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        关系约束检查时不做任何处理

        参数:
            obj1: 第一个模型实例
            obj2: 第二个模型实例
            **hints: 额外的提示信息字典

        返回值:
            None: 不影响关系约束决策
        """
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        迁移控制时不做任何处理

        参数:
            db: 数据库别名
            app_label: 应用标签
            model_name: 模型名称（可选）
            **hints: 额外的提示信息字典

        返回值:
            None: 不影响迁移决策
        """
        return None


class UsingDB:
    """
    动态数据库切换工具类

    这是一个装饰器和上下文管理器的组合实现，用于在特定代码块或函数中临时切换数据库。
    通过线程本地变量（thread-local）实现，确保多线程环境下的安全性。

    工作原理：
    - 使用栈结构存储数据库覆盖配置，支持嵌套使用
    - 进入上下文时将指定数据库推入栈顶
    - 退出上下文时从栈中弹出配置
    - BackendRouter会优先检查栈顶配置，实现动态路由

    使用场景：
    - 临时查询特定数据库的数据
    - 在测试中模拟不同数据库环境
    - 跨数据库数据迁移或同步

    用法示例1 - 作为上下文管理器：
    .. code-block:: python
        from bkmonitor.db_routers import using_db

        # 在指定数据库中执行查询
        with using_db("Database_A"):
            results = MyModel.objects.filter(status="active")

        # 嵌套使用
        with using_db("Database_A"):
            data_a = ModelA.objects.all()
            with using_db("Database_B"):
                data_b = ModelB.objects.all()  # 使用Database_B
            # 这里又回到Database_A

    用法示例2 - 作为装饰器：
    .. code-block:: python
        from bkmonitor.db_routers import using_db
        from my_app.models import Account


        @using_db("Database_B")
        def get_lowest_id_account():
            # 整个函数的数据库操作都在Database_B上执行
            return Account.objects.order_by("id").first()


        @using_db("Database_C")
        def sync_data():
            # 复杂的数据同步逻辑
            pass
    """

    def __init__(self, database):
        """
        初始化数据库切换器

        参数:
            database: 数据库别名，必须在Django DATABASES配置中存在
        """
        self.database = database

    def __enter__(self):
        """
        进入上下文管理器时的处理逻辑

        返回值:
            self: 返回自身实例，支持 with ... as 语法

        该方法实现上下文进入逻辑：
        1. 检查线程本地变量是否已初始化，未初始化则创建空列表
        2. 将指定的数据库别名推入读写覆盖栈的栈顶
        3. BackendRouter会优先使用栈顶的数据库配置
        """
        # 初始化线程本地变量的读覆盖栈（如果不存在）
        if not hasattr(local, "DB_FOR_READ_OVERRIDE"):
            local.DB_FOR_READ_OVERRIDE = []

        # 初始化线程本地变量的写覆盖栈（如果不存在）
        if not hasattr(local, "DB_FOR_WRITE_OVERRIDE"):
            local.DB_FOR_WRITE_OVERRIDE = []

        # 将指定数据库推入栈顶，同时覆盖读和写操作
        local.DB_FOR_READ_OVERRIDE.append(self.database)
        local.DB_FOR_WRITE_OVERRIDE.append(self.database)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        退出上下文管理器时的清理逻辑

        参数:
            exc_type: 异常类型（如果有异常发生）
            exc_value: 异常值（如果有异常发生）
            traceback: 异常追踪信息（如果有异常发生）

        该方法实现上下文退出逻辑：
        1. 从读写覆盖栈中弹出当前数据库配置
        2. 恢复到上一层的数据库配置（如果有嵌套）
        3. 不处理异常，让异常正常传播
        """
        # 从栈中弹出当前数据库配置，恢复到上一层配置
        local.DB_FOR_READ_OVERRIDE.pop()
        local.DB_FOR_WRITE_OVERRIDE.pop()

    def __call__(self, querying_func):
        """
        作为装饰器使用时的处理逻辑

        参数:
            querying_func: 被装饰的函数

        返回值:
            inner: 包装后的函数，执行时会在指定数据库上下文中运行

        该方法实现装饰器逻辑：
        1. 创建一个包装函数，保留原函数的元数据
        2. 在包装函数中使用上下文管理器包裹原函数调用
        3. 确保原函数的所有数据库操作都在指定数据库上执行
        """

        @wraps(querying_func)
        def inner(*args, **kwargs):
            """
            包装函数：在指定数据库上下文中调用原函数

            参数:
                *args: 原函数的位置参数
                **kwargs: 原函数的关键字参数

            返回值:
                原函数的返回值
            """
            # 在上下文管理器中调用原函数，确保使用指定数据库
            with self:
                return querying_func(*args, **kwargs)

        return inner


# 提供小写别名，符合Python函数命名规范
using_db = UsingDB
