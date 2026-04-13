"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import collections
import logging

from rest_framework.viewsets import ModelViewSet

from bkmonitor.documents import ActionInstanceDocument, AlertDocument
from bkmonitor.iam import ActionEnum
from bkmonitor.iam.drf import BusinessActionPermission
from bkmonitor.views.renderers import PlainTextRenderer
from core.drf_resource import resource
from core.drf_resource.viewsets import ResourceRoute, ResourceViewSet
from core.errors.iam import PermissionDeniedError
from fta_web.alert.serializers import SearchFavoriteSerializer
from fta_web.models.alert import SearchFavorite

logger = logging.getLogger(__name__)


class AlertViewSet(ResourceViewSet):
    def check_alert_permission(self):
        """
        基于告警关联人员的细粒度权限校验（绕过 IAM 业务权限）

        返回值:
            True  — 当前用户对目标告警有访问权限
            False — 无权限或无法判断

        校验流程:
        1. 判断当前 action 是否在受理范围（读操作 / 写操作）内，不在则直接拒绝
        2. 从请求参数中提取告警 ID 列表（兼容 id / alert_id / ids / alert_ids 多种传参方式）
        3. 批量查询告警文档，收集每条告警的通知人(assignee)、负责人(appointee)、主管(supervisor)、关注人(follower)
        4. 优先判断用户是否为 assignee/appointee/supervisor：
           - 是 → 读写操作均放行
           - 否且为写操作 → 直接拒绝（写操作不支持 follower 降级）
        5. 读操作降级判断：用户是否为所有告警的 follower，是则放行
        """
        read_actions = [
            "alert/detail",
            "alert/get_experience",
            "alert/log",
            "event/search",
            "alert/event_count",
            "alert/related_info",
            "alert/extend_fields",
            "alert/graph_query",
            "event/date_histogram",
            "strategy_snapshot",
            "action/search",
        ]
        write_actions = [
            "alert/save_experience",
            "alert/ack",
            "event/top_n",
            "alert/feedback",
        ]
        all_actions = read_actions + write_actions
        if self.action not in all_actions:
            return False

        # 从请求参数提取出ID字段
        params = self.request.data or self.request.query_params
        if "id" in params:
            alert_ids = [params["id"]]
        elif "alert_id" in params:
            alert_ids = [params["alert_id"]]
        elif "ids" in params:
            alert_ids = params["ids"]
        elif "alert_ids" in params:
            alert_ids = params["alert_ids"]
        else:
            alert_ids = []

        if not alert_ids:
            return False

        # 通知人， 负责人,关注人在可以查看相关的告警
        alerts = AlertDocument.mget(alert_ids, fields=["assignee", "appointee", "supervisor", "follower"])

        if not alerts:
            return False

        username = self.request.user.username
        alerts_users = collections.defaultdict(list)
        alert_followers = collections.defaultdict(list)
        for alert in alerts:
            alerts_users[alert.id].extend(alert.assignee)
            alerts_users[alert.id].extend(alert.appointee)
            alerts_users[alert.id].extend(alert.supervisor)
            alert_followers[alert.id].extend(alert.follower)

        result = True
        for users in alerts_users.values():
            if username not in users:
                # 读权限的，设置result为False, 可以根据Follower进行下一步判断
                result = False
                break
        if result or self.action in write_actions:
            # 如果在负责人的权限下可以通过，直接返回
            # 如果当前操作为写操作，没有权限也可以直接返回
            return result

        # 查看信息的动作，根据关注人再进行一次处理
        for users in alert_followers.values():
            if username not in users:
                return False
        return True

    def check_action_permission(self):
        """
        基于处理动作执行人的细粒度权限校验（绕过 IAM 业务权限）

        返回值:
            True  — 当前用户是目标动作的执行人(operator)，有查看权限
            False — 无权限或无法判断

        校验流程:
        1. 仅受理 action/detail 和 action/detail/sub_actions 两个查看动作
        2. 从请求参数中提取动作 ID（兼容 id / parent_action_id 两种传参方式）
        3. 批量查询动作实例文档，逐条校验当前用户是否为 operator
        4. 任一动作的 operator 不包含当前用户即拒绝
        """
        if self.action not in [
            "action/detail",
            "action/detail/sub_actions",
        ]:
            return False
        # 从请求参数提取出ID字段
        params = self.request.data or self.request.query_params
        if "id" in params:
            action_ids = [params["id"]]
        elif "parent_action_id" in params:
            action_ids = [params["parent_action_id"]]
        else:
            action_ids = []

        if not action_ids:
            return False

        # 判断负责人是否在里面
        actions = ActionInstanceDocument.mget(action_ids, fields=["operator"])
        username = self.request.user.username

        if not actions:
            return False

        for action in actions:
            if username not in action.operator:
                return False
        return True

    def check_permissions(self, request):
        """
        覆写 DRF ViewSet 的权限校验入口，实现多层级权限降级策略

        参数:
            request: HttpRequest 对象

        校验流程:
        1. 白名单放行：search_history / list_index_by_host / validate_query_string / allowed_biz 无需鉴权
        2. IAM 业务权限校验：
           - alert/search 需要 VIEW_EVENT 或 VIEW_BUSINESS 权限（支持跨业务搜索场景）
           - 其余操作仅需 VIEW_EVENT 权限
        3. IAM 校验失败后的降级策略（按优先级依次尝试）：
           a. check_alert_permission  — 基于告警关联人员（通知人/负责人/关注人）放行
           b. check_action_permission — 基于动作执行人(operator)放行
           c. 列表类/统计类操作兜底   — 已登录用户对 search/top_n/export/date_histogram/tags 等
              聚合查询接口直接放行（这些接口内部会按业务过滤数据，不会越权）
        4. 以上均不满足则抛出 PermissionDeniedError
        """
        if self.action in [
            "search_history",
            "list_index_by_host",
            "validate_query_string",
            "generate_query_string",
            "allowed_biz",
        ]:
            return
        elif self.action == "alert/search":
            permission = BusinessActionPermission([ActionEnum.VIEW_EVENT, ActionEnum.VIEW_BUSINESS])
        else:
            permission = BusinessActionPermission([ActionEnum.VIEW_EVENT])

        try:
            permission.has_permission(request, self)
        except PermissionDeniedError as e:
            if self.check_alert_permission():
                return

            if self.check_action_permission():
                return

            if (
                self.action
                in [
                    "alert/search",
                    "alert/top_n",
                    "alert/export",
                    "alert/date_histogram",
                    "alert/tags",
                    "action/search",
                    "action/top_n",
                    "action/export",
                    "action/date_histogram",
                ]
                and self.request.user.username
            ):
                return

            raise e

    resource_routes = [
        ResourceRoute("GET", resource.alert.list_allowed_biz, endpoint="allowed_biz"),
        ResourceRoute("GET", resource.alert.list_search_history, endpoint="search_history"),
        ResourceRoute("POST", resource.alert.search_alert, endpoint="alert/search"),
        ResourceRoute("POST", resource.alert.export_alert, endpoint="alert/export"),
        ResourceRoute("POST", resource.alert.alert_date_histogram, endpoint="alert/date_histogram"),
        ResourceRoute("POST", resource.alert.list_alert_tags, endpoint="alert/tags"),
        ResourceRoute("GET", resource.alert.alert_detail, endpoint="alert/detail"),
        ResourceRoute("GET", resource.alert.get_experience, endpoint="alert/get_experience"),
        ResourceRoute("POST", resource.alert.save_experience, endpoint="alert/save_experience"),
        ResourceRoute("POST", resource.alert.delete_experience, endpoint="alert/delete_experience"),
        ResourceRoute("POST", resource.alert.list_alert_log, endpoint="alert/log"),
        ResourceRoute("POST", resource.alert.search_event, endpoint="event/search"),
        ResourceRoute("POST", resource.alert.alert_event_count, endpoint="alert/event_count"),
        ResourceRoute("POST", resource.alert.alert_related_info, endpoint="alert/related_info"),
        ResourceRoute("POST", resource.alert.alert_extend_fields, endpoint="alert/extend_fields"),
        ResourceRoute("POST", resource.alert.ack_alert, endpoint="alert/ack"),
        ResourceRoute("POST", resource.alert.alert_graph_query, endpoint="alert/graph_query"),
        ResourceRoute("POST", resource.alert.edit_data_meaning, endpoint="alert/edit_data_meaning"),
        ResourceRoute("POST", resource.alert.event_date_histogram, endpoint="event/date_histogram"),
        ResourceRoute("POST", resource.alert.search_action, endpoint="action/search"),
        ResourceRoute("GET", resource.alert.action_detail, endpoint="action/detail"),
        ResourceRoute("GET", resource.alert.sub_action_detail, endpoint="action/detail/sub_actions"),
        ResourceRoute("POST", resource.alert.export_action, endpoint="action/export"),
        ResourceRoute("POST", resource.alert.action_date_histogram, endpoint="action/date_histogram"),
        ResourceRoute("POST", resource.alert.validate_query_string, endpoint="validate_query_string"),
        ResourceRoute("POST", resource.alert.generate_query_string, endpoint="generate_query_string"),
        # 策略配置快照详情
        ResourceRoute("GET", resource.alert.strategy_snapshot, endpoint="strategy_snapshot"),
        ResourceRoute("POST", resource.alert.alert_top_n, endpoint="alert/top_n"),
        ResourceRoute("POST", resource.alert.action_top_n, endpoint="action/top_n"),
        ResourceRoute("POST", resource.alert.event_top_n, endpoint="event/top_n"),
        # 根据主机查询对应已下发的日志平台采集索引列表
        ResourceRoute("POST", resource.alert.list_index_by_host, endpoint="list_index_by_host"),
        # 告警反馈
        ResourceRoute("POST", resource.alert.feedback_alert, endpoint="alert/create_feedback"),
        ResourceRoute("GET", resource.alert.list_alert_feedback, endpoint="alert/list_feedback"),
        # 维度下钻
        ResourceRoute("GET", resource.alert.dimension_drill_down, endpoint="alert/dimension_drill_down"),
        # 指标推荐
        ResourceRoute("GET", resource.alert.metric_recommendation, endpoint="alert/metric_recommendation"),
        # 指标推荐反馈
        ResourceRoute(
            "POST", resource.alert.metric_recommendation_feedback, endpoint="alert/metric_recommendation_feedback"
        ),
        # 主机多指标异常检测告警详情图表
        ResourceRoute("GET", resource.alert.multi_anomaly_detect_graph, endpoint="alert/multi_anomaly_detect_graph"),
        # 业务统计相关接口
        ResourceRoute("GET", resource.alert.get_four_metrics_strategy, endpoint="alert/get_four_metrics_strategy"),
        ResourceRoute("GET", resource.alert.get_tmp_data, endpoint="alert/get_tmp_data"),
        ResourceRoute("GET", resource.alert.get_four_metrics_data, endpoint="alert/get_four_metrics_data"),
    ]


class QuickAlertHandleViewSet(ResourceViewSet):
    renderer_classes = [PlainTextRenderer]
    # 快捷操作
    resource_routes = [
        ResourceRoute("GET", resource.alert.quick_alert_shield, endpoint="alert/quick_shield"),
        ResourceRoute("GET", resource.alert.quick_alert_ack, endpoint="alert/quick_ack"),
    ]


class SearchFavoriteViewSet(ModelViewSet):
    serializer_class = SearchFavoriteSerializer

    def get_permissions(self):
        return []

    def get_queryset(self):
        queryset = SearchFavorite.objects.filter(create_user=self.request.user.username)
        search_type = self.request.query_params.get("search_type")
        if search_type is not None:
            queryset = queryset.filter(search_type=search_type)
        return queryset
