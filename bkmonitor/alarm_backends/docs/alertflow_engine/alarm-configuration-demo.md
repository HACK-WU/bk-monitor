## 用户层配置 Demo

### 1. CPU 使用率监控策略

```json
{
  "strategy": {
    "id": "strategy_cpu_001",
    "name": "业务服务器CPU使用率监控",
    "description": "监控核心业务服务器的CPU使用情况，超过阈值时触发告警",
    "enabled": true,
    
    "biz_id": 100,
    "scenario": "infrastructure",
    "tags": {
      "team": "ops",
      "category": "resource",
      "priority": "high"
    },
    
    "data_source": {
      "type": "metric",
      "metric_id": "system.cpu.usage",
      "aggregation_method": "avg",
      "aggregation_interval": 60,
      "query_conditions": {
        "bk_biz_id": 100,
        "tags.environment": "production"
      }
    },
    
    "detect_rule": {
      "algorithm": "threshold",
      "thresholds": [
        {
          "level": 3,
          "level_name": "警告",
          "operator": ">=",
          "value": 80,
          "consecutive_count": 3,
          "description": "CPU使用率超过80%，持续3分钟"
        },
        {
          "level": 2,
          "level_name": "错误",
          "operator": ">=",
          "value": 90,
          "consecutive_count": 2,
          "description": "CPU使用率超过90%，持续2分钟"
        },
        {
          "level": 1,
          "level_name": "致命",
          "operator": ">=",
          "value": 95,
          "consecutive_count": 1,
          "description": "CPU使用率超过95%，立即告警"
        }
      ]
    },
    
    "notification": {
      "enabled": true,
      "channels": [
        {
          "type": "weixin",
          "enabled": true,
          "title_template": "[{{level}}] {{strategy_name}} - {{target}}",
          "content_template": "**告警详情**\n> 目标：{{target}}\n> 当前值：{{value}}%\n> 主机：{{host_name}}\n> 时间：{{time}}\n> 值班人：{{operator}}\n\n[查看详情]({{alert_url}})"
        },
        {
          "type": "sms",
          "enabled": true,
          "work_hours_only": false,
          "content_template": "[{{level}}]{{strategy_name}}，目标{{target}}，当前值{{value}}%，请立即处理！"
        },
        {
          "type": "voice",
          "enabled": true,
          "levels": [1, 2],
          "content_template": "紧急告警，{{strategy_name}}，目标{{target}}，当前值{{value}}%，请立即处理"
        }
      ],
      "receivers": {
        "type": "duty",
        "duty_group": "oncall_ops",
        "fallback": ["admin", "backup_admin"]
      },
      "mute_window": {
        "enabled": true,
        "periods": [
          {
            "name": "深夜免打扰",
            "start_time": "23:00",
            "end_time": "08:00",
            "weekdays": [1, 2, 3, 4, 5],
            "channels_excluded": ["voice"],
            "levels_excluded": [3]
          }
        ]
      }
    },
    
    "shield": {
      "enabled": true,
      "rules": [
        {
          "name": "每周维护窗口",
          "description": "每周二凌晨系统维护期间屏蔽告警",
          "enabled": true,
          "type": "maintenance",
          "scope": {
            "type": "biz",
            "ids": [100]
          },
          "time_range": {
            "type": "periodic",
            "weekdays": [2],
            "start_time": "02:00",
            "stop_time": "06:00"
          }
        },
        {
          "name": "测试环境屏蔽",
          "description": "屏蔽测试环境的告警",
          "enabled": true,
          "type": "temporary",
          "conditions": [
            {
              "field": "tags.environment",
              "operator": "in",
              "value": ["test", "staging"]
            }
          ]
        }
      ]
    },
    
    "converge": {
      "enabled": true,
      "window": 300,
      "dimensions": ["ip", "strategy_id"],
      "description": "相同IP的CPU告警5分钟内只通知一次"
    },
    
    "recovery": {
      "enabled": true,
      "type": "threshold",
      "operator": "<",
      "value": 75,
      "consecutive_count": 3,
      "send_notification": true
    },
    
    "advanced": {
      "consecutive_check": true,
      "data_gap_tolerance": 120,
      "max_alert_per_hour": 100
    }
  }
}
```

### 2. 磁盘空间监控策略

```json
{
  "strategy": {
    "id": "strategy_disk_001",
    "name": "磁盘空间不足告警",
    "description": "监控服务器磁盘使用率，防止磁盘写满导致服务异常",
    "enabled": true,
    
    "biz_id": 100,
    "tags": {
      "team": "ops",
      "category": "storage"
    },
    
    "data_source": {
      "type": "metric",
      "metric_id": "system.disk.usage",
      "aggregation_method": "max",
      "aggregation_interval": 300,
      "query_conditions": {
        "mount_point": ["/", "/data", "/var/log"]
      }
    },
    
    "detect_rule": {
      "algorithm": "threshold",
      "thresholds": [
        {
          "level": 3,
          "level_name": "警告",
          "operator": ">=",
          "value": 80,
          "consecutive_count": 1
        },
        {
          "level": 2,
          "level_name": "错误",
          "operator": ">=",
          "value": 90,
          "consecutive_count": 1
        }
      ]
    },
    
    "notification": {
      "enabled": true,
      "channels": [
        {
          "type": "weixin",
          "enabled": true
        },
        {
          "type": "mail",
          "enabled": true,
          "to": ["ops-team@company.com"]
        }
      ],
      "receivers": {
        "type": "role",
        "role": "ops_engineer"
      },
      "aggregate": {
        "enabled": true,
        "window": 600,
        "max_count": 20,
        "template": "磁盘告警汇总（{{count}}条）：\n{{#alerts}}\n- {{target}}: {{value}}%\n{{/alerts}}"
      }
    },
    
    "shield": {
      "rules": [
        {
          "name": "临时扩容期间",
          "enabled": false,
          "type": "temporary",
          "time_range": {
            "type": "once",
            "begin_time": "2024-01-20T00:00:00",
            "end_time": "2024-01-20T06:00:00"
          }
        }
      ]
    },
    
    "auto_action": {
      "enabled": true,
      "triggers": [
        {
          "name": "自动清理日志",
          "condition": {
            "level": 2,
            "mount_point": "/var/log"
          },
          "action": {
            "type": "script",
            "script_id": "clean_old_logs",
            "params": {
              "days": 7,
              "path": "/var/log"
            }
          },
          "confirm_required": false
        }
      ]
    }
  }
}
```

### 3. HTTP 接口可用性监控

```json
{
  "strategy": {
    "id": "strategy_http_001",
    "name": "核心API接口可用性监控",
    "description": "监控订单服务API的可用性和响应时间",
    "enabled": true,
    
    "biz_id": 100,
    "tags": {
      "team": "sre",
      "category": "application",
      "service": "order-api"
    },
    
    "data_source": {
      "type": "uptime",
      "check_type": "http",
      "url": "https://api.company.com/v1/orders/health",
      "method": "GET",
      "headers": {
        "Authorization": "Bearer ${API_TOKEN}",
        "X-Check-Id": "monitoring"
      },
      "interval": 30,
      "timeout": 10,
      "retry": 2
    },
    
    "detect_rule": {
      "algorithm": "threshold",
      "conditions": [
        {
          "name": "接口不可用",
          "type": "status_code",
          "operator": "!=",
          "value": 200,
          "level": 1,
          "consecutive_count": 2
        },
        {
          "name": "响应时间过长",
          "type": "response_time",
          "operator": ">",
          "value": 1000,
          "level": 2,
          "consecutive_count": 3,
          "unit": "ms"
        },
        {
          "name": "响应内容异常",
          "type": "content_match",
          "operator": "not_contains",
          "value": "\"status\":\"ok\"",
          "level": 2,
          "consecutive_count": 2
        }
      ]
    },
    
    "notification": {
      "enabled": true,
      "channels": [
        {
          "type": "weixin",
          "enabled": true
        },
        {
          "type": "slack",
          "enabled": true,
          "webhook": "https://hooks.slack.com/services/xxx",
          "channel": "#sre-alerts"
        },
        {
          "type": "pagerduty",
          "enabled": true,
          "levels": [1],
          "service_key": "${PAGERDUTY_KEY}"
        }
      ],
      "receivers": {
        "type": "duty",
        "duty_group": "sre_oncall"
      },
      "escalation": {
        "enabled": true,
        "rules": [
          {
            "timeout": 900,
            "escalate_to_level": 1,
            "add_receivers": ["sre_manager"]
          },
          {
            "timeout": 1800,
            "escalate_to_level": 1,
            "add_channels": ["voice"]
          }
        ]
      }
    },
    
    "converge": {
      "enabled": true,
      "window": 180,
      "dimensions": ["url", "status_code"],
      "description": "相同URL和状态码的告警3分钟内只通知一次"
    }
  }
}
```

### 4. 日志关键字监控

```json
{
  "strategy": {
    "id": "strategy_log_001",
    "name": "错误日志关键字监控",
    "description": "监控应用日志中的错误关键字，及时发现异常",
    "enabled": true,
    
    "biz_id": 100,
    "tags": {
      "team": "dev",
      "category": "log"
    },
    
    "data_source": {
      "type": "log",
      "data_id": "10001",
      "query": {
        "keyword": ["ERROR", "Exception", "Failed"],
        "exclude_keyword": ["test", "debug"],
        "path": "/data/logs/app/*.log",
        "time_range": "1m"
      },
      "aggregation": {
        "method": "count",
        "window": 60
      }
    },
    
    "detect_rule": {
      "algorithm": "threshold",
      "thresholds": [
        {
          "level": 3,
          "operator": ">=",
          "value": 10,
          "consecutive_count": 2,
          "description": "1分钟内错误日志超过10条"
        },
        {
          "level": 2,
          "operator": ">=",
          "value": 50,
          "consecutive_count": 1,
          "description": "1分钟内错误日志超过50条"
        }
      ]
    },
    
    "notification": {
      "enabled": true,
      "channels": [
        {
          "type": "weixin",
          "enabled": true,
          "content_template": "错误日志告警\n时间：{{time}}\n主机：{{host}}\n错误数：{{value}}\n示例：{{sample_log}}"
        }
      ],
      "receivers": {
        "type": "role",
        "role": "developer"
      }
    },
    
    "advanced": {
      "sample_log_collection": true,
      "max_sample_count": 5,
      "group_by": ["error_type", "host"]
    }
  }
}
```

### 5. 智能异常检测策略

```json
{
  "strategy": {
    "id": "strategy_ai_001",
    "name": "订单量异常检测",
    "description": "基于AI算法检测订单量的异常波动",
    "enabled": true,
    
    "biz_id": 100,
    "tags": {
      "team": "data",
      "category": "business"
    },
    
    "data_source": {
      "type": "metric",
      "metric_id": "business.order.count",
      "aggregation_method": "sum",
      "aggregation_interval": 300
    },
    
    "detect_rule": {
      "algorithm": "anomaly",
      "algorithm_config": {
        "type": "3sigma",
        "sensitivity": 0.7,
        "training_window": "7d",
        "min_samples": 1000
      },
      "detect_types": ["spike", "drop"],
      "thresholds": [
        {
          "level": 2,
          "condition": "anomaly_score > 0.8",
          "description": "订单量突增或突降超过正常范围"
        }
      ]
    },
    
    "notification": {
      "enabled": true,
      "channels": [
        {
          "type": "weixin",
          "enabled": true
        }
      ],
      "receivers": {
        "type": "group",
        "group": "business_ops"
      }
    },
    
    "advanced": {
      "seasonality": {
        "enabled": true,
        "patterns": ["weekly", "daily"]
      },
      "holiday_adjust": true
    }
  }
}
```

---

## 配置字段说明

### 基础信息

| 字段          | 类型    | 必填 | 说明                 |
| ------------- | ------- | ---- | -------------------- |
| `id`          | string  | 是   | 策略唯一标识         |
| `name`        | string  | 是   | 策略名称（展示用）   |
| `description` | string  | 否   | 策略描述             |
| `enabled`     | boolean | 否   | 是否启用，默认true   |
| `biz_id`      | int     | 是   | 业务ID               |
| `tags`        | object  | 否   | 标签，用于分类和筛选 |

### 数据源 (`data_source`)

| 字段                   | 类型   | 说明                                |
| ---------------------- | ------ | ----------------------------------- |
| `type`                 | enum   | 数据源类型：metric/uptime/log/event |
| `metric_id`            | string | 指标ID（type=metric时）             |
| `aggregation_method`   | string | 聚合方法：avg/max/min/sum/count     |
| `aggregation_interval` | int    | 聚合周期（秒）                      |

### 检测规则 (`detect_rule`)

| 字段                             | 类型   | 说明                                       |
| -------------------------------- | ------ | ------------------------------------------ |
| `algorithm`                      | enum   | 检测算法：threshold/anomaly/baseline/trend |
| `thresholds`                     | array  | 阈值规则列表                               |
| `thresholds[].level`             | int    | 告警级别：1-致命 2-错误 3-警告 4-提醒      |
| `thresholds[].operator`          | string | 比较操作符：> >= < <= == !=                |
| `thresholds[].value`             | float  | 阈值                                       |
| `thresholds[].consecutive_count` | int    | 连续触发次数                               |

### 通知配置 (`notification`)

| 字段              | 类型    | 说明                                            |
| ----------------- | ------- | ----------------------------------------------- |
| `enabled`         | boolean | 是否启用通知                                    |
| `channels`        | array   | 通知渠道配置                                    |
| `channels[].type` | enum    | 渠道类型：weixin/sms/voice/mail/slack/pagerduty |
| `receivers`       | object  | 接收人配置                                      |
| `receivers.type`  | enum    | 接收人类型：user/group/role/duty                |
| `mute_window`     | object  | 免打扰配置                                      |

### 屏蔽规则 (`shield`)

| 字段                 | 类型    | 说明                                      |
| -------------------- | ------- | ----------------------------------------- |
| `enabled`            | boolean | 是否启用屏蔽                              |
| `rules`              | array   | 屏蔽规则列表                              |
| `rules[].type`       | enum    | 屏蔽类型：maintenance/temporary/permanent |
| `rules[].time_range` | object  | 时间范围配置                              |

### 收敛配置 (`converge`)

| 字段         | 类型    | 说明           |
| ------------ | ------- | -------------- |
| `enabled`    | boolean | 是否启用收敛   |
| `window`     | int     | 收敛窗口（秒） |
| `dimensions` | array   | 收敛维度字段   |

---

## 用户配置界面设计建议

```
┌─────────────────────────────────────────────────────────────┐
│  创建告警策略                                    [保存] [取消]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  基本信息                                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  策略名称: [业务服务器CPU监控                    ]     │  │
│  │  所属业务: [选择业务 ▼]  标签: [ops] [infrastructure]  │  │
│  │  策略说明: [监控生产环境服务器CPU使用情况...       ]    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  检测配置                                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  数据源:  [系统监控 ▼] > [CPU ▼] > [使用率 ▼]          │  │
│  │                                                        │  │
│  │  告警级别设置:                                          │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │ 🔴 致命  ≥ [95  ]%  持续 [1 ]分钟  [删除]         │   │  │
│  │  │ 🟠 错误  ≥ [90  ]%  持续 [2 ]分钟  [删除]         │   │  │
│  │  │ 🟡 警告  ≥ [80  ]%  持续 [3 ]分钟  [删除]         │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │  [+ 添加级别]                                           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  通知配置                                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  通知渠道:  ☑ 企业微信  ☑ 短信  ☐ 语音  ☐ 邮件         │  │
│  │                                                        │  │
│  │  接收人:   [选择值班组 ▼]  备选人: [admin, backup]       │  │
│  │                                                        │  │
│  │  免打扰:   ☑ 启用  时段: [23:00] - [08:00]              │  │
│  │           排除: ☑ 致命告警  ☐ 错误告警                  │  │
│  │                                                        │  │
│  │  高级:     ☑ 告警收敛  窗口: [5 ]分钟                    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  屏蔽规则                                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  [+ 添加屏蔽规则]                                       │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │ 每周维护窗口  [编辑] [删除]                        │   │  │
│  │  │ 类型: 周期维护  时间: 每周二 02:00-06:00          │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  [展开高级配置]                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

这些配置完全面向用户业务场景，无需了解底层 Pipeline 的实现细节，系统会自动转换为可执行的流程配置。