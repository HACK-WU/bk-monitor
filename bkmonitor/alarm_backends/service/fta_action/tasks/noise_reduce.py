import logging
import time
from collections import defaultdict

from django.conf import settings
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from alarm_backends.core.alert import Alert
from alarm_backends.core.alert.alert import AlertKey
from alarm_backends.core.cache import key
from alarm_backends.core.lock.service_lock import service_lock
from alarm_backends.service.fta_action.utils import PushActionProcessor
from alarm_backends.service.scheduler.app import app
from bkmonitor.documents import AlertDocument, AlertLog
from bkmonitor.documents.base import BulkActionType
from bkmonitor.models import ActionInstance
from bkmonitor.utils.common_utils import count_md5
from constants.action import ActionSignal
from constants.alert import HandleStage
from core.errors.alarm_backends import LockError

logger = logging.getLogger("fta_action.run")


@app.task(ignore_result=True, queue="celery_action")
def run_noise_reduce_task(processor):
    processor.process()


class NoiseReduceRecordProcessor:
    def __init__(self, notice_config, signal, strategy_id, alert: AlertDocument, generate_uuid):
        self.noise_reduce_config = notice_config.get("options", {}).get("noise_reduce_config", {})
        self.signal = signal
        self.strategy_id = strategy_id
        self.redis_client = key.NOISE_REDUCE_ABNORMAL_KEY.client
        self.alert = alert
        self.generate_uuid = generate_uuid
        self.noise_dimension_hash = count_md5(self.noise_reduce_config.get("dimensions", []))
        self.abnormal_record_key = key.NOISE_REDUCE_ABNORMAL_KEY.get_key(
            strategy_id=self.strategy_id, noise_dimension_hash=self.noise_dimension_hash, severity=self.alert.severity
        )
        self.alert_record_key = key.NOISE_REDUCE_ALERT_KEY.get_key(
            strategy_id=self.strategy_id, noise_dimension_hash=self.noise_dimension_hash, severity=self.alert.severity
        )

    @cached_property
    def need_noise_reduce(self):
        """
        是否需要在新建任务的时候进行通知降噪
        :param notice_config: 通知配置
        :param signal: 通知信号
        :param execute_times:执行次数
        :return:
        """
        return self.signal == ActionSignal.ABNORMAL and self.noise_reduce_config.get("is_enabled")

    def process(self):
        """
        执行告警降噪处理流程

        返回值:
            bool: True表示告警被降噪抑制，False表示告警正常发送

        该方法实现完整的告警降噪机制，包含：
        1. 降噪条件判断：检查是否需要进行降噪处理
        2. 维度值提取：从告警中提取配置的降噪维度值
        3. 降噪窗口管理：使用分布式锁确保同一策略只创建一个降噪窗口
        4. 异步任务调度：在降噪时间窗口结束时触发汇总通知
        5. 告警记录存储：将告警信息记录到Redis有序集合中
        6. 操作日志记录：记录降噪抑制的操作日志
        """
        # 1. 判断是否需要降噪处理
        if not self.need_noise_reduce:
            return False

        logger.info(
            "start to record dimension values of strategy(%s), start alert(%s)", self.strategy_id, self.alert.id
        )
        current_timestamp = int(time.time())

        # 2. 提取告警维度信息
        # 优先使用原始告警数据中的维度，否则使用告警对象的维度
        alert_dimensions = {dimension.key: dimension.value for dimension in self.alert.dimensions}
        dimensions = self.alert.origin_alarm["data"]["dimensions"] if self.alert.origin_alarm else alert_dimensions

        # 3. 根据降噪配置提取指定的维度值
        dimension_value = {
            dimension_key: dimensions.get(dimension_key) for dimension_key in self.noise_reduce_config["dimensions"]
        }
        # 计算维度值的MD5哈希，用于去重
        dimension_value_hash = count_md5(dimension_value)

        # 4. 使用分布式锁管理降噪窗口的创建
        try:
            with service_lock(
                key.NOISE_REDUCE_INIT_LOCK_KEY,
                strategy_id=self.strategy_id,
                noise_dimension_hash=self.noise_dimension_hash,
            ):
                # 5. 检查当前降噪时间窗口内是否已有告警记录
                # 如果没有记录，说明这是窗口内的第一个告警，需要创建降噪任务
                if not self.redis_client.zrangebyscore(
                    self.abnormal_record_key,
                    (current_timestamp - settings.NOISE_REDUCE_TIMEDELTA * 60),
                    current_timestamp,
                ):
                    # 6. 创建降噪执行处理器
                    execute_processor = NoiseReduceExecuteProcessor(
                        self.noise_reduce_config, self.strategy_id, self.alert.latest_time, self.alert.severity
                    )
                    # 7. 调度异步任务，在降噪窗口结束后执行汇总通知
                    # countdown: 延迟执行时间（降噪窗口时长）
                    # expires: 任务过期时间（窗口时长+2分钟缓冲）
                    task_id = run_noise_reduce_task.apply_async(
                        (execute_processor,),
                        expires=(settings.NOISE_REDUCE_TIMEDELTA + 2) * 60,
                        countdown=settings.NOISE_REDUCE_TIMEDELTA * 60,
                    )
                    logger.info(
                        "start noise reduce window for strategy(%s), new task(%s), start alert(%s)",
                        self.strategy_id,
                        task_id,
                        self.alert.id,
                    )
        except LockError:
            # 8. 获取锁失败说明已有其他进程在处理该策略的降噪窗口创建，可以忽略
            logger.info(
                "noise reduce window of strategy(%s) already exist, current alert(%s)", self.strategy_id, self.alert.id
            )

        # 9. 记录告警维度值到Redis有序集合（用于降噪窗口结束时的汇总统计）
        # key: abnormal_record_key, member: 维度值哈希, score: 时间戳
        self.redis_client.zadd(self.abnormal_record_key, {dimension_value_hash: current_timestamp})

        # 10. 记录告警ID到Redis有序集合（用于追踪被降噪的具体告警）
        # key: alert_record_key, member: "告警ID--UUID", score: 时间戳
        self.redis_client.zadd(self.alert_record_key, {f"{self.alert.id}--{self.generate_uuid}": current_timestamp})

        # 11. 插入告警操作日志，记录降噪抑制信息
        action_log = dict(
            op_type=AlertLog.OpType.ACTION,
            alert_id=[self.alert.id],
            description=_("当前告警策略正在进行降噪处理中，通知被抑制，满足降噪条件之后将会重新发出"),
            time=current_timestamp,
            create_time=current_timestamp,
            event_id=current_timestamp,
        )
        AlertLog.bulk_create([AlertLog(**action_log)])

        logger.info("end to record dimension values of strategy(%s), start alert(%s)", self.strategy_id, self.alert.id)
        # 12. 返回True表示告警已被降噪抑制
        return True


class NoiseReduceExecuteProcessor:
    def __init__(self, noise_reduce_config, strategy_id, latest_time, severity):
        self.noise_reduce_config = noise_reduce_config
        self.count = self.noise_reduce_config.get("count")
        self.strategy_id = strategy_id
        self.begin_time = latest_time
        self.end_time = None
        self.noise_dimension_hash = count_md5(self.noise_reduce_config["dimensions"])
        self.redis_client = None
        self.need_notice = False
        self.total_record_key = key.NOISE_REDUCE_TOTAL_KEY.get_key(
            strategy_id=self.strategy_id, noise_dimension_hash=self.noise_dimension_hash
        )
        self.abnormal_record_key = key.NOISE_REDUCE_ABNORMAL_KEY.get_key(
            strategy_id=self.strategy_id, noise_dimension_hash=self.noise_dimension_hash, severity=severity
        )
        self.alert_record_key = key.NOISE_REDUCE_ALERT_KEY.get_key(
            strategy_id=self.strategy_id, noise_dimension_hash=self.noise_dimension_hash, severity=severity
        )

    def process(self):
        """
        执行降噪窗口结束后的汇总处理流程

        该方法在降噪时间窗口结束时被异步任务调用，负责：
        1. 数据统计：从Redis中获取窗口内的异常告警和总告警数据
        2. 阈值判断：计算异常告警占比，判断是否达到降噪阈值
        3. 通知决策：根据阈值判断结果决定是否发送汇总通知
        4. 缓存清理：清理Redis中的降噪窗口数据
        5. 动作创建：创建降噪汇总通知动作
        """
        # 1. 初始化执行环境
        self.end_time = int(time.time())
        self.redis_client = key.NOISE_REDUCE_TOTAL_KEY.client
        dimensions = ",".join(self.noise_reduce_config["dimensions"])
        logger.info(
            "begin execute noise reduce task of strategy(%s) dimension_hash(%s) dimensions(%s)",
            self.strategy_id,
            self.noise_dimension_hash,
            dimensions,
        )

        try:
            # 2. 使用分布式锁确保同一降噪窗口只被处理一次
            with service_lock(
                key.NOISE_REDUCE_OPERATE_LOCK_KEY,
                strategy_id=self.strategy_id,
                noise_dimension_hash=self.noise_dimension_hash,
            ):
                # 3. 从Redis有序集合中获取降噪窗口内的数据
                # 获取异常告警的维度哈希列表（被降噪抑制的告警）
                dimension_hash_keys = self.redis_client.zrangebyscore(
                    self.abnormal_record_key, self.begin_time, self.end_time
                )
                # 获取总告警的维度哈希列表（包含所有告警）
                total_dimension_hash_keys = self.redis_client.zrangebyscore(
                    self.total_record_key, self.begin_time, self.end_time
                )
                # 获取被降噪的告警ID列表
                alert_keys = self.redis_client.zrangebyscore(self.alert_record_key, self.begin_time, self.end_time)

                # 4. 解析告警信息（格式：告警ID--UUID）
                alert_info = [alert_key.split("--") for alert_key in alert_keys]
                alert_ids = [item[0] for item in alert_info]
                generate_uuids = [item[1] for item in alert_info]

                # 5. 清理Redis中的降噪窗口缓存数据
                self.clear_cache()

                # 6. 计算异常告警占比（异常告警数 / 总告警数 * 100）
                noise_percent = (
                    len(dimension_hash_keys) * 100 // len(total_dimension_hash_keys)
                    if len(total_dimension_hash_keys)
                    else 0
                )

                # 7. 判断是否达到降噪阈值
                if len(dimension_hash_keys) * 100 // len(total_dimension_hash_keys) < self.count:
                    # 7.1 未达到阈值：记录日志并抑制通知
                    action_log = dict(
                        op_type=AlertLog.OpType.ACTION,
                        alert_id=alert_ids,
                        description=_(
                            "在一个降噪收敛窗口（{}min）内, 未达到设置的阈值{}%, 告警通知已被抑制, 当前比值为{}%"
                        ).format(settings.NOISE_REDUCE_TIMEDELTA, self.count, noise_percent),
                        time=self.end_time,
                        create_time=self.end_time,
                        event_id=self.end_time,
                    )
                    AlertLog.bulk_create([AlertLog(**action_log)])

                    logger.info(
                        "count(%s) of noise reduce task of strategy(%s) dimension_hash(%s) is less than settings(%s), "
                        "notice would be canceled",
                        noise_percent,
                        self.strategy_id,
                        self.noise_dimension_hash,
                        self.count,
                    )
                else:
                    # 7.2 达到阈值：标记需要发送通知
                    self.need_notice = True
                    logger.info(
                        "count(%s) of noise reduce task of strategy(%s) dimension_hash(%s) is more than settings(%s), "
                        "ready to create notice action",
                        noise_percent,
                        self.strategy_id,
                        self.noise_dimension_hash,
                        self.count,
                    )

                # 8. 创建降噪汇总通知动作（无论是否达到阈值都会创建，但通知内容不同）
                self.create_noise_reduce_actions(generate_uuids, alert_ids)

        except LockError:
            # 9. 获取锁失败说明已有其他进程在处理该降噪窗口，可以忽略
            logger.info(
                "noise reduce task of strategy(%s) dimension_hash(%s) already exist",
                self.strategy_id,
                self.noise_dimension_hash,
            )

        logger.info(
            "end execute noise reduce task of strategy(%s) dimension_hash(%s) dimensions(%s)",
            self.strategy_id,
            self.noise_dimension_hash,
            dimensions,
        )

    def clear_cache(self):
        """
        清理掉过期的内容
        :return:
        """
        self.redis_client.delete(self.abnormal_record_key)
        self.redis_client.zremrangebyscore(self.total_record_key, 0, self.begin_time)
        self.redis_client.delete(self.alert_record_key)

    def create_noise_reduce_actions(self, generate_uuids, alert_ids):
        """
        降噪窗口结束后创建通知任务或更新告警状态

        参数:
            generate_uuids (List[str]): 主任务UUID列表，用于关联父任务和子任务
            alert_ids (List[int]): 告警ID列表，标识本次降噪窗口涉及的所有告警

        返回值:
            None: 无显式返回值，通过数据库操作和队列推送完成任务创建

        该方法实现降噪窗口结束后的核心处理流程：
        1. 查询父任务ID列表（用于后续过滤）
        2. 批量获取告警文档对象并构建映射关系
        3. 根据降噪判断结果执行不同分支：
           - 需要通知：创建子任务并批量入库
           - 被抑制：更新告警处理阶段为NOISE_REDUCE
        4. 将所有相关任务（父任务+子任务）推送到收敛队列
        """
        logger.info(
            "begin to create noise reduce action for strategy(%s) dimension_hash(%s)",
            self.strategy_id,
            self.noise_dimension_hash,
        )

        # 1. 初始化子任务列表容器
        all_sub_actions = []

        # 2. 查询所有父任务的ID列表
        # 用于后续过滤查询，确保只处理父任务及其关联的子任务
        parent_action_ids = list(
            ActionInstance.objects.filter(is_parent_action=True, generate_uuid__in=generate_uuids).values_list(
                "id", flat=True
            )
        )

        # 3. 批量获取告警文档对象
        # 构建告警键列表，用于从ES中批量查询告警详情
        alert_keys = [AlertKey(alert_id=alert_id, strategy_id=self.strategy_id) for alert_id in alert_ids]
        # 将告警列表转换为字典映射：{alert_id: AlertDocument对象}
        alerts = {alert.id: AlertDocument(**alert.data) for alert in Alert.mget(alert_keys)}

        # 4. 初始化动作与告警的关联关系字典
        # 格式：{generate_uuid: [AlertDocument对象列表]}
        action_alert_relation = defaultdict(list)

        # 5. 根据降噪判断结果执行不同的处理分支
        if self.need_notice:
            # 分支A：达到降噪阈值，需要发送通知
            # 遍历所有父任务，为每个父任务创建对应的子任务
            for parent_action in ActionInstance.objects.filter(is_parent_action=True, generate_uuid__in=generate_uuids):
                # 5.1 创建子任务列表（按通知方式+接收人维度拆分）
                # need_create=False 表示不立即入库，而是先收集到列表中
                all_sub_actions.extend(parent_action.create_sub_actions(need_create=False))

                # 5.2 建立父任务与告警的关联关系
                # 从父任务的alerts字段中取第一个告警ID，获取对应的告警文档对象
                action_alert_relation[parent_action.generate_uuid].append(alerts.get(parent_action.alerts[0], None))

            # 5.3 批量创建子任务入库
            # 使用bulk_create提升性能，batch_size=100控制每批次插入数量
            if all_sub_actions:
                ActionInstance.objects.bulk_create(all_sub_actions, batch_size=100)
        else:
            # 分支B：未达到降噪阈值，通知被抑制
            # 6. 更新告警的处理阶段为"已抑制"（NOISE_REDUCE）
            # 构建告警文档列表，仅更新handle_stage字段
            reduced_alerts = [
                AlertDocument(id=alert_id, handle_stage=[HandleStage.NOISE_REDUCE]) for alert_id in alerts
            ]
            # 批量更新告警文档到ES
            AlertDocument.bulk_create(reduced_alerts, action=BulkActionType.UPDATE)

        # 7. 推送任务到收敛队列
        # 查询所有相关的任务实例（包括父任务和子任务）
        # 使用Q对象构建复杂查询条件：parent_action_id在父任务ID列表中 OR id在父任务ID列表中
        PushActionProcessor.push_actions_to_converge_queue(
            list(
                ActionInstance.objects.filter(generate_uuid__in=generate_uuids).filter(
                    Q(parent_action_id__in=parent_action_ids) | Q(id__in=parent_action_ids)
                )
            ),
            action_alert_relation,
        )
