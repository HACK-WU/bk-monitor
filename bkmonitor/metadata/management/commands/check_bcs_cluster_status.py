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
import time
import logging

from kubernetes import client as k8s_client
from kubernetes.client.rest import ApiException
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.drf_resource import api
from bkmonitor.utils import consul
from metadata import models
from metadata.models.bcs.cluster import BCSClusterInfo
from metadata.models.data_source import DataSource, DataSourceOption
from metadata.models.bcs.resource import ServiceMonitorInfo, PodMonitorInfo
from metadata.models.storage import ClusterInfo, InfluxDBStorage, ESStorage, InfluxDBProxyStorage
from metadata.models.bcs.replace import ReplaceConfig
from metadata.models import BcsFederalClusterInfo, TimeSeriesGroup, TimeSeriesMetric
from metadata.models.space.space import SpaceDataSource
from metadata.models.space.constants import SpaceTypes
from metadata.models.custom_report.subscription_config import CustomReportSubscription
from metadata.models.result_table import (
    ResultTable,
    ResultTableOption,
    ResultTableField,
    ResultTableFieldOption,
    DataSourceResultTable,
)
from metadata.models.influxdb_cluster import InfluxDBClusterInfo, InfluxDBHostInfo
from metadata.models.vm.record import AccessVMRecord
from metadata.models.data_link.data_link import DataLink
from metadata.models.bkdata.result_table import BkBaseResultTable


logger = logging.getLogger("metadata")


def recode_final_result(fun):
    """记录最终结果的装饰器"""
    status_priority = {
        Status.UNKNOWN: 0,
        Status.SUCCESS: 1,
        Status.WARNING: 2,
        Status.ERROR: 3,
        Status.NOT_FOUND: 4,
    }

    def inner(self: "Command", *args, **kwargs):
        result = fun(self, *args, **kwargs)
        status = result.get("status", Status.UNKNOWN)

        current_priority = status_priority.get(status, 0)
        self_priority = status_priority.get(self.status, 0)

        if current_priority > self_priority:
            self.status = status

        if result.get("errors"):
            self.errors.extend(result["errors"])

        if result.get("issues"):
            self.issues.extend(result["issues"])

        if result.get("warnings"):
            self.warnings.extend(result["warnings"])

        return result

    return inner


# 定义状态的枚举类型
class Status:
    UNKNOWN = "UNKNOWN"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NOT_FOUND = "NOT_FOUND"


class Command(BaseCommand):
    """
    BCS集群关联状态检测命令

    检测指定集群ID在整个监控关联链路中的运行状态，包括：
    1. 数据库记录状态检查 - 验证集群基本信息和配置
    2. BCS API连接性测试 - 测试与BCS服务的通信
    3. Kubernetes集群连接测试 - 验证K8s API可用性
    4. 数据源配置验证 - 检查监控数据源配置
    5. 监控资源状态检查 - ServiceMonitor和PodMonitor状态
    6. 数据存储链路检查 - InfluxDB、ES等存储集群状态
    7. Consul配置检查 - 验证配置中心数据同步
    8. 数据采集配置检查 - 替换配置和指标组配置
    9. 联邦集群关系检查 - 联邦集群拓扑和命名空间映射
    10. 数据路由配置检查 - Transfer集群和MQ配置
    11. 集群资源使用情况检查 - 节点、Pod状态和资源使用
    12. 集群初始化资源检查 - EventGroup、TimeSeriesGroup、SpaceDataSource关联状态
    13. bk-collector配置检查 - DaemonSet部署状态、Pod运行状态、配置文件完整性
    14. 集群业务权限检查 - SpaceDataSource授权、space_uid配置、bk_biz_id配置

    使用示例:
    python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001
    python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001 --format json
    python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001 --timeout 60
    """

    help = "检测BCS集群在监控关联链路中的运行状态"

    def __init__(self, *args, **kwargs):
        self.cluster_info = None
        self.bk_biz_id = None
        self.bk_tenant_id = None

        self.status = Status.UNKNOWN
        self.errors = []
        self.issues = []
        self.warnings = []

        super().__init__(*args, **kwargs)

    def add_arguments(self, parser):
        """添加命令行参数配置"""
        parser.add_argument("--cluster-id", type=str, required=True, help="BCS集群ID，例如: BCS-K8S-00001")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式，支持text和json")
        parser.add_argument("--timeout", type=int, default=30, help="连接测试超时时间（秒），默认30秒")

    @property
    def data_sources(self) -> dict[str, DataSource]:
        """获取数据源"""
        if getattr(self, "_data_sources", None):
            return self._data_sources

        data_ids = [
            self.cluster_info.K8sMetricDataID,
            self.cluster_info.CustomMetricDataID,
            self.cluster_info.K8sEventDataID,
        ]

        data_ids = [id for id in data_ids if id != 0]
        data_sources = {d.bk_data_id: d for d in DataSource.objects.filter(bk_data_id__in=data_ids)}
        self._data_sources = data_sources
        return data_sources

    def handle(self, *args, **options):
        """主处理函数，执行集群状态检测流程"""
        cluster_id = options["cluster_id"]
        format_type = options["format"]
        timeout = options["timeout"]

        try:
            # 执行集群状态检测
            check_result = self.check_cluster_status(cluster_id, timeout)

            # 输出检测结果
            if format_type == "json":
                self.stdout.write(json.dumps(check_result, indent=2, ensure_ascii=False, default=str))
            else:
                self.output_text_report(check_result)

        except Exception as e:
            logger.exception(f"检测集群状态时发生异常: {e}")
            raise CommandError(f"集群状态检测失败: {e}")

    def check_cluster_status(self, cluster_id: str, timeout: int = 30) -> dict:
        """执行完整的集群状态检测"""
        start_time = time.time()

        check_result = {
            "cluster_id": cluster_id,
            "check_time": timezone.now().isoformat(),
            "status": Status.UNKNOWN,
            "details": {},
            "errors": [],
            "warnings": [],
            "execution_time": 0,
        }

        try:
            # 1. 数据库记录检查
            self.stdout.write(f"正在检查集群 {cluster_id} 的数据库记录...")
            db_check = self.check_database_record(cluster_id)
            check_result["details"]["database"] = db_check

            if not db_check["exists"]:
                check_result["status"] = Status.NOT_FOUND
                check_result["errors"].append("集群在数据库中不存在")
                return check_result

            cluster_info: BCSClusterInfo = db_check["cluster_model"]
            self.cluster_info: BCSClusterInfo = cluster_info
            self.bk_biz_id = cluster_info.bk_biz_id
            self.bk_tenant_id = cluster_info.bk_tenant_id

            # 2. BCS API连接测试
            self.stdout.write("正在测试BCS API连接...")
            bcs_api_check = self.check_bcs_api_connection(cluster_info, timeout)
            check_result["details"]["bcs_api"] = bcs_api_check

            # 3. Kubernetes集群连接测试
            # todo 待确认
            self.stdout.write("正在测试Kubernetes集群连接...")
            k8s_check = self.check_kubernetes_connection(cluster_info, timeout)
            check_result["details"]["kubernetes"] = k8s_check

            # 4. 数据源配置验证
            self.stdout.write("正在验证数据源配置...")
            datasource_check = self.check_datasource_configuration(cluster_info)
            check_result["details"]["datasources"] = datasource_check

            # 5. 监控资源状态检查
            self.stdout.write("正在检查监控资源状态...")
            monitor_check = self.check_monitor_resources(cluster_info)
            check_result["details"]["monitor_resources"] = monitor_check

            # 6. 数据存储链路检查
            self.stdout.write("正在检查数据存储...")
            storage_check = self.check_storage_clusters(cluster_info)
            check_result["details"]["storage"] = storage_check

            # todo 数据存储的路由配置没有检查

            # 7. Consul配置检查
            self.stdout.write("正在检查datasource的Consul配置...")
            consul_check = self.check_consul_configuration_to_datasource(cluster_info)
            check_result["details"]["consul"] = consul_check

            # 8. 数据采集配置检查
            self.stdout.write("正在检查数据采集配置...")
            collector_check = self.check_data_collection_config(cluster_info)
            check_result["details"]["data_collection"] = collector_check

            # 9. 联邦集群关系检查（如果是联邦集群）
            if self.is_federation_cluster(cluster_info):
                self.stdout.write("正在检查联邦集群关系...")
                federation_check = self.check_federation_cluster(cluster_info)
                check_result["details"]["federation"] = federation_check

            # 10. 数据路由配置检查
            self.stdout.write("正在检查数据路由配置...")
            routing_check = self.check_data_routing(cluster_info)
            check_result["details"]["routing"] = routing_check

            # 11. 集群资源使用情况检查
            # todo 待定
            self.stdout.write("正在检查集群资源使用情况...")
            resource_usage_check = self.check_cluster_resource_usage(cluster_info)
            check_result["details"]["resource_usage"] = resource_usage_check

            # 12. 集群初始化资源检查
            # todo 待定
            self.stdout.write("正在检查集群初始化资源...")
            init_resource_check = self.check_cluster_init_resources(cluster_info)
            check_result["details"]["init_resources"] = init_resource_check

            # 13. bk-collector配置检查
            self.stdout.write("正在检查bk-collector配置...")
            collector_config_check = self.check_bk_collector_config(cluster_info)
            check_result["details"]["bk_collector"] = collector_config_check

            # 14. 检查集群所属空间
            self.stdout.write("检查集群所属空间...")
            space_permission_check = self.check_space_permissions(cluster_info)
            check_result["details"]["space_permissions"] = space_permission_check

            # 15. 检查BCS API Token配置
            # todo 待定
            self.stdout.write("正在检查BCS API Token配置...")
            api_token_check = self.check_bcs_api_token(cluster_info)
            check_result["details"]["api_token"] = api_token_check

            # 16. 检查云区域ID配置
            self.stdout.write("正在检查云区域ID配置...")
            cloud_id_check = self.check_cloud_id_configuration(cluster_info)
            check_result["details"]["cloud_id"] = cloud_id_check

            # 17. 检查DataSourceOption配置
            self.stdout.write("正在检查DataSourceOption配置...")
            datasource_options_check = self.check_datasource_options(cluster_info)
            check_result["details"]["datasource_options"] = datasource_options_check

            # 18. 检查空间类型与SpaceDataSource关联
            self.stdout.write("正在检查空间类型配置...")
            space_type_check = self.check_space_type_and_datasource(cluster_info)
            check_result["details"]["space_type"] = space_type_check

            # 19. 检查指标标签
            # self.stdout.write("正在检查指标标签...")
            # metrics_labels_check = self.check_metrics_labels(cluster_info)
            # check_result["details"]["metrics_labels"] = metrics_labels_check

            # 20. 检查CustomReportSubscription
            self.stdout.write("正在检查CustomReportSubscription...")
            custom_report_sub_check = self.check_custom_report_subscription(cluster_info)
            check_result["details"]["custom_report_subscription"] = custom_report_sub_check

            # 21. 检查table_id合法性
            # self.stdout.write("正在检查结果表ID合法性...")
            # table_id_check = self.check_table_id_validity(cluster_info)
            # check_result["details"]["table_id_validity"] = table_id_check

            # 22. 检查关联模型
            self.stdout.write("正在检查关联模型数据...")
            related_models_check = self.check_related_models(cluster_info)
            check_result["details"]["related_models"] = related_models_check

            # 23. 检查InfluxDB存储配置
            self.stdout.write("正在检查InfluxDB存储配置...")
            influxdb_storage_check = self.check_influxdb_storage_config(cluster_info)
            check_result["details"]["influxdb_storage"] = influxdb_storage_check

            # 24. 检查VM数据链路依赖
            self.stdout.write("正在检查VM数据链路依赖...")
            vm_datalink_check = self.check_vm_datalink_dependencies(cluster_info)
            check_result["details"]["vm_datalink_dependencies"] = vm_datalink_check

            # 确定整体状态
            check_result["status"] = self.status
            check_result["errors"] = self.errors
            check_result["issues"] = self.issues
            check_result["warnings"] = self.warnings

        except Exception as e:
            check_result["status"] = Status.ERROR
            check_result["errors"].append(f"检测过程中发生异常: {str(e)}")
            logger.exception(f"集群状态检测异常: {e}")

        finally:
            check_result["execution_time"] = round(time.time() - start_time, 2)

        return check_result

    @recode_final_result
    def check_database_record(self, cluster_id: str) -> dict:
        """检查集群在数据库中的记录状态"""
        result = {"exists": False, "cluster_info": None, "status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化数据库检查输出"""
            lines = []
            if details:
                lines.append(f"    业务ID: {details.get('bk_biz_id')}")
                lines.append(f"    集群状态: {details.get('status')}")
            return lines

        result["formatter"] = format_output

        try:
            cluster_info = BCSClusterInfo.objects.get(cluster_id=cluster_id)
            result["exists"] = True
            result["cluster_model"] = cluster_info
            result["status"] = Status.SUCCESS

            # 收集集群基本信息
            result["details"] = {
                "bk_biz_id": cluster_info.bk_biz_id,
                "project_id": cluster_info.project_id,
                "status": cluster_info.status,
                "bk_tenant_id": cluster_info.bk_tenant_id,
                "domain_name": cluster_info.domain_name,
                "port": cluster_info.port,
                "data_ids": {
                    "K8sMetricDataID": cluster_info.K8sMetricDataID,
                    "CustomMetricDataID": cluster_info.CustomMetricDataID,
                    "K8sEventDataID": cluster_info.K8sEventDataID,
                },
            }

            # 检查集群状态
            if cluster_info.status not in [
                BCSClusterInfo.CLUSTER_STATUS_RUNNING,
                BCSClusterInfo.CLUSTER_RAW_STATUS_RUNNING,
            ]:
                result["issues"].append(f"集群状态异常: {cluster_info.status}")

            # 检查数据源ID配置
            missing_data_ids = []
            for data_type, data_id in result["details"]["data_ids"].items():
                if data_id == 0:
                    missing_data_ids.append(data_type)

            if missing_data_ids:
                result["issues"].append(f"缺少数据源ID配置: {', '.join(missing_data_ids)}")

        except BCSClusterInfo.DoesNotExist:
            result["status"] = Status.NOT_FOUND
            result["issues"].append("集群记录在数据库中不存在")
        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"数据库查询异常: {str(e)}")

        return result

    @recode_final_result
    def check_bcs_api_connection(self, cluster_info: BCSClusterInfo, timeout: int) -> dict:
        """检查BCS API连接状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化BCS API连接检查输出"""
            lines = []
            if details:
                lines.append(f"    API可访问: {details.get('api_accessible', False)}")
                lines.append(f"    集群发现: {details.get('cluster_found', False)}")
                if details.get("cluster_status"):
                    lines.append(f"    集群状态: {details['cluster_status']}")
            return lines

        result["formatter"] = format_output

        try:
            # 尝试通过BCS API获取集群信息
            bcs_clusters = api.kubernetes.fetch_k8s_cluster_list(bk_tenant_id=cluster_info.bk_tenant_id)

            # 检查目标集群是否在返回列表中
            target_cluster = None
            for cluster in bcs_clusters:
                if cluster.get("cluster_id") == cluster_info.cluster_id:
                    target_cluster = cluster
                    break

            if target_cluster:
                result["status"] = Status.SUCCESS
                result["details"] = {
                    "api_accessible": True,  # API可访问
                    "cluster_found": True,
                    "cluster_status": target_cluster.get("status"),
                    "bk_biz_id": target_cluster.get("bk_biz_id"),
                }

                # 检查状态一致性
                if target_cluster.get("status") != cluster_info.status:
                    result["issues"].append(
                        f"集群状态不一致 - 数据库: {cluster_info.status}, BCS API: {target_cluster.get('status')}"
                    )
            else:
                result["status"] = Status.WARNING
                result["details"] = {"api_accessible": True, "cluster_found": False}
                result["issues"].append("集群在BCS API中未找到，可能已被删除")

        except Exception as e:
            result["status"] = Status.ERROR
            result["details"] = {"api_accessible": False, "error": str(e)}
            result["issues"].append(f"BCS API连接失败: {str(e)}")

        return result

    @recode_final_result
    def check_kubernetes_connection(self, cluster_info: BCSClusterInfo, timeout: int) -> dict:
        """检查Kubernetes集群连接状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化Kubernetes检查输出"""
            lines = []
            if details.get("nodes"):
                nodes = details["nodes"]
                lines.append(f"    节点统计: {nodes['ready']}/{nodes['total']} 就绪")
            return lines

        result["formatter"] = format_output

        try:
            # 测试Kubernetes API连接
            core_api = cluster_info.core_api

            # 获取节点列表
            nodes = core_api.list_node(timeout_seconds=timeout)
            node_count = len(nodes.items)
            ready_nodes = 0

            for node in nodes.items:
                for condition in node.status.conditions:
                    if condition.type == "Ready" and condition.status == "True":
                        ready_nodes += 1
                        break

            result["details"]["nodes"] = {
                "total": node_count,
                "ready": ready_nodes,
            }

            # 获取命名空间列表
            namespaces = core_api.list_namespace(timeout_seconds=timeout)
            result["details"]["namespaces_count"] = len(namespaces.items)

            result["status"] = Status.SUCCESS

            # 检查节点健康状态
            if ready_nodes < node_count:
                result["issues"].append(f"有{node_count - ready_nodes}个节点未就绪")

        except k8s_client.ApiException as e:
            result["status"] = Status.ERROR
            result["details"]["api_error"] = {"status": e.status, "reason": e.reason}
            result["issues"].append(f"Kubernetes API调用失败: {e.status} {e.reason}")

        except Exception as e:
            result["status"] = Status.ERROR
            result["details"]["error"] = str(e)
            result["issues"].append(f"Kubernetes连接异常: {str(e)}")

        return result

    @recode_final_result
    def check_datasource_configuration(self, cluster_info: BCSClusterInfo) -> dict:
        """检查数据源配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化数据源配置检查输出"""
            lines = []
            if details:
                data_ids = details.get("configured_data_ids", [])
                lines.append(f"    已配置数据源: {len(data_ids)}个")
                datasource_status = details.get("datasource_status", {})
                enabled_count = sum(1 for ds in datasource_status.values() if ds.get("is_enable", False))
                lines.append(f"    启用状态: {enabled_count}/{len(datasource_status)}")
            return lines

        result["formatter"] = format_output

        try:
            # todo 应该检查是否全部具备三个数据源ID
            # todo 检查DataSourceOption 模型
            datasource_status = {}
            for data_id, datasource in self.data_sources.items():
                try:
                    # 检查数据源记录
                    # todo 增加对绑定的mq集群的检查,包括配置
                    datasource_status[data_id] = {
                        "exists": True,
                        "data_name": datasource.data_name,
                        "is_enable": datasource.is_enable,
                        "type_label": datasource.type_label,
                    }

                    # 检查数据源是否启用
                    if not datasource.is_enable:
                        result["issues"].append(f"data_id:{data_id}未启用")

                except DataSource.DoesNotExist:
                    datasource_status[data_id] = {"exists": False}
                    result["issues"].append(f"数据源data_id:{data_id}不存在")

            result["details"] = {
                "configured_data_ids": list(self.data_sources.keys()),
                "datasource_status": datasource_status,
            }

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("不存在" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"数据源配置检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_monitor_resources(self, cluster_info: BCSClusterInfo) -> dict:
        """检查监控资源状态
        ServiceMonitorInfo.refresh_resource  从 K8s 拉取 CRD 列表，新增或删除本地记录，保持一致性
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化监控资源检查输出"""
            lines = []
            if details:
                lines.append(f"    ServiceMonitor: {details.get('service_monitors', {}).get('count', 0)}个")
                lines.append(f"    PodMonitor: {details.get('pod_monitors', {}).get('count', 0)}个")
            return lines

        result["formatter"] = format_output

        try:
            # 检查ServiceMonitor资源
            service_monitors = ServiceMonitorInfo.objects.filter(bcs_cluster_id=cluster_info.cluster_id)
            service_monitor_count = service_monitors.count()

            # 检查PodMonitor资源
            pod_monitors = PodMonitorInfo.objects.filter(bcs_cluster_id=cluster_info.cluster_id)
            pod_monitor_count = pod_monitors.count()

            result["details"]["service_monitors"] = {
                "count": service_monitor_count,
            }

            result["details"]["pod_monitors"] = {
                "count": pod_monitor_count,
            }

            if 0 in [service_monitor_count, pod_monitor_count]:
                result["status"] = Status.WARNING
            else:
                result["status"] = Status.SUCCESS

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"监控资源检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_storage_clusters(self, cluster_info: BCSClusterInfo) -> dict:
        """检查数据存储集群状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化存储集群检查输出"""
            lines = []
            if details:
                storage_count = len(details.get("storage_status", {}))
                lines.append(f"    存储配置: {storage_count}个数据源")
            return lines

        result["formatter"] = format_output

        try:
            # 获取数据源相关的结果表
            storage_status = {}
            for data_id in self.data_sources:
                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()
                    if not ds_rt:
                        storage_status[data_id] = {"exists": False, "error": "未找到结果表关联"}
                        result["issues"].append(f"数据源data_id:{data_id}未找到结果表关联")
                        continue

                    rt = ResultTable.objects.get(table_id=ds_rt.table_id, bk_tenant_id=self.bk_tenant_id)
                    storage_status[data_id] = {"exists": True, "table_id": rt.table_id, "storage_clusters": []}

                    # 检查InfluxDB存储
                    influxdb_storages = InfluxDBStorage.objects.filter(
                        table_id=rt.table_id, bk_tenant_id=self.bk_tenant_id
                    )
                    for storage in influxdb_storages:
                        cluster_status = self._check_storage_cluster_health(storage.storage_cluster, "influxdb")
                        storage_status[data_id]["storage_clusters"].append(
                            {
                                "type": "influxdb",
                                "cluster_name": storage.storage_cluster.cluster_name,
                                "status": cluster_status,
                            }
                        )
                        if cluster_status["status"] != Status.SUCCESS:
                            result["issues"].append(
                                f"数据源data_id:{data_id}InfluxDB集群{storage.storage_cluster.cluster_name}状态异常"
                            )

                    # 检查ES存储
                    es_storages = ESStorage.objects.filter(table_id=rt.table_id, bk_tenant_id=self.bk_tenant_id)
                    for storage in es_storages:
                        cluster_status = self._check_storage_cluster_health(storage.storage_cluster, "elasticsearch")
                        storage_status[data_id]["storage_clusters"].append(
                            {
                                "type": "elasticsearch",
                                "cluster_name": storage.storage_cluster.cluster_name,
                                "status": cluster_status,
                            }
                        )
                        if cluster_status["status"] != Status.SUCCESS:
                            result["issues"].append(
                                f"数据源data_id:{data_id}ES集群{storage.storage_cluster.cluster_name}状态异常"
                            )

                except Exception as e:
                    storage_status[data_id] = {"exists": False, "error": str(e)}
                    result["issues"].append(f"数据源data_id:{data_id}存储检查异常: {str(e)}")

            result["details"] = {"storage_status": storage_status}
            result["status"] = (
                Status.SUCCESS
                if not result["issues"]
                else (Status.WARNING if any("状态异常" in issue for issue in result["issues"]) else Status.ERROR)
            )

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"存储集群检查异常: {str(e)}")

        return result

    def _check_storage_cluster_health(self, cluster: ClusterInfo, cluster_type: str) -> dict:
        """检查存储集群健康状态"""
        try:
            if cluster_type in ["influxdb", "elasticsearch"]:
                return {
                    "status": Status.SUCCESS,
                    "details": {
                        "domain": cluster.domain_name,
                        "port": cluster.port,
                        "is_default": cluster.is_default_cluster,
                    },
                }
            else:
                return {"status": Status.UNKNOWN, "details": {}, "error": f"不支持的集群类型: {cluster_type}"}
        except Exception as e:
            return {"status": Status.ERROR, "details": {}, "error": str(e)}

    @recode_final_result
    def check_consul_configuration_to_datasource(self, cluster_info: BCSClusterInfo) -> dict:
        """检查datasource的Consul配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化Consul配置检查输出"""
            lines = []
            if details:
                consul_count = len(details.get("consul_status", {}))
                lines.append(f"    Consul配置: {consul_count}个数据源")
            return lines

        result["formatter"] = format_output

        try:
            consul_client = consul.BKConsul()
            consul_status = {}

            for data_id, datasource in self.data_sources.items():
                try:
                    consul_path = datasource.consul_config_path
                    consul_data = consul_client.kv.get(consul_path)

                    if consul_data[1] is None:
                        consul_status[data_id] = {"exists": False, "path": consul_path}
                        result["issues"].append(f"数据源data_id:{data_id}在Consul中的配置不存在")
                    else:
                        consul_config = json.loads(consul_data[1]["Value"])
                        consul_status[data_id] = {
                            "exists": True,
                            "path": consul_path,
                            "last_modified": consul_data[1].get("ModifyIndex", 0),
                            "has_result_tables": len(consul_config.get("result_table_list", [])) > 0,
                        }
                        if not consul_config.get("result_table_list"):
                            result["issues"].append(f"数据源data_id:{data_id}在Consul中缺少结果表配置")

                except DataSource.DoesNotExist:
                    consul_status[data_id] = {"exists": False, "error": "数据源不存在"}
                    result["issues"].append(f"数据源data_id:{data_id}不存在")
                except Exception as e:
                    consul_status[data_id] = {"exists": False, "error": str(e)}
                    result["issues"].append(f"数据源data_id:{data_id}Consul配置检查异常: {str(e)}")

            result["details"] = {"consul_status": consul_status}
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"Consul配置检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_data_collection_config(self, cluster_info: BCSClusterInfo) -> dict:
        """检查数据采集配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化数据采集配置检查输出"""
            lines = []
            if details:
                lines.append(f"    替换配置: {details.get('replace_config_count', 0)}个")
                lines.append(f"    指标组: {len(details.get('metric_groups', []))}个")
            return lines

        result["formatter"] = format_output

        try:
            # 检查替换配置
            replace_configs = ReplaceConfig.objects.filter(
                cluster_id=cluster_info.cluster_id, is_common=False, custom_level=ReplaceConfig.CUSTOM_LEVELS_CLUSTER
            )
            replace_config_count = replace_configs.count()

            # 检查时序数据组配置
            # 在bkmonitor/metadata/management/commands/refresh_ts_metric.py 中会刷新 TimeSeriesGroup
            # TimeSeriesGroup 通过 bk_data_id 关联租户，DataSource 已包含 bk_tenant_id
            # 因此间接实现了租户隔离，无需显式添加 bk_tenant_id 过滤
            metric_groups = TimeSeriesGroup.objects.filter(
                bk_data_id__in=[cluster_info.K8sMetricDataID, cluster_info.CustomMetricDataID]
            )

            metric_group_details = []
            for group in metric_groups:
                # TimeSeriesMetric 通过 group_id 关联 TimeSeriesGroup，间接实现租户隔离
                metrics_count = TimeSeriesMetric.objects.filter(group_id=group.time_series_group_id).count()
                metric_group_details.append(
                    {
                        "group_id": group.time_series_group_id,
                        "table_id": group.table_id,
                        "bk_data_id": group.bk_data_id,
                        "metrics_count": metrics_count,
                        "is_split_measurement": group.is_split_measurement,
                        "enable_field_blacklist": group.enable_field_blacklist,
                    }
                )

            result["details"] = {
                "replace_config_count": replace_config_count,
                "metric_groups": metric_group_details,
                "collection_features": {
                    "single_metric_table": any(g.is_split_measurement for g in metric_groups),
                    "field_blacklist_enabled": any(g.enable_field_blacklist for g in metric_groups),
                },
            }

            # 检查配置合理性
            if replace_config_count == 0:
                result["issues"].append("没有配置替换规则，可能影响数据采集")

            if len(metric_group_details) == 0:
                result["issues"].append("没有找到时序数据组配置")
                result["status"] = Status.ERROR
            elif not result["issues"]:
                result["status"] = Status.SUCCESS
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"数据采集配置检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_federation_cluster(self, cluster_info: BCSClusterInfo) -> dict:
        """检查联邦集群状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化联邦集群检查输出"""
            lines = []
            if details:
                lines.append(f"    联邦关系: {details.get('federation_count', 0)}个")
            return lines

        result["formatter"] = format_output

        try:
            # 获取联邦集群信息
            fed_clusters = BcsFederalClusterInfo.objects.filter(
                fed_cluster_id=cluster_info.cluster_id, is_deleted=False
            )

            if not fed_clusters.exists():
                result["status"] = Status.ERROR
                result["issues"].append("联邦集群信息不存在")
                return result

            federation_details = []
            for fed_cluster in fed_clusters:
                federation_details.append(
                    {
                        "host_cluster_id": fed_cluster.host_cluster_id,
                        "sub_cluster_id": fed_cluster.sub_cluster_id,
                        "fed_namespaces": fed_cluster.fed_namespaces,
                        "builtin_metric_table_id": fed_cluster.fed_builtin_metric_table_id,
                        "builtin_event_table_id": fed_cluster.fed_builtin_event_table_id,
                    }
                )

            result["details"] = {"federation_count": len(federation_details), "federations": federation_details}

            # 检查联邦集群配置完整性
            for fed in federation_details:
                if not fed["fed_namespaces"]:
                    result["issues"].append(f"子集群{fed['sub_cluster_id']}没有配置命名空间")
                if not fed["builtin_metric_table_id"]:
                    result["issues"].append(f"子集群{fed['sub_cluster_id']}缺少内置指标表ID")

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"联邦集群检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_data_routing(self, cluster_info: BCSClusterInfo) -> dict:
        """检查数据路由配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化数据路由检查输出"""
            lines = []
            if details:
                routing_count = len(details.get("routing_status", {}))
                lines.append(f"    路由配置: {routing_count}个数据源")
            return lines

        result["formatter"] = format_output

        try:
            routing_status = {}

            for data_id, datasource in self.data_sources:
                if data_id == 0:
                    continue

                try:
                    routing_status[data_id] = {
                        "transfer_cluster_id": datasource.transfer_cluster_id,
                        "data_name": datasource.data_name,
                        "mq_cluster_id": datasource.mq_cluster_id,
                        "is_enable": datasource.is_enable,
                    }

                    # 检查路由配置合理性
                    if not datasource.transfer_cluster_id:
                        result["issues"].append(f"数据源data_id:{data_id}未配置转移集群")
                    if not datasource.is_enable:
                        result["issues"].append(f"数据源data_id:{data_id}未启用")

                except DataSource.DoesNotExist:
                    routing_status[data_id] = {"exists": False, "error": "数据源不存在"}
                    result["issues"].append(f"数据源data_id:{data_id}不存在")

            result["details"] = {"routing_status": routing_status}
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"数据路由检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_cluster_resource_usage(self, cluster_info: BCSClusterInfo) -> dict:
        """检查集群资源使用情况"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化集群资源使用检查输出"""
            lines = []
            if details.get("nodes"):
                nodes = details["nodes"]
                lines.append(f"    节点统计: {nodes['ready_count']}/{nodes['count']} 就绪")
            if details.get("pods"):
                pods = details["pods"]
                lines.append(f"    Pod统计: {pods['total_count']}个")
            return lines

        result["formatter"] = format_output

        try:
            core_api = cluster_info.core_api

            # 获取节点资源使用情况
            try:
                nodes = core_api.list_node()
                node_metrics = []

                for node in nodes.items:
                    node_info = {
                        "name": node.metadata.name,
                        "status": "Unknown",
                        "cpu_capacity": None,
                        "memory_capacity": None,
                        "pods_capacity": None,
                        "conditions": [],
                    }

                    # 获取节点状态
                    if node.status.conditions:
                        for condition in node.status.conditions:
                            if condition.type == "Ready":
                                node_info["status"] = "Ready" if condition.status == "True" else "NotReady"
                            node_info["conditions"].append(
                                {
                                    "type": condition.type,
                                    "status": condition.status,
                                    "reason": condition.reason,
                                    "message": condition.message,
                                }
                            )

                    # 获取节点资源信息
                    if node.status.capacity:
                        node_info["cpu_capacity"] = node.status.capacity.get("cpu")
                        node_info["memory_capacity"] = node.status.capacity.get("memory")
                        node_info["pods_capacity"] = node.status.capacity.get("pods")

                    node_metrics.append(node_info)

                    # 检查节点状态问题
                    if node_info["status"] != "Ready":
                        result["issues"].append(f"节点{node_info['name']}状态不正常: {node_info['status']}")

                result["details"]["nodes"] = {
                    "count": len(node_metrics),
                    "ready_count": len([n for n in node_metrics if n["status"] == "Ready"]),
                    "node_details": node_metrics,
                }

            except ApiException as e:
                result["issues"].append(f"获取节点信息失败: {e.reason}")

            # 检查Pod资源使用情况
            try:
                pods = core_api.list_pod_for_all_namespaces()
                pod_status_count = {}
                pod_details = []

                for pod in pods.items:
                    status = pod.status.phase if pod.status.phase else "Unknown"
                    pod_status_count[status] = pod_status_count.get(status, 0) + 1

                    # 收集监控相关Pod信息
                    if any(keyword in pod.metadata.name.lower() for keyword in ["monitor", "prometheus", "bkmonitor"]):
                        pod_details.append(
                            {
                                "name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "status": status,
                                "node_name": pod.spec.node_name,
                                "restart_count": sum(
                                    container.restart_count for container in pod.status.container_statuses or []
                                ),
                            }
                        )

                result["details"]["pods"] = {
                    "total_count": len(pods.items),
                    "status_distribution": pod_status_count,
                    "monitor_pods": pod_details,
                }

                # 检查是否有异常Pod
                if pod_status_count.get("Failed", 0) > 0:
                    result["issues"].append(f"集群中有{pod_status_count['Failed']}个失败的Pod")

            except ApiException as e:
                result["issues"].append(f"获取Pod信息失败: {e.reason}")

            # 确定整体状态
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"集群资源检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_cluster_init_resources(self, cluster_info: BCSClusterInfo) -> dict:
        """检查集群初始化资源状态

        检查项目包括：
        1. EventGroup 创建状态
        2. TimeSeriesGroup 创建状态
        3. SpaceDataSource 关联状态
        4. ConfigMap 配置状态
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化集群初始化资源检查输出"""
            lines = []
            if details:
                lines.append(f"    TimeSeriesGroup: {len(details.get('time_series_groups', []))}个")
                lines.append(f"    SpaceDataSource: {len(details.get('space_datasources', []))}个")
                lines.append(f"    ConfigMap配置: {len(details.get('configmap_configs', []))}个")
            return lines

        result["formatter"] = format_output

        try:
            # 1. 检查EventGroup创建状态
            if cluster_info.K8sEventDataID != 0:
                try:
                    # EventGroup 通过 bk_data_id 关联 DataSource，间接实现租户隔离
                    event_group = models.EventGroup.objects.get(bk_data_id=cluster_info.K8sEventDataID)
                    result["details"]["event_group"] = {
                        "exists": True,
                        "bk_data_id": event_group.bk_data_id,
                        "bk_biz_id": event_group.bk_biz_id,
                        "is_enable": event_group.is_enable,
                    }

                    if not event_group.is_enable:
                        result["issues"].append(f"K8s事件数据源data_id:{cluster_info.K8sEventDataID}的EventGroup未启用")

                except models.EventGroup.DoesNotExist:
                    result["details"]["event_group"] = {"exists": False}
                    result["issues"].append(f"K8s事件数据源data_id:{cluster_info.K8sEventDataID}的EventGroup不存在")

            # 2. 检查TimeSeriesGroup创建状态
            time_series_groups = []
            for data_id in [cluster_info.K8sMetricDataID, cluster_info.CustomMetricDataID]:
                if data_id == 0:
                    continue

                try:
                    # TimeSeriesGroup 通过 bk_data_id 关联 DataSource，间接实现租户隔离
                    ts_groups = models.TimeSeriesGroup.objects.filter(bk_data_id=data_id, is_delete=False)
                    for ts_group in ts_groups:
                        metrics_count = models.TimeSeriesMetric.objects.filter(
                            group_id=ts_group.time_series_group_id
                        ).count()

                        time_series_groups.append(
                            {
                                "group_id": ts_group.time_series_group_id,
                                "bk_data_id": ts_group.bk_data_id,
                                "table_id": ts_group.table_id,
                                "metrics_count": metrics_count,
                                "is_split_measurement": ts_group.is_split_measurement,
                            }
                        )

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}的TimeSeriesGroup检查异常: {str(e)}")

            result["details"]["time_series_groups"] = time_series_groups

            if not time_series_groups:
                result["issues"].append("没有找到任何TimeSeriesGroup记录")

            # 3. 检查SpaceDataSource关联状态
            space_datasources = []
            space_uid = f"bkcc__{cluster_info.bk_biz_id}"

            for data_id in [cluster_info.K8sMetricDataID, cluster_info.CustomMetricDataID, cluster_info.K8sEventDataID]:
                if data_id == 0:
                    continue

                try:
                    space_ds = models.SpaceDataSource.objects.filter(
                        bk_data_id=data_id, space_uid=space_uid, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if space_ds:
                        space_datasources.append(
                            {
                                "bk_data_id": space_ds.bk_data_id,
                                "space_uid": space_ds.space_uid,
                                "space_type_id": space_ds.space_type_id,
                                "space_id": space_ds.space_id,
                            }
                        )
                    else:
                        result["issues"].append(f"数据源data_id:{data_id}未关联到空间{space_uid}")

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}的SpaceDataSource检查异常: {str(e)}")

            result["details"]["space_datasources"] = space_datasources

            # 4. 检查ConfigMap配置状态
            try:
                core_api = cluster_info.core_api
                configmaps = core_api.list_namespaced_config_map(namespace="bkmonitor-operator")

                bk_collector_configs = []
                for cm in configmaps.items:
                    if "bk-collector" in cm.metadata.name and "config" in cm.metadata.name:
                        config_data = cm.data or {}

                        bk_collector_configs.append(
                            {
                                "name": cm.metadata.name,
                                "namespace": cm.metadata.namespace,
                                "creation_timestamp": str(cm.metadata.creation_timestamp),
                                "data_keys": list(config_data.keys()),
                                "data_size": sum(len(str(v)) for v in config_data.values()),
                            }
                        )

                result["details"]["configmap_configs"] = bk_collector_configs

                if not bk_collector_configs:
                    result["issues"].append("未找到bk-collector相关的ConfigMap配置")

            except ApiException as e:
                result["issues"].append(f"ConfigMap检查失败: {e.reason}")
            except Exception as e:
                result["issues"].append(f"ConfigMap检查异常: {str(e)}")

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("不存在" in issue or "异常" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"集群初始化资源检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_bk_collector_config(self, cluster_info: BCSClusterInfo) -> dict:
        """检查bk-collector配置状态

        检查项目包括：
        1. bk-collector DaemonSet 部署状态
        2. bk-collector Pod 运行状态
        3. bk-collector 配置文件完整性
        4. 数据采集配置有效性
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化bk-collector配置检查输出"""
            lines = []
            if details.get("daemonset") and details["daemonset"].get("name"):
                ds = details["daemonset"]
                lines.append(f"    DaemonSet: {ds['ready_pods']}/{ds['desired_pods']} 就绪")
            lines.append(f"    Pod数量: {len(details.get('pods', []))}个")
            lines.append(f"    配置文件: {len(details.get('config_files', []))}个")
            return lines

        result["formatter"] = format_output

        try:
            core_api = cluster_info.core_api
            apps_api = cluster_info.apps_api

            # 1. 检查bk-collector DaemonSet部署状态
            try:
                daemonsets = apps_api.list_namespaced_daemon_set(namespace="bkmonitor-operator")
                bk_collector_ds = None

                for ds in daemonsets.items:
                    if "bk-collector" in ds.metadata.name:
                        bk_collector_ds = ds
                        break

                if bk_collector_ds:
                    result["details"]["daemonset"] = {
                        "name": bk_collector_ds.metadata.name,
                        "namespace": bk_collector_ds.metadata.namespace,
                        "desired_pods": bk_collector_ds.status.desired_number_scheduled,
                        "current_pods": bk_collector_ds.status.current_number_scheduled,
                        "ready_pods": bk_collector_ds.status.number_ready,
                        "available_pods": bk_collector_ds.status.number_available,
                    }

                    # 检查Pod状态
                    if bk_collector_ds.status.number_ready != bk_collector_ds.status.desired_number_scheduled:
                        result["issues"].append(
                            f"bk-collector DaemonSet中有{bk_collector_ds.status.desired_number_scheduled - bk_collector_ds.status.number_ready}个Pod未就绪"
                        )
                else:
                    result["details"]["daemonset"] = {"exists": False}
                    result["issues"].append("bk-collector DaemonSet未部署")

            except ApiException as e:
                result["issues"].append(f"DaemonSet检查失败: {e.reason}")

            # 2. 检查bk-collector Pod运行状态
            try:
                pods = core_api.list_namespaced_pod(namespace="bkmonitor-operator", label_selector="app=bk-collector")

                pod_status = []
                for pod in pods.items:
                    container_statuses = []
                    if pod.status.container_statuses:
                        for container in pod.status.container_statuses:
                            container_statuses.append(
                                {
                                    "name": container.name,
                                    "ready": container.ready,
                                    "restart_count": container.restart_count,
                                    "state": str(container.state),
                                }
                            )

                    pod_status.append(
                        {
                            "name": pod.metadata.name,
                            "phase": pod.status.phase,
                            "node_name": pod.spec.node_name,
                            "containers": container_statuses,
                        }
                    )

                    # 检查Pod是否有异常
                    if pod.status.phase != "Running":
                        result["issues"].append(f"bk-collector Pod {pod.metadata.name}状态异常: {pod.status.phase}")

                    # 检查容器重启次数
                    if pod.status.container_statuses:
                        for container in pod.status.container_statuses:
                            if container.restart_count > 5:
                                result["issues"].append(
                                    f"bk-collector Pod {pod.metadata.name}中容器{container.name}重启次数过多: {container.restart_count}"
                                )

                result["details"]["pods"] = pod_status

            except ApiException as e:
                result["issues"].append(f"Pod检查失败: {e.reason}")

            # 3. 检查bk-collector配置文件完整性
            try:
                configmaps = core_api.list_namespaced_config_map(namespace="bkmonitor-operator")
                config_files = []

                for cm in configmaps.items:
                    if "bk-collector" in cm.metadata.name and "config" in cm.metadata.name:
                        config_data = cm.data or {}

                        # 检查关键配置文件
                        required_configs = ["config.yaml", "cluster_config.yaml"]
                        missing_configs = []

                        for config_name in required_configs:
                            if config_name not in config_data:
                                missing_configs.append(config_name)

                        config_files.append(
                            {
                                "name": cm.metadata.name,
                                "config_keys": list(config_data.keys()),
                                "missing_configs": missing_configs,
                            }
                        )

                        if missing_configs:
                            result["issues"].append(
                                f"ConfigMap {cm.metadata.name}缺少关键配置: {', '.join(missing_configs)}"
                            )

                result["details"]["config_files"] = config_files

            except ApiException as e:
                result["issues"].append(f"配置文件检查失败: {e.reason}")

            # 4. 检查数据采集配置有效性（检查dataID是否正确配置）
            collection_configs = {
                "K8sMetricDataID": cluster_info.K8sMetricDataID,
                "CustomMetricDataID": cluster_info.CustomMetricDataID,
                "K8sEventDataID": cluster_info.K8sEventDataID,
            }

            invalid_configs = []
            for config_name, data_id in collection_configs.items():
                if data_id == 0:
                    invalid_configs.append(config_name)

            result["details"]["collection_configs"] = collection_configs

            if invalid_configs:
                result["issues"].append(f"以下数据采集配置无效: {', '.join(invalid_configs)}")

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("未部署" in issue or "失败" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"bk-collector配置检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_space_permissions(self, cluster_info: BCSClusterInfo) -> dict:
        """检查集群所属空间状态

        检查项目包括：
        1. SpaceDataSource 数据源授权关系
        2. DataSource 的 space_uid 配置
        3. ResultTable 的 bk_biz_id 配置
        4. EventGroup 的 bk_biz_id 配置
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化空间权限检查输出"""
            lines = []
            if details:
                authorized_count = len(
                    [ds for ds in details.get("space_datasources", []) if ds.get("status") == "authorized"]
                )
                total_count = len(details.get("space_datasources", []))
                lines.append(f"    数据源授权: {authorized_count}/{total_count}")
                correct_space_count = len(
                    [ds for ds in details.get("datasource_spaces", []) if ds.get("status") == "correct"]
                )
                total_space_count = len(details.get("datasource_spaces", []))
                lines.append(f"    空间配置: {correct_space_count}/{total_space_count} 正确")
            return lines

        result["formatter"] = format_output

        try:
            expected_space_uid = f"bkcc__{cluster_info.bk_biz_id}"
            data_ids = [cluster_info.K8sMetricDataID, cluster_info.CustomMetricDataID, cluster_info.K8sEventDataID]

            # 1. 检查SpaceDataSource数据源授权关系
            space_datasource_status = []
            for data_id in data_ids:
                if data_id == 0:
                    continue

                try:
                    space_ds = models.SpaceDataSource.objects.filter(
                        bk_data_id=data_id, space_uid=expected_space_uid, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if space_ds:
                        space_datasource_status.append(
                            {
                                "bk_data_id": data_id,
                                "space_uid": space_ds.space_uid,
                                "space_type_id": space_ds.space_type_id,
                                "space_id": space_ds.space_id,
                                "status": "authorized",
                            }
                        )
                    else:
                        space_datasource_status.append({"bk_data_id": data_id, "status": "not_authorized"})
                        result["issues"].append(f"数据源data_id:{data_id}未授权给空间{expected_space_uid}")

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}的空间授权检查异常: {str(e)}")

            result["details"]["space_datasources"] = space_datasource_status

            # 2. 检查DataSource的space_uid配置
            datasource_space_status = []
            for data_id in data_ids:
                if data_id == 0:
                    continue

                try:
                    datasource = DataSource.objects.get(bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id)

                    if datasource.space_uid == expected_space_uid:
                        datasource_space_status.append(
                            {"bk_data_id": data_id, "space_uid": datasource.space_uid, "status": "correct"}
                        )
                    else:
                        datasource_space_status.append(
                            {
                                "bk_data_id": data_id,
                                "space_uid": datasource.space_uid,
                                "expected_space_uid": expected_space_uid,
                                "status": "incorrect",
                            }
                        )
                        result["issues"].append(
                            f"数据源data_id:{data_id}的space_uid配置错误: {datasource.space_uid}, 期望: {expected_space_uid}"
                        )

                except DataSource.DoesNotExist:
                    result["issues"].append(f"数据源data_id:{data_id}不存在")
                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}的space_uid检查异常: {str(e)}")

            result["details"]["datasource_spaces"] = datasource_space_status

            # 3. 检查ResultTable的bk_biz_id配置
            result_table_status = []
            for data_id in data_ids:
                if data_id == 0:
                    continue

                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()
                    if ds_rt:
                        result_table = ResultTable.objects.get(table_id=ds_rt.table_id, bk_tenant_id=self.bk_tenant_id)

                        if result_table.bk_biz_id == cluster_info.bk_biz_id:
                            result_table_status.append(
                                {
                                    "bk_data_id": data_id,
                                    "table_id": result_table.table_id,
                                    "bk_biz_id": result_table.bk_biz_id,
                                    "status": "correct",
                                }
                            )
                        else:
                            result_table_status.append(
                                {
                                    "bk_data_id": data_id,
                                    "table_id": result_table.table_id,
                                    "bk_biz_id": result_table.bk_biz_id,
                                    "expected_bk_biz_id": cluster_info.bk_biz_id,
                                    "status": "incorrect",
                                }
                            )
                            result["issues"].append(
                                f"数据源data_id:{data_id}对应的结果表{result_table.table_id}bk_biz_id配置错误: {result_table.bk_biz_id}, 期望: {cluster_info.bk_biz_id}"
                            )
                    else:
                        result["issues"].append(f"数据源data_id:{data_id}未找到对应的结果表")

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}的结果表检查异常: {str(e)}")

            result["details"]["result_tables"] = result_table_status

            # 4. 检查EventGroup的bk_biz_id配置
            if cluster_info.K8sEventDataID != 0:
                try:
                    # EventGroup 通过 bk_data_id 关联 DataSource，间接实现租户隔离
                    event_group = models.EventGroup.objects.get(bk_data_id=cluster_info.K8sEventDataID)

                    if event_group.bk_biz_id == cluster_info.bk_biz_id:
                        result["details"]["event_group"] = {
                            "bk_data_id": event_group.bk_data_id,
                            "bk_biz_id": event_group.bk_biz_id,
                            "status": "correct",
                        }
                    else:
                        result["details"]["event_group"] = {
                            "bk_data_id": event_group.bk_data_id,
                            "bk_biz_id": event_group.bk_biz_id,
                            "expected_bk_biz_id": cluster_info.bk_biz_id,
                            "status": "incorrect",
                        }
                        result["issues"].append(
                            f"EventGroup bk_biz_id配置错误: {event_group.bk_biz_id}, 期望: {cluster_info.bk_biz_id}"
                        )

                except models.EventGroup.DoesNotExist:
                    result["issues"].append(f"K8s事件数据源data_id:{cluster_info.K8sEventDataID}的EventGroup不存在")
                except Exception as e:
                    result["issues"].append(f"EventGroup检查异常: {str(e)}")

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("不存在" in issue or "异常" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"空间权限检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_bcs_api_token(self, cluster_info: BCSClusterInfo) -> dict:
        """检查BCS API Token配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化API Token检查输出"""
            lines = []
            if details:
                lines.append(f"    Token已配置: {details.get('api_key_configured', False)}")
                if "token_length" in details:
                    lines.append(f"    Token长度: {details['token_length']} 字符")
            return lines

        result["formatter"] = format_output

        try:
            # 检查API密钥是否配置
            if not cluster_info.api_key_content:
                result["issues"].append("BCS API Token未配置")
                result["status"] = Status.ERROR
                result["details"] = {"api_key_configured": False}
                return result

            # 检查API密钥是否与当前配置一致
            from django.conf import settings

            if cluster_info.api_key_content != settings.BCS_API_GATEWAY_TOKEN:
                result["issues"].append("BCS API Token与当前配置不一致")
                result["status"] = Status.WARNING
            else:
                result["status"] = Status.SUCCESS

            result["details"] = {
                "api_key_configured": True,
                "api_key_match": cluster_info.api_key_content == settings.BCS_API_GATEWAY_TOKEN,
                "token_length": len(cluster_info.api_key_content) if cluster_info.api_key_content else 0,
            }

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"BCS API Token检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_datasource_options(self, cluster_info: BCSClusterInfo) -> dict:
        """检查DataSourceOption数据完整性

        验证数据源的关键配置项是否完整且符合规范
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化DataSourceOption检查输出"""
            lines = []
            if details:
                total_datasources = len(details)
                lines.append(f"    数据源数量: {total_datasources}")
                for data_id, opt_info in list(details.items())[:3]:  # 只显示前3个
                    if isinstance(opt_info, dict) and "options_count" in opt_info:
                        lines.append(f"    数据源data_id:{data_id}: {opt_info['options_count']}个配置项")
            return lines

        result["formatter"] = format_output

        try:
            # 关键配置项列表
            important_options = [
                DataSourceOption.OPTION_TIMESTAMP_UNIT,
                # DataSourceOption.OPTION_ALIGN_TIME_UNIT,
                DataSourceOption.OPTION_DROP_METRICS_ETL_CONFIGS,
            ]

            option_status = {}
            for data_id, datasource in self.data_sources.items():
                try:
                    # 查询该数据源的所有配置项
                    options = DataSourceOption.objects.filter(bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id).only(
                        "name", "value"
                    )

                    option_dict = {opt.name: opt.value for opt in options}

                    missing_options = []
                    for option in important_options:
                        if option not in option_dict:
                            missing_options.append(option)

                    if (
                        datasource.etl_config != "bk_standard_v2_event"
                        and DataSourceOption.OPTION_ALIGN_TIME_UNIT not in option_dict
                    ):
                        missing_options.append(DataSourceOption.OPTION_ALIGN_TIME_UNIT)

                    option_status[data_id] = {
                        "options_count": len(option_dict),
                        "missing_options": missing_options,
                        "configured_options": list(option_dict.keys()),
                    }

                    # 检查缺失的关键配置项
                    if missing_options:
                        result["issues"].append(f"数据源data_id:{data_id}缺少关键配置项: {', '.join(missing_options)}")

                except Exception as e:
                    option_status[data_id] = {"error": str(e)}
                    result["issues"].append(f"数据源data_id:{data_id}配置检查异常: {str(e)}")

            result["details"] = option_status
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"DataSourceOption检查异常: {str(e)}")
            logger.exception(f"检查DataSourceOption时发生异常: {e}")

        return result

    @recode_final_result
    def check_space_type_and_datasource(self, cluster_info: BCSClusterInfo) -> dict:
        """检查空间类型与SpaceDataSource关联

        验证数据源的空间类型配置是否正确
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化空间类型检查输出"""
            lines = []
            if details:
                total_datasources = len(details)
                lines.append(f"    数据源数量: {total_datasources}")
                all_space_count = sum(1 for v in details.values() if isinstance(v, dict) and v.get("is_all_space_type"))
                lines.append(f"    全局空间类型: {all_space_count}/{total_datasources}")
            return lines

        result["formatter"] = format_output

        try:
            space_check_status = {}

            for data_id, datasource in self.data_sources.items():
                try:
                    space_type_id = datasource.space_type_id
                    space_uid = datasource.space_uid

                    # 检查是否为全局空间类型
                    is_all_space_type = space_type_id == SpaceTypes.ALL.value

                    space_datasource_exists = False
                    tenant_consistent = True

                    if not is_all_space_type:
                        # 查询SpaceDataSource关联
                        space_ds = SpaceDataSource.objects.filter(
                            bk_data_id=data_id, space_uid=space_uid, bk_tenant_id=self.bk_tenant_id
                        ).first()

                        if space_ds:
                            space_datasource_exists = True
                            # 检查租户一致性
                            tenant_consistent = space_ds.bk_tenant_id == datasource.bk_tenant_id
                        else:
                            result["issues"].append(
                                f"数据源data_id:{data_id}(space_type:{space_type_id})缺少SpaceDataSource关联"
                            )

                    space_check_status[data_id] = {
                        "space_uid": space_uid,
                        "space_type_id": space_type_id,
                        "is_all_space_type": is_all_space_type,
                        "space_datasource_exists": space_datasource_exists if not is_all_space_type else None,
                        "tenant_consistent": tenant_consistent,
                    }

                    if not is_all_space_type and not tenant_consistent:
                        result["issues"].append(f"数据源data_id:{data_id}的租户ID不一致")

                except Exception as e:
                    space_check_status[data_id] = {"error": str(e)}
                    result["issues"].append(f"数据源data_id:{data_id}空间类型检查异常: {str(e)}")

            result["details"] = space_check_status
            result["status"] = Status.SUCCESS if not result["issues"] else Status.ERROR

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"空间类型检查异常: {str(e)}")
            logger.exception(f"检查空间类型时发生异常: {e}")

        return result

    @recode_final_result
    def check_custom_report_subscription(self, cluster_info: BCSClusterInfo) -> dict:
        """检查CustomReportSubscription配置

        验证BCS集群的自定义上报订阅配置是否正确
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化CustomReportSubscription检查输出"""
            lines = []
            if details:
                lines.append(f"    订阅数量: {details.get('subscription_count', 0)}")
                if details.get("subscription_exists"):
                    lines.append(f"    业务ID: {details.get('bk_biz_id')}")
            return lines

        result["formatter"] = format_output

        try:
            bk_biz_id = cluster_info.bk_biz_id

            # 查询自定义上报订阅配置
            subscriptions = CustomReportSubscription.objects.filter(bk_biz_id=bk_biz_id)

            subscription_count = subscriptions.count()
            subscription_details = []

            for sub in subscriptions:
                try:
                    # 检查订阅参数完整性
                    config_complete = bool(sub.config)

                    if hasattr(sub, "subscription_id") and sub.subscription_id:
                        # 配置存在
                        pass

                    subscription_details.append(
                        {
                            "subscription_id": sub.id,
                            "bk_data_id": sub.bk_data_id,
                            "config_complete": config_complete,
                        }
                    )

                except Exception as e:
                    result["issues"].append(f"订阅{sub.id}检查异常: {str(e)}")

            result["details"] = {
                "bk_biz_id": bk_biz_id,
                "subscription_exists": subscription_count > 0,
                "subscription_count": subscription_count,
                "subscriptions": subscription_details,
            }

            if subscription_count == 0:
                result["status"] = Status.WARNING
                result["issues"].append("没有找到自定义上报订阅配置")
            else:
                result["status"] = Status.SUCCESS

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"CustomReportSubscription检查异常: {str(e)}")
            logger.exception(f"检查CustomReportSubscription时发生异常: {e}")

        return result

    @recode_final_result
    def check_related_models(self, cluster_info: BCSClusterInfo) -> dict:
        """检查关联模型数据完整性

        验证结果表相关的配置数据是否完整
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化关联模型检查输出"""
            lines = []
            if details:
                ds_rt_count = len(details.get("datasource_result_table", {}))
                rt_options_count = len(details.get("result_table_options", {}))
                lines.append(f"    数据源结果表: {ds_rt_count}")
                lines.append(f"    结果表配置: {rt_options_count}")
            return lines

        result["formatter"] = format_output

        try:
            datasource_result_table = {}
            result_table_options = {}
            result_table_fields = {}
            result_table_field_options = {}

            # 检查 DataSourceResultTable
            for data_id, datasource in self.data_sources.items():
                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if ds_rt:
                        table_id = ds_rt.table_id
                        tenant_consistent = ds_rt.bk_tenant_id == datasource.bk_tenant_id

                        datasource_result_table[data_id] = {
                            "table_id": table_id,
                            "relation_exists": True,
                            "tenant_consistent": tenant_consistent,
                        }

                        # 检查ResultTableOption
                        options = ResultTableOption.objects.filter(table_id=table_id, bk_tenant_id=self.bk_tenant_id)
                        option_names = [opt.name for opt in options]

                        result_table_options[table_id] = {
                            "options_count": len(option_names),
                            "required_options_present": True,
                            "configured_options": option_names,
                        }

                        # 检查ResultTableField
                        fields = ResultTableField.objects.filter(table_id=table_id, bk_tenant_id=self.bk_tenant_id)

                        time_field_exists = fields.filter(field_name="time").exists()
                        metric_fields = fields.filter(tag=ResultTableField.FIELD_TAG_METRIC)
                        dimension_fields = fields.filter(tag=ResultTableField.FIELD_TAG_DIMENSION)

                        result_table_fields[table_id] = {
                            "total_fields": fields.count(),
                            "time_field_exists": time_field_exists,
                            "metric_fields_count": metric_fields.count(),
                            "dimension_fields_count": dimension_fields.count(),
                        }

                        if not time_field_exists:
                            result["issues"].append(f"结果表{table_id}缺少时间字段")

                        # 检查ResultTableFieldOption
                        field_options = ResultTableFieldOption.objects.filter(
                            table_id=table_id, bk_tenant_id=self.bk_tenant_id
                        )

                        result_table_field_options[table_id] = {
                            "fields_with_options": field_options.values("field_name").distinct().count(),
                        }

                    else:
                        datasource_result_table[data_id] = {"relation_exists": False}
                        result["issues"].append(f"数据源data_id:{data_id}缺少结果表关联")

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}关联模型检查异常: {str(e)}")

            result["details"] = {
                "datasource_result_table": datasource_result_table,
                "result_table_options": result_table_options,
                "result_table_fields": result_table_fields,
                "result_table_field_options": result_table_field_options,
            }

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"关联模型检查异常: {str(e)}")
            logger.exception(f"检查关联模型时发生异常: {e}")

        return result

    @recode_final_result
    def check_influxdb_storage_config(self, cluster_info: BCSClusterInfo) -> dict:
        """检查InfluxDB存储配置

        验证InfluxDB存储相关配置的完整性和正确性
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化InfluxDB存储配置检查输出"""
            lines = []
            if details:
                proxy_count = details.get("influxdb_proxy_storage", {}).get("total_records", 0)
                cluster_count = details.get("influxdb_cluster_info", {}).get("total_clusters", 0)
                host_count = details.get("influxdb_host_info", {}).get("total_hosts", 0)
                lines.append(f"    代理存储: {proxy_count}")
                lines.append(f"    集群: {cluster_count}")
                lines.append(f"    主机: {host_count}")
            return lines

        result["formatter"] = format_output

        try:
            # 检查InfluxDBProxyStorage
            proxy_storage_details = []
            influxdb_storages = []

            for data_id in self.data_sources.keys():
                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if not ds_rt:
                        continue

                    # 查询InfluxDB存储
                    influx_storages = InfluxDBStorage.objects.filter(
                        table_id=ds_rt.table_id, bk_tenant_id=self.bk_tenant_id
                    )

                    for storage in influx_storages:
                        influxdb_storages.append(storage)

                        # 检查代理存储配置
                        if hasattr(storage, "influxdb_proxy_storage_id"):
                            try:
                                proxy_storage = InfluxDBProxyStorage.objects.filter(
                                    proxy_cluster_id=storage.influxdb_proxy_storage_id
                                ).first()

                                if proxy_storage:
                                    proxy_storage_details.append(
                                        {
                                            "proxy_cluster_id": proxy_storage.proxy_cluster_id,
                                            "service_name": proxy_storage.service_name,
                                            "instance_cluster_name": proxy_storage.instance_cluster_name,
                                            "is_default": proxy_storage.is_default,
                                        }
                                    )
                                else:
                                    result["issues"].append(f"存储{storage.table_id}的代理存储配置不存在")
                            except Exception as e:
                                result["issues"].append(f"存储{storage.table_id}代理配置检查异常: {str(e)}")

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}InfluxDB存储检查异常: {str(e)}")

            # 检查InfluxDBClusterInfo
            cluster_details = []
            try:
                clusters = InfluxDBClusterInfo.objects.all()
                for cluster in clusters:
                    # 获取集群关联的主机数量
                    host_count = InfluxDBClusterInfo.objects.filter(cluster_name=cluster.cluster_name).count()

                    cluster_details.append(
                        {
                            "cluster_name": cluster.cluster_name,
                            "host_count": host_count,
                            "host_readable": cluster.host_readable,
                        }
                    )

            except Exception as e:
                result["issues"].append(f"InfluxDBClusterInfo检查异常: {str(e)}")

            # 检查InfluxDBHostInfo
            host_details = []
            try:
                hosts = InfluxDBHostInfo.objects.all()
                for host in hosts:
                    host_details.append(
                        {
                            "host_name": host.host_name,
                            "domain_name": host.domain_name,
                            "port": host.port,
                        }
                    )

            except Exception as e:
                result["issues"].append(f"InfluxDBHostInfo检查异常: {str(e)}")

            result["details"] = {
                "influxdb_proxy_storage": {
                    "total_records": len(proxy_storage_details),
                    "proxy_details": proxy_storage_details,
                },
                "influxdb_cluster_info": {
                    "total_clusters": len(set([c["cluster_name"] for c in cluster_details])),
                    "clusters_detail": cluster_details,
                },
                "influxdb_host_info": {
                    "total_hosts": len(host_details),
                    "host_details": host_details[:10],  # 只显示前10个
                },
            }

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"InfluxDB存储配置检查异常: {str(e)}")
            logger.exception(f"检查InfluxDB存储配置时发生异常: {e}")

        return result

    @recode_final_result
    def check_vm_datalink_dependencies(self, cluster_info: BCSClusterInfo) -> dict:
        """检查VM数据链路依赖模型

        验证VM数据链路创建和访问所依赖的各个模型配置是否完整
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化VM数据链路依赖检查输出"""
            lines = []
            if details:
                vm_record_count = details.get("access_vm_record", {}).get("total_records", 0)
                link_count = details.get("data_link", {}).get("total_links", 0)
                is_federal = details.get("federal_cluster_info", {}).get("is_federal", False)
                lines.append(f"    VM访问记录: {vm_record_count}")
                lines.append(f"    数据链路: {link_count}")
                lines.append(f"    联邦集群: {'是' if is_federal else '否'}")
            return lines

        result["formatter"] = format_output

        try:
            access_vm_records = []
            data_link_records = []
            federal_cluster_records = []
            bkbase_result_tables = []

            # 检查AccessVMRecord
            for data_id in self.data_sources.keys():
                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if not ds_rt:
                        continue

                    # 查询VM访问记录
                    vm_records = AccessVMRecord.objects.filter(
                        result_table_id=ds_rt.table_id, bk_tenant_id=self.bk_tenant_id
                    )

                    for vm_record in vm_records:
                        access_vm_records.append(
                            {
                                "result_table_id": vm_record.result_table_id,
                                "vm_result_table_id": vm_record.vm_result_table_id,
                                "vm_cluster_id": vm_record.vm_cluster_id,
                                "storage_cluster_id": vm_record.storage_cluster_id,
                                "data_type": vm_record.data_type,
                            }
                        )

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}VM访问记录检查异常: {str(e)}")

            # 检查DataLink
            try:
                data_links = DataLink.objects.filter(bk_tenant_id=self.bk_tenant_id)

                for data_link in data_links:
                    data_link_records.append(
                        {
                            "data_link_name": data_link.data_link_name,
                            "data_link_strategy": data_link.data_link_strategy,
                            "namespace": data_link.namespace,
                        }
                    )

            except Exception as e:
                result["issues"].append(f"DataLink检查异常: {str(e)}")

            # 检查BcsFederalClusterInfo
            try:
                federal_clusters = BcsFederalClusterInfo.objects.filter(
                    fed_cluster_id=cluster_info.cluster_id, is_deleted=False
                )

                for fed_cluster in federal_clusters:
                    federal_cluster_records.append(
                        {
                            "fed_cluster_id": fed_cluster.fed_cluster_id,
                            "sub_cluster_id": fed_cluster.sub_cluster_id,
                            "fed_namespaces": fed_cluster.fed_namespaces,
                            "builtin_metric_table_id": fed_cluster.fed_builtin_metric_table_id,
                        }
                    )

            except Exception as e:
                result["issues"].append(f"BcsFederalClusterInfo检查异常: {str(e)}")

            # 检查BkBaseResultTable
            try:
                bkbase_tables = BkBaseResultTable.objects.filter(bk_tenant_id=self.bk_tenant_id)

                for bkbase_table in bkbase_tables:
                    bkbase_result_tables.append(
                        {
                            "data_link_name": bkbase_table.data_link_name,
                            "monitor_table_id": bkbase_table.monitor_table_id,
                            "bkbase_table_id": bkbase_table.bkbase_table_id,
                            "storage_type": bkbase_table.storage_type,
                            "status": bkbase_table.status,
                        }
                    )

            except Exception as e:
                result["issues"].append(f"BkBaseResultTable检查异常: {str(e)}")

            result["details"] = {
                "access_vm_record": {
                    "total_records": len(access_vm_records),
                    "table_mapping": access_vm_records[:10],  # 只显示前10个
                },
                "data_link": {
                    "total_links": len(data_link_records),
                    "link_details": data_link_records[:10],
                },
                "federal_cluster_info": {
                    "is_federal": len(federal_cluster_records) > 0,
                    "federal_count": len(federal_cluster_records),
                    "federal_details": federal_cluster_records,
                },
                "bkbase_result_table": {
                    "total_tables": len(bkbase_result_tables),
                    "table_details": bkbase_result_tables[:10],
                },
            }

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"VM数据链路依赖检查异常: {str(e)}")
            logger.exception(f"检查VM数据链路依赖时发生异常: {e}")

        return result

    @recode_final_result
    def check_cloud_id_configuration(self, cluster_info: BCSClusterInfo) -> dict:
        """检查云区域ID配置状态"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化云区域ID配置检查输出"""
            lines = []
            if details:
                lines.append(f"    云区域ID已配置: {details.get('cloud_id_configured', False)}")
                if details.get("bk_cloud_id") is not None:
                    lines.append(f"    云区域ID: {details['bk_cloud_id']}")
            return lines

        result["formatter"] = format_output

        try:
            # 检查云区域ID是否配置
            if cluster_info.bk_cloud_id is None:
                result["issues"].append("云区域ID未配置")
                result["status"] = Status.WARNING
            else:
                result["status"] = Status.SUCCESS

            result["details"] = {
                "bk_cloud_id": cluster_info.bk_cloud_id,
                "cloud_id_configured": cluster_info.bk_cloud_id is not None,
            }

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"云区域ID配置检查异常: {str(e)}")

        return result

    def is_federation_cluster(self, cluster_info: BCSClusterInfo) -> bool:
        """判断是否为联邦集群"""
        try:
            return BcsFederalClusterInfo.objects.filter(
                fed_cluster_id=cluster_info.cluster_id, is_deleted=False
            ).exists()
        except Exception:
            return False

    def output_text_report(self, check_result: dict):
        """输出文本格式的检测报告"""
        cluster_id = check_result["cluster_id"]
        status = check_result["status"]

        # 输出标题
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("BCS集群关联状态检测报告"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # 输出基本信息
        self.stdout.write(f"集群ID: {cluster_id}")
        self.stdout.write(f"检测时间: {check_result['check_time']}")
        self.stdout.write(f"执行时间: {check_result['execution_time']}秒")

        # 输出整体状态
        status_style = self.get_status_style(status)
        self.stdout.write(f"整体状态: {status_style(status)}")

        # 输出详细信息
        if check_result.get("details"):
            self.stdout.write("\n详细检测结果:")
            self.output_detailed_results(check_result["details"])

        # 输出错误和警告
        if check_result.get("errors"):
            self.stdout.write(f"\n{self.style.ERROR('错误信息:')}")
            for error in check_result["errors"]:
                self.stdout.write(f"  • {self.style.ERROR(error)}")

        if check_result.get("warnings"):
            self.stdout.write(f"\n{self.style.WARNING('警告信息:')}")
            for warning in check_result["warnings"]:
                self.stdout.write(f"  • {self.style.WARNING(warning)}")

    def output_detailed_results(self, details: dict):
        """输出详细检测结果"""
        for component, result in details.items():
            if not isinstance(result, dict):
                continue

            status = result.get("status", Status.UNKNOWN)
            style = self.get_status_style(status)

            self.stdout.write(f"\n  {component.upper()}: {style(status)}")

            # 输出问题信息
            if result.get("issues"):
                for issue in result["issues"]:
                    self.stdout.write(f"    ⚠ {issue}")

            # 调用对应的格式化函数输出关键信息
            formatter = result.get("formatter")
            if formatter and callable(formatter):
                try:
                    lines = formatter(result.get("details", {}))
                    for line in lines:
                        self.stdout.write(line)
                except Exception as e:
                    logger.warning(f"输出{component}格式化信息失败: {e}")

    def get_status_style(self, status: str):
        """根据状态获取样式函数"""
        status_styles = {
            Status.SUCCESS: self.style.SUCCESS,
            Status.WARNING: self.style.WARNING,
            Status.ERROR: self.style.ERROR,
            Status.NOT_FOUND: self.style.ERROR,
            Status.UNKNOWN: self.style.NOTICE,
        }
        return status_styles.get(status, self.style.NOTICE)
