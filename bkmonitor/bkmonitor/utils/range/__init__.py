# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""
from constants.common import DutyType

from . import conditions, fields, period

__all__ = [
    "load_condition_instance",
    "TIME_MATCH_CLASS_MAP",
    "load_field_instance",
    "load_agg_condition_instance",
    "DUTY_TIME_MATCH_CLASS_MAP",
    "CONDITION_CLASS_MAP",
]

SUPPORT_SIMPLE_METHODS = ("include", "exclude", "gt", "gte", "lt", "lte", "eq", "neq", "reg", "nreg")
SUPPORT_COMPOSITE_METHODS = ("or", "and")

# 条件表达式与类的映射
CONDITION_CLASS_MAP = {
    "eq": conditions.EqualCondition,
    "neq": conditions.NotEqualCondition,
    "lt": conditions.LesserCondition,
    "lte": conditions.LesserOrEqualCondition,
    "gt": conditions.GreaterCondition,
    "gte": conditions.GreaterOrEqualCondition,
    "reg": conditions.RegularCondition,
    "nreg": conditions.NotRegularCondition,
    "include": conditions.IncludeCondition,
    "exclude": conditions.ExcludeCondition,
    "issuperset": conditions.IsSuperSetCondition,
}

# 默认的维度字段类
DEFAULT_DIMENSION_FIELD_CLASS = fields.DimensionField
# 维度字段名称与类的映射
DIMENSION_FIELD_CLASS_MAP = {
    "ip": fields.IpDimensionField,
    "bk_target_ip": fields.BkTargetIpDimensionField,
    "cc_topo_set": fields.TopoSetDimensionField,
    "cc_topo_module": fields.TopoModuleDimensionField,
    "cc_app_module": fields.AppModuleDimensionField,
    "bk_topo_node": fields.TopoNodeDimensionField,
    "host_topo_node": fields.HostTopoNodeDimensionField,
    "service_topo_node": fields.ServiceTopoNodeDimensionField,
}

TIME_MATCH_CLASS_MAP = {
    -1: period.TimeMatchBySingle,
    2: period.TimeMatchByDay,
    3: period.TimeMatchByWeek,
    4: period.TimeMatchByMonth,
}

DUTY_TIME_MATCH_CLASS_MAP = {
    DutyType.WEEKLY: period.TimeMatchByWeek,
    DutyType.MONTHLY: period.TimeMatchByMonth,
    DutyType.DAILY: period.TimeMatchByDay,
    DutyType.SINGLE: period.TimeMatchBySingle,
}


def load_field_instance(field_name, field_value):
    cond_field_class = DIMENSION_FIELD_CLASS_MAP.get(field_name, DEFAULT_DIMENSION_FIELD_CLASS)
    return cond_field_class(field_name, field_value)


def load_agg_condition_instance(agg_condition):
    """
    Load Condition instance by condition model
    :param agg_condition:
            [{"field":"ip", "method":"eq", "value":"111"}, {"field":"ip", "method":"eq", "value":"111", "method": "eq"}]
    :return: condition object
    """
    conditions_config = []

    condition = []
    for c in agg_condition:
        if c.get("condition") == "or" and condition:
            conditions_config.append(condition)
            condition = []

        condition.append({"field": c["key"], "method": c["method"], "value": c["value"]})

    if condition:
        conditions_config.append(condition)
    return load_condition_instance(conditions_config)


def load_condition_instance(conditions_config, default_value_if_not_exists=True):
    """
    根据conditions配置加载Conditions实例
    :param conditions_config: 条件配置列表，每个元素是一个条件列表，用于构建OrCondition对象
            格式为: [[{"field":"ip", "method":"eq", "value":"111"}, {}], []]
    :param default_value_if_not_exists: 如果条件不存在时的默认值
    :return: condition object: 返回构建的OrCondition对象
    """
    # 检查conditions_config是否为列表或元组，如果不是则抛出异常
    if not isinstance(conditions_config, (list, tuple)):
        raise Exception("Config Incorrect, Check your settings.")

    # 创建一个OrCondition对象，用于最终返回
    or_cond_obj = conditions.OrCondition()
    # 遍历conditions_config中的每个条件列表，每个条件列表用于构建一个AndCondition对象
    for cond_item_list in conditions_config:
        and_cond_obj = conditions.AndCondition()
        # 遍历条件列表中的每个条件，构建单个条件对象
        for cond_item in cond_item_list:
            field_name = cond_item.get("field")
            method = cond_item.get("method", "eq")
            # 日志对eq/neq 进行了转换(is one of/is not one of)
            if method not in CONDITION_CLASS_MAP:
                method = cond_item.get("_origin_method", "eq")

            field_value = cond_item.get("value")
            # 如果field_name, method, field_value任一为空，则跳过当前条件
            if not all([field_name, method, field_value]):
                continue

            # 加载单个条件字段实例
            cond_field = load_field_instance(field_name, field_value)
            # 根据方法获取对应的条件类实例，并传入单个条件字段实例
            cond_obj = CONDITION_CLASS_MAP.get(method)(cond_field, default_value_if_not_exists)
            # 将条件类实例添加到AndCondition对象中
            and_cond_obj.add(cond_obj)

        # 将构建好的AndCondition对象添加到OrCondition对象中
        or_cond_obj.add(and_cond_obj)
    # 返回最终构建的OrCondition对象
    return or_cond_obj

