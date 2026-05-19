# bklog 度量/脱敏/审计/采集/提取迁移价值评估报告（批次 5）

> 评估范围：`log_measure/` + `log_desensitize/` + `log_audit/` + `log_bcs/` + `ai_assistant/` + `bk_log_admin/` + `log_extract/`（75 个文件，约 13,913 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 总分 | 结论 |
|------|------|------|------|
| `log_desensitize/handlers/desensitize_operator/base.py` | 36 | **23/25** | ✅ 强烈推荐迁移 |
| `log_desensitize/handlers/desensitize_operator/mask_shield.py` | 77 | **21/25** | ✅ 强烈推荐迁移 |
| `log_desensitize/handlers/desensitize_operator/text_replace.py` | 70 | **21/25** | ✅ 强烈推荐迁移 |
| `log_desensitize/handlers/desensitize.py` | 691 | **21/25** | ✅ 强烈推荐迁移 |
| `log_desensitize/utils.py` | 63 | **20/25** | ✅ 推荐迁移 |
| `log_measure/utils/es.py` | 1,126 | **20/25** | ✅ 推荐迁移 |
| `log_extract/handlers/local.py` | 149 | **20/25** | ✅ 推荐迁移 |
| `log_measure/handlers/metrics.py` | 297 | **18/25** | ✅ 推荐迁移 |
| `log_extract/handlers/thread.py` | 128 | **18/25** | ✅ 推荐迁移 |
| `log_measure/utils/metric.py` | 150 | 16/25 | ⚠️ 有条件迁移 |
| `log_extract/handlers/extract.py` | 241 | 17/25 | ⚠️ 有条件迁移 |
| `log_extract/permission.py` | 41 | 17/25 | ⚠️ 有条件迁移 |
| `bk_log_admin/permission.py` | 41 | 17/25 | ⚠️ 有条件迁移 |
| 其余 62 个文件 | ~11,030 | ≤14/25 | ❌ 不迁移 |

---

## 二、迁移目标详细分析（≥18 分）

### 1. 脱敏算子抽象基类（23/25）⭐ 最高分

**源文件：** `log_desensitize/handlers/desensitize_operator/base.py`（36 行）

```python
class DesensitizeMethodBase(ABC):
    """策略模式：文本变换算子的抽象基类"""
    ParamsSerializer = None  # 参数校验器声明
    @abstractmethod
    def transform(self, target_text, context=None) -> str: ...
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 5/5 | 纯抽象基类，零业务耦合 |
| **复用价值** | 5/5 | 策略模式经典实现，可作为文本处理算子框架基础 |
| **独立性** | 4/5 | 仅依赖 `abc` 标准库 |
| **接口稳定性** | 5/5 | `transform(target_text, context)` 覆盖所有文本变换场景 |
| **代码质量** | 5/5 | 职责单一，符合 SOLID 原则 |

### 2. 掩码屏蔽算子（21/25）

**源文件：** `log_desensitize/handlers/desensitize_operator/mask_shield.py`（77 行）

保留前 N 位 / 后 N 位，中间用指定符号替换。支持手机号、身份证、银行卡号脱敏。

### 3. Jinja2 模板替换算子（21/25）

**源文件：** `log_desensitize/handlers/desensitize_operator/text_replace.py`（70 行）

使用 Jinja2 沙箱环境渲染模板，支持正则捕获组作为模板变量，惰性初始化 + pickle 序列化支持。

### 4. 脱敏引擎核心（21/25）

**源文件：** `log_desensitize/handlers/desensitize.py`（691 行）

```python
class DesensitizeHandler:
    """流水线式文本处理引擎：规则列表 → 正则匹配 → 子串合并 → 算子处理"""
    def transform_text(self, text, rules): ...
    def transform_dict(self, data, rules): ...
```

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | 脱敏引擎核心逻辑具有通用性 |
| **复用价值** | 5/5 | 流水线处理 + 正则匹配 + 子串合并算法设计精良 |
| **独立性** | 3/5 | DesensitizeHandler 类相对独立，RuleHandler 强依赖 Django Model |
| **接口稳定性** | 4/5 | `transform_text()` / `transform_dict()` 接口清晰 |
| **代码质量** | 5/5 | 子串位置合并、高亮支持实现精巧 |

### 5. 嵌套字典展平/合并（20/25）

**源文件：** `log_desensitize/utils.py`（63 行）

```python
def expand_nested_data(data):   # {"a": {"b": 1}} → {"a.b": 1}
def merge_nested_data(data):    # {"a.b": 1} → {"a": {"b": 1}}
```

零业务依赖，递归实现清晰。

### 6. ES 全版本指标映射库（20/25）

**源文件：** `log_measure/utils/es.py`（1,126 行）

覆盖 ES 0.90.x 到 7.x 全版本的指标定义，版本适配器模式 `stats_for_version(version)`。

### 7. Greenlet 兼容 Local 对象（20/25）

**源文件：** `log_extract/handlers/local.py`（149 行）

兼容 Greenlet 和原生线程的 Local 对象，零业务依赖。

### 8. 指标采集框架（18/25）

**源文件：** `log_measure/handlers/metrics.py`（297 行）

```python
def register_metric(fn):           # 装饰器：为方法附加元数据
class BaseMetricCollector:          # 自动发现注册的指标方法
class Metric:                       # to_prometheus_text() 维度标签格式化
```

### 9. 线程池 + 上下文传播（18/25）

**源文件：** `log_extract/handlers/thread.py`（128 行）

继承 `multiprocessing.pool.ThreadPool`，自动传播 thread-local 上下文、时区、语言到工作线程。

---

## 三、不迁移模块说明

| 模块 | 不迁移原因 |
|------|-----------|
| `log_measure/metric_collectors/`（13 个文件） | 全部深度耦合 bklog 业务模型 |
| `log_audit/`（4 个文件） | 硬编码 URL 正则映射表，完全绑定 bklog API 路由 |
| `log_bcs/`（6 个文件） | BCS 薄封装层，`k8s.py` 存在 bug |
| `ai_assistant/`（7 个文件） | 强依赖 ai_agent 框架，完全绑定 bklog 日志检索 |
| `bk_log_admin/`（8 个文件） | 业务 CRUD handler |
| `log_extract/` 业务 handler | 深度耦合 Django Model、IAM、JOB 平台 API |

---

## 四、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| 策略模式（Strategy） | `desensitize_operator/base.py` | 文本处理算子框架 |
| 流水线模式（Pipeline） | `desensitize.py` | 规则→匹配→合并→算子→拼接 |
| 版本适配器 | `es.py` | 多版本 ES 指标采集 |
| 装饰器元编程 | `metrics.py` | 指标自动注册与发现 |
| Thread-local 上下文传播 | `local.py` + `thread.py` | Greenlet 兼容的并发上下文 |
| 嵌套数据展平 | `utils.py` | 配置处理、ES 文档转换 |
| Jinja2 沙箱渲染 | `text_replace.py` | 安全模板渲染 |
| 正则匹配 + 重叠子串合并 | `desensitize.py` | 文本搜索与替换 |
