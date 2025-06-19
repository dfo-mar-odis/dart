"""
Utility functions for managing per-database configuration and connections for the dart app.
"""

import uuid
import os
import copy

from django.conf import settings
from django.core.management import call_command
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.models import F

from dart.models import Mission
from user_settings.models import LocalSetting

import logging
logger = logging.getLogger('dart')
user_logger = logging.getLogger('dart.user')


# Python
def get_location():
    location = LocalSetting.objects.filter(connected=True)

    if location.exists():
        # Get the connected directory
        directory = location.first().database_location
    else:
        # Default to './missions' if no connected location exists
        default_location = "./missions"
        location, created = LocalSetting.objects.get_or_create(
            database_location=default_location, defaults={"connected": True}
        )
        directory = location.database_location

    # Ensure the directory exists in the file system
    if directory == "./missions" and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    return directory


def create_database(db_name, db_dir=None):
    """
    Creates a new SQLite database for the dart app, runs migrations, and makes it the active database.

    Args:
        db_name (str): The name of the database (used as the file name).
        db_dir (str, optional): Directory to store the database file. Defaults to BASE_DIR/databases.

    Raises:
        FileExistsError: If the database file already exists.

    Returns:
        django.db.backends.base.base.BaseDatabaseWrapper: The active database connection.
    """
    location = get_location()

    if db_dir is None:
        db_dir = os.path.join(settings.BASE_DIR, location)

    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, f"{db_name}.sqlite3")
    if os.path.isfile(db_path):
        message = f"A Database file with this name already exists at: {db_path}"
        logger.error(message)
        raise FileExistsError(message)

    db_config = copy.deepcopy(settings.DATABASES['default'])
    db_config['NAME'] = db_path

    # use a unique alias to create the database, then make it active once migrations are run
    unique_alias = f"dart_new_{db_name}_{uuid.uuid4().hex}"
    settings.DATABASES[unique_alias] = db_config

    user_logger.info("Running migrations")
    call_command('migrate', 'dart', database=unique_alias)

    # Swap to 'dart_active' for runtime
    active_alias = 'dart_active'
    settings.DATABASES[active_alias] = db_config

    # Optionally, clean up the unique alias
    del settings.DATABASES[unique_alias]

    return connections[active_alias]


def connect_database(db_name, db_dir=None):
    """
    Connects to an existing SQLite database for the dart app and makes it the active database.

    Args:
        db_name (str): The name of the database (file name).
        db_dir (str, optional): Directory where the database file is stored. Defaults to BASE_DIR/databases.

    Raises:
        FileNotFoundError: If the database file does not exist.

    Returns:
        django.db.backends.base.base.BaseDatabaseWrapper: The active database connection.
    """
    location = get_location()

    if db_dir is None:
        db_dir = os.path.join(settings.BASE_DIR, location)

    os.makedirs(db_dir, exist_ok=True)  # Ensure directory exists

    db_path = os.path.join(db_dir, f"{db_name}.sqlite3")

    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database file not found at: {db_path}")

    alias = "dart_active"
    # Check if already connected to this database
    if alias in settings.DATABASES:
        current_name = settings.DATABASES[alias].get('NAME')
        if current_name != db_path:
            # Close the old connection if open
            if alias in connections:
                connections[alias].close()


    db_config = copy.deepcopy(settings.DATABASES['default'])
    db_config['NAME'] = db_path
    settings.DATABASES[alias] = db_config

    return connections[alias]


def load_svg(svg_name: str):
    """
    Load an SVG icon from the static files directory.

    Args:
        svg_name (str): Name of the SVG file (with or without .svg extension).

    Raises:
        FileNotFoundError: If the SVG file cannot be found.

    Returns:
        str: Contents of the SVG file as a string.
    """
    file = os.path.join(settings.STATIC_ROOT, settings.BS_ICONS_CUSTOM_PATH,
                        svg_name + ("" if svg_name.endswith('.svg') else ".svg"))

    if not os.path.isfile(file):
        file = os.path.join(settings.BASE_DIR, settings.STATIC_URL, settings.BS_ICONS_CUSTOM_PATH,
                            svg_name + ("" if svg_name.endswith('.svg') else ".svg"))
        if not os.path.isfile(file):
            raise FileNotFoundError

    with open(file, 'r') as fp:
        svg_icon = fp.read()

    return svg_icon


def get_mission_dictionary(db_dir=None, filter=None):
    """
    List all mission databases in the databases directory, including their migration status and version.

    Returns:
        dict: Mapping of database names to metadata, including mission name, migration status, and version.
    """
    location = get_location()
    db_dir = db_dir if db_dir else os.path.join(settings.BASE_DIR, location)
    if not os.path.exists(db_dir):
        os.mkdir(db_dir)

    databases = [f.replace(".sqlite3", "") for f in os.listdir(db_dir) if
                 os.path.isfile(os.path.join(db_dir, f)) and f.endswith('sqlite3')]
    # repo = Repo(settings.BASE_DIR)

    missions = {}
    for database in databases:
        databases = settings.DATABASES
        databases[database] = databases['default'].copy()
        databases[database]['NAME'] = os.path.join(db_dir, f'{database}.sqlite3')
        try:
            if Mission.objects.using(database).exists():
                if is_database_synchronized(database):
                    mission = Mission.objects.using(database).all()
                    if filter:
                        mission = mission.filter(name__icontains=filter['mission_name']) if 'mission_name' in filter and filter.get('mission_name') else mission
                        mission = mission.filter(end_date__gte=filter['start_date']) if 'start_date' in filter and filter.get('start_date') else mission
                        mission = mission.filter(start_date__lte=filter['end_date']) if 'end_date' in filter and filter.get('end_date') else mission
                    if mission.exists():
                        missions[database] = mission.first()
                elif not filter:
                    version = getattr(Mission.objects.using(database).first(), 'dart_version', None)
                    # short_version = repo.git.rev_parse(version, short=8)
                    short_version = version[:8] if version else 'unknown'
                    missions[database] = {'name': database, 'requires_migration': 'true', 'version': short_version}
        except Exception as ex:
            logger.exception(ex)
            logger.error(_("Could not open database, it appears to be corrupted") + " : " + database)

    for connection in connections.all():
        if connection.alias != 'default':
            connection.close()
            settings.DATABASES.pop(connection.alias)

    return missions

def is_database_synchronized(using='dart_active'):
    """
    Check if the specified database is up to date with all migrations for the dart app.

    Args:
        using (str): Django database alias to check. Defaults to 'dart_active'.

    Returns:
        bool: True if the database is synchronized, False if migrations are pending.
    """
    connection = connections[using]
    connection.prepare_database()
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes('dart')
    return not executor.migration_plan(targets)


def is_active_database(database):
    alias = 'dart_active'
    current_name = settings.DATABASES[alias].get('NAME')
    if not current_name.endswith(f"{database}.sqlite3"):
        return False

    return True