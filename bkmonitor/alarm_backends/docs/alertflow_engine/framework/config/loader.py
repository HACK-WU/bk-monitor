"""配置加载器

支持从 JSON 文件、YAML 文件和数据库加载 Pipeline 配置。
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ConfigLoader:
    """配置加载器

    支持多种配置来源：
    - JSON 文件
    - YAML 文件
    - 数据库（Django ORM）
    - 字典（内存）
    """

    def load_from_file(self, file_path: str) -> dict[str, Any]:
        """从文件加载配置（自动识别 JSON/YAML）"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        content = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix in (".json",):
            return json.loads(content)
        elif suffix in (".yaml", ".yml"):
            return self._load_yaml(content)
        else:
            raise ValueError(f"不支持的配置文件格式: {suffix}")

    def load_from_dict(self, config: dict[str, Any]) -> dict[str, Any]:
        """直接使用字典配置"""
        return config

    def load_from_db(self, pipeline_id: str) -> dict[str, Any]:
        """从数据库加载配置"""
        from framework.config.models import PipelineConfig

        try:
            record = PipelineConfig.objects.get(pipeline_id=pipeline_id)
            return record.config_json
        except PipelineConfig.DoesNotExist:
            raise KeyError(f"Pipeline '{pipeline_id}' 不存在")

    def load(
        self,
        file_path: str | None = None,
        pipeline_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一加载入口，按优先级尝试加载"""
        if config is not None:
            return self.load_from_dict(config)
        if file_path is not None:
            return self.load_from_file(file_path)
        if pipeline_id is not None:
            return self.load_from_db(pipeline_id)
        raise ValueError("必须指定 config、file_path 或 pipeline_id 之一")

    @staticmethod
    def _load_yaml(content: str) -> dict[str, Any]:
        """加载 YAML 内容"""
        try:
            import yaml

            return yaml.safe_load(content) or {}
        except ImportError:
            raise ImportError("需要安装 PyYAML: pip install PyYAML")
