# 配置管理设计

> 返回 [目录](./README.md)

## 配置管理设计

### 配置管理方式

框架采用**配置文件 + 数据库 + 命令行工具**的方式进行配置管理:

1. **配置文件**:
   - 支持 JSON 和 YAML 格式
   - 便于版本控制和团队协作
   - 支持配置模板和变量替换

2. **数据库持久化**:
   - PostgreSQL 存储配置元数据
   - 支持配置版本管理
   - 支持配置历史追溯

3. **命令行工具**:
   - 提供 Pipeline 配置的 CRUD 操作
   - 支持配置导入导出
   - 支持配置验证和测试

4. **内部服务接口**:
   - 提供 REST API 供其他服务调用
   - 支持配置查询和更新
   - 支持批量操作

### 配置管理命令

```bash
# 创建 Pipeline 配置
bk-monitor pipeline create --config config/pipeline.yaml

# 更新 Pipeline 配置
bk-monitor pipeline update --pipeline-id pipeline_001 --config config/pipeline.yaml

# 删除 Pipeline 配置
bk-monitor pipeline delete --pipeline-id pipeline_001

# 查询 Pipeline 配置
bk-monitor pipeline get --pipeline-id pipeline_001

# 列出所有 Pipeline 配置
bk-monitor pipeline list

# 验证配置文件
bk-monitor pipeline validate --config config/pipeline.yaml

# 测试 Pipeline 配置
bk-monitor pipeline test --config config/pipeline.yaml --test-data test/event.json
```

### REST API 接口

提供内部服务接口供其他后台服务调用:

```
POST   /api/v1/pipelines/               # 创建 Pipeline
GET    /api/v1/pipelines/               # 获取 Pipeline 列表
GET    /api/v1/pipelines/{id}/          # 获取 Pipeline 详情
PUT    /api/v1/pipelines/{id}/          # 更新 Pipeline
DELETE /api/v1/pipelines/{id}/          # 删除 Pipeline
POST   /api/v1/pipelines/{id}/validate  # 验证配置
POST   /api/v1/pipelines/{id}/test      # 测试配置
GET    /api/v1/pipelines/{id}/versions  # 获取配置版本历史
POST   /api/v1/pipelines/{id}/rollback  # 回滚到指定版本
```

### 配置数据结构

#### Pipeline 配置表

```python
class PipelineConfig:
    id: str                              # Pipeline 唯一标识
    name: str                            # Pipeline 名称
    version: str                         # 版本号
    description: str                     # 描述
    scenario: str                        # 应用场景
    enabled: bool                        # 是否启用
    config_json: Dict[str, Any]          # 完整配置 JSON
    created_at: datetime                 # 创建时间
    updated_at: datetime                 # 更新时间
    created_by: str                      # 创建人
```

#### 配置版本历史表

```python
class PipelineConfigVersion:
    id: str                              # 版本记录 ID
    pipeline_id: str                     # Pipeline ID
    version: str                         # 版本号
    config_json: Dict[str, Any]          # 配置 JSON 快照
    change_reason: str                   # 变更原因
    created_at: datetime                 # 创建时间
    created_by: str                      # 创建人
```


---

**上一篇**: [可观测性设计](./04-observability.md) | **下一篇**: [架构设计总结](./06-summary.md)
