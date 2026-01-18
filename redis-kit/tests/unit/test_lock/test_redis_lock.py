# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import pytest
import time
from unittest.mock import MagicMock, Mock, patch
from redis_kit.lock.redis_lock import RedisLock, MultiRedisLock, ReadWriteLock
from redis_kit.exceptions import LockAcquisitionError, LockReleaseError


class TestRedisLock:
    """测试 RedisLock 类"""

    def test_acquire_and_release(self):
        """测试获取和释放锁"""
        client = MagicMock()
        client.set.return_value = True
        client.get.return_value = None
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        # 获取锁
        assert lock.acquire(blocking=False) is True
        assert lock.is_locked() is True
        
        # 模拟锁已持有
        client.get.return_value = lock._token
        
        # 释放锁
        client.delete.return_value = 1
        lock.release()
        assert lock.is_locked() is False

    def test_acquire_already_locked(self):
        """测试锁已被占用时的获取"""
        client = MagicMock()
        client.set.return_value = False  # SET NX 失败
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        # 非阻塞模式应该立即返回 False
        assert lock.acquire(blocking=False) is False

    def test_acquire_with_timeout(self):
        """测试带超时的获取"""
        client = MagicMock()
        # 第一次失败，第二次成功
        client.set.side_effect = [False, False, True]
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        start = time.time()
        result = lock.acquire(blocking=True, timeout=1.0)
        elapsed = time.time() - start
        
        assert result is True
        assert elapsed < 1.5  # 应该在超时前成功

    def test_acquire_timeout_exhausted(self):
        """测试超时耗尽"""
        client = MagicMock()
        client.set.return_value = False  # 始终失败
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        start = time.time()
        result = lock.acquire(blocking=True, timeout=0.5)
        elapsed = time.time() - start
        
        assert result is False
        assert 0.4 < elapsed < 0.7

    def test_context_manager(self):
        """测试上下文管理器"""
        client = MagicMock()
        client.set.return_value = True
        client.delete.return_value = 1
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        # 模拟获取锁后 get 返回 token
        def set_side_effect(*args, **kwargs):
            client.get.return_value = lock._token
            return True
        client.set.side_effect = set_side_effect
        
        with lock:
            assert lock.is_locked() is True
        
        assert lock.is_locked() is False

    def test_context_manager_acquire_fail(self):
        """测试上下文管理器获取锁失败"""
        client = MagicMock()
        client.set.return_value = False
        
        lock = RedisLock(client, "test_lock", ttl=10)
        
        with pytest.raises(LockAcquisitionError):
            with lock:
                pass

    def test_extend_lock(self):
        """测试延长锁时间"""
        client = MagicMock()
        client.set.return_value = True
        client.expire.return_value = True
        client.get.return_value = None
        
        lock = RedisLock(client, "test_lock", ttl=10)
        lock.acquire(blocking=False)
        
        # 模拟锁已持有
        client.get.return_value = lock._token
        
        result = lock.extend(20)
        assert result is True
        client.expire.assert_called()

    def test_release_without_acquire(self):
        """测试未获取锁就释放"""
        client = MagicMock()
        lock = RedisLock(client, "test_lock", ttl=10)
        
        # 应该不会抛出异常，只是不做任何操作
        lock.release()


class TestMultiRedisLock:
    """测试 MultiRedisLock 类"""

    def test_acquire_all_locks(self):
        """测试获取多个锁"""
        client = MagicMock()
        client.set.return_value = True
        client.delete.return_value = 1
        
        keys = ["lock1", "lock2", "lock3"]
        lock = MultiRedisLock(client, keys, ttl=10)
        
        # 模拟所有锁都成功获取
        client.get.return_value = lock._token
        
        assert lock.acquire(blocking=False) is True
        assert lock.is_locked() is True
        
        lock.release()
        assert lock.is_locked() is False

    def test_acquire_partial_failure(self):
        """测试部分锁获取失败"""
        client = MagicMock()
        # 第一个锁成功，第二个失败
        client.set.side_effect = [True, False]
        client.delete.return_value = 1
        
        keys = ["lock1", "lock2"]
        lock = MultiRedisLock(client, keys, ttl=10)
        
        # 应该回滚已获取的锁
        assert lock.acquire(blocking=False) is False

    def test_context_manager(self):
        """测试上下文管理器"""
        client = MagicMock()
        client.set.return_value = True
        client.delete.return_value = 1
        
        keys = ["lock1", "lock2", "lock3"]
        lock = MultiRedisLock(client, keys, ttl=10)
        
        # 模拟获取锁后 get 返回 token
        client.get.return_value = lock._token
        
        with lock:
            assert lock.is_locked() is True
        
        assert lock.is_locked() is False


class TestReadWriteLock:
    """测试 ReadWriteLock 类"""

    def test_multiple_readers(self):
        """测试多个读锁"""
        client = MagicMock()
        client.incr.return_value = 1
        client.decr.return_value = 0
        client.get.return_value = None  # 没有写锁
        
        lock = ReadWriteLock(client, "resource", ttl=10)
        
        # 第一个读者
        with lock.read():
            client.incr.assert_called()
            
            # 第二个读者
            client.incr.return_value = 2
            with lock.read():
                pass

    def test_read_blocked_by_write(self):
        """测试读锁被写锁阻塞"""
        client = MagicMock()
        client.get.return_value = "write_token"  # 有写锁
        
        lock = ReadWriteLock(client, "resource", ttl=10)
        
        # 读锁应该被阻塞
        with pytest.raises(LockAcquisitionError):
            with lock.read():
                pass

    def test_write_lock(self):
        """测试写锁"""
        client = MagicMock()
        client.set.return_value = True  # 获取写锁成功
        client.get.return_value = "0"  # 没有读者
        client.delete.return_value = 1
        
        lock = ReadWriteLock(client, "resource", ttl=10)
        
        # 模拟获取锁后的状态
        def set_side_effect(*args, **kwargs):
            client.get.return_value = lock._write_token
            return True
        client.set.side_effect = set_side_effect
        
        with lock.write():
            client.set.assert_called()

    def test_write_blocked_by_readers(self):
        """测试写锁被读锁阻塞"""
        client = MagicMock()
        client.get.side_effect = [None, "5"]  # 写锁可获取，但有5个读者
        
        lock = ReadWriteLock(client, "resource", ttl=10)
        
        # 写锁应该被阻塞
        with pytest.raises(LockAcquisitionError):
            with lock.write():
                pass

    def test_write_blocks_read(self):
        """测试写锁阻塞读锁"""
        client = MagicMock()
        # 先获取写锁
        client.set.return_value = True
        client.get.side_effect = ["0", "write_token"]
        client.delete.return_value = 1
        
        lock = ReadWriteLock(client, "resource", ttl=10)
        
        # 模拟写锁已持有
        def set_side_effect(*args, **kwargs):
            client.get.side_effect = ["write_token", "write_token"]
            return True
        client.set.side_effect = set_side_effect
        
        with lock.write():
            # 尝试获取读锁应该失败
            client.get.side_effect = ["write_token"]
            with pytest.raises(LockAcquisitionError):
                with lock.read():
                    pass
