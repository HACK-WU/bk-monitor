"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import logging

from django.conf import settings
from django.db.transaction import atomic
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from bkmonitor.utils.tenant import bk_biz_id_to_bk_tenant_id
from core.drf_resource import api
from metadata import config
from metadata.models.data_link import DataIdConfig, utils
from metadata.models.data_link.constants import DataLinkKind, DataLinkResourceStatus

logger = logging.getLogger("metadata")


@atomic(config.DATABASE_CONNECTION_NAME)
def apply_data_id_v2(
    data_name: str,
    bk_biz_id: int,
    namespace: str = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
    is_base: bool = False,
    event_type: str = "metric",
) -> bool:
    """
    下发 data_id 资源并记录配置信息

    参数:
        data_name (str): 数据源名称
        bk_biz_id (int): 业务ID
        namespace (str): 资源命名空间（默认值来自系统配置）
        is_base (bool): 是否为基础数据源（1000/1001业务）
        event_type (str): 数据类型（默认为"metric"）

    返回值:
        bool: 操作结果状态（始终返回True）

    执行流程:
        1. 解析业务ID获取租户ID
        2. 根据数据源类型处理数据名称
        3. 创建或获取数据ID配置
        4. 调用数据链路API应用配置
    """
    # 记录申请data_id的详细信息
    logger.info("apply_data_id_v2:apply data_id for data_name: %s,event_type: %s", data_name, event_type)

    # 从业务ID解析租户ID
    bk_tenant_id = bk_biz_id_to_bk_tenant_id(bk_biz_id)

    # 根据数据源类型处理数据名称
    if is_base:  # 处理基础数据源（1000/1001业务）
        # 使用原始数据名称作为唯一键
        bkbase_data_name = data_name
    else:  # 处理自定义数据源
        # 二次处理数据名称避免长度限制和特殊字符
        bkbase_data_name = utils.compose_bkdata_data_id_name(data_name)

    # 记录处理后的数据名称
    logger.info("apply_data_id_v2:bkbase_data_name: %s", bkbase_data_name)

    # 创建或获取数据ID配置记录
    data_id_config_ins, _ = DataIdConfig.objects.get_or_create(
        name=bkbase_data_name, namespace=namespace, bk_biz_id=bk_biz_id, bk_tenant_id=bk_tenant_id
    )

    # 生成数据链路配置
    data_id_config = data_id_config_ins.compose_config(event_type=event_type)

    # 调用数据链路API应用配置
    api.bkdata.apply_data_link(config=[data_id_config], bk_tenant_id=bk_tenant_id)

    # 记录操作成功日志
    logger.info("apply_data_id_v2:apply data_id for data_name: %s success", data_name)
    return True


def get_data_id_v2(
    data_name: str,
    bk_biz_id: int,
    namespace: str | None = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
    is_base: bool = False,
) -> dict:
    """
    获取数据源对应的 data_id（版本2）

    参数:
        data_name: 原始数据源名称字符串
        bk_biz_id: 业务ID整数值，用于租户ID转换
        namespace: 命名空间字符串（可选），默认使用settings中定义的默认命名空间
        is_base: 布尔标志，指示是否为基础数据源（True=基础数据源，False=自定义数据源）

    返回值:
        包含状态和data_id的字典对象：
        - 正常状态：{"status": "OK", "data_id": int}
        - 异常状态：{"status": 具体状态值, "data_id": None}

    该函数实现完整的data_id获取流程：
    1. 数据源名称处理（基础/自定义分类处理）
    2. 业务ID到租户ID的转换
    3. 元数据服务查询与数据库状态同步
    4. 数据有效性验证与状态管理
    """
    logger.info("get_data_id: data_name->[%s]", data_name)

    # 数据源名称处理逻辑分支
    # 基础数据源使用原始名称作为唯一键
    if is_base:
        data_id_name = data_name
    else:  # 自定义数据源需要特殊处理
        # 通过工具函数进行名称格式转换，避免长度限制和特殊字符问题
        data_id_name = utils.compose_bkdata_data_id_name(data_name)

    # 业务ID到租户ID的转换
    bk_tenant_id = bk_biz_id_to_bk_tenant_id(bk_biz_id)

    # 元数据服务查询
    # 通过API接口获取数据链路配置信息
    data_id_config = api.bkdata.get_data_link(
        kind=DataLinkKind.get_choice_value(DataLinkKind.DATAID.value),
        namespace=namespace,
        name=data_id_name,
        bk_tenant_id=bk_tenant_id,
    )

    # 数据库实例获取
    # 查询本地存储的数据ID配置记录
    data_id_config_ins = DataIdConfig.objects.get(name=data_id_name, namespace=namespace, bk_tenant_id=bk_tenant_id)

    logger.info("get_data_id: request bkbase data_id_config->[%s]", data_id_config)

    # 状态解析与有效性验证
    # 从配置信息中提取状态阶段值
    phase = data_id_config.get("status", {}).get("phase")

    # 正常状态处理分支
    if phase == DataLinkResourceStatus.OK.value:
        # 从注解信息中提取data_id数值
        data_id = int(data_id_config.get("metadata", {}).get("annotations", {}).get("dataId", 0))
        # 更新数据库记录状态
        data_id_config_ins.status = phase
        data_id_config_ins.save()
        logger.info("get_data_id: request data_name -> [%s] now is ok", data_name)
        return {"status": phase, "data_id": data_id}

    # 异常状态处理分支
    # 持久化异常状态到数据库
    data_id_config_ins.status = phase
    data_id_config_ins.save()
    logger.info("get_data_id: request data_name -> [%s] ,phase->[%s]", data_name, phase)
    return {"status": phase, "data_id": None}


def get_data_link_component_config(
    bk_tenant_id: str,
    kind: str,
    component_name: str,
    namespace: str | None = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
):
    """
    获取数据链路组件状态
    @param kind: 数据链路组件类型
    @param component_name: 数据链路组件名称
    @param namespace: 数据链路命名空间
    @return: 状态
    """
    logger.info(
        "get_data_link_component_config: try to get component config,kind->[%s],name->[%s],namespace->[%s]",
        kind,
        component_name,
        namespace,
    )
    try:
        bkbase_kind = DataLinkKind.get_choice_value(kind)
        if not bkbase_kind:
            logger.info("get_data_link_component_config: kind is not valid,kind->[%s]", kind)
        component_config = api.bkdata.get_data_link(
            bk_tenant_id=bk_tenant_id, kind=bkbase_kind, namespace=namespace, name=component_name
        )
        return component_config
    except Exception as e:
        logger.error(
            "get_data_link_component_config: get component config failed,kind->[%s],name->[%s],namespace->[%s],"
            "error->[%s]",
            kind,
            component_name,
            namespace,
            e,
        )
        return None


def get_data_link_component_status(
    bk_tenant_id: str,
    kind: str,
    component_name: str,
    namespace: str = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
):
    """
    获取数据链路组件状态
    @param kind: 数据链路组件类型
    @param component_name: 数据链路组件名称
    @param namespace: 数据链路命名空间
    @return: 状态
    """
    logger.info(
        "get_data_link_component_status: try to get component status,kind->[%s],name->[%s],namespace->[%s]",
        kind,
        component_name,
        namespace,
    )
    try:
        bkbase_kind = DataLinkKind.get_choice_value(kind)
        if not bkbase_kind:
            logger.info("get_data_link_component_status: kind is not valid,kind->[%s]", kind)
        component_config = get_bkbase_component_status_with_retry(
            bk_tenant_id=bk_tenant_id, kind=bkbase_kind, namespace=namespace, name=component_name
        )
        phase = component_config.get("status", {}).get("phase")
        return phase
    except RetryError as e:
        logger.error(
            "get_data_link_component_status: get component status failed,kind->[%s],name->[%s],namespace->["
            "%s],error->[%s]",
            kind,
            component_name,
            namespace,
            e.__cause__,
        )
        return DataLinkResourceStatus.FAILED.value
    except Exception as e:
        logger.error(
            "get_data_link_component_status: get component status failed,kind->[%s],name->[%s],namespace->[%s],"
            "error->[%s]",
            kind,
            component_name,
            namespace,
            e,
        )
        return DataLinkResourceStatus.FAILED.value


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
def get_bkbase_component_status_with_retry(
    bk_tenant_id: str,
    kind: str,
    namespace: str,
    name: str,
):
    """
    获取bkbase组件状态，具备重试机制
    """
    try:
        return api.bkdata.get_data_link(bk_tenant_id=bk_tenant_id, kind=kind, namespace=namespace, name=name)
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            "get_bkbase_component_status_with_retry: get component status failed,kind->[%s],name->[%s],error->[%s]",
            kind,
            name,
            e,
        )
        raise e
