# metadata Task 小文件迁移价值评估报告（批次 4）

> 评估范围：`bkmonitor/metadata/task/` 下 11 个小文件（约 1,840 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `utils.py` | 44 | **24/25** | ✅ 强烈推荐迁移 |
| `constants.py` | 82 | 16/25 | ❌ 不迁移 |
| `entity_relation.py` | 103 | 12/25 | ❌ 不迁移 |
| `auto_deploy_proxy.py` | 230 | 10/25 | ❌ 不迁移 |
| `vm.py` | 121 | 10/25 | ❌ 不迁移 |
| `ping_server.py` | 205 | 9/25 | ❌ 不迁移 |
| `refresh_default_rp.py` | 45 | 9/25 | ❌ 不迁移 |
| `record_rule_v4.py` | 37 | 9/25 | ❌ 不迁移 |
| `refresh_data_link.py` | 36 | 8/25 | ❌ 不迁移 |
| `tenant.py` | 210 | 8/25 | ❌ 不迁移 |
| `sync_cmdb_relation.py` | 192 | 8/25 | ❌ 不迁移 |

---

## 二、迁移目标：多线程批量处理器（24/25）

**源文件：** `metadata/task/utils.py`

### 核心设计

两个纯函数工具，零外部依赖：

```python
def bulk_handle(handler, data, bulk_size, is_wait_finish=True):
    """多线程批量处理器：将大数据列表按 bulk_size 分组，每组启动一个线程执行"""
    ...

def chunk_list(data, size):
    """列表等分切块器：将列表按固定大小切分为子列表"""
    ...
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 完全通用，不依赖任何业务逻辑 |
| **复用价值** | 5/5 | 批量 API 调用、批量数据写入、批量通知等场景均可使用 |
| **独立性** | 5/5 | 零外部依赖，仅使用标准库 `threading` |
| **接口稳定性** | 5/5 | 接口极简，参数类型清晰 |
| **代码质量** | 4/5 | 结构清晰、有类型注解；缺少并发数限制和异常传播机制 |

### 迁移范围

整文件直接迁移（44 行）。建议增加 `max_workers` 参数、异常收集机制。

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 批量 API 调用 | 并发调用外部 API（CMDB、节点管理等） |
| 批量数据写入 | 数据库批量写入、ES 批量索引 |
| 流式分片 | 大数据集分批处理 |

---

## 三、不迁移模块说明

| 文件 | 总分 | 不迁移原因 | 可参考设计 |
|------|------|-----------|-----------|
| `constants.py` | 16 | BKBase V4 链路 Kind-Storage 映射配置，业务绑定 | 结构化映射表模式 |
| `entity_relation.py` | 12 | 依赖 entity_relation Django Model + Redis | DB-Redis 差集清理模式 |
| `auto_deploy_proxy.py` | 10 | 依赖 api.node_man + api.cmdb | 版本比对+差异部署 |
| `vm.py` | 10 | 依赖多个 Django Model | — |
| `ping_server.py` | 9 | 依赖 CMDB + HashRing + 节点管理 API | 一致性哈希分片分配 |
| 其余 5 个文件 | 8-9 | 深度业务耦合 | — |

---

## 四、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| DB-Redis 差集清理 | `entity_relation.py` | 缓存兜底刷新 |
| Kind-Storage 结构化映射表 | `constants.py` | 配置驱动的数据同步 |
| 版本比对+差异部署 | `auto_deploy_proxy.py` | 插件自动升级 |
| Redis-DB 双写+Token 校验 | `sync_cmdb_relation.py` | 缓存一致性维护 |
| 一致性哈希分片分配 | `ping_server.py` | 分布式任务分片 |
