from django.apps import AppConfig
from django.core.management import call_command

from dart2 import settings


class BioTablesAppConf(AppConfig):
    name = 'bio_tables'

    def ready(self):
        if not settings.DEBUG:
            call_command('loaddata', 'biochem_fixtures')
