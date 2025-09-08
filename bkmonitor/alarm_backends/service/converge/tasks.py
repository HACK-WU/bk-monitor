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
from typing import Literal

from django.db import OperationalError

from alarm_backends.constants import CONST_HALF_MINUTE
from alarm_backends.service.scheduler.app import app
from core.prometheus import metrics
from constants.action import action_instance_id, converge_instance_id

logger = logging.getLogger("fta_action.converge")


@app.task(ignore_result=True, queue="celery_converge")
def run_converge(
    converge_config,
    instance_id: action_instance_id | converge_instance_id,
    instance_type: Literal["action", "converge"],
    converge_context=None,
    alerts=None,
    retry_times=0,
):
    """
    执行收敛动作的主函数，包含异常处理和自动重试机制

    参数:
        converge_config: 收敛策略配置对象，包含收敛规则和阈值设置
        instance_id: 对象唯一标识符（整型）
        instance_type: 对象类型标识（字符串）
        converge_context: 可选参数，收敛上下文数据字典
        alerts: 可选参数，告警快照数据列表
        retry_times: 当前重试次数计数器（整型，默认0次）

    返回值:
        None 表示正常结束
        异常情况下可能触发异步重试任务（通过apply_async）

    该函数实现完整的收敛处理流程：
    1. 初始化收敛处理器并执行核心收敛逻辑
    2. 处理各类异常情况（锁冲突、数据库异常、其他异常）
    3. 实现指数退避重试机制（最多3次）
    4. 记录监控指标（处理时间、成功率、异常类型统计）
    """
    from alarm_backends.service.converge.processor import (
        ConvergeLockError,
        ConvergeProcessor,
    )

    logger.info("--begin converge action(%s %s)--", instance_id, instance_type)

    exc = None

    bk_biz_id = 0
    start_time = time.time()
    try:
        # 创建收敛处理器实例并执行核心收敛逻辑
        converge_handler = ConvergeProcessor(converge_config, instance_id, instance_type, converge_context, alerts)
        bk_biz_id = getattr(converge_handler.instance, "bk_biz_id", 0)
        converge_handler.converge_alarm()
    except ConvergeLockError as error:
        # 处理收敛锁获取失败情况（资源竞争）
        logger.info(
            "end to converge %s, %s, due to can not get converge lock  %s", instance_type, instance_id, str(error)
        )
    except OperationalError as error:
        # 数据库操作异常处理
        exc = error
        logger.exception("execute converge %s, %s error: %s", instance_type, instance_id, error)
    except Exception as error:
        # 其他未预期异常处理
        exc = error
        logger.exception("execute converge %s, %s error: %s", instance_type, instance_id, error)
    else:
        # 收敛成功完成的日志记录
        logger.info("--end converge action(%s_%s)--  result %s", instance_id, instance_type, converge_handler.status)

    if exc:
        # 如果产生了异常，可以重试，至多3次
        if retry_times < 3:
            # 如果当前重试次数没有达到3次，可以重发任务
            task_id = run_converge.apply_async(
                (converge_config, instance_id, instance_type, converge_context, alerts, retry_times + 1),
                countdown=CONST_HALF_MINUTE,
            )
            logger.info(
                "[run_converge] retry to push %s(%s) to converge queue again, delay %s, task_id(%s)",
                instance_type,
                instance_id,
                CONST_HALF_MINUTE,
                task_id,
            )

    # 指标采集与监控上报
    cost = time.time() - start_time
    metrics.CONVERGE_PROCESS_TIME.labels(
        bk_biz_id=bk_biz_id, strategy_id=metrics.TOTAL_TAG, instance_type=instance_type
    ).observe(cost)
    metrics.CONVERGE_PROCESS_COUNT.labels(
        bk_biz_id=bk_biz_id,
        strategy_id=metrics.TOTAL_TAG,
        instance_type=instance_type,
        status=metrics.StatusEnum.from_exc(exc),
        exception=exc,
    ).inc()
    metrics.report_all()
