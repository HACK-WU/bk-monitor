"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from bkmonitor.data_source import DataQuery
from bkmonitor.data_source.handler.elastic_search import ESDataQuery
from bkmonitor.data_source.handler.log_search import LogSearchDataQuery
from bkmonitor.data_source.handler.time_series import TSDataQuery
from constants.data_source import DataSourceLabel, DataTypeLabel

__all__ = ["DataQueryHandler", "HandlerType"]


class DataQueryHandler:
    """
    数据查询处理器工厂类，根据数据源和数据类型标签生成对应的查询实例

    该类采用工厂模式实现，通过__new__方法根据传入的标签组合
    动态创建不同类型的数据查询对象，实现查询逻辑的适配和解耦
    """

    def __new__(cls, data_source_label, data_type_label):
        """
        创建数据查询实例的工厂方法

        参数:
            data_source_label: 数据源标签，标识数据来源系统
            data_type_label: 数据类型标签，标识数据内容形态

        返回值:
            根据标签组合返回以下实例之一：
            - ESDataQuery: 处理日志类数据查询（ES存储）
            - LogSearchDataQuery: 处理日志搜索专用查询
            - TSDataQuery: 处理时序数据查询
            - DataQuery: 默认基础查询实例

        标签组合优先级说明：
        1. 首先匹配预定义的复合标签组合（BK_MONITOR_COLLECTOR+LOG等）
        2. 其次处理日志搜索专用组合（BK_LOG_SEARCH+LOG）
        3. 再处理时序数据组合（BK_MONITOR_COLLECTOR+TIME_SERIES）
        4. 最后兜底使用基础查询类
        """

        # 处理预定义复合标签组合的查询实例创建
        if (data_source_label, data_type_label) in [
            (DataSourceLabel.BK_MONITOR_COLLECTOR, DataTypeLabel.LOG),
            (DataSourceLabel.CUSTOM, DataTypeLabel.EVENT),
            (DataSourceLabel.BK_APM, DataTypeLabel.LOG),
            (DataSourceLabel.BK_APM, DataTypeLabel.TIME_SERIES),
        ]:
            q = ESDataQuery((data_source_label, data_type_label))

        # 处理日志搜索专用数据源的查询实例创建
        elif data_source_label == DataSourceLabel.BK_LOG_SEARCH and data_type_label == DataTypeLabel.LOG:
            q = LogSearchDataQuery((data_source_label, data_type_label))

        # 处理时序数据查询实例创建
        elif data_source_label == DataSourceLabel.BK_MONITOR_COLLECTOR and data_type_label == DataTypeLabel.TIME_SERIES:
            q = TSDataQuery((data_source_label, data_type_label))

        # 默认基础查询实例兜底
        else:
            q = DataQuery((data_source_label, data_type_label))

        return q


class HandlerType:
    KEYWORDS = "keywords"
    LOG_SEARCH = "log_search"
    TIME_SERIES = "time_series"
    CUSTOM_EVENT = "custom_event"
    BASE = "base"
