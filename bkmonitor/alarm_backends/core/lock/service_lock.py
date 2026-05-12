"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import functools
import time
from contextlib import contextmanager

from alarm_backends.core.cache.key import RedisDataKey
from alarm_backends.core.cluster import get_cluster
from alarm_backends.core.lock import MultiRedisLock, RedisLock
from alarm_backends.core.storage.redis import Cache
from core.errors.alarm_backends import LockError


@contextmanager
def service_lock(key_instance, **kwargs):
    """
    单键分布式服务锁的上下文管理器

    参数:
        key_instance: RedisDataKey 实例，提供锁的 key 生成规则和过期时间
        **kwargs: 传递给 key_instance.get_key() 的参数，用于动态生成锁的 key

    返回值:
        yield RedisLock 实例，在 with 代码块内可操作锁对象

    异常:
        LockError: 加锁失败（锁已被他人持有时）抛出

    该方法实现单键服务锁的完整生命周期管理：
    1. 根据 key_instance 和 kwargs 生成锁的 Redis key
    2. 创建 RedisLock 并尝试在 0.1 秒内获取锁
    3. 加锁成功则 yield 锁对象，供业务代码使用
    4. 加锁失败则抛出 LockError，阻止并发执行
    5. 无论是否异常，finally 中确保锁被释放
    """
    lock = None
    lock_key = key_instance.get_key(**kwargs)
    try:
        lock = RedisLock(lock_key, key_instance.ttl)
        if lock.acquire(0.1):
            yield lock
        else:
            raise LockError(msg=f"{lock_key} is already locked")
    except LockError as err:
        raise err

    finally:
        if lock is not None:
            lock.release()


@contextmanager
def multi_service_lock(key_instance, keys):
    """
    批量分布式服务锁的上下文管理器

    参数:
        key_instance: RedisDataKey 实例，提供锁的过期时间（ttl）
        keys: 需要加锁的 Redis key 列表

    返回值:
        yield MultiRedisLock 实例，可通过 is_locked(key) 查询单个 key 的加锁状态

    该方法实现批量服务锁的完整生命周期管理：
    1. 创建 MultiRedisLock，通过 Pipeline 批量加锁
    2. yield 锁对象供业务代码使用
    3. finally 中确保释放所有成功加锁的 key

    注意：批量锁采用"尽力而为"模式，不保证所有 key 都加锁成功，
    业务方应通过 lock.is_locked(key) 检查具体 key 的加锁状态
    """
    lock = None
    try:
        lock = MultiRedisLock(keys, key_instance.ttl)
        lock.acquire()
        yield lock
    finally:
        if lock is not None:
            lock.release()


def share_lock(ttl=600, identify=None):
    """
    Celery 任务去重装饰器，防止同一任务被并发重复执行

    参数:
        ttl: 锁的过期时间（秒），默认 600 秒；超时后锁自动释放
        identify: 锁的唯一标识，默认使用函数名；
                  当不同模块存在同名函数时，应指定 identify 以避免锁冲突，
                  推荐格式为 `${module}_${method_used_for}`

    该装饰器实现 Celery 任务的互斥执行逻辑：
    1. 生成基于时间戳的唯一 token，标识当前执行实例
    2. 构建集群维度的锁 key（格式：{集群名}_celery_lock_{标识}）
    3. 通过 SET NX 原子操作尝试加锁：成功则执行函数，失败则静默跳过（返回 None）
    4. 函数执行完毕后，校验 token 一致才删除锁，防止误删其他实例的锁
    """

    def wrapper(func):
        @functools.wraps(func)
        def _inner(*args, **kwargs):
            token = str(time.time())
            # 防止函数重名导致方法失效，增加一个ID参数，可以通过ID参数屏蔽多模块函数名重复的问题
            # 例如，可以为`${module}_${method_used_for}`
            name = func.__name__ if identify is None else identify
            cache_key = f"{get_cluster().name}_celery_lock_{name}"
            client = Cache("service-lock")
            lock_success = client.set(cache_key, token, ex=ttl, nx=True)
            if not lock_success:
                return

            try:
                return func(*args, **kwargs)
            finally:
                if client.get(cache_key) == token:
                    client.delete(cache_key)

        return _inner

    return wrapper


@contextmanager
def refresh_service_lock(key_instance: RedisDataKey, token: str, **kwargs):
    """刷新当前key实例的锁，用于长时间任务执行期间续期锁

    :param key_instance: 锁实例
    :param token: 标记，一般用时间戳，用于标识当前持锁者
    :param **kwargs: 传递给 key_instance.get_key() 的参数

    该方法实现锁续期的完整流程：
    1. 直接 SET（非 NX）刷新锁的值和过期时间，达到续期目的
    2. yield 让业务代码执行
    3. 退出时检查锁是否被其他任务刷新：
       - 未被刷新（token 仍一致）→ 删除锁，当前任务不再持有
       - 已被刷新（token 不一致）→ 不删除，新任务正在使用该锁
    """
    lock_key = key_instance.get_key(**kwargs)
    client = Cache("service-lock")
    client.set(lock_key, token, ex=key_instance.ttl)

    yield

    # 如果当前锁还没有被刷新，则删除，否则说明有其他任务刷新了锁并正常执行逻辑中
    if not check_lock_updated(key_instance, token, **kwargs):
        client.delete(lock_key)


def check_lock_updated(key_instance: RedisDataKey, token: str = None, **kwargs) -> bool:
    """检查锁是否被更新，用于一些重载后需要停止旧任务实例的场景（秒级别，秒内的任务重载忽略）

    :param key_instance: 锁实例
    :param token: 标记，一般用时间戳
    :param **kwargs: 传递给 key_instance.get_key() 的参数
    :return: True 表示锁已被其他任务更新；False 表示锁未被更新，仍由当前实例持有

    判断逻辑：
    1. 从 Redis 读取锁当前的 token 值
    2. 与传入的 token 比对：一致说明未被更新，不一致说明已被其他任务覆盖
    """
    lock_key = key_instance.get_key(**kwargs)
    client = Cache("service-lock")
    last_token = client.get(lock_key)
    if last_token == str(token):
        return False

    return True
