import os.path
import sys

from os import listdir

from django.apps import AppConfig
from django.conf import settings


class SettingsdbConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'settingsdb'

    # By using the app.py ready function we'll be running migrations and installing fixtures on possibly
    # dozens of databases every time the dart application starts. We may only want to do this when a user actually
    # access a database.
    def ready(self):
        # if any of these actions are being preformed we don't want to run migrations and load fixtures
        if 'test' in sys.argv or 'migrate' in sys.argv or 'collectstatic' in sys.argv or 'makemigrations' in sys.argv:
            return

        from . import models, utils

        if not models.LocalSetting.objects.all().exists():
            default = models.LocalSetting()
            default.save()

        db_settings: models.LocalSetting = models.LocalSetting.objects.first()
        db_dir = db_settings.database_location

        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        databases = [f.replace(".sqlite3", "") for f in listdir(db_dir) if
                     os.path.isfile(os.path.join(db_dir, f)) and f.endswith('sqlite3')]

        keys = [k for k in settings.DATABASES.keys() if k != 'default']
        for key in keys:
            if key not in databases:
                settings.DATABASES.pop(key)

        for database in databases:
            utils.add_database(database)
