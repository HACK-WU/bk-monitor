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

import json
import logging
import time
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from kubernetes import client as k8s_client

from core.drf_resource import api
from metadata.models.bcs.cluster import BCSClusterInfo
from metadata.models.data_source import DataSource
from metadata.models.result_table import DataSourceResultTable
from metadata.models.bcs.resource import ServiceMonitorInfo, PodMonitorInfo
from metadata import config

logger = logging.getLogger("metadata")


class Command(BaseCommand):
    """
    BCS集群关联状态检测命令
    
    检测指定集群ID在整个监控关联链路中的运行状态，包括：
    1. 数据库记录状态检查
    2. BCS API连接性测试
    3. Kubernetes集群连接测试
    4. 数据源配置验证
    5. 监控资源状态检查
    
    使用示例:
    python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001
    python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001 --format json
    """

    help = "检测BCS集群在监控关联链路中的运行状态"

    def add_arguments(self, parser):
        """添加命令行参数配置"""
        parser.add_argument(
            "--cluster-id",
            type=str,
            required=True,
            help="BCS集群ID，例如: BCS-K8S-00001"
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="输出格式，支持text和json"
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=30,
            help="连接测试超时时间（秒），默认30秒"
        )

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
                self.stdout.write(json.dumps(check_result, indent=2, ensure_ascii=False))
            else:
                self.output_text_report(check_result)
                
        except Exception as e:
            logger.exception(f"检测集群状态时发生异常: {e}")
            raise CommandError(f"集群状态检测失败: {e}")

    def check_cluster_status(self, cluster_id: str, timeout: int = 30) -> Dict:
        """执行完整的集群状态检测"""
        start_time = time.time()
        
        check_result = {
            "cluster_id": cluster_id,
            "check_time": timezone.now().isoformat(),
            "status": "UNKNOWN",
            "details": {},
            "errors": [],
            "warnings": [],
            "execution_time": 0
        }

        try:
            # 1. 数据库记录检查
            self.stdout.write(f"正在检查集群 {cluster_id} 的数据库记录...")
            db_check = self.check_database_record(cluster_id)
            check_result["details"]["database"] = db_check
            
            if not db_check["exists"]:
                check_result["status"] = "NOT_FOUND"
                check_result["errors"].append("集群在数据库中不存在")
                return check_result

            cluster_info = db_check["cluster_info"]
            
            # 2. BCS API连接测试
            self.stdout.write("正在测试BCS API连接...")
            bcs_api_check = self.check_bcs_api_connection(cluster_info, timeout)
            check_result["details"]["bcs_api"] = bcs_api_check
            
            # 3. Kubernetes集群连接测试
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
            
            # 确定整体状态
            check_result["status"] = self.determine_overall_status(check_result["details"])
            
        except Exception as e:
            check_result["status"] = "ERROR"
            check_result["errors"].append(f"检测过程中发生异常: {str(e)}")
            logger.exception(f"集群状态检测异常: {e}")
        
        finally:
            check_result["execution_time"] = round(time.time() - start_time, 2)
        
        return check_result

    def check_database_record(self, cluster_id: str) -> Dict:
        """检查集群在数据库中的记录状态"""
        result = {
            "exists": False,
            "cluster_info": None,
            "status": "UNKNOWN",
            "details": {},
            "issues": []
        }
        
        try:
            cluster_info = BCSClusterInfo.objects.get(cluster_id=cluster_id)
            result["exists"] = True
            result["cluster_info"] = cluster_info
            result["status"] = "SUCCESS"
            
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
                }
            }
            
            # 检查集群状态
            if cluster_info.status not in [BCSClusterInfo.CLUSTER_STATUS_RUNNING, BCSClusterInfo.CLUSTER_RAW_STATUS_RUNNING]:
                result["issues"].append(f"集群状态异常: {cluster_info.status}")
            
            # 检查数据源ID配置
            missing_data_ids = []
            for data_type, data_id in result["details"]["data_ids"].items():
                if data_id == 0:
                    missing_data_ids.append(data_type)
            
            if missing_data_ids:
                result["issues"].append(f"缺少数据源ID配置: {', '.join(missing_data_ids)}")
                
        except BCSClusterInfo.DoesNotExist:
            result["status"] = "NOT_FOUND"
            result["issues"].append("集群记录在数据库中不存在")
        except Exception as e:
            result["status"] = "ERROR"
            result["issues"].append(f"数据库查询异常: {str(e)}")
            
        return result

    def check_bcs_api_connection(self, cluster_info: BCSClusterInfo, timeout: int) -> Dict:
        """检查BCS API连接状态"""
        result = {
            "status": "UNKNOWN",
            "details": {},
            "issues": []
        }
        
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
                result["status"] = "SUCCESS"
                result["details"] = {
                    "api_accessible": True,
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
                result["status"] = "WARNING"
                result["details"] = {
                    "api_accessible": True,
                    "cluster_found": False
                }
                result["issues"].append("集群在BCS API中未找到，可能已被删除")
                
        except Exception as e:
            result["status"] = "ERROR"
            result["details"] = {
                "api_accessible": False,
                "error": str(e)
            }
            result["issues"].append(f"BCS API连接失败: {str(e)}")
            
        return result

    def check_kubernetes_connection(self, cluster_info: BCSClusterInfo, timeout: int) -> Dict:
        """检查Kubernetes集群连接状态"""
        result = {
            "status": "UNKNOWN",
            "details": {},
            "issues": []
        }
        
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
            
            result["status"] = "SUCCESS"
            
            # 检查节点健康状态
            if ready_nodes < node_count:
                result["issues"].append(f"有{node_count - ready_nodes}个节点未就绪")
                
        except k8s_client.ApiException as e:
            result["status"] = "ERROR"
            result["details"]["api_error"] = {
                "status": e.status,
                "reason": e.reason
            }
            result["issues"].append(f"Kubernetes API调用失败: {e.status} {e.reason}")
            
        except Exception as e:
            result["status"] = "ERROR"
            result["details"]["error"] = str(e)
            result["issues"].append(f"Kubernetes连接异常: {str(e)}")
            
        return result

    def check_datasource_configuration(self, cluster_info: BCSClusterInfo) -> Dict:
        """检查数据源配置状态"""
        result = {
            "status": "UNKNOWN",
            "details": {},
            "issues": []
        }
        
        try:
            data_ids = [
                cluster_info.K8sMetricDataID,
                cluster_info.CustomMetricDataID,
                cluster_info.K8sEventDataID,
            ]
            
            # 过滤掉为0的data_id
            valid_data_ids = [data_id for data_id in data_ids if data_id != 0]
            
            datasource_status = {}
            
            for data_id in valid_data_ids:
                try:
                    # 检查数据源记录
                    datasource = DataSource.objects.get(bk_data_id=data_id)
                    datasource_status[data_id] = {
                        "exists": True,
                        "data_name": datasource.data_name,
                        "is_enable": datasource.is_enable,
                        "type_label": datasource.type_label
                    }
                    
                    # 检查数据源是否启用
                    if not datasource.is_enable:
                        result["issues"].append(f"数据源{data_id}未启用")
                        
                except DataSource.DoesNotExist:
                    datasource_status[data_id] = {
                        "exists": False
                    }
                    result["issues"].append(f"数据源{data_id}不存在")
            
            result["details"] = {
                "configured_data_ids": valid_data_ids,
                "datasource_status": datasource_status,
            }
            
            # 确定整体状态
            if not result["issues"]:
                result["status"] = "SUCCESS"
            elif any("不存在" in issue for issue in result["issues"]):
                result["status"] = "ERROR"
            else:
                result["status"] = "WARNING"
                
        except Exception as e:
            result["status"] = "ERROR"
            result["issues"].append(f"数据源配置检查异常: {str(e)}")
            
        return result

    def check_monitor_resources(self, cluster_info: BCSClusterInfo) -> Dict:
        """检查监控资源状态"""
        result = {
            "status": "UNKNOWN",
            "details": {},
            "issues": []
        }
        
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
            
            result["status"] = "SUCCESS"
            
        except Exception as e:
            result["status"] = "ERROR"
            result["issues"].append(f"监控资源检查异常: {str(e)}")
            
        return result

    def determine_overall_status(self, details: Dict) -> str:
        """确定整体状态"""
        statuses = [
            details.get("database", {}).get("status", "UNKNOWN"),
            details.get("bcs_api", {}).get("status", "UNKNOWN"),
            details.get("kubernetes", {}).get("status", "UNKNOWN"),
            details.get("datasources", {}).get("status", "UNKNOWN"),
            details.get("monitor_resources", {}).get("status", "UNKNOWN"),
        ]
        
        # 如果有任何ERROR状态，整体状态为ERROR
        if "ERROR" in statuses:
            return "ERROR"
        
        # 如果有任何WARNING状态，整体状态为WARNING
        if "WARNING" in statuses:
            return "WARNING"
        
        # 如果有任何NOT_FOUND状态，整体状态为NOT_FOUND
        if "NOT_FOUND" in statuses:
            return "NOT_FOUND"
        
        # 如果所有状态都是SUCCESS，整体状态为SUCCESS
        if all(status == "SUCCESS" for status in statuses):
            return "SUCCESS"
        
        # 其他情况为UNKNOWN
        return "UNKNOWN"

    def output_text_report(self, check_result: Dict):
        """输出文本格式的检测报告"""
        cluster_id = check_result["cluster_id"]
        status = check_result["status"]
        
        # 输出标题
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"BCS集群关联状态检测报告"))
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

    def output_detailed_results(self, details: Dict):
        """输出详细检测结果"""
        for component, result in details.items():
            if not isinstance(result, dict):
                continue
                
            status = result.get("status", "UNKNOWN")
            style = self.get_status_style(status)
            
            self.stdout.write(f"\n  {component.upper()}: {style(status)}")
            
            # 输出问题信息
            if result.get("issues"):
                for issue in result["issues"]:
                    self.stdout.write(f"    ⚠ {issue}")
            
            # 输出关键信息
            if component == "database" and result.get("details"):
                db_details = result["details"]
                self.stdout.write(f"    业务ID: {db_details.get('bk_biz_id')}")
                self.stdout.write(f"    集群状态: {db_details.get('status')}")
                
            elif component == "kubernetes" and result.get("details", {}).get("nodes"):
                nodes = result["details"]["nodes"]
                self.stdout.write(f"    节点统计: {nodes['ready']}/{nodes['total']} 就绪")
                
            elif component == "monitor_resources" and result.get("details"):
                monitor_details = result["details"]
                self.stdout.write(f"    ServiceMonitor: {monitor_details.get('service_monitors', {}).get('count', 0)}个")
                self.stdout.write(f"    PodMonitor: {monitor_details.get('pod_monitors', {}).get('count', 0)}个")

    def get_status_style(self, status: str):
        """根据状态获取样式函数"""
        status_styles = {
            "SUCCESS": self.style.SUCCESS,
            "WARNING": self.style.WARNING,
            "ERROR": self.style.ERROR,
            "NOT_FOUND": self.style.ERROR,
            "UNKNOWN": self.style.NOTICE,
        }
        return status_styles.get(status, self.style.NOTICE)