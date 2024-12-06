from django.urls import re_path as url  # noqa

from console import views  # noqa

urlpatterns = (url(r"^accounts/logout", views.user_exit),)
