from django.urls import re_path as url, include

app_name = "log_adapter"

urlpatterns = [
    url(r"^", include("log_adapter.home.urls")),
]
