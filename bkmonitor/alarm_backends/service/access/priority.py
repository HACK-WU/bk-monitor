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

from alarm_backends.core.cache import key
from alarm_backends.core.control.item import Item
from alarm_backends.service.access.data.records import DataRecord
from alarm_backends.service.access.event.records.base import EventRecord


class PriorityChecker:
    """
    优先级检查，判断当前是否被抑制
    1. 根据优先级分组，获取优先级信息
    2. 比对时间戳，看是否过期，过期则覆盖，过期时间是一个固定的时间
    3. 比对维度优先级，如果优先级低则标记为抑制，否则更新优先级信息
    5. 设置一个删除时间，如果超过删除时间，删除优先级信息

    优先级信息是一个hashmap，key为维度分组，hash key为维度，hash value为优先级/时间戳的组合字段。

    数值越大，优先级越高，完全相同的一条数据检测到异常时以优先级高的策略为主？
    Q：不同的策略检测阈值可能不同，这里的实现是优先级低的数据点不推到检测队列，如果优先级高的策略同时检测阈值很高
    Q：会不会导致低优先级且符合告警条件的策略被忽略？
    A：会，目前告警优先级的设计是保留高优先级的点并推送到检测队列，丢弃低优先级的数据
    """

    def __init__(self, priority_group_key: str):
        self.priority_group_key = priority_group_key
        self.priority_cache = {}

        # 需要更新的优先级信息
        self.need_update = {}

        # 需要删除的优先级信息
        self.need_delete = []

        # redis client
        self.client = key.ACCESS_PRIORITY_KEY.client
        self.cache_key = key.ACCESS_PRIORITY_KEY.get_key(priority_group_key=self.priority_group_key)
        self.cache_ttl = key.ACCESS_PRIORITY_KEY.ttl

    def get_priority(self):
        """
        获取优先级信息
        """
        cache_key = key.ACCESS_PRIORITY_KEY.get_key(priority_group_key=self.priority_group_key)
        self.priority_cache = self.client.hgetall(cache_key)

    def get_priority_by_dimensions(self, dimensions_md5: str) -> str | None:
        """
        获取维度优先级信息
        """
        cache_key = key.ACCESS_PRIORITY_KEY.get_key(priority_group_key=self.priority_group_key)
        return self.client.hget(cache_key, dimensions_md5)

    def is_inhibited(self, record: DataRecord | EventRecord, item: Item) -> bool:
        """
        判断数据点是否被抑制，同时记录需要更新的优先级信息

        参数:
            record: 数据记录，DataRecord(时序数据)或EventRecord(事件数据)
            item: 监控项，包含策略配置信息(strategy.priority, strategy.get_interval())

        返回值:
            True: 数据点被抑制（存在更高优先级的策略正在告警）
            False: 数据点不被抑制（可以正常产生告警）

        执行步骤:
            1. 提取维度MD5作为唯一标识
            2. 查询该维度的优先级缓存
            3. 判断是否需要抑制或更新优先级信息

        抑制判断逻辑:
        ┌─────────────────────────────────────────────────────────────────────────┐
        │                          优先级抑制判断流程                              │
        ├─────────────────────────────────────────────────────────────────────────┤
        │                                                                         │
        │  获取dimensions_md5 (维度唯一标识)                                       │
        │       ↓                                                                 │
        │  查询 priority_cache[dimensions_md5]                                    │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ 缓存不存在?                                                     │    │
        │  │   → YES: 首次出现，更新缓存，返回False (不抑制)                  │    │
        │  │   → NO: 继续判断                                                │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │       ↓                                                                 │
        │  解析缓存: "优先级:时间戳"                                               │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ 缓存过期 (timestamp + interval*5 < now)?                        │    │
        │  │   → YES: 更新缓存，返回False (不抑制)                            │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ 当前策略优先级 >= 缓存优先级?                                    │    │
        │  │   → YES: 优先级更高或相等，更新缓存，返回False (不抑制)          │    │
        │  │   → NO: 存在更高优先级策略，返回True (被抑制)                    │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │                                                                         │
        │  注: priority数值越大，优先级越高                                        │
        │                                                                         │
        └─────────────────────────────────────────────────────────────────────────┘
        """
        now_timestamp = time.time()

        # Step1: 提取维度MD5作为唯一标识
        # DataRecord: 从record_id中提取 (格式: "md5.xxx")
        # EventRecord: 直接使用md5_dimension属性
        if isinstance(record, DataRecord):
            dimensions_md5 = record.record_id.split(".")[0]
        else:
            dimensions_md5 = record.md5_dimension
        strategy_priority = item.strategy.priority

        # Step2: 查询该维度的优先级缓存
        priority = self.priority_cache.get(dimensions_md5)

        # Step3-A: 缓存不存在，说明该维度首次出现，当前策略获得告警权
        if not priority:
            # 优先级为0时不存储，因为0是最小值，没有存储意义，减少内存占用
            if strategy_priority:
                self.need_update[dimensions_md5] = f"{strategy_priority}:{now_timestamp}"
                self.priority_cache[dimensions_md5] = f"{strategy_priority}:{now_timestamp}"
            return False  # 不抑制

        # 解析缓存格式: "优先级:时间戳"
        priority, timestamp = priority.split(":")

        # 获取策略的数据检测周期，用于计算过期时间
        interval = item.strategy.get_interval()

        # Step3-B: 判断是否应该更新优先级（两种情况不被抑制）
        # 条件1: 缓存过期 (超过5个检测周期未更新)
        # 条件2: 当前策略优先级 >= 缓存的优先级 (priority数值越大优先级越高)
        if float(timestamp) + interval * 5 < now_timestamp or int(priority) <= strategy_priority:
            # 优先级为0时不存储，因为0是最小值，没有存储意义，减少内存占用
            if strategy_priority:
                self.need_update[dimensions_md5] = f"{strategy_priority}:{now_timestamp}"
                self.priority_cache[dimensions_md5] = f"{strategy_priority}:{now_timestamp}"
            return False  # 不抑制

        # Step3-C: 存在更高优先级的策略正在告警，当前策略被抑制
        return True

    @staticmethod
    def check_records(records: list[DataRecord | EventRecord]):
        """
        检查数据点是否被抑制（基于策略优先级的告警抑制）

        参数:
            records: 数据记录列表，可以是DataRecord（时序数据）或EventRecord（事件数据）
                    每个record包含多个item（监控项），每个item关联一个策略

        返回值:
            None，结果通过修改 record.inhibitions[item.id] 记录是否被抑制

        执行步骤:
            1. 遍历所有records，筛选出配置了优先级的有效item
            2. 按策略优先级从高到低排序（priority数值越大优先级越高）
            3. 对每个item，通过PriorityChecker判断是否被更高优先级策略抑制
            4. 将抑制结果写入 record.inhibitions 字典
            5. 批量同步本次处理的优先级信息到Redis缓存

        数据流向图:
        ┌─────────────────────────────────────────────────────────────────────────┐
        │                     策略优先级抑制检查流程                                │
        ├─────────────────────────────────────────────────────────────────────────┤
        │                                                                         │
        │  records (数据记录列表)                                                  │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ Step1: 过滤有效item                                             │    │
        │  │   - is_retains[item.id] = True (数据点保留该item)               │    │
        │  │   - strategy.priority is not None (配置了优先级)                │    │
        │  │   - strategy.priority_group_key 存在 (有分组key)                │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ Step2: 按优先级排序 (priority数值大→小，即优先级高→低)           │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ Step3: 逐个item检查抑制                                         │    │
        │  │   - 按priority_group_key获取/创建PriorityChecker                │    │
        │  │   - 从Redis读取该分组的优先级缓存                                │    │
        │  │   - is_inhibited() 判断是否被更高优先级策略抑制                  │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │       ↓                                                                 │
        │  record.inhibitions[item.id] = True/False (记录抑制结果)                │
        │       ↓                                                                 │
        │  ┌─────────────────────────────────────────────────────────────────┐    │
        │  │ Step4: sync_priority() 批量同步到Redis                          │    │
        │  │   - 更新 access.data.priority.{priority_group_key} 缓存         │    │
        │  └─────────────────────────────────────────────────────────────────┘    │
        │                                                                         │
        └─────────────────────────────────────────────────────────────────────────┘
        """
        if not records:
            return

        # 按priority_group_key缓存PriorityChecker实例，避免重复创建和查询Redis
        priority_checkers: dict[str, PriorityChecker] = {}

        for record in records:
            items = record.items

            # Step1: 过滤有效item - 只处理保留的、配置了优先级的item
            items = [
                item
                for item in items
                if record.is_retains[item.id]  # 数据点需要保留该item
                and item.strategy.priority is not None  # 策略配置了优先级
                and item.strategy.priority_group_key  # 策略有优先级分组key
            ]

            # Step2: 按优先级由高到低排序（priority数值越大优先级越高）
            # 排序目的：高优先级策略先处理，可以抢占维度的告警权
            items.sort(key=lambda x: x.strategy.priority, reverse=True)

            # Step3: 逐个item检查是否被抑制
            for item in items:
                priority_group_key = item.strategy.priority_group_key

                # 获取或创建该分组的PriorityChecker
                priority_checker = priority_checkers.get(priority_group_key)
                if not priority_checker:
                    priority_checker = PriorityChecker(priority_group_key)
                    priority_checkers[priority_group_key] = priority_checker
                    # 从Redis加载该分组的优先级缓存数据
                    priority_checker.get_priority()

                # 判断并记录是否被抑制（被更高优先级策略抢占）
                record.inhibitions[item.id] = priority_checker.is_inhibited(record, item)

        # Step4: 批量同步优先级信息到Redis（更新本轮处理的优先级数据）
        for priority_checker in priority_checkers.values():
            priority_checker.sync_priority(records[0].items[0])

    def sync_priority(self, item: Item):
        """
        批量同步优先级信息到Redis

        参数:
            item: 监控项，用于获取策略的检测周期(interval)

        执行步骤:
            1. 扫描内存缓存，标记过期数据(超过10个检测周期)
            2. 刷新Redis Key的TTL
            3. 批量写入新增/更新的优先级信息
            4. 批量删除过期的优先级信息

        数据流向图:
        ┌─────────────────────────────────────────────────────────────────┐
        │                      sync_priority 数据流                        │
        ├─────────────────────────────────────────────────────────────────┤
        │                                                                 │
        │  priority_cache (内存)                                          │
        │       ↓                                                         │
        │  扫描过期数据 (timestamp + interval*10 < now)                    │
        │       ↓                                                         │
        │  ┌──────────────────────────────────────────────────────────┐   │
        │  │               Redis 操作                                  │   │
        │  │                                                          │   │
        │  │  1. EXPIRE cache_key cache_ttl    # 刷新Key过期时间       │   │
        │  │  2. HMSET cache_key need_update   # 批量更新优先级        │   │
        │  │  3. HDEL cache_key need_delete    # 批量删除过期数据      │   │
        │  └──────────────────────────────────────────────────────────┘   │
        │                                                                 │
        │  Redis Key格式: access.data.priority.{priority_group_key}       │
        │  Hash Value格式: { dimensions_md5: "优先级:时间戳" }            │
        │                                                                 │
        └─────────────────────────────────────────────────────────────────┘
        """
        interval = item.strategy.get_interval()

        # Step1: 扫描内存缓存，标记超过10个检测周期的过期数据
        # 过期阈值: interval * 10 (比is_inhibited的5倍周期更宽松，避免频繁删除)
        for dimensions_md5, priority in self.priority_cache.items():
            priority, timestamp = priority.split(":")
            if float(timestamp) + interval * 10 < time.time():
                self.need_delete.append(dimensions_md5)

        # Step2: 刷新Redis Key的TTL，防止整个Hash过期
        self.client.expire(self.cache_key, self.cache_ttl)

        # Step3: 批量写入新增/更新的优先级信息 (由is_inhibited方法收集)
        if self.need_update:
            self.client.hmset(self.cache_key, self.need_update)

        # Step4: 批量删除过期的优先级信息，释放Redis内存
        if self.need_delete:
            self.client.hdel(self.cache_key, *self.need_delete)
