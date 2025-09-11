# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""


import six

__all__ = [
    "patch_all",
    "patch_module",
]


def patch_module(name, items=None):
    """
    动态修补指定模块，替换该模块中的某些属性或方法
    该代码源自 gevent.monkey.patch_module()
    
    :param name: 需要修补的模块名称
    :param items: 需要替换的属性或方法列表，如果为None，则从修补模块的__implements__中获取
    :return: 修补完成的模块
    """
    # 导入修补源模块，即包含修补代码的模块
    rt_module = __import__("patches." + name)
    # 导入目标模块，即需要修补的模块
    target_module = __import__(name)
    
    # 遍历模块名称的每个部分，以处理嵌套模块
    for i, submodule in enumerate(name.split(".")):
        # 逐级获取修补源模块的子模块
        rt_module = getattr(rt_module, submodule)
        # 如果不是第一个子模块，也以同样的方式获取目标模块的子模块
        if i:
            target_module = getattr(target_module, submodule)
    
    # 获取需要修补的项，如果没有指定，则尝试从修补源模块的__implements__中获取
    items = items or getattr(rt_module, "__implements__", None)
    # 如果修补项为空，则抛出异常
    if items is None:
        raise AttributeError("%r does not have __implements__" % rt_module)
    
    # 遍历修补项，替换目标模块中的相应属性或方法
    for attr in items:
        setattr(target_module, attr, getattr(rt_module, attr))
    
    # 返回修补完成的目标模块
    return target_module



def patch_all(targets=None):
    """
    targets = {
        'celery.utils.log': None,
    }
    """
    if not isinstance(targets, dict):
        targets = {}

    for module, items in six.iteritems(targets):
        patch_module(module, items=items)
