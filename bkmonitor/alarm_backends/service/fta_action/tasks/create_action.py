import copy
import logging
import math
import time
import json

from django.conf import settings
from django.utils.translation import gettext as _
from elasticsearch import ConflictError

from alarm_backends.constants import CONST_SECOND
from alarm_backends.core.alert import Alert, AlertCache
from alarm_backends.core.alert.alert import AlertKey
from alarm_backends.core.cache.action_config import ActionConfigCacheManager
from alarm_backends.core.cache.subscribe import SubscribeCacheManager
from alarm_backends.core.cache.assign import AssignCacheManager
from alarm_backends.core.cache.key import ACTION_POLL_KEY_LOCK
from alarm_backends.core.cluster import get_cluster_bk_biz_ids
from alarm_backends.core.control.strategy import Strategy
from alarm_backends.core.lock.service_lock import service_lock
from alarm_backends.service.converge.shield.shielder import AlertShieldConfigShielder
from alarm_backends.service.fta_action.double_check import DoubleCheckHandler
from alarm_backends.service.fta_action.tasks.alert_assign import AlertAssigneeManager
from alarm_backends.service.fta_action.tasks.noise_reduce import (
    NoiseReduceRecordProcessor,
)
from alarm_backends.service.fta_action.utils import PushActionProcessor, need_poll
from alarm_backends.core.circuit_breaking.manager import ActionCircuitBreakingManager
from alarm_backends.service.scheduler.app import app
from bkmonitor.action.serializers import ActionPluginSlz
from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.documents.base import BulkActionType
from bkmonitor.models import ActionInstance, ActionPlugin
from bkmonitor.utils import extended_json
from bkmonitor.utils.common_utils import count_md5
from constants.action import (
    DEFAULT_NOTICE_ACTION,
    ActionNoticeType,
    ActionPluginType,
    ActionSignal,
    IntervalNotifyMode,
    UserGroupType,
    VoiceNoticeMode,
)
from constants.alert import EventSeverity, EventStatus, HandleStage
from core.errors.alarm_backends import LockError
from core.prometheus import metrics

logger = logging.getLogger("fta_action.run")


@app.task(ignore_result=True, queue="celery_action")
def create_actions(
    strategy_id,
    signal,
    alert_ids=None,
    alerts: list[AlertDocument] = None,
    severity=None,
    dimensions=None,
    dimension_hash="",
    relation_id=None,
    execute_times=0,
    is_unshielded=False,
    notice_type=ActionNoticeType.NORMAL,
):
    """
    根据策略产生任务
    :param notice_type: 通知类型
    :param is_unshielded: 是否为解屏蔽
    :param execute_times: 执行次数
    :param strategy_id:策略ID
    :param signal:产生信号
    :param alert_ids:告警ID列表
    :param alerts: 告警列表
    :param severity: 告警级别，如果为None, 则默认用告警级别最严重的alert填充
    :param dimensions: 策略匹配维度, 默认为列表，包含key， value, display_key, display_value
    :param dimension_hash: 维度hash
    :param relation_id: 关联的ID
    :return:
    """
    exc = None  # 初始化异常变量
    actions = []  # 初始化动作列表

    if is_unshielded:  # 如果是解屏蔽操作
        notice_type = ActionNoticeType.UNSHILEDED  # 修改通知类型为解屏蔽

    public_labels = {  # 定义公共标签字典
        "strategy_id": metrics.TOTAL_TAG,
        "signal": signal,
        "run_type": "once",
        "notice_type": notice_type,
    }

    alert_id = alerts[0].id if alerts else alert_ids[0]  # 获取告警ID
    logger.info("[create actions(begin)](%s) for alert(%s)", notice_type, alert_id)  # 记录开始创建动作的日志

    try:
        with metrics.ACTION_CREATE_PROCESS_TIME.labels(**public_labels).time():  # 记录创建动作的处理时间
            # 创建任务
            actions = CreateActionProcessor(
                strategy_id,
                signal,
                alert_ids,
                alerts,
                severity,
                dimensions,
                dimension_hash,
                relation_id,
                execute_times,
                is_unshielded,
                notice_type,
            ).do_create_actions()
        logger.info(
            "[create actions(end)](%s) for alert(%s), action count(%s)", notice_type, alert_id, len(actions)
        )  # 记录结束创建动作的日志
    except BaseException as e:  # 捕获所有异常
        exc = e  # 设置异常变量
        logger.exception("create actions for alert(%s) failed: %s", alert_id, e)  # 记录异常日志

    metrics.ACTION_CREATE_PROCESS_COUNT.labels(  # 更新动作创建过程计数器
        status=metrics.StatusEnum.from_exc(exc), exception=exc, **public_labels
    ).inc()
    metrics.ACTION_CREATE_PUSH_COUNT.labels(**public_labels).inc(len(actions))  # 更新动作创建推送计数器
    metrics.report_all()  # 报告所有指标

    return actions  # 返回创建的动作列表


@app.task(ignore_result=True, queue="celery_interval_action")
def create_interval_actions(
    strategy_id,
    signal,
    alert_ids=None,
    alerts: list[AlertDocument] = None,
    severity=None,
    dimensions=None,
    dimension_hash="",
    action_id=None,
    execute_times=0,
):
    """
    创建周期性告警动作的处理流程

    参数:
        strategy_id: 告警策略ID
        signal: 告警信号类型
        alert_ids: 告警记录ID列表（可选）
        alerts: 告警文档对象列表（可选）
        severity: 告警严重级别（可选）
        dimensions: 告警维度信息（可选）
        dimension_hash: 维度哈希值（可选）
        action_id:  策略与处理套餐的关联ID，这里就是action的ID（可选）,后续用于过滤操作
        execute_times: 执行次数计数器（默认0）

    返回值:
        list: 创建的Action对象列表

    该函数实现周期性告警动作的完整创建流程：
    1. 构建公共标签元数据
    2. 初始化动作创建处理器
    3. 执行动作创建并记录指标
    4. 异常处理及日志记录
    5. 指标数据上报
    """
    exc = None
    actions = []

    public_labels = {
        "strategy_id": strategy_id,
        "signal": signal,
        "run_type": "interval",
        "notice_type": ActionNoticeType.NORMAL,
    }

    alert_id = alerts[0].id if alerts else alert_ids[0]
    # 配置的间隔通知模式，这里对应的就是“polled actions” 循环动作
    logger.info("do create polled actions for alert(%s), relation_id(%s)", alert_id, action_id)

    # 执行动作创建核心流程
    # 包含指标计时、处理器调用和结果日志记录
    try:
        with metrics.ACTION_CREATE_PROCESS_TIME.labels(**public_labels).time():
            actions = CreateActionProcessor(
                strategy_id, signal, alert_ids, alerts, severity, dimensions, dimension_hash, action_id, execute_times
            ).do_create_actions()
        logger.info("create polled actions(%s) for alert(%s)", len(actions), alert_id)
    except BaseException as e:
        exc = e
        logger.exception("create polled actions for alert(%s) failed: %s", alert_id, e)

    # 上报动作创建指标数据
    # 包含处理状态、异常信息和动作数量统计
    metrics.ACTION_CREATE_PROCESS_COUNT.labels(
        status=metrics.StatusEnum.from_exc(exc), exception=exc, **public_labels
    ).inc()
    metrics.ACTION_CREATE_PUSH_COUNT.labels(**public_labels).inc(len(actions))
    metrics.report_all()

    return actions


def check_create_poll_action():
    """
    周期创建循环通知任务
    :return:
    """
    try:
        polled_action_interval = int(getattr(settings, "POLLED_ACTION_INTERVAL", CONST_SECOND * 30))
    except BaseException as error:  # NOCC:broad-except(设计如此:)
        logger.info("get polled_action_interval from settings failed(), use default interval", str(error))
        polled_action_interval = CONST_SECOND * 30
    for interval in range(0, 60, polled_action_interval):
        check_create_poll_action_10_secs.apply_async(countdown=interval, expires=120)


@app.task(ignore_result=True, queue="celery_action_cron")
def check_create_poll_action_10_secs():
    """
    每10s进行一次数据查询
    :return:
    """
    try:
        with service_lock(ACTION_POLL_KEY_LOCK):
            CreateIntervalActionProcessor().process()
    except LockError:
        # 加锁失败
        logger.info("[get service lock fail] check_create_poll_action. will process later")
        return
    except BaseException as e:  # NOCC:broad-except(设计如此:)
        logger.exception(f"[process error] check_create_poll_action, reason：{str(e)}")
        return


class CreateIntervalActionProcessor:
    def __init__(self):
        self.polled_actions = []
        self.finished_actions = []
        self.polled_alerts = []
        self.need_polled_actions = {}

    def process(self):
        # 检查需要创建周期任务的内容
        self.check_polled_actions()
        # 创建周期任务
        self.create_interval_action()

        logger.info(
            f"check_create_poll_action need_polled_actions({len(self.need_polled_actions.keys())}), polled_actions({len(self.polled_actions)}) finished_actions({len(self.finished_actions)})"
        )

    def check_polled_actions(self):
        """
        检查所有需要轮询的任务
        :return:
        """
        bk_biz_ids = set(get_cluster_bk_biz_ids())
        action_instances = ActionInstance.objects.filter(need_poll=True, is_polled=False).only(
            "id",
            "need_poll",
            "is_polled",
            "inputs",
            "action_config_id",
            "execute_times",
            "strategy_id",
            "signal",
            "alerts",
            "alert_level",
            "dimensions",
            "dimension_hash",
            "strategy_relation_id",
            "end_time",
            "is_parent_action",
        )
        checked_alerts = []
        for action_instance in action_instances:
            # 仅处理集群内的业务
            if action_instance.bk_biz_id not in bk_biz_ids:
                continue
            action_config = ActionConfigCacheManager.get_action_config_by_id(config_id=action_instance.action_config_id)
            action_instance.action_config = action_config
            self.check_finished_actions(checked_alerts, action_instance)
            self.check_interval_matched_actions(action_instance, action_config)

    def create_interval_action(self):
        """
        创建周期任务
        :return:
        """
        polled_alert_docs = {alert.id: alert for alert in AlertDocument.mget(ids=self.polled_alerts)}
        for action_id, action_instance in self.need_polled_actions.items():
            # 当上一次任务结束时间已经满足了轮转，则需要创建任务
            alert = polled_alert_docs.get(action_instance.alerts[0], None)
            alert_latest_time = alert.latest_time if alert else 0

            if (
                action_instance.inputs.get("alert_latest_time", 0) < alert_latest_time
                and alert.status_detail == EventStatus.ABNORMAL
            ):
                # 当前周期通知的最近异常点一定要大于历史异常点
                # 当前告警的具体状态一定， 存在恢复中状态的周期通知不需要发送
                create_interval_actions.delay(
                    action_instance.strategy_id,
                    action_instance.signal,
                    action_instance.alerts,
                    severity=action_instance.alert_level,
                    dimensions=action_instance.dimensions,
                    dimension_hash=action_instance.dimension_hash,
                    action_id=action_instance.strategy_relation_id,
                    execute_times=action_instance.execute_times,
                )
                self.polled_actions.append(action_id)

        # 更新DB的数据，已经轮询的，设置为已经轮询，不需要轮询的，直接取消
        ActionInstance.objects.filter(id__in=self.polled_actions).update(is_polled=True)
        ActionInstance.objects.filter(id__in=self.finished_actions).update(need_poll=False)

    def check_finished_actions(self, checked_alerts: list, action_instance):
        check_key = f"{action_instance.alerts[0]}_{action_instance.action_config_id}"
        if check_key in checked_alerts:
            # 增加检测机制，每个alert对应的action类型仅保留一个同类型的周期任务
            self.finished_actions.append(action_instance.id)
            return
        checked_alerts.append(check_key)
        if not need_poll(action_instance):
            # 不需要轮询的时候，直接设置为结束
            self.finished_actions.append(action_instance.id)

    def check_interval_matched_actions(self, action_instance, action_config):
        """
        判断周期间隔是否已经达到
        """
        if action_instance.id in self.finished_actions:
            return
        try:
            execute_config = action_config["execute_config"]["template_detail"]
        except KeyError as error:
            logger.error("No execute_config params in action_config %s error %s", action_config, str(error))
            return
        except TypeError as error:
            logger.error("type error execute_config params in action_config %s error %s", action_config, str(error))
            return
        notify_interval = self.calc_action_interval(execute_config, action_instance)
        if notify_interval <= 0 or int(action_instance.end_time.timestamp()) + notify_interval > int(time.time()):
            # 不满足创建周期任务条件的时候，直接返回
            return

        self.need_polled_actions.update({action_instance.id: action_instance})
        self.polled_alerts.extend(action_instance.alerts)

    @staticmethod
    def calc_action_interval(execute_config, action_instance: ActionInstance):
        """
        计算周期任务间隔
        :param execute_config: 执行参数
        :param action_instance: 当前的主任务动作
        :return:
        """
        if execute_config.get("need_poll", True) is False:
            return 0

        try:
            notify_interval = int(execute_config.get("notify_interval", 0))
        except TypeError:
            notify_interval = 0

        interval_notify_mode = execute_config.get("interval_notify_mode", IntervalNotifyMode.STANDARD)
        if interval_notify_mode == IntervalNotifyMode.INCREASING:
            # 按照指数级别进行处理
            notify_interval = int(notify_interval * math.pow(2, action_instance.execute_times - 1))
        return notify_interval


class CreateActionProcessor:
    def __init__(
        self,
        strategy_id,  # 策略ID
        signal,  # 信号
        alert_ids=None,  # 警报ID列表
        alerts: list[AlertDocument] = None,  # 警报文档列表
        severity=None,  # 严重性
        dimensions=None,  # 维度
        dimension_hash="",  # 维度哈希
        action_id=None,  # 后续用于过滤action
        execute_times=0,  # 执行次数
        is_unshielded=False,  # 是否为解除屏蔽
        notice_type=ActionNoticeType.NORMAL,  # 通知类型
    ):
        """
        初始化告警处理上下文对象

        参数:
            strategy_id: 策略唯一标识符
            signal: 触发动作的原始信号
            alert_ids: 可选的警报ID列表
            alerts: 可选的警报文档对象列表
            severity: 告警严重等级
            dimensions: 多维数据标签集合
            dimension_hash: 维度组合唯一标识
            action_id: 动作关联唯一标识
            execute_times: 当前执行次数计数器
            is_unshielded: 屏蔽状态标志位
            notice_type: 通知消息类型枚举

        该构造函数主要完成以下核心初始化流程：
        1. 基础属性赋值
        2. 警报数据预加载与过滤
        3. 策略配置加载
        4. 运行时状态初始化
        """

        # 基础属性初始化
        self.strategy_id = strategy_id
        self.signal = signal

        # 警报标识处理
        # 优先使用显式传入的警报ID列表，否则从警报文档中提取
        alert_ids = alert_ids or [alert.id for alert in alerts]

        # 构建分布式存储访问键
        # 生成用于从Redis/ES批量获取告警的复合键列表
        alert_keys = [AlertKey(alert_id=alert_id, strategy_id=self.strategy_id) for alert_id in alert_ids]

        # 分布式存储批量读取
        # 通过mget接口一次性获取所有关联告警对象
        self.alert_objs = {alert.id: alert for alert in Alert.mget(alert_keys)}

        # 有效告警过滤
        # 根据执行次数和动作ID筛选可处理的警报文档
        self.alerts = [
            AlertDocument(**alert.data)
            for alert in self.alert_objs.values()
            if alert.is_valid_handle(execute_times, action_id)
        ]

        # 运行时状态初始化
        self.is_alert_shielded = False
        self.shield_detail = ""
        self.alert_ids = alert_ids

        # 严重等级继承处理
        # 使用显式传入值或默认取首个有效告警的等级
        self.severity = severity or self.alerts[0].severity

        # 上下文属性赋值
        self.dimensions = dimensions
        self.dimension_hash = dimension_hash
        self.relation_id = action_id
        self.execute_times = execute_times
        self.is_unshielded = is_unshielded

        # 策略配置加载
        # 优先加载最新策略配置，降级使用有效告警的策略
        self.strategy = Strategy(strategy_id).config or (self.alerts[0].strategy if self.alerts else {})

        #  生产uuid,本次执行产生的ActionInstance将会拥有相同的uuid
        self.generate_uuid = self.get_generate_uuid()

        # 通知系统初始化
        self.noise_reduce_result = False
        self.notice = {}
        self.notice_type = notice_type

    def get_generate_uuid(self):
        # 生成UUID的方法
        md5_elements = [self.strategy_id, self.signal, self.alert_ids, int(time.time())]  # MD5元素列表
        if self.relation_id:
            # 如果有特定的关联关系，也加入MD5元素
            md5_elements.append(self.relation_id)
        # 返回MD5哈希值作为UUID
        return count_md5(md5_elements)

    def _merge_notify_info(self, target_notify_info: dict, source_notify_info: dict):
        """
        合并两个通知信息字典，去重处理
        :param target_notify_info: 目标通知信息字典
        :param source_notify_info: 源通知信息字典
        """
        for notice_way, users in source_notify_info.items():
            if notice_way not in target_notify_info:
                target_notify_info[notice_way] = []

            # 去重：避免同一用户在同一渠道重复通知
            for user in users:
                if user not in target_notify_info[notice_way]:
                    target_notify_info[notice_way].append(user)

    def get_action_relations(self):
        """
        获取处理动作，并对通知动作进行降噪

        参数:
            self: 包含策略配置和上下文信息的实例对象，需包含以下属性：
                - strategy: 策略字典，包含actions和notice配置（可选）
                - notice_type: 通知类型（ActionNoticeType枚举），决定是否进行降噪处理
                - relation_id: 需要过滤的处理套餐ID（可选）
                - signal: 信号类型字符串，用于过滤支持的信号动作
                - DEFAULT_NOTICE_ACTION: 默认通知动作配置（模块级变量）
                - alerts: 告警对象列表（至少包含一个元素）
                - generate_uuid: 唯一标识生成器
                - strategy_id: 策略唯一标识

        返回值:
            list: 过滤后的动作列表，每个元素为包含配置信息的字典对象

        执行流程：
        1. 策略配置加载：优先从策略获取actions和notice，否则使用默认通知配置
        2. 通知关联处理：当通知包含配置ID时：
           - 将通知对象加入动作列表
           - 非升级类型通知执行降噪处理
        3. 动作过滤机制：
           - 优先按指定relation_id进行精确匹配过滤
           - 后续按信号类型进行匹配过滤
        """
        # 获取到关联的处理套餐
        if self.strategy:
            # 从策略中获取，处理套餐可以存在于actions和notices中
            actions = copy.deepcopy(self.strategy.get("actions", []))
            self.notice = copy.deepcopy(self.strategy.get("notice", {}))
        else:
            # 如果没有策略，使用默认的告警通知（默认的告警通知中没有配置告警处理套餐）
            self.notice = copy.deepcopy(DEFAULT_NOTICE_ACTION)
            actions = [self.notice]

        # 获取到通知中关联的处理套餐
        if self.notice.get("config_id"):
            actions.append(self.notice)
            # 如果通知中有配置ID，增加通知操作并进行降噪处理
            if self.notice_type != ActionNoticeType.UPGRADE:
                # 如果不是通知升级，进行降噪处理
                self.noise_reduce_result = NoiseReduceRecordProcessor(
                    self.notice, self.signal, self.strategy_id, self.alerts[0], self.generate_uuid
                ).process()

        # 根据指定的处理套餐ID进行过滤
        if self.relation_id:
            actions = [action for action in actions if action["id"] == self.relation_id]

        # 根据信号过滤处理动作
        actions = [action for action in actions if self.signal in action["signal"]]
        return actions

    def get_alert_shield_result(self):
        """
        获取告警的屏蔽状态
        :return: 返回一个元组，第一个元素表示是否有告警被屏蔽（True/False），第二个元素是被屏蔽告警的ID列表
        """
        for alert in self.alerts:  # 遍历所有告警
            # 关联多告警的内容，只要有其中一个不满足条件，直接就屏蔽
            try:
                shielder = AlertShieldConfigShielder(alert)  # 实例化一个告警屏蔽配置对象
                if shielder.is_matched():  # 如果当前告警满足屏蔽条件
                    self.shield_detail = extended_json.loads(shielder.detail).get("message", "")  # 获取屏蔽详情信息
                    return True, shielder.list_shield_ids()  # 返回True和被屏蔽告警的ID列表
            except Exception as error:  # 如果处理过程中出现异常
                logger.exception(
                    "check alert(%s) shield status failed ,error is %s", alert.id, str(error)
                )  # 记录错误日志
        return False, []  # 如果没有告警被屏蔽，返回False和一个空列表

    def is_alert_status_valid(self, alert):
        """
        判断当前告警是否需要执行

        不进行告警分派的两种情况：
            1.信号为已确认，并且已经进行了告警通知
            2.告警为已确认，或者告警状态发生了变化（如果告警状态与信号不一致，则告警状态发生了改变）

        """
        # 在传入信号是确认情况下，如果告警已经通知过了，那么就不用再进行告警分派，否则需要进行告警分派
        # 信号不是已确认，需要进行其他情况的判断
        if self.signal == ActionSignal.ACK:
            if not alert.is_ack_noticed:
                # 如果当前信息为确认通知并且没有发送过，则一定执行
                return True
            return False

        # 故障生成时，默认有效
        if self.signal == ActionSignal.INCIDENT:
            return True

        compared_status = EventStatus.ABNORMAL if self.signal == ActionSignal.NO_DATA else self.signal.upper()
        # 如果告警状态是已确认，或者告警状态和当前信号不一致，则不进行告警分派
        # 当告警状态发生变化时，系统会忽略掉所有通知和处理套餐的执行
        if alert.is_ack or (alert.status != compared_status):
            # 告警已经确认
            desc = _("用户已确认当前告警，系统自动忽略所有的通知和处理套餐的执行")
            current_timestamp = int(time.time())
            if not alert.is_ack:
                # 如果当前告警处理时延在1min以内，需要执行通知。
                if alert.begin_time + CONST_SECOND * 60 < current_timestamp:
                    return True

                desc = _("当前告警状态发生变化，系统自动忽略{}的所有通知和处理套餐的执行").format(
                    ActionSignal.ACTION_SIGNAL_DICT.get(self.signal)
                )
            action_log = dict(
                op_type=AlertLog.OpType.ACTION,
                alert_id=[alert.id],
                description=desc,
                time=current_timestamp,
                create_time=current_timestamp,
                event_id=current_timestamp,
            )
            AlertLog.bulk_create([AlertLog(**action_log)])
            return False
        return True

    def alert_assign_handle(self, alert, action_configs, origin_actions, itsm_actions) -> AlertAssigneeManager:
        """
        告警分派核心处理函数，实现告警分配逻辑与ITSM动作同步机制

        参数:
            alert: 告警对象，包含事件详情和业务上下文信息
            action_configs: 动作配置字典，缓存动作ID到配置的映射关系
            origin_actions: 原始动作ID列表，记录已存在的动作配置ID
            itsm_actions: ITSM动作列表，存储需要执行的ITSM流程配置

        返回值:
            AlertAssigneeManager: 告警分配管理器实例，包含分派结果和匹配规则信息

        执行流程:
        1. 解析分派模式（基于规则/默认通知）
        2. 构建监控指标上下文标签
        3. 创建分配管理器实例并处理异常
        4. 更新ITSM动作配置（首次执行且非升级通知时）
        5. 记录监控指标数据
        """
        # 获取告警分派模式：by_rule(基于规则分派)|only_notice(默认通知)
        assign_mode = self.notice["options"].get("assign_mode")

        # 初始化分配上下文标签
        assign_labels = {
            "bk_biz_id": alert.event.bk_biz_id,
            "assign_type": "action",
            "notice_type": self.notice_type,
            "alert_source": getattr(alert.event, "plugin_id", ""),
        }

        # 使用metrics记录分配处理时间（包含异常处理上下文）
        with metrics.ALERT_ASSIGN_PROCESS_TIME.labels(**assign_labels).time():
            exc = None
            assignee_manager = None
            try:
                # 创建告警分配管理器实例
                # 该实例内部完成告警分派规则匹配和执行人计算
                assignee_manager = AlertAssigneeManager(
                    alert,
                    self.notice["user_groups"],
                    assign_mode,
                    self.notice["options"].get("upgrade_config", {}),
                    notice_type=self.notice_type,
                )
                # 将匹配到的规则组ID注入监控标签
                assign_labels.update({"rule_group_id": assignee_manager.matched_group})
            except BaseException as error:
                # 异常处理分支：记录错误信息并更新监控标签
                assign_labels.update({"rule_group_id": None})
                exc = error
                logger.exception("[alert assign error] alert(%s) assign failed, error info %s", alert.id, str(error))
            assign_labels["status"] = metrics.StatusEnum.from_exc(exc)

        # 记录分配处理次数指标
        metrics.ALERT_ASSIGN_PROCESS_COUNT.labels(**assign_labels).inc()

        # ITSM动作配置同步逻辑（仅首次执行且非升级通知时触发）
        if self.execute_times == 0 and self.notice_type != ActionNoticeType.UPGRADE and exc is None:
            # 遍历分配管理器关联的ITSM动作
            for itsm_action_id in assignee_manager.itsm_actions.keys():
                # 动态加载缺失的动作配置
                if str(itsm_action_id) not in action_configs:
                    action_configs[str(itsm_action_id)] = ActionConfigCacheManager.get_action_config_by_id(
                        itsm_action_id
                    )
                # 注册新发现的ITSM动作到执行列表
                if str(itsm_action_id) not in origin_actions:
                    itsm_actions.append({"config_id": itsm_action_id, "id": 0, "options": {}})

        return assignee_manager

    @classmethod
    def is_action_config_valid(cls, alert, action_config, config_id):
        """
        当前处理套餐是否有效
        :param alert:
        :param action_config:
        :param config_id:
        :return:
        """
        if action_config and action_config["is_enabled"]:
            return True
        current_timestamp = int(time.time())
        action_log = dict(
            op_type=AlertLog.OpType.ACTION,
            alert_id=[alert.id],
            description=_("处理套餐【{}】已经被删除或禁用，系统自动忽略该处理").format(
                action_config.get("name") or config_id
            ),
            time=current_timestamp,
            create_time=current_timestamp,
            event_id=current_timestamp,
        )
        AlertLog.bulk_create([AlertLog(**action_log)])
        return False

    def do_create_actions(self):
        """
        创建告警处理动作的核心方法，实现告警通知、分派、升级等完整处理流程

        参数:
            self: 包含以下关键属性
                - alerts: 告警文档列表（AlertDocument对象）
                - strategy_id: 策略ID（用于关联处理规则）
                - signal: 动作信号类型（ActionSignal枚举）
                - alert_ids: 告警ID列表
                - severity: 告警严重程度
                - execute_times: 执行次数计数器
                - relation_id: 关联ID（用于链路追踪）
                - notice_type: 通知类型（ActionNoticeType枚举）

        返回值:
            list: 创建的处理动作ID列表，若发生以下情况返回空列表：
                - 无有效告警
                - 无匹配处理配置
                - 无数据告警的恢复/关闭场景
                - 通知被QoS限制

        该方法实现完整的告警处理流程：
        1. 基础校验与日志记录
        2. 获取处理配置与用户分组
        3. 告警分派与负责人管理
        4. 动作实例ActionInstance创建与批量持久化
        5. 将告警推送到处理队列，执行动作处理逻辑
        6. 状态更新与日志记录
        """
        # 基础校验与日志记录模块
        # 检查告警列表是否为空并记录日志
        if not self.alerts:
            logger.info(
                "[create actions] failed: empty alerts(%s), strategy_id(%s), signal(%s)",
                self.alert_ids,
                self.strategy_id,
                self.signal,
            )
            return []

        logger.info(
            "[create actions]do_create_actions: strategy_id(%s), signal(%s), alert_ids(%s), severity(%s),"
            " execute_times(%s), relation_id(%s)",
            self.strategy_id,
            self.signal,
            self.alert_ids,
            self.severity,
            self.execute_times,
            self.relation_id,
        )

        # 配置获取与预处理模块
        # 获取关联处理配置并进行降噪处理
        actions = self.get_action_relations()
        new_actions: list[ActionInstance] = []
        # 获取告警屏蔽状态及屏蔽配置ID列表
        self.is_alert_shielded, shield_ids = self.get_alert_shield_result()
        # 创建消息队列通知动作
        self.create_message_queue_action(new_actions)

        alert: AlertDocument = self.alerts[0]
        # 无数据告警特殊处理逻辑
        if alert.is_no_data() and self.signal in [ActionSignal.RECOVERED, ActionSignal.CLOSED]:
            # 无数据告警恢复和关闭时仅推送消息队列，不发送通知
            return []

        # 处理配置有效性检查
        if not actions:
            # 策略配置的notice 和 action 未命中当前的signal
            logger.info(
                "[create actions]ignore: empty config for signal(%s), strategy(%s), alerts %s",
                self.signal,
                self.strategy_id,
                self.alert_ids,
            )
            return new_actions

        # 缓存加载模块
        # 从缓存获取处理套餐配置
        action_configs = {
            str(action["config_id"]): ActionConfigCacheManager.get_action_config_by_id(action["config_id"])
            for action in actions
        }
        origin_action_ids = list(action_configs.keys())

        # 插件加载模块
        # 获取全量动作插件信息
        action_plugins = {
            str(plugin["id"]): plugin for plugin in ActionPluginSlz(instance=ActionPlugin.objects.all(), many=True).data
        }

        # 数据初始化模块
        action_instances = []  # 告警套餐实例列表
        # 初始化各类用户组字典
        alerts_assignee = {}  # 告警受理人（固定轮值被通知人）
        alerts_appointee = {}  # 被指派负责人
        alerts_supervisor = {}  # 升级负责人
        alerts_follower = {}  # 关注人（只读）

        # 核心处理流程模块
        alert_logs = []
        qos_alerts = []
        current_qos_count = 0

        # 告警遍历处理循环
        for alert in self.alerts:
            alert_dict = alert.to_dict()
            # 初始化各类用户组字段
            alerts_assignee[alert.id] = alert_dict.get("assignee") or []
            alerts_appointee[alert.id] = alert_dict.get("appointee") or []
            alerts_supervisor[alert.id] = alert_dict.get("supervisor") or []
            alerts_follower[alert.id] = alert_dict.get("follower") or []

            # 告警状态有效性校验
            if not self.is_alert_status_valid(alert):
                # 所有的通知，需要判断信号是否为有效状态
                continue

            itsm_actions: list[dict] = []  # 流程服务类型的告警套餐
            # 告警分派处理，并返回分派管理对象
            assignee_manager: AlertAssigneeManager = self.alert_assign_handle(
                alert, action_configs, origin_action_ids, itsm_actions
            )
            # 自动分派负责人只能追加
            # 手动分派的情况下直接覆盖
            supervisors = []
            assignees = []
            if not assignee_manager:
                # 告警分派异常, 搜索日志: [alert assign error]
                continue
            if not assignee_manager.is_matched and not self.strategy_id:
                # 告警分派如果没有适配到的规则，且没有对应的策略ID，直接忽略
                # 没有策略ID，那么也没有对应的action,后续没有处理的必要
                continue

            if self.notice_type == ActionNoticeType.UPGRADE:
                # 告警升级
                supervisors = assignee_manager.get_supervisors()
                followers = assignee_manager.get_supervisors(user_type=UserGroupType.FOLLOWER)
                # 这里不再做判定，由于可能 action 执行队列堵塞， 导致这里获取到的 supervisor 为空，引起升级告警 action 未创建
                # 仅记录日志
                if not supervisors:
                    logger.warning("notice for alert(%s) get empty supervisor", alert.id)
                is_qos, current_qos_count = self.alert_objs[alert.id].qos_calc(self.signal)
                if is_qos:
                    qos_alerts.append(alert.id)
                    logger.info("ignore to send supervise notice for alert(%s) due to notice qos", alert.id)
                    continue
            else:
                # 示例：["zhangsan", "lisi"]
                assignees: list[str] = assignee_manager.get_assignees()  # 常规通知处理分支
                followers: list[str] = assignee_manager.get_assignees(user_type=UserGroupType.FOLLOWER)  # 告警关注人

            # 用户组合并与去重处理
            alerts_assignee[alert.id] = self.get_alert_related_users(assignees + supervisors, alerts_assignee[alert.id])

            # 告警负责人字段，替换为当前的负责人
            if assignees:
                # 如果有新的负责人，才进行更新
                alerts_appointee[alert.id] = assignees

            # 告警升级负责人
            alerts_supervisor[alert.id] = self.get_alert_related_users(supervisors, alerts_supervisor[alert.id])

            # 告警关注人
            alerts_follower[alert.id] = self.get_alert_related_users(followers, alerts_follower[alert.id])

            # 获取订阅的 follower 用户并合并到 alerts_follower
            if assignee_manager and assignee_manager.match_manager:
                subscription_notify_info, subscription_follow_notify_info = (
                    assignee_manager.get_subscription_notify_info()
                )
                # 从订阅的 follower 通知信息中提取所有用户（格式: {notice_way: [user_list]}）
                subscription_follower_users = []
                for notice_way, users in subscription_follow_notify_info.items():
                    # 排除特殊字段（如 wxbot_mention_users）
                    if notice_way != "wxbot_mention_users" and users:
                        subscription_follower_users.extend(users)
                # 去重并合并到 alerts_follower
                if subscription_follower_users:
                    # 使用集合去重，保持顺序
                    unique_subscription_followers = list(dict.fromkeys(subscription_follower_users))
                    alerts_follower[alert.id] = self.get_alert_related_users(
                        unique_subscription_followers, alerts_follower[alert.id]
                    )
                    logger.info(
                        "[alert_subscription] alert(%s) added subscription followers: %s",
                        alert.id,
                        unique_subscription_followers,
                    )

            for action in actions + itsm_actions:
                action_config = action_configs.get(str(action["config_id"]))
                # 处理套餐无效则跳过
                if not self.is_action_config_valid(alert, action_config, action["config_id"]):
                    continue
                # 获取到插件
                action_plugin = action_plugins.get(str(action_config["plugin_id"]))
                skip_delay = int(action["options"].get("skip_delay", 0))
                current_time = int(time.time())
                # 告警分派中向itsm_actions添加的action不存在signal字段
                if (
                    ActionSignal.ABNORMAL in action.get("signal", [])
                    and current_time - alert["begin_time"] > skip_delay > 0
                ):
                    # 如果当前时间距离告警开始时间，大于skip_delay，则不处理改套餐
                    description = {
                        "config_id": action["config_id"],
                        "action_name": action_config["name"],
                        "action_signal": action["signal"],
                        "skip_delay": skip_delay,
                        "content": f"告警开始时间距离当前时间大于{skip_delay}秒,不处理该套餐",
                    }

                    # 由于并没有实际创建ActionInstance,所以这里的action_instance_id为0
                    action_log = dict(
                        op_type=AlertLog.OpType.ACTION,
                        alert_id=alert.id,
                        description=json.dumps(description, ensure_ascii=False),
                        time=current_time,
                        create_time=current_time,
                        event_id=f"{int(time.time() * 1000)}0",
                    )
                    AlertLog.bulk_create([AlertLog(**action_log)])
                    logger.warning(
                        "[fta_action] AlertID: %s, ActionName: %s, Reason: %s",
                        alert.id,
                        action_config["name"],
                        f"告警开始时间距离当前时间大于{skip_delay}秒,不处理该套餐",
                    )

                    continue
                action_instances.append(
                    self.do_create_action(
                        action_config,
                        action_plugin,
                        alert,
                        action_relation=action,
                        assignee_manager=assignee_manager,
                        shield_ids=shield_ids,
                    )
                )
            if assignee_manager.match_manager:
                alert_log = assignee_manager.match_manager.get_alert_log()
                if alert_log:
                    alert_logs.append(AlertLog(**alert_log))

        # 资源清理模块
        AssignCacheManager.clear()
        # 清理订阅缓存
        SubscribeCacheManager.clear()

        # 批量持久化处理模块
        if action_instances:
            ActionInstance.objects.bulk_create(action_instances)
            # 推送处理事件至收敛队列，并返回处理套餐ID列表
            new_actions.extend(
                # todo 动作收敛在这里
                PushActionProcessor.push_actions_to_queue(
                    self.generate_uuid,
                    alerts=self.alerts,
                    is_shielded=self.is_alert_shielded,
                    need_noise_reduce=self.noise_reduce_result,
                    notice_config=self.notice,
                )
            )

        # 日志记录模块
        logger.info(
            "[create actions]do_create_actions finished, strategy_id %s, alerts %s, signal %s, created actions(%s) %s",
            self.strategy_id,
            self.alert_ids,
            self.signal,
            len(new_actions),
            new_actions,
        )
        # 更新是否已经处理的状态至告警
        # 当前告警如果是降噪处理，也认为是已经处理，不需要创建任务出来
        is_handled = True if self.noise_reduce_result else bool(new_actions)
        self.update_alert_documents(
            alerts_assignee, shield_ids, is_handled, alerts_appointee, alerts_supervisor, alerts_follower
        )
        if qos_alerts:
            # 有qos处理记录， 这里只有可能是通知处理的
            alert_logs.append(Alert.create_qos_log(qos_alerts, current_qos_count, len(qos_alerts)))
        if alert_logs:
            AlertLog.bulk_create(alert_logs)
        return new_actions

    @staticmethod
    def get_alert_related_users(users: list, alert_users: list):
        """
        获取告警相关的负责人并去重
        """
        if not users:
            # 没有新用户的话，直接返回
            return alert_users

        if set(users) == set(alert_users):
            # 如果用户内容一致， 以最近产生的用户顺序为准
            alert_users = users
        else:
            # 不一致的情况下，去重，在添加到原有用户后面
            alert_users.extend([man for man in users if man not in alert_users])
        return alert_users

    def update_alert_documents(
        self, alerts_assignee, shield_ids, is_handled, alerts_appointee, alerts_supervisor, alerts_follower
    ):
        """
        批量更新告警文档并处理版本冲突，包含以下核心流程：
        1. 构建告警更新数据集
        2. 更新内存告警对象属性
        3. 持久化存储告警快照
        4. 重试机制处理版本冲突

        参数:
            alerts_assignee: Dict[str, str] 告警通知人映射表，格式{id: assignee}
            shield_ids: Union[str, None] 告警屏蔽规则ID
            is_handled: bool 处理状态标记
            alerts_appointee: Dict[str, str] 告警负责人映射表，格式{id: appointee}
            alerts_supervisor: Dict[str, str] 告警监督人映射表，格式{id: supervisor}
            alerts_follower: Dict[str, str] 告警关注人映射表，格式{id: follower}

        返回值:
            None 通过批量操作更新ES文档，异常时抛出ConflictError

        该方法实现完整的告警文档更新流程：
        1. 遍历告警列表构建更新数据字典
        2. 同步更新内存对象属性和文档对象属性
        3. 使用双写策略持久化存储告警快照
        4. 最多3次重试处理版本冲突异常
        """
        update_alerts = []
        # 构建告警更新数据集
        for alert in self.alerts:
            update_data = dict(
                id=alert.id,
                is_handled=is_handled,
                is_ack_noticed=True if self.signal == ActionSignal.ACK else alert.is_ack_noticed,
                handle_stage=[HandleStage.HANDLE] if not self.noise_reduce_result else [HandleStage.NOISE_REDUCE],
                is_shielded=self.is_alert_shielded,
                shield_id=shield_ids,
                severity=alert.severity,
                assignee=alerts_assignee[alert.id],
                appointee=alerts_appointee[alert.id],
                follower=alerts_follower[alert.id],
                supervisor=alerts_supervisor[alert.id],
                extra_info=alert.extra_info,
                assign_tags=alert.assign_tags,
            )
            # 同步更新内存对象属性
            for key, value in update_data.items():
                setattr(alert, key, value)
            update_alerts.append(AlertDocument(**update_data))

        # 双写策略持久化存储告警快照
        cached_alerts = [Alert(data=alert.to_dict()) for alert in self.alerts]
        AlertCache.save_alert_to_cache(cached_alerts)
        AlertCache.save_alert_snapshot(cached_alerts)

        # 版本冲突重试机制
        retry_times = 0
        while retry_times < 3:
            # 更新alert 的时候，可能会有版本冲突，所以需要做重试处理，最多3次
            try:
                AlertDocument.bulk_create(update_alerts, action=BulkActionType.UPDATE)
                break
            except ConflictError:
                # 版本冲突一般是由于其他进程并发导致，在1分钟的周期任务频率下会比较严重，可以加重试处理
                logger.info(
                    "[update_alert_document] update alert(%s) failed because of version conflict",
                    [ad.id for ad in self.alerts],
                )
                retry_times += 1

    def _check_circuit_breaking_for_message_queue(self):
        """
        检查 message_queue 类型动作的熔断规则
        :return: tuple(valid_alert_ids, circuit_breaking_alert_ids)
        """
        circuit_breaking_manager = ActionCircuitBreakingManager()

        if not circuit_breaking_manager:
            # 如果熔断管理器不可用，返回所有告警ID
            return self.alert_ids, []

        valid_alert_ids = []
        circuit_breaking_alert_ids = []

        for alert in self.alerts:
            # 构建每个告警的熔断检查上下文信息
            context = {
                "strategy_id": self.strategy_id or alert.strategy_id or 0,
                "bk_biz_id": alert.event.bk_biz_id,
                "plugin_type": "message_queue",
            }

            # 获取数据源标签和类型标签
            data_source_label = ""
            data_type_label = ""

            # 优先从策略配置中获取
            if self.strategy and self.strategy.get("items"):
                first_item = self.strategy["items"][0]
                if first_item.get("query_configs"):
                    first_query_config = first_item["query_configs"][0]
                    data_source_label = first_query_config.get("data_source_label", "")
                    data_type_label = first_query_config.get("data_type_label", "")

            if data_source_label:
                context["data_source_label"] = data_source_label
            if data_type_label:
                context["data_type_label"] = data_type_label

            logger.info(
                f"[circuit breaking] [message_queue] checking alert({alert.id}) for create action dimensions: {context}"
            )
            # 检查当前告警是否命中熔断规则
            is_circuit_breaking = circuit_breaking_manager.is_circuit_breaking(**context)

            if is_circuit_breaking:
                circuit_breaking_alert_ids.append(alert.id)
                logger.info(
                    f"[circuit breaking] [message_queue] skip create action for strategy({context['strategy_id']}) "
                    f"alert({alert.id}): circuit breaking"
                )
            else:
                valid_alert_ids.append(alert.id)

        return valid_alert_ids, circuit_breaking_alert_ids

    def create_message_queue_action(self, new_actions: list):
        """
        创建消息队列推送动作实例并加入执行队列

        参数:
            new_actions: 新增的动作实例ID列表，用于后续批量处理

        返回值:
            None（无显式返回值，通过参数new_actions传递结果）

        该方法实现消息队列推送动作的完整创建流程：
        1. 环境配置校验（消息队列开关和DSN配置）
        2. 告警屏蔽状态处理逻辑
        3. 动作实例创建与关联属性设置
        4. 动作实例入队执行队列
        5. 动作ID回填至任务列表
        """
        # 检查消息队列功能是否启用（前置条件校验）
        need_message_queue = settings.ENABLE_MESSAGE_QUEUE and settings.MESSAGE_QUEUE_DSN
        if not need_message_queue:
            return

        # 处理告警屏蔽状态的特殊逻辑
        if self.is_alert_shielded and not settings.ENABLE_PUSH_SHIELDED_ALERT:
            # 当前告警处于屏蔽状态且配置禁止推送时，记录日志并终止流程
            logger.info(
                "[create actions]ignore push message queue for shielded alert(%s)"
                " because config[ENABLE_PUSH_SHIELDED_ALERT] is %s",
                self.alert_ids,
                settings.ENABLE_PUSH_SHIELDED_ALERT,
            )
            return

        # 检查熔断规则（创建阶段）
        valid_alert_ids, circuit_breaking_alert_ids = self._check_circuit_breaking_for_message_queue()

        # 如果所有告警都被熔断，直接返回
        if not valid_alert_ids:
            logger.info(
                f"[circuit breaking] all alerts({self.alert_ids}) are circuit breaking, "
                f"skip creating message queue action"
            )
            return

        # 如果部分告警被熔断，只为未熔断的告警创建 message_queue 动作
        if circuit_breaking_alert_ids:
            logger.info(
                f"[circuit breaking] partial alerts({circuit_breaking_alert_ids}) are circuit breaking, "
                f"creating message queue action for valid alerts({valid_alert_ids})"
            )

        # 创建动作实例 - 只为未熔断的告警创建 message_queue action
        action_instance = ActionInstance.objects.create(
            alerts=valid_alert_ids,  # 只使用未熔断的告警ID
            signal=self.signal,
            strategy_id=self.strategy_id or 0,
            alert_level=self.severity,
            bk_biz_id=self.alerts[0].event.bk_biz_id,
            dimensions=self.dimensions or [],
            action_plugin={"plugin_type": ActionPluginType.MESSAGE_QUEUE},
        )
        # 只为未熔断的告警推送到执行队列
        valid_alerts = [alert for alert in self.alerts if alert.id in valid_alert_ids]
        PushActionProcessor.push_action_to_execute_queue(action_instance, valid_alerts)
        new_actions.append(action_instance.id)

    def do_create_action(
        self,
        action_config: dict,
        action_plugin: dict,
        alert: AlertDocument,
        action_relation=None,
        assignee_manager=None,
        shield_ids=None,
    ):
        """
        根据套餐配置创建处理记录，并返回处理套餐实例

        参数:
            action_config (dict): 处理套餐配置快照，包含id和业务ID等核心字段
            action_plugin (dict): 处理套餐类型快照，包含plugin_type等插件元数据
            alert (AlertDocument): 待处理的告警文档对象，包含告警核心属性
            action_relation (dict, optional): 关联处理套餐关系配置，默认为空字典
            assignee_manager (object, optional): 告警负责人管理器实例，默认为None
            shield_ids (list, optional): 屏蔽规则ID列表，默认为None

        返回值:
            ActionInstance: 包含完整处理上下文的处理实例对象，包含以下关键属性：
                - alerts: 关联告警ID列表
                - signal: 处理信号类型
                - inputs: 处理上下文输入参数
                - is_parent_action: 是否为父级处理任务
                - assignee: 实际处理人列表

        该方法实现完整的处理记录创建流程，包含：
        1. 输入参数初始化与告警状态映射
        2. 通知任务的特殊处理逻辑（负责人/关注人通知分离）
        3. 二次确认机制集成
        4. 周期处理记录维护（执行次数/时间追踪）
        """

        # 初始化处理关系配置
        # 当未提供action_relation时使用空字典作为默认值
        action_relation = action_relation or {}

        # 构建处理上下文输入参数
        # 包含告警状态、屏蔽信息、通知配置等核心处理依据
        inputs = {
            "alert_latest_time": alert.latest_time,  # 告警最新发生时间
            "is_alert_shielded": self.is_alert_shielded,  # 告警屏蔽状态
            "shield_ids": shield_ids,  # 关联屏蔽规则ID列表
            "shield_detail": self.shield_detail,  # 屏蔽规则详细信息
            "is_unshielded": self.is_unshielded,  # 解除屏蔽状态
            "notice_type": self.notice_type,  # 通知类型标识
            # 提取排除的通知方式
            "exclude_notice_ways": action_relation["options"].get("exclude_notice_ways", {}).get(self.signal, []),
            # 构建时间范围字符串
            "time_range": "--".join(
                [
                    action_relation["options"].get("start_time", "00:00:00"),
                    action_relation["options"].get("end_time", "23:59:59"),
                ]
            ),
        }

        # 初始化父级任务标识
        is_parent_action = False

        # 尝试获取告警级别
        # 优先使用告警对象自身级别，失败时回退到默认级别
        alert_level = EventSeverity.REMIND
        try:
            alert_level = alert.severity or int(self.severity)
        except ValueError as error:
            logger.error("Get alert level failed: %s, alerts: %s", str(error), alert.alert_name)

        # 通知类型处理逻辑
        # 创建父级通知任务并准备通知接收人信息
        if action_plugin["plugin_type"] == ActionPluginType.NOTICE:
            # 通知套餐，父 action_instance 创建
            is_parent_action = True  # 标记为父级任务

            # 获取负责人和关注人通知信息
            notify_info = assignee_manager.get_notify_info()
            # 获取要通知的关注人
            follow_notify_info = assignee_manager.get_notify_info(user_type=UserGroupType.FOLLOWER)

            # 处理无负责人通知信息的特殊情况
            if not notify_info and self.notice_type != ActionNoticeType.UPGRADE:
                # 如果没有负责人的通知信息，需要将负责人通知信息带上，默认以当前适配到的通知方式为准
                notify_configs = {notice_way: [] for notice_way in follow_notify_info.keys()}
                notify_info = assignee_manager.get_appointee_notify_info(notify_configs)

            # 获取并合并订阅用户信息
            subscription_notify_info, subscription_follow_notify_info = assignee_manager.get_subscription_notify_info()
            self._merge_notify_info(notify_info, subscription_notify_info)
            self._merge_notify_info(follow_notify_info, subscription_follow_notify_info)

            # 如果当前用户即是负责人，又是通知人, 需要进行去重, 以通知人为准
            for notice_way, receivers in follow_notify_info.items():
                valid_receivers = [
                    receiver for receiver in receivers if receiver not in notify_info.get(notice_way, [])
                ]
                follow_notify_info[notice_way] = valid_receivers
            inputs["notify_info"] = notify_info
            inputs["follow_notify_info"] = follow_notify_info
            # 设置语音通知模式
            voice_notice = (
                action_config.get("execute_config", {})
                .get("template_detail", {})
                .get("voice_notice", VoiceNoticeMode.PARALLEL)
            )
            # 设置语音通知模式(默认为并行)
            inputs["voice_notice_mode"] = voice_notice
        try:
            # TODO: 如果有更多的处理场景，需要将二次确认的处理提到更前端
            DoubleCheckHandler(alert).handle(inputs)
        except Exception:  # pylint: disable=broad-except
            logger.exception("二次确认发生错误，跳过处理 Alert<%s>", alert)

        # 获取关联ID
        relation_id = action_relation.get("id") or 0

        # 异常信号处理逻辑
        # 更新周期处理记录（执行次数/时间戳）
        if self.signal in ActionSignal.ABNORMAL_SIGNAL and alert.extra_info:
            # 如果处理的时候，记录第一次一次通知时间和通知次数，用来作为记录当前告警是否已经产生通知
            handle_record = {
                "last_time": int(time.time()),
                "is_shielded": self.is_alert_shielded,
                "latest_anomaly_time": alert.latest_time,
                "execute_times": self.execute_times + 1,
            }

            # 维护周期处理记录
            if alert.cycle_handle_record:
                history_record = alert.cycle_handle_record.get(str(relation_id))
                if not history_record or history_record["execute_times"] < handle_record["execute_times"]:
                    alert.extra_info["cycle_handle_record"][str(relation_id)] = handle_record
            else:
                # 以关联的处理套餐ID为key，创建周期处理记录
                alert.extra_info["cycle_handle_record"] = {str(relation_id): handle_record}

        # 创建并返回处理实例
        # 整合所有处理参数和上下文信息
        return ActionInstance(
            alerts=[alert.id],
            signal=self.signal,
            strategy_id=self.strategy_id or alert.strategy_id or 0,
            inputs=inputs,
            alert_level=alert_level,
            is_parent_action=is_parent_action,
            action_config=action_config,
            action_config_id=action_config["id"],
            action_plugin=action_plugin,
            bk_biz_id=alert.event.bk_biz_id or action_config["bk_biz_id"],
            assignee=assignee_manager.get_appointees(action_id=action_config["id"])
            or assignee_manager.get_origin_notice_receivers(),
            generate_uuid=self.generate_uuid,
            dimensions=self.dimensions or [],
            dimension_hash=self.dimension_hash,
            strategy=self.strategy,
            strategy_relation_id=relation_id,
            execute_times=self.execute_times,
        )
