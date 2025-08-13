# coding=utf-8
# Time: 2025/8/13 22:31
# name: settings
# author: HACK-WU

from django.conf import settings
from rest_framework.settings import APISettings

DEFAULT = {
    "DEFAULT_USING_CACHE": "drf_resource.cache.DefaultUsingCache"
}

IMPORT_STRINGS = [
    "DEFAULT_USING_CACHE"
]


class DrfResourceSettings(APISettings):
    """
    DrfResourceSettings
    """

    @property
    def user_settings(self):
        if not hasattr(self, '_user_settings'):
            self._user_settings = getattr(settings, 'DRF_RESOURCE', {})
        return self._user_settings


resource_settings = DrfResourceSettings(None, DEFAULT, IMPORT_STRINGS)
