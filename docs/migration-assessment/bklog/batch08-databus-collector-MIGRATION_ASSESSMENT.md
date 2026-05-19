# log_databus 采集器核心模块迁移价值评估报告（批次 8）

> 评估范围：`log_databus/handlers/collector/` + `handlers/collector_scenario/` + `handlers/collector_handler/`（15 个文件，约 8,722 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `collector_scenario/utils.py` | 106 | **20/25** | ✅ 推荐迁移 |
| `collector_scenario/base.py` | 503 | **19/25** | ✅ 推荐迁移 |
| `collector_scenario/kafka.py` | 333 | **19/25** | ✅ 推荐迁移 |
| `collector_scenario/custom_define/custom.py` | 326 | **19/25** | ✅ 推荐迁移 |
| `collector_scenario/syslog.py` | 267 | **18/25** | ✅ 推荐迁移 |
| `collector_scenario/redis_slowlog.py` | 206 | **18/25** | ✅ 推荐迁移 |
| `collector_scenario/row.py` | 331 | 17/25 | ⚠️ 有条件迁移 |
| `collector_scenario/section.py` | 340 | 17/25 | ⚠️ 有条件迁移 |
| `collector_scenario/wineventlog.py` | 434 | 17/25 | ⚠️ 有条件迁移 |
| `collector_scenario/custom.py` | 137 | 17/25 | ⚠️ 有条件迁移 |
| `collector_scenario/client.py` | 64 | 15/25 | ⚠️ 有条件迁移 |
| `collector/base.py` | 1,709 | 14/25 | ❌ 不迁移 |
| `collector/host.py` | 1,410 | 11/25 | ❌ 不迁移 |
| `collector/k8s.py` | 2,370 | 11/25 | ❌ 不迁移 |
| `collector_handler/log.py` | 639 | 14/25 | ❌ 不迁移 |

---

## 二、迁移目标详细分析（≥18 分）

### 1. 采集参数转换工具集（20/25）

**源文件：** `collector_scenario/utils.py`（106 行）

```python
def deal_collector_scenario_param(params):
    """前端条件格式 → 采集器下发格式（正向转换）"""

def convert_filters_to_collector_condition(filters):
    """采集器下发格式 → 前端条件格式（反向转换）"""

def build_es_option_type(field, es_version):
    """根据 ES 版本生成兼容的字段类型配置"""
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 过滤条件双向转换是日志采集领域的通用需求 |
| **复用价值** | 4/5 | 任何日志过滤条件配置系统均可复用 |
| **独立性** | 4/5 | 仅依赖两个常量枚举，无外部服务依赖 |
| **接口稳定性** | 4/5 | 输入输出格式明确 |
| **代码质量** | 4/5 | 函数职责单一，异常处理完善 |

**迁移范围：** 整个文件（106 行），需替换枚举为通用参数化。

### 2. 采集场景基类与工厂模式（19/25）

**源文件：** `collector_scenario/base.py`（503 行）

```python
class CollectorScenario:
    @staticmethod
    def get_instance(collector_scenario_id):
        """工厂方法：根据枚举值动态加载采集场景实现"""

    def update_or_create_data_id(self, ...):
        """数据源创建/更新"""

    def get_edge_transport_output_params(self, ...):
        """边缘传输 Kafka 输出参数构建"""

    def _add_labels(self, template, labels):
        """标签与元数据注入"""
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 采集场景抽象接口 + 工厂模式通用 |
| **复用价值** | 4/5 | 多采集场景策略切换是通用架构 |
| **独立性** | 3/5 | 依赖 TransferApi、NodeApi、Django ORM |
| **接口稳定性** | 4/5 | 基类接口设计稳定 |
| **代码质量** | 4/5 | 模板方法模式运用得当 |

### 3. Kafka 采集场景（19/25）

**源文件：** `collector_scenario/kafka.py`（333 行）

Kafka 消费者配置构建 + `parse_steps()` 反向解析，支持 SSL、认证、多主机。

### 4. 自定义类型注册器（19/25）

**源文件：** `collector_scenario/custom_define/custom.py`（326 行）

```python
CUSTOM_MAP = {}

def register(cls):
    """@register 装饰器：将自定义类型注册到全局注册表"""

class CustomMeta:
    """自定义类型元类：etl_params, etl_config, fields, after_hook"""
```

同时包含 OTLP Log/Trace 完整字段定义。

### 5. Syslog 采集场景（18/25）

**源文件：** `collector_scenario/syslog.py`（267 行）

Syslog 过滤规则构建（支持 AND/OR 逻辑运算符），TCP/UDP 协议配置。

### 6. Redis 慢日志采集场景（18/25）

**源文件：** `collector_scenario/redis_slowlog.py`（206 行）

Redis 连接配置（多主机列表、密码认证、密码文件三种认证方式），标准字段集定义。

---

## 三、有条件迁移目标（15-17 分）

| 文件 | 总分 | 可提取价值 |
|------|------|-----------|
| `collector_scenario/row.py` | 17 | 行日志采集场景，`get_subscription_steps` / `parse_steps` 双向转换模式 |
| `collector_scenario/section.py` | 17 | 段日志采集场景，多行日志配置模式（multiline_pattern/max_lines/timeout） |
| `collector_scenario/wineventlog.py` | 17 | Windows 事件日志字段定义（约 25 个字段） |
| `collector_scenario/custom.py` | 17 | 最小场景实现参考模板 |
| `collector_scenario/client.py` | 15 | 最小实现参考（64 行） |

---

## 四、不迁移模块说明

| 文件 | 总分 | 不迁移原因 |
|------|------|-----------|
| `collector/base.py` | 14 | 与 Django ORM（6+ 模型）深度耦合，强依赖 TransferApi、NodeApi、IAM。1,709 行约 80% 是业务逻辑 |
| `collector/host.py` | 11 | 与蓝鲸节点管理（NodeApi）深度绑定，1,410 行几乎全部是业务代码 |
| `collector/k8s.py` | 11 | 2,370 行，与 BCS API、Kubernetes client 深度耦合 |
| `collector_handler/log.py` | 14 | 日志采集列表查询处理器，与 Django ORM 深度耦合 |

---

## 五、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 工厂模式 + 动态加载 | `collector_scenario/base.py` | 通用策略工厂 |
| 注册器模式（@register） | `collector_scenario/custom_define/custom.py` | 插件系统、协议处理器注册 |
| 订阅步骤双向转换 | 所有 `collector_scenario/*.py` | 配置持久化场景 |
| 过滤条件构建器 | `collector_scenario/utils.py` | 通用查询条件构建 |
| 边缘传输参数构建 | `collector_scenario/base.py` | 数据管道配置 |
| 标签与元数据注入 | `collector_scenario/base.py` | Agent 配置模板系统 |
| 链式处理模式（RETRIEVE_CHAIN） | `collector/base.py` | 数据补全管道 |
| 并发查询封装 | `collector/base.py` | 多数据源聚合查询 |
| 批量分片 + 重试 | `collector/base.py` | 分片批量查询容错 |
| ES 字段类型兼容 | `collector_scenario/utils.py` | 多版本存储适配 |
