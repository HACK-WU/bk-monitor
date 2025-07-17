import requests
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

cookie = Path("grafana/cookie").read_text().strip()
url = Path("grafana/url").read_text().strip()

headers = {}


def get_promqls():
    with open("grafana/promqls.json") as f:
        return json.load(f)


def search(json_data):
    response = requests.post(url, headers=headers, json=json_data, verify=False)
    return response.json()


def strip_outer_quotes(s):
    """安全移除外层引号"""
    if not isinstance(s, str):
        return s
    s = s.strip()

    while len(s) > 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
        s = s.strip()

    return s


def get_param():
    # 获取params参数
    #  grep "\-\-data-raw" curls | cut -c13-  > ./params
    params = []
    with open("grafana/params") as f:
        for line in f:
            line = line.strip().replace("^", "").replace("&", "")
            line = strip_outer_quotes(line)
            line = line.replace(r"\"", '"').replace(r'\\"', r"\"")
            try:
                line = line.replace("false", "False").replace("true", "True")
                params.append(eval(line))
            except Exception:
                print(line)
                raise

    with open("grafana/formated_params.json", "w") as f:
        json.dump(params, f, indent=4)

    return params


def main():
    titles = list()
    exited_titles = set()

    has_data = set()
    no_data = set()

    panel_id_title_map = get_promqls()

    not_found = set()
    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = {}
        count = 0
        max_count = -1

        for param in get_param():
            for query in param.get("queries", []):
                panel_id = query["requestId"][0:-1]
                headers["x-panel-id"] = panel_id
                title = panel_id_title_map.get(panel_id, None)
                if not title:
                    not_found.add(panel_id)
                    continue

                if title not in exited_titles:
                    titles.append(title)
                    exited_titles.add(title)
                else:
                    continue
                futures[executor.submit(search, param)] = title
                count += 1
                if max_count >= 0 and count > max_count:
                    break
            if max_count >= 0 and count > max_count:
                break

        for future in as_completed(futures):
            data = future.result()
            title = futures[future]
            for key, value in data["results"].items():
                if not value["frames"]:
                    no_data.add(title)
                else:
                    has_data.add(title)

    data_json = {"has_data": list(), "no_data": list()}

    for title in titles:
        if title in has_data:
            data_json["has_data"].append(title)
        else:
            data_json["no_data"].append(title)

    with open("grafana/grafana_data.json", "w") as f:
        json.dump(data_json, f, indent=4, ensure_ascii=False)

    print("not found promqls:", len(not_found))
    print("has data:", len(has_data))
    print("no data:", len(no_data))

    print("\nResponse saved to 'grafana_data.json'")


main()
