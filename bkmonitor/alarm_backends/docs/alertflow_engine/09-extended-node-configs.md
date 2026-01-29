# 扩展节点配置数据结构

> 返回 [目录](./README.md)

本文档定义新增节点的配置数据结构，按分类组织。

---

## 数据处理类节点 (DATA_PROCESSING)

### 聚合节点配置 (AggregateNodeConfigSerializer)

聚合节点用于对数据进行时间窗口聚合计算。

```python
from rest_framework import serializers


class AggregateFunction(str, Enum):
    """聚合函数"""
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    FIRST = "first"
    LAST = "last"
    PERCENTILE = "percentile"
    STDDEV = "stddev"


class AggregateFieldConfigSerializer(serializers.Serializer):
    """聚合字段配置"""
    source_field = serializers.CharField(help_text="源字段路径")
    target_field = serializers.CharField(help_text="目标字段路径")
    function = serializers.ChoiceField(choices=[(e.value, e.name) for e in AggregateFunction], help_text="聚合函数")
    percentile_value = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100, help_text="百分位值")


class AggregateNodeConfigSerializer(BaseNodeConfigSerializer):
    """聚合节点配置"""
    node_type = serializers.CharField(default="aggregate", read_only=True)
    
    # 聚合键
    group_by_fields = serializers.ListField(child=serializers.CharField(), help_text="分组字段列表")
    
    # 聚合字段
    aggregations = AggregateFieldConfigSerializer(many=True, help_text="聚合配置")
    
    # 时间窗口
    window_type = serializers.ChoiceField(
        choices=[("tumbling", "tumbling"), ("sliding", "sliding"), ("session", "session")], 
        default="tumbling", 
        help_text="窗口类型"
    )
    window_size = serializers.IntegerField(min_value=1, help_text="窗口大小（秒）")
    window_slide = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="滑动步长（秒）")
    
    # 输出配置
    emit_on_close = serializers.BooleanField(default=True, help_text="窗口关闭时输出")
    emit_interval = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="定期输出间隔")
    
    def validate_group_by_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个分组字段")
        return value
    
    def validate_aggregations(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个聚合配置")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "metric_aggregator",
  "description": "指标聚合计算",
  "node_type": "aggregate",
  "group_by_fields": ["event.strategy_id", "event.ip"],
  "aggregations": [
    {
      "source_field": "event.value",
      "target_field": "aggregated.avg_value",
      "function": "avg"
    },
    {
      "source_field": "event.value",
      "target_field": "aggregated.max_value",
      "function": "max"
    },
    {
      "source_field": "event.value",
      "target_field": "aggregated.p99_value",
      "function": "percentile",
      "percentile_value": 99
    },
    {
      "source_field": "event.id",
      "target_field": "aggregated.count",
      "function": "count"
    }
  ],
  "window_type": "tumbling",
  "window_size": 60,
  "emit_on_close": true
}
```

---

### 窗口节点配置 (WindowNodeConfigSerializer)

窗口节点用于数据的时间窗口处理。

```python
from rest_framework import serializers


class WindowNodeConfigSerializer(BaseNodeConfigSerializer):
    """窗口节点配置"""
    node_type = serializers.CharField(default="window", read_only=True)
    
    # 窗口类型
    window_type = serializers.ChoiceField(
        choices=[("tumbling", "tumbling"), ("sliding", "sliding"), ("session", "session"), ("count", "count")],
        help_text="窗口类型"
    )
    
    # 时间窗口配置
    window_size = serializers.IntegerField(default=60, min_value=1, help_text="窗口大小（秒/条数）")
    window_slide = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="滑动步长")
    session_gap = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="会话间隔")
    
    # 时间字段
    timestamp_field = serializers.CharField(default="event.time", help_text="时间戳字段")
    
    # 窗口键
    window_key_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="窗口键字段")
    
    # 输出策略
    output_strategy = serializers.ChoiceField(
        choices=[("all", "all"), ("first", "first"), ("last", "last"), ("sample", "sample")], 
        default="all", 
        help_text="输出策略"
    )
    sample_size = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="采样数量")
```

**JSON 配置示例：**

```json
{
  "name": "event_window",
  "description": "事件时间窗口",
  "node_type": "window",
  "window_type": "sliding",
  "window_size": 300,
  "window_slide": 60,
  "timestamp_field": "event.time",
  "window_key_fields": ["event.strategy_id"],
  "output_strategy": "all"
}
```

---

### 采样节点配置 (SampleNodeConfigSerializer)

采样节点用于数据降采样处理。

```python
from rest_framework import serializers


class SampleMethod(str, Enum):
    """采样方法"""
    RANDOM = "random"           # 随机采样
    FIRST = "first"             # 取前 N 条
    LAST = "last"               # 取后 N 条
    RESERVOIR = "reservoir"     # 蓄水池采样
    STRATIFIED = "stratified"   # 分层采样


class SampleNodeConfigSerializer(BaseNodeConfigSerializer):
    """采样节点配置"""
    node_type = serializers.CharField(default="sample", read_only=True)
    
    # 采样方法
    method = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in SampleMethod], 
        default=SampleMethod.RANDOM.value, 
        help_text="采样方法"
    )
    
    # 采样参数
    sample_rate = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=1, help_text="采样率")
    sample_count = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="采样数量")
    
    # 分层采样配置
    stratify_field = serializers.CharField(required=False, allow_null=True, help_text="分层字段")
    
    # 时间窗口
    window_size = serializers.IntegerField(default=60, min_value=1, help_text="采样窗口（秒）")
```

**JSON 配置示例：**

```json
{
  "name": "data_sampler",
  "description": "数据降采样",
  "node_type": "sample",
  "method": "random",
  "sample_rate": 0.1,
  "window_size": 60
}
```

---

### 分裂节点配置 (SplitNodeConfigSerializer)

分裂节点用于将一条数据拆分为多条。

```python
from rest_framework import serializers


class SplitNodeConfigSerializer(BaseNodeConfigSerializer):
    """分裂节点配置"""
    node_type = serializers.CharField(default="split", read_only=True)
    
    # 分裂字段
    split_field = serializers.CharField(help_text="要分裂的数组字段路径")
    
    # 输出配置
    output_field = serializers.CharField(default="split_item", help_text="分裂后的字段名")
    include_index = serializers.BooleanField(default=False, help_text="是否包含索引")
    index_field = serializers.CharField(default="split_index", help_text="索引字段名")
    
    # 保留原字段
    preserve_original = serializers.BooleanField(default=False, help_text="是否保留原数组字段")
```

**JSON 配置示例：**

```json
{
  "name": "dimension_splitter",
  "description": "按维度分裂事件",
  "node_type": "split",
  "split_field": "event.dimensions",
  "output_field": "dimension",
  "include_index": true,
  "index_field": "dimension_index",
  "preserve_original": false
}
```

---

### 关联节点配置 (JoinNodeConfigSerializer)

关联节点用于多数据源关联。

```python
from rest_framework import serializers


class JoinType(str, Enum):
    """关联类型"""
    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    OUTER = "outer"


class JoinNodeConfigSerializer(BaseNodeConfigSerializer):
    """关联节点配置"""
    node_type = serializers.CharField(default="join", read_only=True)
    
    # 关联类型
    join_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in JoinType], 
        default=JoinType.LEFT.value, 
        help_text="关联类型"
    )
    
    # 关联键
    left_key_fields = serializers.ListField(child=serializers.CharField(), help_text="左侧关联键")
    right_key_fields = serializers.ListField(child=serializers.CharField(), help_text="右侧关联键")
    
    # 右侧数据源
    right_source = DataSourceConfigSerializer(help_text="右侧数据源配置")
    
    # 输出字段映射
    right_field_mappings = FieldMappingSerializer(many=True, required=False, default=list, help_text="右侧字段映射")
    
    # 关联窗口
    join_window = serializers.IntegerField(default=60, min_value=1, help_text="关联时间窗口（秒）")
    
    # 缓存配置
    cache_enabled = serializers.BooleanField(default=True, help_text="是否缓存右侧数据")
    cache_ttl = serializers.IntegerField(default=300, min_value=0, help_text="缓存TTL")
    
    def validate_left_key_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个左侧关联键")
        return value
    
    def validate_right_key_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个右侧关联键")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "alert_context_join",
  "description": "关联告警上下文",
  "node_type": "join",
  "join_type": "left",
  "left_key_fields": ["event.alert_id"],
  "right_key_fields": ["alert_id"],
  "right_source": {
    "type": "database",
    "db_connection": "default",
    "db_query": "SELECT * FROM alert_context WHERE alert_id = ?"
  },
  "right_field_mappings": [
    {
      "source_field": "context",
      "target_field": "event.context"
    }
  ],
  "join_window": 300,
  "cache_enabled": true,
  "cache_ttl": 600
}
```

---

## 检测类节点 (DETECTION)

### 阈值检测节点配置 (ThresholdNodeConfigSerializer)

阈值检测节点用于静态/动态阈值判断。

```python
from rest_framework import serializers


class ThresholdOperator(str, Enum):
    """阈值操作符"""
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
    level = serializers.IntegerField(min_value=1, max_value=5, help_text="告警级别")
    operator = serializers.ChoiceField(choices=[(e.value, e.name) for e in ThresholdOperator], help_text="比较操作符")
    value = serializers.FloatField(help_text="阈值")
    value_max = serializers.FloatField(required=False, allow_null=True, help_text="区间最大值（between操作符时必填）")
    priority = serializers.IntegerField(default=0, min_value=0, help_text="评估优先级，值越小优先级越高")


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
    consecutive_count = serializers.IntegerField(default=1, min_value=1, help_text="连续满足次数")
    
    # 检测窗口
    detection_window = serializers.IntegerField(default=60, min_value=1, help_text="检测窗口（秒）")
    
    # 输出配置
    output_level_field = serializers.CharField(default="alert.level", help_text="输出级别字段")
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

**JSON 配置示例：**

```json
{
  "name": "cpu_threshold",
  "description": "CPU使用率阈值检测",
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

---

### 异常检测节点配置 (AnomalyNodeConfigSerializer)

异常检测节点用于基于 AI/统计的智能异常检测。

```python
from rest_framework import serializers


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
    sigma_multiplier = serializers.FloatField(default=3.0, min_value=1.0, max_value=5.0, help_text="sigma倍数")


class IQRAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - IQR"""
    iqr_multiplier = serializers.FloatField(default=1.5, min_value=1.0, max_value=3.0, help_text="IQR倍数")


class IForestAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - 孤立森林"""
    n_estimators = serializers.IntegerField(default=100, min_value=50, max_value=500, help_text="树的数量")
    contamination = serializers.FloatField(default=0.1, min_value=0.01, max_value=0.5, help_text="异常比例")
    max_features = serializers.FloatField(default=1.0, min_value=0.1, max_value=1.0, help_text="最大特征比例")


class LOFAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - LOF"""
    n_neighbors = serializers.IntegerField(default=20, min_value=5, max_value=100, help_text="近邻数量")
    contamination = serializers.FloatField(default=0.1, min_value=0.01, max_value=0.5, help_text="异常比例")


class ProphetAlgorithmParamsSerializer(serializers.Serializer):
    """算法参数 - Prophet"""
    seasonality_mode = serializers.ChoiceField(
        choices=[("additive", "additive"), ("multiplicative", "multiplicative")],
        default="additive",
        help_text="季节性模式"
    )
    changepoint_prior_scale = serializers.FloatField(default=0.05, min_value=0.001, max_value=0.5, help_text="变点先验尺度")
    interval_width = serializers.FloatField(default=0.95, min_value=0.5, max_value=0.99, help_text="置信区间宽度")


class AnomalyNodeConfigSerializer(BaseNodeConfigSerializer):
    """异常检测节点配置"""
    node_type = serializers.CharField(default="anomaly", read_only=True)
    
    # 检测字段
    value_field = serializers.CharField(help_text="检测值字段路径")
    timestamp_field = serializers.CharField(default="event.time", help_text="时间戳字段（时序算法必须）")
    
    # 算法配置
    algorithm = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in AnomalyAlgorithm], 
        default=AnomalyAlgorithm.SIGMA_3.value, 
        help_text="检测算法"
    )
    sensitivity = serializers.FloatField(default=0.5, min_value=0, max_value=1, help_text="敏感度")
    
    # 算法特定参数（根据 algorithm 选择使用）
    sigma_params = SigmaAlgorithmParamsSerializer(required=False, allow_null=True, help_text="3sigma算法参数")
    iqr_params = IQRAlgorithmParamsSerializer(required=False, allow_null=True, help_text="IQR算法参数")
    iforest_params = IForestAlgorithmParamsSerializer(required=False, allow_null=True, help_text="孤立森林算法参数")
    lof_params = LOFAlgorithmParamsSerializer(required=False, allow_null=True, help_text="LOF算法参数")
    prophet_params = ProphetAlgorithmParamsSerializer(required=False, allow_null=True, help_text="Prophet算法参数")
    
    # 训练配置
    training_window = serializers.IntegerField(default=3600, min_value=60, help_text="训练窗口（秒）")
    min_samples = serializers.IntegerField(default=30, min_value=10, help_text="最小样本数")
    
    # 检测配置
    detection_window = serializers.IntegerField(default=60, min_value=1, help_text="检测窗口（秒）")
    
    # 输出配置
    output_score_field = serializers.CharField(default="anomaly.score", help_text="异常分数字段")
    output_is_anomaly_field = serializers.CharField(default="anomaly.is_anomaly", help_text="是否异常字段")
```

**JSON 配置示例：**

```json
{
  "name": "metric_anomaly",
  "description": "指标异常检测",
  "node_type": "anomaly",
  "value_field": "event.value",
  "algorithm": "3sigma",
  "sensitivity": 0.7,
  "training_window": 7200,
  "min_samples": 100,
  "detection_window": 60,
  "output_score_field": "event.anomaly_score",
  "output_is_anomaly_field": "event.is_anomaly"
}
```

---

### 基线检测节点配置 (BaselineNodeConfigSerializer)

基线检测节点用于环比、同比基线对比检测。

```python
from rest_framework import serializers


class BaselineType(str, Enum):
    """基线类型"""
    HOUR_ON_HOUR = "hour_on_hour"     # 环比（小时）
    DAY_ON_DAY = "day_on_day"         # 环比（天）
    WEEK_ON_WEEK = "week_on_week"     # 同比（周）
    MONTH_ON_MONTH = "month_on_month" # 同比（月）
    CUSTOM = "custom"                  # 自定义


class BaselineNodeConfigSerializer(BaseNodeConfigSerializer):
    """基线检测节点配置"""
    node_type = serializers.CharField(default="baseline", read_only=True)
    
    # 检测字段
    value_field = serializers.CharField(help_text="检测值字段路径")
    timestamp_field = serializers.CharField(default="event.time", help_text="时间戳字段（用于确定对比时间点）")
    
    # 基线类型
    baseline_type = serializers.ChoiceField(choices=[(e.value, e.name) for e in BaselineType], help_text="基线类型")
    custom_offset = serializers.IntegerField(required=False, allow_null=True, help_text="自定义偏移（秒）")
    
    # 对比配置
    comparison_periods = serializers.IntegerField(default=1, min_value=1, max_value=7, help_text="对比周期数")
    aggregation_method = serializers.ChoiceField(
        choices=[("avg", "avg"), ("max", "max"), ("min", "min"), ("median", "median")],
        default="avg",
        help_text="多周期聚合方法"
    )
    
    # 阈值配置
    upper_threshold_percent = serializers.FloatField(default=50, min_value=0, help_text="上升阈值百分比")
    lower_threshold_percent = serializers.FloatField(default=50, min_value=0, help_text="下降阈值百分比")
    
    # 输出配置
    output_baseline_field = serializers.CharField(default="baseline.value", help_text="基线值字段")
    output_deviation_field = serializers.CharField(default="baseline.deviation", help_text="偏差字段")
    output_deviation_percent_field = serializers.CharField(default="baseline.deviation_percent", help_text="偏差百分比字段")
```

**JSON 配置示例：**

```json
{
  "name": "traffic_baseline",
  "description": "流量环比检测",
  "node_type": "baseline",
  "value_field": "event.request_count",
  "baseline_type": "hour_on_hour",
  "comparison_periods": 3,
  "upper_threshold_percent": 100,
  "lower_threshold_percent": 50,
  "output_baseline_field": "event.baseline_value",
  "output_deviation_field": "event.deviation_percent"
}
```

---

### 趋势检测节点配置 (TrendNodeConfigSerializer)

趋势检测节点用于上升/下降趋势、突增突降检测。

```python
from rest_framework import serializers


class TrendType(str, Enum):
    """趋势类型"""
    RISING = "rising"           # 上升趋势
    FALLING = "falling"         # 下降趋势
    SPIKE = "spike"             # 突增
    DROP = "drop"               # 突降
    VOLATILITY = "volatility"   # 波动


class TrendNodeConfigSerializer(BaseNodeConfigSerializer):
    """趋势检测节点配置"""
    node_type = serializers.CharField(default="trend", read_only=True)
    
    # 检测字段
    value_field = serializers.CharField(help_text="检测值字段路径")
    
    # 趋势类型
    trend_types = serializers.ListField(
        child=serializers.ChoiceField(choices=[(e.value, e.name) for e in TrendType]),
        help_text="检测的趋势类型"
    )
    
    # 检测配置
    window_size = serializers.IntegerField(default=300, min_value=60, help_text="检测窗口（秒）")
    min_points = serializers.IntegerField(default=5, min_value=3, help_text="最小数据点数")
    
    # 阈值配置
    slope_threshold = serializers.FloatField(default=0.1, min_value=0, help_text="斜率阈值")
    spike_threshold_percent = serializers.FloatField(default=100, min_value=0, help_text="突增阈值百分比")
    drop_threshold_percent = serializers.FloatField(default=50, min_value=0, help_text="突降阈值百分比")
    
    # 输出配置
    output_trend_field = serializers.CharField(default="trend.type", help_text="趋势类型字段")
    output_slope_field = serializers.CharField(default="trend.slope", help_text="斜率字段")
    
    def validate_trend_types(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个趋势类型")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "latency_trend",
  "description": "延迟趋势检测",
  "node_type": "trend",
  "value_field": "event.latency",
  "trend_types": ["rising", "spike"],
  "window_size": 600,
  "min_points": 10,
  "slope_threshold": 0.05,
  "spike_threshold_percent": 200,
  "output_trend_field": "event.trend_type",
  "output_slope_field": "event.trend_slope"
}
```

---

### 关联检测节点配置 (CorrelationNodeConfigSerializer)

关联检测节点用于多指标关联分析和根因定位。

```python
from rest_framework import serializers


class CorrelationMethod(str, Enum):
    """关联分析方法"""
    PEARSON = "pearson"           # 皮尔逊相关
    SPEARMAN = "spearman"         # 斯皮尔曼相关
    GRANGER = "granger"           # 格兰杰因果
    DTW = "dtw"                   # 动态时间规整


class CorrelationNodeConfigSerializer(BaseNodeConfigSerializer):
    """关联检测节点配置"""
    node_type = serializers.CharField(default="correlation", read_only=True)
    
    # 主指标
    primary_field = serializers.CharField(help_text="主指标字段路径")
    
    # 关联指标
    secondary_fields = serializers.ListField(child=serializers.CharField(), help_text="关联指标字段列表")
    
    # 分析方法
    method = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in CorrelationMethod], 
        default=CorrelationMethod.PEARSON.value, 
        help_text="关联分析方法"
    )
    
    # 分析配置
    window_size = serializers.IntegerField(default=3600, min_value=60, help_text="分析窗口（秒）")
    correlation_threshold = serializers.FloatField(default=0.7, min_value=0, max_value=1, help_text="相关性阈值")
    
    # 输出配置
    output_correlations_field = serializers.CharField(default="correlation.results", help_text="关联结果字段")
    output_root_cause_field = serializers.CharField(default="correlation.root_cause", help_text="根因字段")
    
    def validate_secondary_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个关联指标字段")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "error_correlation",
  "description": "错误关联分析",
  "node_type": "correlation",
  "primary_field": "event.error_rate",
  "secondary_fields": [
    "event.cpu_usage",
    "event.memory_usage",
    "event.disk_io",
    "event.network_latency"
  ],
  "method": "pearson",
  "window_size": 1800,
  "correlation_threshold": 0.8,
  "output_correlations_field": "event.correlations",
  "output_root_cause_field": "event.probable_root_cause"
}
```

---

## 流控类节点 (FLOW_CONTROL)

### 延迟节点配置 (DelayNodeConfigSerializer)

延迟节点用于延迟处理（等待恢复、防抖动）。

```python
from rest_framework import serializers


class DelayNodeConfigSerializer(BaseNodeConfigSerializer):
    """延迟节点配置"""
    node_type = serializers.CharField(default="delay", read_only=True)
    
    # 延迟时间
    delay_seconds = serializers.IntegerField(min_value=1, max_value=3600, help_text="延迟时间（秒）")
    
    # 延迟键
    delay_key_template = serializers.CharField(required=False, allow_null=True, help_text="延迟键模板")
    
    # 取消条件
    cancel_on_recovery = serializers.BooleanField(default=True, help_text="恢复时取消延迟")
    cancel_condition = ConditionGroupSerializer(required=False, allow_null=True, help_text="取消条件")
    
    # 存储配置
    storage_type = serializers.ChoiceField(
        choices=[("memory", "memory"), ("redis", "redis")], 
        default="redis", 
        help_text="存储类型"
    )
```

**JSON 配置示例：**

```json
{
  "name": "alert_delay",
  "description": "告警延迟发送（防抖动）",
  "node_type": "delay",
  "delay_seconds": 300,
  "delay_key_template": "{event.strategy_id}:{event.dimension_hash}",
  "cancel_on_recovery": true,
  "cancel_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.status",
        "operator": "eq",
        "value": "recovered"
      }
    ]
  },
  "storage_type": "redis"
}
```

---

### 分叉节点配置 (ForkNodeConfigSerializer)

分叉节点用于数据复制到多个分支并行处理。

```python
from rest_framework import serializers


class ForkNodeConfigSerializer(BaseNodeConfigSerializer):
    """分叉节点配置"""
    node_type = serializers.CharField(default="fork", read_only=True)
    
    # 目标分支
    target_stages = serializers.ListField(child=serializers.CharField(), help_text="目标阶段列表")
    
    # 复制策略
    copy_mode = serializers.ChoiceField(
        choices=[("shallow", "shallow"), ("deep", "deep")], 
        default="deep", 
        help_text="复制模式"
    )
    
    # 等待配置
    wait_for_all = serializers.BooleanField(default=False, help_text="是否等待所有分支完成")
    timeout = serializers.IntegerField(default=60, min_value=1, help_text="等待超时（秒）")
    
    def validate_target_stages(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("至少需要两个目标阶段")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "parallel_fork",
  "description": "并行分叉处理",
  "node_type": "fork",
  "target_stages": ["notification_stage", "storage_stage", "analysis_stage"],
  "copy_mode": "deep",
  "wait_for_all": false
}
```

---

### 合并节点配置 (MergeNodeConfigSerializer)

合并节点用于多个分支数据合并。

```python
from rest_framework import serializers


class MergeStrategy(str, Enum):
    """合并策略"""
    FIRST = "first"       # 取第一个
    LAST = "last"         # 取最后一个
    ALL = "all"           # 合并所有
    VOTE = "vote"         # 投票


class MergeNodeConfigSerializer(BaseNodeConfigSerializer):
    """合并节点配置"""
    node_type = serializers.CharField(default="merge", read_only=True)
    
    # 源分支
    source_stages = serializers.ListField(child=serializers.CharField(), help_text="源阶段列表")
    
    # 合并策略
    strategy = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in MergeStrategy], 
        default=MergeStrategy.ALL.value, 
        help_text="合并策略"
    )
    
    # 等待配置
    wait_for_all = serializers.BooleanField(default=True, help_text="是否等待所有分支")
    timeout = serializers.IntegerField(default=60, min_value=1, help_text="等待超时（秒）")
    
    # 合并键
    merge_key_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="合并键字段")
    
    def validate_source_stages(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("至少需要两个源阶段")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "result_merge",
  "description": "合并分支结果",
  "node_type": "merge",
  "source_stages": ["analysis_a", "analysis_b"],
  "strategy": "all",
  "wait_for_all": true,
  "timeout": 120,
  "merge_key_fields": ["event.alert_id"]
}
```

---

## 告警生命周期类节点 (ALERT_LIFECYCLE)

### 抑制节点配置 (SuppressNodeConfigSerializer)

抑制节点用于告警抑制（主机/依赖关系抑制）。

```python
from rest_framework import serializers


class SuppressType(str, Enum):
    """抑制类型"""
    DEPENDENCY = "dependency"   # 依赖关系抑制
    PARENT = "parent"           # 父级抑制
    SIBLING = "sibling"         # 同级抑制
    CUSTOM = "custom"           # 自定义抑制


class SuppressNodeConfigSerializer(BaseNodeConfigSerializer):
    """抑制节点配置"""
    node_type = serializers.CharField(default="suppress", read_only=True)
    
    # 抑制类型
    suppress_type = serializers.ChoiceField(choices=[(e.value, e.name) for e in SuppressType], help_text="抑制类型")
    
    # 抑制键
    suppress_key_fields = serializers.ListField(child=serializers.CharField(), help_text="抑制键字段")
    
    # 依赖关系配置
    dependency_field = serializers.CharField(required=False, allow_null=True, help_text="依赖关系字段")
    dependency_source = DataSourceConfigSerializer(required=False, allow_null=True, help_text="依赖数据源")
    
    # 抑制时间
    suppress_window = serializers.IntegerField(default=300, min_value=1, help_text="抑制窗口（秒）")
    
    # 日志记录
    log_suppressed = serializers.BooleanField(default=True, help_text="是否记录被抑制的告警")
    
    def validate_suppress_key_fields(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个抑制键字段")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "dependency_suppress",
  "description": "依赖关系抑制",
  "node_type": "suppress",
  "suppress_type": "dependency",
  "suppress_key_fields": ["event.service_name"],
  "dependency_field": "event.depends_on",
  "dependency_source": {
    "type": "cmdb",
    "cmdb_object_type": "service_dependency"
  },
  "suppress_window": 600,
  "log_suppressed": true
}
```

---

### 恢复节点配置 (RecoveryNodeConfigSerializer)

恢复节点用于告警自动恢复检测。

```python
from rest_framework import serializers


class RecoveryConditionType(str, Enum):
    """恢复条件类型"""
    THRESHOLD = "threshold"     # 阈值恢复
    TIMEOUT = "timeout"         # 超时恢复
    MANUAL = "manual"           # 手动恢复
    CONDITION = "condition"     # 条件恢复


class RecoveryOperator(str, Enum):
    """恢复比较操作符"""
    LT = "lt"           # 小于
    LTE = "lte"         # 小于等于
    GT = "gt"           # 大于
    GTE = "gte"         # 大于等于
    EQ = "eq"           # 等于
    BETWEEN = "between" # 区间


class RecoveryNodeConfigSerializer(BaseNodeConfigSerializer):
    """恢复节点配置"""
    node_type = serializers.CharField(default="recovery", read_only=True)
    
    # 恢复条件类型
    recovery_type = serializers.ChoiceField(choices=[(e.value, e.name) for e in RecoveryConditionType], help_text="恢复条件类型")
    
    # 阈值恢复配置
    recovery_threshold = serializers.FloatField(required=False, allow_null=True, help_text="恢复阈值")
    recovery_threshold_max = serializers.FloatField(required=False, allow_null=True, help_text="恢复阈值最大值（between操作符时使用）")
    recovery_operator = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in RecoveryOperator],
        default=RecoveryOperator.LT.value,
        required=False,
        help_text="恢复阈值比较操作符"
    )
    value_field = serializers.CharField(required=False, allow_null=True, help_text="值字段")
    
    # 超时恢复配置
    recovery_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="恢复超时（秒）")
    
    # 条件恢复配置
    recovery_condition = ConditionGroupSerializer(required=False, allow_null=True, help_text="恢复条件")
    
    # 连续检测
    consecutive_count = serializers.IntegerField(default=1, min_value=1, help_text="连续满足次数")
    
    # 恢复通知
    send_recovery_notification = serializers.BooleanField(default=True, help_text="是否发送恢复通知")
```

**JSON 配置示例：**

```json
{
  "name": "auto_recovery",
  "description": "自动恢复检测",
  "node_type": "recovery",
  "recovery_type": "threshold",
  "recovery_threshold": 70,
  "value_field": "event.cpu_usage",
  "consecutive_count": 3,
  "send_recovery_notification": true
}
```

---

### 升级节点配置 (EscalationNodeConfigSerializer)

升级节点用于告警升级（未处理→升级通知）。

```python
from rest_framework import serializers


class EscalationLevelSerializer(serializers.Serializer):
    """升级链单个级别配置"""
    timeout = serializers.IntegerField(min_value=60, help_text="等待时间（秒），超过后触发升级")
    escalate_to_level = serializers.IntegerField(min_value=1, max_value=5, help_text="升级到的告警级别")
    recipients = RecipientConfigSerializer(help_text="升级通知接收人")
    channels = serializers.ListField(
        child=serializers.ChoiceField(choices=[(e.value, e.name) for e in NotificationChannel]),
        help_text="升级通知渠道"
    )
    message_template = serializers.CharField(required=False, allow_null=True, help_text="升级通知模板（可覆盖默认）")


class EscalationNodeConfigSerializer(BaseNodeConfigSerializer):
    """升级节点配置"""
    node_type = serializers.CharField(default="escalation", read_only=True)
    
    # 升级条件
    escalation_timeout = serializers.IntegerField(min_value=60, help_text="升级超时（秒）")
    
    # 升级级别
    escalate_to_level = serializers.IntegerField(min_value=1, max_value=5, help_text="升级到级别")
    
    # 升级通知
    escalation_recipients = RecipientConfigSerializer(help_text="升级通知接收人")
    escalation_channels = serializers.ListField(
        child=serializers.ChoiceField(choices=[(e.value, e.name) for e in NotificationChannel]),
        help_text="升级通知渠道"
    )
    
    # 多级升级（完整结构定义）
    escalation_chain = EscalationLevelSerializer(many=True, required=False, default=list, help_text="升级链 - 多级升级配置")
    
    # 排除条件
    exclude_acknowledged = serializers.BooleanField(default=True, help_text="排除已确认的告警")
    exclude_shielded = serializers.BooleanField(default=True, help_text="排除已屏蔽的告警")
```

**JSON 配置示例：**

```json
{
  "name": "alert_escalation",
  "description": "告警升级",
  "node_type": "escalation",
  "escalation_timeout": 1800,
  "escalate_to_level": 4,
  "escalation_recipients": {
    "source": "cmdb",
    "cmdb_role": "manager"
  },
  "escalation_channels": ["voice", "sms"],
  "escalation_chain": [
    {
      "timeout": 1800,
      "escalate_to_level": 4,
      "recipients": {
        "source": "cmdb",
        "cmdb_role": "manager"
      },
      "channels": ["wework", "sms"],
      "message_template": null
    },
    {
      "timeout": 3600,
      "escalate_to_level": 5,
      "recipients": {
        "source": "cmdb",
        "cmdb_role": "director"
      },
      "channels": ["voice", "sms"],
      "message_template": "[紧急升级] {{ event.alert_name }} 已超过1小时未处理"
    }
  ],
  "exclude_acknowledged": true,
  "exclude_shielded": true
}
```

---

### 确认节点配置 (AcknowledgeNodeConfigSerializer)

确认节点用于告警确认处理。

```python
from rest_framework import serializers


class AcknowledgeNodeConfigSerializer(BaseNodeConfigSerializer):
    """确认节点配置"""
    node_type = serializers.CharField(default="acknowledge", read_only=True)
    
    # 确认来源
    ack_source = serializers.ChoiceField(
        choices=[("api", "api"), ("webhook", "webhook"), ("auto", "auto")], 
        default="api", 
        help_text="确认来源"
    )
    
    # 自动确认条件
    auto_ack_condition = ConditionGroupSerializer(required=False, allow_null=True, help_text="自动确认条件")
    
    # 确认超时
    ack_timeout = serializers.IntegerField(required=False, allow_null=True, min_value=1, help_text="确认超时（秒）")
    
    # 确认后动作
    on_ack_action = serializers.ChoiceField(
        choices=[("continue", "continue"), ("stop", "stop"), ("redirect", "redirect")], 
        default="continue", 
        help_text="确认后动作"
    )
    redirect_stage = serializers.CharField(required=False, allow_null=True, help_text="重定向阶段")
```

**JSON 配置示例：**

```json
{
  "name": "alert_acknowledge",
  "description": "告警确认处理",
  "node_type": "acknowledge",
  "ack_source": "api",
  "ack_timeout": 3600,
  "on_ack_action": "redirect",
  "redirect_stage": "acknowledged_handling"
}
```

---

### 级别调整节点配置 (SeverityNodeConfigSerializer)

级别调整节点用于动态调整告警级别。

```python
from rest_framework import serializers


class SeverityAdjustmentType(str, Enum):
    """级别调整类型"""
    RELATIVE = "relative"     # 相对调整（+1, -1）
    ABSOLUTE = "absolute"     # 绝对调整（设为固定值）


class SeverityAdjustmentConditionSerializer(serializers.Serializer):
    """级别调整条件"""
    field = serializers.CharField(help_text="字段路径")
    operator = serializers.ChoiceField(choices=[(e.value, e.name) for e in MatchOperator], help_text="比较操作符")
    value = serializers.JSONField(help_text="比较值")
    case_sensitive = serializers.BooleanField(default=True, required=False, help_text="是否区分大小写")


class SeverityAdjustmentRuleSerializer(serializers.Serializer):
    """级别调整规则 - 单条规则定义"""
    name = serializers.CharField(required=False, allow_null=True, max_length=128, help_text="规则名称")
    condition = SeverityAdjustmentConditionSerializer(help_text="触发条件")
    condition_group = ConditionGroupSerializer(required=False, allow_null=True, help_text="复杂条件组（与condition二选一）")
    adjustment_type = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in SeverityAdjustmentType],
        default=SeverityAdjustmentType.RELATIVE.value,
        help_text="调整类型"
    )
    adjustment_value = serializers.IntegerField(min_value=-4, max_value=4, help_text="调整值（相对调整时为增量，绝对调整时为目标级别）")
    priority = serializers.IntegerField(default=0, min_value=0, help_text="规则优先级，值越小优先级越高")
    enabled = serializers.BooleanField(default=True, help_text="规则是否启用")


class SeverityNodeConfigSerializer(BaseNodeConfigSerializer):
    """级别调整节点配置"""
    node_type = serializers.CharField(default="severity", read_only=True)
    
    # 调整规则（完整结构定义）
    adjustment_rules = SeverityAdjustmentRuleSerializer(many=True, help_text="调整规则列表")
    
    # 级别字段
    severity_field = serializers.CharField(default="event.severity", help_text="级别字段")
    
    # 边界控制
    min_severity = serializers.IntegerField(default=1, min_value=1, max_value=5, help_text="最低级别")
    max_severity = serializers.IntegerField(default=5, min_value=1, max_value=5, help_text="最高级别")
    
    # 评估模式
    evaluation_mode = serializers.ChoiceField(
        choices=[("first_match", "first_match"), ("all_match", "all_match"), ("cumulative", "cumulative")],
        default="first_match",
        help_text="评估模式：first_match=第一个匹配的规则生效, all_match=所有匹配规则的最后一个生效, cumulative=累加所有匹配规则的调整值"
    )
    
    def validate_adjustment_rules(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一条调整规则")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "severity_adjuster",
  "description": "动态调整告警级别",
  "node_type": "severity",
  "adjustment_rules": [
    {
      "name": "vip_service_upgrade",
      "condition": {
        "field": "event.is_vip_service",
        "operator": "eq",
        "value": true
      },
      "adjustment_type": "relative",
      "adjustment_value": 1,
      "priority": 0,
      "enabled": true
    },
    {
      "name": "night_downgrade",
      "condition": {
        "field": "event.time_of_day",
        "operator": "between",
        "value": [0, 6]
      },
      "adjustment_type": "relative",
      "adjustment_value": -1,
      "priority": 1,
      "enabled": true
    },
    {
      "name": "critical_service_absolute",
      "condition": {
        "field": "event.service_tier",
        "operator": "eq",
        "value": "critical"
      },
      "adjustment_type": "absolute",
      "adjustment_value": 5,
      "priority": 2,
      "enabled": true
    }
  ],
  "severity_field": "event.severity",
  "min_severity": 1,
  "max_severity": 5,
  "evaluation_mode": "first_match"
}
```

---

### 不监控节点配置 (NoMonitorNodeConfigSerializer)

不监控节点用于标记某些事件/告警不需要被监控系统处理，直接跳过后续流程。

```python
from rest_framework import serializers
from enum import Enum


class NoMonitorAction(str, Enum):
    """不监控动作类型"""
    DROP = "drop"              # 丢弃事件，不做任何处理
    MARK_ONLY = "mark_only"    # 仅标记，继续流转但不触发通知
    LOG = "log"                # 记录日志后丢弃
    ARCHIVE = "archive"        # 归档保存但不处理


class NoMonitorRuleSerializer(serializers.Serializer):
    """不监控规则定义"""
    name = serializers.CharField(required=False, allow_null=True, max_length=128, help_text="规则名称")
    condition = ConditionSerializer(required=False, allow_null=True, help_text="匹配条件（简单条件）")
    condition_group = ConditionGroupSerializer(required=False, allow_null=True, help_text="匹配条件组（复杂条件，与condition二选一）")
    action = serializers.ChoiceField(
        choices=[(a.value, a.value) for a in NoMonitorAction],
        default="drop",
        help_text="匹配后的动作"
    )
    reason = serializers.CharField(max_length=512, required=False, allow_null=True, help_text="不监控原因（用于日志和审计）")
    priority = serializers.IntegerField(default=0, min_value=0, help_text="规则优先级，值越小优先级越高")
    enabled = serializers.BooleanField(default=True, help_text="规则是否启用")
    
    # 有效期配置
    valid_from = serializers.DateTimeField(required=False, allow_null=True, help_text="生效开始时间")
    valid_until = serializers.DateTimeField(required=False, allow_null=True, help_text="生效结束时间")


class NoMonitorNodeConfigSerializer(BaseNodeConfigSerializer):
    """不监控节点配置"""
    node_type = serializers.CharField(default="no_monitor", read_only=True)
    
    # 规则来源
    rules_source = serializers.ChoiceField(
        choices=[("inline", "inline"), ("database", "database"), ("api", "api")],
        default="inline",
        help_text="规则来源：inline=配置内嵌, database=数据库, api=外部API"
    )
    
    # 内嵌规则（rules_source=inline时使用）
    rules = NoMonitorRuleSerializer(many=True, required=False, help_text="不监控规则列表")
    
    # 数据库/API规则配置
    rules_cache_ttl = serializers.IntegerField(default=60, min_value=0, help_text="规则缓存TTL（秒）")
    rules_api_url = serializers.CharField(required=False, allow_null=True, help_text="规则API地址（rules_source=api时）")
    
    # 默认动作（无匹配规则时）
    default_action = serializers.ChoiceField(
        choices=[("pass", "pass"), ("drop", "drop")],
        default="pass",
        help_text="默认动作：pass=继续处理, drop=丢弃"
    )
    
    # 标记字段
    mark_field = serializers.CharField(default="_no_monitor", required=False, help_text="标记字段名")
    mark_reason_field = serializers.CharField(default="_no_monitor_reason", required=False, help_text="原因字段名")
    
    # 审计配置
    audit_enabled = serializers.BooleanField(default=True, help_text="是否记录审计日志")
    
    def validate(self, attrs):
        if attrs.get("rules_source") == "inline":
            if not attrs.get("rules"):
                raise serializers.ValidationError({"rules": "内嵌模式必须提供规则列表"})
        elif attrs.get("rules_source") == "api":
            if not attrs.get("rules_api_url"):
                raise serializers.ValidationError({"rules_api_url": "API模式必须提供API地址"})
        return attrs
```

**JSON 配置示例：**

```json
{
  "name": "test_env_no_monitor",
  "description": "测试环境不监控",
  "node_type": "no_monitor",
  "rules_source": "inline",
  "rules": [
    {
      "name": "exclude_test_hosts",
      "condition": {
        "field": "event.host",
        "operator": "regex",
        "value": "^test-.*"
      },
      "action": "drop",
      "reason": "测试环境主机不监控",
      "priority": 0,
      "enabled": true
    },
    {
      "name": "exclude_debug_alerts",
      "condition": {
        "field": "event.tags.environment",
        "operator": "eq",
        "value": "debug"
      },
      "action": "log",
      "reason": "调试告警仅记录不处理",
      "priority": 1,
      "enabled": true
    },
    {
      "name": "maintenance_window",
      "condition": {
        "field": "event.service",
        "operator": "in",
        "value": ["service-a", "service-b"]
      },
      "action": "archive",
      "reason": "维护窗口期间归档",
      "priority": 2,
      "enabled": true,
      "valid_from": "2024-01-15T00:00:00Z",
      "valid_until": "2024-01-15T06:00:00Z"
    }
  ],
  "default_action": "pass",
  "mark_field": "_no_monitor",
  "mark_reason_field": "_no_monitor_reason",
  "audit_enabled": true
}
```

---

## 动作类节点 (ACTION)

### Webhook 节点配置 (WebhookNodeConfigSerializer)

Webhook 节点用于发送 HTTP 请求。

```python
from rest_framework import serializers


class WebhookResponseHandlingSerializer(serializers.Serializer):
    """响应处理配置"""
    success_status_codes = serializers.ListField(
        child=serializers.IntegerField(),
        default=[200, 201, 202, 204],
        help_text="成功状态码列表"
    )
    extract_fields = serializers.DictField(
        default=dict,
        required=False,
        help_text="从响应体提取字段的映射，如 {'response_id': '$.data.id'}"
    )
    store_response_body = serializers.BooleanField(default=False, help_text="是否存储完整响应体")
    response_field = serializers.CharField(default="webhook.response", required=False, help_text="响应存储字段")


class WebhookNodeConfigSerializer(BaseNodeConfigSerializer):
    """Webhook 节点配置"""
    node_type = serializers.CharField(default="webhook", read_only=True)
    
    # 请求配置
    url = serializers.CharField(help_text="Webhook URL")
    method = serializers.ChoiceField(
        choices=[("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"), ("PATCH", "PATCH"), ("DELETE", "DELETE")], 
        default="POST", 
        help_text="HTTP 方法"
    )
    headers = serializers.DictField(default=dict, required=False, help_text="请求头")
    
    # 请求体
    body_template = serializers.CharField(required=False, allow_null=True, help_text="请求体模板")
    content_type = serializers.ChoiceField(
        choices=[("json", "json"), ("form", "form"), ("text", "text")], 
        default="json", 
        help_text="内容类型"
    )
    
    # 认证
    auth_type = serializers.ChoiceField(
        choices=[("basic", "basic"), ("bearer", "bearer"), ("api_key", "api_key")], 
        required=False, 
        allow_null=True, 
        help_text="认证类型"
    )
    auth_config = serializers.DictField(required=False, allow_null=True, help_text="认证配置")
    
    # 重试配置
    retry_on_failure = serializers.BooleanField(default=True, help_text="失败重试")
    retry_status_codes = serializers.ListField(
        child=serializers.IntegerField(), 
        default=[500, 502, 503, 504], 
        help_text="重试状态码"
    )
    
    # 超时配置
    connect_timeout = serializers.IntegerField(default=10, min_value=1, help_text="连接超时（秒）")
    read_timeout = serializers.IntegerField(default=30, min_value=1, help_text="读取超时（秒）")
    
    # 响应处理
    response_handling = WebhookResponseHandlingSerializer(required=False, allow_null=True, help_text="响应处理配置")
```

**JSON 配置示例：**

```json
{
  "name": "slack_webhook",
  "description": "发送到 Slack",
  "node_type": "webhook",
  "url": "https://hooks.slack.com/services/xxx",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body_template": "{\"text\": \"[{{ event.severity_display }}] {{ event.alert_name }}\", \"channel\": \"#alerts\"}",
  "content_type": "json",
  "retry_on_failure": true,
  "connect_timeout": 10,
  "read_timeout": 30
}
```

---

### 故障事件节点配置 (IncidentNodeConfigSerializer)

故障事件节点用于创建/更新故障事件。

```python
from rest_framework import serializers


class IncidentAction(str, Enum):
    """故障事件动作"""
    CREATE = "create"
    UPDATE = "update"
    RESOLVE = "resolve"
    MERGE = "merge"


class IncidentNodeConfigSerializer(BaseNodeConfigSerializer):
    """故障事件节点配置"""
    node_type = serializers.CharField(default="incident", read_only=True)
    
    # 动作类型
    action = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in IncidentAction], 
        default=IncidentAction.CREATE.value, 
        help_text="动作类型"
    )
    
    # 事件字段映射
    title_template = serializers.CharField(help_text="标题模板")
    description_template = serializers.CharField(default="", required=False, help_text="描述模板")
    
    # 分类配置
    category_field = serializers.CharField(required=False, allow_null=True, help_text="分类字段")
    priority_field = serializers.CharField(required=False, allow_null=True, help_text="优先级字段")
    
    # 关联配置
    correlation_key_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="关联键字段")
    merge_window = serializers.IntegerField(default=300, min_value=1, help_text="合并窗口（秒）")
    
    # 外部系统
    external_system = serializers.CharField(required=False, allow_null=True, help_text="外部系统标识")
```

**JSON 配置示例：**

```json
{
  "name": "create_incident",
  "description": "创建故障事件",
  "node_type": "incident",
  "action": "create",
  "title_template": "[{{ event.severity_display }}] {{ event.alert_name }}",
  "description_template": "告警详情: {{ event.content }}\n\n影响范围: {{ event.scope }}",
  "category_field": "event.category",
  "priority_field": "event.severity",
  "correlation_key_fields": ["event.strategy_id", "event.biz_id"],
  "merge_window": 600
}
```

---

### 回调节点配置 (CallbackNodeConfigSerializer)

回调节点用于外部系统回调处理。

```python
from rest_framework import serializers


class CallbackNodeConfigSerializer(BaseNodeConfigSerializer):
    """回调节点配置"""
    node_type = serializers.CharField(default="callback", read_only=True)
    
    # 回调配置
    callback_id = serializers.CharField(help_text="回调标识")
    callback_type = serializers.ChoiceField(
        choices=[("sync", "sync"), ("async", "async")], 
        default="async", 
        help_text="回调类型"
    )
    
    # 等待配置
    wait_for_response = serializers.BooleanField(default=False, help_text="是否等待响应")
    wait_timeout = serializers.IntegerField(default=60, min_value=1, help_text="等待超时（秒）")
    
    # 响应处理
    response_field_mapping = FieldMappingSerializer(many=True, required=False, default=list, help_text="响应字段映射")
    on_timeout_action = serializers.ChoiceField(
        choices=[("continue", "continue"), ("fail", "fail"), ("retry", "retry")], 
        default="continue", 
        help_text="超时动作"
    )
```

**JSON 配置示例：**

```json
{
  "name": "approval_callback",
  "description": "审批回调",
  "node_type": "callback",
  "callback_id": "approval_{{ event.alert_id }}",
  "callback_type": "async",
  "wait_for_response": true,
  "wait_timeout": 3600,
  "response_field_mapping": [
    {
      "source_field": "approved",
      "target_field": "event.is_approved"
    },
    {
      "source_field": "approver",
      "target_field": "event.approver"
    }
  ],
  "on_timeout_action": "continue"
}
```

---

## 存储类节点 (STORAGE)

### 存储节点配置 (StorageNodeConfigSerializer)

存储节点用于数据持久化存储。

```python
from rest_framework import serializers


class StorageType(str, Enum):
    """存储类型"""
    ELASTICSEARCH = "elasticsearch"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    KAFKA = "kafka"
    INFLUXDB = "influxdb"


class StorageNodeConfigSerializer(BaseNodeConfigSerializer):
    """存储节点配置"""
    node_type = serializers.CharField(default="storage", read_only=True)
    
    # 存储类型
    storage_type = serializers.ChoiceField(choices=[(e.value, e.name) for e in StorageType], help_text="存储类型")
    
    # 连接配置
    connection_name = serializers.CharField(help_text="连接名称")
    
    # ES 配置
    es_index_template = serializers.CharField(required=False, allow_null=True, help_text="ES 索引模板")
    es_doc_type = serializers.CharField(default="_doc", required=False, help_text="ES 文档类型")
    
    # DB 配置
    table_name = serializers.CharField(required=False, allow_null=True, help_text="表名")
    field_mapping = FieldMappingSerializer(many=True, required=False, default=list, help_text="字段映射")
    
    # Kafka 配置
    topic = serializers.CharField(required=False, allow_null=True, help_text="Kafka Topic")
    partition_key_field = serializers.CharField(required=False, allow_null=True, help_text="分区键字段")
    
    # 批量配置
    batch_size = serializers.IntegerField(default=100, min_value=1, help_text="批量大小")
    flush_interval = serializers.IntegerField(default=5, min_value=1, help_text="刷新间隔（秒）")
```

**JSON 配置示例：**

```json
{
  "name": "alert_storage",
  "description": "告警数据存储到 ES",
  "node_type": "storage",
  "storage_type": "elasticsearch",
  "connection_name": "default_es",
  "es_index_template": "alerts-{{ event.biz_id }}-{{ event.date }}",
  "batch_size": 200,
  "flush_interval": 10
}
```

---

### 查询节点配置 (QueryNodeConfigSerializer)

查询节点用于从外部数据源查询数据。

```python
from rest_framework import serializers


class QueryNodeConfigSerializer(BaseNodeConfigSerializer):
    """查询节点配置"""
    node_type = serializers.CharField(default="query", read_only=True)
    
    # 数据源
    data_source = DataSourceConfigSerializer(help_text="数据源配置")
    
    # 查询配置
    query_template = serializers.CharField(help_text="查询模板")
    query_params = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="查询参数字段")
    
    # 结果配置
    result_field = serializers.CharField(default="query_result", help_text="结果字段")
    single_result = serializers.BooleanField(default=False, help_text="是否单条结果")
    
    # 缓存配置
    cache_enabled = serializers.BooleanField(default=True, help_text="是否启用缓存")
    cache_ttl = serializers.IntegerField(default=300, min_value=0, help_text="缓存TTL")
```

**JSON 配置示例：**

```json
{
  "name": "history_query",
  "description": "查询历史告警",
  "node_type": "query",
  "data_source": {
    "type": "database",
    "db_connection": "default"
  },
  "query_template": "SELECT * FROM alerts WHERE strategy_id = ? AND status = 'active' ORDER BY create_time DESC LIMIT 10",
  "query_params": ["event.strategy_id"],
  "result_field": "event.history_alerts",
  "single_result": false,
  "cache_enabled": true,
  "cache_ttl": 60
}
```

---

### 日志节点配置 (LogNodeConfigSerializer)

日志节点用于记录处理日志。

```python
from rest_framework import serializers


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogNodeConfigSerializer(BaseNodeConfigSerializer):
    """日志节点配置"""
    node_type = serializers.CharField(default="log", read_only=True)
    
    # 日志配置
    log_level = serializers.ChoiceField(
        choices=[(e.value, e.name) for e in LogLevel], 
        default=LogLevel.INFO.value, 
        help_text="日志级别"
    )
    log_template = serializers.CharField(help_text="日志模板")
    
    # 字段配置
    include_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="包含字段")
    exclude_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="排除字段")
    
    # 存储配置
    storage_type = serializers.ChoiceField(
        choices=[("file", "file"), ("elasticsearch", "elasticsearch"), ("stdout", "stdout")], 
        default="elasticsearch", 
        help_text="存储类型"
    )
    es_index = serializers.CharField(required=False, allow_null=True, help_text="ES 索引")
    file_path = serializers.CharField(required=False, allow_null=True, help_text="文件路径")
```

**JSON 配置示例：**

```json
{
  "name": "audit_log",
  "description": "审计日志记录",
  "node_type": "log",
  "log_level": "info",
  "log_template": "[{{ event.trace_id }}] Alert {{ event.alert_id }} processed: {{ event.status }}",
  "include_fields": ["event.alert_id", "event.strategy_id", "event.status", "event.operator"],
  "storage_type": "elasticsearch",
  "es_index": "audit-logs-{{ event.date }}"
}
```

---

### 指标生成节点配置 (MetricNodeConfigSerializer)

指标生成节点用于生成监控指标。

```python
from rest_framework import serializers


class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class MetricDefinitionSerializer(serializers.Serializer):
    """指标定义"""
    name = serializers.CharField(help_text="指标名称")
    type = serializers.ChoiceField(choices=[(e.value, e.name) for e in MetricType], help_text="指标类型")
    value_field = serializers.CharField(help_text="值字段")
    label_fields = serializers.ListField(child=serializers.CharField(), required=False, default=list, help_text="标签字段")
    description = serializers.CharField(default="", required=False, help_text="指标描述")


class MetricNodeConfigSerializer(BaseNodeConfigSerializer):
    """指标生成节点配置"""
    node_type = serializers.CharField(default="metric", read_only=True)
    
    # 指标定义
    metrics = MetricDefinitionSerializer(many=True, help_text="指标定义列表")
    
    # 导出配置
    export_type = serializers.ChoiceField(
        choices=[("prometheus", "prometheus"), ("influxdb", "influxdb"), ("statsd", "statsd")], 
        default="prometheus", 
        help_text="导出类型"
    )
    export_endpoint = serializers.CharField(required=False, allow_null=True, help_text="导出端点")
    
    # 前缀配置
    metric_prefix = serializers.CharField(default="alertflow_", help_text="指标前缀")
    
    def validate_metrics(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("至少需要一个指标定义")
        return value
```

**JSON 配置示例：**

```json
{
  "name": "pipeline_metrics",
  "description": "Pipeline 处理指标",
  "node_type": "metric",
  "metrics": [
    {
      "name": "alerts_processed_total",
      "type": "counter",
      "value_field": "1",
      "label_fields": ["event.strategy_id", "event.severity"],
      "description": "Total alerts processed"
    },
    {
      "name": "alert_processing_duration_seconds",
      "type": "histogram",
      "value_field": "event.processing_duration",
      "label_fields": ["event.node_type"],
      "description": "Alert processing duration"
    }
  ],
  "export_type": "prometheus",
  "metric_prefix": "bkmonitor_alertflow_"
}
```

---

## 节点类型汇总表（完整版）

| 分类 | 节点类型 | 配置类 | 用途 |
|------|---------|-------|------|
| **DATA_PROCESSING** | filter | FilterNodeConfigSerializer | 条件过滤 |
| | transform | TransformNodeConfigSerializer | 数据转换 |
| | enrichment | EnrichmentNodeConfigSerializer | 数据丰富 |
| | aggregate | AggregateNodeConfigSerializer | 数据聚合 |
| | window | WindowNodeConfigSerializer | 窗口处理 |
| | sample | SampleNodeConfigSerializer | 数据采样 |
| | split | SplitNodeConfigSerializer | 数据分裂 |
| | join | JoinNodeConfigSerializer | 数据关联 |
| **DETECTION** | threshold | ThresholdNodeConfigSerializer | 阈值检测 |
| | anomaly | AnomalyNodeConfigSerializer | 异常检测 |
| | baseline | BaselineNodeConfigSerializer | 基线检测 |
| | trend | TrendNodeConfigSerializer | 趋势检测 |
| | correlation | CorrelationNodeConfigSerializer | 关联检测 |
| **FLOW_CONTROL** | router | RouterNodeConfigSerializer | 条件路由 |
| | circuit_breaker | CircuitBreakerNodeConfigSerializer | 熔断保护 |
| | rate_limit | RateLimitNodeConfigSerializer | 限流控制 |
| | dedupe | DedupeNodeConfigSerializer | 去重 |
| | converge | ConvergeNodeConfigSerializer | 告警收敛 |
| | delay | DelayNodeConfigSerializer | 延迟处理 |
| | fork | ForkNodeConfigSerializer | 并行分叉 |
| | merge | MergeNodeConfigSerializer | 分支合并 |
| **ALERT_LIFECYCLE** | shield | ShieldNodeConfigSerializer | 屏蔽规则 |
| | suppress | SuppressNodeConfigSerializer | 告警抑制 |
| | recovery | RecoveryNodeConfigSerializer | 恢复检测 |
| | escalation | EscalationNodeConfigSerializer | 告警升级 |
| | acknowledge | AcknowledgeNodeConfigSerializer | 告警确认 |
| | severity | SeverityNodeConfigSerializer | 级别调整 |
| **ACTION** | notification | NotificationNodeConfigSerializer | 通知发送 |
| | action | ActionNodeConfigSerializer | 自动化动作 |
| | webhook | WebhookNodeConfigSerializer | Webhook 调用 |
| | incident | IncidentNodeConfigSerializer | 故障事件 |
| | callback | CallbackNodeConfigSerializer | 回调处理 |
| **STORAGE** | storage | StorageNodeConfigSerializer | 数据存储 |
| | query | QueryNodeConfigSerializer | 数据查询 |
| | log | LogNodeConfigSerializer | 日志记录 |
| | metric | MetricNodeConfigSerializer | 指标生成 |

---

**上一篇**: [节点配置数据结构](./08-node-config-schemas.md) | **下一篇**: 无

---

> 返回 [目录](./README.md)
