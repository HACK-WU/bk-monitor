"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import time

from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django_elasticsearch_dsl.registries import registry
from elasticsearch_dsl import InnerDoc, Search, field

from bkmonitor.documents import EventDocument
from bkmonitor.documents.base import BaseDocument, Date
from bkmonitor.documents.constants import ES_INDEX_SETTINGS
from bkmonitor.models import NO_DATA_TAG_DIMENSION
from constants.alert import (
    EVENT_SEVERITY,
    HANDLE_STAGE_DICT,
    TARGET_DIMENSIONS,
    EventStatus,
)
from constants.data_source import DataSourceLabel, DataTypeLabel
from core.errors.alert import AlertNotFoundError


@registry.register_document
class AlertDocument(BaseDocument):
    """
    告警数据文档模型，用于Elasticsearch存储与检索

    该类定义了告警数据的完整字段结构和索引策略，包含以下核心功能：
    1. 告警生命周期管理（创建/更新/结束时间）
    2. 多维度责任人体系（负责人/关注人/升级人）
    3. 状态流转控制（确认/屏蔽/处理状态）
    4. 时序数据关联（事件序列/持续时间）
    5. 多维度过滤与聚合能力（标签/维度属性）

    索引策略采用时间分片方案，支持高效的时间范围查询
    """

    REINDEX_ENABLED = True
    REINDEX_QUERY = Search().filter("term", status=EventStatus.ABNORMAL).to_dict()

    bk_tenant_id = field.Keyword()
    id = field.Keyword(required=True)  # 告警唯一标识符（含时间戳+序列号）
    seq_id = field.Long()  # 序列化ID（用于排序）

    alert_name = field.Text(fields={"raw": field.Keyword()})  # 告警名称（全文检索+精确匹配）
    strategy_id = field.Keyword()  # 关联策略ID

    # 告警时间体系
    create_time = Date(format=BaseDocument.DATE_FORMAT)  # 告警创建时间（服务器时间）
    update_time = Date(format=BaseDocument.DATE_FORMAT)  # 最后更新时间
    begin_time = Date(format=BaseDocument.DATE_FORMAT)  # 告警开始时间
    end_time = Date(format=BaseDocument.DATE_FORMAT)  # 告警结束时间
    latest_time = Date(format=BaseDocument.DATE_FORMAT)  # 最新异常时间
    first_anomaly_time = Date(format=BaseDocument.DATE_FORMAT)  # 首次异常时间

    # 责任人体系字段
    assignee = field.Keyword(multi=True)  # 主负责人（可多人）
    appointee = field.Keyword(multi=True)  # 指定处理人
    supervisor = field.Keyword(multi=True)  # 升级监督人
    follower = field.Keyword(multi=True)  # 只读关注人

    # 时间统计字段
    duration = field.Long()  # 持续时间（毫秒）
    ack_duration = field.Long()  # 确认耗时（毫秒）

    # 关联事件对象
    event = field.Object(doc_class=type("EventInnerDoc", (EventDocument, InnerDoc), {}))  # 最新事件对象
    severity = field.Integer()  # 严重程度等级
    status = field.Keyword()  # 当前状态（open/closed/ack等）

    # 状态标志位
    is_blocked = field.Boolean()  # 是否阻断状态
    is_handled = field.Boolean()  # 是否已处理
    is_ack = field.Boolean()  # 是否已确认
    is_ack_noticed = field.Boolean()  # 确认通知状态
    ack_operator = field.Keyword()  # 确认操作者
    is_shielded = field.Boolean()  # 是否被屏蔽
    shield_left_time = field.Integer()  # 剩余屏蔽时间
    shield_id = field.Keyword(multi=True)  # 屏蔽规则ID列表
    handle_stage = field.Keyword(multi=True)  # 处理阶段标记
    labels = field.Keyword(multi=True)  # 标签集合

    # 分配标签结构
    assign_tags = field.Nested(
        properties={
            "key": field.Keyword(),  # 标签键
            "value": field.Text(required=True, fields={"raw": field.Keyword(ignore_above=256)}),  # 标签值
        }
    )

    # 状态流转字段
    next_status = field.Keyword()  # 下一状态标识
    next_status_time = Date(format=BaseDocument.DATE_FORMAT)  # 状态切换时间

    # 关联实体
    incident_id = field.Keyword()  # 关联故障ID
    dedupe_md5 = field.Keyword()  # 去重指纹

    class Dimension(InnerDoc):
        """
        多维度过滤嵌套文档结构

        定义告警的多维属性标签，支持以下字段：
        key: 维度键（英文标识）
        value: 维度值（原始值）
        display_key: 展示用键名（中文）
        display_value: 展示用值（中文）

        to_dict方法强制保留空值字段
        """

        key = field.Keyword()
        value = field.Keyword()
        display_key = field.Keyword()
        display_value = field.Keyword()

        def to_dict(self) -> dict:
            """序列化时保留空字段"""
            return super().to_dict(skip_empty=False)

    dimensions = field.Object(enabled=False, multi=True, doc_class=Dimension)  # 维度集合（禁用全文检索）
    extra_info = field.Object(enabled=False)  # 扩展信息（策略快照等，禁用全文检索）

    class Index:
        name = "bkfta_alert"
        settings = ES_INDEX_SETTINGS.copy()

    def get_index_time(self):
        """
        获取文档索引时间戳

        返回值:
            int - 从文档ID解析出的时间戳（秒）
        """
        return self.parse_timestamp_by_id(self.id)

    @classmethod
    def parse_timestamp_by_id(cls, uuid: str) -> int:
        """
        从UUID格式ID提取时间戳

        参数:
            uuid: 告警唯一标识（前10位为时间戳）

        返回值:
            int - Unix时间戳（秒）
        """
        return int(str(uuid)[:10])

    @classmethod
    def parse_sequence_by_id(cls, uuid: str) -> int:
        """
        从UUID格式ID提取序列号

        参数:
            uuid: 告警唯一标识（第10-20位为序列号）

        返回值:
            int - 序列号数值
        """
        return int(str(uuid)[10:])

    @classmethod
    def get(cls, id) -> "AlertDocument":
        """
        根据ID获取单条告警记录

        参数:
            id: 告警唯一标识符

        返回值:
            AlertDocument实例

        异常:
            ValueError: ID格式错误
            AlertNotFoundError: 未找到对应告警

        执行流程:
        1. 解析ID获取时间戳
        2. 构建精确查询条件
        3. 执行ES搜索
        4. 返回匹配的文档实例
        """
        try:
            ts = cls.parse_timestamp_by_id(id)
        except Exception:
            raise ValueError(f"invalid alert_id: {id}")
        hits = cls.search(start_time=ts, end_time=ts).filter("term", id=id).execute().hits
        if not hits:
            raise AlertNotFoundError({"alert_id": id})
        return cls(**hits[0].to_dict())

    @classmethod
    def mget(cls, ids, fields: list = None) -> list["AlertDocument"]:
        """
        批量获取告警记录

        参数:
            ids: 告警ID列表（支持字符串/整型）
            fields: 需要返回的字段列表（None表示返回全部字段）

        返回值:
            AlertDocument实例列表（按匹配顺序排列）

        执行流程:
        1. 解析ID时间范围：从ID中提取时间戳确定查询窗口
        2. 构建查询条件：组合时间范围过滤和ID集合过滤
        3. 字段裁剪：根据fields参数限制返回字段
        4. 执行查询：最大返回5000条记录（防止内存溢出）
        """
        if not ids:
            return []

        # 解析ID时间范围以确定索引查询区间
        start_time = None
        end_time = None
        for id in ids:
            try:
                ts = cls.parse_timestamp_by_id(id)
            except Exception:  # NOCC:broad-except(设计如此:)
                continue
            if not start_time:
                start_time = ts
            else:
                start_time = min(start_time, ts)
            if not end_time:
                end_time = ts
            else:
                end_time = max(end_time, ts)

        # 构建带时间范围约束的批量查询条件
        search = cls.search(start_time=start_time, end_time=end_time).filter("terms", id=ids)

        # 应用字段裁剪策略（None表示不裁剪）
        if fields:
            # .source()方法用于指定返回的字段列表,类似于ORM中的.only()
            search = search.source(fields=fields)

        # 执行查询并转换为文档实例列表
        return [cls(**hit.to_dict()) for hit in search.params(size=5000).scan()]

    @classmethod
    def get_by_dedupe_md5(cls, dedupe_md5, start_time=None) -> "AlertDocument":
        search_object = cls.search(all_indices=True)
        if start_time:
            search_object = search_object.filter("range", latest_time={"gte": start_time})
        hits = search_object.filter("term", dedupe_md5=dedupe_md5).sort(*["-create_time"]).execute().hits
        if not hits:
            raise AlertNotFoundError({"alert_id": dedupe_md5})
        return cls(**hits[0].to_dict())

    # @property
    # def duration(self) -> int:
    #     """
    #     持续时间
    #     """
    #     # 加上60秒的冗余，避免显示为0
    #     return self.latest_time - self.begin_time + 60

    @cached_property
    def severity_display(self):
        """
        级别名称
        :rtype: str
        """
        for severity, display in EVENT_SEVERITY:
            if severity == self.severity:
                return str(display)
        return ""

    @property
    def strategy(self):
        if not self.extra_info or getattr(self.extra_info, "strategy", None) is None:
            return None
        return self.extra_info["strategy"].to_dict()

    @property
    def assign_group(self):
        if not self.extra_info or not getattr(self.extra_info, "matched_rule_info", None):
            return {}
        matched_rule_info = self.extra_info["matched_rule_info"].to_dict()
        return matched_rule_info.get("group_info") or {}

    @property
    def agg_dimensions(self):
        if not self.extra_info or "agg_dimensions" not in self.extra_info:
            return []
        return self.extra_info["agg_dimensions"]

    @property
    def origin_alarm(self):
        if not self.extra_info or "origin_alarm" not in self.extra_info:
            return None
        return self.extra_info["origin_alarm"].to_dict()

    @property
    def stage_display(self):
        """
        处理阶段
        """
        if self.is_shielded:
            return _("已屏蔽")
        if self.is_ack:
            return _("已确认")
        if self.handle_stage:
            return HANDLE_STAGE_DICT.get(self.handle_stage[0])
        if self.is_handled:
            return _("已通知")
        if self.is_blocked:
            return _("已流控")
        return ""

    @property
    def event_document(self):
        return EventDocument(**self.event.to_dict())

    @property
    def target_dimensions(self):
        # 目标维度
        return [d.to_dict() for d in self.dimensions if d.key in TARGET_DIMENSIONS]

    @property
    def common_dimensions(self):
        # 非目标维度
        return [d.to_dict() for d in self.dimensions if d.key not in TARGET_DIMENSIONS]

    @property
    def common_dimension_tuple(self) -> tuple:
        return tuple(sorted([(d["key"], d["value"]) for d in self.common_dimensions], key=lambda x: x[0]))

    @property
    def is_composite_strategy(self):
        """
        检查是否为关联告警策略
        """
        strategy = self.strategy
        if not strategy:
            return False
        for item in strategy["items"]:
            for query_config in item["query_configs"]:
                if query_config["data_type_label"] == DataTypeLabel.ALERT:
                    return True
        return False

    @property
    def is_fta_event_strategy(self):
        """
        检查是否为自愈事件策略
        """
        strategy = self.strategy
        if not strategy:
            return False
        for item in strategy["items"]:
            for query_config in item["query_configs"]:
                if (
                    query_config["data_type_label"] == DataTypeLabel.EVENT
                    and query_config["data_source_label"] == DataSourceLabel.BK_FTA
                ):
                    return True
        return False

    @property
    def status_detail(self):
        if self.status == EventStatus.ABNORMAL and getattr(self.extra_info, "is_recovering", False):
            return EventStatus.RECOVERING
        return self.status

    @property
    def cycle_handle_record(self):
        if not self.extra_info or getattr(self.extra_info, "cycle_handle_record", None) is None:
            return {}
        return self.extra_info["cycle_handle_record"].to_dict()

    def is_no_data(self):
        """
        是否为无数据告警
        """
        event = self.event.to_dict()
        for dimension in event.get("tags", []):
            if NO_DATA_TAG_DIMENSION == dimension["key"]:
                return True
        return False

    def refresh_duration(self):
        """
        刷新告警持续时间
        """
        if self.is_composite_strategy:
            # 如果是关联告警，则按当前时间计算告警持续时间
            duration = int(time.time()) - self.first_anomaly_time
        else:
            # 其他情况，按照最新事件时间计算持续时间
            duration = self.latest_time - self.first_anomaly_time
            # 设置60s的冗余时间，避免显示为0
        duration = max(duration, 60)
        self.duration = duration
