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
import logging
import random
from typing import Any

from django.conf import settings
from django.db.models import Q
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from bkmonitor.utils.tenant import get_tenant_datalink_biz_id, get_tenant_default_biz_id
from constants.data_source import DATA_LINK_V3_VERSION_NAME, DATA_LINK_V4_VERSION_NAME
from core.drf_resource import api
from core.prometheus import metrics
from metadata.models import (
    AccessVMRecord,
    BCSClusterInfo,
    BcsFederalClusterInfo,
    ClusterInfo,
    DataSource,
    DataSourceOption,
)
from metadata.models.data_link import DataLink
from metadata.models.data_link.constants import DataLinkResourceStatus
from metadata.models.data_link.utils import (
    compose_bkdata_data_id_name,
    compose_bkdata_table_id,
)
from metadata.models.space.constants import EtlConfigs
from metadata.models.vm.bk_data import BkDataAccessor, access_vm
from metadata.models.vm.config import BkDataStorageWithDataID
from metadata.models.vm.constants import (
    ACCESS_DATA_LINK_FAILURE_STATUS,
    ACCESS_DATA_LINK_SUCCESS_STATUS,
    BKDATA_NS_TIMESTAMP_DATA_ID_LIST,
    TimestampLen,
)

logger = logging.getLogger("metadata")


def refine_bkdata_kafka_info(bk_tenant_id: str):
    """获取接入计算平台时使用的Kafka信息

    该函数实现从ClusterInfo中获取已注册的Kafka集群信息，并与计算平台API返回的
    Kafka主机信息进行匹配，最终返回有效的集群ID和主机名。

    :param bk_tenant_id: 蓝鲸租户ID（字符串格式）
    :return: 包含 cluster_id（集群ID）和 host（主机名）的字典
    :raises ValueError: 当计算平台未返回Kafka信息或主机未在ClusterInfo注册时抛出
    """
    from metadata.models import ClusterInfo

    # 获取已注册的Kafka集群信息
    # 查询当前租户下所有Kafka类型集群，提取domain_name和cluster_id
    kafka_clusters = ClusterInfo.objects.filter(bk_tenant_id=bk_tenant_id, cluster_type=ClusterInfo.TYPE_KAFKA).values(
        "cluster_id", "domain_name"
    )

    # 构建域名到集群ID的映射表
    kafka_domain_cluster_id = {obj["domain_name"]: obj["cluster_id"] for obj in kafka_clusters}

    # 调用计算平台API获取Kafka信息
    bkdata_kafka_data: list[dict[str, Any]] = api.bkdata.get_kafka_info(bk_tenant_id=bk_tenant_id)
    if not bkdata_kafka_data:
        logger.error("bkdata kafka info not found, bk_tenant_id: %s", bk_tenant_id)
        raise ValueError("bkdata kafka info not found")

    # 提取API返回的主机列表
    bkdata_kafka_host_list = bkdata_kafka_data[0].get("ip_list", "").split(",")

    # 查找已注册的可用主机
    # 获取metadata和API返回的主机交集
    existed_host_list = list(set(bkdata_kafka_host_list) & set(kafka_domain_cluster_id.keys()))

    # 无可用主机时抛出异常
    if not existed_host_list:
        logger.error("bkdata kafka host not registered ClusterInfo, bkdata resp: %s", json.dumps(bkdata_kafka_data))
        raise ValueError("bkdata kafka host not registered ClusterInfo")

    # 随机选择一个可用主机并返回结果
    host = random.choice(existed_host_list)
    cluster_id = kafka_domain_cluster_id[host]
    logger.info("refine exist kafka, cluster_id: %s, host: %s", cluster_id, host)
    return {"cluster_id": cluster_id, "host": host}


def access_bkdata(bk_tenant_id: str, bk_biz_id: int, table_id: str, data_id: int):
    """根据类型接入计算平台

    该函数实现将指定数据源接入计算平台的核心流程，主要处理VictoriaMetrics类型数据源的接入。
    包含空间信息处理、数据源校验、平台接入、记录创建及BCS集群特殊处理等步骤。

    1. 仅针对接入influxdb类型数据源
    2. 异常处理通过日志记录并触发告警通知

    :param bk_tenant_id: 蓝鲸租户ID（字符串格式）
    :param bk_biz_id: 业务ID（整数类型）
    :param table_id: 结果表标识符（字符串格式）
    :param data_id: 数据源唯一标识（整数类型）
    :return: None（通过return提前退出表示流程终止）
    """
    logger.info("bk_biz_id: %s, table_id: %s, data_id: %s start access vm", bk_biz_id, table_id, data_id)

    from metadata.models import AccessVMRecord, KafkaStorage, Space, SpaceVMInfo

    # 获取业务空间信息
    # NOTE: 0业务没有空间信息，无需处理
    space_data = {}
    try:
        # 通过业务ID获取空间信息（强制转换bk_biz_id为整数）
        space_data = Space.objects.get_space_info_by_biz_id(int(bk_biz_id))
    except Exception as e:
        logger.error("get space error by biz_id: %s, error: %s", bk_biz_id, e)

    # 空间VM记录创建
    # 检查并创建业务对应的空间VM信息记录
    if (
        space_data
        and not SpaceVMInfo.objects.filter(
            space_type=space_data["space_type"], space_id=space_data["space_id"]
        ).exists()
    ):
        SpaceVMInfo.objects.create_record(space_type=space_data["space_type"], space_id=space_data["space_id"])

    # 接入状态检查
    # 若已存在接入记录则直接返回
    if AccessVMRecord.objects.filter(result_table_id=table_id).exists():
        logger.info("table_id: %s has already been created", table_id)
        return

    # 配置参数准备
    # 获取数据源类型和集群信息
    data_type_cluster = get_data_type_cluster(data_id)
    data_type = data_type_cluster.get("data_type")

    # 获取VM集群配置
    vm_cluster = get_vm_cluster_id_name(bk_tenant_id, space_data.get("space_type", ""), space_data.get("space_id", ""))
    vm_cluster_name = vm_cluster.get("cluster_name")

    # 数据平台接入执行
    # 包含BCS集群标识、数据名称、时间戳精度等参数准备
    bcs_cluster_id = data_type_cluster.get("bcs_cluster_id")
    data_name_and_topic = get_bkbase_data_name_and_topic(table_id)
    timestamp_len = get_timestamp_len(data_id)

    try:
        # 执行VM平台接入操作
        vm_data = access_vm_by_kafka(
            bk_tenant_id, table_id, data_name_and_topic["data_name"], vm_cluster_name, timestamp_len
        )
        # 上报成功指标
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V3_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_SUCCESS_STATUS,
            strategy=DataLink.BK_STANDARD_V2_TIME_SERIES,
        )
    except Exception as e:
        # 异常处理及失败指标上报
        logger.error("access vm error, %s", e)
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V3_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_FAILURE_STATUS,
            strategy=DataLink.BK_STANDARD_V2_TIME_SERIES,
        )
        return

    # 接入结果校验
    # 检查返回值中的错误信息
    if vm_data.get("err_msg"):
        logger.error("access vm error")
        return

    # 数据记录创建
    # 包含Kafka存储和VM接入记录的创建
    try:
        # Kafka存储创建（若不存在）
        if not vm_data.get("kafka_storage_exist"):
            KafkaStorage.create_table(
                bk_tenant_id=bk_tenant_id,
                table_id=table_id,
                is_sync_db=True,
                storage_cluster_id=vm_data["cluster_id"],
                topic=data_name_and_topic["topic_name"],
                use_default_format=False,
            )
    except Exception as e:
        logger.error("create KafkaStorage error for access vm: %s", e)

    try:
        # 创建VM接入记录
        AccessVMRecord.objects.create(
            bk_tenant_id=bk_tenant_id,
            data_type=data_type,
            result_table_id=table_id,
            bcs_cluster_id=bcs_cluster_id,
            storage_cluster_id=vm_data["cluster_id"],
            vm_cluster_id=vm_cluster["cluster_id"],
            bk_base_data_id=vm_data["bk_data_id"],  # 计算平台数据ID
            bk_base_data_name=data_name_and_topic["data_name"],  # 计算平台数据名称
            vm_result_table_id=vm_data["clean_rt_id"],
        )
    except Exception as e:
        logger.error("create AccessVMRecord error for access vm: %s", e)

    logger.info("bk_biz_id: %s, table_id: %s, data_id: %s access vm successfully", bk_biz_id, table_id, data_id)

    # BCS集群合流处理
    # 需满足：1.启用合流 2.存在目标RT 3.具有BCS集群ID
    if (
        settings.BCS_DATA_CONVERGENCE_CONFIG.get("is_enabled")
        and settings.BCS_DATA_CONVERGENCE_CONFIG.get("k8s_metric_rt")
        and settings.BCS_DATA_CONVERGENCE_CONFIG.get("custom_metric_rt")
        and bcs_cluster_id
    ):
        try:
            # 获取合流参数
            data_name_and_dp_id = get_bcs_convergence_data_name_and_dp_id(table_id)
            # 构建清洗参数
            clean_data = BkDataAccessor(
                bk_tenant_id=bk_tenant_id,
                bk_table_id=data_name_and_dp_id["data_name"],
                data_hub_name=data_name_and_dp_id["data_name"],
                timestamp_len=timestamp_len,
            ).clean
            # 设置目标结果表
            clean_data["result_table_id"] = (
                settings.BCS_DATA_CONVERGENCE_CONFIG["k8s_metric_rt"]
                if data_type == AccessVMRecord.BCS_CLUSTER_K8S
                else settings.BCS_DATA_CONVERGENCE_CONFIG["custom_metric_rt"]
            )
            clean_data["processing_id"] = data_name_and_dp_id["dp_id"]
            # 创建清洗任务
            api.bkdata.databus_cleans(**clean_data)
            # 启动清洗任务
            api.bkdata.start_databus_cleans(
                result_table_id=clean_data["result_table_id"],
                storages=["kafka"],
                processing_id=data_name_and_dp_id["dp_id"],
            )
        except Exception as e:
            logger.error(
                "bcs convergence create or start data clean error, table_id: %s, params: %s, error: %s",
                table_id,
                json.dumps(clean_data),
                e,
            )


def access_vm_by_kafka(
    bk_tenant_id: str, table_id: str, raw_data_name: str, vm_cluster_name: str, timestamp_len: int
) -> dict:
    """通过 kafka 配置接入 vm

    该函数实现将指定结果表通过 Kafka 接入 VictoriaMetrics 存储的核心流程。
    主要处理 Kafka 存储配置检查、数据清洗规则创建、VM 存储接入等操作。

    :param bk_tenant_id: 蓝鲸租户ID（字符串格式）
    :param table_id: 结果表ID（格式为"结果表名.模块名"）
    :param raw_data_name: 原始数据名称（清洗后的数据标识）
    :param vm_cluster_name: VM集群名称（目标存储集群标识）
    :param timestamp_len: 时间戳长度（13位毫秒/16位纳秒）
    :return: 包含接入结果的字典，成功时包含 clean_rt_id、bk_data_id、cluster_id 等信息，
             失败时包含 err_msg 错误信息
    """
    from metadata.models import BkDataStorage, KafkaStorage, ResultTable

    # 初始化 Kafka 存储状态和集群ID
    kafka_storage_exist, storage_cluster_id = True, 0
    try:
        # 查询现有 Kafka 存储配置
        kafka_storage = KafkaStorage.objects.get(bk_tenant_id=bk_tenant_id, table_id=table_id)
        storage_cluster_id = kafka_storage.storage_cluster_id
    except Exception as e:
        logger.info("query kafka storage error %s", e)
        kafka_storage_exist = False

    # Kafka 存储配置不存在时的处理流程
    if not kafka_storage_exist:
        try:
            # 获取 Kafka 集群配置信息
            kafka_data = refine_bkdata_kafka_info(bk_tenant_id=bk_tenant_id)
        except Exception as e:
            logger.error("get bkdata kafka host error, table_id: %s, error: %s", table_id, e)
            return {"err_msg": f"request vm api error, {e}"}
        storage_cluster_id = kafka_data["cluster_id"]
        try:
            # 调用 VM 接入接口创建基础配置
            vm_data = access_vm(
                bk_tenant_id=bk_tenant_id,
                raw_data_name=raw_data_name,
                vm_cluster=vm_cluster_name,
                timestamp_len=timestamp_len,
            )
            vm_data["cluster_id"] = storage_cluster_id
            return vm_data
        except Exception as e:
            logger.error("request vm api error, table_id: %s, error: %s", table_id, e)
            return {"err_msg": f"request vm api error, {e}"}

    # 数据清洗规则创建
    bk_base_data = BkDataStorage.objects.filter(bk_tenant_id=bk_tenant_id, table_id=table_id).first()
    if not bk_base_data:
        bk_base_data = BkDataStorage.objects.create(table_id=table_id)
    if bk_base_data.raw_data_id == -1:
        result_table = ResultTable.objects.get(bk_tenant_id=bk_tenant_id, table_id=table_id)
        bk_base_data.create_databus_clean(result_table)
    # 重新加载数据以获取最新状态
    bk_base_data.refresh_from_db()

    # 构建清洗参数
    data_biz_id = get_tenant_datalink_biz_id(bk_tenant_id).data_biz_id
    raw_data_name = get_bkbase_data_name_and_topic(table_id)["data_name"]
    clean_data = BkDataAccessor(
        bk_tenant_id=bk_tenant_id,
        bk_biz_id=data_biz_id,
        bk_table_id=raw_data_name,
        data_hub_name=raw_data_name,
        vm_cluster=vm_cluster_name,
        timestamp_len=timestamp_len,
    ).clean
    clean_data.update(
        {
            "bk_biz_id": data_biz_id,
            "raw_data_id": bk_base_data.raw_data_id,
            "clean_config_name": raw_data_name,
            "kafka_storage_exist": kafka_storage_exist,
        }
    )
    clean_data["json_config"] = json.dumps(clean_data["json_config"])

    try:
        # 创建并启动数据清洗任务
        bkbase_result_table_id = api.bkdata.databus_cleans(**clean_data)["result_table_id"]
        api.bkdata.start_databus_cleans(result_table_id=bkbase_result_table_id, storages=["kafka"])
    except Exception as e:
        logger.error(
            "create or start data clean error, table_id: %s, params: %s, error: %s", table_id, json.dumps(clean_data), e
        )
        return {"err_msg": f"request clean api error, {e}"}

    # VM 存储接入处理
    try:
        storage_params = BkDataStorageWithDataID(bk_base_data.raw_data_id, raw_data_name, vm_cluster_name).value
        api.bkdata.create_data_storages(**storage_params)
        return {
            "clean_rt_id": f"{data_biz_id}_{raw_data_name}",
            "bk_data_id": bk_base_data.raw_data_id,
            "cluster_id": storage_cluster_id,
            "kafka_storage_exist": kafka_storage_exist,
        }
    except Exception as e:
        logger.error("create vm storage error, %s", e)
        return {"err_msg": f"request vm storage api error, {e}"}


def get_data_type_cluster(data_id: int) -> dict:
    from metadata.models import AccessVMRecord, BCSClusterInfo

    # NOTE: data id 不允许跨集群
    bcs_cluster = BCSClusterInfo.objects.filter(Q(K8sMetricDataID=data_id) | Q(CustomMetricDataID=data_id)).first()
    # 获取对应的类型
    data_type = AccessVMRecord.ACCESS_VM
    bcs_cluster_id = None
    if not bcs_cluster:
        data_type = AccessVMRecord.USER_CUSTOM
    elif bcs_cluster.K8sMetricDataID == data_id:
        data_type = AccessVMRecord.BCS_CLUSTER_K8S
        bcs_cluster_id = bcs_cluster.cluster_id
    else:
        data_type = AccessVMRecord.BCS_CLUSTER_CUSTOM
        bcs_cluster_id = bcs_cluster.cluster_id
    return {"data_type": data_type, "bcs_cluster_id": bcs_cluster_id}


def report_metadata_data_link_access_metric(
    version: str,
    status: int,
    biz_id: int,
    data_id: int,
    strategy: str,
) -> None:
    """
    上报接入链路相关指标
    @param version: 链路版本（V3/V4）
    @param status: 接入状态（失败-1/成功1） 以是否成功向bkbase发起请求为准
    @param biz_id: 业务ID
    @param data_id: 数据ID
    @param strategy: 链路策略（套餐类型）
    """
    try:
        logger.info("try to report metadata data link component status metric,data_id->[%s]", data_id)
        metrics.METADATA_DATA_LINK_ACCESS_TOTAL.labels(
            version=version, biz_id=biz_id, strategy=strategy, status=status
        ).inc()
        metrics.report_all()
    except Exception as err:  # pylint: disable=broad-except
        logger.error("report metadata data link access metric error->[%s],data_id->[%s]", err, data_id)
        return


def report_metadata_data_link_status_info(data_link_name: str, biz_id: str, kind: str, status: str):
    """
    上报数据链路状态信息
    @param data_link_name: 数据链路名称
    @param biz_id: 业务ID
    @param kind: 数据链路类型
    @param status: 数据链路状态
    """
    try:
        logger.info("try to report metadata data link status info,data_link_name->[%s]", data_link_name)
        status_number = DataLinkResourceStatus.get_choice_value(status)
        metrics.METADATA_DATA_LINK_STATUS_INFO.labels(data_link_name=data_link_name, biz_id=biz_id, kind=kind).set(
            status_number
        )
    except Exception as err:
        logger.error("report metadata data link status info error->[%s],data_link_name->[%s]", err, data_link_name)


def get_vm_cluster_id_name(
    bk_tenant_id: str, space_type: str | None = "", space_id: str | None = "", vm_cluster_name: str | None = ""
) -> dict:
    """获取 vm 集群 ID 和名称

    1. 如果 vm 集群名称存在，则需要查询到对应的ID，如果查询不到，则需要抛出异常
    2. 如果 vm 集群名称不存在，则需要查询空间是否已经接入过，如果已经接入过，则可以直接获取
    3. 如果没有接入过，则需要使用默认值
    """
    from metadata.models import ClusterInfo, SpaceVMInfo

    # vm 集群名称存在
    if vm_cluster_name:
        cluster = ClusterInfo.objects.filter(
            bk_tenant_id=bk_tenant_id, cluster_type=ClusterInfo.TYPE_VM, cluster_name=vm_cluster_name
        ).first()
        if not cluster:
            logger.error(
                "query vm cluster error, vm_cluster_name: %s not found, please register to clusterinfo", vm_cluster_name
            )
            raise ValueError(f"vm_cluster_name: {vm_cluster_name} not found")
        return {"cluster_id": cluster.cluster_id, "cluster_name": cluster.cluster_name}
    elif space_type and space_id:
        space_vm_info = SpaceVMInfo.objects.filter(space_type=space_type, space_id=space_id).first()
        if not space_vm_info:
            logger.warning("space_type: %s, space_id: %s not access vm", space_type, space_id)
        else:
            try:
                cluster = ClusterInfo.objects.get(bk_tenant_id=bk_tenant_id, cluster_id=space_vm_info.vm_cluster_id)
            except Exception:
                logger.error(
                    "space_type: %s, space_id: %s, cluster_id: %s not found",
                    space_type,
                    space_id,
                    space_vm_info.vm_cluster_id,
                )
                raise ValueError(f"space_type: {space_type}, space_id: {space_id} not found vm cluster")
            return {"cluster_id": cluster.cluster_id, "cluster_name": cluster.cluster_name}

    # 获取默认 VM 集群
    cluster = ClusterInfo.objects.filter(
        bk_tenant_id=bk_tenant_id, cluster_type=ClusterInfo.TYPE_VM, is_default_cluster=True
    ).first()
    if not cluster:
        logger.error("not found vm default cluster")
        raise ValueError("not found vm default cluster")
    return {"cluster_id": cluster.cluster_id, "cluster_name": cluster.cluster_name}


def get_bkbase_data_name_and_topic(table_id: str) -> dict:
    """获取 bkbase 的结果表名称"""
    # 如果以 '__default__'结尾，则取前半部分
    if table_id.endswith("__default__"):
        table_id = table_id.split(".__default__")[0]
    name = f"{table_id.replace('-', '_').replace('.', '_').replace('__', '_')[-40:]}"
    # NOTE: 清洗结果表不能出现双下划线
    vm_name = f"vm_{name}".replace("__", "_")
    # 兼容部分场景中划线和下划线允许同时存在的情况
    is_exist = AccessVMRecord.objects.filter(vm_result_table_id__contains=vm_name).exists()
    if is_exist:
        if len(vm_name) > 45:
            vm_name = vm_name[:45]
        vm_name = vm_name + "_add"

    return {"data_name": vm_name, "topic_name": f"{vm_name}{settings.DEFAULT_BKDATA_BIZ_ID}"}


def get_bcs_convergence_data_name_and_dp_id(table_id: str) -> dict:
    """获取 bcs 合流对应的结果表及数据处理 ID"""
    if table_id.endswith("__default__"):
        table_id = table_id.split(".__default__")[0]
    name = f"{table_id.replace('-', '_').replace('.', '_').replace('__', '_')[-40:]}"
    # NOTE: 清洗结果表不能出现双下划线
    return {"data_name": f"dp_{name}", "dp_id": f"{settings.DEFAULT_BKDATA_BIZ_ID}_{name}_dp_metric_all"}


def get_timestamp_len(data_id: int | None = None, etl_config: str | None = None) -> int:
    """通过 data id 或者 etl config 获取接入 vm 是清洗时间的长度

    1. 如果 data id 在指定的白名单中，则为 纳米
    2. 其它，则为 毫秒
    """
    logger.info("get_timestamp_len: data_id: %s, etl_config: %s", data_id, etl_config)
    if data_id and data_id in BKDATA_NS_TIMESTAMP_DATA_ID_LIST:
        return TimestampLen.NANOSECOND_LEN.value

    # Note: BCS集群接入场景时，由于事务中嵌套异步任务，可能导致数据未就绪
    # 新接入场景默认使用毫秒作为单位，若过程出现失败，直接返回默认单位，不应影响后续流程
    try:
        ds = DataSource.objects.get(bk_data_id=data_id)
        ds_option = DataSourceOption.objects.filter(bk_data_id=data_id, name=DataSourceOption.OPTION_ALIGN_TIME_UNIT)
        # 若存在对应配置项，优先使用配置的时间格式
        if ds_option.exists():
            logger.info("get_timestamp_len: ds_option exists,ds_option ALIGN_TIME)UNIT: %s", ds_option.first().value)
            return TimestampLen.get_len_choices(ds_option.first().value)
        # Note： 历史原因，针对脚本等配置，若不存在对应时间戳配置，默认单位应为秒
        if ds.etl_config in {EtlConfigs.BK_EXPORTER.value, EtlConfigs.BK_STANDARD.value}:
            logger.info("get_timestamp_len: ds.etl_config: %s,will use second as time format", ds.etl_config)
            return TimestampLen.SECOND_LEN.value
    except Exception as e:
        logger.error("get_timestamp_len:failed %s", e)
    return TimestampLen.MILLISECOND_LEN.value


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
def get_data_source(data_id):
    """
    根据 data_id 获取对应的 DataSource，重试三次，间隔1->2-4秒，规避事务未及时提交导致的查询失败问题
    """
    return DataSource.objects.get(bk_data_id=data_id)


def access_v2_bkdata_vm(bk_tenant_id: str, bk_biz_id: int, table_id: str, data_id: int):
    """
    接入计算平台V4链路

    该函数负责将数据源接入到VM(VictoriaMetrics)存储集群，并创建相应的数据链路。
    主要包括空间信息确认、VM集群信息获取、数据链路创建和联邦集群配置等步骤。

    @param bk_tenant_id: 租户ID，用于标识租户身份
    @param bk_biz_id: 业务ID，用于标识具体的业务
    @param table_id: 结果表ID，数据存储的表标识
    @param data_id: 数据源ID，数据来源的唯一标识
    """
    logger.info("bk_biz_id: %s, table_id: %s, data_id: %s start access v2 vm", bk_biz_id, table_id, data_id)

    from metadata.models import AccessVMRecord, DataSource, Space, SpaceVMInfo

    # 如果 bk_biz_id 为 0，则使用 tenant 默认的业务ID
    bk_biz_id = int(bk_biz_id)
    if bk_biz_id == 0:
        bk_biz_id = get_tenant_default_biz_id(bk_tenant_id)

    # 0. 确认空间信息
    # NOTE: 0 业务没有空间信息，不需要查询或者创建空间及空间关联的 vm
    space_data = {}
    try:
        # NOTE: 这里确保 bk_biz_id 为整型，获取业务对应的空间信息
        # 空间信息包含space_type和space_id，用于后续VM集群的选择和配置
        space_data = Space.objects.get_space_info_by_biz_id(int(bk_biz_id))
    except Exception as e:  # pylint: disable=broad-except
        logger.error("get space error by biz_id: %s, error: %s", bk_biz_id, e)

    # 步骤1: 获取VM集群信息
    # 根据租户ID、空间类型和空间ID来确定应该使用的VM存储集群
    # VM集群是实际存储时序数据的VictoriaMetrics集群
    vm_cluster = get_vm_cluster_id_name(
        bk_tenant_id=bk_tenant_id,
        space_type=space_data.get("space_type", ""),
        space_id=space_data.get("space_id", ""),
    )
    # 步骤1.1: 校验并创建空间与VM集群的关联记录
    # SpaceVMInfo用于记录空间与VM集群的映射关系，确保数据路由的正确性
    if (
        space_data
        and not SpaceVMInfo.objects.filter(
            space_type=space_data["space_type"], space_id=space_data["space_id"]
        ).exists()
    ):
        # 创建空间与VM集群的关联记录，建立数据存储的映射关系
        SpaceVMInfo.objects.create_record(
            space_type=space_data["space_type"], space_id=space_data["space_id"], vm_cluster_id=vm_cluster["cluster_id"]
        )

    try:
        # 步骤1.2: 获取数据源信息
        # NOTE: 由于事务和异步操作的原因，DataSource记录可能还未完全写入DB
        # 因此使用重试机制确保能够正确获取到数据源信息
        ds = get_data_source(data_id)
    except RetryError as e:
        logger.error("create vm data link error, get data_id: %s, error: %s", data_id, e.__cause__)
        return
    except DataSource.DoesNotExist:
        logger.error("create vm data link error, data_id: %s not found", data_id)
        return

    # 步骤2: 获取VM集群名称
    # 集群名称用于后续创建数据链路时指定目标存储集群
    vm_cluster_name = vm_cluster.get("cluster_name")

    # 步骤3: 获取数据源对应的BCS集群信息
    # 用于获取数据来源的Kubernetes集群ID，支持容器化环境的数据采集
    data_type_cluster = get_data_type_cluster(data_id=data_id)
    # 步骤4: 检查是否已经接入过VM
    # 如果该结果表已经创建过VM接入记录，则只需要创建联邦集群的数据链路
    # 联邦集群用于跨集群的数据汇聚和查询
    if AccessVMRecord.objects.filter(result_table_id=table_id).exists():
        logger.info("table_id: %s has already been created,now try to create fed vm data link", table_id)

        # 创建联邦集群的数据链路，实现跨集群数据汇聚
        create_fed_bkbase_data_link(
            bk_biz_id=bk_biz_id,
            monitor_table_id=table_id,
            data_source=ds,
            storage_cluster_name=vm_cluster_name,
            bcs_cluster_id=data_type_cluster["bcs_cluster_id"],
        )
        return

    # 步骤5: 创建VM数据链路
    # 这是主要的数据链路创建逻辑，将数据源接入到VM存储集群
    try:
        logger.info("access_v2_bkdata_vm: enable_v2_access_bkbase_method is True, now try to create bkbase data link")
        # 获取BCS集群ID，用于容器化环境的数据采集配置
        bcs_cluster_id = None
        bcs_record = BCSClusterInfo.objects.filter(K8sMetricDataID=ds.bk_data_id)
        if bcs_record:
            bcs_cluster_id = bcs_record.first().cluster_id

        # 创建基础的数据链路，建立从数据源到VM存储的完整链路
        create_bkbase_data_link(
            bk_biz_id=bk_biz_id,
            data_source=ds,
            monitor_table_id=table_id,
            storage_cluster_name=vm_cluster_name,
            bcs_cluster_id=bcs_cluster_id,
        )

        # 上报数据链路创建成功的指标，用于监控数据链路的创建状态
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V4_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_SUCCESS_STATUS,
            strategy=DataLink.BK_STANDARD_V2_TIME_SERIES,
        )
    except RetryError as e:
        # 处理重试失败的情况，通常是由于外部依赖服务不可用
        logger.error("create vm data link error, table_id: %s, data_id: %s, error: %s", table_id, data_id, e.__cause__)
        # 上报数据链路创建失败的指标
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V4_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_FAILURE_STATUS,
            strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES,
        )
        return
    except Exception as e:  # pylint: disable=broad-except
        # 处理其他所有异常情况，确保不会中断整个流程
        logger.error("create vm data link error, table_id: %s, data_id: %s, error: %s", table_id, data_id, e)
        # 上报数据链路创建失败的指标
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V4_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_FAILURE_STATUS,
            strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES,
        )
        return

    try:
        # 步骤6: 创建联邦集群数据链路
        # 联邦集群用于实现跨集群的数据汇聚和统一查询能力
        # 特别是在多集群BCS环境中，需要将各个集群的数据汇聚到统一的查询入口
        create_fed_bkbase_data_link(
            bk_biz_id=bk_biz_id,
            monitor_table_id=table_id,
            data_source=ds,
            storage_cluster_name=vm_cluster_name,
            bcs_cluster_id=data_type_cluster["bcs_cluster_id"],
        )
        # 上报联邦集群数据链路创建成功的指标
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V4_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_SUCCESS_STATUS,
            strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES,
        )
    except Exception as e:  # pylint: disable=broad-except
        # 联邦集群创建失败不影响基础数据链路的正常使用
        logger.error("create fed vm data link error, table_id: %s, data_id: %s, error: %s", table_id, data_id, e)
        # 上报联邦集群数据链路创建失败的指标
        report_metadata_data_link_access_metric(
            version=DATA_LINK_V4_VERSION_NAME,
            data_id=data_id,
            biz_id=bk_biz_id,
            status=ACCESS_DATA_LINK_FAILURE_STATUS,
            strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES,
        )
        return


def create_bkbase_data_link(
    bk_biz_id: int,
    data_source: DataSource,
    monitor_table_id: str,
    storage_cluster_name: str,
    data_link_strategy: str = DataLink.BK_STANDARD_V2_TIME_SERIES,
    namespace: str | None = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
    bcs_cluster_id: str | None = None,
):
    """
    申请计算平台链路
    @param bk_biz_id: 业务ID
    @param data_source: 数据源
    @param monitor_table_id: 监控平台自身结果表ID
    @param storage_cluster_name: 存储集群名称
    @param data_link_strategy: 链路策略
    @param namespace: 命名空间
    @param bcs_cluster_id: BCS集群ID
    """
    logger.info(
        "create_bkbase_data_link:try to access bkbase,data_id->[%s],storage_cluster_name->[%s],data_link_strategy->["
        "%s],namespace->[%s]",
        data_source.bk_data_id,
        storage_cluster_name,
        data_link_strategy,
        namespace,
    )
    # 0. 组装生成计算平台侧需要的data_name和rt_name
    bkbase_data_name = compose_bkdata_data_id_name(data_name=data_source.data_name)
    bkbase_rt_name = compose_bkdata_table_id(table_id=monitor_table_id)
    logger.info(
        "create_bkbase_data_link:try to access bkbase , data_id->[%s],bkbase_data_name->[%s],bkbase_vmrt_name->[%s]",
        data_source.bk_data_id,
        bkbase_data_name,
        bkbase_rt_name,
    )

    # 1. 判断是否是联邦代理集群链路
    if BcsFederalClusterInfo.objects.filter(fed_cluster_id=bcs_cluster_id, is_deleted=False).exists():
        logger.info("create_bkbase_data_link: bcs_cluster_id->[%s] is a federal proxy cluster!", bcs_cluster_id)
        data_link_strategy = DataLink.BCS_FEDERAL_PROXY_TIME_SERIES

    # TODO: 优化为MAP形式选取
    if data_source.etl_config == EtlConfigs.BK_EXPORTER.value:
        data_link_strategy = DataLink.BK_EXPORTER_TIME_SERIES
    elif data_source.etl_config == EtlConfigs.BK_STANDARD.value:
        data_link_strategy = DataLink.BK_STANDARD_TIME_SERIES

    # 2. 创建链路资源对象
    data_link_ins, _ = DataLink.objects.get_or_create(
        bk_tenant_id=data_source.bk_tenant_id,
        data_link_name=bkbase_data_name,
        namespace=namespace,
        data_link_strategy=data_link_strategy,
    )
    try:
        # 2. 尝试根据套餐，申请创建链路
        logger.info(
            "create_bkbase_data_link:try to access bkbase,data_id->[%s],storage_cluster_name->[%s],"
            "data_link_strategy->[%s],"
            "namespace->[%s]，monitor_table_id->[%s]",
            data_source.bk_data_id,
            storage_cluster_name,
            data_link_strategy,
            namespace,
            monitor_table_id,
        )
        data_link_ins.apply_data_link(
            bk_biz_id=bk_biz_id,
            data_source=data_source,
            table_id=monitor_table_id,
            storage_cluster_name=storage_cluster_name,
        )
        # 2.1 上报链路接入指标
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            "create_bkbase_data_link: access bkbase error, data_id->[%s],storage_cluster_name->[%s],"
            "data_link_strategy->["
            "%s],namespace->[%s],error->[%s]",
            data_source.bk_data_id,
            storage_cluster_name,
            data_link_strategy,
            namespace,
            e,
        )
        raise e

    logger.info(
        "create_bkbase_data_link:try to sync metadata,data_id->[%s],storage_cluster_name->[%s],data_link_strategy->["
        "%s],"
        "namespace->[%s]，monitor_table_id->[%s]",
        data_source.bk_data_id,
        storage_cluster_name,
        data_link_strategy,
        namespace,
        monitor_table_id,
    )
    # 3. 同步更新元数据
    data_link_ins.sync_metadata(
        data_source=data_source,
        table_id=monitor_table_id,
        storage_cluster_name=storage_cluster_name,
    )

    # TODO：路由双写至旧的AccessVMRecord，完成灰度验证后，统一迁移至新表后删除
    storage_cluster_id = ClusterInfo.objects.get(
        bk_tenant_id=data_source.bk_tenant_id, cluster_name=storage_cluster_name
    ).cluster_id
    logger.info(
        "create_bkbase_data_link:try to write AccessVMRecord,data_id->[%s],storage_cluster_id->[%s],"
        "data_link_strategy->[%s]",
        data_source.bk_data_id,
        storage_cluster_id,
        data_link_strategy,
    )
    datalink_biz_id = get_tenant_datalink_biz_id(bk_tenant_id=data_source.bk_tenant_id, bk_biz_id=bk_biz_id)
    AccessVMRecord.objects.update_or_create(
        bk_tenant_id=data_source.bk_tenant_id,
        result_table_id=monitor_table_id,
        bk_base_data_id=data_source.bk_data_id,
        bk_base_data_name=bkbase_data_name,
        defaults={
            "vm_cluster_id": storage_cluster_id,
            "vm_result_table_id": f"{datalink_biz_id.data_biz_id}_{bkbase_rt_name}",
            "bcs_cluster_id": bcs_cluster_id,
        },
    )
    logger.info(
        "create_bkbase_data_link:access bkbase success,data_id->[%s],storage_cluster_name->[%s],data_link_strategy->["
        "%s]",
        data_source.bk_data_id,
        storage_cluster_name,
        data_link_strategy,
    )


def create_fed_bkbase_data_link(
    bk_biz_id: int,
    monitor_table_id: str,
    data_source: DataSource,
    storage_cluster_name: str,
    bcs_cluster_id: str,
    namespace: str | None = settings.DEFAULT_VM_DATA_LINK_NAMESPACE,
):
    """
    创建联邦集群汇聚链路（子集群->代理集群）
    """
    from metadata.models import BcsFederalClusterInfo
    from metadata.models.data_link.utils import is_k8s_metric_data_id

    logger.info(
        "create_fed_bkbase_data_link: bcs_cluster_id->[%s],data_id->[%s] start to create fed_bkbase_data_link",
        bcs_cluster_id,
        data_source.bk_data_id,
    )
    federal_records = BcsFederalClusterInfo.objects.filter(sub_cluster_id=bcs_cluster_id, is_deleted=False)

    # 若不存在对应联邦集群记录 / 非K8S内建指标数据，直接返回
    if not (federal_records.exists() and is_k8s_metric_data_id(data_name=data_source.data_name)):
        logger.info(
            "create_fed_bkbase_data_link: bcs_cluster_id->[%s],data_id->[%s] does not belong to any federal "
            "topo,return",
            bcs_cluster_id,
            data_source.bk_data_id,
        )
        return

    bkbase_data_name = compose_bkdata_data_id_name(
        data_name=data_source.data_name, strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES
    )
    # bkbase_rt_name = compose_bkdata_table_id(table_id=monitor_table_id)

    logger.info(
        "create_fed_bkbase_data_link: bcs_cluster_id->[%s],data_id->[%s],data_link_name->[%s] try to create "
        "fed_bkbase_data_link",
        bcs_cluster_id,
        data_source.bk_data_id,
        bkbase_data_name,
    )
    data_link_ins, _ = DataLink.objects.get_or_create(
        bk_tenant_id=data_source.bk_tenant_id,
        data_link_name=bkbase_data_name,
        namespace=namespace,
        data_link_strategy=DataLink.BCS_FEDERAL_SUBSET_TIME_SERIES,
    )

    try:
        logger.info(
            "create_fed_bkbase_data_link: bcs_cluster_id->[%s],data_id->[%s],table_id->[%s],data_link_name->[%s] try "
            "to access bkdata",
            bcs_cluster_id,
            data_source.bk_data_id,
            monitor_table_id,
            bkbase_data_name,
        )
        data_link_ins.apply_data_link(
            bk_biz_id=bk_biz_id,
            data_source=data_source,
            table_id=monitor_table_id,
            storage_cluster_name=storage_cluster_name,
            bcs_cluster_id=bcs_cluster_id,
        )
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            "create_bkbase_data_link: access bkbase error, data_id->[%s],data_link_name->[%s],bcs_cluster_id->[%s],"
            "storage_cluster_name->[%s],namespace->[%s],error->[%s]",
            data_source.bk_data_id,
            bkbase_data_name,
            bcs_cluster_id,
            storage_cluster_name,
            namespace,
            e,
        )
        raise e

    data_link_ins.sync_metadata(
        data_source=data_source,
        table_id=monitor_table_id,
        storage_cluster_name=storage_cluster_name,
    )
    logger.info(
        "create_fed_bkbase_data_link: data_link_name->[%s],data_id->[%s],bcs_cluster_id->[%s],storage_cluster_name->["
        "%s] create fed datalink successfully",
        bkbase_data_name,
        data_source.bk_data_id,
        bcs_cluster_id,
        storage_cluster_name,
    )
