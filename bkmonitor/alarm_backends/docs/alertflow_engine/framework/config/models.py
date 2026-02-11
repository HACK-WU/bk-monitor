"""AlertFlow Engine 数据模型

定义 Pipeline 配置和版本管理的 ORM 模型。
"""

from django.db import models


class PipelineConfig(models.Model):
    """Pipeline 配置表

    存储 Pipeline 的完整配置信息，包括节点编排、全局设置等。
    config_json 字段使用 PostgreSQL 的 JSONB 类型存储完整的 Pipeline 配置。
    """

    pipeline_id = models.CharField("Pipeline ID", max_length=128, unique=True, db_index=True)
    name = models.CharField("名称", max_length=256)
    version = models.CharField("版本号", max_length=64, default="1.0.0")
    description = models.TextField("描述", blank=True, default="")
    scenario = models.CharField("应用场景", max_length=64, default="alert")
    enabled = models.BooleanField("是否启用", default=True)
    config_json = models.JSONField("Pipeline 配置", default=dict)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    created_by = models.CharField("创建人", max_length=128, default="")

    class Meta:
        db_table = "alertflow_pipeline_config"
        verbose_name = "Pipeline 配置"
        verbose_name_plural = "Pipeline 配置"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["scenario", "enabled"], name="idx_pipeline_scenario_enabled"),
        ]

    def __str__(self):
        return f"[{self.pipeline_id}] {self.name} v{self.version}"


class PipelineConfigVersion(models.Model):
    """配置版本历史表

    每次 Pipeline 配置变更时自动创建版本快照，支持版本回溯和回滚。
    """

    pipeline = models.ForeignKey(
        PipelineConfig,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="关联 Pipeline",
    )
    version = models.CharField("版本号", max_length=64)
    config_json = models.JSONField("配置快照", default=dict)
    change_reason = models.TextField("变更原因", blank=True, default="")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    created_by = models.CharField("创建人", max_length=128, default="")

    class Meta:
        db_table = "alertflow_pipeline_config_version"
        verbose_name = "Pipeline 配置版本"
        verbose_name_plural = "Pipeline 配置版本"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["pipeline", "version"], name="idx_version_pipeline_ver"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["pipeline", "version"],
                name="uq_pipeline_version",
            ),
        ]

    def __str__(self):
        return f"[{self.pipeline.pipeline_id}] v{self.version}"
