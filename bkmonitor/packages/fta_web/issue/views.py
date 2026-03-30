"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from core.drf_resource import resource
from core.drf_resource.viewsets import ResourceRoute, ResourceViewSet


class IssueViewSet(ResourceViewSet):
    """Issues 功能接口 ViewSet"""

    resource_routes = [
        # Issue 列表查询
        ResourceRoute("POST", resource.issue.search_issue, endpoint="issue/search"),
        # 指派负责人（含改派，支持批量）
        ResourceRoute("POST", resource.issue.assign_issue, endpoint="issue/assign"),
        # 标记为已解决（支持批量）
        ResourceRoute("POST", resource.issue.resolve_issue, endpoint="issue/resolve"),
        # 归档 Issue（实例级，支持批量）
        ResourceRoute("POST", resource.issue.archive_issue, endpoint="issue/archive"),
        # 修改优先级（支持批量）
        ResourceRoute("POST", resource.issue.update_issue_priority, endpoint="issue/update_priority"),
        # 添加跟进信息（支持批量）
        ResourceRoute("POST", resource.issue.add_issue_follow_up, endpoint="issue/add_follow_up"),
        # 查询变更记录(活动日志)
        ResourceRoute("GET", resource.issue.list_issue_activities, endpoint="issue/activities"),
    ]
