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

from alarm_backends.core.cache import key
from alarm_backends.service.detect.process import DetectProcess
from alarm_backends.service.scheduler.app import app
from core.errors.alarm_backends import LockError
from core.prometheus import metrics

logger = logging.getLogger("detect")


@app.task(ignore_result=True, queue="celery_service")
def run_detect(strategy_id):
    """
    执行策略检测的Celery异步任务

    参数:
        strategy_id: 策略ID，用于标识需要检测的策略

    该方法实现策略检测的完整执行流程，包含：
    1. 初始化Redis客户端和数据信号Key，用于延迟重试场景
    2. 创建检测处理器并执行检测逻辑
    3. 锁冲突处理：获取分布式锁失败时，通过延迟队列20秒后重新投递策略ID
    4. 异常处理：捕获并记录非锁类异常，用于指标上报
    5. 忙碌处理：当前策略待检测数据积压时，异步重新调度本任务
    6. 上报检测处理计数指标并推送至Prometheus
    """
    # 获取数据信号队列的Redis客户端和Key，用于锁冲突时延迟重试
    client = key.DATA_SIGNAL_KEY.client
    data_signal_key = key.DATA_SIGNAL_KEY.get_key()
    exc = None
    try:
        # 创建检测处理器并执行策略检测
        processor = DetectProcess(strategy_id)
        processor.process()
    except LockError:
        # 获取分布式锁失败，说明其他worker正在处理该策略
        # 将策略ID通过延迟队列20秒后重新推入数据信号队列，等待下次调度
        logger.info(f"Failed to acquire lock. on strategy({strategy_id})")
        client.delay("lpush", data_signal_key, strategy_id, delay=20)
    except Exception as e:
        # 记录异常，用于后续指标上报（异常状态不重试，由上层决定处理方式）
        exc = e
        logger.exception(f"Process strategy({strategy_id}) exception, {e}")
    else:
        # 检测正常完成，但当前策略待检测数据量过多（is_busy=True）
        # 重新投递Celery任务，让下一个调度周期继续处理剩余数据
        if processor.is_busy:
            run_detect.apply_async(args=(strategy_id,))
            logger.info(f"detect processor is busy with strategy({strategy_id})")

    # 上报检测处理计数指标（成功/失败/异常状态由exc决定）
    metrics.DETECT_PROCESS_COUNT.labels(
        strategy_id=metrics.TOTAL_TAG, status=metrics.StatusEnum.from_exc(exc), exception=exc
    ).inc()

    metrics.report_all()


@app.task(ignore_result=True, queue="celery_service_aiops")
def run_detect_with_sdk(strategy_id):
    """
    使用AIOps SDK执行策略检测的Celery异步任务

    参数:
        strategy_id: 策略ID，用于标识需要检测的策略

    该方法是run_detect的AIOps版本，使用独立的Celery队列(celery_service_aiops)，
    实际检测逻辑委托给run_detect执行。
    """
    return run_detect(strategy_id)
