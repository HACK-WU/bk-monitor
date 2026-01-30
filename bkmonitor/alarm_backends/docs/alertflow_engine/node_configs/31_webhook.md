# Webhook Node Configuration (Webhook节点配置)

## 节点类型
- **NodeType**: `webhook`
- **分类**: ACTION (动作类)
- **功能**: 发送 HTTP 请求到外部系统，支持多种HTTP方法和认证方式

## 配置 Schema

### WebhookNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class HttpMethod(str, Enum):
    """HTTP方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class AuthType(str, Enum):
    """认证类型"""
    NONE = "none"               # 无认证
    BASIC = "basic"             # Basic认证
    BEARER = "bearer"           # Bearer Token
    API_KEY = "api_key"         # API Key
    OAUTH2 = "oauth2"           # OAuth2
    CUSTOM = "custom"           # 自定义


class ContentType(str, Enum):
    """请求内容类型"""
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    XML = "application/xml"
    TEXT = "text/plain"


class AuthConfigSerializer(serializers.Serializer):
    """认证配置"""
    type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AuthType],
        default="none",
        help_text="认证类型"
    )
    # Basic认证
    username = serializers.CharField(
        required=False,
        help_text="用户名（Basic认证）"
    )
    password = serializers.CharField(
        required=False,
        help_text="密码（Basic认证）"
    )
    # Bearer Token
    token = serializers.CharField(
        required=False,
        help_text="Token（Bearer认证）"
    )
    # API Key
    api_key_name = serializers.CharField(
        required=False,
        help_text="API Key名称"
    )
    api_key_value = serializers.CharField(
        required=False,
        help_text="API Key值"
    )
    api_key_location = serializers.ChoiceField(
        choices=[("header", "Header"), ("query", "Query")],
        default="header",
        required=False,
        help_text="API Key位置"
    )
    # OAuth2
    oauth2_token_url = serializers.CharField(
        required=False,
        help_text="OAuth2 Token URL"
    )
    oauth2_client_id = serializers.CharField(
        required=False,
        help_text="OAuth2 Client ID"
    )
    oauth2_client_secret = serializers.CharField(
        required=False,
        help_text="OAuth2 Client Secret"
    )
    oauth2_scope = serializers.CharField(
        required=False,
        help_text="OAuth2 Scope"
    )


class RetryConfigSerializer(serializers.Serializer):
    """重试配置"""
    enabled = serializers.BooleanField(
        default=True,
        help_text="是否启用重试"
    )
    max_attempts = serializers.IntegerField(
        default=3,
        min_value=1,
        max_value=10,
        help_text="最大重试次数"
    )
    retry_interval = serializers.IntegerField(
        default=5,
        help_text="重试间隔（秒）"
    )
    backoff_multiplier = serializers.FloatField(
        default=2.0,
        help_text="退避乘数"
    )
    retry_on_status = serializers.ListField(
        child=serializers.IntegerField(),
        default=[429, 500, 502, 503, 504],
        help_text="需要重试的HTTP状态码"
    )


class ResponseHandlerSerializer(serializers.Serializer):
    """响应处理配置"""
    success_status_codes = serializers.ListField(
        child=serializers.IntegerField(),
        default=[200, 201, 202, 204],
        help_text="成功状态码列表"
    )
    extract_fields = serializers.DictField(
        default=dict,
        required=False,
        help_text="从响应中提取字段的映射"
    )
    response_field = serializers.CharField(
        default="_webhook_response",
        help_text="存储响应的字段名"
    )
    store_response = serializers.BooleanField(
        default=True,
        help_text="是否存储响应数据"
    )


class WebhookNodeConfigSerializer(BaseNodeConfigSerializer):
    """Webhook节点配置"""
    node_type = serializers.CharField(default="webhook", read_only=True)
    
    # 请求URL
    url = serializers.CharField(help_text="Webhook URL（支持模板变量）")
    
    # HTTP方法
    method = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in HttpMethod],
        default="POST",
        help_text="HTTP方法"
    )
    
    # 请求头
    headers = serializers.DictField(
        default=dict,
        required=False,
        help_text="自定义请求头"
    )
    
    # 内容类型
    content_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ContentType],
        default="application/json",
        help_text="请求内容类型"
    )
    
    # 请求体模板
    body_template = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="请求体模板（支持Jinja2语法）"
    )
    
    # 查询参数
    query_params = serializers.DictField(
        default=dict,
        required=False,
        help_text="URL查询参数"
    )
    
    # 认证配置
    auth = AuthConfigSerializer(
        required=False,
        help_text="认证配置"
    )
    
    # 超时配置
    connect_timeout = serializers.IntegerField(
        default=10,
        help_text="连接超时（秒）"
    )
    read_timeout = serializers.IntegerField(
        default=30,
        help_text="读取超时（秒）"
    )
    
    # 重试配置
    retry = RetryConfigSerializer(
        required=False,
        help_text="重试配置"
    )
    
    # 响应处理
    response_handler = ResponseHandlerSerializer(
        required=False,
        help_text="响应处理配置"
    )
    
    # SSL配置
    verify_ssl = serializers.BooleanField(
        default=True,
        help_text="是否验证SSL证书"
    )
    client_cert = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="客户端证书路径"
    )
    client_key = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="客户端私钥路径"
    )
    
    # 并发控制
    max_concurrent = serializers.IntegerField(
        default=10,
        help_text="最大并发请求数"
    )
    
    # 失败处理
    fail_on_error = serializers.BooleanField(
        default=False,
        help_text="请求失败时是否中断Pipeline"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "webhook" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `url` | string | 是 | - | Webhook URL |
| `method` | string | 否 | "POST" | HTTP方法 |
| `headers` | object | 否 | {} | 自定义请求头 |
| `content_type` | string | 否 | "application/json" | 内容类型 |
| `body_template` | string | 否 | null | 请求体模板 |
| `query_params` | object | 否 | {} | 查询参数 |
| `auth` | object | 否 | - | 认证配置 |
| `connect_timeout` | integer | 否 | 10 | 连接超时 |
| `read_timeout` | integer | 否 | 30 | 读取超时 |
| `verify_ssl` | boolean | 否 | true | 验证SSL |
| `fail_on_error` | boolean | 否 | false | 失败中断 |

### 认证配置 (AuthConfig)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 否 | 认证类型 |
| `username` | string | 否 | Basic用户名 |
| `password` | string | 否 | Basic密码 |
| `token` | string | 否 | Bearer Token |
| `api_key_name` | string | 否 | API Key名称 |
| `api_key_value` | string | 否 | API Key值 |
| `api_key_location` | string | 否 | API Key位置 |

### 重试配置 (RetryConfig)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `enabled` | boolean | 否 | true | 启用重试 |
| `max_attempts` | integer | 否 | 3 | 最大重试次数 |
| `retry_interval` | integer | 否 | 5 | 重试间隔 |
| `backoff_multiplier` | float | 否 | 2.0 | 退避乘数 |
| `retry_on_status` | array | 否 | [429,500...] | 重试状态码 |

### 响应处理配置 (ResponseHandler)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `success_status_codes` | array | 否 | [200,201...] | 成功状态码 |
| `extract_fields` | object | 否 | {} | 字段提取映射 |
| `response_field` | string | 否 | "_webhook_response" | 响应字段 |
| `store_response` | boolean | 否 | true | 存储响应 |

### 认证类型说明

| 类型 | 说明 | 配置项 |
|------|------|--------|
| `none` | 无认证 | - |
| `basic` | HTTP Basic | username, password |
| `bearer` | Bearer Token | token |
| `api_key` | API Key | api_key_name, api_key_value, api_key_location |
| `oauth2` | OAuth2 | oauth2_token_url, oauth2_client_id, oauth2_client_secret |
| `custom` | 自定义 | 通过headers配置 |

## JSON 配置示例

### 示例 1: 简单POST请求

```json
{
  "name": "simple_webhook",
  "description": "发送告警到外部系统",
  "enabled": true,
  "node_type": "webhook",
  "url": "https://api.example.com/alerts",
  "method": "POST",
  "headers": {
    "X-Custom-Header": "value"
  },
  "content_type": "application/json",
  "body_template": "{\n  \"alert_id\": \"{{ event.alert_id }}\",\n  \"alert_name\": \"{{ event.alert_name }}\",\n  \"severity\": {{ event.severity }},\n  \"target\": \"{{ event.target }}\",\n  \"current_value\": {{ event.current_value }},\n  \"timestamp\": \"{{ event.time }}\"\n}",
  "auth": {
    "type": "bearer",
    "token": "${WEBHOOK_TOKEN}"
  },
  "connect_timeout": 10,
  "read_timeout": 30,
  "retry": {
    "enabled": true,
    "max_attempts": 3,
    "retry_interval": 5
  },
  "fail_on_error": false,
  "execution": {
    "timeout": 60
  }
}
```

### 示例 2: 带OAuth2认证的Webhook

```json
{
  "name": "oauth2_webhook",
  "description": "OAuth2认证的企业API回调",
  "enabled": true,
  "node_type": "webhook",
  "url": "https://enterprise.example.com/api/v1/incidents",
  "method": "POST",
  "headers": {
    "Accept": "application/json",
    "X-Request-Id": "{{ event.trace_id }}"
  },
  "content_type": "application/json",
  "body_template": "{\n  \"title\": \"[{{ event.severity_display }}] {{ event.alert_name }}\",\n  \"description\": \"告警目标: {{ event.target }}\\n当前值: {{ event.current_value }}\\n触发时间: {{ event.time }}\",\n  \"priority\": {{ 5 - event.severity }},\n  \"category\": \"monitoring\",\n  \"tags\": {{ event.tags | tojson }},\n  \"source\": \"bk_monitor\",\n  \"external_id\": \"{{ event.alert_id }}\"\n}",
  "auth": {
    "type": "oauth2",
    "oauth2_token_url": "https://auth.example.com/oauth/token",
    "oauth2_client_id": "${OAUTH_CLIENT_ID}",
    "oauth2_client_secret": "${OAUTH_CLIENT_SECRET}",
    "oauth2_scope": "incidents:write"
  },
  "connect_timeout": 15,
  "read_timeout": 45,
  "retry": {
    "enabled": true,
    "max_attempts": 3,
    "retry_interval": 10,
    "backoff_multiplier": 2.0,
    "retry_on_status": [429, 500, 502, 503, 504]
  },
  "response_handler": {
    "success_status_codes": [200, 201],
    "extract_fields": {
      "incident_id": "data.id",
      "incident_url": "data.url"
    },
    "response_field": "_incident_response",
    "store_response": true
  },
  "verify_ssl": true,
  "max_concurrent": 5,
  "fail_on_error": false,
  "execution": {
    "timeout": 90
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 企业微信机器人消息

```json
{
  "name": "wecom_robot_webhook",
  "description": "企业微信机器人告警通知",
  "enabled": true,
  "node_type": "webhook",
  "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${WECOM_KEY}",
  "method": "POST",
  "content_type": "application/json",
  "body_template": "{\n  \"msgtype\": \"markdown\",\n  \"markdown\": {\n    \"content\": \"## <font color=\\\"{{ 'warning' if event.severity == 1 else 'info' }}\\\">{{ event.severity_display }}</font> {{ event.alert_name }}\\n> **告警目标**: {{ event.target }}\\n> **当前值**: {{ event.current_value }}\\n> **触发时间**: {{ event.time | datetime }}\\n> **策略ID**: {{ event.strategy_id }}\\n\\n[查看详情]({{ event.alert_url }})\"\n  }\n}",
  "auth": {
    "type": "none"
  },
  "connect_timeout": 10,
  "read_timeout": 30,
  "retry": {
    "enabled": true,
    "max_attempts": 2,
    "retry_interval": 3,
    "retry_on_status": [429, 500, 502, 503]
  },
  "response_handler": {
    "success_status_codes": [200],
    "extract_fields": {
      "errcode": "errcode",
      "errmsg": "errmsg"
    },
    "store_response": true
  },
  "verify_ssl": true,
  "max_concurrent": 20,
  "fail_on_error": false,
  "skip_condition": {
    "logic": "or",
    "conditions": [
      {
        "field": "event.is_shielded",
        "operator": "eq",
        "value": true
      }
    ]
  },
  "execution": {
    "timeout": 30
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **告警推送**：将告警推送到第三方系统（ITSM、工单系统）
2. **机器人通知**：发送到企业微信/钉钉/飞书机器人
3. **数据同步**：告警数据同步到数据仓库或分析平台
4. **触发自动化**：触发CI/CD流水线或自动化脚本
5. **事件聚合**：发送到事件管理平台进行聚合分析
6. **状态更新**：更新外部系统的告警状态
7. **回调通知**：告警处理后的回调通知

## 注意事项

1. **URL模板**：
   - 支持Jinja2模板语法
   - 敏感信息使用环境变量 `${VAR_NAME}`
   - 注意URL编码特殊字符

2. **请求体模板**：
   - JSON格式需确保语法正确
   - 字符串值需要引号包裹
   - 使用 `| tojson` 过滤器处理复杂类型

3. **认证安全**：
   - 敏感信息通过环境变量配置
   - 建议使用HTTPS
   - OAuth2 Token会自动刷新

4. **超时配置**：
   - `connect_timeout` 控制连接建立时间
   - `read_timeout` 控制响应读取时间
   - 总超时应在节点execution.timeout内

5. **重试策略**：
   - 指数退避避免压垮目标系统
   - 429状态码表示限流，应增加间隔
   - 5xx通常可以重试，4xx通常不应重试

6. **响应处理**：
   - `extract_fields` 可从响应提取数据到事件
   - 提取路径使用JSONPath语法
   - 存储响应便于后续节点使用

7. **并发控制**：
   - `max_concurrent` 限制并发请求数
   - 避免对目标系统造成过大压力
   - 高并发场景建议增加超时

8. **SSL/TLS**：
   - 生产环境建议 `verify_ssl=true`
   - 自签名证书需配置客户端证书

## 相关节点

- **上游节点**：
  - Transform（转换节点）：准备Webhook数据
  - Converge（收敛节点）：收敛后批量发送
  - Router（路由节点）：路由到不同Webhook

- **下游节点**：
  - Storage（存储节点）：存储Webhook响应
  - Callback（回调节点）：处理Webhook响应
  - Log（日志节点）：记录请求日志

### 典型组合模式

1. **Transform → Webhook → Storage**
   - 转换 → Webhook → 存储

2. **Converge → Webhook[批量]**
   - 收敛 → 批量Webhook

3. **Router → [Webhook_A | Webhook_B]**
   - 路由 → 不同Webhook

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
