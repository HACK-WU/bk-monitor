# apm BKData + eBPF Handler 迁移价值评估报告（批次 8）

> 评估范围：`apm/core/handlers/bk_data/`（5 文件）+ `ebpf/base.py`（1 文件），约 1,110 行
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 总分 | 结论 |
|------|------|------|
| `bk_data/flow.py` | 14 | ❌ 不迁移（模板方法+状态机可参考） |
| `bk_data/constants.py` | 17 | ❌ 不迁移 |
| `bk_data/helper.py` | 12 | ❌ 不迁移 |
| `bk_data/tail_sampling.py` | 9 | ❌ 不迁移 |
| `bk_data/virtual_metric.py` | 9 | ❌ 不迁移 |
| `ebpf/base.py` | 12 | ❌ 不迁移 |

**评估结论：6 个文件均未达到迁移阈值。**

---

## 二、不迁移模块说明

### `bk_data/flow.py`（14/25）— 设计参考价值最高

`ApmFlow` 是整个 BkData 子系统的核心基类，采用模板方法模式定义了 5 步编排流程：

```
_config_deploy → _config_cleans → _start_cleans → _auth_project → _start_flow
```

设计亮点：
- **状态机追踪**：每一步失败都有明确的 `FlowStatus` 状态码，执行过程持久化到数据库
- **差异化更新**：`_is_diff` 方法基于 MD5 对比，避免重复调用 BkData API
- **日志上下文封装**：`_BkdataFlowLogger` 将业务上下文注入 logger，同时持久化到 DB

深度耦合 `BkdataFlowConfig` Model、`api.bkdata.*` 系列接口（6 个 API），无法脱离 BkData 生态复用。

### 其余文件

| 文件 | 不迁移原因 |
|------|-----------|
| `bk_data/tail_sampling.py` | `ApmFlow` 子类，尾部采样专属，深度耦合 ES 集群资源管理 |
| `bk_data/virtual_metric.py` | 虚拟指标专属 Flow，高度重复的编排逻辑 |
| `bk_data/helper.py` | 22 行薄封装，仅查询 `BkdataFlowConfig` |
| `bk_data/constants.py` | `FlowStatus` 枚举完全对应 `flow.py` 编排阶段，脱离上下文无意义 |
| `ebpf/base.py` | eBPF 应用生命周期管理器，深度耦合 EbpfApplicationConfig Model 和 K8s API |

---

## 三、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 模板方法 + 多阶段编排 | `flow.py` | 分阶段执行且阶段间有依赖关系的场景 |
| 状态机追踪 + 过程持久化 | `flow.py` | 执行状态可观测的异步任务 |
| 配置差异检测（MD5） | `flow.py` | 避免无意义的外部 API 调用 |
| 日志上下文封装 | `flow.py` | 可观测性与可追溯性 |
| ES 资源注册与授权 | `tail_sampling.py` | BkData 资源对接参考 |
