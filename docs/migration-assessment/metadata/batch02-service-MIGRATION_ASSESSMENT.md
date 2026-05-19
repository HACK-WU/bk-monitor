# metadata Service 服务层迁移价值评估报告（批次 2）

> 评估范围：`bkmonitor/metadata/service/`（8 个文件，约 2,285 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `vm_short_link.py` | 682 | 9/25 | ❌ 不迁移 |
| `storage_details.py` | 437 | 9/25 | ❌ 不迁移 |
| `sync_metadata.py` | 298 | 8/25 | ❌ 不迁移 |
| `vm_storage.py` | 285 | 8/25 | ❌ 不迁移 |
| `space_redis.py` | 226 | 8/25 | ❌ 不迁移 |
| `data_source.py` | 169 | 8/25 | ❌ 不迁移 |
| `es_storage.py` | 79 | 8/25 | ❌ 不迁移 |
| `influxdb_instance.py` | 55 | 8/25 | ❌ 不迁移 |

**评估结论：8 个文件全部不迁移。** 整个 service 层是蓝鲸监控元数据的 CRUD 封装层，业务逻辑与 Django Model 高度交织，不存在可独立抽取的通用设计能力。

---

## 二、不迁移模块说明

| 文件 | 核心职责 | 不迁移原因 |
|------|---------|-----------|
| `vm_short_link.py` | VM 短链路 CRUD 生命周期 | 依赖 6 个 Django Model + 2 个内部工具 + 外部 API，无通用设计 |
| `storage_details.py` | 数据源+结果表+存储集群详情查询 | 依赖 10+ 个 Django Model + Kafka 客户端，纯查询聚合 |
| `sync_metadata.py` | 从 BKBase 同步集群元信息 | 标准 CRUD "查-建-更"模式，业务绑定极强 |
| `vm_storage.py` | VM 存储查询和路由管理 | 跨多 Model 的业务操作流程 |
| `space_redis.py` | ES/Doris 空间路由推送 Redis | 组装 Redis value + publish，深度依赖 Model |
| `data_source.py` | 数据源管理（transfer/kafka 集群） | Model update + consul 刷新 + GSE 路由下发 |
| `es_storage.py` | ES 索引查询 | 仅 3 个方法，全部委托 Model |
| `influxdb_instance.py` | InfluxDB 主机/集群记录管理 | 仅 55 行，纯 `update_or_create` 封装 |

---

## 三、设计参考索引

| 参考点 | 来源 | 说明 |
|--------|------|------|
| 批量操作前先校验再执行 | `vm_short_link.py` | 先拉取并校验整批数据，避免部分写入后失败 |
| 幂等 upsert 模式 | `vm_short_link.py` | `update_or_create` 保证重复执行安全 |
| overwrite 破坏性开关 | `vm_short_link.py` | 默认拒绝覆盖，显式传 `overwrite=True` 才允许 |
| 策略分发模式 | `storage_details.py` | `type_func_map` 按集群类型分发到不同处理函数 |
| 写入开关控制 | `sync_metadata.py` | `settings.ENABLE_SYNC_*` 控制是否实际写库 |
