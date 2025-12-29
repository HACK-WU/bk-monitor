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
import time

from kafka.consumer.fetcher import ConsumerRecord

from alarm_backends.core.alert import Event
from alarm_backends.service.alert.builder.processor import AlertBuilder
from alarm_backends.service.scheduler.app import app
from core.prometheus import metrics


@app.task(ignore_result=True, queue="celery_alert_builder")
def run_alert_builder(topic_data_id, bootstrap_server, events: list[ConsumerRecord]):
    """
    告警事件构建任务，将Kafka原始事件转换为告警对象并处理

    参数:
        topic_data_id (dict): Topic与DataID的映射表，格式为 {"{bootstrap_server}|{topic}": data_id}
        bootstrap_server (str): Kafka集群地址
        events (List[ConsumerRecord]): Kafka消费者记录列表

    返回值:
        无返回值，处理结果通过日志和指标上报

    执行流程:
    1. 遍历Kafka原始事件，解析JSON并补充data_id和topic字段
    2. 过滤无效事件，将有效事件转换为Event对象
    3. 调用AlertBuilder.process批量处理告警事件
    4. 记录处理耗时和成功率指标，上报到监控系统
    """
    builder = AlertBuilder()
    exc = None
    builder.logger.info("[alert.builder] start, total(%s) events", len(events))
    valid_events = []
    start = time.time()

    try:
        # 步骤1-2: 解析并过滤事件
        for event in events:
            try:
                topic = event.topic
                # 根据bootstrap_server和topic查找对应的data_id
                data_id = topic_data_id.get(f"{bootstrap_server}|{topic}")
                # 解析Kafka消息体（JSON格式）
                value = json.loads(event.value)
                # 补充元数据字段
                value.update({"data_id": data_id, "topic": topic})
                valid_events.append(Event(value))
            except Exception as e:
                # 单个事件解析失败不影响其他事件，记录警告后跳过
                builder.logger.warning("[alert.builder] ignore event: %s, reason: %s", event, e)
                continue

        # 步骤3: 批量处理有效事件
        builder.process(valid_events)
    except Exception as e:
        builder.logger.exception("[alert.builder ERROR] detail: %s", e)
        exc = e

    builder.logger.info("[alert.builder] end, event processed(%s/%s)", len(valid_events), len(events))

    # 步骤4: 上报性能指标
    if events:
        # 记录单个事件平均处理耗时
        metrics.ALERT_PROCESS_TIME.observe((time.time() - start) / len(events))

    # 记录处理的事件总数和状态（成功/失败）
    metrics.ALERT_PROCESS_PULL_EVENT_COUNT.labels(status=metrics.StatusEnum.from_exc(exc), exception=exc).inc(
        len(events)
    )
    metrics.report_all()


@app.task(ignore_result=True, queue="celery_alert_builder")
def dedupe_events_to_alerts(events: list[Event]):
    builder = AlertBuilder()
    try:
        builder.dedupe_events_to_alerts(events)
    except Exception as e:
        builder.logger.exception("[alert.builder dedupe_events_to_alerts] failed detail: %s", e)

    metrics.report_all()
