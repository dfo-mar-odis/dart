import os.path

from django.core import management
from django.core.management.commands import dumpdata

from biochem import models as biochem_models
from . import models as bio_models


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


def create_fixture(bio_table_name: str = None, output_dir: str = "bio_tables/fixtures/"):
    # if a bio_table_name is supplied a fixture for that specific file will be created
    # otherwise a fixture for all bio_tables will be created

    bio_table = "bio_tables"
    fixture_output = "biochem_fixtures.json"
    if bio_table_name:
        bio_table += f".{bio_table_name}"
        fixture_output = bio_table_name.lower() + ".json"

    management.call_command(dumpdata.Command(), bio_table, indent=4, output=os.path.join(output_dir, fixture_output))


def sync(bio_table_model, biochem_model, field_map, force_create_fixture) -> bool:
    updated = sync_table(bio_table_model=bio_table_model, biochem_model=biochem_model,
                         field_map=field_map)

    if force_create_fixture:
        create_fixture(bio_table_model.__name__)

    return updated


def sync_data_centers(force_create_fixture=False):
    field_map = ['name', 'location', 'description']

    bio_table_model = bio_models.BCDataCenter
    biochem_model = biochem_models.Bcdatacenters

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_units(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'name', 'description']

    bio_table_model = bio_models.BCUnit
    biochem_model = biochem_models.Bcunits

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_data_retrievals(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'parameter_name',
                 'parameter_description', ('unit_seq_id', 'unit_seq'), 'places_before', 'places_after',
                 'minimum_value', 'maximum_value', 'originally_entered_by']

    bio_table_model = bio_models.BCDataRetrieval
    biochem_model = biochem_models.Bcdataretrievals

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_analysis(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'name', 'description']

    bio_table_model = bio_models.BCAnalysis
    biochem_model = biochem_models.Bcanalyses

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_storage(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'name', 'description']

    bio_table_model = bio_models.BCStorage
    biochem_model = biochem_models.Bcstorages

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_sample_handeling(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'name', 'description']

    bio_table_model = bio_models.BCSampleHandling
    biochem_model = biochem_models.Bcsamplehandlings

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_preservation(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'name', 'description', 'type']

    bio_table_model = bio_models.BCPreservation
    biochem_model = biochem_models.Bcpreservations

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_data_types(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), ('data_retrieval_id', 'data_retrieval_seq'),
                 ('analysis_id', 'analysis_seq'), ('preservation_id', 'preservation_seq'),
                 ('sample_handling_id', 'sample_handling_seq'), ('storage_id', 'storage_seq'),
                 ('unit_id', 'unit_seq'), 'description', 'conversion_equation', 'originally_entered_by', 'method',
                 'priority', 'p_code', 'bodc_code']

    bio_table_model = bio_models.BCDataType
    biochem_model = biochem_models.Bcdatatypes

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_taxon_codes(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'tsn', 'taxonomic_name', 'best_nodc7', 'authority',
                 'collectors_comment', 'data_managers_comment', 'short_name', 'tsn_itis', 'aphiaid']

    bio_table_model = bio_models.BCNatnlTaxonCode
    biochem_model = biochem_models.Bcnatnltaxoncodes

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_gear_codes(force_create_fixture=False):
    field_map = [('data_center_code_id', 'data_center_code'), 'type', 'model', 'gear_size', 'description']

    bio_table_model = bio_models.BCGear
    biochem_model = biochem_models.Bcgears

    return sync(bio_table_model, biochem_model, field_map, force_create_fixture)


def sync_all(force_create_fixture=False):
    updated = force_create_fixture
    fixture_methods = [sync_data_centers(), sync_units(), sync_data_retrievals(), sync_analysis(), sync_storage(),
                       sync_sample_handeling(), sync_preservation(), sync_data_types(), sync_taxon_codes(),
                       sync_gear_codes()]

    for method in fixture_methods:
        updated = updated or method

    if updated:
        print("Exporting new fixture file")
        create_fixture()
