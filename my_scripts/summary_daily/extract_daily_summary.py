#!/usr/bin/env python3
# 提取日报中的总结内容
import requests
import sys
import io
import re
from pathlib import Path
import json

# 设置标准输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

output_file = Path(__file__).parent / "daily_summary_output.txt"
config_path = Path(__file__).parent / "config.json"
config = json.load(open(config_path))

headers = config["headers"]
headers.update(
    {
        "cookie": config["cookie"],
        "referer": config["referer"],
        "x-csrftoken": config["csrftoken"],
    }
)


def get_daily_report(username: str):
    # URL and parameters
    url = config["url"]
    params = {
        "num": config["days"],
        "username": username,
    }
    # Perform the GET request
    response = requests.get(url, params=params, headers=headers)

    return response.json()


def extract_all_summaries(daily_report: dict, username: str):
    """
    从JSON文件中提取所有日期的总结内容

    Args:
        daily_report (dict): 日报数据字典

    Returns:
        str: 所有日期的总结内容
    """
    try:
        # 读取JSON文件

        # 按日期排序记录
        records = sorted(daily_report.get("data", []), key=lambda x: x.get("send_date", ""), reverse=True)

        result = f"{username}--所有日期的总结内容:\n"
        result += "=" * 50 + "\n"

        for record in records:
            send_date = record.get("send_date", "")
            content = record.get("content", "")

            # 提取"今日总结"部分
            summary_pattern = r"<p><span[^>]*><strong>今日总结：</strong></span></p><ol>(.*?)</ol>"
            summary_match = re.search(summary_pattern, content, re.DOTALL)

            if summary_match:
                # 提取总结列表项
                summary_items = re.findall(r"<li>(.*?)</li>", summary_match.group(1))

                result += f"日期: {send_date}\n"
                result += "今日总结:\n"
                for i, item in enumerate(summary_items, 1):
                    # 清理HTML标签
                    clean_item = re.sub(r"<[^>]+>", "", item).strip()
                    result += f"  {i}. {clean_item}\n"
                result += "-" * 30 + "\n"

        return result
    except Exception as e:
        return f"{username}--处理过程中发生错误: {str(e)}"


def output_to_file(username: str):
    daily_report = get_daily_report(username)
    all_summaries = extract_all_summaries(daily_report, username)

    # 将结果追加到文件
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(all_summaries)
        f.write("=" * 30 + "\n\n")


if __name__ == "__main__":
    # 清空output_file 文件内容
    output_file.write_text("")

    for user in config["users"]:
        output_to_file(user)
    print("done")
