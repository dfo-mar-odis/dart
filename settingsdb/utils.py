import os
from datetime import datetime
import pytz

from django.conf import settings
from django.core.management import call_command
from django.db import connections

from settingsdb import models
from bio_tables import models as biomodels
from dart2 import settings

import logging

logger = logging.getLogger('dart')


def load_biochem_fixtures(database):
    try:
        # call_command('migrate')
        if 'bio_tables_bcupdate' in connections[database].introspection.table_names():
            # check the bio_chem fixture file. If it's been modified then automatically reload the fixtures.
            fixture_file = os.path.join(settings.BASE_DIR, 'bio_tables/fixtures/biochem_fixtures.json')
            modified = datetime.fromtimestamp(os.path.getmtime(fixture_file))
            modified = pytz.utc.localize(modified)

            if not biomodels.BCUpdate.objects.using(database).filter(pk=1).exists():
                logger.info("Loading biochem fixtures, this may take a moment")
                call_command('loaddata', 'biochem_fixtures', database=database)
                last_update = biomodels.BCUpdate(last_update=modified)
                last_update.save(using=database)

            elif modified.timestamp() != biomodels.BCUpdate.objects.using(database).get(pk=1).last_update.timestamp():
                last_update = biomodels.BCUpdate.objects.using(database).get(pk=1)
                logger.info("Loading biochem fixtures, this may take a moment")
                call_command('loaddata', 'biochem_fixtures', database=database)
                last_update.last_update = modified
                last_update.save(using=database)

    except Exception as ex:
        logger.error('Could not load biochem fixtures')
        logger.exception(ex)


def add_database(database):

    location = models.LocalSetting.objects.first().database_location

    if not os.path.exists(location):
        os.makedirs(location)

    databases = settings.DATABASES
    databases[database] = databases['default'].copy()
    databases[database]['NAME'] = os.path.join(location, f'{database}.sqlite3')

    call_command('migrate', database=database, app_label="core")
    load_biochem_fixtures(database)


def connect_database(database):
    if database not in settings.DATABASES:
        location = models.LocalSetting.objects.using('default').get(connected=True)
        databases = settings.DATABASES
        databases[database] = databases['default'].copy()
        databases[database]['NAME'] = os.path.join(location.database_location, f'{database}.sqlite3')
