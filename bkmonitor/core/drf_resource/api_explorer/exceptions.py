"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""


class APIExplorerException(Exception):
    """API Explorer 基础异常类"""

    def __init__(self, message, code=None):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ResourceNotFoundError(APIExplorerException):
    """指定的 API 资源不存在"""

    def __init__(self, message):
        super().__init__(message, code="404")


class InvocationError(APIExplorerException):
    """API 调用过程中发生错误"""

    def __init__(self, message):
        super().__init__(message, code="500")


class EnvironmentDeniedError(APIExplorerException):
    """非测试环境拒绝访问"""

    def __init__(self, message="API Explorer 仅在开发/测试环境可用"):
        super().__init__(message, code="403")
