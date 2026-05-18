# alarm_backends/service/selfmonitor + nodata 迁移价值评估报告

> 评估范围：`bkmonitor/alarm_backends/service/selfmonitor/`（8 文件）+ `bkmonitor/alarm_backends/service/nodata/`（7 文件）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）
> 迁移目标：PythonCodeHub — 可复用、低耦合、易参考的通用 Python 代码

---

## 一、selfmonitor 总览

| 文件 | 总分 | 结论 |
|------|------|------|
| `log/rotate.py` | **23/25** | ✅ 强烈推荐迁移 |
| `log/processor.py` | 15/25 | ⚠️ 有条件迁移（需参数化配置） |
| `handler.py` | 13/25 | ❌ 不迁移 |
| `collect/redis.py` | 12/25 | ❌ 不迁移 |
| `collect/transfer.py` | 11/25 | ❌ 不迁移 |
| 3 个空 `__init__.py` | — | 跳过 |

---

## 二、迁移目标：时间+大小双条件日志轮转器

**源文件：** `alarm_backends/service/selfmonitor/log/rotate.py`

**总分：23/25** — 零外部依赖，完全通用的日志轮转工具类

### 2.1 核心设计

```python
class TimeAndSizeRotateFile:
    """时间+大小双条件日志轮转"""

    def handle(self):
        """统一入口：should_rollover → do_rollover → cleanup"""

    def should_rollover(self) -> bool:
        """午夜到达或文件超过 max_bytes 时触发"""

    def do_rollover(self):
        """轮转 + gzip 压缩归档"""

    def get_files_to_delete(self) -> list:
        """按 backup_count 控制保留数量，清理过期文件"""
```

核心特性：
- **双条件触发**：午夜到达（时间轮转）或文件超过 `max_bytes`（大小轮转）
- **gzip 压缩**：归档文件自动压缩，命名格式 `{filename}.{YYYY-MM-DD}.{序号}.gz`
- **自动清理**：`get_files_to_delete` 按 `backup_count` 控制保留数量
- **完整生命周期**：`should_rollover → do_rollover → cleanup`

### 2.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 日志轮转是所有服务的通用需求 |
| **复用价值** | 5/5 | 任何 Python 服务的日志管理均可直接使用 |
| **独立性** | 5/5 | 零外部依赖，仅使用 Python 标准库（os, re, time, gzip, glob） |
| **接口稳定性** | 4/5 | `handle()` 统一入口，各阶段方法职责清晰 |
| **代码质量** | 4/5 | 设计简洁，注释详尽；`six.moves.range` 需移除 |

### 2.3 业务耦合清单

**无业务耦合。** 这是整个 selfmonitor 模块中最干净的文件。

### 2.4 迁移范围

- 整个 `TimeAndSizeRotateFile` 类可直接平移
- 仅需移除 `six.moves.range` 导入（Python 3 直接用 `range`）
- 预估工作量：0.5h

### 2.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| Web 服务日志管理 | Nginx/Apache 风格的日志轮转 |
| 后台任务日志 | Celery/自定义 worker 的日志管理 |
| 日志采集系统 | 日志文件产生 + 自动归档 |
| 容器化部署 | 容器内日志的本地轮转 |
| 审计日志 | 按时间分片存储审计日志 |

---

## 三、有条件迁移目标

### 3.1 日志轮转处理器（`log/processor.py`，15/25）

**核心设计：** 信号处理（SIGTERM/SIGINT）实现优雅退出 + 通配符扫描日志文件 + 轮转处理器管理。

**需解耦：**
- `settings.LOG_PATH` → 构造函数参数
- `settings.LOG_LOGFILE_MAXSIZE` / `BACKUP_COUNT` / `BACKUP_GZIP` → 构造函数参数
- 固定的文件模式 `kernel*.log` → 可配置参数

**迁移说明：** 参数化后评分可提升至 18-19 分。核心的"信号驱动 + 轮转循环"模式有一定复用价值。

---

## 四、不迁移模块说明（selfmonitor）

| 文件 | 不迁移原因 | 可参考设计 |
|------|-----------|-----------|
| `handler.py` | 仅 13 行的薄分发层，`SELF_MONITOR_TO_CLASS_MAP` 模式过简单 | — |
| `collect/redis.py` | 深度耦合 `CacheNode`、Redis key、Prometheus metrics | Redis 指标采集模式 |
| `collect/transfer.py` | 深度耦合 Consul、Django ORM、自定义上报工具 | — |

---

## 五、nodata 总览

| 文件 | 总分 | 结论 |
|------|------|------|
| `__init__.py` | — | 空文件，跳过 |
| `scenarios/__init__.py` | — | 空文件，跳过 |
| `handler.py` | 9/25 | ❌ 不迁移 |
| `processor.py` | 11/25 | ❌ 不迁移 |
| `scenarios/base.py` | 10/25 | ❌ 不迁移 |
| `scenarios/filters.py` | 12/25 | ❌ 不迁移 |
| `tasks.py` | 10/25 | ❌ 不迁移 |

**评估结论：没有文件达到迁移门槛（≥15 分）。**

### 不迁移模块说明

| 文件 | 不迁移原因 | 可参考设计 |
|------|-----------|-----------|
| `handler.py` | 分布式领导者选举 + 定时触发，深度绑定 Redis 锁、策略缓存、集群路由 | Redis SET NX 领导者竞争 |
| `processor.py` | 继承 `BaseAbnormalPushProcessor`，依赖 Strategy/Item/DataPoint 等 6+ 内部模块 | "未来数据回退"的时间窗口机制 |
| `scenarios/base.py` | `@register_scenario` 场景注册模式设计合理，但强依赖 CMDB 模型 | 场景注册 + 动态加载模式 |
| `scenarios/filters.py` | 继承自 access 模块的 RangeFilter，46 行，绑定策略体系 | — |
| `tasks.py` | 标准 Celery 任务包装 + Prometheus 指标 | — |

---

## 六、迁移优先级汇总

| 优先级 | 文件 | 模块 | 总分 | 工作量 |
|--------|------|------|------|--------|
| **P0** | `log/rotate.py` | selfmonitor | 23/25 | 0.5h |
| **P2** | `log/processor.py` | selfmonitor | 15/25 | 2h（参数化后） |
