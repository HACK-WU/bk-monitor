"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import json
import time

from consul import NotFound
from django.utils.functional import cached_property

from alarm_backends.management.base.protocol import AbstractServiceDiscoveryMixin
from bkmonitor.utils import consul


class ConsulServiceDiscoveryMixin(AbstractServiceDiscoveryMixin):
    """
    基于 Consul 的服务发现混入类

    提供服务注册、注销、查询等功能，使用 Consul 的 KV 存储和 Session 机制
    实现分布式服务的自动发现和健康检查
    """

    # 当前 Consul Session ID，用于维持服务注册状态
    __SESSION_ID__ = None

    # Consul KV 存储路径前缀，子类需要指定
    _PATH_PREFIX_ = None
    # Session 过期时间（秒），默认 120 秒
    _SESSION_TTL_ = 120

    def __init__(self, *args, **kwargs):
        """
        初始化服务发现混入类

        设置上次续约时间为 0，确保首次调用时立即进行注册
        """
        super().__init__(*args, **kwargs)
        self.last_renew_session_time = 0

    @cached_property
    def _client(self):
        """获取 Consul 客户端实例（缓存属性）"""
        return consul.BKConsul()

    @cached_property
    def _registration_path(self):
        """
        获取当前服务实例的注册路径（缓存属性）

        路径格式: {PATH_PREFIX}/{host_addr}/{pid}
        例如: /bkmonitor/alert/192.168.1.100/12345
        """
        return "/".join(map(str, [self._PATH_PREFIX_, self.host_addr, self.pid]))

    @property
    def _registry(self):
        """
        获取服务注册表

        返回值:
            dict: {host_addr: [pid1, pid2, ...]} 格式的注册表

        从 Consul KV 中读取所有已注册的服务实例，解析路径并按主机地址分组
        """
        _, node_list = self._client.kv.get(self._PATH_PREFIX_, keys=True)
        node_list = node_list or {}

        registry = {}
        for node in node_list:
            # 从路径中提取主机地址和进程 ID
            host_addr, pid = node[len(self._PATH_PREFIX_) + 1 :].split("/")
            registry.setdefault(host_addr, []).append(pid)

        return registry

    def _renew_or_create_session_id(self):
        """
        续约或创建 Consul Session

        返回值:
            str: Session ID

        执行流程:
        1. 如果已有 Session ID，尝试续约
        2. 续约失败（Session 不存在）则清空 Session ID
        3. 如果没有 Session ID，创建新的 Session
        4. Session 配置: behavior=delete（Session 过期时自动删除关联的 KV），lock_delay=0，ttl=120s
        """
        session = consul.BKConsul.Session(self._client.agent.agent)

        if self.__SESSION_ID__:
            try:
                session.renew(self.__SESSION_ID__)
            except NotFound:
                self.__SESSION_ID__ = None

        if self.__SESSION_ID__ is None:
            self.__SESSION_ID__ = session.create(behavior="delete", lock_delay=0, ttl=self._SESSION_TTL_)

        return self.__SESSION_ID__

    def get_registration_info(self, registration_path=None):
        """
        获取指定路径的注册信息

        参数:
            registration_path: 注册路径，默认使用当前实例的注册路径

        返回值:
            dict: 注册信息的 JSON 对象，如果不存在则返回 None
        """
        if registration_path is None:
            registration_path = self._registration_path

        _, result = self._client.kv.get(registration_path)

        if result:
            return json.loads(result["Value"])

    def update_registration_info(self, value=None):
        """
        更新服务注册信息

        参数:
            value: 要注册的信息（可序列化为 JSON 的对象）

        执行流程:
        1. 检查距离上次续约是否超过 TTL 的一半（60 秒），未超过则跳过
        2. 将注册信息序列化为 JSON
        3. 续约或创建 Session
        4. 使用 Session 锁定机制将信息写入 Consul KV

        注意: 使用 TTL/2 作为续约间隔，确保在 Session 过期前完成续约
        """
        now = time.time()
        if now - self.last_renew_session_time < self._SESSION_TTL_ / 2:
            return
        self.last_renew_session_time = now

        try:
            info = json.dumps(value)
        except:  # noqa
            info = b""

        session_id = self._renew_or_create_session_id()
        assert session_id, f"session_id should not be {type(session_id)!r}"

        self._client.kv.put(self._registration_path, info, acquire=session_id)

    def register(self, registration_info=None):
        """
        注册服务实例

        参数:
            registration_info: 注册信息（可选）

        将当前服务实例注册到 Consul，并关联到 Session
        """
        self.update_registration_info(registration_info)

    def unregister(self):
        """
        注销服务实例

        销毁 Consul Session，由于 Session 配置了 behavior=delete，
        关联的 KV 记录会自动删除，实现服务的优雅下线
        """
        if self.__SESSION_ID__:
            self._client.session.destroy(self.__SESSION_ID__)

    def query_for_hosts(self):
        """
        查询所有已注册的主机地址

        返回值:
            list: 主机地址列表
        """
        return list(self._registry.keys())

    def query_for_instances(self, host_addr=None):
        """
        查询服务实例信息

        参数:
            host_addr: 主机地址，默认为当前主机

        返回值:
            tuple: (所有主机列表, 指定主机的实例路径列表)
            例如: (['192.168.1.100', '192.168.1.101'], ['192.168.1.100/12345', '192.168.1.100/12346'])
        """
        if host_addr is None:
            host_addr = self.host_addr

        registry = dict(self._registry)
        return (list(registry.keys()), [f"{host_addr}/{pid}" for pid in registry.get(host_addr, [])])
