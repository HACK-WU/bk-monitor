"""Enrichment 丰富化节点

支持 CMDB 数据获取、自定义映射、静态值注入和标签补充。
"""

import logging
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


class EnrichmentSource:
    """丰富化数据源基类"""

    def fetch(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CMDBSource(EnrichmentSource):
    """CMDB 数据源"""

    def fetch(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        """从 CMDB API 获取主机信息并缓存"""
        ip = context.event.get("ip", "")
        bk_cloud_id = context.event.get("bk_cloud_id", 0)

        if not ip:
            return {}

        # TODO: 对接真实 CMDB API + Redis 缓存
        # 当前返回基础结构，后续集成真实接口
        return {
            "host": {
                "ip": ip,
                "bk_cloud_id": bk_cloud_id,
                "bk_biz_id": context.event.get("bk_biz_id", 0),
            }
        }


class CustomMappingSource(EnrichmentSource):
    """自定义字段映射"""

    def fetch(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        mapping = config.get("mapping", {})
        result = {}
        for target_field, source_path in mapping.items():
            value = self._resolve_path(context.event, source_path)
            if value is not None:
                result[target_field] = value
        return result

    @staticmethod
    def _resolve_path(data: dict, path: str) -> Any:
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value


class StaticSource(EnrichmentSource):
    """静态值注入"""

    def fetch(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        return config.get("static_values", {})


class TagSource(EnrichmentSource):
    """标签补充"""

    def fetch(self, context: ProcessContext, config: dict[str, Any]) -> dict[str, Any]:
        tags = config.get("tags", {})
        return {"tags": tags}


# 数据源类型映射
_SOURCE_MAP: dict[str, type] = {
    "cmdb": CMDBSource,
    "custom": CustomMappingSource,
    "static": StaticSource,
    "tag": TagSource,
}


@register_processor
class EnrichmentNode(BaseNode):
    """丰富化节点

    根据配置的丰富化类型，从不同数据源获取信息并注入到事件数据中。

    配置示例:
    {
        "enrichments": [
            {"type": "cmdb", "config": {}},
            {"type": "static", "config": {"static_values": {"team": "ops"}}},
            {"type": "custom", "config": {"mapping": {"env": "labels.environment"}}}
        ],
        "fallback_values": {"team": "unknown"},
        "timeout": 5
    }
    """

    name = "enrichment"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._enrichments = config.get("enrichments", [])
        self._fallback_values = config.get("fallback_values", {})
        self._timeout = config.get("timeout", 5)

    def process(self, context: ProcessContext) -> ProcessResult:
        enriched_data = {}

        for enrichment in self._enrichments:
            enrich_type = enrichment.get("type", "")
            enrich_config = enrichment.get("config", {})

            source_class = _SOURCE_MAP.get(enrich_type)
            if not source_class:
                logger.warning("[%s] 未知丰富化类型: %s", context.trace_id, enrich_type)
                continue

            try:
                source = source_class()
                data = source.fetch(context, enrich_config)
                enriched_data.update(data)
            except Exception as e:
                logger.warning(
                    "[%s] 丰富化 %s 失败: %s，使用降级值",
                    context.trace_id,
                    enrich_type,
                    e,
                )

        # 应用降级默认值
        for key, default_value in self._fallback_values.items():
            if key not in enriched_data:
                enriched_data[key] = default_value

        # 将丰富化数据合并到事件
        context.event.update(enriched_data)

        return ProcessResult(
            status=ProcessStatus.SUCCESS,
            data=enriched_data,
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enrichments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {"type": "string", "enum": ["cmdb", "custom", "static", "tag"]},
                            "config": {"type": "object"},
                        },
                    },
                },
                "fallback_values": {"type": "object"},
                "timeout": {"type": "integer", "minimum": 1, "default": 5},
            },
        }
