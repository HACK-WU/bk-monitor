# TAPD 开放平台 API - 用户态授权凭证

> 原文档地址: https://o.tapd.woa.com/document/api-doc/next/api/API%E8%B0%83%E7%94%A8%E8%AF%B4%E6%98%8E%E4%B9%A6/%E6%8E%88%E6%9D%83%E5%87%AD%E8%AF%81/%E7%94%A8%E6%88%B7%E6%80%81.html

## 概述

在每个用户进入应用页面或者非界面接入点时，TAPD 通过下发授权码的方式，向应用授权获取当前用户信息的 API（OAuth 方式）。

---

## 一、获取用户授权码

### URL 获取授权码

所有用户接入点填写的地址，都会自动带上一个公共的参数 `code`，代表当前用户的授权码。可以用来换取临时 `access_token`，在 resource 中获取当前用户信息，也调用用户态的 API 接口，或者进行应用登录。

---

## 二、换取 Access Token

### 接入方使用过程

#### 1. 拼接 URL

**格式：**
```
https://tapd.woa.com/oauth/?response_type=code&client_id=%s&redirect_uri=%s&scope=%s&state=%s&auth_by=%s
```

**注意：**
1. 取多个 scope，使用空格分隔，如 `story#read bug#read`；
2. 参数要经过 `urlencode`。比如 scope 取 `story#read bug#read`，urlencode 后则是 `story%23read%20bug%23read` 或者 `story#read+bug#read`；
3. `auth_by` 目前支持 `user`；
4. `state` 参数**必填**，可以用来防止 CSRF 攻击，也可以用来传递一些自定义信息（如用户 ID 等）；
5. `client_id` 是应用 ID，需在应用管理中获取。

**示例：**
```
https://tapd.woa.com/oauth/?response_type=code&client_id=JnKeFzm1&redirect_uri=http://lion.oa.com/~anyechen/code/php/oauth_demo/hey.php&scope=story%23read%20bug%23read&auth_by=user&state=random_string
```

#### 2. 浏览器打开拼接好的 URL

#### 3. 用户点击"同意授权"

#### 4. 跳转到配置的回调 URL

跳转后会传递 `code` 参数、授权 `user_id` 的 `resource` 参数，以及回传的 `state` 参数。

**示例回调 URL：**
```
http://lion.oa.com/~anyechen/code/php/oauth_demo/hey.php?code=e09881835fc0a44c3bdabbbc091a1aa3f189554b&state=random_string&resource=%7B%22type%22%3A%22user%22%2C%22user_id%22%3A%221001320052%22%7D
```

**解析后的参数：**
```
Array
(
    [code] => e09881835fc0a44c3bdabbbc091a1aa3f189554b
    [state] => random_string
    [resource] => {"type":"user","user_id":"1001320052"}
)
```

**注意：**
- `code` 的有效期为 **五分钟**

#### 5. 使用 code 获取 access_token

##### 请求信息

| 项           | 内容                                      |
|--------------|-------------------------------------------|
| **请求 URL** | `http://apiv2.tapd.woa.com/tokens/request_token` |
| **请求方法** | POST                                      |

##### POST 参数

| 参数           | 说明                     |
|----------------|--------------------------|
| `grant_type`   | 必须取值 `authorization_code` |
| `redirect_uri` | 为配置的回调 URI          |
| `code`         | 从链接参数上取得的 code   |

##### 鉴权头（Basic Auth）

假设发放的 `client_id` 为 `Aladdin`，`client_secret` 为 `open sesame`，则处理步骤如下：

1. 将 `Aladdin:open sesame` 通过 BASE64 编码为：`QWxhZGRpbjpvcGVuIHNlc2FtZQ==`
2. 写入 HTTP 头部的 Authorization 信息：
```
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

##### 返回参数

| 参数           | 说明                          |
|----------------|-------------------------------|
| `access_token` | 访问 API 的凭据               |
| `expires_in`   | 有效时长，单位为秒            |
| `token_type`   | 凭据类型，都是 `Bearer`       |
| `scope`        | 接口范围                      |
| `resource`     | 项目权限范围                  |
| `now`          | 服务器当前时间                |

##### 示例请求

```bash
curl -u "client_id:client_secret" \
  -d "grant_type=authorization_code&redirect_uri=http://lion.oa.com/~anyechen/code/php/oauth_demo/hey.php&code=e09881835fc0a44c3bdabbbc091a1aa3f189554b" \
  "http://apiv2.tapd.woa.com/tokens/request_token"
```

##### 示例返回

```json
{
    "status": 1,
    "data": {
        "access_token": "9f11dab4be3fed782d15b7cfzxc8d08c49792119",
        "expires_in": 7200,
        "token_type": "Bearer",
        "scope": "bug#read story#read",
        "resource": {
            "type": "user",
            "user_id": "1001320052"
        },
        "now": "2026-01-06 17:16:04"
    },
    "info": "success"
}
```

---

## 三、获取用户信息

获取用户详细信息，请参考接口文档：
- [用户信息接口](/document/api-doc/API%E6%96%87%E6%A1%A3/api_reference/user/get_users_info.html)

---

## 四、用户免登录

### 概述

第三方应用可以通过 TAPD 官方提供的登录能力方便地获取当前 TAPD 的用户标识，利用 TAPD 用户标识来作为应用用户体系。

### 登录流程时序

```
用户已登录 TAPD
    │
    ▼
访问第三方应用（自动带上 code 参数）
    │
    ▼
应用后端向 TAPD 发送 /tokens/request_token 请求
    │
    ▼
获取用户基本信息 + 用户态 access_token
    │
    ▼
应用完成登录（可使用 nick/openid 作为登录态）
```

### 免登流程步骤

1. **用户第一次进入应用页面**时，应用访问链接会自动带上 TAPD 开放平台生成的授权码 `code` 参数；
2. **应用后端服务器发送请求**，由应用服务器端向 TAPD 接口发送 `/tokens/request_token` 请求：
   - 获取资源详情（即用户基本信息）
   - 获取用户态接口的 `access_token`（用于后续访问该用户的其他用户态接口）
3. **应用获取到用户 nick（或 openid）以及 access_token** 后，可以：
   - 直接将其作为用户登录态
   - 或转化为自定义的登录态，完成应用的登录
4. **凭证过期处理**：
   - 如果应用后端发现用户登录过期或者访问 TAPD 接口的凭证过期，可通过前端调用 TAPD 方法获取新的 code；
   - 获取到 code 之后，重新完成步骤 2-3 的登录操作。
5. **获取其他用户信息**：如果需要获取用户的其他信息，可调用获取用户信息接口。

---

## 五、高频问题

| 序号 | 问题描述 | 原因及解决方案 |
|------|----------|----------------|
| 1 | 访问授权链接时提示 **"invalid scope"** | scope 参数的权限没有在应用权限中勾选对应的权限。勾选完成后需**发布应用**才能生效。 |
| 2 | 访问授权链接时提示 **"参数 state 不能为空"** | state 参数为空。需填写 state 参数后才能访问。 |
| 3 | 访问授权链接时提示 **"redirect_uri mismatch"** | redirect_uri 和应用设置-安全设置中的 redirect_uri 不一致。需修改 redirect_uri 后才能访问。 |
| 4 | 请求 request_token 接口时返回 **"The redirect URI is missing or do not match"** | redirect_uri 和授权链接中传的 redirect_uri 不一致。需修改 redirect_uri 后才能访问。 |
| 5 | 请求 request_token 接口时返回 **"The authorization code has expired"** | code 已过期（有效期 5 分钟）。需重新获取 code 后才能访问。 |
