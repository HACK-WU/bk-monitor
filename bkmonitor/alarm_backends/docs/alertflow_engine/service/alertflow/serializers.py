"""DRF 序列化器"""

from rest_framework import serializers


class ProcessorConfigSerializer(serializers.Serializer):
    """处理器配置序列化器"""

    id = serializers.CharField(max_length=128)
    type = serializers.CharField(max_length=64)
    version = serializers.CharField(max_length=64, required=False, default="")
    config = serializers.DictField(required=False, default=dict)
    condition = serializers.DictField(required=False, allow_null=True)
    enabled = serializers.BooleanField(default=True)
    error_strategy = serializers.ChoiceField(
        choices=["ignore", "retry", "stop", "fallback"],
        default="stop",
    )
    timeout = serializers.IntegerField(required=False, min_value=1, allow_null=True)
    retry = serializers.DictField(required=False, allow_null=True)


class StageConfigSerializer(serializers.Serializer):
    """阶段配置序列化器"""

    name = serializers.CharField(max_length=256)
    type = serializers.ChoiceField(
        choices=["sequential", "parallel", "conditional"],
        default="sequential",
    )
    processors = ProcessorConfigSerializer(many=True)
    enabled = serializers.BooleanField(default=True)
    timeout = serializers.IntegerField(required=False, min_value=1, allow_null=True)


class PipelineConfigSerializer(serializers.Serializer):
    """Pipeline 配置序列化器"""

    id = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=256)
    version = serializers.CharField(max_length=64)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    scenario = serializers.ChoiceField(
        choices=["alert", "event", "custom"],
        default="alert",
    )
    enabled = serializers.BooleanField(default=True)
    stages = StageConfigSerializer(many=True)
    global_config = serializers.DictField(required=False, default=dict)
    error_handling = serializers.DictField(required=False, default=dict)


class PipelineListSerializer(serializers.Serializer):
    """Pipeline 列表序列化器"""

    pipeline_id = serializers.CharField()
    name = serializers.CharField()
    version = serializers.CharField()
    scenario = serializers.CharField()
    enabled = serializers.BooleanField()
    updated_at = serializers.CharField()


class PipelineVersionSerializer(serializers.Serializer):
    """版本历史序列化器"""

    version = serializers.CharField()
    change_reason = serializers.CharField()
    created_at = serializers.CharField()
    created_by = serializers.CharField()


class RollbackSerializer(serializers.Serializer):
    """回滚请求序列化器"""

    version = serializers.CharField()


class TestPipelineSerializer(serializers.Serializer):
    """测试请求序列化器"""

    event = serializers.DictField()
    variables = serializers.DictField(required=False, default=dict)
