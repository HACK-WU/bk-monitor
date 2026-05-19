# metadata 顶层配置 + Agents 迁移价值评估报告（批次 3）

> 评估范围：`bkmonitor/metadata/` 顶层文件 + agents/（6 个文件，约 1,930 行）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）

---

## 一、总览表

| 文件 | 行数 | 通用性 | 复用价值 | 独立性 | 接口稳定性 | 代码质量 | 总分 | 结论 |
|------|------|--------|----------|--------|------------|----------|------|------|
| `agents/diagnostic/metadata_diagnostic_agent.py` | 167 | 4 | 4 | 3 | 4 | 4 | **19** | ✅ 推荐迁移 |
| `admin.py` | 438 | 3 | 3 | 2 | 3 | 3 | 14 | ⚠️ 部分提取 |
| `health_check.py` | 786 | 2 | 3 | 2 | 3 | 3 | 13 | ❌ 不迁移（参考） |
| `migration_util.py` | 280 | 2 | 2 | 1 | 2 | 2 | 9 | ❌ 不迁移 |
| `config.py` | 120 | 2 | 1 | 2 | 3 | 2 | 10 | ❌ 不迁移 |
| `signals.py` | 82 | 1 | 1 | 1 | 2 | 2 | 7 | ❌ 不迁移 |

---

## 二、迁移目标：LLM 诊断 Agent 模板（19/25）

**源文件：** `agents/diagnostic/metadata_diagnostic_agent.py`

### 核心设计

三层架构 + Generator 流式输出的 AI Agent 诊断模板：

```python
class MetadataDiagnosisAgent:
    def diagnosis_flow(self, bk_data_id: int) -> Generator:
        """Generator 流式输出：进度反馈 → 错误处理 → 最终报告"""
        yield "status", {"stage": "metadata", "progress": 20, "message": "..."}
        yield "error", {"stage": "...", "message": "..."}
        yield "report", formatted_report

    def llm_analysis_engine(self, metadata_json: str) -> str:
        """调用 LLM 进行智能分析，内置指数退避重试"""
```

### 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 4/5 | Agent 架构、LLM 调用、Generator 流式输出模式通用 |
| **复用价值** | 4/5 | 可作为 AI Agent 诊断模板 |
| **独立性** | 3/5 | 依赖 LangChain/LLM Provider，可抽象 |
| **接口稳定性** | 4/5 | `diagnose` 接口清晰 |
| **代码质量** | 4/5 | 重试机制、错误处理、日志、类型注解完善 |

### 设计亮点

| 模式 | 说明 |
|------|------|
| **三层架构** | 数据获取 → LLM 分析 → 报告生成 |
| **Generator 流式输出** | yield "status"/"error"/"report"，调用方可实时获取进度 |
| **重试容错** | tenacity 指数退避（最多 4 次）+ JSON 解析容错 |
| **提示词模板化** | 从外部文件加载，支持动态变量替换 |

### 迁移范围

核心类 `MetadataDiagnosisAgent`，约 120 行。需抽象 `DataLinkInfoResource` 为 `DataProvider` 接口。

### 跨项目使用场景

| 场景 | 说明 |
|------|------|
| AI 辅助诊断 | 任意需要 LLM 辅助诊断的 Agent 场景 |
| 流式进度反馈 | 长时任务的实时进度展示 |
| 数据链路健康检查 | 自动化故障排查 |

---

## 三、有条件提取目标

### YamlJsonField（`admin.py`，14/25）

```python
class YamlJsonField(forms.CharField):
    """同时接受 YAML 和 JSON 输入，存储为 JSON，展示时转为格式化 JSON"""
```

通用 Django 表单字段组件，支持双格式输入 + 浏览器兼容性处理。约 30 行可独立提取。

---

## 四、设计参考索引

| 模式 | 来源 | 适用场景 |
|------|------|----------|
| Agent 三层架构 | `metadata_diagnostic_agent.py` | AI Agent 开发模板 |
| Generator 流式输出 | `metadata_diagnostic_agent.py` | 长时任务进度反馈 |
| LLM 重试容错 | `metadata_diagnostic_agent.py` | LLM 调用最佳实践 |
| 提示词模板化 | `metadata_diagnostic_agent.py` | Prompt 工程管理 |
| YamlJsonField | `admin.py` | Django 表单字段扩展 |
| Generation 版本控制 | `admin.py` | 实体版本管理 |
| Pydantic 状态模型 | `health_check.py` | 状态定义与校验 |
| 场景枚举 + 策略分发 | `health_check.py` | 多场景业务逻辑 |
