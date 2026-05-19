# apm Core 配置层迁移价值评估报告（批次 2）

> 评估范围：`apm/core/application_config.py`（688 行）、`apm/core/platform_config.py`（551 行）、`apm/core/cluster_config.py`（53 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|--------|----------|--------|------------|----------|------|------|
| `application_config.py` | 1 | 2 | 1 | 3 | 3 | 10 | ❌ 不迁移 |
| `platform_config.py` | 1 | 2 | 1 | 3 | 3 | 10 | ❌ 不迁移 |
| `cluster_config.py` | 2 | 2 | 2 | 3 | 4 | 8 | ❌ 不迁移 |

**评估结论：三个文件均属于 APM 核心业务配置层，全部不建议迁移。**

---

## 二、不迁移模块说明

### `application_config.py`（10/25）

`ApplicationConfig` 是 APM 应用配置的"聚合器"，深度耦合 **11 个 Django Model**（ApmApplication, ApdexConfig, SamplerConfig, LicenseConfig, QpsConfig, ProbeConfig, CustomServiceConfig, NormalTypeValueConfig, SubscriptionConfig, ApmInstanceDiscover, ApmMetricDimension）以及数十项 settings 常量和内部 API。

- 每个 `get_*_config()` 方法独立从 DB 读取一种配置
- `get_application_config()` 作为聚合方法拼接所有子配置为 Jinja2 模板上下文
- 双通道下发：`refresh()` 走节点管理，`refresh_k8s()` 走 K8s Secret

### `platform_config.py`（10/25）

`PlatformConfig` 管理 APM 平台级配置（apdex、采样率、license、SpanKind 维度等），深度耦合 Django Model、Kubernetes Python Client、BcsKubeClient 等。

- K8s Secret 的 gzip + base64 编码下发模式有一定通用性
- 但 `BkCollectorClusterConfig.deploy_to_k8s_with_hash`（父类）已提供更完善的通用实现

### `cluster_config.py`（8/25）

`BkCollectorInstaller` 仅 53 行，功能是检查 K8s Deployment 是否存在并将集群 ID 写入 Redis。体量太小且功能过于专用。

---

## 三、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 配置聚合模式 | `application_config.py` | 多子配置拼装为模板上下文 |
| K8s Secret Hash 分桶批量部署 | `platform_config.py`（父类） | 大规模配置下发 |
| K8s Secret gzip+base64 创建/更新 | `platform_config.py` | 单条配置下发 |
| 生成器工厂模式 | `cluster_config.py` | 共享资源的工厂生成器 |
| 节点管理订阅生命周期 | 两个配置文件 | 节点管理插件配置下发 |
