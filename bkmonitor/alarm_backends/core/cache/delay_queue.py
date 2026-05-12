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

from alarm_backends.constants import CONST_MINUTES
from alarm_backends.core.cache.key import KEY_PREFIX
from alarm_backends.core.storage.redis import CACHE_BACKEND_CONF_MAP, Cache

logger = logging.getLogger("cache.delay_queue")


class DelayQueueManager:
    """
    延迟队列管理器

    基于 Redis 实现的延迟任务调度器，用于将需要延后执行的任务暂存起来，
    在到达预定执行时间后再投递到对应的目标队列中。

    数据结构说明：
    - TASK_DELAY_QUEUE: Redis ZSet（有序集合），member 为 task_id，score 为预定执行时间戳，
      用于按时间排序筛选到期任务。
    - TASK_STORAGE_QUEUE: Redis Hash，field 为 task_id，value 为任务的序列化数据（JSON），
      用于存放任务的详细执行信息（命令、目标队列、参数、调度时间等）。
    """

    # 任务详情存储队列（Redis Hash），存放每个 task_id 对应的任务体
    TASK_STORAGE_QUEUE = KEY_PREFIX + "task_storage"
    # 任务延迟调度队列（Redis ZSet），按到期时间戳排序的待触发任务集合
    TASK_DELAY_QUEUE = KEY_PREFIX + "task_delay_queue"

    @classmethod
    def refresh_single_db(cls, backend):
        """
        刷新单个 Redis 实例上的延迟队列，将到期任务重新投递到目标队列

        参数:
            backend: Redis 后端标识，对应 CACHE_BACKEND_CONF_MAP 中的某个 key，
                     用于实例化对应的 Redis 客户端

        返回值:
            None。无到期任务时直接返回；有任务时按其原始命令重投递到目标队列后返回

        执行步骤：
        1. 通过 zrangebyscore 取出 score 在 [0, now] 区间内（即已到期）的所有 task_id
        2. 利用 zrem 的原子性，使用 pipeline 批量删除这些 task_id；
           只有删除成功（flag 为真）的任务才视为本次"抢占"成功，避免多实例并发重复处理
        3. 通过 hmget 一次性从存储队列加载这些任务的详情，并反序列化为 Python 对象
        4. 通过 hdel 清理存储队列中已处理的任务详情
        5. 按任务记录中的命令（cmd）和目标队列（queue），将参数（values）重新投递回业务队列
        """
        redis_client = Cache(backend)

        # 1. 取出所有已到期（score <= 当前时间戳）的任务 ID
        now = int(time.time())
        task_ids = redis_client.zrangebyscore(cls.TASK_DELAY_QUEUE, 0, now)

        # 2. 利用 zrem 的原子性防并发：仅删除成功的 task_id 才属于当前进程处理
        pipe = redis_client.pipeline()
        for task_id in task_ids:
            pipe.zrem(cls.TASK_DELAY_QUEUE, task_id)
        result = pipe.execute()
        data_keys = [data_key for data_key, flag in zip(task_ids, result) if flag]
        if not data_keys:
            # 没有抢到任何到期任务，直接返回
            return

        # 3. 加载任务详情数据（JSON 反序列化）
        task_list = redis_client.hmget(cls.TASK_STORAGE_QUEUE, data_keys)
        task_list = [json.loads(task) for task in task_list]

        # 4. 删除存储队列中对应的任务详情，避免内存堆积
        redis_client.hdel(cls.TASK_STORAGE_QUEUE, *data_keys)

        # 5. 按原始命令将任务重新投递到目标队列
        pipe = redis_client.pipeline()
        for task in task_list:
            # 任务结构：(task_id, cmd, queue, values, scheduled)
            # cmd 为 Redis 命令名（如 lpush/rpush 等），queue 为目标队列名，values 为命令参数
            task_id, cmd, queue, values, scheduled = task
            getattr(pipe, cmd)(queue, *values)
        pipe.execute()

    @classmethod
    def refresh(cls):
        """
        延迟队列刷新主循环入口

        由定时任务调度，每分钟启动一次，单次运行持续约一分钟；
        在持续期内每秒轮询一次所有 Redis 后端，触发到期任务的重投递。

        执行步骤：
        1. 记录起始时间戳 now，作为本次运行的时间基准
        2. 在不超过 CONST_MINUTES（一分钟）的时间内循环执行：
           a. 遍历所有缓存后端配置 CACHE_BACKEND_CONF_MAP
           b. 通过 db 编号去重，避免对同一 Redis DB 重复处理
           c. 调用 refresh_single_db 处理该后端上的到期任务，异常仅记录日志不中断循环
        3. 每轮处理后 sleep(1) 秒，控制轮询频率
        """
        now = int(time.time())
        while int(time.time()) - now < CONST_MINUTES:
            # 同一 db 只处理一次，避免多个 backend 指向同一 Redis DB 时的重复扫描
            duplicate_db = set()
            for backend, redis_conf in list(CACHE_BACKEND_CONF_MAP.items()):
                db = redis_conf.get("db", 0)
                if db in duplicate_db:
                    continue
                duplicate_db.add(db)

                try:
                    cls.refresh_single_db(backend)
                except Exception as e:
                    # 单个后端处理异常不影响其他后端，记录异常堆栈便于排查
                    logger.exception(f"redo push(backend:{backend}), error({e})")
            time.sleep(1)


def main():
    # 模块入口，启动延迟队列刷新主循环
    DelayQueueManager.refresh()
