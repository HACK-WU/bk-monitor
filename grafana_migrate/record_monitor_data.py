import requests
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

cookie = Path("monitor/cookie").read_text().strip()
url = Path("monitor/url").read_text().strip()

headers = {}

json_data = {
    "end_time": 1752555116,
    "format": "time_series",
    "start_time": 1752511916,
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

    # # 打印响应结果
    # print(f"Status Code: {response.status_code}")
    # print("Response Body:")
    # print(response.json())
    return response.json()["data"]


titles = list()
exited_titles = set()

has_data = set()
no_data = set()

promqls = get_promqls()

pool = ThreadPoolExecutor(40)

with ThreadPoolExecutor(max_workers=40) as executor:
    futures = {}
    count = 0
    for p, info in promqls.items():
        title = info["inner_title"]
        if title not in exited_titles:
            titles.append(title)
            exited_titles.add(title)
        else:
            continue
        futures[executor.submit(search, p)] = title
        count += 1
        # if count > 10:
        #     break

    for future in as_completed(futures):
        data = future.result()
        title = futures[future]
        if data["series"] == []:
            no_data.add(title)
        else:
            has_data.add(title)


data_json = {"has_data": list(), "no_data": list()}

for title in titles:
    if title in has_data:
        data_json["has_data"].append(title)
    else:
        data_json["no_data"].append(title)


with open("monitor/grafana_data.json", "w") as f:
    json.dump(data_json, f, indent=4, ensure_ascii=False)


print("\nResponse saved to 'data.json'")
