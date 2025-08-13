from django.utils.deprecation import MiddlewareMixin

from drf_resource.utils.local import local


class RequestProvider(MiddlewareMixin):
    """
    @summary: request事件接收者
    """

    def process_request(self, request):
        local.current_request = request
        return None

    def process_response(self, request, response):
        local.clear()
        return response
