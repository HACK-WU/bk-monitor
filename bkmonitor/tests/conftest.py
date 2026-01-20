"""
Tencent is pleased to support the open source community by making 蓝鲸智云 - 监控平台 (BlueKing - Monitor) available.
Copyright (C) 2017-2025 Tencent. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import pytest
from django.conf import settings
from django.utils.functional import empty

import settings as monitor_settings
from api.cmdb.client import ListServiceInstanceDetail


def pytest_configure():
    # Setup django for every upper key in the settings.py
    config_dict = {key: getattr(monitor_settings, key) for key in dir(monitor_settings) if key.upper() == key}

    # fix database collation
    config_dict["DATABASES"]["default"]["TEST"] = {
        "CHARSET": "utf8",
        "COLLATION": "utf8_general_ci",
    }

    config_dict["DATABASES"]["monitor_api"]["TEST"] = {
        "CHARSET": "utf8",
        "COLLATION": "utf8_general_ci",
    }

    # 配置测试环境专用路由器，确保 Django 内置应用使用 default 数据库
    # 需要在 configure 之前就设置好
    config_dict["DATABASE_ROUTERS"] = ["bkmonitor.tests.test_db_router.TestBackendRouter"]

    # 配置日志，方便调试路由器问题
    config_dict["LOGGING"] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "[%(levelname)s] %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "loggers": {
            "bkmonitor.tests.test_db_router": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": True,
            },
        },
    }

    if settings._wrapped is empty:
        settings.configure(**config_dict)

        # 配置后强制刷新路由器缓存，确保新路由器生效
        # 这一步很关键，因为 Django 会缓存路由器实例
        import django.db.utils

        # 清除可能存在的路由器缓存
        if hasattr(django.db.utils, "connection_router"):
            try:
                delattr(django.db.utils, "connection_router")
            except Exception:
                pass

        # 确保新路由器被正确加载
        from django.db import connections

        # 刷新所有连接的路由器引用
        for conn in connections.all():
            if hasattr(conn, "router"):
                try:
                    delattr(conn, "router")
                except Exception:
                    pass


@pytest.fixture(autouse=True)
def reset_db_router():
    """
    每个测试前重置数据库路由器，确保测试路由器正确生效

    这个夹具会自动应用于所有测试，确保：
    1. 路由器缓存被清除
    2. 测试路由器被正确加载
    3. Django 内置应用（contenttypes、auth、sessions）使用 default 数据库
    """
    import django.db.utils

    # 清除路由器缓存
    if hasattr(django.db.utils, "connection_router"):
        try:
            delattr(django.db.utils, "connection_router")
        except Exception:
            pass

    # 清除所有连接的路由器引用
    from django.db import connections

    for conn in connections.all():
        if hasattr(conn, "router"):
            try:
                delattr(conn, "router")
            except Exception:
                pass

    # 强制重新加载路由器
    from django.db.utils import ConnectionRouter

    _ = ConnectionRouter()

    yield

    # 测试结束后再次清除缓存
    if hasattr(django.db.utils, "connection_router"):
        try:
            delattr(django.db.utils, "connection_router")
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def setup_django_content_type():
    """
    在测试会话开始时确保 django_content_type 表在 default 数据库中存在

    这个夹具在所有测试开始前运行一次，确保：
    1. django_content_type 表在 default 数据库中被正确创建
    2. ContentType 缓存被正确初始化
    """
    from django.contrib.contenttypes.models import ContentType
    from django.db import connections

    # 强制在 default 数据库中同步 contenttypes 表
    try:
        with connections["default"].cursor() as cursor:
            # 检查表是否存在
            cursor.execute("SHOW TABLES LIKE 'django_content_type'")
            if not cursor.fetchone():
                # 表不存在，需要运行迁移
                from django.core.management import call_command

                call_command("migrate", "contenttypes", database="default", verbosity=0, interactive=False)

        # 清空 ContentType 缓存，强制从数据库重新加载
        ContentType.objects.clear_cache()

        # 预加载所有 content types，确保它们在 default 数据库中
        list(ContentType.objects.using("default").all())

    except Exception as e:
        # 如果出错，只记录日志，不中断测试
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to setup django_content_type: {e}")


@pytest.fixture
def monkeypatch_list_service_instance_detail(monkeypatch):
    mock_return_value = {
        "count": 1,
        "info": [
            {
                "bk_biz_id": 2,
                "process_instances": [
                    {
                        "process": {
                            "proc_num": None,
                            "bk_start_check_secs": None,
                            "bind_info": [
                                {
                                    "enable": True,
                                    "protocol": "1",
                                    "approval_status": "2",
                                    "template_row_id": 1,
                                    "ip": "0.0.0.0",
                                    "type": "custom",
                                    "company_port_id": 1,
                                    "port": "80",
                                },
                                {
                                    "enable": True,
                                    "protocol": "1",
                                    "approval_status": "2",
                                    "template_row_id": 2,
                                    "ip": "0.0.0.0",
                                    "type": "custom",
                                    "company_port_id": 2,
                                    "port": "7000-8000",
                                },
                                {
                                    "enable": True,
                                    "protocol": "1",
                                    "approval_status": "2",
                                    "template_row_id": 3,
                                    "ip": "0.0.0.0",
                                    "type": "custom",
                                    "company_port_id": 3,
                                    "port": "8800",
                                },
                            ],
                            "priority": None,
                            "pid_file": "",
                            "auto_start": None,
                            "stop_cmd": "",
                            "description": "",
                            "bk_process_id": 1,
                            "bk_process_name": "process_name",
                            "bk_start_param_regex": "",
                            "start_cmd": "",
                            "user": "",
                            "face_stop_cmd": "",
                            "bk_biz_id": 2,
                            "bk_func_name": "process_name",
                            "work_path": "",
                            "service_instance_id": 1,
                            "reload_cmd": "",
                            "timeout": None,
                            "bk_supplier_account": "tencent",
                            "restart_cmd": "",
                        },
                        "relation": {
                            "bk_biz_id": 2,
                            "process_template_id": 1,
                            "bk_host_id": 1,
                            "service_instance_id": 1,
                            "bk_process_id": 1,
                            "bk_supplier_account": "tencent",
                        },
                    }
                ],
                "bk_module_id": 1,
                "name": "1.1.1.1_process_name_80",
                "labels": None,
                "bk_host_id": 1,
                "bk_supplier_account": "tencent",
                "service_template_id": 1,
            }
        ],
    }
    monkeypatch.setattr(ListServiceInstanceDetail, "perform_request", lambda *args, **kwargs: mock_return_value)
