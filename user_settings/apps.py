# user_settings/apps.py
from django.apps import AppConfig, apps
from django.db import connection
from django.db.models.signals import post_migrate
from django.core.management import call_command

import logging

logger = logging.getLogger('dart')


def load_default_settings(sender, **kwargs):
    table_name = 'user_settings_globalgeographicregion'
    if table_name not in connection.introspection.table_names():
        return

    GlobalGeographicRegion = apps.get_model('user_settings', 'GlobalGeographicRegion')
    if not GlobalGeographicRegion.objects.exists():
        logger.debug("Importing Default Geographic Regions")
        call_command("loaddata", "default_geographic_region_fixtures.json",
            app="user_settings", verbosity=0, ignorenonexistent=True
        )

    table_name = 'user_settings_globalstation'
    if table_name not in connection.introspection.table_names():
        return

    GlobalStation = apps.get_model('user_settings', 'GlobalStation')
    if not GlobalStation.objects.exists():
        logger.debug("Importing Default Global Stations")
        call_command("loaddata", "default_station_fixtures.json",
            app="user_settings", verbosity=0, ignorenonexistent=True
        )


class UserSettingsConfig(AppConfig):
    name = "user_settings"

    def ready(self):

        post_migrate.connect(load_default_settings, sender=self)
