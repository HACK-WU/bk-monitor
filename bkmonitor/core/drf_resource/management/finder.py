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

import logging
import os

from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder

from core.drf_resource.management.exceptions import ErrorSettingsWithResourceDirs

logger = logging.getLogger(__name__)

DEFAULT_API_DIR = "api"
DEFAULT_RESOURCE_DIRS = []

API_DIR = getattr(settings, "API_DIR", DEFAULT_API_DIR)
# 也可以在settings.py中配置额外的resources模块目录，使用相对路径
RESOURCE_DIRS = getattr(settings, "RESOURCE_DIRS", DEFAULT_RESOURCE_DIRS)
if API_DIR not in RESOURCE_DIRS:
    RESOURCE_DIRS.append(API_DIR)


class ResourceFinder(BaseFinder):
    def __init__(self, app_names=None, *args, **kwargs):
        # Mapping of app names to resource modules
        self.resource_path = []
        app_path_directories = []
        app_configs = apps.get_app_configs()  # type: list["AppConfig"]
        if app_names:
            app_names = set(app_names)
            # 过滤只存在app_names的app_config
            app_configs = [ac for ac in app_configs if ac.name in app_names]

        # 查询每个应用的resources模块
        for app_config in app_configs:
            self.resource_path += self.find(app_config.path, root_path=os.path.dirname(app_config.path))
            app_path_directories.append(app_config.path)

        # 查询settings中配置的额外资源模块目录
        for path in RESOURCE_DIRS:
            search_path = os.path.join(settings.BASE_DIR, path)
            if search_path in app_path_directories:
                continue

            self.resource_path += self.find(search_path, from_settings=True)

        self.resource_path.sort()
        self.found()

    def found(self):
        p_list = []
        for path in self.resource_path:
            p_list.append(ResourcePath(path))

        self.resource_path = p_list

    def list(self, ignore_patterns):
        """
        List all resource path.
        """
        for path in self.resource_path:
            yield path.path, path.status

    def find(self, path, root_path=None, from_settings=False):
        """
        查找app应用目录下的resources模块。
        包括resources目录和resources.py文件以及default.py文件
        """
        # 初始化匹配集合，用于存储找到的资源模块路径
        matches = set()

        # 检查路径是否以settings.BASE_DIR开头，以确保查找的路径是有效的
        if not path.startswith(settings.BASE_DIR):
            # 如果路径无效且来自设置，则抛出异常
            if from_settings:
                raise ErrorSettingsWithResourceDirs("RESOURCE_DIRS settings error")
            # 如果路径无效且非来自设置，则直接返回空列表
            return []

        # 遍历指定路径下的所有目录和文件
        for root, dirs, files in sorted(os.walk(path)):
            # 跳过 __pycache__ 目录
            if os.path.basename(root) == "__pycache__":
                continue

            # 匹配resources目录
            # 如果当前目录名为"resources"，则将其相对路径转换为点分隔格式并添加到匹配集合中
            if os.path.basename(root) == "resources":
                # 获取到resources目录所在的相对路径，然后将其转换为点分隔格式，并添加到匹配集合中
                relative_path = os.path.relpath(os.path.dirname(root), root_path or settings.BASE_DIR)
                matches.add(self.path_to_dotted(relative_path))
                continue

            # 匹配resources.py文件以及default.py文件
            for file_path in files:
                file_name = os.path.basename(file_path)
                base_file_name, ext_name = os.path.splitext(file_name)

                # 如果文件名为"resources"或"default"，则将其所在目录的相对路径转换为点分隔格式并添加到匹配集合中
                if ext_name == ".py" and base_file_name in ["resources", "default"]:
                    relative_path = os.path.relpath(root, root_path or settings.BASE_DIR)
                    matches.add(self.path_to_dotted(relative_path))

        # 返回匹配集合作为结果
        return matches

    @staticmethod
    def path_to_dotted(path) -> str:
        """
        将文件路径转换为带点的字符串格式。

        此函数的目的是将一个文件系统路径转换为一个不包含路径分隔符的带点的字符串格式，
        常用于生成Python包的虚路径表示。

        参数:
        - path (str): 文件或目录的路径字符串。

        返回:
        - str: 转换后的带点的字符串格式路径。
        """
        # 使用os.sep来确保跨平台兼容性，移除空字符串以避免不必要的点
        return ".".join([p for p in path.split(os.sep) if p])


class ResourceStatus(object):
    # 待加载
    unloaded = "unloaded"
    # 加载成功
    loaded = "loaded"
    # 忽略
    ignored = "ignored"
    # 加载错误
    error = "error"


class ResourcePath(object):
    """
    path = ResourcePath("api.xxx")
    path.loaded()
    path.ignored()
    path.error()
    """

    def __init__(self, path):
        status = ResourceStatus.unloaded
        path_info = path.split(":")
        if len(path_info) > 1:
            rspath, status = path_info[:2]
        else:
            rspath = path_info[0]

        self.path = rspath.strip()
        self.status = status.strip()

    def __getattr__(self, item):
        status = getattr(ResourceStatus, item, None)
        if status:
            return status_setter(status)(lambda: status, self)

    def __repr__(self):
        return "{}: {}".format(self.path, self.status)


def status_setter(status):
    def setter(func, path):
        path.status = status
        return func

    return setter
