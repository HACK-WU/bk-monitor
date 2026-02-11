"""Notification 通知节点

支持多渠道告警通知：邮件、短信、微信、企业微信、Webhook。
"""

import logging
from typing import Any

from framework.pipeline.context import ProcessContext
from framework.processor.base import ProcessResult, ProcessStatus
from framework.processor.registry import register_processor
from nodes.base import BaseNode

logger = logging.getLogger(__name__)


class NotificationChannel:
    """通知渠道基类"""

    channel_type: str = ""

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        """发送通知，返回是否成功"""
        raise NotImplementedError


class EmailChannel(NotificationChannel):
    """邮件通知"""

    channel_type = "email"

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        receivers = config.get("receivers", [])
        title = config.get("title", "告警通知")
        # TODO: 对接邮件发送服务
        logger.info("[%s] 发送邮件通知: receivers=%s, title=%s", context.trace_id, receivers, title)
        return True


class SMSChannel(NotificationChannel):
    """短信通知"""

    channel_type = "sms"

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        receivers = config.get("receivers", [])
        logger.info("[%s] 发送短信通知: receivers=%s", context.trace_id, receivers)
        return True


class WechatChannel(NotificationChannel):
    """微信通知"""

    channel_type = "wechat"

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        receivers = config.get("receivers", [])
        logger.info("[%s] 发送微信通知: receivers=%s", context.trace_id, receivers)
        return True


class WeworkChannel(NotificationChannel):
    """企业微信通知"""

    channel_type = "wework"

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        receivers = config.get("receivers", [])
        group_id = config.get("group_id", "")
        logger.info("[%s] 发送企业微信通知: receivers=%s, group=%s", context.trace_id, receivers, group_id)
        return True


class WebhookChannel(NotificationChannel):
    """Webhook 通知"""

    channel_type = "webhook"

    def send(self, context: ProcessContext, config: dict[str, Any]) -> bool:
        url = config.get("url", "")
        # TODO: 对接 HTTP 请求发送
        logger.info("[%s] 发送 Webhook 通知: url=%s", context.trace_id, url)
        return True


_CHANNEL_MAP: dict[str, type] = {
    "email": EmailChannel,
    "sms": SMSChannel,
    "wechat": WechatChannel,
    "wework": WeworkChannel,
    "webhook": WebhookChannel,
}


@register_processor
class NotificationNode(BaseNode):
    """通知节点

    配置示例:
    {
        "channels": [
            {
                "type": "email",
                "receivers": ["admin@example.com"],
                "title": "【告警】{alert_name}"
            },
            {
                "type": "wework",
                "receivers": ["ops_group"],
                "group_id": "group_001"
            }
        ],
        "template": "告警: {alert_name}, 级别: {severity}"
    }
    """

    name = "notification"
    version = "1.0.0"

    def on_initialize(self, config: dict[str, Any]) -> None:
        self._channels_config = config.get("channels", [])
        self._template = config.get("template", "")

    def process(self, context: ProcessContext) -> ProcessResult:
        results = []
        success_count = 0
        fail_count = 0

        for ch_config in self._channels_config:
            ch_type = ch_config.get("type", "")
            channel_class = _CHANNEL_MAP.get(ch_type)

            if not channel_class:
                logger.warning("[%s] 未知通知渠道: %s", context.trace_id, ch_type)
                results.append({"channel": ch_type, "success": False, "error": "未知渠道"})
                fail_count += 1
                continue

            try:
                channel = channel_class()
                success = channel.send(context, ch_config)
                results.append({"channel": ch_type, "success": success})
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logger.error("[%s] 通知渠道 %s 发送异常: %s", context.trace_id, ch_type, e)
                results.append({"channel": ch_type, "success": False, "error": str(e)})
                fail_count += 1

        return ProcessResult(
            status=ProcessStatus.SUCCESS if success_count > 0 else ProcessStatus.FAILED,
            data={
                "channels": results,
                "success_count": success_count,
                "fail_count": fail_count,
            },
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type"],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["email", "sms", "wechat", "wework", "webhook"],
                            },
                            "receivers": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "template": {"type": "string"},
            },
        }
