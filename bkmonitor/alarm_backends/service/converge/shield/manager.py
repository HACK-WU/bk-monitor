"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from bkmonitor.models import ActionInstance
from bkmonitor.documents import AlertDocument
from .shielder import AlertShieldConfigShielder, AlarmTimeShielder, GlobalShielder


class ShieldManager:
    """
    屏蔽管理
    """

    Shielders = (AlertShieldConfigShielder, AlarmTimeShielder)

    @classmethod
    def shield(cls, action_instance: ActionInstance, alerts: list[dict] = None):
        """
        屏蔽处理核心逻辑，按优先级依次执行全局屏蔽检测和各类屏蔽策略匹配

        参数:
            action_instance: ActionInstance对象，包含策略ID和关联告警ID列表
            alerts: 告警快照数据列表，默认为None时将从ES获取完整告警数据

        返回值:
            tuple (bool, Shielder)
            - 第一个元素表示是否匹配屏蔽规则
            - 第二个元素为匹配的屏蔽器实例或None

        执行流程:
        1. 全局屏蔽策略优先级最高，匹配则直接返回
        2. 告警数据优先使用传入快照，缺失时通过mget批量获取
        3. 按屏蔽器注册顺序依次匹配：
           - AlertShieldConfigShielder逐条检查告警策略匹配
           - AlarmTimeShielder检查时间范围匹配
        """
        # 先做全局屏蔽的检测
        global_shielder = GlobalShielder()
        if global_shielder.is_matched():
            return True, global_shielder

        if alerts:
            # 默认使用快照内容，快照没有，再从DB获取
            alerts = [AlertDocument(**alert) for alert in alerts]
        else:
            alerts = AlertDocument.mget(ids=action_instance.alerts)

        # 依次执行各类屏蔽策略匹配
        for shielder_cls in cls.Shielders:
            if shielder_cls == AlertShieldConfigShielder:
                for alert in alerts:
                    # 关联多告警的内容，只要有其中一个不满足条件，直接就屏蔽
                    alert.strategy_id = alert.strategy_id or action_instance.strategy_id
                    shielder = shielder_cls(alert)
                    if shielder.is_matched():
                        return True, shielder
            else:
                shielder = shielder_cls(action_instance)
                if shielder.is_matched():
                    return True, shielder
        return False, None
