# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

"""Thread-local/Greenlet-local objects

Thread-local/Greenlet-local objects support the management of
thread-local/greenlet-local data. If you have data that you want
to be local to a thread/greenlet, simply create a
thread-local/greenlet-local object and use its attributes:

  >>> mydata = Local()
  >>> mydata.number = 42
  >>> mydata.number
  42
  >>> hasattr(mydata, 'number')
  True
  >>> hasattr(mydata, 'username')
  False

  Reference :
  from threading import local
"""

from contextlib import contextmanager

try:
    from greenlet import getcurrent as get_ident
except ImportError:
    try:
        from six.moves._thread import get_ident
    except ImportError:
        from _thread import get_ident

__all__ = ["local", "Local", "get_ident"]


class Localbase(object):
    __slots__ = ("__storage__", "__ident_func__")

    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls, *args, **kwargs)
        object.__setattr__(self, "__storage__", {})
        object.__setattr__(self, "__ident_func__", get_ident)
        return self


class Local(Localbase):
    """
    线程局部存储类，继承自Localbase。

    内部维护线程/进程隔离的数据存储空间，通过唯一标识符（ident）实现不同线程间的数据隔离。
    支持属性访问、迭代操作和存储清理功能，确保多线程环境下数据访问的安全性。

    属性:
        __storage__ (dict): 嵌套字典存储结构，键为线程标识符，值为对应线程的数据字典
        __ident_func__ (callable): 获取当前线程/进程唯一标识符的函数
    """

    def __iter__(self):
        """
        获取当前线程/进程存储数据的迭代器。

        返回:
            iterator: 包含(key, value)元组的迭代器，若当前线程无存储数据则返回空迭代器

        处理流程:
            1. 获取当前线程唯一标识符
            2. 尝试返回对应存储字典的迭代器
            3. 捕获KeyError异常并返回空迭代器
        """
        ident = self.__ident_func__()
        try:
            return iter(list(self.__storage__[ident].items()))
        except KeyError:
            return iter([])

    def __release_local__(self):
        """
        释放当前线程/进程的本地存储空间。

        从存储字典中移除当前线程的标识符键值对，实现存储空间回收。
        该方法被clear()方法直接调用，也可在子类中单独调用。
        """
        self.__storage__.pop(self.__ident_func__(), None)

    def __getattr__(self, name):
        """
        获取线程局部变量的属性值。

        参数:
            name (str): 要获取的属性名称

        返回:
            any: 对应属性的值

        异常:
            AttributeError: 当指定属性不存在时抛出
        """
        ident = self.__ident_func__()
        try:
            return self.__storage__[ident][name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        """
        设置线程局部变量的属性值。

        参数:
            name (str): 要设置的属性名称
            value (any): 要设置的属性值

        异常:
            AttributeError: 当尝试修改只读属性(__storage__或__ident_func__)时抛出
        """
        if name in ("__storage__", "__ident_func__"):
            raise AttributeError("{!r} object attribute '{}' is read-only".format(self.__class__.__name__, name))

        ident = self.__ident_func__()
        storage = self.__storage__
        if ident not in storage:
            storage[ident] = dict()
        storage[ident][name] = value

    def __delattr__(self, name):
        """
        删除线程局部变量的属性。

        参数:
            name (str): 要删除的属性名称

        异常:
            AttributeError: 当尝试删除只读属性或不存在的属性时抛出
        """
        if name in ("__storage__", "__ident_func__"):
            raise AttributeError("{!r} object attribute '{}' is read-only".format(self.__class__.__name__, name))

        ident = self.__ident_func__()
        try:
            del self.__storage__[ident][name]
            if len(self.__storage__[ident]) == 0:
                self.__release_local__()
        except KeyError:
            raise AttributeError(name)

    def clear(self):
        """
        清空当前线程的所有局部存储数据。

        通过调用__release_local__()方法实现存储字典的完全释放，
        是释放线程资源的安全方式。
        """
        self.__release_local__()


local = Local()  # 创建Local类的实例


@contextmanager
def with_request_local():
    """
    上下文管理器用于临时隔离线程局部变量。

    在进入上下文时备份指定的线程局部变量，并在退出时恢复原始值。
    主要用于保护 'operator', 'username', 'current_request' 这些关键变量
    的上下文隔离，确保上下文执行期间对这些变量的修改不会影响外部作用域。

    Yields:
        local: 当前线程的局部变量对象（修改后的状态）
    """
    local_vars = {}
    for k in ["operator", "username", "current_request"]:
        if hasattr(local, k):
            local_vars[k] = getattr(local, k)
            delattr(local, k)

    try:
        yield local
    finally:
        for k, v in list(local_vars.items()):
            setattr(local, k, v)


@contextmanager
def with_client_user(username):
    """
    上下文管理器用于临时设置客户端用户名。

    在上下文执行期间将线程局部变量 local.username 设置为指定值，
    并在上下文退出后恢复原始值。通过组合使用 with_request_local 实现。

    Args:
        username: 需要临时设置的用户名（字符串或等效类型）

    Yields:
        None: 仅用于上下文管理器的上下文隔离
    """
    with with_request_local() as local:
        local.username = username
        yield


@contextmanager
def with_client_operator(update_user):
    """
    上下文管理器用于临时设置客户端操作员。

    在上下文执行期间将线程局部变量 local.operator 设置为指定值，
    并在上下文退出后恢复原始值。通过组合使用 with_request_local 实现。

    Args:
        update_user: 需要临时设置的操作员用户对象

    Yields:
        None: 仅用于上下文管理器的上下文隔离
    """
    with with_request_local() as local:
        local.operator = update_user
        yield
