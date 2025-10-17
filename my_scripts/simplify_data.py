import json
from typing import Any


def simplify_data(
    data: dict | list | Any, ignore_keys: str | None = None, present_key: str | None = None
) -> dict | list | Any:
    """
    递归简化数据结构，将数组类型的数据最大只保留三个元素

    参数:
        data: 需要简化的数据，可以是字典、列表或其他基本类型

    返回值:
        简化后的数据结构
    """
    if isinstance(data, dict):
        # 如果是字典类型，递归处理每个键值对
        return {key: simplify_data(value, ignore_keys, key) for key, value in data.items()}
    elif isinstance(data, list):
        if present_key is not None and present_key != ignore_keys:
            # 如果是列表类型，最多保留前三个元素，并递归处理每个元素
            simplified_list = data[:3]  # 最多取前三个元素
        else:
            simplified_list = data
        return [simplify_data(item, ignore_keys, present_key) for item in simplified_list]
    else:
        # 其他基本类型直接返回
        return data


def process_json_file(input_file_path: str, output_file_path: str = None, ignore_keys: str | None = None) -> None:
    """
    读取JSON文件并简化其中的数据

    参数:
        input_file_path: 输入JSON文件路径
        output_file_path: 输出JSON文件路径，如果为None则覆盖原文件

    异常:
        FileNotFoundError: 当输入文件不存在时抛出
        json.JSONDecodeError: 当文件不是有效的JSON格式时抛出
    """
    try:
        # 读取JSON文件
        with open(input_file_path, encoding="utf-8") as file:
            data = json.load(file)

        # 简化数据
        simplified_data = simplify_data(data, ignore_keys)

        # 确定输出文件路径
        if output_file_path is None:
            output_file_path = input_file_path

        # 将简化后的数据写入文件
        with open(output_file_path, "w", encoding="utf-8") as file:
            json.dump(simplified_data, file, ensure_ascii=False, indent=2)

        print(f"数据已成功简化并保存至: {output_file_path}")

    except FileNotFoundError:
        print(f"错误: 找不到文件 '{input_file_path}'")
    except json.JSONDecodeError as e:
        print(f"错误: 文件 '{input_file_path}' 不是有效的JSON格式: {e}")
    except Exception as e:
        print(f"处理过程中发生错误: {e}")


if __name__ == "__main__":
    # 示例用法
    input_file = "data.json"
    output_file = "simplified_data.json"

    # 处理JSON文件
    # ignore_keys= None
    ignore_keys = "data"

    process_json_file(input_file, output_file, ignore_keys)
