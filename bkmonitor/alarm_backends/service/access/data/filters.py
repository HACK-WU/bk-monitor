"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from __future__ import annotations

import logging

import arrow

from typing import TYPE_CHECKING

from alarm_backends import constants
from alarm_backends.core.cache.cmdb import HostManager
from alarm_backends.core.control.item import Item
from alarm_backends.service.access import base
from bkmonitor.utils.common_utils import safe_int

if TYPE_CHECKING:
    from alarm_backends.service.access.data.records import DataRecord
    from alarm_backends.service.access.event.records.base import EventRecord

logger = logging.getLogger("access.data")


class ExpireFilter(base.Filter):
    """
    过期数据过滤器
    """

    def filter(self, record):
        utctime = record.time
        # 丢弃超过max(半个小时 或者 10个周期延迟)的告警
        expire_seconds = max([record.items[0].query_configs[0]["agg_interval"] * 10, 30 * constants.CONST_MINUTES])
        if arrow.utcnow().timestamp - arrow.get(utctime).timestamp > expire_seconds:
            logger.info(f"Discard the data({record.raw_data}) because it takes more than 30 minutes")
            return True
        else:
            return False


class RangeFilter(base.Filter):
    """
    策略目标过滤器

    根据策略配置的监控目标范围（agg_condition）过滤数据记录。
    每条数据可能关联多个监控策略（items），每个策略有独立的目标范围配置。
    """

    def filter(self, record: "DataRecord" | "EventRecord"):  # noqa
        """
        根据策略目标范围过滤监控数据记录

        参数:
            record: DataRecord / EventRecord 监控数据记录对象，包含维度信息和关联的策略列表

        返回值:
            始终返回 False，表示记录不被整体过滤
            - 原因1：数据可能多策略共用，不同策略有不同的过滤条件
            - 原因2：即使所有策略都不匹配，也需保留记录供无数据告警使用

        过滤规则:
            1. 维度在策略范围内 → 不过滤，返回 False
            2. 维度不在策略范围内 → 过滤，返回 True

        处理流程:
            1. 获取记录的维度信息和关联的策略列表
            2. 遍历每个策略项（item），检查是否已被前置过滤器过滤
            3. 调用 item.is_range_match() 判断维度是否匹配策略目标范围
            4. 更新 record.is_retains 字典，标记每个策略的保留状态

        数据流:
            record.dimensions ──┐
                                ├──► item.is_range_match() ──► is_match
            item.agg_condition ─┘
                                              │
                                              ▼
                              record.is_retains[item_id] = is_match
        """
        # 获取记录的维度信息（如 bk_target_ip、bk_target_cloud_id 等）
        dimensions = record.dimensions
        # 获取记录关联的所有策略项（一条数据可能被多个策略使用）
        items: list[Item] = record.items

        for item in items:
            item_id = item.id
            # 跳过已被前置过滤器过滤的策略项，节省处理时间
            if not record.is_retains[item_id]:
                continue

            # 检查维度是否匹配策略配置的目标范围（agg_condition）
            is_match = item.is_range_match(dimensions)
            is_filtered = not is_match

            if is_filtered:
                logger.debug(
                    f"Discard the alarm ({record.raw_data}) because it not match strategy({item.strategy.id}) item({item_id}) agg_condition"
                )

            # 更新该策略项的保留状态：匹配则保留，不匹配则过滤
            record.is_retains[item_id] = not is_filtered

        # 始终返回 False：记录整体保留，各策略项的过滤状态已记录在 is_retains 中
        return False


class HostStatusFilter(base.Filter):
    """
    主机状态过滤器
    """

    def filter(self, record: DataRecord | EventRecord):
        """
        根据主机运营状态过滤监控数据记录

        如果主机运营状态为不监控的几种类型，则直接过滤该记录。
        该方法会检查主机的ignore_monitoring标志，决定是否保留该监控数据。

        参数:
            record: DataRecord / EventRecord 监控数据记录对象

        返回值:
            True: 该记录应被过滤（丢弃）
            False: 该记录应被保留（继续处理）

        处理流程:
        1. 检查是否为主机数据（包含bk_host_id或bk_target_ip维度）
        2. 验证主机标识的有效性
        3. 根据主机标识查询主机信息（优先使用bk_host_id）
        4. 检查主机的ignore_monitoring状态，更新记录的保留标志


          raw_data:
            {
                "bk_target_ip":"127.0.0.1",
                "load5":1.38,
                "bk_target_cloud_id":"0",
                "time":1569246480
            }

        output_standard_data:
            {
                "record_id":"f7659f5811a0e187c71d119c7d625f23",
                "value":1.38,
                "values":{
                    "timestamp":1569246480,
                    "load5":1.38
                },
                "dimensions":{
                    "bk_target_ip":"127.0.0.1",
                    "bk_target_cloud_id":"0"
                },
                "time":1569246480
            }

        """
        # 非主机数据不处理，直接放行
        if "bk_host_id" not in record.dimensions and "bk_target_ip" not in record.dimensions:
            return False

        # 过滤非法的主机数据：既没有主机ID也没有目标IP的记录
        if not record.dimensions.get("bk_target_ip") and not record.dimensions.get("bk_host_id"):
            return True

        # 根据主机标识查询主机信息（优先使用bk_host_id）
        if record.dimensions.get("bk_host_id"):
            # 通过主机ID查询（推荐方式，更精确）
            host = HostManager.get_by_id(
                bk_tenant_id=record.bk_tenant_id, bk_host_id=record.dimensions["bk_host_id"], using_mem=True
            )
        elif "bk_target_ip" in record.dimensions and "bk_target_cloud_id" in record.dimensions:
            # 通过IP和云区域ID查询（兼容旧数据）
            host = HostManager.get(
                bk_tenant_id=record.bk_tenant_id,
                ip=record.dimensions["bk_target_ip"],
                bk_cloud_id=safe_int(record.dimensions["bk_target_cloud_id"]),
                using_mem=True,
            )
        else:
            # 缺少必要的查询条件，过滤该记录
            return False

        # 主机不存在，记录日志并过滤
        if host is None:
            logger.debug(f"Discard the record ({record.raw_data}) because host is unknown")
            return True

        # 根据主机的ignore_monitoring标志更新记录中所有指标项的保留状态
        is_filtered = host.ignore_monitoring
        for item in record.items:
            # 只有当主机未被忽略且原本保留标志为True时，才保留该指标项
            record.is_retains[item.id] = not is_filtered and record.is_retains[item.id]

        # 记录过滤日志
        if is_filtered:
            logger.debug(
                f"Discard the record ({record.raw_data}) because host({host.display_name}) status is {host.bk_state}"
            )

        # 返回False表示不过滤整个记录，但内部已更新各指标项的保留状态
        return False
