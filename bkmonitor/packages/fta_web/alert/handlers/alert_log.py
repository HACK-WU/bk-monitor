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

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.models import NO_DATA_TAG_DIMENSION
from bkmonitor.utils.time_tools import utc2datetime
from bkmonitor.utils.user import get_user_display_name
from constants.alert import EVENT_SEVERITY_DICT, EventSeverity


class AlertLogHandler:
    OP_TYPE_DISPLAY = {
        AlertLog.OpType.CREATE: _lazy("告警产生"),
        AlertLog.OpType.CONVERGE: _lazy("告警收敛"),
        AlertLog.OpType.RECOVER: _lazy("告警恢复"),
        AlertLog.OpType.CLOSE: _lazy("告警关闭"),
        AlertLog.OpType.RECOVERING: _lazy("告警恢复中"),
        AlertLog.OpType.DELAY_RECOVER: _lazy("延迟恢复"),
        AlertLog.OpType.ABORT_RECOVER: _lazy("中断恢复"),
        AlertLog.OpType.SYSTEM_RECOVER: _lazy("系统恢复"),
        AlertLog.OpType.SYSTEM_CLOSE: _lazy("系统关闭"),
        AlertLog.OpType.ACK: _lazy("告警确认"),
        AlertLog.OpType.SEVERITY_UP: _lazy("告警级别调整"),
        AlertLog.OpType.ACTION: _lazy("处理动作"),
        AlertLog.OpType.ALERT_QOS: _lazy("告警流控"),
        AlertLog.OpType.EVENT_DROP: _lazy("事件忽略"),
    }

    def __init__(self, alert_id: str):
        self.alert = AlertDocument.get(alert_id)
        self.log_records = []

    def search(self, operate_list: list = None, offset: int = None, limit: int = None):
        """
        搜索告警日志记录，支持分页和操作类型过滤

        参数:
            operate_list: list, 操作类型过滤列表，可选值参考 AlertLog.OpType
                          例如: [AlertLog.OpType.CREATE, AlertLog.OpType.RECOVER]
            offset: int, 分页偏移量，为 create_time 时间戳，查询该时间之前的记录
            limit: int, 返回记录数量限制

        返回值:
            list[dict]: 告警日志记录列表，每条记录结构如下:
            {
                "action_id": str,          # 日志记录ID (ES文档ID)
                "time": datetime,          # 创建时间
                "operate": str,            # 操作类型 (如 CREATE/CONVERGE/RECOVER)
                "operate_display": str,    # 操作类型显示名称 (如 "告警产生")
                "offset": int,             # 时间戳，用于分页
                "contents": list[str],     # 日志内容列表
                ...                        # 其他字段根据操作类型不同而异
            }

        执行步骤:
            1. 构建ES搜索对象，按 alert_id 过滤并按时间倒序排序
            2. 应用操作类型过滤条件（如有）
            3. 应用时间偏移分页条件（如有）
            4. 遍历搜索结果，处理每条日志记录
            5. 对收敛类型记录进行特殊合并处理

        数据流:
            ES(AlertLog) --scan()--> hit --handle_hit()--> log_records
                                      |
                           [收敛记录合并: 同一时间戳的CONVERGE记录会被合并]
        """
        # 初始化日志记录列表
        self.log_records = []

        # 构建ES搜索对象:
        # - all_indices=True: 搜索所有索引（包含历史索引）
        # - ignore_unavailable=True: 忽略不可用的索引
        # - preserve_order=True: 保持排序顺序
        # - 按 alert_id 精确匹配过滤
        # - 排序规则: 创建时间倒序 -> 操作类型 -> 文档ID倒序
        search_object = (
            AlertLog.search(all_indices=True)
            .params(ignore_unavailable=True, preserve_order=True)
            .filter("term", alert_id=self.alert.id)
            .sort("-create_time", "op_type", "-_doc")
        )

        # 应用操作类型过滤条件（如: 只查询 CREATE 和 RECOVER 类型）
        if operate_list:
            search_object = search_object.filter("terms", op_type=operate_list)

        # 应用时间偏移分页条件（查询 create_time 小于 offset 的记录，用于分页加载更早的日志）
        if offset:
            search_object = search_object.filter("range", create_time={"lt": offset})

        # 使用 scan() 方法遍历搜索结果（游标方式，适合大量数据）
        for hit in search_object.scan():
            # ====== 分页截断逻辑 ======
            # 当已收集的记录数达到 limit 时，需要判断是否可以截断
            if limit and len(self.log_records) >= limit:
                last_record = self.log_records[-1]
                # 以下两种情况需要继续处理，不能截断:
                # 1. 当前和下一条都是收敛类型(CONVERGE)时，需要将剩余的收敛记录合并完
                # 2. 下一条记录的时间戳与上一条相同时，也要继续处理（保证同一时间点的记录完整）
                if (
                    last_record["operate"] != AlertLog.OpType.CONVERGE or hit.op_type != AlertLog.OpType.CONVERGE
                ) or hit.create_time < last_record["offset"]:
                    break

            # 处理单条日志记录，根据操作类型调用对应的处理方法
            self.handle_hit(hit)

        return self.log_records

    def handle_hit(self, hit: AlertLog):
        content_handlers = {
            AlertLog.OpType.CREATE: self.add_record_create,
            AlertLog.OpType.CONVERGE: self.add_record_converge,
            AlertLog.OpType.RECOVER: self.add_record_recover,
            AlertLog.OpType.CLOSE: self.add_record_close,
            AlertLog.OpType.DELAY_RECOVER: self.add_record_delay_recover,
            AlertLog.OpType.ABORT_RECOVER: self.add_record_abort_recover,
            AlertLog.OpType.SYSTEM_RECOVER: self.add_record_system_recover,
            AlertLog.OpType.SYSTEM_CLOSE: self.add_record_system_close,
            AlertLog.OpType.ACK: self.add_record_ack,
            AlertLog.OpType.SEVERITY_UP: self.add_record_severity_up,
            AlertLog.OpType.ACTION: self.add_record_action,
            AlertLog.OpType.ALERT_QOS: self.add_record_action,
            AlertLog.OpType.EVENT_DROP: self.add_record_event_drop,
        }

        record = {
            "action_id": hit.meta.id,
            "time": utc2datetime(hit.create_time),
            "operate": hit.op_type,
            "operate_display": self.OP_TYPE_DISPLAY.get(hit.op_type, hit.op_type),
            "offset": hit.create_time,
        }

        op_type = hit.op_type

        if op_type in content_handlers:
            content_handlers[op_type](AlertLog(**hit.to_dict()), record)
        else:
            self.add_record_default(AlertLog(**hit.to_dict()), record)

    def add_record_create(self, hit, record):
        """
        处理告警产生类型的日志记录

        参数:
            hit: ES搜索命中结果，包含 description 等日志字段
            record: dict, 基础日志记录字典，由 handle_hit 方法预先构建

        执行步骤:
            1. 提取告警描述作为日志内容的基础
            2. 获取告警开始时间作为数据源时间
            3. 根据告警类型（无数据/普通）生成对应的触发条件描述
            4. 更新记录并追加到日志列表

        触发条件说明:
            - 无数据告警: "数据连续丢失N个周期"
            - 普通告警: "N周期内满足M次检测算法"
        """
        # 初始化日志内容列表，首条为告警描述
        contents = [hit.description]
        # 获取告警开始时间（UTC转本地时间）
        source_time = utc2datetime(self.alert.begin_time)

        # 判断是否存在策略配置且包含检测算法
        if self.alert.strategy and self.alert.strategy["items"][0]["algorithms"]:
            item = self.alert.strategy["items"][0]
            detect = self.alert.strategy["detects"][0]

            # 根据告警类型生成不同的触发条件描述
            if NO_DATA_TAG_DIMENSION in self.alert.origin_alarm["data"]["dimensions"]:
                # 无数据告警: 从 no_data_config 获取连续丢失周期数
                continuous = item["no_data_config"]["continuous"]
                contents.append(_(" 达到了触发告警条件（数据连续丢失{}个周期）").format(continuous))
            else:
                # 普通告警: 从 trigger_config 获取检查窗口和触发次数
                trigger_config = detect["trigger_config"]
                contents.append(
                    _(" 达到了触发告警条件（{}周期内满足{}次检测算法）").format(
                        trigger_config["check_window"], trigger_config["count"]
                    )
                )

        # 更新记录: source_time=数据源时间, index=0表示首条记录, contents=日志内容列表
        record.update({"source_time": source_time, "index": 0, "contents": contents})
        self.log_records.append(record)

    def add_record_recover(self, hit, record):
        record.update(
            {
                "contents": [hit.description],
            }
        )
        self.log_records.append(record)

    def add_record_delay_recover(self, hit, record):
        record.update(
            {
                "contents": [
                    hit.description,
                    _("根据系统配置，告警将于 {} 延时恢复").format(utc2datetime(hit.next_status_time)),
                ]
            }
        )
        self.log_records.append(record)

    def add_record_abort_recover(self, hit, record):
        if hit.description:
            record.update({"contents": [hit.description]})
        else:
            record.update({"contents": [_("在延时恢复的时间窗口收到了新的异常事件，延时恢复被中断")]})
        self.log_records.append(record)

    def add_record_system_recover(self, hit, record):
        record.update({"contents": [_("延时恢复时间窗口结束，告警已恢复")]})
        self.log_records.append(record)

    def add_record_ack(self, hit, record):
        display_name = ""
        if hit.operator:
            display_name = get_user_display_name(hit.operator)

        if hit.description:
            contents = [_("{}确认了该告警事件并备注：").format(display_name), hit.description]
        else:
            contents = [_("{}确认了该告警事件").format(display_name)]
        record.update({"contents": contents})
        self.log_records.append(record)

    def add_record_close(self, hit, record):
        record.update(
            {
                "contents": [hit.description],
            }
        )
        self.log_records.append(record)

    def add_record_default(self, hit, record):
        record.update(
            {
                "contents": [hit.description],
            }
        )
        self.log_records.append(record)

    def add_record_system_close(self, hit, record):
        record.update(
            {
                "contents": [_("长时间未收到新的异常事件，系统关闭告警")],
            }
        )
        self.log_records.append(record)

    def add_record_event_drop(self, hit, record):
        contents = [
            hit.description,
            _("告警级别【{}】低于当前告警触发级别，系统已忽略").format(EventSeverity.get_display_name(hit.severity)),
        ]
        self.record_collect(hit, record, AlertLog.OpType.EVENT_DROP, contents)

    def add_record_converge(self, hit, record):
        self.record_collect(hit, record)

    def record_collect(self, hit, record, op_type=AlertLog.OpType.CONVERGE, contents=None):
        """
        汇总部分收敛记录和告警事件丢弃记录
        """

        record.update(
            {
                "index": 0,
                "contents": contents if contents else [hit.description],
                "time": utc2datetime(hit.create_time),
                "begin_time": utc2datetime(hit.create_time),
                "is_multiple": False,
                "source_time": utc2datetime(hit.time),
                "begin_source_time": utc2datetime(hit.time),
                "source_timestamp": hit.time,
                "begin_source_timestamp": hit.time,
                "count": 1,
                "offset": hit.create_time,
            }
        )

        should_create = False
        if not self.log_records:
            should_create = True
        elif self.log_records[-1]["operate"] != op_type:
            # 如果前一条记录不是收敛类型，就增加一条新的
            should_create = True
        elif len(self.log_records) == 1:
            # 如果只有一条流水，且上一条是收敛，则让上一条显示详情，然后另开一条新的做收敛
            should_create = True
        elif self.log_records[-2]["operate"] != op_type:
            # 如果有两条以上的流水，且上条是收敛，上上条不是收敛，也需要另开一条新的做收敛
            should_create = True
        if should_create:
            self.log_records.append(record)
        else:
            # 如果前一条记录是收敛类型，就在原来的基础上更新
            last_record = self.log_records[-1]
            last_record["time"] = max(record["time"], last_record["time"])
            last_record["begin_time"] = min(record["begin_time"], last_record["begin_time"])
            last_record["source_time"] = max(record["source_time"], last_record["source_time"])
            last_record["begin_source_time"] = min(record["begin_source_time"], last_record["begin_source_time"])
            last_record["source_timestamp"] = max(record["source_timestamp"], last_record["source_timestamp"])
            last_record["begin_source_timestamp"] = min(
                record["begin_source_timestamp"], last_record["begin_source_timestamp"]
            )
            last_record["is_multiple"] = True
            last_record["count"] += 1
            last_record["offset"] = min(record["offset"], last_record["offset"])

    def add_record_severity_up(self, hit, record):
        record.update(
            {
                "contents": [
                    _("收到了更高级别的事件，告警级别上升为：{}").format(
                        EVENT_SEVERITY_DICT.get(hit.severity, hit.severity)
                    )
                ],
            }
        )
        self.log_records.append(record)

    def add_record_action(self, hit, record):
        data = hit.to_dict()
        try:
            content = json.loads(data.get("description", ""))
        except BaseException:
            content = {"text": data.get("description", "")}
        record.update(
            {
                "contents": [content.get("text", "")],
                "action_plugin_type": content.get("action_plugin_type"),
            }
        )
        # router_info 供前端拼接路由，拼接好的 url 用于第三方跳转
        if "router_info" in content:
            record["router_info"] = content["router_info"]
        else:
            record["url"] = content.get("url", "")

        record.update({"action_id": hit["event_id"]})
        self.log_records.append(record)
