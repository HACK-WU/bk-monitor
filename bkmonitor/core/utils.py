# coding=utf-8
# Time: 2025/7/29 22:52
# name: utils
# author: HACK-WU

from blueapps.account import load_backend, ConfFixture
from django.utils.module_loading import import_string


def get_bk_login_ticket(request):
    """
    从 request 中获取用户登录凭据
    """
    form_cls = "AuthenticationForm"
    context = [request.COOKIES, request.GET]

    if request.is_rio():
        # 为了保证能够使用RIO,需要调整import路径
        context.insert(0, request.META)
        AuthenticationForm = import_string("blueapps.account.components.rio.forms.RioAuthenticationForm")
    else:
        if request.is_wechat():
            form_cls = "WeixinAuthenticationForm"

        AuthenticationForm = load_backend("{}.forms.{}".format(ConfFixture.BACKEND_TYPE, form_cls))

    for form in (AuthenticationForm(c) for c in context):
        if form.is_valid():
            return form.cleaned_data

    return {}


