# BK-Monitor AI 知识库

> BK-Monitor 项目的 AI 辅助开发知识体系和工具集

[![Git](https://img.shields.io/badge/git-bkmonitor%2Fai--docs-blue)](https://git.woa.com/bkmonitor/ai-docs)
[![License](https://img.shields.io/badge/license-Internal-green)]()

---

## 📚 仓库结构

```
ai-docs/
├── bk-monitor/              # BK-Monitor 项目知识体系
│   ├── AGENTS.md            # ⭐ AI 任务执行入口协议
│   ├── AI知识体系.md        # 项目知识体系总览
│   ├── Agent路径使用指南.md  # 路径变量与配置加载规范
│   ├── docs/                # 技术文档
│   │   └── 告警后台(alarm_backends)/  # 告警后台8个核心模块文档
│   └── scenarios/           # 场景化知识体系
│       ├── AI-RULES.md      # 场景知识体系 AI 执行规则（详细版）
│       ├── spec-kit-rules.md # Spec-Kit AI 规则
│       ├── code-review/     # 代码审查场景
│       ├── coding/          # 编码开发场景
│       ├── troubleshooting/ # 问题排查场景
│       └── default/         # 默认通用场景
├── publish_skill/           # ⭐ 初始化时应扫描的共享技能库（git 追踪）
│   ├── gtm-workflow/        # GTM 工作流技能
│   └── create-skill/        # 创建技能的技能
├── skills/                  # 本地私有技能库（gitignored，不入库）
│   ├── code-review/         # 代码审查技能
│   ├── k8s-pod-exec/        # K8s Pod 执行技能
│   ├── log-searcher/        # 日志检索技能
│   └── qywx-bot-notifier/   # 企业微信机器人通知技能
├── rules/                   # 全局规则
│   ├── path-variables.md    # 路径变量规范
│   └── config-init-guide.md # 配置初始化指南
└── .config/                 # 配置文件（私有，不入库）
```

---

## 🎯 核心功能

### 1. 场景化知识体系

**场景自动识别**：AI 根据用户请求自动识别场景并加载对应知识

| 场景 | 触发关键词 | 说明 |
|-----|-----------|------|
| **code-review** | PR、pull request、代码审查、review | GitHub PR 代码审查 |
| **coding** | 开发、实现、修复、fix、feat、重构、优化 | 编码开发和功能实现 |
| **troubleshooting** | 排查、故障、报错、异常、debug、为什么 | 问题排查和诊断 |
| **default** | 文档、更新、配置、其他未匹配任务 | 通用场景（兜底） |

**详细文档**：
- 场景体系：[bk-monitor/scenarios/README.md](bk-monitor/scenarios/README.md)
- 识别规则：[bk-monitor/scenarios/scenario-identification-rules.md](bk-monitor/scenarios/scenario-identification-rules.md)
- AI 执行规则：[bk-monitor/scenarios/AI-RULES.md](bk-monitor/scenarios/AI-RULES.md)

### 2. 技能库

**可发布共享技能**（`publish_skill/`，git 追踪，可跨项目分发）：

- Agent 初始化时应主动扫描 `publish_skill/*/SKILL.md`
- 扫描后将技能名称和用途记录到上下文，后续任务命中时优先加载对应技能
- 这些技能属于仓库内可用能力，不需要用户再次手动声明目录位置

| 技能 | 功能 | 文档 |
|-----|------|------|
| **gtm-workflow** | TAPD 单据和 GitHub PR 工作流 | [publish_skill/gtm-workflow/SKILL.md](publish_skill/gtm-workflow/SKILL.md) |
| **create-skill** | 创建新技能的指南 | [publish_skill/create-skill/SKILL.md](publish_skill/create-skill/SKILL.md) |
| **bkmonitor-assistant-triage** | 蓝鲸监控助手前置分诊（给前线助手提效：咨询/排查分流 + 知识库经验匹配，默认产出"对外可投放"的指引或排障小结，仅检索不执行） | [publish_skill/bkmonitor-assistant-triage/SKILL.md](publish_skill/bkmonitor-assistant-triage/SKILL.md) |

**本地私有技能**（`skills/`，gitignored，仅本地使用）：

| 技能 | 功能 |
|-----|------|
| **code-review** | GitHub PR 代码审查 |
| **k8s-pod-exec** | K8s 集群命令执行与调试 |
| **log-searcher** | 蓝鲸监控日志检索与分析 |
| **qywx-bot-notifier** | 企业微信机器人消息通知 |

### 3. 技术文档库

**BK-Monitor 核心模块文档**（告警后台 alarm_backends）：

| 模块 | 职责 |
|------|------|
| **access** | 数据接入、去重、窗口管理 |
| **detect** | 异常检测、二次确认 |
| **nodata** | 无数据告警检测 |
| **trigger** | 告警触发判断 |
| **alert** | 告警生成、状态管理、CMDB 丰富 |
| **converge** | 告警收敛、降噪 |
| **fta_action** | 动作执行、通知发送 |
| **scheduler** | 定时任务调度 |

**文档索引**：[bk-monitor/docs/告警后台(alarm_backends)/modules/README.md](bk-monitor/docs/告警后台(alarm_backends)/modules/README.md)

---

## 🚀 快速开始

### 用户如何让 Agent 初始化知识库

本仓库采用**用户触发式初始化**，不要求 Agent 先自动发现仓库入口。

用户首次接入时，只需要完成两步：

1. 将本仓库拉取到项目代码目录下，并按所使用的 Agent 习惯命名目录
2. 把本 `README.md` 交给 Agent，并明确要求“基于 README 完成知识库初始化”

### 不同 Agent 的推荐目录名

| Agent | 推荐目录名 | 说明 |
|------|-----------|------|
| Cursor | `.cursor` | 适合直接作为项目目录下的 Cursor 知识库目录使用 |
| CodeBuddy | `.codebuddy` | 适合直接作为项目目录下的 CodeBuddy 知识库目录使用 |
| 其他 Agent | `ai-docs` 或自定义目录名 | 只要能明确把对应目录下的 `README.md` 交给 Agent 即可 |

**挂载后的目录形态示例**：

```text
# Cursor
project-root/
└── .cursor/
    └── README.md

# CodeBuddy
project-root/
└── .codebuddy/
    └── README.md
```

**推荐对 Agent 说的话**：

```text
我已将这个知识库仓库拉取到项目目录下，请先阅读该目录下的 README.md，
基于 README 完成知识库初始化。初始化完成后，再继续处理我的具体任务。
```

**按 Agent 的说法示例**：

```text
# Cursor
我已将知识库挂载到项目目录的 .cursor 下，请先阅读 .cursor/README.md，
基于 README 完成知识库初始化，再继续处理我的任务。

# CodeBuddy
我已将知识库挂载到项目目录的 .codebuddy 下，请先阅读 .codebuddy/README.md，
基于 README 完成知识库初始化，再继续处理我的任务。
```

### Agent 首次初始化协议（强制）

如果你是收到本 `README.md` 的 AI Agent，首次接入本知识库时，必须按以下顺序执行：

1. **确认知识库根目录**
   - 以当前 `README.md` 所在目录作为知识库根目录
   - 后续所有文档路径都以该目录为基准解析

2. **读取配置初始化规则**
   - 读取 `rules/config-init-guide.md`
   - 按文档中的检测策略识别 `bk-monitor` 代码仓库路径
   - 默认将当前知识库根目录下的 `.config/` 作为 `{PRIVATE_CONFIG_DIR}`

3. **检查或生成配置文件**
   - 检查 `{PRIVATE_CONFIG_DIR}/bk-monitor-config.json` 是否存在
   - 默认情况下，该路径等价于 `.config/bk-monitor-config.json`
   - 若不存在，参考 `.config/README.md` 和 `.config/bk-monitor-config.json.example`
   - 若仍无法自动完成，向用户索取最少必要信息后再继续

4. **加载路径变量规范**
   - 读取 `rules/path-variables.md`
   - 在后续任务中使用路径变量，禁止硬编码个人路径

5. **扫描可用共享技能**
   - 检查 `publish_skill/` 目录下的可用技能
   - 优先读取各技能目录中的 `SKILL.md`
   - 当用户任务与技能能力匹配时，优先加载对应技能

6. **进入领域执行协议**
   - 读取 `bk-monitor/AGENTS.md`
   - 后续再按场景识别、场景规则加载、任务执行的流程继续

### 初始化完成判定

满足以下条件，才算知识库初始化完成：

- 已确认知识库根目录
- 已获得 `bk-monitor` 本地代码仓库路径
- 已能读取或生成 `{PRIVATE_CONFIG_DIR}/bk-monitor-config.json`
- 已理解并加载 `rules/path-variables.md`
- 已扫描 `publish_skill/` 下的可用共享技能
- 已进入 `bk-monitor/AGENTS.md`，或已明确下一步要进入该文件

在初始化完成前，**不要直接进入业务任务执行阶段**。

### 初始化失败时怎么办

如果自动检测失败，按以下顺序回退：

1. 无法识别 `bk-monitor` 本地仓库路径
   - 询问用户提供本地代码仓库路径

2. 无法生成 `{PRIVATE_CONFIG_DIR}/bk-monitor-config.json`
   - 引导用户参考 `.config/bk-monitor-config.json.example`
   - 至少补全 `local.bk_monitor_repo`

3. 用户不希望将敏感配置放在知识库目录下
   - 允许用户显式覆盖 `{PRIVATE_CONFIG_DIR}`
   - 覆盖后统一从新的私有配置目录读取配置文件

4. 任一步骤失败且缺少必要信息
   - 明确告知用户初始化尚未完成
   - 不要跳过初始化直接处理具体任务

### AI 使用方式

1. **完成初始化后自动识别场景**

AI 会根据用户请求自动识别场景：

```
用户：帮我 review 一下 PR #9532
→ AI 自动识别为 code-review 场景
→ 加载 scenarios/code-review/ 和 skills/code-review/
→ 执行代码审查
```

2. **主动加载场景**

```
@scenarios/code-review  # 加载代码审查场景
@publish_skill/gtm-workflow  # 加载共享工作流技能
@skills/k8s-pod-exec         # 加载本地私有技能
```

3. **查看文档**

```
查看告警后台 access 模块的文档
→ AI 读取 bk-monitor/docs/告警后台(alarm_backends)/modules/access/
```

### 开发者使用方式

**目录命名约定**：

- 如果你是 Cursor Agent：将本知识库目录重命名为项目目录下的 `.cursor/`
- 如果你是 CodeBuddy Agent：将本知识库目录重命名为项目目录下的 `.codebuddy/`
- 如果你是其他 Agent：可将本知识库目录命名为 `ai-docs/` 或与你的产品约定一致的目录名

> 本 README 假设仓库已经被拉取到本地，因此这里不再重复描述获取仓库的命令，只约定挂载后的目录命名方式。

**更新文档**：
```bash
cd .cursor   # 或 .codebuddy / ai-docs
# 编辑文档...
git add .
git commit -m "docs: 更新说明"
git push origin master
```

---

## 📖 文档规范

### 场景文档结构

```
scenarios/{scenario-name}/
├── README.md           # 场景索引（简洁）
├── SKILL.md           # 场景规范（如有技能迁移）
├── rules/             # 场景规则
│   └── *.md
└── docs/              # 场景文档
    └── *.md
```

### 技能文档结构

```
skills/{skill-name}/
├── SKILL.md           # 技能核心定义
├── references/        # 详细参考文档
│   └── *.md
└── tools/             # 技能工具
    ├── README.md
    └── *.py / *.sh
```

### 技术文档结构

```
bk-monitor/docs/{module}/
├── README.md          # 模块索引
└── {topic}.md         # 主题文档
```

---

## 🔧 AI Agent 工具适配规范

### 设计理念

本知识体系采用**语义化工具描述**，不绑定特定 AI Agent 实现。任何 Agent 加载后可根据自身工具集进行适配。

### 核心工具语义映射表

| 语义功能 | 标准工具名 | 常见别名 | 说明 |
|---------|-----------|---------|------|
| 执行命令 | `execute_command` | `run_terminal_cmd`, `shell`, `bash` | 执行 Shell 命令 |
| 搜索文件 | `search_file` | `glob_file_search`, `find_files` | 按文件名模式查找 |
| 搜索内容 | `search_content` | `codebase_search`, `grep`, `ripgrep` | 按文本/正则搜索 |
| 读取文件 | `read_file` | `read`, `cat`, `get_file` | 读取文件内容 |
| 写入文件 | `write_to_file` | `write`, `save_file`, `create_file` | 写入/创建文件 |
| 列出目录 | `list_dir` | `ls`, `list_directory` | 列出目录结构 |

### Agent 适配指南

#### 如果你是 AI Agent

收到用户转交的本 `README.md` 后，请：

1. **工具映射**：将文档中的工具名映射到你的实际工具
   ```python
   # 示例：文档中的 execute_command 映射到你的工具
   文档: execute_command(command="date")
   映射: 你的工具名(参数...) 
   ```

2. **语义理解**：关注工具的**语义功能**，而非具体名称
   - 看到 `search_file` → 理解为"按文件名查找文件"
   - 看到 `search_content` → 理解为"在文件中搜索文本"

3. **参数适配**：根据你的工具接口调整参数格式
   ```python
   # 文档示例
   search_file(target_directory="/path", pattern="*.py", recursive=true)
   
   # 如果你的工具接口不同，请适配
   your_search_tool(path="/path", glob="*.py", include_subdirs=true)
   ```

4. **初始化优先**：先完成本 README 的初始化协议，再进入 `bk-monitor/AGENTS.md` 处理具体任务

#### 如果你是文档编写者

编写文档时，请：

1. **使用标准工具名**：优先使用"标准工具名"列中的名称
2. **注释语义功能**：在复杂场景添加注释说明意图
   ```python
   # 查找所有 Python 文件（使用文件搜索工具）
   search_file(target_directory="/path", pattern="*.py")
   ```

3. **避免硬编码工具名**：在描述性文本中使用语义描述
   - ❌ "使用 execute_command 工具执行..."
   - ✅ "执行 Shell 命令..."

### 路径规范

**通用原则**（适用于所有 Agent）：

- ✅ **优先使用绝对路径**：通过路径变量 `{AI_DOCS_ROOT}` 组合出完整路径
- ✅ **使用工具查找**：通过文件搜索工具获取准确路径
- ❌ **避免相对路径**：不同 Agent 的工作目录可能不同

路径变量的实际值由配置文件提供，详见 [rules/path-variables.md](rules/path-variables.md)。

**示例**：
```bash
# ✅ 路径变量（推荐）
{AI_DOCS_ROOT}/skills/code-review/tools/review_pr.py

# ✅ 使用工具查找（跨 Agent 通用）
[使用文件搜索工具] pattern="review_pr.py" in "{AI_DOCS_ROOT}/skills"

# ❌ 相对路径（不推荐）
../../skills/code-review/tools/review_pr.py
```

### 已废弃的工具名

以下工具名已在历史文档中修正，**不应再使用**：

| 废弃工具名 | 替换为 | 修正日期 |
|-----------|--------|---------|
| `run_terminal_cmd` | `execute_command` | 2026-02-03 |
| `glob_file_search` | `search_file` | 2026-02-03 |
| `codebase_search` | `search_content` | 2026-02-03 |
| `grep` | `search_content` | 2026-02-03 |
| `write()` | `write_to_file` | 2026-02-03 |

---

## 📝 最近更新

### 2026-03-06

**README 更新，同步仓库实际结构**
- ✅ 新增 `publish_skill/` 目录说明（git 追踪，存放可发布共享技能）
- ✅ `skills/` 标注为本地私有技能库（已从 git 移除追踪，不入库）
- ✅ 技能表格按 `publish_skill/` 和 `skills/` 拆分展示
- ✅ 新增 `bk-monitor/scenarios/spec-kit-rules.md` 文件说明
- ✅ 修正统计信息中的技能数量

### 2026-02-27

**排障场景知识体系大幅更新**
- ✅ `docs/index.md` 新增"按模块检索"分类视图（access / trigger / alert / fta_action / nodata / scheduler）
- ✅ 新增排障文档：nodata 模块锁超时批量误告、ActionProcessor context 类型混用导致通知失败
- ✅ `troubleshooting-process.md` 补充任务完成归档工作流（已知问题 vs 新问题的区分处理）
- ✅ `AGENTS.md` 重写为简洁三步协议（识别场景 → 加载规则 → 执行任务）
- ✅ 路径硬编码全面替换为 `{BK_MONITOR_LOCAL_REPO}`、`{PRIVATE_CONFIG_DIR}` 等路径变量

### 2026-01-30

**AI-RULES 执行协议增强**
- ✅ troubleshooting 场景新增"样例优先查找"规则：收到排查任务必须先检索 `docs/` 下的已有案例
- ✅ 新增场景技能自动加载规则（遍历 `skills/` 和 `tools/` 目录下所有 SKILL.md）

### 2026-02-03

**工具使用规范修正** ([f05aa8a](https://git.woa.com/bkmonitor/ai-docs/-/commit/f05aa8a))
- ✅ 修正 21 处工具名称错误
- ✅ 统一使用绝对路径
- ✅ 优化场景文档结构
- 影响文件：8 个核心文档
- 影响场景：code-review、troubleshooting、k8s-pod-exec

---

## 🤝 贡献指南

### 添加新场景

1. 在 `bk-monitor/scenarios/` 下创建场景目录
2. 参考 [scenarios/README.md](bk-monitor/scenarios/README.md) 创建结构
3. 在 [scenario-identification-rules.md](bk-monitor/scenarios/scenario-identification-rules.md) 中添加识别规则
4. 提交 PR

### 添加新技能

- **可发布技能**：在 `publish_skill/` 下创建目录，参考 [publish_skill/create-skill/SKILL.md](publish_skill/create-skill/SKILL.md) 创建，提交 PR
- **本地私有技能**：在 `skills/` 下创建目录（不入库，仅本地有效）

### 更新文档

1. 遵循文档规范
2. 使用正确的工具名称（见工具使用规范）
3. 使用绝对路径
4. 提交清晰的 commit 信息

---

## 📊 统计信息

- **场景数量**：4 个（code-review、coding、troubleshooting、default）
- **可发布技能**：2 个（gtm-workflow、create-skill，位于 `publish_skill/`）
- **本地私有技能**：4 个（code-review、k8s-pod-exec、log-searcher、qywx-bot-notifier，位于 `skills/`，不入库）
- **文档数量**：220+ Markdown 文档
- **工具脚本**：6+ 可执行脚本

---

## 📮 联系方式

- **项目**：BK-Monitor
- **仓库**：https://git.woa.com/bkmonitor/ai-docs
- **问题反馈**：通过 GitLab Issues 提交

---

## 📄 许可证

内部使用，仅限腾讯员工访问。

---

**最后更新**：2026-03-06  
**维护者**：BK-Monitor Team
