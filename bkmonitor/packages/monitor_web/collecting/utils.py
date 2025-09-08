"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from core.drf_resource import api
from monitor_web.models import CollectConfigMeta


def chunks(lst, n):
    """
    切割数组
    :param lst: 数组
    :param n: 每组多少份
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def fetch_sub_statistics(config_data_list: list[CollectConfigMeta]):
    """
    获取订阅配置统计信息并建立ID映射关系

    参数:
        config_data_list (List[ConfigObject]): 配置对象列表，要求每个对象包含deployment_config属性，
                                            且deployment_config需包含subscription_id字段

    返回值:
        Tuple[Dict[int, ConfigObject], List[Dict]]: 包含两个元素的元组
            - subscription_id_config_map: 订阅ID到配置对象的映射字典
            - collect_statistics_data: 节点管理接口返回的统计信息列表，包含所有分组的统计数据

    处理流程:
    1. 构建订阅ID与配置对象的映射关系
    2. 将订阅ID按20个一组分批请求统计信息
    3. 合并所有批次的统计结果
    """

    # 建立订阅ID到配置对象的映射关系
    # 过滤条件: 仅保留包含有效subscription_id的配置项
    subscription_id_config_map = {
        config.deployment_config.subscription_id: config
        for config in config_data_list
        if config.deployment_config.subscription_id
    }

    # 分批请求节点管理统计信息
    # 采用批量请求方式减少单次请求压力，每组最多20个订阅ID
    # 请求参数格式: [{"subscription_id_list": [id1,id2,...]}, ...]
    collect_statistics_data = api.node_man.fetch_subscription_statistic.bulk_request(
        [
            {"subscription_id_list": subscription_id_group}
            for subscription_id_group in chunks(list(subscription_id_config_map.keys()), 20)
        ],
        ignore_exceptions=True,
    )
    # 将分组返回的统计结果展平为单一列表
    # 示例输入: [[group1_data], [group2_data]] -> 输出: [group1_data, group2_data]
    collect_statistics_data = [item for group in collect_statistics_data for item in group]

    return subscription_id_config_map, collect_statistics_data
