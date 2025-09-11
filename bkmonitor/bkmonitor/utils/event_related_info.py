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
import time
from urllib.parse import urlencode

import arrow
from django.conf import settings

from bkmonitor.data_source import load_data_source
from bkmonitor.documents import AlertDocument
from bkmonitor.models import Event, QueryConfigModel
from bkmonitor.utils import time_tools
from constants.data_source import DataSourceLabel, DataTypeLabel

__all__ = ["get_event_relation_info", "get_alert_relation_info"]

from core.drf_resource import api

logger = logging.getLogger("fta_action.run")


def get_event_relation_info(event: Event):
    """
    获取事件最近的日志
    1. 自定义事件：查询事件关联的最近一条事件信息
    2. 日志关键字：查询符合条件的一条日志信息
    """
    query_config = (
        QueryConfigModel.objects.filter(strategy_id=event.strategy_id)
        .values("data_source_label", "data_type_label", "config")
        .first()
    )

    # 关联日志信息目前固定单指标
    if not query_config or (query_config["data_source_label"], query_config["data_type_label"]) not in (
        (DataSourceLabel.BK_MONITOR_COLLECTOR, DataTypeLabel.LOG),
        (DataSourceLabel.BK_LOG_SEARCH, DataTypeLabel.LOG),
        (DataSourceLabel.BK_LOG_SEARCH, DataTypeLabel.TIME_SERIES),
        (DataSourceLabel.CUSTOM, DataTypeLabel.EVENT),
    ):
        return ""

    query_config = event.origin_config["items"][0]["query_configs"][0]
    data_source_class = load_data_source(query_config["data_source_label"], query_config["data_type_label"])
    data_source = data_source_class.init_by_query_config(query_config, bk_biz_id=event.bk_biz_id)

    data_source.filter_dict.update(
        {
            key: value
            for key, value in event.origin_alarm["data"]["dimensions"].items()
            if key in query_config.get("agg_dimension", [])
        }
    )

    content = get_data_source_log(
        event, data_source, query_config, int(event.latest_anomaly_record.source_time.timestamp())
    )
    return content[: settings.EVENT_RELATED_INFO_LENGTH] if settings.EVENT_RELATED_INFO_LENGTH else content


def get_alert_relation_info(alert: AlertDocument, length_limit=True):
    """
    获取事件最近的日志信息，支持多类型告警源关联查询

    参数:
        alert: AlertDocument对象，包含告警基础信息和策略配置
        length_limit: 布尔值，控制返回内容是否进行长度截断（默认True）

    返回值:
        str类型，包含关联日志信息或空字符串：
        - 日志聚类新类告警返回聚类详情
        - 日志聚类数量告警返回统计信息
        - 普通日志/事件告警返回原始日志内容
        - 无匹配类型返回空字符串

    处理流程：
    1. 优先处理日志聚类相关标签（新类/数量告警）
    2. 回退到通用日志/事件关联信息查询
    3. 根据配置进行内容长度截断
    """
    if not alert.strategy:
        # 策略配置缺失时直接返回空字符串
        return ""

    content = ""
    query_config = (
        QueryConfigModel.objects.filter(strategy_id=alert.strategy["id"])
        .values("data_source_label", "data_type_label", "config")
        .first()
    )

    # 日志聚类告警需要提供更详细的信息
    for label in alert.strategy.get("labels") or []:
        # 日志聚类新类告警具有特定标签，格式 "LogClustering/NewClass/{index_set_id}"
        # 根据前缀可识别出来
        if label.startswith("LogClustering/NewClass/"):
            content = get_alert_info_for_log_clustering_new_class(alert, label.split("/")[-1])
            break
        # 日志聚类数量告警具有特定标签，格式 "LogClustering/Count/{index_set_id}"
        # 根据前缀可识别出来
        elif label.startswith("LogClustering/Count/"):
            content = get_alert_info_for_log_clustering_count(alert, label.split("/")[-1])
            break

    # 关联日志信息目前固定单指标
    if (
        not content
        and query_config
        and (query_config["data_source_label"], query_config["data_type_label"])
        in (
            (DataSourceLabel.BK_MONITOR_COLLECTOR, DataTypeLabel.LOG),
            (DataSourceLabel.BK_LOG_SEARCH, DataTypeLabel.LOG),
            (DataSourceLabel.BK_LOG_SEARCH, DataTypeLabel.TIME_SERIES),
            (DataSourceLabel.CUSTOM, DataTypeLabel.EVENT),
            (DataSourceLabel.BK_FTA, DataTypeLabel.EVENT),
        )
    ):
        content = get_alert_relation_info_for_log(alert, not length_limit)

    # 执行内容长度截断处理
    if length_limit:
        content = content[: settings.EVENT_RELATED_INFO_LENGTH] if settings.EVENT_RELATED_INFO_LENGTH else content
    return content


def get_alert_info_for_log_clustering_count(alert: AlertDocument, index_set_id: str):
    query_config = alert.strategy["items"][0]["query_configs"][0]
    interval = query_config.get("agg_interval", 60)
    start_time = alert.begin_time - 60 * 60
    end_time = max(alert.begin_time + interval, alert.latest_time) + 60 * 60
    group_by = query_config.get("agg_dimension", [])

    try:
        dimensions = alert.origin_alarm["data"]["dimensions"]
        if "__dist_05" in dimensions:
            sensitivity = "__dist_05"
            signatures = [dimensions["__dist_05"]]
        else:
            signatures = [dimensions["signature"]]
            sensitivity = dimensions.get("sensitivity", "__dist_05")
    except Exception as e:
        logger.exception("[get_alert_info_for_log_clustering_count] get dimension error: %s", e)
        return ""

    return get_clustering_log(alert, index_set_id, start_time, end_time, sensitivity, signatures, group_by, dimensions)


def get_alert_info_for_log_clustering_new_class(alert: AlertDocument, index_set_id: str):
    """
    get_alert_relation_info_for_log_clustering_new_class
    """
    query_config = alert.strategy["items"][0]["query_configs"][0]
    data_source_class = load_data_source(query_config["data_source_label"], query_config["data_type_label"])
    data_source = data_source_class.init_by_query_config(query_config, bk_biz_id=alert.event.bk_biz_id)
    interval = query_config.get("agg_interval", 60)
    start_time = alert.begin_time
    end_time = max(alert.begin_time + interval, alert.latest_time)
    group_by = query_config.get("agg_dimension", [])
    signatures = []

    try:
        dimensions = alert.origin_alarm["data"]["dimensions"]
        if dimensions.get("signature"):
            signatures = [dimensions["signature"]]
        # 新类敏感度默认取最低档，即最少告警
        sensitivity = dimensions.get("sensitivity", "__dist_09")
        if not sensitivity.startswith("__"):
            # 补充双下划线前缀
            sensitivity = "__" + sensitivity
    except Exception as e:
        logger.exception("[get_alert_info_for_log_clustering_new_class] get dimension error: %s", e)
        sensitivity = "__dist_09"
        dimensions = {}

    if not signatures:
        signatures = data_source.query_dimensions(
            dimension_field="signature", start_time=start_time * 1000, end_time=end_time * 1000
        )
    return get_clustering_log(alert, index_set_id, start_time, end_time, sensitivity, signatures, group_by, dimensions)


def get_clustering_log(
    alert: AlertDocument, index_set_id: str, start_time, end_time, sensitivity, signatures, group_by, dimensions
):
    start_time_str = time_tools.utc2biz_str(start_time)
    end_time_str = time_tools.utc2biz_str(end_time)

    builtin_dimension_fields = ["sensitivity", "signature", "__dist_05"]

    addition = [{"field": sensitivity, "operator": "=", "value": ",".join(signatures)}]
    addition.extend(
        [
            {"field": dimension_field, "operator": "=", "value": dimension_value}
            for dimension_field, dimension_value in dimensions.items()
            if dimension_field not in builtin_dimension_fields
        ]
    )
    params = {
        "bizId": alert.event.bk_biz_id,
        "addition": json.dumps(addition),
        "start_time": start_time_str,
        "end_time": end_time_str,
    }

    # 拼接查询链接
    bklog_link = f"{settings.BKLOGSEARCH_HOST}#/retrieve/{index_set_id}?{urlencode(params)}"

    # 查询关联日志，最多展示1条
    record = {}
    log_signature = None
    try:
        log_data_source_class = load_data_source(DataSourceLabel.BK_LOG_SEARCH, DataTypeLabel.LOG)
        log_data_source = log_data_source_class.init_by_query_config(
            {
                "index_set_id": index_set_id,
                "result_table_id": "",
                "agg_condition": [{"key": sensitivity, "method": "eq", "value": signatures}]
                + [
                    {"key": dimension_field, "method": "eq", "value": [dimension_value]}
                    for dimension_field, dimension_value in dimensions.items()
                    if dimension_field not in builtin_dimension_fields
                ],
            },
            bk_biz_id=alert.event.bk_biz_id,
        )
        logs, log_total = log_data_source.query_log(start_time=start_time * 1000, end_time=end_time * 1000, limit=1)
        if logs:
            record = logs[0]
            for key in record.copy():
                if key.startswith("__dist_"):
                    # 获取pattern
                    if key == sensitivity:
                        log_signature = record[key]
                    # 去掉数据签名相关字段，精简显示内容
                    record.pop(key)

    except Exception as e:
        logger.exception(f"get alert[{alert.id}] log clustering new class log error: {e}")

    record["bklog_link"] = bklog_link

    if log_signature:
        try:
            addition = [{"field": sensitivity, "operator": "=", "value": log_signature}]
            # 增加聚类分组告警维度值作为查询条件
            addition.extend(
                [
                    {"field": dimension_field, "operator": "=", "value": dimension_value}
                    for dimension_field, dimension_value in dimensions.items()
                    if dimension_field not in builtin_dimension_fields
                ]
            )
            pattern_params = {
                "bizId": alert.event.bk_biz_id,
                "addition": addition,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "index_set_id": index_set_id,
                "pattern_level": sensitivity.lstrip("__dist_"),
                "show_new_pattern": False,
            }
            # 增加聚类分组参数
            group_by = [group for group in group_by if group not in ["sensitivity", "signature"]]
            if group_by:
                pattern_params["group_by"] = group_by
                record["group_by"] = group_by

            patterns = api.log_search.search_pattern(pattern_params)
            log_pattern = patterns[0]
            record["pattern"] = log_pattern["pattern"]
            record["owners"] = ",".join(log_pattern["owners"])
            if log_pattern["remark"]:
                remark = log_pattern["remark"][-1]
                record["remark_text"] = remark["remark"]
                record["remark_user"] = remark["username"]
                # 获取备注创建时间字符串
                record["remark_time"] = arrow.get(remark["create_time"] / 1000).to("local").format("YYYY-MM-DD HH:mm")
        except Exception as e:
            logger.exception(f"get alert[{alert.id}] signature[{log_signature}] log clustering new pattern error: {e}")

    content = json.dumps(record, ensure_ascii=False)
    return content


def get_alert_relation_info_for_log(alert: AlertDocument, is_raw=False):
    """
    获取告警关联日志信息的主函数，包含重试机制

    参数:
        alert: 告警文档对象，包含策略配置和事件信息
        is_raw: 布尔值，指示是否返回原始日志数据（默认False）

    返回值:
        成功时返回日志内容（字符串或原始数据结构）
        失败时返回空值或抛出异常（当两次尝试均失败时）

    该函数实现以下核心流程：
    1. 加载并初始化数据源实例
    2. 构建维度过滤条件
    3. 首次尝试获取日志内容
    4. 异常处理及重试机制
    """

    # 加载数据源类并初始化实例
    query_config = alert.strategy["items"][0]["query_configs"][0]
    data_source_class = load_data_source(query_config["data_source_label"], query_config["data_type_label"])
    data_source = data_source_class.init_by_query_config(query_config, bk_biz_id=alert.event.bk_biz_id)

    # 构建维度过滤条件：仅保留聚合维度相关的字段
    data_source.filter_dict.update(
        {
            key: value
            for key, value in alert.origin_alarm.get("data", {}).get("dimensions", {}).items()
            if key in query_config.get("agg_dimension", [])
        }
    )

    # 配置重试间隔时间（毫秒转秒）
    retry_interval = settings.DELAY_TO_GET_RELATED_INFO_INTERVAL

    # 首次尝试获取日志内容
    try:
        content = get_data_source_log(alert, data_source, query_config, alert.event.time, is_raw)
        if content:
            return content
        logger.info("alert(%s) related info is empty, try again after %s ms", alert.id, retry_interval)
    except BaseException as error:
        logger.error("alert(%s) related info failed: %s, try again after %s ms", alert.id, str(error), retry_interval)

    # 当第一次获取失败之后，等待指定间隔后重试
    time.sleep(retry_interval / 1000)
    return get_data_source_log(alert, data_source, query_config, alert.event.time, is_raw)


def get_data_source_log(alert, data_source, query_config, source_time, is_raw=False):
    """
    查询指定时间范围内的数据源日志并格式化返回内容

    参数:
        alert: 告警对象，包含事件基本信息和原始告警数据
        data_source: 数据源对象，需实现query_log方法进行日志查询
        query_config: 查询配置字典，包含以下关键字段:
            - agg_interval: 聚合间隔（秒）
            - data_source_label: 数据源标签
            - data_type_label: 数据类型标签
            - index_set_id: 索引集ID（日志类数据源）
            - query_string: 查询语句
            - agg_dimension: 聚合维度列表
        source_time: 时间戳（秒），作为查询时间基准
        is_raw: 布尔值，是否返回原始关联信息链接

    返回值:
        格式化后的日志内容字符串，根据数据源类型返回不同格式：
        - BK_LOG_SEARCH/BK_FTA返回特定字段内容
        - 其他数据源返回JSON序列化字符串
        - 无记录时返回空字符串

    该方法实现完整的日志查询处理流程：
    1. 构建查询时间范围（事件开始前5个周期至1个周期后）
    2. 执行日志查询并处理结果
    3. 根据数据源类型进行差异化处理
    4. 生成带上下文信息的查询链接（当is_raw=True时）
    5. 格式化返回最终内容
    """
    # 计算查询时间范围（事件开始前5个周期至1个周期后）
    interval = query_config.get("agg_interval", 60)
    start_time = int(source_time) - 5 * interval
    end_time = int(source_time) + interval

    # 执行日志查询（时间戳转换为毫秒）
    records, _ = data_source.query_log(start_time=start_time * 1000, end_time=end_time * 1000, limit=1)

    # 处理空查询结果
    if not records:
        return ""

    record = records[0]

    # 处理蓝鲸日志平台数据源的特殊逻辑
    if (
        query_config["data_source_label"] == DataSourceLabel.BK_LOG_SEARCH
        and query_config["data_type_label"] == DataTypeLabel.LOG
    ):
        index_set_id = query_config["index_set_id"]
        start_time_str = time_tools.utc2biz_str(start_time)
        end_time_str = time_tools.utc2biz_str(end_time)
        addition = [
            {"field": dimension_field, "operator": "=", "value": dimension_value}
            for dimension_field, dimension_value in alert.origin_alarm.get("data", {}).get("dimensions", {}).items()
            if dimension_field in query_config.get("agg_dimension", [])
        ]
        params = {
            "bizId": alert.event.bk_biz_id,
            "addition": json.dumps(addition),
            "start_time": start_time_str,
            "end_time": end_time_str,
            "keyword": query_config["query_string"],
        }
        # 构建原始日志链接（当is_raw=True时）
        if is_raw:
            bklog_link = f"{settings.BKLOGSEARCH_HOST}#/retrieve/{index_set_id}?{urlencode(params)}"
            record["bklog_link"] = bklog_link

    # 根据不同数据源类型提取内容
    if query_config["data_source_label"] in [DataSourceLabel.BK_MONITOR_COLLECTOR, DataSourceLabel.CUSTOM]:
        content = record["event"]["content"]
    elif query_config["data_source_label"] == DataSourceLabel.BK_FTA:
        content = record["description"]
    else:
        content = json.dumps(record, ensure_ascii=False)

    return content
