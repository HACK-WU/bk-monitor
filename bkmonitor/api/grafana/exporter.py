from constants.data_source import DataSourceLabel


class DashboardExporter:
    def __init__(self, data_source_metas: list[dict]):
        self.name_data_sources = {}
        self.uid_data_sources = {}
        self.type_data_sources = {}
        for data_source_meta in data_source_metas:
            self.uid_data_sources[data_source_meta["uid"]] = data_source_meta
            self.name_data_sources[data_source_meta["name"]] = data_source_meta
            self.type_data_sources[data_source_meta["type"]] = data_source_meta

        self.variables = {}  # 存储模板变量信息
        self.requires = {}  # 存储依赖项信息
        self.inputs = {}  # 存储数据源变量

    def templateize_datasource(self, config: dict, fallback=None, datasource_mapping=None) -> None:
        """
        数据源模板化处理函数，将数据源配置转换为模板变量形式

        参数:
        - config: 包含数据源配置的字典对象，会被直接修改
        - fallback: 当config中不存在datasource时使用的默认数据源
        - datasource_mapping: 用于存储数据源名称与原始UID映射关系的字典（可选）

        """
        # 处理默认数据源逻辑：当没有配置datasource时尝试使用fallback
        if not config.get("datasource"):
            if fallback:
                config["datasource"] = fallback
            else:
                return

        # 解析数据源配置（支持字符串和字典两种形式）
        data_source: str | dict = config["datasource"]
        if isinstance(data_source, str):
            # 处理字符串形式的数据源名称（跳过已模板化的变量）
            name = data_source
            if name.startswith("$"):
                return

            data_source_meta = self.name_data_sources.get(name)
        else:
            # 处理字典形式的数据源配置（跳过已模板化的UID）
            uid = data_source.get("uid") or ""
            if uid.startswith("$"):
                return

            data_source_type = data_source.get("type") or ""
            data_source_meta = self.uid_data_sources.get(uid) or self.type_data_sources.get(data_source_type)

        # 未找到元数据时提前返回
        if not data_source_meta:
            return

        # 构建数据源依赖配置
        self.requires[f"datasource{data_source_meta['type']}"] = {
            "type": "datasource",
            "id": data_source_meta["type"],
            "name": data_source_meta["name"],
        }

        # 生成标准化的数据源引用名称
        ref_name = f"DS_{data_source_meta['name'].replace(' ', '_').upper()}"
        # 创建输入项配置
        self.inputs[ref_name] = {
            "name": ref_name,
            "label": data_source_meta["name"],
            "description": "",
            "type": "datasource",
            "pluginId": data_source_meta["type"],
            "pluginName": data_source_meta["name"],
        }

        # 替换原始配置为模板变量形式
        if isinstance(data_source, str):
            config["datasource"] = f"${{{ref_name}}}"
        else:
            config["datasource"] = {"type": data_source_meta["type"], "uid": f"${{{ref_name}}}"}

        # 更新外部映射关系（如果存在）
        if datasource_mapping:
            datasource_mapping[ref_name] = data_source_meta["uid"]

    def replace_table_id_with_data_label(self, query_config: dict):
        """
        将结果表ID的值替换为 data_label 的值
        """
        if not query_config:
            return

        data_source_label = query_config.get("data_source_label")
        if data_source_label not in [DataSourceLabel.BK_MONITOR_COLLECTOR, DataSourceLabel.CUSTOM]:
            return

        data_label = query_config.get("data_label")
        if not data_label:
            return

        query_config["result_table_id"] = data_label

    def make_exportable(self, dashboard: dict, datasource_mapping: dict = None):
        """
        将仪表盘配置转换为可导出的通用格式

        Args:
            dashboard: 原始仪表盘配置字典
            datasource_mapping: 数据源映射关系字典（可选），用于替换具体数据源为模板变量

        Returns:
            Dict: 处理后的标准化仪表盘配置，去除实例特定信息，添加模板化元素

        处理流程：
        1. 预处理模板变量，统一数据源引用格式
        2. 遍历所有面板组件，标准化数据源配置
        3. 清理元数据并添加导出所需依赖项
        """
        # 模板变量预处理：统一数据源变量格式，初始化变量状态
        # 变量的类型只有两种，query和interval
        for variable in dashboard.get("templating", {}).get("list", []):
            # query类型时，进行额外的处理逻辑
            if variable.get("type") == "query":
                self.templateize_datasource(variable, datasource_mapping=datasource_mapping)
            self.variables[variable["name"]] = variable
            variable["current"] = {}
            variable["refresh"] = variable.get("refresh") or 1  # 设置默认刷新策略
            variable["options"] = []

        # 面板数据处理：递归处理所有层级的数据源配置
        for row in dashboard.get("panels") or []:
            self.templateize_datasource(row, datasource_mapping=datasource_mapping)

            # 处理嵌套面板结构
            for panel in row.get("panels") or []:
                self.templateize_datasource(panel, datasource_mapping=datasource_mapping)

                # 替换目标数据源引用格式
                for target in panel.get("targets") or []:
                    self.templateize_datasource(target, panel.get("datasource"), datasource_mapping=datasource_mapping)

                    for query_config in target.get("query_configs") or {}:
                        self.replace_table_id_with_data_label(query_config)

            # 处理行级目标配置
            for target in row.get("targets") or []:
                self.templateize_datasource(target, row.get("datasource"), datasource_mapping=datasource_mapping)

                for query_config in target.get("query_configs") or {}:
                    self.replace_table_id_with_data_label(query_config)

        # todo: libraryPanel处理
        dashboard["__inputs"] = list(self.inputs.values())
        dashboard["__requires"] = sorted(self.requires.values(), key=lambda x: x["id"])
        dashboard.pop("id", None)  # 移除实例唯一标识
        dashboard.pop("uid", None)  # 清除全局唯一标识
        return dashboard
