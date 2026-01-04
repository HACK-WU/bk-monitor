"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from copy import deepcopy
from functools import lru_cache

from django.conf import settings
from django.utils.translation import gettext as _

from bkmonitor.utils.request import get_request
from constants.data_source import DataSourceLabel, DataTypeLabel
from core.drf_resource import api
from monitor_web.constants import EVENT_TYPE
from monitor_web.models.custom_report import CustomEventGroup


@lru_cache(maxsize=1000)
def get_org_id(bk_biz_id: int) -> int | None:
    """
    获取业务对应的Grafana组织ID
    :param bk_biz_id: 业务
    :return: 组织ID
    """

    result = api.grafana.get_organization_by_name(name=str(bk_biz_id))

    if not result or not result["result"]:
        return

    return result["data"]["id"]


def patch_home_panels():
    panels = [
        {
            "datasource": None,
            "fieldConfig": {"defaults": {"custom": {}}, "overrides": []},
            "gridPos": {"h": 4, "w": 24, "x": 0, "y": 0},
            "id": 2,
            "options": {"content": "<br>\n<br>\n<br>\n<div><H1>" + _("欢迎使用仪表盘") + "</H1></div>", "mode": "html"},
            "pluginVersion": "7.1.0",
            "targets": [],
            "timeFrom": None,
            "timeShift": None,
            "title": "",
            "transparent": True,
            "type": "text",
        },
        {
            "datasource": None,
            "fieldConfig": {"defaults": {"custom": {}}, "overrides": []},
            "folderId": None,
            "gridPos": {"h": 24, "w": 8, "x": 0, "y": 4},
            "headings": True,
            "id": 7,
            "limit": None,
            "pluginVersion": "7.2.0-beta1",
            "query": "",
            "recent": False,
            "search": True,
            "starred": False,
            "tags": [],
            "targets": [],
            "timeFrom": None,
            "timeShift": None,
            "title": _("所有仪表盘"),
            "type": "dashlist",
        },
        {
            "datasource": None,
            "fieldConfig": {"defaults": {"custom": {}}, "overrides": []},
            "gridPos": {"h": 24, "w": 8, "x": 8, "y": 4},
            "headings": True,
            "id": 6,
            "limit": 15,
            "pluginVersion": "7.2.0-beta1",
            "query": "",
            "recent": True,
            "search": False,
            "starred": True,
            "tags": [],
            "targets": [],
            "timeFrom": None,
            "timeShift": None,
            "title": _("收藏和最近查看的仪表盘"),
            "type": "dashlist",
        },
        {
            "datasource": None,
            "fieldConfig": {"defaults": {"custom": {}}, "overrides": []},
            "gridPos": {"h": 24, "w": 8, "x": 16, "y": 4},
            "id": 3,
            "options": {
                "content": f"""
<br>
<div>
    <a href="{settings.SITE_URL}grafana/dashboard/new"><H3>"""
                + _("快速创建您的仪表盘吧！")
                + f"""</H3></a>
</div>
<br>
<div>
    <a href="{settings.SITE_URL}grafana/dashboards/folder/new"><H3>"""
                + _("你可以通过创建目录来管理仪表盘。")
                + f"""</H3></a>
</div>
<br>
<div>
    <a href="{settings.SITE_URL}grafana/dashboard/import"><H3>"""
                + _("你可以直接导入，如果本地有仪表盘文件")
                + f"""</H3></a>
</div>
<br><br><br><br>
<div>
    <a href="{settings.BK_DOCS_SITE_URL}markdown/ZH/Monitor/{settings.BK_DOC_VERSION}"""
                + """/UserGuide/ProductFeatures/data-visualization/dashboard.md" target="_blank">
        """
                + _("查看产品文档")
                + """
    </a>
</div>
                """,
                "mode": "html",
            },
            "pluginVersion": "7.1.0",
            "targets": [],
            "timeFrom": None,
            "timeShift": None,
            "title": _("仪表盘使用指引"),
            "type": "text",
        },
    ]
    return panels


def get_cookies_filter() -> dict | None:
    """
    解析Cookies过滤字段
    HTTP_KEEPCOOKIES可能为空
    """
    request = get_request(peaceful=True)
    if not request:
        return

    # 提取KEEPCOOKIES请求头，找到需要提取的字段
    # 值可能为<no value>或[field1, field2]
    cookies = request.META.get("HTTP_KEEPCOOKIES")
    if not cookies or "no value" in cookies:
        return
    cookies = [c for c in cookies[1:-1].split(" ") if c]
    if not cookies:
        return

    # 提取cookies中的字段作为过滤条件
    filter_dict = {field: request.COOKIES[field] for field in cookies if request.COOKIES.get(field)}
    return filter_dict


def remove_all_conditions(where_list: list) -> list:
    """
    删除查询条件列表中的全选条件，并处理逻辑连接符

    参数:
        where_list: list - 查询条件列表，每个条件包含key、value、method、condition等字段
            示例: [
                {"key": "field1", "value": ["__BKMONITOR_ALL__"], "method": "eq"},
                {"key": "field2", "value": ["value2"], "method": "eq", "condition": "and"}
            ]

    返回值:
        list - 清理后的条件列表，如果整个表达式恒为True则返回空列表

    该方法实现全选条件的智能清理，包含：
    1. 识别并删除包含全选标签的无效条件
    2. 处理删除条件后的逻辑连接符调整
    3. 检测恒为True的表达式并返回空列表
    4. 清理首个条件的逻辑连接符

    逻辑说明:
        - 全选标签(__BKMONITOR_ALL__)表示选择所有值，相当于无过滤条件
        - 当全选条件使用肯定方法(eq/include/regex)时，该条件恒为True
        - 删除恒为True的条件后需要调整逻辑连接符，避免语法错误
        - 如果出现"True OR ..."的情况，整个表达式恒为True，返回空列表
    """
    # 全选标签常量
    select_all_tag = "__BKMONITOR_ALL__"

    # 1. 空列表直接返回
    if not where_list:
        return []

    # 2. 深拷贝避免修改原列表
    where_list = deepcopy(where_list)
    index = 0

    # 3. 遍历条件列表，删除全选条件
    while index < len(where_list):
        where = where_list[index]

        # 4. 判断是否为需要删除的全选条件
        # 条件：包含全选标签 且 使用肯定方法(eq/include/regex)
        if select_all_tag not in where["value"] or where["method"] not in ["eq", "include", "regex"]:
            # 不是全选条件，继续检查下一个
            index += 1
            continue

        # 5. 删除当前全选条件
        where_list.pop(index)

        # 6. 获取下一个条件（如果存在）
        # 注意：删除后index位置已经是原来的下一个条件
        next_where = where_list[index] if index < len(where_list) else None

        # 7. 处理逻辑连接符调整
        # 如果删除的是第一个条件(index==0)或者删除的条件前面是OR连接
        if where.get("condition") == "or" or index == 0:
            if not next_where or next_where.get("condition") == "or":
                # 情况1: True OR ... = True (整个表达式恒为True)
                # 或者删除后没有剩余条件，返回空列表表示无过滤
                return []
            else:
                # 情况2: True AND next_condition = next_condition
                # 但由于删除了True条件，需要将下一个条件的连接符改为or
                # 这是因为原表达式可能是: prev OR True AND next
                # 删除True后变为: prev OR next
                next_where["condition"] = "or"

    # 8. 清理第一个条件的逻辑连接符
    # 第一个条件不应该有condition字段（没有前置条件可连接）
    if where_list:
        where_list[0].pop("condition", None)

    return where_list


def convert_to_microseconds(time_str: str) -> int:
    # 定义单位转换关系
    time_multipliers = {
        "ns": 1e-3,  # 纳秒到微秒
        "us": 1,  # 微秒到微秒
        "µs": 1,  # 微秒到微秒 (有些地方会用µs表示)
        "ms": 1e3,  # 毫秒到微秒
        "s": 1e6,  # 秒到微秒
        "m": 60 * 1e6,  # 分钟到微秒
        "h": 3600 * 1e6,  # 小时到微秒
    }

    # 提取数字部分和单位部分
    for unit in time_multipliers:
        if time_str.lower().endswith(unit):
            time_value = float(time_str[: -len(unit)])
            return int(time_value * time_multipliers[unit])

    raise ValueError("Unsupported time format")


def is_global_k8s_event(params: dict, bk_biz_id: int) -> bool:
    """
    判断是否是全局k8s事件
    """

    data_source_label = params["data_source_label"]
    data_type_label = params["data_type_label"]
    field = params["field"]
    metric_field = params["metric_field"]
    result_table_id = params["result_table_id"]
    data_id = result_table_id.split("_")[-1]

    # 判断是否是自定义事件数据ID
    try:
        data_id = int(data_id)
        is_custom_event_data_id = CustomEventGroup.objects.filter(
            bk_biz_id=bk_biz_id,
            type=EVENT_TYPE.CUSTOM_EVENT,
            bk_data_id=data_id,
        ).exists()
    except (ValueError, TypeError):
        is_custom_event_data_id = False

    # 判断是否是全局k8s事件,是则返回True
    if (
        data_source_label == DataSourceLabel.CUSTOM
        and data_type_label == DataTypeLabel.EVENT
        and field == "event_name"
        and metric_field == "__INDEX__"
        and not is_custom_event_data_id
    ):
        return True
    else:
        return False
