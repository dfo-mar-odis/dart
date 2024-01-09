import os.path
import sys
from datetime import datetime
import pytz

from django.apps import AppConfig
from django.core.management import call_command
from django.db import connection

from dart2 import settings

import logging

logger = logging.getLogger('dart')


class BioTablesAppConf(AppConfig):
    name = 'bio_tables'

    def ready(self):
        if 'migrate' in sys.argv or 'collectstatic' in sys.argv:
            # if runserver is not in the system args then we don't want to load fixtures
            return

        from . import models

        try:
            # call_command('migrate')
            if 'bio_tables_bcupdate' in connection.introspection.table_names():
                # check the bio_chem fixture file. If it's been modified then automatically reload the fixtures.
                fixture_file = os.path.join(settings.BASE_DIR, 'bio_tables/fixtures/biochem_fixtures.json')
                modified = datetime.fromtimestamp(os.path.getmtime(fixture_file))
                modified = pytz.utc.localize(modified)

                if not models.BCUpdate.objects.filter(pk=1).exists():
                    logger.info("Loading biochem fixtures, this may take a moment")
                    call_command('loaddata', 'biochem_fixtures')
                    last_update = models.BCUpdate(last_update=modified)
                    last_update.save()

                elif modified.timestamp() != (last_update := models.BCUpdate.objects.get(pk=1)).last_update.timestamp():
                    logger.info("Loading biochem fixtures, this may take a moment")
                    call_command('loaddata', 'biochem_fixtures')
                    last_update.last_update = modified
                    last_update.save()

        except Exception as ex:
            logger.error('Could not load biochem fixtures')
            logger.exception(ex)
        # if not settings.DEBUG:
        #     call_command('loaddata', 'biochem_fixtures')
