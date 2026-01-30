# AlertFlow Engine 节点配置文档

本目录包含 AlertFlow Engine 所有节点的独立配置文档。

## 目录结构

### 数据处理类 (DATA_PROCESSING)
1. [Filter - 过滤节点](./01_filter.md)
2. [Transform - 转换节点](./02_transform.md)
3. [Enrichment - 丰富化节点](./03_enrichment.md)
4. [Aggregate - 聚合节点](./04_aggregate.md)
5. [Window - 窗口节点](./05_window.md)
6. [Sample - 采样节点](./06_sample.md)
7. [Split - 分裂节点](./07_split.md)
8. [Join - 关联节点](./08_join.md)

### 检测类 (DETECTION)
9. [Threshold - 阈值检测节点](./09_threshold.md)
10. [Anomaly - 异常检测节点](./10_anomaly.md)
11. [Baseline - 基线检测节点](./11_baseline.md)
12. [Trend - 趋势检测节点](./12_trend.md)
13. [Correlation - 关联检测节点](./13_correlation.md)

### 流控类 (FLOW_CONTROL)
14. [Router - 路由节点](./14_router.md)
15. [CircuitBreaker - 熔断节点](./15_circuit_breaker.md)
16. [RateLimit - 限流节点](./16_rate_limit.md)
17. [Dedupe - 去重节点](./17_dedupe.md)
18. [Converge - 收敛节点](./18_converge.md)
19. [Delay - 延迟节点](./19_delay.md)
20. [Fork - 分叉节点](./20_fork.md)
21. [Merge - 合并节点](./21_merge.md)

### 告警生命周期类 (ALERT_LIFECYCLE)
22. [Shield - 屏蔽节点](./22_shield.md)
23. [Suppress - 抑制节点](./23_suppress.md)
24. [Recovery - 恢复节点](./24_recovery.md)
25. [Escalation - 升级节点](./25_escalation.md)
26. [Acknowledge - 确认节点](./26_acknowledge.md)
27. [Severity - 级别调整节点](./27_severity.md)
28. [NoMonitor - 不监控节点](./28_no_monitor.md)

### 动作类 (ACTION)
29. [Notification - 通知节点](./29_notification.md)
30. [Action - 自动化动作节点](./30_action.md)
31. [Webhook - Webhook节点](./31_webhook.md)
32. [Incident - 故障事件节点](./32_incident.md)
33. [Callback - 回调节点](./33_callback.md)
38. [Issues - 问题跟踪节点](./38_issues.md)

### 存储类 (STORAGE)
34. [Storage - 存储节点](./34_storage.md)
35. [Query - 查询节点](./35_query.md)
36. [Log - 日志节点](./36_log.md)
37. [Metric - 指标生成节点](./37_metric.md)

## 文档规范

每个节点配置文档包含以下部分：

1. **节点类型**：NodeType、分类、功能说明
2. **配置 Schema**：完整的 Serializer 定义
3. **配置字段说明**：字段表格说明
4. **JSON 配置示例**：至少3个典型场景的示例
5. **使用场景**：节点的典型应用场景
6. **注意事项**：配置时需要注意的要点

## 快速查找

### 按功能查找

- **数据筛选**：Filter, Sample
- **数据转换**：Transform, Enrichment
- **数据聚合**：Aggregate, Window, Join
- **异常检测**：Threshold, Anomaly, Baseline, Trend
- **流量控制**：Router, CircuitBreaker, RateLimit, Dedupe, Converge
- **告警管理**：Shield, Suppress, Recovery, Escalation, Severity, NoMonitor
- **执行动作**：Notification, Action, Webhook, Incident, Callback
- **数据存储**：Storage, Query, Log, Metric

### 按应用场景查找

- **告警降噪**：Filter, Dedupe, Converge, Suppress, Shield
- **告警丰富**：Enrichment, Transform
- **告警路由**：Router, Fork
- **告警升级**：Escalation, Severity
- **告警通知**：Notification, Webhook
- **系统保护**：CircuitBreaker, RateLimit
- **故障处理**：Incident, Issues, Action, Callback
- **问题跟踪**：Issues（告警后续跟踪、外部系统集成）
- **数据分析**：Aggregate, Window, Correlation
