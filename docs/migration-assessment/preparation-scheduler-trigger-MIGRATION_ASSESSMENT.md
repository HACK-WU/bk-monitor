# alarm_backends/service/preparation + scheduler + trigger 迁移价值评估报告

> 评估范围：`bkmonitor/alarm_backends/service/preparation/`（5 文件）+ `scheduler/`（6 文件）+ `trigger/`（4 文件）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）
> 迁移目标：PythonCodeHub — 可复用、低耦合、易参考的通用 Python 代码

---

## 一、总览

| 模块 | 文件 | 总分 | 结论 |
|------|------|------|------|
| scheduler | `tasks/__init__.py`（perform_sharding_task） | **23/25** | ✅ 强烈推荐迁移 |
| preparation | `base.py` | **20/25** | ✅ 强烈推荐迁移 |
| scheduler | `tasks/cron.py`（task_duration 装饰器） | 16/25 | ⚠️ 有条件迁移 |
| scheduler | `app.py` | 12/25 | ❌ 不迁移 |
| scheduler | `tasks/api_cron.py` | 12/25 | ❌ 不迁移 |
| preparation | `aiops/processor.py` | 10/25 | ❌ 不迁移 |
| preparation | `tasks.py` | 8/25 | ❌ 不迁移 |
| scheduler | `tasks/report_cron.py` | 8/25 | ❌ 不迁移 |
| trigger | 3 个核心文件 | 13/25 | ❌ 不迁移 |

---

## 二、迁移目标 1：Celery 任务分片调度器

**源文件：** `alarm_backends/service/scheduler/tasks/__init__.py`

**总分：23/25** — 极简通用的分片调度函数

### 2.1 核心设计

```python
def perform_sharding_task(
    task_func,
    targets: list,
    num_per_task: int = 10,
    **kwargs
):
    """将大任务列表按固定批次大小拆分，通过 apply_async 异步分发"""
    for i in range(0, len(targets), num_per_task):
        batch = targets[i:i + num_per_task]
        task_func.apply_async(args=(batch,), **kwargs)
```

核心特性：
- **Map/Scatter 模式**：将大任务拆分为多个子任务并行执行
- **零业务耦合**：仅依赖 Celery 的 `apply_async` API
- **可配置批次大小**：`num_per_task` 参数控制并发粒度

### 2.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 批量任务分片是通用需求 |
| **复用价值** | 5/5 | 任何 Celery 场景的批量异步分发均可复用 |
| **独立性** | 5/5 | 仅依赖 Celery `apply_async` |
| **接口稳定性** | 4/5 | `perform_sharding_task(task_func, targets)` 接口简洁 |
| **代码质量** | 4/5 | 实现简洁高效 |

### 2.3 业务耦合清单

**无业务耦合。** 仅 ~10 行代码。

### 2.4 迁移范围

- `perform_sharding_task` 函数（~10 行）可直接提取
- 预估工作量：0.5h

### 2.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 批量数据处理 | 大数据集分片并行处理 |
| 批量通知 | 大量通知分片发送 |
| 批量任务执行 | 定时任务分片调度 |
| 数据同步 | 大表增量同步分片执行 |

---

## 三、迁移目标 2：抽象预处理基类

**源文件：** `alarm_backends/service/preparation/base.py`

**总分：20/25** — 零依赖的模板方法基类

### 3.1 核心设计

```python
class BasePreparationProcess(metaclass=ABCMeta):
    """数据准备/预处理的通用抽象基类"""

    @abstractmethod
    def process(self) -> None:
        """定义预处理契约"""
        ...
```

### 3.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | "数据准备/预处理"是通用模式 |
| **复用价值** | 3/5 | 可作为预处理类任务的通用基类模板 |
| **独立性** | 5/5 | 零外部依赖，仅 `abc` 和 `logging` |
| **接口稳定性** | 4/5 | `process()` 抽象方法契约清晰 |
| **代码质量** | 4/5 | 设计简洁 |

### 3.3 业务耦合清单

**无业务耦合。** 约 10 行有效代码。

### 3.4 迁移范围

- 整个文件可直接迁移
- 预估工作量：0.5h

### 3.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 数据预处理 | ETL 管道的预处理阶段 |
| 模型训练准备 | 机器学习数据预处理 |
| 配置初始化 | 系统启动时的数据准备 |
| 缓存预热 | 服务启动前的缓存加载 |

---

## 四、有条件迁移目标

### 4.1 执行耗时统计装饰器（`scheduler/tasks/cron.py`，16/25）

**核心设计：**

```python
@task_duration
def my_task():
    ...
```

装饰器包含：
- 执行时间记录
- 异常捕获与日志
- Prometheus 指标上报（`CRON_TASK_EXECUTE_TIME`、`CRON_TASK_EXECUTE_COUNT`）

**需解耦：**
- `core.prometheus.metrics` — 抽象为可插拔的回调接口
- `alarm_backends.core.cluster.get_cluster` — 移除
- `django.conf.settings` — 移除

**附带可提取工具：**
- `_get_func` — 动态导入函数
- `get_interval` — 计算 cron 间隔

---

## 五、不迁移模块说明

### preparation 模块

| 文件 | 不迁移原因 | 可参考设计 |
|------|-----------|-----------|
| `tasks.py` | 深度绑定 AIOps SDK 依赖数据准备 | 分布式锁领导者选举 |
| `aiops/processor.py` | 依赖 10+ 内部模块 | `ThreadPoolExecutor` 并发加载 + 自适应时间窗口预取 |

### scheduler 模块

| 文件 | 不迁移原因 | 可参考设计 |
|------|-----------|-----------|
| `app.py` | Celery 应用工厂，配置全部硬编码 | `PeriodicTask` 基类 |
| `tasks/api_cron.py` | 动态注册 API 定时任务，绑定 `API_CRONTAB` | 集群判断 + 任务注册模式 |
| `tasks/report_cron.py` | 混合多种报表任务，与 BMW 系统深度集成 | — |

### trigger 模块

| 文件 | 总分 | 不迁移原因 | 可参考设计 |
|------|------|-----------|-----------|
| `checker.py` | 13/25 | 依赖 6 个内部模块，数据结构全部领域特定 | 多级别异常检测（高→低优先级逐级判断）、Redis ZSet 滑动窗口 |
| `handler.py` | 13/25 | 绑定 Redis 锁、BaseHandler、Prometheus metrics | Queue Consumer + Distributed Lock 模式 |
| `processor.py` | 13/25 | 绑定策略体系、ES 适配器、Redis 集群 | **fail-open 限流 + deferred commit 模式**（先读后写，Kafka 成功后才提交计数） |

**特别说明：** `trigger/processor.py` 的限流设计质量极高（fail-open 策略 + 延迟提交避免失败时额度消耗），值得作为设计参考但代码本身无法迁移。

---

## 六、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 任务分片调度 | `scheduler/tasks/__init__.py` | 批量并行处理 |
| 预处理基类 | `preparation/base.py` | 数据预处理框架 |
| 执行耗时装饰器 | `scheduler/tasks/cron.py` | 性能监控 |
| fail-open 限流 + deferred commit | `trigger/processor.py` | 高可用限流 |
| Redis ZSet 滑动窗口检测 | `trigger/checker.py` | 实时异常检测 |
| Queue Consumer + Distributed Lock | `trigger/handler.py` | 分布式消费 |
| ThreadPoolExecutor 自适应预取 | `preparation/aiops/processor.py` | 缓存预热 |
| PeriodicTask 基类 | `scheduler/app.py` | 定时任务框架 |

---

## 七、迁移优先级汇总

| 优先级 | 文件 | 模块 | 总分 | 工作量 |
|--------|------|------|------|--------|
| **P0** | `tasks/__init__.py` | scheduler | 23/25 | 0.5h |
| **P0** | `base.py` | preparation | 20/25 | 0.5h |
| **P2** | `tasks/cron.py`（task_duration） | scheduler | 16/25 | 2h |
