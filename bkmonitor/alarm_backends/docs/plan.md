# 监控告警数据流处理框架设计文档

## 一、项目概述

### 1.1 背景与愿景

基于 `bkmonitor/alarm_backends` 模块的实现经验，我们希望提炼出一套**面向监控告警领域的、可复用的数据流处理框架**。该框架专注于解决监控告警场景中的常见问题，可以在不同监控项目中快速集成使用。

**核心理念**：每个处理流程视为一个**节点(Node)**，节点可自由组合形成**流水线(Pipeline)**，实现代码层面的可编排数据流处理。

**领域聚焦**：虽然框架设计具有通用性，但**首要目标是服务于监控告警场景**，内置针对告警处理的专用节点和规则。

### 1.2 设计目标

| 目标 | 说明 |
|-----|------|
| **领域聚焦** | 专注监控告警场景：事件丰富化、过滤、抑制、收敛、屏蔽、通知等 |
| **可编排** | 节点可自由组合，支持顺序、并行、条件、循环等模式 |
| **配置驱动** | 通过 YAML/JSON 定义流水线，无需修改代码 |
| **可插拔** | 标准化节点接口，支持动态注册和扩展 |
| **规则引擎** | 内置告警触发条件、收敛规则、屏蔽规则等配置化能力 |
| **生产就绪** | 支持 Redis/Kafka/Celery 等生产级中间件 |
| **兼容性** | 支持 Python 3.6+（考虑现有项目环境） |

### 1.3 核心功能清单

基于 alarm_backends 的功能抽象，框架需内置支持以下**监控告警领域特定功能**：

| 功能类别 | 具体功能 | 说明 |
|---------|---------|------|
| **事件丰富化** | CMDB信息补充、维度翻译、策略配置加载 | 为原始事件补充上下文信息 |
| **事件过滤** | 白名单/黑名单、业务过滤、维度过滤、过期过滤 | 根据条件筛选事件 |
| **事件抑制** | 去重抑制、降噪处理、频率限制 | 减少重复和无效事件 |
| **流量控制** | 限流、熔断、防洪峰 | 保护下游系统 |
| **告警聚合** | 时间窗口聚合、维度聚合、事件→告警转换 | 将事件聚合为告警 |
| **告警收敛** | 策略收敛、业务收敛、汇总收敛、防御收敛 | 减少告警数量 |
| **告警屏蔽** | 策略屏蔽、维度屏蔽、时间屏蔽、范围屏蔽 | 临时或永久屏蔽告警 |
| **告警升级** | 级别检查、优先级调整、升级触发 | 告警级别管理 |
| **动作执行** | 通知发送、Webhook调用、ITSM工单、自动化处理 | 告警响应动作 |

### 1.4 框架定位

```
┌─────────────────────────────────────────────────────────────────┐
│                    监控告警项目 (Application)                    │
│  蓝鲸监控 │ 自研监控 │ 日志告警 │ APM │ 基础设施监控 │ ...     │
├─────────────────────────────────────────────────────────────────┤
│           Alert DataFlow Framework (本框架)                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    内置告警处理节点                       │    │
│  │  Enricher│Filter│Suppressor│Converge│Shield│Action     │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │  Pipeline   │    Node     │    Rule     │   Config    │      │
│  │ Orchestrator│  Registry   │   Engine    │   Manager   │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
├─────────────────────────────────────────────────────────────────┤
│                    基础设施层 (Infrastructure)                    │
│  Redis │ Kafka │ Celery │ RabbitMQ │ ES │ MySQL │ ...          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、第三方库技术选型

### 2.1 流处理框架对比

| 框架 | 特点 | 优势 | 劣势 | 推荐场景 |
|-----|------|------|------|---------|
| **Bytewax** | Rust+Python 流处理 | 高性能、有状态、窗口聚合、Kafka原生支持 | 相对新、社区较小 | 实时流处理、复杂事件处理 |
| **Faust** | Kafka Streams Python版 | 异步、表支持、RocksDB状态存储 | 强依赖Kafka、项目活跃度下降 | Kafka场景 |
| **RxPY** | 响应式编程 | 丰富的操作符、事件驱动 | 学习曲线陡、调试困难 | 事件驱动、UI响应 |

### 2.2 工作流编排框架对比

| 框架 | 特点 | 优势 | 劣势 | 推荐场景 |
|-----|------|------|------|---------|
| **Prefect** | 现代工作流编排 | 动态DAG、UI界面、云原生 | 重量级、需要服务端 | 复杂ETL、数据管道 |
| **Celery Canvas** | 任务编排原语 | 轻量、chain/group/chord、动态 | 监控较弱、无DAG可视化 | 分布式任务、异步处理 |
| **Dagster** | 数据资产编排 | 资产血缘、类型系统 | 学习成本高 | 数据工程 |
| **Luigi** | 批处理管道 | 简单、依赖管理好 | 无动态DAG、较老 | 批量ETL |

### 2.3 规则引擎对比

| 库 | 特点 | 优势 | 劣势 | 推荐场景 |
|---|------|------|------|---------|
| **durable-rules** | 实时规则引擎 | 高性能C扩展、支持CEP、前向链推理 | 文档较少 | 复杂事件处理、实时决策 |
| **business-rules** | 简单规则引擎 | 易用、JSON配置 | 功能有限 | 简单业务规则 |
| **json-rules-engine** | Node.js移植 | 条件组合灵活 | Python版维护较少 | 轻量规则 |
| **PyKE** | 知识引擎 | 强大的推理能力 | 过于复杂 | 专家系统 |

### 2.4 推荐技术栈

```yaml
# 推荐组合方案

方案A - 轻量级 (推荐用于中小规模):
  流水线编排: Celery Canvas + 自研轻量Pipeline
  规则引擎: durable-rules 或 自研简化版
  消息队列: Redis (Celery backend)
  状态存储: Redis
  适用: 事件处理、告警系统、异步任务

方案B - 流处理 (实时场景):
  流处理: Bytewax
  消息队列: Kafka
  状态存储: RocksDB (内置)
  规则引擎: 自研 (集成到Bytewax operator)
  适用: 实时分析、流计算、CEP

方案C - 重量级 (大规模数据管道):
  流水线编排: Prefect / Dagster
  消息队列: Kafka
  状态存储: Redis + PostgreSQL
  规则引擎: durable-rules
  适用: 数据ETL、大规模批处理
```

### 2.5 技术选型建议

基于监控告警场景特点（事件驱动、规则匹配、状态管理、高可用）和 **Python 3.6 兼容性要求**，**推荐方案A**：

```python
# 核心依赖 (Python 3.6+ 兼容)
dependencies = {
    "celery": ">=4.4.0,<6.0.0",     # 分布式任务 + Canvas编排 (4.x支持py36)
    "redis": ">=3.5.0,<5.0.0",      # 状态存储 + 消息队列
    "pyyaml": ">=5.4.0",            # YAML配置
    "typing-extensions": ">=3.7.4", # 类型提示兼容
}

# Python 3.6 兼容说明
# - 不使用 dataclasses (3.7+)，使用 attr 或普通类
# - 不使用 f-string walrus operator (3.8+)
# - 不使用 pydantic v2 (需3.7+)，使用 pydantic v1 或 attr+validators

# 可选依赖
optional_dependencies = {
    "kafka": ["confluent-kafka>=1.5.0"],
    "rules": ["durable-rules>=2.0.0"],  # 规则引擎
    "validation": ["attrs>=20.3.0"],     # 数据校验 (替代pydantic)
}
```

### 2.6 Python 3.6 兼容性方案

| 特性 | Python 3.7+ | Python 3.6 替代方案 |
|-----|-------------|-------------------|
| dataclasses | `@dataclass` | `attr.s` 或普通类 |
| pydantic v2 | `BaseModel` | `pydantic v1` 或 `attrs` |
| 类型注解 | `dict[str, Any]` | `Dict[str, Any]` |
| f-string = | `f"{x=}"` | `f"x={x}"` |
| walrus | `if (x := func())` | `x = func(); if x` |

---

## 三、内置告警处理节点设计

### 3.1 节点分类体系

```
告警处理节点
├── 输入节点 (Input)
│   ├── KafkaConsumer      # Kafka事件消费
│   ├── RedisSubscriber    # Redis订阅
│   └── HTTPReceiver       # HTTP事件接收
├── 丰富化节点 (Enricher)
│   ├── CMDBEnricher       # CMDB信息补充
│   ├── StrategyEnricher   # 策略配置加载
│   ├── DimensionEnricher  # 维度信息翻译
│   └── ContextEnricher    # 上下文信息补充
├── 过滤节点 (Filter)
│   ├── WhitelistFilter    # 白名单过滤
│   ├── BlacklistFilter    # 黑名单过滤
│   ├── BizFilter          # 业务过滤
│   ├── DimensionFilter    # 维度条件过滤
│   └── ExpireFilter       # 过期事件过滤
├── 抑制节点 (Suppressor)
│   ├── DedupSuppressor    # 去重抑制
│   ├── NoiseReducer       # 降噪处理
│   ├── RateLimiter        # 频率限制
│   └── CircuitBreaker     # 熔断保护
├── 聚合节点 (Aggregator)
│   ├── WindowAggregator   # 时间窗口聚合
│   ├── DimensionAggregator# 维度聚合
│   └── EventToAlert       # 事件转告警
├── 收敛节点 (Converge)
│   ├── StrategyConverge   # 策略维度收敛
│   ├── BizConverge        # 业务维度收敛
│   ├── DefenseConverge    # 防御收敛
│   └── SummaryConverge    # 汇总收敛
├── 屏蔽节点 (Shield)
│   ├── StrategyShielder   # 策略屏蔽
│   ├── DimensionShielder  # 维度屏蔽
│   ├── TimeShielder       # 时间周期屏蔽
│   └── ScopeShielder      # 范围屏蔽(IP/集群等)
├── 检查节点 (Checker)
│   ├── LevelChecker       # 级别检查
│   ├── PriorityChecker    # 优先级检查
│   ├── UpgradeChecker     # 升级检查
│   └── AssignChecker      # 分派规则检查
└── 动作节点 (Action)
    ├── NoticeAction       # 通知发送(邮件/短信/微信)
    ├── WebhookAction      # Webhook调用
    ├── ITSMAction         # ITSM工单
    ├── JobAction          # 作业执行
    └── CallbackAction     # 自定义回调
```

### 3.2 核心节点详细设计

#### 3.2.1 收敛节点 (ConvergeNode)

```python
# dataflow/builtin/converge/base.py

from typing import Dict, List, Any, Optional
from enum import Enum

class ConvergeMethod(Enum):
    """收敛方式"""
    COLLECT = "collect"      # 汇总收敛：多条合并为一条
    DEFENSE = "defense"      # 防御收敛：达到阈值后抑制
    SKIP = "skip"            # 跳过：直接放行

class ConvergeConfig:
    """收敛配置"""
    def __init__(
        self,
        count: int = 1,                    # 触发阈值
        timedelta: int = 60,               # 时间窗口(秒)
        condition: List[Dict] = None,      # 收敛维度条件
        converge_func: ConvergeMethod = ConvergeMethod.COLLECT,
        need_biz_converge: bool = False,   # 是否需要业务级收敛
        sub_converge_config: Dict = None,  # 二级收敛配置
    ):
        self.count = count
        self.timedelta = timedelta
        self.condition = condition or []
        self.converge_func = converge_func
        self.need_biz_converge = need_biz_converge
        self.sub_converge_config = sub_converge_config

class ConvergeNode(INode):
    """收敛节点基类"""
    
    def __init__(self, redis_client, config: ConvergeConfig):
        self.redis = redis_client
        self.config = config
    
    def process(self, context: NodeContext) -> NodeOutput:
        alerts = context.data
        if not isinstance(alerts, list):
            alerts = [alerts]
        
        result_alerts = []
        for alert in alerts:
            # 计算收敛key
            converge_key = self._build_converge_key(alert)
            
            # 检查是否需要收敛
            should_converge, converge_count = self._check_converge(converge_key, alert)
            
            if should_converge:
                if self.config.converge_func == ConvergeMethod.DEFENSE:
                    # 防御收敛：记录但不发送
                    alert['is_converged'] = True
                    alert['converge_count'] = converge_count
                elif self.config.converge_func == ConvergeMethod.COLLECT:
                    # 汇总收敛：合并告警
                    alert = self._merge_alerts(converge_key, alert)
            
            result_alerts.append(alert)
        
        return NodeOutput(
            result=NodeResult.SUCCESS,
            data=result_alerts,
            metrics={'converged_count': len([a for a in result_alerts if a.get('is_converged')])}
        )
    
    def _build_converge_key(self, alert: Dict) -> str:
        """构建收敛Key"""
        key_parts = []
        for cond in self.config.condition:
            dim = cond.get('dimension')
            value = cond.get('value')
            if value == ['self']:
                # 使用告警自身的维度值
                key_parts.append(f"{dim}:{alert.get(dim, '')}")
            else:
                key_parts.append(f"{dim}:{value}")
        return ":".join(key_parts)
    
    def _check_converge(self, key: str, alert: Dict) -> tuple:
        """检查是否触发收敛"""
        # 使用Redis实现滑动窗口计数
        now = int(time.time())
        window_key = f"converge:{key}:window"
        
        # 添加当前时间戳
        self.redis.zadd(window_key, {str(now): now})
        
        # 清理过期数据
        cutoff = now - self.config.timedelta
        self.redis.zremrangebyscore(window_key, 0, cutoff)
        
        # 获取窗口内计数
        count = self.redis.zcard(window_key)
        
        # 设置过期时间
        self.redis.expire(window_key, self.config.timedelta * 2)
        
        return count >= self.config.count, count
```

#### 3.2.2 屏蔽节点 (ShieldNode)

```python
# dataflow/builtin/shield/base.py

from typing import Dict, List, Any, Optional
from abc import abstractmethod

class ShieldType(Enum):
    """屏蔽类型"""
    STRATEGY = "strategy"      # 策略屏蔽
    DIMENSION = "dimension"    # 维度屏蔽
    SCOPE = "scope"            # 范围屏蔽
    TIME = "time"              # 时间屏蔽

class ShieldConfig:
    """屏蔽配置"""
    def __init__(
        self,
        shield_type: ShieldType,
        dimension_config: Dict = None,     # 维度匹配条件
        scope_type: str = None,            # 范围类型(ip/cluster/module)
        cycle_config: Dict = None,         # 时间周期配置
        begin_time: str = None,            # 开始时间
        end_time: str = None,              # 结束时间
    ):
        self.shield_type = shield_type
        self.dimension_config = dimension_config or {}
        self.scope_type = scope_type
        self.cycle_config = cycle_config
        self.begin_time = begin_time
        self.end_time = end_time

class BaseShielder(INode):
    """屏蔽节点基类"""
    
    @abstractmethod
    def is_match(self, alert: Dict, shield_config: ShieldConfig) -> bool:
        """检查告警是否匹配屏蔽规则"""
        pass
    
    def process(self, context: NodeContext) -> NodeOutput:
        alerts = context.data
        shield_configs = context.config.get('shield_configs', [])
        
        result_alerts = []
        for alert in alerts:
            is_shielded = False
            matched_shield = None
            
            for shield_cfg in shield_configs:
                config = ShieldConfig(**shield_cfg)
                if self.is_match(alert, config):
                    is_shielded = True
                    matched_shield = shield_cfg
                    break
            
            alert['is_shielded'] = is_shielded
            if matched_shield:
                alert['shield_info'] = matched_shield
            
            result_alerts.append(alert)
        
        return NodeOutput(
            result=NodeResult.SUCCESS,
            data=result_alerts,
            metrics={'shielded_count': len([a for a in result_alerts if a.get('is_shielded')])}
        )

class DimensionShielder(BaseShielder):
    """维度屏蔽器"""
    
    @property
    def name(self) -> str:
        return "dimension_shielder"
    
    def is_match(self, alert: Dict, config: ShieldConfig) -> bool:
        """检查维度是否匹配"""
        for dim_key, dim_value in config.dimension_config.items():
            alert_value = alert.get(dim_key)
            if isinstance(dim_value, list):
                if alert_value not in dim_value:
                    return False
            else:
                if alert_value != dim_value:
                    return False
        return True

class TimeShielder(BaseShielder):
    """时间屏蔽器"""
    
    @property
    def name(self) -> str:
        return "time_shielder"
    
    def is_match(self, alert: Dict, config: ShieldConfig) -> bool:
        """检查是否在屏蔽时间范围内"""
        from datetime import datetime
        
        now = datetime.now()
        
        # 检查时间范围
        if config.begin_time and config.end_time:
            begin = datetime.strptime(config.begin_time, "%Y-%m-%d %H:%M:%S")
            end = datetime.strptime(config.end_time, "%Y-%m-%d %H:%M:%S")
            if not (begin <= now <= end):
                return False
        
        # 检查周期配置（如每周一到周五）
        if config.cycle_config:
            # 实现周期检查逻辑
            pass
        
        return True
```

#### 3.2.3 触发条件检测节点 (TriggerNode)

```python
# dataflow/builtin/trigger/detector.py

class TriggerConfig:
    """触发条件配置
    
    示例：5个周期内出现2次则触发
    {
        "check_window": 5,      # 检查窗口(周期数)
        "trigger_count": 2,     # 触发次数阈值
        "recovery_window": 3,   # 恢复窗口
        "recovery_count": 3,    # 恢复次数阈值
    }
    """
    def __init__(
        self,
        check_window: int = 5,
        trigger_count: int = 1,
        recovery_window: int = 3,
        recovery_count: int = 3,
    ):
        self.check_window = check_window
        self.trigger_count = trigger_count
        self.recovery_window = recovery_window
        self.recovery_count = recovery_count

class TriggerDetector(INode):
    """触发条件检测节点"""
    
    def __init__(self, redis_client, config: TriggerConfig):
        self.redis = redis_client
        self.config = config
    
    @property
    def name(self) -> str:
        return "trigger_detector"
    
    def process(self, context: NodeContext) -> NodeOutput:
        events = context.data
        triggered_events = []
        
        for event in events:
            # 构建检测key
            detect_key = self._build_detect_key(event)
            
            # 记录当前检测结果
            is_anomaly = event.get('is_anomaly', False)
            self._record_result(detect_key, is_anomaly)
            
            # 检查是否满足触发条件
            should_trigger = self._check_trigger(detect_key)
            
            if should_trigger:
                event['triggered'] = True
                triggered_events.append(event)
        
        return NodeOutput(
            result=NodeResult.SUCCESS,
            data=triggered_events,
            metrics={
                'input_count': len(events),
                'triggered_count': len(triggered_events)
            }
        )
    
    def _build_detect_key(self, event: Dict) -> str:
        """构建检测Key（基于策略+维度）"""
        strategy_id = event.get('strategy_id', '')
        dimensions = event.get('dimensions', {})
        dim_str = ":".join(f"{k}={v}" for k, v in sorted(dimensions.items()))
        return f"trigger:{strategy_id}:{dim_str}"
    
    def _record_result(self, key: str, is_anomaly: bool):
        """记录检测结果到滑动窗口"""
        result_key = f"{key}:results"
        self.redis.lpush(result_key, "1" if is_anomaly else "0")
        self.redis.ltrim(result_key, 0, self.config.check_window - 1)
        self.redis.expire(result_key, 3600)
    
    def _check_trigger(self, key: str) -> bool:
        """检查是否满足触发条件"""
        result_key = f"{key}:results"
        results = self.redis.lrange(result_key, 0, self.config.check_window - 1)
        
        # 统计异常次数
        anomaly_count = sum(1 for r in results if r == b"1")
        
        return anomaly_count >= self.config.trigger_count
```

---

## 四、框架核心架构

### 4.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DataFlow Framework                               │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Pipeline Layer (编排层)                       │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │                  Pipeline Definition (YAML)                  │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  │                              ↓                                     │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │              Pipeline Orchestrator (Celery Canvas)           │  │  │
│  │  │  chain() → group() → chord() → 动态组合                      │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                       Node Layer (节点层)                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │  │
│  │  │ Enricher │ │  Filter  │ │Suppressor│ │ Converge │ │ Action │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │  │
│  │       ↑             ↑             ↑             ↑           ↑     │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │              Node Registry (节点注册中心)                    │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Core Layer (核心层)                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │  │
│  │  │ Rule Engine  │  │Context Manager│ │Config Manager │             │  │
│  │  │(durable-rules)│  │   (Redis)    │  │  (Pydantic)  │             │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                  Infrastructure Layer (基础设施)                   │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐      │  │
│  │  │ Celery │  │ Redis  │  │ Kafka  │  │  ES    │  │ MySQL  │      │  │
│  │  └────────┘  └────────┘  └────────┘  └────────┘  └────────┘      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 核心概念

| 概念 | 说明 | 类比 |
|-----|------|------|
| **Node** | 最小处理单元，执行单一职责 | 函数 |
| **Pipeline** | 节点的有序组合，定义数据流 | 工作流 |
| **Context** | 贯穿流水线的数据载体 | 请求上下文 |
| **Rule** | 条件+动作的配置化定义 | if-then |
| **Registry** | 节点注册与发现中心 | 服务注册 |

### 4.3 与 alarm_backends 的关系

```
alarm_backends 现有实现          →    DataFlow Framework (抽象)
─────────────────────────────         ────────────────────────────
AlertBuilder                    →    Node (丰富化节点)
ConvergeProcessor               →    Node (收敛节点)
ShieldManager                   →    Node (屏蔽节点)
EventEnrichFactory              →    Pipeline (丰富化流水线)
CircuitBreakingMatcher          →    Rule Engine
StrategyCacheManager            →    Config Manager
Redis Lock                      →    Context Manager
```

---

## 五、基于 Celery Canvas 的实现方案

### 5.1 为什么选择 Celery Canvas

| 优势 | 说明 |
|-----|------|
| **成熟稳定** | 10年+ 生产验证，社区活跃 |
| **编排原语丰富** | chain/group/chord/map 满足各种组合需求 |
| **动态工作流** | 支持运行时动态构建任务链 |
| **分布式原生** | 天然支持分布式、重试、结果追踪 |
| **技术栈统一** | alarm_backends 已使用 Celery |

### 5.2 编排原语映射

```python
# Celery Canvas 原语 → 流水线模式

from celery import chain, group, chord

# 1. 顺序执行 (Sequential)
chain(node_a.s(), node_b.s(), node_c.s())
# A → B → C

# 2. 并行执行 (Parallel)  
group(node_a.s(), node_b.s(), node_c.s())
# A ─┐
# B ─┼→ (同时执行)
# C ─┘

# 3. 扇出-汇聚 (Fan-out/Fan-in)
chord(
    group(node_a.s(), node_b.s(), node_c.s()),
    merge_results.s()
)
# A ─┐
# B ─┼→ merge_results
# C ─┘

# 4. 条件执行 (Conditional)
@app.task(bind=True)
def conditional_node(self, data, condition):
    if evaluate(condition, data):
        return node_true.delay(data)
    else:
        return node_false.delay(data)

# 5. 动态链 (Dynamic Chain)
def build_dynamic_chain(node_names, data):
    tasks = [registry.get(name).s() for name in node_names]
    return chain(*tasks).apply_async(args=[data])
```

### 5.3 节点接口设计

```python
# dataflow/node/interface.py

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel
from celery import Task

T = TypeVar('T')

class NodeResult(Enum):
    """节点执行结果"""
    SUCCESS = "success"      # 成功，继续执行
    SKIP = "skip"            # 跳过，继续执行
    FAIL = "fail"            # 失败，触发错误处理
    RETRY = "retry"          # 重试
    ABORT = "abort"          # 中止整个流水线

@dataclass
class NodeContext:
    """节点执行上下文"""
    data: Any                                    # 输入数据
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元信息
    state: Dict[str, Any] = field(default_factory=dict)     # 共享状态
    config: Dict[str, Any] = field(default_factory=dict)    # 节点配置
    pipeline_id: Optional[str] = None            # 流水线ID
    trace_id: Optional[str] = None               # 追踪ID
    
    def clone(self, **updates) -> 'NodeContext':
        """创建上下文副本"""
        return NodeContext(
            data=updates.get('data', self.data),
            metadata={**self.metadata, **updates.get('metadata', {})},
            state={**self.state, **updates.get('state', {})},
            config={**self.config, **updates.get('config', {})},
            pipeline_id=self.pipeline_id,
            trace_id=self.trace_id,
        )

@dataclass
class NodeOutput:
    """节点执行输出"""
    result: NodeResult
    data: Any
    message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

class INode(ABC):
    """节点接口规范"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """节点唯一名称"""
        pass
    
    @property
    def version(self) -> str:
        """节点版本"""
        return "1.0.0"
    
    @property
    def description(self) -> str:
        """节点描述"""
        return ""
    
    @classmethod
    def config_schema(cls) -> type[BaseModel]:
        """配置Schema (Pydantic Model)"""
        return BaseModel
    
    @abstractmethod
    def process(self, context: NodeContext) -> NodeOutput:
        """
        执行节点逻辑
        
        Args:
            context: 节点执行上下文
            
        Returns:
            NodeOutput: 节点执行结果
        """
        pass
    
    def on_success(self, context: NodeContext, output: NodeOutput) -> None:
        """成功回调"""
        pass
    
    def on_failure(self, context: NodeContext, error: Exception) -> None:
        """失败回调"""
        pass

class CeleryNode(Task, INode):
    """Celery任务节点基类"""
    
    # Celery配置
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 3
    
    def run(self, context_dict: Dict) -> Dict:
        """Celery任务入口"""
        context = NodeContext(**context_dict)
        try:
            output = self.process(context)
            self.on_success(context, output)
            return {
                'result': output.result.value,
                'data': output.data,
                'message': output.message,
                'metrics': output.metrics,
            }
        except Exception as e:
            self.on_failure(context, e)
            raise
```

### 5.4 节点注册中心

```python
# dataflow/node/registry.py

from typing import Dict, Type, Optional, List, Callable
import importlib
import pkgutil
import logging

class NodeRegistry:
    """节点注册中心"""
    
    _nodes: Dict[str, Type[INode]] = {}
    _instances: Dict[str, INode] = {}
    _metadata: Dict[str, Dict] = {}
    
    @classmethod
    def register(cls, name: str = None, **metadata):
        """
        注册节点装饰器
        
        Usage:
            @NodeRegistry.register("my_node", category="filter")
            class MyNode(INode):
                ...
        """
        def decorator(node_class: Type[INode]):
            node_name = name or node_class.__name__
            cls._nodes[node_name] = node_class
            cls._metadata[node_name] = {
                'class': node_class,
                'module': node_class.__module__,
                **metadata
            }
            logging.info(f"Registered node: {node_name}")
            return node_class
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[INode]]:
        """获取节点类"""
        return cls._nodes.get(name)
    
    @classmethod
    def create(cls, name: str, config: Dict = None) -> INode:
        """创建节点实例"""
        node_class = cls.get(name)
        if not node_class:
            raise ValueError(f"Unknown node: {name}")
        
        # 验证配置
        if config and hasattr(node_class, 'config_schema'):
            schema = node_class.config_schema()
            schema(**config)  # Pydantic验证
        
        return node_class()
    
    @classmethod
    def list_nodes(cls, category: str = None) -> List[Dict]:
        """列出所有节点"""
        nodes = []
        for name, meta in cls._metadata.items():
            if category and meta.get('category') != category:
                continue
            nodes.append({
                'name': name,
                'description': meta['class'].description if hasattr(meta['class'], 'description') else '',
                'version': meta['class'].version if hasattr(meta['class'], 'version') else '1.0.0',
                **meta
            })
        return nodes
    
    @classmethod
    def discover(cls, package: str) -> None:
        """自动发现并注册包内的节点"""
        try:
            pkg = importlib.import_module(package)
            for _, module_name, _ in pkgutil.walk_packages(
                pkg.__path__, prefix=f"{package}."
            ):
                try:
                    importlib.import_module(module_name)
                except ImportError as e:
                    logging.warning(f"Failed to import {module_name}: {e}")
        except ImportError as e:
            logging.error(f"Failed to discover nodes in {package}: {e}")
```

### 5.5 流水线编排器

```python
# dataflow/pipeline/orchestrator.py

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
from celery import chain, group, chord, signature
import yaml
import logging

class StageType(Enum):
    """阶段类型"""
    SEQUENTIAL = "sequential"   # 顺序: A → B → C
    PARALLEL = "parallel"       # 并行: A | B | C
    FANOUT = "fanout"           # 扇出汇聚: (A | B | C) → merge
    CONDITIONAL = "conditional" # 条件: if X then A else B
    SWITCH = "switch"           # 多路选择: switch(X) { case 1: A; case 2: B }

@dataclass
class StageConfig:
    """阶段配置"""
    name: str
    type: StageType
    nodes: List[str]
    config: Dict[str, Any] = None
    condition: Optional[str] = None
    merge_node: Optional[str] = None  # fanout模式的汇聚节点
    enabled: bool = True

@dataclass  
class PipelineConfig:
    """流水线配置"""
    id: str
    name: str
    version: str
    stages: List[StageConfig]
    global_config: Dict[str, Any] = None
    error_handler: Optional[str] = None

class PipelineOrchestrator:
    """流水线编排器"""
    
    def __init__(self, registry: NodeRegistry, celery_app):
        self.registry = registry
        self.celery = celery_app
        self.pipelines: Dict[str, PipelineConfig] = {}
        self.logger = logging.getLogger(__name__)
    
    def load_from_yaml(self, yaml_path: str) -> PipelineConfig:
        """从YAML加载流水线配置"""
        with open(yaml_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        return self.load_from_dict(config_dict)
    
    def load_from_dict(self, config_dict: Dict) -> PipelineConfig:
        """从字典加载流水线配置"""
        stages = []
        for stage_dict in config_dict.get('stages', []):
            stage = StageConfig(
                name=stage_dict['name'],
                type=StageType(stage_dict.get('type', 'sequential')),
                nodes=stage_dict['nodes'],
                config=stage_dict.get('config', {}),
                condition=stage_dict.get('condition'),
                merge_node=stage_dict.get('merge_node'),
                enabled=stage_dict.get('enabled', True),
            )
            stages.append(stage)
        
        pipeline = PipelineConfig(
            id=config_dict['id'],
            name=config_dict['name'],
            version=config_dict['version'],
            stages=stages,
            global_config=config_dict.get('global_config', {}),
            error_handler=config_dict.get('error_handler'),
        )
        self.pipelines[pipeline.id] = pipeline
        return pipeline
    
    def build_workflow(self, pipeline_id: str) -> signature:
        """构建Celery工作流"""
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            raise ValueError(f"Unknown pipeline: {pipeline_id}")
        
        workflow_parts = []
        for stage in pipeline.stages:
            if not stage.enabled:
                continue
            
            stage_workflow = self._build_stage(stage, pipeline.global_config)
            if stage_workflow:
                workflow_parts.append(stage_workflow)
        
        if not workflow_parts:
            raise ValueError("Pipeline has no enabled stages")
        
        # 组合所有阶段为一个chain
        return chain(*workflow_parts)
    
    def _build_stage(self, stage: StageConfig, global_config: Dict) -> signature:
        """构建单个阶段的工作流"""
        # 获取节点签名
        node_sigs = []
        for node_name in stage.nodes:
            node_config = {
                **(stage.config or {}).get(node_name, {}),
                **global_config
            }
            sig = self._get_node_signature(node_name, node_config)
            node_sigs.append(sig)
        
        if not node_sigs:
            return None
        
        # 根据类型构建工作流
        if stage.type == StageType.SEQUENTIAL:
            return chain(*node_sigs)
        
        elif stage.type == StageType.PARALLEL:
            return group(*node_sigs)
        
        elif stage.type == StageType.FANOUT:
            if not stage.merge_node:
                raise ValueError(f"Fanout stage {stage.name} requires merge_node")
            merge_sig = self._get_node_signature(stage.merge_node, global_config)
            return chord(group(*node_sigs), merge_sig)
        
        elif stage.type == StageType.CONDITIONAL:
            # 条件执行需要特殊处理，返回条件路由器
            return self._build_conditional(stage, node_sigs, global_config)
        
        else:
            raise ValueError(f"Unknown stage type: {stage.type}")
    
    def _get_node_signature(self, node_name: str, config: Dict) -> signature:
        """获取节点的Celery签名"""
        node_class = self.registry.get(node_name)
        if not node_class:
            raise ValueError(f"Unknown node: {node_name}")
        
        # 假设节点已注册为Celery任务
        task_name = f"dataflow.nodes.{node_name}"
        return self.celery.signature(task_name, kwargs={'config': config})
    
    def _build_conditional(self, stage: StageConfig, node_sigs: List, 
                          global_config: Dict) -> signature:
        """构建条件执行工作流"""
        # 创建条件路由任务
        router_name = f"dataflow.router.{stage.name}"
        return self.celery.signature(
            router_name,
            kwargs={
                'condition': stage.condition,
                'branches': {sig.name: sig for sig in node_sigs},
                'config': global_config,
            }
        )
    
    def execute(self, pipeline_id: str, data: Any, 
                metadata: Dict = None) -> str:
        """执行流水线"""
        workflow = self.build_workflow(pipeline_id)
        
        # 构建初始上下文
        context = {
            'data': data,
            'metadata': metadata or {},
            'state': {},
            'config': self.pipelines[pipeline_id].global_config,
            'pipeline_id': pipeline_id,
        }
        
        # 异步执行
        result = workflow.apply_async(args=[context])
        self.logger.info(f"Started pipeline {pipeline_id}, task_id={result.id}")
        return result.id
    
    def execute_sync(self, pipeline_id: str, data: Any, 
                     metadata: Dict = None, timeout: int = 300) -> Any:
        """同步执行流水线"""
        workflow = self.build_workflow(pipeline_id)
        
        context = {
            'data': data,
            'metadata': metadata or {},
            'state': {},
            'config': self.pipelines[pipeline_id].global_config,
            'pipeline_id': pipeline_id,
        }
        
        result = workflow.apply_async(args=[context])
        return result.get(timeout=timeout)
```

### 5.6 规则引擎 (基于 durable-rules)

```python
# dataflow/rule/engine.py

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from durable.lang import ruleset, rule, when_all, when_any, m, c, post
import logging

@dataclass
class RuleConfig:
    """规则配置"""
    id: str
    name: str
    conditions: List[Dict]      # 条件列表
    action: str                 # 动作名称
    action_params: Dict = None  # 动作参数
    priority: int = 0
    enabled: bool = True

class RuleEngine:
    """
    规则引擎 - 基于 durable-rules
    
    支持的条件操作符:
    - eq, neq: 等于/不等于
    - gt, gte, lt, lte: 大小比较
    - contains, not_contains: 包含/不包含
    - matches: 正则匹配
    - in, not_in: 在列表中
    """
    
    def __init__(self, name: str = "default"):
        self.name = name
        self.rules: List[RuleConfig] = []
        self.actions: Dict[str, Callable] = {}
        self._ruleset = None
        self.logger = logging.getLogger(__name__)
    
    def register_action(self, name: str, handler: Callable):
        """注册动作处理器"""
        self.actions[name] = handler
    
    def load_rules(self, rules_config: List[Dict]):
        """加载规则配置"""
        self.rules = []
        for rule_dict in rules_config:
            if not rule_dict.get('enabled', True):
                continue
            self.rules.append(RuleConfig(
                id=rule_dict['id'],
                name=rule_dict['name'],
                conditions=rule_dict['conditions'],
                action=rule_dict['action'],
                action_params=rule_dict.get('action_params', {}),
                priority=rule_dict.get('priority', 0),
                enabled=True,
            ))
        # 按优先级排序
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        self._build_ruleset()
    
    def _build_ruleset(self):
        """构建 durable-rules 规则集"""
        rules_def = {}
        
        for rule_config in self.rules:
            # 构建条件表达式
            condition = self._build_condition(rule_config.conditions)
            
            # 构建动作
            action_name = rule_config.action
            action_params = rule_config.action_params
            
            def make_action(act_name, act_params):
                def action_handler(c):
                    handler = self.actions.get(act_name)
                    if handler:
                        handler(c.m, act_params)
                return action_handler
            
            rules_def[rule_config.id] = {
                'when': condition,
                'run': make_action(action_name, action_params)
            }
        
        # 使用 durable-rules API
        self._ruleset = ruleset(self.name, rules_def)
    
    def _build_condition(self, conditions: List[Dict]) -> Any:
        """构建条件表达式"""
        exprs = []
        for cond in conditions:
            field = cond['field']
            op = cond['operator']
            value = cond['value']
            
            if op == 'eq':
                exprs.append(m[field] == value)
            elif op == 'neq':
                exprs.append(m[field] != value)
            elif op == 'gt':
                exprs.append(m[field] > value)
            elif op == 'gte':
                exprs.append(m[field] >= value)
            elif op == 'lt':
                exprs.append(m[field] < value)
            elif op == 'lte':
                exprs.append(m[field] <= value)
            elif op == 'contains':
                exprs.append(m[field].contains(value))
            elif op == 'matches':
                exprs.append(m[field].matches(value))
        
        # 默认 AND 逻辑
        return when_all(*exprs) if len(exprs) > 1 else exprs[0]
    
    def evaluate(self, data: Dict) -> List[str]:
        """评估数据，返回触发的规则ID列表"""
        triggered = []
        try:
            post(self.name, data)
            # durable-rules 会自动触发匹配的规则动作
            # 这里通过回调收集触发的规则
        except Exception as e:
            self.logger.error(f"Rule evaluation failed: {e}")
        return triggered

# 简化版规则引擎 (不依赖 durable-rules)
class SimpleRuleEngine:
    """简化版规则引擎 - 纯Python实现"""
    
    OPERATORS = {
        'eq': lambda a, b: a == b,
        'neq': lambda a, b: a != b,
        'gt': lambda a, b: a > b,
        'gte': lambda a, b: a >= b,
        'lt': lambda a, b: a < b,
        'lte': lambda a, b: a <= b,
        'in': lambda a, b: a in b,
        'not_in': lambda a, b: a not in b,
        'contains': lambda a, b: b in a if a else False,
        'matches': lambda a, b: bool(__import__('re').match(b, str(a))) if a else False,
    }
    
    def __init__(self):
        self.rules: List[RuleConfig] = []
    
    def load_rules(self, rules_config: List[Dict]):
        """加载规则"""
        self.rules = [
            RuleConfig(**{**r, 'conditions': r['conditions']})
            for r in rules_config if r.get('enabled', True)
        ]
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def evaluate(self, data: Dict) -> List[RuleConfig]:
        """评估数据，返回匹配的规则列表"""
        matched = []
        for rule in self.rules:
            if self._match_rule(rule, data):
                matched.append(rule)
        return matched
    
    def evaluate_first(self, data: Dict) -> Optional[RuleConfig]:
        """返回第一个匹配的规则"""
        for rule in self.rules:
            if self._match_rule(rule, data):
                return rule
        return None
    
    def _match_rule(self, rule: RuleConfig, data: Dict) -> bool:
        """匹配单个规则"""
        for cond in rule.conditions:
            field_value = self._get_nested_value(data, cond['field'])
            op_func = self.OPERATORS.get(cond['operator'])
            if not op_func:
                continue
            if not op_func(field_value, cond['value']):
                return False
        return True
    
    def _get_nested_value(self, data: Dict, field: str, default=None):
        """获取嵌套字段值"""
        keys = field.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        return value if value is not None else default
```

---

## 六、使用示例

### 6.1 定义节点

```python
# nodes/enricher.py

from dataflow.node import INode, NodeContext, NodeOutput, NodeResult, NodeRegistry
from pydantic import BaseModel
from typing import List, Optional

class CMDBEnricherConfig(BaseModel):
    """CMDB丰富化节点配置"""
    api_url: str
    cache_ttl: int = 300
    fields: List[str] = ["bk_host_innerip", "bk_cloud_id"]

@NodeRegistry.register("cmdb_enricher", category="enricher")
class CMDBEnricherNode(INode):
    """CMDB信息丰富化节点"""
    
    @property
    def name(self) -> str:
        return "cmdb_enricher"
    
    @property
    def description(self) -> str:
        return "从CMDB获取主机信息并补充到事件中"
    
    @classmethod
    def config_schema(cls):
        return CMDBEnricherConfig
    
    def process(self, context: NodeContext) -> NodeOutput:
        config = CMDBEnricherConfig(**context.config)
        data = context.data
        
        # 获取CMDB信息
        host_info = self._fetch_cmdb_info(
            data.get('ip'), 
            data.get('bk_cloud_id'),
            config
        )
        
        # 丰富数据
        if host_info:
            for field in config.fields:
                if field in host_info:
                    data[field] = host_info[field]
        
        return NodeOutput(
            result=NodeResult.SUCCESS,
            data=data,
            metrics={'enriched_fields': len(config.fields)}
        )
    
    def _fetch_cmdb_info(self, ip: str, cloud_id: int, config) -> dict:
        # 实现CMDB API调用...
        pass
```

### 6.2 定义流水线配置

```yaml
# pipelines/alert_pipeline.yaml

id: alert_processing
name: 告警处理流水线
version: "1.0.0"

global_config:
  timeout: 300
  retry_max_attempts: 3

stages:
  # 阶段1: 数据丰富化 (顺序执行)
  - name: enrichment
    type: sequential
    nodes:
      - cmdb_enricher
      - strategy_enricher
      - dimension_enricher
    config:
      cmdb_enricher:
        api_url: "http://cmdb.example.com/api"
        cache_ttl: 300
        fields: ["bk_host_innerip", "bk_cloud_id", "bk_biz_name"]

  # 阶段2: 过滤 (条件执行)
  - name: filtering
    type: conditional
    condition: "data.get('bk_biz_id') is not None"
    nodes:
      - whitelist_filter
      - blacklist_filter
      - expire_filter

  # 阶段3: 多重检查 (并行执行)
  - name: validation
    type: parallel
    nodes:
      - rate_limiter
      - circuit_breaker
      - dedup_checker

  # 阶段4: 告警生成 (顺序执行)
  - name: alert_building
    type: sequential
    nodes:
      - event_aggregator
      - alert_builder
    config:
      event_aggregator:
        window_seconds: 300
        group_by: ["strategy_id", "target"]

  # 阶段5: 收敛处理 (扇出汇聚)
  - name: convergence
    type: fanout
    nodes:
      - strategy_converge
      - biz_converge
      - global_converge
    merge_node: converge_merger

  # 阶段6: 通知发送 (条件执行)
  - name: notification
    type: conditional
    condition: "not data.get('is_shielded', False)"
    nodes:
      - notice_sender
      - webhook_caller

error_handler: alert_error_handler
```

### 6.3 执行流水线

```python
# main.py

from dataflow.pipeline import PipelineOrchestrator
from dataflow.node import NodeRegistry
from celery import Celery

# 初始化Celery
app = Celery('dataflow', broker='redis://localhost:6379/0')

# 自动发现并注册节点
NodeRegistry.discover('myproject.nodes')

# 创建编排器
orchestrator = PipelineOrchestrator(NodeRegistry, app)

# 加载流水线配置
orchestrator.load_from_yaml('pipelines/alert_pipeline.yaml')

# 执行流水线
event_data = {
    'alert_name': 'CPU使用率过高',
    'ip': '10.0.0.1',
    'bk_cloud_id': 0,
    'value': 95.5,
    'timestamp': 1704067200,
}

# 异步执行
task_id = orchestrator.execute('alert_processing', event_data)
print(f"Pipeline started: {task_id}")

# 或同步执行
result = orchestrator.execute_sync('alert_processing', event_data, timeout=60)
print(f"Pipeline result: {result}")
```

### 6.4 使用规则引擎

```python
# 规则配置
rules_config = [
    {
        "id": "high_cpu_alert",
        "name": "CPU告警升级",
        "priority": 100,
        "conditions": [
            {"field": "metric_name", "operator": "eq", "value": "cpu_usage"},
            {"field": "value", "operator": "gte", "value": 90}
        ],
        "action": "escalate",
        "action_params": {"level": "critical", "notify": ["oncall"]}
    },
    {
        "id": "disk_warning",
        "name": "磁盘告警",
        "priority": 50,
        "conditions": [
            {"field": "metric_name", "operator": "eq", "value": "disk_usage"},
            {"field": "value", "operator": "gte", "value": 80}
        ],
        "action": "alert",
        "action_params": {"level": "warning"}
    }
]

# 使用规则引擎
from dataflow.rule import SimpleRuleEngine

engine = SimpleRuleEngine()
engine.load_rules(rules_config)

# 评估事件
event = {"metric_name": "cpu_usage", "value": 95, "host": "server-1"}
matched_rules = engine.evaluate(event)

for rule in matched_rules:
    print(f"Matched rule: {rule.name}, action: {rule.action}")
```

---

## 七、框架目录结构

```
dataflow/                              # 框架根目录
├── __init__.py
├── node/                              # 节点模块
│   ├── __init__.py
│   ├── interface.py                   # 节点接口定义
│   ├── registry.py                    # 节点注册中心
│   ├── base.py                        # 基础节点实现
│   └── celery.py                      # Celery节点适配
├── pipeline/                          # 流水线模块
│   ├── __init__.py
│   ├── orchestrator.py                # 流水线编排器
│   ├── stage.py                       # 阶段定义
│   └── context.py                     # 上下文管理
├── rule/                              # 规则引擎模块
│   ├── __init__.py
│   ├── engine.py                      # 规则引擎
│   ├── condition.py                   # 条件匹配器
│   └── durable.py                     # durable-rules集成
├── config/                            # 配置管理模块
│   ├── __init__.py
│   ├── manager.py                     # 配置管理器
│   ├── loader.py                      # 配置加载器
│   └── schema.py                      # Pydantic模型
├── builtin/                           # 内置节点
│   ├── __init__.py
│   ├── enricher/                      # 丰富化节点
│   │   ├── __init__.py
│   │   ├── cmdb.py
│   │   └── dimension.py
│   ├── filter/                        # 过滤节点
│   │   ├── __init__.py
│   │   ├── whitelist.py
│   │   └── expire.py
│   ├── suppressor/                    # 抑制节点
│   │   ├── __init__.py
│   │   ├── dedup.py
│   │   ├── rate_limit.py
│   │   └── circuit_breaker.py
│   ├── converge/                      # 收敛节点
│   │   ├── __init__.py
│   │   └── strategy.py
│   └── action/                        # 动作节点
│       ├── __init__.py
│       ├── notice.py
│       └── webhook.py
├── contrib/                           # 扩展集成
│   ├── __init__.py
│   ├── kafka.py                       # Kafka连接器
│   ├── redis.py                       # Redis工具
│   └── bytewax.py                     # Bytewax流处理
├── utils/                             # 工具函数
│   ├── __init__.py
│   ├── lock.py                        # 分布式锁
│   └── metrics.py                     # 指标收集
└── cli/                               # 命令行工具
    ├── __init__.py
    └── main.py                        # CLI入口
```

---

## 八、实施计划

### 8.1 里程碑

| 阶段 | 时间 | 目标 | 交付物 |
|-----|------|------|-------|
| **M0** | 1周 | 技术验证 | Celery Canvas + 简单节点 POC |
| **M1** | 2周 | 核心框架 | 节点接口、注册中心、流水线编排器 |
| **M2** | 2周 | 规则引擎 | SimpleRuleEngine + durable-rules集成 |
| **M3** | 2周 | 内置节点 | 5-8个常用节点 (过滤、丰富化、抑制) |
| **M4** | 1周 | 配置管理 | YAML加载、热更新、版本管理 |
| **M5** | 1周 | 测试完善 | 单元测试、集成测试、性能测试 |
| **M6** | 1周 | 文档发布 | 使用文档、API文档、示例项目 |

### 8.2 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|-----|------|------|---------|
| Celery Canvas 性能 | 高 | 低 | 提供本地执行模式bypass |
| durable-rules 学习成本 | 中 | 中 | 提供SimpleRuleEngine备选 |
| 配置复杂度 | 中 | 中 | 提供默认配置和脚手架 |

---

## 九、评估结论

### 9.1 可行性总结

| 维度 | 评分 | 说明 |
|-----|------|------|
| **技术可行性** | 9/10 | 依托成熟库(Celery/Redis)，alarm_backends已验证技术方案 |
| **领域适配性** | 9/10 | 专注监控告警，内置收敛/屏蔽/触发等核心能力 |
| **复用价值** | 9/10 | 可在多个监控项目中快速集成使用 |
| **开发效率** | 8/10 | 使用第三方库减少工作量，专注业务逻辑 |
| **兼容性** | 8/10 | 支持Python 3.6+，兼容现有项目环境 |

### 9.2 与 alarm_backends 的关系

```
本框架定位：面向监控告警领域的可复用数据流处理库

alarm_backends          Alert DataFlow Framework
─────────────────       ────────────────────────────
业务特定实现       →     提供领域通用抽象
紧耦合代码         →     可复用的独立库
硬编码流程         →     配置驱动的流水线
单一项目           →     跨项目复用
                   →     内置告警处理节点(收敛/屏蔽/触发等)
```

### 9.3 下一步行动

1. **技术验证 (POC)**：用 Celery Canvas 实现收敛+屏蔽两个核心节点
2. **核心框架开发**：节点接口、注册中心、流水线编排器
3. **内置节点开发**：优先实现收敛、屏蔽、触发检测等告警核心节点
4. **集成测试**：与现有 alarm_backends 进行对比验证
5. **第一个版本发布**：发布 v0.1.0，支持基础告警处理场景

---

## 附录

### A. 参考项目

| 项目 | 语言 | 说明 |
|-----|------|------|
| Apache Camel | Java | 企业集成模式实现 |
| Spring Integration | Java | 消息驱动架构 |
| Netflix Conductor | Java | 微服务编排 |
| Prefect | Python | 现代工作流编排 |
| Bytewax | Python/Rust | 流处理框架 |
| Faust | Python | Kafka流处理 |

### B. 核心依赖

```toml
# pyproject.toml

[project]
name = "dataflow-framework"
version = "0.1.0"
dependencies = [
    "celery>=5.3.0",
    "redis>=4.5.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0.0",
]

[project.optional-dependencies]
rules = ["durable-rules>=2.0.0"]
kafka = ["confluent-kafka>=2.0.0"]
stream = ["bytewax>=0.18.0"]
all = ["dataflow-framework[rules,kafka,stream]"]
```

### C. 术语表

| 术语 | 定义 |
|-----|------|
| **Node** | 节点，执行单一处理逻辑的最小单元 |
| **Pipeline** | 流水线，节点的有序组合 |
| **Stage** | 阶段，流水线中的一个执行步骤 |
| **Context** | 上下文，贯穿流水线的数据载体 |
| **Rule** | 规则，条件+动作的配置化定义 |
| **Registry** | 注册中心，节点的注册与发现 |
| **Orchestrator** | 编排器，负责构建和执行流水线 |
