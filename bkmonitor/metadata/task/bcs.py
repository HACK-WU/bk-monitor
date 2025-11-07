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
import itertools
import logging
import time

from django.conf import settings

from alarm_backends.core.lock.service_lock import share_lock
from alarm_backends.service.scheduler.app import app
from bkmonitor.utils.tenant import bk_biz_id_to_bk_tenant_id
from core.drf_resource import api
from core.prometheus import metrics
from metadata import models
from metadata.config import PERIODIC_TASK_DEFAULT_TTL
from metadata.models.bcs.resource import (
    BCSClusterInfo,
    PodMonitorInfo,
    ServiceMonitorInfo,
)
from metadata.task.tasks import bulk_create_fed_data_link
from metadata.tools.constants import TASK_FINISHED_SUCCESS, TASK_STARTED
from metadata.utils.bcs import change_cluster_router, get_bcs_dataids

logger = logging.getLogger("metadata")

BCS_SYNC_SYNC_CONCURRENCY = 20
CMDB_IP_SEARCH_MAX_SIZE = 100


@share_lock(ttl=PERIODIC_TASK_DEFAULT_TTL, identify="metadata_refreshBCSMonitorInfo")
def refresh_bcs_monitor_info():
    """
    刷新BCS集群监控信息

    该函数用于定时刷新BCS集群的监控资源配置，包括：
    1. 获取联邦集群信息并进行异常处理
    2. 查询运行中的BCS集群并按优先级排序
    3. 遍历集群刷新内置和自定义监控资源
    4. 同步联邦集群记录
    5. 上报任务状态和耗时指标

    参数:
        无

    返回值:
        无

    执行流程：
    1. 初始化指标统计并记录任务开始时间
    2. 获取所有租户下的联邦集群信息
    3. 查询运行中的BCS集群并按是否为联邦集群排序
    4. 遍历集群执行以下操作：
       - 刷新集群内置公共dataid资源
       - 刷新ServiceMonitor和PodMonitor资源
       - 刷新自定义dataid资源配置
       - 若为联邦集群则同步集群记录
    5. 记录任务耗时并上报指标
    """
    # 统计&上报 任务状态指标
    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="refresh_bcs_monitor_info", status=TASK_STARTED, process_target=None
    ).inc()
    start_time = time.time()
    fed_clusters = {}
    fed_cluster_id_list = []
    try:
        for tenant in api.bk_login.list_tenant():
            fed_clusters.update(api.bcs.get_federation_clusters(bk_tenant_id=tenant["id"]))
            fed_cluster_id_list.extend(list(fed_clusters.keys()))
    except Exception as e:  # pylint: disable=broad-except
        fed_cluster_id_list = []
        logger.error(f"get federation clusters failed: {e}")

    bcs_clusters = list(
        BCSClusterInfo.objects.filter(
            status__in=[models.BCSClusterInfo.CLUSTER_STATUS_RUNNING, models.BCSClusterInfo.CLUSTER_RAW_STATUS_RUNNING],
        )
    )

    # 对 bcs_clusters 进行排序，确保 fed_cluster_id_list 中的集群优先
    bcs_clusters = sorted(bcs_clusters, key=lambda x: x.cluster_id not in fed_cluster_id_list)

    # 拉取所有cluster，遍历刷新monitorinfo信息
    for cluster in bcs_clusters:
        try:
            is_fed_cluster = cluster.cluster_id in fed_cluster_id_list
            # 刷新集群内置公共dataid resource
            cluster.refresh_common_resource(is_fed_cluster=is_fed_cluster)
            logger.debug(f"refresh bcs common resource in cluster:{cluster.cluster_id} done")

            # 查找新的monitor info并记录到数据库，删除已不存在的
            ServiceMonitorInfo.refresh_resource(cluster.cluster_id, cluster.CustomMetricDataID)
            logger.debug(f"refresh bcs service monitor resource in cluster:{cluster.cluster_id} done")
            PodMonitorInfo.refresh_resource(cluster.cluster_id, cluster.CustomMetricDataID)
            logger.debug(f"refresh bcs pod monitor resource in cluster:{cluster.cluster_id} done")

            # 刷新配置了自定义dataid的dataid resource
            ServiceMonitorInfo.refresh_custom_resource(cluster_id=cluster.cluster_id)
            logger.debug(f"refresh bcs service monitor custom resource in cluster:{cluster.cluster_id} done")
            PodMonitorInfo.refresh_custom_resource(cluster_id=cluster.cluster_id)
            logger.debug(f"refresh bcs pod monitor custom resource in cluster:{cluster.cluster_id} done")
            if is_fed_cluster:
                # 更新联邦集群记录
                try:
                    sync_federation_clusters(fed_clusters)
                except Exception as e:  # pylint: disable=broad-except
                    logger.error(f"sync_federation_clusters failed, error:{e}")

        except Exception:  # noqa
            logger.exception("refresh bcs monitor info failed, cluster_id(%s)", cluster.cluster_id)

    cost_time = time.time() - start_time

    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="refresh_bcs_monitor_info", status=TASK_FINISHED_SUCCESS, process_target=None
    ).inc()
    # 统计耗时，并上报指标
    metrics.METADATA_CRON_TASK_COST_SECONDS.labels(task_name="refresh_bcs_monitor_info", process_target=None).observe(
        cost_time
    )
    metrics.report_all()
    logger.info("refresh_bcs_monitor_info: task finished, cost time->[%s] seconds", cost_time)


@app.task(ignore_result=True, queue="celery_cron")
def refresh_dataid_resource(cluster_id, data_id):
    ServiceMonitorInfo.refresh_resource(cluster_id, data_id)
    PodMonitorInfo.refresh_resource(cluster_id, data_id)


@share_lock(ttl=PERIODIC_TASK_DEFAULT_TTL, identify="metadata_refreshBCSMetricsInfo")
def refresh_bcs_metrics_label():
    """
    刷新BCS集群监控指标label
    """

    # 统计&上报 任务状态指标
    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="refresh_bcs_metrics_label", status=TASK_STARTED, process_target=None
    ).inc()
    start_time = time.time()
    logger.info("start refresh bcs metrics label")
    # 获取所有bcs相关dataid
    data_ids, data_id_cluster_map = get_bcs_dataids()
    logger.info(f"get bcs dataids->{data_ids}")

    # 基于dataid过滤出自定义指标group_id
    time_series_group_ids = [
        item["time_series_group_id"]
        for item in models.TimeSeriesGroup.objects.filter(bk_data_id__in=data_ids, is_delete=False).values(
            "time_series_group_id"
        )
    ]

    # 基于group_id拿到对应的指标项
    bcs_metrics = [
        item
        for item in models.TimeSeriesMetric.objects.filter(label="").values(
            "field_name", "field_id", "label", "group_id"
        )
    ]

    kubernetes_field_ids = []
    non_kubernetes_field_ids = []

    # 遍历指标组
    for metric in bcs_metrics:
        # 若非容器指标，则打上custom标签
        if metric["group_id"] not in time_series_group_ids:
            non_kubernetes_field_ids.append(metric["field_id"])
        else:
            kubernetes_field_ids.append(metric["field_id"])

    # 更新指标label
    if kubernetes_field_ids:
        models.TimeSeriesMetric.objects.filter(field_id__in=kubernetes_field_ids).update(label="kubernetes")

    if non_kubernetes_field_ids:
        models.TimeSeriesMetric.objects.filter(field_id__in=non_kubernetes_field_ids).update(label="custom")

    cost_time = time.time() - start_time

    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="refresh_bcs_metrics_label", status=TASK_FINISHED_SUCCESS, process_target=None
    ).inc()
    # 统计耗时，上报指标
    metrics.METADATA_CRON_TASK_COST_SECONDS.labels(task_name="refresh_bcs_metrics_label", process_target=None).observe(
        cost_time
    )
    metrics.report_all()
    logger.info("refresh bcs metrics label done,use->[%s] seconds", cost_time)


@share_lock(ttl=3600, identify="metadata_discoverBCSClusters")
def discover_bcs_clusters():
    """
    BCS集群同步周期任务,调用BCS侧API全量拉取集群信息（包含联邦集群）,并进行同步逻辑

    该函数实现以下核心功能：
    1. 获取所有租户并遍历处理
    2. 调用BCS API获取租户下的K8S集群列表
    3. 获取联邦集群信息并调整排序（联邦集群优先处理）
    4. 处理BCS集群信息，包含：
       - 集群信息变更检测（状态/API密钥/业务ID/项目ID）
       - 云区域ID更新
       - 联邦集群关系同步
       - 集群资源初始化
    5. 清理已删除集群（排除始终运行的假集群）
    6. 统计任务耗时并上报监控指标

    参数:
        无显式参数（由定时任务触发）

    返回值:
        None（异常情况下可能提前返回）
    """

    def _init_bcs_cluster_resource(cluster: BCSClusterInfo, is_fed_cluster: bool) -> tuple[bool, Exception | None]:
        """
        初始化 BCS 集群资源
        """
        try:
            init_result = cluster.init_resource(is_fed_cluster=is_fed_cluster)
            return init_result, None
        except Exception as e:  # pylint: disable=broad-except
            return False, e

    # 统计&上报 任务状态指标
    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="discover_bcs_clusters", status=TASK_STARTED, process_target=None
    ).inc()

    # 记录任务开始时间，用于计算执行耗时
    start_time = time.time()
    logger.info("discover_bcs_clusters: start to discover bcs clusters")

    # 初始化集群列表，用于记录所有活跃的集群ID
    cluster_list: list[str] = []
    # 遍历所有租户，获取每个租户下的BCS集群信息
    for tenant in api.bk_login.list_tenant():
        bk_tenant_id = tenant["id"]
        try:
            # 调用BCS API获取租户下的K8S集群列表
            # 注意：BCS API仅返回非DELETED状态的集群
            bcs_clusters = api.kubernetes.fetch_k8s_cluster_list(bk_tenant_id=bk_tenant_id)
        except Exception as e:  # pylint: disable=broad-except
            logger.error(f"discover_bcs_clusters: get bcs clusters failed, error:{e}")
            return

        # 获取联邦集群信息并调整排序（联邦集群优先处理）
        fed_clusters = {}
        try:
            # 获取当前租户下的联邦集群拓扑信息
            fed_clusters = api.bcs.get_federation_clusters(bk_tenant_id=bk_tenant_id)
            fed_cluster_id_list = list(fed_clusters.keys())  # 联邦的代理集群列表
        except Exception as e:  # pylint: disable=broad-except
            fed_cluster_id_list = []
            logger.warning(f"discover_bcs_clusters: get federation clusters failed, error:{e}")

        # 联邦集群排序前置（创建链路依赖联邦关系记录）
        # 确保联邦集群优先处理，因为子集群的数据链路依赖联邦集群的配置
        bcs_clusters = sorted(bcs_clusters, key=lambda x: x["cluster_id"] not in fed_cluster_id_list)

        # 处理BCS集群信息，更新或注册新集群
        for bcs_cluster in bcs_clusters:
            logger.info("discover_bcs_clusters: get bcs cluster:{},start to register".format(bcs_cluster["cluster_id"]))
            project_id = bcs_cluster["project_id"]
            bk_biz_id = int(bcs_cluster["bk_biz_id"])

            # 对 业务ID 进行二次校验
            try:
                bk_biz_id_tenant_id = bk_biz_id_to_bk_tenant_id(bk_biz_id)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    f"discover_bcs_clusters: cluster_id:{bcs_cluster['cluster_id']} bk_biz_id:{bk_biz_id} get bk_tenant_id failed, error:{e}"
                )
                continue

            if bk_biz_id_tenant_id != bk_tenant_id:
                logger.error(
                    f"discover_bcs_clusters: cluster_id:{bcs_cluster['cluster_id']} bk_biz_id:{bk_biz_id} not belong to bk_tenant_id:{bk_tenant_id}"
                )
                continue

            cluster_id = bcs_cluster["cluster_id"]
            cluster_raw_status = bcs_cluster["status"]
            cluster_list.append(cluster_id)

            # 判断是否为联邦集群
            is_fed_cluster = cluster_id in fed_cluster_id_list

            # 检测集群是否已存在于数据库中（支持集群迁移场景）
            cluster = BCSClusterInfo.objects.filter(cluster_id=cluster_id).first()
            if cluster:
                # 更新集群信息，兼容集群迁移场景
                # 场景1:集群迁移业务，项目ID不变，只会变业务ID
                # 场景2:集群迁移项目，项目ID和业务ID都可能变化
                update_fields: set[str] = set()

                # 如果集群状态为初始化失败，则重试
                if cluster.status == BCSClusterInfo.CLUSTER_STATUS_INIT_FAILED:
                    init_result, err = _init_bcs_cluster_resource(cluster, is_fed_cluster=is_fed_cluster)
                    if init_result:
                        logger.info(
                            f"cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} retry init resource success"
                        )
                        update_fields.add("status")
                        cluster.status = BCSClusterInfo.CLUSTER_RAW_STATUS_RUNNING
                    else:
                        logger.error(
                            f"cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} retry init resource failed, error:{err}"
                        )

                # NOTE: 现阶段完全以 BCS 的集群状态为准，如果集群初始化状态为失败，则不更新
                if cluster_raw_status != cluster.status and cluster.status != BCSClusterInfo.CLUSTER_STATUS_INIT_FAILED:
                    cluster.status = cluster_raw_status
                    update_fields.add("status")

                # 检查BCS API Token是否需要更新
                # 如果 BCS Token 变了需要刷新，确保API调用正常
                if cluster.api_key_content != settings.BCS_API_GATEWAY_TOKEN:
                    cluster.api_key_content = settings.BCS_API_GATEWAY_TOKEN
                    update_fields.add("api_key_content")

                # 处理业务ID变更场景（支持集群在不同业务间迁移）
                if int(bk_biz_id) != cluster.bk_biz_id:
                    # 记录旧业务ID，用于路由信息变更
                    old_bk_biz_id = cluster.bk_biz_id
                    cluster.bk_biz_id = int(bk_biz_id)
                    update_fields.add("bk_biz_id")

                    # 若业务ID变更，其RT对应的业务ID也应一并变更
                    logger.info(
                        f"discover_bcs_clusters: cluster_id:{cluster_id},project_id:{project_id} change bk_biz_id to {int(bk_biz_id)}"
                    )

                    # 变更对应的路由元信息
                    # 更新数据源路由配置，确保监控数据能正确路由到新业务
                    change_cluster_router(
                        cluster=cluster,
                        old_bk_biz_id=old_bk_biz_id,
                        new_bk_biz_id=bk_biz_id,
                        is_fed_cluster=is_fed_cluster,
                    )

                # 处理项目ID变更场景
                if project_id != cluster.project_id:
                    cluster.project_id = project_id
                    update_fields.add("project_id")

                # 执行数据库更新操作
                if update_fields:
                    # 添加修改时间字段，记录变更时间
                    update_fields.add("last_modify_time")
                    cluster.save(update_fields=list(update_fields))

                # 更新云区域ID配置（如果尚未配置）
                if cluster.bk_cloud_id is None:
                    # 通过集群节点信息自动推断云区域ID
                    update_bcs_cluster_cloud_id_config(bk_biz_id, cluster_id)

                # 同步联邦集群关系
                if is_fed_cluster:
                    # 为联邦集群创建或更新相关记录
                    try:
                        sync_federation_clusters(fed_clusters)
                    except Exception as e:  # pylint: disable=broad-except
                        logger.warning(f"discover_bcs_clusters: sync_federation_clusters failed, error:{e}")

                logger.info(f"cluster_id:{cluster_id},project_id:{project_id} already exists,skip create it")
                continue

            # 注册新集群到元数据系统
            # 为新发现的集群创建数据库记录和相关监控资源
            cluster = BCSClusterInfo.register_cluster(
                bk_tenant_id=bk_tenant_id,
                bk_biz_id=bk_biz_id,
                cluster_id=cluster_id,
                project_id=project_id,
                creator="admin",
                is_fed_cluster=is_fed_cluster,
            )
            logger.info(
                f"discover_bcs_clusters: cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} registered"
            )

            # 初始化集群资源
            init_result, err = _init_bcs_cluster_resource(cluster, is_fed_cluster=is_fed_cluster)
            if init_result:
                logger.info(
                    f"cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} init resource success"
                )
            else:
                cluster.status = BCSClusterInfo.CLUSTER_STATUS_INIT_FAILED
                cluster.save(update_fields=["status"])
                logger.error(
                    f"cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} init resource failed, error:{err}"
                )
                continue

            # 更新云区域ID配置
            # 通过集群节点信息自动推断并设置云区域ID
            update_bcs_cluster_cloud_id_config(bk_biz_id, cluster_id)

            logger.info(
                f"cluster_id:{cluster.cluster_id},project_id:{cluster.project_id},bk_biz_id:{cluster.bk_biz_id} init resource finished"
            )

    # 清理已删除集群（排除始终运行的假集群）
    if cluster_list:
        logger.info(
            "discover_bcs_clusters: enable always running fake clusters->[%s]",
            settings.ALWAYS_RUNNING_FAKE_BCS_CLUSTER_ID_LIST,
        )
        # 将配置的假集群ID添加到活跃集群列表中，避免被误删
        cluster_list.extend(settings.ALWAYS_RUNNING_FAKE_BCS_CLUSTER_ID_LIST)

        # 将不在活跃集群列表中的集群状态标记为已删除
        # 这样可以保持历史数据，同时标识集群已不可用
        BCSClusterInfo.objects.exclude(cluster_id__in=cluster_list).update(
            status=BCSClusterInfo.CLUSTER_RAW_STATUS_DELETED
        )

    # 统计任务耗时并上报监控指标
    cost_time = time.time() - start_time
    logger.info("discover_bcs_clusters finished, cost time->[%s]", cost_time)

    # 上报任务成功完成状态指标
    metrics.METADATA_CRON_TASK_STATUS_TOTAL.labels(
        task_name="discover_bcs_clusters", status=TASK_FINISHED_SUCCESS, process_target=None
    ).inc()

    # 上报任务执行耗时指标，用于性能监控和优化
    metrics.METADATA_CRON_TASK_COST_SECONDS.labels(task_name="refresh_bcs_monitor_info", process_target=None).observe(
        cost_time
    )

    # 将所有指标数据上报到监控系统
    metrics.report_all()


def update_bcs_cluster_cloud_id_config(bk_biz_id=None, cluster_id=None):
    """
    补齐云区域ID配置的主函数，通过BCS集群节点信息自动补全缺失的云区域ID

    参数:
        bk_biz_id: 业务ID，用于过滤特定业务的集群（可选）
        cluster_id: 集群ID，用于指定单个集群处理（可选）

    返回值:
        None: 函数通过直接修改数据库记录完成更新，无显式返回值

    处理流程包含以下核心步骤：
    1. 过滤出运行状态且缺失云区域ID的集群
    2. 并发请求BCS接口获取集群节点IP信息
    3. 通过CMDB接口查询节点IP对应的云区域信息
    4. 统计节点云区域分布并更新集群配置
    """
    # 获得缺失云区域的集群配置
    filter_kwargs = {}
    if bk_biz_id:
        filter_kwargs["bk_biz_id"] = bk_biz_id
    if cluster_id:
        filter_kwargs["cluster_id"] = cluster_id
    filter_kwargs.update(
        {
            "status__in": [BCSClusterInfo.CLUSTER_STATUS_RUNNING, BCSClusterInfo.CLUSTER_RAW_STATUS_RUNNING],
            "bk_cloud_id__isnull": True,
        }
    )
    clusters = BCSClusterInfo.objects.filter(**filter_kwargs).values("bk_tenant_id", "bk_biz_id", "cluster_id")

    # 分批次处理集群节点信息
    for start in range(0, len(clusters), BCS_SYNC_SYNC_CONCURRENCY):
        cluster_chunk = clusters[start : start + BCS_SYNC_SYNC_CONCURRENCY]
        # 从BCS获取集群的节点IP
        params: dict[str, tuple[str, int]] = {
            cluster["cluster_id"]: (cluster["bk_tenant_id"], cluster["bk_biz_id"]) for cluster in cluster_chunk
        }
        bulk_request_params = [
            {"bcs_cluster_id": bcs_cluster_id, "bk_tenant_id": bk_tenant_id}
            for bcs_cluster_id, (bk_tenant_id, _) in params.items()
        ]
        try:
            api_nodes = api.kubernetes.fetch_k8s_node_list_by_cluster.bulk_request(
                bulk_request_params, ignore_exceptions=True
            )
        except Exception as exc_info:  # noqa
            logger.exception(exc_info)
            continue

        # 构建节点IP与业务/集群的映射关系
        node_ip_map = {}
        for node in itertools.chain.from_iterable(item for item in api_nodes if item):
            bcs_cluster_id = node["bcs_cluster_id"]
            if not params.get(bcs_cluster_id):
                continue
            bk_biz_id = params[bcs_cluster_id][1]
            node_ip = node["node_ip"]
            if not node_ip:
                continue
            node_ip_map.setdefault(bk_biz_id, {}).setdefault(bcs_cluster_id, []).append(node_ip)

        # 构造CMDB查询参数
        cmdb_params = []
        for bk_biz_id, cluster_info in node_ip_map.items():
            for node_ips in cluster_info.values():
                # 防止ip过多超过接口限制
                node_ips = node_ips[:CMDB_IP_SEARCH_MAX_SIZE]
                cmdb_params.append(
                    {
                        "bk_biz_id": bk_biz_id,
                        "ips": [
                            {
                                "ip": ip,
                            }
                            for ip in node_ips
                        ],
                    }
                )
        if not cmdb_params:
            continue

        # 从CMDB获取主机云区域信息
        try:
            host_infos = api.cmdb.get_host_by_ip.bulk_request(cmdb_params)
        except Exception as exc_info:  # noqa
            logger.exception(exc_info)
            continue

        # 构建IP到云区域ID的映射表
        bk_cloud_map = {}
        for item in itertools.chain.from_iterable(host_info_chunk for host_info_chunk in host_infos if host_info_chunk):
            ip_map = {}
            if item.bk_host_innerip:
                ip_map[item.bk_host_innerip] = item.bk_cloud_id
            if item.bk_host_innerip_v6:
                ip_map[item.bk_host_innerip_v6] = item.bk_cloud_id
            bk_cloud_map.setdefault(item.bk_biz_id, {}).update(ip_map)

        # 计算集群云区域分布
        update_params = {}
        for bk_biz_id, cluster_info in node_ip_map.items():
            for bcs_cluster_id, node_ips in cluster_info.items():
                # 获取节点IP对应的云区域ID
                bk_cloud_ids = []
                for node_ip in node_ips:
                    bk_cloud_id = bk_cloud_map.get(bk_biz_id, {}).get(node_ip)
                    if bk_cloud_id is None:
                        continue
                    bk_cloud_ids.append(bk_cloud_id)
                if not bk_cloud_ids:
                    continue

                # 统计云区域计数并取最高频值
                counter = collections.Counter(bk_cloud_ids)
                most_common_bk_cloud_id = counter.most_common(1)[0][0]
                update_params.setdefault(most_common_bk_cloud_id, []).append(bcs_cluster_id)

        # 批量更新集群云区域配置
        for bk_cloud_id, bcs_cluster_ids in update_params.items():
            BCSClusterInfo.objects.filter(cluster_id__in=bcs_cluster_ids).update(bk_cloud_id=bk_cloud_id)


def sync_federation_clusters(fed_clusters):
    """
    同步联邦集群信息，创建或更新对应数据记录，并清理不再使用的旧记录

    参数:
        fed_clusters (dict): 联邦集群配置信息字典，格式为：
            {
                "fed_cluster_id": {
                    "host_cluster_id": str,
                    "sub_clusters": {
                        "sub_cluster_id": [namespace1, namespace2, ...]
                    }
                }
            }

    返回值:
        None: 此函数无返回值，仅执行同步操作并触发异步任务

    执行流程包括：
    1. 比较传入与现有联邦集群ID集合，删除不再存在的联邦集群记录
    2. 遍历最新联邦集群关系，同步其子集群及命名空间归属信息
    3. 对比数据库中已有记录，判断是否需要更新命名空间列表
    4. 若存在变更则更新或创建BcsFederalClusterInfo记录
    5. 清理不属于任何联邦集群的孤立子集群记录
    6. 触发异步任务批量创建联邦数据链路
    """
    logger.info("sync_federation_clusters:sync_federation_clusters started.")
    need_process_clusters = []  # 记录需要创建联邦汇聚链路的集群列表，统一进行异步操作
    try:
        # 获取传入数据中的所有联邦集群 ID
        fed_cluster_ids = set(fed_clusters.keys())

        # 获取数据库中现有的联邦集群 ID (排除软删除的记录)
        existing_fed_clusters = set(
            models.BcsFederalClusterInfo.objects.filter(is_deleted=False).values_list("fed_cluster_id", flat=True)
        )

        # 删除不再归属的联邦集群记录
        clusters_to_delete = existing_fed_clusters - fed_cluster_ids
        if clusters_to_delete:
            logger.info("sync_federation_clusters:Deleting federation cluster info for->[%s]", clusters_to_delete)
            models.BcsFederalClusterInfo.objects.filter(fed_cluster_id__in=clusters_to_delete).update(is_deleted=True)

        # 遍历最新的联邦集群关系
        for fed_cluster_id, fed_cluster_data in fed_clusters.items():
            logger.info("sync_federation_clusters:Syncing federation cluster ->[%s]", fed_cluster_id)

            host_cluster_id = fed_cluster_data["host_cluster_id"]
            sub_clusters = fed_cluster_data["sub_clusters"]

            # 获取代理集群的对应 RT 信息
            # 查询联邦集群对应的指标和事件数据ID及表ID，用于后续创建联邦记录
            cluster = models.BCSClusterInfo.objects.get(cluster_id=fed_cluster_id)
            fed_builtin_k8s_metric_data_id = cluster.K8sMetricDataID
            fed_builtin_k8s_event_data_id = cluster.K8sEventDataID

            fed_builtin_metric_table_id = models.DataSourceResultTable.objects.get(
                bk_data_id=fed_builtin_k8s_metric_data_id
            ).table_id
            fed_builtin_event_table_id = models.DataSourceResultTable.objects.get(
                bk_data_id=fed_builtin_k8s_event_data_id
            ).table_id

            # 遍历每个子集群，处理命名空间归属
            for sub_cluster_id, namespaces in sub_clusters.items():
                logger.info(
                    "sync_federation_clusters:Syncing sub-cluster -> [%s],namespaces->[%s]", sub_cluster_id, namespaces
                )
                if namespaces is None:
                    logger.info(
                        "sync_federation_clusters:Skipping sub-cluster->[%s] as namespaces is None", sub_cluster_id
                    )
                    continue

                # 获取现有的命名空间记录（当前数据库中已存在的子集群记录，排除软删除的记录）
                existing_records = models.BcsFederalClusterInfo.objects.filter(
                    fed_cluster_id=fed_cluster_id, sub_cluster_id=sub_cluster_id, is_deleted=False
                )

                # 获取现有的命名空间列表
                if existing_records.exists():
                    current_namespaces = existing_records.first().fed_namespaces
                else:
                    current_namespaces = []

                # 直接覆盖更新命名空间列表
                updated_namespaces = list(set(namespaces))

                # 如果数据库中的记录与更新的数据一致，跳过更新
                if set(updated_namespaces) == set(current_namespaces):
                    logger.info(
                        "sync_federation_clusters:Sub-cluster->[%s] in federation->[%s] is already up-to-date,skipping",
                        sub_cluster_id,
                        fed_cluster_id,
                    )
                    continue

                # 如果命名空间有变更，更新记录
                logger.info(
                    "sync_federation_clusters:Updating namespaces for sub-cluster->[%s],in federation->[%s]",
                    sub_cluster_id,
                    fed_cluster_id,
                )

                # 更新或创建联邦集群信息记录，包含联邦集群ID、主机集群ID、子集群ID和命名空间信息
                models.BcsFederalClusterInfo.objects.update_or_create(
                    fed_cluster_id=fed_cluster_id,
                    host_cluster_id=host_cluster_id,
                    sub_cluster_id=sub_cluster_id,
                    defaults={
                        "fed_namespaces": updated_namespaces,
                        "fed_builtin_metric_table_id": fed_builtin_metric_table_id,
                        "fed_builtin_event_table_id": fed_builtin_event_table_id,
                    },
                )

                # 记录需要处理的子集群，后续统一异步创建联邦链路
                need_process_clusters.append(sub_cluster_id)
                logger.info(
                    "sync_federation_clusters:Updated federation cluster info for sub-cluster->[%s] in fed->[%s] "
                    "successfully，will create fed data_link later",
                    sub_cluster_id,
                    fed_cluster_id,
                )

        # 查找哪些子集群的联邦集群信息不再存在于传入的 fed_clusters 中
        all_sub_clusters_in_fed_clusters = {
            (fed_cluster_id, sub_cluster_id)
            for fed_cluster_id, fed_cluster_data in fed_clusters.items()
            for sub_cluster_id in fed_cluster_data["sub_clusters"].keys()
        }

        # 获取数据库中所有子集群的记录（排除软删除的记录）
        existing_sub_clusters = models.BcsFederalClusterInfo.objects.filter(is_deleted=False).values_list(
            "fed_cluster_id", "sub_cluster_id"
        )

        # 找出不再归属任何联邦集群的子集群记录
        sub_clusters_to_delete = set(existing_sub_clusters) - all_sub_clusters_in_fed_clusters

        if sub_clusters_to_delete:
            logger.info(
                "sync_federation_clusters:Deleting sub-clusters that are no longer part of any federation->[%s]",
                sub_clusters_to_delete,
            )
            # 使用动态条件生成过滤器来删除记录
            for sub_cluster_id in sub_clusters_to_delete:
                models.BcsFederalClusterInfo.objects.filter(
                    fed_cluster_id=sub_cluster_id[0], sub_cluster_id=sub_cluster_id[1]
                ).update(is_deleted=True)

        logger.info(
            "sync_federation_clusters:Start Creating federation data links for sub-clusters->[%s] asynchronously",
            need_process_clusters,
        )
        # bulk_create_fed_data_link(need_process_clusters)
        bulk_create_fed_data_link.delay(set(need_process_clusters))  # 异步创建联邦汇聚链路

        logger.info("sync_federation_clusters:sync_federation_clusters finished successfully.")

    except Exception as e:  # pylint: disable=broad-except
        logger.exception(e)
        logger.warning("sync_federation_clusters:sync_federation_clusters failed, error->[%s]", e)
