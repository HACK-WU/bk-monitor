import logging

from kubernetes import client as k8s_client
from kubernetes.dynamic import client as dynamic_client
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError

from metadata import config

logger = logging.getLogger("metadata")


def is_equal_dict(source: dict, target: dict) -> bool:
    """
    判断传入的dict是否相同，以source为准
    """
    # 只检查自己生成的配置，额外配置不检查
    for source_key, source_value in source.items():
        if source_key not in target.keys():
            return False
        if isinstance(source_value, dict):
            if not isinstance(target[source_key], dict):
                return False
            if not is_equal_dict(source_value, target[source_key]):
                return False
        else:
            if source_value != target[source_key]:
                return False
    return True


def is_equal_config(source: dict, target: dict) -> bool:
    """
    判断传入的config与当前是否相同
    """
    return is_equal_dict(source, target)


def ensure_data_id_resource(api_client: k8s_client.ApiClient, resource_name: str, config_data: dict) -> bool:
    """
    将resource和data_id的关系注入到BCS集群当中

    参数:
        api_client: Kubernetes API客户端实例，用于连接BCS集群
        resource_name: 要操作的资源名称，作为CRD资源的唯一标识
        config_data: 包含完整资源配置的字典对象，需符合CRD定义的schema

    返回值:
        bool: 操作成功返回True，资源CRD不存在或发生异常返回False
        特别说明：当获取动态客户端失败时会抛出原始异常

    该函数实现完整的资源生命周期管理流程：
    1. 动态客户端初始化（失败立即抛出异常）
    2. 资源存在性检查（通过名称精确匹配）
    3. 双态操作模式：
       - 存在则执行更新（保留资源版本号进行乐观锁控制）
       - 不存在则创建新资源
    4. 多级异常处理：
       - 资源未找到（静默退出）
       - CRD定义缺失（记录调试日志）
       - 其他异常（记录错误日志）
    """

    # NOTE: 如果获取 client 出错，直接返回，避免错误消息被覆盖
    try:
        d_client = dynamic_client.DynamicClient(api_client)
    except Exception as e:
        logger.exception("get bcs cluster client error!")
        raise e

    # 更新或创建集群资源
    try:
        resource = d_client.resources.get(
            api_version=f"{config.BCS_RESOURCE_GROUP_NAME}/{config.BCS_RESOURCE_VERSION}",
            kind=config.BCS_RESOURCE_DATA_ID_RESOURCE_KIND,
        )
        action = "update"
        # 检查是否已存在,存在则更新
        data = d_client.get(resource=resource, name=resource_name)
        config_data["metadata"]["resourceVersion"] = data["metadata"]["resourceVersion"]
        d_client.replace(resource=resource, body=config_data)
    except NotFoundError:
        # 不存在则新增
        action = "create"
        d_client.create(resource, body=config_data)
    except ResourceNotFoundError:
        # 异常处理：CRD定义缺失
        logger.debug("dataid resource crd not found in k8s cluster, will not create any dataid resource")
        return False
    except Exception as e:
        # 异常处理：其他未知错误
        logger.error(f"unexpected error in ensure dataid:{e}")
        return False

    logger.info(
        "[%s] datasource [%s]",
        action,
        resource_name,
    )
    return True
