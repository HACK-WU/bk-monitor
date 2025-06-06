"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2022 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from functools import lru_cache

from django.utils.functional import cached_property
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes

from constants.alert import EventSeverity
from constants.apm import CachedEnum, OtlpKey, SpanKindKey, TelemetryDataType

GLOBAL_CONFIG_BK_BIZ_ID = 0
DEFAULT_EMPTY_NUMBER = 0
COLLECT_SERVICE_CONFIG_KEY = "collect_service"
DEFAULT_NO_DATA_PERIOD = 10  # minute
DEFAULT_DIMENSION_DATA_PERIOD = 5  # minute
NODATA_ERROR_STRATEGY_CONFIG_KEY = "nodata_error_strategy_id"

nodata_error_strategy_config_mapping = {
    TelemetryDataType.TRACE.value: "nodata_error_strategy_id",
    TelemetryDataType.METRIC.value: "nodata_error_metric_strategy_id",
    TelemetryDataType.LOG.value: "nodata_error_log_strategy_id",
    TelemetryDataType.PROFILING.value: "nodata_error_profiling_strategy_id",
}

DEFAULT_APM_APP_QPS = 500

DEFAULT_APM_APP_EVENT_CONFIG = {"is_enabled_metric_tags": False}

OTLP_JAEGER_SPAN_KIND = {2: "server", 3: "client", 4: "producer", 5: "consumer", 1: "internal", 0: "unset"}
IDENTIFY_KEYS = ["db.system", "http.target", "messaging.system", "rpc.system"]

DEFAULT_DIFF_TRACE_MAX_NUM = 5

# 随组件类型变化的where条件 用于指标值查询 (如果 where 里面有 or 连接符的话不能使用这个因为不能设置优先级)
component_where_mapping = {
    "db": {"key": "db_system", "method": "eq", "value": ["{predicate_value}"], "condition": "and"},
    "messaging": {"key": "messaging_system", "method": "eq", "value": ["{predicate_value}"], "condition": "and"},
}

# 随组件类型变化的where条件 用于指标值查询
component_filter_mapping = {
    "db": {"db_system": "{predicate_value}"},
    "messaging": {"messaging_system": "{predicate_value}"},
}


COLUMN_KEY_PROFILING_DATA_COUNT = "profiling_data_count"
COLUMN_KEY_PROFILING_DATA_STATUS = "profiling_data_status"


class TraceKind:
    # 所有trace
    ALL = "all"
    # 有根span的trace
    HAVE_ROOT_SPAN = "have_root_span"
    # 有service的trace
    HAVE_SERVICE_SPAN = "have_service_span"


class AlertStatusEnum:
    NORMAL = 1
    ALARMING = 2


class SceneEventKey:
    SWITCH_SCENES_TYPE = "switch_scenes_type"
    SWITCH_SCENE = "switch_scene"


class ApmScene:
    APM_APPLICATION_SCENE_ID = "apm_application"
    APM_SERVICE_SCENE_ID = "apm_service"
    DETAIL = "detail"
    OVERVIEW = "overview"


class DbCategoryEnum:
    ALL = "all"
    DB_SLOW = "db_slow"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.ALL: _("全部"),
            cls.DB_SLOW: _("慢语句"),
        }.get(key, key)

    @classmethod
    def get_db_filter_fields(cls):
        return [
            {
                "id": cls.ALL,
                "name": cls.get_label_by_key(cls.ALL),
                "icon": "icon-gailan",
            },
            {
                "id": cls.DB_SLOW,
                "name": cls.get_label_by_key(cls.DB_SLOW),
                "icon": "icon-DB",
            },
        ]


class CategoryEnum:
    HTTP = "http"
    RPC = "rpc"
    DB = "db"
    MESSAGING = "messaging"
    ASYNC_BACKEND = "async_backend"
    ALL = "all"
    OTHER = "other"

    # profile 为新的展示类型 只用来展示在 serviceList 无实际作用
    PROFILING = "profiling"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.HTTP: _("网页"),
            cls.RPC: _("远程调用"),
            cls.DB: _("数据库"),
            cls.MESSAGING: _("消息队列"),
            cls.ASYNC_BACKEND: _("后台任务"),
            cls.ALL: _("全部"),
            cls.OTHER: _("其他"),
        }.get(key, key)

    @classmethod
    def get_remote_service_label_by_key(cls, key: str):
        return {cls.HTTP: _("网页(自定义服务)")}.get(key, key)

    @classmethod
    def get_filter_fields(cls):
        return [
            {
                "id": cls.ALL,
                "name": cls.get_label_by_key(cls.ALL),
                "icon": "icon-gailan",
            },
            {
                "id": cls.HTTP,
                "name": cls.get_label_by_key(cls.HTTP),
                "icon": "icon-wangye",
            },
            {
                "id": cls.RPC,
                "name": cls.get_label_by_key(cls.RPC),
                "icon": "icon-yuanchengfuwu",
            },
            {
                "id": cls.DB,
                "name": cls.get_label_by_key(cls.DB),
                "icon": "icon-shujuku",
            },
            {
                "id": cls.MESSAGING,
                "name": cls.get_label_by_key(cls.MESSAGING),
                "icon": "icon-xiaoxizhongjianjian",
            },
            {
                "id": cls.ASYNC_BACKEND,
                "name": cls.get_label_by_key(cls.ASYNC_BACKEND),
                "icon": "icon-renwu",
            },
            {
                "id": cls.OTHER,
                "name": cls.get_label_by_key(cls.OTHER),
                "icon": "icon-mc-service-unknown",
            },
        ]

    @classmethod
    def classify(cls, span):
        # TODO: 转为InferenceHandler进行推断
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.HTTP_METHOD):
            return cls.HTTP
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.RPC_SERVICE):
            return cls.RPC
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.DB_SYSTEM):
            return cls.DB
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.MESSAGING_SYSTEM):
            return cls.MESSAGING
        return cls.OTHER

    @classmethod
    def list_span_keys(cls):
        """获取所有分类字段"""
        return [
            SpanAttributes.DB_SYSTEM,
            SpanAttributes.MESSAGING_SYSTEM,
            SpanAttributes.RPC_SYSTEM,
            SpanAttributes.HTTP_METHOD,
            SpanAttributes.MESSAGING_DESTINATION,
        ]

    @classmethod
    def list_component_generate_keys(cls):
        """获取 APM 手动处理(手动生成服务节点)的字段"""
        return [
            SpanAttributes.DB_SYSTEM,
            SpanAttributes.MESSAGING_SYSTEM,
        ]


class CalculationMethod:
    # 错误率
    ERROR_RATE = "error_rate"
    # 错误数
    ERROR_COUNT = "error_count"
    # 平均响应时间
    AVG_DURATION = "avg_duration"
    # 请求数
    REQUEST_COUNT = "request_count"
    # 实例数量
    INSTANCE_COUNT = "instance_count"
    # 健康度
    APDEX = "apdex"
    # 耗时 Bucket
    DURATION_BUCKET = "duration_bucket"

    # 服务间调用错误率
    SERVICE_FLOW_ERROR_RATE = "service_flow_error_rate"
    # 服务间请求数
    SERVICE_FLOW_COUNT = "service_flow_request_count"
    # 服务间耗时
    SERVICE_FLOW_DURATION = "service_flow_duration"


class ApdexColor:
    GRAY = 1
    YELLOW = 2
    RED = 3


class Apdex:
    DIMENSION_KEY = "apdex_type"
    SATISFIED = "satisfied"
    TOLERATING = "tolerating"
    FRUSTRATED = "frustrated"
    ERROR = "error"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {cls.SATISFIED: _("满意"), cls.TOLERATING: _("可容忍"), cls.FRUSTRATED: _("烦躁期")}.get(key, key)

    @classmethod
    def get_status_by_key(cls, key: str):
        return {
            cls.SATISFIED: {"type": Status.SUCCESS, "text": cls.get_label_by_key(key)},
            cls.TOLERATING: {"type": Status.WAITING, "text": cls.get_label_by_key(key)},
            cls.FRUSTRATED: {"type": Status.FAILED, "text": cls.get_label_by_key(key)},
        }.get(key, {"type": None, "text": "--"})


class Status:
    """状态"""

    NORMAL = "normal"
    WARNING = "warning"
    FAILED = "failed"
    SUCCESS = "success"
    DISABLED = "disabled"
    WAITING = "waiting"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.NORMAL: _("正常"),
            cls.WARNING: _("预警"),
            cls.FAILED: _("异常"),
            cls.SUCCESS: _("成功"),
            cls.DISABLED: _("禁用"),
            cls.WAITING: _("等待"),
        }.get(key, key)


class DataStatus:
    NORMAL = "normal"
    NO_DATA = "no_data"
    DISABLED = "disabled"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.NORMAL: _("正常"),
            cls.NO_DATA: _("无数据"),
            cls.DISABLED: _("未开启"),
        }.get(key, key)

    @classmethod
    def get_status_by_key(cls, key: str):
        return {
            cls.NORMAL: {"type": Status.SUCCESS, "text": cls.get_label_by_key(key)},
            cls.NO_DATA: {"type": Status.FAILED, "text": cls.get_label_by_key(key)},
        }.get(key, {"type": Status.FAILED, "text": cls.get_label_by_key(key)})


class StorageStatus:
    NORMAL = "normal"
    ERROR = "error"
    DISABLED = "disabled"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.NORMAL: _("正常"),
            cls.ERROR: _("异常"),
            cls.DISABLED: _("未开启"),
        }.get(key, key)


class ServiceStatus(EventSeverity):
    NORMAL = 9999

    @classmethod
    def get_label_by_key(cls, key: int):
        return {
            cls.NORMAL: _("无告警"),
            cls.FATAL: _("致命"),
            cls.REMIND: _("提醒"),
            cls.WARNING: _("预警"),
        }.get(key, key)

    @classmethod
    def get_status_by_key(cls, key: int):
        return {
            cls.NORMAL: {"type": Status.SUCCESS, "text": cls.get_label_by_key(key)},
            cls.FATAL: {"type": Status.FAILED, "text": cls.get_label_by_key(key)},
            cls.REMIND: {"type": Status.WARNING, "text": cls.get_label_by_key(key)},
            cls.WARNING: {"type": Status.WARNING, "text": cls.get_label_by_key(key)},
        }.get(key, {"type": Status.FAILED, "text": cls.get_label_by_key(key)})

    @classmethod
    def get_default(cls):
        return cls.NORMAL


class DefaultApdex:
    """默认Apdex配置值 单位: ms"""

    DEFAULT = 2000
    HTTP = 800
    DB = 800
    RPC = 2000
    BACKEND = 800
    MESSAGE = 2000


class DefaultSetupConfig:
    DEFAULT_ES_RETENTION_DAYS = 7
    DEFAULT_ES_NUMBER_OF_REPLICAS = 1
    DEFAULT_ES_RETENTION_DAYS_MAX = 7
    DEFAULT_ES_NUMBER_OF_REPLICAS_MAX = 3
    PRIVATE_ES_RETENTION_DAYS_MAX = 30
    PRIVATE_ES_NUMBER_OF_REPLICAS_MAX = 10


class BizConfigKey:
    DEFAULT_ES_RETENTION_DAYS_MAX = "default_es_retention_days_max"
    PRIVATE_ES_RETENTION_DAYS_MAX = "private_es_retention_days_max"
    DEFAULT_ES_NUMBER_OF_REPLICAS_MAX = "default_es_number_of_replicas_max"
    PRIVATE_ES_NUMBER_OF_REPLICAS_MAX = "private_es_number_of_replicas_max"


class AlertColor:
    # 红色
    RED = 1
    # 黄色
    YELLOW = 2
    # 绿色
    GREEN = 3


class AlertLevel:
    # 致命
    ERROR = 1
    # 告警
    WARN = 2
    # 提醒
    INFO = 3

    @classmethod
    def get_label(cls, key):
        return {
            cls.ERROR: "error",
            cls.WARN: "warn",
            cls.INFO: "info",
        }.get(key, key)


class AlertStatus:
    # 未恢复
    ABNORMAL = "ABNORMAL"
    # 已恢复
    RECOVERED = "RECOVERED"
    # 已失效
    CLOSED = "CLOSED"


class ServiceDetailReqTypeChoices:
    GET = "get"
    SET = "set"
    DEL = "del"

    @classmethod
    def choices(cls):
        return [(cls.GET, "获取"), (cls.SET, "更新"), (cls.DEL, "删除")]


class ServiceRelationLogTypeChoices:
    OTHER = "other"
    BK_LOG = "bk_log"

    @classmethod
    def choices(cls):
        return [
            (cls.BK_LOG, "日志平台"),
            (cls.OTHER, "其他日志"),
        ]

    @classmethod
    def choice_list(cls):
        return [{"id": choice_id, "name": name} for choice_id, name in cls.choices()]


class CMDBCategoryIconMap:
    icon_map = {
        "数据库": "db",
        "消息队列": "message",
        "HTTP 服务": "http",
        "存储": "storage",
    }

    @classmethod
    def get_icon_id(cls, category_name: str):
        if not category_name:
            return ""
        return cls.icon_map.get(category_name.lower())


class SamplerTypeChoices:
    """采样类型枚举"""

    RANDOM = "random"
    TAIL = "tail"
    EMPTY = "empty"

    @classmethod
    def choices(cls):
        return [
            (cls.RANDOM, "随机采样"),
            (cls.TAIL, "尾部采样"),
            (cls.EMPTY, "不采样"),
        ]


class DefaultSamplerConfig:
    """默认采样配置"""

    TYPE = SamplerTypeChoices.RANDOM
    PERCENTAGE = 100


class DefaultInstanceNameConfig:
    """默认实例名配置"""

    SERVICE_NAME = OtlpKey.get_resource_key(ResourceAttributes.SERVICE_NAME)
    LANGUAGE = OtlpKey.get_resource_key(ResourceAttributes.TELEMETRY_SDK_LANGUAGE)
    HOST_NAME = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_NAME)
    HOST_IP = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_IP)
    HOST_PORT = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_PORT)

    # 默认实例名配置 语言:服务模块:主机名称:IP:端口
    DEFAULT_INSTANCE_NAME_COMPOSITION = [LANGUAGE, SERVICE_NAME, HOST_NAME, HOST_IP, HOST_PORT]

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.SERVICE_NAME: _("服务模块"),
            cls.LANGUAGE: _("语言"),
            cls.HOST_NAME: _("主机名称"),
            cls.HOST_IP: "IP",
            cls.HOST_PORT: _("端口"),
        }.get(key, key)


class DefaultDimensionConfig:
    """默认维度配置"""

    # todo 这里列举了一部分 待确认后再补充
    DEFAULT_DIMENSIONS = [
        {
            "span_kind": SpanKindKey.SERVER,
            "predicate_key": OtlpKey.get_attributes_key(SpanAttributes.HTTP_METHOD),
            "dimensions": [
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_SERVER_NAME),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_CLIENT_IP),
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_NAME),
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_IP),
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_PORT),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_METHOD),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_ROUTE),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_SCHEME),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_FLAVOR),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_RESPONSE_CONTENT_LENGTH),
                OtlpKey.get_attributes_key(SpanAttributes.HTTP_STATUS_CODE),
            ],
        },
        {
            "span_kind": SpanKindKey.SERVER,
            "predicate_key": OtlpKey.get_attributes_key(SpanAttributes.RPC_SYSTEM),
            "dimensions": [
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_NAME),
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_IP),
                OtlpKey.get_attributes_key(SpanAttributes.NET_HOST_PORT),
                OtlpKey.get_attributes_key(SpanAttributes.RPC_METHOD),
                OtlpKey.get_attributes_key(SpanAttributes.RPC_SERVICE),
                OtlpKey.get_attributes_key(SpanAttributes.RPC_SYSTEM),
                OtlpKey.get_attributes_key(SpanAttributes.RPC_GRPC_STATUS_CODE),
            ],
        },
    ]


class InstanceDiscoverKeys:
    """实例名配置可选项(固定字段)"""

    SDK_LANGUAGE = OtlpKey.get_resource_key(ResourceAttributes.TELEMETRY_SDK_LANGUAGE)
    SDK_VERSION = OtlpKey.get_resource_key(ResourceAttributes.TELEMETRY_SDK_VERSION)
    SDK_NAME = OtlpKey.get_resource_key(ResourceAttributes.TELEMETRY_SDK_NAME)
    SERVICE_NAME = OtlpKey.get_resource_key(ResourceAttributes.SERVICE_NAME)
    SERVICE_VERSION = OtlpKey.get_resource_key(ResourceAttributes.SERVICE_VERSION)
    BK_DATA_ID = OtlpKey.get_resource_key("bk_data_id")
    HOST_NAME = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_NAME)
    HOST_IP = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_IP)
    HOST_PORT = OtlpKey.get_resource_key(SpanAttributes.NET_HOST_PORT)

    instance_keys = {
        SDK_LANGUAGE: {"name": SDK_LANGUAGE, "alias": _("SDK语言"), "fix": True},
        SDK_VERSION: {"name": SDK_VERSION, "alias": _("SDK版本"), "fix": False},
        SDK_NAME: {"name": SDK_NAME, "alias": _("SDK名称"), "fix": False},
        SERVICE_NAME: {"name": SERVICE_NAME, "alias": _("服务名称"), "fix": True},
        SERVICE_VERSION: {"name": SERVICE_VERSION, "alias": _("服务版本"), "fix": False},
        BK_DATA_ID: {"name": BK_DATA_ID, "alias": _("蓝鲸DataId"), "fix": False},
        HOST_NAME: {"name": HOST_NAME, "alias": _("主机名称"), "fix": True},
        HOST_IP: {"name": HOST_IP, "alias": _("主机IP"), "fix": True},
        HOST_PORT: {"name": HOST_PORT, "alias": _("主机端口"), "fix": True},
    }

    @classmethod
    def get_label_by_key(cls, key):
        for k, v in cls.instance_keys.items():
            if k == key:
                return v["alias"]

        return None

    @classmethod
    def get_list(cls):
        res = []
        for k, v in cls.instance_keys.items():
            if v["fix"]:
                res.append({"id": k, "name": v["name"], "alias": v["alias"]})

        return res


class ApdexConfigEnum:
    """apdex可配置项"""

    DEFAULT = "apdex_default"
    HTTP = "apdex_http"
    DB = "apdex_db"
    MESSAGING = "apdex_messaging"
    BACKEND = "apdex_backend"
    RPC = "apdex_rpc"


class ApdexCategoryMapping:
    """
    服务apdex与服务分类的配置关联
    比如http的服务只能配置apdex_http的值
    """

    mapping = (
        (CategoryEnum.HTTP, ApdexConfigEnum.HTTP, DefaultApdex.HTTP),
        (CategoryEnum.DB, ApdexConfigEnum.DB, DefaultApdex.DB),
        (CategoryEnum.MESSAGING, ApdexConfigEnum.MESSAGING, DefaultApdex.MESSAGE),
        (CategoryEnum.ASYNC_BACKEND, ApdexConfigEnum.BACKEND, DefaultApdex.BACKEND),
        (CategoryEnum.RPC, ApdexConfigEnum.RPC, DefaultApdex.RPC),
    )

    @classmethod
    def get_apdex_by_category(cls, category):
        for first, second, third in cls.mapping:
            if first == category:
                return second

        return ApdexConfigEnum.DEFAULT

    @classmethod
    def get_apdex_default_value_by_category(cls, apdex_key):
        for first, second, third in cls.mapping:
            if second == apdex_key:
                return third

        return DefaultApdex.DEFAULT


class CustomServiceType:
    """自定义服务分类"""

    HTTP = "http"

    @classmethod
    def choices(cls):
        return [
            (cls.HTTP, "http"),
        ]


class CustomServiceMatchType:
    AUTO = "auto"
    MANUAL = "manual"

    @classmethod
    def choices(cls):
        return [
            (cls.AUTO, "自动匹配"),
            (cls.MANUAL, "手动匹配"),
        ]


class TopoNodeKind:
    """节点的类型 对应API侧ApmTopoDiscoverRule.TOPO_*"""

    SERVICE = "service"
    COMPONENT = "component"
    REMOTE_SERVICE = "remote_service"

    # 虚拟服务 (Flow 指标处)
    VIRTUAL_SERVICE = "virtualService"

    @classmethod
    def get_label_by_key(cls, key: str):
        return {
            cls.SERVICE: _("服务"),
            cls.COMPONENT: _("服务组件"),
            cls.REMOTE_SERVICE: _("自定义服务"),
            cls.VIRTUAL_SERVICE: _("虚拟服务"),
        }.get(key, key)


class TopoVirtualServiceKind:
    """虚拟服务中的分类"""

    # 虚拟主调服务
    CALLER = "bk_vServiceCaller"
    # 虚拟被调服务
    CALLEE = "bk_vServiceCallee"

    @classmethod
    def all_kinds(cls):
        return [cls.CALLER, cls.CALLEE]


class TraceFilterField:
    """trace检索表头支持获取候选值的字段"""

    ROOT_SERVICE = "root_service"
    ROOT_SPAN_NAME = "root_span_name"
    ROOT_STATUS_CODE = "root_status_code"
    ROOT_CATEGORY = "root_category"

    @classmethod
    def choices(cls):
        return [
            (cls.ROOT_SERVICE, "入口服务"),
            (cls.ROOT_SPAN_NAME, "入口接口"),
            (cls.ROOT_STATUS_CODE, "状态码"),
            (cls.ROOT_CATEGORY, "调用类型"),
        ]


class QueryMode:
    """查询视角 Trace/Span"""

    TRACE = "trace"
    SPAN = "span"

    @classmethod
    def choices(cls):
        return [
            (cls.TRACE, "Trace 视角"),
            (cls.SPAN, "Span 视角"),
        ]


# TRPC 场景默认设置（表头、常用筛选项）
TRPC_TRACE_VIEW_CONFIG = {
    "span_config": {
        "resident_setting": [
            "trace_id",
            "elapsed_time",
            "attributes.trpc.namespace",  # "物理环境"
            "attributes.trpc.envname",  # "用户环境"
            "attributes.trpc.caller_server",  # "主调服务"
            "attributes.trpc.caller_service",  # "主调 Service"
            "attributes.trpc.caller_method",  # "主调接口"
            "attributes.trpc.caller_ip",  # "主调 IP"
            "attributes.trpc.caller_container",  # "主调容器"
            "attributes.trpc.callee_server",  # "被调服务"
            "attributes.trpc.callee_service",  # "被调 Service"
            "attributes.trpc.callee_method",  # "被调接口"
            "attributes.trpc.callee_ip",  # "被调 IP"
            "attributes.trpc.callee_container",  # "被调容器"
            "attributes.trpc.status_code",  # "tRPC 状态码"
        ],
        "display_columns": [
            "span_id",
            "kind",
            "start_time",
            "elapsed_time",
            "attributes.trpc.caller_service",  # "主调 Service"
            "attributes.trpc.caller_method",  # "主调接口"
            "attributes.trpc.callee_service",  # "被调 Service"
            "attributes.trpc.callee_method",  # "被调接口"
            "attributes.trpc.status_code",  # "tRPC 状态码"
            "attributes.trpc.envname",  # "用户环境"
            "status.code",
            "trace_id",
        ],
    },
    "trace_config": {
        "resident_setting": [
            "trace_id",
            "trace_duration",
            "collections.resource.service.name",
            "collections.span_name",
        ],
        "display_columns": [
            "trace_id",
            "min_start_time",
            "root_span_name",
            "root_service",
            "root_service_span_name",
            "root_service_category",
            "root_service_status_code",
            "trace_duration",
            "span_count",
            "service_count",
        ],
    },
}

# Trace 检索下默认场景的设置（表头、常用筛选项）
DEFAULT_TRACE_VIEW_CONFIG = {
    "span_config": {
        "resident_setting": ["trace_id", "elapsed_time", "resource.service.name", "span_name"],
        "display_columns": [
            "span_id",
            "span_name",
            "start_time",
            "end_time",
            "elapsed_time",
            "status.code",
            "kind",
            "resource.service.name",
            "trace_id",
        ],
    },
    "trace_config": {
        "resident_setting": [
            "trace_id",
            "trace_duration",
            "collections.resource.service.name",
            "collections.span_name",
        ],
        "display_columns": [
            "trace_id",
            "min_start_time",
            "root_span_name",
            "root_service",
            "root_service_span_name",
            "root_service_category",
            "root_service_status_code",
            "trace_duration",
            "span_count",
            "service_count",
        ],
    },
}


# Span 顶层字段展示顺序
SPAN_SORTED_FIELD = [
    "trace_id",
    "span_id",
    "elapsed_time",
    "kind",
    "span_name",
    "start_time",
    "end_time",
    "parent_span_id",
    "trace_state",
    "time",
    "status",
    "resource",
    "attributes",
    "events",
    "links",
]


class SpanSourceCategory:
    """Span来源分类"""

    OPENTELEMETRY = "opentelemetry"
    EBPF_SYSTEM = "ebpf_system"
    EBPF_NETWORK = "ebpf_network"

    EBPF = "ebpf"


class EbpfSignalSourceType:
    SIGNAL_SOURCE_PACKET = "Packet"
    SIGNAL_SOURCE_XFLOW = "XFlow"
    SIGNAL_SOURCE_EBPF = "eBPF"
    SIGNAL_SOURCE_OTEL = "OTel"


class EbpfTapSideType:
    OTHER_NIC = "Other NIC"
    LOCAL_NIC = "Local NIC"
    CLIENT_NIC = "Client NIC"
    CLIENT_K8S_NODE = "Client K8s Node"
    CLIENT_VM_HYPERVISOR = "Client VM Hypervisor"
    CLIENT_SIDE_GATEWAY = "Client-side Gateway"
    CLIENT_SIDE_GATEWAY_HYPERVISOR = "Client-side Gateway Hypervisor"
    SERVER_NIC = "Server NIC"
    SERVER_K8S_NODE = "Server K8s Node"
    SERVER_VM_HYPERVISOR = "Server VM Hypervisor"
    SERVER_SIDE_GATEWAY = "Server-side Gateway"
    SERVER_SIDE_GATEWAY_HYPERVISOR = "Server-side Gateway Hypervisor"
    CLIENT_PROCESS = "Client Process"
    SERVER_PROCESS = "Server Process"
    CLIENT_APPLICATION = "Client Application"
    SERVER_APPLICATION = "Server Application"
    APPLICATION = "Application"

    # 这里中英文对应
    tap_side_map = {
        OTHER_NIC: _("其他网卡"),
        LOCAL_NIC: _("本机网卡"),
        CLIENT_NIC: _("客户端网卡"),
        CLIENT_K8S_NODE: _("客户端容器节点"),
        CLIENT_VM_HYPERVISOR: _("客户端宿主机"),
        CLIENT_SIDE_GATEWAY: _("客户端到网关"),
        CLIENT_SIDE_GATEWAY_HYPERVISOR: _("客户端到网关宿主机"),
        SERVER_NIC: _("服务端网卡"),
        SERVER_K8S_NODE: _("服务端容器节点"),
        SERVER_VM_HYPERVISOR: _("服务端宿主机"),
        SERVER_SIDE_GATEWAY: _("网关到服务端"),
        SERVER_SIDE_GATEWAY_HYPERVISOR: _("网关宿主机到服务端"),
        CLIENT_PROCESS: _("客户端进程"),
        SERVER_PROCESS: _("服务端进程"),
        CLIENT_APPLICATION: _("客户端应用"),
        SERVER_APPLICATION: _("服务端应用"),
        APPLICATION: _("应用"),
    }

    @classmethod
    def get_display_name(cls, tap_side):
        if tap_side not in cls.tap_side_map:
            tap_side = cls.OTHER_NIC
        return cls.tap_side_map.get(tap_side)


class HostAddressType:
    """主机地址类型"""

    IPV4 = "ipv4"
    IPV6 = "ipv6"


# APM 应用列表页, 应用相关指标 key -> BKMONITOR_{PLATFORM}_{ENVIRONMENT}_APM_APPLICATION_METRIC_{bk_biz_id}_{application_id}
APM_APPLICATION_METRIC = "BKMONITOR_{}_{}_APM_APPLICATION_METRIC_{}_{}"

APM_APPLICATION_METRIC_DEFAULT_EXPIRED_TIME = 24 * 60 * 60

# APM 应用列表页, 应用默认指标
APM_APPLICATION_DEFAULT_METRIC = {
    "apdex": None,
    "avg_duration": 0.0,
    "request_count": 0,
    "error_rate": 0.0,
    "error_count": 0,
}

# 慢命令key, attributes.db.is_slow
APM_IS_SLOW_ATTR_KEY = "db.is_slow"

# DB 配置默认阀值(threshold)
DEFAULT_DB_CONFIG_IS_SLOW_QUERY_THRESHOLD = 500

# DB 配置默认发现字段(predicate_key)
DEFAULT_DB_CONFIG_PREDICATE_KEY = "attributes.db.system"

# DB 配置cut key 默认值
DEFAULT_DB_CONFIG_CUT_KEY = "attributes.db.statement"


class TraceMode:
    """
    追踪模式
    """

    # 原生
    ORIGIN = "origin"
    # 无参
    NO_PARAMETERS = "no_parameters"
    # 关闭
    CLOSED = "closed"

    # APM 配置下发 drop keys
    APM_DROP_KEYS_MAPPING = {
        ORIGIN: [],
        NO_PARAMETERS: ["attributes.db.parameters"],
        CLOSED: ["attributes.db.statement", "attributes.db.parameters"],
    }


"""
数据来源
https://github.com/open-telemetry/opentelemetry-specification/blob/v1.20.0/specification/trace/semantic_conventions/database.md
"""
DB_SYSTEM_TUPLE = (
    "hanadb",
    "trino",
    "informix",
    "oracle",
    "coldfusion",
    "elasticsearch",
    "couchdb",
    "h2",
    "memcached",
    "hive",
    "cloudscape",
    "postgresql",
    "couchbase",
    "firebird",
    "dynamodb",
    "pointbase",
    "mariadb",
    "cache",
    "hbase",
    "netezza",
    "redshift",
    "opensearch",
    "maxdb",
    "ingres",
    "edb",
    "firstsql",
    "mysql",
    "redis",
    "db2",
    "clickhouse",
    "sqlite",
    "instantdb",
    "cockroachdb",
    "sybase",
    "cassandra",
    "cosmosdb",
    "progress",
    "derby",
    "mssqlcompact",
    "teradata",
    "filemaker",
    "vertica",
    "pervasive",
    "mssql",
    "adabas",
    "hsqldb",
    "geode",
    "neo4j",
    "mongodb",
    "interbase",
)

DEFAULT_DB_CONFIG = {
    "db_system": "",
    "trace_mode": "origin",
    "length": 10000,
    "threshold": 500,
    "enabled_slow_sql": False,
}

METRIC_TUPLE = ("request_count", "avg_duration", "error_request_count", "slow_request_count", "slow_command_rate")

METRIC_PARAM_MAP = {
    "error_request_count": {"filter": {"bool": {"filter": [{"term": {"status.code": 2}}]}}},
    "slow_request_count": {"filter": {"bool": {"filter": [{"term": {"attributes.db.is_slow": 1}}]}}},
}

METRIC_MAP = {
    "request_count": {"request_count": {"value_count": {"field": ""}}},
    "avg_duration": {"avg_duration": {"avg": {"field": "elapsed_time"}}},
    "error_request_count": {"aggs": {"count": {"value_count": {"field": ""}}}},
    "slow_request_count": {"aggs": {"count": {"value_count": {"field": ""}}}},
    "slow_command_rate": {
        "slow_command_rate": {
            "bucket_script": {
                "buckets_path": {"slowRequestCount": "slow_request_count.count", "requestCount": "request_count"},
                "script": {"inline": "params.slowRequestCount/params.requestCount"},
            }
        }
    },
}

METRIC_RELATION_MAP = {"slow_command_rate": {"slow_request_count", "request_count"}}

METRIC_RATE_TUPLE = ("slow_command_rate",)

METRIC_VALUE_COUNT_TUPLE = ("request_count",)

OPERATOR_MAP = {"=": "equal", "!=": "not_equal", "exists": "exists", "does not exists": "not exists"}

DEFAULT_MAX_VALUE = 10000

DEFAULT_SPLIT_SYMBOL = "--"


class ApmCacheKey:
    """一些 APM 的缓存 Key"""

    # 存放应用下服务的数据状态
    APP_SERVICE_STATUS_KEY = "apm:application:{application_id}:service_data_status"
    # 存放应用下监控项数据的映射
    APP_SCOPE_NAME_KEY = "apm:application_metric_scope_name_mapping:{bk_biz_id}:{application_id}"


class LogIndexSource:
    """服务日志的数据关联来源"""

    HOST = "host"
    RELATION = "relation"
    CUSTOM_REPORT = "custom_report"

    @classmethod
    def get_source_label(cls, key):
        return {
            cls.HOST: "主机关联",
            cls.RELATION: "关联配置",
            cls.CUSTOM_REPORT: "自定义上报",
        }.get(key, key)


METRIC_COMMON_DIMENSION = [
    "namespace",  # 环境
    "env_name",  # 用户环境
    "instance",  # 实例
    "container_name",  # 容器
    "version",  # 版本
    "app",  # 应用
    "server",  # 服务
    "service_name",  # 服务名：service_name (组成逻辑app+server)
]


class ServiceStatusCachedEnum(CachedEnum):
    FATAL = 1
    WARNING = 2
    REMIND = 3
    NORMAL = 9999

    @cached_property
    def label(self):
        return str(
            {
                self.NORMAL: _("无告警"),
                self.FATAL: _("致命"),
                self.REMIND: _("提醒"),
                self.WARNING: _("预警"),
            }.get(self, self.value)
        )

    @cached_property
    def status(self):
        return {
            self.NORMAL: {"type": Status.SUCCESS, "text": self.label},
            self.FATAL: {"type": Status.FAILED, "text": self.label},
            self.REMIND: {"type": Status.WARNING, "text": self.label},
            self.WARNING: {"type": Status.WARNING, "text": self.label},
        }.get(self, {"type": Status.FAILED, "text": self.label})

    @classmethod
    def get_default(cls, value):
        default = super().get_default(value)
        default.label = value
        default.status = {"type": Status.FAILED, "text": value}
        return default


class ApdexCachedEnum(CachedEnum):
    DIMENSION_KEY = "apdex_type"
    SATISFIED = "satisfied"
    TOLERATING = "tolerating"
    FRUSTRATED = "frustrated"
    ERROR = "error"

    @cached_property
    def label(self):
        return str(
            {self.SATISFIED: _("满意"), self.TOLERATING: _("可容忍"), self.FRUSTRATED: _("烦躁期")}.get(
                self, self.value
            )
        )

    @cached_property
    def status(self):
        return {
            self.SATISFIED: {"type": Status.SUCCESS, "text": self.label},
            self.TOLERATING: {"type": Status.WAITING, "text": self.label},
            self.FRUSTRATED: {"type": Status.FAILED, "text": self.label},
        }.get(self, {"type": None, "text": "--"})

    @classmethod
    def get_default(cls, value):
        default = super().get_default(value)
        default.label = value
        default.status = {"type": None, "text": "--"}
        return default


class CategoryCachedEnum(CachedEnum):
    HTTP = "http"
    RPC = "rpc"
    DB = "db"
    MESSAGING = "messaging"
    ASYNC_BACKEND = "async_backend"
    ALL = "all"
    OTHER = "other"

    # profile 为新的展示类型 只用来展示在 serviceList 无实际作用
    PROFILING = "profiling"

    @cached_property
    def label(self):
        return str(
            {
                self.HTTP: _("网页"),
                self.RPC: _("远程调用"),
                self.DB: _("数据库"),
                self.MESSAGING: _("消息队列"),
                self.ASYNC_BACKEND: _("后台任务"),
                self.ALL: _("全部"),
                self.OTHER: _("其他"),
            }.get(self, self.value)
        )

    @cached_property
    def remote_service_label(self):
        return str({self.HTTP: _("网页(自定义服务)")}.get(self, self.value))

    @classmethod
    @lru_cache(maxsize=1)
    def get_filter_fields(cls):
        return [
            {
                "id": cls.ALL.value,
                "name": gettext("全部"),
                "icon": "icon-gailan",
            },
            {
                "id": cls.HTTP.value,
                "name": gettext("网页"),
                "icon": "icon-wangye",
            },
            {
                "id": cls.RPC.value,
                "name": gettext("远程调用"),
                "icon": "icon-yuanchengfuwu",
            },
            {
                "id": cls.DB.value,
                "name": gettext("数据库"),
                "icon": "icon-shujuku",
            },
            {
                "id": cls.MESSAGING.value,
                "name": gettext("消息队列"),
                "icon": "icon-xiaoxizhongjianjian",
            },
            {
                "id": cls.ASYNC_BACKEND.value,
                "name": gettext("后台任务"),
                "icon": "icon-renwu",
            },
            {
                "id": cls.OTHER.value,
                "name": gettext("其他"),
                "icon": "icon-mc-service-unknown",
            },
        ]

    @classmethod
    def classify(cls, span):
        # TODO: 转为InferenceHandler进行推断
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.HTTP_METHOD):
            return cls.HTTP.value
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.RPC_SERVICE):
            return cls.RPC.value
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.DB_SYSTEM):
            return cls.DB.value
        if span[OtlpKey.ATTRIBUTES].get(SpanAttributes.MESSAGING_SYSTEM):
            return cls.MESSAGING.value
        return cls.OTHER.value

    @classmethod
    def list_span_keys(cls):
        """获取所有分类字段"""
        return [
            SpanAttributes.DB_SYSTEM,
            SpanAttributes.MESSAGING_SYSTEM,
            SpanAttributes.RPC_SYSTEM,
            SpanAttributes.HTTP_METHOD,
            SpanAttributes.MESSAGING_DESTINATION,
        ]

    @classmethod
    def list_component_generate_keys(cls):
        """获取 APM 手动处理(手动生成服务节点)的字段"""
        return [
            SpanAttributes.DB_SYSTEM,
            SpanAttributes.MESSAGING_SYSTEM,
        ]

    @classmethod
    def get_default(cls, value):
        default = super().get_default(value)
        default.label = value
        default.remote_service_label = value
        return default


class DataStatusColumnEnum(CachedEnum):
    NORMAL = "normal"
    NO_DATA = "no_data"
    DISABLED = "disabled"

    @classmethod
    @lru_cache(maxsize=1)
    def list(cls):
        return {
            cls.NORMAL: _("正常"),
            cls.NO_DATA: _("无数据"),
            cls.DISABLED: _("未开启"),
        }

    @cached_property
    def label(self):
        return str(self.list().get(self, self.value))

    @cached_property
    def status(self):
        return {
            self.NORMAL: {"type": Status.SUCCESS, "text": gettext("正常")},
            self.NO_DATA: {"type": Status.FAILED, "text": gettext("无数据")},
        }.get(self, {"type": Status.FAILED, "text": self.value})

    @classmethod
    def get_default(cls, value):
        default = super().get_default(value)
        default.label = gettext("未开启")
        default.status = {"type": Status.FAILED, "text": gettext("未开启")}
        return default
