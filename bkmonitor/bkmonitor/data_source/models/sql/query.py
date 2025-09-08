"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from importlib import import_module

from django.db.models.sql import AND

from bkmonitor.data_source.models.sql.where import WhereNode
from constants.data_source import DataSourceLabel, DataTypeLabel
from core.drf_resource import api

DATA_SOURCE = {
    DataSourceLabel.BK_MONITOR_COLLECTOR: {
        DataTypeLabel.TIME_SERIES: {
            "query": api.metadata.get_ts_data,
            "backends": "bkmonitor.data_source.backends.time_series",
        },
        DataTypeLabel.LOG: {
            "query": api.metadata.get_es_data,
            "backends": "bkmonitor.data_source.backends.elastic_search",
        },
        DataTypeLabel.ALERT: {
            "query": None,
            "backends": "bkmonitor.data_source.backends.fta_event",
        },
    },
    DataSourceLabel.BK_DATA: {
        DataTypeLabel.TIME_SERIES: {
            "query": api.bkdata.query_data,
            "backends": "bkmonitor.data_source.backends.time_series",
        },
        DataTypeLabel.LOG: {"query": api.bkdata.query_data, "backends": "bkmonitor.data_source.backends.log"},
    },
    DataSourceLabel.BK_LOG_SEARCH: {
        DataTypeLabel.TIME_SERIES: {
            "query": api.log_search.es_query_search,
            "backends": "bkmonitor.data_source.backends.log_search",
        },
        DataTypeLabel.LOG: {
            "query": api.log_search.es_query_search,
            "backends": "bkmonitor.data_source.backends.log_search",
        },
    },
    DataSourceLabel.CUSTOM: {
        DataTypeLabel.EVENT: {
            "query": api.metadata.get_es_data,
            "backends": "bkmonitor.data_source.backends.elastic_search",
        },
        DataTypeLabel.TIME_SERIES: {
            "query": api.metadata.get_ts_data,
            "backends": "bkmonitor.data_source.backends.time_series",
        },
    },
    DataSourceLabel.BK_FTA: {
        DataTypeLabel.EVENT: {
            "query": None,
            "backends": "bkmonitor.data_source.backends.fta_event",
        },
        DataTypeLabel.ALERT: {
            "query": None,
            "backends": "bkmonitor.data_source.backends.fta_event",
        },
    },
    DataSourceLabel.BK_APM: {
        DataTypeLabel.TIME_SERIES: {
            "query": api.metadata.get_es_data,
            "backends": "bkmonitor.data_source.backends.elastic_search",
        },
        DataTypeLabel.LOG: {
            "query": api.metadata.get_es_data,
            "backends": "bkmonitor.data_source.backends.elastic_search",
        },
    },
}


def load_backends(using):
    """
    加载指定数据源的数据查询后端模块

    参数:
        using: 元组类型，包含两个元素
            - data_source: 数据源标识符（如数据库类型）
            - data_type: 数据类型标识符（如日志/指标类型）

    返回值:
        元组包含：
        - query_func: 配置中指定的查询函数对象
        - connection_module: 动态导入的后端连接模块

    执行流程：
    1. 解析数据源和数据类型参数
    2. 从全局配置中获取对应后端配置
    3. 动态导入指定的后端连接模块
    4. 返回查询函数和连接模块的元组
    """
    # 解析传入的元组参数为具体的数据源和数据类型
    data_source, data_type = using

    # 从全局配置字典中获取对应后端配置
    config = DATA_SOURCE.get(data_source, {}).get(data_type)

    # 提取配置中的查询函数和后端模块路径
    query_func = config["query"]
    backend_name = config["backends"]

    try:
        # 动态导入后端连接模块并返回结果
        return query_func, import_module(f"{backend_name}.connection")
    except ImportError:
        # 模块导入失败时抛出原始异常
        raise



def get_limit_range(low=None, high=None, low_mark=None, high_mark=None):
    if high is not None:
        if high_mark is not None:
            high_mark = min(high_mark, low_mark + high)
        else:
            high_mark = low_mark + high
    if low is not None:
        if high_mark is not None:
            low_mark = min(high_mark, low_mark + low)
        else:
            low_mark = low_mark + low
    return low_mark, high_mark


class RawQuery:
    """
    A single raw SQL query
    """

    def __init__(self, sql, using=None, params=None):
        self.params = params or ()
        self.sql = sql

        self.using = using or (DataSourceLabel.BK_MONITOR_COLLECTOR, DataTypeLabel.TIME_SERIES)

    def execute_query(self):
        sql = self.sql % self.params
        query_func, backend = load_backends(self.using)
        conn = backend.DatabaseConnection(query_func)
        return conn.execute(sql)


class Query:
    """
    SQL查询构建器基类，用于构造和管理数据库查询语句

    该类提供完整的SQL语句构建能力，支持查询条件、排序分组、聚合操作等
    核心功能包括：
    1. 查询条件管理（where子句）
    2. 字段选择与聚合配置
    3. 分页与排序控制
    4. 特定于ES的DSL扩展功能

    属性:
        bk_tenant_id: 蓝鲸租户ID
        select: 查询字段列表
        table_name: 数据表名称
        where: 查询条件树节点
        where_class: 条件节点类引用
        agg_condition: 聚合条件列表
        group_by: 分组字段列表
        order_by: 排序字段列表
        distinct: 去重标识符
        low_mark/high_mark: 分页起止位置
        slimit: 限制结果集大小
        offset: 偏移量
        index_set_id: 索引集ID（ES专用）
        group_hits_size: 分组结果大小
        ...
    """

    compiler = "SQLCompiler"

    def __init__(self, using, where=WhereNode):
        """
        初始化查询对象

        参数:
            using: 数据库连接别名
            where: 查询条件节点类，默认使用WhereNode

        初始化内容包含：
        1. 查询基础参数（select/table/where）
        2. 分组排序配置
        3. 分页参数（offset/limit）
        4. ES专用DSL扩展参数
        """
        self.bk_tenant_id = None
        self.select = []
        self.table_name = None
        self.where = where()
        self.where_class = where
        self.agg_condition = []
        self.group_by = []
        self.order_by = []
        self.distinct = ""
        self.low_mark, self.high_mark = 0, None  # Used for offset/limit
        self.slimit = None
        self.offset = None

        # DSL扩展参数初始化
        self.index_set_id = None
        # -1 表示不需要返回命中的 Top n 原始数据：使用场景是 APM
        self.group_hits_size = 0
        self.event_group_id = ""
        self.raw_query_string = ""
        self.nested_paths = {}
        # search after: https://www.elastic.co/guide/en/elasticsearch/reference/
        # current/search-aggregations-bucket-composite-aggregation.html#_pagination
        self.search_after_key = None
        self.use_full_index_names = False
        # 目前 ES 场景下默认都会补 date_histogram，在原始日志/指标计算等场景下非必须
        # 提供开关用于控制该行为，默认逻辑和之前一致（True）
        self.enable_date_histogram = True

        self.time_field = ""
        self.target_type = "ip"
        self.using = using

    def __str__(self):
        """
        返回格式化后的SQL字符串

        执行流程：
        1. 调用sql_with_params获取带占位符的SQL语句
        2. 去除参数列表末尾的多余元素
        3. 使用字符串格式化填充参数
        """
        sql, params = self.sql_with_params()
        params = params[:-1]
        return sql % params

    def clone(self):
        """
        创建当前查询对象的深拷贝

        执行步骤：
        1. 实例化新对象并复制基础属性
        2. 对列表/字典等可变对象执行深拷贝
        3. 特殊字段如search_after_key进行条件拷贝
        4. 返回克隆后的对象实例
        """
        obj = self.__class__(using=self.using)
        obj.bk_tenant_id = self.bk_tenant_id
        obj.select = self.select[:]
        obj.table_name = self.table_name
        obj.where = self.where.clone()
        obj.where_class = self.where_class
        obj.group_by = self.group_by[:]
        obj.order_by = self.order_by[:]
        # mysql: https://stackoverflow.com/questions/34312757/
        # es: https://www.elastic.co/guide/en/elasticsearch/reference/current/collapse-search-results.html
        obj.distinct = self.distinct
        obj.time_field = self.time_field
        obj.target_type = self.target_type
        obj.agg_condition = self.agg_condition[:]
        obj.low_mark, obj.high_mark = self.low_mark, self.high_mark
        obj.slimit = self.slimit
        obj.offset = self.offset

        # dsl
        obj.index_set_id = self.index_set_id
        obj.event_group_id = self.event_group_id
        obj.raw_query_string = self.raw_query_string
        obj.nested_paths = self.nested_paths.copy()
        if self.search_after_key is not None:
            obj.search_after_key = self.search_after_key.copy()
        obj.group_hits_size = self.group_hits_size
        obj.use_full_index_names = self.use_full_index_names
        obj.enable_date_histogram = self.enable_date_histogram

        return obj

    def set_bk_tenant_id(self, bk_tenant_id: int):
        """
        设置蓝鲸租户ID

        参数:
            bk_tenant_id: 租户ID整数值
        """
        if bk_tenant_id:
            self.bk_tenant_id = bk_tenant_id

    def sql_with_params(self):
        """
        Returns the query as an SQL string
        """
        return self.get_compiler(self.using).as_sql()

    def get_compiler(self, using=None, connection=None):
        """
        获取数据库编译器实例

        参数:
            using: 数据库连接别名
            connection: 数据库连接对象（可选）

        返回值:
            数据库编译器实例
        """
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if using:
            query_func, backend = load_backends(using)
            connection = backend.DatabaseConnection(query_func)
        return connection.ops.compiler(self.compiler)(self, connection, using)

    def add_select(self, col):
        """
        添加查询字段

        参数:
            col: 需要添加的字段名
        """
        if col and col.strip():
            self.select.append(col)

    def clear_select_fields(self):
        """清空所有已设置的查询字段"""
        self.select = []

    def set_agg_condition(self, agg_condition):
        """
        设置聚合查询条件

        参数:
            agg_condition: 聚合条件列表
        """
        if agg_condition:
            self.agg_condition = agg_condition

    def set_time_field(self, time_field):
        """
        设置时间字段

        参数:
            time_field: 时间字段名称
        """
        if time_field:
            self.time_field = time_field

    def set_target_type(self, target_type):
        """
        设置目标类型

        参数:
            target_type: 目标类型标识符
        """
        if target_type:
            self.target_type = target_type

    def set_offset(self, offset):
        """
        设置查询偏移量

        参数:
            offset: 偏移量数值
        """
        if offset:
            self.offset = offset

    def add_q(self, q_object):
        """
        添加查询条件对象

        参数:
            q_object: 查询条件对象
        """
        self.where.add(q_object, AND)

    def add_ordering(self, *ordering):
        """
        添加排序字段

        参数:
            *ordering: 可变数量的排序字段
        """
        if ordering:
            self.order_by.extend([x for x in ordering if x and x.strip()])

    def add_grouping(self, *grouping):
        """
        添加分组字段

        参数:
            *grouping: 可变数量的分组字段
        """
        if grouping:
            self.group_by.extend([x for x in grouping if x and x.strip()])

    def set_limits(self, low=None, high=None):
        """
        设置查询结果范围限制

        参数:
            low: 起始位置
            high: 结束位置
        """
        self.low_mark, self.high_mark = get_limit_range(low, high, self.low_mark, self.high_mark)

    def set_slimit(self, s):
        """
        设置结果集大小限制

        参数:
            s: 限制大小数值
        """
        self.slimit = s


class InsertQuery(Query):
    """
    TODO: Empty implements
    """

    compiler = "SQLInsertCompiler"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
