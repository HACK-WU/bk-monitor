"""配置管理器

Pipeline 配置的 CRUD 操作、版本管理和热加载。
"""

import logging
from typing import Any

from framework.config.loader import ConfigLoader
from framework.config.validator import ConfigValidator

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器

    职责：
    1. Pipeline 配置的 CRUD
    2. 配置版本管理和回滚
    3. 配置缓存与热加载
    """

    def __init__(self):
        self._loader = ConfigLoader()
        self._validator = ConfigValidator()
        # 内存缓存: pipeline_id -> config_dict
        self._cache: dict[str, dict[str, Any]] = {}

    def create(
        self,
        config: dict[str, Any],
        created_by: str = "",
    ) -> "PipelineConfig":
        """创建 Pipeline 配置

        Args:
            config: Pipeline 配置字典
            created_by: 创建人

        Returns:
            PipelineConfig ORM 实例
        """
        # 验证配置
        is_valid, errors = self._validator.validate(config)
        if not is_valid:
            raise ValueError(f"配置验证失败: {'; '.join(errors)}")

        from framework.config.models import PipelineConfig, PipelineConfigVersion

        pipeline = PipelineConfig.objects.create(
            pipeline_id=config["id"],
            name=config["name"],
            version=config["version"],
            description=config.get("description", ""),
            scenario=config.get("scenario", "alert"),
            enabled=config.get("enabled", True),
            config_json=config,
            created_by=created_by,
        )

        # 创建初始版本快照
        PipelineConfigVersion.objects.create(
            pipeline=pipeline,
            version=config["version"],
            config_json=config,
            change_reason="初始创建",
            created_by=created_by,
        )

        # 更新缓存
        self._cache[config["id"]] = config
        logger.info("创建 Pipeline: %s v%s", config["id"], config["version"])
        return pipeline

    def update(
        self,
        pipeline_id: str,
        config: dict[str, Any],
        change_reason: str = "",
        updated_by: str = "",
    ) -> "PipelineConfig":
        """更新 Pipeline 配置"""
        is_valid, errors = self._validator.validate(config)
        if not is_valid:
            raise ValueError(f"配置验证失败: {'; '.join(errors)}")

        from framework.config.models import PipelineConfig, PipelineConfigVersion

        try:
            pipeline = PipelineConfig.objects.get(pipeline_id=pipeline_id)
        except PipelineConfig.DoesNotExist:
            raise KeyError(f"Pipeline '{pipeline_id}' 不存在")

        # 更新记录
        pipeline.name = config["name"]
        pipeline.version = config["version"]
        pipeline.description = config.get("description", "")
        pipeline.scenario = config.get("scenario", "alert")
        pipeline.enabled = config.get("enabled", True)
        pipeline.config_json = config
        pipeline.save()

        # 创建版本快照
        PipelineConfigVersion.objects.create(
            pipeline=pipeline,
            version=config["version"],
            config_json=config,
            change_reason=change_reason or "配置更新",
            created_by=updated_by,
        )

        # 更新缓存
        self._cache[pipeline_id] = config
        logger.info("更新 Pipeline: %s -> v%s", pipeline_id, config["version"])
        return pipeline

    def get(self, pipeline_id: str, use_cache: bool = True) -> dict[str, Any]:
        """获取 Pipeline 配置"""
        if use_cache and pipeline_id in self._cache:
            return self._cache[pipeline_id]

        config = self._loader.load_from_db(pipeline_id)
        self._cache[pipeline_id] = config
        return config

    def delete(self, pipeline_id: str) -> None:
        """删除 Pipeline 配置"""
        from framework.config.models import PipelineConfig

        PipelineConfig.objects.filter(pipeline_id=pipeline_id).delete()
        self._cache.pop(pipeline_id, None)
        logger.info("删除 Pipeline: %s", pipeline_id)

    def list_pipelines(self, scenario: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]:
        """列出 Pipeline 配置"""
        from framework.config.models import PipelineConfig

        qs = PipelineConfig.objects.all()
        if scenario is not None:
            qs = qs.filter(scenario=scenario)
        if enabled is not None:
            qs = qs.filter(enabled=enabled)

        return [
            {
                "pipeline_id": p.pipeline_id,
                "name": p.name,
                "version": p.version,
                "scenario": p.scenario,
                "enabled": p.enabled,
                "updated_at": p.updated_at.isoformat(),
            }
            for p in qs
        ]

    def get_versions(self, pipeline_id: str) -> list[dict[str, Any]]:
        """获取配置版本历史"""
        from framework.config.models import PipelineConfig

        try:
            pipeline = PipelineConfig.objects.get(pipeline_id=pipeline_id)
        except PipelineConfig.DoesNotExist:
            raise KeyError(f"Pipeline '{pipeline_id}' 不存在")

        return [
            {
                "version": v.version,
                "change_reason": v.change_reason,
                "created_at": v.created_at.isoformat(),
                "created_by": v.created_by,
            }
            for v in pipeline.versions.all()
        ]

    def rollback(self, pipeline_id: str, version: str, rolled_by: str = "") -> "PipelineConfig":
        """回滚到指定版本"""
        from framework.config.models import PipelineConfig, PipelineConfigVersion

        try:
            pipeline = PipelineConfig.objects.get(pipeline_id=pipeline_id)
        except PipelineConfig.DoesNotExist:
            raise KeyError(f"Pipeline '{pipeline_id}' 不存在")

        try:
            version_record = PipelineConfigVersion.objects.get(pipeline=pipeline, version=version)
        except PipelineConfigVersion.DoesNotExist:
            raise KeyError(f"Pipeline '{pipeline_id}' 无版本 '{version}'")

        return self.update(
            pipeline_id=pipeline_id,
            config=version_record.config_json,
            change_reason=f"回滚到 v{version}",
            updated_by=rolled_by,
        )

    def reload(self, pipeline_id: str) -> dict[str, Any]:
        """热加载配置（清除缓存后重新加载）"""
        self._cache.pop(pipeline_id, None)
        return self.get(pipeline_id, use_cache=False)

    def reload_all(self) -> None:
        """重新加载所有已缓存的配置"""
        pipeline_ids = list(self._cache.keys())
        self._cache.clear()
        for pid in pipeline_ids:
            try:
                self.get(pid, use_cache=False)
            except KeyError:
                logger.warning("Pipeline %s 已被删除，跳过重载", pid)
