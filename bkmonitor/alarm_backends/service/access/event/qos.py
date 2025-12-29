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

from django.conf import settings

from alarm_backends.core.cache import key
from bkmonitor.utils.common_utils import count_md5

logger = logging.getLogger("access.qos")


class QoSMixin:
    @classmethod
    def hash_alarm_by_match_info(cls, event_record, strategy_id, item_id):
        """
        根据告警匹配信息生成唯一哈希值，用于QoS流控标识

        参数:
            event_record: 事件记录对象，包含告警的完整信息
            strategy_id: 策略ID，标识触发告警的监控策略
            item_id: 监控项ID，标识具体的监控指标

        返回值:
            str: MD5哈希值，由业务ID、策略ID、监控项ID、目标IP和告警级别组成

        该哈希值用于在Redis中唯一标识一个告警维度，相同维度的告警会被计数统计
        """
        return count_md5(
            [
                event_record.bk_biz_id,
                strategy_id,
                item_id,
                event_record.data["data"]["dimensions"]["bk_target_ip"],
                event_record.level,
            ]
        )

    def check_qos(self, check_client=None):
        """
        执行QoS（服务质量）流控检查，防止告警洪泛

        参数:
            check_client: 可选的Redis客户端，用于测试或特殊场景

        返回值:
            bool: True表示QoS控制已启用，False表示未启用

        该方法实现告警流控机制，包含：
        1. 检查QoS控制开关是否启用
        2. 对每个事件记录按维度进行计数统计
        3. 超过阈值的告警会被丢弃，防止告警风暴
        4. 未超过阈值的告警保留到新列表中
        """
        # 获取Redis客户端，用于QoS计数统计
        client = check_client or key.QOS_CONTROL_KEY.client
        # 检查QoS控制开关是否启用，未启用则直接返回
        if not client.exists(key.QOS_CONTROL_KEY.get_key()):
            return False

        # 存储通过QoS检查的事件记录
        new_record_list = []
        # 遍历所有事件记录进行QoS检查
        for event_record in self.record_list:
            # 遍历事件关联的所有监控项
            # event_record.items: List[Item] - 监控项列表，每个Item对象包含id、strategy、algorithms等属性
            for item in event_record.items:
                strategy_id = item.strategy.id
                item_id = item.id
                # 跳过已被过滤或抑制的事件
                if not event_record.is_retains[item_id] or event_record.inhibitions[item_id]:
                    continue
                # 生成告警维度的唯一哈希值
                dimensions_md5 = self.hash_alarm_by_match_info(event_record, strategy_id, item_id)
                try:
                    # 使用Redis的hincrby原子递增该维度的告警计数
                    count_of_alarm = client.hincrby(
                        key.QOS_CONTROL_KEY.get_key(), key.QOS_CONTROL_KEY.get_field(dimensions_md5=dimensions_md5), 1
                    )
                    # 判断告警计数是否超过阈值
                    if count_of_alarm > settings.QOS_DROP_ALARM_THREADHOLD:
                        # 超过阈值则丢弃告警，记录警告日志
                        logger.warning(
                            "qos drop alarm: cc_biz_id(%s), host(%s), strategy_id(%s), item_id(%s), level(%s)",
                            event_record.bk_biz_id,
                            event_record.data["data"]["dimensions"]["bk_target_ip"],
                            strategy_id,
                            item_id,
                            event_record.level,
                        )
                    else:
                        # 未超过阈值则保留该事件记录
                        new_record_list.append(event_record)
                except Exception as err:
                    # 发生异常时保留事件记录，避免因QoS检查失败导致告警丢失
                    new_record_list.append(event_record)
                    logger.exception(err)

        # 更新事件记录列表为通过QoS检查的记录
        self.record_list = new_record_list
        return True
