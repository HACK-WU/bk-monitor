"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import collections
import logging

from django.utils.functional import cached_property

from bkmonitor.models import ActionInstance
from constants.action import NoticeChannel, NoticeWay
from utils import count_md5
from . import BaseContextObject, ActionContext

logger = logging.getLogger("fta_action.run")


class Converge(BaseContextObject):
    """
    告警信息收敛上下文对象
    """

    def __int__(self, parent):
        assert isinstance(parent, ActionContext), "ERROR: parent must be ActionContext"
        super().__init__(parent)

    @cached_property
    def bk_biz_id(self):
        """
        业务ID
        """
        return self.parent.action.bk_biz_id

    @cached_property
    def bk_host_id(self):
        return self.parent.target.host.bk_host_id

    @cached_property
    def bk_set_ids(self):
        """集群信息"""
        self.parent.target.host.bk_set_ids.sort()
        return self.parent.target.host.bk_set_ids

    @cached_property
    def bk_module_ids(self):
        """模块信息"""
        self.parent.target.host.bk_module_ids.sort()
        return self.parent.target.host.bk_module_ids

    @cached_property
    def rack_id(self):
        """
        rack_id: 机架
        """
        return self.parent.target.host.rack_id

    @cached_property
    def net_device_id(self):
        """
        网络设备ID == 交换机
        """
        return self.parent.target.host.net_device_id

    @cached_property
    def idc_unit_name(self):
        """
        机房
        """
        return self.parent.target.host.idc_unit_name

    @cached_property
    def alert_name(self):
        """
        告警名称
        """
        return self.parent.alarm.name

    @cached_property
    def strategy_id(self):
        """
        对应的策略ID
        :return:
        """
        return self.parent.action.strategy_id

    @cached_property
    def action_id(self):
        """
        处理套餐ID
        """
        return self.parent.action_config_id

    @cached_property
    def alert_level(self):
        """
        发送通知方式
        """
        return self.parent.action.alert_level

    @cached_property
    def alert_info(self):
        if self.strategy_id:
            return f"{self.strategy_id}_{self.alert_level}_{self.signal}_{self.dimensions}"
        return f"{self.alert_name}_{self.alert_level}_{self.signal}_{self.dimensions}"

    @cached_property
    def signal(self):
        """
        发送通知方式
        """
        return self.parent.action.signal

    @cached_property
    def notice_way(self):
        """
        发送通知方式
        """
        if self.parent.notice_channel not in NoticeChannel.DEFAULT_CHANNELS:
            # 如果不在默认渠道内的话，需要拼接channel
            return f"{self.parent.notice_channel}|{self.parent.notice_way}"
        return self.parent.notice_way

    @cached_property
    def notice_receiver(self):
        """
        接收人
        """
        if self.notice_way == NoticeWay.VOICE:
            return ",".join(self.parent.action.inputs.get("notice_receiver", []))
        return self.parent.notice_receiver

    @cached_property
    def user_type(self):
        """
        对应用户组的类型：关注人或者None
        """
        return self.parent.user_type

    @cached_property
    def group_notice_way(self):
        """
        带用户类型的通知方法，包含了用户组的信息
        """
        if self.user_type:
            return f"{self.user_type}_{self.notice_way}"
        return self.notice_way

    @cached_property
    def notice_info(self):
        """
        通知信息组合
        :return:
        """
        return f"{self.alert_info}_{self.notice_way}_{self.notice_receiver}"

    @cached_property
    def action_info(self):
        """
        :return:
        """
        return f"{self.strategy_id}_{self.signal}_{self.action_id}"

    @cached_property
    def process(self):
        """
        进程名称
        """
        return self.parent.target.process["process_name"].bk_process_name

    @cached_property
    def port(self):
        """进程绑定端口"""
        return self.parent.target.process["process_name"].port

    @cached_property
    def dimensions(self):
        """
        普通维度
        """
        if self.parent.action.dimension_hash:
            return self.parent.action.dimension_hash

        order_dimensions = {}
        try:
            dimensions_dict = {d["key"]: d["value"] for d in self.parent.alert.common_dimensions if d.get("value")}
            order_dimensions = collections.OrderedDict(sorted(dimensions_dict.items()))
        except BaseException as error:
            if isinstance(self.parent.action, ActionInstance):
                logger.info("$%s get dimensions ctx error %s", self.parent.action.id, str(error))
        return count_md5(order_dimensions)

    @cached_property
    def target(self):
        """目标"""
        return self.parent.alert.event_document.target

    @cached_property
    def action_create_time(self):
        return int(self.parent.action.create_time.timestamp())

    @cached_property
    def action_status(self):
        return self.parent.action.status

    def get_dict(self, fields: list[str]):
        """根据需要转成"""
        ctx_dict = {}
        for field in fields:
            try:
                ctx_dict[field] = getattr(self, field, "")
            except BaseException as error:
                ctx_dict[field] = None
                logger.debug(f"action({self.parent.action.id}) create converge context field({field}) error, {error}")
        return ctx_dict
