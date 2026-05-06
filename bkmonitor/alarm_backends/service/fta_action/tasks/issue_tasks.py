"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import logging
import re
import time
from typing import Any

from alarm_backends.core.cache.cmdb import BusinessManager, SetManager
from alarm_backends.service.scheduler.app import app
from bkmonitor.documents.alert import AlertDocument
from bkmonitor.documents.base import BulkActionType
from bkmonitor.documents.issue import IssueDocument
from bkmonitor.utils.common_utils import safe_int
from bkmonitor.utils.tenant import bk_biz_id_to_bk_tenant_id
from constants.issue import IssueStatus

logger = logging.getLogger("fta_action.issue")

ORPHAN_ISSUE_THRESHOLD_SECONDS = 300
ISSUE_SCAN_PAGE_SIZE = 500
ALERT_SCAN_PAGE_SIZE = 500


PROGRESS_LOG_INTERVAL = 100


@app.task(ignore_result=True, queue="celery_action_cron")
def sync_issue_alert_stats():
    """
    定期对活跃 Issue 执行：
      1) 漏关联补偿（回填 AlertDocument.issue_id）
      2) 统计 alert_count / last_alert_time
      3) 重算 impact_scope
      4) 检测 orphan issue 并触发监控告警
    """
    start_ts = time.time()
    processed = 0
    failed = 0
    total = 0

    for hit, total in _iter_issue_hits_with_total():
        issue = IssueDocument(**hit.to_dict())
        processed += 1

        if processed == 1:
            logger.info("[issue] sync_issue_alert_stats: start, active_issues=%d", total)

        logger.debug(
            "[issue] sync_issue_alert_stats: processing [%d/%d] strategy(%s) issue(%s)",
            processed,
            total,
            issue.strategy_id,
            issue.id,
        )
        if processed % PROGRESS_LOG_INTERVAL == 0:
            logger.info(
                "[issue] sync_issue_alert_stats: progress [%d/%d], failed=%d, elapsed=%.1fs",
                processed,
                total,
                failed,
                time.time() - start_ts,
            )

        try:
            _process_single_issue(issue)
        except Exception:
            failed += 1
            logger.exception(
                "[issue] sync_issue_alert_stats: failed, strategy(%s) issue(%s)",
                issue.strategy_id,
                issue.id,
            )

    elapsed = time.time() - start_ts
    logger.info(
        "[issue] sync_issue_alert_stats: done, processed=%d/%d, failed=%d, elapsed=%.1fs",
        processed,
        total,
        failed,
        elapsed,
    )


def _process_single_issue(issue: IssueDocument):
    _backfill_unlinked_alerts(issue)

    alert_search = AlertDocument.search(all_indices=True).filter("term", issue_id=issue.id).params(size=0)
    alert_search.aggs.metric("alert_count", "value_count", field="id")
    alert_search.aggs.metric("max_begin_time", "max", field="begin_time")

    result = alert_search.execute()
    alert_count = int(result.aggregations.alert_count.value or 0)
    # ES date aggregations always return milliseconds; IssueDocument uses epoch_second → divide by 1000
    raw_max = result.aggregations.max_begin_time.value
    last_alert_time = int(raw_max / 1000) if raw_max else issue.last_alert_time

    agg_config = issue.aggregate_config
    if hasattr(agg_config, "to_dict"):
        agg_config = agg_config.to_dict()
    agg_dims: list[str] = (agg_config or {}).get("aggregate_dimensions", [])
    impact_scope = _build_impact_scope(issue.id, aggregate_dimensions=agg_dims)

    now = int(time.time())
    if alert_count == 0:
        issue_create_time = issue.create_time if issue.create_time else 0
        try:
            issue_create_time = int(issue_create_time)
        except (TypeError, ValueError):
            issue_create_time = 0
        age = now - issue_create_time
        if age > ORPHAN_ISSUE_THRESHOLD_SECONDS:
            logger.error(
                "[issue] orphan issue detected (no alerts associated), strategy(%s) issue(%s) age_seconds=%.0f",
                issue.strategy_id,
                issue.id,
                age,
            )

    update_doc = IssueDocument(
        id=issue.id,
        alert_count=alert_count,
        last_alert_time=last_alert_time,
        impact_scope=impact_scope,
        update_time=now,
    )
    try:
        IssueDocument.bulk_create([update_doc], action=BulkActionType.UPDATE)
    except Exception as e:
        logger.error(
            "[issue] sync_issue_alert_stats: UPDATE failed, strategy(%s) issue(%s): %s",
            issue.strategy_id,
            issue.id,
            e,
        )
        raise


def _backfill_unlinked_alerts(issue: IssueDocument):
    """回填创建窗口期及其后的同策略未关联 Alert 的 issue_id（1:1 模型）"""
    issue_create_time = issue.create_time
    if not issue_create_time:
        return

    try:
        issue_create_time = int(issue_create_time)
    except (TypeError, ValueError):
        return

    base_search = (
        AlertDocument.search(all_indices=True)
        .filter("term", strategy_id=str(issue.strategy_id))
        .filter("range", begin_time={"gte": issue_create_time})
        .exclude("exists", field="issue_id")
    )

    total = 0
    for hits in _iter_alert_hit_batches(base_search):
        update_docs = [AlertDocument(id=hit.id, issue_id=issue.id) for hit in hits]
        try:
            AlertDocument.bulk_create(update_docs, action=BulkActionType.UPSERT)
            total += len(update_docs)
        except Exception:
            logger.exception("[issue] backfill failed, strategy(%s) issue(%s)", issue.strategy_id, issue.id)
            return

    if total:
        logger.info("[issue] backfilled %d unlinked alerts, strategy(%s) issue(%s)", total, issue.strategy_id, issue.id)


def _allowed_scope_keys(aggregate_dimensions: list[str]) -> set[str] | None:
    """
    根据聚合维度决定 impact_scope 允许输出的 key 集合。

    返回值语义：
      - None  → aggregate_dimensions 为空，不收窄，全量输出
      - set() → 非空 dims 但无已知资源映射，收窄为空（输出 {}）
      - {...} → 允许输出的 key 集合

    APM 粒度规则（优先级从粗到细）：
      - app_name 在 dims → 允许 apm_app（应用级）
      - app_name + service_name 均在 dims → 额外允许 apm_service（服务级）

    K8S 粒度规则：
      - bcs_cluster_id / pod / node 等在 dims → 允许 cluster / node / pod
      - 额外含 service_name / service → 允许 service
    """
    if not aggregate_dimensions:
        return None

    dims = set(aggregate_dimensions)
    allowed: set[str] = set()

    if dims & {"bk_target_ip", "ip", "bk_host_id", "bk_cloud_id", "bk_target_cloud_id"}:
        allowed.update(["host", "set"])

    if dims & {"bk_target_service_instance_id", "bk_service_instance_id"}:
        allowed.update(["service_instances", "set"])

    # K8S：bcs_cluster_id 为必要锚点；service 需 service_name/service 显式在聚合维度中
    if dims & {"bcs_cluster_id", "pod", "pod_name", "node", "node_name"}:
        allowed.update(["cluster", "node", "pod"])
        if dims & {"service_name", "service"}:
            allowed.add("service")

    # APM：app_name → 应用级（apm_app）；service_name 额外在 dims 才开放服务级（apm_service）
    if "app_name" in dims:
        allowed.add("apm_app")
        if "service_name" in dims:
            allowed.add("apm_service")

    # 非空 dims 但无已知资源映射时，返回空集合而非 None：
    # None 表示"不收窄"，空集合表示"收窄为空"，两者语义不同
    return allowed


def _build_impact_scope(issue_id: str, aggregate_dimensions: list[str] | None = None) -> dict:
    """
    按关联告警汇总影响范围快照。

    参数:
        issue_id: Issue 文档 ID，用于检索关联的 AlertDocument 集合
        aggregate_dimensions: 聚合维度列表，来自 IssueDocument.aggregate_config["aggregate_dimensions"]；
            非空时按维度类型收窄输出 key（仅保留与维度对应的资源类型）；
            为空时全量输出所有资源维度

    返回值:
        dict — 以资源维度名为 key，每个维度格式为:
        {
            "count": int,           # 该维度下实例总数
            "instance_list": list,  # 实例详情列表（最多50条）
            "link_tpl": str|None    # 前端跳转链接模板，支持 {field} 占位符
        }
        支持的资源维度 key: set / host / service_instances / cluster / node / pod / service / apm_app / apm_service

    该方法实现完整的影响范围汇总流程，包含：
    1. 初始化各类资源的去重容器（Set / Host / ServiceInstance / K8S 集群 / APM 应用）
    2. 分批遍历 issue 关联的所有 AlertDocument，逐条解析：
       a. dimensions 字段解析与标准化（去除 "tags." 前缀，提取 topo_node / cluster_display）
       b. 关键字段提取（target_type / target / bk_host_id / bk_service_instance_id / bk_biz_id）
       c. CMDB Set 统计：按 bk_topo_node 归属收集 Set→Hosts/SIs 映射，缺少展示名时加入待查询队列
       d. K8S Cluster 统计：按 bcs_cluster_id 聚合 Node / Service / Pod 实例
       e. APM 统计：按 app_name 聚合 Service 实例，支持从 target 字段回退拆分
    3. 批量补全 CMDB Set 展示名（按业务分组查询 SetManager）
    4. 序列化为统一格式输出，每个维度截取前 50 条实例
    5. 聚合维度收窄：根据 aggregate_dimensions 过滤非相关资源维度 key
    """
    # ── 步骤1：初始化各类资源的去重容器 ──────────────────────────────────────
    # sets — CMDB 集群维度，按 set_node 去重
    # 示例: {"set|5043076": {"display_name": "DB数据库生产环境/db.es.es", "hosts": {"1804751"}, "service_instances": {"14041299"}}}
    sets: dict[str, dict] = {}

    # pending_set_names — 缺少展示名的集群，待循环结束后批量查询 CMDB 补全
    # 示例: {"set|5179871": 5017605}
    pending_set_names: dict[str, int] = {}

    # all_hosts — 全局主机去重表，携带 display_name + bk_biz_id，用于拼装跳转链接 ?bizId={bk_biz_id}#/...
    # 示例: {"9185731": {"display_name": "21.249.64.16", "bk_biz_id": 5017605}}
    all_hosts: dict[str, dict] = {}

    # all_sids — 全局服务实例去重表
    # 示例: {"14041299": {"display_name": "11.181.33.209_es-es_datanode_9200", "bk_biz_id": 5043076}}
    all_sids: dict[str, dict] = {}

    # k8s_clusters — K8S 集群维度，按 bcs_cluster_id 去重
    # 示例: {"BCS-K8S-26322": {
    #     "display_name": "TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)",
    #     "bk_biz_id": 5017605,
    #     "nodes": {"21.249.64.16": "BCS-K8S-26322/21.249.64.16"},
    #     "services": {"bkmonitor-operator-stack-kube-state-metrics": "BCS-K8S-26322/bkmonitor-operator-stack-kube-state-metrics"},
    #     "pods": {"light-prom-exporter-flkq7": "BCS-K8S-26322/light-prom-exporter-flkq7"},
    # }}
    k8s_clusters: dict[str, dict] = {}

    # apm_apps — APM 应用维度，按 app_name 去重
    # 示例: {"nf": {
    #     "services": {"nf.pushsvr": ("nf/nf.pushsvr", 5016913)},
    #     "bk_biz_id": 5016913,
    # }}
    apm_apps: dict[str, dict] = {}

    # ── 步骤2：分批遍历关联 AlertDocument，逐条解析资源归属 ──────────────────
    # 使用 search_after 分页，按 id 排序保证遍历稳定性和去重正确性
    base_search = AlertDocument.search(all_indices=True).filter("term", issue_id=issue_id)
    for hits in _iter_alert_hit_batches(base_search, sort_fields=["id"]):
        for hit in hits:
            hit_dict = hit.to_dict()

            # ── 步骤 2a：dimensions 字段解析与标准化 ──────────────────────────
            # dim_map: 将所有维度 key→value 映射，"tags." 前缀的 key 去掉前缀后也存一份
            # dim_topo_nodes: bk_topo_node 维度的值列表（用于非 HOST/SERVICE 场景）
            # dim_cluster_display: 格式化后的 K8S 集群展示名
            dim_map: dict[str, Any] = {}
            dim_topo_nodes: list[str] = []
            dim_cluster_display: str = ""

            for d in hit_dict.get("dimensions") or []:
                k, v = d.get("key", ""), d.get("value")
                # bk_topo_node 特殊处理：值为列表，需展平到 dim_topo_nodes
                if k == "bk_topo_node":
                    dim_topo_nodes.extend(v if isinstance(v, list) else ([str(v)] if v else []))
                elif k and v is not None:
                    dim_map[k] = v
                    # 去除 "tags." 前缀后存一份，兼容两种命名字段
                    if k.startswith("tags."):
                        dim_map[k[5:]] = v
                    # 提取 K8S 集群展示名（格式: "cluster_id(展示名)" → "展示名(cluster_id)"）
                    if k in ("tags.bcs_cluster_id", "bcs_cluster_id"):
                        dim_cluster_display = _format_cluster_display(d.get("display_value", ""), str(v))

            # ── 步骤 2b：关键字段提取 ──────────────────────────────────────────
            # target_type: 告警目标类型，决定资源归属维度（HOST/SERVICE/K8S-*/APM-SERVICE）
            # target: 告警目标标识，K8S 场景为节点/服务/Pod 名称，APM 场景为 "app:service"
            # host_key / sid: CMDB 主机/服务实例的唯一标识，用于去重
            target_type = (
                hit_dict.get("target_type")
                or dim_map.get("target_type", "")
                or hit_dict.get("event", {}).get("target_type", "")
            )
            target = dim_map.get("target", "")
            host_key = str(
                hit_dict.get("bk_host_id")
                or dim_map.get("bk_host_id")
                or hit_dict.get("event", {}).get("bk_host_id")
                or ""
            )
            sid = str(
                hit_dict.get("bk_service_instance_id")
                or dim_map.get("bk_service_instance_id")
                or dim_map.get("bk_target_service_instance_id")
                or ""
            )

            # ── 步骤 2c：CMDB Set 统计 ──────────────────────────────────────────
            # 按 bk_topo_node 中 "set|" 开头的节点归属，收集 Set→Hosts/SIs 映射关系。
            # HOST/SERVICE 类型：从告警顶层 / event 层读取 bk_topo_node，并利用
            #   dimension_translation 翻译展示名
            # 其他类型（K8S 宿主机等）：使用 dimensions 中提取的 dim_topo_nodes，
            #   展示名留空，待循环结束后通过 CMDB 批量补全
            # 业务 ID 提取：AlertDocument 顶层未声明 bk_biz_id，实际存放在 event.bk_biz_id 中，
            # 与 Alert.bk_biz_id 的读取逻辑（top_event.get("bk_biz_id")）以及
            # alert/manager/tasks.py 中的取法保持一致
            bk_biz_id = hit_dict.get("bk_biz_id") or (hit_dict.get("event") or {}).get("bk_biz_id")
            try:
                bk_biz_id = int(bk_biz_id) if bk_biz_id else None
            except (TypeError, ValueError):
                bk_biz_id = None
            if target_type in ("HOST", "SERVICE"):
                topo_nodes = hit_dict.get("bk_topo_node") or hit_dict.get("event", {}).get("bk_topo_node") or []
                if isinstance(topo_nodes, str):
                    topo_nodes = [topo_nodes]
                topo_translation = (
                    hit_dict.get("extra_info", {})
                    .get("origin_alarm", {})
                    .get("dimension_translation", {})
                    .get("bk_topo_node", {})
                    .get("display_value", [])
                )
            else:
                topo_nodes = dim_topo_nodes
                topo_translation = []

            # 过滤出 "set|" 开头的拓扑节点，每个 set_node 格式为 "set|{set_id}"
            set_nodes = [n for n in topo_nodes if str(n).startswith("set|")]
            for set_node in set_nodes:
                # 首次遇到该 Set 节点时初始化条目
                if set_node not in sets:
                    if topo_translation:
                        # HOST/SERVICE 场景：优先从 dimension_translation 提取展示名
                        display_name = _build_set_display_name(set_node, topo_translation)
                    else:
                        # K8S 等场景：展示名留空，加入待查询队列，循环结束后批量补全
                        display_name = ""
                        if bk_biz_id and set_node not in pending_set_names:
                            pending_set_names[set_node] = bk_biz_id
                    sets[set_node] = {"display_name": display_name, "hosts": set(), "service_instances": set()}

                # 将主机和服务实例归属到当前 Set
                entry = sets[set_node]
                # 将主机归属到当前 Set，同时维护全局主机去重表 all_hosts
                if host_key:
                    entry["hosts"].add(host_key)
                    # setdefault 确保首次记录的 display_name / bk_biz_id 不被后续覆盖
                    all_hosts.setdefault(
                        host_key,
                        {
                            "display_name": (
                                dim_map.get("ip")
                                or hit_dict.get("ip")
                                or hit_dict.get("event", {}).get("ip")
                                or host_key
                            ),
                            "bk_biz_id": bk_biz_id,
                        },
                    )
                # SERVICE 类型告警：将服务实例归属到当前 Set
                if target_type == "SERVICE" and sid:
                    entry["service_instances"].add(sid)
                    all_sids.setdefault(
                        sid,
                        {
                            "display_name": _build_si_display_name(hit_dict, dim_map, sid),
                            "bk_biz_id": bk_biz_id,
                        },
                    )

            # 兜底：HOST/SERVICE 类型但未命中任何 Set 节点的主机，仍需记入 all_hosts
            if target_type in ("HOST", "SERVICE") and host_key and host_key not in all_hosts:
                all_hosts[host_key] = {
                    "display_name": (
                        dim_map.get("ip") or hit_dict.get("ip") or hit_dict.get("event", {}).get("ip") or host_key
                    ),
                    "bk_biz_id": bk_biz_id,
                }

            # ── 步骤 2d：K8S Cluster 统计（与 CMDB Set 并行，不互斥）──────────────
            # 按 bcs_cluster_id 聚合 K8S 资源（Node / Service / Pod），与 CMDB Set 统计互不排斥，
            # 即同一告警可能同时贡献到 Set 和 K8S Cluster
            if target_type and target_type.startswith("K8S"):
                cluster_id = dim_map.get("bcs_cluster_id")
                if cluster_id:
                    # setdefault 确保同一集群只初始化一次
                    entry = k8s_clusters.setdefault(
                        cluster_id,
                        {
                            "display_name": "",
                            "bk_biz_id": bk_biz_id,
                            "nodes": {},  # {node_name: "cluster_id/node_name"}
                            "services": {},  # {service_name: "cluster_id/service_name"}
                            "pods": {},  # {pod_name: "cluster_id/pod_name"}
                        },
                    )
                    # 补全集群展示名（仅首次非空时写入）
                    if dim_cluster_display and not entry["display_name"]:
                        entry["display_name"] = dim_cluster_display
                    # 补全业务 ID（仅当条目中尚未记录时写入）
                    if not entry.get("bk_biz_id") and bk_biz_id:
                        entry["bk_biz_id"] = bk_biz_id

                    # 根据 target_type 将目标实例记入对应子维度
                    if target_type == "K8S-NODE" and target:
                        entry["nodes"][target] = f"{cluster_id}/{target}"
                    elif target_type == "K8S-SERVICE" and target:
                        entry["services"][target] = f"{cluster_id}/{target}"
                    elif target_type == "K8S-POD" and target:
                        entry["pods"][target] = f"{cluster_id}/{target}"

                    # 从 dimensions 中补充 node / service / pod（某些告警目标非 K8S 类型但维度中含 K8S 字段）
                    if node := dim_map.get("node") or dim_map.get("node_name"):
                        entry["nodes"][node] = f"{cluster_id}/{node}"
                    if svc := dim_map.get("service") or dim_map.get("service_name"):
                        entry["services"][svc] = f"{cluster_id}/{svc}"
                    if pod := dim_map.get("pod") or dim_map.get("pod_name"):
                        entry["pods"][pod] = f"{cluster_id}/{pod}"

            # ── 步骤 2e：APM 统计 ──────────────────────────────────────────────
            # 按 app_name 聚合 APM 服务，支持从 target 字段回退拆分（格式 "app:service"）
            elif target_type == "APM-SERVICE":
                app_name = dim_map.get("app_name")
                service_name = dim_map.get("service_name")
                # 回退逻辑：dimensions 中缺少 app_name 时，从 target 字段按 ":" 拆分
                if not app_name and target and ":" in target:
                    app_name, service_name = target.split(":", 1)
                if app_name:
                    entry = apm_apps.setdefault(app_name, {"services": {}, "bk_biz_id": bk_biz_id})
                    if service_name:
                        # services 值为 (display_name, bk_biz_id) 元组
                        entry["services"][service_name] = (f"{app_name}/{service_name}", bk_biz_id)

    # ── 步骤3：批量补全 CMDB Set 展示名 ──────────────────────────────────────
    # 循环结束后，按业务分组查询 SetManager，避免逐条请求 CMDB
    if pending_set_names:
        # 按业务 ID 分组，每组一次性批量查询该业务下的所有 Set
        biz_to_set_nodes: dict[int, list[str]] = {}
        for set_node, biz_id in pending_set_names.items():
            biz_to_set_nodes.setdefault(biz_id, []).append(set_node)

        for biz_id, nodes in biz_to_set_nodes.items():
            # 获取租户 ID 和业务名称，用于拼装展示名 "{biz_name}/{set_name}"
            bk_tenant_id = bk_biz_id_to_bk_tenant_id(biz_id)
            biz_obj = BusinessManager.get(biz_id)
            biz_name = biz_obj.bk_biz_name if biz_obj else str(biz_id)

            # 批量查询 Set 对象
            set_ids = [int(n.split("|")[1]) for n in nodes if "|" in n]
            set_map = SetManager.mget(bk_tenant_id=bk_tenant_id, bk_set_ids=set_ids)

            # 回填展示名：查询成功用实际名称，失败回退到 set_id 或原始 set_node
            for set_node in nodes:
                set_id_str = set_node.split("|")[1] if "|" in set_node else ""
                set_obj = set_map.get(int(set_id_str)) if set_id_str else None
                set_name = set_obj.bk_set_name if set_obj else (set_id_str or set_node)
                sets[set_node]["display_name"] = f"{biz_name}/{set_name}"

    # ── 步骤4：序列化为统一输出格式 ──────────────────────────────────────────
    # 每个资源维度格式: {count, instance_list(最多50条), link_tpl}
    # link_tpl 为前端跳转链接模板，支持 {field} 占位符替换
    result: dict[str, Any] = {}

    # 过滤掉 "__unknown_set__" 等无效 Set 节点
    valid_sets = {k: v for k, v in sets.items() if k != "__unknown_set__"}
    if valid_sets:
        result["set"] = {
            "count": len(valid_sets),
            "instance_list": [
                {"set_id": _parse_set_id(snode), "display_name": d["display_name"]} for snode, d in valid_sets.items()
            ][:50],
            "link_tpl": None,
        }

    if all_hosts:
        result["host"] = {
            "count": len(all_hosts),
            "instance_list": [
                {"bk_host_id": int(hid), "bk_biz_id": data.get("bk_biz_id"), "display_name": data["display_name"]}
                for hid, data in all_hosts.items()
            ][:50],
            "link_tpl": "?bizId={bk_biz_id}#/performance/detail/{bk_host_id}",
        }

    if all_sids:
        result["service_instances"] = {
            "count": len(all_sids),
            "instance_list": [
                {
                    "bk_service_instance_id": int(si_id),
                    "bk_biz_id": data.get("bk_biz_id"),
                    "display_name": data["display_name"],
                }
                for si_id, data in all_sids.items()
            ][:50],
            "link_tpl": None,
        }

    if k8s_clusters:
        if len(k8s_clusters) > 1:
            # 多集群场景：输出集群级汇总，不展开子资源（避免跨集群混淆）
            result["cluster"] = {
                "count": len(k8s_clusters),
                "instance_list": [
                    {"bcs_cluster_id": cid, "bk_biz_id": d.get("bk_biz_id"), "display_name": d["display_name"]}
                    for cid, d in k8s_clusters.items()
                ][:50],
                "link_tpl": (
                    "?bizId={bk_biz_id}#/k8s-new?cluster={bcs_cluster_id}"
                    "&sceneId=kubernetes&scene=performance&activeTab=list"
                ),
            }
        else:
            # 单集群场景：展开子资源维度（node / service / pod），提供更细粒度的实例列表
            cid, cdata = next(iter(k8s_clusters.items()))
            cluster_biz_id = cdata.get("bk_biz_id")
            if cdata["nodes"]:
                result["node"] = {
                    "count": len(cdata["nodes"]),
                    "instance_list": [
                        {"bcs_cluster_id": cid, "bk_biz_id": cluster_biz_id, "node": n, "display_name": dn}
                        for n, dn in cdata["nodes"].items()
                    ][:50],
                    "link_tpl": (
                        "?bizId={bk_biz_id}#/k8s-new?cluster={bcs_cluster_id}"
                        '&filterBy={{"node":["{node}"]}}&groupBy=["node"]'
                        "&sceneId=kubernetes&scene=capacity&activeTab=list"
                    ),
                }
            if cdata["services"]:
                result["service"] = {
                    "count": len(cdata["services"]),
                    "instance_list": [
                        {"bcs_cluster_id": cid, "bk_biz_id": cluster_biz_id, "service": s, "display_name": dn}
                        for s, dn in cdata["services"].items()
                    ][:50],
                    "link_tpl": (
                        "?bizId={bk_biz_id}#/k8s-new?cluster={bcs_cluster_id}"
                        '&filterBy={{"namespace":[],"service":["{service}"]}}&groupBy=["namespace","service"]'
                        "&sceneId=kubernetes&scene=network&activeTab=list"
                    ),
                }
            if cdata["pods"]:
                result["pod"] = {
                    "count": len(cdata["pods"]),
                    "instance_list": [
                        {"bcs_cluster_id": cid, "bk_biz_id": cluster_biz_id, "pod": p, "display_name": dn}
                        for p, dn in cdata["pods"].items()
                    ][:50],
                    "link_tpl": (
                        "?bizId={bk_biz_id}#/k8s-new?cluster={bcs_cluster_id}"
                        '&filterBy={{"namespace":[],"pod":["{pod}"]}}&groupBy=["namespace","pod"]'
                        "&sceneId=kubernetes&scene=performance&activeTab=list"
                    ),
                }

    if apm_apps:
        result["apm_app"] = {
            "count": len(apm_apps),
            "instance_list": [
                {"app_name": app, "bk_biz_id": data["bk_biz_id"], "display_name": app} for app, data in apm_apps.items()
            ][:50],
            "link_tpl": "?bizId={bk_biz_id}#/apm/application?filter-app_name={app_name}",
        }
        all_apm_services = [
            {"app_name": app_name, "service_name": svc, "bk_biz_id": biz_id, "display_name": dn}
            for app_name, app_data in apm_apps.items()
            for svc, (dn, biz_id) in app_data["services"].items()
        ]
        if all_apm_services:
            result["apm_service"] = {
                "count": len(all_apm_services),
                "instance_list": all_apm_services[:50],
                "link_tpl": (
                    "?bizId={bk_biz_id}#/apm/service?filter-app_name={app_name}&filter-service_name={service_name}"
                ),
            }

    # ── 步骤5：聚合维度收窄 ──────────────────────────────────────────────────
    # 根据 aggregate_dimensions 过滤非相关资源维度 key，仅保留与维度类型对应的输出
    allowed_keys = _allowed_scope_keys(aggregate_dimensions or [])
    if allowed_keys is not None:
        result = {k: v for k, v in result.items() if k in allowed_keys}

    return result


def _build_set_display_name(set_node: str, translation: list) -> str:
    """
    HOST/SERVICE 场景：从 origin_alarm.dimension_translation.bk_topo_node 提取 biz_name/set_name。
    有 bk_inst_id 时精确匹配，防止同一告警含多个 Set 时取错名称；
    bk_inst_id 缺失时直接信任该集群条目（dimension_translation 里的集群条目即对应当前 set）。
    K8S 宿主机场景由调用方循环结束后统一批量填充。
    """
    set_id = int(set_node.split("|")[1]) if "|" in set_node else None
    biz_name = set_name = ""
    for item in translation or []:
        obj = item.get("bk_obj_id", "") or item.get("bk_obj_name", "")
        name = item.get("bk_inst_name", "")
        if obj in ("biz", "业务"):
            biz_name = name
        elif obj in ("set", "集群") and set_id:
            inst_id = safe_int(item.get("bk_inst_id"), dft=None)
            # inst_id 缺失或无法解析时直接信任该条目（translation 中集群条目即为当前 set）
            if inst_id is None or inst_id == set_id:
                set_name = name
    if biz_name and set_name:
        return f"{biz_name}/{set_name}"
    return set_node


def _build_si_display_name(hit_dict: dict, dim_map: dict, sid: str) -> str:
    """服务实例展示名：优先从 target_key 提取，否则回退到 sid"""
    target_key = hit_dict.get("target_key", "")
    if target_key.startswith("服务实例名称 "):
        return target_key[len("服务实例名称 ") :]
    return str(sid)


def _parse_set_id(set_node: str) -> str:
    """set|5017605 → '5017605'"""
    return set_node.split("|")[1] if "|" in set_node else set_node


def _format_cluster_display(raw_display: str, cluster_id: str) -> str:
    """
    dimensions 中 bcs_cluster_id 的 display_value 格式为 "cluster_id(展示名)"，
    如 "BCS-K8S-41797(kihan-test-gz-0611)"，目标输出为 "展示名(cluster_id)"。
    """
    m = re.match(r"^(.+?)\((.+)\)$", raw_display or "")
    if m and m.group(1) == cluster_id:
        return f"{m.group(2)}({cluster_id})"
    return raw_display or cluster_id


def _iter_issue_hits_with_total():
    """逐页迭代活跃 Issue，同时从首批响应中提取 total（无额外 ES count 请求）。
    每次 yield (hit, total)，total 在首批确定后保持不变。
    """
    search = (
        IssueDocument.search(all_indices=True)
        .filter("terms", status=IssueStatus.ACTIVE_STATUSES)
        .sort("create_time", "id")
        .params(track_total_hits=True)
    )
    search_after = None
    total = 0
    while True:
        current = search.params(size=ISSUE_SCAN_PAGE_SIZE)
        if search_after:
            current = current.extra(search_after=search_after)
        response = current.execute()
        hits = response.hits
        if not hits:
            break
        if total == 0:
            total = getattr(getattr(hits, "total", None), "value", 0) or len(hits)
        for hit in hits:
            yield hit, total
        search_after = getattr(hits[-1].meta, "sort", None)
        if not search_after:
            break


def _iter_alert_hit_batches(base_search, sort_fields=None):
    sort_fields = sort_fields or ["begin_time", "id"]
    search = base_search.sort(*sort_fields)
    search_after = None
    while True:
        current = search.params(size=ALERT_SCAN_PAGE_SIZE)
        if search_after:
            current = current.extra(search_after=search_after)
        hits = current.execute().hits
        if not hits:
            break
        yield hits
        search_after = getattr(hits[-1].meta, "sort", None)
        if not search_after:
            break
