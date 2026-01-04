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
import logging
from datetime import datetime, timedelta
from typing import Any

import arrow
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from bkmonitor.data_source import load_data_source, filter_dict_to_q
from bkmonitor.data_source.unify_query.builder import QueryConfigBuilder, UnifyQuerySet
from bkmonitor.share.api_auth_resource import ApiAuthResource
from bkmonitor.utils.request import get_request_tenant_id
from constants.data_source import DataSourceLabel, DataTypeLabel, GrayUnifyQueryDataSources
from core.drf_resource import resource

logger = logging.getLogger(__name__)


class LogQueryResource(ApiAuthResource):
    """
    日志数据查询
    """

    class RequestSerializer(serializers.Serializer):
        data_format = serializers.CharField(label="数据格式", default="strategy")

        bk_biz_id = serializers.IntegerField(label="业务ID")
        data_source_label = serializers.CharField(label="数据来源")
        data_type_label = serializers.CharField(label="数据类型")

        query_string = serializers.CharField(default="", allow_blank=True)
        index_set_id = serializers.CharField(label="索引集ID", default="", allow_blank=True)
        alert_name = serializers.CharField(label="告警名称", required=False)
        bkmonitor_strategy_id = serializers.CharField(label="策略ID", required=False)

        result_table_id = serializers.CharField(label="结果表ID", default="", allow_blank=True)
        where = serializers.ListField(label="过滤条件", default=lambda: [])
        filter_dict = serializers.DictField(default=lambda: {})

        start_time = serializers.IntegerField(required=False, label="开始时间")
        end_time = serializers.IntegerField(required=False, label="结束时间")
        limit = serializers.IntegerField(label="查询条数", default=10)
        offset = serializers.IntegerField(label="查询偏移", default=0)

        @classmethod
        def to_str(cls, value):
            if isinstance(value, list):
                return [cls.to_str(v) for v in value if v or not isinstance(v, dict | list)]
            elif isinstance(value, dict):
                return {k: cls.to_str(v) for k, v in value.items() if v or not isinstance(v, dict | list)}
            else:
                return str(value)

        def validate(self, attrs):
            attrs["filter_dict"] = self.to_str(attrs["filter_dict"])
            # 过滤掉无效的 where 条件
            validated_where = []
            for condition in attrs.get("where", []):
                if not isinstance(condition, dict):
                    continue
                value = condition.get("value")
                # 过滤掉 value 为 None、空列表或只包含 None 的列表
                if value is None:
                    continue
                if isinstance(value, list):
                    # 移除列表中的 None，如果移除后列表为空则跳过该条件
                    filtered_value = [v for v in value if v is not None]
                    if not filtered_value:
                        continue
                    condition["value"] = filtered_value
                validated_where.append(condition)

            attrs["where"] = validated_where

            return attrs

    @staticmethod
    def table_format(data: list[dict], total: int, data_format: str = ""):
        """
        生成grafana table格式
        """
        dimensions = set()
        for row in data:
            for key in row:
                dimensions.add(key)

        if dimensions:
            dimensions.add("time")

        dimensions = ["time"] + sorted([d for d in dimensions if d != "time"])

        if data_format == "scene_view":
            return {
                "columns": [
                    {"name": _("时间"), "id": "time", "type": "time"},
                    {"name": _("事件名"), "id": "event_name", "type": "string"},
                    {"name": _("事件内容"), "id": "event.content", "type": "string"},
                    {"name": _("目标"), "id": "target", "type": "string"},
                ],
                "checkable": False,
                "data": data,
                "total": total,
            }
        else:
            return [
                {
                    "columns": [{"text": d, "type": "time" if d == "time" else "string"} for d in dimensions],
                    "rows": [[row.get(d, "") for d in dimensions] for row in data],
                }
            ]

    @staticmethod
    def get_time(record: dict, time_field: str) -> int:
        time_value = record.pop(time_field)

        # 带毫秒的时间戳处理
        try:
            time_value = int(time_value)
            if len(str(time_value)) > 10:
                time_value = time_value // 1000
        except (TypeError, ValueError):
            pass

        # 将时间字段序列化
        try:
            _time = arrow.get(time_value)
        except Exception as e:
            logger.error(f"parse time error: {time_value}")
            logger.exception(e)
            _time = arrow.now()

        return int(_time.timestamp)

    def perform_request(self, params):
        """
        执行日志查询请求

        参数:
            params: 查询参数字典，包含以下关键字段：
                - bk_biz_id: 业务ID
                - data_source_label: 数据源标签（如BK_LOG_SEARCH、BK_FTA等）
                - data_type_label: 数据类型标签（如LOG、ALERT等）
                - start_time/end_time: 查询时间范围（秒级时间戳）
                - where: 查询条件列表
                - filter_dict: 过滤条件字典
                - query_string: 查询字符串
                - limit/offset: 分页参数

        返回:
            dict: 查询结果，包含data（日志记录列表）和meta（总数等元信息）

        执行流程:
            1. 时间范围处理（默认最近1小时，转换为毫秒级时间戳）
            2. 获取时间字段配置（日志平台需查询索引集配置）
            3. 构建数据源查询参数
            4. 执行查询（灰度数据源使用UnifyQuery，其他使用传统方式）
            5. 格式化查询结果（处理不同数据源的字段结构）
            6. 返回结果（支持table/scene_view等格式）
        """
        # 1. 时间范围处理：如果未指定时间，默认查询最近1小时
        if "start_time" not in params or "end_time" not in params:
            params["end_time"] = int(datetime.now().timestamp())
            params["start_time"] = int((datetime.now() - timedelta(hours=1)).timestamp())

        # 将时间戳从秒级转换为毫秒级
        params["start_time"] *= 1000
        params["end_time"] *= 1000

        # 2. 获取时间字段配置：日志平台需要查询索引集的时间字段配置
        time_field: str | None = None
        if (params["data_source_label"], params["data_type_label"]) == (
            DataSourceLabel.BK_LOG_SEARCH,
            DataTypeLabel.LOG,
        ):
            try:
                result = resource.strategies.get_index_set_list(
                    bk_biz_id=params["bk_biz_id"], index_set_id=params["index_set_id"]
                )
                if result["metric_list"]:
                    time_field = result["metric_list"][0]["extend_fields"].get("time_field") or None
            except Exception as e:
                logger.exception(e)

        # 3. 构建数据源查询参数
        data_source_key: tuple[str, str] = (params["data_source_label"], params["data_type_label"])
        data_source_class = load_data_source(*data_source_key)
        time_field = time_field or data_source_class.DEFAULT_TIME_FIELD
        kwargs = dict(
            bk_tenant_id=get_request_tenant_id(),
            table=params["result_table_id"],
            index_set_id=params["index_set_id"],
            where=params["where"],
            query_string=params["query_string"],
            filter_dict=params["filter_dict"],
            time_field=time_field,
            bk_biz_id=params["bk_biz_id"],
        )

        # 特殊数据源的参数校验和补充
        if params["data_source_label"] == DataSourceLabel.BK_FTA:
            if not params.get("alert_name"):
                raise ValidationError(_("告警名称不能为空"))
            kwargs["alert_name"] = params["alert_name"]
        elif data_source_key == (DataSourceLabel.BK_MONITOR_COLLECTOR, DataTypeLabel.ALERT):
            if not params.get("bkmonitor_strategy_id"):
                raise ValidationError(_("策略ID不能为空"))
            kwargs["bkmonitor_strategy_id"] = params["bkmonitor_strategy_id"]

        # 4. 执行查询：根据数据源类型选择查询方式
        limit = 1000 if params["limit"] <= 0 else params["limit"]
        if data_source_key in GrayUnifyQueryDataSources:
            # 灰度数据源使用UnifyQuery查询
            q: QueryConfigBuilder = (
                QueryConfigBuilder((data_source_key[1], data_source_key[0]))
                .table(kwargs["table"])
                .time_field(kwargs["time_field"] or data_source_class.DEFAULT_TIME_FIELD)
                .index_set_id(kwargs["index_set_id"])
                .conditions(kwargs["where"])
                .filter(filter_dict_to_q(kwargs["filter_dict"]))
                .query_string(kwargs["query_string"])
            )
            queryset: UnifyQuerySet = (
                UnifyQuerySet()
                .scope(bk_biz_id=kwargs["bk_biz_id"])
                .start_time(params["start_time"])
                .end_time(params["end_time"])
                .time_agg(False)
                .time_align(False)
                .instant()
            )
            records: list[dict[str, Any]] = list(queryset.add_query(q).limit(limit).offset(params["offset"]))

            # 查询总数（使用COUNT聚合）
            try:
                total: int = list(queryset.add_query(q.metric(field="_index", method="COUNT", alias="a")).limit(1))[0][
                    "_result_"
                ]
            except Exception:  # pylint: disable=broad-except
                total = len(records)
        else:
            # 传统数据源使用原有查询方式
            data_source = data_source_class(**kwargs)
            records, total = data_source.query_log(
                start_time=params["start_time"], end_time=params["end_time"], limit=limit, offset=params["offset"]
            )

        # 5. 格式化查询结果：根据不同数据源类型处理字段结构
        result = []
        for record in records:
            # 移除UnifyQuery查询结果中的元数据字段
            record.pop("_meta", None)
            _record: dict[str, Any] = {"time": self.get_time(record, time_field)}

            # 处理监控采集器和自定义数据源（非告警类型）
            if params["data_source_label"] in (DataSourceLabel.BK_MONITOR_COLLECTOR, DataSourceLabel.CUSTOM) and params[
                "data_type_label"
            ] not in [DataTypeLabel.ALERT]:
                dimensions = record.pop("dimensions", {})

                # 表格和场景视图格式需要过滤掉内部维度字段
                if params["data_source_label"] == DataSourceLabel.BK_MONITOR_COLLECTOR and params.get(
                    "data_format"
                ) in ["table", "scene_view"]:
                    for dimension in [
                        "bk_biz_id",
                        "bk_collect_config_id",
                        "bk_module_id",
                        "bk_set_id",
                        "bk_target_service_category_id",
                        "dimensions.bk_target_service_instance_id",
                        "bk_target_topo_id",
                        "bk_target_topo_level",
                    ]:
                        dimensions.pop(dimension, None)

                # 提取事件信息
                event: dict[str, Any] = record.pop("event", {})
                _record["event.count"] = event.get("count", 1)
                _record["event.content"] = event.get("content", "")
                _record.update({f"event.extra.{key}": value for key, value in event.get("extra", {}).items()})

                # 合并维度和其他字段
                _record.update({f"dimensions.{key}": value for key, value in dimensions.items()})
                _record.update(record)
            elif params["data_source_label"] == DataSourceLabel.BK_LOG_SEARCH and "log" in record:
                # 日志平台数据源直接使用log字段
                _record["event.content"] = record["log"]
            else:
                # 其他数据源将整个记录序列化为JSON
                _record["event.content"] = json.dumps(record, ensure_ascii=False)

            result.append(_record)

        # 6. 返回结果：根据数据格式返回不同结构
        if params.get("data_format") in ["table", "scene_view"]:
            return self.table_format(result, total, params.get("data_format"))

        return {
            "result": True,
            "data": result,
            "meta": {
                "total": total,
            },
            "code": 200,
            "message": "OK",
        }
