# coding=utf-8
# Time: 2025/8/10 23:03
# name: cache
# author: HACK-WU
import json
import time

from django.conf import settings

from drf_resource.cache import DefaultUsingCache, BaseCacheType, CacheTypeItem
from drf_resource.utils.local import local


class UsingCache(DefaultUsingCache):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.local_cache_enable = settings.ROLE == "web"

    def is_use_cache(self) -> bool:
        if settings.ENVIRONMENT == "development":
            return False
        return True

    def get_value(self, cache_key, default=None):
        """
        新增一级内存缓存（local）。在同一个请求(线程)中，优先使用内存缓存。
        一级缓存： local（web服务单次请求中生效）
        二级缓存： cache（60s生效）
        机制：
        local (miss), cache(miss): cache <- result
        local (miss), cache(hit): local <- result
        """
        # 尝试从一级内存缓存中获取值
        if self.local_cache_enable:
            value = getattr(local, cache_key, None)
            if value:
                # 一级缓存命中，返回解析后的值
                return json.loads(value)

        value = super().get_value(cache_key, default)

        if self.local_cache_enable:
            setattr(local, cache_key, json.dumps(value))

        # 返回最终值
        return value


using_cache = UsingCache


class CacheType(BaseCacheType):
    """
    缓存类型选项
    >>>@using_cache(CacheType.DATA(60 * 60))
    >>>@using_cache(CacheType.BIZ)
    """

    BIZ = CacheTypeItem(key="biz", timeout=settings.CACHE_BIZ_TIMEOUT, label="业务及人员相关", user_related=True)

    HOST = CacheTypeItem(key="host", timeout=settings.CACHE_HOST_TIMEOUT, label="主机信息相关", user_related=False)

    CC = CacheTypeItem(key="cc", timeout=settings.CACHE_CC_TIMEOUT, label="CC模块和Set相关", user_related=True)

    DATA = CacheTypeItem(key="data", timeout=settings.CACHE_DATA_TIMEOUT, label="计算平台接口相关", user_related=False)
    OVERVIEW = CacheTypeItem(
        key="overview", timeout=settings.CACHE_OVERVIEW_TIMEOUT, label="首页接口相关", user_related=False
    )
    USER = CacheTypeItem(key="user", timeout=settings.CACHE_USER_TIMEOUT, user_related=False)
    GSE = CacheTypeItem(key="gse", timeout=60 * 5, user_related=False)
    BCS = CacheTypeItem(key="bcs", timeout=60 * 5, user_related=False)
    METADATA = CacheTypeItem(key="metadata", timeout=60 * 10, user_related=False)
    APM = CacheTypeItem(key="apm", timeout=60 * 10, user_related=False)
    APM_EBPF = CacheTypeItem(key="apm_ebpf", timeout=60 * 10, user_related=False)
    APM_ENDPOINTS = CacheTypeItem(key="apm_endpoints", timeout=60 * 10, user_related=False)
    CC_BACKEND = CacheTypeItem(key="cc_backend", timeout=60 * 10, user_related=False)
    LOG_SEARCH = CacheTypeItem(key="log_search", timeout=60 * 5, label="日志平台相关", user_related=False)
    NODE_MAN = CacheTypeItem(key="node_man", timeout=60 * 30, label="节点管理相关", user_related=False)
    # 重要： 此类型表示所有resource调用均大概率命中缓存，因为缓存失效时间较长。缓存刷新由后台周期任务进行
    # 详细参看： from alarm_backends.core.api_cache.library import cmdb_api_list
    # 当出现cmdb数据变更长时间未生效，考虑后台进程缓存任务失败的可能：bk-monitor-alarm-api-cron-worker
    CC_CACHE_ALWAYS = CacheTypeItem(key="cc_cache_always", timeout=60 * 60, user_related=False)
    HOME = CacheTypeItem(key="home", timeout=settings.CACHE_HOME_TIMEOUT, label="自愈统计数据相关", user_related=False)
    DEVOPS = CacheTypeItem(key="devops", timeout=60 * 5, label="蓝盾接口相关", user_related=False)
    GRAFANA = CacheTypeItem(key="grafana", timeout=60 * 5, label="仪表盘相关", user_related=False)
    SCENE_VIEW = CacheTypeItem(key="scene_view", timeout=60 * 1, label="观测场景相关", user_related=False)


class InstanceCache(object):
    @classmethod
    def instance(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.__cache = {}

    def clear(self):
        self.__cache = {}

    def set(self, key, value, seconds=0, use_round=False):
        """
        :param key:
        :param value:
        :param seconds:
        :param use_round: 时间是否需要向上取整，取整用于缓存时间同步
        :return:
        """
        if not seconds:
            timeout = 0
        else:
            if not use_round:
                timeout = time.time() + seconds
            else:
                timeout = (time.time() + seconds) // seconds * seconds
        self.__cache[key] = (value, timeout)

    def __get_raw(self, key):
        value = self.__cache.get(key)
        if not value:
            return None
        if value[1] and time.time() > value[1]:
            del self.__cache[key]
            return None
        return value

    def exists(self, key):
        value = self.__get_raw(key)
        return value is not None

    def get(self, key):
        value = self.__get_raw(key)
        return value and value[0]

    def delete(self, key):
        try:
            del self.__cache[key]
        except KeyError:
            pass
