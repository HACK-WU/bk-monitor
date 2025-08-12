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
import operator
import time
from datetime import datetime, timezone
from collections import defaultdict
from functools import reduce
from itertools import chain

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.db.models import Q as DQ
from elasticsearch_dsl import Q
from elasticsearch_dsl.response.aggs import BucketData
from luqum.tree import FieldGroup, OrOperation, Phrase, SearchField, Word

from bkmonitor.documents import ActionInstanceDocument, AlertDocument, AlertLog
from bkmonitor.models import ActionInstance, ConvergeRelation, MetricListCache, Shield
from bkmonitor.models.fta.action import ActionConfig
from bkmonitor.strategy.new_strategy import get_metric_id
from bkmonitor.utils.ip import exploded_ip
from bkmonitor.utils.request import get_request_tenant_id
from bkmonitor.utils.time_tools import hms_string
from constants.action import ConvergeStatus
from constants.alert import (
    EVENT_SEVERITY,
    EVENT_STATUS,
    EVENT_STATUS_DICT,
    EVENT_TARGET_TYPE,
    IGNORED_TAGS,
    AlertFieldDisplay,
    EventStatus,
)
from constants.data_source import (
    DATA_SOURCE_LABEL_CHOICE,
    DataTypeLabel,
    OthersResultTableLabel,
)
from core.drf_resource import resource
from fta_web.alert.handlers.base import (
    AlertDimensionFormatter,
    BaseBizQueryHandler,
    BaseQueryTransformer,
    QueryField,
)
from fta_web.alert.handlers.translator import (
    BizTranslator,
    CategoryTranslator,
    MetricTranslator,
    PluginTranslator,
    StrategyTranslator,
)
from fta_web.alert.handlers.action import ActionQueryHandler

logger = logging.getLogger(__name__)


def readable_name_alias_to_id(node: SearchField):
    """将 readable name 挂载到 metric id 查询"""
    bk_tenant_id = get_request_tenant_id()

    # 尝试查找是否存在对应的 readable_name
    metric = MetricListCache.objects.filter(bk_tenant_id=bk_tenant_id, readable_name=str(node.expr).strip('"')).first()
    if not metric:
        return

    # 存在时将 readable_name 查询转换为 metric_id 查询
    metric_id = get_metric_id(
        data_source_label=metric.data_source_label,
        data_type_label=metric.data_type_label,
        result_table_id=metric.result_table_id,
        metric_field=metric.metric_field,
        index_set_id=metric.related_id,
        custom_event_name=metric.extend_fields.get("custom_event_name"),
    )
    node.expr = Phrase(f'"{metric_id}"')
    return


def get_alert_ids_by_action_id(action_ids) -> list:
    if not isinstance(action_ids, list):
        action_ids = [action_ids]
    try:
        actions = ActionInstanceDocument.mget(action_ids)
        if actions:
            alert_ids = [action.alert_id for action in actions]
        else:
            action_ids = [int(str(action_id)[10:]) for action_id in action_ids]
            alert_ids = ActionInstance.objects.filter(id__in=action_ids).values_list("alerts", flat=True)
    except Exception:
        alert_ids = []
    alert_ids = set(chain.from_iterable(alert_ids))
    return list(alert_ids)


def get_alert_ids_by_action_name(action_names, include=False, exclude=False, **kwargs) -> list:
    """通过处理套餐名称获取告警ID"""
    if not isinstance(action_names, list):
        action_names = [action_names]

    # 边界检查：排除无效参数组合
    if include and exclude:
        raise ValueError("Parameters 'include' and 'exclude' cannot be True simultaneously")

    if "page_size" in kwargs:
        # 增加额外的查询数量
        kwargs["page_size"] = kwargs["page_size"] + 50

    alert_ids = _query_alert_ids_from_es(action_names, include=include, exclude=exclude, **kwargs)
    if alert_ids:
        return alert_ids

    # ES无结果时，回退到Django ORM查询
    return _query_alert_ids_from_db(action_names, include=include, exclude=exclude, **kwargs)


def _query_alert_ids_from_es(action_names, include=False, exclude=False, **kwargs):
    """内部方法：通过ES查询获取告警ID"""
    method = "exclude" if exclude else "include" if include else "eq"

    kwargs["conditions"] = [{"key": "action_name.raw", "value": action_names, "method": method, "condition": "and"}]

    action_handler = ActionQueryHandler(**kwargs)
    search_obj = action_handler.get_search_object()
    search_obj = action_handler.add_conditions(search_obj)
    search_obj = action_handler.add_pagination(search_obj)
    search_obj = search_obj.source(["alert_id"])  # 仅请求必要字段

    result = search_obj.execute()
    alert_ids = [item for hit in result.hits for item in hit.alert_id]
    return list(set(alert_ids))


def _query_alert_ids_from_db(
    action_names, bk_biz_ids, start_time, end_time, page, page_size, include=False, exclude=False
):
    """内部方法：通过DB查询获取告警ID"""
    # 构建查询条件
    if include:
        # 模糊查询多个名称
        name_conditions = DQ()
        for action_name in action_names:
            name_conditions |= DQ(name__icontains=action_name)
        filter_params = {"bk_biz_id__in": bk_biz_ids}
        filter_params_query = DQ(**filter_params) & name_conditions
    else:
        filter_params_query = DQ(name__in=action_names, bk_biz_id__in=bk_biz_ids)

    if include is False and exclude:
        filter_params_query = ~filter_params_query

    action_config_ids = ActionConfig.objects.filter(filter_params_query).values_list("id", flat=True)

    start_time = datetime.fromtimestamp(start_time, tz=timezone.utc)
    end_time = datetime.fromtimestamp(end_time, tz=timezone.utc)

    alert_id_ids = (
        ActionInstance.objects.filter(
            action_config_id__in=list(action_config_ids), create_time__gte=start_time, create_time__lte=end_time
        )
        .values_list("alerts", flat=True)
        .order_by("id")[(page - 1) * page_size : page * page_size]
    )
    alert_ids = set(chain.from_iterable(alert_id_ids))
    return list(alert_ids)


class AlertQueryTransformer(BaseQueryTransformer):
    NESTED_KV_FIELDS = {"tags": "event.tags"}
    VALUE_TRANSLATE_FIELDS = {
        "severity": EVENT_SEVERITY,
        "status": EVENT_STATUS,
        "event.target_type": EVENT_TARGET_TYPE,
        "event.data_type": DATA_SOURCE_LABEL_CHOICE,
    }
    doc_cls = AlertDocument
    # 可供查询的ES字段配置
    query_fields = [
        QueryField("id", AlertFieldDisplay.ID),
        QueryField("alert_name", _lazy("告警名称"), agg_field="alert_name.raw", is_char=True),
        QueryField("status", _lazy("状态")),
        QueryField("description", _lazy("告警内容"), es_field="event.description", is_char=True),
        QueryField("severity", _lazy("级别")),
        QueryField(
            "metric", _lazy("指标ID"), es_field="event.metric", is_char=True, alias_func=readable_name_alias_to_id
        ),
        QueryField("labels", _lazy("策略标签"), is_char=True),
        QueryField("bk_biz_id", _lazy("业务ID"), es_field="event.bk_biz_id"),
        QueryField("ip", _lazy("目标IP"), es_field="event.ip", is_char=True),
        QueryField("ipv6", _lazy("目标IPv6"), es_field="event.ipv6", is_char=True),
        QueryField("bk_host_id", _lazy("主机ID"), es_field="event.bk_host_id"),
        QueryField("bk_cloud_id", _lazy("目标云区域ID"), es_field="event.bk_cloud_id"),
        QueryField("bk_service_instance_id", _lazy("目标服务实例ID"), es_field="event.bk_service_instance_id"),
        QueryField("bk_topo_node", _lazy("目标节点"), es_field="event.bk_topo_node"),
        QueryField("assignee", _lazy("通知人")),
        QueryField("appointee", _lazy("负责人")),
        QueryField("supervisor", _lazy("知会人")),
        QueryField("follower", _lazy("关注人")),
        QueryField("is_ack", _lazy("是否已确认")),
        QueryField("is_shielded", _lazy("是否已屏蔽")),
        QueryField("shield_left_time", _lazy("屏蔽剩余时间")),
        QueryField("shield_id", _lazy("屏蔽配置ID")),
        QueryField("is_handled", _lazy("是否已处理")),
        QueryField("is_blocked", _lazy("是否熔断")),
        QueryField("strategy_id", _lazy("策略ID")),
        QueryField("create_time", _lazy("创建时间")),
        QueryField("update_time", _lazy("更新时间")),
        QueryField("begin_time", _lazy("开始时间")),
        QueryField("end_time", _lazy("结束时间")),
        QueryField("latest_time", _lazy("最新事件时间")),
        QueryField("first_anomaly_time", _lazy("首次异常时间")),
        QueryField("target_type", _lazy("告警目标类型"), es_field="event.target_type", is_char=True),
        QueryField("target", _lazy("告警目标"), es_field="event.target", is_char=True),
        QueryField("category", _lazy("分类"), es_field="event.category"),
        QueryField("tags", _lazy("维度"), es_field="event.tags", is_char=True),
        QueryField("category_display", _lazy("分类名称"), searchable=False),
        QueryField("duration", _lazy("持续时间")),
        QueryField("ack_duration", _lazy("确认时间")),
        QueryField("data_type", _lazy("数据类型"), es_field="event.data_type"),
        QueryField("action_id", _lazy("处理记录ID"), es_field="id"),
        QueryField("action_name", _lazy("处理套餐名称"), es_field="id"),
        QueryField("converge_id", _lazy("收敛记录ID"), es_field="id"),
        QueryField("event_id", _lazy("事件ID"), es_field="event.event_id", is_char=True),
        QueryField("plugin_id", _lazy("告警来源"), es_field="event.plugin_id", is_char=True),
        QueryField("plugin_display_name", _lazy("告警源名称"), searchable=False),
        QueryField("strategy_name", _lazy("策略名称"), es_field="alert_name", agg_field="alert_name.raw", is_char=True),
        QueryField("module_id", _lazy("模块ID"), es_field="event.bk_topo_node"),
        QueryField("set_id", _lazy("集群ID"), es_field="event.bk_topo_node"),
    ]

    def visit_word(self, node: Word, context: dict):
        """
        处理搜索词节点的转换与翻译逻辑

        参数:
            node: 当前处理的语法树节点对象，包含原始搜索值
            context: 上下文字典，包含搜索字段配置信息：
                - ignore_word: 布尔值，是否跳过当前节点处理
                - search_field_name: 当前搜索字段名称
                - search_field_origin_name: 原始搜索字段名称（带国际化标识）

        返回值:
            生成器产出处理后的语法树节点，可能包含：
            - 原始节点直接传递
            - 转换后的字段值
            - 组合查询条件节点
            - 空结果占位符(如[0])

        该方法实现搜索条件的多维度转换：
        1. 字段值翻译：将展示值转换为存储值
        2. 特殊字段处理：动作ID/收敛ID解析
        3. IPv6地址标准化
        4. 无字段名时的模糊匹配处理
        """
        if context.get("ignore_word"):
            # 跳过处理模式：直接传递节点到通用访问器处理
            yield from self.generic_visit(node, context)
        else:
            process_fun_list = [
                self._process_not_search_field_name,
                self._process_value_translate_fields,
                self._process_action_id,
                self._process_converge_id,
                self._process_event_ipv6,
                self._process_action_name,
                self._process_module_id,
                self._process_set_id,
            ]

            for fun in process_fun_list:
                new_node, new_context = fun(node, context)
                if new_node:
                    node, context = new_node, new_context
                    break

            yield from self.generic_visit(node, context)

    def _process_not_search_field_name(self, node: Word, context: dict) -> tuple:
        search_field_name = context.get("search_field_name")
        if search_field_name:
            return None, None

        for key, choices in self.VALUE_TRANSLATE_FIELDS.items():
            origin_value = None
            for value, display in choices:
                # 尝试将匹配翻译值，并转换回原值。例如: severity: 致命 => severity: 1
                if display == node.value:
                    origin_value = str(value)

            if origin_value is not None:
                # 例如:  致命 =>  致命 OR (severity: 1)
                node = FieldGroup(OrOperation(node, SearchField(key, Word(origin_value))))
                context.update({"ignore_search_field": True, "ignore_word": True})

                break
        else:
            node.value = f'"{node.value}"'
        return node, context

    def _process_value_translate_fields(self, node: Word, context: dict) -> tuple:
        """处理值翻译字段"""
        search_field_name = context.get("search_field_name")
        if search_field_name not in self.VALUE_TRANSLATE_FIELDS:
            return None, None

        for value, display in self.VALUE_TRANSLATE_FIELDS[search_field_name]:
            # 尝试将匹配翻译值，并转换回原值
            if display == node.value:
                node.value = str(value)

        return node, context

    def _process_action_id(self, node: Word, context: dict) -> tuple:
        """
        处理动作ID
        """
        search_field_name = context.get("search_field_name")
        if search_field_name == "id" and context.get("search_field_origin_name") in [
            "action_id",
            _("处理记录ID"),
        ]:
            alert_ids = get_alert_ids_by_action_id(node.value)
            node = FieldGroup(OrOperation(*[Word(str(alert_id)) for alert_id in alert_ids or [0]]))
            context.update({"ignore_search_field": True, "ignore_word": True})

            return node, context
        return None, None

    def _process_converge_id(self, node: Word, context: dict) -> tuple:
        """处理收敛ID"""
        search_field_name = context.get("search_field_name")
        if search_field_name == "id" and context.get("search_field_origin_name") in [
            "converge_id",
            _("收敛记录ID"),
        ]:
            # 收敛动作ID不是告警的标准字段，需要从动作ID中提取出告警ID，再将其作为查询条件
            converge_id = node.value
            try:
                # TODO 这一部分的内容要进行调整， 统一通过ES查询
                action_instance = ActionInstanceDocument.get(converge_id)
                if action_instance.is_converge_primary:
                    queryset = ConvergeRelation.objects.filter(
                        converge_id=action_instance.converge_id, converge_status=ConvergeStatus.SKIPPED
                    )
                    alert_ids = list(chain(*[converge.alerts for converge in queryset]))
                else:
                    alert_ids = []
            except Exception:
                alert_ids = []
            node = FieldGroup(OrOperation(*[Word(str(alert_id)) for alert_id in alert_ids or [0]]))
            context.update({"ignore_search_field": True, "ignore_word": True})

            return node, context
        return None, None

    def _process_event_ipv6(self, node: Word, context: dict) -> tuple:
        """处理事件IPv6"""
        search_field_name = context.get("search_field_name")
        if search_field_name == "event.ipv6":
            ip = exploded_ip(node.value.strip('"'))
            node.value = f'"{ip}"'
            return node, context
        return None, None

    def _process_action_name(self, node: Word, context: dict) -> tuple:
        """处理动作名称"""
        search_field_name = context.get("search_field_name")

        if search_field_name == "id" and context.get("search_field_origin_name") in [
            "action_name",
            _("处理套餐名称"),
        ]:
            params = {
                "action_names": [node.value],
                "bk_biz_ids": context.get("bk_biz_ids", []),
                "start_time": context.get("start_time"),
                "end_time": context.get("end_time"),
                "page": context.get("page", 1),
                "page_size": context.get("page_size", 10),
            }

            alert_ids = get_alert_ids_by_action_name(**params)
            node = FieldGroup(OrOperation(*[Word(str(alert_id)) for alert_id in alert_ids or [0]]))
            context = {"ignore_search_field": True, "ignore_word": True}
            return node, context

        return None, None

    def _process_module_id(self, node: Word, context: dict) -> tuple:
        """处理模块ID"""
        search_field_name = context.get("search_field_name")
        search_field_origin_name = context.get("search_field_origin_name")
        bk_biz_ids = set(context.get("bk_biz_ids", []))

        is_need_process = search_field_name == "event.bk_topo_node" and search_field_origin_name in [
            "module_id",
            _("模块ID"),
        ]

        if not is_need_process:
            return None, None

        # 如果值不是数字，则将其作为模块名，并尝试查询对应的模块ID
        if not node.value.isdigit():
            if bk_biz_ids:
                values = resource.commons.get_topo_list(
                    bk_biz_ids=bk_biz_ids,
                    bk_obj_id="module",
                    condition={"bk_module_name": node.value},
                )
            else:
                values = []

            if len(values) == 1:
                node.value = f"module|{values[0]['bk_module_id']}"
            elif len(values) > 1:
                node = FieldGroup(OrOperation(*[Word(f"module|{value['bk_module_id']}") for value in values]))
            else:
                node.value = "module|''"

        else:
            node.value = f"module|{node.value}"

        context.update({"ignore_search_field": True, "ignore_word": True})
        return node, context

    def _process_set_id(self, node: Word, context: dict) -> tuple:
        """处理集群ID"""
        search_field_name = context.get("search_field_name")
        search_field_origin_name = context.get("search_field_origin_name")
        bk_biz_ids = context.get("bk_biz_ids", [])

        is_need_process = search_field_name == "event.bk_topo_node" and search_field_origin_name in [
            "set_id",
            _("集群ID"),
        ]

        if not is_need_process:
            return None, None

        if not node.value.isdigit():
            if bk_biz_ids:
                values = resource.commons.get_topo_list(
                    bk_biz_ids=bk_biz_ids,
                    bk_obj_id="set",
                    condition={"bk_set_name": node.value},
                )
            else:
                values = []

            if len(values) == 1:
                node.value = f"set|{values[0]['bk_set_id']}"
            elif len(values) > 1:
                node = FieldGroup(OrOperation(*[Word(f"set|{value['bk_set_id']}") for value in values]))
            else:
                node.value = "set|''"

        else:
            node.value = f"set|{node.value}"

        context.update({"ignore_search_field": True, "ignore_word": True})
        return node, context


class AlertQueryHandler(BaseBizQueryHandler):
    """
    告警查询
    """

    query_transformer = AlertQueryTransformer

    # 导出时需要排除的无用字段（这些字段会在处理过程中被移除）
    EXCLUDED_EXPORT_FIELDS = {"action_id", "action_name", "module_id", "set_id"}

    # 以下常量定义不同状态名称，用于业务逻辑中的状态过滤或标识：
    # - MINE_STATUS_NAME: 表示当前用户直接关联的状态（如用户自己创建的条目）
    # - MY_APPOINTEE_STATUS_NAME: 表示被当前用户指定人员关联的状态（如被委派人处理的条目）
    # - MY_ASSIGNEE_STATUS_NAME: 表示当前用户被指派处理的状态（如用户被分配的任务）
    # - MY_FOLLOW_STATUS_NAME: 表示当前用户关注条目的状态
    # - SHIELD_ABNORMAL_STATUS_NAME: 表示被屏蔽的异常状态
    # - NOT_SHIELD_ABNORMAL_STATUS_NAME: 表示未被屏蔽的正常状态

    # “我的告警” 状态名称
    MINE_STATUS_NAME = "MINE"
    MY_APPOINTEE_STATUS_NAME = "MY_APPOINTEE"
    MY_ASSIGNEE_STATUS_NAME = "MY_ASSIGNEE"
    MY_FOLLOW_STATUS_NAME = "MY_FOLLOW"
    SHIELD_ABNORMAL_STATUS_NAME = "SHIELDED_ABNORMAL"
    NOT_SHIELD_ABNORMAL_STATUS_NAME = "NOT_SHIELDED_ABNORMAL"

    def __init__(
        self,
        bk_biz_ids: list[int] = None,
        username: str = "",
        status: list[str] = None,
        is_time_partitioned: bool = False,
        is_finaly_partition: bool = False,
        need_bucket_count: bool = True,
        **kwargs,
    ):
        super().__init__(bk_biz_ids, username, **kwargs)
        self.must_exists_fields = kwargs.get("must_exists_fields", [])
        self.status = [status] if isinstance(status, str) else status
        if not self.ordering:
            # 默认排序
            self.ordering = ["status", "-create_time", "-seq_id"]
        self.is_time_partitioned = is_time_partitioned
        self.is_finaly_partition = is_finaly_partition
        self.need_bucket_count = need_bucket_count

    def get_search_object(
        self,
        start_time: int = None,
        end_time: int = None,
        is_time_partitioned: bool = False,
        is_finaly_partition: bool = False,
    ):
        """
        获取告警文档的查询对象，支持时间范围过滤、业务条件过滤、用户状态过滤等复杂条件组合

        没有恢复的告警不受start_time和end_time限制

        参数说明:
            start_time: 查询起始时间戳（可选，默认使用实例的start_time）
            end_time: 查询结束时间戳（可选，默认使用实例的end_time）
            is_time_partitioned: 是否启用时间分区查询（默认False）
            is_finaly_partition: 是否为最终时间分区（仅在is_time_partitioned=True时生效）

        返回值:
            构建完成的elasticsearch查询对象

        该方法实现以下核心功能：
        1. 参数优先级处理：优先使用传入参数，否则回退到实例变量
        2. 时间范围过滤：支持时间分区模式和普通模式的双分支处理逻辑
        3. 多维条件组合：包含业务维度、用户维度、状态维度的复合过滤条件
        4. 字段存在性验证：强制要求某些字段必须存在的过滤条件
        """
        # 参数初始化：优先使用传入参数，否则使用实例变量
        start_time = start_time or self.start_time
        end_time = end_time or self.end_time
        is_time_partitioned = is_time_partitioned or self.is_time_partitioned
        is_finaly_partition = is_finaly_partition or self.is_finaly_partition

        # 初始化基础查询对象
        search_object = AlertDocument.search(start_time=self.start_time, end_time=self.end_time)

        # 时间范围过滤逻辑（核心条件组合）
        if start_time and end_time:
            if is_time_partitioned:
                # 时间分区模式下的特殊处理逻辑
                if is_finaly_partition:
                    search_object = search_object.filter(
                        (Q("range", end_time={"gte": start_time}) | ~Q("exists", field="end_time"))
                        & (Q("range", begin_time={"lte": end_time}) | Q("range", create_time={"lte": end_time}))
                    )
                else:
                    # ES 的时间切片应该使用 [start, end)
                    search_object = search_object.filter(
                        (Q("range", end_time={"gte": start_time, "lt": end_time}) | ~Q("exists", field="end_time"))
                        & (Q("range", begin_time={"lt": end_time}) | Q("range", create_time={"lt": end_time}))
                    )
            else:
                # 非时间分区模式的基础过滤
                # 对应dsl语句
                # {
                #   "query": {
                #     "bool": {
                #       "must": [
                #         {
                #           "bool": {
                #             "should": [
                #               {
                #                 "range": {
                #                   "end_time": {
                #                     "gte": start_time
                #                   }
                #                 }
                #               },
                #               {
                #                 "bool": {
                #                   "must_not": {
                #                     "exists": {
                #                       "field": end_time
                #                     }
                #                   }
                #                 }
                #               }
                #             ]
                #           }
                #         },
                #         {
                #           "bool": {
                #             "should": [
                #               {
                #                 "range": {
                #                   "begin_time": {
                #                     "lte": end_time
                #                   }
                #                 }
                #               },
                #               {
                #                 "range": {
                #                   "create_time": {
                #                     "lte": end_time
                #                   }
                #                 }
                #               }
                #             ]
                #           }
                #         }
                #       ]
                #     }
                #   }
                # }

                # 查询在start_time到end_time之间的已恢复(已失效)的告警，或者查询还没有恢复的告警。
                # 不存在end_time,则说明告警未恢复。
                search_object = search_object.filter(
                    (Q("range", end_time={"gte": start_time}) | ~Q("exists", field="end_time"))
                    & (Q("range", begin_time={"lte": end_time}) | Q("range", create_time={"lte": end_time}))
                )

        # 添加业务维度过滤条件
        search_object = self.add_biz_condition(search_object)

        # 用户维度过滤（精确匹配负责人或委托负责人）
        if self.username:
            search_object = search_object.filter(Q("term", assignee=self.username) | Q("term", appointee=self.username))

        # 复杂状态过滤逻辑（多条件OR组合）
        if self.status:
            queries = []
            for status in self.status:
                # 特殊状态转换逻辑
                if status == self.MINE_STATUS_NAME:
                    queries.append(
                        Q("term", assignee=self.request_username) | Q("term", appointee=self.request_username)
                    )
                if status == self.MY_ASSIGNEE_STATUS_NAME:
                    queries.append(Q("term", assignee=self.request_username))
                if status == self.MY_APPOINTEE_STATUS_NAME:
                    queries.append(Q("term", appointee=self.request_username))
                if status == self.MY_FOLLOW_STATUS_NAME:
                    queries.append(Q("term", follower=self.request_username))
                elif status == self.SHIELD_ABNORMAL_STATUS_NAME:
                    queries.append(Q("term", status=EventStatus.ABNORMAL) & Q("term", is_shielded=True))
                elif status == self.NOT_SHIELD_ABNORMAL_STATUS_NAME:
                    queries.append(Q("term", status=EventStatus.ABNORMAL) & ~Q("term", is_shielded=True))
                else:
                    queries.append(Q("term", status=status))

            # 组合所有状态查询条件
            if queries:
                search_object = search_object.filter(reduce(operator.or_, queries))

        # 添加必须存在字段的过滤条件
        for field in self.must_exists_fields:
            search_object = search_object.filter("exists", field=field)

        return search_object

    def search_raw(self, show_overview=False, show_aggs=False, show_dsl=False):
        # 构建上下文信息
        context = {
            "bk_biz_ids": self.bk_biz_ids,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "page": self.page,
            "page_size": self.page_size,
        }

        search_object = self.get_search_object()
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object, context=context)
        search_object = self.add_ordering(search_object)
        search_object = self.add_pagination(search_object)

        # 根据参数添加附加功能
        if show_overview:
            search_object = self.add_overview(search_object)

        if show_aggs:
            search_object = self.add_aggs(search_object)

        # 执行搜索并跟踪总匹配数
        search_result = search_object.params(track_total_hits=True).execute()

        # 根据参数决定是否返回DSL字典
        if show_dsl:
            return search_result, search_object.to_dict()

        return search_result, None

    def search(self, show_overview=False, show_aggs=False, show_dsl=False):
        """
        搜索告警并返回格式化结果

        参数:
            show_overview (bool): 是否包含统计概览信息
            show_aggs (bool): 是否包含聚合数据
            show_dsl (bool): 是否包含原始查询DSL语句

        返回值:
            dict: 结构化的告警搜索结果，包含以下字段：
                - alerts (list): 格式化后的告警列表
                - total (int): 匹配的告警总数
                - overview (dict): 统计概览信息（当show_overview=True时存在）
                - aggs (dict): 聚合数据（当show_aggs=True时存在）
                - dsl (str): 原始查询DSL语句（当show_dsl=True时存在）

        异常:
            Exception: 当搜索过程中发生错误时抛出，异常对象会包含已处理的结果数据

        该方法实现完整的告警搜索流程，包含：
        1. 原始搜索执行与异常处理
        2. 搜索结果格式化处理
        3. 多维度字段翻译（业务/策略/分类/插件）
        4. 条件性扩展信息注入
        5. 异常数据回填与抛出
        """
        exc = None

        # 执行原始搜索并处理异常情况
        try:
            search_result, dsl = self.search_raw(show_overview, show_aggs, show_dsl)
        except Exception as e:
            logger.exception("search alerts error: %s", e)
            search_result = self.make_empty_response()
            dsl = None
            exc = e

        # 处理原始搜索结果
        alerts = self.handle_hit_list(search_result)
        self.handle_operator(alerts)

        # 执行多维度字段翻译
        MetricTranslator(bk_biz_ids=self.bk_biz_ids).translate_from_dict(
            list(chain(*[alert["metric_display"] for alert in alerts])), "id", "name"
        )
        StrategyTranslator().translate_from_dict(alerts, "strategy_id", "strategy_name")
        BizTranslator().translate_from_dict(alerts, "bk_biz_id", "bk_biz_name")
        CategoryTranslator().translate_from_dict(alerts, "category", "category_display")
        PluginTranslator().translate_from_dict(alerts, "plugin_id", "plugin_display_name")

        # 构建基础结果集
        result = {"alerts": alerts, "total": search_result.hits.total.value}

        # 按需添加扩展信息
        if show_overview:
            result["overview"] = self.handle_overview(search_result)

        if show_aggs:
            result["aggs"] = self.handle_aggs(search_result)

        if dsl:
            result["dsl"] = dsl

        # 异常情况下注入数据并重新抛出
        if exc:
            exc.data = result
            raise exc

        return result

    def _get_buckets(
        self,
        result: dict[tuple[tuple[str, any]], any],
        dimensions: dict[str, any],
        aggregation: BucketData,
        agg_fields: list[str],
    ):
        """
        获取聚合结果
        """
        if agg_fields:
            field = agg_fields[0]
            if field.startswith("tags."):
                buckets = aggregation[field].key.value.buckets
            else:
                buckets = aggregation[field].buckets
            for bucket in buckets:
                dimensions[field] = bucket.key
                self._get_buckets(result, dimensions, bucket, agg_fields[1:])
        else:
            dimension_tuple: tuple = tuple(dimensions.items())
            result[dimension_tuple] = aggregation

    def date_histogram(self, interval: str = "auto", group_by: list[str] = None):
        interval = self.calculate_agg_interval(self.start_time, self.end_time, interval)

        # 默认按status聚合
        if group_by is None:
            group_by = ["status"]

        # status 会被单独处理
        status_group = False
        if "status" in group_by:
            status_group = True
            group_by = [field for field in group_by if field != "status"]

        # TODO: tags开头的字段是否能够进行嵌套聚合？
        tags_field_count = 0
        for field in group_by:
            if field.startswith("tags."):
                tags_field_count += 1
        if tags_field_count > 1:
            raise ValueError("can not group by more than one tags field")

        # 将tags开头的字段放在后面
        group_by = sorted(group_by, key=lambda x: x.startswith("tags."))

        # 查询时间对齐
        start_time = self.start_time // interval * interval
        end_time = self.end_time // interval * interval + interval
        now_time = int(time.time()) // interval * interval + interval

        search_object = self.get_search_object(start_time=start_time, end_time=end_time)
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object)

        # 已经恢复或关闭的告警，按end_time聚合
        ended_object = search_object.aggs.bucket(
            "end_time", "filter", {"range": {"end_time": {"lte": end_time}}}
        ).bucket("end_alert", "filter", {"terms": {"status": [EventStatus.RECOVERED, EventStatus.CLOSED]}})
        # 查询时间范围内产生的告警，按begin_time聚合
        new_anomaly_object = search_object.aggs.bucket(
            "begin_time", "filter", {"range": {"begin_time": {"gte": start_time, "lte": end_time}}}
        )
        # 开始时间在查询时间范围之前的告警总数
        old_anomaly_object = search_object.aggs.bucket(
            "init_alert", "filter", {"range": {"begin_time": {"lt": start_time}}}
        )

        # 时间聚合
        ended_object = ended_object.bucket(
            "time", "date_histogram", field="end_time", fixed_interval=f"{interval}s"
        ).bucket("status", "terms", field="status")
        new_anomaly_object = new_anomaly_object.bucket(
            "time", "date_histogram", field="begin_time", fixed_interval=f"{interval}s"
        )

        # 维度聚合
        for field in group_by:
            ended_object = self.add_agg_bucket(ended_object, field)
            new_anomaly_object = self.add_agg_bucket(new_anomaly_object, field)
            old_anomaly_object = self.add_agg_bucket(old_anomaly_object, field)

        # 查询
        search_result = search_object[:0].execute()

        result = defaultdict(
            lambda: {
                status: {ts * 1000: 0 for ts in range(start_time, min(now_time, end_time), interval)}
                for status in EVENT_STATUS_DICT
            }
        )
        if hasattr(search_result.aggs, "begin_time"):
            for time_bucket in search_result.aggs.begin_time.time.buckets:
                begin_time_result = {}
                self._get_buckets(begin_time_result, {}, time_bucket, group_by)

                key = int(time_bucket.key_as_string) * 1000
                for dimension_tuple, bucket in begin_time_result.items():
                    if key in result[dimension_tuple][EventStatus.ABNORMAL]:
                        result[dimension_tuple][EventStatus.ABNORMAL][key] = bucket.doc_count

        if hasattr(search_result.aggs, "end_time") and hasattr(search_result.aggs.end_time, "end_alert"):
            for time_bucket in search_result.aggs.end_time.end_alert.time.buckets:
                for status_bucket in time_bucket.status.buckets:
                    end_time_result = {}
                    self._get_buckets(end_time_result, {}, status_bucket, group_by)

                    key = int(time_bucket.key_as_string) * 1000
                    for dimension_tuple, bucket in end_time_result.items():
                        if key in result[dimension_tuple][status_bucket.key]:
                            result[dimension_tuple][status_bucket.key][key] = bucket.doc_count

        init_alert_result = {}
        if hasattr(search_result.aggs, "init_alert"):
            self._get_buckets(init_alert_result, {}, search_result.aggs.init_alert, group_by)

        # 获取全部维度
        all_dimensions = set(result.keys()) | set(init_alert_result.keys())

        # 按维度分别统计事件数量
        for dimension_tuple in all_dimensions:
            all_series = result[dimension_tuple]

            if dimension_tuple in init_alert_result:
                current_abnormal_count = init_alert_result[dimension_tuple].doc_count
            else:
                current_abnormal_count = 0

            for ts in all_series[EventStatus.ABNORMAL]:
                # 异常是一个持续的状态，会随着时间的推移不断叠加
                # 一旦有恢复或关闭的告警，异常告警将会相应减少
                all_series[EventStatus.ABNORMAL][ts] = (
                    current_abnormal_count
                    + all_series[EventStatus.ABNORMAL][ts]
                    - all_series[EventStatus.CLOSED][ts]
                    - all_series[EventStatus.RECOVERED][ts]
                )
                current_abnormal_count = all_series[EventStatus.ABNORMAL][ts]

            # 如果不按status聚合，需要将status聚合的结果合并到一起
            if not status_group:
                for ts in all_series[EventStatus.ABNORMAL]:
                    all_series[EventStatus.ABNORMAL][ts] += (
                        all_series[EventStatus.CLOSED][ts] + all_series[EventStatus.RECOVERED][ts]
                    )
                all_series.pop(EventStatus.CLOSED, None)
                all_series.pop(EventStatus.RECOVERED, None)
        return result

    def parse_condition_item(self, condition: dict) -> Q:
        if condition["key"] == "stage":
            conditions = []
            for value in condition["value"]:
                if value == "is_handled":
                    conditions.append(
                        ~Q("term", is_shielded=True) & ~Q("term", is_ack=True) & Q("term", is_handled=True)
                    )
                elif value == "is_ack":
                    conditions.append(~Q("term", is_shielded=True) & Q("term", is_ack=True))
                elif value == "is_shielded":
                    conditions.append(Q("term", is_shielded=True))
                elif value == "is_blocked":
                    conditions.append(Q("term", is_blocked=True))
            # 对 key 为 stage 进行特殊处理
            return reduce(operator.or_, conditions)
        elif condition["key"].startswith("tags."):
            # 对 tags 开头的字段进行特殊处理
            return Q(
                "nested",
                path="event.tags",
                query=Q("term", **{"event.tags.key": condition["key"][5:]})
                & Q("terms", **{"event.tags.value.raw": condition["value"]}),
            )
        elif condition["key"] == "alert_name":
            condition["key"] = "alert_name.raw"
        elif condition["key"] == "id" and condition["origin_key"] == "action_id":
            # 处理动作ID不是告警的标准字段，需要从动作ID中提取出告警ID，再将其作为查询条件
            alert_ids = get_alert_ids_by_action_id(condition["value"])
            if not alert_ids:
                alert_ids = [0]
            return Q("ids", values=alert_ids)

        elif condition["origin_key"] == "action_name" and condition["key"] == "id":
            # 用于支持对处理套餐名称查询
            params = {
                "action_names": condition["value"],
                "bk_biz_ids": self.bk_biz_ids,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "page": self.page,
                "page_size": self.page_size,
                "include": condition["method"] == "include",
                "exclude": condition["method"] == "exclude",
            }
            alert_ids = get_alert_ids_by_action_name(**params)

            # 如果没有找到匹配的告警ID，则构造一个不可能匹配的条件
            if not alert_ids:
                alert_ids = [0]

            return Q("ids", values=alert_ids)
        return super().parse_condition_item(condition)

    def add_biz_condition(self, search_object):
        """根据业务权限和用户关系条件过滤告警查询

        参数:
            search_object (Search): 原始查询对象

        返回:
            Search: 添加过滤条件后的查询对象。当存在查询条件时返回过滤后的查询，
                    否则返回原始查询对象
        """
        queries = []
        # 添加授权业务ID过滤条件
        if self.authorized_bizs is not None and self.bk_biz_ids:
            queries.append(Q("terms", **{"event.bk_biz_id": self.authorized_bizs}))

        # 构建用户相关查询条件（处理人/负责人/督导人）
        user_condition = Q(
            Q("term", assignee=self.request_username)
            | Q("term", appointee=self.request_username)
            | Q("term", supervisor=self.request_username)
        )

        # 未指定业务ID时仅返回用户相关告警
        if not self.bk_biz_ids:
            queries.append(user_condition)

        # 处理未授权业务下的用户关联告警
        if self.unauthorized_bizs and self.request_username:
            queries.append(Q(Q("terms", **{"event.bk_biz_id": self.unauthorized_bizs}) & user_condition))

        # 合并所有过滤条件
        if queries:
            return search_object.filter(reduce(operator.or_, queries))
        return search_object

    def add_filter(self, search_object, start_time: int = None, end_time: int = None):
        # 条件过滤
        if self.bk_biz_ids:
            search_object = search_object.filter("terms", **{"event.bk_biz_id": self.bk_biz_ids})

        start_time = start_time or self.start_time
        end_time = end_time or self.end_time
        if start_time and end_time:
            search_object = search_object.filter(
                Q("range", end_time={"gte": start_time, "lte": end_time}) | ~Q("exists", field="end_time")
            )

        return search_object

    def add_overview(self, search_object):
        """
        为搜索对象添加多维度聚合分析配置，用于生成数据概览统计信息

        参数:
            search_object: Elasticsearch搜索对象，包含查询条件和聚合配置
                          类型通常为elasticsearch_dsl.search.Search或兼容对象

        返回值:
            添加聚合配置后的搜索对象，支持链式调用

        聚合适配逻辑说明：
        1. status与is_shielded的嵌套聚合：统计不同状态下的条目屏蔽分布
           - 外层按状态分组（active/inactive等）
           - 内层按是否屏蔽分组（布尔值聚合）
        2. mine过滤聚合：统计当前用户关联条目（包含经办人或指派人身份）
        3. assignee/appointee/follower专项过滤：分别统计当前用户作为经办人、
           指派人、关注者的条目数量
        """

        # 总览聚合：创建状态与屏蔽状态的双维度统计
        search_object.aggs.bucket("status", "terms", field="status").bucket(
            "is_shielded",
            "terms",
            field="is_shielded",
            missing=False,
            size=10000,
        )
        # 禁用中的状态聚合（历史保留配置）
        # search_object.aggs.bucket("status", "terms", field="status")

        # 用户关联条目统计：包含经办人或指派人身份的过滤聚合
        search_object.aggs.bucket(
            "mine", "filter", (Q("term", assignee=self.request_username) | Q("term", appointee=self.request_username))
        )

        # 专项身份统计：分别创建经办人、指派人、关注者的独立过滤聚合
        search_object.aggs.bucket("assignee", "filter", {"term": {"assignee": self.request_username}})
        search_object.aggs.bucket("appointee", "filter", {"term": {"appointee": self.request_username}})
        search_object.aggs.bucket("follower", "filter", {"term": {"follower": self.request_username}})

        return search_object

    def add_aggs(self, search_object):
        """
        添加高级筛选聚合配置到Elasticsearch搜索对象

        参数:
            search_object: Elasticsearch DSL搜索对象，包含当前查询的聚合配置

        返回值:
            修改后的Elasticsearch DSL搜索对象，包含新增的聚合配置

        该方法实现以下聚合配置：
        1. 初始化基础聚合容器
        2. 添加多维度terms聚合：
           - 告警严重程度（severity）
           - 事件数据类型（event.data_type）带默认分类
           - 事件分类（event.category）带最大分类数限制
        3. 添加复合条件过滤聚合：
           - 屏蔽状态过滤
           - 确认状态过滤（排除已屏蔽记录）
           - 处理状态过滤（双重否定条件）
           - 阻断状态过滤
        """
        # 高级筛选聚合
        search_object.aggs.bucket("severity", "terms", field="severity")
        search_object.aggs.bucket("data_type", "terms", field="event.data_type", missing=DataTypeLabel.EVENT)
        search_object.aggs.bucket(
            "category", "terms", field="event.category", missing=OthersResultTableLabel.other_rt, size=10000
        )
        search_object.aggs.bucket("is_shielded", "filter", Q("term", is_shielded=True))
        search_object.aggs.bucket(
            "is_ack",
            "filter",
            (~Q("term", is_shielded=True) & Q("term", is_ack=True)),
        )
        search_object.aggs.bucket(
            "is_handled",
            "filter",
            (~Q("term", is_shielded=True) & ~Q("term", is_ack=True) & Q("term", is_handled=True)),
        )

        search_object.aggs.bucket("is_blocked", "filter", Q("term", is_blocked=True))

        return search_object

    @classmethod
    def handle_operator(cls, alerts):
        """
        处理告警操作者信息填充，分离已确认和已屏蔽告警进行专项处理

        参数:
            alerts (list): 告警数据列表，每个元素为包含告警元数据的字典对象
                必须包含字段: id(str), is_ack(bool), is_shielded(bool)
                可选字段: shield_id(list), ack_operator(str), shield_operator(set)

        返回值:
            None: 直接修改输入列表中每个告警对象的操作者字段

        执行流程:
        1. 初始化告警分类容器
        2. 遍历告警列表进行基础字段初始化
        3. 按确认状态和屏蔽状态分类处理
        4. 调用专项处理方法填充操作者信息
        """
        ack_alerts = {}
        shield_alerts = {}
        for alert in alerts:
            alert["ack_operator"] = ""
            alert["shield_operator"] = set()
            if alert["is_ack"]:
                ack_alerts[alert["id"]] = alert
            if alert["is_shielded"]:
                shield_alerts[alert["id"]] = alert

        if ack_alerts:
            cls.handle_ack_operator(ack_alerts)
        if shield_alerts:
            cls.handle_shield_operator(shield_alerts)

    @classmethod
    def handle_ack_operator(cls, ack_alerts):
        """
        处理已确认告警的操作者信息填充

        参数:
            ack_alerts (dict): 已确认告警字典，键为告警ID，值为告警对象

        返回值:
            None: 直接修改ack_alerts中每个告警对象的ack_operator字段

        处理逻辑:
        1. 批量获取确认日志
        2. 构建告警ID到操作者的映射表
        3. 为每个确认告警填充对应操作者
        """
        ack_logs = AlertLog.get_ack_logs(list(ack_alerts.keys()))
        alert_operators = {}
        for ack_log in ack_logs:
            log_alerts = {alert_id: ack_log.operator for alert_id in ack_log.alert_id}
            alert_operators.update(log_alerts)
        for alert_id, alert in ack_alerts.items():
            alert["ack_operator"] = alert_operators.get(alert_id, "")

    @classmethod
    def handle_shield_operator(cls, shield_alerts):
        """
        处理已屏蔽告警的操作者信息填充

        参数:
            shield_alerts (dict): 已屏蔽告警字典，键为告警ID，值为告警对象

        返回值:
            None: 直接修改shield_alerts中每个告警对象的shield_operator集合

        处理流程:
        1. 收集所有关联的屏蔽策略ID
        2. 建立屏蔽策略ID到告警的反向映射
        3. 批量查询屏蔽策略并填充创建者信息
        """
        shield_ids = []
        shield_alert_relation = defaultdict(list)
        for alert in shield_alerts.values():
            if not alert["shield_id"]:
                continue
            shield_ids.extend(alert["shield_id"])
            for shield_id in alert["shield_id"]:
                shield_alert_relation[shield_id].append(alert)

        for shield_obj in Shield.objects.filter(id__in=shield_ids).order_by("create_user", "id"):
            alerts = shield_alert_relation[shield_obj.id]
            for alert in alerts:
                alert["shield_operator"].add(shield_obj.create_user)

    @classmethod
    def handle_aggs(cls, search_result):
        """
        处理搜索结果的聚合分析

        参数:
            search_result (dict): 包含原始搜索结果的数据字典

        返回值:
            list: 包含四个元素的聚合结果列表，依次为：
                - 严重度分布聚合结果
                - 阶段分布聚合结果
                - 数据类型分布聚合结果
                - 分类分布聚合结果

        聚合维度:
        1. 告警严重度统计
        2. 处理阶段分布
        3. 数据类型统计
        4. 告警分类分布
        """
        agg_result = [
            cls.handle_aggs_severity(search_result),
            cls.handle_aggs_stage(search_result),
            cls.handle_aggs_data_type(search_result),
            cls.handle_aggs_category(search_result),
        ]

        return agg_result

    @classmethod
    def handle_aggs_severity(cls, search_result):
        if search_result.aggs:
            severity_dict = {bucket.key: bucket.doc_count for bucket in search_result.aggs.severity.buckets}
        else:
            severity_dict = {}

        result = {
            "id": "severity",
            "name": _("级别"),
            "count": sum(severity_dict.values()),
            "children": [
                {"id": severity, "name": str(display), "count": severity_dict.get(severity, 0)}
                for severity, display in EVENT_SEVERITY
            ],
        }
        return result

    @classmethod
    def handle_aggs_category(cls, search_result):
        if search_result.aggs:
            category_dict = {bucket.key: bucket.doc_count for bucket in search_result.aggs.category.buckets}
        else:
            category_dict = {}

        try:
            labels = resource.commons.get_label()
        except Exception:
            labels = []
        for first_label in labels:
            first_label["count"] = 0
            for second_label in first_label["children"]:
                count = category_dict.get(second_label["id"], 0)
                second_label["count"] = count
                first_label["count"] += count

            first_label["children"].sort(key=lambda x: x["index"])

        return {
            "id": "category",
            "name": _("分类"),
            "count": sum(category_dict.values()),
            "children": labels,
        }

    @classmethod
    def handle_aggs_stage(cls, search_result):
        handled_count = search_result.aggs.is_handled.doc_count if search_result.aggs else 0
        ack_count = search_result.aggs.is_ack.doc_count if search_result.aggs else 0
        shielded_count = search_result.aggs.is_shielded.doc_count if search_result.aggs else 0
        blocked_count = search_result.aggs.is_blocked.doc_count if search_result.aggs else 0

        return {
            "id": "stage",
            "name": _("处理阶段"),
            "count": handled_count + ack_count + shielded_count,
            "children": [
                {"id": "is_handled", "name": _("已通知"), "count": handled_count},
                {"id": "is_ack", "name": _("已确认"), "count": ack_count},
                {"id": "is_shielded", "name": _("已屏蔽"), "count": shielded_count},
                {"id": "is_blocked", "name": _("已流控"), "count": blocked_count},
            ],
        }

    @classmethod
    def handle_aggs_data_type(cls, search_result):
        if search_result.aggs:
            data_type_dict = {bucket.key: bucket.doc_count for bucket in search_result.aggs.data_type.buckets}
        else:
            data_type_dict = {}

        return {
            "id": "data_type",
            "name": _("数据类型"),
            "count": sum(data_type_dict.values()),
            "children": [
                {"id": data_type, "name": display, "count": data_type_dict.get(data_type, 0)}
                for data_type, display in DATA_SOURCE_LABEL_CHOICE
            ],
        }

    @classmethod
    def handle_overview(cls, search_result):
        agg_result = {
            cls.SHIELD_ABNORMAL_STATUS_NAME: 0,
            cls.NOT_SHIELD_ABNORMAL_STATUS_NAME: 0,
            EventStatus.RECOVERED: 0,
        }

        if search_result.aggs:
            for status_bucket in search_result.aggs.status.buckets:
                status = status_bucket.key
                if status == EventStatus.ABNORMAL:
                    for is_shielded_bucket in status_bucket.is_shielded.buckets:
                        # 只记录已屏蔽，未恢复的告警数量
                        if is_shielded_bucket.key:
                            agg_result[cls.SHIELD_ABNORMAL_STATUS_NAME] = is_shielded_bucket.doc_count
                        else:
                            agg_result[cls.NOT_SHIELD_ABNORMAL_STATUS_NAME] = is_shielded_bucket.doc_count
                elif status in agg_result:
                    agg_result[status] = status_bucket.doc_count

        result = {
            "id": "alert",
            "name": _("告警"),
            "count": search_result.hits.total.value,
            "children": [
                {
                    "id": cls.MINE_STATUS_NAME,
                    "name": _("我的告警"),
                    "count": search_result.aggs.mine.doc_count if search_result.aggs else 0,
                },
                {
                    "id": cls.MY_APPOINTEE_STATUS_NAME,
                    "name": _("我负责的"),
                    "count": search_result.aggs.appointee.doc_count if search_result.aggs else 0,
                },
                {
                    "id": cls.MY_FOLLOW_STATUS_NAME,
                    "name": _("我关注的"),
                    "count": search_result.aggs.follower.doc_count if search_result.aggs else 0,
                },
                {
                    "id": cls.MY_ASSIGNEE_STATUS_NAME,
                    "name": _("我收到的"),
                    "count": search_result.aggs.assignee.doc_count if search_result.aggs else 0,
                },
                {
                    "id": cls.NOT_SHIELD_ABNORMAL_STATUS_NAME,
                    "name": _("未恢复"),
                    "count": agg_result[cls.NOT_SHIELD_ABNORMAL_STATUS_NAME],
                },
                {
                    "id": cls.SHIELD_ABNORMAL_STATUS_NAME,
                    "name": _("未恢复(已屏蔽)"),
                    "count": agg_result[cls.SHIELD_ABNORMAL_STATUS_NAME],
                },
                {
                    "id": EventStatus.RECOVERED,
                    "name": _("已恢复"),
                    "count": agg_result[EventStatus.RECOVERED],
                },
            ],
        }
        return result

    def export_with_docs(self) -> tuple[list[AlertDocument], list[dict]]:
        """导出告警数据，并附带原始文档。"""
        raw_docs = [AlertDocument(**hit.to_dict()) for hit in self.scan(source_fields=self.get_export_fields())]
        cleaned_docs = (self.clean_document(doc, exclude=["extra_info"]) for doc in raw_docs)
        return raw_docs, list(self.translate_field_names(cleaned_docs))

    def get_export_fields(self):
        """
        获取导出时需要查询的字段列表
        """
        fields = set()

        # 从 query_fields 中提取需要的字段，排除无用字段
        for field in self.query_transformer.query_fields:
            if field.field in self.EXCLUDED_EXPORT_FIELDS:
                continue
            if field.es_field:
                fields.add(field.es_field)
            elif field.field:
                fields.add(field.field)

        # 关联信息AlertRelatedInfo依赖的字段
        fields.update({"extra_info", "dimensions"})

        # 添加排序字段
        for field in self.ordering:
            field = field.lstrip("-")
            es_field = self.query_transformer.transform_field_to_es_field(field)
            if es_field:
                fields.add(es_field)

        return list(fields)

    @classmethod
    def handle_hit(cls, hit):
        return cls.clean_document(AlertDocument(**hit.to_dict()), exclude=["extra_info"])

    @classmethod
    def clean_document(cls, doc: AlertDocument, exclude: list = None) -> dict:
        """
        清洗告警数据并填充标准化字段

        参数:
            cls: 当前类引用，包含查询转换器配置
            doc: AlertDocument实例，原始告警数据对象
            exclude: 需要排除的字段列表，默认不排除任何字段

        返回值:
            dict类型，包含清洗后的标准化告警数据字典

        执行流程:
            1. 应用查询转换器映射规则处理固定字段
            2. 移除系统保留字段action_id
            3. 补充业务展示字段和格式化数据
            4. 根据参数排除指定字段
        """
        data = doc.to_dict()
        cleaned_data = {}

        # 固定字段（跳过无用字段）
        for field in cls.query_transformer.query_fields:
            if field.field in cls.EXCLUDED_EXPORT_FIELDS:
                continue
            cleaned_data[field.field] = field.get_value_by_es_field(data)

        # 额外字段
        cleaned_data.update(
            {
                # "strategy_name": doc.strategy.get("name") if doc.strategy else None,
                "stage_display": doc.stage_display,
                "duration": hms_string(doc.duration),
                "shield_left_time": hms_string(doc.shield_left_time or 0),
                "dimensions": data.get("dimensions", []),
                "seq_id": data.get("seq_id"),
                "dedupe_md5": data.get("dedupe_md5"),
                "dedupe_keys": data.get("event", {}).get("dedupe_keys"),
                "extra_info": data.get("extra_info"),
                "dimension_message": AlertDimensionFormatter.get_dimensions_str(data.get("dimensions", [])),
                "metric_display": [{"id": metric, "name": metric} for metric in cleaned_data.get("metric") or []],
                "target_key": AlertDimensionFormatter.get_target_key(
                    cleaned_data.get("target_type"), data.get("dimensions")
                ),
            }
        )

        # 动态字段排除：
        # 根据调用参数移除指定字段（如敏感信息或非必要字段）
        # 使用安全pop方法避免KeyError异常
        if exclude:
            for field in exclude:
                cleaned_data.pop(field, None)

        return cleaned_data

    @classmethod
    def adapt_to_event(cls, alert):
        """
        将告警数据适配为事件数据
        """
        event = alert["event"]

        for field in ["id", "status", "assignee"]:
            event[field] = alert.get(field)
        return event

    def top_n(self, fields: list, size=10, translators: dict = None, char_add_quotes=True):
        translators = {
            "metric": MetricTranslator(name_format="{name} ({id})", bk_biz_ids=self.bk_biz_ids),
            "bk_biz_id": BizTranslator(),
            "strategy_id": StrategyTranslator(),
            "category": CategoryTranslator(),
            "plugin_id": PluginTranslator(),
        }
        return super().top_n(fields, size, translators, char_add_quotes)

    def list_tags(self):
        """
        获取告警标签列表
        :return:
        [
            {
                "id": "device_name",
                "name": "device_name",
                "count": 1234,
            }
        ]
        """
        search_object = self.get_search_object()
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object)

        # tags_count = defaultdict(int)
        # tags_name = {}
        #
        # for hit in search_object.source(fields=["event.tags", "dimensions"]).scan():
        #     hit_dict = hit.to_dict()
        #     for dimension in hit_dict.get("dimensions", []):
        #         if not dimension["key"].startswith("tags."):
        #             continue
        #         key = dimension["key"][len("tags.") :]
        #         if key != dimension.get("display_key"):
        #             tags_name[key] = dimension["display_key"]
        #
        #     for tag in hit_dict.get("event", {}).get("tags", []):
        #         tags_count[tag["key"]] += 1
        #
        # result = [
        #     {"id": f"tags.{key}", "name": tags_name.get(key, key), "count": value}
        #     for key, value in tags_count.items()
        #     if key not in IGNORED_TAGS
        # ]
        # result.sort(key=lambda item: item["count"], reverse=True)

        search_object.aggs.bucket("tags", "nested", path="event.tags").bucket(
            "key", "terms", field="event.tags.key", size=1000
        )
        search_result = search_object[:0].execute()

        result = []
        if search_result.aggs:
            result = [
                {
                    "id": f"tags.{bucket.key}",
                    "name": bucket.key,
                    "count": bucket.doc_count,
                }
                for bucket in search_result.aggs.tags.key.buckets
                if bucket.key not in IGNORED_TAGS
            ]

        return result
