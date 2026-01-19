"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import concurrent.futures
import logging
import os
import signal
import time
from concurrent.futures import Executor, Future
from threading import RLock

from django.db import close_old_connections

logger = logging.getLogger(__name__)


class BeatShutdown(Exception):
    always_raise = True


class MonitorBeater:
    """
    任务执行方式：
    dumy: 单进程堵塞式执行，注意该模式可能会让周期任务调度并不是那么精确，但是消耗最小同时最可靠。
    thread: 线程池执行(默认)，注意： 使用线程池可能会比dumy模式小消耗更多的cpu资源，在资源紧张情况下，可以考虑使用dumy模式。
    通过环境变量: MONITOR_BEAT_EXEC_TYPE可以设置执行方式
    """

    def __init__(self, name="monitor_beater", entries=None):
        if entries is None:
            entries = {}
        self.name = name
        self.entries = entries
        self.max_interval = 1
        self.executor = BeaterExecutor(self, exec_type=os.getenv("MONITOR_BEAT_EXEC_TYPE", "thread"))
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
        self.__shutdown = False

    def shutdown(self, signum, frame):
        self.__shutdown = True
        self.executor.shutdown(True)

    def maybe_due(self, entry):
        """
        是否需要发布任务
        :param entry: schedule
        :return: 下次运行时间
        """
        is_due, next_time_to_run = entry.is_due()
        new_entry = None
        if is_due:
            logger.info(f"{self.display_name} Sending due task {entry.task.__name__} args: {entry.args}")
            self.executor.execute(entry)
            new_entry = entry.next()
        return next_time_to_run, new_entry

    def tick(self):
        """
        执行一次调度周期，检查所有任务条目是否到期并执行

        返回值:
            float: 距离下一个任务执行的最小等待时间（秒）

        执行步骤:
            1. 遍历所有任务条目，调用 maybe_due 检查是否到期
            2. 收集所有任务的下次执行时间
            3. 批量更新需要刷新的任务条目（避免遍历时修改字典）
            4. 返回最小等待时间，用于控制下次 tick 的触发

        数据流:
            entries -> maybe_due() -> (next_time, new_entry)
                                          |
                          +---------------+---------------+
                          |                               |
                  remaining_times[]              entries_temp{}
                          |                               |
                          v                               v
                    min(times)                    更新 entries
        """
        # 收集所有任务的下次执行时间
        remaining_times = []
        # 临时存储需要更新的任务条目（避免遍历时修改字典）
        entries_temp = {}
        # 创建 key 列表快照，防止遍历时字典被修改
        entry_keys = list(self.entries.keys())

        for entry_key in entry_keys:
            try:
                # 检查任务是否到期，返回下次执行时间和可能更新的条目
                next_time_to_run, new_entry = self.maybe_due(self.entries[entry_key])
                # 由于并发原因，entries 中可能会出现 key 被修改的情况
                # logger.debug(
                #     f"{self.display_name} Ticks runtime key: {entry_key},"
                #     f"values: {self.entries[entry_key].args}, next_time: {next_time_to_run}"
                # )
                if next_time_to_run:
                    remaining_times.append(next_time_to_run)
                if new_entry:
                    # 收集需要更新的条目，延迟更新避免影响遍历
                    entries_temp[entry_key] = new_entry
            except RuntimeError as e:
                logger.exception(f"{self.display_name} Ticks runtime error:{e}, key: {self.entries[entry_key].args}")

        # 批量更新任务条目
        for group_key, entry in entries_temp.items():
            self.entries[group_key] = entry

        # 返回最小等待时间，若无任务则使用最大间隔
        return min(remaining_times + [self.max_interval])

    def beater(self, drift=-0.010):
        """
        调度器主循环，持续执行任务调度直到收到关闭信号

        参数:
            drift: float, 时间偏移量（默认-0.010秒）
                   负值使任务略微提前执行，补偿系统调度延迟

        执行步骤:
            1. 启动时记录日志，输出加载的任务条目信息
            2. 进入主循环，持续调用 tick() 执行调度
            3. 根据 tick() 返回的间隔时间休眠
            4. 收到关闭信号时抛出 BeatShutdown 异常退出

        调度流程:
            ┌─────────────────────────────────────────┐
            │              启动调度器                  │
            │     记录任务条目信息到日志               │
            └─────────────────┬───────────────────────┘
                              │
                              v
            ┌─────────────────────────────────────────┐
            │         while not __shutdown            │
            │  ┌───────────────────────────────────┐  │
            │  │  interval = tick() + drift        │  │
            │  │  sleep(interval)                  │  │
            │  └───────────────────────────────────┘  │
            └─────────────────┬───────────────────────┘
                              │ __shutdown = True
                              v
            ┌─────────────────────────────────────────┐
            │         raise BeatShutdown              │
            └─────────────────────────────────────────┘
        """
        # 启动日志：记录调度器名称和加载的任务数量
        logger.info(f"{self.display_name} Starting, load {len(self.entries)} entries")
        # 逐条记录任务信息：任务名称和调度配置
        for entry in self.entries.values():
            logger.info(f"{self.display_name} loading entry: {entry.task.__name__}({entry.schedule})")

        # 主调度循环
        while not self.__shutdown:
            # 执行一次调度周期，获取下次执行的等待时间
            interval = self.tick()
            # 应用时间偏移，补偿系统调度延迟
            interval = interval + drift if interval else interval
            if interval and interval > 0:
                logger.debug(f"{self.display_name} beat: Waking up in {interval}s.")
                time.sleep(interval)
        else:
            # 收到关闭信号，抛出异常终止调度器
            raise BeatShutdown(f"{self.display_name} beat shut down now")

    def __str__(self):
        return f"[monitor.beater.{self.name}]({id(self)})"

    @property
    def display_name(self):
        return str(self)


class DummyExecutor(Executor):
    def __init__(self, max_workers):
        self._shutdown = False
        self._shutdownLock = RLock()

    def submit(self, fn, *args, **kwargs):
        with self._shutdownLock:
            if self._shutdown:
                raise RuntimeError("can't schedule new futures after shutdown")

            f = Future()
            try:
                result = fn(*args, **kwargs)
            except BaseException as e:
                f.set_exception(e)
            else:
                f.set_result(result)

            return f

    def shutdown(self, wait=True):
        with self._shutdownLock:
            self._shutdown = True


class BeaterExecutor:
    """
    reference: apscheduler
    """

    exec_map = {
        "dumy": DummyExecutor,
        "thread": concurrent.futures.ThreadPoolExecutor,
        # "process": concurrent.futures.ProcessPoolExecutor,
    }

    def __init__(self, beat, max_workers=3, exec_type="dumy"):
        exector_cls = self.exec_map.get(exec_type)
        if not exector_cls:
            raise Exception(f"BeaterExecutor get unaccepted exec_type: {exec_type}")
        self._pool = exector_cls(int(max_workers))
        self.beat = beat
        self._lock = RLock()

    def shutdown(self, wait=True):
        self._pool.shutdown(wait)

    def execute(self, entry):
        with self._lock:
            self._do_submit_job(entry)

    def _do_submit_job(self, entry):
        def callback(f: Future):
            exc, tb = f.exception(), getattr(f.exception(), "__traceback__", None)
            if exc:
                self._run_job_error(exc, tb)
            else:
                self._run_job_success(f.result())

        future: Future = self._pool.submit(run_entry, entry)
        future.add_done_callback(callback)

    def _run_job_error(self, exc, traceback=None):
        exc_info = (exc.__class__, exc, traceback)
        logger.exception(f"{self.beat.display_name} task error: {exc}", exc_info=exc_info)

    def _run_job_success(self, result):
        entry, _, cost = result
        logger.info(f"{self.beat.display_name} task[{entry.task.__name__}] done in {cost}")


def run_entry(entry):
    start = time.time()
    try:
        result = entry.task(*entry.args)
    except Exception as exc:
        raise exc
    finally:
        close_old_connections()
    return entry, result, time.time() - start
