# apm Discover 子系统迁移价值评估报告（批次 6）

> 评估范围：`apm/core/discover/` 下 metric/profile/precalculation 三个子系统（9 个文件，约 1,530 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `precalculation/check.py` | 238 | 12 | ❌ 不迁移（模拟退火算法可参考） |
| `precalculation/processor.py` | 273 | 12 | ❌ 不迁移（Trace DAG 分析可参考） |
| `precalculation/storage.py` | 443 | 12 | ❌ 不迁移（Rendezvous Hash 可参考） |
| `precalculation/consul_handler.py` | 197 | 8 | ❌ 不迁移 |
| `precalculation/daemon.py` | 363 | 8 | ❌ 不迁移 |
| `metric/service.py` | 168 | 9 | ❌ 不迁移 |
| `profile/service.py` | 205 | 9 | ❌ 不迁移 |
| `metric/base.py` | 19 | 10 | ❌ 不迁移 |
| `profile/base.py` | 76 | 10 | ❌ 不迁移 |

**评估结论：9 个文件均未达到迁移阈值。但蕴含 3 个值得独立实现的算法设计。**

---

## 二、设计参考模块

### 2.1 模拟退火负载均衡算法（`precalculation/check.py`）

`PreCalculateCheck.calculate_distribution()` 实现了完整的**模拟退火算法**，用于将应用均匀分配到多个任务队列：
- 以请求量标准差作为代价函数
- 随机初始解 + 迭代扰动 + Metropolis 接受准则
- 可配置冷却速率、迭代次数、初始温度
- 约 80 行纯算法逻辑可独立提取

### 2.2 Trace DAG 分析器（`precalculation/processor.py`）

`PrecalculateProcessor.get_trace_info()` 使用 `networkx.DiGraph` 构建 Span 父子关系有向图：
- 通过 `dag_longest_path_length()` 计算调用层级深度
- 通过入度 `in_degree` 识别入口 Span
- 统计分类（HTTP/RPC/DB/Messaging）和类型（Sync/Async/Internal）分布

### 2.3 Rendezvous Hash（`precalculation/storage.py`）

基于 SHA1 的 **Rendezvous Hashing**（最高随机权重）实现：
- 18 行纯算法，零外部依赖
- 适用于分布式存储分片、缓存路由、负载分配
- 比普通哈希取模有更好的节点增删稳定性

---

## 三、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 模拟退火负载均衡 | `check.py` | 加权队列分配 |
| Rendezvous Hashing | `storage.py` | 一致性哈希分片 |
| DAG 调用深度分析 | `processor.py` | Trace 结构分析 |
| 多版本 ES 兼容 | `storage.py` | 运行时版本适配 |
| 写索引日期别名 | `storage.py` | 时间分区存储 |
| Schema 变更检测 | `storage.py` | 配置变更管理 |
