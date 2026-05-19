# log_databus ETL 与工具层迁移价值评估报告（批次 9）

> 评估范围：`log_databus/handlers/etl_storage/` + `handlers/etl/` + `handlers/check_collector/` + `handlers/storage.py` + `handlers/archive.py` + `handlers/itsm.py` + `handlers/collector_plugin/` + `tasks/` + `scripts/` + `management/commands/` + `constants.py` + `exceptions.py`（19 个文件/模块，约 10,609 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `exceptions.py` | 430 | 15/25 | ⚠️ 有条件迁移 |
| `scripts/check_bkunifylogbeat/check.py` | 305 | 14/25 | ❌ 不迁移 |
| `handlers/etl_storage/base.py` | 1,710 | 14/25 | ❌ 不迁移 |
| `handlers/storage.py` | 1,200 | 13/25 | ❌ 不迁移 |
| `handlers/check_collector/checker/bkunifylogbeat_checker.py` | 453 | 13/25 | ❌ 不迁移 |
| `handlers/etl_storage/bk_log_delimiter.py` | 465 | 12/25 | ❌ 不迁移 |
| `handlers/etl_storage/bk_log_json.py` | 390 | 12/25 | ❌ 不迁移 |
| `handlers/etl_storage/bk_log_regexp.py` | 380 | 12/25 | ❌ 不迁移 |
| `handlers/etl_storage/bk_log_text.py` | 226 | 12/25 | ❌ 不迁移 |
| `handlers/check_collector/checker/agent_checker.py` | 237 | 12/25 | ❌ 不迁移 |
| `constants.py` | 754 | 11/25 | ❌ 不迁移 |
| `handlers/etl/base.py` | 408 | 11/25 | ❌ 不迁移 |
| `handlers/collector_plugin/base.py` | 396 | 11/25 | ❌ 不迁移 |
| `handlers/etl/transfer.py` | 274 | 9/25 | ❌ 不迁移 |
| `handlers/archive.py` | 577 | 9/25 | ❌ 不迁移 |
| `handlers/itsm.py` | 214 | 9/25 | ❌ 不迁移 |
| `tasks/collector.py` | 576 | 9/25 | ❌ 不迁移 |
| `tasks/bkdata.py` | 279 | 8/25 | ❌ 不迁移 |
| `management/commands/`（3 个文件） | 1,535 | 8/25 | ❌ 不迁移 |

**评估结论：本批次所有文件均未达到迁移阈值（18 分），最高分 15 分。**

---

## 二、有条件迁移目标（15-17 分）

### 1. 错误码分层异常体系（15/25）

**源文件：** `exceptions.py`（430 行）

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 2/5 | 异常体系完全服务于 BK-LOG 业务 |
| **复用价值** | 2/5 | MODULE_CODE + ERROR_CODE 二级错误码编排模式可参考 |
| **独立性** | 3/5 | 仅依赖 `apps.exceptions.BaseException` 和 `ErrorCode` |
| **接口稳定性** | 4/5 | 异常类定义稳定 |
| **代码质量** | 4/5 | 分层清晰、命名规范 |

**有条件迁移说明：** 价值在于错误码分层设计模式（MODULE_CODE + ERROR_CODE 二级编码），而非具体异常类。单独迁移 ROI 不高。

---

## 三、不迁移模块说明

### ETL Storage 体系（5 个文件，12-14 分）

所有子类（delimiter/json/regexp/text）均继承 `EtlStorage`，基类大量依赖 `TransferApi`、`CollectorConfig` 等 Django Model 和内部 API。配置格式完全绑定 BK-LOG 的 Transfer 数据链路。V3/V4 双轨逻辑为过渡期兼容，非通用设计。

### ETL Handler（2 个文件，9-11 分）

纯粹的业务编排层，`EtlHandler.update_or_create` 方法超过 100 行，混合聚类逻辑、ITSM 审批、存储容量检查。

### Check Collector（2 个文件，12-13 分）

依赖 `Bcs`（K8s 客户端）、`JobApi`、特定 CRD/ConfigMap/DaemonSet 常量，与 BK-LOG 采集器架构强绑定。

### StorageHandler（13 分）

ES 集群管理与 `TransferApi`、`BkDataResourceCenterApi` 深度耦合，冷热分离、存储配额完全业务化。

### ArchiveHandler / ItsmHandler（9 分）

归档绑定 TransferApi 快照接口，ITSM 绑定 `BkItsmApi`。

### Tasks（8-9 分）

Celery 定时任务全部服务于 BK-LOG 业务逻辑。

### Management Commands（8 分）

运维专用命令（初始化 admin、初始化数据链路等），无通用性。

---

## 四、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| Strategy + Factory 组合 | `etl_storage/base.py` | `get_instance()` 动态加载 + `etl_config` 策略选择 |
| 时间格式映射表（60+ 种） | `etl_storage/base.py` | V3→V4 格式转换 |
| 错误码分层体系 | `exceptions.py` | MODULE_CODE + ERROR_CODE 二级编码 |
| 分步骤检查框架 | `bkunifylogbeat_checker.py` | `check_*` 步骤串联 + 结果收集 |
| Pod 轻量建模 | `bkunifylogbeat_checker.py` | `@dataclass` 定义 K8s 资源结构体 |
| JSON 递归展开 | `storage.py` | `flatten_json` 嵌套 dict/list 处理 |
| 索引日期排序 | `storage.py` | 解析索引名称日期后缀排序 |
| 并行检测模式 | `storage.py` | 批量集群连通性检测 |
| 批量 Upsert 模式 | `tasks/collector.py` | 先查再分类创建/更新 + 事务保证 |
| 脚本化检查框架 | `scripts/check.py` | `Result` 类步骤化检查结果收集 |
