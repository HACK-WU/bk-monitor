from pathlib import Path
import json
import requests
from string import Template

cookie = Path("monitor/cookie").read_text().strip()
config = Path("monitor/config.json").read_text().strip()
config = json.loads(config)
url = config["get_variable_value"]
headers = config["headers"]
headers["cookie"] = cookie

start_time = config["start_time"]
end_time = config["end_time"]
bk_biz_id = config["bk_biz_id"]


class CustomTemplate(Template):
    delimiter = "$"  # 使用单个 $ 作为分隔符


def search(query: dict, conf, variables):
    if not isinstance(query, dict):
        raise TypeError("query must be a dict")

    promql: str | None = query.get("query", None)
    if not promql:
        return []
    if "$" in promql:
        promql = CustomTemplate(promql).safe_substitute(variables)
        promql = promql.replace('"', r"\"")

    query_type = query.get("queryType", None)

    if not query_type:
        query_type = conf["datasource"]["type"]

    request_params = {
        "params": {
            "end_time": end_time,
            "promql": promql,
            "start_time": start_time,
        },
        "scenario": "os",
        "type": query_type,
        "bk_biz_id": bk_biz_id,
    }

    response = requests.post(url, headers=headers, json=request_params, verify=False)
    data = response.json()
    if data["result"] is not True:
        raise Exception(f"request failed, error: {data}")
    values = [item["value"] for item in data["data"]]
    return values


def get_variables(template: dict):
    variables = {}
    for conf in template.get("list", []):
        name = conf["name"]
        if isinstance(conf["query"], str):
            value = conf["query"]

        else:
            value = conf["current"]["value"]
            if value == "$__all" or "$__all" in value:
                value = search(conf["query"], conf, variables)
        variables[name] = value

    return variables


template = {
    "list": [
        {
            "current": {
                "selected": False,
                "text": "ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311",
                "value": "ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311",
            },
            "description": "",
            "hide": 2,
            "includeAll": False,
            "label": "cluster",
            "multi": False,
            "name": "cluster",
            "options": [
                {
                    "selected": True,
                    "text": "ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311",
                    "value": "ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311",
                }
            ],
            "query": "ddzgamesvr-cls-6hmd6m8l|BCS-K8S-41311",
            "queryValue": "",
            "skipUrlSync": False,
            "type": "custom",
        },
        {
            "current": {"selected": False, "text": "ddzgamesvr-hlddz", "value": "ddzgamesvr-hlddz"},
            "hide": 2,
            "includeAll": False,
            "label": "namespace",
            "multi": False,
            "name": "namespace",
            "options": [{"selected": True, "text": "ddzgamesvr-hlddz", "value": "ddzgamesvr-hlddz"}],
            "query": "ddzgamesvr-hlddz",
            "queryValue": "",
            "skipUrlSync": False,
            "type": "custom",
        },
        {
            "current": {"selected": False, "text": "cpp-sf", "value": "cpp-sf"},
            "hide": 2,
            "includeAll": False,
            "label": "apptype",
            "multi": False,
            "name": "apptype",
            "options": [{"selected": True, "text": "cpp-sf", "value": "cpp-sf"}],
            "query": "cpp-sf",
            "queryValue": "",
            "skipUrlSync": False,
            "type": "custom",
        },
        {
            "allValue": ".*",
            "current": {"selected": False, "text": "All", "value": "$__all"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": "- Blueking Monitor - 主机",
            "hide": 0,
            "includeAll": True,
            "label": "app",
            "multi": False,
            "name": "app",
            "options": [],
            "query": {},
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "allValue": "$app.*",
            "current": {"selected": False, "text": "All", "value": "$__all"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_up{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, pod)',
            "hide": 0,
            "includeAll": True,
            "label": "pod",
            "multi": False,
            "name": "pod",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_up{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, pod)',
                "query": 'label_values(hlsvr_up{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, pod)',
                "queryType": "prometheus",
            },
            "refresh": 1,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_request_duration_summary_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, url)',
            "hide": 2,
            "includeAll": True,
            "label": "url",
            "multi": True,
            "name": "url",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_request_duration_summary_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, url)',
                "query": 'label_values(hlsvr_request_duration_summary_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, url)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": False, "text": "LogCnt", "value": "LogCnt"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, trigger_type)',
            "hide": 0,
            "includeAll": False,
            "label": "事件触发量分组",
            "multi": False,
            "name": "trigger_group",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, trigger_type)',
                "query": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, trigger_type)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "/.*/",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", trigger_type="$trigger_group"},  name)',
            "hide": 0,
            "includeAll": True,
            "label": "事件触发量名字",
            "multi": True,
            "name": "trigger_name",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", trigger_type="$trigger_group"},  name)',
                "query": 'label_values(hlsvr_business_trigger_count{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", trigger_type="$trigger_group"},  name)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": False, "text": "EcSysGameSvr", "value": "EcSysGameSvr"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"},  res_type)',
            "hide": 0,
            "includeAll": False,
            "label": "资源使用量类型",
            "multi": False,
            "name": "res_type",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"},  res_type)',
                "query": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"},  res_type)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", res_type="$res_type"},   name)',
            "hide": 0,
            "includeAll": True,
            "label": "资源使用量名字",
            "multi": True,
            "name": "res_name",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", res_type="$res_type"},   name)',
                "query": 'label_values(hlsvr_process_res_usage{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", res_type="$res_type"},   name)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "auto": False,
            "auto_count": 30,
            "auto_min": "10s",
            "current": {"selected": False, "text": "1m", "value": "1m"},
            "hide": 0,
            "label": "interval",
            "name": "interval",
            "options": [
                {"selected": True, "text": "1m", "value": "1m"},
                {"selected": False, "text": "5m", "value": "5m"},
                {"selected": False, "text": "10m", "value": "10m"},
            ],
            "query": "1m,5m,10m",
            "queryValue": "",
            "refresh": 2,
            "skipUrlSync": False,
            "type": "interval",
        },
        {
            "current": {"selected": False, "text": "5", "value": "5"},
            "hide": 2,
            "includeAll": False,
            "label": "topK",
            "multi": False,
            "name": "topK",
            "options": [
                {"selected": True, "text": "5", "value": "5"},
                {"selected": False, "text": "10", "value": "10"},
                {"selected": False, "text": "15", "value": "15"},
                {"selected": False, "text": "20", "value": "20"},
                {"selected": False, "text": "50", "value": "50"},
                {"selected": False, "text": "100", "value": "100"},
                {"selected": False, "text": "999", "value": "999"},
            ],
            "query": "5,10,15,20,50,100, 999",
            "queryValue": "",
            "skipUrlSync": False,
            "type": "custom",
        },
        {
            "current": {"selected": False, "text": "240260-T_sigplay_mode", "value": "240260-T_sigplay_mode"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
            "hide": 0,
            "includeAll": False,
            "label": "场次",
            "multi": False,
            "name": "scene",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
                "query": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "type": "query",
        },
        {
            "allValue": "",
            "current": {"selected": False, "text": "All", "value": "$__all"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
            "hide": 2,
            "includeAll": True,
            "multi": False,
            "name": "gaugetype",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
                "query": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
                "queryType": "prometheus",
            },
            "refresh": 1,
            "regex": "",
            "skipUrlSync": False,
            "sort": 2,
            "type": "query",
        },
        {
            "allValue": "",
            "current": {"selected": False, "text": "All", "value": "$__all"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
            "hide": 2,
            "includeAll": True,
            "multi": False,
            "name": "countertype",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
                "query": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",SceneStr="$scene"}, Type)',
                "queryType": "prometheus",
            },
            "refresh": 1,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "type": "query",
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_attr_id_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
            "hide": 0,
            "includeAll": True,
            "label": "Attr名字",
            "multi": True,
            "name": "attr_id_name",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_attr_id_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
                "query": 'label_values(hlsvr_attr_id_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_attr_id_gague{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
            "hide": 0,
            "includeAll": True,
            "label": "Attr gauge 名字",
            "multi": True,
            "name": "attr_gague_name",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_attr_id_gague{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
                "query": 'label_values(hlsvr_attr_id_gague{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app"}, name)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
        {
            "current": {"selected": False, "text": "10260", "value": "10260"},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
            "hide": 2,
            "includeAll": False,
            "label": "",
            "multi": False,
            "name": "sceneid",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
                "query": 'label_values(hlsvr_gamesvr_counter{ bcs_cluster_id=~"$cluster", namespace="$namespace",},SceneStr)',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "/(?<value>.*)-.*/",
            "skipUrlSync": False,
            "sort": 0,
            "type": "query",
        },
        {
            "hide": 2,
            "name": "warm_game_bean_add_reason",
            "query": "1632|1678|1811|1253|1819|1820|1821",
            "skipUrlSync": False,
            "type": "constant",
        },
        {
            "hide": 2,
            "name": "warm_game_bean_minus_reason",
            "query": "2130|2154|2176|2069|2753|2754|2755",
            "skipUrlSync": False,
            "type": "constant",
        },
        {
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
            "datasource": {"type": "bkmonitor-timeseries-datasource", "uid": "sjsRKBfMz"},
            "definition": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", Type="CurPlayer"},   SceneStr)\n',
            "hide": 0,
            "includeAll": True,
            "label": "当前gamesvr内场次名",
            "multi": True,
            "name": "gamesvr_scene_names",
            "options": [],
            "query": {
                "promql": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", Type="CurPlayer"},   SceneStr)\n',
                "query": 'label_values(hlsvr_gamesvr_gauge{ bcs_cluster_id=~"$cluster", namespace="$namespace",apptype="$apptype",app=~"$app", Type="CurPlayer"},   SceneStr)\n',
                "queryType": "prometheus",
            },
            "refresh": 2,
            "regex": "",
            "skipUrlSync": False,
            "sort": 0,
            "tagValuesQuery": "",
            "tagsQuery": "",
            "type": "query",
            "useTags": False,
        },
    ]
}

res = get_variables(template)
print(json.dumps(res, ensure_ascii=False))
