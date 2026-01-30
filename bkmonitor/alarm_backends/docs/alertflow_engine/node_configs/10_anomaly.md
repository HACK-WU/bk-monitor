# Anomaly Node Configuration (异常检测节点配置)

## 节点类型
- **NodeType**: `anomaly`
- **分类**: DETECTION (检测类)
- **功能**: 使用机器学习算法检测异常行为

## 配置 Schema

### AnomalyNodeConfigSerializer

```python
from rest_framework import serializers
from enum import Enum


class AnomalyAlgorithm(str, Enum):
    """异常检测算法"""
    SIGMA_3 = "3sigma"              # 3-sigma 规则
    IQR = "iqr"                     # 四分位距
    ISOLATION_FOREST = "iforest"   # 孤立森林
    LOCAL_OUTLIER = "lof"          # 局部异常因子
    DBSCAN = "dbscan"              # DBSCAN 聚类
    PROPHET = "prophet"            # Prophet 时序预测
    ARIMA = "arima"                # ARIMA 模型


class SigmaAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - 3-sigma"""
    sigma_multiplier = serializers.FloatField(
        default=3.0,
        min_value=1.0,
        max_value=5.0,
        help_text="sigma倍数"
    )


class IQRAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - IQR"""
    iqr_multiplier = serializers.FloatField(
        default=1.5,
        min_value=1.0,
        max_value=3.0,
        help_text="IQR倍数"
    )


class IForestAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - 孤立森林"""
    n_estimators = serializers.IntegerField(
        default=100,
        min_value=50,
        max_value=500,
        help_text="树的数量"
    )
    contamination = serializers.FloatField(
        default=0.1,
        min_value=0.01,
        max_value=0.5,
        help_text="异常比例"
    )
    max_features = serializers.FloatField(
        default=1.0,
        min_value=0.1,
        max_value=1.0,
        help_text="最大特征比例"
    )


class LOFAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - LOF"""
    n_neighbors = serializers.IntegerField(
        default=20,
        min_value=5,
        max_value=100,
        help_text="近邻数量"
    )
    contamination = serializers.FloatField(
        default=0.1,
        min_value=0.01,
        max_value=0.5,
        help_text="异常比例"
    )


class ProphetAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - Prophet"""
    seasonality_mode = serializers.ChoiceField(
        choices=[("additive", "additive"), ("multiplicative", "multiplicative")],
        default="additive",
        help_text="季节性模式"
    )
    changepoint_prior_scale = serializers.FloatField(
        default=0.05,
        min_value=0.001,
        max_value=0.5,
        help_text="变点先验尺度"
    )
    interval_width = serializers.FloatField(
        default=0.95,
        min_value=0.5,
        max_value=0.99,
        help_text="置信区间宽度"
    )


class AnomalyNodeConfigSerializer(BaseNodeConfigSerializer):
    """异常检测节点配置"""
    node_type = serializers.CharField(default="anomaly", read_only=True)
    
    # 检测字段
    value_field = serializers.CharField(help_text="检测值字段路径")
    timestamp_field = serializers.CharField(
        default="event.time",
        help_text="时间戳字段（时序算法必须）"
    )
    
    # 算法配置
    algorithm = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AnomalyAlgorithm],
        default=AnomalyAlgorithm.SIGMA_3.value,
        help_text="检测算法"
    )
    sensitivity = serializers.FloatField(
        default=0.5,
        min_value=0,
        max_value=1,
        help_text="敏感度"
    )
    
    # 算法特定参数（根据 algorithm 选择使用）
    sigma_params = SigmaAlgorithmParamsSerializer(
        required=False,
        allow_null=True,
        help_text="3sigma算法参数"
    )
    iqr_params = IQRAlgorithmParamsSerializer(
        required=False,
        allow_null=True,
        help_text="IQR算法参数"
    )
    iforest_params = IForestAlgorithmParamsSerializer(
        required=False,
        allow_null=True,
        help_text="孤立森林算法参数"
    )
    lof_params = LOFAlgorithmParamsSerializer(
        required=False,
        allow_null=True,
        help_text="LOF算法参数"
    )
    prophet_params = ProphetAlgorithmParamsSerializer(
        required=False,
        allow_null=True,
        help_text="Prophet算法参数"
    )
    
    # 训练配置
    training_window = serializers.IntegerField(
        default=3600,
        min_value=60,
        help_text="训练窗口（秒）"
    )
    min_samples = serializers.IntegerField(
        default=30,
        min_value=10,
        help_text="最小样本数"
    )
    
    # 检测配置
    detection_window = serializers.IntegerField(
        default=60,
        min_value=1,
        help_text="检测窗口（秒）"
    )
    
    # 输出配置
    output_score_field = serializers.CharField(
        default="anomaly.score",
        help_text="异常分数字段"
    )
    output_is_anomaly_field = serializers.CharField(
        default="anomaly.is_anomaly",
        help_text="是否异常字段"
    )
```

## 配置字段说明

### 节点基础字段

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "anomaly" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |
| `value_field` | string | 是 | - | 检测值字段路径 |
| `timestamp_field` | string | 否 | "event.time" | 时间戳字段 |
| `algorithm` | string | 否 | "3sigma" | 检测算法 |
| `sensitivity` | float | 否 | 0.5 | 敏感度(0-1) |
| `training_window` | integer | 否 | 3600 | 训练窗口（秒） |
| `min_samples` | integer | 否 | 30 | 最小样本数 |
| `detection_window` | integer | 否 | 60 | 检测窗口（秒） |
| `output_score_field` | string | 否 | "anomaly.score" | 异常分数字段 |
| `output_is_anomaly_field` | string | 否 | "anomaly.is_anomaly" | 是否异常字段 |

### 算法特定参数

#### 3-Sigma 算法参数 (sigma_params)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sigma_multiplier` | float | 3.0 | sigma倍数(1.0-5.0) |

#### IQR 算法参数 (iqr_params)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `iqr_multiplier` | float | 1.5 | IQR倍数(1.0-3.0) |

#### 孤立森林算法参数 (iforest_params)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `n_estimators` | integer | 100 | 树的数量(50-500) |
| `contamination` | float | 0.1 | 异常比例(0.01-0.5) |
| `max_features` | float | 1.0 | 最大特征比例(0.1-1.0) |

#### LOF 算法参数 (lof_params)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `n_neighbors` | integer | 20 | 近邻数量(5-100) |
| `contamination` | float | 0.1 | 异常比例(0.01-0.5) |

#### Prophet 算法参数 (prophet_params)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `seasonality_mode` | string | "additive" | 季节性模式 |
| `changepoint_prior_scale` | float | 0.05 | 变点先验尺度(0.001-0.5) |
| `interval_width` | float | 0.95 | 置信区间宽度(0.5-0.99) |

### 算法选择说明

| 算法 | 说明 | 适用场景 |
|------|------|----------|
| `3sigma` | 3-西格玛规则 | 正态分布数据，简单快速 |
| `iqr` | 四分位距 | 非正态分布，对离群值鲁棒 |
| `iforest` | 孤立森林 | 高维数据，复杂异常模式 |
| `lof` | 局部异常因子 | 局部密度异常检测 |
| `dbscan` | 聚类算法 | 基于密度的异常检测 |
| `prophet` | 时序预测 | 具有季节性的时序数据 |
| `arima` | 时序模型 | 平稳时序数据 |

## JSON 配置示例

### 示例 1: 3-Sigma 简单异常检测

```json
{
  "name": "metric_anomaly_3sigma",
  "description": "基于3-Sigma的指标异常检测",
  "enabled": true,
  "node_type": "anomaly",
  "value_field": "event.value",
  "timestamp_field": "event.time",
  "algorithm": "3sigma",
  "sensitivity": 0.7,
  "sigma_params": {
    "sigma_multiplier": 3.0
  },
  "training_window": 7200,
  "min_samples": 100,
  "detection_window": 60,
  "output_score_field": "event.anomaly_score",
  "output_is_anomaly_field": "event.is_anomaly"
}
```

### 示例 2: 孤立森林高级异常检测

```json
{
  "name": "iforest_anomaly",
  "description": "孤立森林算法检测复杂异常模式",
  "enabled": true,
  "node_type": "anomaly",
  "value_field": "event.request_latency",
  "algorithm": "iforest",
  "sensitivity": 0.8,
  "iforest_params": {
    "n_estimators": 200,
    "contamination": 0.05,
    "max_features": 1.0
  },
  "training_window": 3600,
  "min_samples": 50,
  "detection_window": 300,
  "output_score_field": "anomaly.iforest_score",
  "output_is_anomaly_field": "anomaly.detected",
  "execution": {
    "timeout": 30,
    "retry_enabled": false
  }
}
```

### 示例 3: Prophet 时序异常检测

```json
{
  "name": "prophet_traffic_anomaly",
  "description": "Prophet算法检测流量异常（含季节性）",
  "enabled": true,
  "node_type": "anomaly",
  "value_field": "event.traffic_volume",
  "timestamp_field": "event.timestamp",
  "algorithm": "prophet",
  "sensitivity": 0.6,
  "prophet_params": {
    "seasonality_mode": "multiplicative",
    "changepoint_prior_scale": 0.05,
    "interval_width": 0.95
  },
  "training_window": 86400,
  "min_samples": 288,
  "detection_window": 300,
  "output_score_field": "anomaly.prophet_score",
  "output_is_anomaly_field": "anomaly.is_traffic_anomaly",
  "error_handling": {
    "on_error": "log",
    "log_error": true
  }
}
```

## 使用场景

1. **指标异常检测**：对CPU、内存、网络流量等指标进行AI智能异常检测
2. **响应时间异常**：检测Web服务、API响应时间的异常波动
3. **业务指标异常**：订单量、交易额等业务指标的异常变化
4. **日志量异常**：检测应用日志量的异常增长（可能隐含故障）
5. **季节性数据检测**：使用Prophet/ARIMA检测具有明显周期性的数据
6. **多维度异常**：使用孤立森林检测高维指标的异常模式
7. **实时流量分析**：对实时流量数据进行在线异常检测

## 注意事项

1. **算法选择**：
   - 3-Sigma/IQR：适合简单场景，计算快速
   - Isolation Forest/LOF：适合复杂异常模式，计算较慢
   - Prophet/ARIMA：适合时序数据，需要充足历史数据

2. **训练窗口设置**：
   - 统计算法：建议 1-2 小时（至少 100 个样本）
   - 机器学习算法：建议 3-6 小时（至少 200 个样本）
   - 时序算法：建议 1-7 天（含完整周期）
   - 样本不足时会跳过检测

3. **敏感度调优**：
   - 0.3-0.5：低敏感度，误报少，漏报多
   - 0.5-0.7：中等敏感度，平衡
   - 0.7-1.0：高敏感度，漏报少，误报多
   - 需根据实际效果调整

4. **性能考虑**：
   - 3-Sigma/IQR：毫秒级，timeout 设置 5-10秒
   - Isolation Forest：秒级，timeout 设置 20-30秒
   - Prophet/ARIMA：十秒级，timeout 设置 60-120秒
   - 避免同时运行大量复杂算法

5. **数据质量**：
   - 确保数据连续性，缺失过多会影响精度
   - 异常值和空值需预先处理
   - 时间戳必须准确（时序算法）

6. **模型维护**：
   - 建议定期重新训练模型（天/周）
   - 数据分布变化时需要重训
   - 可配置模型缓存避免频繁训练

7. **算法参数调优**：
   - sigma_multiplier：更大的值降低敏感度
   - contamination：预期异常比例，需根据实际设置
   - interval_width：置信区间宽度，影响判定范围

8. **输出字段**：
   - anomaly_score：0-1 之间，值越大越异常
   - is_anomaly：布尔值，根据 sensitivity 阈值判定
   - 输出字段会添加到事件数据供下游使用

## 相关节点

- **上游节点**：
  - Filter：过滤出需要检测的数据
  - Transform：计算衍生指标后再检测
  - Window：聚合窗口数据后进行异常检测
  - Enrichment：补充上下文信息后分析

- **下游节点**：
  - Threshold：对异常分数进行阈值判断
  - Router：根据异常类型路由到不同处理流
  - Notification：检测到异常后发送告警
  - Severity：根据异常程度调整告警级别
  - Correlation：与其他指标进行关联分析

### 典型组合模式

1. **Window → Anomaly → Threshold → Notification**
   - 窗口聚合 → 异常检测 → 阈值分类 → 通知

2. **Transform → Anomaly → Router → [Notification|Escalation]**
   - 指标计算 → 异常检测 → 路由分发 → 通知/升级

3. **Anomaly → Correlation → Incident**
   - 异常检测 → 关联分析 → 生成事件

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
