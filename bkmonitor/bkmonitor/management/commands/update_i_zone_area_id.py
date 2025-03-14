import sys
from collections import defaultdict
from typing import Dict

from django.core.management.base import BaseCommand

from bkmonitor.models.strategy import QueryConfigModel, StrategyModel


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, default=-1, help="追加的area_id")
        parser.add_argument("-n", "--num", type=str, default="0", help="指定要更新的策略数量，'all',表示全部更新")
        parser.add_argument("-b", "--biz", nargs="+", type=int, default=[], help="指定业务ID,多个业务ID用空格分隔,不指定业务则更新所有业务")

    def handle(self, *args, **options):
        print(update_i_zone_area_id.__doc__)
        num = -1 if options["num"] == "all" else options["num"]
        if num != "0" and options["id"] == -1:
            print("需要指定追加的area_id,使用--id参数")
            sys.exit(1)
        update_i_zone_area_id(options["id"], options["biz"], num)


def valid_condition(condition):
    key = condition.get("key", "")
    value = condition.get("value", [])
    fields = ["iZoneAreaID", "iZoneAreaIDStr", "iZoneAreaID(iZoneAreaID)", "iZoneAreaIDStr(iZoneAreaIDStr)"]
    values = [{1, 2}, {1}, {2}]
    if not isinstance(value, list):
        return False
    try:
        value = set(map(int, value))
    except (ValueError, TypeError):
        return False
    return key in fields and value in values


def update_i_zone_area_id(area_id, biz, num=0):
    """
    更新iZoneAreaID
    usages:
        python manage.py update_i_zone_area_id   # 预览所有业务下需要被更新的策略
        python manage.py update_i_zone_area_id --biz 2 # 预览2业务下所有需要被更新的策略
        python manage.py update_i_zone_area_id --id 6 --biz 2 -n 1  # 追加area_id=6，更新2业务下的1条策略
        python manage.py update_i_zone_area_id --id 6 --biz 2 3 -n all  # 追加area_id=6，更新2和3业务下的所有策略
    """
    try:
        area_id = int(area_id)
        num = int(num)
    except Exception:
        raise TypeError("area_id和num必须是整数")

    query_config = QueryConfigModel.objects.all().only("strategy_id", "config")

    # step1: 查询出所有要被更新的策略和query_config
    strategy_qc_mapping: Dict[int, Dict] = defaultdict(lambda: {"qc": None, "conditions": []})
    for qc in query_config:
        agg_condition = qc.config.get("agg_condition", [])
        for condition in agg_condition:
            if valid_condition(condition):
                strategy_qc_mapping[qc.strategy_id]["qc"] = qc
                strategy_qc_mapping[qc.strategy_id]["conditions"].append(condition)

    # step2: 过滤出指定业务的策略
    filter_dict = {"id__in": list(strategy_qc_mapping.keys())}
    if biz:
        filter_dict["bk_biz_id__in"] = biz
    strategies = StrategyModel.objects.filter(**filter_dict).only("id", "bk_biz_id")
    # 构建strategy_id到biz_id的映射
    strategy_biz_mapping = {s.id: s.bk_biz_id for s in strategies}
    if not strategy_biz_mapping:
        print("没有找到符合条件的策略")
        return

    # step3: 如果num等于0，则表示不更新，这里打印出要更新的策略的ID和聚合条件配置信息
    if num == 0:
        print(f"总共有{len(strategy_biz_mapping)}个策略需要被更新:")
        for strategy_id, biz_id in strategy_biz_mapping.items():
            message = [f"Strategy ID: {strategy_id}, biz_id:{biz_id}, condition: "]
            for c in strategy_qc_mapping[strategy_id]["conditions"]:
                message.append(f"{c.get('key')}={c.get('value')},")
            print("".join(message).strip(","))
        print("预览完毕")
        return

    # step4: 更新query_config
    count = 0
    qc_to_update = []
    updated_strategies = []
    for strategy_id in strategy_biz_mapping:
        # 控制更新数量
        # num=-1 表示不限制
        if num != -1 and count >= num:
            break

        d = strategy_qc_mapping[strategy_id]
        for c in d["conditions"]:
            c["value"].append(area_id)
        qc_to_update.append(d["qc"])
        updated_strategies.append(strategy_id)
        count += 1

    # 批量更新
    QueryConfigModel.objects.bulk_update(qc_to_update, ["config"])
    print(f"本次更新了{count}条策略")
    for strategy_id in updated_strategies:
        message = [f"Strategy ID: {strategy_id}, biz_id:{strategy_biz_mapping[strategy_id]}, condition: "]
        for c in strategy_qc_mapping[strategy_id]["conditions"]:
            message.append(f"{c.get('key')}={c.get('value')},")
        print("".join(message).strip(","))
    print("执行完毕")
