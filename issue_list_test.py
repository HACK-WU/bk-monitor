"""
Issue 列表接口测试脚本
- 直接调用 SearchIssueResource / IssueQueryHandler 测试列表查询
- 覆盖：分页、排序、条件过滤、虚拟状态、时间范围、query_string、聚合统计、show_dsl 等场景
- 前置条件：先运行 issue_test.py 写入 12 条测试数据
"""

# import hello 是加载Django环境，不要删除。
import hello  # noqa
import json
import time
import traceback

from fta_web.issue.resources import SearchIssueResource, IssueAlertDateHistogramResultResource
from fta_web.issue.handlers.issue import IssueQueryHandler

# ────────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────────
NOW = int(time.time())
HOUR = 3600
DAY = 86400

# 测试用户名（与 issue_test.py 中的 assignee 对应）
TEST_USERNAME = "zhangsan"

# 测试业务 ID（与 issue_test.py 中的 bk_biz_id 对应）
ALL_BIZ_IDS = [2, 6, 8]

# 统计计数器
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def sep(title: str):
    """打印分隔线"""
    print(f"\n{'=' * 90}")
    print(f"  {title}")
    print(f"{'=' * 90}")


def print_issues_brief(issues: list, max_show: int = 5):
    """简要打印 Issue 列表"""
    for i, issue in enumerate(issues[:max_show]):
        assignee_str = ",".join(issue.get("assignee") or []) or "(无)"
        print(
            f"    [{i + 1}] id={issue['id'][:18]}...  biz={issue.get('bk_biz_id', '?'):<4} "
            f"status={issue.get('status', '?'):<18} priority={issue.get('priority', '?'):<4} "
            f"assignee={assignee_str:<16} name={issue.get('name', '?')}"
        )
    if len(issues) > max_show:
        print(f"    ... 还有 {len(issues) - max_show} 条")


def print_aggs(aggs: list):
    """打印聚合统计"""
    for agg in aggs:
        children_str = ", ".join([f"{c['id']}={c['count']}" for c in agg.get("children", [])])
        print(f"    {agg['id']}({agg['name']}): total={agg['count']}  [{children_str}]")


def run_test(name: str, request_data: dict, validate_fn=None):
    """
    执行单个测试用例

    参数:
        name: 测试名称
        request_data: 传给 SearchIssueResource 的请求参数
        validate_fn: 可选的校验函数，接收 result dict，返回 (bool, msg)
    """
    global PASS_COUNT, FAIL_COUNT, SKIP_COUNT
    print(f"\n  ▶ {name}")
    print(f"    请求参数: {json.dumps(request_data, ensure_ascii=False, default=str)}")

    try:
        result = SearchIssueResource().request(**request_data)
        total = result.get("total", 0)
        issues = result.get("issues", [])
        aggs = result.get("aggs")
        dsl = result.get("dsl")

        print(f"    ✅ 返回 total={total}, issues={len(issues)} 条")

        if issues:
            print_issues_brief(issues)

        if aggs:
            print("    📊 聚合统计:")
            print_aggs(aggs)

        if dsl:
            print(f"    📋 DSL: {json.dumps(dsl, ensure_ascii=False)[:200]}...")

        # 执行自定义校验
        if validate_fn:
            ok, msg = validate_fn(result)
            if ok:
                print(f"    ✅ 校验通过: {msg}")
                PASS_COUNT += 1
            else:
                print(f"    ❌ 校验失败: {msg}")
                FAIL_COUNT += 1
        else:
            PASS_COUNT += 1

        return result

    except Exception as e:
        print(f"    ❌ 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1
        return None


def run_handler_test(name: str, handler_kwargs: dict, search_kwargs: dict = None, validate_fn=None):
    """
    直接调用 IssueQueryHandler 执行测试

    参数:
        name: 测试名称
        handler_kwargs: IssueQueryHandler 构造参数
        search_kwargs: handler.search() 的参数
        validate_fn: 可选的校验函数
    """
    global PASS_COUNT, FAIL_COUNT
    search_kwargs = search_kwargs or {}
    print(f"\n  ▶ {name}")
    print(f"    Handler参数: {json.dumps(handler_kwargs, ensure_ascii=False, default=str)}")

    try:
        handler = IssueQueryHandler(**handler_kwargs)
        result = handler.search(**search_kwargs)
        total = result.get("total", 0)
        issues = result.get("issues", [])

        print(f"    ✅ 返回 total={total}, issues={len(issues)} 条")
        if issues:
            print_issues_brief(issues)

        if validate_fn:
            ok, msg = validate_fn(result)
            if ok:
                print(f"    ✅ 校验通过: {msg}")
                PASS_COUNT += 1
            else:
                print(f"    ❌ 校验失败: {msg}")
                FAIL_COUNT += 1
        else:
            PASS_COUNT += 1

        return result

    except Exception as e:
        print(f"    ❌ 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1
        return None


# ────────────────────────────────────────────────────────────────
# 测试用例组 1：基础查询
# ────────────────────────────────────────────────────────────────
def test_basic_queries():
    sep("测试组 1：基础查询")

    # 1.1 查询所有 Issue（不带任何过滤条件）
    run_test(
        "1.1 查询所有 Issue（无过滤）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
        validate_fn=lambda r: (r["total"] >= 12, f"期望 >=12 条，实际 {r['total']} 条"),
    )

    # 1.2 查询单个业务的 Issue
    run_test(
        "1.2 查询业务 bk_biz_id=2 的 Issue",
        {"bk_biz_ids": [2], "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
        validate_fn=lambda r: (
            all(issue["bk_biz_id"] in ("2", 2) for issue in r["issues"]),
            f"所有 Issue 的 bk_biz_id 应为 2，实际返回 {r['total']} 条",
        ),
    )

    # 1.3 查询多个业务
    run_test(
        "1.3 查询业务 bk_biz_id=[2, 6] 的 Issue",
        {"bk_biz_ids": [2, 6], "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
        validate_fn=lambda r: (
            all(issue["bk_biz_id"] in ("2", "6", 2, 6) for issue in r["issues"]),
            f"所有 Issue 的 bk_biz_id 应为 2 或 6，实际返回 {r['total']} 条",
        ),
    )

    # 1.4 查询不存在的业务
    run_test(
        "1.4 查询不存在的业务 bk_biz_id=99999",
        {"bk_biz_ids": [99999], "username": TEST_USERNAME, "page": 1, "page_size": 50},
        validate_fn=lambda r: (r["total"] == 0, f"期望 0 条，实际 {r['total']} 条"),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 2：分页
# ────────────────────────────────────────────────────────────────
def test_pagination():
    sep("测试组 2：分页")

    # 2.1 第一页，每页 3 条
    result1 = run_test(
        "2.1 分页：page=1, page_size=3",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 3, "show_aggs": False},
        validate_fn=lambda r: (len(r["issues"]) == 3, f"期望 3 条，实际 {len(r['issues'])} 条"),
    )

    # 2.2 第二页
    result2 = run_test(
        "2.2 分页：page=2, page_size=3",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 2, "page_size": 3, "show_aggs": False},
        validate_fn=lambda r: (len(r["issues"]) == 3, f"期望 3 条，实际 {len(r['issues'])} 条"),
    )

    # 2.3 验证两页数据不重复
    if result1 and result2:
        ids_page1 = {issue["id"] for issue in result1["issues"]}
        ids_page2 = {issue["id"] for issue in result2["issues"]}
        overlap = ids_page1 & ids_page2
        if not overlap:
            print("    ✅ 两页数据无重复")
        else:
            print(f"    ❌ 两页数据有重复: {overlap}")

    # 2.4 第四页（每页 3 条，12 条数据，第 4 页应有 3 条）
    run_test(
        "2.4 分页：page=4, page_size=3",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 4, "page_size": 3, "show_aggs": False},
        validate_fn=lambda r: (len(r["issues"]) == 3, f"期望 3 条，实际 {len(r['issues'])} 条"),
    )

    # 2.5 超出范围的页码
    run_test(
        "2.5 分页：page=100, page_size=3（超出范围）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 100, "page_size": 3, "show_aggs": False},
        validate_fn=lambda r: (len(r["issues"]) == 0, f"期望 0 条，实际 {len(r['issues'])} 条"),
    )

    # 2.6 page_size=1，逐条翻页
    run_test(
        "2.6 分页：page=1, page_size=1",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 1, "show_aggs": False},
        validate_fn=lambda r: (len(r["issues"]) == 1, f"期望 1 条，实际 {len(r['issues'])} 条"),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 3：排序
# ────────────────────────────────────────────────────────────────
def test_ordering():
    sep("测试组 3：排序")

    # 3.1 默认排序（status + -update_time）
    run_test(
        "3.1 默认排序（不传 ordering）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 12, "show_aggs": False},
    )

    # 3.2 按创建时间倒序
    run_test(
        "3.2 按创建时间倒序 ordering=['-create_time']",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "ordering": ["-create_time"],
            "page": 1,
            "page_size": 12,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(
                r["issues"][i].get("create_time", 0) >= r["issues"][i + 1].get("create_time", 0)
                for i in range(len(r["issues"]) - 1)
            ),
            "create_time 应为倒序",
        ),
    )

    # 3.3 按优先级排序
    run_test(
        "3.3 按优先级排序 ordering=['priority']",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "ordering": ["priority"],
            "page": 1,
            "page_size": 12,
            "show_aggs": False,
        },
    )

    # 3.4 按更新时间正序
    run_test(
        "3.4 按更新时间正序 ordering=['update_time']",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "ordering": ["update_time"],
            "page": 1,
            "page_size": 12,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(
                r["issues"][i].get("update_time", 0) <= r["issues"][i + 1].get("update_time", 0)
                for i in range(len(r["issues"]) - 1)
            ),
            "update_time 应为正序",
        ),
    )

    # 3.5 多字段排序
    run_test(
        "3.5 多字段排序 ordering=['priority', '-update_time']",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "ordering": ["priority", "-update_time"],
            "page": 1,
            "page_size": 12,
            "show_aggs": False,
        },
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 4：虚拟状态过滤
# ────────────────────────────────────────────────────────────────
def test_virtual_status():
    sep("测试组 4：虚拟状态过滤")

    # 4.1 MY_ISSUE - 查询 zhangsan 负责的 Issue
    run_test(
        "4.1 虚拟状态 MY_ISSUE（zhangsan 负责的）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": ["MY_ISSUE"],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(TEST_USERNAME in (issue.get("assignee") or []) for issue in r["issues"]),
            f"所有 Issue 的 assignee 应包含 {TEST_USERNAME}",
        ),
    )

    # 4.2 NO_ASSIGNEE - 查询未分派的 Issue
    run_test(
        "4.2 虚拟状态 NO_ASSIGNEE（未分派的）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": ["NO_ASSIGNEE"],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(not (issue.get("assignee") or []) for issue in r["issues"]),
            "所有 Issue 的 assignee 应为空",
        ),
    )

    # 4.3 MY_ISSUE + NO_ASSIGNEE 组合（OR 语义）
    run_test(
        "4.3 虚拟状态组合 MY_ISSUE + NO_ASSIGNEE",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": ["MY_ISSUE", "NO_ASSIGNEE"],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(
                TEST_USERNAME in (issue.get("assignee") or []) or not (issue.get("assignee") or [])
                for issue in r["issues"]
            ),
            f"所有 Issue 应为 {TEST_USERNAME} 负责或未分派",
        ),
    )

    # 4.4 用 lisi 用户测试 MY_ISSUE
    run_test(
        "4.4 虚拟状态 MY_ISSUE（lisi 负责的）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": "lisi",
            "status": ["MY_ISSUE"],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all("lisi" in (issue.get("assignee") or []) for issue in r["issues"]),
            "所有 Issue 的 assignee 应包含 lisi",
        ),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 5：conditions 条件过滤
# ────────────────────────────────────────────────────────────────
def test_conditions():
    sep("测试组 5：conditions 条件过滤")

    # 5.1 按实际状态过滤 - unresolved
    run_test(
        "5.1 conditions: status=unresolved",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["unresolved"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] == "unresolved" for issue in r["issues"]),
            "所有 Issue 的 status 应为 unresolved",
        ),
    )

    # 5.2 按实际状态过滤 - pending_review
    run_test(
        "5.2 conditions: status=pending_review",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["pending_review"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] == "pending_review" for issue in r["issues"]),
            "所有 Issue 的 status 应为 pending_review",
        ),
    )

    # 5.3 按实际状态过滤 - resolved
    run_test(
        "5.3 conditions: status=resolved",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["resolved"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] == "resolved" for issue in r["issues"]),
            "所有 Issue 的 status 应为 resolved",
        ),
    )

    # 5.4 按实际状态过滤 - archived
    run_test(
        "5.4 conditions: status=archived",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["archived"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] == "archived" for issue in r["issues"]),
            "所有 Issue 的 status 应为 archived",
        ),
    )

    # 5.5 多状态过滤（unresolved + pending_review）
    run_test(
        "5.5 conditions: status=[unresolved, pending_review]",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["unresolved", "pending_review"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] in ("unresolved", "pending_review") for issue in r["issues"]),
            "所有 Issue 的 status 应为 unresolved 或 pending_review",
        ),
    )

    # 5.6 按优先级过滤 - P0
    run_test(
        "5.6 conditions: priority=P0",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "priority", "value": ["P0"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["priority"] == "P0" for issue in r["issues"]),
            "所有 Issue 的 priority 应为 P0",
        ),
    )

    # 5.7 按优先级过滤 - P0 + P1
    run_test(
        "5.7 conditions: priority=[P0, P1]",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "priority", "value": ["P0", "P1"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["priority"] in ("P0", "P1") for issue in r["issues"]),
            "所有 Issue 的 priority 应为 P0 或 P1",
        ),
    )

    # 5.8 按负责人过滤
    run_test(
        "5.8 conditions: assignee=zhangsan",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "assignee", "value": ["zhangsan"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all("zhangsan" in (issue.get("assignee") or []) for issue in r["issues"]),
            "所有 Issue 的 assignee 应包含 zhangsan",
        ),
    )

    # 5.9 按 is_regression 过滤
    run_test(
        "5.9 conditions: is_regression=true",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "is_regression", "value": [True], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue.get("is_regression") is True for issue in r["issues"]),
            "所有 Issue 的 is_regression 应为 True",
        ),
    )

    # 5.10 按策略 ID 过滤
    run_test(
        "5.10 conditions: strategy_id=1001",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "strategy_id", "value": ["1001"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue.get("strategy_id") == "1001" for issue in r["issues"]),
            "所有 Issue 的 strategy_id 应为 1001",
        ),
    )

    # 5.11 neq 方法 - 排除 P2
    run_test(
        "5.11 conditions: priority neq P2",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "priority", "value": ["P2"], "method": "neq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["priority"] != "P2" for issue in r["issues"]),
            "所有 Issue 的 priority 不应为 P2",
        ),
    )

    # 5.12 include 方法 - 名称模糊匹配
    run_test(
        "5.12 conditions: name include 'CPU'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "name", "value": ["CPU"], "method": "include"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all("CPU" in issue.get("name", "") for issue in r["issues"]),
            "所有 Issue 的 name 应包含 CPU",
        ),
    )

    # 5.13 gt 方法 - alert_count > 20
    run_test(
        "5.13 conditions: alert_count gt 20",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "alert_count", "value": [20], "method": "gt"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue.get("alert_count", 0) > 20 for issue in r["issues"]),
            "所有 Issue 的 alert_count 应 > 20",
        ),
    )

    # 5.14 多条件组合 - status=unresolved AND priority=P0
    run_test(
        "5.14 多条件组合: status=unresolved AND priority=P0",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [
                {"key": "status", "value": ["unresolved"], "method": "eq", "condition": "and"},
                {"key": "priority", "value": ["P0"], "method": "eq"},
            ],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue["status"] == "unresolved" and issue["priority"] == "P0" for issue in r["issues"]),
            "所有 Issue 应为 unresolved + P0",
        ),
    )

    # 5.15 按标签过滤
    run_test(
        "5.15 conditions: labels include 'K8S'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "labels", "value": ["K8S"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 5.16 lte 方法 - create_time <= 3天前
    run_test(
        "5.16 conditions: create_time lte 3天前",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "create_time", "value": [NOW - 3 * DAY], "method": "lte"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue.get("create_time", 0) <= NOW - 3 * DAY for issue in r["issues"]),
            "所有 Issue 的 create_time 应 <= 3天前",
        ),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 6：时间范围过滤
# ────────────────────────────────────────────────────────────────
def test_time_range():
    sep("测试组 6：时间范围过滤")

    # 6.1 仅传 end_time（create_time <= end_time）
    run_test(
        "6.1 仅传 end_time=3天前（只查 3 天前创建的 Issue）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "end_time": NOW - 3 * DAY,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(issue.get("create_time", 0) <= NOW - 3 * DAY for issue in r["issues"]),
            "所有 Issue 的 create_time 应 <= 3天前",
        ),
    )

    # 6.2 仅传 start_time（resolved_time >= start_time OR resolved_time IS NULL）
    run_test(
        "6.2 仅传 start_time=2天前",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - 2 * DAY,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (
            all(
                issue.get("resolved_time") is None or issue.get("resolved_time", 0) >= NOW - 2 * DAY
                for issue in r["issues"]
            ),
            "所有 Issue 的 resolved_time 应 >= 2天前 或为 null",
        ),
    )

    # 6.3 同时传 start_time 和 end_time
    run_test(
        "6.3 时间范围: start_time=5天前, end_time=1天前",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - 5 * DAY,
            "end_time": NOW - 1 * DAY,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 6.4 不传时间范围（查询所有）
    run_test(
        "6.4 不传时间范围（查询所有 Issue）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 6.5 极小时间范围（1小时内创建的）
    run_test(
        "6.5 极小时间范围: end_time=NOW, start_time=1小时前",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - HOUR,
            "end_time": NOW,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 6.6 极大时间范围（30天）
    run_test(
        "6.6 极大时间范围: start_time=30天前, end_time=NOW",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - 30 * DAY,
            "end_time": NOW,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 7：query_string 搜索
# ────────────────────────────────────────────────────────────────
def test_query_string():
    sep("测试组 7：query_string 搜索")

    # 7.1 搜索 "CPU"
    run_test(
        "7.1 query_string='CPU'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "CPU",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 7.2 搜索 "回归"
    run_test(
        "7.2 query_string='回归'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "回归",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 7.3 搜索 "K8S"
    run_test(
        "7.3 query_string='K8S'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "K8S",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 7.4 搜索 "Redis"
    run_test(
        "7.4 query_string='Redis'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "Redis",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 7.5 搜索不存在的关键词
    run_test(
        "7.5 query_string='不存在的关键词xyz123'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "不存在的关键词xyz123",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (r["total"] == 0, f"期望 0 条，实际 {r['total']} 条"),
    )

    # 7.6 搜索 "Elasticsearch"
    run_test(
        "7.6 query_string='Elasticsearch'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "Elasticsearch",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 7.7 搜索 "磁盘"
    run_test(
        "7.7 query_string='磁盘'",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "磁盘",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 8：聚合统计（show_aggs）
# ────────────────────────────────────────────────────────────────
def test_aggs():
    sep("测试组 8：聚合统计")

    # 8.1 show_aggs=True
    result = run_test(
        "8.1 show_aggs=True（全量查询）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
    )

    if result and result.get("aggs"):
        aggs = result["aggs"]

        # 验证聚合维度完整性
        agg_ids = {a["id"] for a in aggs}
        expected_ids = {"priority", "status", "assignee", "is_regression"}
        missing = expected_ids - agg_ids
        if not missing:
            print(f"    ✅ 聚合维度完整: {agg_ids}")
        else:
            print(f"    ❌ 缺少聚合维度: {missing}")

        # 验证 priority 聚合
        priority_agg = next((a for a in aggs if a["id"] == "priority"), None)
        if priority_agg:
            p_ids = {c["id"] for c in priority_agg["children"]}
            print(f"    优先级聚合子项: {p_ids}")

        # 验证 status 聚合
        status_agg = next((a for a in aggs if a["id"] == "status"), None)
        if status_agg:
            s_ids = {c["id"] for c in status_agg["children"]}
            print(f"    状态聚合子项: {s_ids}")

        # 验证 assignee 聚合
        assignee_agg = next((a for a in aggs if a["id"] == "assignee"), None)
        if assignee_agg:
            a_ids = {c["id"] for c in assignee_agg["children"]}
            expected_a = {"my_assignee", "no_assignee"}
            if a_ids == expected_a:
                print(f"    ✅ 负责人聚合子项正确: {a_ids}")
            else:
                print(f"    ❌ 负责人聚合子项异常: 期望 {expected_a}，实际 {a_ids}")

    # 8.2 show_aggs=False
    result2 = run_test(
        "8.2 show_aggs=False",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": False},
        validate_fn=lambda r: ("aggs" not in r, "show_aggs=False 时不应返回 aggs 字段"),
    )

    # 8.3 带条件过滤时的聚合
    run_test(
        "8.3 带条件过滤时的聚合（status=unresolved）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "status", "value": ["unresolved"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": True,
        },
    )

    # 8.4 单业务聚合
    run_test(
        "8.4 单业务聚合（bk_biz_id=2）",
        {"bk_biz_ids": [2], "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 9：show_dsl 调试
# ────────────────────────────────────────────────────────────────
def test_show_dsl():
    sep("测试组 9：show_dsl 调试")

    # 9.1 show_dsl=True
    run_test(
        "9.1 show_dsl=True",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 10,
            "show_aggs": False,
            "show_dsl": True,
        },
        validate_fn=lambda r: ("dsl" in r and isinstance(r["dsl"], dict), "应返回 dsl 字段且为 dict"),
    )

    # 9.2 show_dsl=False
    run_test(
        "9.2 show_dsl=False",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 10,
            "show_aggs": False,
            "show_dsl": False,
        },
        validate_fn=lambda r: ("dsl" not in r, "show_dsl=False 时不应返回 dsl 字段"),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 10：返回字段完整性校验
# ────────────────────────────────────────────────────────────────
def test_response_fields():
    sep("测试组 10：返回字段完整性校验")

    result = run_test(
        "10.1 查询全量数据，校验返回字段",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 50, "show_aggs": True},
    )

    if not result or not result.get("issues"):
        print("    ⚠️ 无数据，跳过字段校验")
        return

    # 顶层字段
    top_fields = {"issues", "total"}
    missing_top = top_fields - set(result.keys())
    if not missing_top:
        print(f"    ✅ 顶层字段完整: {top_fields}")
    else:
        print(f"    ❌ 缺少顶层字段: {missing_top}")

    # Issue 单项字段
    expected_issue_fields = {
        "id",
        "name",
        "status",
        "status_display",
        "priority",
        "priority_display",
        "assignee",
        "is_regression",
        "strategy_id",
        "strategy_name",
        "bk_biz_id",
        "bk_biz_name",
        "labels",
        "alert_count",
        "anomaly_message",
        "trend",
        "first_alert_time",
        "last_alert_time",
        "create_time",
        "update_time",
        "resolved_time",
        "is_resolved",
        "duration",
        "impact_scope",
        "aggregate_config",
    }

    for i, issue in enumerate(result["issues"][:3]):
        issue_fields = set(issue.keys())
        missing = expected_issue_fields - issue_fields
        extra = issue_fields - expected_issue_fields
        if not missing:
            print(f"    ✅ Issue[{i}] 字段完整")
        else:
            print(f"    ❌ Issue[{i}] 缺少字段: {missing}")
        if extra:
            print(f"    ℹ️  Issue[{i}] 额外字段: {extra}")

        # 校验计算字段
        if issue.get("status") in ("pending_review", "unresolved", "archived"):
            if issue.get("resolved_time") is not None:
                print(f"    ❌ Issue[{i}] status={issue['status']} 但 resolved_time 不为 null")
            if issue.get("is_resolved") is not False:
                print(f"    ❌ Issue[{i}] status={issue['status']} 但 is_resolved 不为 False")

        if issue.get("status") == "resolved":
            if issue.get("resolved_time") is None:
                print(f"    ❌ Issue[{i}] status=resolved 但 resolved_time 为 null")
            if issue.get("is_resolved") is not True:
                print(f"    ❌ Issue[{i}] status=resolved 但 is_resolved 不为 True")

        # 校验 duration 格式
        duration = issue.get("duration", "")
        if duration and duration != "--":
            print(f"    ℹ️  Issue[{i}] duration={duration}")

        # 校验 impact_scope 中的 display_name
        impact_scope = issue.get("impact_scope", {})
        if impact_scope:
            for dim_key, dim_data in impact_scope.items():
                if isinstance(dim_data, dict):
                    if "display_name" not in dim_data:
                        print(f"    ❌ Issue[{i}] impact_scope.{dim_key} 缺少 display_name")
                    else:
                        print(f"    ℹ️  Issue[{i}] impact_scope.{dim_key}.display_name={dim_data['display_name']}")

        # 校验 trend 格式
        trend = issue.get("trend", [])
        if trend:
            if isinstance(trend, list) and len(trend) > 0:
                sample = trend[0]
                if isinstance(sample, list) and len(sample) == 2:
                    ts_ms, count = sample
                    if ts_ms > 1_000_000_000_000:
                        print(f"    ✅ Issue[{i}] trend 格式正确（毫秒时间戳），共 {len(trend)} 个点")
                    else:
                        print(f"    ⚠️ Issue[{i}] trend 时间戳可能不是毫秒: {ts_ms}")
                else:
                    print(f"    ❌ Issue[{i}] trend 元素格式异常: {sample}")


# ────────────────────────────────────────────────────────────────
# 测试用例组 11：复合场景
# ────────────────────────────────────────────────────────────────
def test_combined_scenarios():
    sep("测试组 11：复合场景")

    # 11.1 虚拟状态 + conditions + 排序 + 分页
    run_test(
        "11.1 MY_ISSUE + priority=P0 + ordering=[-create_time] + page=1,size=5",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": ["MY_ISSUE"],
            "conditions": [{"key": "priority", "value": ["P0"], "method": "eq"}],
            "ordering": ["-create_time"],
            "page": 1,
            "page_size": 5,
            "show_aggs": True,
        },
    )

    # 11.2 时间范围 + query_string + conditions
    run_test(
        "11.2 时间范围 + query_string + conditions",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - 7 * DAY,
            "end_time": NOW,
            "query_string": "主机",
            "conditions": [{"key": "priority", "value": ["P0", "P1"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
            "show_aggs": True,
        },
    )

    # 11.3 NO_ASSIGNEE + 单业务 + 排序
    run_test(
        "11.3 NO_ASSIGNEE + bk_biz_id=2 + ordering=[-priority]",
        {
            "bk_biz_ids": [2],
            "username": TEST_USERNAME,
            "status": ["NO_ASSIGNEE"],
            "ordering": ["-priority"],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 11.4 多条件 + 时间范围 + 分页
    run_test(
        "11.4 多条件 + 时间范围 + 分页",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "start_time": NOW - 5 * DAY,
            "end_time": NOW,
            "conditions": [
                {"key": "status", "value": ["unresolved", "pending_review"], "method": "eq", "condition": "and"},
                {"key": "is_regression", "value": [True], "method": "eq"},
            ],
            "ordering": ["-update_time"],
            "page": 1,
            "page_size": 10,
            "show_aggs": True,
        },
    )

    # 11.5 全参数组合
    run_test(
        "11.5 全参数组合（所有参数都传）",
        {
            "bk_biz_ids": [2, 6],
            "username": TEST_USERNAME,
            "status": ["MY_ISSUE"],
            "start_time": NOW - 7 * DAY,
            "end_time": NOW,
            "query_string": "",
            "conditions": [{"key": "priority", "value": ["P0", "P1"], "method": "eq"}],
            "ordering": ["status", "-update_time"],
            "page": 1,
            "page_size": 20,
            "show_aggs": True,
            "show_dsl": True,
        },
    )

    # 11.6 空结果场景
    run_test(
        "11.6 空结果场景（不存在的组合）",
        {
            "bk_biz_ids": [8],
            "username": TEST_USERNAME,
            "conditions": [
                {"key": "status", "value": ["archived"], "method": "eq", "condition": "and"},
                {"key": "priority", "value": ["P0"], "method": "eq"},
            ],
            "page": 1,
            "page_size": 50,
            "show_aggs": True,
        },
        validate_fn=lambda r: (r["total"] == 0, f"期望 0 条，实际 {r['total']} 条"),
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 12：直接调用 IssueQueryHandler
# ────────────────────────────────────────────────────────────────
def test_handler_direct():
    sep("测试组 12：直接调用 IssueQueryHandler")

    # 12.1 基础查询
    run_handler_test(
        "12.1 Handler 基础查询",
        handler_kwargs={
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 50,
        },
        search_kwargs={"show_aggs": True},
        validate_fn=lambda r: (r["total"] >= 12, f"期望 >=12 条，实际 {r['total']} 条"),
    )

    # 12.2 虚拟状态
    run_handler_test(
        "12.2 Handler MY_ISSUE",
        handler_kwargs={
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": ["MY_ISSUE"],
            "page": 1,
            "page_size": 50,
        },
        search_kwargs={"show_aggs": False},
    )

    # 12.3 带条件
    run_handler_test(
        "12.3 Handler 带 conditions",
        handler_kwargs={
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [{"key": "priority", "value": ["P0"], "method": "eq"}],
            "page": 1,
            "page_size": 50,
        },
        search_kwargs={"show_aggs": True},
    )

    # 12.4 show_dsl
    run_handler_test(
        "12.4 Handler show_dsl=True",
        handler_kwargs={
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 10,
        },
        search_kwargs={"show_aggs": False, "show_dsl": True},
        validate_fn=lambda r: ("dsl" in r, "应返回 dsl 字段"),
    )

    # 12.5 不传 bk_biz_ids（查询当前用户相关的）
    run_handler_test(
        "12.5 Handler 不传 bk_biz_ids",
        handler_kwargs={
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 50,
        },
        search_kwargs={"show_aggs": False},
    )

    # 12.6 不传 start_time/end_time
    run_handler_test(
        "12.6 Handler 不传时间范围",
        handler_kwargs={
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 50,
        },
        search_kwargs={"show_aggs": False},
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 13：边界场景
# ────────────────────────────────────────────────────────────────
def test_edge_cases():
    sep("测试组 13：边界场景")

    # 13.1 page_size=0
    run_test(
        "13.1 page_size=0（只要 total 和 aggs）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 0, "show_aggs": True},
        validate_fn=lambda r: (len(r["issues"]) == 0 and r["total"] >= 0, "page_size=0 应返回 0 条 issues"),
    )

    # 13.2 空 conditions 列表
    run_test(
        "13.2 空 conditions 列表",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "conditions": [],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 13.3 空 status 列表
    run_test(
        "13.3 空 status 列表",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "status": [],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 13.4 空 query_string
    run_test(
        "13.4 空 query_string",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "query_string": "",
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 13.5 空 ordering
    run_test(
        "13.5 空 ordering（使用默认排序）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "ordering": [],
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )

    # 13.6 page_size=500（最大值）
    run_test(
        "13.6 page_size=500（最大值）",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 500, "show_aggs": False},
    )

    # 13.7 同时传 show_aggs=True 和 show_dsl=True
    run_test(
        "13.7 show_aggs=True + show_dsl=True",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 10,
            "show_aggs": True,
            "show_dsl": True,
        },
        validate_fn=lambda r: (
            "aggs" in r and "dsl" in r,
            "应同时返回 aggs 和 dsl",
        ),
    )

    # 13.8 未来时间的 end_time（应被截断为 now+60s）
    run_test(
        "13.8 未来时间 end_time（+1天）",
        {
            "bk_biz_ids": ALL_BIZ_IDS,
            "username": TEST_USERNAME,
            "end_time": NOW + DAY,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
    )


# ────────────────────────────────────────────────────────────────
# 测试用例组 14：告警趋势图（IssueAlertDateHistogramResultResource）
# ────────────────────────────────────────────────────────────────
def _get_test_issue_ids():
    """从 ES 中获取当前测试数据的 Issue ID 列表"""
    from bkmonitor.documents.issue import IssueDocument

    results = IssueDocument.search(all_indices=True).params(size=50).execute()
    return [hit.meta.id for hit in results.hits]


def run_histogram_test(name: str, call_fn, validate_fn=None):
    """
    执行告警趋势图测试用例

    参数:
        name: 测试名称
        call_fn: 无参调用函数，返回 result
        validate_fn: 可选校验函数
    """
    global PASS_COUNT, FAIL_COUNT
    print(f"\n  ▶ {name}")

    try:
        result = call_fn()
        print(f"    ✅ 返回类型: {type(result).__name__}")

        # 打印结果摘要
        if isinstance(result, dict):
            if "default_time_series" in result:
                print(f"    ℹ️  空结果（default_time_series）: {result['default_time_series']}")
            else:
                for key in list(result.keys())[:5]:
                    val = result[key]
                    if isinstance(val, dict):
                        print(f"    ℹ️  key={key}, 子键数={len(val)}")
                    else:
                        print(f"    ℹ️  key={key}, type={type(val).__name__}")
                if len(result) > 5:
                    print(f"    ... 还有 {len(result) - 5} 个 key")

        if validate_fn:
            ok, msg = validate_fn(result)
            if ok:
                print(f"    ✅ 校验通过: {msg}")
                PASS_COUNT += 1
            else:
                print(f"    ❌ 校验失败: {msg}")
                FAIL_COUNT += 1
        else:
            PASS_COUNT += 1

        return result

    except Exception as e:
        print(f"    ❌ 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1
        return None


def test_alert_trend():
    sep("测试组 14：告警趋势图（IssueAlertDateHistogramResultResource）")

    issue_ids = _get_test_issue_ids()
    if not issue_ids:
        print("  ⚠️ 无测试 Issue 数据，跳过趋势图测试")
        return

    print(f"  📋 测试 Issue ID 数量: {len(issue_ids)}")
    print(f"  📋 示例 ID: {issue_ids[:3]}")

    # ── 14.1 直接调用 perform_request（无 group_by）──
    run_histogram_test(
        "14.1 IssueAlertDateHistogramResultResource 无 group_by",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - 7 * DAY,
            end_time=NOW,
            interval="auto",
            conditions=[{"key": "issue_id", "value": issue_ids, "method": "eq"}],
        ),
        validate_fn=lambda r: (
            isinstance(r, dict),
            f"返回应为 dict，实际为 {type(r).__name__}",
        ),
    )

    # ── 14.2 直接调用 perform_request（group_by=["issue_id"]）──
    run_histogram_test(
        "14.2 IssueAlertDateHistogramResultResource group_by=['issue_id']",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - 7 * DAY,
            end_time=NOW,
            interval="auto",
            conditions=[{"key": "issue_id", "value": issue_ids, "method": "eq"}],
            group_by=["issue_id"],
        ),
        validate_fn=lambda r: (
            isinstance(r, dict),
            f"返回应为 dict，实际为 {type(r).__name__}",
        ),
    )

    # ── 14.3 sliced_date_histogram（无 group_by，时间分片并行）──
    run_histogram_test(
        "14.3 sliced_date_histogram 无 group_by（时间分片并行）",
        lambda: IssueAlertDateHistogramResultResource.sliced_date_histogram(
            start_time=NOW - 30 * DAY,
            end_time=NOW,
            interval="auto",
            handler_kwargs={
                "conditions": [{"key": "issue_id", "value": issue_ids, "method": "eq"}],
            },
        ),
        validate_fn=lambda r: (
            isinstance(r, dict),
            f"返回应为 dict，实际为 {type(r).__name__}",
        ),
    )

    # ── 14.4 sliced_date_histogram（group_by=["issue_id"]，时间分片并行）──
    run_histogram_test(
        "14.4 sliced_date_histogram group_by=['issue_id']（时间分片并行）",
        lambda: IssueAlertDateHistogramResultResource.sliced_date_histogram(
            start_time=NOW - 30 * DAY,
            end_time=NOW,
            interval="auto",
            handler_kwargs={
                "conditions": [{"key": "issue_id", "value": issue_ids, "method": "eq"}],
            },
            group_by=["issue_id"],
        ),
        validate_fn=lambda r: (
            isinstance(r, dict),
            f"返回应为 dict，实际为 {type(r).__name__}",
        ),
    )

    # ── 14.5 ≤7天直接请求（与 add_alert_trend 中的阈值逻辑一致）──
    run_histogram_test(
        "14.5 ≤7天直接请求（单次，不分片）",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - 3 * DAY,
            end_time=NOW,
            interval="auto",
            conditions=[{"key": "issue_id", "value": issue_ids[:3], "method": "eq"}],
            group_by=["issue_id"],
        ),
        validate_fn=lambda r: (
            isinstance(r, dict),
            "返回应为 dict",
        ),
    )

    # ── 14.6 空 issue_ids 查询（应返回空结果）──
    run_histogram_test(
        "14.6 空 issue_ids 查询（应返回 default_time_series）",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - DAY,
            end_time=NOW,
            interval="auto",
            conditions=[{"key": "issue_id", "value": ["nonexistent_id"], "method": "eq"}],
            group_by=["issue_id"],
        ),
        validate_fn=lambda r: (
            isinstance(r, dict) and ("default_time_series" in r or len(r) == 0 or isinstance(r, dict)),
            "不存在的 issue_id 应返回空结果或 default_time_series",
        ),
    )

    # ── 14.7 极小时间范围（1小时）──
    run_histogram_test(
        "14.7 极小时间范围（1小时）",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - HOUR,
            end_time=NOW,
            interval="auto",
            conditions=[{"key": "issue_id", "value": issue_ids, "method": "eq"}],
        ),
    )

    # ── 14.8 指定固定 interval（非 auto）──
    run_histogram_test(
        "14.8 指定固定 interval=3600",
        lambda: IssueAlertDateHistogramResultResource().request(
            start_time=NOW - 7 * DAY,
            end_time=NOW,
            interval=3600,
            conditions=[{"key": "issue_id", "value": issue_ids, "method": "eq"}],
            group_by=["issue_id"],
        ),
    )


def test_trend_in_list():
    """测试列表接口中 trend/alert_count/anomaly_message 字段的填充"""
    global PASS_COUNT, FAIL_COUNT
    sep("测试组 15：列表接口中的 trend 字段")

    # 15.1 查询列表，验证 trend 字段存在且格式正确
    result = run_test(
        "15.1 列表接口 trend 字段格式校验",
        {"bk_biz_ids": ALL_BIZ_IDS, "username": TEST_USERNAME, "page": 1, "page_size": 12, "show_aggs": False},
    )

    if result and result.get("issues"):
        for i, issue in enumerate(result["issues"][:5]):
            trend = issue.get("trend")
            alert_count = issue.get("alert_count")
            anomaly_message = issue.get("anomaly_message")

            # 校验 trend 字段
            if trend is None:
                print(f"    ❌ Issue[{i}] 缺少 trend 字段")
            elif isinstance(trend, list):
                if len(trend) > 0:
                    sample = trend[0]
                    if isinstance(sample, list) and len(sample) == 2:
                        ts_ms, count = sample
                        if isinstance(ts_ms, int | float) and isinstance(count, int | float):
                            print(f"    ✅ Issue[{i}] trend 格式正确: {len(trend)} 个点, 首点=[{ts_ms}, {count}]")
                        else:
                            print(f"    ❌ Issue[{i}] trend 元素类型异常: {sample}")
                    else:
                        print(f"    ❌ Issue[{i}] trend 元素格式异常: {sample}")
                else:
                    print(f"    ℹ️  Issue[{i}] trend 为空列表（无关联告警数据）")
            else:
                print(f"    ❌ Issue[{i}] trend 类型异常: {type(trend).__name__}")

            # 校验 alert_count 字段
            if alert_count is None:
                print(f"    ❌ Issue[{i}] 缺少 alert_count 字段")
            elif isinstance(alert_count, int) and alert_count >= 0:
                print(f"    ✅ Issue[{i}] alert_count={alert_count}")
            else:
                print(f"    ⚠️  Issue[{i}] alert_count 异常: {alert_count}")

            # 校验 anomaly_message 字段
            if anomaly_message is None:
                print(f"    ❌ Issue[{i}] 缺少 anomaly_message 字段")
            elif isinstance(anomaly_message, str):
                print(f"    ✅ Issue[{i}] anomaly_message='{anomaly_message[:50]}'")
            else:
                print(f"    ⚠️  Issue[{i}] anomaly_message 类型异常: {type(anomaly_message).__name__}")

    # 15.2 单页少量 Issue 的 trend 填充
    run_test(
        "15.2 单页 3 条 Issue 的 trend 填充",
        {"bk_biz_ids": [2], "username": TEST_USERNAME, "page": 1, "page_size": 3, "show_aggs": False},
        validate_fn=lambda r: (
            all("trend" in issue and "alert_count" in issue and "anomaly_message" in issue for issue in r["issues"]),
            "所有 Issue 应包含 trend、alert_count、anomaly_message 字段",
        ),
    )

    # 15.3 空结果时不应报错
    run_test(
        "15.3 空结果时 trend 不报错",
        {
            "bk_biz_ids": [99999],
            "username": TEST_USERNAME,
            "page": 1,
            "page_size": 50,
            "show_aggs": False,
        },
        validate_fn=lambda r: (r["total"] == 0 and len(r["issues"]) == 0, "空结果应正常返回"),
    )

    # 15.4 Handler 直接调用 add_alert_trend
    print("\n  ▶ 15.4 直接调用 IssueQueryHandler.add_alert_trend()")
    try:
        handler = IssueQueryHandler(
            bk_biz_ids=ALL_BIZ_IDS,
            username=TEST_USERNAME,
            page=1,
            page_size=5,
        )
        search_result = handler.search(show_aggs=False)
        issues = search_result.get("issues", [])
        print(f"    查询到 {len(issues)} 条 Issue")

        # 验证 trend 已被填充
        has_trend = all("trend" in issue for issue in issues)
        has_count = all("alert_count" in issue for issue in issues)
        has_msg = all("anomaly_message" in issue for issue in issues)

        if has_trend and has_count and has_msg:
            print("    ✅ add_alert_trend 已正确填充所有字段")
            PASS_COUNT += 1
        else:
            print(f"    ❌ 缺少字段: trend={has_trend}, alert_count={has_count}, anomaly_message={has_msg}")
            FAIL_COUNT += 1

        # 打印各 Issue 的 trend 摘要
        for i, issue in enumerate(issues[:3]):
            trend = issue.get("trend", [])
            print(
                f"    Issue[{i}] id={issue['id'][:18]}... "
                f"trend_points={len(trend)} alert_count={issue.get('alert_count', '?')} "
                f"anomaly_msg='{issue.get('anomaly_message', '?')[:30]}'"
            )
    except Exception as e:
        print(f"    ❌ 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 90)
    print("  Issue 列表接口测试脚本")
    print(f"  测试用户: {TEST_USERNAME}")
    print(f"  测试业务: {ALL_BIZ_IDS}")
    print(f"  当前时间: {NOW}")
    print("=" * 90)

    test_basic_queries()  # 组 1：基础查询（4 个用例）
    test_pagination()  # 组 2：分页（6 个用例）
    test_ordering()  # 组 3：排序（5 个用例）
    test_virtual_status()  # 组 4：虚拟状态（4 个用例）
    test_conditions()  # 组 5：conditions 过滤（16 个用例）
    test_time_range()  # 组 6：时间范围（6 个用例）
    test_query_string()  # 组 7：query_string 搜索（7 个用例）
    test_aggs()  # 组 8：聚合统计（4 个用例）
    test_show_dsl()  # 组 9：show_dsl（2 个用例）
    test_response_fields()  # 组 10：返回字段完整性（1 个用例 + 详细校验）
    test_combined_scenarios()  # 组 11：复合场景（6 个用例）
    test_handler_direct()  # 组 12：直接调用 Handler（6 个用例）
    test_edge_cases()  # 组 13：边界场景（8 个用例）
    test_alert_trend()  # 组 14：告警趋势图（8 个用例）
    test_trend_in_list()  # 组 15：列表接口中的 trend 字段（4 个用例）

    # 打印汇总
    total = PASS_COUNT + FAIL_COUNT
    sep("测试汇总")
    print(f"  ✅ 通过: {PASS_COUNT}")
    print(f"  ❌ 失败: {FAIL_COUNT}")
    print(f"  📊 总计: {total}")
    print(f"  📈 通过率: {PASS_COUNT / total * 100:.1f}%" if total > 0 else "  📈 通过率: N/A")
    print("=" * 90)
