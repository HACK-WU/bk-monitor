import requests
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

cookie = Path("monitor/cookie").read_text().strip()
config = Path("monitor/config.json").read_text().strip()
config = json.loads(config)
url = config["graph_promql_query"]
headers = config["headers"]
headers["cookie"] = cookie

json_data = {
    "end_time": 1752810591,
    "format": "time_series",
    "start_time": 1752788991,
    "step": "auto",
    "type": "range",
    "bk_biz_id": "455",
}


def get_promqls():
    with open("monitor/promqls.json") as f:
        return json.load(f)


def search(promql):
    json_data["promql"] = promql
    response = requests.post(url, headers=headers, json=json_data, verify=False)

    data = response.json()
    if response.status_code != 200 or data["result"] != True:
        data["origin_json_data"] = json_data
        data = json.dumps(data, ensure_ascii=False)
        raise Exception(f"Request failed: {data}")

    return data


def record_data():
    titles = list()
    exited_titles = set()
    has_data = set()
    no_data = set()

    promqls = get_promqls()

    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = {}
        count = 0
        max_count = -1
        for p, info in promqls.items():
            title = info.get("inner_title", None)
            if not title:
                continue
            if title not in exited_titles:
                titles.append(title)
                exited_titles.add(title)
            else:
                continue
            futures[executor.submit(search, p)] = title
            count += 1
            if max_count != -1 and count > max_count:
                break

        for future in as_completed(futures):
            response = future.result()
            try:
                data = response["data"]
            except Exception as e:
                print(response)
                raise e
            title = futures[future]
            if data["series"] == []:
                no_data.add(title)
            else:
                has_data.add(title)

    data_json = {"has_data": list(), "no_data": list(), "total": 0}

    for title in titles:
        if title in has_data:
            data_json["has_data"].append(title)
        else:
            data_json["no_data"].append(title)

    data_json["total"] = len(titles)

    with open("monitor/grafana_data.json", "w") as f:
        json.dump(data_json, f, indent=4, ensure_ascii=False)

    print("\nResponse saved to 'data.json'")


if __name__ == "__main__":
    # get_monitor_promql()
    record_data()
    # json_data={
    #     "end_time": 1752810591,
    #     "format": "time_series",
    #     "start_time": 1752788991,
    #     "step": "auto",
    #     "type": "range",
    #     "bk_biz_id": "455",
    #     "promql": "(sum(increase(hlsvr_business_trigger_count{ bcs_cluster_id=~\"ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311\", namespace=\"ddzgamesvr-hlddz\",trigger_type=\"GameSvr-EcSysSubReason\", name=~\"$warm_game_bean_add_reason\"}[1m])) by (app) - sum(increase(hlsvr_business_trigger_count{ bcs_cluster_id=~\"ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311\", namespace=\"ddzgamesvr-hlddz\",trigger_type=\"GameSvr-EcSysSubReason\", name=~\"$warm_game_bean_minus_reason\"}[1m])) by (app)) / 10000"
    # }
    # promql=json_data["promql"]
    # res=search(promql)
    # print(res)
