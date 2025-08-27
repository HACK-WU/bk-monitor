# BCS集群关联状态检测命令使用指南

## 命令概述

`check_bcs_cluster_status` 是一个Django管理命令，用于检测指定BCS集群ID在整个监控关联链路中的运行状态。该命令可以全面诊断集群从注册到数据采集的各个环节是否正常。

## 检测项目

该命令会检测以下关键环节：

### 1. 数据库记录状态检查
- 集群记录是否存在
- 集群基本信息完整性
- 数据源ID配置情况
- 集群状态信息

### 2. BCS API连接性测试
- BCS API网络连通性
- 认证信息有效性
- 集群信息获取
- 状态一致性校验

### 3. Kubernetes集群连接测试
- K8s API服务器连通性
- 认证信息有效性
- 节点状态检查
- 命名空间统计

### 4. 数据源配置验证
- 数据源记录完整性
- 结果表配置状态
- 数据源启用状态

### 5. 监控资源状态检查
- ServiceMonitor资源状态
- PodMonitor资源状态
- DataID资源配置状态

## 命令语法

```bash
python manage.py check_bcs_cluster_status --cluster-id <CLUSTER_ID> [OPTIONS]
```

## 参数说明

### 必需参数

- `--cluster-id`: BCS集群ID，必须提供
  - 示例：`BCS-K8S-00001`

### 可选参数

- `--format`: 输出格式
  - 可选值：`text`（默认）、`json`
  - 示例：`--format json`

- `--timeout`: 连接测试超时时间（秒）
  - 默认值：30秒
  - 示例：`--timeout 60`

## 使用示例

### 1. 基本用法 - 文本格式输出

```bash
python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001
```

输出示例：
```
============================================================
BCS集群关联状态检测报告
============================================================
集群ID: BCS-K8S-00001
检测时间: 2024-01-01T12:00:00+08:00
执行时间: 5.23秒
整体状态: SUCCESS

详细检测结果:

  DATABASE: SUCCESS
    业务ID: 1001
    集群状态: running

  BCS_API: SUCCESS

  KUBERNETES: SUCCESS
    节点统计: 3/3 就绪

  DATASOURCES: SUCCESS

  MONITOR_RESOURCES: SUCCESS
    ServiceMonitor: 5个
    PodMonitor: 3个
```

### 2. JSON格式输出

```bash
python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001 --format json
```

输出示例：
```json
{
  "cluster_id": "BCS-K8S-00001",
  "check_time": "2024-01-01T12:00:00+08:00",
  "status": "SUCCESS",
  "details": {
    "database": {
      "exists": true,
      "status": "SUCCESS",
      "details": {
        "bk_biz_id": 1001,
        "project_id": "project001",
        "status": "running",
        "bk_tenant_id": "default",
        "domain_name": "bcs-api.example.com",
        "port": 443,
        "data_ids": {
          "K8sMetricDataID": 50001,
          "CustomMetricDataID": 50002,
          "K8sEventDataID": 50003
        }
      },
      "issues": []
    },
    "bcs_api": {
      "status": "SUCCESS",
      "details": {
        "api_accessible": true,
        "cluster_found": true,
        "cluster_status": "running",
        "bk_biz_id": 1001
      },
      "issues": []
    },
    "kubernetes": {
      "status": "SUCCESS",
      "details": {
        "nodes": {
          "total": 3,
          "ready": 3
        },
        "namespaces_count": 12
      },
      "issues": []
    },
    "datasources": {
      "status": "SUCCESS",
      "details": {
        "configured_data_ids": [50001, 50002, 50003],
        "datasource_status": {
          "50001": {
            "exists": true,
            "data_name": "bcs_BCS-K8S-00001_k8s_metric",
            "is_enable": true,
            "type_label": "time_series"
          }
        }
      },
      "issues": []
    },
    "monitor_resources": {
      "status": "SUCCESS",
      "details": {
        "service_monitors": {
          "count": 5
        },
        "pod_monitors": {
          "count": 3
        }
      },
      "issues": []
    }
  },
  "errors": [],
  "warnings": [],
  "execution_time": 5.23
}
```

### 3. 自定义超时时间

```bash
python manage.py check_bcs_cluster_status --cluster-id BCS-K8S-00001 --timeout 60
```

## 状态说明

### 整体状态值

- `SUCCESS`: 所有检测项目都正常
- `WARNING`: 存在警告但不影响基本功能
- `ERROR`: 存在错误需要处理
- `NOT_FOUND`: 集群未找到
- `UNKNOWN`: 状态未知或检测异常

### 各检测项状态

每个检测项都会返回以下状态之一：
- `SUCCESS`: 检测通过
- `WARNING`: 存在警告
- `ERROR`: 检测失败
- `NOT_FOUND`: 资源未找到
- `UNKNOWN`: 状态未知

## 常见问题诊断

### 1. 集群未找到

```
整体状态: NOT_FOUND
错误信息:
  • 集群在数据库中不存在
```

**解决方案**：
- 检查集群ID是否正确
- 确认集群是否已正确注册到监控系统
- 运行集群发现任务：`python manage.py discover_bcs_clusters`

### 2. BCS API连接失败

```
  BCS_API: ERROR
    ⚠ BCS API连接失败: HTTPSConnectionPool(host='bcs-api.example.com', port=443)
```

**解决方案**：
- 检查网络连通性
- 验证BCS API Gateway配置
- 检查认证Token是否正确

### 3. Kubernetes连接异常

```
  KUBERNETES: ERROR
    ⚠ Kubernetes API调用失败: 403 Forbidden
```

**解决方案**：
- 检查集群API Key是否有效
- 验证集群域名和端口配置
- 确认集群状态是否正常

### 4. 数据源配置异常

```
  DATASOURCES: ERROR
    ⚠ 数据源50001不存在
    ⚠ 数据源50002未启用
```

**解决方案**：
- 重新初始化集群监控资源
- 检查数据源配置完整性
- 手动创建缺失的数据源

### 5. 监控资源异常

```
  MONITOR_RESOURCES: WARNING
    ⚠ 监控资源检查异常: Failed to list custom objects
```

**解决方案**：
- 检查集群CRD是否正确安装
- 验证bkmonitor-operator部署状态
- 重新部署监控资源

## 故障排除流程

1. **确认集群ID正确性**
   ```bash
   # 列出所有已注册集群
   python manage.py shell -c "
   from metadata.models.bcs.cluster import BCSClusterInfo
   for cluster in BCSClusterInfo.objects.all():
       print(f'{cluster.cluster_id} - {cluster.status} - 业务ID:{cluster.bk_biz_id}')
   "
   ```

2. **检查集群发现状态**
   ```bash
   # 手动执行集群发现
   python manage.py shell -c "
   from metadata.task.bcs import discover_bcs_clusters
   discover_bcs_clusters()
   "
   ```

3. **重新初始化集群资源**
   ```bash
   # 在Django shell中执行
   python manage.py shell -c "
   from metadata.models.bcs.cluster import BCSClusterInfo
   cluster = BCSClusterInfo.objects.get(cluster_id='BCS-K8S-00001')
   cluster.init_resource()
   "
   ```

4. **刷新监控资源**
   ```bash
   # 刷新BCS监控信息
   python manage.py shell -c "
   from metadata.task.bcs import refresh_bcs_monitor_info
   refresh_bcs_monitor_info()
   "
   ```

## 最佳实践

1. **定期检测**：建议定期运行该命令检测集群健康状态
2. **JSON输出**：在自动化脚本中使用JSON格式便于解析
3. **日志记录**：检测结果可以记录到监控日志中
4. **告警集成**：可以将检测结果集成到告警系统中

## 集成示例

### Shell脚本集成

```bash
#!/bin/bash
# 检测多个集群状态

CLUSTERS=("BCS-K8S-00001" "BCS-K8S-00002" "BCS-K8S-00003")
FAILED_CLUSTERS=()

for cluster in "${CLUSTERS[@]}"; do
    echo "检测集群: $cluster"
    result=$(python manage.py check_bcs_cluster_status --cluster-id "$cluster" --format json)
    status=$(echo "$result" | jq -r '.status')
    
    if [ "$status" != "SUCCESS" ]; then
        FAILED_CLUSTERS+=("$cluster")
        echo "集群 $cluster 状态异常: $status"
    else
        echo "集群 $cluster 状态正常"
    fi
done

if [ ${#FAILED_CLUSTERS[@]} -gt 0 ]; then
    echo "发现异常集群: ${FAILED_CLUSTERS[*]}"
    exit 1
fi
```

### Python脚本集成

```python
import subprocess
import json

def check_cluster_status(cluster_id):
    """检测集群状态"""
    try:
        result = subprocess.run([
            'python', 'manage.py', 'check_bcs_cluster_status',
            '--cluster-id', cluster_id,
            '--format', 'json'
        ], capture_output=True, text=True, check=True)
        
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        return {"status": "ERROR", "error": str(e)}

# 检测多个集群
clusters = ["BCS-K8S-00001", "BCS-K8S-00002"]
for cluster_id in clusters:
    status = check_cluster_status(cluster_id)
    print(f"集群 {cluster_id}: {status['status']}")
```

通过以上文档，用户可以全面了解如何使用BCS集群关联状态检测命令，以及如何根据检测结果进行问题诊断和解决。