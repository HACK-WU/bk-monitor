---
id: REQ-20260615-001
feature: TAPD授权与建单
status: 设计中
created: 2026-06-15
updated: 2026-06-15
version: 1
tags: [feat, integration, design, S06]
depends_on: [S01]
author: AI
document_type: design
parent: DESIGN.md
---

# S-06 查询授权状态

> 状态：设计中

---

## ★ 1. 术语

| 术语 | 含义 | 引用 |
|------|------|------|
| `auth_status` | 用户 TAPD 授权状态 | — |
| `expires_at` | Token 过期时间 | 见父文档 §4.3 |

---

## ★ 2. 现状（AS-IS）

### 2.1 现状描述

当前蓝鲸监控平台无法查询用户的 TAPD 授权状态。用户需要手动判断是否已授权，无法在页面加载时自动展示授权状态。

### 2.2 痛点

- 痛点 1：用户无法在页面加载时看到授权状态
- 痛点 2：无法自动引导用户完成授权流程
- 痛点 3：Token 过期后用户无感知，导致功能不可用

---

## ★ 3. 方案（TO-BE）

### 3.1 方案概述

实现查询授权状态接口，检查 `USER_TAPD_TOKEN` 表中的记录状态，返回「已授权」、「已过期」或「未授权」三种状态，前端根据状态展示不同的 UI。

### 3.2 关键决策点

| 决策 | 选择 | 理由 | 备选方案 | 否决原因 |
|------|------|------|----------|----------|
| 状态判断逻辑 | 检查记录存在性和过期时间 | 简单直接 | 调用 TAPD API 验证 | 增加网络开销，无必要 |
| 状态返回格式 | 返回状态码和提示信息 | 前端可直接使用 | 返回布尔值 | 信息不足 |

### 3.3 行为差异对照表

| 场景 | AS-IS | TO-BE | 影响 |
|------|-------|-------|------|
| 状态查询 | 无查询功能 | 查询本地数据库 | 新增功能 |
| 状态展示 | 无状态展示 | 自动展示授权状态 | 新增功能 |

---

## ★ 4a. 接口设计

### 4a.1 对外接口

#### 查询用户授权状态

```python
class GetAuthStatusResource(Resource):
    """查询用户授权状态"""
    
    class RequestSerializer(serializers.Serializer):
        username = serializers.CharField(label="用户名")
    
    class ResponseSerializer(serializers.Serializer):
        status = serializers.CharField(label="授权状态")
        message = serializers.CharField(label="提示信息")
        expires_at = serializers.DateTimeField(label="过期时间", required=False)
    
    def perform_request(self, validated_request_data):
        # 1. 查询 USER_TAPD_TOKEN
        # 2. 检查记录状态
        # 3. 返回授权状态
        pass
```

| 接口 | 输入 | 输出 | 异常 |
|------|------|------|------|
| 查询授权状态 | `username` | `status, message, expires_at` | `用户不存在` |

### 4a.2 内部协作接口

| 接口 | 调用方 | 被调用方 | 说明 |
|------|--------|----------|------|
| `get_user_token()` | 查询授权状态 | 数据库操作 | 获取用户 Token |

### 4a.3 契约变更声明

| 变更类型 | 接口 | 变更内容 | 影响的子需求 |
|---------|------|---------|------------|
| 新增 | 查询授权状态 | 全新接口 | S-02 |

---

## +6. 异常处理

| 场景 | 行为 | 是否对外暴露 |
|------|------|:----------:|
| 用户不存在 | 返回「未授权」状态 | 否 |
| 数据库查询异常 | 记录错误日志，返回「未授权」状态 | 否 |

---

## +10. 影响范围

| 影响对象 | 影响类型 | 影响描述 | 是否破坏性变更 |
|---------|---------|---------|:----------:|
| `fta_web/issue/` | 接口变更 | 新增 1 个 Resource | 否 |
| `urls.py` | 接口变更 | 新增 1 个 URL 路由 | 否 |
| 前端页面 | 行为变更 | 新增授权状态展示 | 否 |
