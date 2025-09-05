"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import time
from abc import ABC
from collections.abc import Callable, Iterable

from django.utils.translation import gettext as _
from elasticsearch_dsl import AttrDict, Q, Search
from elasticsearch_dsl.aggs import Bucket
from elasticsearch_dsl.response import Response
from luqum.auto_head_tail import auto_head_tail
from luqum.elasticsearch import ElasticsearchQueryBuilder, SchemaAnalyzer
from luqum.exceptions import ParseError
from luqum.parser import lexer, parser
from luqum.tree import AndOperation, FieldGroup, SearchField, Word

from bkmonitor.utils.elasticsearch.handler import BaseTreeTransformer
from bkmonitor.utils.ip import exploded_ip
from bkmonitor.utils.request import get_request, get_request_username
from constants.alert import EventTargetType
from core.drf_resource import resource
from core.errors.alert import QueryStringParseError
from fta_web.alert.handlers.translator import AbstractTranslator
from fta_web.alert.utils import process_metric_string, process_stage_string, is_include_promql, strip_outer_quotes
import re


class QueryField:
    def __init__(
        self,
        field: str,
        display: str,
        es_field: str = None,
        agg_field: str = None,
        searchable: bool = True,
        is_char: bool = False,
        alias_func: Callable[[SearchField], None] | None = None,
    ):
        """
        :param field: 展示的字段英文名
        :param display: 展示的字段中文名
        :param es_field: 实际用于查询ES的底层字段名
        :param agg_field: ES 用于聚合计算的字段
        :param searchable: 是否为计算字段（即不在ES中保存）
        :param is_char: 是否为字符字段
        :param alias_func:
        """
        self.field = field
        self.display = display
        self.es_field = field if es_field is None else es_field
        self.agg_field = self.es_field if agg_field is None else agg_field
        self.searchable = searchable
        # is_char参数对查询没有影响，仅用于前端展示
        # top_n查询时，is_char为True时，会将字段值加上双引号。
        self.is_char = is_char
        self.alias_func = alias_func

    def get_value_by_es_field(self, data: dict):
        """
        根据ES字段从Hit中拿出对应字段数据
        :param data:
        :return:
        """
        if not self.es_field:
            return None
        value = data
        try:
            for path in self.es_field.split("."):
                value = value.get(path, None)
        except Exception:
            value = None
        return value


class BaseQueryTransformer(BaseTreeTransformer):
    """
    Elasticsearch 自定义 query_string 到 标准化 query_string 转换器
    """

    # 可供查询的ES字段配置
    query_fields: list[QueryField] = []

    # 需要转换的嵌套KV字段，key 为匹配前缀，value 为搜索字段
    # 例如 "tags.": "event.tags"
    NESTED_KV_FIELDS = {}

    # 需要进行值转换的字段
    VALUE_TRANSLATE_FIELDS = {}

    # ES 文档类
    doc_cls = None

    def visit_search_field(self, node, context):
        """
        处理搜索字段的解析与转换逻辑

        参数:
            node: 当前处理的搜索字段节点对象
                包含字段名称(name)和表达式(expr)等属性
            context: 上下文字典
                包含搜索字段处理的运行时状态信息
                特殊键值:
                    - ignore_search_field: 布尔值，是否忽略字段转换
                    - search_field_name: 处理后的字段名称
                    - search_field_origin_name: 原始字段名称

        返回值:
            生成器对象，遍历处理后的节点元素
            通过yield from返回处理链的中间件响应

        执行流程:
        1. 安全短路处理: 当忽略字段转换时直接透传节点
        2. 嵌套KV字段转换:
           对tags.key/tags.value等特殊字段进行双重搜索转换
           (tags.a : b) => (tags.key : a AND tags.value : b)
        3. 字段别名处理:
           调用字段别名函数(如存在)
           执行字段名到ES存储名的转换
        4. IPv6地址规范化:
           对event.ipv6字段执行地址展开标准化
        5. 上下文更新:
           记录原始字段名与转换后字段名
        """
        if context.get("ignore_search_field"):
            yield from self.generic_visit(node, context)
        else:
            origin_node_name = node.name
            # NESTED_KV_FIELDS 为监控定义的特殊字段，tags.key, tags.value, tags.value.raw
            for field, es_field in self.NESTED_KV_FIELDS.items():
                if node.name.startswith(f"{field}."):
                    self.has_nested_field = True
                    # 对标签进行特殊处理， (tags.a : b) => (tags.key : a AND tags.value : b)
                    node = SearchField(
                        es_field,
                        FieldGroup(
                            AndOperation(
                                SearchField("key", Word(node.name[len(field) + 1 :])),
                                SearchField("value.raw", node.expr),
                            )
                        ),
                    )
                    # tags的存储格式为：
                    # {"tags": [{"key": "host", "value": "server1"}, {"key": "module", "value": "web"}]}
                    break
            else:
                query_field = self.get_field_info(node.name)
                if query_field and query_field.alias_func:
                    query_field.alias_func(node)

                node = SearchField(self.transform_field_to_es_field(node.name), node.expr)

            if node.name == "event.ipv6":
                ipv6 = exploded_ip(node.expr.value.strip('"'))
                node.expr.value = f'"{ipv6}"'

            context.update({"search_field_name": node.name, "search_field_origin_name": origin_node_name})

            yield from self.generic_visit(node, context)

    @classmethod
    def transform_query_string(cls, query_string: str, context=None):
        """
        转换查询字符串为ES查询DSL或重整后的查询字符串

        参数:
            cls: 当前类，用于创建转换对象实例
            query_string: 原始查询字符串，需要被解析转换的输入。
                          空字符串将直接返回空结果，无需处理

        返回:
            str: 转换后的ES查询DSL字符串或优化后的查询字符串。
                 当存在嵌套字段时返回DSL格式，否则返回重整后的查询字符串

        该方法实现完整的查询字符串转换流程，包含：
        1. PromQL语法预处理
        2. 查询语法树解析
        3. 嵌套字段特殊处理
        4. 查询语句格式重整
        """

        def parse_query_string_node(_transform_obj, _query_string, _context):
            """解析查询字符串生成语法树节点"""
            try:
                query_node = parser.parse(_query_string, lexer=lexer.clone())
                return _transform_obj.visit(query_node, _context)
            except ParseError as e:
                raise QueryStringParseError({"msg": e})

        # 处理空输入情况
        if not query_string:
            return ""

        transform_obj = cls()

        # 处理PromQL特殊语法
        # 包含promql语句时需要特殊转换处理，可能触发语法错误
        if is_include_promql(query_string):
            # todo 调整，将判断是否为promql语句，调整到top_n查询中，如果为promql语句，返回转义后的语句。然后再使用转义后的语句进行查询
            query_string = cls.convert_metric_id(query_string)

        # 解析生成查询语法树
        # 使用自定义语法解析器进行节点转换
        query_tree = parse_query_string_node(transform_obj, query_string, context)

        # 嵌套字段特殊处理逻辑
        # 当存在嵌套字段时需要转换为DSL模式（query_string兼容性限制）
        if getattr(transform_obj, "has_nested_field", False) and cls.doc_cls:
            schema_analyzer = SchemaAnalyzer(cls.doc_cls._index.to_dict())
            es_builder = QueryBuilder(**schema_analyzer.query_builder_options())
            dsl = es_builder(query_tree)
            return dsl

        # 查询语句格式重整
        # 修复语法树转换过程中导致的空格丢失问题
        query_tree = auto_head_tail(query_tree)

        return str(query_tree)

    @classmethod
    def convert_metric_id(cls, query_string: str) -> str:
        """
        当指定了指标ID时，且指标ID值是一个promql，比如"sum(sum_over_time({__name__="custom::bk_apm_count"}[1m])) or vector(0)"
        此时需要对指标ID进行转义，并在前后加上“*”，用于支持模糊查询

        '+ - = && || > < ! ( ) { } [ ] ^ " ~ * ? : \ /' 字符串在query string中具有特殊含义，需要转义
        参考文档： https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-query-string-query
        """

        def convert_metric(match):
            value = match.group(0)
            value = strip_outer_quotes(value.split(":", 1)[1])

            value = re.sub(r'([+\-=&|><!(){}[\]^"~*?\\:\/ ])', lambda match: "\\" + match.group(0), value.strip())

            # 给value前后加上“*”，用于支持模糊匹配
            if not value.startswith("*"):
                value = "*" + value
            if not value.endswith("*"):
                value = value + "*"
            return f"{target_type} : {value}"

        def add_quote(match):
            value = match.group("value")
            value = f'"{value}"' if value else value
            return f"{target_type} : {value}"

        target_type = "指标ID"

        # 如果匹配上，则指标ID是被截断过的
        if re.match(r'(指标ID|event.metric)\s*:.*\.{3}"', query_string, flags=re.IGNORECASE):
            query_string = re.sub(
                r'(指标ID|event.metric)\s*:.*\.{3}"', convert_metric, query_string, flags=re.IGNORECASE
            )
            return query_string

        # 指标ID: "sum(sum_over_time({__name__=\"custom::bk_apm_count\"}[1m])) or vector(0)"
        # 匹配需要被转义的promql语句，是根据`指标ID:"{promql}"`的格式进行匹配
        #  - 如果promql本身就已经具有引号，会导致匹配失败，需要到promql中的引号提前处理，这里是将其转为“#”号。
        #  - 如果指标格式为`指标ID:{promql}`，也会匹配失败，需要转变为`指标ID:"{promql}"`
        query_string = cls.process_label_filter(query_string)
        query_string = re.sub(
            r'(指标ID|event.metric)\s*:\s*(?P<value>[^\s+\'"]*)', add_quote, query_string, re.IGNORECASE
        )
        query_string = re.sub(
            r'(指标ID|event.metric)\s*:\s*("[^"]*"*|\'[^\']*\'*)', convert_metric, query_string, re.IGNORECASE
        )

        # 还原process_label_filter函数中处理的双引号，并做转义
        query_string = query_string.replace("###", r"\~\"")
        query_string = query_string.replace("##", r"\=\"")
        query_string = query_string.replace("#", r"\"")

        return query_string

    @classmethod
    def process_label_filter(cls, query_string: str) -> str:
        """处理promql语句中的过滤条件，对双引号进行提前处理，否则会导致转义失败"""

        def replace(match):
            value = match.group(0)
            # 将{__name__="custom::bk_apm_count"}[1m]) 替换为 {__name__##custom::bk_apm_count#}
            value = value.replace('~"', "###").replace('="', "##").replace('"', "#")
            return value

        # 匹配promql中的过滤条件,比如：{__name__="custom::bk_apm_count"}
        pattern = r"\{.*(=|~).*\}"
        query_string = re.sub(pattern, replace, query_string)
        return query_string

    @classmethod
    def get_field_info(cls, field: str) -> QueryField | None:
        """查询 QueryField"""
        for field_info in cls.query_fields:
            if field_info.searchable and field in [field_info.field, str(field_info.display), _(field_info.display)]:
                return field_info

    @classmethod
    def transform_field_to_es_field(cls, field: str, for_agg=False):
        """
        将字段名转换为ES可查询的真实字段名
        """
        field_info = cls.get_field_info(field)
        if field_info:
            return field_info.agg_field if for_agg else field_info.es_field

        return field


class BaseQueryHandler:
    # query_string 语法树自定义解析类
    query_transformer = None

    class DurationOption:
        # 关于时间差的选项
        FILTER = {
            "minute": {"lt": 60 * 60},
            "hour": {"gte": 60 * 60, "lt": 24 * 60 * 60},
            "day": {"gte": 24 * 60 * 60},
        }
        AGG = {
            "minute": {"key": "minute", "to": 60 * 60},
            "hour": {"key": "hour", "from": 60 * 60, "to": 24 * 60 * 60},
            "day": {"key": "day", "from": 24 * 60 * 60},
        }
        QUERYSTRING = {
            "minute": f"<{60 * 60}",
            "hour": f"[{60 * 60} TO {24 * 60 * 60}]",
            "day": f">{24 * 60 * 60}",
        }
        DISPLAY = {
            "minute": _("小于1h"),
            "hour": _("大于1h且小于1d"),
            "day": _("大于1d"),
        }

    def __init__(
        self,
        start_time: int = None,
        end_time: int = None,
        ordering: list[str] = None,
        query_string: str = "",
        conditions: list = None,
        page: int = 1,
        page_size: int = 10,
        need_bucket_count: bool = True,
        **kwargs,
    ):
        self.start_time = start_time
        # 结束时间为未来时间的时候，默认为当前时间 加1min
        self.end_time = end_time
        if self.end_time:
            self.end_time = min(int(time.time() + 60), end_time)
        self.query_string = query_string
        self.conditions = conditions
        self.page = page
        self.page_size = page_size

        # 转换 ordering 字段
        self.ordering = self.query_transformer.transform_ordering_fields(ordering)
        # 转换 condition 的字段
        self.conditions = self.query_transformer.transform_condition_fields(conditions)
        self.bucket_count_suffix = ".bucket_count" if need_bucket_count else ""

    def scan(self, source_fields=None):
        """
        扫描全量符合条件的文档

        :param source_fields: 可选，指定需要返回的字段。如果为None，返回所有字段。
        """
        search_object = self.get_search_object()
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object)
        search_object = self.add_ordering(search_object)

        if source_fields:
            search_object = search_object.source(source_fields)

        yield from search_object.params(preserve_order=True).scan()

    def export(self) -> list[dict]:
        """
        将数据导出，用于生成 csv 文件
        :return:
        """
        cleaned_docs = (self.handle_hit(hit) for hit in self.scan())
        return list(self.translate_field_names(cleaned_docs))

    def translate_field_names(self, docs: Iterable[dict]) -> Iterable[dict]:
        """将字段名转换为显示名。"""
        # 预先翻译
        translated_fields = [(field.field, str(field.display)) for field in self.query_transformer.query_fields]

        for doc in docs:
            translated_doc = {}
            for field, display in translated_fields:
                translated_doc[display] = doc.get(field)
            yield translated_doc

    def get_search_object(self, *args, **kwargs) -> Search:
        """
        获取ES查询对象的方式，子类必须实现
        """
        raise NotImplementedError

    def add_pagination(self, search_object: Search, page: int = None, page_size: int = None):
        """
        分页
        """
        page = self.page if page is None else page
        page_size = self.page_size if page_size is None else page_size

        end_offset = page * page_size
        start_offset = end_offset - page_size
        search_object = search_object[start_offset:end_offset]
        return search_object

    def add_ordering(self, search_object: Search, ordering=None):
        """
        排序
        """
        ordering = self.ordering if ordering is None else self.query_transformer.transform_ordering_fields(ordering)

        if ordering:
            search_object = search_object.sort(*ordering)

        return search_object

    def add_query_string(self, search_object: Search, query_string: str = None, context=None):
        """
        处理并添加查询字符串到Elasticsearch搜索对象

        参数:
            search_object: Elasticsearch DSL Search对象，用于构建查询
            query_string: 原始查询字符串（可选），默认使用self.query_string

        返回值:
            包含查询条件的Search对象

        该方法实现完整的查询字符串处理流程：
        1. 查询字符串初始化：优先使用传入参数，否则使用实例属性
        2. 字符串预处理：依次执行阶段处理和指标处理逻辑
        3. DSL转换：将文本查询转换为Elasticsearch DSL结构
        4. 查询构建：根据DSL类型选择query_string或filter查询方式
        """
        query_string = self.query_string if query_string is None else query_string
        # todo 移动到 Transformer 中进行处理
        query_string = process_stage_string(query_string)
        query_string = process_metric_string(query_string)

        if query_string.strip():
            query_dsl = self.query_transformer.transform_query_string(query_string, context)
            if isinstance(query_dsl, str):
                # 使用query_string查询方式构建查询条件
                search_object = search_object.query("query_string", query=query_dsl)
            else:
                # 使用filter查询方式构建结构化查询
                search_object = search_object.query(query_dsl)
        return search_object

    def add_conditions(self, search_object: Search, conditions: list = None):
        """
        为搜索对象添加过滤条件

        Args:
            search_object: 需要被处理的原始搜索对象（Search类型）
            conditions: 过滤条件列表，每个条件项应包含字段、方法、值等信息。
                        当为None时使用self.conditions作为默认条件

        Returns:
            Search: 添加过滤条件后的新搜索对象

        处理逻辑：
        1. 条件预处理：转换条件字段命名或格式
        2. 条件组合：根据逻辑运算符（AND/OR）组合多个条件
        3. 反向条件处理：支持不等于（neq）的特殊处理
        """
        # 处理条件默认值及字段转换
        conditions = (
            self.conditions if conditions is None else self.query_transformer.transform_condition_fields(conditions)
        )

        if not conditions:
            return search_object

        # 初始化组合查询条件
        cond_q = None
        # 遍历所有条件进行组合
        for condition in conditions:
            q = self.parse_condition_item(condition)
            # 处理不等于的特殊逻辑
            if condition["method"] == "neq":
                q = ~q

            # 组合查询逻辑（AND/OR）
            if cond_q is None:
                cond_q = q
            elif condition["condition"] == "or":
                cond_q |= q
            else:
                cond_q &= q

        # 将最终组合的条件应用到搜索对象
        if cond_q is not None:
            search_object = search_object.filter(cond_q)

        return search_object

    def parse_condition_item(self, condition: dict) -> Q:
        """
        将字典格式的查询条件转换为Elasticsearch DSL的Q查询对象

        参数:
            condition: 包含查询条件的字典对象，格式要求:
                {
                    "method": "include/exclude/terms/gte/gt/lte/lt",
                    "key": 字段名称,
                    "value": 匹配值(字符串、列表或范围对象)
                }

        返回值:
            转换后的Q查询对象，用于构建Elasticsearch查询条件

        处理逻辑:
        1. 包含查询(include):
            - 单值转换为通配符查询(*value*)
            - 多值生成多个通配符查询并通过OR组合
        2. 排除查询(exclude):
            - 单值转换为取反的通配符查询
            - 多值生成多个通配符查询后整体取反
        3. 范围查询(gte/gt/lte/lt):
            - 支持大于等于、大于、小于等于、小于的范围比较
        4. 默认terms查询:
            - 直接转换为terms精确匹配查询
        """
        if condition["method"] == "include":
            if isinstance(condition["value"], list):
                # 生成多个wildcard查询并组合
                # 当存在多个包含条件时，通过bool should组合查询条件
                queries = [Q("wildcard", **{condition["key"]: f"*{value}*"}) for value in condition["value"]]
                return queries[0] if len(queries) == 1 else Q("bool", should=queries)
            # 生成单个wildcard查询
            return Q("wildcard", **{condition["key"]: f"*{condition['value']}*"})

        elif condition["method"] == "exclude":
            if isinstance(condition["value"], list):
                # 生成多个wildcard查询并组合后整体取反
                # 通过~运算符实现逻辑非操作
                queries = [Q("wildcard", **{condition["key"]: f"*{value}*"}) for value in condition["value"]]
                return ~(queries[0] if len(queries) == 1 else Q("bool", should=queries))
            # 生成单个取反wildcard查询
            return ~Q("wildcard", **{condition["key"]: f"*{condition['value']}*"})

        elif condition["method"] in ["gte", "gt", "lte", "lt"]:
            # 范围查询：支持大于、大于等于、小于、小于等于操作
            # 构建range查询条件，用于数值或日期字段的范围比较
            value = condition["value"]
            if isinstance(value, list) and value:
                value = value[0]
            return Q("range", **{condition["key"]: {condition["method"]: value}})

        # 默认执行terms精确匹配查询
        return Q("terms", **{condition["key"]: condition["value"]})

    @classmethod
    def calculate_agg_interval(cls, start_time: int, end_time: int, interval: str = "auto"):
        """
        根据起止时间计算聚合步长
        返回单位：秒
        """
        if not interval or interval == "auto":
            hour_interval = (end_time - start_time) // 3600
            if hour_interval <= 1:
                # 1分钟
                interval = 60
            elif hour_interval <= 6:
                # 5分钟
                interval = 5 * 60
            elif hour_interval <= 72:
                # 1小时
                interval = 60 * 60
            else:
                # 1天
                interval = 24 * 60 * 60
        else:
            interval = int(interval)

        return interval

    @classmethod
    def handle_hit_list(cls, hits=None):
        hits = hits or []
        return [cls.handle_hit(hit) for hit in hits]

    @classmethod
    def handle_hit(cls, hit):
        """
        处理Elasticsearch查询结果的数据清洗与字段映射

        参数:
            cls: 调用该方法的类对象
            hit: Elasticsearch查询结果对象，可以是字典或包含to_dict()方法的对象

        返回值:
            dict: 包含清洗后数据的字典对象，结构根据query_transformer配置决定

        执行流程:
        1. 统一数据格式转换（字典化处理）
        2. 空字段配置快速返回优化
        3. 固定字段映射与值转换
        """
        # 统一数据格式转换
        if isinstance(hit, dict):
            data = hit
        else:
            data = hit.to_dict()

        # 短路处理：当无字段映射需求时直接返回原始数据
        if not cls.query_transformer.query_fields:
            return data

        cleaned_data = {}

        # 固定字段映射处理
        # 遍历配置字段并执行以下操作：
        # 1. 获取字段原始名称
        # 2. 通过字段定义的get_value_by_es_field方法进行值转换
        for field in cls.query_transformer.query_fields:
            cleaned_data[field.field] = field.get_value_by_es_field(data)
        return cleaned_data

    @classmethod
    def make_empty_response(cls):
        """
        构造一个空的ES返回请求
        :return:
        """
        result = {"hits": {"total": {"value": 0, "relation": "eq"}, "max_score": 1.0, "hits": []}}
        return Response(Search(), result)

    def add_agg_bucket(self, search_object: Bucket, field: str, size: int = 10):
        """
        按字段添加聚合桶
        """
        # 处理桶排序
        if field.startswith("-"):
            order = {"_count": "desc"}
            actual_field = field[1:]
        elif field.startswith("+"):
            order = {"_count": "asc"}
            actual_field = field[1:]
        else:
            # 默认情况
            order = {"_count": "desc"}
            actual_field = field

        if actual_field.startswith("tags."):
            # tags 标签需要做嵌套查询
            tag_key = actual_field[len("tags.") :]

            # 进行桶聚合
            new_search_object = (
                search_object.bucket(field, "nested", path="event.tags")
                .bucket("key", "filter", {"term": {"event.tags.key": tag_key}})
                .bucket(
                    "value",
                    "terms",
                    field="event.tags.value.raw",
                    size=size,
                    order=order,
                )
            )

        else:
            agg_field = self.query_transformer.transform_field_to_es_field(actual_field, for_agg=True)
            if agg_field == "duration":
                # 对于Duration，需要进行范围桶聚合
                new_search_object = search_object.bucket(
                    field,
                    "range",
                    ranges=list(self.DurationOption.AGG.values()),
                    field=agg_field,
                )
            else:
                new_search_object = search_object.bucket(
                    field,
                    "terms",
                    field=agg_field,
                    order=order,
                    size=size,
                )

        return new_search_object

    def add_cardinality_bucket(self, search_object: Bucket, field: str, bucket_count_suffix: str):
        """
        添加基数聚合桶
        """
        actual_field = field.lstrip("+-")
        if actual_field.startswith("tags."):
            tag_key = actual_field[len("tags.") :]
            search_object.bucket(f"{field}{bucket_count_suffix}", "nested", path="event.tags").bucket(
                "key", "filter", {"term": {"event.tags.key": tag_key}}
            ).bucket("value", "cardinality", field="event.tags.value.raw")
        else:
            agg_field = self.query_transformer.transform_field_to_es_field(actual_field, for_agg=True)
            search_object.bucket(f"{field}{bucket_count_suffix}", "cardinality", field=agg_field)

    def top_n(self, fields: list, size=10, translators: dict[str, AbstractTranslator] = None, char_add_quotes=True):
        """
        字段值 TOP N 统计
        通过Elasticsearch聚合查询获取指定字段的TOP N分布情况，支持字段排序方式配置、字符字段处理和结果翻译

        :param fields: 需要统计的字段列表，字段名前可加排序标识：
                      "+abc" 升序排列，"-abc" 降序排列，默认降序排列
                      支持特殊字段处理：tags.*字段、duration字段、bk_biz_id字段
        :param size: 每个字段返回的TOP N数量，默认10，最大不超过10000
        :param translators: 翻译器字典，用于对聚合结果进行翻译转换
                           格式：{"字段名": translator实例}
        :param char_add_quotes: 是否为字符字段的桶值添加双引号，默认True
        :return: 包含以下结构的字典：
        {
            "doc_count": int,  # 总文档数
            "fields": list[dict],  # 每个字段的统计结果列表
            # 单个字段统计结构：
            {
                "field": str,  # 原始字段名
                "is_char": bool,  # 是否为字符字段
                "bucket_count": int,  # 总桶数（用于分页）
                "buckets": list[dict],  # TOP N桶列表
                # 单个桶结构：
                {
                    "key": str,  # 桶值
                    "doc_count": int  # 文档计数
                }
            }
        }
        """
        # 初始化翻译器字典
        translators = translators or {}

        # 构建并配置搜索对象
        # 添加过滤条件和查询字符串，设置参数track_total_hits=True保证准确计数
        search_object = self.get_search_object()
        search_object = self.add_conditions(search_object)
        search_object = self.add_query_string(search_object)
        search_object = search_object.params(track_total_hits=True).extra(size=0)

        # 限制最大桶数量，防止超过ES限制
        size = min(size, 10000)

        bucket_count_suffix = self.bucket_count_suffix
        for field in fields:
            self.add_agg_bucket(search_object.aggs, field, size=size)
            if bucket_count_suffix:
                self.add_cardinality_bucket(search_object.aggs, field, bucket_count_suffix)

        # 执行ES搜索查询
        search_result = search_object.execute()

        # 初始化基础结果结构
        result = {
            "doc_count": search_result.hits.total.value,
            "fields": [],
        }

        # 获取所有字符字段列表，用于后续处理
        char_fields = [field_info.field for field_info in self.query_transformer.query_fields if field_info.is_char]

        # 处理每个字段的聚合结果
        for field in fields:
            bucket_count = None
            if not search_result.aggs:
                result["fields"].append(
                    {
                        "field": field,
                        "is_char": field in char_fields,
                        "bucket_count": bucket_count,
                        "buckets": [],
                    }
                )
                continue

            # 提取实际字段名（去除排序标识符）
            actual_field = field.strip("-+")

            # 特殊处理tags.*字段：从多层嵌套聚合中提取数据
            if actual_field.startswith("tags."):
                if bucket_count_suffix:
                    bucket_count = getattr(search_result.aggs, f"{field}{bucket_count_suffix}").key.value.value

                buckets = [
                    {"id": bucket.key, "name": bucket.key, "count": bucket.doc_count}
                    for bucket in getattr(search_result.aggs, field).key.value.buckets
                ]

            # 特殊处理duration字段：使用预定义的持续时间选项
            elif actual_field == "duration":
                if bucket_count_suffix:
                    bucket_count = len(self.DurationOption.AGG)

                buckets = [
                    {
                        "id": self.DurationOption.QUERYSTRING[bucket.key],
                        "name": self.DurationOption.DISPLAY[bucket.key],
                        "count": bucket.doc_count,
                    }
                    for bucket in getattr(search_result.aggs, field).buckets
                ]

            # 特殊处理bk_biz_id字段：补充授权业务数据
            elif actual_field == "bk_biz_id" and hasattr(self, "authorized_bizs"):
                buckets = [
                    {"id": bucket.key, "name": bucket.key, "count": bucket.doc_count}
                    for bucket in getattr(search_result.aggs, field).buckets
                ]
                exist_bizs = {int(bucket["id"]) for bucket in buckets}
                # 补充未出现在聚合结果中的授权业务
                for bk_biz_id in self.authorized_bizs:
                    if len(buckets) >= size:
                        break
                    if int(bk_biz_id) in exist_bizs:
                        continue
                    buckets.append({"id": bk_biz_id, "name": bk_biz_id, "count": 0})

                if bucket_count_suffix:
                    bucket_count = len(set(self.authorized_bizs) | exist_bizs)

            # 默认字段处理：提取普通聚合结果
            else:
                if bucket_count_suffix:
                    # 获取到基数聚合后的桶数量
                    bucket_count = getattr(search_result.aggs, f"{field}{bucket_count_suffix}").value
                buckets = []
                for bucket in getattr(search_result.aggs, field).buckets:
                    if bucket_count_suffix and not bucket.key:
                        bucket_count -= 1
                    else:
                        buckets.append({"id": bucket.key, "name": bucket.key, "count": bucket.doc_count})

            # 应用翻译器转换数据
            if actual_field in translators:
                translators[actual_field].translate_from_dict(buckets, "id", "name")

            # 为字符字段添加双引号
            if char_add_quotes:
                for bucket in buckets:
                    if actual_field in char_fields or actual_field.startswith("tags."):
                        bucket["id"] = '"{}"'.format(bucket["id"])

            # 组装最终字段结果
            result["fields"].append(
                {
                    "field": field,
                    "is_char": actual_field in char_fields or actual_field.startswith("tags."),
                    "bucket_count": bucket_count,
                    "buckets": buckets,
                }
            )
        return result


class BaseBizQueryHandler(BaseQueryHandler, ABC):
    def __init__(
        self,
        bk_biz_ids: list[int] = None,
        username: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.bk_biz_ids = bk_biz_ids
        self.authorized_bizs = self.bk_biz_ids
        self.unauthorized_bizs = []
        self.username = username
        self.request_username = username or get_request_username()
        if self.bk_biz_ids is not None:
            self.authorized_bizs, self.unauthorized_bizs = self.parse_biz_item(bk_biz_ids, **kwargs)

    @classmethod
    def parse_biz_item(self, bk_biz_ids, **kwargs):
        if "authorized_bizs" in kwargs:
            authorized_bizs = kwargs["authorized_bizs"] or bk_biz_ids
            unauthorized_bizs = kwargs["unauthorized_bizs"] or []
        else:
            try:
                req = get_request()
            except Exception:
                return bk_biz_ids, []
            authorized_bizs = resource.space.get_bk_biz_ids_by_user(req.user)
            if -1 not in bk_biz_ids:
                authorized_bizs = list(set(bk_biz_ids) & set(authorized_bizs))
            unauthorized_bizs = list(set(bk_biz_ids or []) - set(authorized_bizs))
        return authorized_bizs, unauthorized_bizs


class QueryBuilder(ElasticsearchQueryBuilder):
    """
    Elasticsearch query_string 到 DSL 转换器
    """

    def _yield_nested_children(self, parent, children):
        yield from children


class AlertDimensionFormatter:
    """
    将告警维度格式化为人类可读字符串
    """

    @staticmethod
    def get_dimension_display_value(value):
        if isinstance(value, list):
            display_value = ",".join(value)
        else:
            display_value = value

        return display_value

    @classmethod
    def get_dimensions_str(cls, dimensions):
        if not dimensions:
            return ""

        dimension_list = cls.get_dimensions(dimensions)

        dimension_str_list = []
        for dimension in dimension_list:
            if dimension["key"] in ["bk_cloud_id"] and str(dimension["value"]) == "0":
                continue
            dimension_str_list.append("{display_key}({display_value})".format(**dimension))

        # 隐藏默认云区域
        return " - ".join(dimension_str_list)

    @classmethod
    def get_dimensions(cls, dimensions):
        """
        获取维度展示字段
        :param dimensions: 维度列表
        :rtype: list(dict)
        """
        if not dimensions:
            return []

        dimension_list = []

        for dimension in dimensions:
            if isinstance(dimension, AttrDict):
                dimension = dimension.to_dict()
            dimension_list.append(
                {
                    "key": dimension["key"],
                    "value": dimension["value"],
                    "display_key": dimension.get("display_key", dimension["key"]),
                    "display_value": cls.get_dimension_display_value(dimension.get("display_value", "")),
                }
            )

        return dimension_list

    @classmethod
    def get_target_key(cls, target_type, dimensions):
        if not dimensions:
            return ""

        dimension_dict = {d["key"]: d for d in dimensions}

        display_key = ""

        if target_type == EventTargetType.HOST and "ip" in dimension_dict:
            dimension_field = "ip"
            display_key = _("主机")
        elif target_type == EventTargetType.SERVICE and "bk_service_instance_id" in dimension_dict:
            dimension_field = "bk_service_instance_id"
        elif target_type == EventTargetType.TOPO and "bk_topo_node" in dimension_dict:
            dimension_field = "bk_topo_node"
        elif "target" in dimension_dict:
            dimension_field = "target"
        else:
            return ""

        return "{} {}".format(
            display_key or dimension_dict[dimension_field].get("display_key", ""),
            dimension_dict[dimension_field].get("display_value", ""),
        )
