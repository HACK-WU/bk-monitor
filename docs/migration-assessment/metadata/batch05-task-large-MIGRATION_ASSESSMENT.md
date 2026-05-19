# metadata Task 大文件迁移价值评估报告（批次 5）

> 评估范围：`bkmonitor/metadata/task/` 下 8 个大文件（约 6,237 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `bkbase.py` | 687 | 11/25 | ❌ 不迁移（设计参考） |
| `config_refresh.py` | 630 | 9/25 | ❌ 不迁移 |
| `tasks.py` | 2,266 | 8/25 | ❌ 不迁移 |
| `sync_space.py` | 1,043 | 7/25 | ❌ 不迁移 |
| `bcs.py` | 693 | 7/25 | ❌ 不迁移 |
| `custom_report.py` | 347 | 7/25 | ❌ 不迁移 |
| `datalink.py` | 282 | 7/25 | ❌ 不迁移 |
| `migrate.py` | 289 | 9/25 | ❌ 不迁移 |

**评估结论：8 个文件全部不迁移。** 整个 task 层是蓝鲸监控的核心业务任务调度代码，承担数据源管理、空间同步、集群发现、配置刷新等关键业务职责。业务价值高，但迁移价值低——它们是"业务实现"而非"可复用设计"。

---

## 二、不迁移模块说明

| 文件 | 核心职责 | 不迁移原因 |
|------|---------|-----------|
| `tasks.py` | 40+ 个 Celery 任务（数据源创建、ES 索引、链路状态刷新） | 全部操作 `DataSource`、`ResultTable`、`ESStorage` 等平台私有 Model |
| `sync_space.py` | BKCC/BCS 空间同步、归档业务处理 | 完全依赖 `SpaceTypes.BKCC`、CMDB/BCS 私有 API |
| `bcs.py` | BCS 集群发现、监控信息刷新 | 绑定 `BCSClusterInfo`、`ServiceMonitorInfo` 等 BCS 专属模型 |
| `bkbase.py` | BkBase Redis 监听、集群信息同步 | 虽有设计参考价值，但实现与 BkBase 协议强绑定 |
| `config_refresh.py` | Consul/ES/Kafka/InfluxDB 配置刷新 | 绑定特定存储模型和 Consul 配置中心 |
| `custom_report.py` | 自定义事件/日志配置下发 | 绑定 `EventGroup`/`LogGroup` Model |
| `datalink.py` | 日志/事件组 V4 数据链路创建 | 绑定 `DataLink`/`BkBaseResultTable` Model |
| `migrate.py` | 日志纳秒结果表迁移 | 深拷贝+字段变换，绑定特定表结构 |

---

## 三、设计参考索引

虽然不建议迁移，但以下设计模式值得在其他项目中参考借鉴：

| 模式 | 来源 | 说明 |
|------|------|------|
| **Redis Pub/Sub 监听 + 自动重连** | `bkbase.py` L107-190 | `psubscribe` + 正则过滤 + 单调时钟超时 + ConnectionError 自动重连 |
| **分布式锁 + 看门狗续期** | `bkbase.py` L62-104 | 主线程持有锁 + 守护线程定期续约 + `threading.Event()` 停止信号 |
| **字段映射抽象** | `bkbase.py` L256-396 | `field_mappings` 字典描述字段映射，`_get_attr_by_path()` 支持嵌套路径 |
| **批量操作 + 线程池并行** | 多文件 | `bulk_handle` + `ThreadPoolExecutor` 用于 IO 密集场景 |
| **任务状态指标上报** | 多文件 | 开始/结束计数 + 耗时 histogram + 统一 `report_all()` |
| **记录迁移（深拷贝+字段变换）** | `migrate.py` L68-289 | `deepcopy` ORM 对象 → 置空 pk → 修改字段 → 保存为新记录 |

### 重点关注：Redis Pub/Sub + 锁续期组合

`bkbase.py` 中的 `watch_bkbase_meta_redis_task()` 展示了一个完整的长时任务运行框架：

```
分布式锁 acquire → 启动看门狗线程 renew → Redis psubscribe 监听 → 超时/信号退出 → finally 释放锁和关闭 pubsub
```

该模式适合任何需要"持续监听 + 互斥执行 + 优雅退出"的场景，但实现与 BkBase 协议深度交织，提取成本高于重新实现。

---

## 四、总结

`metadata/task/` 大文件层共 6,237 行代码，全部是蓝鲸监控平台的核心业务任务调度。这些代码：
- 平均每个文件导入 15-25 个 `metadata.models` 子模块
- 强依赖 `settings` 中的 20+ 个私有配置项
- 函数签名全部面向业务场景，无法抽象为通用 Protocol

**建议**：如需沉淀上述设计模式，应以设计文档或代码片段形式保留在设计参考库中，而非作为完整模块迁移到 CodeHub。
