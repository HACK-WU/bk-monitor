"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
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
    根据conditions配置加载Conditions实例，构建组合条件对象树

    参数:
        conditions_config: 条件配置列表，每个元素是一个条件列表，用于构建OrCondition对象
                          格式为: [[{"field":"ip", "method":"eq", "value":"111"}, {}], []]
                          支持多级嵌套结构，每个子列表代表一个OR条件组
        default_value_if_not_exists: 布尔值，当条件字段不存在时的默认处理策略
                                   True表示返回空值继续处理，False表示抛出异常

    返回值:
        OrCondition对象: 包含完整条件树的组合条件对象
                       结构为: OrCondition(AndCondition(Condition,...), ...)

    处理流程:
    1. 参数类型校验（list/tuple）
    2. 构建OR条件根节点
    3. 遍历每个AND条件组
    4. 解析条件字段配置
    5. 创建具体条件实例
    6. 组装完整的条件树
    """
    # 检查conditions_config是否为列表或元组，如果不是则抛出异常
    if not isinstance(conditions_config, list | tuple):
        raise Exception("Config Incorrect, Check your settings.")

    # 创建OrCondition对象作为根节点容器
    or_cond_obj = conditions.OrCondition()

    # 遍历顶层OR条件组
    for cond_item_list in conditions_config:
        # 创建AND条件容器
        and_cond_obj = conditions.AndCondition()

        # 处理单个条件项
        for cond_item in cond_item_list:
            # 提取条件三要素
            field_name = cond_item.get("field")
            method = cond_item.get("method", "eq")
            # 日志对eq/neq进行了转换处理
            if method not in CONDITION_CLASS_MAP:
                method = cond_item.get("_origin_method", "eq")

            field_value = cond_item.get("value")

            # 跳过不完整条件
            if not all([field_name, method, field_value]):
                continue

            # 加载字段实例
            cond_field = load_field_instance(field_name, field_value)
            # 创建具体条件对象
            cond_obj = CONDITION_CLASS_MAP.get(method)(cond_field, default_value_if_not_exists)
            # 添加到AND条件组
            and_cond_obj.add(cond_obj)

        # 将AND条件组添加到OR根节点
        or_cond_obj.add(and_cond_obj)

    # 返回构建完成的条件树
    return or_cond_obj
