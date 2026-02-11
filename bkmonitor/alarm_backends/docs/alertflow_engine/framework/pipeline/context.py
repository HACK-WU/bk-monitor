"""Pipeline 执行上下文

ProcessContext 是 Pipeline 中节点间传递数据和状态的核心载体。
"""

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProcessContext:
    """处理上下文 - 在节点间传递的数据容器

    Attributes:
        trace_id: 全链路追踪 ID
        pipeline_id: 所属 Pipeline ID
        event: 原始事件数据
        alert: 告警数据（在处理过程中生成/更新）
        variables: 全局变量（节点间共享）
        upstream: 上游节点输出，key 为节点 ID
        metadata: 元数据（来源、时间戳等）
        should_stop: 是否终止后续节点执行
        error: 错误信息
        metrics: 性能指标
        executed_nodes: 已执行节点 ID 列表
    """

    # 追踪与标识
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    pipeline_id: str = ""

    # 业务数据
    event: dict[str, Any] = field(default_factory=dict)
    alert: dict[str, Any] | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    upstream: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)

    # 流程控制
    should_stop: bool = False
    error: str | None = None

    # 可观测性
    metrics: dict[str, Any] = field(default_factory=dict)
    executed_nodes: list[str] = field(default_factory=list)

    # 内部时间戳
    _created_at: float = field(default_factory=time.time, repr=False)

    def set_upstream_output(self, node_id: str, output: dict[str, Any]) -> None:
        """记录节点输出到 upstream，供下游节点引用"""
        self.upstream[node_id] = output

    def get_upstream_output(self, node_id: str) -> dict[str, Any] | None:
        """获取指定上游节点的输出"""
        return self.upstream.get(node_id)

    def get_upstream_field(self, node_id: str, field_path: str, default: Any = None) -> Any:
        """获取上游节点输出的嵌套字段

        支持点分隔路径，如 get_upstream_field("filter_01", "result.matched")
        """
        output = self.upstream.get(node_id)
        if output is None:
            return default

        keys = field_path.split(".")
        value = output
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    def record_node_execution(self, node_id: str) -> None:
        """记录已执行的节点"""
        self.executed_nodes.append(node_id)

    def stop(self, reason: str = "") -> None:
        """终止 Pipeline 执行"""
        self.should_stop = True
        if reason:
            self.error = reason

    @property
    def elapsed_ms(self) -> float:
        """从创建到当前的耗时（毫秒）"""
        return (time.time() - self._created_at) * 1000

    def clone(self) -> "ProcessContext":
        """深拷贝上下文（用于分支/并行场景）"""
        return copy.deepcopy(self)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "trace_id": self.trace_id,
            "pipeline_id": self.pipeline_id,
            "event": self.event,
            "alert": self.alert,
            "variables": self.variables,
            "upstream": self.upstream,
            "metadata": self.metadata,
            "should_stop": self.should_stop,
            "error": self.error,
            "metrics": self.metrics,
            "executed_nodes": self.executed_nodes,
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessContext":
        """从字典反序列化"""
        return cls(
            trace_id=data.get("trace_id", uuid.uuid4().hex),
            pipeline_id=data.get("pipeline_id", ""),
            event=data.get("event", {}),
            alert=data.get("alert"),
            variables=data.get("variables", {}),
            upstream=data.get("upstream", {}),
            metadata=data.get("metadata", {}),
            should_stop=data.get("should_stop", False),
            error=data.get("error"),
            metrics=data.get("metrics", {}),
            executed_nodes=data.get("executed_nodes", []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ProcessContext":
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))
