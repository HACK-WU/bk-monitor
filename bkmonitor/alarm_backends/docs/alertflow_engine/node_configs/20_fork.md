# Fork Node Configuration (分叉节点配置)

## 节点类型
- **NodeType**: `fork`
- **分类**: FLOW_CONTROL (流控类)
- **功能**: 将事件复制到多个并行分支

## 配置 Schema

### ForkNodeConfigSerializer

```python
from rest_framework import serializers


class ForkNodeConfigSerializer(BaseNodeConfigSerializer):
    """分叉节点配置"""
    node_type = serializers.CharField(default="fork", read_only=True)
    
    # TODO: 添加节点特定的配置字段
    # 参考文档：08-node-config-schemas.md 和 09-extended-node-configs.md
```

## 配置字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `node_type` | string | 是 | "fork" | 节点类型标识 |
| `name` | string | 是 | - | 节点实例名称 |
| `description` | string | 否 | "" | 节点描述 |
| `enabled` | boolean | 否 | true | 是否启用 |

## JSON 配置示例

### 示例 1: 基础配置

```json
{
  "name": "fork_example",
  "description": "分叉节点示例",
  "enabled": true,
  "node_type": "fork"
}
```

### 示例 2: 完整配置

```json
{
  "name": "fork_full",
  "description": "分叉节点完整配置示例",
  "enabled": true,
  "node_type": "fork",
  "execution": {
    "timeout": 30,
    "retry_enabled": true,
    "retry_max_attempts": 3
  },
  "error_handling": {
    "on_error": "continue",
    "log_error": true
  }
}
```

### 示例 3: 高级配置

```json
{
  "name": "fork_advanced",
  "description": "分叉节点高级配置示例",
  "enabled": true,
  "node_type": "fork",
  "skip_condition": {
    "logic": "and",
    "conditions": [
      {
        "field": "event.environment",
        "operator": "eq",
        "value": "production"
      }
    ]
  }
}
```

## 使用场景

1. **场景一**：将事件复制到多个并行分支的基础应用
2. **场景二**：与其他节点配合使用
3. **场景三**：复杂业务逻辑处理

## 注意事项

1. 确保 `node_type` 字段值为 `fork`
2. 配置字段需符合 Schema 定义
3. 建议启用错误处理和重试机制
4. 根据实际场景调整 timeout 配置

## 相关节点

- 上游节点：根据业务流程选择合适的上游节点
- 下游节点：根据业务流程选择合适的下游节点

## 参考文档

- [节点配置基础文档](../08-node-config-schemas.md)
- [扩展节点配置文档](../09-extended-node-configs.md)
- [节点配置索引](./README.md)
