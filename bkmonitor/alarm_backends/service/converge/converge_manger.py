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
import random
import time
from datetime import datetime, timezone
from typing import Literal

from django.utils.translation import gettext as _

from alarm_backends.core.cache.key import FTA_SUB_CONVERGE_DIMENSION_LOCK_KEY
from alarm_backends.service.converge.dimension import (
    DimensionCalculator,
    DimensionHandler,
)
from alarm_backends.service.converge.tasks import run_converge
from alarm_backends.service.converge.utils import list_other_converged_instances
from bkmonitor.models.fta.action import (
    ActionInstance,
    ConvergeInstance,
    ConvergeRelation,
)
from constants.action import (
    ALL_CONVERGE_DIMENSION,
    ActionStatus,
    ConvergeStatus,
    ConvergeType,
)

logger = logging.getLogger("fta_action.converge")


class ConvergeManager:
    def __init__(
        self,
        converge_config,
        dimension,
        start_time,
        instance: ActionInstance | ConvergeInstance,
        instance_type: Literal["action", "converge"] = ConvergeType.ACTION,
        end_timestamp=None,
        alerts=None,
    ):
        """
        收敛管理器初始化

        参数:
            converge_config: 收敛配置字典，包含收敛规则和条件
            dimension: 收敛维度标识，用于区分不同收敛场景
            start_time: 收敛计算起始时间（datetime对象）
            instance: 关联实例对象（告警/事件）
            instance_type: 实例类型枚举，默认为ACTION类型
            end_timestamp: 收敛结束时间戳（可选）
            alerts: 告警列表数据（可选）

        初始化流程说明:
        1. 基础属性赋值
        2. 收敛实例获取与时间戳校准
        3. 收敛条件解析与维度处理器初始化
        """
        self.alerts = alerts
        self.converge_config = converge_config
        self.instance_type = instance_type
        self.instance = instance
        self.dimension = dimension
        self.is_created = False  # 收敛实例是否创建
        self.start_time = start_time
        self.end_timestamp = end_timestamp
        self.match_action_id_list = []
        self.converge_instance = self.get_converge_instance(start_time)
        self.start_timestamp = int(self.start_time.timestamp())
        self.biz_converge_existed = False

        if self.converge_instance:
            # 校准创建时间戳：若起始时间早于收敛实例创建时间
            create_timestamp = int(self.converge_instance.create_time.timestamp())
            if self.start_timestamp < create_timestamp:
                self.start_timestamp = self.start_timestamp

        # 解析收敛条件中的维度配置
        converged_condition = {
            condition_item["dimension"]: self.converge_config["converged_condition"].get(condition_item["dimension"])
            for condition_item in self.converge_config["condition"]
        }

        # 初始化维度处理器，用于处理维度相关的匹配逻辑
        self.dimension_handler = DimensionHandler(
            self.dimension,
            converged_condition,
            self.start_timestamp,
            instance_id=self.instance.id,
            end_timestamp=self.end_timestamp,
            instance_type=self.instance_type,
            strategy_id=getattr(self.instanec, "strategy_id", 0),
            converged_condition=self.converge_config["converged_condition"],
        )

    def do_converge(self):
        """
        执行收敛计算的核心方法

        返回值:
            bool: 收敛处理结果状态
                True表示已处理/无需处理
                False表示处理失败或不满足条件

        处理流程:
        1. 检查现有收敛实例，存在返回True
        2. 获取匹配的告警ID列表
        3. 创建新收敛实例（如满足条件）
        4. 子收敛队列处理（如配置启用）
        """
        if self.converge_instance:
            # 已存在同维度收敛实例，跳过处理
            logger.info(
                "%s|converge(%s) skipped because converge(%s) dimension existed already",
                self.instance_type,
                self.instance.id,
                self.converge_instance.id,
            )
            return True

        # 获取关联的动作实例ID列表
        self.match_action_id_list = self.get_related_ids()
        matched_count = len(self.match_action_id_list)

        # 假设设置的count=5
        # 第一次进行故障自愈，创建了一次，此时matched_count=1。由于没有到达count的要求直接返回False,也就是不进行收敛。
        # 后面也就不会进行收敛函数进行判断。
        # 当到第五次执行后，满足match_count=5，后面才会对收敛函数进行判断，比如“成功后跳过”
        if not self.converge_instance and matched_count >= int(self.converge_config["count"]):
            # 创建新收敛实例：满足数量阈值且不存在现有实例
            logger.info("[create_converge_instance] begin to create converge by %s", self.instance.id)
            try:
                self.create_converge_instance(self.start_time)
            except Exception as error:
                logger.exception(
                    "[create_converge_instance] create converge by instance(%s) failed：%s", self.instance.id, error
                )
                return False

            logger.info(
                "[create_converge_instance] end create converge(%s) by %s ", self.converge_instance.id, self.instance.id
            )

        if not self.converge_instance or matched_count == 0:
            # 无匹配告警或未创建实例，终止处理
            logger.info("$%s no matched_count , return!!", self.instance.id)
            return False

        if (
            self.is_created
            and self.converge_config.get("sub_converge_config")
            and self.converge_config.get("need_biz_converge")
        ):
            # 触发二级收敛处理：需满足三个条件
            # 1. 当前实例已创建
            # 2. 存在子收敛配置
            # 3. 需要业务收敛
            self.push_to_sub_converge_queue()

        return True

    def push_to_sub_converge_queue(self):
        """
        推送二级收敛至收敛队列
        """

        sub_converge_config = self.converge_config.get("sub_converge_config", {})
        sub_converge_config["is_enabled"] = True  # 需要二级收敛的，默认都设置is_enabled为True
        if self.is_biz_converge_existed(sub_converge_config["count"]):
            # 当前已经达到了业务汇总的条件，当前的告警不发出
            self.biz_converge_existed = True

        sub_converge_info = DimensionCalculator(
            self.converge_instance,
            ConvergeType.CONVERGE,
            converge_config=sub_converge_config,
        ).calc_sub_converge_dimension()
        task_id = run_converge.delay(
            sub_converge_config,
            self.converge_instance.id,
            ConvergeType.CONVERGE,
            sub_converge_info["converge_context"],
            alerts=self.alerts,
        )
        logger.info("push converge(%s) to converge queue, task id %s", self.converge_instance.id, task_id)

    def is_biz_converge_existed(self, matched_count):
        client = FTA_SUB_CONVERGE_DIMENSION_LOCK_KEY.client

        # 去除策略ID避免存储被路由到不同的redis
        key_params = self.dimension_handler.get_sub_converge_label_info()
        key_params.pop("strategy_id", None)

        biz_converge_lock_key = FTA_SUB_CONVERGE_DIMENSION_LOCK_KEY.get_key(**key_params)
        if client.incr(biz_converge_lock_key) > matched_count:
            # 如果当前的计数器大于并发数，直接返回异常
            logger.info(
                "action(%s|%s) will be skipped because count of biz_converge_lock_key(%s) is bigger than %s, ",
                self.instance.id,
                self.converge_instance.id,
                biz_converge_lock_key,
                matched_count,
            )
            return True
        client.expire(biz_converge_lock_key, FTA_SUB_CONVERGE_DIMENSION_LOCK_KEY.ttl)
        return False

    def get_related_ids(self):
        """
        获取当前收敛对象关联的未收敛处理动作ID列表

        参数:
            self: Converge实例对象，包含以下属性
                - dimension_handler: 维度过滤器对象，提供get_by_condition方法
                - instance_type: 当前实例类型标识符
                - converge_instance: 当前收敛主对象实例（可选）
                - dimension: 当前处理的维度信息

        返回值:
            list: 包含符合当前收敛条件的未处理动作ID列表，元素类型为整数

        执行流程说明：
        1. 通过维度过滤器获取原始匹配ID集合
        2. 过滤并提取符合当前实例类型的数字ID
        3. 查询已存在的收敛关联关系
        4. 排除当前实例已存在的关联
        5. 计算未收敛的ID集合并返回
        """

        matched_related_ids = self.dimension_handler.get_by_condition()

        # 过滤原始ID集合，仅保留符合当前实例类型且提取纯数字ID
        matched_related_ids = [
            int(related_id.split("_")[-1]) for related_id in matched_related_ids if self.instance_type in related_id
        ]

        if not matched_related_ids:
            return []

        # 查询已存在的收敛关联关系
        converge_relations = ConvergeRelation.objects.filter(
            related_id__in=matched_related_ids, related_type=self.instance_type
        )
        if self.converge_instance:
            # 排除当前实例已存在的关联关系，防止自我关联
            converge_relations = converge_relations.exclude(converge_id=self.converge_instance.id)

        # 提取已收敛的related_id集合
        converged_related_ids = converge_relations.values_list("related_id", flat=True)

        # 计算未收敛的ID集合（原始匹配ID - 已收敛ID）
        matched_related_ids = list(set(matched_related_ids) - set(converged_related_ids))
        logger.info(
            "$%s:%s dimension alarm list: %s, %s",
            self.instance.id,
            self.instance_type,
            self.dimension,
            len(matched_related_ids),
        )
        return matched_related_ids

    def create_converge_instance(self, start_time=None):
        self.insert_converge_instance()
        if start_time and self.converge_instance.create_time < start_time:
            logger.info(
                "converge(%s) end by start_time (%s < %s)",
                self.converge_instance.id,
                self.converge_instance.create_time,
                start_time,
            )
            self.end_converge_by_id(self.converge_instance.id)

        return self.converge_instance

    @classmethod
    def get_fixed_dimension(cls, dimension):
        return f"{dimension} fixed at {int(datetime.now().timestamp())} {random.randint(100, 999)}"

    @classmethod
    def end_converge_by_id(cls, converge_id, conv_instance=None):
        """
        终止指定ID的收敛实例及其关联的多级收敛实例

        参数:
            converge_id: 收敛实例的唯一标识符（数据库主键）
            conv_instance: 可选的ConvergeInstance实例，若未提供则自动查询数据库获取

        返回值:
            None: 该方法通过副作用修改数据库记录，不返回具体值

        该方法实现完整的收敛终止流程，包含以下核心步骤：
        1. 日志记录当前操作的收敛ID
        2. 惰性加载收敛实例（首次访问时从数据库获取）
        3. 更新终止时间并修正维度字段（仅当实例存在且未终止时）
        4. 递归终止多级收敛关联的所有子实例
        5. 最终记录终止完成日志
        """
        logger.info("conv_instance end by id %s", converge_id)
        if conv_instance is None:
            # 从数据库获取收敛实例（惰性加载模式）
            conv_instance = ConvergeInstance.objects.get(id=converge_id)
        if conv_instance and not conv_instance.end_time:
            # 持久化终止时间和修正后的维度信息
            conv_instance.end_time = datetime.now(tz=timezone.utc)
            conv_instance.dimension = cls.get_fixed_dimension(conv_instance.dimension)
            conv_instance.save(update_fields=["end_time", "dimension"])
        if conv_instance.converge_type == ConvergeType.CONVERGE:
            # 处理多级收敛终止逻辑（递归关闭关联收敛实例）
            for conv_id in ConvergeRelation.objects.filter(converge_id=converge_id).values_list(
                "related_id", flat=True
            ):
                cls.end_converge_by_id(conv_id)
        logger.info("converge(%s) already end at %s", converge_id, conv_instance.end_time)

    def insert_converge_instance(self):
        """
        插入告警收敛实例并生成业务描述信息

        参数:
            self: 包含以下实例属性
                - converge_config: 收敛配置字典，包含收敛规则参数
                - instance: 告警实例对象，包含业务ID等信息
                - dimension: 收敛维度标识字符串
                - instance_type: 收敛实例类型标识
                - is_created: 布尔值，表示实例创建状态标志
                - converge_instance: 收敛实例对象存储位置

        返回值:
            None: 通过修改self.converge_instance和self.is_created返回结果
                - 成功时创建新的ConvergeInstance对象并标记is_created=True
                - 失败时记录错误日志并尝试获取已有实例，标记is_created=False

        执行流程:
        1. 解析收敛维度配置，过滤action_id字段
        2. 生成国际化告警描述文本
        3. 创建数据库记录并维护状态标志
        4. 异常处理机制保障实例最终可达
        """
        try:
            # 收集非action_id维度的收敛条件显示名称
            converged_condition_display = []
            for converged_condition_key in self.converge_config["converged_condition"]:
                if converged_condition_key == "action_id":
                    continue
                converged_condition_display.append(
                    str(ALL_CONVERGE_DIMENSION.get(converged_condition_key, converged_condition_key))
                )

            # 生成带业务语义的告警描述文本（时间间隔转换为分钟）
            description = _("在{}分钟内，当具有相同{}的告警超过{}条以上，在执行相同的处理套餐时，进行告警防御").format(
                self.converge_config["timedelta"] // 60,
                ",".join(converged_condition_display),
                self.converge_config["count"],
            )

            # 创建收敛实例数据库记录
            self.converge_instance = ConvergeInstance.objects.create(
                converge_config=self.converge_config,
                bk_biz_id=self.instance.bk_biz_id,
                dimension=self.dimension,
                description=description,
                content=self.converge_config.get("context", "{}"),
                end_time=None,
                converge_func=self.converge_config["converge_func"],
                converge_type=self.instance_type,
                is_visible=True,
            )
        except BaseException as error:
            # 记录创建失败日志，尝试获取已有实例并标记创建状态
            logger.error("[create converge] insert_converge_instance error %s", str(error))
            self.is_created = False
            self.converge_instance = self.get_converge_instance()

        else:
            # 成功创建时更新状态标志
            self.is_created = True

    def get_converge_instance(self, start_time=None):
        """
        获取与当前维度匹配的最新收敛实例，并处理过期实例清理逻辑

        参数:
            start_time: datetime.datetime类型，用于判断收敛实例是否过期的时间阈值
                        当实例创建时间早于该时间时将被强制终止

        返回值:
            ConvergeInstance实例对象或None：
            - 成功获取有效实例时返回实例对象
            - 无有效实例或实例过期时返回None

        该方法实现收敛实例的生命周期管理流程：
        1. 从数据库查询最新收敛实例
        2. 异常安全处理数据库访问
        3. 过期实例自动清理机制
        4. 实例状态本地缓存更新
        """
        try:
            # 尝试从数据库获取最新收敛实例
            converge_instance = ConvergeInstance.objects.filter(dimension=self.dimension).first()
        except Exception:
            # 数据库访问异常时安全降级
            converge_instance = None

        # start_time 是基于实例创建时间和收敛配置的时间窗口计算得出的最早有效时间
        # 而action先创建，然后才有converge，所以理论上converge的创建时间一定大于start_time
        # 所以如果start_time大于converge的创建时间，说明该实例已经过期
        if converge_instance and start_time and converge_instance.create_time < start_time:
            # 检测到过期收敛实例，记录日志并终止该实例
            logger.info(
                "[do_converge] converge(%s) end by start_time (%s < %s)",
                converge_instance.id,
                converge_instance.create_time,
                start_time,
            )
            self.end_converge_by_id(converge_instance.id)
            converge_instance = None

        # 更新本地缓存并返回结果
        self.converge_instance = converge_instance
        return self.converge_instance

    def connect_converge(self, status: str | bool = ConvergeStatus.SKIPPED):
        """
        关联告警实例到收敛实例并处理相关状态更新

        参数:
            status: ConvergeStatus枚举类型，表示当前收敛状态，默认为SKIPPED
                    在非主实例关联时作为备选状态使用

        返回值:
            None: 当关联关系创建失败时返回（可能已存在关联）
            异常情况下通过logger记录错误信息但不抛出异常

        执行流程包含以下核心步骤：
        1. 创建收敛关联记录（主实例标记为EXECUTED，其他为SKIPPED）
        2. 处理其他关联实例的统计恢复逻辑
        3. 更新收敛实例可见性状态
        4. 同步更新收敛实例描述信息
        """
        try:
            # 判断当前实例是否为主要实例：如果是新创建的收敛实例则为主要实例，否则为关联实例
            is_primary = True if self.is_created else False
            if is_primary:
                converge_status = ConvergeStatus.EXECUTED
            else:
                # 非主实例根据传入状态或默认策略确定状态
                converge_status = ConvergeStatus.SKIPPED if status else ConvergeStatus.EXECUTED

            # 创建收敛关联记录
            # 包含关联ID、收敛ID、实例类型、主实例标识、状态及关联告警列表
            ConvergeRelation.objects.create(
                related_id=self.instance.id,
                converge_id=self.converge_instance.id,
                related_type=self.instance_type,
                is_primary=is_primary,
                converge_status=converge_status,
                alerts=getattr(self.instance, "alerts", []),
            )
        except BaseException as error:
            # 关联失败处理（已存在关联记录的情况）
            # 记录日志用于监控重复关联尝试
            logger.info("create converge relation record failed %s, is_created: %s", str(error), self.is_created)
            return

        # 统计恢复逻辑处理
        # 仅当当前实例为已创建状态且存在匹配告警ID列表时执行
        if self.is_created and self.match_action_id_list:
            # 获取其他已收敛实例集合
            other_converged_instances = list_other_converged_instances(
                self.match_action_id_list, self.instance, self.instance_type
            )

            # 针对动作实例的特殊过滤处理
            if self.instance_type == ConvergeType.ACTION:
                other_converged_instances = (
                    ActionInstance.objects.filter(id__in=self.match_action_id_list)
                    .exclude(status__in=[ActionStatus.RECEIVED, ActionStatus.SLEEP, ActionStatus.WAITING])
                    .exclude(id=self.instance.id)
                )

            # 建立二级关联关系
            if other_converged_instances.exists():
                ConvergeRelationManager.connect(
                    self.converge_instance.id,
                    set(other_converged_instances.values_list("id", flat=True)),
                    self.instance_type,
                    self.instance.id,
                    converge_status=ConvergeStatus.SKIPPED
                    if self.instance_type == ConvergeType.CONVERGE
                    else ConvergeStatus.EXECUTED,
                )
                # 二级收敛时抑制一级收敛显示
                if self.instance_type == ConvergeType.CONVERGE:
                    other_converged_instances.update(is_visible=False)

        # 收敛实例可见性更新
        # 主收敛实例强制设置为不可见
        if self.instance_type == ConvergeType.CONVERGE:
            self.instance.is_visible = False
            self.instance.save(update_fields=["is_visible"])

        # 描述信息同步逻辑
        # 仅当存在新描述且与现有描述不同时执行更新
        description = self.converge_config.get("description")
        if not description or description == self.converge_instance.description:
            return

        # 更新收敛实例描述字段
        ConvergeInstance.objects.filter(id=self.converge_instance.id).update(description=description)


class ConvergeRelationManager:
    @staticmethod
    def count(converge_id):
        return ConvergeRelation.objects.filter_by(converge_id=converge_id).count()

    @staticmethod
    def index(converge_id, relate_id):
        related_ids = list(ConvergeRelation.objects.filter(converge_id=converge_id).values_list("relate_id", flat=True))
        return related_ids.index(relate_id)

    @staticmethod
    def connect(converge_id, related_ids, related_type, instance_id, converge_status=ConvergeStatus.SKIPPED):
        """关联收敛关系"""
        try:
            ConvergeRelationManager._connect(converge_id, related_ids, related_type, instance_id, converge_status)
        except BaseException:
            time.sleep(random.randint(1, 100) / 100.0)
            ConvergeRelationManager._connect(converge_id, related_ids, related_type, instance_id, converge_status)

    @staticmethod
    def _connect(
        converge_id,
        related_ids,
        related_type=ConvergeType.ACTION,
        instance_id=None,
        converge_status=ConvergeStatus.SKIPPED,
    ):
        """
        因为必定有很多重复记录，需要使用mysql IGNORE特性
        """
        converge_relations = [
            ConvergeRelation(
                converge_id=converge_id,
                related_id=related_id,
                related_type=related_type,
                converge_status=converge_status,
            )
            for related_id in related_ids
        ]
        ConvergeRelation.objects.ignore_blur_create(converge_relations)

        logger.info("converge(%s) connect: instance_id(%s) len(%s)", converge_id, instance_id, len(related_ids))
