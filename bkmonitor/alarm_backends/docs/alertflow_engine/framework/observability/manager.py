"""ObservabilityManager

统一管理 ES 日志写入和查询。
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ES 索引名定义
ES_INDEX_EXECUTION_LOG = "alertflow_execution_log"
ES_INDEX_NODE_LOG = "alertflow_node_log"
ES_INDEX_RATE_LIMIT_LOG = "alertflow_rate_limit_log"
ES_INDEX_SHIELD_LOG = "alertflow_shield_log"
ES_INDEX_CONVERGE_LOG = "alertflow_converge_log"
ES_INDEX_FREQUENCY_RULE_LOG = "alertflow_frequency_rule_log"


class ObservabilityManager:
    """可观测性管理器

    负责：
    1. 将执行日志异步写入 ES
    2. 提供 trace_id 查询接口
    3. 管理 ES 索引
    """

    def __init__(self, es_client=None):
        self._es_client = es_client
        self._buffer: list[dict[str, Any]] = []
        self._buffer_size = 100  # 批量写入阈值

    def _get_es_client(self):
        """懒加载 ES 客户端"""
        if self._es_client is None:
            try:
                from elasticsearch import Elasticsearch

                self._es_client = Elasticsearch(["http://localhost:9200"])
            except ImportError:
                logger.warning("elasticsearch 未安装，日志将不会写入 ES")
        return self._es_client

    def log_pipeline_execution(
        self,
        trace_id: str,
        pipeline_id: str,
        status: str,
        elapsed_ms: float,
        executed_nodes: list[str],
        error: str | None = None,
    ) -> None:
        """记录 Pipeline 执行日志"""
        doc = {
            "trace_id": trace_id,
            "pipeline_id": pipeline_id,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "executed_nodes": executed_nodes,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._write(ES_INDEX_EXECUTION_LOG, doc)

    def log_node_execution(
        self,
        trace_id: str,
        pipeline_id: str,
        node_id: str,
        node_type: str,
        status: str,
        elapsed_ms: float,
        input_data: dict | None = None,
        output_data: dict | None = None,
        error: str | None = None,
    ) -> None:
        """记录节点执行日志"""
        doc = {
            "trace_id": trace_id,
            "pipeline_id": pipeline_id,
            "node_id": node_id,
            "node_type": node_type,
            "status": status,
            "elapsed_ms": elapsed_ms,
            "input_summary": self._summarize(input_data),
            "output_summary": self._summarize(output_data),
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._write(ES_INDEX_NODE_LOG, doc)

    def log_rate_limit(self, trace_id: str, pipeline_id: str, key: str, limited: bool) -> None:
        """记录限流日志"""
        self._write(
            ES_INDEX_RATE_LIMIT_LOG,
            {
                "trace_id": trace_id,
                "pipeline_id": pipeline_id,
                "rate_limit_key": key,
                "limited": limited,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def log_shield(self, trace_id: str, pipeline_id: str, rule_id: str, shielded: bool, reason: str) -> None:
        """记录屏蔽日志"""
        self._write(
            ES_INDEX_SHIELD_LOG,
            {
                "trace_id": trace_id,
                "pipeline_id": pipeline_id,
                "shield_rule_id": rule_id,
                "shielded": shielded,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def log_converge(self, trace_id: str, pipeline_id: str, converge_key: str, converged: bool, reason: str) -> None:
        """记录收敛日志"""
        self._write(
            ES_INDEX_CONVERGE_LOG,
            {
                "trace_id": trace_id,
                "pipeline_id": pipeline_id,
                "converge_key": converge_key,
                "converged": converged,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def query_by_trace_id(self, trace_id: str) -> dict[str, list[dict]]:
        """根据 trace_id 查询完整执行链路"""
        es = self._get_es_client()
        if es is None:
            return {}

        result = {}
        indices = [
            ES_INDEX_EXECUTION_LOG,
            ES_INDEX_NODE_LOG,
            ES_INDEX_RATE_LIMIT_LOG,
            ES_INDEX_SHIELD_LOG,
            ES_INDEX_CONVERGE_LOG,
        ]

        for index in indices:
            try:
                resp = es.search(
                    index=index,
                    body={
                        "query": {"term": {"trace_id": trace_id}},
                        "sort": [{"timestamp": "asc"}],
                        "size": 100,
                    },
                )
                hits = [h["_source"] for h in resp.get("hits", {}).get("hits", [])]
                if hits:
                    result[index] = hits
            except Exception as e:
                logger.warning("查询 ES 索引 %s 异常: %s", index, e)

        return result

    def _write(self, index: str, doc: dict[str, Any]) -> None:
        """写入 ES（带缓冲批量写入）"""
        self._buffer.append({"_index": index, "_source": doc})

        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> None:
        """刷新缓冲区，批量写入 ES"""
        if not self._buffer:
            return

        es = self._get_es_client()
        if es is None:
            self._buffer.clear()
            return

        try:
            from elasticsearch.helpers import bulk

            bulk(es, self._buffer)
            logger.debug("批量写入 ES: %d 条", len(self._buffer))
        except Exception as e:
            logger.error("批量写入 ES 失败: %s", e)
        finally:
            self._buffer.clear()

    @staticmethod
    def _summarize(data: dict | None, max_len: int = 500) -> str | None:
        """摘要数据，避免日志过大"""
        if data is None:
            return None
        import json

        text = json.dumps(data, ensure_ascii=False, default=str)
        if len(text) > max_len:
            return text[:max_len] + "...(truncated)"
        return text
