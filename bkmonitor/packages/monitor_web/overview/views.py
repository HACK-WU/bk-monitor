"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import json
from collections.abc import Generator, Iterator
from typing import Any

from django.http import StreamingHttpResponse
from rest_framework import serializers, viewsets
from rest_framework.request import Request

from bkmonitor.utils.request import get_request_tenant_id
from core.drf_resource import resource
from core.drf_resource.viewsets import ResourceRoute, ResourceViewSet
from monitor_web.overview.search import Searcher


class SearchSerializer(serializers.Serializer):
    """
    搜索参数
    """

    query = serializers.CharField(label="搜索关键字")


class SearchViewSet(viewsets.GenericViewSet):
    """
    搜索, 使用多线程搜索，使用 event-stream 返回搜索结果
    """

    def unescape(self, query: str) -> str:
        """
        将 HTML 转义字符还原为原始字符
        Args:
            query: 包含 HTML 转义字符的原始查询字符串
        Returns:
            str: 反转义后的安全字符串
        """
        query = query.replace("&lt;", "<")
        query = query.replace("&gt;", ">")
        query = query.replace("&amp;", "&")
        query = query.replace("&quot;", '"')
        query = query.replace("&#39;", "'")
        query = query.replace("&nbsp;", " ")
        return query

    def list(self, request: Request, *args: Any, **kwargs: Any) -> StreamingHttpResponse:
        """
        处理搜索请求并返回流式响应
        Args:
            request: 包含查询参数的请求对象
        Returns:
            StreamingHttpResponse: 使用 text/event-stream 格式的流式响应
        """
        # 验证查询参数
        serializer = SearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        # 获取并清洗查询词
        query: str = serializer.validated_data["query"]
        query = self.unescape(query).strip()

        # 初始化搜索器并执行搜索
        searcher: Searcher = Searcher(bk_tenant_id=get_request_tenant_id(), username=request.user.username)
        result: Iterator[dict] = searcher.search(query)

        def event_stream() -> Generator[str, None, None]:
            """
            生成符合 SSE 规范的事件流
            Yields:
                str: 格式化的事件字符串，包含 start/data/end 三种事件类型
            """
            yield "event: start\n\n"  # 流开始标记
            for line in result:
                yield f"data: {json.dumps(line)}\n\n"  # 实时搜索结果数据
            yield "event: end\n\n"  # 流结束标记

        # 配置流式响应头
        sr = StreamingHttpResponse(event_stream(), content_type="text/event-stream")

        # 禁用客户端缓存
        # 对客户端的意义：浏览器每次使用缓存前必须向服务器验证有效性（发送 If-None-Match 头）
        # 对代理服务器的意义：禁止中间代理（如 CDN）缓存响应内容
        # 在 SSE 场景中的必要性：防止客户端或代理缓存事件流数据，确保实时性（若被缓存会导致事件流延迟或中断）
        sr.headers["Cache-Control"] = "no-cache"
        # 禁用 Nginx 代理缓冲
        # 默认行为：Nginx 代理会缓存整个响应直到后端关闭连接（默认 proxy_buffering=on）
        # 设置 no 的效果：
        #   -禁用代理层缓冲（相当于设置 proxy_buffering off）
        #   -实时传递数据块（立即转发 chunked 响应）
        # 对 SSE 的影响：若不设置该头，Nginx 可能积攒多个事件后才一次性推送给客户端，破坏实时性
        sr.headers["X-Accel-Buffering"] = "no"
        return sr


class FunctionShortcutViewSet(ResourceViewSet):
    """
    功能快捷入口
    """

    resource_routes = [
        ResourceRoute("POST", resource.overview.get_function_shortcut),
        ResourceRoute("POST", resource.overview.add_access_record, endpoint="add_access_record"),
    ]


class AlarmGraphConfigViewSet(ResourceViewSet):
    """
    首页告警图配置
    """

    resource_routes = [
        ResourceRoute("GET", resource.overview.get_alarm_graph_config),
        ResourceRoute("POST", resource.overview.save_alarm_graph_config),
        ResourceRoute("POST", resource.overview.delete_alarm_graph_config, endpoint="delete"),
        ResourceRoute("POST", resource.overview.save_alarm_graph_biz_index, endpoint="save_biz_index"),
    ]
