"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
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
    from _thread import get_ident

__all__ = ["local", "Local", "get_ident"]


class Localbase:
    __slots__ = ("__storage__", "__ident_func__")

    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls, *args, **kwargs)
        object.__setattr__(self, "__storage__", {})
        object.__setattr__(self, "__ident_func__", get_ident)
        return self


class Local(Localbase):
    """
    内部封装了一个嵌套字典：{ ident: {key: value, ...}, ... }
    ident是线程的标识符，key-value就是当前线程中保存的数据
    """

    # 定义迭代器方法，返回当前线程/进程的存储项的迭代器
    def __iter__(self):
        ident = self.__ident_func__()  # 获取当前线程/进程的唯一标识符
        try:
            return iter(list(self.__storage__[ident].items()))  # 尝试返回存储项的迭代器
        except KeyError:
            return iter([])  # 如果没有找到对应的存储项，则返回空迭代器

    # 定义释放本地存储的方法
    def __release_local__(self):
        self.__storage__.pop(self.__ident_func__(), None)  # 移除当前线程/进程的存储项

    # 定义获取属性的方法
    def __getattr__(self, name):
        ident = self.__ident_func__()  # 获取当前线程/进程的唯一标识符
        try:
            return self.__storage__[ident][name]  # 尝试返回指定名称的存储值
        except KeyError:
            raise AttributeError(name)  # 如果没有找到指定的属性，则抛出AttributeError异常

    # 定义设置属性的方法
    def __setattr__(self, name, value):
        if name in ("__storage__", "__ident_func__"):
            raise AttributeError(
                f"{self.__class__.__name__!r} object attribute '{name}' is read-only"
            )  # 如果设置的属性是只读的，则抛出AttributeError异常

        ident = self.__ident_func__()  # 获取当前线程/进程的唯一标识符
        storage = self.__storage__
        if ident not in storage:  # 如果当前线程/进程还没有存储项，则创建一个新的存储字典
            storage[ident] = dict()
        storage[ident][name] = value  # 设置指定名称的存储值

    # 定义删除属性的方法
    def __delattr__(self, name):
        if name in ("__storage__", "__ident_func__"):
            raise AttributeError(
                f"{self.__class__.__name__!r} object attribute '{name}' is read-only"
            )  # 如果删除的属性是只读的，则抛出AttributeError异常

        ident = self.__ident_func__()  # 获取当前线程/进程的唯一标识符
        try:
            del self.__storage__[ident][name]  # 尝试删除指定名称的存储项
            if len(self.__storage__[ident]) == 0:  # 如果当前线程/进程的存储字典为空，则释放存储
                self.__release_local__()
        except KeyError:
            raise AttributeError(name)  # 如果没有找到指定的属性，则抛出AttributeError异常

    # 定义清空存储的方法
    def clear(self):
        self.__release_local__()  # 调用释放本地存储的方法清空存储


local = Local()  # 创建Local类的实例


@contextmanager
def with_request_local():
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
    with with_request_local() as local:
        local.username = username
        yield


@contextmanager
def with_client_operator(update_user):
    with with_request_local() as local:
        local.operator = update_user
        yield
