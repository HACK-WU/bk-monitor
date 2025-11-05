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
import copy
import hashlib
import logging
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Literal

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from alarm_backends.constants import CONST_HALF_MINUTE, CONST_MINUTES, CONST_SECOND
from alarm_backends.core.cache.action_config import ActionConfigCacheManager
from alarm_backends.core.cache.key import (
    ACTION_CONVERGE_KEY_PROCESS_LOCK,
    FTA_NOTICE_COLLECT_KEY,
)
from alarm_backends.core.context import ActionContext
from alarm_backends.service.converge.converge_func import ConvergeFunc
from alarm_backends.service.converge.converge_manger import ConvergeManager
from alarm_backends.service.converge.shield import ShieldManager
from alarm_backends.service.converge.shield.shielder import AlertShieldConfigShielder
from alarm_backends.service.converge.utils import get_execute_related_ids
from alarm_backends.service.fta_action import need_poll
from alarm_backends.service.fta_action.tasks import dispatch_action_task
from bkmonitor.models.fta.action import ActionInstance, ConvergeInstance
from bkmonitor.utils import extended_json
from constants.action import (
    ALL_CONVERGE_DIMENSION,
    ActionPluginType,
    ActionStatus,
    ConvergeType,
    action_instance_id,
    converge_instance_id,
)
from core.errors.alarm_backends import ActionAlreadyFinishedError, StrategyNotFound
from core.prometheus import metrics

logger = logging.getLogger("fta_action.converge")


class ConvergeLockError(BaseException):
    def __init__(self, *args, **kwargs):  # real signature unknown
        pass


class ConvergeProcessor:
    InstanceModel = {ConvergeType.CONVERGE: ConvergeInstance, ConvergeType.ACTION: ActionInstance}

    def __init__(
        self,
        converge_config,
        instance_id: action_instance_id | converge_instance_id,
        instance_type: Literal["action", "converge"],
        converge_context=None,
        alerts=None,
    ):
        """
        收敛处理器基类，用于处理告警收敛的核心逻辑
        "converge_config": {
            "count": 1,
            "condition": [
                {
                    "dimension": "strategy_id",
                    "value": [
                        "self"
                    ]
                }
            ],
            "timedelta": 60,
            "is_enabled": true,
            "converge_func": "collect",
            "need_biz_converge": true,
            "sub_converge_config": {
                "timedelta": 60,
                "count": 2,
                "condition": [
                    {
                        "dimension": "bk_biz_id",
                        "value": ["self"]
                    }
                ],
                "converge_func": "collect_alarm"
            }
        }

        初始化流程说明：
        1. 基础属性初始化与实例加载
        2. 收敛配置合法性校验（启用状态/必要字段/数值范围）
        3. 时间窗口计算（基础时间范围与最大扩展范围）
        4. 收敛维度提取与安全长度限制

        """

        self.status = converge_context.get("status", "") if converge_context else ""
        self.comment = ""
        self.instance_type = instance_type
        self.shield_manager = ShieldManager()
        self.is_illegal = False
        self.converge_config = {}
        self.sleep_time = CONST_HALF_MINUTE
        self.instance_id = instance_id
        self.dimension = ""
        self.lock_key = ""
        self.need_unlock = False
        self.instance_model = self.InstanceModel[instance_type]
        self.instance = self.instance_model.objects.get(id=instance_id)
        self.alerts = alerts
        self.origin_converge_config = copy.deepcopy(converge_config)
        self.context = converge_context
        if self.context is None:
            self.get_converge_context()
        converge_config = self.set_converge_count_and_timedelta(converge_config) if converge_config else {}
        self.converge_config.update(converge_config)

        if converge_config.get("is_enabled", False) is False:
            # 不需要收敛的内容
            self.is_illegal = True
            return

        if self.is_parent_action() or not converge_config:
            # 如果没有收敛参数，表示不需要任何收敛
            # 如果收敛对象对虚拟的主响应动作，不做收敛
            # 如果没有开启告警防御，直接不做收敛处理
            self.is_illegal = True
            return

        if not converge_config.get("condition"):
            self.is_illegal = True
            self.converge_config.update({"description": "illegal converge_config"})
            logger.warning("$%s illegal converge_config %s", self.instance["id"], converge_config["condition"])
            return

        # check timedelta and count
        if converge_config["timedelta"] <= 0:
            self.converge_config.update({"description": "illegal converge_config, timedelta <= 0"})
            self.is_illegal = True
            logger.warning(
                "$%s illegal converge_config #%s: timedelta %s <= 0",
                instance_id,
                converge_config["id"],
                converge_config["timedelta"],
            )
            return

        self.converge_count = converge_config["count"]
        if self.converge_count < 0:
            self.converge_config.update({"description": "illegal converge_config, count < 0"})
            self.is_illegal = True
            logger.warning("$%s illegal converge_config : count %s <= 0", instance_id, self.converge_count)
            return

        # 将单位转换为分钟
        self.converge_timedelta = int(self.converge_config["timedelta"]) // CONST_MINUTES
        self.max_converge_timedelta = int(self.converge_config.get("max_timedelta") or 0) // CONST_MINUTES

        # 使用实例创建前的几分钟作为开始时间
        self.start_time = self.instance.create_time - timedelta(
            minutes=self.max_converge_timedelta or self.converge_timedelta
        )
        self.start_timestamp = int(self.start_time.timestamp())

        # 第一次进行收敛的时候，只计算可收敛条件，不用持续时间
        self.first_start_timestamp = int(
            (self.instance.create_time - timedelta(minutes=self.converge_timedelta)).timestamp()
        )

        # 添加一个收敛结束的时候，避免大范围内
        self.end_timestamp = int(
            (
                self.instance.create_time + timedelta(minutes=self.max_converge_timedelta or self.converge_timedelta)
            ).timestamp()
        )
        self.dimension = self.get_dimension(safe_length=128)

    def set_converge_count_and_timedelta(self, converge_config):
        """
        设置默认收敛策略配置参数
        修改dimension的值为notice_info或者actions_info，以便后续进行匹配

        参数:
            converge_config (dict): 收敛策略配置字典，包含以下可能字段：
                - timedelta (int): 时间窗口阈值（秒）
                - count (int): 触发次数阈值
                - condition (list): 收敛维度条件列表，每个元素包含：
                    * dimension (str): 维度名称
                    * value (list): 需要匹配的值列表

        返回值:
            dict: 更新后的收敛策略配置字典，包含完整的收敛参数配置

        该方法根据实例类型实现两种收敛策略配置：
        1. 动作类型实例(ConvergeType.ACTION)：
           - 通知类动作特殊处理：设置2分钟时间窗口，单次触发阈值
           - 自动补充缺失的收敛维度条件
        2. 收敛类型实例(ConvergeType.CONVERGE)：
           - 使用全局配置的多策略收集窗口和阈值
        """
        if self.instance_type == ConvergeType.ACTION:
            # 处理动作类型实例的收敛配置
            if self.instance.action_config["plugin_type"] == ActionPluginType.NOTICE:
                # 通知类动作特殊配置：
                # 1. 设置2分钟时间窗口（CONST_MINUTES*2）
                # 2. 单次触发阈值（count=1）
                # 3. 添加notice_info维度收敛条件（若存在上下文信息）
                converge_config["timedelta"] = CONST_MINUTES * 2
                converge_config["count"] = 1
                if self.context.get("notice_info"):
                    # 如果不存在notice_info维度信息，可能是老数据，保留原来的收敛维度
                    converge_config["condition"] = [{"dimension": "notice_info", "value": ["self"]}]

            elif not converge_config.get("condition"):
                # 对于没有指定收敛条件的其他动作类型：
                # 设置默认的action_info维度收敛条件
                converge_config["condition"] = [{"dimension": "action_info", "value": ["self"]}]

        if self.instance_type == ConvergeType.CONVERGE:
            # 处理收敛类型实例：
            # 使用全局配置的多策略收集窗口和阈值参数
            converge_config["timedelta"] = settings.MULTI_STRATEGY_COLLECT_WINDOW
            converge_config["count"] = settings.MULTI_STRATEGY_COLLECT_THRESHOLD

        return converge_config

    def get_converge_context(self):
        """
        根据实例对象获取到收敛上下文

        参数:
            self: 当前对象实例

        返回值:
            None: 上下文数据存储在self.context属性中
        """
        if self.instance_type == ConvergeType.ACTION:
            self.context = ActionContext(self.instance, [], alerts=self.alerts).converge_context.get_dict(
                ALL_CONVERGE_DIMENSION.keys()
            )
        else:
            self.context = self.instance.converge_config["converged_condition"]

    def is_parent_action(self):
        """
        判断当前实例是否为虚拟主任务

        参数:
            self: 当前对象实例

        返回值:
            bool: 是否为虚拟主任务
        """
        return self.instance_type == ConvergeType.ACTION and self.instance.is_parent_action

    def is_alert_shield(self):
        """
        检查当前告警是否被屏蔽

        参数:
            self: 当前对象实例

        返回值:
            tuple: (是否屏蔽, 屏蔽器实例)
                - bool: True表示存在屏蔽
                - Shielder: 匹配的屏蔽器实例或None
        """
        for alert in self.alerts:
            # 关联多告警的内容，只要有其中一个不满足条件，直接就屏蔽
            alert.strategy_id = alert.strategy_id
            shielder = AlertShieldConfigShielder(alert)
            if shielder.is_matched():
                return True, shielder

        return False, None

    def converge_alarm(self):
        """
        执行告警收敛主流程，包含异常处理和状态更新

        参数:
            self: 当前对象实例

        异常:
            ConvergeLockError: 获取并发锁失败时抛出
            ActionAlreadyFinishedError: 动作已结束异常
            StrategyNotFound: 策略未找到异常
        """
        try:
            # 主流程执行
            self.status = self.run_converge()
            self.comment = self.converge_config.get("description")
            # 收敛后队列处理
            self.push_to_queue()
        except ConvergeLockError as error:
            raise error
        except ActionAlreadyFinishedError as error:
            logger.info("run action converge(%s) failed: %s", self.instance_id, str(error))
            return
        except StrategyNotFound:
            # 策略异常处理逻辑
            logger.info(
                "run action converge(%s) skip: strategy(%s) not found", self.instance_id, self.instance.strategy_id
            )
            self.status = ActionStatus.SKIPPED
            self.comment = _("策略({}) 被删除或停用, 跳过.").format(
                self.instance.strategy_id,
            )
            self.push_to_queue()
            return
        # except BaseException:
        #     logger.exception(
        #         "run converge failed: [%s]",
        #         self.converge_config,
        #     )
        #     # 收敛失败的，则重新推入收敛队列, 1分钟之后再做收敛检测
        #     self.push_converge_queue()
        #     return
        finally:
            self.unlock()

    def lock(self):
        """
        获取并发锁，控制并行收敛数量

        参数:
            self: 当前对象实例

        异常:
            ConvergeLockError: 当并发数超过限制时抛出
        """
        client = ACTION_CONVERGE_KEY_PROCESS_LOCK.client
        parallel_converge_count = max(int(self.converge_count) // 2, 1)
        self.lock_key = ACTION_CONVERGE_KEY_PROCESS_LOCK.get_key(dimension=self.dimension)
        if client.incr(self.lock_key) > parallel_converge_count:
            # 如果当前的计数器大于并发数，直接返回异常
            client.decr(self.lock_key)
            ttl = client.ttl(self.lock_key)
            if ttl is None or ttl < 0:
                # 如果没有ttl的情况，很有可能是并发抢占，需要设置一下ttl, 避免长期占用
                client.expire(self.lock_key, ACTION_CONVERGE_KEY_PROCESS_LOCK.ttl)
            raise ConvergeLockError(
                f"get parallel converge failed, current_parallel_converge_count is {parallel_converge_count}, converge condition is {self.dimension}"
            )
        client.expire(self.lock_key, ACTION_CONVERGE_KEY_PROCESS_LOCK.ttl)
        # 当获取到锁的情况下才需要去解锁
        self.need_unlock = True

    def unlock(self):
        """
        释放已获取的并发锁

        参数:
            self: 当前对象实例
        """
        if self.need_unlock is False:
            return
        client = ACTION_CONVERGE_KEY_PROCESS_LOCK.client
        if int(client.get(self.lock_key) or 0) > 0:
            # 当前key没有过期的时候，需要进行递减
            client.decr(self.lock_key)

    def run_converge(self):
        """
        执行收敛处理的核心流程控制方法

        参数:
            self: 包含以下关键属性的对象实例
                - instance_type: 收敛类型(ConvergeType.ACTION/CONVERGE)
                - instance: 收敛实例对象，包含状态(status)、执行次数(execute_times)等属性
                - converge_config: 收敛配置字典，包含收敛方法(converge_func)等配置项
                - dimension: 收敛维度标识
                - start_time: 收敛开始时间戳
                - end_timestamp: 收敛结束时间戳
                - alerts: 关联告警列表
                - shield_manager: 屏蔽管理器实例
                - is_illegal: 布尔值表示是否非法收敛状态

        返回值:
            ActionStatus.SKIPPED: 表示任务被跳过
            ActionStatus.SHIELD: 表示任务被屏蔽
            False: 表示无需进行收敛
            其他情况返回收敛执行结果状态

        抛出异常:
            ActionAlreadyFinishedError: 当检测到已结束的收敛实例时抛出

        该方法实现完整的收敛处理流程，包含：
        1. 屏蔽状态优先级校验
        2. 任务状态有效性验证
        3. 分布式锁获取控制
        4. 收敛逻辑执行调度
        5. 执行结果状态处理
        6. 收敛日志记录
        """
        # 告警屏蔽优先级最高，如果屏蔽了，则都不需要处理，直接不做收敛
        if self.instance_type == ConvergeType.ACTION:
            if self.instance.status in ActionStatus.END_STATUS:
                # 已经结束不再进行收敛防御
                raise ActionAlreadyFinishedError({"action_id": self.instance_id, "action_status": self.instance.status})

            if self.instance.status == ActionStatus.SLEEP and self.is_sleep_timeout():
                # 超时的任务直接忽略收敛
                return ActionStatus.SKIPPED
            if self.instance.is_parent_action is False:
                # 收敛的时候，非主任务需要判断当前的Action是否是屏蔽状态的
                is_shielded, shielder = self.shield_manager.shield(self.instance, self.alerts)
                if is_shielded:
                    # 如果告警是处理屏蔽状态的，直接忽略
                    logger.info(f"action({self.instance_id}) shielded")
                    self.converge_config["description"] = "Stop to converge because of shielded"
                    shield_detail = extended_json.loads(shielder.detail)
                    self.instance.outputs = {"shield": {"type": shielder.type, "detail": shield_detail}}
                    self.instance.ex_data = shield_detail
                    # 屏蔽的时候，将不会执行，所以此处执行次数默认加1
                    self.instance.execute_times += 1
                    self.instance.insert_alert_log(
                        description=_("套餐处理【{}】已屏蔽， 屏蔽原因：{}").format(
                            self.instance.name, shield_detail.get("message", "others")
                        )
                    )
                    return ActionStatus.SHIELD

        if self.instance_type == ConvergeType.CONVERGE and self.instance.end_time:
            # 如果为二级收敛并且结束，直接抛出完成的异常
            raise ActionAlreadyFinishedError(
                {
                    "action_id": f"{self.instance_id}-{self.instance_type}",
                    "action_status": ActionStatus.SUCCESS,
                }
            )

        if self.is_illegal:
            # 不需要收敛的直接返回
            return False

        converge_manager = ConvergeManager(
            self.converge_config,
            self.dimension,
            self.start_time,
            self.instance,
            self.instance_type,
            end_timestamp=self.end_timestamp,
            alerts=self.alerts,
        )

        converged_instance = converge_manager.converge_instance
        if self.need_get_lock(converged_instance):
            # 当没有生成收敛记录的时候，才进行分布式锁控制
            # 当前生成了收敛记录，但是关联数量不够的情况下， 也需要进行加锁控制
            self.get_dimension_lock()

        if converge_manager.do_converge() is False:
            return False

        converge_instance = converge_manager.converge_instance

        converge_func = ConvergeFunc(
            self.instance,
            converge_manager.match_action_id_list,
            converge_manager.is_created,
            converge_instance,
            self.converge_config,
            converge_manager.biz_converge_existed,
        )
        converge_method = getattr(converge_func, self.converge_config["converge_func"])
        self.status = False if converge_method is None else converge_method()
        converge_manager.connect_converge(status=self.status)
        if self.status == ActionStatus.SKIPPED and self.instance_type == ConvergeType.ACTION:
            # 忽略的时候，需要在日志中插入记录
            action_name = ActionConfigCacheManager.get_action_config_by_id(self.instance.action_config_id).get("name")
            # 忽略的时候，将不会执行，所以此处执行次数默认加1
            self.instance.execute_times += 1
            self.instance.insert_alert_log(
                description=_("套餐【{}】已收敛， 收敛原因：{}").format(action_name, converge_instance.description)
            )
        return self.status

    def get_dimension_lock(self):
        """
        获取收敛维度锁

        异常:
            ConvergeLockError: 当获取锁失败时抛出异常
        """
        try:
            self.lock()
        except ConvergeLockError as error:
            # 获取锁错误的时候，进入收敛等待队列
            self.sleep_time = CONST_SECOND * 3
            self.push_converge_queue()
            raise error

    def need_get_lock(self, conv_inst: ConvergeInstance = None):
        """
        判断是否需要获取收敛锁

        参数:
            conv_inst (ConvergeInstance): 收敛实例对象，默认为None

        返回:
            bool: 是否需要获取锁
        """
        if conv_inst is None:
            # 不存在converge_inst的时候，
            return True

        if self.instance_type == ConvergeType.CONVERGE or self.converge_count <= 1:
            # 已经业务汇总并产生了收敛实例， 不需要
            # 当前收敛个数为1,已经产生了，一定不需要
            return False

        if get_execute_related_ids(conv_inst.id, self.instance_type).count() < self.converge_count:
            return True

    def is_sleep_timeout(self):
        """
        检查睡眠状态是否超时

        返回:
            bool: 当前实例是否处于超时状态
        """
        if self.instance_type != ConvergeType.ACTION:
            return False

        execute_config = self.instance.action_config["execute_config"]
        max_timeout = max(int(execute_config["timeout"]), self.max_converge_timedelta * 60)
        if int(self.instance.create_time.timestamp()) + max_timeout < int(datetime.now().timestamp()):
            # 如果创建时间已经超过了处理的超时时间，则忽略不处理
            return True
        return False

    def get_dimension_value(self, value):
        """
        获取指定维度的哈希值

        参数:
            value (any): 维度原始值，支持列表或其他类型

        返回:
            str: 处理后的维度字符串

        注：当value为列表且长度>=4时，执行特殊压缩处理逻辑
        """
        if isinstance(value, list):
            if len(value) >= 4:
                h = hashlib.md5(value).hexdigest()[:5]
                value = [value[0], f"{h}.{len(value) - 2}", value[-1]]
            dimension_value = ",".join(map(str, value))
        else:
            dimension_value = value
        return dimension_value

    def get_dimension(self, safe_length=0):
        """
        通过收敛条件中配置的收敛规则获取到维度信息

        参数:
            safe_length (int): 返回维度字符串的安全长度限制，默认为0

        返回:
            str: 经过SHA1哈希处理的维度字符串，按safe_length截断

        注：该方法主要处理以下核心逻辑：
            1. 合并原始和当前收敛配置的维度条件
            2. 替换维度值中的'self'为上下文实际值
            3. 生成SHA1哈希标识的维度字符串
        """
        converge_dimension = ["#{}".format(self.converge_config["converge_func"])]
        self.converge_config["converged_condition"] = {}
        dimension_conditions = {
            condition["dimension"]: condition for condition in self.converge_config.get("condition")
        }
        # 合并原始配置和当前配置的维度条件，并保持有序排列
        dimension_conditions.update(
            {condition["dimension"]: condition for condition in self.origin_converge_config.get("condition", [])}
        )
        dimension_conditions = collections.OrderedDict(sorted(dimension_conditions.items()))

        # 遍历所有维度条件，执行以下操作：
        # 1. 替换'self'为上下文实际值
        # 2. 生成维度键值对
        # 3. 存储收敛配置的维度条件
        for dimension_condition in dimension_conditions.values():
            # replace "self" to real value
            key = dimension_condition["dimension"]
            values = deepcopy(dimension_condition["value"])
            for index, value in enumerate(values):
                if value == "self":
                    values[index] = self.context.get(key, "")
                converge_dimension.append(f"|{key}:{self.get_dimension_value(values[index])}")
            self.converge_config["converged_condition"][key] = [
                value[0] if isinstance(value, list) else value for value in values
            ]
        dimension = "".join(converge_dimension)
        sha1 = hashlib.sha1(dimension.encode("utf-8"))
        dimension = f"!sha1#{sha1.hexdigest()}"
        return dimension[:safe_length]

    def push_to_queue(self):
        """
        更新实例状态并根据状态类型推送到对应处理队列

        参数:
            self: 包含以下属性的对象实例
                - status: 当前动作状态（ActionStatus枚举）
                - instance: 动作实例对象（ActionInstance类型）
                - comment: 状态更新附带信息（字符串）
                - ex_data: 扩展数据字段
                - execute_times: 执行次数计数器

        返回值:
            None: 当处理动作处于结束状态时直接返回
            其他情况通过队列推送继续处理流程

        执行流程说明：
        1. 根据状态确定结束时间
        2. 更新ActionInstance对象的状态和元数据
        3. 根据状态类型决定推送至收敛队列或动作队列
        """
        end_time = datetime.now(tz=timezone.utc) if self.status in ActionStatus.END_STATUS else None

        # 处理ActionInstance状态更新逻辑
        if isinstance(self.instance, ActionInstance):
            # 更新实例核心状态字段
            self.instance.status = self.status if self.status else ActionStatus.CONVERGED
            self.instance.outputs = {"message": self.comment}
            self.instance.end_time = end_time
            self.instance.update_time = end_time

            # 特殊状态处理：需要轮询检测
            if end_time:
                self.instance.need_poll = need_poll(self.instance)

            # 持久化存储状态变更
            self.instance.save(
                update_fields=["outputs", "status", "end_time", "update_time", "need_poll", "ex_data", "execute_times"]
            )

            # 提前终止处理：已到达结束状态
            if self.instance.status in ActionStatus.END_STATUS:
                return

        # 等待状态处理：重新推入收敛队列
        if self.status == ActionStatus.SLEEP:
            # 收敛队列重推逻辑：1分钟后再次检测
            self.push_converge_queue()
        else:
            # 常规动作处理：推入动作执行队列
            self.push_to_action_queue()

    def push_to_action_queue(self):
        """
        将告警事件推送到动作执行队列

        参数:
            self: 包含以下属性的对象实例
                - instance_type: 实例类型（ConvergeType）
                - instance_id: 实例唯一标识
                - status: 当前动作状态（ActionStatus）
                - alerts: 告警信息集合
                - context: 上下文信息
                - instance: 动作实例对象
                - alerts: 告警数据

        返回值:
            None: 直接返回，通过消息队列异步处理

        注：该方法主要处理以下核心逻辑：
            1. 根据插件类型选择不同的执行策略
            2. 构建任务参数并提交到消息队列
            3. 记录推送指标数据
        """
        logger.info("converge: ready to push to action queue %s instance id %s", self.instance_type, self.instance_id)
        if self.instance_type != ConvergeType.ACTION:
            # 非动作类的事件，仅仅是为了做收敛，不做具体的事件处理
            return

        if self.status in [ActionStatus.SKIPPED, ActionStatus.SHIELD]:
            # 为忽略状态的任务表示收敛不处理，不需要推送至队列
            return

        plugin_type = self.instance.action_plugin["plugin_type"]
        action_info = {
            "id": self.instance_id,
            "function": "create_approve_ticket" if self.status == ActionStatus.WAITING else "execute",
            "alerts": self.alerts,
        }
        collect_key = ""
        countdown = 0
        if plugin_type == ActionPluginType.NOTICE and self.instance.is_parent_action is False:
            # 通知子任务需要记录通知方式，触发信号，告警ID进行后续的汇总合并
            client = FTA_NOTICE_COLLECT_KEY.client
            collect_key = FTA_NOTICE_COLLECT_KEY.get_key(
                **{
                    "notice_way": self.context["group_notice_way"],
                    "action_signal": self.instance.signal,
                    "alert_id": "_".join([str(a) for a in self.instance.alerts]),
                }
            )
            # 设置key
            client.hset(collect_key, self.context["notice_receiver"], self.instance_id)
            client.expire(collect_key, FTA_NOTICE_COLLECT_KEY.ttl)
            countdown = 1
        task_id = dispatch_action_task(plugin_type, action_info, countdown=countdown)
        logger.info(
            "$ %s push fta action %s %s to rabbitmq, alerts %s, collect_key %s",
            task_id,
            self.instance_id,
            plugin_type,
            self.instance.alerts,
            collect_key,
        )
        metrics.CONVERGE_PUSH_ACTION_COUNT.labels(
            bk_biz_id=self.instance.bk_biz_id,
            plugin_type=plugin_type,
            strategy_id=metrics.TOTAL_TAG,
            signal=self.instance.signal,
        ).inc()

    def push_converge_queue(self):
        """
        将收敛实例重新推送到收敛队列

        参数:
            self: 包含以下属性的对象实例
                - origin_converge_config: 原始收敛配置
                - instance_id: 实例唯一标识
                - instance_type: 实例类型（ConvergeType）
                - context: 上下文信息
                - alerts: 告警数据
                - sleep_time: 等待时间间隔

        返回值:
            None: 直接返回，通过异步任务处理

        注：该方法主要执行以下核心逻辑：
            1. 构建异步任务参数
            2. 提交收敛任务到消息队列
            3. 记录推送指标数据
        """
        # 如果还在等待中的收敛，则重新推入收敛队列, 1分钟之后再做收敛检测
        from alarm_backends.service.converge.tasks import run_converge

        task_id = run_converge.apply_async(
            (self.origin_converge_config, self.instance_id, self.instance_type, self.context, self.alerts),
            countdown=self.sleep_time,
        )

        logger.info(
            "push %s(%s) to converge queue again, delay %s, task_id(%s)",
            self.instance_type,
            self.instance_id,
            self.sleep_time,
            task_id,
        )
        metrics.CONVERGE_PUSH_CONVERGE_COUNT.labels(
            bk_biz_id=self.instance.bk_biz_id, instance_type=self.instance_type
        ).inc()
