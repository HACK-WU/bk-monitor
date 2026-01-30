# Threshold Node Configuration (阈值检测节点配置)

## 节点类型
- **NodeType**: `threshold`
- **分类**: DETECTION (检测类)
- **功能**: 基于阈值规则判断是否触发告警

## 配置 Schema

### ThresholdNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class ThresholdOperator(str, Enum):
    """阈值比较操作符"""
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    EQ = "eq"           # 等于
    NE = "ne"           # 不等于
    BETWEEN = "between" # 区间


class EvaluationMode(str, Enum):
    """多阈值评估模式"""
    HIGHEST = "highest"   # 返回最高匹配级别
    LOWEST = "lowest"     # 返回最低匹配级别
    FIRST = "first"       # 返回第一个匹配的级别
    ALL = "all"           # 返回所有匹配级别


class ThresholdLevelSerializer(serializers.Serializer):
    """阈值级别配置"""
    level = serializers.IntegerField(
        min_value=1,
        max_value=5,
        help_text="告警级别（1-5，5最高）"
    )
    operator = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in ThresholdOperator],
        help_text="比较操作符"
    )
    value = serializers.FloatField(help_text="阈值")
    value_max = serializers.FloatField(
        required=False,
        allow_null=True,
        help_text="区间最大值（between操作符时必填）"
    )
    priority = serializers.IntegerField(
        default=0,
        min_value=0,
        help_text="评估优先级，值越小优先级越高"
    )


class ThresholdNodeConfigSerializer(BaseNodeConfigSerializer):
    """阈值检测节点配置"""
    node_type = serializers.CharField(default="threshold", read_only=True)
    
    # 检测字段
    value_field = serializers.CharField(help_text="检测值字段路径")
    
    # 阈值配置（多级）
    thresholds = ThresholdLevelSerializer(many=True, help_text="阈值配置列表")
    
    # 多阈值评估模式
    evaluation_mode = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in EvaluationMode],
        default=EvaluationMode.HIGHEST.value,
        help_text="多阈值评估模式：highest=取最高级别, lowest=取最低级别, first=按优先级取第一个, all=返回所有"
    )
    
    # 连续检测
    consecutive_count = serializers.IntegerField(
        default=1,
        min_value=1,
        help_text="连续满足次数"
    )
    
    # 检测窗口
    detection_window = serializers.IntegerField(
        default=60,
        min_value=1,
        help_text="检测窗口（秒）"
    )
    
    # 输出配置
    output_level_field = serializers.CharField(
        default="alert.level",
        help_text="输出级别字段"
    )
    output_matched_thresholds_field = serializers.CharField(
        default="alert.matched_thresholds",
        required=False,
        help_text="输出匹配的阈值列表字段（evaluation_mode=all时生效）"
    )
    
    def validate_thresholds(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个阈值配置")
        return value
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "threshold" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `value_field` | string | 是 | - | 检测值字段路径 |
| `thresholds` | array | 是 | - | 阈值配置列表 |
| `evaluation_mode` | string | 否 | "highest" | 多阈值评估模式 |
| `consecutive_count` | integer | 否 | 1 | 连续满足次数 |
| `detection_window` | integer | 否 | 60 | 检测窗口（秒） |
| `output_level_field` | string | 否 | "alert.level" | 输出级别字段 |
| `output_matched_thresholds_field` | string | 否 | "alert.matched_thresholds" | 输出匹配阈值列表字段 |

### 阈值级别配置 (ThresholdLevel)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `level` | integer | 是 | - | 告警级别（1-5） |
| `operator` | string | 是 | - | 比较操作符：gt/gte/lt/lte/eq/ne/between |
| `value` | float | 是 | - | 阈值 |
| `value_max` | float | 否 | null | 区间最大值（between时必填） |
| `priority` | integer | 否 | 0 | 评估优先级 |

### 比较操作符说明

| 操作符 | 说明 | 示例 |
|--------|------|------|
| `gt` | 大于 | value > 80 |
| `gte` | 大于等于 | value >= 80 |
| `lt` | 小于 | value < 20 |
| `lte` | 小于等于 | value <= 20 |
| `eq` | 等于 | value == 100 |
| `ne` | 不等于 | value != 0 |
| `between` | 区间 | 80 <= value <= 100 |

### 评估模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `highest` | 返回最高匹配级别 | 多阈值时取最严重的级别 |
| `lowest` | 返回最低匹配级别 | 多阈值时取最轻的级别 |
| `first` | 返回第一个匹配 | 按优先级顺序匹配 |
| `all` | 返回所有匹配 | 需要记录所有触发的阈值 |

## JSON 配置示例

### 示例 1: CPU 使用率阈值检测

```json
{
  "name": "cpu_threshold",
  "description": "CPU使用率多级阈值检测",
  "enabled": true,
  "node_type": "threshold",
  "value_field": "event.cpu_usage",
  "thresholds": [
    {
      "level": 3,
      "operator": "gte",
      "value": 80,
      "priority": 2
    },
    {
      "level": 4,
      "operator": "gte",
      "value": 90,
      "priority": 1
    },
    {
      "level": 5,
      "operator": "gte",
      "value": 95,
      "priority": 0
    }
  ],
  "evaluation_mode": "highest",
  "consecutive_count": 3,
  "detection_window": 300,
  "output_level_field": "alert.severity"
}
```

### 示例 2: 响应时间区间检测

```json
{
  "name": "response_time_threshold",
  "description": "响应时间异常区间检测",
  "enabled": true,
  "node_type": "threshold",
  "value_field": "event.response_time",
  "thresholds": [
    {
      "level": 2,
      "operator": "between",
      "value": 1000,
      "value_max": 2000,
      "priority": 1
    },
    {
      "level": 4,
      "operator": "gt",
      "value": 2000,
      "priority": 0
    }
  ],
  "evaluation_mode": "first",
  "consecutive_count": 2,
  "detection_window": 120,
  "output_level_field": "alert.level"
}
```

### 示例 3: 错误率多阈值检测（返回所有匹配）

```json
{
  "name": "error_rate_threshold",
  "description": "错误率多阈值检测，记录所有触发阈值",
  "enabled": true,
  "node_type": "threshold",
  "value_field": "event.error_rate",
  "thresholds": [
    {
      "level": 2,
      "operator": "gte",
      "value": 0.01,
      "priority": 3
    },
    {
      "level": 3,
      "operator": "gte",
      "value": 0.05,
      "priority": 2
    },
    {
      "level": 4,
      "operator": "gte",
      "value": 0.1,
      "priority": 1
    },
    {
      "level": 5,
      "operator": "gte",
      "value": 0.2,
      "priority": 0
    }
  ],
  "evaluation_mode": "all",
  "consecutive_count": 5,
  "detection_window": 600,
  "output_level_field": "alert.severity",
  "output_matched_thresholds_field": "alert.triggered_thresholds",
  "execution": {
    "timeout": 10,
    "retry_enabled": false
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

## 使用场景

1. **CPU/内存使用率检测**：对系统资源使用率进行多级阈值检测
2. **响应时间监控**：Web服务、API响应时间超过阈值告警
3. **错误率检测**：应用错误率、失败率超过阈值告警
4. **业务指标监控**：订单量、交易额等业务指标的阈值检测
5. **网络流量监控**：带宽使用率、连接数等网络指标检测
6. **数据库性能监控**：慢查询数、连接数、锁等待时间检测
7. **磁盘空间监控**：磁盘使用率、inode使用率阈值检测

## 注意事项

1. **阈值设置**：
   - 阈值应根据历史数据和业务需求合理设置
   - 建议设置多级阈值（warning、error、critical）
   - between 操作符必须同时设置 value 和 value_max

2. **评估模式选择**：
   - `highest`：适合多阈值场景，取最严重级别
   - `first`：按优先级顺序匹配，适合有明确优先级的场景
   - `all`：需要记录所有触发阈值时使用

3. **连续检测**：
   - `consecutive_count > 1` 可避免偶发性告警
   - 建议 CPU、内存等波动指标设置为 3-5 次
   - 关键业务指标可设置为 1 次（立即告警）

4. **检测窗口**：
   - `detection_window` 应大于数据采集周期
   - 过小可能导致数据不足，过大会延迟告警
   - 建议设置为采集周期的 3-5 倍

5. **性能考虑**：
   - 阈值检测通常很快，timeout 可设置较小（5-10秒）
   - 多阈值配置不会显著影响性能
   - 避免在单个节点配置过多阈值（建议<10个）

6. **字段路径**：
   - `value_field` 必须指向数值类型字段
   - 支持嵌套路径，如 `event.metrics.cpu.usage`
   - 字段不存在或非数值时会触发错误处理

7. **优先级设置**：
   - priority 值越小优先级越高
   - 相同 level 的多个阈值通过 priority 区分
   - 建议按严重程度设置优先级

8. **输出字段**：
   - 可自定义输出字段路径
   - `evaluation_mode=all` 时会输出所有匹配的阈值列表
   - 输出字段会添加到事件数据中供下游节点使用

## 相关节点

- **上游节点**：
  - Filter（过滤节点）：先过滤再检测，减少不必要的阈值判断
  - Transform（转换节点）：计算衍生指标后再进行阈值检测
  - Enrichment（丰富化节点）：补充上下文信息后判断阈值
  - Window（窗口节点）：聚合窗口数据后进行阈值检测

- **下游节点**：
  - Severity（级别调整节点）：根据上下文调整阈值检测的级别
  - Router（路由节点）：根据阈值检测结果路由到不同处理流程
  - Notification（通知节点）：阈值触发后发送告警通知
  - Escalation（升级节点）：阈值超过一定时间未恢复则升级
  - Recovery（恢复节点）：检测阈值恢复正常

### 典型组合模式

1. **Transform → Threshold → Notification**
   - 计算指标 → 阈值检测 → 发送告警

2. **Filter → Threshold → Severity → Router → Notification**
   - 过滤 → 阈值检测 → 调整级别 → 路由 → 通知

3. **Window → Threshold → Converge → Notification**
   - 窗口聚合 → 阈值检测 → 收敛 → 通知

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
