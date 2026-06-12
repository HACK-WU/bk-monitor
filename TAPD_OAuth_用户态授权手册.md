# TAPD 用户态 OAuth 2.0 授权操作手册

> 基于实际对接经验整理，已验证通过。
> 客户端：gtm | 用户 ID：1002022208

---

## 一、前置准备清单

在开始之前，必须确认以下 4 项全部就绪：

### 1. TAPD 开放平台应用

| 项目          | 要求                                 | 获取位置                              |
| ------------- | ------------------------------------ | ------------------------------------- |
| client_id     | 应用唯一标识，如 `gtm`               | `https://o.tapd.woa.com/admin/myapps` |
| client_secret | 应用密钥，用于后端换 token           | 同上，创建应用后生成                  |
| 应用已发布    | **修改权限或安全设置后必须点击发布** | 应用管理页面右上角                    |

### 2. 安全设置（redirect_uri）

在应用管理的 **安全设置** 中填写回调地址，**必须与后续代码中配置的一字不差**：

```
http://localhost:5000/callback
```

⚠️ **常见踩坑**：

- `http://` vs `https://` 必须一致
- 域名、端口必须完全匹配

### 3. 权限设置（scope）

在应用管理的 **权限设置** 中勾选需要的 API 权限，例如：

- `story#read`（读取需求）
- `bug#read`（读取缺陷）
- `user#read`（读取用户信息）

⚠️ **修改权限后必须点击发布**，否则授权时会报 `invalid scope`。

### 4. 浏览器已登录 TAPD

确保当前浏览器已经登录了 TAPD（`https://tapd.woa.com`），否则无法完成静默授权。

---

## 二、完整授权流程

### 时序图

```
┌─────────┐         ┌──────────┐         ┌─────────────┐
│  用户   │         │  你的应用 │         │  TAPD 服务器 │
└────┬────┘         └────┬─────┘         └──────┬──────┘
     │                   │                      │
     │  1.访问应用首页    │                      │
     │──────────────────>│                      │
     │                   │  2.生成授权 URL      │
     │                   │  （含 state 防 CSRF）│
     │  3.展示授权链接    │                      │
     │<──────────────────│                      │
     │                   │                      │
     │  4.点击链接跳转   │                      │
     │─────────────────────────────────────────>│
     │                   │                      │
     │                   │  5.TAPD 展示授权页面 │
     │                   │  （用户点"同意"）    │
     │<─────────────────────────────────────────│
     │                   │                      │
     │  6.302 重定向回本 │                      │
     │    应用 callback │                      │
     │    ?code=xxx     │                      │
     │──────────────────>│                      │
     │                   │  7.后端用 code +     │
     │                   │    client_secret     │
     │                   │    换 access_token   │
     │                   │─────────────────────>│
     │                   │                      │
     │                   │  8.返回 token 信息   │
     │                   │  （含 refresh_token）│
     │                   │<─────────────────────│
     │                   │                      │
     │  9.展示授权结果    │                      │
     │<──────────────────│                      │
```

---

## 三、步骤详解

### Step 1：生成授权 URL

拼接以下参数：

| 参数            | 值                               | 说明                                                    |
| --------------- | -------------------------------- | ------------------------------------------------------- |
| `response_type` | `code`                           | 固定值                                                  |
| `client_id`     | `gtm`                            | 你的应用 ID                                             |
| `redirect_uri`  | `http://localhost:5000/callback` | 安全设置中配置的回调地址                                |
| `scope`         | `story#read`                     | 需要的 API 权限（多个用空格分隔），`#` 必须编码为 `%23` |
| `state`         | 随机字符串                       | **必填**，防 CSRF，也可透传自定义信息                   |
| `auth_by`       | `user`                           | 固定值，表示用户态授权                                  |

**生成的 URL 示例**：

```
https://tapd.woa.com/oauth/?response_type=code&client_id=gtm
&redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fcallback
&scope=story%23read
&state=7xmK4vR9sTjLwQpM3nFgHz
&auth_by=user
```

> ⚠️ `scope` 中的 `#` 必须经过 URL 编码（`%23`），否则会被浏览器截断。

---

### Step 2：用户授权

用户浏览器打开上述 URL 后，TAPD 会自动展示授权页面：

```
┌─────────────────────────────┐
│  应用 gtm 请求获取以下权限：  │
│  • 读取需求 (story#read)     │
│                             │
│      [ 同意授权 ]  [取消]    │
└─────────────────────────────┘
```

点击 **同意授权** 后，TAPD 会 302 重定向到：

```
http://localhost:5000/callback
?code=e09881835fc0a44c3bdabbbc091a1aa3f189554b
&state=7xmK4vR9sTjLwQpM3nFgHz
&resource=%7B%22type%22%3A%22user%22%2C%22user_id%22%3A%221002022208%22%7D
```

**回调参数说明**：

| 参数       | 说明                                      |
| ---------- | ----------------------------------------- |
| `code`     | 授权码，**有效期仅 5 分钟**，一次性使用   |
| `state`    | 回传你之前传入的 state，用于校验 CSRF     |
| `resource` | 授权用户信息（JSON 字符串），含 `user_id` |

---

### Step 3：换取 Access Token

后端收到 `code` 后，立即向 TAPD 发起 POST 请求换 token：

```bash
curl -X POST http://apiv2.tapd.woa.com/tokens/request_token \
  -H "Authorization: Basic $(echo -n 'gtm:03A9E73B-3F09-202F-F7B5-165C8C5DD403' | base64)" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=http://localhost:5000/callback" \
  -d "code=e09881835fc0a44c3bdabbbc091a1aa3f189554b"
```

**关键点**：

- `Authorization` 头使用 **Basic Auth**，格式为 `Base64(client_id:client_secret)`
- `redirect_uri` 必须与授权 URL 中的**完全一致**
- `client_secret` **绝对不能暴露到前端**

---

### Step 4：Token 返回结果解析

**实际返回示例**：

```json
{
  "status": 1,
  "data": {
    "access_token": "a39eb90daf107a5b7a6765b3fe47822361502037",
    "expires_in": 7200,
    "token_type": "Bearer",
    "scope": "story#read",
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

**字段说明**：

| 字段               | 值                    | 说明                                        |
| ------------------ | --------------------- | ------------------------------------------- |
| `access_token`     | `a39eb90d...`         | **访问令牌**，后续调用 API 时携带           |
| `expires_in`       | `7200`                | 有效期 **7200 秒 = 2 小时**                 |
| `token_type`       | `Bearer`              | 令牌类型，调用 API 时格式：`Bearer <token>` |
| `scope`            | `story#read`          | 实际授权的权限范围                          |
| `refresh_token`    | `9b5b4ffd...`         | **刷新令牌** ⚠️ 官方文档未提及，但实际存在！ |
| `resource.user_id` | `1002022208`          | 当前授权用户的 TAPD 用户 ID                 |
| `now`              | `2026-06-04 15:55:21` | TAPD 服务器当前时间（北京时间）             |

---

## 四、认证方式：Client Secret vs Cookie（重要！）

> 🔑 **这是 TAPD OAuth 对接中最关键的发现，已实际验证。**

### 4.1 核心结论

TAPD 的不同接口对认证方式有**不同的强制要求**：

| 接口类型       | 示例接口                                           | 必须的认证方式        |
| -------------- | -------------------------------------------------- | --------------------- |
| **Token 接口** | `/tokens/request_token`<br>`/tokens/refresh_token` | ✅ **必须 Basic Auth** |

### 4.2  Cookie

> **Cookie** = 接入内网环境后，浏览器访问 TAPD 页面时自动携带的身份凭证。

当你的服务器部署在**腾讯内网**环境中：

1. 用户通过内网访问 TAPD 页面（如 `https://tapd.woa.com`）
2. 浏览器自动保存 TAPD 登录状态（包含 `bk_uid`、`bk_ticket` 等字段）
3. 这个完整的 Cookie 字符串就是"接入内网的 TAPD Cookie"

**Cookie 示例**：

```
bklogin_csrftoken_1a4e1f7=xxx; bk_uid=v_wypgwu; bk_ticket=e7-6Vcaf...; blueking_language=zh-cn
```

### 4.3 为什么 Token 接口必须用 Client Secret？

实测结果：如果只用 Cookie 调用 token 接口：

```json
{
  "status": 422,
  "data": null,
  "info": "basic auth info is required",
  "meta": {},
  "request_id": "19c153610764cf8837eb3991d6a77f9df"
}
```

**原因分析**：

- Token 接口是**应用级别的操作**（换取令牌），需要验证应用身份 → 必须 `Basic Auth`
- 业务 API 是**用户级别操作**（查询数据），可以用用户身份 → 支持 Cookie

### 4.4 实际调用示例

#### 换取 access_token（必须 Basic Auth）

```bash
# ✅ 正确方式：Basic Auth + Cookie（可选）
curl -X POST http://apiv2.tapd.woa.com/tokens/request_token \
  -H "Authorization: Basic $(echo -n 'gtm:CLIENT_SECRET' | base64)" \  # 必须有
  -H "Cookie: bk_uid=v_wypgwu; bk_ticket=xxx..." \                      # 可选
  -d "grant_type=authorization_code" \
  -d "redirect_uri=http://localhost:5000/callback" \
  -d "code=e09881835fc0a44c..."

# ❌ 错误方式：仅使用 Cookie
curl -X POST http://apiv2.tapd.woa.com/tokens/request_token \
  -H "Cookie: bk_uid=v_wypgwu; bk_ticket=xxx..."
# 返回: basic auth info is required (status: 422)
```

#### 调用业务 API（Cookie 即可）

```bash
# ✅ 方式一：使用 access_token
curl http://apiv2.tapd.woa.com/users/info?access_token=xxx

# ✅ 方式二：使用 Cookie（内网环境推荐）
curl http://apiv2.tapd.woa.com/users/info \
  -H "Cookie: bk_uid=v_wypgwu; bk_ticket=xxx..."
```



---

## 五、Refresh Token 刷新访问令牌


### 5.1 为什么需要 Refresh Token？

| 问题 | 解决方案 |
|------|----------|
| `access_token` 有效期仅 **2 小时** | 使用 `refresh_token` 换取新 token，无需用户重新授权 |
| 用户离开后 token 过期 | 后端定期刷新，保持登录状态 |
| 频繁授权影响体验 | 一次授权，长期可用 |

### 5.2 接口说明

**接口地址**：`POST http://apiv2.tapd.woa.com/tokens/refresh_token`

> ⚠️ **注意**：这是独立接口，不是复用 `/tokens/request_token`

**请求参数**：

| 参数 | 位置 | 必须 | 说明 |
|------|------|------|------|
| `Authorization` | Header | ✅ | `Basic base64(client_id:client_secret)` |
| `grant_type` | Body | ✅ | 固定值 `refresh_token` |
| `refresh_token` | Body | ✅ | 授权时获取的 refresh_token |

**返回结果**：

```json
{
    "status": 1,
    "data": {
        "access_token": "新生成的 access_token",
        "refresh_token": "新的 refresh_token（可选）",
        "expires_in": 7200,
        "scope": "story#read story#write",
        "resource": {
            "type": "user",
            "user_id": "1002022208"
        }
    },
    "info": "success"
}
```

### 5.3 代码实现

```python
import base64
import requests

def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """使用 refresh_token 换取新的 access_token
    
    Args:
        client_id: TAPD 应用 ID
        client_secret: TAPD 应用密钥
        refresh_token: 刷新令牌（授权时获取）
    
    Returns:
        dict: TAPD API 返回的 JSON 响应
    """
    # 1. 构造 Basic Auth（必须）
    credentials = f"{client_id}:{client_secret}"
    auth = base64.b64encode(credentials.encode()).decode()
    
    # 2. 发送请求
    headers = {
        "Authorization": f"Basic {auth}"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    resp = requests.post(
        "http://apiv2.tapd.woa.com/tokens/refresh_token",
        headers=headers,
        data=data,
        timeout=15
    )
    return resp.json()


# 使用示例
result = refresh_access_token(
    client_id="gtm",
    client_secret="03A9E73B-3F09-202F-F7B5-165C8C5DD403",
    refresh_token="9b5b4ffdc36cccee62abc3f94554df5d50d7d19f"
)

if result.get("status") == 1:
    new_token = result["data"]["access_token"]
    print(f"刷新成功，新 token: {new_token}")
else:
    print(f"刷新失败: {result.get('info')}")
```

### 5.4 最佳实践：Token 自动续期

```python
import time
from datetime import datetime, timedelta

class TAPDTokenManager:
    """TAPD Token 管理器，支持自动续期"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.refresh_token = None
        self.expire_at = None  # token 过期时间
    
    def set_token(self, token_data: dict):
        """设置初始 token（授权成功后调用）"""
        self.access_token = token_data.get("access_token")
        self.refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 7200)
        self.expire_at = datetime.now() + timedelta(seconds=expires_in)
    
    def get_access_token(self) -> str:
        """获取有效的 access_token，必要时自动刷新"""
        # 检查是否需要刷新（提前 5 分钟刷新）
        if self.expire_at and datetime.now() >= self.expire_at - timedelta(minutes=5):
            self._refresh()
        return self.access_token
    
    def _refresh(self):
        """执行刷新"""
        if not self.refresh_token:
            raise Exception("无 refresh_token，需要重新授权")
        
        result = refresh_access_token(
            self.client_id,
            self.client_secret,
            self.refresh_token
        )
        
        if result.get("status") == 1:
            self.set_token(result["data"])
            print(f"[{datetime.now()}] Token 已刷新，新过期时间: {self.expire_at}")
        else:
            raise Exception(f"刷新失败: {result}")


# 使用示例
manager = TAPDTokenManager("gtm", "SECRET")
manager.set_token(authorize_result["data"])  # 授权后设置

# 业务代码中使用（自动续期）
token = manager.get_access_token()  # 如果即将过期，会自动刷新
```

### 5.5 注意事项

| 事项 | 说明 |
|------|------|
| **必须使用 Basic Auth** | 不支持纯 Cookie 方式 |
| **refresh_token 可能更新** | 刷新后建议保存新的 refresh_token |
| **提前刷新** | 建议在过期前 5 分钟刷新，避免业务中断 |
| **存储安全** | refresh_token 应加密存储，不要明文持久化 |

---

## 六、授权 URL 中没有项目参数

**授权 URL 不包含任何项目/空间参数**（如 `project_id`、`workspace_id`）：

- `scope` 是**全局级别**的权限声明
- 换到的 `access_token` 在该用户**所有可见的 TAPD 项目**中通用
- 后续调用具体项目 API 时，在请求参数中单独传入项目 ID

---

## 七、常见问题速查

| 错误提示                                      | 原因                                                  | 解决                                                         |
| --------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------ |
| `invalid scope`                               | 应用权限设置中未勾选对应 scope，或修改后未发布        | 勾选权限 → 点击发布                                          |
| `参数state不能为空`                           | state 参数缺失                                        | 确保 URL 中包含 `state`                                      |
| `redirect_uri mismatch`                       | 回调地址与"安全设置"不一致                            | 一字不差地对齐，包括协议、端口、路径                         |
| `The redirect URI is missing or do not match` | 换 token 时的 `redirect_uri` 与授权 URL 中的不一致    | 两处必须使用相同的 `redirect_uri`                            |
| `The authorization code has expired`          | code 超过 5 分钟未使用                                | 重新生成授权 URL，让用户重新授权                             |
| `invalid_client`                              | client_id 或 client_secret 错误                       | 检查 credential 配置                                         |
| **`basic auth info is required`**             | **Token 接口仅用 Cookie，缺少 Basic Auth**            | **必须添加 `Authorization: Basic {base64(client_id:secret)}` 头** |
| **`No address associated with hostname`**     | **使用了内网域名 `api.tapd.woa.com`（外网无法解析）** | **改用公网域名 `apiv2.tapd.woa.com`，如 `/users/info`、`/tokens/request_token`** |

---

## 八、安全红线

1. **`client_secret` 绝对禁止写入前端代码或 Git 仓库**
2. **Token 相关接口必须在后端完成**（换 token、refresh），前端只负责跳转
3. **`state` 参数必须校验**，防止 CSRF 攻击
4. **不要在公开平台分享含 `access_token` 或 `refresh_token` 的日志**
5. **Cookie 包含用户登录凭证**，存储时需加密，避免明文持久化

---

## 九、快速开始（一键运行）

```bash
# 安装依赖
pip install flask requests

# 运行测试脚本（配置已内置）
python tapd_oauth_demo.py

# 复制终端输出的授权 URL 到浏览器打开
# 点击"同意授权"，页面自动展示 token 结果

# 可切换 Cookie/Client Secret 方式测试：
# 访问 http://localhost:5000/switch
```

---

**文档版本**：v1.1 | **最后更新时间**：2026-06-05 | **新增认证方式对比章节**