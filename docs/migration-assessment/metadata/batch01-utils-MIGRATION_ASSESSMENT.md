# metadata Utils + Tools 迁移价值评估报告（批次 1）

> 评估范围：`bkmonitor/metadata/utils/` + `metadata/tools/`（15 个文件，约 1,880 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `utils/hash_util.py` | 98 | **23/25** | ✅ 强烈推荐迁移 |
| `utils/env.py` | 41 | **22/25** | ✅ 强烈推荐迁移 |
| `utils/db.py` | 154 | **19/25** | ✅ 推荐迁移 |
| `tools/redis_lock.py` | 76 | **19/25** | ✅ 推荐迁移 |
| `utils/es_tools.py` | 134 | 18/25 | ⚠️ 有条件迁移 |
| `utils/consul_tools.py` | 133 | 18/25 | ⚠️ 有条件迁移 |
| `utils/basic.py` | 113 | 17/25 | ⚠️ 有条件迁移 |
| `utils/redis_tools.py` | 164 | 14/25 | ❌ 不迁移 |
| `utils/influxdb_tools.py` | 127 | 12/25 | ❌ 不迁移 |
| `utils/gse.py` | 149 | 11/25 | ❌ 不迁移 |
| `utils/bkbase.py` | 179 | 10/25 | ❌ 不迁移 |
| `utils/bcs.py` | 213 | 10/25 | ❌ 不迁移 |
| `utils/data_link.py` | 101 | 10/25 | ❌ 不迁移 |
| `utils/go_time.py` | 13 | 10/25 | ❌ 不迁移 |
| `tools/constants.py` | 14 | 8/25 | ❌ 不迁移 |

---

## 二、迁移目标 1：递归对象 MD5 哈希器（23/25）

**源文件：** `metadata/utils/hash_util.py`

### 核心设计

递归序列化 dict/list 为确定性字符串，再计算 MD5，保证相同结构永远产生相同哈希：

```python
def object_md5(info) -> str:
    """对 dict/list/bytes/str 计算确定性 MD5，dict 键排序保证一致性"""

def _trans_dict_to_str(d) -> str:
    """字典按 key 排序后递归序列化为 'k1=v1&k2=v2' 格式"""

def _trans_list_to_str(l) -> str:
    """列表递归序列化，嵌套 dict/list 自动展开"""
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 纯函数，零外部依赖，任何需要数据指纹的场景均适用 |
| **复用价值** | 5/5 | 配置变更检测、缓存失效判断、数据一致性校验等高频场景 |
| **独立性** | 5/5 | 仅依赖 `hashlib` 标准库 |
| **接口稳定性** | 5/5 | 输入任意 Python 对象，输出 hex 字符串 |
| **代码质量** | 3/5 | 功能正确；缺少类型注解，未处理 tuple/set 等类型 |

### 迁移范围

整文件迁移（98 行）。建议增强：添加 type hints、支持 tuple/frozenset、可配置哈希算法。

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 配置变更检测 | 比对 Consul/DB 配置是否变化，避免无意义写入 |
| 缓存键生成 | 对复杂查询参数生成唯一缓存键 |
| 数据一致性校验 | 跨系统数据对账 |

---

## 三、迁移目标 2：环境变量列表采集器（22/25）

**源文件：** `metadata/utils/env.py`

### 核心设计

从编号环境变量中收集列表值（如 `IP0=1.1.1.1, IP1=2.2.2.2` → `["1.1.1.1", "2.2.2.2"]`）：

```python
def get_env_list(env_prefix: str) -> list[str]:
    """按前缀+递增序号收集环境变量，遇到第一个不存在的即停止"""
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 编号环境变量是容器/K8s 场景常见模式 |
| **复用价值** | 5/5 | 多节点配置、多 IP 传参等场景 |
| **独立性** | 5/5 | 仅依赖 `os` 和 `logging` 标准库 |
| **接口稳定性** | 5/5 | 极简接口，一个参数一个返回 |
| **代码质量** | 3/5 | 简洁；建议增加 `max_count` 防御参数 |

### 迁移范围

整文件迁移（41 行）。

---

## 四、迁移目标 3：Django ORM 分页查询器（19/25）

**源文件：** `metadata/utils/db.py`

### 核心设计

将大列表的 `IN` 查询按页拆分，避免数据库锁和查询超时：

```python
def filter_model_by_in_page(model, field_op, filter_data, page_size=500, ...):
    """分页 IN 查询：将大列表按 page_size 分组，逐页查询后合并"""

def filter_query_set_by_in_page(query_set, field_op, filter_data, ...):
    """对已有 QuerySet 的分页 IN 查询"""

def array_group(data, key, group=0):
    """列表按字段分组，支持计数模式"""
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 大批量 IN 查询分页是 Django 项目通用需求 |
| **复用价值** | 4/5 | 数据迁移、批量导入、报表查询等场景 |
| **独立性** | 3/5 | 依赖 Django ORM（ModelBase、QuerySet） |
| **接口稳定性** | 4/5 | 参数设计合理，支持 values/values_list 切换 |
| **代码质量** | 4/5 | 类型注解完整，职责拆分清晰 |

### 迁移范围

提取 `filter_model_by_in_page`、`filter_query_set_by_in_page`、`array_group`、`array_chunk`（约 100 行）。需保留 Django ORM 依赖。

---

## 五、迁移目标 4：Redis 分布式锁（19/25）

**源文件：** `metadata/tools/redis_lock.py`

### 核心设计

基于 Redis `SET NX` 的分布式锁，支持非阻塞获取、安全释放、手动续约：

```python
class DistributedLock:
    def __init__(self, redis_client, lock_name, timeout=...):
        """基于 redis.lock() 的分布式锁封装"""

    def acquire(self) -> bool: ...    # 非阻塞获取
    def release(self): ...            # 安全释放 + LockError 兜底
    def renew(self): ...              # 手动续约
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 分布式锁是微服务通用基础设施 |
| **复用价值** | 4/5 | 定时任务互斥、资源竞争控制 |
| **独立性** | 3/5 | 依赖 `redis-py` + `django.conf.settings` |
| **接口稳定性** | 4/5 | acquire/release/renew 接口简洁 |
| **代码质量** | 4/5 | LockError 兜底、日志完整 |

### 迁移范围

整文件迁移（76 行）。需将 `settings.BKBASE_REDIS_WATCH_LOCK_EXPIRE_SECONDS` 改为构造器注入。

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| 定时任务互斥 | 防止多个 worker 同时执行同一任务 |
| 资源竞争控制 | 保护共享资源的独占访问 |
| 长任务续期 | 配合看门狗线程自动延长锁有效期 |

---

## 六、有条件迁移目标

### HashConsul（`consul_tools.py`，18/25）

基于哈希对比的 Consul KV 写入器，只在值变化时才实际写入 Consul：

```python
class HashConsul:
    def put(self, key, value, is_force_update=False):
        """先比对 MD5，不同才写入 Consul，降低刷新频率"""
```

核心价值：哈希去重写入模式（30 行可提取）。依赖 `consul` 库和 `hash_util`。

### ES 多版本客户端工厂（`es_tools.py`，18/25）

```python
def get_client_by_datasource_info(datasource_info: dict) -> Elasticsearch:
    """根据版本号自动选择 ES5/ES6/ES7 客户端 + IPv6 兼容 + SSL/认证"""
```

核心价值：多版本 ES 客户端工厂 + 重试策略注入（约 70 行可提取）。依赖 `elasticsearch` 库。

### 嵌套字典安全取值（`basic.py`，17/25）

```python
def getitems(obj: dict, items: list | str, default=None) -> Any:
    """按 dotted path 安全取值：'foo.bar.baz' → obj['foo']['bar']['baz']"""
```

核心价值：仅 `getitems` 函数（20 行）可独立提取，零依赖。同文件其余函数依赖 Django Model。

---

## 七、不迁移模块说明

| 文件 | 总分 | 不迁移原因 |
|------|------|-----------|
| `utils/redis_tools.py` | 14 | Redis 路由推送工具，深度绑定 metadata 路由键规范和 Model |
| `utils/influxdb_tools.py` | 12 | InfluxDB 客户端封装，绑定 InfluxDB 集群配置和路由 |
| `utils/gse.py` | 11 | GSE 路由管理，绑定 GSE API 和 DataSource Model |
| `utils/bkbase.py` | 10 | BkBase 数据同步工具，绑定 BkBase API 和 Redis 监听 |
| `utils/bcs.py` | 10 | BCS 集群管理工具，绑定 BCS API 和 K8s 客户端 |
| `utils/data_link.py` | 10 | 数据链路配置，绑定 DataLink Model 和 BkBase API |
| `utils/go_time.py` | 13 | Go 时间格式转换，仅 13 行，过于简单 |
| `tools/constants.py` | 8 | 仅 2 个 Redis key 常量，业务绑定 |

---

## 八、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 递归对象 MD5 指纹 | `hash_util.py` | 配置变更检测、数据一致性校验 |
| 编号环境变量列表采集 | `env.py` | 容器/K8s 多节点配置传入 |
| 分页 IN 查询 | `db.py` | 大批量 ORM 查询防锁 |
| 哈希去重写入 | `consul_tools.py` | 降低配置中心写入频率 |
| 多版本客户端工厂 | `es_tools.py` | 多版本外部服务适配 |
| dotted path 安全取值 | `basic.py` | 嵌套配置/响应数据访问 |
| 分布式锁（acquire/release/renew） | `redis_lock.py` | 分布式互斥执行 |
| 前端/后端 Kafka 分层 | `redis_tools.py` | 消息队列路由管理参考 |
