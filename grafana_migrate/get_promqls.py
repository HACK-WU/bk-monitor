from pathlib import Path
import json
from get_variables import get_variables
from string import Template


class CustomTemplate(Template):
    delimiter = "$"  # 使用单个 $ 作为分隔符


def replace_variables(promql: str, variables: dict):
    if "$" not in promql:
        return promql
    promql = CustomTemplate(promql).safe_substitute(**variables)
    return promql


def get_promql(src_path, promql_key):
    setting = src_path.read_text()
    setting = json.loads(setting)

    templating = setting["dashboard"]["templating"]
    variables = get_variables(templating)

    alert_new_json = {}
    find_inner_title = set()

    def _get_promql(_panel, value):
        for target in _panel.get("targets", []):
            promql = target.get(promql_key)
            if promql:
                find_inner_title.add(value["inner_title"])
                promql = replace_variables(promql, variables)
                alert_new_json[promql] = value

    for out_panel in setting["dashboard"]["panels"]:
        out_title = out_panel["title"]
        for panel in out_panel.get("panels", []):
            item = {"out_title": out_title, "inner_title": panel["title"]}
            _get_promql(panel, item)

        item = {
            "inner_title": out_title,
        }
        _get_promql(out_panel, item)

    alert_new_json["meta"] = {
        "total_inner_title": len(find_inner_title),
    }
    return alert_new_json, find_inner_title


def get_monitor_promql():
    src_path = Path("monitor/panel_info.json")
    dest_path = Path("monitor/promqls.json")
    promql_key = "source"
    result, find_inner_title = get_promql(src_path, promql_key)

    print(len(result), f"个{promql_key}")

    with open(str(dest_path), "w") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)


def get_grafana_promql():
    src_path = Path("grafana/panel_info.json")
    dest_path = Path("grafana/promqls.json")
    src_path = src_path.read_text()
    src_path = json.loads(src_path)

    print(len(src_path["dashboard"]["panels"]), "个panels")

    def inner(panel, panel_title):
        if "title" in panel:
            _id = panel["id"]
            panel_title[_id] = panel["title"]

        if "panels" in panel:
            for _panel in panel["panels"]:
                inner(_panel, panel_title)

        return

    alert_new_json = {}
    for out_panel in src_path["dashboard"]["panels"]:
        inner(out_panel, alert_new_json)

    print(len(alert_new_json), "个panels")
    with open(str(dest_path), "w") as f:
        json.dump(alert_new_json, f, indent=4, ensure_ascii=False)
