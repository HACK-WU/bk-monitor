# apm 常量 + DeepFlow 迁移价值评估报告（批次 3）

> 评估范围：`apm/constants.py`（736 行）、`apm/core/deepflow/base.py`（519 行）、`apm/core/deepflow/constants.py`（29 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|--------|----------|--------|------------|----------|------|------|
| `deepflow/constants.py` | 4 | 3 | 5 | 5 | 4 | **21** | ✅ 强烈推荐迁移 |
| `deepflow/base.py` | 3 | 4 | 3 | 3 | 3 | 16 | ⚠️ 部分迁移（剥离后） |
| `constants.py` | 2 | 2 | 2 | 3 | 3 | 12 | ❌ 不迁移 |

---

## 二、迁移目标：DeepFlow L7 协议常量（21/25）

**源文件：** `apm/core/deepflow/constants.py`

### 核心设计

定义 DeepFlow L7 应用层协议的整数编号常量，涵盖 16 种协议：

```python
HTTP_1 = 20
HTTP_2 = 21
GRPC = 40
DUBBO = 41
MYSQL = 61
POSTGRESQL = 62
REDIS = 81
MONGODB = 82
KAFKA = 101
MQTT = 102
DNS = 120
# ... 等
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | L7 协议编号是 DeepFlow/eBPF 网络可观测领域的通用常量 |
| **复用价值** | 3/5 | 任何对接 DeepFlow l7_flow_log 的系统都需要 |
| **独立性** | 5/5 | 纯整数常量定义，零外部依赖 |
| **接口稳定性** | 5/5 | 协议编号由 DeepFlow 开源项目定义，极少变动 |
| **代码质量** | 4/5 | 定义清晰；建议迁移时改为 IntEnum |

### 迁移范围

整文件 29 行，直接迁移。建议改为 `IntEnum` 枚举类。

---

## 三、有条件迁移目标：DeepFlow 协议解析器（16/25）

**源文件：** `apm/core/deepflow/base.py`

### 核心设计

- **`Span` 类**（~40 行）：轻量级 OTel Span 数据模型，提供 `span_to_dict()` 序列化
- **`EBPFHandler` 类**（~400 行）：基于策略模式的协议解析器，按 `l7_protocol` 分发到 `set_http`/`set_mysql`/`set_grpc` 等 10 种协议解析方法
- **`l7_flow_log_to_resource_span()`**：主入口，将 DeepFlow l7_flow_log 转换为 OTel 格式

### 业务耦合清单

| 耦合项 | 可剥离性 |
|--------|----------|
| `apm_web.constants.EbpfSignalSourceType` | 可剥离，改为内部定义 |
| `apm_web.constants.EbpfTapSideType` | 可剥离，改为内部定义 |
| `constants.apm.SpanKind` | 可剥离，使用标准 OTel SpanKind |
| `django.conf.settings.TIME_ZONE` | 可剥离，改为参数传入 |

### ⚠️ 已发现 Bug

1. `put_bool_value_to_map`（第 126-127 行）逻辑缺陷：永远返回 False
2. 第 503 行：Redis 协议错误地调用了 `set_mysql`，应为 `set_redis`

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| eBPF 数据采集 | DeepFlow l7_flow_log 解析 |
| 网络 Trace 构建 | 从网络流量构建 OTel Span |
| 协议识别 | L7 协议分类和属性提取 |

---

## 四、不迁移模块说明

### `apm/constants.py`（12/25）

736 行中约 300 行（40%）是与蓝鲸计算平台清洗规则和平台配置的硬编码数据。深度依赖 Django settings、TextChoices、翻译框架。整体与蓝鲸 APM 业务强绑定，不迁移。

**可参考设计：** `ApmCacheConfig` 的"类型枚举 + 配置容器"模式（key 模板 + 过期时间统一管理）。

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| L7 协议编号枚举 | `deepflow/constants.py` | eBPF/网络可观测 |
| 轻量级 Span 数据模型 | `deepflow/base.py` | 无 ORM 依赖的 OTel 数据结构 |
| 协议解析策略模式 | `deepflow/base.py` | 按类型分发的解析器架构 |
| 缓存配置容器模式 | `constants.py` | 缓存 key 模板 + TTL 统一管理 |
