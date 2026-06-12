# TAPD OAuth 接入文档

> 原文档地址: https://o.tapd.woa.com/document/api-doc/API%E6%96%87%E6%A1%A3/TAPD%20OAuth%20%E6%8E%A5%E5%85%A5%E6%96%87%E6%A1%A3/

## 概述

TAPD 新开放平台（https://o.tapd.woa.com/）支持多人管理、项目管理员自助授权、各种类型挂载点、应用市场等，能满足大部分接入到 TAPD 和调用 TAPD API 接口的需要。

在某些场景中，比如平台级系统，需要在这些系统中发起 TAPD OAuth 授权，授权完成后又跳转回这些系统中。这时候，就需要使用 **TAPD OAuth 跳转模式**。

---

## 一、创建开放平台应用

1. 在 TAPD 创建好应用；
2. 根据应用所需要接口配置好应用权限；
3. 在应用管理首页获取到：
   - **应用 ID（client_id）**
   - **应用密钥（client_secret）**

---

## 二、OAuth 对接过程

### 1. 配置 OAuth 跳转链接

在开放平台应用 **"安全配置"** 的 **"三方应用数据授权"** 中添加回调 URL 白名单，**可以添加多个**。

> ⚠️ **注意**：回调 URL **不能包含 `#`**

---

### 2. 拼接 OAuth 跳转 URL

#### 格式

```
https://tapd.woa.com/oauth/open_app_install?test=1&show_installed=0&client_id=%s&cb=%s&state=%s
```

#### 参数说明

| 参数             | 类型     | 必需 | 说明 |
|------------------|----------|------|------|
| `client_id`      | `string` | 是   | 应用 ID（在应用管理首页获取） |
| `cb`             | `string` | 是   | 回跳 URL，**必须在步骤 1 配置的白名单中** |
| `state`          | `string` | 是   | 透传参数。授权完成后，会原样带到回跳 URL 上 |
| `test`           | `integer`| 否   | 是否测试应用。应用未上架前取 `1`，上架后改成 `0` |
| `show_installed` | `integer`| 否   | 是否显示已授权过的项目。默认不显示，取 `1` 会显示 |

#### 示例

```
https://tapd.woa.com/oauth/open_app_install?test=1&client_id=oauth_demo&cb=http%3A%2F%2Flion.oa.com%2F~anyechen%2Fcode%2Fphp%2Foauth_demo%2Fhey.php&show_installed=1&state=demo-product123
```

---

### 3. 浏览器打开拼接好的 URL

用户会在浏览器中看到 TAPD 的项目选择授权页面。

---

### 4. 用户选项目，点击"下一步"

用户选择需要授权的项目。

---

### 5. 授权完成并跳转

授权完成后，会跳转到上面配置的跳转 URL，并携带以下参数：

- `code` — 授权码
- `resource` — 授权的项目信息（包含 `workspace_id`）
- `state` — 原样回传的透传参数

#### 示例回调 URL

```
http://lion.oa.com/~anyechen/code/php/oauth_demo/hey.php?code=4f9b2fab25a7c69715d426295a66717769666a0c&state=demo-product123&resource=%7B%22type%22%3A%22workspace%22%2C%22workspace_id%22%3A%2269990779%22%7D
```

#### 解析后的参数

```
Array
(
    [code] => 4f9b2fab25a7c69715d426295a66717769666a0c
    [state] => demo-product123
    [resource] => {"type":"workspace","workspace_id":"69990779"}
)
```

**注意：**
- 返回的 `resource` 会带上这次授权的项目 ID（`workspace_id`）

---

### 6. 通过 Basic Auth 使用 API 访问对应项目的数据

获取到授权码 `code` 和项目信息 `resource` 后，即可通过 **Basic Auth** 方式调用 TAPD API 接口访问对应项目的数据。

**示例：**

```bash
curl -u 'client_id:client_secret' \
  'http://apiv2.tapd.woa.com/bugs/count?workspace_id=69990779'
```

---

## 流程总结

```
┌─────────────────┐
│ 1. 创建开放平台应用 │
│   (获取 client_id   │
│    和 client_secret)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 配置 OAuth   │
│   回调 URL 白名单  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 拼接授权 URL │
│   引导用户访问    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 用户选择项目  │
│   点击授权       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. 跳转回应用   │
│   携带 code +   │
│   workspace_id  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. 调用 TAPD    │
│   API 获取数据   │
└─────────────────┘
```
