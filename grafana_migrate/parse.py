import json
from itertools import chain


def get_grafana_data():
    with open("./grafana/grafana_data.json") as f:
        return json.load(f)


def get_monitor_data():
    with open("./monitor/grafana_data.json") as f:
        return json.load(f)


def parse():
    grafana_data = get_grafana_data()
    monitor_data = get_monitor_data()

    count = 0
    all_data = {}

    for data in chain(
        grafana_data["no_data"], monitor_data["no_data"], grafana_data["has_data"], monitor_data["has_data"]
    ):
        all_data[data] = count
        count += 1

    grafana_no_data = set(grafana_data["no_data"])
    grafana_has_data = set(grafana_data["has_data"])

    monitor_no_data = set(monitor_data["no_data"])
    monitor_has_data = set(monitor_data["has_data"])

    res = {
        "description_uncertain": "待定：两边都没有数据",
        "description_abnormal": "异常：monitor没有数据，grafana有数据",
    }

    # 待定：两边都没有数据
    uncertain = list(grafana_no_data & monitor_no_data)
    uncertain = sorted(uncertain, key=lambda x: all_data[x])

    res["uncertain"] = uncertain
    print("待定：", uncertain)

    # 异常：monitor没有数据，grafana有数据
    abnormal = list(grafana_has_data & monitor_no_data)
    abnormal = sorted(abnormal, key=lambda x: all_data[x])
    res["abnormal"] = abnormal
    print("异常：", abnormal)

    with open("./parse_result.json", "w") as f:
        json.dump(res, f, indent=4, ensure_ascii=False)


def get_monitor_inner_title():
    inner_titles = list()
    exit_titles = set()
    with open("./monitor/promqls.json") as f:
        promqls = json.load(f)
        for promql, item in promqls.items():
            title = item.get("inner_title", None)
            if title is None or title in exit_titles:
                continue
            inner_titles.append(title)
            exit_titles.add(title)
    return inner_titles


if __name__ == "__main__":
    # parse()

    print(get_monitor_inner_title())
