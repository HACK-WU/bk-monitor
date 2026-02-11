"""URL 路由配置"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from service.alertflow.views import NodeViewSet, PipelineViewSet, TraceViewSet

router = DefaultRouter()
router.register(r"pipelines", PipelineViewSet, basename="pipeline")
router.register(r"nodes", NodeViewSet, basename="node")
router.register(r"traces", TraceViewSet, basename="trace")

urlpatterns = [
    path("api/v1/", include(router.urls)),
]
