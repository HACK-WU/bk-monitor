# 策略管理API

<cite>
**本文档引用的文件**
- [strategy_v3.py](file://bkmonitor/kernel_api/views/v4/strategy_v3.py)
- [strategy_v2.py](file://bkmonitor/kernel_api/views/v4/strategy_v2.py)
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py)
- [models.py](file://bkmonitor/bkmonitor/models/strategy.py)
</cite>

## 目录
1. [简介](#简介)
2. [API端点](#api端点)
3. [请求/响应结构](#请求响应结构)
4. [策略配置关键字段](#策略配置关键字段)
5. [Python请求示例](#python请求示例)
6. [API认证](#api认证)
7. [常见错误响应](#常见错误响应)

## 简介
策略管理API提供了创建、查询、修改和删除监控策略的功能。该API支持v2和v3版本，允许用户配置检测算法、触发条件和告警动作等关键监控参数。API设计遵循RESTful原则，使用JSON格式进行数据交换。

## API端点

### 策略搜索
- **HTTP方法**: POST
- **URL路径**: `/api/v4/strategy/search/`
- **功能**: 根据条件搜索监控策略

### 策略保存
- **HTTP方法**: POST
- **URL路径**: `/api/v4/strategy/save/`
- **功能**: 创建或更新监控策略

### 策略删除
- **HTTP方法**: POST
- **URL路径**: `/api/v4/strategy/delete/`
- **功能**: 删除指定的监控策略

### 策略批量更新
- **HTTP方法**: POST
- **URL路径**: `/api/v4/strategy/update_bulk/`
- **功能**: 批量更新多个策略

### 策略开关
- **HTTP方法**: POST
- **URL路径**: `/api/v4/strategy/switch_by_labels/`
- **功能**: 根据标签批量开关策略

**Section sources**
- [strategy_v3.py](file://bkmonitor/kernel_api/views/v4/strategy_v3.py#L90-L104)

## 请求响应结构

### 创建/更新策略请求JSON Schema
```json
{
  "name": "策略名称",
  "bk_biz_id": "业务ID",
  "scenario": "监控场景",
  "is_enabled": "是否启用",
  "items": [
    {
      "name": "监控项名称",
      "metric_id": "指标ID",
      "data_source_label": "数据源标签",
      "data_type_label": "数据类型标签",
      "target": "监控目标",
      "query_configs": [
        {
          "agg_method": "聚合方法",
          "agg_interval": "聚合周期",
          "agg_dimension": "聚合维度",
          "agg_condition": "查询条件"
        }
      ],
      "algorithms": [
        {
          "level": "告警级别",
          "type": "算法类型",
          "config": "算法配置"
        }
      ]
    }
  ],
  "actions": [
    {
      "action_type": "动作类型",
      "config": "动作配置",
      "notice_groups": "通知组"
    }
  ]
}
```

### 查询策略响应JSON Schema
```json
{
  "list": [
    {
      "id": "策略ID",
      "name": "策略名称",
      "bk_biz_id": "业务ID",
      "scenario": "监控场景",
      "is_enabled": "是否启用",
      "items": [
        {
          "id": "监控项ID",
          "name": "监控项名称",
          "metric_id": "指标ID",
          "data_source_label": "数据源标签",
          "data_type_label": "数据类型标签",
          "target": "监控目标",
          "query_configs": [
            {
              "agg_method": "聚合方法",
              "agg_interval": "聚合周期",
              "agg_dimension": "聚合维度",
              "agg_condition": "查询条件"
            }
          ],
          "algorithms": [
            {
              "id": "算法ID",
              "level": "告警级别",
              "type": "算法类型",
              "config": "算法配置"
            }
          ]
        }
      ],
      "actions": [
        {
          "id": "动作ID",
          "action_type": "动作类型",
          "config": "动作配置",
          "notice_groups": "通知组"
        }
      ]
    }
  ],
  "total": "总数"
}
```

**Section sources**
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py#L54-L623)
- [models.py](file://bkmonitor/bkmonitor/models/strategy.py#L81-L800)

## 策略配置关键字段

### 检测算法 (detect)
检测算法定义了如何判断监控指标是否异常。支持多种算法类型：

- **静态阈值算法 (Threshold)**: 基于固定阈值进行判断
- **简易环比算法 (SimpleRingRatio)**: 基于与上一周期的比较
- **高级同比算法 (AdvancedYearRound)**: 基于与历史同期的比较
- **智能异常检测算法 (IntelligentDetect)**: 使用机器学习模型检测异常

每个算法配置包含：
- `level`: 告警级别 (1: 致命, 2: 预警, 3: 提醒)
- `type`: 算法类型
- `config`: 算法具体配置参数

### 触发条件 (trigger)
触发条件定义了告警产生的规则：

- `trigger_config`: 触发条件配置，包含连续周期数等
- `recovery_config`: 恢复条件配置
- `connector`: 同级别算法连接符 (and/or)

### 告警动作 (action)
告警动作定义了当告警触发时的处理方式：

- `action_type`: 动作类型 (如通知、自愈等)
- `config`: 动作执行配置
- `notice_groups`: 通知组列表
- `notice_template`: 通知模板

**Section sources**
- [models.py](file://bkmonitor/bkmonitor/models/strategy.py#L113-L232)
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py#L69-L80)

## Python请求示例

以下是一个使用Python requests库创建基于阈值的CPU监控策略的完整示例：

```python
import requests
import json

# API配置
api_url = "http://your-api-host/api/v4/strategy/save/"
api_token = "your-api-token"

# 策略配置
strategy_config = {
    "name": "CPU使用率监控策略",
    "bk_biz_id": 123,
    "scenario": "host",
    "is_enabled": True,
    "items": [
        {
            "name": "CPU单核使用率",
            "metric_id": "cpu_usage",
            "data_source_label": "bk_monitor",
            "data_type_label": "time_series",
            "target": [
                [
                    {
                        "field": "bk_target_ip",
                        "value": [
                            {
                                "bk_inst_id": 1,
                                "bk_obj_id": "module",
                                "ip": "192.168.1.1",
                                "bk_cloud_id": 0
                            }
                        ],
                        "method": "ip"
                    }
                ]
            ],
            "query_configs": [
                {
                    "agg_method": "AVG",
                    "agg_interval": 60,
                    "agg_dimension": ["ip", "bk_cloud_id"],
                    "agg_condition": [],
                    "result_table_id": "system.cpu_summary",
                    "metric_field": "cpu_usage"
                }
            ],
            "algorithms": [
                {
                    "level": 2,
                    "type": "Threshold",
                    "config": [
                        [
                            {
                                "method": "gte",
                                "threshold": 80
                            }
                        ]
                    ],
                    "trigger_config": {
                        "count": 3,
                        "check_window": 5
                    },
                    "recovery_config": {
                        "check_window": 5
                    }
                }
            ]
        }
    ],
    "actions": [
        {
            "action_type": "notice",
            "config": {
                "alarm_interval": 300,
                "send_recovery_alarm": True
            },
            "notice_groups": [1, 2]
        }
    ]
}

# 发送请求
headers = {
    "Content-Type": "application/json",
    "X-API-TOKEN": api_token
}

response = requests.post(
    api_url,
    data=json.dumps(strategy_config),
    headers=headers
)

# 处理响应
if response.status_code == 200:
    result = response.json()
    print(f"策略创建成功，ID: {result['id']}")
else:
    print(f"策略创建失败: {response.status_code} - {response.text}")
```

**Section sources**
- [strategy_v3.py](file://bkmonitor/kernel_api/views/v4/strategy_v3.py#L97)
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py#L548-L607)

## API认证
策略管理API使用API Token进行认证。客户端需要在HTTP请求头中包含`X-API-TOKEN`字段：

```
X-API-TOKEN: your-api-token-here
```

API Token通常由系统管理员生成并分发给授权用户。每个Token关联到特定的业务和权限范围，确保API调用的安全性。

**Section sources**
- [strategy_v3.py](file://bkmonitor/kernel_api/views/v4/strategy_v3.py#L13)
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py#L21-L33)

## 常见错误响应

### 400 参数错误
当请求参数无效或缺失必要参数时返回：

```json
{
  "code": 400,
  "message": "参数校验失败",
  "errors": {
    "name": ["该字段不能为空"],
    "bk_biz_id": ["该字段必须为整数"]
  }
}
```

### 404 未找到
当请求的资源不存在时返回：

```json
{
  "code": 404,
  "message": "策略不存在",
  "errors": {
    "strategy_id": "指定的策略ID不存在"
  }
}
```

### 403 权限不足
当用户没有权限执行操作时返回：

```json
{
  "code": 403,
  "message": "权限不足",
  "errors": {
    "permission": "您没有权限操作该业务的策略"
  }
}
```

### 500 服务器错误
当服务器内部发生错误时返回：

```json
{
  "code": 500,
  "message": "服务器内部错误",
  "errors": {
    "exception": "数据库连接失败"
  }
}
```

**Section sources**
- [strategy.py](file://bkmonitor/bkmonitor/strategy/strategy.py#L43-L48)
- [models.py](file://bkmonitor/bkmonitor/models/strategy.py#L335-L403)