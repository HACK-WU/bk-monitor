"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

路径前缀分组器

根据 URL 路径前缀对 API 路径进行分组，用于当某个 tag 下的 API 数量超过阈值时，
自动按路径前缀生成二级分组。
"""

import logging
from collections import defaultdict

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_path_prefix_threshold():
    """获取启用路径前缀分组的 API 数量阈值"""
    drf_resource_settings = getattr(settings, "DRF_RESOURCE", {})
    return drf_resource_settings.get("DOCS_PATH_PREFIX_THRESHOLD", 50)


def _is_path_prefix_grouping_enabled():
    """检查是否启用了路径前缀分组"""
    drf_resource_settings = getattr(settings, "DRF_RESOURCE", {})
    return drf_resource_settings.get("DOCS_PATH_PREFIX_GROUPING_ENABLED", True)


def should_enable_grouping(count):
    """
    根据 API 数量判断是否应该启用路径前缀分组

    Args:
        count: API 数量

    Returns:
        bool: 是否应该启用分组
    """
    if not _is_path_prefix_grouping_enabled():
        return False
    return count > _get_path_prefix_threshold()


class PathPrefixGrouper:
    """
    路径前缀分组器

    根据 URL 路径的公共前缀将路径列表分组。
    例如：
        /rest/v2/action/list
        /rest/v2/action/detail
        /rest/v2/apm/meta/list
        /rest/v2/apm/meta/detail

    会被分组为：
        /rest/v2/action -> [/rest/v2/action/list, /rest/v2/action/detail]
        /rest/v2/apm    -> [/rest/v2/apm/meta/list, /rest/v2/apm/meta/detail]
    """

    @staticmethod
    def _get_path_parts(path):
        """将路径分割为部分"""
        return [p for p in path.strip("/").split("/") if p]

    @staticmethod
    def _find_grouping_depth(paths_parts):
        """
        找到合适的分组深度

        通过找到路径开始分叉的层级来确定分组前缀的深度。
        """
        if not paths_parts:
            return 0

        min_len = min(len(parts) for parts in paths_parts)
        if min_len <= 1:
            return 0

        # 找到第一个有多个不同值的层级
        for depth in range(min_len):
            unique_values = set(parts[depth] for parts in paths_parts)
            if len(unique_values) > 1:
                return depth

        return min_len - 1

    @classmethod
    def group_paths_by_prefix(cls, paths_list):
        """
        按路径前缀将路径列表分组

        Args:
            paths_list: 路径列表，如 ["/rest/v2/action/list", "/rest/v2/apm/meta/list"]

        Returns:
            dict: {prefix: [paths]}，如 {"/rest/v2/action": [...], "/rest/v2/apm": [...]}
        """
        if not paths_list:
            return {}

        paths_parts = [cls._get_path_parts(path) for path in paths_list]
        grouping_depth = cls._find_grouping_depth(paths_parts)

        groups = defaultdict(list)
        for path, parts in zip(paths_list, paths_parts):
            if len(parts) > grouping_depth + 1:
                # 使用 grouping_depth + 1 层作为分组前缀
                prefix = "/" + "/".join(parts[: grouping_depth + 1])
            else:
                # 路径太短，使用整个路径作为前缀
                prefix = "/" + "/".join(parts[:-1]) if len(parts) > 1 else path
            groups[prefix].append(path)

        return dict(groups)

    @classmethod
    def group_paths_with_info(cls, paths_list):
        """
        返回每个路径对应的分组前缀

        Args:
            paths_list: 路径列表

        Returns:
            dict: {path: prefix}，如 {"/rest/v2/action/list": "/rest/v2/action"}
        """
        groups = cls.group_paths_by_prefix(paths_list)
        result = {}
        for prefix, paths in groups.items():
            for path in paths:
                result[path] = prefix
        return result
