"""REST API 视图"""

import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from service.alertflow.manager import PipelineService
from service.alertflow.serializers import (
    PipelineConfigSerializer,
    RollbackSerializer,
    TestPipelineSerializer,
)

logger = logging.getLogger(__name__)

# 全局单例
_pipeline_service = PipelineService()


class PipelineViewSet(ViewSet):
    """Pipeline CRUD 视图集"""

    def create(self, request):
        """POST /api/v1/pipelines/ - 创建 Pipeline"""
        serializer = PipelineConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = _pipeline_service.create_pipeline(
                config=serializer.validated_data,
                created_by=request.user.username if hasattr(request, "user") else "",
            )
            return Response(result, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request):
        """GET /api/v1/pipelines/ - 列出 Pipeline"""
        scenario = request.query_params.get("scenario")
        enabled = request.query_params.get("enabled")
        if enabled is not None:
            enabled = enabled.lower() == "true"

        result = _pipeline_service.list_pipelines(scenario=scenario, enabled=enabled)
        return Response(result)

    def retrieve(self, request, pk=None):
        """GET /api/v1/pipelines/{id}/ - 获取详情"""
        try:
            result = _pipeline_service.get_pipeline(pk)
            return Response(result)
        except KeyError:
            return Response({"error": f"Pipeline '{pk}' 不存在"}, status=status.HTTP_404_NOT_FOUND)

    def update(self, request, pk=None):
        """PUT /api/v1/pipelines/{id}/ - 更新"""
        serializer = PipelineConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = _pipeline_service.update_pipeline(
                pipeline_id=pk,
                config=serializer.validated_data,
                change_reason=request.data.get("change_reason", ""),
                updated_by=request.user.username if hasattr(request, "user") else "",
            )
            return Response(result)
        except (KeyError, ValueError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        """DELETE /api/v1/pipelines/{id}/ - 删除"""
        try:
            _pipeline_service.delete_pipeline(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except KeyError:
            return Response({"error": f"Pipeline '{pk}' 不存在"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        """POST /api/v1/pipelines/{id}/validate/ - 验证配置"""
        result = _pipeline_service.validate_pipeline(request.data)
        return Response(result)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """POST /api/v1/pipelines/{id}/test/ - Dry Run 测试"""
        serializer = TestPipelineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = _pipeline_service.test_pipeline(
                pipeline_id=pk,
                event=serializer.validated_data["event"],
                variables=serializer.validated_data.get("variables"),
            )
            return Response(result)
        except (KeyError, RuntimeError) as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def versions(self, request, pk=None):
        """GET /api/v1/pipelines/{id}/versions/ - 版本历史"""
        try:
            result = _pipeline_service.get_versions(pk)
            return Response(result)
        except KeyError:
            return Response({"error": f"Pipeline '{pk}' 不存在"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        """POST /api/v1/pipelines/{id}/rollback/ - 回滚"""
        serializer = RollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = _pipeline_service.rollback(
                pipeline_id=pk,
                version=serializer.validated_data["version"],
                rolled_by=request.user.username if hasattr(request, "user") else "",
            )
            return Response(result)
        except KeyError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class NodeViewSet(ViewSet):
    """节点类型视图集"""

    def list(self, request):
        """GET /api/v1/nodes/ - 获取所有可用节点类型"""
        result = _pipeline_service.get_node_types()
        return Response(result)

    @action(detail=True, methods=["get"], url_path="config")
    def config_schema(self, request, pk=None):
        """GET /api/v1/nodes/{type}/config/ - 获取节点配置 Schema"""
        try:
            result = _pipeline_service.get_node_schema(pk)
            return Response(result)
        except KeyError:
            return Response({"error": f"节点类型 '{pk}' 不存在"}, status=status.HTTP_404_NOT_FOUND)


class TraceViewSet(ViewSet):
    """链路追踪视图集"""

    def retrieve(self, request, pk=None):
        """GET /api/v1/traces/{trace_id}/ - 查询执行链路"""
        result = _pipeline_service.query_trace(pk)
        return Response(result)
