"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from django.db.models.manager import BaseManager
import json
import time
import logging

from kubernetes import client as k8s_client
from kubernetes.dynamic import client as dynamic_client
from kubernetes.client.rest import ApiException
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings

from core.drf_resource import api
from metadata import models, config
from metadata.models.bcs.cluster import BCSClusterInfo
from metadata.models.constants import DataIdCreatedFromSystem
from metadata.models.data_source import DataSource, DataSourceOption
from metadata.models.bcs.resource import ServiceMonitorInfo, PodMonitorInfo
from metadata.models.storage import ClusterInfo, InfluxDBStorage, ESStorage, InfluxDBProxyStorage, DorisStorage
from metadata.models import BcsFederalClusterInfo, TimeSeriesGroup, EventGroup
from metadata.models.space.space import SpaceDataSource, Space
from metadata.models.space.constants import SpaceTypes, SpaceStatus, ENABLE_V4_DATALINK_ETL_CONFIGS
from metadata.models.custom_report.subscription_config import CustomReportSubscription
from metadata.models.result_table import (
    ResultTable,
    ResultTableOption,
    ResultTableField,
    ResultTableFieldOption,
    DataSourceResultTable, LogV4DataLinkOption,
)
from metadata.models.influxdb_cluster import InfluxDBClusterInfo, InfluxDBHostInfo
from metadata.models.vm.record import AccessVMRecord
from metadata.models.data_link.data_link import DataLink
from metadata.models.bkdata.result_table import BkBaseResultTable
from metadata.utils import hash_util, consul_tools

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
        status = result.get("status", Status.UNKNOWN).upper()

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
            # 输出检测开始信息
            if format_type == "text":
                self.stdout.write(self.style.SUCCESS("=" * 60))
                self.stdout.write(self.style.SUCCESS("BCS集群关联状态检测"))
                self.stdout.write(self.style.SUCCESS("=" * 60))
                self.stdout.write(f"集群ID: {cluster_id}")
                self.stdout.write(f"检测时间: {timezone.now().isoformat()}")
                self.stdout.write("")

            # 执行集群状态检测（检测过程中已经实时输出结果）
            check_result = self.check_cluster_status(cluster_id, timeout)

            # 输出汇总信息
            if format_type == "json":
                self.stdout.write(json.dumps(check_result, indent=2, ensure_ascii=False, default=str))
            else:
                self.output_summary_report(check_result)

        except Exception as e:
            logger.exception(f"检测集群状态时发生异常: {e}")
            raise CommandError(f"集群状态检测失败: {e}")

    def output_check_result(self, component: str, result: dict):
        """立即输出单个检查项的结果"""
        if not isinstance(result, dict):
            return

        status = result.get("status", Status.UNKNOWN)
        style = self.get_status_style(status)

        self.stdout.write(f"    result: {style(status)}")

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
                self.stdout.write(self.style.ERROR(f"输出{component}格式化信息失败: {e}"))

        self.stdout.write("")  # 空行分隔

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
            self.stdout.write(f"\n正在检查集群 {cluster_id} 的数据库记录...")
            db_check = self.check_database_record(cluster_id)
            check_result["details"]["database"] = db_check
            self.output_check_result("database", db_check)

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
            self.output_check_result("check_bcs_api_connection", bcs_api_check)

            # 4. 数据源配置验证
            self.stdout.write("正在验证数据源配置...")
            datasource_check = self.check_datasource_configuration(cluster_info)
            check_result["details"]["datasources"] = datasource_check
            self.output_check_result("check_datasource_configuration", datasource_check)

            # 17. 检查DataSourceOption配置
            self.stdout.write("正在检查DataSourceOption配置...")
            datasource_options_check = self.check_datasource_options(cluster_info)
            check_result["details"]["datasource_options"] = datasource_options_check
            self.output_check_result("check_datasource_options", datasource_options_check)

            # 18. 检查关联mq_cluster是否正常
            self.stdout.write("正在检查关联mq_cluster是否正常...")
            mq_cluster_check = self.check_mq_cluster(cluster_info)
            check_result["details"]["mq_cluster"] = mq_cluster_check
            self.output_check_result("check_mq_cluster", mq_cluster_check)

            # 19. 检查空间类型与SpaceDataSource关联
            self.stdout.write("正在检查datasource、space空间配置...")
            space_type_check = self.check_space_type_and_datasource(cluster_info)
            check_result["details"]["space_type"] = space_type_check
            self.output_check_result("check_space_type_and_datasource", space_type_check)

            # 5. 监控资源状态检查
            self.stdout.write("正在检查监控资源状态...")
            monitor_check = self.check_monitor_resources(cluster_info)
            check_result["details"]["monitor_resources"] = monitor_check
            self.output_check_result("check_monitor_resources", monitor_check)

            # 22. 检查关联的结果表
            self.stdout.write("正在检查关联的结果表...")
            related_models_check = self.check_related_result_table(cluster_info)
            check_result["details"]["related_result_table"] = related_models_check
            self.output_check_result("check_related_result_table", related_models_check)

            # 23. 检查InfluxDB存储配置
            self.stdout.write("正在检查InfluxDB存储配置...")
            influxdb_storage_check = self.check_influxdb_storage_config(cluster_info)
            check_result["details"]["influxdb_storage"] = influxdb_storage_check
            self.output_check_result("check_influxdb_storage_config", influxdb_storage_check)

            # 24. 检查VM数据链路依赖
            self.stdout.write("正在检查VM数据链路依赖...")
            vm_datalink_check = self.check_vm_datalink_dependencies(cluster_info)
            check_result["details"]["vm_datalink_dependencies"] = vm_datalink_check
            self.output_check_result("check_vm_datalink_dependencies", vm_datalink_check)

            # 25. 检查VM发布空间路由
            self.stdout.write("正在检查VM发布空间路由...")
            vm_publish_space_router_check = self.check_vm_publish_space_router(cluster_info)
            check_result["details"]["vm_publish_space_router"] = vm_publish_space_router_check
            self.output_check_result("check_vm_publish_space_router", vm_publish_space_router_check)

            # 检查日志v4数据链路
            self.stdout.write("正在检查日志v4数据链路...")
            log_v4_datalink_check = self.check_log_datalink(cluster_info)
            check_result["details"]["log_v4_datalink"] = log_v4_datalink_check
            self.output_check_result("check_log_datalink", log_v4_datalink_check)

            # 6. 数据存储链路检查
            self.stdout.write("正在检查数据存储...")
            storage_check = self.check_storage_clusters(cluster_info)
            check_result["details"]["storage"] = storage_check
            self.output_check_result("check_storage_clusters", storage_check)

            # 9. 联邦集群关系检查（如果是联邦集群）
            if self.is_federation_cluster(cluster_info):
                self.stdout.write("正在检查联邦集群关系...")
                federation_check = self.check_federation_cluster(cluster_info)
                check_result["details"]["federation"] = federation_check
                self.output_check_result("check_federation_cluster", federation_check)

            # 12. 集群初始化资源检查
            # todo 待确认
            # self.stdout.write("正在检查集群初始化资源...")
            # init_resource_check = self.check_cluster_init_resources(cluster_info)
            # check_result["details"]["init_resources"] = init_resource_check
            # self.output_check_result("check_cluster_init_resources", init_resource_check)

            # 19. 检查datasource的Consul配置
            self.stdout.write("正在检查datasource的Consul配置...")
            consul_config = self.check_datasource_consul_config(cluster_info)
            check_result["details"]["datasource_consul_config"] = consul_config
            self.output_check_result("check_datasource_consul_config", consul_config)

            # 12.1 检查BCS集群CRD资源状态
            # todo 增加对replace 替换配置模型的检查
            self.stdout.write("正在检查BCS集群CRD资源...")
            crd_resource_check = self.check_bcs_cluster_crd_resource(cluster_info)
            check_result["details"]["crd_resources"] = crd_resource_check
            self.output_check_result("check_bcs_cluster_crd_resource", crd_resource_check)

            # 13. bk-collector配置检查
            # todo 待确认
            # self.stdout.write("正在检查bk-collector配置...")
            # collector_config_check = self.check_bk_collector_config(cluster_info)
            # check_result["details"]["bk_collector"] = collector_config_check
            # self.output_check_result("check_bk_collector_config", collector_config_check)

            # 15. 检查BCS API Token配置
            self.stdout.write("正在检查BCS API Token配置...")
            api_token_check = self.check_bcs_api_token(cluster_info)
            check_result["details"]["api_token"] = api_token_check
            self.output_check_result("check_bcs_api_token", api_token_check)

            # 16. 检查云区域ID配置
            self.stdout.write("正在检查云区域ID配置...")
            cloud_id_check = self.check_cloud_id_configuration(cluster_info)
            check_result["details"]["cloud_id"] = cloud_id_check
            self.output_check_result("check_cloud_id_configuration", cloud_id_check)

            # 20. 检查CustomReportSubscription
            self.stdout.write("正在检查CustomReportSubscription...")
            custom_report_sub_check = self.check_custom_report_subscription(cluster_info)
            check_result["details"]["custom_report_subscription"] = custom_report_sub_check
            self.output_check_result("check_custom_report_subscription", custom_report_sub_check)

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
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}集群状态异常: {cluster_info.status}")

            # 检查数据源ID配置
            missing_data_ids = []
            for data_type, data_id in result["details"]["data_ids"].items():
                if data_id == 0:
                    missing_data_ids.append(data_type)

            if missing_data_ids:
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}缺少数据源ID配置: {', '.join(missing_data_ids)}")

        except BCSClusterInfo.DoesNotExist:
            result["status"] = Status.NOT_FOUND
            message = f"[BCSClusterInfo] [cluster_id={cluster_id}] "
            result["issues"].append(f"{message}集群记录在数据库中不存在")
        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[BCSClusterInfo] [cluster_id={cluster_id}] "
            result["issues"].append(f"{message}数据库查询异常: {str(e)}")

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
                    message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                    result["issues"].append(
                        f"{message}集群状态不一致 - 数据库: {cluster_info.status}, BCS API: {target_cluster.get('status')}"
                    )
            else:
                result["status"] = Status.WARNING
                result["details"] = {"api_accessible": True, "cluster_found": False}
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}集群在BCS API中未找到，可能已被删除")

        except Exception as e:
            result["status"] = Status.ERROR
            result["details"] = {"api_accessible": False, "error": str(e)}
            message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}BCS API连接失败: {str(e)}")

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
            datasource_status = {}
            for data_id, datasource in self.data_sources.items():
                try:
                    # 检查数据源记录
                    datasource_status[data_id] = {
                        "exists": True,
                        "data_name": datasource.data_name,
                        "is_enable": datasource.is_enable,
                        "type_label": datasource.type_label,
                    }

                    # 检查数据源是否启用
                    if not datasource.is_enable:
                        message = f"[DataSource] [bk_data_id={data_id}] "
                        result["issues"].append(f"{message}未启用")

                except DataSource.DoesNotExist:
                    datasource_status[data_id] = {"exists": False}
                    message = f"[DataSource] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}不存在")

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
            message = f"[DataSource] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}数据源配置检查异常: {str(e)}")

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
            service_monitors = ServiceMonitorInfo.objects.filter(cluster_id=cluster_info.cluster_id)
            service_monitor_count = service_monitors.count()

            # 检查PodMonitor资源
            pod_monitors = PodMonitorInfo.objects.filter(cluster_id=cluster_info.cluster_id)
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
            message = f"[ServiceMonitor/PodMonitor] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}监控资源检查异常: {str(e)}")

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
                        message = f"[DataSourceResultTable] [bk_data_id={data_id}] "
                        result["issues"].append(f"{message}未找到结果表关联")
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
                            message = f"[InfluxDBStorage] [bk_data_id={data_id},cluster_name={storage.storage_cluster.cluster_name}] "
                            result["issues"].append(f"{message}集群状态异常")

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
                            message = f"[ESStorage] [bk_data_id={data_id},cluster_name={storage.storage_cluster.cluster_name}] "
                            result["issues"].append(f"{message}集群状态异常")

                except Exception as e:
                    storage_status[data_id] = {"exists": False, "error": str(e)}
                    message = f"[Storage] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}存储检查异常: {str(e)}")

            result["details"] = {"storage_status": storage_status}
            result["status"] = (
                Status.SUCCESS
                if not result["issues"]
                else (Status.WARNING if any("状态异常" in issue for issue in result["issues"]) else Status.ERROR)
            )

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[Storage] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}存储集群检查异常: {str(e)}")

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
    def check_datasource_consul_config(self, cluster_info: BCSClusterInfo) -> dict:
        """检查datasource Consul配置"""
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化Consul配置检查输出"""
            lines = []
            if details:
                consul_status = details.get("consul_status", {})
                consistent_count = sum(1 for status in consul_status.values() if status.get("is_consistent"))
                total_count = len(consul_status)
                lines.append(f"    配置一致性: {consistent_count}/{total_count}个数据源配置一致")

                if details.get("skipped_count", 0) > 0:
                    lines.append(f"    跳过检查: {details['skipped_count']}个数据源(不支持Consul同步)")
            return lines

        result["formatter"] = format_output

        try:
            hash_consul = consul_tools.HashConsul()
            consul_status = {}
            skipped_count = 0

            for data_id, datasource in self.data_sources.items():
                try:
                    # 检查数据源是否支持Consul配置刷新
                    if not datasource.can_refresh_consul_and_gse():
                        skipped_count += 1
                        consul_status[data_id] = {
                            "path": datasource.consul_config_path,
                            "skipped": True,
                            "reason": "数据源不支持Consul配置刷新",
                        }
                        continue

                    # 获取Consul中的配置
                    num, consul_config = hash_consul.get(datasource.consul_config_path)
                    consul_config = consul_config.get("Value", {})
                    if isinstance(consul_config, str):
                        try:
                            consul_config = json.loads(consul_config)
                        except json.JSONDecodeError:
                            consul_status[data_id] = {"error": "Consul配置JSON解析失败"}
                            message = f"[DataSource] [bk_data_id={data_id}] "
                            result["issues"].append(f"{message}Consul配置JSON解析失败")
                            continue

                    if not consul_config:
                        consul_status[data_id] = {
                            "path": datasource.consul_config_path,
                            "exists": False,
                            "is_consistent": False,
                        }
                        message = f"[DataSource] [bk_data_id={data_id},consul_path={datasource.consul_config_path}] "
                        result["issues"].append(f"{message}Consul配置不存在")
                        continue

                    # 生成数据源的标准配置
                    datasource_config = datasource.to_json(is_consul_config=True)

                    # 比较配置是否一致
                    is_consistent = consul_config == datasource_config
                    consul_status[data_id] = {
                        "path": datasource.consul_config_path,
                        "exists": True,
                        "is_consistent": is_consistent,
                    }

                    if not is_consistent:
                        # 记录配置不一致的详细信息
                        diff_keys = self._find_config_diff(consul_config, datasource_config)
                        consul_status[data_id]["diff_keys"] = diff_keys
                        message = f"[DataSource] [bk_data_id={data_id},consul_path={datasource.consul_config_path}] "
                        result["issues"].append(
                            f"{message}Consul配置与数据库配置不一致, 差异字段:{','.join(diff_keys)}"
                        )

                except Exception as e:
                    consul_status[data_id] = {"error": str(e)}
                    message = f"[DataSource] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}配置检查异常: {str(e)}")
                    logger.exception(f"data_id->[{data_id}] consul config check failed: {e}")

            result["details"] = {
                "consul_status": consul_status,
                "skipped_count": skipped_count,
                "total_count": len(self.data_sources),
            }
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[Consul] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}Consul配置检查异常: {str(e)}")
            logger.exception(f"check_datasource_consul_config failed: {e}")

        return result

    def _find_config_diff(self, consul_config: dict, datasource_config: dict, prefix: str = "") -> list[str]:
        """查找两个配置字典的差异字段"""
        diff_keys = []
        all_keys = set(consul_config.keys()) | set(datasource_config.keys())

        for key in all_keys:
            current_path = f"{prefix}.{key}" if prefix else key

            if key not in consul_config:
                diff_keys.append(f"consul 配置缺失{current_path} 字段")
            elif key not in datasource_config:
                diff_keys.append(f"consul 配置多余{current_path} 字段")
            else:
                val1, val2 = consul_config[key], datasource_config[key]
                if isinstance(val1, dict) and isinstance(val2, dict):
                    # 递归比较嵌套字典
                    diff_keys.extend(self._find_config_diff(val1, val2, current_path))
                elif val1 != val2:
                    diff_keys.append(current_path)

        return diff_keys

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
                message = f"[BcsFederalClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}联邦集群信息不存在")
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
                    message = f"[BcsFederalClusterInfo] [sub_cluster_id={fed['sub_cluster_id']}] "
                    result["issues"].append(f"{message}没有配置命名空间")
                if not fed["builtin_metric_table_id"]:
                    message = f"[BcsFederalClusterInfo] [sub_cluster_id={fed['sub_cluster_id']}] "
                    result["issues"].append(f"{message}缺少内置指标表ID")

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[BcsFederalClusterInfo] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}联邦集群检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_bcs_cluster_crd_resource(self, cluster_info: BCSClusterInfo) -> dict:
        """检查BCS集群CRD资源状态

        检查项目包括：
        1. DataIDResource CRD定义是否存在
        2. 集群的DataIDResource资源配置状态
        3. 资源配置与数据库配置的一致性
        4. 资源标签和元数据完整性
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化CRD资源检查输出"""
            lines = []
            if details:
                crd_status = details.get("crd_status", {})
                if crd_status.get("exists"):
                    lines.append(f"    CRD定义: {crd_status.get('kind')}/{crd_status.get('version')}")

                resources = details.get("dataid_resources", [])
                if resources:
                    consistent_count = sum(1 for r in resources if r.get("is_consistent"))
                    lines.append(f"    DataID资源: {len(resources)}个, 配置一致: {consistent_count}/{len(resources)}")
            return lines

        result["formatter"] = format_output

        try:
            # 获取动态客户端
            try:
                d_client = dynamic_client.DynamicClient(cluster_info.api_client)
            except Exception as e:
                result["status"] = Status.ERROR
                message = f"[DynamicClient] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}无法连接到BCS集群: {str(e)}")
                logger.exception(f"Failed to get dynamic client for cluster {cluster_info.cluster_id}: {e}")
                return result

            # 1. 检查DataIDResource CRD定义是否存在
            try:
                resource_api = d_client.resources.get(
                    api_version=f"{config.BCS_RESOURCE_GROUP_NAME}/{config.BCS_RESOURCE_VERSION}",
                    kind=config.BCS_RESOURCE_DATA_ID_RESOURCE_KIND,
                )
                result["details"]["crd_status"] = {
                    "exists": True,
                    "kind": config.BCS_RESOURCE_DATA_ID_RESOURCE_KIND,
                    "version": config.BCS_RESOURCE_VERSION,
                    "group": config.BCS_RESOURCE_GROUP_NAME,
                }
            except ResourceNotFoundError:
                result["status"] = Status.ERROR
                result["details"]["crd_status"] = {"exists": False}
                message = f"[DataIDResource CRD] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}CRD未定义，集群不支持监控资源注入")
                return result
            except Exception as e:
                result["status"] = Status.ERROR
                message = f"[DataIDResource CRD] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查CRD定义失败: {str(e)}")
                logger.exception(f"cluster_id->[{cluster_info.cluster_id}] Failed to check CRD definition: {e}")
                return result

            # 2. 检查集群的DataIDResource资源配置状态
            dataid_resources = []
            is_fed_cluster = BcsFederalClusterInfo.objects.filter(
                fed_cluster_id=cluster_info.cluster_id, is_deleted=False
            ).exists()

            for usage, register_info in cluster_info.DATASOURCE_REGISTER_INFO.items():
                # 联邦集群跳过非自定义指标
                if is_fed_cluster and usage != cluster_info.DATA_TYPE_CUSTOM_METRIC:
                    logger.info(f"cluster_id->[{cluster_info.cluster_id}] skip {usage} for federation cluster")
                    continue

                data_id = getattr(cluster_info, register_info["datasource_name"])
                if data_id == 0:
                    continue

                resource_name = cluster_info.compose_dataid_resource_name(
                    register_info["datasource_name"].lower(), is_fed_cluster=is_fed_cluster
                )

                try:
                    # 获取集群中的资源实际配置
                    cluster_resource = d_client.get(resource=resource_api, name=resource_name)

                    # 生成期望的配置
                    expected_config = cluster_info.make_config(
                        register_info, usage=usage, is_fed_cluster=is_fed_cluster
                    )

                    # 比较配置是否一致
                    is_consistent = self._compare_dataid_resource(cluster_resource, expected_config)

                    resource_detail = {
                        "name": resource_name,
                        "usage": usage,
                        "data_id": data_id,
                        "exists": True,
                        "is_consistent": is_consistent,
                        "spec": {
                            "dataID": cluster_resource.get("spec", {}).get("dataID"),
                            "labels": cluster_resource.get("spec", {}).get("labels", {}),
                        },
                        "metadata": {
                            "creation_timestamp": str(
                                cluster_resource.get("metadata", {}).get("creationTimestamp", "")
                            ),
                            "labels": cluster_resource.get("metadata", {}).get("labels", {}),
                        },
                    }

                    if not is_consistent:
                        diff_info = self._get_dataid_resource_diff(cluster_resource, expected_config)
                        resource_detail["diff"] = diff_info
                        message = (
                            f"[DataIDResource] [cluster_id={cluster_info.cluster_id},resource_name={resource_name}] "
                        )
                        result["issues"].append(f"{message}配置不一致：{', '.join(diff_info)}")
                    dataid_resources.append(resource_detail)

                except NotFoundError:
                    # 资源不存在
                    dataid_resources.append(
                        {
                            "name": resource_name,
                            "usage": usage,
                            "data_id": data_id,
                            "exists": False,
                            "is_consistent": False,
                        }
                    )
                    message = f"[DataIDResource] [cluster_id={cluster_info.cluster_id},resource_name={resource_name},data_id={data_id}] "
                    result["issues"].append(f"{message}不存在于集群中")
                except Exception as e:
                    dataid_resources.append(
                        {
                            "name": resource_name,
                            "usage": usage,
                            "data_id": data_id,
                            "exists": False,
                            "error": str(e),
                        }
                    )
                    message = f"[DataIDResource] [cluster_id={cluster_info.cluster_id},resource_name={resource_name}] "
                    result["issues"].append(f"{message}检查异常: {str(e)}")

            result["details"]["dataid_resources"] = dataid_resources
            result["details"]["is_fed_cluster"] = is_fed_cluster

            # 确定整体状态
            if not dataid_resources:
                result["status"] = Status.WARNING
                message = f"[DataIDResource] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}没有找到任何DataIDResource资源")
            elif all(r.get("exists") and r.get("is_consistent") for r in dataid_resources if "error" not in r):
                result["status"] = Status.SUCCESS
            elif any(not r.get("exists") for r in dataid_resources):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[DataIDResource] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}CRD资源检查异常: {str(e)}")

        return result

    def _compare_dataid_resource(self, cluster_resource: dict, expected_config: dict) -> bool:
        """比较集群中的DataIDResource与期望配置是否一致"""
        try:
            # 比较spec中的关键字段
            cluster_spec = cluster_resource.get("spec", {})
            expected_spec = expected_config.get("spec", {})

            # 比较dataID
            if cluster_spec.get("dataID") != expected_spec.get("dataID"):
                return False

            # 比较labels
            cluster_labels = cluster_spec.get("labels", {})
            expected_labels = expected_spec.get("labels", {})
            if cluster_labels != expected_labels:
                return False

            # 比较metricReplace
            if cluster_spec.get("metricReplace", {}) != expected_spec.get("metricReplace", {}):
                return False

            # 比较dimensionReplace
            if cluster_spec.get("dimensionReplace", {}) != expected_spec.get("dimensionReplace", {}):
                return False

            return True
        except Exception as e:
            logger.warning(f"Failed to compare dataid resource: {e}")
            return False

    def _get_dataid_resource_diff(self, cluster_resource: dict, expected_config: dict) -> list[str]:
        """获取DataIDResource配置差异信息"""
        diff_info = []
        try:
            cluster_spec = cluster_resource.get("spec", {})
            expected_spec = expected_config.get("spec", {})

            # 检查dataID
            if cluster_spec.get("dataID") != expected_spec.get("dataID"):
                diff_info.append(
                    f"dataID不一致(cluster:{cluster_spec.get('dataID')}, expected:{expected_spec.get('dataID')})"
                )

            # 检查labels
            cluster_labels = cluster_spec.get("labels", {})
            expected_labels = expected_spec.get("labels", {})
            for key in set(cluster_labels.keys()) | set(expected_labels.keys()):
                if cluster_labels.get(key) != expected_labels.get(key):
                    diff_info.append(
                        f"labels.{key}不一致(cluster:{cluster_labels.get(key)}, expected:{expected_labels.get(key)})"
                    )

            # 检查metricReplace
            cluster_metric_replace = cluster_spec.get("metricReplace", {})
            expected_metric_replace = expected_spec.get("metricReplace", {})
            if cluster_metric_replace != expected_metric_replace:
                diff_count = len(set(cluster_metric_replace.items()) ^ set(expected_metric_replace.items()))
                diff_info.append(f"metricReplace有{diff_count}个差异")

            # 检查dimensionReplace
            cluster_dimension_replace = cluster_spec.get("dimensionReplace", {})
            expected_dimension_replace = expected_spec.get("dimensionReplace", {})
            if cluster_dimension_replace != expected_dimension_replace:
                diff_count = len(set(cluster_dimension_replace.items()) ^ set(expected_dimension_replace.items()))
                diff_info.append(f"dimensionReplace有{diff_count}个差异")

        except Exception as e:
            diff_info.append(f"检查差异失败: {str(e)}")

        return diff_info

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
                        message = f"[EventGroup] [bk_data_id={cluster_info.K8sEventDataID}] "
                        result["issues"].append(f"{message}EventGroup未启用")

                except models.EventGroup.DoesNotExist:
                    result["details"]["event_group"] = {"exists": False}
                    message = f"[EventGroup] [bk_data_id={cluster_info.K8sEventDataID}] "
                    result["issues"].append(f"{message}EventGroup不存在")

            # 2. 检查TimeSeriesGroup创建状态
            time_series_groups = []
            for data_id in [cluster_info.K8sMetricDataID, cluster_info.CustomMetricDataID]:
                if data_id == 0:
                    continue

                try:
                    # TimeSeriesGroup 通过 bk_data_id 关联 DataSource，间接实现租户隔离
                    ts_groups = models.TimeSeriesGroup.objects.filter(
                        bk_data_id=data_id, is_delete=False, bk_tenant_id=self.bk_tenant_id
                    )
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
                    message = f"[TimeSeriesGroup] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}TimeSeriesGroup检查异常: {str(e)}")

            result["details"]["time_series_groups"] = time_series_groups

            if not time_series_groups:
                message = f"[TimeSeriesGroup] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}没有找到任何TimeSeriesGroup记录")

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
                        message = f"[SpaceDataSource] [bk_data_id={data_id},space_uid={space_uid}] "
                        result["issues"].append(f"{message}未关联到空间")

                except Exception as e:
                    message = f"[SpaceDataSource] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}SpaceDataSource检查异常: {str(e)}")

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
                    message = f"[ConfigMap] [cluster_id={cluster_info.cluster_id}] "
                    result["issues"].append(f"{message}未找到bk-collector相关的ConfigMap配置")

            except ApiException as e:
                message = f"[ConfigMap] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}ConfigMap检查失败: {e.reason}")
            except Exception as e:
                message = f"[ConfigMap] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}ConfigMap检查异常: {str(e)}")

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("不存在" in issue or "异常" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[ClusterInitResources] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}集群初始化资源检查异常: {str(e)}")

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
                    message = f"[DaemonSet] [cluster_id={cluster_info.cluster_id},name=bk-collector] "
                    result["issues"].append(f"{message}未部署")

            except ApiException as e:
                message = f"[DaemonSet] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查失败: {e.reason}")

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
                        message = f"[Pod] [cluster_id={cluster_info.cluster_id},pod_name={pod.metadata.name}] "
                        result["issues"].append(f"{message}状态异常: {pod.status.phase}")

                    # 检查容器重启次数
                    if pod.status.container_statuses:
                        for container in pod.status.container_statuses:
                            if container.restart_count > 5:
                                message = f"[Pod] [cluster_id={cluster_info.cluster_id},pod_name={pod.metadata.name},container_name={container.name}] "
                                result["issues"].append(f"{message}容器重启次数过多: {container.restart_count}")

                result["details"]["pods"] = pod_status

            except ApiException as e:
                message = f"[Pod] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查失败: {e.reason}")

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
                            message = (
                                f"[ConfigMap] [cluster_id={cluster_info.cluster_id},configmap_name={cm.metadata.name}] "
                            )
                            result["issues"].append(f"{message}缺少关键配置: {', '.join(missing_configs)}")

                result["details"]["config_files"] = config_files

            except ApiException as e:
                message = f"[ConfigMap] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}配置文件检查失败: {e.reason}")

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
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}以下数据采集配置无效: {', '.join(invalid_configs)}")

            # 确定整体状态
            if not result["issues"]:
                result["status"] = Status.SUCCESS
            elif any("未部署" in issue or "失败" in issue for issue in result["issues"]):
                result["status"] = Status.ERROR
            else:
                result["status"] = Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[BkCollector] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}bk-collector配置检查异常: {str(e)}")

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
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}BCS API Token未配置")
                result["status"] = Status.ERROR
                result["details"] = {"api_key_configured": False}
                return result

            # 检查API密钥是否与当前配置一致
            from django.conf import settings

            if cluster_info.api_key_content != settings.BCS_API_GATEWAY_TOKEN:
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}BCS API Token与当前配置不一致")
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
            message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}BCS API Token检查异常: {str(e)}")

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
                        message = f"[DataSourceOption] [bk_data_id={data_id}] "
                        result["issues"].append(f"{message}缺少关键配置项: {', '.join(missing_options)}")

                except Exception as e:
                    option_status[data_id] = {"error": str(e)}
                    message = f"[DataSourceOption] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}配置检查异常: {str(e)}")

            result["details"] = option_status
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[DataSourceOption] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}检查异常: {str(e)}")
            logger.exception(f"检查DataSourceOption时发生异常: {e}")

        return result

    def _get_space_info_by_biz_id(self, bk_biz_id: int, datasource: DataSource) -> dict:
        """
        通过业务ID获取空间信息
        """

        target_bk_biz_id = bk_biz_id
        data_id = datasource.bk_data_id

        if target_bk_biz_id == 0:
            if TimeSeriesGroup.objects.filter(bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id).exists():
                # 自定义时序指标，查找所属空间
                target_bk_biz_id = datasource.data_name.split("_")[0]
            elif EventGroup.objects.filter(bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id).exists():
                # 自定义事件，查找所属空间
                target_bk_biz_id = datasource.data_name.split("_")[-1]
            try:
                # 不符合要求的data_name，无法解析业务字段，使用默认全局业务。
                target_bk_biz_id = int(target_bk_biz_id)
            except (ValueError, TypeError):
                target_bk_biz_id = 0

        space_type_id = datasource.space_type_id
        space_uid = datasource.space_uid

        if target_bk_biz_id != 0:
            space = Space.objects.get_space_info_by_biz_id(bk_biz_id=int(target_bk_biz_id))
            space_type_id, space_uid = space["space_type"], space["space_id"]

        return {
            "space_type_id": space_type_id,
            "space_uid": space_uid,
        }

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
                    space_info = self._get_space_info_by_biz_id(bk_biz_id=self.bk_biz_id, datasource=datasource)
                    space_type_id = space_info.get("space_type_id", datasource.space_type_id)
                    space_uid = space_info.get("space_uid", datasource.space_uid)

                    # 检查是否为全局空间类型
                    is_all_space_type = space_type_id == SpaceTypes.ALL.value

                    space_datasource_exists = False

                    if space_type_id and space_uid:
                        # 查询SpaceDataSource关联
                        space_ds = SpaceDataSource.objects.filter(
                            bk_data_id=data_id,
                            space_id=space_uid,
                            bk_tenant_id=self.bk_tenant_id,
                            space_type_id=space_type_id,
                        ).first()

                        if space_ds:
                            space_datasource_exists = True
                        else:
                            message = f"[SpaceDataSource] [bk_data_id={data_id},space_type_id={space_type_id}] "
                            result["issues"].append(f"{message}缺少SpaceDataSource关联")

                        space = Space.objects.filter(space_id=space_uid, space_type_id=space_type_id).first()
                        if not space:
                            result["issues"].append(
                                f"数据源data_id:{data_id}(space_type:{space_type_id})关联的空间不存在"
                            )
                        elif space.status != SpaceStatus.NORMAL.value:
                            result["issues"].append(
                                f"数据源data_id:{data_id}(space_type:{space_type_id})关联的空间状态异常: {space.status}"
                            )

                    space_check_status[data_id] = {
                        "space_uid": space_uid,
                        "space_type_id": space_type_id,
                        "is_all_space_type": is_all_space_type,
                        "space_datasource_exists": space_datasource_exists if not is_all_space_type else None,
                    }

                except Exception as e:
                    space_check_status[data_id] = {"error": str(e)}
                    message = f"[DataSource] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}空间类型检查异常: {str(e)}")

            result["details"] = space_check_status
            result["status"] = Status.SUCCESS if not result["issues"] else Status.ERROR

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[DataSource] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}空间类型检查异常: {str(e)}")
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
                    message = f"[CustomReportSubscription] [subscription_id={sub.id}] "
                    result["issues"].append(f"{message}订阅检查异常: {str(e)}")

            result["details"] = {
                "bk_biz_id": bk_biz_id,
                "subscription_exists": subscription_count > 0,
                "subscription_count": subscription_count,
                "subscriptions": subscription_details,
            }

            if subscription_count == 0:
                result["status"] = Status.WARNING
                message = f"[CustomReportSubscription] [bk_biz_id={bk_biz_id}] "
                result["issues"].append(f"{message}没有找到自定义上报订阅配置")
            else:
                result["status"] = Status.SUCCESS

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[CustomReportSubscription] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}CustomReportSubscription检查异常: {str(e)}")
            logger.exception(f"检查CustomReportSubscription时发生异常: {e}")

        return result

    @recode_final_result
    def check_related_result_table(self, cluster_info: BCSClusterInfo) -> dict:
        """检查关联的结果表

        验证结果表相关的配置数据是否完整
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化关联模型检查输出"""
            lines = []
            if details:
                ds_rt_count = len(details.get("datasource_result_table", {}))
                rt_options_count = len(details.get("result_table_options", {}))
                filter_alias_count = details.get("space_type_filter_alias", {}).get("total_count", 0)
                lines.append(f"    数据源结果表: {ds_rt_count}")
                lines.append(f"    结果表配置: {rt_options_count}")
                lines.append(f"    空间类型路由别名: {filter_alias_count}")
            return lines

        result["formatter"] = format_output

        try:
            datasource_result_table = {}
            result_table_options = {}
            result_table_fields = {}
            result_table_field_options = {}
            space_type_filter_alias = {}
            all_table_ids = set()

            # 检查 DataSourceResultTable
            for data_id, datasource in self.data_sources.items():
                try:
                    ds_rt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).first()

                    if ds_rt:
                        table_id = ds_rt.table_id
                        all_table_ids.add(table_id)
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
                            message = f"[ResultTableField] [table_id={table_id}] "
                            result["issues"].append(f"{message}缺少时间字段")

                        # 检查ResultTableFieldOption
                        field_options = ResultTableFieldOption.objects.filter(
                            table_id=table_id, bk_tenant_id=self.bk_tenant_id
                        )

                        result_table_field_options[table_id] = {
                            "fields_with_options": field_options.values("field_name").distinct().count(),
                        }

                    else:
                        datasource_result_table[data_id] = {"relation_exists": False}
                        message = f"[DataSourceResultTable] [bk_data_id={data_id}] "
                        result["issues"].append(f"{message}缺少结果表关联")

                except Exception as e:
                    message = f"[DataSourceResultTable] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}关联模型检查异常: {str(e)}")

            # 检查 SpaceTypeToResultTableFilterAlias
            try:
                from metadata.models.space.space import SpaceTypeToResultTableFilterAlias

                filter_alias_list = []
                filter_alias_details = {}

                result_tables = ResultTable.objects.filter(
                    table_id__in=all_table_ids, bk_tenant_id=self.bk_tenant_id
                ).values_list("table_id", "bk_biz_id_alias")

                for table_id, bk_biz_id_alias in result_tables:
                    try:
                        # bk_biz_id_alias 为空，不要检查
                        if not bk_biz_id_alias:
                            continue
                        # 查询该结果表的空间类型过滤别名
                        filter_alias = SpaceTypeToResultTableFilterAlias.objects.filter(
                            table_id=table_id, filter_alias=bk_biz_id_alias, space_type=SpaceTypes.BKCC.value
                        ).first()

                        if filter_alias:
                            filter_alias_list.append(
                                {
                                    "table_id": table_id,
                                    "space_type": filter_alias.space_type,
                                    "filter_alias": filter_alias.filter_alias,
                                    "status": filter_alias.status,
                                }
                            )

                            filter_alias_details[table_id] = {
                                "exists": True,
                                "filter_alias": filter_alias.filter_alias,
                                "status": filter_alias.status,
                            }

                            if not filter_alias.status:
                                message = f"[SpaceTypeToResultTableFilterAlias] [table_id={table_id},filter_alias={filter_alias.filter_alias}] "
                                result["issues"].append(f"{message}空间类型过滤别名未启用")
                        else:
                            filter_alias_details[table_id] = {"exists": False}
                            message = f"[SpaceTypeToResultTableFilterAlias] [table_id={table_id},bk_biz_id_alias={bk_biz_id_alias}] "
                            # 注意：这里应该使用warnings而不是warning
                            if "warnings" not in result:
                                result["warnings"] = []
                            result["warnings"].append(f"{message}空间类型过滤别名不存在")

                    except Exception as e:
                        message = f"[SpaceTypeToResultTableFilterAlias] [table_id={table_id}] "
                        result["issues"].append(f"{message}检查异常: {str(e)}")

                space_type_filter_alias = {
                    "total_count": len(filter_alias_list),
                    "filter_aliases": filter_alias_list,
                    "details": filter_alias_details,
                }

            except Exception as e:
                message = f"[SpaceTypeToResultTableFilterAlias] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

            result["details"] = {
                "datasource_result_table": datasource_result_table,
                "result_table_options": result_table_options,
                "result_table_fields": result_table_fields,
                "result_table_field_options": result_table_field_options,
                "space_type_filter_alias": space_type_filter_alias,
            }

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[ResultTable] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}关联模型检查异常: {str(e)}")

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
                    influx_storages: BaseManager[InfluxDBStorage] = InfluxDBStorage.objects.filter(
                        table_id=ds_rt.table_id, bk_tenant_id=self.bk_tenant_id
                    )

                    for storage in influx_storages:
                        influxdb_storages.append(storage)

                        message = f"[InfluxDBStorage] [id={storage.id},table_id={storage.table_id}] "
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
                                    result["issues"].append(
                                        f"{message}存储代理存储配置influxdb_proxy_storage_id[{storage.influxdb_proxy_storage_id}]不存在"
                                    )
                            except Exception as e:
                                result["issues"].append(
                                    f"{message}存储代理配置influxdb_proxy_storage_id[{storage.influxdb_proxy_storage_id}]检查异常: {str(e)}"
                                )
                        else:
                            result["issues"].append(f"{message}代理存储字段influxdb_proxy_storage_id为空")

                except Exception as e:
                    message = f"[InfluxDBStorage] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}InfluxDB存储检查异常: {str(e)}")

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
                message = f"[InfluxDBClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

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
                message = f"[InfluxDBHostInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

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
            message = f"[InfluxDBStorage] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}InfluxDB存储配置检查异常: {str(e)}")
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
                    message = f"[AccessVMRecord] [bk_data_id={data_id}] "
                    result["issues"].append(f"{message}VM访问记录检查异常: {str(e)}")

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
                message = f"[DataLink] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

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
                message = f"[BcsFederalClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

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
                message = f"[BkBaseResultTable] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}检查异常: {str(e)}")

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
            message = f"[VMDataLink] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}VM数据链路依赖检查异常: {str(e)}")
            logger.exception(f"检查VM数据链路依赖时发生异常: {e}")

        return result

    @recode_final_result
    def check_vm_publish_space_router(self, cluster_info: BCSClusterInfo) -> dict:
        """检查VM推送并发布空间路由功能
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化VM空间路由检查输出"""
            lines = []
            if details:
                router_status = details.get("router_status", {})
                total_checked = len(router_status)
                missing_space = sum(
                    1 for v in router_status.values() if isinstance(v, dict) and not v.get("space_router_exists")
                )
                lines.append(f"    数据源数量: {total_checked}")
                lines.append(f"    空间路由缺失: {missing_space}/{total_checked}")
            return lines

        result["formatter"] = format_output

        try:
            from django.conf import settings
            from metadata.models.space.constants import (
                SPACE_TO_RESULT_TABLE_KEY,
                DATA_LABEL_TO_RESULT_TABLE_KEY,
                RESULT_TABLE_DETAIL_KEY,
            )
            from metadata.utils.redis_tools import RedisTools

            router_status = {}

            for data_id, datasource in self.data_sources.items():
                try:

                    is_v4_datalink_etl_config = datasource.etl_config in ENABLE_V4_DATALINK_ETL_CONFIGS
                    if (
                        is_v4_datalink_etl_config and settings.ENABLE_V2_VM_DATA_LINK) or not settings.ENABLE_INFLUXDB_STORAGE:
                        pass
                    else:
                        continue

                    # 获取空间信息
                    space_info = self._get_space_info_by_biz_id(self.bk_biz_id, datasource)
                    space_type_id = space_info.get("space_type_id", datasource.space_type_id)
                    space_uid = space_info.get("space_uid", datasource.space_uid)

                    # 构建多租户模式下的Redis键
                    if settings.ENABLE_MULTI_TENANT_MODE:
                        space_redis_key = f"{space_type_id}__{space_uid}|{self.bk_tenant_id}"
                    else:
                        space_redis_key = f"{space_type_id}__{space_uid}"

                    # 检查空间路由是否存在
                    space_router_values = RedisTools.hmget(SPACE_TO_RESULT_TABLE_KEY, [space_redis_key])
                    space_router_exists = bool(space_router_values and space_router_values[0])

                    router_status[data_id] = {
                        "space_redis_key": space_redis_key,
                        "space_router_exists": space_router_exists,
                    }

                    # 记录缺失项
                    if not space_router_exists:
                        result["issues"].append(
                            f"数据源data_id:{data_id}缺少空间路由配置, key:{SPACE_TO_RESULT_TABLE_KEY}/{space_redis_key}"
                        )

                except Exception as e:
                    router_status[data_id] = {"error": str(e)}
                    result["issues"].append(f"数据源data_id:{data_id}空间路由检查异常: {str(e)}")
                    logger.exception(f"data_id->[{data_id}] 空间路由检查失败: {e}")

            result["details"] = {"router_status": router_status, "total_datasources": len(self.data_sources)}
            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"VM空间路由检查异常: {str(e)}")
            logger.exception(f"check_vm_publish_space_router failed: {e}")

        return result

    @recode_final_result
    def check_log_datalink(self, cluster_info: BCSClusterInfo) -> dict:
        """检查日志V4数据链路配置

        验证集群日志数据链路配置是否正确，包括：
        1. V4数据链路启用配置
        2. 数据链路配置项完整性
        3. 存储集群(ES/Doris)配置有效性
        4. 数据源和结果表关联正常
        5. 计算平台链路配置正确性
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": []}

        def format_output(details: dict) -> list[str]:
            """格式化日志数据链路检查输出"""
            lines = []
            if details:
                log_datasources = details.get("log_datasources", [])
                v4_enabled_count = sum(1 for ds in log_datasources if ds.get("v4_enabled"))
                lines.append(f"    日志数据源: {len(log_datasources)}个")
                lines.append(f"    V4链路启用: {v4_enabled_count}/{len(log_datasources)}")

                storage_check = details.get("storage_check", {})
                if storage_check:
                    es_ok = sum(1 for v in storage_check.values() if v.get("es_storage_exists"))
                    doris_ok = sum(1 for v in storage_check.values() if v.get("doris_storage_exists"))
                    lines.append(f"    ES存储配置: {es_ok}个")
                    lines.append(f"    Doris存储配置: {doris_ok}个")
            return lines

        result["formatter"] = format_output

        try:
            log_datasources = []
            storage_check = {}
            datalink_check = {}

            # 遍历所有数据源，检查日志相关配置
            for data_id, datasource in self.data_sources.items():
                try:

                    # 获取数据源关联的结果表
                    dsrt = DataSourceResultTable.objects.filter(
                        bk_data_id=data_id, bk_tenant_id=self.bk_tenant_id
                    ).last()

                    if not dsrt:
                        continue

                    table_id = dsrt.table_id

                    # 获取结果表信息
                    rt = ResultTable.objects.filter(
                        bk_tenant_id=self.bk_tenant_id, table_id=table_id
                    ).first()

                    if not rt:
                        result["issues"].append(f"数据源data_id:{data_id}关联的结果表{table_id}不存在")
                        continue

                    if rt.default_storage != ClusterInfo.TYPE_ES:
                        continue

                    # 检查是否启用V4数据链路
                    enabled_v4_option = ResultTableOption.objects.filter(
                        bk_tenant_id=self.bk_tenant_id,
                        table_id=table_id,
                        name=ResultTableOption.OPTION_ENABLE_V4_LOG_DATA_LINK,
                    ).first()

                    v4_enabled = False
                    if enabled_v4_option:
                        try:
                            v4_enabled = enabled_v4_option.to_json().get(
                                ResultTableOption.OPTION_ENABLE_V4_LOG_DATA_LINK, False
                            )
                        except Exception as e:
                            result["issues"].append(
                                f"数据源data_id:{data_id}的V4链路启用配置解析失败: {str(e)}"
                            )

                    log_ds_info = {
                        "data_id": data_id,
                        "table_id": table_id,
                        "v4_enabled": v4_enabled,
                    }

                    # 如果启用了V4链路，进行详细检查
                    if v4_enabled:
                        # 检查V4数据链路配置项
                        datalink_option = ResultTableOption.objects.filter(
                            bk_tenant_id=self.bk_tenant_id,
                            table_id=table_id,
                            name=ResultTableOption.OPTION_V4_LOG_DATA_LINK,
                        ).first()

                        if not datalink_option:
                            result["issues"].append(
                                f"数据源data_id:{data_id}启用了V4链路但缺少数据链路配置项"
                            )
                            log_ds_info["config_exists"] = False
                        else:
                            log_ds_info["config_exists"] = True

                            # 校验配置格式
                            try:
                                datalink_config = LogV4DataLinkOption(**json.loads(datalink_option.value))
                                log_ds_info["config_valid"] = True

                                # 检查存储配置
                                es_storage_exists = False
                                doris_storage_exists = False

                                if datalink_config.es_storage_config:
                                    es_storage = ESStorage.objects.filter(
                                        bk_tenant_id=self.bk_tenant_id, table_id=table_id
                                    ).first()

                                    if es_storage:
                                        es_storage_exists = True
                                        storage_check[f"{data_id}_es"] = {
                                            "table_id": table_id,
                                            "storage_cluster_id": es_storage.storage_cluster_id,
                                            "es_storage_exists": True,
                                        }
                                    else:
                                        result["issues"].append(
                                            f"数据源data_id:{data_id}配置了ES存储但ES存储记录不存在"
                                        )
                                        storage_check[f"{data_id}_es"] = {
                                            "table_id": table_id,
                                            "es_storage_exists": False,
                                            "error": "ES存储记录不存在",
                                        }

                                if datalink_config.doris_storage_config:
                                    doris_storage = DorisStorage.objects.filter(
                                        bk_tenant_id=self.bk_tenant_id, table_id=table_id
                                    ).first()

                                    if doris_storage:
                                        doris_storage_exists = True
                                        storage_check[f"{data_id}_doris"] = {
                                            "table_id": table_id,
                                            "storage_cluster_id": doris_storage.storage_cluster_id,
                                            "doris_storage_exists": True,
                                        }
                                    else:
                                        result["issues"].append(
                                            f"数据源data_id:{data_id}配置了Doris存储但Doris存储记录不存在"
                                        )
                                        storage_check[f"{data_id}_doris"] = {
                                            "table_id": table_id,
                                            "doris_storage_exists": False,
                                            "error": "Doris存储记录不存在",
                                        }

                                log_ds_info["es_storage_configured"] = bool(datalink_config.es_storage_config)
                                log_ds_info["doris_storage_configured"] = bool(
                                    datalink_config.doris_storage_config
                                )
                                log_ds_info["es_storage_exists"] = es_storage_exists
                                log_ds_info["doris_storage_exists"] = doris_storage_exists

                            except (json.JSONDecodeError, TypeError) as e:
                                result["issues"].append(
                                    f"数据源data_id:{data_id}的数据链路配置JSON解析失败: {str(e)}"
                                )
                                log_ds_info["config_valid"] = False
                                log_ds_info["error"] = f"JSON解析失败: {str(e)}"
                            except Exception as e:
                                result["issues"].append(
                                    f"数据源data_id:{data_id}的数据链路配置验证失败: {str(e)}"
                                )
                                log_ds_info["config_valid"] = False
                                log_ds_info["error"] = f"配置验证失败: {str(e)}"

                        # 检查计算平台链路配置
                        bkbase_rt = BkBaseResultTable.objects.filter(
                            bk_tenant_id=self.bk_tenant_id, monitor_table_id=table_id
                        ).first()

                        if bkbase_rt:
                            # 检查DataLink是否存在
                            datalink = DataLink.objects.filter(
                                bk_tenant_id=self.bk_tenant_id,
                                namespace="bklog",
                                data_link_strategy=DataLink.BK_LOG,
                            ).first()

                            if datalink:
                                datalink_check[data_id] = {
                                    "table_id": table_id,
                                    "data_link_name": bkbase_rt.data_link_name,
                                    "datalink_exists": True,
                                    "data_link_strategy": datalink.data_link_strategy,
                                }
                            else:
                                result["issues"].append(
                                    f"数据源data_id:{data_id}的计算平台结果表存在但DataLink不存在"
                                )
                                datalink_check[data_id] = {
                                    "table_id": table_id,
                                    "data_link_name": bkbase_rt.data_link_name,
                                    "datalink_exists": False,
                                }
                        else:
                            # V4链路应该有BkBaseResultTable记录
                            result["issues"].append(
                                f"数据源data_id:{data_id}启用了V4链路但缺少计算平台结果表记录"
                            )
                            datalink_check[data_id] = {
                                "table_id": table_id,
                                "bkbase_rt_exists": False,
                            }

                        # 检查数据源created_from字段
                        if datasource.created_from != DataIdCreatedFromSystem.BKDATA.value:
                            result["issues"].append(
                                f"数据源data_id:{data_id}启用了V4链路但created_from不是BKDATA: {datasource.created_from}"
                            )
                            log_ds_info["created_from_correct"] = False
                        else:
                            log_ds_info["created_from_correct"] = True

                    log_datasources.append(log_ds_info)

                except Exception as e:
                    result["issues"].append(f"数据源data_id:{data_id}日志链路检查异常: {str(e)}")
                    logger.exception(f"检查数据源data_id:{data_id}日志链路时发生异常: {e}")

            result["details"] = {
                "log_datasources": log_datasources,
                "storage_check": storage_check,
                "datalink_check": datalink_check,
            }

            if sum(1 for ds in log_datasources if ds.get("v4_enabled")) == 0:
                result["warnings"].append("没有启用V4链路的日志数据源")

            result["status"] = Status.SUCCESS if not result["issues"] else Status.WARNING

        except Exception as e:
            result["status"] = Status.ERROR
            result["issues"].append(f"日志V4数据链路检查异常: {str(e)}")
            logger.exception(f"检查日志V4数据链路时发生异常: {e}")

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
                message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
                result["issues"].append(f"{message}云区域ID未配置")
                result["status"] = Status.WARNING
            else:
                result["status"] = Status.SUCCESS

            result["details"] = {
                "bk_cloud_id": cluster_info.bk_cloud_id,
                "cloud_id_configured": cluster_info.bk_cloud_id is not None,
            }

        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[BCSClusterInfo] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}云区域ID配置检查异常: {str(e)}")

        return result

    @recode_final_result
    def check_mq_cluster(self, cluster_info: BCSClusterInfo):
        """
        检查mq集群状态
        :param cluster_info: BCS集群信息
        :return: 检查结果
        """
        result = {"status": Status.UNKNOWN, "details": {}, "issues": [], "warnings": []}
        issues = set()

        def format_output(details: dict) -> list[str]:
            """格式化MQ集群检查输出"""
            lines = []
            if details:
                configured_count = len(details)
                lines.append(f"    数据源配置: {configured_count}个")

                error_count = sum(1 for detail in details.values() if detail.get("issues"))
                if error_count > 0:
                    lines.append(f"    异常配置: {error_count}个")

                for data_id, detail in list(details.items()):  # 只显示前3个详情
                    if isinstance(detail, dict):
                        lines.append(f"    数据源data_id`{data_id}`: 集群ID {detail.get('mq_cluster_id', 'N/A')}")
                        if detail.get("mq_cluster_type"):
                            lines.append(f"    集群类型mq_cluster_type: {detail['mq_cluster_type']}")
            return lines

        result["formatter"] = format_output

        try:
            for data_id, data_source in self.data_sources.items():
                mq_cluster_id = data_source.mq_cluster_id
                mq_config_id = data_source.mq_config_id
                details = result["details"].setdefault(data_id, {})

                mq_cluster = ClusterInfo.objects.filter(
                    cluster_id=mq_cluster_id, bk_tenant_id=self.bk_tenant_id
                ).first()
                details.update(
                    {
                        "mq_cluster_id": mq_cluster_id,
                    }
                )

                if not mq_cluster:
                    message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id}] "
                    error_message = f"{message}MQ集群未找到"
                    issues.add(error_message)
                    details.setdefault("issues", []).append(error_message)
                    continue

                details.update(
                    {
                        "mq_cluster_type": mq_cluster.cluster_type,
                    }
                )
                if mq_cluster.cluster_type not in data_source.MQ_CONFIG_DICT:
                    message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id},cluster_type={mq_cluster.cluster_type}] "
                    error_message = f"{message}MQ集群类型未找到"
                    issues.add(error_message)
                    details.setdefault("issues", []).append(error_message)
                    continue

                mq_config = (
                    data_source.MQ_CONFIG_DICT[mq_cluster.cluster_type].objects.filter(bk_data_id=data_id).first()
                )

                details.update(
                    {
                        "mq_config_id": mq_config_id,
                    }
                )
                if not mq_config:
                    message = f"[MQConfig] [mq_config_id={mq_config_id},bk_data_id={data_id}] "
                    error_message = f"{message}MQ配置未找到"
                    issues.add(error_message)
                    details.setdefault("issues", []).append(error_message)
                    continue

                # 如果要刷新consul和gse，mq_cluster必须已经初始化了
                if data_source.can_refresh_consul_and_gse() and mq_cluster.gse_stream_to_id == -1:
                    message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id},bk_data_id={data_id}] "
                    error_message = f"{message}消息队列未初始化，请联系管理员处理"
                    issues.add(error_message)
                    details.setdefault("issues", []).append(error_message)

                try:
                    params = {
                        "condition": {"plat_name": config.DEFAULT_GSE_API_PLAT_NAME, "channel_id": data_id},
                        "operation": {"operator_name": settings.COMMON_USERNAME},
                    }
                    details.update({"gse_route_query_params": params})
                    route_config = api.gse.query_route(**params)
                    if not route_config:
                        message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id},bk_data_id={data_id}] "
                        error_message = f"{message}未查询到GSE路由配置"
                        issues.add(error_message)
                        details.setdefault("issues", []).append(error_message)

                    # 查找匹配的路由配置
                    old_route = None
                    for route_info in route_config:
                        if old_route:
                            break

                        stream_to_info_list = route_info.get("route", [])
                        if not stream_to_info_list:
                            continue

                        for stream_to_info in stream_to_info_list:
                            route_name = stream_to_info.get("name", "")
                            # 如果路由名称匹配，则保存旧的路由配置
                            if route_name != data_source.gse_route_config["name"]:
                                continue

                            old_route = {"name": route_name, "stream_to": stream_to_info["stream_to"]}
                            break

                    # 比较现有配置与新配置的差异
                    old_hash = hash_util.object_md5(old_route)
                    new_hash = hash_util.object_md5(data_source.gse_route_config)
                    # 如果配置一致，则直接返回
                    if old_hash != new_hash:
                        message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id},bk_data_id={data_id}] "
                        error_message = f"{message}GSE路由配置不一致"
                        issues.add(error_message)
                        details.setdefault("issues", []).append(error_message)

                except Exception as e:
                    message = f"[ClusterInfo] [mq_cluster_id={mq_cluster_id},bk_data_id={data_id}] "
                    error_message = f"{message}查询GSE路由失败: {str(e)}"
                    issues.add(error_message)
                    details.setdefault("issues", []).append(error_message)
                    if config.is_built_in_data_id(data_id):
                        warning_msg = f"{message}查询GSE路由失败: {str(e)},{data_id} 是内置数据源"
                        details.setdefault("warnings", []).append(warning_msg)
                        result["warnings"].append(warning_msg)

            if not issues:
                result["status"] = Status.SUCCESS
            else:
                result["status"] = Status.ERROR

            result["issues"] = list(issues)
        except Exception as e:
            result["status"] = Status.ERROR
            message = f"[ClusterInfo] [cluster_id={cluster_info.cluster_id}] "
            result["issues"].append(f"{message}MQ集群检查异常: {str(e)}")

        return result

    def is_federation_cluster(self, cluster_info: BCSClusterInfo) -> bool:
        """判断是否为联邦集群"""
        try:
            return BcsFederalClusterInfo.objects.filter(
                fed_cluster_id=cluster_info.cluster_id, is_deleted=False
            ).exists()
        except Exception:
            return False

    def output_summary_report(self, check_result: dict):
        """输出汇总报告（详细结果已在检查过程中输出）"""
        status = check_result["status"]

        # 输出分隔线
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("检测完成 - 汇总报告"))
        self.stdout.write("=" * 60)

        # 输出基本信息
        self.stdout.write(f"执行时间: {check_result['execution_time']}秒")

        # 输出整体状态
        status_style = self.get_status_style(status)
        self.stdout.write(f"\n整体状态: {status_style(status)}")

        # 输出错误和警告汇总
        if check_result.get("errors"):
            self.stdout.write(f"\n{self.style.ERROR('错误信息:')}（共{len(check_result['errors'])}条）")
            for error in check_result["errors"]:
                self.stdout.write(f"  • {self.style.ERROR(error)}")

        if check_result.get("warnings"):
            self.stdout.write(f"\n{self.style.WARNING('警告信息:')}（共{len(check_result['warnings'])}条）")
            for warning in check_result["warnings"]:
                self.stdout.write(f"  • {self.style.WARNING(warning)}")

        if check_result.get("issues"):
            self.stdout.write(f"\n{self.style.WARNING('问题信息:')}（共{len(check_result['issues'])}条）")
            for issue in check_result["issues"]:
                self.stdout.write(f"  • {self.style.WARNING(issue)}")

        # 输出结束信息
        self.stdout.write("\n" + "=" * 60)
        if status == Status.SUCCESS:
            self.stdout.write(self.style.SUCCESS("✅ 集群状态检测通过！"))
        elif status == Status.WARNING:
            self.stdout.write(self.style.WARNING("⚠️  集群状态检测完成，但存在警告项。"))
        elif status == Status.ERROR:
            self.stdout.write(self.style.ERROR("❌ 集群状态检测发现错误！"))
        elif status == Status.NOT_FOUND:
            self.stdout.write(self.style.ERROR("❌ 集群未找到！"))
        else:
            self.stdout.write(self.style.NOTICE("❓ 集群状态未知。"))
        self.stdout.write("=" * 60)

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
