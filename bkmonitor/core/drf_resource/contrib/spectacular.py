"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

drf-spectacular 扩展模块

为 ResourceViewSet 提供 OpenAPI 3.0 schema 生成支持。

使用方法
--------
在项目的 settings.py 中配置：

    INSTALLED_APPS = [
        # ...
        "drf_spectacular",
    ]

    REST_FRAMEWORK = {
        "DEFAULT_SCHEMA_CLASS": "core.drf_resource.contrib.spectacular.FaultTolerantAutoSchema",
    }

    SPECTACULAR_SETTINGS = {
        "TITLE": "BkMonitor API",
        "VERSION": "1.0.0",
        "DESCRIPTION": "BkMonitor API 文档",
        "SERVE_INCLUDE_SCHEMA": False,
        "PREPROCESSING_HOOKS": [
            "core.drf_resource.contrib.spectacular.preprocess_resource_routes",
        ],
    }
"""

import logging

from rest_framework.serializers import Serializer

logger = logging.getLogger(__name__)


# ============================================================================
# 容错 AutoSchema 类
# ============================================================================

try:
    from drf_spectacular.openapi import AutoSchema as _BaseAutoSchema

    _HAS_SPECTACULAR = True
except ImportError:
    from rest_framework.schemas.openapi import AutoSchema as _BaseAutoSchema

    _HAS_SPECTACULAR = False


class FaultTolerantAutoSchema(_BaseAutoSchema):
    """
    容错的 AutoSchema 类

    当生成 API 文档时遇到错误（如自定义 permission 类访问不存在的 request 属性），
    会记录警告日志并跳过该端点，而不是抛出异常导致整个文档生成失败。

    在 REST_FRAMEWORK 配置中设置：
    'DEFAULT_SCHEMA_CLASS': 'core.drf_resource.contrib.spectacular.FaultTolerantAutoSchema'
    """

    def get_operation(self, path, path_regex, path_prefix, method, registry):
        try:
            result = super().get_operation(path, path_regex, path_prefix, method, registry)
            if result:
                logger.debug(f"[drf-spectacular] 成功生成 schema: {method} {path}")
            return result
        except Exception as e:
            logger.warning(
                f"[drf-spectacular] 跳过端点 {method} {path}，生成 schema 时发生错误: {type(e).__name__}: {e}"
            )
            return None


# ============================================================================
# Schema 辅助函数
# ============================================================================


def get_resource_schema(view_cls, method: str, action: str):
    """
    从 ResourceViewSet 的 resource_routes 中提取对应 action 的 schema 信息
    """
    resource_routes = getattr(view_cls, "resource_routes", [])

    empty_endpoint_methods = {
        "GET": "list",
        "POST": "create",
        "PUT": "update",
        "PATCH": "partial_update",
        "DELETE": "destroy",
    }

    for route in resource_routes:
        if route.endpoint:
            route_action = route.endpoint
        else:
            if route.pk_field and route.method == "GET":
                route_action = "retrieve"
            else:
                route_action = empty_endpoint_methods.get(route.method, "")

        if route_action == action and route.method == method.upper():
            request_serializer = route.resource_class.RequestSerializer or Serializer
            response_serializer = route.resource_class.ResponseSerializer or Serializer
            description = str(route.resource_class.__doc__).strip() if route.resource_class.__doc__ else ""
            return {
                "request": request_serializer,
                "responses": {200: response_serializer},
                "description": description,
            }

    return None


def preprocess_resource_routes(endpoints, **kwargs):
    """
    drf-spectacular 预处理钩子

    为 ResourceViewSet 的动态端点添加 schema 信息。
    在 SPECTACULAR_SETTINGS['PREPROCESSING_HOOKS'] 中配置此函数。
    """
    try:
        from drf_spectacular.utils import extend_schema
    except ImportError:
        return endpoints

    from core.drf_resource.viewsets import ResourceViewSet

    processed = []
    for endpoint_tuple in endpoints:
        path, path_regex, method, callback = endpoint_tuple
        view_cls = getattr(callback, "cls", None)

        if view_cls and issubclass(view_cls, ResourceViewSet):
            actions = getattr(callback, "actions", {})
            action = actions.get(method.lower(), "")

            schema_info = get_resource_schema(view_cls, method, action)

            if schema_info:
                decorated_callback = extend_schema(
                    request=schema_info["request"],
                    responses=schema_info["responses"],
                    description=schema_info["description"],
                )(callback)
                processed.append((path, path_regex, method, decorated_callback))
                continue

        processed.append(endpoint_tuple)

    return processed


def generate_resource_schema_decorator(resource_route):
    """
    为单个 ResourceRoute 生成 extend_schema 装饰器
    """
    try:
        from drf_spectacular.utils import extend_schema
    except ImportError:
        return lambda f: f

    request_serializer = resource_route.resource_class.RequestSerializer or Serializer
    response_serializer = resource_route.resource_class.ResponseSerializer or Serializer
    description = str(resource_route.resource_class.__doc__).strip() if resource_route.resource_class.__doc__ else ""

    if resource_route.method == "GET":
        return extend_schema(
            parameters=[request_serializer],
            responses={200: response_serializer},
            description=description,
        )
    else:
        return extend_schema(
            request=request_serializer,
            responses={200: response_serializer},
            description=description,
        )


# ============================================================================
# 标签过滤 Schema 生成器
# ============================================================================

try:
    from drf_spectacular.generators import SchemaGenerator

    _HAS_SCHEMA_GENERATOR = True
except ImportError:
    SchemaGenerator = object
    _HAS_SCHEMA_GENERATOR = False


class FilterableSchemaGenerator(SchemaGenerator):
    """
    支持按标签（Tag）过滤的 Schema 生成器

    允许通过 tags 参数只生成包含指定标签的 API 端点的 schema，
    从而实现按需加载 API 文档，减少浏览器内存占用。
    """

    def __init__(self, *args, tags=None, path_prefix=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_tags = tags or []
        self.filter_prefix = path_prefix

    def parse(self, request, public):
        result = super().parse(request, public)

        if not self.filter_tags and not self.filter_prefix:
            return result

        filtered_paths = {}
        for path, path_item in result.items():
            if not isinstance(path_item, dict):
                continue

            filtered_operations = {}
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    filtered_operations[method] = operation
                    continue

                operation_tags = operation.get("tags", [])

                if self.filter_tags and not any(tag in self.filter_tags for tag in operation_tags):
                    continue

                filtered_operations[method] = operation

            if filtered_operations:
                filtered_paths[path] = filtered_operations

        logger.debug(
            f"[drf-spectacular] 标签过滤完成: "
            f"过滤标签={self.filter_tags}, "
            f"原始路径数={len(result)}, "
            f"过滤后路径数={len(filtered_paths)}"
        )

        return filtered_paths

    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request=request, public=public)

        # 添加路径前缀分组信息
        schema = self._add_path_prefix_grouping(schema)

        # 路径前缀过滤（必须在添加 x-path-prefix 之后）
        if self.filter_prefix:
            schema = self._filter_by_path_prefix(schema)

        if not self.filter_tags:
            return schema

        if "tags" in schema:
            schema["tags"] = [tag for tag in schema["tags"] if tag.get("name") in self.filter_tags]

        return schema

    def _add_path_prefix_grouping(self, schema):
        """
        为 schema 中的操作添加路径前缀分组信息

        根据配置项和 API 数量判断是否启用分组，
        并为每个操作添加 x-path-prefix 扩展字段。
        """
        from core.drf_resource.contrib.grouper import (
            PathPrefixGrouper,
            should_enable_grouping,
        )

        paths = schema.get("paths", {})
        if not paths:
            return schema

        # 按标签收集路径
        paths_by_tag = {}
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                operation_tags = operation.get("tags", ["未分类"])
                for tag in operation_tags:
                    if tag not in paths_by_tag:
                        paths_by_tag[tag] = []
                    paths_by_tag[tag].append(path)

        # 为每个标签计算分组
        tag_path_prefixes = {}
        for tag, tag_paths in paths_by_tag.items():
            unique_paths = list(set(tag_paths))
            if should_enable_grouping(len(unique_paths)):
                tag_path_prefixes[tag] = PathPrefixGrouper.group_paths_with_info(unique_paths)
                logger.debug(
                    f"[drf-spectacular] 标签 '{tag}' 启用路径前缀分组, "
                    f"API数量={len(unique_paths)}, "
                    f"分组数={len(set(tag_path_prefixes[tag].values()))}"
                )
            else:
                tag_path_prefixes[tag] = {p: None for p in unique_paths}

        # 为每个操作添加 x-path-prefix 扩展字段
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                operation_tags = operation.get("tags", ["未分类"])
                primary_tag = operation_tags[0] if operation_tags else "未分类"
                path_prefix = tag_path_prefixes.get(primary_tag, {}).get(path)
                operation["x-path-prefix"] = path_prefix

        return schema

    def _filter_by_path_prefix(self, schema):
        paths = schema.get("paths", {})
        filtered_paths = {}

        for path, path_item in paths.items():
            if not path.startswith(self.filter_prefix):
                continue
            if not isinstance(path_item, dict):
                continue
            filtered_paths[path] = path_item

        schema["paths"] = filtered_paths

        logger.debug(
            f"[drf-spectacular] 路径前缀过滤完成: "
            f"过滤前缀={self.filter_prefix}, "
            f"原始路径数={len(paths)}, "
            f"过滤后路径数={len(filtered_paths)}"
        )

        return schema


# ============================================================================
# Schema 视图与缓存
# ============================================================================

from hashlib import md5

from django.conf import settings
from django.core.cache import cache as django_cache

DEFAULT_SCHEMA_CACHE_TIMEOUT = 3600  # 1小时


def get_schema_cache_timeout():
    """获取 schema 缓存超时时间"""
    drf_resource_settings = getattr(settings, "DRF_RESOURCE", {})
    return drf_resource_settings.get("SCHEMA_CACHE_TIMEOUT", DEFAULT_SCHEMA_CACHE_TIMEOUT)


def get_docs_tag_threshold():
    """获取分组接口数量警告阈值"""
    drf_resource_settings = getattr(settings, "DRF_RESOURCE", {})
    return drf_resource_settings.get("DOCS_TAG_THRESHOLD", 100)


def generate_cache_key(prefix, *args):
    key_data = ":".join(str(arg) for arg in args if arg)
    hash_suffix = md5(key_data.encode()).hexdigest()[:12]
    return f"{prefix}:{hash_suffix}"


try:
    from drf_spectacular.views import SpectacularAPIView

    _HAS_SPECTACULAR_VIEWS = True
except ImportError:
    SpectacularAPIView = object
    _HAS_SPECTACULAR_VIEWS = False


class FilterableSpectacularAPIView(SpectacularAPIView):
    """
    支持标签过滤和缓存的 Schema API 视图

    查询参数：
    - tags: 逗号分隔的标签列表，如 ?tags=user,auth
    - prefix: 路径前缀过滤，如 ?prefix=/rest/v2/apm
    - refresh: 设置为 1 时强制刷新缓存
    - format: 输出格式 (json/yaml)
    """

    def _get_schema_generator_class(self):
        return FilterableSchemaGenerator

    def _get_tags_from_request(self, request):
        tags_param = request.query_params.get("tags", "")
        if tags_param:
            return [tag.strip() for tag in tags_param.split(",") if tag.strip()]
        return []

    def _get_prefix_from_request(self, request):
        return request.query_params.get("prefix", "").strip() or None

    def _should_refresh_cache(self, request):
        return request.query_params.get("refresh", "") == "1"

    def _get_cache_key(self, request, tags, path_prefix):
        tags_str = ",".join(sorted(tags)) if tags else "all"
        prefix_str = path_prefix or "all"
        format_type = request.query_params.get("format", "json")
        return generate_cache_key("bkmonitor:schema", tags_str, prefix_str, format_type)

    def _get_schema_response(self, request):
        from rest_framework.response import Response

        tags = self._get_tags_from_request(request)
        path_prefix = self._get_prefix_from_request(request)
        should_refresh = self._should_refresh_cache(request)
        cache_key = self._get_cache_key(request, tags, path_prefix)
        cache_timeout = get_schema_cache_timeout()

        logger.info(f"[drf-spectacular] Schema 请求: tags={tags}, prefix={path_prefix}, cache_key={cache_key}")

        if not should_refresh and cache_timeout > 0:
            cached_schema = django_cache.get(cache_key)
            if cached_schema is not None:
                logger.debug(f"[drf-spectacular] 返回缓存的 schema, paths 数量={len(cached_schema.get('paths', {}))}")
                return Response(data=cached_schema)

        generator_class = self._get_schema_generator_class()
        generator = generator_class(
            urlconf=self.urlconf,
            api_version=self.api_version,
            patterns=self.patterns,
            tags=tags,
            path_prefix=path_prefix,
        )

        schema = generator.get_schema(request=None, public=self.serve_public)

        logger.info(f"[drf-spectacular] 生成 schema 完成: paths 数量={len(schema.get('paths', {}))}")

        if cache_timeout > 0:
            django_cache.set(cache_key, schema, cache_timeout)

        return Response(data=schema)


# ============================================================================
# API 标签统计服务（含二级分组）
# ============================================================================


def _build_recursive_subgroups(paths_list, parent_prefix="", max_depth=5):
    """
    递归构建子分组，支持多级分组

    Args:
        paths_list: 路径列表
        parent_prefix: 父级前缀
        max_depth: 最大递归深度，防止无限递归

    Returns:
        list: 子分组列表，每个子分组包含 prefix, name, count, has_subgroups, subgroups
    """
    from core.drf_resource.contrib.grouper import (
        PathPrefixGrouper,
        should_enable_grouping,
    )

    if not paths_list or max_depth <= 0:
        return []

    # 使用 PathPrefixGrouper 进行分组
    groups = PathPrefixGrouper.group_paths_by_prefix(paths_list)

    # 如果只有一个分组且分组名等于父前缀，说明无法继续分组
    if len(groups) == 1:
        single_prefix = list(groups.keys())[0]
        if single_prefix == parent_prefix or not parent_prefix:
            return []

    result = []
    for prefix, group_paths in sorted(groups.items()):
        count = len(group_paths)

        # 从前缀中提取友好名称（取最后一级路径）
        name_parts = prefix.strip("/").split("/")
        friendly_name = name_parts[-1] if name_parts else prefix

        # 检查是否需要继续分组
        nested_subgroups = []
        has_nested_subgroups = False

        if should_enable_grouping(count) and max_depth > 1:
            # 递归检查是否需要更深层的分组
            nested_subgroups = _build_recursive_subgroups(group_paths, parent_prefix=prefix, max_depth=max_depth - 1)
            has_nested_subgroups = len(nested_subgroups) > 1  # 至少有2个子分组才有意义

        result.append(
            {
                "prefix": prefix,
                "name": friendly_name,
                "count": count,
                "has_subgroups": has_nested_subgroups,
                "subgroups": nested_subgroups if has_nested_subgroups else [],
            }
        )

    return result


def get_all_api_tags(request=None):
    """
    获取所有已注册 API 的标签信息，包括递归多级分组详情

    Returns:
        list: [{
            "name": "tag",
            "count": 123,
            "has_subgroups": True,
            "subgroup_count": 2,
            "subgroups": [
                {
                    "prefix": "/rest/v2",
                    "name": "v2",
                    "count": 536,
                    "has_subgroups": True,
                    "subgroups": [...]
                },
                ...
            ]
        }, ...]
    """
    from core.drf_resource.contrib.grouper import should_enable_grouping

    cache_key = "bkmonitor:api_tags_summary_v3"
    cache_timeout = get_schema_cache_timeout()

    cached_result = django_cache.get(cache_key)
    if cached_result is not None:
        logger.debug(f"[drf-spectacular] 从缓存获取 API 标签，共 {len(cached_result)} 个标签")
        return cached_result

    logger.info("[drf-spectacular] 开始生成 API schema...")
    generator = FilterableSchemaGenerator()
    try:
        schema = generator.get_schema(request=None, public=True)
    except Exception as e:
        logger.error(
            f"[drf-spectacular] 获取 API 标签时发生错误: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return []

    # 收集每个标签下的所有路径
    tags_paths = {}  # {tag: [path1, path2, ...]}
    tags_count = {}  # {tag: count}
    paths = schema.get("paths", {})
    logger.info(f"[drf-spectacular] schema 生成完成，共 {len(paths)} 个路径")

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if isinstance(operation, dict):
                operation_tags = operation.get("tags", ["未分类"])

                for tag in operation_tags:
                    tags_count[tag] = tags_count.get(tag, 0) + 1

                    # 收集该标签下的所有路径
                    if tag not in tags_paths:
                        tags_paths[tag] = []
                    if path not in tags_paths[tag]:
                        tags_paths[tag].append(path)

    # 获取 schema 中定义的标签描述
    schema_tags = {tag.get("name"): tag.get("description", "") for tag in schema.get("tags", [])}

    # 合并结果
    result = []
    for tag_name, count in sorted(tags_count.items()):
        tag_paths = tags_paths.get(tag_name, [])

        # 检查是否需要分组
        subgroups = []
        has_subgroups = False

        if should_enable_grouping(count) and len(tag_paths) > 1:
            # 递归构建子分组
            subgroups = _build_recursive_subgroups(tag_paths, max_depth=5)
            has_subgroups = len(subgroups) > 1  # 至少有2个子分组才有意义

        result.append(
            {
                "name": tag_name,
                "description": schema_tags.get(tag_name, ""),
                "count": count,
                "warning": count > get_docs_tag_threshold(),
                "has_subgroups": has_subgroups,
                "subgroup_count": len(subgroups) if has_subgroups else 0,
                "subgroups": subgroups if has_subgroups else [],
            }
        )

    logger.info(f"[drf-spectacular] 统计完成，共 {len(result)} 个 API 标签")

    if cache_timeout > 0 and result:
        django_cache.set(cache_key, result, cache_timeout)

    return result


def clear_schema_cache():
    """清除所有 schema 相关的缓存"""
    django_cache.delete("bkmonitor:api_tags_summary_v1")
    django_cache.delete("bkmonitor:api_tags_summary_v2")
    django_cache.delete("bkmonitor:api_tags_summary_v3")
    logger.info("[drf-spectacular] Schema 缓存已清除")


# ============================================================================
# 文档视图
# ============================================================================

from django.http import JsonResponse
from django.views.generic import TemplateView

try:
    from drf_spectacular.views import SpectacularSwaggerView

    _HAS_SWAGGER_VIEW = True
except ImportError:
    SpectacularSwaggerView = TemplateView
    _HAS_SWAGGER_VIEW = False


class FilterableSwaggerView(SpectacularSwaggerView):
    """
    支持标签过滤的 Swagger UI 视图
    """

    def _get_schema_url(self, request):
        schema_url = super()._get_schema_url(request)
        tags = request.GET.get("tags", "")
        if tags:
            separator = "&" if "?" in schema_url else "?"
            schema_url = f"{schema_url}{separator}tags={tags}"
        return schema_url

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if hasattr(response, "data") and isinstance(response.data, dict):
            response.data["tags"] = request.GET.get("tags", "")
        return response


class ApiTagsView(TemplateView):
    """
    API 标签统计接口

    返回所有可用标签及其接口数量的 JSON 数据
    """

    def get(self, request, *args, **kwargs):
        tags = get_all_api_tags()
        return JsonResponse({"tags": tags, "threshold": get_docs_tag_threshold()})


class ApiDocsView(TemplateView):
    """
    API 文档页面

    采用左侧分组导航 + 中间 API 列表的双栏布局，支持：
    - API 搜索
    - HTTP 方法快捷过滤
    - 点击 API 跳转到 Swagger UI 详情页
    """

    template_name = "spectacular/api_docs.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.urls import reverse

        context["tags_url"] = reverse("api-tags")
        context["schema_url"] = reverse("schema")
        context["swagger_url"] = reverse("swagger-ui")
        return context


try:
    from drf_spectacular.views import SpectacularRedocView

    _HAS_REDOC_VIEW = True
except ImportError:
    from django.views.generic import TemplateView as SpectacularRedocView

    _HAS_REDOC_VIEW = False


class FilterableSpectacularRedocView(SpectacularRedocView):
    """
    支持缓存和标签过滤的 ReDoc UI 视图
    """

    def _get_schema_url(self, request):
        schema_url = super()._get_schema_url(request)

        tags = request.GET.get("tags", "")
        prefix = request.GET.get("prefix", "")
        refresh = request.GET.get("refresh", "")
        format_type = request.GET.get("format", "json")

        params = []
        if tags:
            params.append(f"tags={tags}")
        if prefix:
            params.append(f"prefix={prefix}")
        if refresh:
            params.append(f"refresh={refresh}")
        if format_type:
            params.append(f"format={format_type}")

        if params:
            separator = "?" if "?" not in schema_url else "&"
            schema_url = schema_url + separator + "&".join(params)

        return schema_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tags"] = self.request.GET.get("tags", "")
        context["prefix"] = self.request.GET.get("prefix", "")
        return context
