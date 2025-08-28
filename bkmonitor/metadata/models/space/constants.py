"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

空间管理模块常量定义文件

该文件定义了蓝鲸监控平台中空间管理相关的所有常量，包括：
1. 空间类型和状态枚举
2. 数据表类型定义
3. Redis缓存配置
4. ETL清洗配置
5. 数据源访问权限配置
6. 特殊空间和数据源的处理规则

这些常量在整个空间管理系统中被广泛使用，用于确保数据的一致性和系统的可维护性。
"""

import os
from enum import Enum

from django.conf import settings

# ===== 分页配置 =====
# 默认页码，用于分页查询时的起始页
DEFAULT_PAGE = 1
# 默认页面大小，用于分页查询时的每页记录数
DEFAULT_PAGE_SIZE = 1000


# ===== 空间类型枚举 =====
class SpaceTypes(Enum):
    """空间类型枚举
    
    定义了蓝鲸监控平台支持的所有空间类型，每种类型对应不同的业务场景：
    - BKCC: 蓝鲸配置管理数据库空间，用于传统CMDB业务
    - BCS: 蓝鲸容器服务空间，用于Kubernetes集群监控
    - BKCI: 蓝鲸持续集成空间，用于CI/CD流水线监控
    - BKSAAS: 蓝鲸SaaS应用空间，用于SaaS应用监控
    - DEFAULT: 默认空间类型
    - ALL: 所有空间类型，用于权限控制等场景
    """

    BKCC = "bkcc"      # 蓝鲸配置管理数据库空间
    BCS = "bcs"        # 蓝鲸容器服务空间
    BKCI = "bkci"      # 蓝鲸持续集成空间
    BKSAAS = "bksaas"  # 蓝鲸SaaS应用空间
    DEFAULT = "default"  # 默认空间类型
    ALL = "all"        # 所有空间类型

    _choices_labels = (
        (BKCC, "bkcc"),
        (BCS, "bcs"),
        (BKCI, "bkci"),
        (BKSAAS, "bksaas"),
        (DEFAULT, "default"),
        (ALL, "all"),
    )


class SpaceStatus(Enum):
    """空间状态枚举
    
    定义空间的运行状态：
    - NORMAL: 正常状态，空间可以正常使用
    - DISABLED: 禁用状态，空间被暂停使用
    """

    NORMAL = "normal"      # 正常状态
    DISABLED = "disabled"  # 禁用状态


class MeasurementType(Enum):
    """数据表类型枚举
    
    定义监控数据存储的表类型：
    - BK_TRADITIONAL: 传统单表模式，所有指标存储在一张表中
    - BK_SPLIT: 分表模式，按指标分别存储
    - BK_EXPORTER: Exporter模式，适用于Prometheus exporter数据
    - BK_STANDARD_V2_TIME_SERIES: 标准时序数据表，V2版本格式
    """

    BK_TRADITIONAL = "bk_traditional_measurement"           # 传统单表模式
    BK_SPLIT = "bk_split_measurement"                       # 分表模式
    BK_EXPORTER = "bk_exporter"                            # Exporter模式
    BK_STANDARD_V2_TIME_SERIES = "bk_standard_v2_time_series"  # 标准时序数据表V2


# ===== 系统配置 =====
# 系统资源创建者用户名，用于标识系统自动创建的资源
# 可通过 COMMON_USERNAME 环境变量配置，默认为 "system"
SYSTEM_USERNAME = getattr(settings, "COMMON_USERNAME", "system")

# ===== Redis缓存配置 =====
# Redis中存储空间信息的主键
# 用于缓存所有空间的基本信息列表
SPACE_REDIS_KEY = os.environ.get("SPACE_REDIS_KEY", "bkmonitorv3:spaces")

# Redis中存储空间详情的键前缀
# 用于缓存每个空间的详细配置信息
SPACE_DETAIL_REDIS_KEY_PREFIX = os.environ.get("SPACE_DETAIL_REDIS_KEY_PREFIX", "bkmonitorv3:spaces")

# 空间变动的Redis发布频道
# 当空间信息发生变化时，通过此频道通知 unify-query 等订阅者重新加载数据
SPACE_CHANNEL = os.environ.get("SPACE_CHANNEL", "bkmonitorv3:spaces")

# 空间唯一标识连接符
# 用于构造空间的唯一标识符，格式：{space_type}__{space_id}
SPACE_UID_HYPHEN = "__"

# ===== 空间路由缓存配置 =====
# Redis键的统一前缀，用于空间相关的所有缓存
SPACE_REDIS_PREFIX_KEY = "bkmonitorv3:spaces"

# 空间与结果表映射关系的Redis键
# 存储每个空间可以访问的结果表列表，用于数据查询权限控制
SPACE_TO_RESULT_TABLE_KEY = os.environ.get(
    "SPACE_TO_RESULT_TABLE_KEY", f"{SPACE_REDIS_PREFIX_KEY}:space_to_result_table"
)
# 空间与结果表映射关系变更的通知频道
SPACE_TO_RESULT_TABLE_CHANNEL = os.environ.get(
    "SPACE_TO_RESULT_TABLE_CHANNEL", f"{SPACE_REDIS_PREFIX_KEY}:space_to_result_table:channel"
)

# 数据标签与结果表映射关系的Redis键
# 存储数据标签与结果表的对应关系，用于按标签查询数据
DATA_LABEL_TO_RESULT_TABLE_KEY = os.environ.get(
    "DATA_LABEL_TO_RESULT_TABLE_KEY", f"{SPACE_REDIS_PREFIX_KEY}:data_label_to_result_table"
)
# 数据标签与结果表映射关系变更的通知频道
DATA_LABEL_TO_RESULT_TABLE_CHANNEL = os.environ.get(
    "DATA_LABEL_TO_RESULT_TABLE_CHANNEL", f"{SPACE_REDIS_PREFIX_KEY}:data_label_to_result_table:channel"
)

# 结果表详细信息的Redis键
# 存储每个结果表的详细配置信息，包括字段定义、存储配置等
RESULT_TABLE_DETAIL_KEY = os.environ.get("RESULT_TABLE_DETAIL_KEY", f"{SPACE_REDIS_PREFIX_KEY}:result_table_detail")
# 结果表详情变更的通知频道
RESULT_TABLE_DETAIL_CHANNEL = os.environ.get(
    "RESULT_TABLE_DETAIL_CHANNEL", f"{SPACE_REDIS_PREFIX_KEY}:result_table_detail:channel"
)


# ===== ETL清洗配置枚举 =====
class EtlConfigs(Enum):
    """ETL数据清洗配置枚举
    
    定义了不同类型数据的ETL清洗配置，用于数据接入时的格式化处理：
    
    系统监控类：
    - 主机基础监控数据（CPU、内存、磁盘等）
    - 进程监控数据
    - 端口监控数据
    - 拨测监控数据
    
    多租户类：
    - 支持多租户模式的数据采集配置
    - 隔离不同租户的数据
    
    自定义类：
    - 用户自定义指标数据
    - Prometheus exporter数据
    """
    
    # === 系统监控类 ETL 配置（多指标单表模式） ===
    BK_SYSTEM_BASEREPORT = "bk_system_basereport"                # 主机基础监控数据（CPU、内存、磁盘等）
    BK_UPTIMECHECK_HEARTBEAT = "bk_uptimecheck_heartbeat"        # 拨测心跳监控
    BK_UPTIMECHECK_HTTP = "bk_uptimecheck_http"                  # HTTP拨测监控
    BK_UPTIMECHECK_TCP = "bk_uptimecheck_tcp"                    # TCP拨测监控
    BK_UPTIMECHECK_UDP = "bk_uptimecheck_udp"                    # UDP拨测监控
    BK_SYSTEM_PROC_PORT = "bk_system_proc_port"                  # 系统进程端口监控
    BK_SYSTEM_PROC = "bk_system_proc"                            # 系统进程监控
    
    # === 自定义监控类 ETL 配置 ===
    BK_STANDARD_V2_TIME_SERIES = "bk_standard_v2_time_series"    # 标准时序数据V2格式

    # === 多租户监控类 ETL 配置 ===
    BK_MULTI_TENANCY_BASEREPORT_ETL_CONFIG = "bk_multi_tenancy_basereport"          # 多租户主机基础数据
    BK_MULTI_TENANCY_AGENT_EVENT_ETL_CONFIG = "bk_multi_tenancy_agent_event"        # 多租户Agent事件数据
    BK_MULTI_TENANCY_SYSTEM_PROC_PERF_ETL_CONFIG = "bk_multi_tenancy_system_proc_perf"  # 多租户进程性能数据
    BK_MULTI_TENANCY_SYSTEM_PROC_PORT_ETL_CONFIG = "bk_multi_tenancy_system_proc_port"  # 多租户进程端口数据

    # === Prometheus/Exporter 类 ETL 配置（固定指标单表模式） ===
    BK_EXPORTER = "bk_exporter"        # Prometheus exporter数据
    BK_STANDARD = "bk_standard"        # 标准指标数据

    _choices_labels = (
        (BK_SYSTEM_BASEREPORT, "bk_system_basereport"),
        (BK_UPTIMECHECK_HEARTBEAT, "bk_uptimecheck_heartbeat"),
        (BK_UPTIMECHECK_HTTP, "bk_uptimecheck_http"),
        (BK_UPTIMECHECK_TCP, "bk_uptimecheck_tcp"),
        (BK_UPTIMECHECK_UDP, "bk_uptimecheck_udp"),
        (BK_SYSTEM_PROC_PORT, "bk_system_proc_port"),
        (BK_SYSTEM_PROC, "bk_system_proc"),
        (BK_STANDARD_V2_TIME_SERIES, "bk_standard_v2_time_series"),
        (BK_EXPORTER, "bk_exporter"),
        (BK_STANDARD, "bk_standard"),
        (BK_MULTI_TENANCY_AGENT_EVENT_ETL_CONFIG, "bk_multi_tenancy_agent_event"),
        (BK_MULTI_TENANCY_BASEREPORT_ETL_CONFIG, "bk_multi_tenancy_basereport"),
        (BK_MULTI_TENANCY_SYSTEM_PROC_PERF_ETL_CONFIG, "bk_multi_tenancy_system_proc_perf"),
        (BK_MULTI_TENANCY_SYSTEM_PROC_PORT_ETL_CONFIG, "bk_multi_tenancy_system_proc_port"),
    )


# ===== ETL配置相关常量 =====
# 空间数据源支持的所有ETL配置类型列表
# 从 EtlConfigs 枚举中提取所有配置项，用于验证和选择
SPACE_DATASOURCE_ETL_LIST = [item[0] for item in EtlConfigs._choices_labels.value]

# 启用V4数据链路的ETL配置类型列表
# V4数据链路提供更好的性能和稳定性，这些配置类型优先使用V4方式申请DataID
ENABLE_V4_DATALINK_ETL_CONFIGS = [
    EtlConfigs.BK_STANDARD_V2_TIME_SERIES.value,                      # 标准时序数据
    EtlConfigs.BK_MULTI_TENANCY_AGENT_EVENT_ETL_CONFIG.value,         # 多租户Agent事件
    EtlConfigs.BK_MULTI_TENANCY_BASEREPORT_ETL_CONFIG.value,          # 多租户基础监控
    EtlConfigs.BK_MULTI_TENANCY_SYSTEM_PROC_PERF_ETL_CONFIG.value,    # 多租户进程性能
    EtlConfigs.BK_MULTI_TENANCY_SYSTEM_PROC_PORT_ETL_CONFIG.value,    # 多租户进程端口
]

# 根据配置动态添加插件相关的V4数据链路支持
# 当启用插件接入V4数据链路时，将 Prometheus exporter 和标准指标也使用V4链路
if settings.ENABLE_PLUGIN_ACCESS_V4_DATA_LINK:
    ENABLE_V4_DATALINK_ETL_CONFIGS.append(EtlConfigs.BK_EXPORTER.value)  # Prometheus exporter数据
    ENABLE_V4_DATALINK_ETL_CONFIGS.append(EtlConfigs.BK_STANDARD.value)  # 标准指标数据


# 系统内置基础数据的ETL配置类型列表
# 这些配置用于系统自带的基础监控功能，包括主机监控、进程监控等
SYSTEM_BASE_DATA_ETL_CONFIGS = [
    EtlConfigs.BK_SYSTEM_BASEREPORT.value,                            # 传统主机基础监控
    EtlConfigs.BK_MULTI_TENANCY_BASEREPORT_ETL_CONFIG.value,          # 多租户主机基础监控
    EtlConfigs.BK_MULTI_TENANCY_AGENT_EVENT_ETL_CONFIG.value,         # 多租户Agent事件监控
    EtlConfigs.BK_MULTI_TENANCY_SYSTEM_PROC_PERF_ETL_CONFIG.value,    # 多租户进程性能监控
    EtlConfigs.BK_MULTI_TENANCY_SYSTEM_PROC_PORT_ETL_CONFIG.value,    # 多租户进程端口监控
]

# 日志和事件类数据的ETL配置类型列表
# 用于处理系统日志、应用事件等非指标类数据
LOG_EVENT_ETL_CONFIGS = [EtlConfigs.BK_MULTI_TENANCY_AGENT_EVENT_ETL_CONFIG.value]

# ===== 特殊空间配置 =====
# BKCC类型中的特殊空间配置
# BKCC存在一个特殊的"全业务"空间，空间ID为"0"，在某些场景下需要特殊处理
EXCLUDED_SPACE_TYPE_ID = SpaceTypes.BKCC.value  # 需要特殊处理的空间类型
EXCLUDED_SPACE_ID = "0"                         # 需要特殊处理的空间ID

# 在BKCC空间枚举中需要跳过的数据源ID列表
# 这些数据源虽然属于"0"业务，但不属于BKCC类型，需要在处理时跳过
SKIP_DATA_ID_LIST_FOR_BKCC = [1110000]


# ===== BCS集群配置 =====
class BCSClusterTypes(Enum):
    """BCS集群类型枚举
    
    定义蓝鲸容器服务（BCS）支持的集群类型：
    - SINGLE: 独占集群，仅供单个空间使用
    - SHARED: 共享集群，可供多个空间共同使用
    """

    SINGLE = "single"  # 独占集群
    SHARED = "shared"  # 共享集群


# ===== BKCI权限配置 =====
# 授权蓝鲸持续集成（BKCI）访问的数据源ID列表
# 这些数据源允许BKCI空间跨空间类型访问
BKCI_AUTHORIZED_DATA_ID_LIST = [1001]

# BKCI在数据源1001下允许访问的结果表前缀配置
BKCI_1001_TABLE_ID_PREFIX = "devx_system."      # 开发体验相关的系统数据表前缀
P4_1001_TABLE_ID_PREFIX = "perforce_system."    # Perforce版本控制系统相关的主机数据表前缀

# 允许所有空间类型访问的结果表列表
# 这些表包含公共数据，不受空间类型限制
ALL_SPACE_TYPE_TABLE_ID_LIST = [
    "custom_report_aggate.base",  # 自定义上报聚合基础数据表
    "bkm_statistics.base"         # 监控平台统计基础数据表
]

# 数据源1001下仅允许DBM（数据库管理）访问的结果表前缀
DBM_1001_TABLE_ID_PREFIX = "dbm_system."

# BKCI类型空间可以访问的主机类型结果表前缀
# 主要用于获取主机基础监控数据，如CPU、内存、磁盘等指标
BKCI_SYSTEM_TABLE_ID_PREFIX = "system."
