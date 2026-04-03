"""
Issue 测试数据脚本
- 生成 12 条 Issue，覆盖所有状态 × 优先级 × 负责人 × 回归 × 标签 × 影响范围组合（业务统一为 bk_biz_id=2）
- 今天日期：2026-03-30，时间戳基准 ≈ 1774841300
"""

# import hello 是加载Django环境，不要删除。
# import hello  # noqa
import datetime
import random
import time
import uuid

# /root/bk-monitor/bkmonitor/.venv/bin/python
# 这个是Python路径，使用这个Python执行脚本
from bkmonitor.documents.alert import AlertDocument
from bkmonitor.documents.base import BulkActionType
from bkmonitor.documents.issue import IssueActivityDocument, IssueDocument
from constants.issue import IssuePriority, IssueStatus
from elasticsearch.helpers import bulk
from elasticsearch_dsl.connections import get_connection

# 修改超时时间
AlertDocument.ES_REQUEST_TIMEOUT=120
IssueDocument.ES_REQUEST_TIMEOUT=120
IssueActivityDocument.ES_REQUEST_TIMEOUT=120

# ────────────────────────────────────────────────────────────────
# 时间基准（2026-03-30 11:00:00 CST）
# ────────────────────────────────────────────────────────────────
NOW = int(time.time())
HOUR = 3600
DAY = 86400
# MONTH = 30 * DAY

# 各 Issue 的创建时间分布（从 7 天前到刚才）
T_7D = NOW - 7 * DAY  # 7 天前
T_5D = NOW - 5 * DAY  # 5 天前
T_3D = NOW - 3 * DAY  # 3 天前
T_2D = NOW - 2 * DAY  # 2 天前
T_1D = NOW - 1 * DAY  # 1 天前
T_12H = NOW - 12 * HOUR  # 12 小时前
T_6H = NOW - 6 * HOUR  # 6 小时前
T_3H = NOW - 3 * HOUR  # 3 小时前
T_1H = NOW - 1 * HOUR  # 1 小时前
T_30M = NOW - 30 * 60  # 30 分钟前
T_10M = NOW - 10 * 60  # 10 分钟前
T_5M = NOW - 5 * 60  # 5 分钟前


# 测试数据固定后缀，用于筛选和安全删除
TEST_DATA_SUFFIX = "_issuetest"


def _id(ts: int) -> str:
    """生成 Issue ID：10位时间戳 + 8位UUID + 固定后缀"""
    return f"{ts}{uuid.uuid4().hex[:8]}{TEST_DATA_SUFFIX}"


# ────────────────────────────────────────────────────────────────
# 影响范围模板
# ────────────────────────────────────────────────────────────────
IMPACT_HOST_ONLY = {
    "host": {
        "count": 2,
        "instance_list": [
            {"bk_host_id": 9185731, "display_name": "21.249.64.16"},
            {"bk_host_id": 10692392, "display_name": "21.186.179.6"},
        ],
        "link_tpl": "/performance/detail/{bk_host_id}",
    }
}

IMPACT_HOST_AND_SET = {
    "set": {
        "count": 2,
        "instance_list": [
            {"set_id": "5070644", "display_name": "kihan-test/bcs-tke-test-BCS-K8S-41797"},
            {"set_id": "5017605", "display_name": "蓝鲸PaaS平台/BCS-K8S-40340"},
        ],
        "link_tpl": None,
    },
    "host": {
        "count": 3,
        "instance_list": [
            {"bk_host_id": 9185731, "display_name": "21.249.64.16"},
            {"bk_host_id": 10692392, "display_name": "21.186.179.6"},
            {"bk_host_id": 1804751, "display_name": "11.181.33.209"},
        ],
        "link_tpl": "/performance/detail/{bk_host_id}",
    },
    "service_instances": {
        "count": 1,
        "instance_list": [
            {"bk_service_instance_id": 14041299, "display_name": "11.181.33.209_es-es_datanode_9200"},
        ],
        "link_tpl": None,
    },
}

IMPACT_K8S = {
    "cluster": {
        "count": 2,
        "instance_list": [
            {"bcs_cluster_id": "BCS-K8S-26322", "display_name": "TC-ZY-SZ-TEST-26322-INNER(BCS-K8S-26322)"},
            {"bcs_cluster_id": "BCS-K8S-41193", "display_name": "南京三集群-业务安全-V1.26.1(BCS-K8S-41193)"},
        ],
        "link_tpl": "/k8s?filter-bcs_cluster_id={bcs_cluster_id}&sceneId=kubernetes&sceneType=overview",
    },
    "pod": {
        "count": 5,
        "instance_list": [
            {
                "bcs_cluster_id": "BCS-K8S-26322",
                "pod": "nginx-deploy-7f8b9c-abc12",
                "display_name": "nginx-deploy-7f8b9c-abc12",
            },
            {"bcs_cluster_id": "BCS-K8S-26322", "pod": "redis-master-0", "display_name": "redis-master-0"},
        ],
        "link_tpl": None,
    },
}

IMPACT_APM = {
    "app": {
        "count": 1,
        "instance_list": [
            {"app_name": "nf", "bk_biz_id": 2, "display_name": "nf"},
        ],
        "link_tpl": None,
    },
    "apm_service": {
        "count": 2,
        "instance_list": [
            {"app_name": "nf", "service_name": "nf.pushsvr", "bk_biz_id": 2, "display_name": "nf/nf.pushsvr"},
            {"app_name": "nf", "service_name": "nf.gateway", "bk_biz_id": 2, "display_name": "nf/nf.gateway"},
        ],
        "link_tpl": "?bizId={bk_biz_id}#/apm/service?filter-app_name={app_name}&filter-service_name={service_name}",
    },
}

IMPACT_EMPTY = {}


# ────────────────────────────────────────────────────────────────
# 聚合配置模板
# ────────────────────────────────────────────────────────────────
AGG_CONFIG_HOST = {
    "aggregate_dimensions": ["bk_target_ip"],
    "conditions": [],
    "alert_levels": [1, 2],
}

AGG_CONFIG_K8S = {
    "aggregate_dimensions": ["bcs_cluster_id", "pod"],
    "conditions": [{"key": "namespace", "value": ["default", "kube-system"]}],
    "alert_levels": [1],
}

AGG_CONFIG_EMPTY = {}

# 全局变量：保存已创建 Issue 的 ID 列表，供告警关联使用
CREATED_ISSUE_IDS = []

# 告警描述模板（用于 anomaly_message 测试）
ALERT_DESCRIPTIONS = [
    "CPU使用率达到95.3%，超过阈值90%",
    "磁盘IO延迟达到200ms，超过阈值100ms",
    "内存使用率达到88.7%，超过阈值85%",
    "Pod CrashLoopBackOff，已重启12次",
    "服务响应时间P99达到5.2s，超过阈值3s",
    "日志采集延迟达到30分钟，超过阈值10分钟",
    "网络丢包率达到8.5%，超过阈值5%",
    "数据库连接池使用率100%，无可用连接",
    "ES集群状态变为Yellow，存在未分配分片",
    "测试环境误报，已自动恢复",
    "Redis主从同步延迟达到15s，超过阈值5s",
    "进程端口8080未监听，服务不可用",
]


# ────────────────────────────────────────────────────────────────
# 12 条测试 Issue 定义
# ────────────────────────────────────────────────────────────────
ISSUE_DEFINITIONS = [
    # ── 1. pending_review × P0 × biz=2 × 无负责人 × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1001",
        "name": "主机 CPU 使用率过高",
        "status": IssueStatus.PENDING_REVIEW,
        "priority": IssuePriority.P0,
        "assignee": [],
        "is_regression": False,
        "labels": ["主机监控", "基础设施"],
        "alert_count": 15,
        "first_alert_time": T_7D,
        "last_alert_time": T_30M,
        "create_time": T_7D,
        "update_time": T_30M,
        "resolved_time": None,
        "impact_scope": IMPACT_HOST_AND_SET,
        "aggregate_config": AGG_CONFIG_HOST,
        "strategy_name": "主机 CPU 使用率过高",
    },
    # ── 2. pending_review × P1 × biz=6 × 无负责人 × 回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1002",
        "name": "[回归] 磁盘 IO 延迟告警",
        "status": IssueStatus.PENDING_REVIEW,
        "priority": IssuePriority.P1,
        "assignee": [],
        "is_regression": True,
        "labels": ["磁盘", "IO"],
        "alert_count": 8,
        "first_alert_time": T_3D,
        "last_alert_time": T_1H,
        "create_time": T_3D,
        "update_time": T_1H,
        "resolved_time": None,
        "impact_scope": IMPACT_HOST_ONLY,
        "aggregate_config": AGG_CONFIG_HOST,
        "strategy_name": "磁盘 IO 延迟告警",
    },
    # ── 3. pending_review × P2 × biz=8 × 无负责人 × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1003",
        "name": "内存使用率超过阈值",
        "status": IssueStatus.PENDING_REVIEW,
        "priority": IssuePriority.P2,
        "assignee": [],
        "is_regression": False,
        "labels": ["内存"],
        "alert_count": 3,
        "first_alert_time": T_1D,
        "last_alert_time": T_5M,
        "create_time": T_1D,
        "update_time": T_5M,
        "resolved_time": None,
        "impact_scope": IMPACT_EMPTY,
        "aggregate_config": AGG_CONFIG_EMPTY,
        "strategy_name": "内存使用率超过阈值",
    },
    # ── 4. unresolved × P0 × biz=2 × zhangsan × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1004",
        "name": "K8S Pod 频繁重启",
        "status": IssueStatus.UNRESOLVED,
        "priority": IssuePriority.P0,
        "assignee": ["zhangsan"],
        "is_regression": False,
        "labels": ["K8S", "容器"],
        "alert_count": 42,
        "first_alert_time": T_5D,
        "last_alert_time": T_10M,
        "create_time": T_5D,
        "update_time": T_10M,
        "resolved_time": None,
        "impact_scope": IMPACT_K8S,
        "aggregate_config": AGG_CONFIG_K8S,
        "strategy_name": "K8S Pod 频繁重启",
    },
    # ── 5. unresolved × P1 × biz=6 × lisi × 回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1005",
        "name": "[回归] APM 服务响应超时",
        "status": IssueStatus.UNRESOLVED,
        "priority": IssuePriority.P1,
        "assignee": ["lisi"],
        "is_regression": True,
        "labels": ["APM", "超时"],
        "alert_count": 20,
        "first_alert_time": T_2D,
        "last_alert_time": T_3H,
        "create_time": T_2D,
        "update_time": T_3H,
        "resolved_time": None,
        "impact_scope": IMPACT_APM,
        "aggregate_config": AGG_CONFIG_EMPTY,
        "strategy_name": "APM 服务响应超时",
    },
    # ── 6. unresolved × P2 × biz=8 × wangwu × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1006",
        "name": "日志采集延迟过高",
        "status": IssueStatus.UNRESOLVED,
        "priority": IssuePriority.P2,
        "assignee": ["wangwu"],
        "is_regression": False,
        "labels": ["日志", "采集"],
        "alert_count": 6,
        "first_alert_time": T_12H,
        "last_alert_time": T_6H,
        "create_time": T_12H,
        "update_time": T_6H,
        "resolved_time": None,
        "impact_scope": IMPACT_HOST_ONLY,
        "aggregate_config": AGG_CONFIG_HOST,
        "strategy_name": "日志采集延迟过高",
    },
    # ── 7. resolved × P0 × biz=2 × zhangsan × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1007",
        "name": "网络丢包率异常",
        "status": IssueStatus.RESOLVED,
        "priority": IssuePriority.P0,
        "assignee": ["zhangsan"],
        "is_regression": False,
        "labels": ["网络"],
        "alert_count": 30,
        "first_alert_time": T_7D,
        "last_alert_time": T_2D,
        "create_time": T_7D,
        "update_time": T_1D,
        "resolved_time": T_1D,
        "impact_scope": IMPACT_HOST_AND_SET,
        "aggregate_config": AGG_CONFIG_HOST,
        "strategy_name": "网络丢包率异常",
    },
    # ── 8. resolved × P1 × biz=6 × lisi × 回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1008",
        "name": "[回归] 数据库连接池耗尽",
        "status": IssueStatus.RESOLVED,
        "priority": IssuePriority.P1,
        "assignee": ["lisi", "zhangsan"],
        "is_regression": True,
        "labels": ["数据库", "连接池"],
        "alert_count": 12,
        "first_alert_time": T_5D,
        "last_alert_time": T_3D,
        "create_time": T_5D,
        "update_time": T_2D,
        "resolved_time": T_2D,
        "impact_scope": IMPACT_EMPTY,
        "aggregate_config": AGG_CONFIG_EMPTY,
        "strategy_name": "数据库连接池耗尽",
    },
    # ── 9. resolved × P2 × biz=8 × wangwu × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1009",
        "name": "Elasticsearch 集群 Yellow 状态",
        "status": IssueStatus.RESOLVED,
        "priority": IssuePriority.P2,
        "assignee": ["wangwu"],
        "is_regression": False,
        "labels": ["ES", "集群健康"],
        "alert_count": 5,
        "first_alert_time": T_3D,
        "last_alert_time": T_1D,
        "create_time": T_3D,
        "update_time": T_1D,
        "resolved_time": T_1D,
        "impact_scope": IMPACT_K8S,
        "aggregate_config": AGG_CONFIG_K8S,
        "strategy_name": "Elasticsearch 集群 Yellow 状态",
    },
    # ── 10. archived × P1 × biz=2 × 无负责人 × 非回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1010",
        "name": "测试环境误报告警",
        "status": IssueStatus.ARCHIVED,
        "priority": IssuePriority.P1,
        "assignee": [],
        "is_regression": False,
        "labels": ["误报"],
        "alert_count": 1,
        "first_alert_time": T_7D,
        "last_alert_time": T_7D,
        "create_time": T_7D,
        "update_time": T_5D,
        "resolved_time": None,
        "impact_scope": IMPACT_EMPTY,
        "aggregate_config": AGG_CONFIG_EMPTY,
        "strategy_name": "测试环境误报告警",
    },
    # ── 11. unresolved × P0 × biz=2 × zhangsan,lisi（多负责人）× 回归 ──
    {
        "bk_biz_id": 2,
        "strategy_id": "1011",
        "name": "[回归] Redis 主从同步延迟",
        "status": IssueStatus.UNRESOLVED,
        "priority": IssuePriority.P0,
        "assignee": ["zhangsan", "lisi"],
        "is_regression": True,
        "labels": ["Redis", "主从同步", "基础设施"],
        "alert_count": 55,
        "first_alert_time": T_3D,
        "last_alert_time": T_5M,
        "create_time": T_3D,
        "update_time": T_5M,
        "resolved_time": None,
        "impact_scope": IMPACT_HOST_AND_SET,
        "aggregate_config": AGG_CONFIG_HOST,
        "strategy_name": "Redis 主从同步延迟",
    },
    # ── 12. pending_review × P0 × biz=6 × 无负责人 × 非回归（无标签、无影响范围）──
    {
        "bk_biz_id": 2,
        "strategy_id": "1012",
        "name": "进程端口未监听",
        "status": IssueStatus.PENDING_REVIEW,
        "priority": IssuePriority.P0,
        "assignee": [],
        "is_regression": False,
        "labels": [],
        "alert_count": 2,
        "first_alert_time": T_6H,
        "last_alert_time": T_10M,
        "create_time": T_6H,
        "update_time": T_10M,
        "resolved_time": None,
        "impact_scope": IMPACT_EMPTY,
        "aggregate_config": AGG_CONFIG_EMPTY,
        "strategy_name": "进程端口未监听",
    },
]


# ────────────────────────────────────────────────────────────────
# 操作函数
# ────────────────────────────────────────────────────────────────


def _ensure_write_aliases_for_doc(doc_cls, index_prefix, timestamps):
    """通用函数：为指定文档类型的历史日期创建写入别名"""
    client = get_connection()

    date_strs = set()
    for ts in timestamps:
        date_str = datetime.datetime.utcfromtimestamp(ts).strftime("%Y%m%d")
        date_strs.add(date_str)

    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    today_write_alias = f"write_{today_str}_{index_prefix}"

    try:
        physical_indices = list(client.indices.get_alias(name=today_write_alias).keys())
        if not physical_indices:
            print(f"⚠️  找不到当天写入别名 {today_write_alias}，请先执行 {doc_cls.__name__}.rollover()")
            return False
        target_index = physical_indices[0]
    except Exception:
        print(f"⚠️  找不到当天写入别名 {today_write_alias}，请先执行 {doc_cls.__name__}.rollover()")
        return False

    print(f"📌 {index_prefix} 当天物理索引: {target_index}")

    for date_str in sorted(date_strs):
        alias_name = f"write_{date_str}_{index_prefix}"
        try:
            existing = client.indices.get_alias(name=alias_name, ignore=[404])
            if existing and not isinstance(existing, dict):
                existing = {}
            if target_index in (existing or {}):
                print(f"  ✅ 别名已存在: {alias_name} → {target_index}")
                continue
        except Exception:
            pass

        try:
            client.indices.update_aliases(
                body={"actions": [{"add": {"index": target_index, "alias": alias_name, "is_write_index": True}}]}
            )
            print(f"  ✅ 创建别名: {alias_name} → {target_index}")
        except Exception as e:
            print(f"  ❌ 创建别名失败: {alias_name}: {e}")
            return False

    return True


def ensure_write_aliases():
    """为 Issue 历史日期创建写入别名"""
    timestamps = [defn["create_time"] for defn in ISSUE_DEFINITIONS]
    return _ensure_write_aliases_for_doc(IssueDocument, "bkfta_issue", timestamps)


def ensure_alert_write_aliases(alert_timestamps):
    """为 Alert 历史日期创建写入别名"""
    return _ensure_write_aliases_for_doc(AlertDocument, "bkfta_alert", alert_timestamps)


def create_test_issues():
    """根据 ISSUE_DEFINITIONS 批量创建 12 条 Issue 测试数据"""

    # 确保历史日期的写入别名存在
    if not ensure_write_aliases():
        print("❌ 写入别名创建失败，终止写入")
        return

    global CREATED_ISSUE_IDS
    CREATED_ISSUE_IDS = []

    issues = []
    for defn in ISSUE_DEFINITIONS:
        issue_id = _id(defn["create_time"])
        CREATED_ISSUE_IDS.append(issue_id)
        issue = IssueDocument(
            id=issue_id,
            bk_biz_id=defn["bk_biz_id"],
            strategy_id=defn["strategy_id"],
            name=defn["name"],
            status=defn["status"],
            priority=defn["priority"],
            assignee=defn["assignee"],
            is_regression=defn["is_regression"],
            labels=defn["labels"],
            alert_count=defn["alert_count"],
            first_alert_time=defn["first_alert_time"],
            last_alert_time=defn["last_alert_time"],
            create_time=defn["create_time"],
            update_time=defn["update_time"],
            resolved_time=defn["resolved_time"],
            impact_scope=defn["impact_scope"],
            aggregate_config=defn["aggregate_config"],
            strategy_name=defn["strategy_name"],
        )
        issues.append(issue)

    # 分批写入，每批 3 条，避免 ES 超时
    BATCH_SIZE = 3
    total_written = 0
    for batch_start in range(0, len(issues), BATCH_SIZE):
        batch = issues[batch_start : batch_start + BATCH_SIZE]
        try:
            result = IssueDocument.bulk_create(batch, action=BulkActionType.INDEX)
            total_written += len(batch)
            print(f"  ✅ 第 {batch_start // BATCH_SIZE + 1} 批写入完成 ({len(batch)} 条)")
        except Exception as e:
            print(f"  ❌ 第 {batch_start // BATCH_SIZE + 1} 批写入异常: {type(e).__name__}: {e}")
    print(f"✅ 全部写入完成: {total_written}/{len(issues)} 条")
    if total_written == 0:
        return

    # 刷新 ES 索引，确保后续查询能立即看到数据
    try:
        client = get_connection()
        client.indices.refresh(index="*_issue*")
        print("✅ ES 索引已刷新")
    except Exception as e:
        print(f"⚠️  ES 刷新失败（不影响写入）: {e}")

    print(f"\n{'=' * 90}")
    print(f"{'序号':<4} {'biz':<5} {'status':<18} {'priority':<10} {'assignee':<20} {'regression':<12} {'name'}")
    print(f"{'=' * 90}")
    for i, issue in enumerate(issues, 1):
        assignee_str = ",".join(issue.assignee) if issue.assignee else "(无)"
        print(
            f"{i:<4} {issue.bk_biz_id:<5} {issue.status:<18} {issue.priority:<10} "
            f"{assignee_str:<20} {str(issue.is_regression):<12} {issue.name}"
        )
    print(f"{'=' * 90}")
    print(f"共写入 {len(issues)} 条 Issue\n")

    # 打印字段值汇总
    print_field_summary(issues)


def print_field_summary(issues):
    """打印所有字段的可选值汇总，方便查询测试"""
    print(f"\n{'=' * 60}")
    print("📋 字段值汇总（用于查询测试）")
    print(f"{'=' * 60}")

    # 收集各字段的唯一值
    fields = {
        "bk_biz_id": set(),
        "status": set(),
        "priority": set(),
        "assignee": set(),
        "is_regression": set(),
        "labels": set(),
        "strategy_id": set(),
        "strategy_name": set(),
    }
    for issue in issues:
        fields["bk_biz_id"].add(str(issue.bk_biz_id))
        fields["status"].add(issue.status)
        fields["priority"].add(issue.priority)
        for a in issue.assignee or []:
            fields["assignee"].add(a)
        fields["is_regression"].add(str(issue.is_regression))
        for l in issue.labels or []:
            fields["labels"].add(l)
        fields["strategy_id"].add(issue.strategy_id)
        fields["strategy_name"].add(issue.strategy_name)

    for field_name, values in fields.items():
        print(f"\n  {field_name}:")
        for v in sorted(values):
            print(f"    - {v}")

    # 统计各维度分布
    print(f"\n{'=' * 60}")
    print("📊 维度分布统计")
    print(f"{'=' * 60}")

    # 按状态统计
    status_count = {}
    for issue in issues:
        status_count[issue.status] = status_count.get(issue.status, 0) + 1
    print("\n  按状态:")
    for s, c in sorted(status_count.items()):
        print(f"    {s}: {c} 条")

    # 按优先级统计
    priority_count = {}
    for issue in issues:
        priority_count[issue.priority] = priority_count.get(issue.priority, 0) + 1
    print("\n  按优先级:")
    for p, c in sorted(priority_count.items()):
        print(f"    {p}: {c} 条")

    # 按业务统计
    biz_count = {}
    for issue in issues:
        biz_count[str(issue.bk_biz_id)] = biz_count.get(str(issue.bk_biz_id), 0) + 1
    print("\n  按业务:")
    for b, c in sorted(biz_count.items()):
        print(f"    bk_biz_id={b}: {c} 条")

    # 按负责人统计
    assignee_count = {"有负责人": 0, "无负责人": 0}
    for issue in issues:
        if issue.assignee:
            assignee_count["有负责人"] += 1
        else:
            assignee_count["无负责人"] += 1
    print("\n  按负责人:")
    for a, c in assignee_count.items():
        print(f"    {a}: {c} 条")

    # 按回归统计
    regression_count = {"回归": 0, "新问题": 0}
    for issue in issues:
        if issue.is_regression:
            regression_count["回归"] += 1
        else:
            regression_count["新问题"] += 1
    print("\n  按回归:")
    for r, c in regression_count.items():
        print(f"    {r}: {c} 条")

    print()


def _generate_alert_id(begin_time, seq):
    """生成告警 ID：10位时间戳 + 10位序列号 + 固定后缀"""
    return f"{begin_time}{seq:010d}{TEST_DATA_SUFFIX}"


def create_test_alerts(start_time, end_time):
    """为每个 Issue 生成关联的 AlertDocument 测试数据"""
    # 先查询已有的 Issue，获取 ID 列表
    results = IssueDocument.search(start_time=start_time, end_time=end_time).params(size=50).execute()
    issue_map = {}  # issue_id -> issue_defn_index
    for hit in results.hits:
        issue_map[hit.meta.id] = hit

    if not issue_map:
        print("⚠️  无 Issue 数据，请先执行 create_test_issues()")
        return

    print(f"📋 找到 {len(issue_map)} 条 Issue，开始生成关联告警...")

    # 收集所有告警的时间戳，用于创建写入别名
    all_alert_timestamps = []
    alert_plan = []  # [(issue_hit, defn, alert_count)]

    for issue_id, hit in issue_map.items():
        # 找到对应的 ISSUE_DEFINITIONS
        defn = None
        for d in ISSUE_DEFINITIONS:
            if d["strategy_id"] == hit.strategy_id and d["name"] == hit.name:
                defn = d
                break
        if not defn:
            continue

        alert_count = defn["alert_count"]
        first_alert = defn["first_alert_time"]
        last_alert = defn["last_alert_time"]

        # 在 first_alert_time ~ last_alert_time 之间均匀分布告警
        if alert_count <= 1:
            timestamps = [first_alert]
        else:
            step = max(1, (last_alert - first_alert) // (alert_count - 1))
            timestamps = [first_alert + i * step for i in range(alert_count)]
            # 确保最后一条告警在 last_alert_time
            timestamps[-1] = last_alert

        all_alert_timestamps.extend(timestamps)
        alert_plan.append((issue_id, hit, defn, timestamps))

    # 确保告警写入别名存在
    if not ensure_alert_write_aliases(all_alert_timestamps):
        print("❌ Alert 写入别名创建失败，终止写入")
        return

    # 生成 AlertDocument 列表
    alerts = []
    seq = 1
    status_choices = ["ABNORMAL", "RECOVERED", "CLOSED"]

    for issue_id, hit, defn, timestamps in alert_plan:
        bk_biz_id = defn["bk_biz_id"]
        strategy_id = defn["strategy_id"]
        strategy_name = defn["strategy_name"]
        desc_template = ALERT_DESCRIPTIONS[ISSUE_DEFINITIONS.index(defn) % len(ALERT_DESCRIPTIONS)]

        for i, begin_time in enumerate(timestamps):
            # 告警状态分布：大部分 ABNORMAL，部分 RECOVERED/CLOSED
            if defn["status"] in (IssueStatus.RESOLVED, IssueStatus.ARCHIVED):
                # 已解决/已归档的 Issue，告警多为 RECOVERED/CLOSED
                status = random.choice(["RECOVERED", "CLOSED", "RECOVERED"])
            elif i < len(timestamps) - 2:
                status = random.choice(["ABNORMAL", "ABNORMAL", "RECOVERED"])
            else:
                status = "ABNORMAL"

            end_time = begin_time + random.randint(60, 600)
            create_time = begin_time - random.randint(0, 30)
            duration = end_time - begin_time

            alert_id = _generate_alert_id(begin_time, seq)
            severity = random.choice([1, 2, 3])

            # 每条告警的 description 略有不同
            description = f"{desc_template}（第{i + 1}次）"

            alert = AlertDocument(
                id=alert_id,
                alert_name=strategy_name,
                strategy_id=strategy_id,
                create_time=create_time,
                update_time=end_time,
                begin_time=begin_time,
                end_time=end_time,
                latest_time=end_time,
                first_anomaly_time=begin_time,
                assignee=defn["assignee"] or ["admin"],
                duration=duration,
                severity=severity,
                status=status,
                is_blocked=False,
                is_handled=True,
                is_ack=status in ("RECOVERED", "CLOSED"),
                is_shielded=False,
                dedupe_md5=f"md5_{strategy_id}_{i}",
                issue_id=issue_id,
                dimensions=[
                    {
                        "key": "bk_biz_id",
                        "value": str(bk_biz_id),
                        "display_key": "业务ID",
                        "display_value": str(bk_biz_id),
                    },
                ],
                extra_info={
                    "strategy": {"name": strategy_name, "items": []},
                },
            )
            # event 字段需要单独设置（InnerDoc）
            alert.event = {
                "bk_biz_id": bk_biz_id,
                "description": description,
                "metric": [f"metric_{strategy_id}"],
                "category": "os",
                "data_type": "time_series",
                "target_type": "HOST",
                "target": f"host_{bk_biz_id}",
                "ip": f"10.0.{bk_biz_id}.{random.randint(1, 254)}",
                "bk_cloud_id": 0,
            }
            alerts.append(alert)
            seq += 1

    # 分批写入，每批 20 条，避免 ES 超时
    BATCH_SIZE = 20
    total_written = 0
    for batch_start in range(0, len(alerts), BATCH_SIZE):
        batch = alerts[batch_start : batch_start + BATCH_SIZE]
        try:
            AlertDocument.bulk_create(batch, action=BulkActionType.INDEX)
            total_written += len(batch)
            print(f"  ✅ 告警第 {batch_start // BATCH_SIZE + 1} 批写入完成 ({len(batch)} 条)")
        except Exception as e:
            print(f"  ❌ 告警第 {batch_start // BATCH_SIZE + 1} 批写入异常: {type(e).__name__}: {e}")
    print(f"✅ 告警全部写入完成: {total_written}/{len(alerts)} 条")
    if total_written == 0:
        return

    # 刷新索引
    try:
        client = get_connection()
        client.indices.refresh(index="*alert*")
        print("✅ Alert ES 索引已刷新")
    except Exception as e:
        print(f"⚠️  Alert ES 刷新失败: {e}")

    # 打印汇总
    print(f"\n{'=' * 100}")
    print(f"{'Issue名称':<30} {'issue_id':<22} {'告警数':<8} {'状态分布'}")
    print(f"{'=' * 100}")
    for issue_id, hit, defn, timestamps in alert_plan:
        # 统计该 Issue 下各状态告警数
        issue_alerts = [a for a in alerts if a.issue_id == issue_id]
        status_dist = {}
        for a in issue_alerts:
            status_dist[a.status] = status_dist.get(a.status, 0) + 1
        dist_str = ", ".join(f"{s}={c}" for s, c in sorted(status_dist.items()))
        print(f"  {defn['name']:<28} {issue_id[:20]:<22} {len(issue_alerts):<8} {dist_str}")
    print(f"{'=' * 100}")
    print(f"共写入 {len(alerts)} 条告警，关联 {len(alert_plan)} 个 Issue\n")


def query_alerts(start_time=None, end_time=None):
    """查询所有关联 Issue 的告警"""
    results = (
        AlertDocument.search(start_time=start_time, end_time=end_time)
        .filter("exists", field="issue_id")
        .params(size=200)
        .execute()
    )
    print(f"\n🔔 关联 Issue 的告警共 {results.hits.total.value} 条:")
    print(f"{'─' * 130}")

    # 按 issue_id 分组统计
    issue_alert_count = {}
    for hit in results.hits:
        iid = getattr(hit, "issue_id", "unknown")
        issue_alert_count[iid] = issue_alert_count.get(iid, 0) + 1

    for iid, count in sorted(issue_alert_count.items(), key=lambda x: -x[1]):
        print(f"  issue_id={iid[:20]}...  告警数={count}")
    print(f"{'─' * 130}")


def delete_alerts(start_time=None, end_time=None):
    """删除带有测试后缀的告警"""
    results = (
        AlertDocument.search(start_time=start_time, end_time=end_time)
        .filter("wildcard", id=f"*{TEST_DATA_SUFFIX}")
        .params(size=1000)
        .execute()
    )
    actions = [{"_op_type": "delete", "_index": hit.meta.index, "_id": hit.meta.id} for hit in results.hits]
    if actions:
        client = get_connection()
        success, failed = bulk(client, actions, raise_on_error=True)
        print(f"🗑️  告警删除: {success} 条")
    else:
        print("🗑️  无测试告警需要删除")


def query_issues(start_time=None, end_time=None):
    """查询所有 Issue"""
    results = (
        IssueDocument.search(start_time=start_time, end_time=end_time, all_indices=True).params(size=100).execute()
    )
    print(f"\n📦 Issue 共 {results.hits.total.value} 条:")
    print(f"{'─' * 120}")
    for hit in results.hits:
        assignee = getattr(hit, "assignee", None) or []
        assignee_str = ",".join(assignee) if assignee else "(无)"
        resolved = getattr(hit, "resolved_time", None)
        resolved_str = str(int(resolved)) if resolved else "null"
        print(
            f"  id={hit.meta.id}  biz={hit.bk_biz_id}  status={hit.status:<18} "
            f"priority={hit.priority:<4} assignee={assignee_str:<20} "
            f"regression={str(getattr(hit, 'is_regression', False)):<6} "
            f"resolved_time={resolved_str:<12} name={hit.name}"
        )
    print(f"{'─' * 120}")


def query_activities(start_time=None, end_time=None):
    """查询所有活动记录"""
    results = (
        IssueActivityDocument.search(start_time=start_time, end_time=end_time, all_indices=True)
        .params(size=500)
        .execute()
    )
    print(f"\n📝 活动记录共 {results.hits.total.value} 条:")
    for hit in results.hits:
        print(
            f"  id={hit.meta.id}  issue_id={hit.issue_id}  type={hit.activity_type}  "
            f"operator={hit.operator}  from={getattr(hit, 'from_value', None)}  "
            f"to={getattr(hit, 'to_value', None)}  content={getattr(hit, 'content', None)}"
        )


def delete_issues(start_time=None, end_time=None):
    """删除带有测试后缀的 Issue"""
    results = (
        IssueDocument.search(start_time=start_time, end_time=end_time)
        .filter("wildcard", id=f"*{TEST_DATA_SUFFIX}")
        .params(size=500)
        .execute()
    )
    actions = [{"_op_type": "delete", "_index": hit.meta.index, "_id": hit.meta.id} for hit in results.hits]
    if actions:
        client = get_connection()
        success, failed = bulk(client, actions, raise_on_error=True)
        print(f"🗑️  测试 Issue 删除: {success} 条")
    else:
        print("🗑️  无测试 Issue 需要删除")


def delete_activities(start_time=None, end_time=None):
    """删除带有测试后缀的活动记录"""
    results = (
        IssueActivityDocument.search(start_time=start_time, end_time=end_time)
        .filter("wildcard", issue_id=f"*{TEST_DATA_SUFFIX}")
        .params(size=500)
        .execute()
    )
    actions = [{"_op_type": "delete", "_index": hit.meta.index, "_id": hit.meta.id} for hit in results.hits]
    if actions:
        client = get_connection()
        success, failed = bulk(client, actions, raise_on_error=True)
        print(f"🗑️  测试活动日志删除: {success} 条")
    else:
        print("🗑️  无测试活动日志需要删除")


def query_issue_index():
    """查看所有 bkfta_issue 相关的索引和别名"""
    client = get_connection()
    aliases = client.indices.get_alias(index="*_issue*", ignore=[404])
    print("\n📂 Issue 相关索引:")
    for index_name, info in aliases.items():
        print(f"  物理索引: {index_name}")
        for alias in info.get("aliases", {}).keys():
            print(f"    别名: {alias}")


def delete_issue_index():
    """删除所有 Issue 相关索引"""
    client = get_connection()
    aliases = client.indices.get_alias(index="*_issue*", ignore=[404])
    for index_name, info in aliases.items():
        client.indices.delete(index=index_name, ignore=[400, 404])
        print(f"🗑️  删除物理索引: {index_name}")



#------ 用例执行入口 ------
# ── 初始化索引（首次运行需取消注释）──
# IssueDocument.rollover()
# IssueActivityDocument.rollover()
# AlertDocument.rollover()

# ── 查看索引 ──
# query_issue_index()

# ── 删除索引 ──
# delete_issue_index()

# ── 清理旧数据（最近1个月）──

start_time=NOW-3 * DAY
end_time=NOW

# delete_issues(start_time=start_time, end_time=end_time)
# delete_activities(start_time=start_time, end_time=end_time)
# delete_alerts(start_time=start_time, end_time=end_time)

# ── 创建测试数据（12 条 Issue + 关联告警）──
# create_test_issues()
# create_test_alerts(start_time=start_time, end_time=end_time)

# ── 查询验证（最近1个月）──
query_issues(start_time=start_time, end_time=end_time)
query_alerts(start_time=start_time, end_time=end_time)
query_activities(start_time=start_time, end_time=end_time)
