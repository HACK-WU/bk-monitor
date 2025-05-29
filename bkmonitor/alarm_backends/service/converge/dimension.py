"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import json
import logging

import arrow

from alarm_backends.constants import CONST_MINUTES
from alarm_backends.core.cache.key import (
    FTA_CONVERGE_DIMENSION_KEY,
    FTA_SUB_CONVERGE_DIMENSION_KEY,
    KEY_PREFIX,
)
from alarm_backends.core.context import ActionContext
from constants.action import (
    ALL_CONVERGE_DIMENSION,
    COMPARED_CONVERGE_DIMENSION,
    SUB_CONVERGE_DIMENSION,
    ConvergeType,
)

logger = logging.getLogger("fta_action.converge")


class DimensionHandler:
    def __init__(
        self,
        dimension,
        condition,
        start_timestamp,
        instance_id,
        end_timestamp=None,
        instance_type=ConvergeType.ACTION,
        strategy_id=0,
        converged_condition=None,
    ):
        """
        :param dimension: the result key for redis
        :param condition: dict {"dimension_key": ["dimension_value", ]}
        :param start_timestamp: start time's timestamp
        """
        self.dimension = dimension
        self.condition = condition
        self.strategy_id = strategy_id
        self.start_timestamp = start_timestamp
        self.end_timestamp = end_timestamp or arrow.utcnow().timestamp
        self.instance_id = instance_id
        self.instance_type = instance_type
        self.converged_condition = converged_condition
        logger.info("$%s condition %s", self.instance_id, json.dumps(self.condition))

    def get_by_condition(self):
        """
        :return related_id_list: actions(matched condition) event_id_list
        """

        keys_length = {}
        if self.instance_type == ConvergeType.CONVERGE:
            # 如果是二级收敛，获取方法不一致
            keys_length, pipeline_results = self.get_sub_converge_instances()
        else:
            pipeline = FTA_CONVERGE_DIMENSION_KEY.client.pipeline()
            for key, values in self.condition.items():
                set_keys = self.get_set_keys(key, values)
                keys_length[key] = len(set_keys)
                for set_key in set_keys:
                    # 获取并集
                    pipeline.zrangebyscore(set_key, self.start_timestamp, self.end_timestamp, withscores=True)
            pipeline_results = pipeline.execute()
        return self.calc_converge_results(keys_length, pipeline_results)

    def calc_converge_results(self, keys_length, converge_results):
        index = 0
        all_key_results = []
        for length in keys_length.values():
            all_key_results.append(converge_results[index : index + length])
            index += 1

        if not all_key_results:
            return []

        union_results = []
        for key_results in all_key_results:
            single_key_union_results = []
            for results in key_results:
                single_key_union_results.extend([item[0] for item in results])
            union_results.append(set(single_key_union_results))
        result_list = union_results[0].intersection(*union_results[1:])

        logger.info(
            "$%s dimension_key %s len:%s filter:%s-%s",
            self.instance_id,
            self.dimension,
            len(result_list),
            self.start_timestamp,
            self.end_timestamp,
        )
        return result_list

    def get_sub_converge_instances(self):
        """
        获取二级收敛对象集合
        :return:
        """
        pipeline = FTA_SUB_CONVERGE_DIMENSION_KEY.client.pipeline()
        keys_length = {}

        # 去除策略ID避免存储被路由到不同的redis
        key_params = self.get_sub_converge_label_info()
        key_params.pop("strategy_id", None)
        converge_key = FTA_SUB_CONVERGE_DIMENSION_KEY.get_key(**key_params)
        keys_length[converge_key] = 1
        pipeline.zrangebyscore(converge_key, self.start_timestamp, self.end_timestamp, withscores=True)
        pipeline_results = pipeline.execute()
        return keys_length, pipeline_results

    def get_sub_converge_label_info(self):
        converge_label_info = {}
        for key, values in self.converged_condition.items():
            if values is None:
                values = ""
            if isinstance(values, (list, set)):
                values = "_".join([str(value) for value in values])
            else:
                values = str(values)
            converge_label_info[key] = values
        return converge_label_info

    def get_set_keys(self, key, values):
        """
        获取集群key
        """
        value_list = []
        for value in values:
            if not isinstance(value, list):
                value = [str(value)]
            value_list.extend(value)
        # get all set_key

        set_keys = (
            [
                FTA_CONVERGE_DIMENSION_KEY.get_key(strategy_id=self.strategy_id, dimension=key, value=v)
                for v in value_list
            ]
            if value_list
            else [FTA_CONVERGE_DIMENSION_KEY.get_key(strategy_id=self.strategy_id, dimension=key, value="")]
        )
        return set(set_keys)


class DimensionCalculator:
    """
    收敛维度计算器类，用于处理告警收敛维度的计算与存储

    类属性:
        DimensionExpireMinutes: 维度过期时间（秒），基于常量分钟数转换
        QUEUE_KEY_TEMPLATE: Redis队列键模板，包含实例类型占位符
    """

    DimensionExpireMinutes = CONST_MINUTES * 60

    QUEUE_KEY_TEMPLATE = KEY_PREFIX + ".converge.{}"

    def __init__(self, related_instance, instance_type=ConvergeType.ACTION, converge_config=None, alerts=None):
        """
        初始化收敛计算器

        参数:
            related_instance: 关联的收敛实例对象
            instance_type: 实例类型（ACTION/CONVERGE），默认为动作类型
            converge_config: 收敛配置字典，可选
            alerts: 告警列表，用于上下文构建

        初始化流程:
        1. 创建ActionContext上下文对象
        2. 获取所有收敛维度的初始值
        3. 若为CONVERGE类型，合并收敛配置中的条件参数
        """
        self.related_instance = related_instance
        self.instance_type = instance_type
        self.converge_config = converge_config
        self.alerts = alerts
        self.converge_ctx = ActionContext(
            self.related_instance, alerts=alerts, use_alert_snap=True
        ).converge_context.get_dict(ALL_CONVERGE_DIMENSION.keys())
        if instance_type == ConvergeType.CONVERGE:
            self.converge_ctx.update(related_instance.converge_config["converged_condition"])

    def calc_dimension(self):
        """
        执行收敛维度计算与Redis存储操作

        处理流程:
        1. 生成基于创建时间的时间戳评分
        2. 创建Redis管道批量操作
        3. 遍历所有比较维度进行以下操作：
           - 跳过空值维度
           - 标准化维度值为列表格式
           - 构建Redis存储键
           - 清理历史过期数据
           - 添加当前实例数据
           - 设置键过期时间
        4. 执行管道命令并返回收敛信息

        返回值:
            调用compile_converge_info方法生成的收敛结果对象
        """
        score = arrow.get(self.related_instance.create_time).replace(tzinfo="utc").timestamp
        pipeline = FTA_CONVERGE_DIMENSION_KEY.client.pipeline()
        for dimension in COMPARED_CONVERGE_DIMENSION.keys():
            values = self.converge_ctx.get(dimension)
            if values is None or not str(values):
                continue
            # 如果值为空的话，忽略掉这个维度
            if not isinstance(values, (list, set)):
                values = [str(values)]
            for value in values:
                key = FTA_CONVERGE_DIMENSION_KEY.get_key(
                    strategy_id=getattr(self.related_instance, "strategy_id", 0), dimension=dimension, value=value
                )
                # 清理历史过期数据（一年前至过期间隔前的数据）
                pipeline.zremrangebyscore(
                    key,
                    arrow.utcnow().replace(years=-1).timestamp,
                    arrow.utcnow().replace(minutes=-self.DimensionExpireMinutes).timestamp,
                )
                # 添加当前实例到维度集合
                kwargs = {f"{self.instance_type}_{str(self.related_instance.id)}": score}
                pipeline.zadd(key, kwargs)
                # 重置键过期时间
                pipeline.expire(key, FTA_CONVERGE_DIMENSION_KEY.ttl)
        pipeline.execute()
        return self.compile_converge_info()

    def calc_sub_converge_dimension(self):
        """
        二级收敛的维度计算

        参数:
            self: 实例对象，包含以下属性:
                - related_instance: 关联实例对象，需包含create_time属性
                - converge_ctx: 收敛上下文信息字典
                - instance_type: 实例类型标识字符串
                - DimensionExpireMinutes: 维度过期时间(分钟)
                - alerts: 告警对象列表(可选)

        返回值:
            调用compile_converge_info方法返回的组装后的收敛信息字典
            当维度数据为空时直接返回None

        执行流程:
        1. 提取关联实例创建时间的时间戳作为评分基准
        2. 遍历SUB_CONVERGE_DIMENSION维度配置，收集有效维度值
        3. 使用Redis管道执行以下原子操作：
           a. 清理指定时间范围内的过期维度数据
           b. 添加当前实例维度信息到有序集合
           c. 设置键值过期时间
        4. 返回组装后的收敛信息
        """
        score = arrow.get(self.related_instance.create_time).replace(tzinfo="utc").timestamp

        label_info = {}
        for dimension in SUB_CONVERGE_DIMENSION.keys():
            values = self.converge_ctx.get(dimension)
            if values is None:
                return
            # 如果值为空的话，忽略掉这个维度
            if isinstance(values, (list, set)):
                values = "_".join([str(value) for value in values])
            label_info[dimension] = values

        sub_converge_key = FTA_SUB_CONVERGE_DIMENSION_KEY.get_key(**label_info)
        pipeline = FTA_SUB_CONVERGE_DIMENSION_KEY.client.pipeline()
        # 先清理过期的数据
        pipeline.zremrangebyscore(
            sub_converge_key,
            arrow.utcnow().replace(years=-1).timestamp,
            arrow.utcnow().replace(minutes=-self.DimensionExpireMinutes).timestamp,
        )
        # 保存的score
        kwargs = {f"{self.instance_type}_{str(self.related_instance.id)}": score}
        pipeline.zadd(sub_converge_key, kwargs)
        pipeline.expire(sub_converge_key, FTA_SUB_CONVERGE_DIMENSION_KEY.ttl)
        pipeline.execute()
        return self.compile_converge_info()

    def compile_converge_info(self):
        """
        组装收敛任务信息

        参数:
            self: 实例对象，包含以下属性:
                - instance_type: 实例类型标识字符串
                - converge_config: 收敛配置对象
                - converge_ctx: 收敛上下文信息字典
                - related_instance: 关联实例对象，需包含id属性
                - alerts: 告警对象列表(可选)

        返回值:
            包含收敛任务信息的字典，结构如下:
            {
                "instance_type": 实例类型标识,
                "converge_config": 收敛配置对象,
                "converge_context": 收敛上下文字典,
                "id": 关联实例ID,
                "alerts": 告警对象字典列表(当存在告警时)
            }

        执行流程:
        1. 提取实例基础信息和配置数据
        2. 将告警对象列表转换为字典表示
        3. 组装并返回完整的收敛信息字典
        """
        instance_info = {
            "instance_type": self.instance_type,
            "converge_config": self.converge_config,
            "converge_context": self.converge_ctx,
            "id": self.related_instance.id,
            "alerts": [alert.to_dict() for alert in self.alerts] if self.alerts else [],
        }

        return instance_info
