"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import ipaddress
from functools import partial
from typing import Any


def is_ip(ip: str, _version: int | None = None) -> bool:
    """
    判断是否为合法 IP
    :param ip:
    :param _version: 是否为合法版本，缺省表示 both
    :return:
    """
    try:
        ip_address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if _version is None:
        return True
    return ip_address.version == _version


# 判断是否为合法 IPv6
is_v6 = partial(is_ip, _version=6)

# 判断是否为合法 IPv4
is_v4 = partial(is_ip, _version=4)


def exploded_ip(ip: str) -> str:
    """
    将 IPv6 地址展开为完整的标准格式（128位全展开），IPv4 或非法地址原样返回。

    IPv6 地址有多种等价的缩写表示形式，例如：
    - 缩写形式: "fe80::1"、"2001:db8::1"、"::1"
    - 展开形式: "fe80:0000:0000:0000:0000:0000:0000:0001"

    在 ES 中存储的 IPv6 地址统一使用展开格式，因此查询时也需要将用户输入的
    缩写形式展开为标准格式，才能正确匹配。

    该函数在以下场景中被调用：
    1. AlertQueryTransformer.visit_search_field 中对 event.ipv6 字段的查询值进行展开
    2. ipv6s_formatter / ipv6_formatter 中批量格式化 IPv6 地址
    3. 数据入库前统一 IPv6 格式，确保存储一致性

    参数:
        ip: IP 地址字符串，可以是 IPv4、IPv6（缩写或完整形式）、或非法地址

    返回值:
        str: 如果是合法 IPv6，返回展开后的标准格式（8组4位十六进制，冒号分隔）；
             否则原样返回输入值

    示例:
        >>> exploded_ip("::1")
        '0000:0000:0000:0000:0000:0000:0000:0001'
        >>> exploded_ip("fe80::1")
        'fe80:0000:0000:0000:0000:0000:0000:0001'
        >>> exploded_ip("192.168.1.1")
        '192.168.1.1'
        >>> exploded_ip("invalid")
        'invalid'
    """
    # 仅对合法的 IPv6 地址进行展开，IPv4 和非法地址直接透传
    if is_v6(ip):
        # ipaddress.ip_address(ip).exploded 会将所有省略的零补全，
        # 例如 "::1" → "0000:0000:0000:0000:0000:0000:0000:0001"
        return ipaddress.ip_address(ip).exploded
    return ip


def compressed_ip(ip: str) -> str:
    """
    如果 ip 为合法的 IPv6，转为压缩格式
    :param ip:
    :return:
    """
    if is_v6(ip):
        return ipaddress.ip_address(ip).compressed
    return ip


def ipv6s_formatter(ips: list[str]) -> list[str]:
    """
    将 IPv6 列表转为标准格式
    :param ips:
    :return:
    """
    return [exploded_ip(ip) for ip in ips]


def ipv6_formatter(data: dict[str, Any], ipv6_field_names: list[str]):
    """
    将 data 中 ipv6_field_names 转为 IPv6 标准格式
    :param data: 可能包含 v6 的字典数据
    :param ipv6_field_names:IPv6 字段
    :return:
    """
    for ipv6_field_name in ipv6_field_names:
        ipv6_val: str | None = data.get(ipv6_field_name)
        data[ipv6_field_name] = exploded_ip(ipv6_val)


def ipv4_to_v6(ipv4: str) -> str:
    """
    IPv4 转为 IPv6
    :param ipv4: IPv4
    :return: IPv6 标准形式
    """
    ipv4_address: ipaddress.IPv4Address = ipaddress.IPv4Address(ipv4)
    prefix6to4: int = int(ipaddress.IPv6Address("2002::"))
    ipv6_address: ipaddress.IPv6Address = ipaddress.IPv6Address(prefix6to4 | (int(ipv4_address) << 80))
    return ipv6_address.exploded


def join_host_port(host: str, port: int) -> str:
    """
    拼接 host:port
    """
    if is_v6(host):
        return f"[{host}]:{port}"
    return f"{host}:{port}"
