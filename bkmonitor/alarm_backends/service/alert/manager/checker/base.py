# -*- coding: utf-8 -*-
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
import time
from typing import List

from alarm_backends.core.alert import Alert

# 初始化日志记录器，用于记录警报管理相关的信息
logger = logging.getLogger("alert.manager")


class BaseChecker:
    def __init__(self, alerts: List[Alert]):
        # 初始化时接收一个Alert对象列表
        self.alerts = alerts

    def is_enabled(self, alert: Alert):
        # 默认情况下，如果为异常告警，则进行检查
        return alert.is_abnormal()

    def check(self, alert: Alert):
        # 抽象方法，需要在子类中实现具体的检查逻辑
        raise NotImplementedError

    def check_all(self):
        # 初始化成功和失败的计数器
        success = 0
        failed = 0
        # 记录开始检查的时间
        start = time.time()
        for alert in self.alerts:
            # 如果警报异常，则进行检查，
            # 如果是异常告警，则is_enabled()方法返回True，否则返回False
            # 换言之，如果是异常告警则会进行检查
            if self.is_enabled(alert):
                try:
                    self.check(alert)
                    # 如果检查成功，增加成功计数器
                    success += 1
                except Exception as e:
                    # 如果检查过程中发生异常，记录异常信息，并增加失败计数器
                    logger.exception(
                        "[%s failed] alert(%s) strategy(%s) %s", self.__class__.__name__, alert.id, alert.strategy_id, e
                    )
                    failed += 1
        # 记录检查结束的时间，并计算总耗时
        logger.info(
            "[%s] success(%s), failed(%s), cost: %s", self.__class__.__name__, success, failed, time.time() - start
        )
