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

import arrow

from alarm_backends import constants
from alarm_backends.core.cache.cmdb import HostManager
from alarm_backends.core.control.item import Item
from alarm_backends.service.access import base
from alarm_backends.service.access.data.records import DataRecord
from bkmonitor.utils.common_utils import safe_int

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
    """

    def filter(self, record):
        """
        1. 在范围内，则不过滤掉，返回False
        2. 不在范围内，则过滤掉，返回True

        注意：每个item的范围是不一致的，只有当所有的item都被过滤掉后，才返回True

        :param record: DataRecord / EventRecord
        """

        dimensions = record.dimensions
        items: list[Item] = record.items
        for item in items:
            item_id = item.id
            if not record.is_retains[item_id]:
                # 如果被前面的filter过滤了，没有被保留下来，这里就直接跳过，节省时间
                continue

            is_match = item.is_range_match(dimensions)
            is_filtered = not is_match
            if is_filtered:
                logger.debug(
                    f"Discard the alarm ({record.raw_data}) because it not match strategy({item.strategy.id}) item({item_id}) agg_condition"
                )

            record.is_retains[item_id] = not is_filtered

        # 数据保留下来，因为数据可能多策略共用，不同策略有不同的过滤条件。同时都被过滤的情况下，也保留下来（给无数据告警使用）
        return False


class HostStatusFilter(base.Filter):
    """
    主机状态过滤器
    """

    def filter(self, record: DataRecord):
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
