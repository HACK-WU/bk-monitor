"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

from django.db.models import F, Max, Value
from django.db.models.functions import Concat
from django.utils.functional import cached_property

from apm_web.utils import get_interval_number
from bkm_space.utils import bk_biz_id_to_space_uid
from bkmonitor.models import (
    BCSCluster,
    BCSContainer,
    BCSIngress,
    BCSNode,
    BCSPod,
    BCSService,
    BCSWorkload,
)
from bkmonitor.utils.time_tools import hms_string
from core.drf_resource import api, resource
from monitor_web.k8s.core.filters import ResourceFilter, load_resource_filter


class FilterCollection:
    """
    过滤查询集合

    内部过滤条件是一个字典， 可以通过 add、remove来添加过滤条件
    """

    def __init__(self, meta: "K8sResourceMeta"):
        # filters={fileter_uid: resource_filter_obj}
        self.filters: dict[str, ResourceFilter] = dict()
        self.meta = meta
        self.query_set = meta.resource_class.objects.all().order_by("id")
        if meta.only_fields:
            self.query_set = self.query_set.only(*self.meta.only_fields)

    def add(self, filter_obj: ResourceFilter):
        """添加过滤条件"""
        self.filters[filter_obj.filter_uid] = filter_obj
        return self

    def remove(self, filter_obj: ResourceFilter):
        """移除过滤条件"""
        self.filters.pop(filter_obj.filter_uid, None)
        return self

    @cached_property
    def filter_queryset(self):
        """
        根据filters内容，返回过滤后的queryset
        """
        for filter_obj in self.filters.values():
            self.query_set = self.query_set.filter(**self.transform_filter_dict(filter_obj))
        return self.query_set

    def transform_filter_dict(self, filter_obj: ResourceFilter) -> dict:
        """用于ORM的查询条件"""
        resource_type = filter_obj.resource_type
        resource_meta = load_resource_meta(resource_type, self.meta.bk_biz_id, self.meta.bcs_cluster_id)
        if not resource_meta:
            return filter_obj.filter_dict

        orm_filter_dict = {}
        for key, value in filter_obj.filter_dict.items():
            # 解析查询条件，带双下划线表示特殊查询条件，不带表示等于
            parsed_token = key.split("__", 1)
            field_name = parsed_token[0]
            condition = parsed_token[1] if len(parsed_token) > 1 else None

            # 字段映射，prometheus数据字段 映射到 ORM中的 模型字段
            field_name = self.meta.column_mapping.get(field_name, field_name)

            # 防止SQL注入攻击
            if not isinstance(field_name, str) or not field_name.isidentifier():
                continue  # 跳过非法字段名

            # 重新组装特殊查询条件
            new_key = field_name if condition is None else f"{field_name}__{condition}"
            orm_filter_dict[new_key] = value

        return orm_filter_dict

    def filter_string(self, exclude=""):
        """
        根据filters内容，返回基于promql语法的过滤条件
        """
        where_string_list = []
        for filter_type, filter_obj in self.filters.items():
            if exclude and filter_type.startswith(exclude):
                continue

            if filter_type.startswith("workload") and len(filter_obj.value) > 1:
                # 多个 workload_id 查询支持
                filter_obj.value = filter_obj.value[:1]
                # workload_filters = [load_resource_filter("workload", value, fuzzy=filter_obj.fuzzy)
                #                     for value in filter_obj.value]
                # self.filters.pop(filter_type, None)
                # return list(self.make_multi_workload_filter_string(workload_filters))

            where_string_list.append(filter_obj.filter_string())
        return ",".join(where_string_list)

    def make_multi_workload_filter_string(self, workload_filters):
        for workload_filter in workload_filters:
            self.filters[workload_filter.filter_uid] = workload_filter
            yield self.filter_string()
            self.filters.pop(workload_filter.filter_uid, None)


class NetworkWithRelation:
    """网络场景，层级关联支持"""

    def label_join_service(self, filter_exclude=""):
        label_filters = FilterCollection(self)
        for filter_id, r_filter in self.filter.filters.items():
            if r_filter.resource_type == "ingress":
                return self.label_join_ingress(filter_exclude)
            if r_filter.resource_type != "pod":
                label_filters.add(r_filter)

        return (
            f"(count by (service, namespace, pod) "
            f"(pod_with_service_relation{{{label_filters.filter_string(exclude=filter_exclude)}}}) * 0 + 1)"
            f" * on (namespace, pod) group_left()"
        )

    def label_join_ingress(self, filter_exclude=""):
        return self.label_join(filter_exclude)

    def label_join_pod(self, filter_exclude=""):
        label_filters = FilterCollection(self)
        filter_service = False
        for filter_id, r_filter in self.filter.filters.items():
            if r_filter.resource_type == "ingress":
                return self.label_join(filter_exclude)
            if r_filter.resource_type == "service":
                filter_service = True
            if r_filter.resource_type != "pod":
                label_filters.add(r_filter)

        if filter_service:
            return self.label_join_service(filter_exclude)

        return ""

    def label_join(self, filter_exclude=""):
        label_filters = FilterCollection(self)
        for filter_id, r_filter in self.filter.filters.items():
            if r_filter.resource_type != "pod":
                label_filters.add(r_filter)

        return f"""(count by (bk_biz_id, bcs_cluster_id, namespace, ingress, service, pod)
            (ingress_with_service_relation{{{label_filters.filter_string(exclude=filter_exclude)}}}) * 0 + 1)
            * on (namespace, service) group_left(pod)
            (count by (service, namespace, pod) (pod_with_service_relation))
            * on (namespace, pod) group_left()"""

    def clean_metric_name(self, metric_name):
        if metric_name.startswith("nw_"):
            return metric_name[3:]
        return metric_name

    @property
    def pod_filters(self):
        pod_filters = FilterCollection(self)
        pod_filters.add(load_resource_filter("bcs_cluster_id", self.bcs_cluster_id))
        for filter_id, r_filter in self.filter.filters.items():
            if r_filter.resource_type in ["pod", "namespace"]:
                pod_filters.add(r_filter)
        return pod_filters


class K8sResourceMeta:
    """
    k8s资源基类
    """

    filter = None  # 用于指定过滤器
    resource_field = ""  # 用于指定资源字段
    resource_class = None  # 用于指定资源模型
    column_mapping = {}  # 用于指定字段映射
    only_fields = []  # 用于指定只查询的字段
    method = ""  # 用于指定聚合方法

    @property
    def resource_field_list(self):
        return [self.resource_field]

    def __init__(self, bk_biz_id, bcs_cluster_id):
        """
        初始化时还会实例化一个 FilterCollection()
        附带有 集群id和业务id信息
        """
        self.bk_biz_id = bk_biz_id
        self.bcs_cluster_id = bcs_cluster_id
        self.setup_filter()
        self.agg_interval = ""
        self.set_agg_method()

    @property
    def bcs_cluster_id_filter(self):
        for f_uid, f_obj in self.filter.filters.items():
            if f_uid.startswith("bcs_cluster_id"):
                filter_string = f"bcs_cluster_id={f_obj.filter_string().split('=')[1]}"
                return filter_string
        return ""

    def set_agg_interval(self, start_time, end_time):
        """设置聚合查询的间隔"""
        if self.method == "count":
            # count表示数量 不用时间聚合
            self.agg_interval = ""
            return

        if self.method == "sum":
            # 默认sum表示当前最新值 sum ( last_over_time )
            time_passed = get_interval_number(start_time, end_time, interval=60)
        else:
            # 其余方法表示时间范围内的聚合 sum( avg_over_time ), sum (max_over_time), sum(min_over_time)
            time_passed = end_time - start_time
        agg_interval = hms_string(time_passed, upper=True)
        self.agg_interval = agg_interval

    def set_agg_method(self, method="sum"):
        self.method = method
        if method == "count":
            # 重置interval
            self.set_agg_interval(0, 1)

    def setup_filter(self):
        """
        启动过滤查询条件
        默认添加 集群id 和业务id 两个过滤信息
        """
        if self.filter is not None:
            return
        self.filter = FilterCollection(self)
        # 默认范围，集群
        self.filter.add(load_resource_filter("bcs_cluster_id", self.bcs_cluster_id))

        """
        针对共享集群进行判断, 如果是共享集群，则需要获取集群下的所有命名空间
        cluster_info： { bcs_cluster_id: {"namespace_list": [], "cluster_type": BcsClusterType}}
        """
        space_uid = bk_biz_id_to_space_uid(self.bk_biz_id)
        cluster_info: dict[str, dict] = api.kubernetes.get_cluster_info_from_bcs_space(
            {"bk_biz_id": self.bk_biz_id, "space_uid": space_uid, "shard_only": True}
        )

        if self.bcs_cluster_id in cluster_info and not isinstance(
            self, K8sNodeMeta | K8sClusterMeta | K8sNamespaceMeta
        ):
            namespaces = cluster_info[self.bcs_cluster_id].get("namespace_list")
            self.filter.add(load_resource_filter("namespace", namespaces))
        # 不再添加业务id 过滤，有集群过滤即可。
        # else:
        #     self.filter.add(load_resource_filter("bk_biz_id", self.bk_biz_id))

        # 默认过滤 container_name!="POD"
        self.filter.add(load_resource_filter("container_exclude", ""))

    def get_from_meta(self):
        """
        数据获取来源

        从 meta 获取数据
        """
        return self.filter.filter_queryset

    def retry_get_from_meta(self):
        return []

    @classmethod
    def distinct(cls, queryset):
        # pod不需要去重，因为不会重名，workload，container 在不同ns下会重名，因此需要去重
        return queryset

    def get_from_promql(self, start_time, end_time, order_by="", page_size=20, method="sum"):
        """
        数据获取来源
        order_by: 排序字段,对应的就是指标名称，
        比如:
            container_cpu_usage_seconds_total，容器CPU累计使用时间的 Prometheus 指标
        """
        self.set_agg_method(method)
        interval = get_interval_number(start_time, end_time, interval=60)
        self.set_agg_interval(start_time, end_time)
        query_params = {
            "bk_biz_id": self.bk_biz_id,
            "query_configs": [
                {
                    "data_source_label": "prometheus",
                    "data_type_label": "time_series",
                    # promql: topk(page_size,...)
                    "promql": self.meta_prom_by_sort(order_by=order_by, page_size=page_size),
                    "interval": interval,
                    "alias": "result",
                }
            ],
            "expression": "",
            "alias": "result",
            "start_time": start_time,
            "end_time": end_time,
            "type": "range",
            "slimit": 10001,
            "down_sample_range": "",
        }
        series = resource.grafana.graph_unify_query(query_params)["series"]

        # latest_metric_value 最新时间点指标值
        # line latest_metric_value所在的时间序列
        # lines=[
        #   [latest_metric_value,[line]],
        #   ....
        # ]
        # 后续需要通过最新时间点指标值latest_metric_value对每个lines进行排序
        # 如果是升序排序，则lines.sort(key=lambda x:x[0], reverse=False)
        # 如果是降序排序，则lines.sort(key=lambda x:x[0], reverse=True)
        lines = []
        max_data_point = None
        # 找到所有有值数据点中的最大时间戳
        for line in series:
            if line["datapoints"]:
                for point in reversed(line["datapoints"]):
                    if point[0] is not None:
                        if max_data_point is None:
                            max_data_point = point[1]
                        else:
                            max_data_point = max(max_data_point, point[1])

        # 如果没有找到任何有值的数据点，max_data_point 仍为 None，后续处理需要考虑这种情况
        if max_data_point is None:
            # 如果所有数据点都是 None，使用最后一个数据点的时间戳作为 max_data_point
            for line in series:
                if line["datapoints"]:
                    max_data_point = line["datapoints"][-1][1]
                    break

        for line in series:
            last_data_points_value: float | int | None = line["datapoints"][-1][0]
            # 时间戳
            last_data_points = line["datapoints"][-1][1]
            if last_data_points == max_data_point:
                # 如果 len(series) <= page_size，则保留实际值为None的情况
                # 反之如果大于则对为 None 的情况进行排除
                if len(series) <= page_size:
                    # 如果数量较少，保留 None 值的情况，但使用特殊标记值进行排序区分
                    # 使用负无穷或极小值来区分 None 和真实 0 值，保证排序时 None 排在最后
                    sort_value = last_data_points_value if last_data_points_value is not None else float("-inf")
                    lines.append([sort_value, line])
                elif last_data_points_value is not None:
                    lines.append([last_data_points_value, line])
            else:
                # 时间戳不等于最新时间点：查找该 series 在最新时间点的值
                value_at_max_time = None
                if max_data_point is not None:
                    for point in reversed(line["datapoints"]):
                        if point[1] == max_data_point:
                            value_at_max_time = point[0]
                            break

                # 如果找到了最新时间点的值，使用该值；否则使用负无穷标记非最新且无值的情况
                if value_at_max_time is not None:
                    lines.append([value_at_max_time, line])
                else:
                    # 非最新时间点且没有值的情况，使用负无穷确保排序时排在最后
                    if len(series) <= page_size:
                        lines.append([float("-inf"), line])
                    # 如果数量超过 page_size，则直接跳过无值的情况（原有逻辑）
        if order_by:
            reverse = order_by.startswith("-")
            lines.sort(key=lambda x: x[0], reverse=reverse)
        obj_list = []
        resource_id_list = []
        for _, line in lines:
            try:
                resource_name = self.get_resource_name(line)
            except KeyError:
                # 如果没有维度字段，则当做无效数据
                continue

            if resource_name not in resource_id_list:
                resource_obj = self.resource_class()
                obj_list.append(self.clean_resource_obj(resource_obj, line))
                resource_id_list.append(resource_name)
        self.set_agg_method()
        return obj_list

    def get_resource_name(self, series):
        """
        通过series获取资源名称，资源名称包含在series["dimensions"]中
        例如：
        series = {
            "dimensions": {
                    "namespace": "aiops-default"
                }，
            ....
        }
        """
        meta_field_list = [series["dimensions"][field] for field in self.resource_field_list]
        return ":".join(meta_field_list)

    def clean_resource_obj(self, obj, series):
        """
        清洗资源对象并注入上下文信息

        参数:
            obj: 待清洗的资源对象，需包含__dict__属性用于批量更新字段
            series: 数据序列对象，包含dimensions维度字典和其他元数据

        返回值:
            经过维度字段映射转换并注入业务/集群ID的资源对象
        """
        # 维度字段映射转换：将dimensions中的原始字段名替换为目标字段名
        # 通过column_mapping配置的映射关系进行键值迁移
        dimensions = series["dimensions"]
        for origin, target in self.column_mapping.items():
            if origin in dimensions:
                dimensions[target] = dimensions.pop(origin, None)

        # 批量注入维度属性到资源对象，并设置上下文业务ID和集群ID
        # 这两个ID为资源归属定位的关键标识
        obj.__dict__.update(series["dimensions"])
        obj.bk_biz_id = self.bk_biz_id
        obj.bcs_cluster_id = self.bcs_cluster_id
        return obj

    @property
    def meta_prom(self):
        """默认资源查询promql"""
        return self.meta_prom_with_container_cpu_usage_seconds_total

    def meta_prom_by_sort(self, order_by="", page_size=20):
        order_field = order_by.strip("-")

        meta_prom_func = f"meta_prom_with_{order_field}"
        if hasattr(self, meta_prom_func):
            if order_by.startswith("-"):
                # desc
                return f"topk({page_size}, {getattr(self, meta_prom_func)})"
            else:
                return f"topk({page_size}, {getattr(self, meta_prom_func)} * -1) * -1"
        raise NotImplementedError(f"metric: {order_field} not supported")

    @property
    def meta_prom_with_node_boot_time_seconds(self):
        """获取节点启动时间的 Prometheus 原始指标
        Returns:
            str: 通过 tpl_prom_with_nothing 模板生成的 node_boot_time_seconds 指标
        """
        return self.tpl_prom_with_nothing("node_boot_time_seconds")

    @property
    def meta_prom_with_container_memory_working_set_bytes(self):
        """获取容器内存工作集的 Prometheus 原始指标
        Returns:
            str: 通过 tpl_prom_with_nothing 模板生成的 container_memory_working_set_bytes 指标
        """
        return self.tpl_prom_with_nothing("container_memory_working_set_bytes")

    @property
    def meta_prom_with_container_cpu_usage_seconds_total(self):
        """获取容器CPU累计使用时间的 Prometheus 指标（带速率计算）
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 container_cpu_usage_seconds_total 指标
        """
        return self.tpl_prom_with_rate("container_cpu_usage_seconds_total")

    @property
    def meta_prom_with_kube_pod_cpu_requests_ratio(self):
        """(未实现) 获取 Pod CPU 请求量比率的 Prometheus 指标
        Raises:
            NotImplementedError: 该指标尚未支持
        """
        raise NotImplementedError("metric: [kube_pod_cpu_requests_ratio] not supported")

    @property
    def meta_prom_with_kube_pod_cpu_limits_ratio(self):
        """(未实现) 获取 Pod CPU 限制量比率的 Prometheus 指标
        Raises:
            NotImplementedError: 该指标尚未支持
        """
        raise NotImplementedError("metric: [kube_pod_cpu_limits_ratio] not supported")

    @property
    def meta_prom_with_kube_pod_memory_requests_ratio(self):
        """(未实现) 获取 Pod 内存请求量比率的 Prometheus 指标
        Raises:
            NotImplementedError: 该指标尚未支持
        """
        raise NotImplementedError("metric: [kube_pod_memory_requests_ratio] not supported")

    @property
    def meta_prom_with_kube_pod_memory_limits_ratio(self):
        """(未实现) 获取 Pod 内存限制量比率的 Prometheus 指标
        Raises:
            NotImplementedError: 该指标尚未支持
        """
        raise NotImplementedError("metric: [kube_pod_memory_limits_ratio] not supported")

    @property
    def meta_prom_with_container_network_receive_bytes_total(self):
        """获取容器网络入流量指标（性能场景）
        维度层级: pod_name -> workload -> namespace -> cluster
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 container_network_receive_bytes_total 指标，
                 并排除 container_exclude 标签
        """
        # 网络入流量（性能场景）维度层级: pod_name -> workload -> namespace -> cluster
        return self.tpl_prom_with_rate("container_network_receive_bytes_total", exclude="container_exclude")

    @property
    def meta_prom_with_container_network_transmit_bytes_total(self):
        """获取容器网络出流量指标（性能场景）
        维度层级: pod_name -> workload -> namespace -> cluster
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 container_network_transmit_bytes_total 指标，
                 并排除 container_exclude 标签
        """
        # 网络出流量（性能场景）维度层级: pod_name -> workload -> namespace -> cluster
        return self.tpl_prom_with_rate("container_network_transmit_bytes_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_receive_bytes_total(self):
        """获取网络场景的容器入流量指标
        维度层级: pod_name -> service -> ingress -> namespace -> cluster
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_receive_bytes_total 指标，
                 并排除 container_exclude 标签
        """
        # 网络入流量（网络场景）维度层级: pod_name -> service -> ingress -> namespace -> cluster
        return self.tpl_prom_with_rate("nw_container_network_receive_bytes_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_transmit_bytes_total(self):
        """获取网络场景的容器出流量指标
        维度层级: pod_name -> service -> ingress -> namespace -> cluster
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_transmit_bytes_total 指标，
                 并排除 container_exclude 标签
        """
        # 网络出流量（网络场景）维度层级: pod_name -> service -> ingress -> namespace -> cluster
        return self.tpl_prom_with_rate("nw_container_network_transmit_bytes_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_receive_packets_total(self):
        """获取网络接收数据包总数指标
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_receive_packets_total 指标，
                 并排除 container_exclude 标签
        """
        return self.tpl_prom_with_rate("nw_container_network_receive_packets_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_transmit_packets_total(self):
        """获取网络发送数据包总数指标
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_transmit_packets_total 指标，
                 并排除 container_exclude 标签
        """
        return self.tpl_prom_with_rate("nw_container_network_transmit_packets_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_receive_errors_total(self):
        """获取网络接收错误总数指标
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_receive_errors_total 指标，
                 并排除 container_exclude 标签
        """
        return self.tpl_prom_with_rate("nw_container_network_receive_errors_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_transmit_errors_total(self):
        """获取网络发送错误总数指标
        Returns:
            str: 通过 tpl_prom_with_rate 模板生成的 nw_container_network_transmit_errors_total 指标，
                 并排除 container_exclude 标签
        """
        return self.tpl_prom_with_rate("nw_container_network_transmit_errors_total", exclude="container_exclude")

    @property
    def meta_prom_with_nw_container_network_receive_errors_ratio(self):
        """计算网络接收错误率指标
        Returns:
            str: 接收错误总数与接收数据包总数的比值表达式
        """
        return f"""{self.meta_prom_with_nw_container_network_receive_errors_total}
        /
        {self.meta_prom_with_nw_container_network_receive_packets_total}"""

    @property
    def meta_prom_with_nw_container_network_transmit_errors_ratio(self):
        """计算网络发送错误率指标
        Returns:
            str: 发送错误总数与发送数据包总数的比值表达式
        """
        return f"""{self.meta_prom_with_nw_container_network_transmit_errors_total}
        /
        {self.meta_prom_with_nw_container_network_transmit_packets_total}"""

    @property
    def meta_prom_with_container_cpu_cfs_throttled_ratio(self):
        """(未实现) 获取容器CPU被限制的比率指标
        Raises:
            NotImplementedError: 该指标尚未支持
        """
        raise NotImplementedError("metric: [container_cpu_cfs_throttled_ratio] not supported")

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        """（模板方法）生成带速率计算的 PromQL 表达式
        Args:
            metric_name (str): Prometheus 指标名称
            exclude (str): 需要排除的标签名称
        Raises:
            NotImplementedError: 需要子类实现具体逻辑
        """
        raise NotImplementedError(f"metric: [{metric_name}] not supported")

    def tpl_prom_with_nothing(self, metric_name, exclude=""):
        """（模板方法）生成原始 Prometheus 指标表达式
        Args:
            metric_name (str): Prometheus 指标名称
            exclude (str): 需要排除的标签名称
        Raises:
            NotImplementedError: 需要子类实现具体逻辑
        """
        raise NotImplementedError(f"metric: [{metric_name}] not supported")

    @property
    def agg_method(self):
        # 如果是sum则返回last，获取最新值
        return "last" if self.method == "sum" else self.method

    def add_filter(self, filter_obj):
        self.filter.add(filter_obj)


class K8sPodMeta(K8sResourceMeta, NetworkWithRelation):
    resource_field = "pod_name"
    resource_class = BCSPod
    column_mapping = {"workload_kind": "workload_type", "pod_name": "name"}
    only_fields = ["name", "namespace", "workload_type", "workload_name", "bk_biz_id", "bcs_cluster_id"]

    def nw_tpl_prom_with_rate(self, metric_name, exclude=""):
        metric_name = self.clean_metric_name(metric_name)
        if self.agg_interval:
            return f"""label_replace(sum by (namespace, pod) ({self.label_join_pod(exclude)}
            sum by (namespace, pod)
            ({self.agg_method}_over_time(rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])[{self.agg_interval}:]))),
            "pod_name", "$1", "pod", "(.*)")"""

        return f"""label_replace({self.agg_method} by (namespace, pod) ({self.label_join_pod(exclude)}
                    sum by (namespace, pod)
                    (rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m]))),
            "pod_name", "$1", "pod", "(.*)")"""

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        if metric_name.startswith("nw_"):
            # 网络场景下的pod数据，需要关联service 和 ingress
            # ingress_with_service_relation 指标忽略pod相关过滤， 因为该指标对应的pod为采集器所属pod，没意义。
            return self.nw_tpl_prom_with_rate(metric_name, exclude="pod")

        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, pod_name) "
                f"({self.agg_method}_over_time(rate("
                f"{metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m])[{self.agg_interval}:]))"
            )
        return (
            f"{self.method} by (workload_kind, workload_name, namespace, pod_name) "
            f"(rate({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m]))"
        )

    def tpl_prom_with_nothing(self, metric_name, exclude=""):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, pod_name) "
                f"({self.agg_method}_over_time("
                f"{metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[{self.agg_interval}:]))"
            )

        return (
            f"{self.method} by (workload_kind, workload_name, namespace, pod_name) "
            f"({metric_name}{{{self.filter.filter_string(exclude=exclude)}}})"
        )

    @property
    def meta_prom_with_container_cpu_cfs_throttled_ratio(self):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, pod_name) "
                f"({self.agg_method}_over_time((increase("
                f"container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
                f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m]))[{self.agg_interval}:]))"
            )

        return (
            f"{self.method} by (workload_kind, workload_name, namespace, pod_name) "
            f"((increase(container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
            f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m])))"
        )

    @property
    def meta_prom_with_kube_pod_cpu_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_cpu_cores
        )
        return promql

    @property
    def meta_prom_with_kube_pod_cpu_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace,pod_name)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_cpu_system_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_limits_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_cpu_cores(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace,pod_name)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_cpu_system_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_requests_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        return promql

    @property
    def meta_prom_with_kube_pod_memory_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_memory_bytes
        )
        return promql

    @property
    def meta_prom_with_kube_pod_memory_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace,pod_name)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_limits_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_memory_bytes(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace,pod_name)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_requests_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        return promql


class K8sClusterMeta(K8sResourceMeta):
    resource_field = "bcs_cluster_id"
    resource_class = BCSCluster
    column_mapping = {"cluster": "name"}
    only_fields = ["name", "bk_biz_id", "bcs_cluster_id"]

    @property
    def meta_prom_with_node_cpu_seconds_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['mode!="idle"'])
        return self.tpl_prom_with_rate("node_cpu_seconds_total", filter_string)

    @property
    def meta_prom_with_node_cpu_capacity_ratio(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['resource="cpu"'])
        if self.agg_method:
            return (
                "sum by (bcs_cluster_id)(sum by (bcs_cluster_id,pod) "
                f"({self.agg_method}_over_time(kube_pod_container_resource_requests{{{filter_string}}}[1m:]))"
                " / "
                f"on (pod) group_left() count (count by (pod)"
                f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
                " / "
                f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
            )
        return (
            "sum by (bcs_cluster_id)(sum by (bcs_cluster_id,pod) "
            f"(kube_pod_container_resource_requests{{{filter_string}}})"
            " / "
            f"on (pod) group_left() count (count by (pod)"
            f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
            " / "
            f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_cpu_usage_ratio(self):
        """
        指标聚合方法写死，使用 avg
        ```PromQL
        (
            1 - avg by(bcs_cluster) (
            rate(node_cpu_seconds_total{
                mode="idle",
                bk_biz_id="2",
                bcs_cluster_id="BCS-K8S-00000"
            }[1m]))
        ) * 100
        ```
        """
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['mode="idle"'])
        # 写死汇聚方法
        self.set_agg_method("avg")
        self.agg_interval = ""
        return f"(1 - ({self.tpl_prom_with_rate('node_cpu_seconds_total', filter_string=filter_string)})) * 100"

    @property
    def meta_prom_with_node_memory_working_set_bytes(self):
        """sum by (bcs_cluster_id)(node_memory_MemTotal_bytes) - sum by (bcs_cluster_id) (node_memory_MemAvailable_bytes)"""
        filter_string = self.filter.filter_string()
        return (
            f"{self.tpl_prom_with_nothing('node_memory_MemTotal_bytes', filter_string=filter_string)}"
            f"-"
            f"{self.tpl_prom_with_nothing('node_memory_MemAvailable_bytes', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_memory_capacity_ratio(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['resource="memory"'])
        if self.agg_method:
            return (
                "sum by (bcs_cluster_id)(sum by (bcs_cluster_id,pod) "
                f"({self.agg_method}_over_time(kube_pod_container_resource_requests{{{filter_string}}}[1m:]))"
                " / "
                f"on (pod) group_left() count (count by (pod)"
                f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
                "/"
                f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
            )
        return (
            "sum by (bcs_cluster_id)(sum by (bcs_cluster_id,pod) "
            f"(kube_pod_container_resource_requests{{{filter_string}}})"
            " / "
            f"on (pod) group_left() count (count by (pod)"
            f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
            "/"
            f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_memory_usage_ratio(self):
        """(1 - (sum by (bcs_cluster_id)(node_memory_MemAvailable_bytes) / sum by (bcs_cluster_id)(node_memory_MemTotal_bytes)))"""
        filter_string = self.filter.filter_string()
        return (
            f"(1 - ({self.tpl_prom_with_nothing('node_memory_MemAvailable_bytes', filter_string=filter_string)}"
            f"/"
            f"{self.tpl_prom_with_nothing('node_memory_MemTotal_bytes', filter_string=filter_string)}))"
        )

    @property
    def meta_prom_with_master_node_count(self):
        """count by (bcs_cluster_id)(sum by (bcs_cluster_id)(kube_node_role{role=~"master|control-plane"}))"""
        filter_string = self.filter.filter_string()
        filter_string += ","
        filter_string += 'role=~"master|control-plane"'
        return f"""count by (bcs_cluster_id)(sum by (bcs_cluster_id)(kube_node_role{{{filter_string}}}))"""

    @property
    def meta_prom_with_worker_node_count(self):
        """count by(bcs_cluster_id)(kube_node_labels) - count(sum by (bcs_cluster_id, node)(kube_node_role{role=~"master|control-plane"}))"""
        filter_string = self.filter.filter_string()
        return f"""(count by(bcs_cluster_id)(kube_node_labels{{{filter_string}}})
         -
         count(sum by (node)(kube_node_role{{{filter_string}, role=~"master|control-plane"}})))"""

    @property
    def meta_prom_with_node_pod_usage(self):
        """sum by (bcs_cluster_id)(kubelet_running_pods) / sum by (bcs_cluster_id)(kube_node_status_capacity_pods)"""
        return (
            f"{self.tpl_prom_with_nothing('kubelet_running_pods')}"
            f"/"
            f"{self.tpl_prom_with_nothing('kube_node_status_capacity_pods')}"
        )

    @property
    def meta_prom_with_node_network_receive_bytes_total(self):
        """sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*"}[1m])) by (bcs_cluster_id)"""
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_receive_bytes_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_transmit_bytes_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_transmit_bytes_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_receive_packets_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_receive_packets_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_transmit_packets_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_transmit_packets_total", filter_string=filter_string)

    def tpl_prom_with_nothing(self, metric_name, exclude="", filter_string=""):
        if not filter_string:
            filter_string = self.filter.filter_string(exclude=exclude)
        if self.agg_interval:
            return (
                f"sum by (bcs_cluster_id) "
                f"({self.agg_method}_over_time("
                f"{metric_name}{{{filter_string}}}[{self.agg_interval}:]))"
            )
        return f"{self.method} by (bcs_cluster_id) ({metric_name}{{{filter_string}}})"

    def tpl_prom_with_rate(self, metric_name, exclude="", filter_string=""):
        if not filter_string:
            filter_string = self.filter.filter_string(exclude=exclude)
        if self.agg_interval:
            return (
                f"sum by (bcs_cluster_id) "
                f"({self.agg_method}_over_time(rate("
                f"{metric_name}{{{filter_string}}}[1m])[{self.agg_interval}:]))"
            )
        return f"{self.method} by (bcs_cluster_id) (rate({metric_name}{{{filter_string}}}[1m]))"


class K8sNodeMeta(K8sResourceMeta):
    resource_field = "node"
    resource_class = BCSNode
    column_mapping = {"node": "name"}
    only_fields = ["name", "bk_biz_id", "bcs_cluster_id"]

    @property
    def meta_prom_with_node_cpu_seconds_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['mode!="idle"'])
        return self.tpl_prom_with_rate("node_cpu_seconds_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_cpu_capacity_ratio(self):
        # 过滤被标记为已驱逐的Pod
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['resource="cpu"'])
        if self.agg_method:
            return (
                "sum by (node)(sum by (node,pod) "
                f"({self.agg_method}_over_time(kube_pod_container_resource_requests{{{filter_string}}}[1m:]))"
                " / "
                f"on (pod) group_left() count (count by (pod)"
                f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
                " / "
                f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
            )
        return (
            "sum by (node)(sum by (node,pod) "
            f"(kube_pod_container_resource_requests{{{filter_string}}})"
            " / "
            f"on (pod) group_left() count (count by (pod)"
            f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
            " / "
            f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_cpu_usage_ratio(self):
        """
        指标聚合方法写死，使用 avg
        ```PromQL
        (
            1 - avg by(node) (
                rate(node_cpu_seconds_total{
                    mode="idle",
                    bk_biz_id="2",
                    bcs_cluster_id="BCS-K8S-00000",
                    node=~"^(node-127-0-0-1)$"
                }[1m]))
        ) * 100
        ```
        """
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['mode="idle"'])
        # 写死汇聚方法
        self.set_agg_method("avg")
        self.agg_interval = ""
        return f"(1 - ({self.tpl_prom_with_rate('node_cpu_seconds_total', filter_string=filter_string)})) * 100"

    @property
    def meta_prom_with_node_memory_working_set_bytes(self):
        """sum by (node)(node_memory_MemTotal_bytes) - sum by (node) (node_memory_MemAvailable_bytes)"""
        filter_string = self.filter.filter_string()
        return (
            f"{self.tpl_prom_with_nothing('node_memory_MemTotal_bytes', filter_string=filter_string)}"
            f"-"
            f"{self.tpl_prom_with_nothing('node_memory_MemAvailable_bytes', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_memory_capacity_ratio(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['resource="memory"'])
        if self.agg_method:
            return (
                "sum by (node)(sum by (node,pod) "
                f"({self.agg_method}_over_time(kube_pod_container_resource_requests{{{filter_string}}}[1m:]))"
                " / "
                f"on (pod) group_left() count (count by (pod)"
                f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
                "/"
                f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
            )
        return (
            "sum by (node)(sum by (node,pod) "
            f"(kube_pod_container_resource_requests{{{filter_string}}})"
            " / "
            f"on (pod) group_left() count (count by (pod)"
            f'(kube_pod_status_phase{{{self.bcs_cluster_id_filter},phase!="Evicted"}})) by (pod))'
            "/"
            f"{self.tpl_prom_with_nothing('kube_node_status_allocatable', filter_string=filter_string)}"
        )

    @property
    def meta_prom_with_node_memory_usage_ratio(self):
        """(1 - (sum by (node)(node_memory_MemAvailable_bytes) / sum by (node)(node_memory_MemTotal_bytes)))"""
        filter_string = self.filter.filter_string()
        return (
            f"(1 - ({self.tpl_prom_with_nothing('node_memory_MemAvailable_bytes', filter_string=filter_string)}"
            f"/"
            f"{self.tpl_prom_with_nothing('node_memory_MemTotal_bytes', filter_string=filter_string)}))"
        )

    @property
    def meta_prom_with_node_pod_usage(self):
        """sum by (node)(kubelet_running_pods) / sum by (node)(kube_node_status_capacity_pods)"""
        return (
            f"{self.tpl_prom_with_nothing('kubelet_running_pods')}"
            f"/"
            f"{self.tpl_prom_with_nothing('kube_node_status_capacity_pods')}"
        )

    @property
    def meta_prom_with_node_network_receive_bytes_total(self):
        """sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*"}[1m])) by (node)"""
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_receive_bytes_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_transmit_bytes_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_transmit_bytes_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_receive_packets_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_receive_packets_total", filter_string=filter_string)

    @property
    def meta_prom_with_node_network_transmit_packets_total(self):
        filter_string = self.filter.filter_string()
        filter_string = ",".join([filter_string] + ['device!~"lo|veth.*"'])
        return self.tpl_prom_with_rate("node_network_transmit_packets_total", filter_string=filter_string)

    def tpl_prom_with_nothing(self, metric_name, exclude="", filter_string=""):
        if not filter_string:
            filter_string = self.filter.filter_string(exclude=exclude)
        if self.agg_interval:
            return (
                f"sum by (node) ({self.agg_method}_over_time({metric_name}{{{filter_string}}}[{self.agg_interval}:]))"
            )
        return f"{self.method} by (node) ({metric_name}{{{filter_string}}})"

    def tpl_prom_with_rate(self, metric_name, exclude="", filter_string=""):
        if not filter_string:
            filter_string = self.filter.filter_string(exclude=exclude)
        if self.agg_interval:
            return (
                f"sum by (node) "
                f"({self.agg_method}_over_time(rate("
                f"{metric_name}{{{filter_string}}}[1m])[{self.agg_interval}:]))"
            )
        return f"{self.method} by (node) (rate({metric_name}{{{filter_string}}}[1m]))"


class NameSpaceQuerySet(list):
    def count(self):
        return len(self)

    def order_by(self, *field_names):
        # 如果没有提供字段名，则不进行排序
        if not field_names:
            return self

        def get_sort_key(item):
            key = []
            for field in field_names:
                # 检查是否为降序字段
                if field.startswith("-"):
                    field_name = field[1:]
                    # 使用负值来反转排序
                    key.append(-item.get(field_name, 0))
                else:
                    key.append(item.get(field, 0))
            return tuple(key)

        # 使用 sorted 函数进行排序
        sorted_data = sorted(self, key=get_sort_key)
        return NameSpaceQuerySet(sorted_data)


class NameSpace(dict):
    columns = ["bk_biz_id", "bcs_cluster_id", "namespace"]

    @property
    def __dict__(self):
        return self

    @property
    def objects(self):
        return BCSPod.objects.values(*self.columns)

    def __getattr__(self, item):
        if item in self:
            return self[item]
        return None

    def __setattr__(self, item, value):
        self[item] = value

    def __call__(self, **kwargs):
        ns = NameSpace.fromkeys(NameSpace.columns, None)
        ns.update(kwargs)
        return ns

    def to_meta_dict(self):
        return self


class K8sNamespaceMeta(K8sResourceMeta, NetworkWithRelation):
    """
    Namespace没有单独的表存储，这里使用Workload表中的namespace字段进行查询
    """

    resource_field = "namespace"
    resource_class = NameSpace.fromkeys(NameSpace.columns, None)
    column_mapping = {}

    def get_from_meta(self):
        return self.distinct(self.filter.filter_queryset)

    def retry_get_from_meta(self):
        # 根据filter 类型进行重新查询
        for filter_id, r_filter in self.filter.filters.items():
            if r_filter.resource_type not in ["service", "ingress", "pod"]:
                continue
            else:
                filter_field = r_filter.resource_type
                break
        else:
            return []

        model = {
            "ingress": BCSIngress,
            "service": BCSService,
            "pod": BCSPod,
        }.get(filter_field)
        self.filter.query_set = model.objects.values(*NameSpace.columns)
        self.column_mapping = {"pod_name": "name", "service": "name", "ingress": "name"}
        return self.get_from_meta()

    def nw_tpl_prom_with_rate(self, metric_name, exclude="container_exclude"):
        metric_name = self.clean_metric_name(metric_name)
        if self.agg_interval:
            return f"""sum by (namespace) ({self.label_join_pod(exclude)}
            sum by (namespace, pod)
            ({self.agg_method}_over_time(
            rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])[{self.agg_interval}:])))"""

        return f"""{self.agg_method} by (namespace) ({self.label_join_pod(exclude)}
                    sum by (namespace, pod)
                    (rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])))"""

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        """
        生成基于速率（rate）的PromQL查询模板

        Args:
            metric_name (str): 指标名称，若以"nw_"开头会自动去除前缀
            exclude (str, optional): 需要排除的过滤条件

        Returns:
            str: 基于namespace维度的PromQL查询语句，包含指定指标的每秒增长率计算，
                根据agg_interval判断是否添加时间窗口聚合
        """
        # 处理网络指标前缀规则
        if metric_name.startswith("nw_"):
            # namespace 层级统计流量， 需要制定container=POD, 因此不能使用container_exclude排除掉POD的container
            return self.nw_tpl_prom_with_rate(metric_name, exclude="container_exclude")

        # 计算出某指标的每秒增长率 ->
        # 计算历史时间段的增长率，并做基于时间窗口的聚合操作 ->
        # 然后再做基于namespace维度的sum聚合操作
        if self.agg_interval:
            return (
                f"sum by (namespace) ({self.agg_method}_over_time(rate("
                f"{metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m])[{self.agg_interval}:]))"
            )
        # 计算出某指标的每秒增长率 ->
        # 基于namespace维度进行聚合
        return f"{self.method} by (namespace) (rate({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m]))"

    def tpl_prom_with_nothing(self, metric_name, exclude=""):
        """
        生成直接指标查询的PromQL模板（非速率计算）

        Args:
            metric_name (str): 需要查询的指标名称
            exclude (str, optional): 需要排除的过滤条件

        Returns:
            str: 基于namespace维度的PromQL查询语句，
                根据agg_interval判断是否添加时间窗口聚合
        """
        # 当存在聚合时间窗口时，添加_over_time聚合逻辑，然后做基于namespace维度的sum聚合操作
        if self.agg_interval:
            return (
                f"sum by (namespace) ({self.agg_method}_over_time("
                f"{metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[{self.agg_interval}:]))"
            )
        # 基础指标查询格式
        return f"{self.method} by (namespace) ({metric_name}{{{self.filter.filter_string(exclude=exclude)}}})"

    @property
    def meta_prom_with_container_cpu_cfs_throttled_ratio(self):
        """
        生成CPU限流占比的PromQL查询语句

        Returns:
            str: 计算容器CPU限流占比的PromQL公式，
                根据agg_interval判断是否添加时间窗口聚合

        Notes:
            - container_cpu_cfs_throttled_periods_total: 容器CPU CFS限流周期总数
            - container_cpu_cfs_periods_total: 容器CPU CFS周期总数
        """
        # 当存在聚合时间窗口时，计算历史时间段的限流占比
        if self.agg_interval:
            # example(忽略filter_string):
            #   sum by (namespace) (avg_over_time((increase(container_cpu_cfs_throttled_periods_total[1m])
            #   / increase(container_cpu_cfs_periods_total[1m]))[5m:]))
            #
            # 含义：
            # - 计算过去5分钟内每个namespace的container_cpu_cfs_throttled_periods_total和container_cpu_cfs_periods_total的增量
            # - 对每个namespace的增量进行平均值计算(avg_over_time 除以时间窗口长度)
            # - 对所有namespace的平均值进行求和

            return (
                f"sum by (namespace) "
                f"({self.agg_method}_over_time((increase("
                f"container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
                f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m]))[{self.agg_interval}:]))"
            )

        # 基础计算公式：最近1分钟的限流占比
        # example(忽略filter_string):
        #   sum by (namespace) ((increase(container_cpu_cfs_throttled_periods_total[1m]) / increase(
        #   container_cpu_cfs_periods_total[1m])))

        return (
            f"{self.method} by (namespace) "
            f"((increase(container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
            f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m])))"
        )

    @classmethod
    def distinct(cls, objs):
        unique_ns_query_set = set()
        for ns in objs:
            row = tuple(ns[field] for field in NameSpace.columns)
            unique_ns_query_set.add(row)
        # 默认按照namespace(第三个字段)排序
        return NameSpaceQuerySet(
            [NameSpace(zip(NameSpace.columns, ns)) for ns in sorted(unique_ns_query_set, key=lambda x: x[2])]
        )


class K8sIngressMeta(K8sResourceMeta, NetworkWithRelation):
    resource_field = "ingress"
    resource_class = BCSIngress
    column_mapping = {"ingress": "name"}

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        metric_name = self.clean_metric_name(metric_name)
        if self.agg_interval:
            return f"""sum by (ingress, namespace) ({self.label_join_ingress(exclude)}
            sum by (namespace, pod)
            ({self.agg_method}_over_time(
            rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])[{self.agg_interval}:])))"""

        return f"""{self.agg_method} by (ingress, namespace) ({self.label_join_ingress(exclude)}
                    sum by (namespace, pod)
                    (rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])))"""


class K8sServiceMeta(K8sResourceMeta, NetworkWithRelation):
    resource_field = "service"
    resource_class = BCSService
    column_mapping = {"service": "name"}

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        metric_name = self.clean_metric_name(metric_name)
        if self.agg_interval:
            return f"""sum by (namespace, service) ({self.label_join_service(exclude)}
            sum by (namespace, pod)
            ({self.agg_method}_over_time(
            rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])[{self.agg_interval}:])))"""

        return f"""{self.agg_method} by (namespace, service) ({self.label_join_service(exclude)}
                    sum by (namespace, pod)
                    (rate({metric_name}{{{self.pod_filters.filter_string()}}}[1m])))"""


class K8sWorkloadMeta(K8sResourceMeta):
    # todo 支持多workload
    resource_field = "workload_name"
    resource_class = BCSWorkload
    column_mapping = {"workload_kind": "type", "workload_name": "name"}
    only_fields = ["type", "name", "namespace", "bk_biz_id", "bcs_cluster_id"]

    @property
    def resource_field_list(self):
        return ["workload_kind", self.resource_field]

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace) ({self.agg_method}_over_time(rate("
                f"{metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m])[{self.agg_interval}:]))"
            )
        return (
            f"{self.method} by (workload_kind, workload_name, namespace) "
            f"(rate({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m]))"
        )

    def tpl_prom_with_nothing(self, metric_name, exclude=""):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace) ({self.agg_method}_over_time"
                f"({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[{self.agg_interval}:]))"
            )
        return (
            f"{self.method} by (workload_kind, workload_name, namespace) "
            f"({metric_name}{{{self.filter.filter_string(exclude=exclude)}}})"
        )

    @property
    def meta_prom_with_container_cpu_cfs_throttled_ratio(self):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace) "
                f"({self.agg_method}_over_time((increase("
                f"container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
                f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m]))[{self.agg_interval}:]))"
            )

        return (
            f"{self.method} by (workload_kind, workload_name, namespace) "
            f"((increase(container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
            f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m])))"
        )

    @property
    def meta_prom_with_kube_pod_cpu_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_cpu_cores
        )
        return promql

    @property
    def meta_prom_with_kube_pod_cpu_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace)
    ((count by (workload_kind, workload_name, namespace, pod_name) (
        container_cpu_usage_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_limits_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_cpu_cores(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace)
    ((count by (workload_kind, workload_name, namespace, pod_name) (
        container_cpu_usage_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_requests_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        return promql

    @property
    def meta_prom_with_kube_pod_memory_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_memory_bytes
        )
        return promql

    @property
    def meta_prom_with_kube_pod_memory_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_limits_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_memory_bytes(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace)
    ((count by (workload_kind, workload_name, pod_name, namespace) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace) (
      kube_pod_container_resource_requests_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        return promql

    @classmethod
    def distinct(cls, queryset):
        query_set = (
            queryset.values("type", "name")
            .order_by("name")
            .annotate(
                distinct_name=Max("id"),
                workload=Concat(F("type"), Value(":"), F("name")),
            )
            .values("workload")
        )
        return query_set


class K8sContainerMeta(K8sResourceMeta):
    resource_field = "container_name"
    resource_class = BCSContainer
    column_mapping = {"workload_kind": "workload_type", "container_name": "name"}
    only_fields = ["name", "namespace", "pod_name", "workload_type", "workload_name", "bk_biz_id", "bcs_cluster_id"]

    @property
    def resource_field_list(self):
        return ["pod_name", self.resource_field]

    @classmethod
    def distinct(cls, queryset):
        query_set = (
            queryset.values("name")
            .order_by("name")
            .annotate(distinct_name=Max("id"))
            .annotate(container=F("name"))
            .values("container")
        )
        return query_set

    def tpl_prom_with_rate(self, metric_name, exclude=""):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, container_name, pod_name) "
                f"({self.agg_method}_over_time"
                f"(rate({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m])[{self.agg_interval}:]))"
            )
        return (
            f"{self.method} by (workload_kind, workload_name, namespace, container_name, pod_name) "
            f"(rate({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[1m]))"
        )

    def tpl_prom_with_nothing(self, metric_name, exclude=""):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, container_name, pod_name) "
                f"({self.agg_method}_over_time"
                f" ({metric_name}{{{self.filter.filter_string(exclude=exclude)}}}[{self.agg_interval}:]))"
            )
        """按内存排序的资源查询promql"""
        return (
            f"{self.method} by (workload_kind, workload_name, namespace, container_name, pod_name)"
            f" ({metric_name}{{{self.filter.filter_string(exclude=exclude)}}})"
        )

    @property
    def meta_prom_with_container_cpu_cfs_throttled_ratio(self):
        if self.agg_interval:
            return (
                f"sum by (workload_kind, workload_name, namespace, pod_name, container_name) "
                f"({self.agg_method}_over_time((increase("
                f"container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
                f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m]))[{self.agg_interval}:]))"
            )

        return (
            f"{self.method} by (workload_kind, workload_name, namespace, pod_name, container_name) "
            f"((increase(container_cpu_cfs_throttled_periods_total{{{self.filter.filter_string()}}}[1m]) / increase("
            f"container_cpu_cfs_periods_total{{{self.filter.filter_string()}}}[1m])))"
        )

    @property
    def meta_prom_with_kube_pod_cpu_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_cpu_cores
        )
        return promql

    @property
    def meta_prom_with_kube_pod_cpu_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_cpu_usage_seconds_total
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace, pod_name, container_name)
    ((count by (workload_kind, workload_name, pod_name, namespace, container_name) (
        container_cpu_usage_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace, container_name)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace, container_name) (
      kube_pod_container_resource_limits_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_cpu_cores(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace, pod_name, container_name)
    ((count by (workload_kind, workload_name, pod_name, namespace, container_name) (
        container_cpu_usage_seconds_total{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace, container_name)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace, container_name) (
      kube_pod_container_resource_requests_cpu_cores{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        return promql

    @property
    def meta_prom_with_kube_pod_memory_requests_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + self.meta_prom_with_kube_pod_container_resource_requests_memory_bytes
        )
        return promql

    @property
    def meta_prom_with_kube_pod_memory_limits_ratio(self):
        promql = (
            self.meta_prom_with_container_memory_working_set_bytes
            + "/ "
            + f"""(sum by (workload_kind, workload_name, namespace, pod_name, container_name)
    ((count by (workload_kind, workload_name, pod_name, namespace, container_name) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace, container_name)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace, container_name) (
      kube_pod_container_resource_limits_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""
        )
        return promql

    @property
    def meta_prom_with_kube_pod_container_resource_requests_memory_bytes(self):
        promql = f"""(sum by (workload_kind, workload_name, namespace, pod_name, container_name)
    ((count by (workload_kind, workload_name, pod_name, namespace, container_name) (
        container_memory_working_set_bytes{{{self.filter.filter_string()}}}
    ) * 0 + 1) *
    on(pod_name, namespace, container_name)
    group_right(workload_kind, workload_name)
    sum by (pod_name, namespace, container_name) (
      kube_pod_container_resource_requests_memory_bytes{{{self.filter.filter_string(exclude="workload")}}}
    )))"""

        return promql


def load_resource_meta(resource_type: str, bk_biz_id: int, bcs_cluster_id: str) -> K8sResourceMeta | None:
    resource_meta_map = {
        "node": K8sNodeMeta,
        "container": K8sContainerMeta,
        "container_name": K8sContainerMeta,
        "pod": K8sPodMeta,
        "pod_name": K8sPodMeta,
        "workload": K8sWorkloadMeta,
        "namespace": K8sNamespaceMeta,
        "ingress": K8sIngressMeta,
        "service": K8sServiceMeta,
        "cluster": K8sClusterMeta,
    }
    if resource_type not in resource_meta_map:
        return None
    meta_class = resource_meta_map[resource_type]
    return meta_class(bk_biz_id, bcs_cluster_id)
