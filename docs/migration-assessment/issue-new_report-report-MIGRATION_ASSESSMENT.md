# alarm_backends/service/issue + new_report + report 迁移价值评估报告

> 评估范围：`bkmonitor/alarm_backends/service/issue/`（2 文件）+ `new_report/`（7 文件）+ `report/`（5 文件）
> 评估标准：通用性 / 复用价值 / 独立性 / 接口稳定性 / 代码质量（各 1-5 分，满分 25）
> 迁移目标：PythonCodeHub — 可复用、低耦合、易参考的通用 Python 代码

---

## 一、总览

| 模块 | 文件 | 总分 | 结论 |
|------|------|------|------|
| report | `render/dashboard.py` | 16/25 | ⚠️ 有条件迁移（Grafana 截图工具） |
| new_report | `handler/base.py` | 13/25 | ❌ 不迁移（模板方法可参考） |
| new_report | `factory.py` | 12/25 | ❌ 不迁移 |
| report | `tasks.py` | 11/25 | ❌ 不迁移 |
| new_report | `tasks.py` | 11/25 | ❌ 不迁移 |
| report | `handler.py` | 7/25 | ❌ 不迁移 |
| issue | `test.py` | 9/25 | ❌ 不迁移 |
| new_report | 4 个 handler 实现 | 9/25 | ❌ 不迁移 |

---

## 二、有条件迁移目标：Grafana 面板截图工具

**源文件：** `alarm_backends/service/report/render/dashboard.py`

**总分：16/25** — 剥离外部依赖后可成为通用工具

### 2.1 核心设计

```python
@dataclass
class RenderDashboardConfig:
    """仪表盘渲染配置"""
    bk_tenant_id: str
    bk_biz_id: int
    dashboard_uid: str
    panel_id: int | None = None
    width: int = 1200
    height: int = 500
    # ... 更多配置项

def generate_dashboard_url(config: RenderDashboardConfig) -> str:
    """根据配置生成 Grafana 仪表盘 URL"""

async def render_dashboard_panel(config: RenderDashboardConfig) -> bytes:
    """使用 pyppeteer 浏览器自动化截图，支持单面板和整仪表盘"""

async def wait_for_panel_render(page, config) -> None:
    """轮询等待所有面板加载完成，带超时机制"""
```

### 2.2 五维评分

| 维度 | 分数 | 说明 |
|------|------|------|
| **通用性** | 3/5 | Grafana 面板截图是监控/运维领域的通用需求 |
| **复用价值** | 3/5 | 任何使用 Grafana 的系统均可复用 |
| **独立性** | 2/5 | 依赖 pyppeteer、内部浏览器管理、Django settings |
| **接口稳定性** | 4/5 | `RenderDashboardConfig` + `render_dashboard_panel` 接口清晰 |
| **代码质量** | 4/5 | 配置 dataclass 设计合理，超时和错误处理完善 |

### 2.3 业务耦合清单

| 耦合点 | 处理方式 |
|--------|----------|
| `settings.BK_MONITOR_HOST` / `IS_CONTAINER_MODE` | 改为构造函数参数 |
| `os.environ.get('LAN_IP')` / `BK_MONITOR_KERNELAPI_PORT` | 改为构造函数参数 |
| `bkmonitor.browser.get_browser` | 替换为注入的浏览器工厂 |
| `core.errors.common.CustomError` | 替换为标准异常 |

### 2.4 迁移范围

- `RenderDashboardConfig` dataclass — 可直接复用
- `generate_dashboard_url()` — 需参数化配置
- `render_dashboard_panel()` + `wait_for_panel_render()` — 需注入浏览器工厂
- 预估工作量：3-4h

### 2.5 跨项目使用场景

| 场景 | 说明 |
|------|------|
| Grafana 报表 | 仪表盘自动生成图片用于报告 |
| 告警附图 | 告警通知中附带面板截图 |
| 监控看板 | 定时生成看板快照 |
| 审批截图 | 变更审批中附带监控截图 |

---

## 三、不迁移模块说明

### issue 模块

| 文件 | 不迁移原因 |
|------|-----------|
| `test.py` | 调试脚本，深度耦合 `StrategyIssueConfig`、`AlertDocument` 等内部模块 |

### new_report 模块

| 文件 | 不迁移原因 | 可参考设计 |
|------|-----------|-----------|
| `factory.py` | 仅 7 行有效代码，过薄 | 工厂模式 |
| `handler/base.py` | 耦合 `Report`/`ReportChannel` 等 Django ORM 模型 | 模板方法模式（`get_render_params` / `render` / `send_check`） |
| `handler/clustering.py` | 深度耦合日志搜索 API 和业务枚举 | — |
| `handler/dashboard.py` | 空实现桩文件 | — |
| `handler/scene.py` | 空实现桩文件 | — |
| `tasks.py` | 绑定 `Report`/`ReportChannel` 模型和报告工具函数 | 订阅检测与执行时间判断 |

### report 模块

| 文件 | 不迁移原因 |
|------|-----------|
| `handler.py` | 711 行"巨型"类，聚合截图/HTML 渲染/邮件发送/权限校验等全部逻辑，深度耦合 10+ 模块 |
| `tasks.py` | 混合多种定时任务，每个任务都重度依赖不同内部模块 |

---

## 四、迁移优先级汇总

| 优先级 | 文件 | 模块 | 总分 | 工作量 |
|--------|------|------|------|--------|
| **P2** | `render/dashboard.py` | report | 16/25 | 3-4h |
