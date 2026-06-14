---
id: REQ-20260615-001
feature: TAPD授权与建单
status: 设计中
created: 2026-06-15
updated: 2026-06-15
version: 1
tags: [feat, integration, design, S01]
depends_on: []
author: AI
document_type: design
parent: DESIGN.md
---

# S-01 数据模型设计

> 状态：设计中

---

## ★ 1. 术语

| 术语 | 含义 | 引用 |
|------|------|------|
| `TAPD_WORKSPACE_BINDING` | TAPD 项目关联表，存储 space_id 与 tapd_workspace_id 的映射关系 | — |
| `USER_TAPD_TOKEN` | 用户 TAPD Token 表，存储用户的 access_token 和 refresh_token | — |
| `upsert` | MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法，实现存在则更新、不存在则插入 | — |

> 共享术语见父文档 §4.3 共享术语速查

---

## ★ 2. 现状（AS-IS）

### 2.1 现状描述

当前蓝鲸监控平台与 TAPD 系统完全独立，无数据交互。用户需要在 TAPD 系统中手动操作，无法在监控平台中直接关联 TAPD 项目或查看授权状态。

### 2.2 痛点

- 痛点 1：用户需要在两个系统间切换，操作繁琐
- 痛点 2：无法在监控平台中统一管理 TAPD 授权状态
- 痛点 3：Token 过期后用户需要手动重新授权，体验差

---

## ★ 3. 方案（TO-BE）

### 3.1 方案概述

设计两个核心数据表：`TAPD_WORKSPACE_BINDING` 存储项目关联关系，`USER_TAPD_TOKEN` 存储用户 Token。采用唯一约束保证数据幂等，Token 字段加密存储保障安全。

### 3.2 关键决策点

| 决策 | 选择 | 理由 | 备选方案 | 否决原因 |
|------|------|------|----------|----------|
| Token 存储方式 | MySQL + Redis 双层 | MySQL 持久化，Redis 缓存提升性能 | 仅 MySQL | 高并发时性能不足 |
| Token 加密方案 | Fernet 对称加密 | Django 生态支持，安全性高 | AES-256 | 需要额外依赖，实现复杂 |
| 关联幂等策略 | 唯一约束 + upsert | 数据库层面保证，简单可靠 | 应用层去重 | 并发时可能重复插入 |

### 3.3 行为差异对照表

| 场景 | AS-IS | TO-BE | 影响 |
|------|-------|-------|------|
| 项目关联 | 无关联关系 | 自动关联 TAPD 项目 | 新增功能 |
| Token 存储 | 无 Token 存储 | 加密存储用户 Token | 新增功能 |
| Token 刷新 | 无刷新机制 | 异步刷新 Token | 新增功能 |

---

## ★ 4b. 数据模型

### 4b.1 持久化结构

```python
# Django Model 定义
class TAPDWorkspaceBinding(models.Model):
    """TAPD 项目关联表"""
    space_id = models.IntegerField("蓝鲸业务空间ID")
    bk_biz_id = models.IntegerField("蓝鲸CMDB业务ID")
    tapd_workspace_id = models.CharField("TAPD项目ID", max_length=64)
    tapd_workspace_name = models.CharField("TAPD项目名称", max_length=255)
    creator = models.CharField("创建人username", max_length=128)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    
    class Meta:
        db_table = "tapd_workspace_binding"
        unique_together = [("space_id", "tapd_workspace_id")]
        verbose_name = "TAPD项目关联"
        verbose_name_plural = "TAPD项目关联"

class UserTapdToken(models.Model):
    """用户 TAPD Token 表"""
    username = models.CharField("用户username", max_length=128, unique=True)
    access_token = models.TextField("TAPD用户态token", help_text="加密存储")
    refresh_token = models.TextField("TAPD刷新token", null=True, blank=True, help_text="加密存储")
    token_type = models.CharField("token类型", max_length=32, default="Bearer")
    expires_at = models.DateTimeField("过期时间")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    
    class Meta:
        db_table = "user_tapd_token"
        verbose_name = "用户TAPD Token"
        verbose_name_plural = "用户TAPD Token"
```

### 4b.2 传输/中间结构

```python
# 序列化器定义
class TAPDWorkspaceBindingSerializer(serializers.ModelSerializer):
    """TAPD 项目关联序列化器"""
    class Meta:
        model = TAPDWorkspaceBinding
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class UserTapdTokenSerializer(serializers.ModelSerializer):
    """用户 TAPD Token 序列化器"""
    class Meta:
        model = UserTapdToken
        fields = ["id", "username", "token_type", "expires_at", "created_at", "updated_at"]
        # 不暴露 token 字段
```

---

## +10. 影响范围

| 影响对象 | 影响类型 | 影响描述 | 是否破坏性变更 |
|---------|---------|---------|:----------:|
| 数据库 | 数据变更 | 新增 2 张表 | 否 |
| Django ORM | 接口变更 | 新增 2 个 Model 类 | 否 |
| Migration | 数据变更 | 新增 Migration 文件 | 否 |

---

## +11. 待定问题

| 编号 | 问题 | 影响范围 | 建议决策时间 | 负责人 |
|------|------|---------|------------|--------|
| T-01 | Token 加密算法选型：Fernet vs bkmonitor 现有加密工具 | S-01, S-02, S-07 | 设计阶段 | 后端开发 |
| T-02 | 数据库索引优化策略 | S-01 | 实施阶段 | DBA |
