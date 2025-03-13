import sys
from collections import defaultdict

from django.core.management.base import BaseCommand

from bkmonitor.models.strategy import QueryConfigModel


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, default=-1, help="追加的area_id")
        parser.add_argument("-n", "--num", type=str, default="0", help="指定要更新的策略数量，'all',表示全部更新")

    def handle(self, *args, **options):
        print(update_i_zone_area_id.__doc__)
        num = -1 if options["num"] == "all" else options["num"]
        update_i_zone_area_id(options["id"], num)


def update_i_zone_area_id(area_id, num=0):
    """
    更新iZoneAreaID
    usages:
        python manage.py update_i_zone_area_id  # 查看所有需要被更新的策略
        python manage.py update_i_zone_area_id --id 6 -n 1  # 追加area_id=6，更新1条策略
        python manage.py update_i_zone_area_id --id 6 -n all  # 追加area_id=6，更新所有策略
    """
    try:
        area_id = int(area_id)
        num = int(num)
    except Exception:
        raise TypeError("area_id和num必须是整数")

    query_config = QueryConfigModel.objects.all().order_by("strategy_id").only("strategy_id", "config")

    def valid_condition(condition):
        # iZoneAreaID(iZoneAreaID)=1,2 或者 iZoneAreaIDStr(iZoneAreaIDStr)=1,2 时将会被更新
        key = condition.get("key", "")
        value = condition.get("value", [])
        if not isinstance(value, list):
            return False
        try:
            value = list(map(int, value))
        except ValueError:
            return False
        return (
            key in ["iZoneAreaID(iZoneAreaID)", "iZoneAreaIDStr(iZoneAreaIDStr)"]
            and len(value) == 2
            and 1 in value
            and 2 in value
        )

    # step1: 查询出所有要被更新的策略和query_config
    strategy_qc_mapping = defaultdict(list)
    for qc in query_config:
        agg_condition = qc.config.get("agg_condition", [])
        for c in agg_condition:
            if valid_condition(c):
                strategy_qc_mapping[qc.strategy_id].append(qc)

    # step2: 如果num等于0，则表示不更新，这里打印出要更新的策略的ID和聚合条件配置信息
    if num == 0:
        print(f"总共有{len(strategy_qc_mapping)}个策略需要被更新:")
        for strategy_id, qc_list in strategy_qc_mapping.items():
            message = [f"Strategy ID: {strategy_id},condition: "]
            for qc in qc_list:
                agg_condition = qc.config.get("agg_condition", [])
                for c in agg_condition:
                    if valid_condition(c):
                        message.append(f"{c.get('key')}={c.get('value')},")
            print("".join(message)[:-1])
        print("执行完毕")
        sys.exit(0)

    # step3: 更新query_config
    if area_id <= 0:
        raise ValueError("area_id must be greater than 0")

    count = 0
    qc_to_update = []
    updated_strategies = []
    for strategy_id, qc_list in strategy_qc_mapping.items():
        # 控制更新数量
        # num=-1 表示不限制
        if num != -1 and count >= num:
            break

        for qc in qc_list:
            agg_condition = qc.config.get("agg_condition", [])
            for c in agg_condition:
                # 追加新的area_id
                c["value"].append(area_id)
            qc_to_update.append(qc)
        updated_strategies.append(strategy_id)
        count += 1

    # 批量更新
    QueryConfigModel.objects.bulk_update(qc_to_update, ["config"])
    print(f"本次更新了{count}条策略,策略ID为:")
    print(updated_strategies)
    print("执行完毕")
