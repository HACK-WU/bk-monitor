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
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from alarm_backends.core.control.mixins.double_check import DoubleCheckStrategy
from constants.action import NoticeWay

if TYPE_CHECKING:
    from bkmonitor.documents import AlertDocument

logger = logging.getLogger(__name__)


@dataclass
class SuspectedMissingPoints:
    alert: "AlertDocument"

    # 通知渠道降级序列，优先级从高到低
    NOTICE_WAY_DEGRADE_SEQUENCE: ClassVar[list] = [
        NoticeWay.VOICE,
        NoticeWay.SMS,
        NoticeWay.WEIXIN,
        NoticeWay.QY_WEIXIN,
        NoticeWay.WX_BOT,
        NoticeWay.MAIL,
    ]

    def handle(self, inputs: dict):
        """
        处理疑似数据缺失场景下的语音通知降级逻辑

        参数:
            inputs: 输入参数字典，包含 notify_info 通知配置信息

        返回值:
            None，直接修改 inputs 中的 notify_info

        该方法实现语音通知的降级处理流程，包含：
        1. 校验是否需要进行通知降级处理（检查 notify_info 和 VOICE 通知方式）
        2. 提取并扁平化语音通知组中的所有通知人（处理嵌套列表结构）
        3. 按降级序列查找可用的替代通知方式，将语音通知人合并到该方式
        4. 若无可用替代方式，则使用降级序列中的下一个通知方式
        """
        # 步骤1: 获取通知配置信息
        notify_info = inputs.get("notify_info", {})
        if not notify_info:
            logger.debug("Alert<%s>-<%s> 可能不需要通知，跳过二次处理", self.alert.id, self.alert.alert_name)
            return

        # 步骤2: 检查是否包含语音通知方式
        if NoticeWay.VOICE not in notify_info:
            logger.debug("Alert<%s>-<%s> 不需要语音通知，跳过二次处理", self.alert.id, self.alert.alert_name)
            return

        # 步骤3: 提取并扁平化语音通知组
        # 由于 VOICE 通知组内部可能存在顺序（嵌套列表），需要先拆解为扁平集合
        notify_group = set()
        for group in notify_info.pop(NoticeWay.VOICE):
            # 处理单个通知人的情况
            if not isinstance(group, list):
                notify_group.add(group)
                continue

            # 处理通知人列表的情况（嵌套结构）
            for g in group:
                notify_group.add(g)

        # 步骤4: 获取语音通知在降级序列中的位置
        voice_index = self.NOTICE_WAY_DEGRADE_SEQUENCE.index(NoticeWay.VOICE)

        # 步骤5: 查找可用的降级通知方式
        # 从语音通知位置开始，向后遍历降级序列，找到第一个已存在的通知方式
        for i in range(voice_index, len(self.NOTICE_WAY_DEGRADE_SEQUENCE)):
            if self.NOTICE_WAY_DEGRADE_SEQUENCE[i] in notify_info:
                # NOTE: 当前使用集合保证通知人不重复，但可能会改变原有的告警顺序
                # 但由于除了语音通知，其他通知渠道均对通知顺序不敏感，所以不做额外保证

                # 将原有通知人与语音通知人合并（去重）
                existed = set(notify_info[self.NOTICE_WAY_DEGRADE_SEQUENCE[i]])
                notify_info[self.NOTICE_WAY_DEGRADE_SEQUENCE[i]] = list(existed.union(notify_group))
                logger.info(
                    "由于二次确认怀疑告警<%s-%s>触发时数据存在缺失，故将语音通知降级处理，降级后的通知配置: %s",
                    self.alert.id,
                    self.alert.alert_name,
                    notify_info,
                )
                return

        # 步骤6: 若不存在其他通知方式，使用降级序列中的下一个通知方式
        # 直接将语音通知组分配给降级序列中语音通知的下一个通知方式
        notify_info[self.NOTICE_WAY_DEGRADE_SEQUENCE[voice_index + 1]] = list(notify_group)
        logger.info(
            "由于二次确认怀疑告警<%s-%s>触发时数据存在缺失，故将语音通知降级处理，降级后的通知配置: %s",
            self.alert.id,
            self.alert.alert_name,
            notify_info,
        )
        return


@dataclass
class DoubleCheckHandler:
    alert: "AlertDocument"
    double_check_result_handle_map: ClassVar[dict[str, type]] = {
        "SUSPECTED_MISSING_POINTS": SuspectedMissingPoints,
    }

    @property
    def tags(self) -> dict:
        return {t["key"]: t["value"] for t in getattr(self.alert.event, "tags", [])}

    def is_point_missing(self, alert=None) -> bool:
        """判断告警是否疑似数据缺失"""
        if alert is not None:
            tags = {t["key"]: t["value"] for t in getattr(alert.event, "tags", [])}
        else:
            tags = self.tags
        return DoubleCheckStrategy.DOUBLE_CHECK_CONTEXT_KEY in tags

    def handle(self, inputs: dict):
        """针对告警二次确认结果做相关处理"""
        if not self.is_point_missing():
            logger.debug("Alert<%s>-<%s> 不需要二次确认处理", self.alert.id, self.alert.alert_name)
            return

        double_check_result = self.tags[DoubleCheckStrategy.DOUBLE_CHECK_CONTEXT_KEY]
        handle_cls = self.double_check_result_handle_map.get(double_check_result, None)
        if handle_cls is None:
            logger.warning("未知二次确认结果: %s, 请在链路上游检查二次确认逻辑", double_check_result)
            return

        handle_cls(self.alert).handle(inputs)
