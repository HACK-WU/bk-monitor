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
import time

from elasticsearch.helpers import BulkIndexError
from elasticsearch_dsl import Q

from alarm_backends.constants import CONST_ONE_DAY, CONST_ONE_HOUR
from alarm_backends.core.alert.alert import Alert, AlertCache, AlertKey
from alarm_backends.core.cache.strategy import StrategyCacheManager
from alarm_backends.core.cluster import get_cluster_bk_biz_ids
from alarm_backends.service.alert.manager.processor import AlertManager
from alarm_backends.service.scheduler.app import app
from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.documents.base import BulkActionType
from constants.alert import EventStatus
from core.prometheus import metrics

logger = logging.getLogger("alert.manager")

# 批处理条数
BATCH_SIZE = 200
# 默认检测周期
DEFAULT_CHECK_INTERVAL = 60


def check_abnormal_alert():
    """
    拉取异常告警，对这些告警进行状态管理
    """
    search = (
        AlertDocument.search(all_indices=True)
        .filter(Q("term", status=EventStatus.ABNORMAL) & ~Q("term", is_blocked=True))
        .source(fields=["id", "strategy_id", "event.bk_biz_id"])
    )

    # 获取集群内的业务ID
    cluster_bk_biz_ids = set(get_cluster_bk_biz_ids())

    alerts = []
    # 这里用 scan 迭代的查询方式，目的是为了突破 ES 查询条数 1w 的限制
    for hit in search.params(size=5000).scan():
        if not getattr(hit, "id", None) or not getattr(hit, "event", None) or not getattr(hit.event, "bk_biz_id", None):
            continue
        # 只处理集群内的告警
        if hit.event.bk_biz_id not in cluster_bk_biz_ids:
            continue
        alerts.append({"id": hit.id, "strategy_id": getattr(hit, "strategy_id", None)})

    if alerts:
        send_check_task(alerts)


def check_blocked_alert():
    """
    拉取异常告警，对这些告警进行状态管理
    """
    current_time = int(time.time())
    end_time = current_time - CONST_ONE_HOUR
    start_time = current_time - CONST_ONE_DAY
    logger.info("[check_blocked_alert] begin %s - %s", start_time, end_time)
    search = (
        AlertDocument.search(start_time=start_time, end_time=end_time)
        .filter(Q("term", status=EventStatus.ABNORMAL) & Q("term", is_blocked=True))
        .source(fields=["id", "strategy_id", "event.bk_biz_id"])
    )

    # 获取集群内的业务ID
    cluster_bk_biz_ids = set(get_cluster_bk_biz_ids())

    alerts = []
    total = 0
    # 这里用 scan 迭代的查询方式，目的是为了突破 ES 查询条数 1w 的限制
    for hit in search.params(size=BATCH_SIZE).scan():
        if not getattr(hit, "id", None) or not getattr(hit, "event", None) or not getattr(hit.event, "bk_biz_id", None):
            continue
        # 只处理集群内的告警
        if hit.event.bk_biz_id not in cluster_bk_biz_ids:
            continue
        alerts.append({"id": hit.id, "strategy_id": getattr(hit, "strategy_id", None)})
        total += 1
        if total % BATCH_SIZE == 0:
            alert_keys = [AlertKey(alert_id=alert["id"], strategy_id=alert.get("strategy_id")) for alert in alerts]
            check_blocked_alert_finished(alert_keys)
            logger.info("[check_blocked_alert]  blocked alert processed (%s)", len(alert_keys))
            alerts = []

    alert_keys = [AlertKey(alert_id=alert["id"], strategy_id=alert.get("strategy_id")) for alert in alerts]
    check_blocked_alert_finished(alert_keys)
    total += len(alerts)
    logger.info("[check_blocked_alert]  blocked alert total count(%s)", total)


def check_blocked_alert_finished(alert_keys):
    alerts = Alert.mget(alert_keys)
    for alert in alerts:
        alert.move_to_next_status()

    alert_logs = []
    alert_documents = []
    closed_alerts = []
    updated_alert_snaps = []
    for alert in alerts:
        if alert.should_refresh_db():
            alert_logs.extend(alert.list_log_documents())
            alert_documents.append(alert.to_document())
            updated_alert_snaps.append(alert)
        if alert.status == EventStatus.CLOSED:
            closed_alerts.append(alert.id)
    if alert_documents:
        try:
            AlertDocument.bulk_create(alert_documents, action=BulkActionType.UPSERT)
        except BulkIndexError as e:
            logger.error(
                "[check_blocked_alert_finished] save blocked alert document failed, total count(%s), "
                " updated(%s), error detail: %s",
                len(alert_keys),
                len(alert_documents),
                e.errors,
            )
            return
    if updated_alert_snaps:
        AlertCache.save_alert_to_cache(updated_alert_snaps)
        AlertCache.save_alert_snapshot(updated_alert_snaps)

    if alert_logs:
        try:
            AlertLog.bulk_create(alert_logs)
        except BulkIndexError as e:
            logger.error(
                "[check_blocked_alert_finished] save alert log document total count(%s) error: %s",
                len(alert_logs),
                e.errors,
            )
    logger.info(
        "[check_blocked_alert_finished] update blocked alert next status succeed, "
        "total count(%s), updated(%s), closed(%s)",
        len(alerts),
        len(alert_documents),
        len(closed_alerts),
    )


def send_check_task(alerts: list[dict], run_immediately=True):
    """
    生成告警检测任务并调度异步执行

    参数:
        alerts: 告警对象列表，每个元素包含id和strategy_id等必要字段
        run_immediately: 布尔值，控制是否立即执行首次检测（默认True）

    返回值:
        None（空列表输入时直接返回）

    执行流程：
    1. 告警分组：根据监控周期将告警分组处理
    2. 任务调度：根据配置周期生成延迟执行任务
    3. 批量处理：按批次大小限制并发处理数量
    4. 日志记录：统计并记录不同周期的告警数量
    """
    if not alerts:
        return

    # 按监控周期对告警进行分组，返回{周期: [告警列表]}结构
    alert_ids_with_interval = cal_alerts_check_interval(alerts)

    # 遍历不同监控周期的告警分组
    for check_interval, alerts in alert_ids_with_interval.items():
        # 初始延迟时间根据立即执行标志确定
        countdown = 0 if run_immediately else check_interval

        # 在基准周期内循环创建延迟任务，实现：
        # - 15秒周期：每分钟执行4次
        # - 30秒周期：每分钟执行2次
        # - 60秒周期：每分钟执行1次
        while countdown < DEFAULT_CHECK_INTERVAL:
            # 按批次大小分割告警列表，防止单次处理过多数据
            for index in range(0, len(alerts), BATCH_SIZE):
                # 异步提交告警处理任务，设置：
                # - 延迟执行时间
                # - 任务过期时间（120秒）
                # - 批量告警键对象列表作为参数
                handle_alerts.apply_async(
                    countdown=countdown,
                    expires=120,
                    kwargs={
                        # 告警键对象列表，后续优先从缓存中获取到告警，获取失败后再从ES中获取。
                        # 因为后续告警处理后，告警信息发生变化，会将其更到新缓存。
                        # 所以优先从缓存中获取，避免使用旧数据。
                        "alert_keys": [
                            AlertKey(alert_id=alert["id"], strategy_id=alert.get("strategy_id"))
                            for alert in alerts[index : index + BATCH_SIZE]
                        ]
                    },
                )
            # 累加当前周期间隔，推进到下一次执行时间点
            countdown += check_interval

    # 记录已发送的告警统计日志，按不同监控周期分类计数
    logger.info(
        "[check_abnormal_alert] alerts(%s/60s, %s/30s, %s/15s) sent to AlertManager",
        len(alert_ids_with_interval[60]),
        len(alert_ids_with_interval[30]),
        len(alert_ids_with_interval[15]),
    )


@app.task(ignore_result=True, queue="celery_alert_manager")
def handle_alerts(alert_keys: list[AlertKey]):
    """
    处理告警（异步任务）
    """
    exc = None
    if not alert_keys:
        return
    total = len(alert_keys)
    manager = AlertManager(alert_keys)
    start_time = time.time()
    try:
        manager.logger.info("[alert.manager start] with total alerts(%s)", total)
        manager.process()
    except Exception as e:
        manager.logger.exception("[alert.manager ERROR] detail: %s", e)
        exc = e
        cost = time.time() - start_time
    else:
        cost = time.time() - start_time
        manager.logger.info("[alert.manager end] cost: %s", cost)

    # 按单条告警进行统计耗时，因为这有两个入口：
    # 1. 周期维护未恢复的告警， 按 total=200 分批跑
    # 2. 产生新告警时，由alert.builder 立刻执行一次周期任务管理， total 较小。
    # 因此会存在耗时跟随total值的变化抖动。所以这里算单条告警的处理平均耗时才能体现出实际情况
    metrics.ALERT_MANAGE_TIME.labels(status=metrics.StatusEnum.from_exc(exc), exception=exc).observe(cost / total)
    metrics.ALERT_MANAGE_COUNT.labels(status=metrics.StatusEnum.from_exc(exc), exception=exc).inc(total)
    metrics.report_all()


def fetch_agg_interval(strategy_ids: list[int]):
    """
    根据策略ID获取每个策略的聚合周期
    """
    agg_interval_by_strategy = {}

    strategies = StrategyCacheManager.get_strategy_by_ids(strategy_ids)

    for strategy in strategies:
        for item in strategy["items"]:
            # 补充周期缓存
            if "query_configs" not in item:
                continue

            for config in item["query_configs"]:
                if "agg_interval" not in config:
                    continue
                if strategy["id"] in agg_interval_by_strategy:
                    # 如果一个策略存在多个agg_interval，则取最小值
                    agg_interval_by_strategy[strategy["id"]] = min(
                        agg_interval_by_strategy[strategy["id"]], config["agg_interval"]
                    )
                else:
                    agg_interval_by_strategy[strategy["id"]] = config["agg_interval"]
    return agg_interval_by_strategy


def cal_alerts_check_interval(alerts: list[dict]):
    """
    计算告警的检查周期分类

    参数:
        alerts (List[Dict]): 待处理的告警列表，每个告警字典应包含以下可选字段:
            - strategy_id (str): 关联的策略ID标识符

    返回值:
        Dict[int, List[Dict]]: 按检查周期分类的告警字典，结构为:
        {
            15: [alert1, alert2],  # 每15秒检查一次的告警列表
            30: [alert3],          # 每30秒检查一次的告警列表
            60: [alert4, alert5]   # 每60秒检查一次的告警列表
        }

    处理逻辑:
        1. 根据策略ID获取聚合间隔配置
        2. 按以下规则进行分类：
           - 聚合间隔<30s → 15s检查周期
           - 30s≤聚合间隔<60s → 30s检查周期
           - 其他情况 → 60s检查周期
        3. 无有效策略配置的告警默认归入60s检查周期
    """
    # 初始化检查周期分类容器
    check_interval = {
        15: [],
        30: [],
        60: [],
    }

    # 收集所有有效策略ID用于批量查询配置
    strategy_ids = set()
    for alert in alerts:
        strategy_id = alert.get("strategy_id")
        if strategy_id:
            strategy_ids.add(strategy_id)

    # 获取策略ID对应的聚合间隔配置
    agg_interval_config = fetch_agg_interval(strategy_ids=list(strategy_ids))

    # 根据策略配置将告警分配到不同检查周期
    for alert in alerts:
        strategy_id = alert.get("strategy_id")
        if not strategy_id or strategy_id not in agg_interval_config:
            # 告警没有策略ID，或者策略中没有周期配置，则按默认60秒检查一次
            check_interval[60].append(alert)
            continue

        agg_interval = agg_interval_config[strategy_id]
        if agg_interval < 30:
            check_interval[15].append(alert)
        elif agg_interval < 60:
            check_interval[30].append(alert)
        else:
            check_interval[60].append(alert)

    return check_interval
