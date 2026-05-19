# log_databus 视图层迁移价值评估报告（批次 10）

> 评估范围：`log_databus/views/`（10 个文件，约 5,653 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `collector_views.py` | 2,576 | 7/25 | ❌ 不迁移 |
| `storage_views.py` | 852 | 7/25 | ❌ 不迁移 |
| `clean_views.py` | 556 | 7/25 | ❌ 不迁移 |
| `collector_plugin_views.py` | 534 | 7/25 | ❌ 不迁移 |
| `archive_views.py` | 355 | 7/25 | ❌ 不迁移 |
| `link_views.py` | 257 | 7/25 | ❌ 不迁移 |
| `restore_views.py` | 250 | 7/25 | ❌ 不迁移 |
| `itsm_views.py` | 183 | 7/25 | ❌ 不迁移 |
| `check_collector_views.py` | 120 | 7/25 | ❌ 不迁移 |
| `log_access_views.py` | 120 | 7/25 | ❌ 不迁移 |

**评估结论：全部 10 个 views 文件均不迁移，统一评分 7/25。**

---

## 二、不迁移原因

所有 views 文件均为标准 Django REST Framework ViewSet 路由层，呈现统一模式：

```
参数校验 → 调用 Handler → 返回 Response
```

| 维度 | 评分 | 说明 |
|------|------|------|
| **通用性** | 1/5 | 深度绑定 log_databus 业务域 |
| **复用价值** | 1/5 | 无跨项目复用场景 |
| **独立性** | 1/5 | 依赖具体 Model、Serializer、Handler、IAM Action |
| **接口稳定性** | 2/5 | API 接口由业务需求驱动，遵循 RESTful 约定 |
| **代码质量** | 2/5 | 结构清晰一致，但均为标准 CRUD 写法 |

---

## 三、设计参考索引

| 模式 | 来源 | 参考价值 |
|------|------|----------|
| FlowMixin 统一响应格式 | `apps/generic.py`（已在批次 2 评估） | 中 |
| ValidationMixin 参数校验 | `apps/generic.py`（已在批次 2 评估） | 中 |
| Action-Permission 声明式映射 | 所有 views 的 `get_permissions()` | 低 |
| Handler 委托模式 | 所有 views | 中（良好分层实践） |

真正的可迁移设计在 Handler 层、Utils 层和基础设施层，视图层天然不具备高迁移价值。
