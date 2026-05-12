"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import time

from alarm_backends.constants import CONST_MINUTES
from alarm_backends.core.storage.redis import Cache
from bkmonitor.utils.common_utils import uniqid4


class BaseLock:
    def __init__(self, name, ttl=None):
        """
        分布式锁基类，定义锁的基本接口和上下文管理器协议。

        参数:
            name: 锁的唯一标识名称，用于在存储后端区分不同的锁
            ttl:  锁的过期时间（秒），防止持锁方异常退出后锁永久占用；默认 CONST_MINUTES（60秒）

        该类提供：
        1. 统一的初始化接口（name / ttl）
        2. acquire / release 抽象方法，由子类实现具体加锁/释放逻辑
        3. __enter__ / __exit__ 支持 with 语句，确保锁在代码块结束后自动释放
        """
        self.name = name
        # 默认60秒过期，防止死锁
        self.ttl = ttl or CONST_MINUTES

    def acquire(self, _wait=None):
        """尝试获取锁，子类必须实现该方法。"""
        raise NotImplementedError

    def release(self):
        """释放锁，子类必须实现该方法。"""
        raise NotImplementedError

    def __exit__(self, t, v, tb):
        """退出 with 代码块时自动释放锁，无论是否发生异常。"""
        self.release()

    def __enter__(self):
        """进入 with 代码块时自动获取锁，返回锁实例本身。"""
        self.acquire()
        return self


class RedisLock(BaseLock):
    """
    基于 Redis SET NX 指令实现的单键分布式互斥锁。

    特性：
    - 使用唯一 token（UUID）标识锁的持有者，防止误释放他人持有的锁
    - 支持短暂等待重试（_wait 参数），适用于轻度竞争场景
    - 锁过期时间由 ttl 控制，避免持锁方崩溃导致死锁
    """

    # 类级别私有属性，存储当前实例持有的锁令牌；初始为 None 表示未持锁
    __token = None

    def __init__(self, name, ttl=None):
        """
        初始化 Redis 单键锁。

        参数:
            name: 锁的 Redis key 名称
            ttl:  锁的过期时间（秒），默认 60 秒
        """
        super().__init__(name, ttl)
        # 使用专用的 "service-lock" Redis 缓存实例，与业务数据隔离
        self.client = Cache("service-lock")

    def acquire(self, _wait=0.001):
        """
        尝试获取 Redis 分布式锁。

        参数:
            _wait: 最长等待时间（秒），默认 0.001 秒；超时后返回 False

        返回值:
            True  — 成功获取锁
            False — 在等待时间内未能获取锁

        执行步骤：
        1. 生成唯一 token，用于标识当前锁持有者
        2. 计算等待截止时间
        3. 循环调用 SET NX 尝试加锁：
           - 成功则保存 token 并返回 True
           - 失败且未超时则短暂 sleep 后重试
           - 超时则返回 False
        """
        token = uniqid4()
        wait_until = time.time() + _wait
        while not self.client.set(self.name, token, ex=self.ttl, nx=True):
            if time.time() < wait_until:
                time.sleep(0.01)
            else:
                return False

        # 记录本实例持有的 token，用于 release 时校验所有权
        self.__token = token
        return True

    def release(self):
        """
        释放 Redis 分布式锁。

        返回值:
            True/非零  — 成功删除锁 key
            False      — 未持锁或 token 不匹配（锁已被他人持有或已过期），不执行删除

        执行步骤：
        1. 检查本实例是否持有 token，未持锁直接返回 False
        2. 从 Redis 读取当前锁的 token 值
        3. 比对 token，仅当一致时才删除 key，防止误释放他人的锁
        """
        if not self.__token:
            return False
        token = self.client.get(self.name)
        if not token or token != self.__token:
            return False
        return self.client.delete(self.name)


class MultiRedisLock:
    """
    基于 Redis Pipeline 的批量分布式锁。

    适用场景：需要同时对多个资源加锁，通过 Pipeline 批量执行 SET NX 减少网络往返，
    提升大批量加锁的性能。

    特性：
    - 所有 key 共享同一个 token，简化 token 管理
    - 加锁为"尽力而为"模式：部分 key 加锁失败不影响其他 key
    - 释放时通过 MGET 批量校验 token，只删除本实例持有的 key
    """

    def __init__(self, keys: list[str], ttl: int = None):
        """
        初始化批量 Redis 锁。

        参数:
            keys: 需要加锁的 Redis key 列表
            ttl:  每个锁的过期时间（秒），默认 60 秒
        """
        self.keys = keys
        self.ttl = ttl or CONST_MINUTES
        # 使用专用的 "service-lock" Redis 缓存实例
        self.client = Cache("service-lock")
        # 所有 key 共享同一个唯一 token，标识本次批量锁的持有者
        self._token = uniqid4()
        # 记录实际加锁成功的 key 集合，用于后续释放
        self._lock_success_keys = set()

    def acquire(self):
        """
        批量尝试获取锁（非阻塞）。

        返回值:
            成功获取锁的 key 集合（set），调用方可据此判断哪些资源被锁定

        执行步骤：
        1. 对 keys 去重，避免重复加锁
        2. 通过 Pipeline 批量执行 SET NX，减少网络往返
        3. 收集加锁成功的 key，存入 _lock_success_keys
        """
        if not self.keys:
            return []

        # 去重，避免对同一 key 重复加锁
        keys = list(set(self.keys))

        # 使用非事务 Pipeline 批量发送 SET NX 命令，提升性能
        pipeline = self.client.pipeline(transaction=False)
        for key in keys:
            pipeline.set(key, self._token, ex=self.ttl, nx=True)

        results = pipeline.execute()

        # 收集加锁成功的 key
        for index, locked in enumerate(results):
            if locked:
                self._lock_success_keys.add(keys[index])

        return self._lock_success_keys

    def release(self):
        """
        批量释放本实例持有的锁。

        返回值:
            实际被删除的 key 列表；若无成功加锁的 key 则返回 None

        执行步骤：
        1. 若无成功加锁的 key，直接返回
        2. 通过 MGET 批量读取各 key 的当前 token 值
        3. 比对 token，仅删除 token 与本实例一致的 key，防止误释放他人的锁
        """
        if not self._lock_success_keys:
            return

        lock_success_keys = list(self._lock_success_keys)

        # 批量获取各 key 的 token，用于所有权校验
        results = self.client.mget(lock_success_keys)

        keys_to_delete = []

        for index, token in enumerate(results):
            if token == self._token:
                # 只有当 token 与当前实例一致的 key 才允许删除
                keys_to_delete.append(lock_success_keys[index])

        if keys_to_delete:
            self.client.delete(*keys_to_delete)
        return keys_to_delete

    def is_locked(self, key: str):
        """
        查询指定 key 是否已被本实例成功加锁。

        参数:
            key: 待查询的 Redis key

        返回值:
            True  — 该 key 已被本实例持有
            False — 该 key 未被本实例持有（加锁失败或未参与本次加锁）
        """
        return key in self._lock_success_keys
