# TAPD 用户态 OAuth 2.0 接口文档

> **文档版本**：v1.0 | **最后更新**：2026-06-05
> 
> 本文档整理了 TAPD 用户态 OAuth 授权相关的所有接口。

---

## 一、接口总览

| 序号 | 接口名称 | 请求方式 | 地址 | 说明 |
|:----:|----------|:--------:|------|------|
| 1 | [用户授权](#二用户授权接口) | GET | `https://tapd.woa.com/oauth/` | 生成授权 URL，引导用户授权 |
| 2 | [获取 Access Token](#三获取-access-token-接口) | POST | `http://apiv2.tapd.woa.com/tokens/request_token` | 用 code 换取 access_token |
| 3 | [刷新 Access Token](#四刷新-access-token-接口) | POST | `http://apiv2.tapd.woa.com/tokens/refresh_token` | 用 refresh_token 换取新 token |
| 4 | [获取用户信息](#五获取用户信息接口) | GET | `http://apiv2.tapd.woa.com/users/info` | 获取当前授权用户信息 |

---

## 二、用户授权接口

### 2.1 接口说明

引导用户进行 OAuth 授权，获取授权码（code）。

**请求方式**：`GET`

**请求地址**：`https://tapd.woa.com/oauth/`

### 2.2 请求参数

| 参数 | 是否必须 | 类型 | 说明 |
|------|:--------:|------|------|
| `response_type` | ✅ | string | 固定值 `code` |
| `client_id` | ✅ | string | TAPD 应用 ID（如 `gtm`） |
| `redirect_uri` | ✅ | string | 回调地址，需 urlencode，必须与应用安全设置一致 |
| `scope` | ✅ | string | 权限范围，多个用空格分隔，`#` 需编码为 `%23` |
| `state` | ✅ | string | 随机字符串，用于防 CSRF，**必须填写** |
| `auth_by` | ✅ | string | 固定值 `user`，表示用户态授权 |

### 2.3 Scope 格式说明

```
原始值：story#read story#write bug#read
编码后：story%23read%20story%23write%20bug%23read

编码规则：
- #  → %23（必须）
- 空格 → %20（必须）
```

**常用 Scope 列表**：

| Scope | 说明 |
|-------|------|
| `story#read` | 读取需求 |
| `story#write` | 写入需求 |
| `bug#read` | 读取缺陷 |
| `bug#write` | 写入缺陷 |
| `user#read` | 读取用户信息 |
| `workspace#read` | 读取项目信息 |

### 2.4 请求示例

```
GET https://tapd.woa.com/oauth/?
  response_type=code&
  client_id=gtm&
  redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fcallback&
  scope=story%23read%20story%23write&
  state=random_string&
  auth_by=user
```

### 2.5 返回说明

用户点击"同意授权"后，TAPD 会 302 重定向到 `redirect_uri`，并携带以下参数：

| 参数 | 说明 |
|------|------|
| `code` | 授权码，**有效期 5 分钟**，一次性使用 |
| `state` | 回传之前传入的 state，用于校验 CSRF |
| `resource` | JSON 字符串，含授权用户信息 |

**返回示例**：

```
http://localhost:5000/callback
?code=e09881835fc0a44c3bdabbbc091a1aa3f189554b
&state=7xmK4vR9sTjLwQpM3nFgHz
&resource=%7B%22type%22%3A%22user%22%2C%22user_id%22%3A%221002022208%22%7D
```

---

## 三、获取 Access Token 接口

### 3.1 接口说明

使用授权码（code）换取访问令牌（access_token）。

**请求方式**：`POST`

**请求地址**：`http://apiv2.tapd.woa.com/tokens/request_token`

### 3.2 请求头（Headers）

| 参数 | 是否必须 | 说明 |
|------|:--------:|------|
| `Authorization` | ✅ | `Basic base64(client_id:client_secret)` |

**Basic Auth 生成方式**：

将 `client_id:client_secret` 字符串进行 Base64 编码，放入 Header。

示例：`gtm:03A9E73B-3F09-202F-F7B5-165C8C5DD403` → `Z3RtOjAzQTlFNzNCLTNGMDktMjAyRi1GN0I1LTE2NUM4QzVERDQwMw==`

### 3.3 请求体（Body）

| 参数 | 是否必须 | 类型 | 说明 |
|------|:--------:|------|------|
| `grant_type` | ✅ | string | 固定值 `authorization_code` |
| `redirect_uri` | ✅ | string | 必须与授权 URL 中的完全一致 |
| `code` | ✅ | string | 用户授权后回调地址中的授权码 |

### 3.4 请求示例

```bash
curl -X POST http://apiv2.tapd.woa.com/tokens/request_token \
  -H "Authorization: Basic Z3RtOjAzQTlFNzNCLTNGMDktMjAyRi1GN0I1LTE2NUM4QzVERDQwMw==" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=http://localhost:5000/callback" \
  -d "code=e09881835fc0a44c3bdabbbc091a1aa3f189554b"
```

### 3.5 返回结果

**成功响应**：

```json
{
    "status": 1,
    "data": {
        "access_token": "a39eb90daf107a5b7a6765b3fe47822361502037",
        "expires_in": 7200,
        "token_type": "Bearer",
        "scope": "story#read story#write bug#read bug#write user#read",
        "refresh_token": "9b5b4ffdc36cccee62abc3f94554df5d50d7d19f",
        "resource": {
            "type": "user",
            "user_id": "1002022208"
        },
        "now": "2026-06-04 15:55:21"
    },
    "info": "success"
}
```

**返回参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | int | 状态码，`1` 表示成功 |
| `data.access_token` | string | 访问令牌，用于调用业务 API |
| `data.expires_in` | int | 有效期（秒），通常为 `7200`（2小时） |
| `data.token_type` | string | 令牌类型，固定为 `Bearer` |
| `data.scope` | string | 实际授权的权限范围 |
| `data.refresh_token` | string | 刷新令牌，用于续期（官方文档未提及，但实际存在） |
| `data.resource.user_id` | string | 授权用户的 TAPD 用户 ID |
| `data.now` | string | TAPD 服务器当前时间（北京时间） |

**失败响应示例**：

```json
{
    "status": -1,
    "data": null,
    "info": "The authorization code has expired",
    "meta": {},
    "request_id": "xxx"
}
```

---

## 四、刷新 Access Token 接口

### 4.1 接口说明

使用 `refresh_token` 换取新的 `access_token`，无需用户重新授权。

> ⚠️ **注意**：官方文档未提及此接口，但实际可用。使用独立的接口地址，不是复用 `/tokens/request_token`。

**请求方式**：`POST`

**请求地址**：`http://apiv2.tapd.woa.com/tokens/refresh_token`

### 4.2 请求头（Headers）

| 参数 | 是否必须 | 说明 |
|------|:--------:|------|
| `Authorization` | ✅ | `Basic base64(client_id:client_secret)` |

### 4.3 请求体（Body）

| 参数 | 是否必须 | 类型 | 说明 |
|------|:--------:|------|------|
| `grant_type` | ✅ | string | 固定值 `refresh_token` |
| `refresh_token` | ✅ | string | 授权时获取的 refresh_token |

### 4.4 请求示例

```bash
curl -X POST http://apiv2.tapd.woa.com/tokens/refresh_token \
  -H "Authorization: Basic Z3RtOjAzQTlFNzNCLTNGMDktMjAyRi1GN0I1LTE2NUM4QzVERDQwMw==" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=9b5b4ffdc36cccee62abc3f94554df5d50d7d19f"
```

### 4.5 返回结果

**成功响应**：

```json
{
    "status": 1,
    "data": {
        "access_token": "新生成的 access_token",
        "refresh_token": "新的 refresh_token（可能为空）",
        "expires_in": 7200,
        "token_type": "Bearer",
        "scope": "story#read story#write",
        "resource": {
            "type": "user",
            "user_id": "1002022208"
        }
    },
    "info": "success"
}
```

**返回参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | int | 状态码，`1` 表示成功 |
| `data.access_token` | string | 新的访问令牌 |
| `data.refresh_token` | string | 新的刷新令牌（可能为空，建议保留原值） |
| `data.expires_in` | int | 有效期（秒），通常为 `7200`（2小时） |

---

## 五、获取用户信息接口

### 5.1 接口说明

获取当前授权用户的详细信息。

**请求方式**：`GET`

**请求地址**：`http://apiv2.tapd.woa.com/users/info`

### 5.2 请求参数

| 参数 | 位置 | 是否必须 | 说明 |
|------|:----:|:--------:|------|
| `access_token` | Query | ✅ | 授权时获取的 access_token |

### 5.3 请求示例

```bash
# 使用 access_token
curl "http://apiv2.tapd.woa.com/users/info?access_token=a39eb90daf107a5b7a6765b3fe47822361502037"

# 使用 Cookie（内网环境）
curl "http://apiv2.tapd.woa.com/users/info" \
  -H "Cookie: bk_uid=v_wypgwu; bk_ticket=xxx..."
```

### 5.4 返回结果

**成功响应**：

```json
{
    "status": 1,
    "data": [
        {
            "id": "1002022208",
            "name": "张三",
            "email": "zhangsan@example.com",
            "avatar": "https://...",
            "created": "2023-01-01 00:00:00",
            "modified": "2026-06-01 12:00:00"
        }
    ],
    "info": "success"
}
```

**返回参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | int | 状态码，`1` 表示成功 |
| `data` | array | 用户信息数组（通常只有一个元素） |
| `data[0].id` | string | 用户 ID |
| `data[0].name` | string | 用户姓名 |
| `data[0].email` | string | 用户邮箱 |
| `data[0].avatar` | string | 头像 URL |

---

## 六、错误码说明

### 6.1 通用错误码

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `basic auth info is required` | Token 接口缺少 Basic Auth | 添加 `Authorization: Basic {base64(client_id:secret)}` |
| `invalid_client` | client_id 或 client_secret 错误 | 检查应用配置 |
| `invalid scope` | 应用未申请该权限 | 在应用权限中勾选并发布 |
| `参数state不能为空` | state 参数缺失 | 确保 URL 包含 state |
| `redirect_uri mismatch` | 回调地址不一致 | 三处 redirect_uri 必须完全一致 |
| `The authorization code has expired` | code 超过 5 分钟 | 重新授权获取新 code |
| `No address associated with hostname` | 域名无法解析 | 使用 `apiv2.tapd.woa.com`（公网） |

### 6.2 HTTP 状态码

| 状态码 | 说明 |
|:------:|------|
| 200 | 请求成功（需检查 `status` 字段） |
| 401 | 未授权（检查 Basic Auth） |
| 403 | 权限不足 |
| 404 | 接口不存在 |
| 422 | 参数错误（如缺少 Basic Auth） |
| 500 | TAPD 服务器内部错误 |

---

## 七、完整调用流程

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户授权流程                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 生成授权 URL                                           │
│  GET https://tapd.woa.com/oauth/?client_id=xxx&scope=xxx...     │
│                                                                 │
│  Step 2: 用户浏览器打开授权 URL，点击"同意授权"                   │
│  → TAPD 302 重定向到 redirect_uri?code=xxx&state=xxx            │
│                                                                 │
│  Step 3: 后端用 code 换取 access_token                          │
│  POST http://apiv2.tapd.woa.com/tokens/request_token            │
│  Authorization: Basic {base64(client_id:secret)}                │
│  Body: grant_type=authorization_code&code=xxx&redirect_uri=xxx  │
│                                                                 │
│  Step 4: 使用 access_token 调用业务 API                          │
│  GET http://apiv2.tapd.woa.com/users/info?access_token=xxx      │
│                                                                 │
│  Step 5: token 过期前，用 refresh_token 刷新                     │
│  POST http://apiv2.tapd.woa.com/tokens/refresh_token            │
│  Authorization: Basic {base64(client_id:secret)}                │
│  Body: grant_type=refresh_token&refresh_token=xxx               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 八、安全注意事项

1. **`client_secret` 绝对不能暴露到前端代码或 Git 仓库**
2. **所有 Token 相关接口必须在后端调用**
3. **`state` 参数必须随机生成并校验**
4. **`access_token` 和 `refresh_token` 应加密存储**
5. **不要在日志中打印完整的 token 值**

---

**文档维护**：如发现接口变更或新接口，请及时更新本文档。
