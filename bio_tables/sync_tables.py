import os.path
import re

from django.conf import settings
from django.core import management
from django.core.management.commands import dumpdata, inspectdb
from django.db.models.fields.related import ForeignKey

import dart.db_routers
from biochem import models as biochem_models
from . import models as bio_models

# The label used in settings.DATABASES must match the label the dart.db_router uses
database_label = 'biochem'


def connect(user: str, password: str, name: str, host: str, port: int, engine: str = 'django.db.backends.oracle'):
    biochem_db = {
        'ENGINE': engine,
        'NAME': name,
        'USER': user,
        'PASSWORD': password,
        'PORT': port,
        'HOST': host,
        'TIME_ZONE': None,
        'CONN_HEALTH_CHECKS': False,
        'CONN_MAX_AGE': 0,
        'AUTOCOMMIT': True,
        'ATOMIC_REQUESTS': False,
        'OPTIONS': {}
    }

    settings.DATABASES[database_label] = biochem_db


# tables should be a comma separated list of table names
def inspect_db(tables: [str]):
    if database_label not in settings.DATABASES:
        raise KeyError("Missing database connection details, run sync_tables.connect() with database details")

    for table in tables:
        management.call_command(inspectdb.Command(), table, database=database_label)


def sync_table(bio_table_model, biochem_model, field_map):
    print(f"Syncing {bio_table_model.__name__.lower()}")
    biochem_data = biochem_model.objects.all()

    updated = False
    new_data = []
    update_data = []
    updated_fields = set()

    for data in biochem_data:
        if not bio_table_model.objects.filter(pk=data.pk).exists():
            bc = bio_table_model(pk=data.pk)
            for field in field_map:
                bc_field_name = field if type(field) is str else field[1]
                bt_field_name = field if type(field) is str else field[0]
                biochem_val = getattr(data, bc_field_name)
                setattr(bc, bt_field_name, biochem_val)
            new_data.append(bc)
        else:
            bc = bio_table_model.objects.get(pk=data.pk)
            row_updated = False
            for field in field_map:
                bc_field_name = field if type(field) is str else field[1]
                bt_field_name = field if type(field) is str else field[0]
                current = getattr(bc, bt_field_name)
                new = getattr(data, bc_field_name)
                if current != new:
                    setattr(bc, bt_field_name, new)
                    updated_fields.add(bt_field_name)
                    row_updated = True

            if row_updated:
                update_data.append(bc)

    if len(new_data) > 0:
        print(f"Adding {len(new_data)} new {bio_table_model.__name__} codes")
        bio_table_model.objects.bulk_create(new_data)
        updated = True

    if len(update_data) > 0:
        print(f"Updating {len(update_data)} {bio_table_model.__name__} codes")
        bio_table_model.objects.bulk_update(update_data, list(updated_fields))
        updated = True

    return updated


def get_mapped_fields(dart_table_model, bio_chem_model) -> list:
    # Get the list of fields specified by the models doc string
    dart_table_fields: list = [field.__dict__['name'] for field in dart_table_model._meta.get_fields()
                               if 'name' in field.__dict__]

    bio_chem_fields: list = [field.__dict__['name'] for field in bio_chem_model._meta.get_fields()
                             if 'name' in field.__dict__]

    # remove the primary key from the fields
    dart_table_fields.remove(dart_table_model._meta.pk.name)

    # change foreign key fields to use ('xxx_id', 'xxx')
    mapped_fields = []
    for field in dart_table_fields:
        if type(dart_table_model._meta.get_field(field)) is ForeignKey:
            # check to see if the field is in the bio_chem_model. if not it probably has '_seq' on the end of it
            if field in bio_chem_fields:
                mapped_fields.append((f'{field}_id', field))
            elif f'{field}_seq' in bio_chem_fields:
                mapped_fields.append((f'{field}_id', f'{field}_seq'))
            else:
                raise ValueError(f"Could not map field {field} for {dart_table_model.__name__}")

        else:
            mapped_fields.append(field)

    return mapped_fields


def create_fixture(bio_table_name: str = None, output_dir: str = "bio_tables/fixtures/"):
    # if a bio_table_name is supplied a fixture for that specific file will be created
    # otherwise a fixture for all bio_tables will be created

    bio_table = "bio_tables"
    fixture_output = "biochem_fixtures.json"
    if bio_table_name:
        bio_table += f".{bio_table_name}"
        fixture_output = bio_table_name.lower() + ".json"

    management.call_command(dumpdata.Command(), bio_table, indent=4, output=os.path.join(output_dir, fixture_output))


def sync(bio_table_model, biochem_model, force_create_fixture=False, field_map=None) -> bool:
    if not field_map:
        field_map = get_mapped_fields(bio_table_model, biochem_model)

    updated = sync_table(bio_table_model=bio_table_model, biochem_model=biochem_model,
                         field_map=field_map)

    if force_create_fixture:
        create_fixture(bio_table_model.__name__)

    return updated


def sync_all(force_create_fixture=False):
    sync_list = [
        (bio_models.BCDataCenter, biochem_models.Bcdatacenters),
        (bio_models.BCUnit, biochem_models.Bcunits),
        (bio_models.BCDataRetrieval, biochem_models.Bcdataretrievals),
        (bio_models.BCAnalysis, biochem_models.Bcanalyses),
        (bio_models.BCStorage, biochem_models.Bcstorages),
        (bio_models.BCSampleHandling, biochem_models.Bcsamplehandlings),
        (bio_models.BCPreservation, biochem_models.Bcpreservations),
        (bio_models.BCDataType, biochem_models.Bcdatatypes),
        (bio_models.BCNatnlTaxonCode, biochem_models.Bcnatnltaxoncodes),
        (bio_models.BCGear, biochem_models.Bcgears),
        (bio_models.BCSex, biochem_models.Bcsexes),
        (bio_models.BCLifeHistory, biochem_models.Bclifehistories),
        (bio_models.BCCollectionMethod, biochem_models.Bccollectionmethods),
        (bio_models.BCProcedure, biochem_models.Bcprocedures),
        (bio_models.BCVolumeMethod, biochem_models.Bcvolumemethods),
    ]

    updated = False

    for sync_model in sync_list:
        if sync(sync_model[0], sync_model[1], force_create_fixture):
            updated = True

    if updated:
        print("Exporting new fixture file")
        create_fixture()
