"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import logging
import operator
import time

from collections import defaultdict
from functools import reduce
from typing import Any

from elasticsearch_dsl import Q, Search
from elasticsearch_dsl.response import Response

from bkmonitor.documents.alert import AlertDocument
from bkmonitor.documents.issue import IssueDocument
from bkmonitor.utils.time_tools import hms_string
from constants.alert import EVENT_STATUS_DICT, EventStatus
from constants.issue import ImpactScopeDimension, IssuePriority, IssueStatus
from fta_web.alert.handlers.base import BaseBizQueryHandler, BaseQueryTransformer, QueryField
from fta_web.alert.handlers.translator import BizTranslator, StrategyTranslator

logger = logging.getLogger("fta_action.issue")


class IssueQueryTransformer(BaseQueryTransformer):
    """Issue ES 查询字段转换器"""

    VALUE_TRANSLATE_FIELDS = {
        "status": IssueStatus.CHOICES,
        "priority": IssuePriority.CHOICES,
    }
    doc_cls = IssueDocument

    query_fields = [
        QueryField("id", "Issue ID"),
        QueryField("name", "Issue 名称", agg_field="name.raw", is_char=True),
        QueryField("status", "状态"),
        QueryField("priority", "优先级"),
        QueryField("assignee", "负责人"),
        QueryField("strategy_id", "策略ID"),
        QueryField("strategy_name", "策略名称", agg_field="strategy_name.raw", is_char=True),
        QueryField("bk_biz_id", "业务ID"),
        QueryField("labels", "标签", is_char=True),
        QueryField("is_regression", "是否回归"),
        QueryField("alert_count", "告警数量"),
        QueryField("first_alert_time", "首次告警时间"),
        QueryField("last_alert_time", "最近告警时间"),
        QueryField("create_time", "创建时间"),
        QueryField("update_time", "更新时间"),
        QueryField("resolved_time", "解决时间"),
    ]


def add_dimension_display_name(impact_scope: dict) -> dict:
    """为 impact_scope 中每个维度添加 display_name 字段"""
    for dimension_key, dimension_data in impact_scope.items():
        if isinstance(dimension_data, dict):
            dimension_data["display_name"] = ImpactScopeDimension.get_display_name(dimension_key)
    return impact_scope


class IssueQueryHandler(BaseBizQueryHandler):
    """Issue 列表查询处理器"""

    query_transformer = IssueQueryTransformer

    MY_ISSUE_STATUS_NAME = "MY_ISSUE"
    NO_ASSIGNEE_STATUS_NAME = "NO_ASSIGNEE"

    def __init__(
        self,
        bk_biz_ids: list[int] = None,
        username: str = "",
        status: list[str] = None,
        start_time: int = None,
        end_time: int = None,
        ordering: list[str] = None,
        query_string: str = "",
        conditions: list = None,
        page: int = 1,
        page_size: int = 10,
        **kwargs,
    ):
        super().__init__(
            bk_biz_ids=bk_biz_ids,
            username=username,
            start_time=start_time,
            end_time=end_time,
            ordering=ordering,
            query_string=query_string,
            conditions=conditions,
            page=page,
            page_size=page_size,
            **kwargs,
        )
        self.status = [status] if isinstance(status, str) else status

        # 默认排序：活跃状态优先，同状态按更新时间倒序
        if not self.ordering:
            self.ordering = ["status", "-update_time"]

    def get_search_object(self, start_time: int = None, end_time: int = None, **kwargs) -> Search:
        start_time = start_time or self.start_time
        end_time = end_time or self.end_time

        # Issue 跨天存在，使用全量索引查询
        search_object = IssueDocument.search(all_indices=True)

        # 时间范围过滤：end_time → create_time, start_time → resolved_time
        if end_time:
            search_object = search_object.filter("range", create_time={"lte": end_time})
        if start_time:
            search_object = search_object.filter(
                Q("range", resolved_time={"gte": start_time}) | ~Q("exists", field="resolved_time")
            )

        # 业务权限过滤
        search_object = self.add_biz_condition(search_object)

        # 状态过滤（含虚拟状态）
        if self.status:
            queries = []
            for s in self.status:
                if s == self.MY_ISSUE_STATUS_NAME:
                    queries.append(Q("term", assignee=self.request_username))
                elif s == self.NO_ASSIGNEE_STATUS_NAME:
                    queries.append(~Q("exists", field="assignee"))

            if queries:
                combined = queries[0]
                for q in queries[1:]:
                    combined = combined | q
                search_object = search_object.filter(combined)

        return search_object

    def add_biz_condition(self, search_object):
        """业务权限过滤"""
        queries = []
        if self.authorized_bizs is not None and self.bk_biz_ids:
            # 有权限的业务直接过滤
            queries.append(Q("terms", bk_biz_id=[str(b) for b in self.authorized_bizs]))

        user_condition = Q("term", assignee=self.request_username)

        if not self.bk_biz_ids:
            # 不带业务信息时，只查与当前用户相关的 Issue
            queries.append(user_condition)

        if self.unauthorized_bizs and self.request_username:
            # 无权限的业务，需要同时是负责人才能看到
            queries.append(Q("terms", bk_biz_id=[str(b) for b in self.unauthorized_bizs]) & user_condition)

        if queries:
            return search_object.filter(reduce(operator.or_, queries))
        return search_object

    def search_raw(self, show_aggs: bool = False, show_dsl: bool = False) -> tuple[Response, dict | None]:
        search_object = self.get_search_object()
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object)
        search_object = self.add_ordering(search_object)
        search_object = self.add_pagination(search_object)

        if show_aggs:
            search_object = self.add_aggs(search_object)

        search_result = search_object.params(track_total_hits=True).execute()

        if show_dsl:
            return search_result, search_object.to_dict()

        return search_result, None

    def search(self, show_aggs: bool = False, show_dsl: bool = False) -> dict:
        exc = None
        try:
            search_result, dsl = self.search_raw(show_aggs=show_aggs, show_dsl=show_dsl)
        except Exception as e:
            logger.exception("search issues error: %s", e)
            search_result = self.make_empty_response()
            dsl = None
            exc = e

        issues = self.handle_hit_list(search_result)

        # 字段翻译
        StrategyTranslator().translate_from_dict(issues, "strategy_id", "strategy_name")
        BizTranslator().translate_from_dict(issues, "bk_biz_id", "bk_biz_name")

        # 批量查询关联告警趋势
        self.add_alert_trend(issues)

        result = {"issues": issues, "total": search_result.hits.total.value}

        if show_aggs:
            result["aggs"] = self.handle_aggs(search_result)

        if dsl:
            result["dsl"] = dsl

        if exc:
            exc.data = result
            raise exc

        return result

    def add_aggs(self, search_object: Search) -> Search:
        """高级筛选聚合"""
        search_object.aggs.bucket("priority", "terms", field="priority")
        search_object.aggs.bucket("status", "terms", field="status")
        search_object.aggs.bucket(
            "assignee",
            "filters",
            filters={
                "my_assignee": Q("term", assignee=self.request_username),
                "no_assignee": (~Q("exists", field="assignee")),
            },
        )
        search_object.aggs.bucket("is_regression", "terms", field="is_regression")
        return search_object

    def handle_aggs(self, search_result: Response) -> list[dict]:
        """解析聚合结果为前端所需格式"""
        if not search_result.aggs:
            return []

        aggs = []
        status_display = dict(IssueStatus.CHOICES)
        priority_display = dict(IssuePriority.CHOICES)

        # 优先级聚合
        priority_buckets = []
        for bucket in search_result.aggs.priority.buckets:
            priority_buckets.append(
                {
                    "id": bucket.key,
                    "name": str(priority_display.get(bucket.key, bucket.key)),
                    "count": bucket.doc_count,
                }
            )
        aggs.append(
            {
                "id": "priority",
                "name": "优先级",
                "count": search_result.hits.total.value,
                "children": priority_buckets,
            }
        )

        # 状态聚合
        status_buckets = []
        for bucket in search_result.aggs.status.buckets:
            status_buckets.append(
                {
                    "id": bucket.key,
                    "name": str(status_display.get(bucket.key, bucket.key)),
                    "count": bucket.doc_count,
                }
            )
        aggs.append(
            {
                "id": "status",
                "name": "状态",
                "count": search_result.hits.total.value,
                "children": status_buckets,
            }
        )

        # 负责人聚合
        assignee_agg = search_result.aggs.assignee
        assignee_children = [
            {"id": "my_assignee", "name": "我负责的", "count": assignee_agg.buckets.my_assignee.doc_count},
            {"id": "no_assignee", "name": "未分配", "count": assignee_agg.buckets.no_assignee.doc_count},
        ]
        aggs.append(
            {
                "id": "assignee",
                "name": "负责人",
                "count": search_result.hits.total.value,
                "children": assignee_children,
            }
        )

        # 类型聚合（是否回归）
        regression_buckets = []
        for bucket in search_result.aggs.is_regression.buckets:
            key_str = str(bucket.key).lower()
            name = "回归问题" if key_str in ("true", "1") else "新问题"
            regression_buckets.append(
                {
                    "id": key_str,
                    "name": name,
                    "count": bucket.doc_count,
                }
            )
        aggs.append(
            {
                "id": "is_regression",
                "name": "类型",
                "count": search_result.hits.total.value,
                "children": regression_buckets,
            }
        )

        return aggs

    @classmethod
    def clean_document(cls, doc: Any) -> dict:
        """数据清洗：从 ES Hit 中提取并格式化字段"""
        if isinstance(doc, dict):
            data = doc
        else:
            data = doc.to_dict()

        cleaned = {}

        # 固定字段
        for field in cls.query_transformer.query_fields:
            cleaned[field.field] = field.get_value_by_es_field(data)

        # 计算字段
        now = int(time.time())
        create_time = cleaned.get("create_time")
        resolved_time = cleaned.get("resolved_time")

        if create_time:
            if resolved_time:
                duration_seconds = int(resolved_time) - int(create_time)
            else:
                duration_seconds = now - int(create_time)
            cleaned["duration"] = hms_string(max(duration_seconds, 0))
        else:
            cleaned["duration"] = "--"

        status_display = dict(IssueStatus.CHOICES)
        priority_display = dict(IssuePriority.CHOICES)
        cleaned["status_display"] = str(status_display.get(cleaned.get("status"), cleaned.get("status", "")))
        cleaned["priority_display"] = str(priority_display.get(cleaned.get("priority"), cleaned.get("priority", "")))
        cleaned["is_resolved"] = resolved_time is not None

        # impact_scope 添加 display_name
        impact_scope = data.get("impact_scope") or {}
        cleaned["impact_scope"] = add_dimension_display_name(impact_scope)

        # aggregate_config 直接透传
        cleaned["aggregate_config"] = data.get("aggregate_config") or {}

        return cleaned

    @classmethod
    def handle_hit(cls, hit: Any) -> dict:
        return cls.clean_document(hit)

    @classmethod
    def _build_empty_trend(cls, issue: dict) -> list:
        """根据 issue 的时间边界生成全零时间序列。"""
        first_alert_time = issue.get("first_alert_time")
        last_alert_time = issue.get("last_alert_time")
        if not first_alert_time or not last_alert_time:
            return []
        interval = cls.calculate_agg_interval(int(first_alert_time), int(last_alert_time))
        start = int(first_alert_time) // interval * interval
        end = int(last_alert_time) // interval * interval + interval
        now_aligned = int(time.time()) // interval * interval + interval
        end = min(end, now_aligned)
        return [[ts * 1000, 0] for ts in range(start, end, interval)]

    def add_alert_trend(self, issues: list[dict]) -> None:
        """
        一次 ES 聚合查询，为每个 Issue 填充 trend、alert_count 和 anomaly_message。

        核心算法复刻自 AlertHandler.date_histogram 的三路聚合：
        1. end_time 路：已结束告警按 end_time 做直方图，区分 RECOVERED/CLOSED
        2. begin_time 路：新产生告警按 begin_time 做直方图
        3. init_alert 路：查询范围之前已存在的异常告警数（初始基数）
        滚动计算：ABNORMAL[t] = ABNORMAL[t-1] + 新增[t] - 恢复[t] - 关闭[t]

        列表场景下，各 Issue 的告警时间跨度不同，因此：
        - ES 查询使用全局最细粒度 interval（保证数据精度不丢失）
        - 每个 issue 桶内额外聚合 min/max begin_time，得到各自的实际时间边界
        - 解析阶段根据各自时间边界重新计算 interval，对 histogram 桶做合并重采样
        """
        issue_ids = [issue["id"] for issue in issues if issue.get("id")]
        if not issue_ids:
            return

        first_alert_times = [issue["first_alert_time"] for issue in issues if issue.get("first_alert_time")]
        last_alert_times = [issue["last_alert_time"] for issue in issues if issue.get("last_alert_time")]

        if not first_alert_times or not last_alert_times:
            for issue in issues:
                issue["trend"] = self._build_empty_trend(issue)
                issue["alert_count"] = 0
                issue["anomaly_message"] = "--"
            return

        # 全局使用最细粒度 interval（取最短时间跨度的 Issue 对应的 interval）
        global_interval = min(
            self.calculate_agg_interval(int(ft), int(lt))
            for ft, lt in zip(
                [issue["first_alert_time"] for issue in issues if issue.get("first_alert_time")],
                [issue["last_alert_time"] for issue in issues if issue.get("last_alert_time")],
            )
        )

        # 时间对齐（使用全局最早/最晚时间）
        start_time = int(min(first_alert_times)) // global_interval * global_interval
        end_time = int(max(last_alert_times)) // global_interval * global_interval + global_interval

        # 构建 AlertDocument 查询，按 issue_id 过滤
        search_object = AlertDocument.search(start_time=start_time, end_time=end_time)
        search_object = search_object.filter("terms", issue_id=issue_ids)

        # 按 issue_id 分桶，桶内构建三路聚合
        issue_agg = search_object.aggs.bucket("issues", "terms", field="issue_id", size=len(issue_ids))
        self._build_alert_trend_aggs(issue_agg, start_time, end_time, global_interval)

        try:
            search_result = search_object[:0].execute()
        except Exception:
            logger.exception("add_alert_trend: ES aggregation failed")
            for issue in issues:
                issue["trend"] = self._build_empty_trend(issue)
                issue["alert_count"] = 0
                issue["anomaly_message"] = "--"
            return

        # 解析聚合结果：每个 issue 桶根据自身时间边界重新计算 interval 并重采样
        # 列表场景不区分状态，只需要一条趋势线
        trend_map = {}
        count_map = {}
        msg_map = {}

        if not search_result.aggs or not hasattr(search_result.aggs, "issues"):
            for issue in issues:
                issue["trend"] = self._build_empty_trend(issue)
                issue["alert_count"] = 0
                issue["anomaly_message"] = "--"
            return

        for issue_bucket in search_result.aggs.issues.buckets:
            issue_id = issue_bucket.key
            trend_data, alert_count, anomaly_message = self._parse_alert_trend_bucket(
                issue_bucket, start_time, end_time, global_interval, status_group=False
            )
            trend_map[issue_id] = trend_data
            count_map[issue_id] = alert_count
            msg_map[issue_id] = anomaly_message

        # 回填到 Issue 列表
        for issue in issues:
            issue_id = issue["id"]
            issue["trend"] = trend_map.get(issue_id) or self._build_empty_trend(issue)
            issue["alert_count"] = count_map.get(issue_id, 0)
            issue["anomaly_message"] = msg_map.get(issue_id, "--")

    @classmethod
    def get_single_issue_alert_trend(
        cls, issue_id: str, first_alert_time: int, last_alert_time: int, status_group: bool = True
    ) -> dict:
        """
        单个 Issue 的告警趋势查询（详情页场景），不按 issue_id 分桶，直接在顶层做三路聚合。

        参数:
            status_group: 是否按状态分组返回趋势数据，默认 True
                - True: trend 为 {状态: [[ts, count], ...]} 字典
                - False: trend 为 [[ts, count], ...] 列表（仅 ABNORMAL 存量快照）

        返回: {"trend": ..., "alert_count": int, "anomaly_message": str}
        """
        default_trend = {status: [] for status in EVENT_STATUS_DICT} if status_group else []
        default_result = {"trend": default_trend, "alert_count": 0, "anomaly_message": "--"}

        if not first_alert_time or not last_alert_time:
            return default_result

        interval = cls.calculate_agg_interval(int(first_alert_time), int(last_alert_time))

        start_time = int(first_alert_time) // interval * interval
        end_time = int(last_alert_time) // interval * interval + interval

        # 构建查询，直接按单个 issue_id 过滤，无需分桶
        search_object = AlertDocument.search(start_time=start_time, end_time=end_time)
        search_object = search_object.filter("term", issue_id=issue_id)

        # 直接在顶层 aggs 上构建三路聚合
        cls._build_alert_trend_aggs(search_object.aggs, start_time, end_time, interval)

        try:
            search_result = search_object[:0].execute()
        except Exception:
            logger.exception("get_single_issue_alert_trend: ES aggregation failed, issue_id=%s", issue_id)
            return default_result

        # 详情场景：interval 就是精确值，无需重采样
        trend_data, alert_count, anomaly_message = cls._parse_alert_trend_bucket(
            search_result.aggs, start_time, end_time, interval, status_group=status_group
        )
        return {"trend": trend_data, "alert_count": alert_count, "anomaly_message": anomaly_message}

    @staticmethod
    def _build_alert_trend_aggs(agg_node, start_time: int, end_time: int, interval: int) -> None:
        """
        在指定的聚合节点上构建三路聚合 + alert_count + latest_alert + min/max 时间边界。
        列表场景传入 issue_id 桶节点，详情场景传入顶层 aggs 节点。
        """
        # 第一路：已结束告警，按 end_time 做直方图，再按 status 分桶
        agg_node.bucket("end_time", "filter", {"range": {"end_time": {"lte": end_time}}}).bucket(
            "end_alert", "filter", {"terms": {"status": [EventStatus.RECOVERED, EventStatus.CLOSED]}}
        ).bucket("time", "date_histogram", field="end_time", fixed_interval=f"{interval}s").bucket(
            "status", "terms", field="status"
        )

        # 第二路：查询范围内新产生的告警，按 begin_time 做直方图
        agg_node.bucket("begin_time", "filter", {"range": {"begin_time": {"gte": start_time, "lte": end_time}}}).bucket(
            "time", "date_histogram", field="begin_time", fixed_interval=f"{interval}s"
        )

        # 第三路：查询范围之前已存在的异常告警数（初始基数）
        agg_node.bucket("init_alert", "filter", {"range": {"begin_time": {"lt": start_time}}})

        # 桶内告警时间边界（用于解析阶段按各 Issue 自身时间范围重新计算 interval）
        agg_node.metric("min_alert_time", "min", field="begin_time")
        agg_node.metric("max_alert_time", "max", field="begin_time")

        # alert_count：精确文档计数
        agg_node.metric("alert_count", "value_count", field="id")

        # anomaly_message：最新告警的 description
        agg_node.metric(
            "latest_alert",
            "top_hits",
            size=1,
            sort=[{"begin_time": {"order": "desc"}}],
            _source=["event.description"],
        )

    @classmethod
    def _parse_alert_trend_bucket(
        cls, bucket, start_time: int, end_time: int, global_interval: int, status_group: bool = False
    ) -> tuple:
        """
        从单个聚合桶中解析三路聚合结果，返回 (trend_data, alert_count, anomaly_message)。

        参数:
            bucket: issue_id 分桶的子桶（列表场景）或顶层 aggs（详情场景）
            global_interval: ES date_histogram 使用的步长（全局最细粒度）
            status_group: 是否按状态分组返回
                - True: trend_data 为 {状态: [[ts, count], ...]}，ABNORMAL 为存量快照，RECOVERED/CLOSED 为增量
                - False: trend_data 为 [[ts, count], ...]，仅 ABNORMAL 存量快照
        """
        now_time = int(time.time())

        # 从桶内 min/max 聚合获取该 Issue 的实际告警时间边界
        issue_min_time = None
        issue_max_time = None
        if hasattr(bucket, "min_alert_time") and bucket.min_alert_time.value is not None:
            issue_min_time = int(bucket.min_alert_time.value)
        if hasattr(bucket, "max_alert_time") and bucket.max_alert_time.value is not None:
            issue_max_time = int(bucket.max_alert_time.value)

        # 根据该 Issue 自身的时间跨度计算最合适的 interval
        if issue_min_time and issue_max_time:
            issue_interval = cls.calculate_agg_interval(issue_min_time, issue_max_time)
        else:
            issue_interval = global_interval

        # 确保 issue_interval 是 global_interval 的整数倍（向上取整对齐）
        if issue_interval < global_interval:
            issue_interval = global_interval
        elif issue_interval % global_interval != 0:
            issue_interval = ((issue_interval // global_interval) + 1) * global_interval

        # === 第一步：解析 ES 桶数据，直接按 issue_interval 对齐归桶 ===
        # 将 global_interval 粒度的 ES 桶直接聚合到 issue_interval 粒度，避免双重循环
        agg_abnormal = defaultdict(int)
        agg_recovered = defaultdict(int)
        agg_closed = defaultdict(int)

        # 解析第二路：新产生的异常告警，按 issue_interval 对齐
        if hasattr(bucket, "begin_time") and hasattr(bucket.begin_time, "time"):
            for tb in bucket.begin_time.time.buckets:
                ts_sec = int(tb.key_as_string)
                aligned_ts = ts_sec // issue_interval * issue_interval * 1000
                agg_abnormal[aligned_ts] += tb.doc_count

        # 解析第一路：已结束的告警（恢复/关闭），按 issue_interval 对齐
        if (
            hasattr(bucket, "end_time")
            and hasattr(bucket.end_time, "end_alert")
            and hasattr(bucket.end_time.end_alert, "time")
        ):
            for tb in bucket.end_time.end_alert.time.buckets:
                ts_sec = int(tb.key_as_string)
                aligned_ts = ts_sec // issue_interval * issue_interval * 1000
                for sb in tb.status.buckets:
                    if sb.key == EventStatus.RECOVERED:
                        agg_recovered[aligned_ts] += sb.doc_count
                    elif sb.key == EventStatus.CLOSED:
                        agg_closed[aligned_ts] += sb.doc_count

        # 解析第三路：初始基数
        init_count = 0
        if hasattr(bucket, "init_alert"):
            init_count = bucket.init_alert.doc_count

        # === 第二步：单层遍历，滚动计算趋势数据 ===
        if issue_min_time and issue_max_time:
            trend_start = issue_min_time // issue_interval * issue_interval
            trend_end = issue_max_time // issue_interval * issue_interval + issue_interval
        else:
            trend_start = start_time
            trend_end = end_time

        now_aligned = now_time // issue_interval * issue_interval + issue_interval
        trend_end = min(trend_end, now_aligned)

        current = init_count
        if status_group:
            trend_data = {status: [] for status in EVENT_STATUS_DICT}
        else:
            trend_data = []

        for ts_sec in range(trend_start, trend_end, issue_interval):
            ts_ms = ts_sec * 1000
            window_abnormal = agg_abnormal.get(ts_ms, 0)
            window_recovered = agg_recovered.get(ts_ms, 0)
            window_closed = agg_closed.get(ts_ms, 0)

            current = current + window_abnormal - window_recovered - window_closed

            if status_group:
                trend_data[EventStatus.ABNORMAL].append([ts_ms, current])
                trend_data[EventStatus.RECOVERED].append([ts_ms, window_recovered])
                trend_data[EventStatus.CLOSED].append([ts_ms, window_closed])
            else:
                trend_data.append([ts_ms, current])

        # alert_count
        alert_count = int(bucket.alert_count.value) if hasattr(bucket, "alert_count") else 0

        # anomaly_message
        anomaly_message = "--"
        if hasattr(bucket, "latest_alert") and bucket.latest_alert:
            hits = bucket.latest_alert.hits
            if hits and hits.hits and len(hits.hits) > 0:
                source = hits.hits[0].to_dict().get("_source", {})
                event = source.get("event", {})
                description = event.get("description", "") if isinstance(event, dict) else ""
                if description:
                    anomaly_message = description

        return trend_data, alert_count, anomaly_message
