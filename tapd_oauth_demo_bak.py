#!/usr/bin/env python3
"""
TAPD 用户态 OAuth 2.0 测试
=========================
功能：
1. 启动时打印授权 URL（复制到浏览器打开即可）
2. /callback 接收 TAPD 回调，自动换 token + 获取用户信息
3. 自动测试 OAuth/Basic Auth 两种方式的"获取已授权项目"接口
4. /granted_workspaces_basic 独立测试 Basic Auth 方式
5. /granted_workspaces_oauth 独立测试 OAuth Access Token 方式

用法：
    python tapd_oauth_demo.py
    # 复制终端输出的授权 URL 到浏览器打开，登录 TAPD 并同意授权
    # 浏览器将自动回调到 /callback，页面直接展示 token 和用户信息

前置检查：
    [ ] TAPD 应用 client_id 和 secret 与下方配置一致
    [ ] 安全设置中的 redirect_uri 为 http://localhost:5000/callback（一字不差）
    [ ] 权限设置中已勾选对应 scope 且已发布
    [ ] 浏览器已登录 TAPD
"""

import sys
import json
import base64
import secrets
import urllib.parse

import requests
from flask import Flask, request

# ============================================================
# 配置区（直接写死）
# ============================================================
CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDIRECT_URI = "http://localhost:5000/callback"
SCOPE = "story#read story#write bug#read"

AUTH_URL = "https://tapd.example.com/oauth/"
TOKEN_URL = "http://apiv2.tapd.example.com/tokens/request_token"
REFRESH_TOKEN_URL = "http://apiv2.tapd.example.com/tokens/refresh_token"
USER_INFO_URL = "http://apiv2.tapd.example.com/users/info"
# 获取应用已授权项目接口（支持 OAuth / Basic Auth 两种方式）
GRANTED_WORKSPACES_URL = "http://apiv2.tapd.example.com/app_auth/get_granted_workspaces"
# ============================================================

app = Flask(__name__)

# 全局变量：保存最新获取的 token，用于后续测试 refresh
_last_token_data = {
    "access_token": None,
    "refresh_token": None,
}

# 授权方式配置：可选 "client_secret" 或 "cookie"
AUTH_METHOD = "client_secret"  # 默认使用 client_secret
TAPD_COOKIE = ""  # 填入 TAPD cookie（从浏览器复制）


def _generate_auth_url():
    """生成授权 URL。注意：scope 需要提前 urlencode（# → %23）"""
    state = secrets.token_urlsafe(16)
    # 用户可能直接传了已编码的 scope（如 story%23read），也可能是未编码的
    scope_value = urllib.parse.unquote(SCOPE)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": scope_value,
        "state": state,
        "auth_by": "user",
    }
    query = urllib.parse.urlencode(params)
    return f"{AUTH_URL}?{query}", state


def _exchange_token(code):
    """code → access_token

    注意：TAPD 的 /tokens/request_token 接口强制要求 Basic Auth，
    Cookie 方式只能作为补充，不能替代 Basic Auth。
    """
    try:
        # 必须使用 Basic Auth（TAPD 强制要求）
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        auth = base64.b64encode(credentials.encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        # 如果是 cookie 方式，额外添加 Cookie header
        if AUTH_METHOD == "cookie" and TAPD_COOKIE:
            headers["Cookie"] = TAPD_COOKIE

        data = {"grant_type": "authorization_code", "redirect_uri": REDIRECT_URI, "code": code}

        resp = requests.post(TOKEN_URL, headers=headers, data=data, timeout=15)
        return resp.json(), AUTH_METHOD  # 返回实际使用的授权方式
    except Exception as e:
        return {"_error": str(e)}, AUTH_METHOD


def _get_user_info(token):
    """access_token → 用户信息"""
    try:
        resp = requests.get(f"{USER_INFO_URL}?access_token={token}", timeout=15)
        return resp.json()
    except Exception as e:
        return {"_error": str(e)}


def _get_granted_workspaces_oauth(token):
    """用 OAuth Access Token (Bearer) 获取应用已授权项目

    文档：http://apiv2.tapd.example.com/app_auth/get_granted_workspaces
    鉴权：Authorization: Bearer <access_token>
    """
    try:
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(GRANTED_WORKSPACES_URL, headers=headers, timeout=15)
        return resp.json()
    except Exception as e:
        return {"_error": str(e)}


def _get_granted_workspaces_basic():
    """用 Basic Auth 获取应用已授权项目（对照组）

    文档：http://apiv2.tapd.example.com/app_auth/get_granted_workspaces
    鉴权：Authorization: Basic base64(client_id:client_secret)
    """
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        auth = base64.b64encode(credentials.encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        resp = requests.get(GRANTED_WORKSPACES_URL, headers=headers, timeout=15)
        return resp.json()
    except Exception as e:
        return {"_error": str(e)}


def _refresh_access_token(refresh_token):
    """用 refresh_token 换取新的 access_token

    注意：TAPD 的 token 接口强制要求 Basic Auth，
    Cookie 只能作为补充。
    """
    try:
        # 必须使用 Basic Auth（TAPD 强制要求）
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        auth = base64.b64encode(credentials.encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        # 如果是 cookie 方式，额外添加 Cookie header
        if AUTH_METHOD == "cookie" and TAPD_COOKIE:
            headers["Cookie"] = TAPD_COOKIE

        data = {"grant_type": "refresh_token", "refresh_token": refresh_token}

        resp = requests.post(REFRESH_TOKEN_URL, headers=headers, data=data, timeout=15)
        return resp.json()
    except Exception as e:
        return {"_error": str(e)}


@app.route("/")
def index():
    """备用：直接访问 / 可以查看授权 URL（如果忘记复制终端输出了）"""
    url, state = _generate_auth_url()

    # 当前授权方式状态
    auth_status = "Cookie" if AUTH_METHOD == "cookie" else "Client Secret"
    cookie_status = "已设置" if TAPD_COOKIE else "未设置"

    return f"""
    <h2>TAPD OAuth 测试</h2>
    <p>当前授权方式：<b>{auth_status}</b> | Cookie 状态：<b>{cookie_status}</b></p>
    <p><a href="/switch">🔄 切换授权方式</a></p>
    <hr>
    <p>state: <code>{state}</code></p>
    <p><a href="{url}">👉 点击授权</a></p>
    <hr>
    <p>或复制到浏览器打开：</p>
    <input type="text" value="{url}" style="width:90%" readonly onclick="this.select()">
    """


@app.route("/switch")
def switch_auth():
    """切换授权方式：client_secret ↔ cookie"""
    global AUTH_METHOD, TAPD_COOKIE

    if AUTH_METHOD == "client_secret":
        # 切换到 Cookie 方式
        AUTH_METHOD = "cookie"
        # 提示用户设置 Cookie
        return """
        <h2>已切换到 Cookie 方式</h2>
        <p>请在下方粘贴 TAPD Cookie：</p>
        <form method="POST" action="/set_cookie">
            <textarea name="cookie" rows="5" style="width:90%" placeholder="从浏览器复制完整的 Cookie 字符串"></textarea>
            <br><br>
            <button type="submit" style="padding:10px 20px;background:#1890ff;color:white;border:none;border-radius:4px;cursor:pointer;">保存 Cookie</button>
        </form>
        <p><a href="/">返回首页</a></p>
        """
    else:
        # 切换到 Client Secret 方式
        AUTH_METHOD = "client_secret"
        return """
        <h2>已切换到 Client Secret 方式</h2>
        <p>将使用 CLIENT_SECRET 进行授权</p>
        <p><a href="/">返回首页</a></p>
        """


@app.route("/set_cookie", methods=["POST"])
def set_cookie():
    """设置 TAPD Cookie"""
    global TAPD_COOKIE
    TAPD_COOKIE = request.form.get("cookie", "").strip()
    return f"""
    <h2>Cookie 已保存</h2>
    <pre>{TAPD_COOKIE[:100]}{"..." if len(TAPD_COOKIE) > 100 else ""}</pre>
    <p><a href="/">返回首页</a> | <a href="/test_cookie">测试 Cookie</a></p>
    """


@app.route("/test_cookie")
def test_cookie():
    """测试 Cookie 是否有效"""
    if not TAPD_COOKIE:
        return "<h2>未设置 Cookie</h2><p><a href='/switch'>去设置</a></p>"

    # 尝试用 Cookie 调用用户信息接口
    try:
        resp = requests.get(USER_INFO_URL, headers={"Cookie": TAPD_COOKIE}, timeout=15)
        result = resp.json()
        return f"""
        <h2>Cookie 测试结果</h2>
        <pre>{json.dumps(result, indent=2, ensure_ascii=False)}</pre>
        <p><a href="/">返回首页</a></p>
        """
    except Exception as e:
        return f"<h2>测试失败</h2><pre>{e}</pre>"


@app.route("/callback")
def callback():
    """接收 TAPD 回调，执行换 token、获取用户信息"""
    code = request.args.get("code")
    state = request.args.get("state")
    print(request)
    resource = request.args.get("resource")

    parts = ["<h1>TAPD OAuth 回调结果</h1><hr>"]

    if not code:
        parts.append("<p style='color:red'>❌ 未收到 code</p>")
        parts.append(f"<pre>args: {dict(request.args)}</pre>")
        return "\n".join(parts)

    parts.append("<h2>1. 回调参数</h2>")
    parts.append(f"<pre>code:     {code}\nstate:    {state}\nresource: {resource}</pre>")

    # 1. 换 token
    parts.append("<h2>2. 换取 access_token</h2>")
    parts.append(f"<pre>当前授权方式: {AUTH_METHOD}</pre>")
    token_resp, used_method = _exchange_token(code)
    parts.append(f"<pre>实际请求方式: {used_method} (Basic Auth + Cookie if set)</pre>")
    parts.append(f"<pre>{json.dumps(token_resp, indent=2, ensure_ascii=False)}</pre>")

    if token_resp.get("status") != 1 or "data" not in token_resp:
        parts.append("<p style='color:red'>❌ 换 token 失败</p>")
        parts.append("<p>可能原因：code 过期、redirect_uri 不一致、client_secret 错误、权限未发布</p>")
        return "\n".join(parts)

    data = token_resp["data"]
    token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires = data.get("expires_in")

    # 保存到全局变量，供后续 refresh 测试
    global _last_token_data
    _last_token_data["access_token"] = token
    _last_token_data["refresh_token"] = refresh_token

    parts.append("<h2>3. Token 信息</h2>")
    parts.append(f"<pre>access_token:   {token}</pre>")
    parts.append(f"<pre>refresh_token:  {refresh_token}</pre>")
    parts.append(f"<pre>expires:        {expires} 秒（≈ {expires // 3600}h）</pre>")
    parts.append(f"<pre>scope:          {data.get('scope')}</pre>")
    parts.append(f"<pre>resource:       {json.dumps(data.get('resource'), ensure_ascii=False)}</pre>")

    # 2. 获取用户信息
    parts.append("<h2>4. 获取用户信息</h2>")
    user_resp = _get_user_info(token)
    parts.append(f"<pre>{json.dumps(user_resp, indent=2, ensure_ascii=False)}</pre>")

    # 3. 用 OAuth Bearer Token 方式获取已授权项目
    parts.append("<h2>5. 获取已授权项目（OAuth Bearer Token 方式）</h2>")
    parts.append("<pre>Authorization: Bearer access_token</pre>")
    gw_oauth_resp = _get_granted_workspaces_oauth(token)
    parts.append(f"<pre>{json.dumps(gw_oauth_resp, indent=2, ensure_ascii=False)}</pre>")

    # 4. 用 Basic Auth (client_id:client_secret) 方式获取已授权项目（对照）
    parts.append("<h2>6. 获取已授权项目（Basic Auth 方式，对照）</h2>")
    parts.append("<pre>Authorization: Basic base64(client_id:client_secret)</pre>")
    gw_basic_resp = _get_granted_workspaces_basic()
    parts.append(f"<pre>{json.dumps(gw_basic_resp, indent=2, ensure_ascii=False)}</pre>")

    # 对比总结
    parts.append("<h2>7. 两种鉴权方式结果对比</h2>")
    if gw_oauth_resp.get("status") == 1 and gw_basic_resp.get("status") == 1:
        oauth_count = gw_oauth_resp.get("data", {}).get("pager", {}).get("count", "N/A")
        basic_count = gw_basic_resp.get("data", {}).get("pager", {}).get("count", "N/A")
        parts.append(f"<pre>OAuth Bearer 方式：授权项目数 = {oauth_count}")
        parts.append(f"Basic Auth 方式：  授权项目数 = {basic_count}")
        if oauth_count == basic_count:
            parts.append("✅ 两种方式结果一致</pre>")
        else:
            parts.append("⚠️ 两种方式结果不一致（可能跟 OAuth scope 有关）</pre>")
    else:
        parts.append("<pre>OAuth 方式 status: " + str(gw_oauth_resp.get("status")))
        parts.append("Basic 方式 status:  " + str(gw_basic_resp.get("status")) + "</pre>")

    # 独立路由入口
    parts.append("<hr><h2>🔗 独立接口测试</h2>")
    parts.append(
        "<p><a href='/granted_workspaces_oauth' style='display:inline-block;padding:8px 16px;background:#1890ff;color:white;text-decoration:none;border-radius:4px;margin-right:8px;'>OAuth 方式</a>"
    )
    parts.append(
        "<a href='/granted_workspaces_basic' style='display:inline-block;padding:8px 16px;background:#52c41a;color:white;text-decoration:none;border-radius:4px;'>Basic Auth 方式</a></p>"
    )

    # 结论
    parts.append("<hr><h2>🎯 结论</h2>")
    if token:
        parts.append("<p style='color:green'>✅ TAPD 用户态 OAuth 可用！Token 有效期 2h。</p>")

    # Refresh Token 测试入口
    parts.append("<hr><h2>🔄 Refresh Token 验证</h2>")
    if refresh_token:
        parts.append("<p>已保存 refresh_token，点击下方按钮验证 refresh_token 是否可用：</p>")
        parts.append(
            "<p><a href='/refresh' style='display:inline-block;padding:10px 20px;background:#1890ff;color:white;text-decoration:none;border-radius:4px;'>🔄 点击验证 Refresh Token</a></p>"
        )
        parts.append(f"<pre>refresh_token: {refresh_token}</pre>")
    else:
        parts.append("<p style='color:orange'>⚠️ 未返回 refresh_token，TAPD 可能不支持 refresh 模式</p>")

    return "\n".join(parts)


@app.route("/refresh")
def refresh():
    """测试 Refresh Token 功能"""
    refresh_token = _last_token_data.get("refresh_token")
    old_access_token = _last_token_data.get("access_token")

    parts = ["<h1>Refresh Token 验证结果</h1><hr>"]

    if not refresh_token:
        parts.append("<p style='color:red'>❌ 未保存 refresh_token，请先完成授权</p>")
        parts.append("<p><a href='/'>返回首页重新授权</a></p>")
        return "\n".join(parts)

    parts.append("<h2>1. 当前保存的 Token</h2>")
    parts.append(f"<pre>access_token:   {old_access_token}</pre>")
    parts.append(f"<pre>refresh_token:  {refresh_token}</pre>")

    # 调用 refresh 接口
    parts.append("<h2>2. 调用 Refresh Token 接口</h2>")
    parts.append(f"<pre>POST {REFRESH_TOKEN_URL}</pre>")
    parts.append(f"<pre>grant_type=refresh_token&refresh_token={refresh_token}</pre>")

    refresh_resp = _refresh_access_token(refresh_token)
    parts.append("<h2>3. Refresh 返回结果</h2>")
    parts.append(f"<pre>{json.dumps(refresh_resp, indent=2, ensure_ascii=False)}</pre>")

    if refresh_resp.get("status") == 1 and "data" in refresh_resp:
        new_data = refresh_resp["data"]
        new_token = new_data.get("access_token")
        new_refresh = new_data.get("refresh_token")
        new_expires = new_data.get("expires_in")

        parts.append("<h2>4. 新 Token 信息</h2>")
        parts.append(f"<pre>new_access_token:   {new_token}</pre>")
        parts.append(f"<pre>new_refresh_token:  {new_refresh}</pre>")
        parts.append(f"<pre>expires:            {new_expires} 秒</pre>")

        # 更新全局变量
        _last_token_data["access_token"] = new_token
        _last_token_data["refresh_token"] = new_refresh or refresh_token

        # 验证新 token 是否可用
        parts.append("<h2>5. 验证新 Token 可用性</h2>")
        user_resp = _get_user_info(new_token)
        parts.append(f"<pre>{json.dumps(user_resp, indent=2, ensure_ascii=False)}</pre>")

        if user_resp.get("status") == 1 or (isinstance(user_resp, list) and len(user_resp) > 0):
            parts.append("<p style='color:green'>✅ Refresh Token 功能验证成功！新 token 可正常使用。</p>")
        else:
            parts.append("<p style='color:orange'>⚠️ Refresh 成功，但新 token 获取用户信息失败</p>")

        # 可以继续刷新测试
        parts.append("<hr><p>可以继续点击验证（使用新的 refresh_token）：</p>")
        parts.append(
            "<p><a href='/refresh' style='display:inline-block;padding:10px 20px;background:#52c41a;color:white;text-decoration:none;border-radius:4px;'>🔄 再次 Refresh</a></p>"
        )
    else:
        parts.append("<p style='color:red'>❌ Refresh Token 失败</p>")
        parts.append("<p>可能原因：</p>")
        parts.append("<ul>")
        parts.append("<li>TAPD 不支持 refresh_token 模式</li>")
        parts.append("<li>refresh_token 已过期或失效</li>")
        parts.append("<li>grant_type 参数错误</li>")
        parts.append("</ul>")

    parts.append("<hr><p><a href='/'>返回首页</a> | <a href='/callback'>查看上次回调结果</a></p>")
    return "\n".join(parts)


@app.route("/granted_workspaces_oauth")
def granted_workspaces_oauth():
    """独立测试：用 OAuth Bearer Token 获取已授权项目"""
    token = _last_token_data.get("access_token")
    parts = ["<h1>获取已授权项目 - OAuth Bearer Token 方式</h1><hr>"]

    if not token:
        parts.append("<p style='color:red'>❌ 未保存 access_token，请先完成授权</p>")
        parts.append("<p><a href='/'>返回首页授权</a></p>")
        return "\n".join(parts)

    parts.append("<h2>1. 请求信息</h2>")
    parts.append(f"<pre>GET {GRANTED_WORKSPACES_URL}")
    parts.append(f"Authorization: Bearer {token[:40]}...</pre>")

    resp = _get_granted_workspaces_oauth(token)
    parts.append("<h2>2. 返回结果</h2>")
    parts.append(f"<pre>{json.dumps(resp, indent=2, ensure_ascii=False)}</pre>")

    if resp.get("status") == 1 and "data" in resp:
        count = resp["data"].get("pager", {}).get("count", 0)
        items = resp["data"].get("list", [])
        parts.append("<h2>3. 结果摘要</h2>")
        parts.append(f"<p>授权项目数：<b>{count}</b></p>")
        parts.append("<table border='1' style='border-collapse:collapse;width:80%'>")
        parts.append(
            "<tr style='background:#f0f0f0'><th>序号</th><th>workspace_id</th><th>type</th><th>created</th></tr>"
        )
        for i, item in enumerate(items, start=1):
            app_info = item.get("OpenOrganizationApp", {})
            parts.append(f"<tr><td>{i}</td><td>{app_info.get('workspace_id', 'N/A')}</td>")
            parts.append(f"<td>{app_info.get('type', 'N/A')}</td><td>{app_info.get('created', 'N/A')}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p style='color:red'>❌ 获取失败</p>")

    parts.append("<hr><p><a href='/'>返回首页</a> | <a href='/granted_workspaces_basic'>切换 Basic Auth 方式</a></p>")
    return "\n".join(parts)


@app.route("/granted_workspaces_basic")
def granted_workspaces_basic():
    """独立测试：用 Basic Auth 获取已授权项目"""
    parts = ["<h1>获取已授权项目 - Basic Auth 方式</h1><hr>"]

    parts.append("<h2>1. 请求信息</h2>")
    parts.append(f"<pre>GET {GRANTED_WORKSPACES_URL}")
    parts.append(f"Authorization: Basic base64({CLIENT_ID}:{'*' * len(CLIENT_SECRET)})</pre>")

    resp = _get_granted_workspaces_basic()
    parts.append("<h2>2. 返回结果</h2>")
    parts.append(f"<pre>{json.dumps(resp, indent=2, ensure_ascii=False)}</pre>")

    if resp.get("status") == 1 and "data" in resp:
        count = resp["data"].get("pager", {}).get("count", 0)
        items = resp["data"].get("list", [])
        parts.append("<h2>3. 结果摘要</h2>")
        parts.append(f"<p>授权项目数：<b>{count}</b></p>")
        parts.append("<table border='1' style='border-collapse:collapse;width:80%'>")
        parts.append(
            "<tr style='background:#f0f0f0'><th>序号</th><th>workspace_id</th><th>type</th><th>created</th></tr>"
        )
        for i, item in enumerate(items, start=1):
            app_info = item.get("OpenOrganizationApp", {})
            parts.append(f"<tr><td>{i}</td><td>{app_info.get('workspace_id', 'N/A')}</td>")
            parts.append(f"<td>{app_info.get('type', 'N/A')}</td><td>{app_info.get('created', 'N/A')}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p style='color:red'>❌ 获取失败</p>")

    parts.append("<hr><p><a href='/'>返回首页</a> | <a href='/granted_workspaces_oauth'>切换 OAuth 方式</a></p>")
    return "\n".join(parts)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    url, state = _generate_auth_url()
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           TAPD 用户态 OAuth 测试服务器已启动                 ║
╚══════════════════════════════════════════════════════════════╝

📋 配置信息：
   client_id:    {CLIENT_ID}
   redirect_uri: {REDIRECT_URI}
   scope:        {SCOPE}

🔗 授权 URL（复制到浏览器打开，已登录 TAPD 状态下自动弹出授权页面）：

   {url}

📝 state: {state}

⚠️  如果浏览器回调 localhost 失败，直接从地址栏复制整个回调链接
    在浏览器继续访问即可。

服务器地址: http://localhost:5000
    """)
    app.run(host="0.0.0.0", port=5000)
