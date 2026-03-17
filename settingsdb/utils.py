import os
from datetime import datetime
import pytz

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.core.management import call_command
from django.db.migrations.executor import MigrationExecutor

import settingsdb.models

from settingsdb import models
from bio_tables import models as biomodels
from config import settings

from core import models as core_models
from git import Repo

import logging

logger = logging.getLogger('dart')


def load_biochem_fixtures(database):
    try:
        # call_command('migrate')
        if 'bio_tables_bcupdate' in connections[database].introspection.table_names():
            # check the bio_chem fixture file. If it's been modified then automatically reload the fixtures.
            fixture_file = os.path.join(settings.BASE_DIR, 'bio_tables/fixtures/biochem_fixtures.json')
            load_bio_fixtures = 'biochem_fixtures'
            if not os.path.exists(fixture_file):
                fixture_file = os.path.join(settings.BASE_DIR, 'bio_tables/fixtures/default_biochem_fixtures.json')
                load_bio_fixtures = 'default_biochem_fixtures'

            modified = datetime.fromtimestamp(os.path.getmtime(fixture_file))
            modified = pytz.utc.localize(modified)

            if not biomodels.BCUpdate.objects.using(database).filter(pk=1).exists():
                logger.info("Loading biochem fixtures, this may take a moment")
                call_command('loaddata', load_bio_fixtures, database=database)
                last_update = biomodels.BCUpdate(last_update=modified)
                last_update.save(using=database)

            elif modified.timestamp() != biomodels.BCUpdate.objects.using(database).get(pk=1).last_update.timestamp():
                last_update = biomodels.BCUpdate.objects.using(database).get(pk=1)
                logger.info("Loading biochem fixtures, this may take a moment")
                call_command('loaddata', fixture_file, database=database)
                last_update.last_update = modified
                last_update.save(using=database)

    except Exception as ex:
        logger.error('Could not load biochem fixtures')
        logger.exception(ex)


def get_db_location(database):
    locations = models.LocalSetting.objects.filter(connected=True)
    if locations.exists():
        location = locations.first()
    else:
        # pk = 1 should always be the default "./missions/" directory
        location = models.LocalSetting.objects.get(pk=1)

    if not os.path.exists(location.database_location):
        os.makedirs(location.database_location)

    return os.path.join(location.database_location, f'{database}.sqlite3')


def add_database(database):

    databases = settings.DATABASES
    mission_database = 'mission_db'
    databases[mission_database] = databases['default'].copy()
    databases[mission_database]['NAME'] = get_db_location(database)

    call_command('migrate', database=mission_database, app_label="core")
    call_command('migrate', database=mission_database, app_label="bio_tables")
    load_biochem_fixtures(mission_database)


def connect_database(database):
    # if database not in settings.DATABASES:
    if database == 'default':
        return

    databases = settings.DATABASES
    mission_database = 'mission_db'
    if mission_database in databases:
        if databases[mission_database].get('LOADED', None) != database:
            close_connection()
        else:
            return

    try:
        location = models.LocalSetting.objects.get(connected=True)
    except settingsdb.models.LocalSetting.DoesNotExist as ex:
        location = models.LocalSetting.objects.order_by('id').first()
        location.connected = True
        location.save()

    # Someone once recommended that Dart databases start with the DART_ prefix to make it clear they are Dart database.
    # This however maks it a pain to work with on the command line. So now we will check for the database with and
    # without the DART_ prefix and use whichever one we find, priority given to whatever name the user provided if
    # it exists.
    db_path = os.path.join(location.database_location, f'{database}.sqlite3')
    if not os.path.exists(db_path) and not database.upper().startswith('DART_'):
        database = f'DART_{database.upper()}'
        db_path_prefix = os.path.join(location.database_location, f'{database}.sqlite3')
        if os.path.exists(db_path_prefix):
            db_path = db_path_prefix

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found at {db_path}")

    logger.info(f"Connecting to database {database}")
    databases[mission_database] = databases['default'].copy()
    databases[mission_database]['NAME'] = db_path
    databases[mission_database]["LOADED"] = database


def is_database_synchronized(database):
    connection = connections[database]
    connection.prepare_database()
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes('core')
    return not executor.migration_plan(targets)


def migrate(database):
    connect_database(database)
    if not is_database_synchronized('mission_db'):
        call_command('migrate', 'core', database='mission_db')
        mission = core_models.Mission.objects.first()
        mission.dart_version = get_dart_git_version()
        mission.save()


def get_dart_git_version():
    repo = Repo(settings.BASE_DIR)
    return  repo.head.commit.hexsha


def close_connection(mission_database='mission_db'):
    databases = settings.DATABASES
    if mission_database in connections:
        logger.info(f"closing {mission_database} connection")
        del connections[mission_database]
        connections.close_all()


def close_connections():
    """
    Close all open database connections in Django.
    """
    for conn in connections.all():
        conn.close()


def test_migration():

    databases = ['CAR2023573', 'CAR2023573-2', 'CAR2023573-3', 'TEL2024880']
    for db in databases:
        connect_database(db)
        try:
            call_command('migrate', 'core', '0002', database=db)
        except Exception as ex:
            print(ex)
