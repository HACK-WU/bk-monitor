# Issues 功能技术实现文档

> 版本：v1.0  
> 最后更新：2026-02-02  
> 作者：蓝鲸监控平台开发团队

---

## 目录

1. [功能概述](#1-功能概述)
2. [技术架构设计](#2-技术架构设计)
3. [数据模型设计](#3-数据模型设计)
4. [API 接口定义](#4-api-接口定义)
5. [详细实现步骤](#5-详细实现步骤)
6. [测试要点](#6-测试要点)
7. [风险评估与应对](#7-风险评估与应对)

---

## 1. 功能概述

### 1.1 功能定位

Issues 功能是蓝鲸监控平台的**告警/故障跟踪管理模块**，旨在解决告警或故障产生后无法进行人工后续跟踪的问题。

**核心价值**：
- 告警恢复 ≠ 问题解决：即使告警已恢复，仍可能需要负责人继续跟进处理
- 提供完整的问题追踪能力，直到问题**真正被解决**

### 1.2 功能范围

| 功能模块 | 描述 |
|---------|------|
| Issue 生成 | 支持告警策略配置聚合方式生成 Issue |
| Issue 状态管理 | 待审核 → 未解决 → 已解决状态流转 |
| Issue 列表 | Issue 查询、筛选、排序、分页 |
| Issue 详情 | 趋势统计、维度分布、告警事件、活动记录 |
| 批量操作 | 批量指派、标记解决、修改优先级 |
| 历史追溯 | 回归问题检测、历史 Issue 关联 |
| 外部系统集成 | ITSM/TAPD/GitHub Issues 1对多关联 |

### 1.3 技术栈

| 组件 | 技术选型 | 用途 |
|------|---------|------|
| 后端框架 | Django 4.2 + DRF | API 服务 |
| 主数据存储 | MySQL 8.0 | Issue 主表、活动记录 |
| 搜索引擎 | Elasticsearch 7.x | Issue 检索、聚合统计 |
| 缓存 | Redis 6.x | Issue 快照、分布式锁 |
| 异步任务 | Celery 5.x | Issue 创建、通知推送 |

---

## 2. 技术架构设计

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Issues 系统架构                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │   Web Gateway   │  ← HTTP API 接入                                       │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        应用层                                    │        │
│  │  ┌─────────────────────┐    ┌─────────────────────┐            │        │
│  │  │  fta_web.issue      │    │ alarm_backends      │            │        │
│  │  │  API Resource       │    │ .service.issue      │            │        │
│  │  └──────────┬──────────┘    └──────────┬──────────┘            │        │
│  │             │                          │                        │        │
│  └─────────────┼──────────────────────────┼────────────────────────┘        │
│                │                          │                                 │
│                ▼                          ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        处理层                                    │        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │        │
│  │  │IssueQuery    │  │IssueBuilder  │  │IssueState    │          │        │
│  │  │Handler       │  │              │  │Machine       │          │        │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │        │
│  │         │                 │                 │                   │        │
│  └─────────┼─────────────────┼─────────────────┼───────────────────┘        │
│            │                 │                 │                            │
│            ▼                 ▼                 ▼                            │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        数据层                                    │        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │        │
│  │  │   MySQL      │  │Elasticsearch │  │    Redis     │          │        │
│  │  │ Issue Model  │  │IssueDocument │  │ Issue Cache  │          │        │
│  │  └──────────────┘  └──────────────┘  └──────────────┘          │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        告警系统                                  │        │
│  │  AlertBuilder → Signal → create_issue Task                      │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流向图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Issue 创建数据流                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  告警系统                                                                    │
│      │                                                                      │
│      ▼                                                                      │
│  AlertBuilder.send_signal()                                                 │
│      │                                                                      │
│      ▼                                                                      │
│  ┌─────────────────────────────────────────┐                                │
│  │ Celery Task: create_or_update_issue     │                                │
│  └─────────────────┬───────────────────────┘                                │
│                    │                                                        │
│                    ▼                                                        │
│  ┌─────────────────────────────────────────┐                                │
│  │ IssueBuilder                            │                                │
│  │   1. 计算 dedupe_md5 (聚合指纹)          │                                │
│  │   2. 获取分布式锁                        │                                │
│  │   3. 查询缓存/数据库                     │                                │
│  │   4. 创建或更新 Issue                    │                                │
│  │   5. 检测回归问题                        │                                │
│  └─────────────────┬───────────────────────┘                                │
│                    │                                                        │
│       ┌────────────┼────────────┐                                           │
│       ▼            ▼            ▼                                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                      │
│  │  MySQL  │  │   ES    │  │  Redis  │                                      │
│  │ 主数据  │  │ 索引    │  │ 缓存    │                                      │
│  └─────────┘  └─────────┘  └─────────┘                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 模块划分

```
bkmonitor/
├── bkmonitor/
│   ├── documents/
│   │   └── issue.py                    # [NEW] Issue ES 文档模型
│   └── models/
│       └── fta/
│           └── issue.py                # [NEW] Issue MySQL 模型
│
├── constants/
│   └── issue.py                        # [NEW] Issue 常量定义
│
├── packages/
│   └── fta_web/
│       └── issue/                      # [NEW] Issue Web 模块
│           ├── __init__.py
│           ├── resources.py            # API Resource
│           ├── serializers.py          # 序列化器
│           ├── urls.py                 # URL 路由
│           ├── views.py                # ViewSet
│           └── handlers/
│               ├── issue.py            # 查询处理器
│               ├── builder.py          # 构建处理器
│               └── state_machine.py    # 状态机
│
└── alarm_backends/
    └── service/
        └── issue/                      # [NEW] Issue 后台服务
            ├── processor.py            # Issue 处理器
            └── tasks/
                └── create_issue.py     # Celery 任务
```

---

## 3. 数据模型设计

### 3.1 MySQL 模型

#### 3.1.1 Issue 主表

```python
# bkmonitor/models/fta/issue.py

from django.db import models
from bkmonitor.utils.model_manager import AbstractRecordModel


class IssueStatus:
    """Issue 状态枚举"""
    PENDING_REVIEW = "pending_review"  # 待审核
    UNRESOLVED = "unresolved"          # 未解决
    RESOLVED = "resolved"              # 已解决


class IssuePriority:
    """Issue 优先级枚举"""
    HIGH = "high"      # 高
    MEDIUM = "medium"  # 中
    LOW = "low"        # 低


class Issue(AbstractRecordModel):
    """Issue 主模型"""
    
    # ===== 基础信息 =====
    id = models.BigAutoField(primary_key=True, verbose_name="Issue ID")
    bk_biz_id = models.IntegerField(verbose_name="业务ID", db_index=True)
    name = models.CharField(verbose_name="Issue名称", max_length=256)
    description = models.TextField(verbose_name="问题描述", blank=True, default="")
    
    # ===== 状态管理 =====
    status = models.CharField(
        verbose_name="状态", max_length=32,
        choices=[
            (IssueStatus.PENDING_REVIEW, "待审核"),
            (IssueStatus.UNRESOLVED, "未解决"),
            (IssueStatus.RESOLVED, "已解决"),
        ],
        default=IssueStatus.PENDING_REVIEW,
        db_index=True
    )
    priority = models.CharField(
        verbose_name="优先级", max_length=16,
        choices=[
            (IssuePriority.HIGH, "高"),
            (IssuePriority.MEDIUM, "中"),
            (IssuePriority.LOW, "低"),
        ],
        default=IssuePriority.MEDIUM
    )
    
    # ===== 责任人体系 =====
    assignee = models.CharField(verbose_name="负责人", max_length=64, blank=True, default="")
    followers = models.JSONField(verbose_name="关注人列表", default=list)
    
    # ===== 聚合信息 =====
    strategy_id = models.IntegerField(verbose_name="关联策略ID", db_index=True, null=True)
    dedupe_md5 = models.CharField(verbose_name="聚合指纹", max_length=64, db_index=True, unique=True)
    aggregation_dimensions = models.JSONField(verbose_name="聚合维度配置", default=list)
    
    # ===== 时间信息 =====
    first_occur_time = models.DateTimeField(verbose_name="首次发生时间")
    last_occur_time = models.DateTimeField(verbose_name="最后发生时间")
    resolved_time = models.DateTimeField(verbose_name="解决时间", null=True, blank=True)
    
    # ===== 统计信息 =====
    alert_count = models.IntegerField(verbose_name="告警事件数量", default=0)
    impact_scope = models.JSONField(verbose_name="影响范围", default=dict)
    
    # ===== 问题类型 =====
    is_regression = models.BooleanField(verbose_name="是否回归问题", default=False)
    related_issue_id = models.BigIntegerField(verbose_name="关联历史Issue ID", null=True, blank=True)
    
    # ===== 标签与扩展 =====
    labels = models.JSONField(verbose_name="标签列表", default=list)
    extra_info = models.JSONField(verbose_name="扩展信息", default=dict)
    
    class Meta:
        db_table = "fta_issue"
        verbose_name = "Issue"
        ordering = ["-last_occur_time"]
        indexes = [
            models.Index(fields=["bk_biz_id", "status"]),
            models.Index(fields=["bk_biz_id", "strategy_id"]),
            models.Index(fields=["assignee"]),
        ]
```

#### 3.1.2 Issue 活动记录表

```python
class IssueActivityType:
    """活动类型枚举"""
    CREATE = "create"                    # 创建
    STATUS_CHANGE = "status_change"      # 状态变更
    PRIORITY_CHANGE = "priority_change"  # 优先级变更
    ASSIGN = "assign"                    # 指派负责人
    COMMENT = "comment"                  # 添加评论
    ALERT_ADD = "alert_add"              # 新增告警
    EXTERNAL_LINK = "external_link"      # 关联外部系统


class IssueActivity(AbstractRecordModel):
    """Issue 活动记录"""
    
    id = models.BigAutoField(primary_key=True)
    issue_id = models.BigIntegerField(verbose_name="Issue ID", db_index=True)
    
    activity_type = models.CharField(verbose_name="活动类型", max_length=32, db_index=True)
    operator = models.CharField(verbose_name="操作人", max_length=64)
    content = models.TextField(verbose_name="活动内容")
    
    old_value = models.CharField(verbose_name="原值", max_length=64, blank=True, default="")
    new_value = models.CharField(verbose_name="新值", max_length=64, blank=True, default="")
    extra_info = models.JSONField(verbose_name="扩展信息", default=dict)
    
    class Meta:
        db_table = "fta_issue_activity"
        ordering = ["-create_time"]
```

#### 3.1.3 Issue-告警关联表

```python
class IssueAlertRelation(models.Model):
    """Issue-告警关联表"""
    
    id = models.BigAutoField(primary_key=True)
    issue_id = models.BigIntegerField(verbose_name="Issue ID", db_index=True)
    alert_id = models.CharField(verbose_name="告警ID", max_length=64, db_index=True)
    create_time = models.DateTimeField(verbose_name="关联时间", auto_now_add=True)
    
    class Meta:
        db_table = "fta_issue_alert_relation"
        unique_together = [("issue_id", "alert_id")]
```

#### 3.1.4 Issue-外部系统关联表

```python
class IssueExternalRelation(AbstractRecordModel):
    """Issue-外部系统关联表"""
    
    id = models.BigAutoField(primary_key=True)
    issue_id = models.BigIntegerField(verbose_name="Issue ID", db_index=True)
    
    system_type = models.CharField(verbose_name="外部系统类型", max_length=32)  # itsm/tapd/github
    external_id = models.CharField(verbose_name="外部系统ID", max_length=128)
    external_url = models.URLField(verbose_name="外部系统链接", max_length=512, blank=True)
    external_status = models.CharField(verbose_name="外部系统状态", max_length=64, blank=True)
    extra_info = models.JSONField(verbose_name="扩展信息", default=dict)
    
    class Meta:
        db_table = "fta_issue_external_relation"
```

### 3.2 Elasticsearch 文档模型

```python
# bkmonitor/documents/issue.py

from django_elasticsearch_dsl.registries import registry
from elasticsearch_dsl import InnerDoc, Search, field

from bkmonitor.documents.base import BaseDocument, Date
from bkmonitor.documents.constants import ES_INDEX_SETTINGS


@registry.register_document
class IssueDocument(BaseDocument):
    """Issue ES 文档模型"""
    
    REINDEX_ENABLED = True
    REINDEX_QUERY = Search().exclude("term", status="resolved").to_dict()
    
    # 唯一标识
    id = field.Keyword(required=True)
    bk_biz_id = field.Keyword()
    bk_tenant_id = field.Keyword()
    
    # 基础信息
    name = field.Text(fields={"raw": field.Keyword()})
    description = field.Text()
    
    # 状态信息
    status = field.Keyword()
    priority = field.Keyword()
    assignee = field.Keyword()
    followers = field.Keyword(multi=True)
    
    # 聚合信息
    strategy_id = field.Keyword()
    dedupe_md5 = field.Keyword()
    
    # 时间体系
    create_time = Date(format=BaseDocument.DATE_FORMAT)
    update_time = Date(format=BaseDocument.DATE_FORMAT)
    first_occur_time = Date(format=BaseDocument.DATE_FORMAT)
    last_occur_time = Date(format=BaseDocument.DATE_FORMAT)
    resolved_time = Date(format=BaseDocument.DATE_FORMAT)
    
    # 统计信息
    alert_count = field.Long()
    impact_scope = field.Object(enabled=False)
    
    # 问题类型
    is_regression = field.Boolean()
    related_issue_id = field.Keyword()
    labels = field.Keyword(multi=True)
    
    # 维度信息
    class Dimension(InnerDoc):
        key = field.Keyword()
        value = field.Keyword()
        display_key = field.Keyword()
        display_value = field.Keyword()
    
    dimensions = field.Object(enabled=False, multi=True, doc_class=Dimension)
    extra_info = field.Object(enabled=False)
    
    class Index:
        name = "bkfta_issue"
        settings = ES_INDEX_SETTINGS.copy()
    
    def get_index_time(self):
        return self.parse_timestamp_by_id(str(self.id))
    
    @classmethod
    def parse_timestamp_by_id(cls, issue_id: str) -> int:
        try:
            return int(str(issue_id)[:10])
        except (ValueError, TypeError):
            return 0
```

### 3.3 Redis 缓存 Key 定义

```python
# alarm_backends/core/cache/key.py 新增

ISSUE_CONTENT_KEY = register_key_with_config({
    "label": "[issue] Issue 内容缓存",
    "key_type": "string",
    "key_tpl": "issue.builder.{strategy_id}.{dedupe_md5}.content",
    "ttl": CONST_ONE_DAY,  # 24 小时
    "backend": "service",
})

ISSUE_SNAPSHOT_KEY = register_key_with_config({
    "label": "[issue] Issue 快照缓存",
    "key_type": "string",
    "key_tpl": "issue.builder.snapshot.{issue_id}",
    "ttl": CONST_MINUTES * 30,  # 30 分钟
    "backend": "service",
})

ISSUE_UPDATE_LOCK = register_key_with_config({
    "label": "[issue] Issue 更新分布式锁",
    "key_type": "string",
    "key_tpl": "issue.builder.lock.{dedupe_md5}",
    "ttl": CONST_MINUTES,  # 1 分钟
    "backend": "service",
})
```

### 3.4 常量定义

```python
# constants/issue.py

from enum import Enum
from django.utils.translation import gettext_lazy as _


class IssueStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    UNRESOLVED = "unresolved"
    RESOLVED = "resolved"


class IssuePriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


ISSUE_STATUS_DICT = {
    IssueStatus.PENDING_REVIEW: _("待审核"),
    IssueStatus.UNRESOLVED: _("未解决"),
    IssueStatus.RESOLVED: _("已解决"),
}

ISSUE_PRIORITY_DICT = {
    IssuePriority.HIGH: _("高"),
    IssuePriority.MEDIUM: _("中"),
    IssuePriority.LOW: _("低"),
}

# 状态流转配置
ISSUE_STATUS_TRANSITIONS = {
    IssueStatus.PENDING_REVIEW: [IssueStatus.UNRESOLVED],
    IssueStatus.UNRESOLVED: [IssueStatus.RESOLVED],
    IssueStatus.RESOLVED: [],  # 终态
}

# 回归问题检测回溯天数
REGRESSION_LOOKBACK_DAYS = 30
```

---

## 4. API 接口定义

### 4.1 接口总览

| 接口名称 | 方法 | 路径 | 说明 |
|---------|------|------|------|
| Issue 列表 | POST | `/api/v1/issue/list/` | 分页查询 Issue 列表 |
| Issue 详情 | GET | `/api/v1/issue/{id}/` | 获取 Issue 详情 |
| Issue 更新 | PUT | `/api/v1/issue/{id}/` | 更新 Issue |
| Issue 批量操作 | POST | `/api/v1/issue/batch_operate/` | 批量操作 |
| Issue 活动记录 | GET | `/api/v1/issue/{id}/activities/` | 获取活动记录 |
| Issue 添加评论 | POST | `/api/v1/issue/{id}/comment/` | 添加跟进评论 |
| Issue 关联告警 | GET | `/api/v1/issue/{id}/alerts/` | 获取关联告警 |
| Issue 趋势统计 | GET | `/api/v1/issue/{id}/trend/` | 获取趋势数据 |
| Issue 维度统计 | GET | `/api/v1/issue/{id}/dimensions/` | 获取维度分布 |
| Issue 导出 | POST | `/api/v1/issue/export/` | 导出数据 |

### 4.2 Issue 列表查询

**请求**

```json
POST /api/v1/issue/list/
{
    "bk_biz_ids": [2, 3],
    "status": ["pending_review", "unresolved"],
    "priority": ["high", "medium"],
    "assignee": "admin",
    "query_string": "磁盘使用率",
    "start_time": 1706745600,
    "end_time": 1706832000,
    "ordering": "-last_occur_time",
    "page": 1,
    "page_size": 20
}
```

**响应**

```json
{
    "result": true,
    "code": 0,
    "data": {
        "total": 156,
        "items": [
            {
                "id": "17067456001234",
                "name": "磁盘使用率告警",
                "status": "unresolved",
                "status_display": "未解决",
                "priority": "high",
                "priority_display": "高",
                "assignee": "admin",
                "strategy_id": 100,
                "strategy_name": "磁盘使用率监控",
                "alert_count": 25,
                "first_occur_time": 1706745600,
                "last_occur_time": 1706831900,
                "is_regression": true,
                "labels": ["infrastructure"],
                "impact_scope": {"hosts": 5}
            }
        ]
    }
}
```

### 4.3 Issue 详情

**响应**

```json
{
    "result": true,
    "code": 0,
    "data": {
        "id": "17067456001234",
        "name": "磁盘使用率告警",
        "description": "多台主机磁盘使用率超过 90%",
        "status": "unresolved",
        "priority": "high",
        "assignee": "admin",
        "followers": ["user1", "user2"],
        "strategy_id": 100,
        "aggregation_dimensions": [
            {"key": "bk_cloud_id", "display_key": "云区域ID"},
            {"key": "ip", "display_key": "IP"}
        ],
        "alert_count": 25,
        "first_occur_time": 1706745600,
        "last_occur_time": 1706831900,
        "is_regression": true,
        "related_issue": {
            "id": "17057456001100",
            "name": "磁盘使用率告警",
            "resolved_time": 1706400000
        },
        "external_relations": [
            {
                "system_type": "tapd",
                "external_id": "BUG-12345",
                "external_url": "https://tapd.cn/xxx/BUG-12345"
            }
        ]
    }
}
```

### 4.4 Issue 更新

**请求**

```json
PUT /api/v1/issue/17067456001234/
{
    "status": "resolved",
    "priority": "high",
    "assignee": "user1",
    "comment": "问题已解决，磁盘已扩容"
}
```

### 4.5 Issue 批量操作

**请求**

```json
POST /api/v1/issue/batch_operate/
{
    "issue_ids": ["17067456001234", "17067456001235"],
    "operate_type": "assign",
    "operate_value": "admin",
    "comment": "批量指派给运维团队"
}
```

---

## 5. 详细实现步骤

### 5.1 Issue 创建流程

#### 5.1.1 核心流程

```
1. AlertBuilder 发送告警信号
       ↓
2. Celery Task: create_or_update_issue
       ↓
3. IssueBuilder 初始化
       ↓
4. 计算聚合指纹 (dedupe_md5)
       ↓
5. 获取分布式锁
       ↓
6. 查询缓存/数据库
       ↓
7. 创建或更新 Issue
       ↓
8. 检测回归问题
       ↓
9. 持久化 (MySQL + ES + Redis)
```

#### 5.1.2 Celery 任务

```python
# alarm_backends/service/issue/tasks/create_issue.py

@shared_task(ignore_result=True, queue="celery_issue")
def create_or_update_issue(alert_ids: list[str], strategy_id: int):
    """创建或更新 Issue 的 Celery 任务"""
    from fta_web.issue.handlers.builder import IssueBuilder
    
    if not alert_ids:
        return
    
    # 1. 获取告警文档
    alerts = AlertDocument.mget(alert_ids)
    
    # 2. 构建 IssueBuilder
    builder = IssueBuilder(alerts=alerts, strategy_id=strategy_id)
    
    # 3. 计算聚合指纹
    dedupe_md5 = builder.calculate_dedupe_md5()
    
    # 4. 获取分布式锁
    lock_key = ISSUE_UPDATE_LOCK.get_key(dedupe_md5=dedupe_md5)
    
    with multi_service_lock(ISSUE_UPDATE_LOCK, [lock_key]) as lock:
        if not lock.is_locked(lock_key):
            # 延迟重试
            create_or_update_issue.apply_async(
                kwargs={"alert_ids": alert_ids, "strategy_id": strategy_id},
                countdown=5
            )
            return
        
        # 5. 查找或创建 Issue
        issue = builder.find_or_create_issue()
        
        # 6. 更新统计
        builder.update_issue_statistics(issue)
        
        # 7. 持久化
        builder.save(issue)
```

#### 5.1.3 IssueBuilder 核心方法

```python
# packages/fta_web/issue/handlers/builder.py

class IssueBuilder:
    """Issue 构建器"""
    
    def __init__(self, alerts: list[AlertDocument], strategy_id: int):
        self.alerts = alerts
        self.strategy_id = strategy_id
        self.strategy_config = self._load_strategy_config()
    
    def calculate_dedupe_md5(self) -> str:
        """计算聚合指纹"""
        issue_config = self.strategy_config.get("notice", {}).get("issue_config", {})
        aggregation_dimensions = issue_config.get("aggregation_dimensions", [])
        
        if not aggregation_dimensions:
            return count_md5([self.strategy_id])
        
        alert = self.alerts[0]
        dimension_values = []
        dimensions_dict = {d.get("key"): d.get("value") for d in (alert.dimensions or [])}
        
        for dim_key in aggregation_dimensions:
            dimension_values.append(dimensions_dict.get(dim_key, ""))
        
        return count_md5([self.strategy_id] + dimension_values)
    
    def find_or_create_issue(self) -> Issue:
        """查找或创建 Issue"""
        dedupe_md5 = self.calculate_dedupe_md5()
        
        # 1. 尝试从缓存获取
        issue = self._get_from_cache(dedupe_md5)
        if issue:
            return issue
        
        # 2. 查询数据库
        try:
            issue = Issue.objects.get(
                dedupe_md5=dedupe_md5,
                status__in=[IssueStatus.PENDING_REVIEW, IssueStatus.UNRESOLVED]
            )
            return issue
        except Issue.DoesNotExist:
            pass
        
        # 3. 创建新 Issue
        return self._create_new_issue(dedupe_md5)
    
    def detect_regression(self, dedupe_md5: str) -> tuple[bool, int | None]:
        """检测回归问题"""
        lookback_date = timezone.now() - timezone.timedelta(days=REGRESSION_LOOKBACK_DAYS)
        
        historical_issue = Issue.objects.filter(
            dedupe_md5=dedupe_md5,
            status=IssueStatus.RESOLVED,
            resolved_time__gte=lookback_date
        ).order_by("-resolved_time").first()
        
        if historical_issue:
            return True, historical_issue.id
        return False, None
```

### 5.2 状态流转机制

#### 5.2.1 状态机实现

```python
# packages/fta_web/issue/handlers/state_machine.py

class IssueStateMachine:
    """Issue 状态机"""
    
    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """检查状态是否可转换"""
        allowed = ISSUE_STATUS_TRANSITIONS.get(from_status, [])
        return to_status in allowed
    
    @classmethod
    def transition(cls, issue: Issue, to_status: str, operator: str, comment: str = None) -> bool:
        """执行状态转换"""
        if not cls.can_transition(issue.status, to_status):
            raise ValueError(f"Invalid transition: {issue.status} -> {to_status}")
        
        old_status = issue.status
        issue.status = to_status
        
        if to_status == IssueStatus.RESOLVED:
            issue.resolved_time = timezone.now()
        
        issue.save()
        
        # 记录活动
        IssueActivity.objects.create(
            issue_id=issue.id,
            activity_type=IssueActivityType.STATUS_CHANGE,
            operator=operator,
            content=f"状态从「{old_status}」变更为「{to_status}」",
            old_value=old_status,
            new_value=to_status
        )
        
        return True
    
    @classmethod
    def auto_transition_on_assign(cls, issue: Issue, operator: str):
        """指派负责人时自动流转：待审核 -> 未解决"""
        if issue.status == IssueStatus.PENDING_REVIEW:
            cls.transition(issue, IssueStatus.UNRESOLVED, operator)
```

#### 5.2.2 状态流转图

```
┌─────────────────────────────────────────────────────────────────┐
│                     Issue 状态流转图                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                       ┌──────────────┐                          │
│                       │   [创建]      │                          │
│                       └──────┬───────┘                          │
│                              │                                  │
│                              ▼                                  │
│                       ┌──────────────┐                          │
│                       │   待审核      │ ← 初始状态，负责人为空    │
│                       │ PENDING_REVIEW│                          │
│                       └──────┬───────┘                          │
│                              │                                  │
│                              │ 指派负责人                        │
│                              ▼                                  │
│                       ┌──────────────┐                          │
│             ┌────────▶│   未解决      │◀────────┐               │
│             │         │  UNRESOLVED  │         │               │
│             │         └──────┬───────┘         │               │
│             │                │                 │               │
│    变更负责人/优先级          │ 标记为已解决    添加评论          │
│             │                │                 │               │
│             └────────────────┴─────────────────┘               │
│                              │                                  │
│                              ▼                                  │
│                       ┌──────────────┐                          │
│                       │   已解决      │ ← 终态，记录解决时间      │
│                       │   RESOLVED   │                          │
│                       └──────────────┘                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 测试要点

### 6.1 单元测试

| 测试模块 | 测试内容 | 优先级 |
|---------|---------|-------|
| IssueBuilder | 聚合指纹计算 | P0 |
| IssueBuilder | Issue 创建 | P0 |
| IssueBuilder | 回归问题检测 | P0 |
| IssueStateMachine | 状态流转合法性 | P0 |
| IssueStateMachine | 自动状态流转 | P1 |
| IssueQueryHandler | 列表查询 | P1 |
| IssueQueryHandler | 详情查询 | P1 |

### 6.2 集成测试

| 测试场景 | 测试内容 | 优先级 |
|---------|---------|-------|
| Issue 创建 | 告警触发 → Issue 创建 → 数据持久化 | P0 |
| Issue 更新 | 新告警 → 更新统计 → 缓存同步 | P0 |
| 回归检测 | 历史 Issue 存在 → 标记回归 | P1 |
| 批量操作 | 批量指派 → 状态流转 | P1 |

### 6.3 性能测试

| 测试项 | 指标 | 目标值 |
|-------|------|-------|
| Issue 列表查询 | 响应时间 | < 200ms |
| Issue 创建 | 吞吐量 | > 1000/min |
| 批量操作 | 响应时间 | < 500ms (100条) |

---

## 7. 风险评估与应对

### 7.1 技术风险

| 风险项 | 风险等级 | 影响 | 应对措施 |
|-------|---------|------|---------|
| ES 索引性能 | 中 | 大量 Issue 时查询变慢 | 按月分片，优化查询条件 |
| 分布式锁超时 | 中 | 并发创建重复 Issue | 增加锁续期，延迟重试 |
| MySQL 热点 | 低 | dedupe_md5 索引争用 | 合理的索引设计 |
| 缓存一致性 | 中 | 数据不一致 | 双写策略，定期同步 |

### 7.2 业务风险

| 风险项 | 风险等级 | 影响 | 应对措施 |
|-------|---------|------|---------|
| 回归检测误判 | 低 | 误标记回归问题 | 可配置回溯天数 |
| 状态流转混乱 | 中 | 业务流程异常 | 状态机强约束 |
| 外部系统集成失败 | 低 | 关联数据缺失 | 异步重试，降级处理 |

### 7.3 应对策略

1. **灰度发布**：先在测试环境验证，再逐步推广
2. **功能开关**：通过配置开关控制 Issue 功能启用
3. **监控告警**：对 Issue 创建/查询性能进行监控
4. **数据备份**：定期备份 Issue 数据

---

## 附录 A：数据库迁移检查清单

- [ ] 创建 `fta_issue` 表
- [ ] 创建 `fta_issue_activity` 表
- [ ] 创建 `fta_issue_alert_relation` 表
- [ ] 创建 `fta_issue_external_relation` 表
- [ ] 创建必要的索引
- [ ] ES 创建 `bkfta_issue` 索引模板

## 附录 B：配置项

| 配置项 | 默认值 | 说明 |
|-------|-------|------|
| `ISSUE_ENABLED` | False | Issue 功能开关 |
| `ISSUE_REGRESSION_LOOKBACK_DAYS` | 30 | 回归检测回溯天数 |
| `ISSUE_CACHE_TTL` | 86400 | Issue 缓存 TTL (秒) |

## 附录 C：相关文档

- [Issues 功能说明文档](./issues_feature_guide.md)
- [AlertBuilder 源码](../alarm_backends/service/alert/builder/processor.py)
- [AlertDocument 源码](../bkmonitor/documents/alert.py)
