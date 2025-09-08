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
import logging
import time

from consul.base import ConsulException

from bkmonitor.utils import consul
from metadata import config
from metadata.utils import hash_util

CONSUL_INFLUXDB_VERSION_PATH = f"{config.CONSUL_PATH}/influxdb_info/version/"

logger = logging.getLogger("metadata")


def refresh_router_version():
    """
    更新consul指定路径下的版本
    :return: True | raise Exception
    """

    client = consul.BKConsul()
    client.kv.put(key=CONSUL_INFLUXDB_VERSION_PATH, value=str(time.time()))
    logger.info("refresh influxdb version in consul success.")


class HashConsul:
    """
    哈希consul工具
    工具在写入consul前，将会先匹配consul上的数据是否与当次写入数据一致
    如果一致，该更新将会被忽略（如果允许），否则才会将配置写入consul
    从而降低consul的刷新频率
    """

    def __init__(self, host="127.0.0.1", port=8500, scheme="http", verify=None, default_force=False):
        """
        初始化
        :param host: consul agent IP地址
        :param port: consul agent 端口
        :param scheme: consul agent协议
        :param verify: SSL 验证
        :param default_force: 默认是否需要强制更新
        """
        # consul agent connect info
        self.host = host
        self.port = port
        self.scheme = scheme
        self.verify = verify

        # 是否强行写
        self.default_force = default_force

    def delete(self, key, recurse=None):
        """
        删除指定kv
        """
        consul_client = consul.BKConsul(host=self.host, port=self.port, scheme=self.scheme, verify=self.verify)
        consul_client.kv.delete(key, recurse)
        logger.info("key->[%s] has been deleted", key)

    def get(self, key):
        """
        获取指定kv
        """
        consul_client = consul.BKConsul(host=self.host, port=self.port, scheme=self.scheme, verify=self.verify)
        return consul_client.kv.get(key)

    def list(self, key):
        consul_client = consul.BKConsul(host=self.host, port=self.port, scheme=self.scheme, verify=self.verify)
        return consul_client.kv.get(key, recurse=True)

    def put(self, key, value, is_force_update=False, bk_data_id: int | None = None, *args, **kwargs):
        """
        更新Consul键值对配置，支持条件更新和变更检测

        参数:
            key: Consul键路径，格式为字符串（如："config/service1"）
            value: 配置内容，支持字典或数组类型，会被序列化为JSON存储
            is_force_update: 强制更新标志，为True时跳过变更检测直接更新
            bk_data_id: 可选数据源ID，用于日志记录和异常追踪
            *args, **kwargs: 其他传递给Consul客户端的参数

        返回值:
            bool: 更新结果状态
                - True: 配置已更新或内容无变化
                - False: 更新失败（通常不会发生，异常会抛出）

        核心处理流程:
        1. 强制更新模式处理：当全局/局部强制标志为True时直接更新
        2. 获取当前配置：从Consul读取现有键值
        3. 变更检测：通过MD5哈希比对新旧配置内容
        4. 条件更新：仅当配置变更时执行更新操作
        5. 异常处理：捕获并记录Consul异常，保留原始错误信息
        """
        consul_client = consul.BKConsul(host=self.host, port=self.port, scheme=self.scheme, verify=self.verify)

        # 强制更新模式处理
        # 当全局强制标志或局部参数为True时，跳过变更检测直接更新
        if self.default_force or is_force_update:
            logger.debug(f"key->[{key}] now is force update, will update consul.")
            return consul_client.kv.put(key=key, value=json.dumps(value), *args, **kwargs)

        # 获取当前Consul配置
        # 如果键不存在（old_value为None），直接执行更新
        old_value = consul_client.kv.get(key)[1]
        if old_value is None:
            logger.info("old_value is missing, will refresh consul.")
            return consul_client.kv.put(key=key, value=json.dumps(value), *args, **kwargs)

        # 配置变更检测
        # 1. 计算新旧配置的MD5哈希值
        # 2. 如果哈希相同（内容未变），直接返回成功状态
        old_hash = hash_util.object_md5(json.loads(old_value["Value"]))
        new_hash = hash_util.object_md5(value)

        if old_hash == new_hash:
            logger.debug(f"new value hash->[{new_hash}] is same as the one on consul, nothing will updated.")
            return True

        # 执行配置更新
        # 1. 记录变更信息（包含数据源ID时附加记录）
        # 2. 尝试更新Consul配置
        # 3. 捕获并处理Consul异常
        if bk_data_id is not None:
            logger.info(
                "data_id->[%s] need update, new value hash->[%s] is different from the old hash->[%s]",
                bk_data_id,
                new_hash,
                old_hash,
            )
        else:
            logger.info(
                "new value hash->[%s] is different from the old hash->[%s], will updated it", new_hash, old_hash
            )
        try:
            return consul_client.kv.put(key=key, value=json.dumps(value), *args, **kwargs)
        except ConsulException as e:
            logger.error("put consul key error, data_id: %s, error: %s", bk_data_id, e)
            raise
