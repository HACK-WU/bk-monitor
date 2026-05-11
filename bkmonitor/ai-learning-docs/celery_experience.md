# bkmonitor Celery 使用经验学习文档

## 一、Celery 架构概览

### 1.1 双 Celery App 设计

bkmonitor 采用**双 Celery App 设计**，分别服务于 Web API 和后台告警服务：

```mermaid
graph TB
    subgraph "Web API 服务"
        A[config/celery/celery.py] --> B[proj Celery App]
        B --> C[django_celery_results<br/>数据库结果后端]
        B --> D[MonitorDatabaseScheduler<br/>自定义调度器]
        B --> E[task_always_eager=True<br/>API模式同步执行]
    end

    subgraph "后台告警服务"
        F[alarm_backends/service/scheduler/app.py] --> G[backend Celery App]
        G --> H[RabbitMQ Broker]
        G --> I[Redis Sentinel<br/>结果后端]
        G --> J[动态Worker数量]
        G --> K[集群隔离队列前缀]
        G --> L[Prometheus监控集成]
    end

    subgraph "任务队列层"
        M[celery_cron] --> N[周期任务]
        O[celery_service] --> P[数据处理]
        Q[celery_action] --> R[动作执行]
        S[celery_resource] --> T[Web异步]
    end
```

### 1.2 核心配置文件

| 服务类型 | 配置文件 | 主要特性 |
|---------|---------|---------|
| Web API | `config/celery/celery.py` | 数据库结果后端、自定义调度器、同步执行模式 |
| 告警后台 | `alarm_backends/service/scheduler/app.py` | RabbitMQ Broker、动态 Worker、集群隔离、监控集成 |

---

## 二、Celery 配置详解

### 2.1 Web API Celery 配置

**文件路径**：`config/celery/celery.py`

```python
from celery import Celery
from config.celery.config import Config

app = Celery("proj")
app.config_from_object("config.celery.config:Config")

# 自动发现任务
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# 使用自定义调度器
from monitor.schedulers import MonitorDatabaseScheduler
app.scheduler = MonitorDatabaseScheduler
```

**配置详情**：`config/celery/config.py`

```python
class Config:
    # Broker 配置
    BROKER_URL = settings.BROKER_URL

    # 结果后端 - 使用 Django 数据库
    CELERY_RESULT_BACKEND = "django_celery_results.backends:DatabaseBackend"

    # 序列化方式
    CELERY_TASK_SERIALIZER = "pickle"
    CELERY_RESULT_SERIALIZER = "pickle"
    CELERY_ACCEPT_CONTENT = ["pickle", "json"]

    # API 服务模式：任务同步执行
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_EAGER_PROPAGATES_EXCEPTIONS = True

    # 时区配置
    CELERY_TIMEZONE = "Asia/Shanghai"
    CELERY_ENABLE_UTCS = True

    # Beat 定时任务配置
    CELERYBEAT_SCHEDULE = {
        "monitor_web.tasks.update_external_approval_status": {
            "task": "monitor_web.tasks.update_external_approval_status",
            "schedule": crontab(minute="*/10"),
            "enabled": True,
        },
        # ... 更多定时任务
    }
```

---

### 2.2 后台告警服务 Celery 配置

**文件路径**：`alarm_backends/service/scheduler/app.py`

```python
from celery import Celery
from celery.signals import beat_init, task_postrun
from kombu import Exchange, Queue
from psutil import cpu_count
import os

# 动态计算 Worker 数量
def default_celery_worker_num():
    """根据 CPU 核数动态计算 Worker 数量"""
    return int(cpu_count() ** 0.6 * 1.85)

# 创建 Celery App
app = Celery("backend")

# 队列定义
def default_queues():
    """默认队列配置"""
    exchange = Exchange("default", type="direct")
    return [
        Queue("celery_cron", exchange, routing_key="celery_cron"),
        Queue("celery_service", exchange, routing_key="celery_service"),
        Queue("celery_action", exchange, routing_key="celery_action"),
        Queue("celery_resource", exchange, routing_key="celery_resource"),
        # ... 更多队列
    ]

# Broker 配置
def rabbitmq_conf():
    conf = {
        "BROKER_URL": settings.BROKER_URL,

        # 结果后端 - Redis Sentinel
        "CELERY_RESULT_BACKEND": f"redis-sentinel://{sentinel_address}/{db}",

        # Worker 配置
        "CELERYD_CONCURRENCY": default_celery_worker_num(),
        "CELERYD_MAX_TASKS_PER_CHILD": 1000,  # 子进程最大任务数

        # 队列配置
        "CELERY_QUEUES": default_queues(),

        # 序列化配置
        "CELERY_TASK_SERIALIZER": "pickle",
        "CELERY_RESULT_SERIALIZER": "pickle",
        "CELERY_ACCEPT_CONTENT": ["pickle", "json"],

        # 时区
        "CELERY_TIMEZONE": "Asia/Shanghai",
    }

    # 集群隔离：非默认集群使用队列前缀
    if not get_cluster().is_default():
        conf["BROKER_TRANSPORT_OPTIONS"] = {
            "queue_name_prefix": f"{get_cluster().name}-",
        }

    return conf

app.config_from_object(rabbitmq_conf())

# 信号处理
@beat_init.connect
def clean_db_connections(sender, **kwargs):
    """Beat 启动时清理数据库连接"""
    close_old_connections()

@task_postrun.connect
def task_postrun_handler(sender=None, **kwargs):
    """任务结束后清理线程变量"""
    from django_tools.local import local
    local.clear()
```

---

### 2.3 Worker 配置优化

```python
# 关键配置参数

# 1. 动态 Worker 数量计算
CELERYD_CONCURRENCY = int(cpu_count() ** 0.6 * 1.85)

# 2. 子进程最大任务数 - 防止内存泄漏
CELERYD_MAX_TASKS_PER_CHILD = 1000

# 3. 任务软超时时间
CELERYD_TASK_SOFT_TIME_LIMIT = 60

# 4. 任务硬超时时间
CELERYD_TASK_TIME_LIMIT = 120

# 5. 预取任务数 - 限制每个 Worker 预取的任务数量
CELERYD_PREFETCH_MULTIPLIER = 4

# 6. 任务结果过期时间
CELERY_RESULT_EXPIRES = 3600
```

---

## 三、队列隔离策略

### 3.1 队列分类设计

```mermaid
graph LR
    subgraph "周期任务队列"
        A1[celery_cron] --> B1[全局周期任务]
        A2[celery_action_cron] --> B2[动作周期任务]
        A3[celery_long_task_cron] --> B3[长耗时周期任务]
        A4[celery_report_cron] --> B4[报表生成任务]
    end

    subgraph "服务处理队列"
        C1[celery_service] --> D1[数据处理]
        C2[celery_service_aiops] --> D2[智能检测]
        C3[celery_service_qos] --> D3[QoS流控]
        C4[celery_service_batch] --> D4[批量处理]
        C5[celery_service_access_event] --> D5[事件接入]
    end

    subgraph "告警处理队列"
        E1[celery_alert_builder] --> F1[告警构建]
        E2[celery_composite] --> F2[关联策略]
        E3[celery_converge] --> F3[告警收敛]
    end

    subgraph "动作执行队列"
        G1[celery_action] --> H1[动作创建]
        G2[celery_interval_action] --> H2[周期通知]
        G3[celery_running_action] --> H3[动作运行]
        G4[celery_webhook_action] --> H4[Webhook执行]
        G5[celery_notice_action] --> H5[通知发送]
    end

    subgraph "Web异步队列"
        I1[celery_resource] --> J1[API异步操作]
    end
```

### 3.2 队列定义表

| 队列名称 | 用途 | 任务类型 | 配置位置 |
|---------|------|---------|---------|
| `celery_cron` | 全局周期任务 | 定时调度 | DEFAULT_CRONTAB |
| `celery_action_cron` | 动作相关周期任务 | 动作管理 | ACTION_TASK_CRONTAB |
| `celery_long_task_cron` | 长耗时周期任务 | 统计同步 | LONG_TASK_CRONTAB |
| `celery_report_cron` | 报表周期任务 | 报表生成 | 报表模块 |
| `celery_service` | 服务层数据处理 | 检测/接入 | 任务装饰器 |
| `celery_service_aiops` | AIOPS 检测 | 智能检测 | 智能检测任务 |
| `celery_service_qos` | QoS 流控数据处理 | 流控队列 | 流控模块 |
| `celery_service_batch` | 批量数据处理 | 批量接入 | 批量任务 |
| `celery_service_access_event` | 事件接入处理 | 自定义事件 | 事件接入 |
| `celery_alert_builder` | 告警构建 | 告警处理 | 告警构建任务 |
| `celery_composite` | 关联策略处理 | 组合检测 | 关联策略任务 |
| `celery_converge` | 告警收敛 | 收敛处理 | 收敛任务 |
| `celery_action` | 动作创建 | 处理套餐 | 动作创建任务 |
| `celery_interval_action` | 周期性动作 | 循环通知 | 周期通知任务 |
| `celery_running_action` | 动作运行 | 动作执行 | 动作执行任务 |
| `celery_webhook_action` | Webhook 执行 | Webhook回调 | Webhook任务 |
| `celery_notice_action` | 通知发送 | 通知处理 | 通知任务 |
| `celery_resource` | Web 资源异步任务 | API 异步操作 | Resource 任务 |

---

## 四、任务定义最佳实践

### 4.1 任务装饰器使用

**基本任务定义**：

```python
from celery import shared_task

@shared_task(ignore_result=True, queue="celery_service")
def run_detect(strategy_id):
    """
    执行检测任务

    参数说明：
    - ignore_result=True: 不存储任务结果，提升性能
    - queue: 指定任务队列
    """
    try:
        processor = DetectProcess(strategy_id)
        processor.process()
    except LockError:
        # 锁获取失败，延迟重试
        client.delay("lpush", data_signal_key, strategy_id, delay=20)
    except Exception as e:
        logger.exception(f"Process strategy({strategy_id}) exception")
```

**带绑定任务定义**：

```python
@shared_task(bind=True, queue="celery_resource")
def run_perform_request(self, resource_obj, username, bk_tenant_id, request_data):
    """
    绑定任务 - 可访问任务实例 self

    用于：
    - 更新任务状态
    - 获取任务 ID
    - 重试控制
    """
    # 设置上下文
    set_local_username(username)
    set_local_tenant_id(bk_tenant_id)

    try:
        result = resource_obj.perform_request(request_data)
        self.update_state(state="COMPLETED", meta={"result": result})
        return result
    except Exception as e:
        self.update_state(state="FAILED", meta={"error": str(e)})
        raise
```

---

### 4.2 任务队列选择策略

```python
# alarm_backends/service/fta_action/tasks/action_tasks.py

def dispatch_action_task(action_type, action_info, countdown=0, **kwargs):
    """
    根据 action_type 自动选择对应的队列发送任务

    设计原则：
    1. 不同任务类型使用独立队列，避免相互阻塞
    2. Webhook 和 MessageQueue 共用队列（相似特性）
    3. 通知任务可使用专用队列（环境变量控制）
    """

    # WEBHOOK 和 MESSAGE_QUEUE 类型使用 webhook 队列
    if action_type in [ActionPluginType.WEBHOOK, ActionPluginType.MESSAGE_QUEUE]:
        return run_webhook_action.apply_async(
            (action_type, action_info),
            countdown=countdown,
            **kwargs
        )

    # NOTICE 类型可以使用专用的通知队列
    if os.getenv("ENABLE_NOTICE_QUEUE") and action_type == ActionPluginType.NOTICE:
        return run_notice_action.apply_async(
            (action_type, action_info),
            countdown=countdown,
            **kwargs
        )

    # 其他类型使用默认的运行队列
    return run_action.apply_async(
        (action_type, action_info),
        countdown=countdown,
        **kwargs
    )
```

---

### 4.3 任务执行模式

#### 4.3.1 异步执行

```python
# 立即异步执行
run_detect.apply_async(args=(strategy_id,))

# 批量异步执行 - 发送多个任务
for strategy_id in strategy_ids:
    run_detect.apply_async(args=(strategy_id,))
```

#### 4.3.2 延迟执行

```python
# 带延迟的异步执行 - countdown 参数
polling_aiops_strategy_status.apply_async(
    args=(flow_id, result["task_id"], base_labels),
    countdown=AIOPS_ACCESS_STATUS_POLLING_INTERVAL,  # 延迟 N 秒执行
)

# 带过期时间的延迟执行 - expires 参数
check_create_poll_action_10_secs.apply_async(
    countdown=interval,
    expires=120  # 任务过期时间，防止堆积
)

# 指定执行时间 - eta 参数
run_action.apply_async(
    args=(action_type, action_info),
    eta=datetime.now() + timedelta(minutes=5),
)
```

#### 4.3.3 重试机制

```python
# 任务内部重试逻辑
@app.task(ignore_result=True, queue="celery_converge")
def run_converge(converge_config, instance_id, ..., retry_times=0):
    try:
        processor = ConvergeManager(...)
        processor.process()
    except Exception as exc:
        logger.exception("run converge error")

        # 重试次数限制
        if retry_times < 3:
            run_converge.apply_async(
                (converge_config, instance_id, ..., retry_times + 1),
                countdown=CONST_HALF_MINUTE,  # 延迟 30 秒重试
            )
        else:
            # 重试次数耗尽，记录失败
            logger.error(f"converge failed after 3 retries: {exc}")

# 使用 Celery 内置重试机制
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_data(self, data_id):
    try:
        process(data_id)
    except TemporaryError as exc:
        # 抛出异常触发重试
        raise self.retry(exc=exc)
    except PermanentError as exc:
        # 永久错误不重试
        logger.error(f"permanent error: {exc}")
```

---

## 五、定时任务配置

### 5.1 Crontab 任务定义

**文件路径**：`config/role/worker.py`

```python
# 周期任务配置格式
DEFAULT_CRONTAB = [
    # (任务路径, cron表达式, 运行类型)
    ("alarm_backends.core.cache.strategy", "*/6 * * * *", "global"),
    ("alarm_backends.core.cache.strategy.smart_refresh", "* * * * *", "global"),
    ("apm.task.tasks.topo_discover_cron", "* * * * *", "global"),
    ("alarm_backends.service.alert.manager.tasks.check_abnormal_alert", "* * * * *", "cluster"),
    # ... 更多任务
]

ACTION_TASK_CRONTAB = [
    ("alarm_backends.core.cache.shield.main", "* * * * *", "global"),
    ("alarm_backends.service.fta_action.tasks.sync_action_instances_every_10_secs", "*/10 * * * *", "cluster"),
    # ... 更多任务
]

LONG_TASK_CRONTAB = [
    ("metadata.task.config_refresh.refresh_es_storage", "*/15 * * * *", "global"),
    # ... 更多任务
]
```

**运行类型说明**：

| 运行类型 | 说明 | 适用场景 |
|---------|------|---------|
| `global` | 全局执行（所有集群） | 数据刷新、拓扑发现 |
| `cluster` | 集群内执行（单集群） | 告警检查、动作同步 |

---

### 5.2 动态 Crontab 注册

**文件路径**：`alarm_backends/service/scheduler/tasks/cron.py`

```python
from celery import shared_task
from config.role.worker import DEFAULT_CRONTAB, ACTION_TASK_CRONTAB, LONG_TASK_CRONTAB

def get_interval(run_every):
    """计算任务间隔时间"""
    # 解析 cron 表达式，返回间隔秒数
    ...

def register_crontab():
    """
    动态注册周期任务

    设计要点：
    1. 使用 expires 防止任务堆积
    2. 区分 global 和 cluster 类型
    3. 支持集群隔离
    """
    for task_path, run_every, run_type in DEFAULT_CRONTAB:
        interval = get_interval(run_every)

        # 任务过期时间 = max(间隔时间, 300秒)，最大 3600秒
        expires = min(3600, max(interval, 300))

        # 注册任务
        app.add_periodic_task(
            interval,
            task_path,
            args=(),
            kwargs={},
            expires=expires,
            queue="celery_cron",
        )
```

---

### 5.3 Beat 调度配置

```python
# config/celery/config.py

from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    # 更新外部审批状态 - 每 10 分钟
    "monitor_web.tasks.update_external_approval_status": {
        "task": "monitor_web.tasks.update_external_approval_status",
        "schedule": crontab(minute="*/10"),
        "enabled": True,
    },

    # 清理过期数据 - 每小时
    "monitor_web.tasks.clean_expired_data": {
        "task": "monitor_web.tasks.clean_expired_data",
        "schedule": crontab(minute=0),
        "enabled": True,
    },

    # 生成报表 - 每天 2:00
    "monitor_web.tasks.generate_daily_report": {
        "task": "monitor_web.tasks.generate_daily_report",
        "schedule": crontab(hour=2, minute=0),
        "enabled": True,
    },
}
```

---

## 六、分布式锁与并发控制

### 6.1 服务锁机制

**文件路径**：`alarm_backends/core/lock/service_lock.py`

```python
import uuid
from contextlib import contextmanager
from alarm_backends.core.cache.key import SERVICE_LOCK_ACCESS

class RedisLock:
    """Redis 分布式锁实现"""

    def __init__(self, key, ttl):
        self.key = key
        self.ttl = ttl
        self.token = str(uuid.uuid4())

    def acquire(self, timeout=0.1):
        """获取锁 - SET NX EX"""
        return self.client.set(self.key, self.token, nx=True, ex=self.ttl)

    def release(self):
        """释放锁 - Lua脚本保证原子性"""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.client.eval(script, 1, self.key, self.token)

@contextmanager
def service_lock(key_instance, **kwargs):
    """
    分布式服务锁上下文管理器

    使用方式：
    with service_lock(SERVICE_LOCK_ACCESS, strategy_group_key=key):
        processor.process()
    """
    lock_key = key_instance.get_key(**kwargs)
    lock = RedisLock(lock_key, key_instance.ttl)

    try:
        if lock.acquire(0.1):
            yield lock
        else:
            raise LockError(msg=f"{lock_key} is already locked")
    except LockError:
        raise
    finally:
        if lock:
            lock.release()
```

---

### 6.2 共享锁装饰器

```python
def share_lock(ttl=600, identify=None, key_instance=None):
    """
    共享锁装饰器

    用于：
    - 防止同一任务被多个进程同时执行
    - 周期任务防重复执行

    参数：
    - ttl: 锁过期时间
    - identify: 锁标识（默认使用函数名）
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            lock_key = key_instance.get_key(identify=identify or func.__name__)
            client = key_instance.client
            token = str(uuid.uuid4())

            acquired = client.set(lock_key, token, nx=True, ex=ttl)
            if not acquired:
                logger.info(f"[share_lock] {func.__name__} is already running")
                return None

            try:
                return func(*args, **kwargs)
            finally:
                # Lua脚本安全释放
                script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                end
                """
                client.eval(script, 1, lock_key, token)

        return wrapper
    return decorator

# 使用示例
@share_lock(ttl=600, key_instance=SYNC_ACTION_LOCK_KEY)
def sync_action_instances():
    """同步动作实例 - 防重复执行"""
    ...
```

---

### 6.3 锁失败重试策略

```python
@app.task(ignore_result=True, queue="celery_service")
def run_detect(strategy_id):
    """
    检测任务执行

    锁失败处理策略：
    1. LockError：延迟 20 秒重新推送任务
    2. 处理繁忙：立即重新调度
    """
    exc = None
    try:
        processor = DetectProcess(strategy_id)
        processor.process()
    except LockError:
        logger.info(f"Failed to acquire lock on strategy({strategy_id})")
        # 延迟重试
        client.delay("lpush", data_signal_key, strategy_id, delay=20)
        return
    except Exception as e:
        exc = e
        logger.exception(f"Process strategy({strategy_id}) exception")
    else:
        # 处理繁忙，立即重新调度
        if processor.is_busy:
            run_detect.apply_async(args=(strategy_id,))

    # 上报监控指标
    metrics.DETECT_PROCESS_COUNT.labels(
        strategy_id=metrics.TOTAL_TAG,
        status=metrics.StatusEnum.from_exc(exc),
        exception=exc
    ).inc()
```

---

## 七、监控集成

### 7.1 Prometheus 监控集成

**文件路径**：`core/prometheus/tools.py`

```python
from celery import Celery
from types import MethodType
import time
import metrics

def celery_app_timer(app):
    """
    Celery 任务监控集成

    通过 hack task 方法，在任务执行前后记录监控指标
    """
    app._old_task = app.task

    def hack_task(self, *args, **kwargs):
        """替换 task 方法，添加监控"""
        func = args[0] if args else kwargs.get("func")
        queue = kwargs.get("queue", "default")

        def wrapper(*task_args, **task_kwargs):
            start_time = time.time()
            exception = None

            try:
                return func(*task_args, **task_kwargs)
            except BaseException as e:
                exception = e
                raise
            finally:
                # 记录执行时间
                metrics.CELERY_TASK_EXECUTE_TIME.labels(
                    task_name=func.__name__,
                    queue=queue,
                    exception=exception.__class__.__name__ if exception else "None",
                ).observe(time.time() - start_time)

                # 记录执行次数
                metrics.CELERY_TASK_EXECUTE_COUNT.labels(
                    task_name=func.__name__,
                    queue=queue,
                    status="success" if not exception else "failure",
                ).inc()

        # 使用原装饰器装饰 wrapper
        return self._old_task(wrapper, *args[1:], **kwargs)

    app.task = MethodType(hack_task, app)
```

---

### 7.2 任务执行指标

```python
# 监控指标定义

CELERY_TASK_EXECUTE_TIME = Histogram(
    "celery_task_execute_time",
    "Celery 任务执行时间",
    ["task_name", "queue", "exception"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
)

CELERY_TASK_EXECUTE_COUNT = Counter(
    "celery_task_execute_count",
    "Celery 任务执行次数",
    ["task_name", "queue", "status"],
)

CELERY_TASK_QUEUE_LENGTH = Gauge(
    "celery_task_queue_length",
    "Celery 任务队列长度",
    ["queue"],
)
```

---

## 八、信号处理与生命周期

### 8.1 信号处理器配置

```python
from celery.signals import (
    beat_init,
    worker_init,
    task_prerun,
    task_postrun,
    task_failure,
)

@beat_init.connect
def clean_db_connections(sender, **kwargs):
    """Beat 启动时清理数据库连接"""
    from django.db import close_old_connections
    close_old_connections()
    logger.info("Beat initialized, cleaned db connections")

@worker_init.connect
def worker_init_handler(sender, **kwargs):
    """Worker 启动时初始化"""
    # 初始化缓存连接
    init_cache_connection()
    # 加载策略缓存
    load_strategy_cache()
    logger.info(f"Worker {sender.hostname} initialized")

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
    """任务执行前处理"""
    # 设置租户上下文
    if kwargs.get("headers"):
        bk_tenant_id = kwargs["headers"].get("bk_tenant_id")
        if bk_tenant_id:
            set_local_tenant_id(bk_tenant_id)
    logger.debug(f"Task {task.name}[{task_id}] starting")

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, **kwargs):
    """任务执行后处理"""
    # 清理线程变量
    from django_tools.local import local
    local.clear()
    # 关闭旧数据库连接
    close_old_connections()
    logger.debug(f"Task {task.name}[{task_id}] finished")

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """任务失败处理"""
    logger.error(f"Task {sender.name}[{task_id}] failed: {exception}")
    # 发送失败告警
    send_failure_alert(task_id, sender.name, str(exception))
```

---

### 8.2 上下文传递

```python
@shared_task(bind=True, queue="celery_resource")
def run_perform_request(self, resource_obj, username, bk_tenant_id, request_data):
    """
    异步任务中传递上下文

    关键点：
    1. 使用 bind=True 获取任务实例
    2. 显式传递用户和租户信息
    3. 任务开始时设置本地上下文
    """
    # 设置用户上下文
    set_local_username(username)
    set_local_tenant_id(bk_tenant_id)

    try:
        result = resource_obj.perform_request(request_data)
        return result
    finally:
        # 清理上下文
        clear_local_context()
```

---

## 九、集群隔离设计

### 9.1 队列前缀机制

```python
# alarm_backends/service/scheduler/app.py

def get_celery_config():
    conf = {...}

    # 集群隔离：非默认集群使用队列前缀
    if not get_cluster().is_default():
        conf["BROKER_TRANSPORT_OPTIONS"] = {
            "queue_name_prefix": f"{get_cluster().name}-",
        }

    return conf

# 队列名称转换示例
# 默认集群：celery_service
# 集群 A：clusterA-celery_service
# 集群 B：clusterB-celery_service
```

### 9.2 任务路由隔离

```python
# config/role/worker.py

DEFAULT_CRONTAB = [
    # global 类型：所有集群执行
    ("alarm_backends.core.cache.strategy", "*/6 * * * *", "global"),

    # cluster 类型：仅集群内执行
    ("alarm_backends.service.alert.manager.tasks.check_abnormal_alert", "* * * * *", "cluster"),
]

def register_crontab():
    for task_path, run_every, run_type in DEFAULT_CRONTAB:
        # cluster 类型任务仅在当前集群注册
        if run_type == "cluster" and not should_run_in_cluster():
            continue

        app.add_periodic_task(...)
```

---

## 十、最佳实践总结

### 10.1 设计原则

| 原则 | 说明 | 实现方式 |
|------|------|---------|
| **队列隔离** | 不同任务类型使用独立队列 | 装饰器指定 queue 参数 |
| **动态 Worker** | 根据 CPU 动态计算并发数 | `cpu_count() ** 0.6 * 1.85` |
| **子进程重生** | 防止内存泄漏 | `worker_max_tasks_per_child = 1000` |
| **任务过期** | 防止任务堆积 | `expires=min(3600, max(interval, 300))` |
| **分布式锁** | 防止并发冲突 | Redis SET NX EX + Lua 释放 |
| **监控集成** | Prometheus 指标采集 | hack task 方法 |
| **集群隔离** | 多集群队列前缀 | `queue_name_prefix` |
| **上下文传递** | 异步任务用户/租户信息 | 显式参数 + 本地设置 |

---

### 10.2 任务定义模板

```python
# 标准 Celery 任务定义模板

@shared_task(
    ignore_result=True,      # 不存储结果，提升性能
    queue="celery_service",  # 指定队列
    max_retries=3,           # 最大重试次数
    default_retry_delay=60,  # 重试间隔
)
def process_data(data_id: int):
    """
    数据处理任务

    Args:
        data_id: 数据ID

    Notes:
        - 使用 ignore_result=True 避免存储结果
        - 使用分布式锁防止并发
        - 异常时延迟重试
    """
    from alarm_backends.core.lock.service_lock import service_lock
    from alarm_backends.core.cache.key import SERVICE_LOCK_DATA

    # 分布式锁保护
    try:
        with service_lock(SERVICE_LOCK_DATA, data_id=data_id):
            processor = DataProcessor(data_id)
            processor.process()

    except LockError:
        # 锁获取失败，延迟重试
        logger.info(f"Lock failed for data {data_id}, retry later")
        process_data.apply_async(args=(data_id,), countdown=30)

    except Exception as e:
        logger.exception(f"Process data {data_id} failed")
        # 内部重试逻辑
        raise
```

---

### 10.3 关键文件路径

| 类别 | 文件路径 |
|------|---------|
| Web Celery App | `config/celery/celery.py` |
| Web Celery 配置 | `config/celery/config.py` |
| 后台 Celery App | `alarm_backends/service/scheduler/app.py` |
| Crontab 配置 | `config/role/worker.py` |
| Cron 注册 | `alarm_backends/service/scheduler/tasks/cron.py` |
| 服务锁 | `alarm_backends/core/lock/service_lock.py` |
| Prometheus 监控 | `core/prometheus/tools.py` |
| Resource 异步任务 | `core/drf_resource/tasks.py` |
| Web 层任务 | `packages/monitor_web/tasks.py` |
| 数据接入任务 | `alarm_backends/service/access/tasks.py` |
| 检测任务 | `alarm_backends/service/detect/tasks.py` |
| 告警构建任务 | `alarm_backends/service/alert/builder/tasks.py` |
| 告警管理任务 | `alarm_backends/service/alert/manager/tasks.py` |
| 收敛任务 | `alarm_backends/service/converge/tasks.py` |
| 动作创建任务 | `alarm_backends/service/fta_action/tasks/create_action.py` |
| 动作执行任务 | `alarm_backends/service/fta_action/tasks/action_tasks.py` |

---

## 十一、常见问题与解决方案

### 11.1 任务堆积问题

**问题**：周期任务堆积，导致任务队列阻塞

**解决方案**：

```python
# 1. 使用 expires 参数防止堆积
app.add_periodic_task(
    interval,
    task_path,
    expires=min(3600, max(interval, 300)),  # 任务过期时间
)

# 2. 使用 share_lock 装饰器防止重复执行
@share_lock(ttl=300, key_instance=SYNC_LOCK_KEY)
def sync_data():
    ...

# 3. 限制 Worker 预取数量
CELERYD_PREFETCH_MULTIPLIER = 4
```

### 11.2 内存泄漏问题

**问题**：Worker 长时间运行导致内存增长

**解决方案**：

```python
# 1. 子进程最大任务数限制
CELERYD_MAX_TASKS_PER_CHILD = 1000

# 2. 任务后清理线程变量
@task_postrun.connect
def task_postrun_handler(sender=None, **kwargs):
    local.clear()
    close_old_connections()

# 3. 使用软超时时间
CELERYD_TASK_SOFT_TIME_LIMIT = 60
```

### 11.3 并发冲突问题

**问题**：多个 Worker 同时处理同一数据

**解决方案**：

```python
# 1. 使用分布式锁
with service_lock(SERVICE_LOCK_DATA, data_id=data_id):
    process(data_id)

# 2. 锁失败延迟重试
except LockError:
    process_data.apply_async(args=(data_id,), countdown=30)
```

### 11.4 任务结果丢失问题

**问题**：任务结果无法获取

**解决方案**：

```python
# 1. 使用数据库结果后端（Web API）
CELERY_RESULT_BACKEND = "django_celery_results.backends:DatabaseBackend"

# 2. 使用 Redis Sentinel 结果后端（后台服务）
CELERY_RESULT_BACKEND = f"redis-sentinel://{sentinel_address}/{db}"

# 3. 设置结果过期时间
CELERY_RESULT_EXPIRES = 3600
```

---

## 十二、扩展阅读

### 12.1 Celery 配置参数详解

```python
# 核心配置参数

# Broker 配置
BROKER_URL = "amqp://guest:guest@localhost:5672//"

# 结果后端配置
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

# 序列化配置
CELERY_TASK_SERIALIZER = "json"      # 任务参数序列化
CELERY_RESULT_SERIALIZER = "json"    # 结果序列化
CELERY_ACCEPT_CONTENT = ["json"]     # 接受的内容类型

# Worker 配置
CELERYD_CONCURRENCY = 4              # Worker 并发数
CELERYD_PREFETCH_MULTIPLIER = 4      # 预取任务数
CELERYD_MAX_TASKS_PER_CHILD = 1000   # 子进程最大任务数
CELERYD_TASK_TIME_LIMIT = 120        # 任务硬超时（秒）
CELERYD_TASK_SOFT_TIME_LIMIT = 60    # 任务软超时（秒）

# 任务配置
CELERY_TASK_ALWAYS_EAGER = False     # 是否同步执行
CELERY_EAGER_PROPAGATES_EXCEPTIONS = True  # 同步模式传播异常
CELERY_TASK_RESULT_EXPIRES = 3600    # 结果过期时间（秒）

# Beat 配置
CELERYBEAT_SCHEDULE = {...}          # 定时任务配置
CELERYBEAT_MAX_LOOP_INTERVAL = 60    # Beat 最大循环间隔

# 时区配置
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_ENABLE_UTCS = True
```

### 12.2 相关文档链接

- Celery 官方文档：https://docs.celeryq.dev/
- Django Celery 集成：https://docs.celeryq.dev/en/stable/django/
- RabbitMQ 文档：https://www.rabbitmq.com/docs
- Redis Sentinel 文档：https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/