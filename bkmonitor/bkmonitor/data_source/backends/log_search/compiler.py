"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import copy
import logging
import re

from django.core.exceptions import EmptyResultSet
from django.db.models import Q
from django.utils import timezone

from bkmonitor.data_source.backends.base import compiler
from constants.common import DEFAULT_TENANT_ID

logger = logging.getLogger("bkmonitor.data_source.log_search")


class SQLCompiler(compiler.SQLCompiler):
    TIME_SECOND_AGG_FIELD_RE = re.compile(r"time\((?P<second>\d+)s\)")
    SELECT_RE = re.compile(
        r"(?P<agg_method>[^\( ]+)[\( ]+" r"(?P<metric_field>[^\) ]+)[\) ]+" r"([ ]?as[ ]+(?P<metric_alias>[^ ]+))?"
    )
    SPECIAL_CHARS = re.compile(r'([+\-=&|><!(){}[\]^"~*?\\:\/ ])')
    ESCAPED_SPECIAL_CHARS = re.compile(r'\\([+\-=&|><!(){}[\]^"~*?\\:\/ ])')

    DEFAULT_AGG_METHOD = "count"
    DEFAULT_METRIC_FIELD = "_index"
    DEFAULT_METRIC_ALIAS = "count"

    DEFAULT_TIME_FIELD = "dtEventTimeStamp"

    METRIC_AGG_TRANSLATE = {"count": "value_count", "min": "min", "max": "max", "avg": "avg", "sum": "sum"}

    def execute_sql(self):
        try:
            sql, params = self.as_sql()
        except Exception:
            raise

        if not params:
            raise EmptyResultSet

        try:
            result = self.connection.execute(sql, params)
            if not result:
                return []

            _, metric_field, metric_alias = self._get_metric()

            agg_interval, dimensions = self._get_dimensions()
            dimensions.reverse()
            dimensions.append(self._get_time_field())

            records = []
            self._get_buckets(records, {}, dimensions, 0, result.get("aggregations"), metric_alias)
            return records
        except Exception:
            raise

    def _parse_filter(self, node) -> str:
        """
        解析过滤条件节点生成查询表达式字符串
        todo query string 可能包含特殊字符需要进行转义
        参数:
            node: 过滤条件节点对象，需包含以下属性：
                - children: 子条件列表，元素类型为tuple或Q对象
                - connector: 条件连接符（AND/OR）

        返回值:
            str: 解析生成的查询表达式字符串，格式示例：
                "(field1: "value" OR field2: (*, 10])"

        执行流程:
            1. 遍历节点的所有子条件
            2. 对元组条件进行字段解析和操作符映射
            3. 对Q对象进行递归解析
            4. 组合所有子查询条件生成最终表达式
        """
        # 步骤1: 初始化子查询列表，用于存储所有解析后的查询表达式
        sub_queries = []

        # 步骤2: 遍历节点的所有子条件
        for child in node.children:
            # 步骤2.1: 处理元组类型的条件 (field__method, value)
            if isinstance(child, tuple) and len(child) == 2:
                # 步骤2.1.1: 解析字段名和操作符
                # 例如: "host__eq" -> field="host", method="eq"
                # 例如: "host" -> field="host", method="eq" (默认)
                field = child[0].split("__")
                if len(field) == 1 or "" in field:
                    # 没有操作符后缀，使用默认的eq操作符
                    field = child[0]
                    method = "eq"
                else:
                    # 提取字段名和操作符: 最后一个元素是操作符，其余是字段名
                    field, method = field[:-1], field[-1]
                    field = "__".join(field)

                # 步骤2.1.2: 统一值的格式为列表
                if not isinstance(child[1], list):
                    values = [child[1]]
                else:
                    values = child[1]

                # 跳过空值列表
                if not values:
                    continue

                # 步骤2.1.3: 转义特殊字符（如引号、括号等）
                values = [self.escape_char(value) for value in values]

                # 步骤2.1.4: 根据操作符映射到对应的查询语法模板
                # 默认多个值之间使用OR连接
                connector = "OR"
                if method == "eq":
                    # 等于: field: "value"
                    expr_template = '{}: "{}"'
                elif method == "neq":
                    # 不等于: NOT field: "value"，多个值使用AND连接
                    expr_template = 'NOT {}: "{}"'
                    connector = "AND"
                elif method == "gt":
                    # 大于: field: (value, *)，取最大值
                    expr_template = "{}: ({}, *)"
                    values = [max(values)]
                elif method == "gte":
                    # 大于等于: field: [value, *)，取最大值
                    expr_template = "{}: [{}, *)"
                    values = [max(values)]
                elif method == "lt":
                    # 小于: field: (*, value)，取最小值
                    expr_template = "{}: (*, {})"
                    values = [min(values)]
                elif method == "lte":
                    # 小于等于: field: (*, value]，取最小值
                    expr_template = "{}: (*, {}]"
                    values = [min(values)]
                elif method == "include":
                    # 包含: field: *value*（模糊匹配）
                    expr_template = "{}: *{}*"
                elif method == "exclude":
                    # 不包含: NOT field: *value*，多个值使用AND连接
                    expr_template = "NOT {}: *{}*"
                    connector = "AND"
                else:
                    # 不支持的操作符，跳过
                    continue

                # 步骤2.1.5: 生成子查询表达式
                # 多个值使用connector连接（OR或AND）
                sub_query_string = f" {connector} ".join(expr_template.format(field, value) for value in values)
                # 多个值时需要用括号包裹
                if len(values) > 1:
                    sub_query_string = f"({sub_query_string})"

                sub_queries.append(sub_query_string)

            # 步骤2.2: 递归处理嵌套的Q对象条件
            elif isinstance(child, Q):
                sub_query_string = self._parse_filter(child)
                if not sub_query_string:
                    continue
                sub_queries.append(sub_query_string)

        # 步骤3: 组合最终查询表达式
        # 使用节点的connector（AND/OR）连接所有子查询
        query_string = f" {node.connector} ".join(sub_queries)
        # 多个子查询时需要用括号包裹
        if len(sub_queries) > 1:
            query_string = f"({query_string})"

        return query_string

    def escape_char(self, s):
        """
        转义query string中的特殊字符
        """
        if not isinstance(s, str):
            return s

        # 避免双重转义：先移除已有转义
        s = self.ESCAPED_SPECIAL_CHARS.sub(r"\1", s)
        return self.SPECIAL_CHARS.sub(r"\\\1", str(s))

    def as_sql(self):
        """
        将查询对象转换为蓝鲸监控平台兼容的查询参数结构

        参数:
            self: Query实例对象，包含以下关键属性：
                - query: 查询上下文对象，包含租户ID(index_set_id)、表名(table_name)、原始查询字符串(raw_query_string)
                - high_mark/low_mark: 分页上限/下限
                - offset: 分页偏移量

        返回值:
            tuple: (空字符串, 查询参数字典)，其中查询参数字典包含：
                - bk_tenant_id: 租户ID
                - index_set_id/indices: 索引集ID或索引名称
                - time_field: 时间字段名称
                - aggs: 聚合配置
                - filter: 过滤条件
                - query_string: 查询语句
                - size/start: 分页参数
                - start_time/end_time: 时间范围

        执行流程:
        1. 租户ID处理：优先使用查询上下文中的租户ID，缺失时使用默认值并记录警告
        2. 时间字段解析：通过私有方法获取时间字段配置
        3. 聚合参数解析：提取聚合方法、指标字段及别名
        4. 索引配置处理：根据索引集ID或表名构建索引配置
        5. 聚合维度解析：获取聚合间隔和维度字段
        6. 过滤条件转换：将查询条件转换为平台兼容的过滤结构
        7. 时间范围提取：从查询条件中解析时间范围并转换为时间戳
        8. 查询语句构建：合并原始查询字符串和过滤条件
        9. 分页参数处理：计算分页大小和起始位置
        """
        # 步骤1: 租户ID处理 - 优先使用查询上下文中的租户ID，缺失时使用默认值
        bk_tenant_id = self.query.bk_tenant_id
        if not bk_tenant_id:
            logger.warning(
                f"get_query_tenant_id is empty, log query: {self.query.index_set_id or self.query.table_name or self.query.raw_query_string}"
            )
            bk_tenant_id = DEFAULT_TENANT_ID

        # 初始化结果字典，租户ID是必需参数
        result = {"bk_tenant_id": bk_tenant_id}

        # 步骤2: 获取时间字段配置（如dtEventTimeStamp、time等）
        time_field = self._get_time_field()

        # 步骤3: 解析SELECT字段 - 提取聚合方法、指标字段和别名
        # 例如: SELECT COUNT(*) AS total -> agg_method=COUNT, metric_field=*, metric_alias=total
        agg_method, metric_field, metric_alias = self._get_metric()

        # 步骤4: 解析索引配置 - 支持索引集ID或直接指定索引名称两种方式
        if self.query.index_set_id:
            # 使用索引集ID（推荐方式，由日志平台管理）
            result["index_set_id"] = self.query.index_set_id
        elif self.query.table_name:
            # 直接指定索引名称（需要同时指定时间字段）
            result["indices"] = self.query.table_name
            result["time_field"] = time_field
        else:
            raise Exception("SQL Error: Empty table name")

        # 步骤5: 解析GROUP BY子句 - 获取聚合间隔和维度字段
        # 例如: GROUP BY time(1m), host -> agg_interval=1m, dimensions=[host]
        agg_interval, dimensions = self._get_dimensions()
        result["aggs"] = self._get_aggregations(agg_interval, dimensions, agg_method, metric_field, metric_alias)

        # 步骤6: 解析过滤条件(agg_condition) - 转换为日志平台的filter格式
        # 将内部条件格式 {key, method, value} 转换为 {field, operator, value}
        if self.query.agg_condition:
            query_filter = []
            for cond in self.query.agg_condition:
                # 字段名映射: key -> field
                new_cond = {
                    "field": cond.get("field", cond.get("key")),
                    "operator": cond.get("operator", cond.get("method")),
                    "value": cond["value"],
                }
                # 保留逻辑连接符(and/or)
                if "condition" in cond:
                    new_cond["condition"] = cond["condition"]
                query_filter.append(new_cond)
            result["filter"] = query_filter

        # 步骤7: 解析WHERE子句 - 提取时间范围并从where条件中移除
        # 构建时间字段的所有可能形式: time__lt, time__lte, time__gt, time__gte
        time_field_list = [f"{time_field}__{method}" for method in ["lt", "lte", "gt", "gte"]]

        # 从where.children中提取时间条件到字典
        where_dict = {}
        for i in self.query.where.children:
            if isinstance(i, tuple) and len(i) == 2:
                where_dict[i[0]] = i[1]

        # 从where.children中移除时间条件（避免重复处理）
        self.query.where.children = [
            i
            for i in self.query.where.children
            if not (isinstance(i, tuple) and len(i) == 2 and i[0] in time_field_list)
        ]

        # 提取开始和结束时间（支持gte/lte/lt三种操作符）
        gte_field = f"{time_field}__gte"
        lte_field = f"{time_field}__lte"
        lt_field = f"{time_field}__lt"
        start_time = where_dict.get(gte_field)
        end_time = where_dict.get(lte_field) or where_dict.get(lt_field)  # lte优先，其次lt

        # 时间戳转换: 毫秒级转秒级（日志平台使用秒级时间戳）
        if start_time:
            result["start_time"] = start_time // 1000
        if end_time:
            result["end_time"] = end_time // 1000

        # 步骤8: 构建查询字符串 - 合并原始查询字符串和过滤条件
        filter_string = self._parse_filter(self.query.where)
        if self.query.raw_query_string and self.query.raw_query_string != "*":
            # 有原始查询字符串（如Lucene语法）
            if filter_string:
                # 同时存在原始查询和过滤条件，使用AND连接
                result["query_string"] = f"({self.query.raw_query_string}) AND {self._parse_filter(self.query.where)}"
            else:
                # 只有原始查询字符串
                result["query_string"] = self.query.raw_query_string
        elif filter_string:
            # 只有过滤条件
            result["query_string"] = self._parse_filter(self.query.where)

        # 步骤9: 设置分页参数
        if self.query.high_mark is not None:
            # 计算分页大小: high_mark - low_mark
            result["size"] = self.query.high_mark - self.query.low_mark
        else:
            # 默认返回1条记录
            result["size"] = 1

        # 注释: 排序功能暂时禁用，默认按时间倒序
        # result["sort_list"] = [[time_field, "desc"]]

        # 设置分页起始位置
        if self.query.offset is not None:
            result["start"] = self.query.offset

        # 返回空字符串和查询参数字典（符合Django ORM编译器接口规范）
        return "", result

    def _get_metric(self):
        if self.query.select:
            select_field = self.query.select[0]
            if "(" in select_field and ")" in select_field:
                match_result = self.SELECT_RE.match(select_field)
                group_dict = match_result.groupdict() if match_result else {}
                agg_method = group_dict.get("agg_method") or self.DEFAULT_AGG_METHOD
                metric_field = group_dict.get("metric_field") or self.DEFAULT_METRIC_FIELD
                metric_alias = group_dict.get("metric_alias") or metric_field
                return agg_method, metric_field, metric_alias
            else:
                return self.DEFAULT_AGG_METHOD, select_field, select_field
        else:
            return self.DEFAULT_AGG_METHOD, self.DEFAULT_METRIC_FIELD, self.DEFAULT_METRIC_ALIAS

    def _get_dimensions(self):
        group_by_fields = self.query.group_by
        group_by = sorted(set(group_by_fields), key=group_by_fields.index)

        second = 60
        dimensions = group_by[:]
        for idx, dim in enumerate(dimensions):
            time_agg_field = self.TIME_SECOND_AGG_FIELD_RE.match(dim)
            if time_agg_field:
                second = time_agg_field.groupdict().get("second")
                dimensions.pop(idx)
                break
        return second, dimensions

    def _get_time_field(self):
        return self.query.time_field or self.DEFAULT_TIME_FIELD

    def _get_aggregations(self, agg_interval, dimensions, agg_method, metric_field, metric_alias):
        """
        agg format:

        "aggregations": {
            "name": {
                "terms": {
                    "field": "name",
                    "size": 10
                },
                "aggregations": {
                    "host": {
                        "terms": {
                            "field": "host",
                            "size": 0
                        },
                        "aggregations": {
                            "dtEventTimeStamp": {
                                "date_histogram": {
                                    "field": "dtEventTimeStamp",
                                    'interval': "minute",

                                },
                                "aggregations": {
                                    "count": {
                                        "value_count": {
                                            "field": "_index"
                                        }
                                    }
                                }
                            }
                        },
                    }
                }
            }
        }
        """

        # metric aggregation
        metric_agg_method = self.METRIC_AGG_TRANSLATE[str(agg_method).lower()]
        metric_aggragations = {metric_alias: {metric_agg_method: {"field": metric_field}}}

        # datetime aggregation
        time_field = self._get_time_field()
        aggragations = {
            time_field: {
                "date_histogram": {
                    "field": time_field,
                    "interval": f"{agg_interval}s",
                    "time_zone": timezone.get_current_timezone().zone,
                },
                "aggregations": metric_aggragations,
            },
        }

        # dimension aggregation
        for dimension in dimensions:
            _aggragations = {dimension: {"terms": {"field": dimension, "size": 10000}}}
            _aggragations[dimension]["aggregations"] = aggragations
            aggragations = _aggragations

        return aggragations

    def _get_buckets(self, records, record, dimensions, i, aggs, metric_alias):
        if not aggs:
            return

        if dimensions:
            count = len(dimensions)
            buckets = aggs.get(dimensions[i]).get("buckets")
            dimension = dimensions[i]
            for bucket in buckets:
                record[dimension] = bucket.get("key")
                if i + 1 == count:
                    record[metric_alias] = bucket.get(metric_alias).get("value")
                    records.append(copy.deepcopy(record))
                else:
                    self._get_buckets(records, record, dimensions, i + 1, bucket, metric_alias)
        else:
            record[metric_alias] = aggs.get(metric_alias).get("value")
            records.append(copy.deepcopy(record))


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
