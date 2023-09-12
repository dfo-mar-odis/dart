from django.apps import AppConfig
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections

import logging

logger = logging.getLogger('dart')


class CoreAppConf(AppConfig):
    name = 'core'

    def ready(self):
        from . import models

        try:
            if 'core_sampletype' in connection.introspection.table_names():
                if not models.SampleType.objects.all().exists():
                    logger.info("Loading sample type fixtures, this may take a moment")
                    call_command('loaddata', 'sample_type_fixtures')

        except Exception as ex:
            logger.error('Could not load biochem fixtures')
            logger.exception(ex)
        # if not settings.DEBUG:
        #     call_command('loaddata', 'biochem_fixtures')
