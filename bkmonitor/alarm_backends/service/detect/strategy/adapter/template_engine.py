"""
TemplateEngine 适配器

将 Django 模板引擎适配为 TsDetect 的 ITemplateEngine 接口。
"""

import logging
from typing import Any

from django.template import Context, Template

from tsdetect.core.interfaces import ITemplateEngine

logger = logging.getLogger("detect")


class DjangoTemplateEngine(ITemplateEngine):
    """
    Django 模板引擎适配器

    封装 Django 的模板系统，实现 TsDetect 的 ITemplateEngine 接口。
    """

    def __init__(self, auto_escape: bool = True):
        """
        初始化适配器

        Args:
            auto_escape: 是否自动转义 HTML
        """
        self.auto_escape = auto_escape
        self._template_cache: dict[str, Template] = {}

    def render(self, template: str, context: dict[str, Any]) -> str:
        """
        渲染模板

        Args:
            template: 模板字符串
            context: 上下文变量字典

        Returns:
            渲染后的字符串
        """
        if not template:
            return ""

        try:
            # 获取或编译模板
            tpl = self.compile(template)

            # 创建上下文
            ctx = Context(context, autoescape=self.auto_escape)

            # 渲染
            return tpl.render(ctx)
        except Exception as e:
            logger.warning(f"Template render failed: {e}, template={template[:100]}...")
            return template

    def compile(self, template: str) -> Template:
        """
        编译模板

        Args:
            template: 模板字符串

        Returns:
            编译后的 Template 对象
        """
        # 检查缓存
        if template in self._template_cache:
            return self._template_cache[template]

        # 编译并缓存
        tpl = Template(template)
        self._template_cache[template] = tpl
        return tpl

    def clear_cache(self):
        """清除模板缓存"""
        self._template_cache.clear()


class StringFormatEngine(ITemplateEngine):
    """
    字符串格式化模板引擎

    使用 Python 的 str.format() 进行简单的模板渲染，
    不依赖 Django。
    """

    def render(self, template: str, context: dict[str, Any]) -> str:
        """
        渲染模板

        Args:
            template: 模板字符串，使用 {variable} 语法
            context: 上下文变量字典

        Returns:
            渲染后的字符串
        """
        if not template:
            return ""

        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template
        except Exception as e:
            logger.warning(f"Template format failed: {e}")
            return template

    def compile(self, template: str) -> str:
        """字符串格式化不需要编译"""
        return template


class Jinja2TemplateEngine(ITemplateEngine):
    """
    Jinja2 模板引擎适配器

    可选的 Jinja2 模板支持，需要安装 jinja2 包。
    """

    def __init__(self, auto_escape: bool = True):
        """
        初始化适配器

        Args:
            auto_escape: 是否自动转义 HTML
        """
        try:
            from jinja2 import Environment

            self._env = Environment(autoescape=auto_escape)
        except ImportError:
            raise ImportError("jinja2 is required for Jinja2TemplateEngine")

        self._template_cache = {}

    def render(self, template: str, context: dict[str, Any]) -> str:
        """
        渲染模板

        Args:
            template: Jinja2 模板字符串
            context: 上下文变量字典

        Returns:
            渲染后的字符串
        """
        if not template:
            return ""

        try:
            tpl = self.compile(template)
            return tpl.render(**context)
        except Exception as e:
            logger.warning(f"Jinja2 render failed: {e}")
            return template

    def compile(self, template: str):
        """
        编译模板

        Args:
            template: 模板字符串

        Returns:
            编译后的模板对象
        """
        if template in self._template_cache:
            return self._template_cache[template]

        tpl = self._env.from_string(template)
        self._template_cache[template] = tpl
        return tpl


def get_default_template_engine() -> ITemplateEngine:
    """
    获取默认的模板引擎

    Returns:
        Django 模板引擎实例
    """
    return DjangoTemplateEngine()
