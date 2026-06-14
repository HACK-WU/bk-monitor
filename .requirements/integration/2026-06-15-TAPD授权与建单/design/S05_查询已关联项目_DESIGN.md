---
id: REQ-20260615-001
feature: TAPD授权与建单
status: 设计中
created: 2026-06-15
updated: 2026-06-15
version: 1
tags: [feat, integration, design, S05]
depends_on: [S01, S03]
author: AI
document_type: design
parent: DESIGN.md
---

# S-05 查询已关联项目

> 状态：设计中

---

## ★ 1. 术语

| 术语 | 含义 | 引用 |
|------|------|------|
| `tapd_workspace_id` | TAPD 项目 ID | 见父文档 §4.3 |
| `tapd_workspace_name` | TAPD 项目名称 | 见父文档 §4.3 |

---

## ★ 2. 现状（AS-IS）

### 2.1 现状描述

当前蓝鲸监控平台无法查询已关联的 TAPD 项目。用户需要手动记录哪些项目已关联，容易出现遗漏或重复关联。

### 2.2 痛点

- 痛点 1：无法在监控平台中查看已关联的 TAPD 项目
- 痛点 2：用户需要手动记录关联关系，容易出错
- 痛点 3：无法批量管理关联关系

---

## ★ 3. 方案（TO-BE）

### 3.1 方案概述

实现 B-02 接口，直接查询 `TAPD_WORKSPACE_BINDING` 表，返回指定业务空间下已关联的 TAPD 项目列表。

### 3.2 关键决策点

| 决策 | 选择 | 理由 | 备选方案 | 否决原因 |
|------|------|------|----------|----------|
| 查询方式 | 直接查数据库 | 简单高效，数据量小 | 调用 TAPD API | 无必要，数据已在本地 |
| 返回字段 | 包含关联信息 | 满足前端展示需求 | 仅返回项目 ID | 信息不足 |

### 3.3 行为差异对照表

| 场景 | AS-IS | TO-BE | 影响 |
|------|-------|-------|------|
| 关联查询 | 无查询功能 | 查询本地数据库 | 新增功能 |
| 关联管理 | 无管理功能 | 可查看关联详情 | 新增功能 |

---

## ★ 4a. 接口设计

### 4a.1 对外接口

#### B-02 查询已关联 TAPD 项目列表

```python
class ListBoundTapdProjectsResource(Resource):
    """查询已关联 TAPD 项目列表"""
    
    class RequestSerializer(serializers.Serializer):
        space_id = serializers.IntegerField(label="业务空间ID")
    
    class ResponseSerializer(serializers.Serializer):
        total = serializers.IntegerField(label="项目总数")
        items = serializers.ListField(label="项目列表")
    
    def perform_request(self, validated_request_data):
        # 1. 按 space_id 查询 TAPD_WORKSPACE_BINDING
        # 2. 返回已关联 TAPD 项目列表
        pass
```

| 接口 | 输入 | 输出 | 异常 |
|------|------|------|------|
| B-02 查询已关联项目 | `space_id` | `total, items` | `空间不存在` |

### 4a.2 内部协作接口

| 接口 | 调用方 | 被调用方 | 说明 |
|------|--------|----------|------|
| `get_bound_projects()` | B-02 | 数据库操作 | 查询已关联项目 |

### 4a.3 契约变更声明

| 变更类型 | 接口 | 变更内容 | 影响的子需求 |
|---------|------|---------|------------|
| 新增 | B-02 查询已关联项目 | 全新接口 | — |

---

## +6. 异常处理

| 场景 | 行为 | 是否对外暴露 |
|------|------|:----------:|
| 空间不存在 | 返回错误提示 | 是 |
| 无已关联项目 | 返回空列表 | 否 |

---

## +10. 影响范围

| 影响对象 | 影响类型 | 影响描述 | 是否破坏性变更 |
|---------|---------|---------|:----------:|
| `fta_web/issue/` | 接口变更 | 新增 1 个 Resource | 否 |
| `urls.py` | 接口变更 | 新增 1 个 URL 路由 | 否 |
| 前端页面 | 行为变更 | 新增已关联项目展示 | 否 |
