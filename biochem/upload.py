from typing import Type

from django.db import connections, DatabaseError

from datetime import datetime
from biochem import models
from dart2.utils import updated_value
from core import models as core_models

import logging

logger = logging.getLogger('dart')


def create_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.create_model(model)


def delete_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.delete_model(model)


def check_and_create_model(database_name: str, upload_model):
    try:
        upload_model.objects.exists()
    except DatabaseError as e:
        # A 942 Oracle error means a table doesn't exist, in this case create the model. Otherwise pass the error along
        if e.args[0].code == 942:
            create_model(database_name, upload_model)
        else:
            raise e

    except Exception as e:
        logger.exception(e)

    return upload_model


# Use when testing DB connections when we don't want to edit the model
#
# example usage:
#
# with in_database(biochem_db):
#     bcd_d = upload.get_bcd_d_model('some_table')
#     try:
#         bcd_d.objects.exists()
#     except DatabaseError as e:
#         # 12545 occurs if we couldn't connect to the DB
#         # 942 occurs if we can connect, but the table doesn't exist
#         if e.args[0].code == 12545:
#             # likely couldn't connect to the database because the DB details were incorrect
#         elif e.args[0].code == 942:
#             # we could connect, but the table hasn't been created yet
def get_bcd_d_model(table_name: str) -> Type[models.BcdD]:
    bcd_table = table_name + '_bcd_d'
    opts = {'__module__': 'biochem'}
    mod = type(bcd_table, (models.BcdD,), opts)
    mod._meta.db_table = bcd_table

    return mod


# Use when we know the connection is working and want to get or create the model for editing
def get_or_create_bcd_d_model(db_name: str, table_name: str) -> Type[models.BcdD]:
    mod = get_bcd_d_model(table_name=table_name)
    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcs_d_model(table_name: str) -> Type[models.BcsD]:
    bcs_table = table_name + '_bcs_d'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsD,), opts)
    mod._meta.db_table = bcs_table

    return mod


def get_or_create_bcs_d_model(db_name: str, table_name: str) -> Type[models.BcsD]:
    mod = get_bcs_d_model(table_name=table_name)
    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcd_p_model(table_name: str) -> Type[models.BcdP]:
    bcd_table = table_name + '_bcd_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcd_table, (models.BcdP,), opts)
    mod._meta.db_table = bcd_table

    return mod


def get_or_create_bcd_p_model(db_name: str, table_name: str) -> Type[models.BcdP]:
    mod = get_bcd_p_model(table_name=table_name)
    return check_and_create_model(database_name=db_name, upload_model=mod)


def get_bcs_p_model(table_name: str) -> Type[models.BcsP]:
    bcs_table = table_name + '_bcs_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsP,), opts)
    mod._meta.db_table = bcs_table

    return mod


def get_or_create_bcs_p_model(db_name: str, table_name: str) -> Type[models.BcsP]:
    mod = get_bcs_p_model(table_name=table_name)
    return check_and_create_model(database_name=db_name, upload_model=mod)


# This actually just uploads bottle data for the mission. It doesn't upload sample values.
def upload_bcs_d(uploader: str, mission: core_models.Mission, batch_name: str = None):
    bcs_objects_to_create = []
    bcs_objects_to_update = []

    updated_fields = set()
    updated_fields.add('')

    # TODO: This could throw an error and should be caught and reported to the users web browser somehow.
    #  It doesn't fit the standard model for using a core_models.Error though and would be difficult to
    #  remove in the event there was a network error. Think on it a bit.
    upload_model = get_or_create_bcs_d_model('biochem', mission.get_biochem_table_name)

    primary_data_center = mission.data_center

    existing_samples = {int(sample.dis_headr_collector_sample_id): sample for sample in
                        upload_model.objects.all()}

    bottles = core_models.Bottle.objects.filter(event__mission=mission)

    for bottle in bottles:
        event = bottle.event

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:02d}_{bottle.bottle_id}'

        existing_sample = bottle.bottle_id in existing_samples.keys()
        if existing_sample:
            bcs_row = existing_samples[bottle.bottle_id]
        else:
            bcs_row = upload_model._meta.model(dis_headr_collector_sample_id=bottle.bottle_id)

        m_start_date = mission.events.first().start_date
        m_end_date = mission.events.last().end_date
        updated_fields.add(updated_value(bcs_row, 'dis_sample_key_value', dis_sample_key_value))
        updated_fields.add(updated_value(bcs_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'created_by', uploader))

        updated_fields.add(updated_value(bcs_row, 'mission_descriptor', mission.mission_descriptor))
        updated_fields.add(updated_value(bcs_row, 'mission_name', mission.name))
        updated_fields.add(updated_value(bcs_row, 'mission_leader', mission.lead_scientist))
        updated_fields.add(updated_value(bcs_row, 'mission_sdate', m_start_date))
        updated_fields.add(updated_value(bcs_row, 'mission_edate', m_end_date))
        updated_fields.add(updated_value(bcs_row, 'mission_platform', mission.platform))
        updated_fields.add(updated_value(bcs_row, 'mission_protocol', mission.protocol))
        updated_fields.add(updated_value(bcs_row, 'mission_geographic_region', mission.geographic_region.name
                                         if mission.geographic_region else ""))
        updated_fields.add(updated_value(bcs_row, 'mission_collector_comment1', mission.collector_comments))
        updated_fields.add(updated_value(bcs_row, 'mission_collector_comment2', mission.more_comments))
        updated_fields.add(updated_value(bcs_row, 'mission_data_manager_comment', mission.data_manager_comments))

        updated_fields.add(updated_value(bcs_row, 'event_collector_event_id', event.event_id))
        updated_fields.add(updated_value(bcs_row, 'event_collector_stn_name', event.station.name))
        updated_fields.add(updated_value(bcs_row, 'event_sdate', datetime.strftime(event.start_date, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'event_edate', datetime.strftime(event.end_date, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'event_stime', datetime.strftime(event.start_date, "%H%M%S")))
        updated_fields.add(updated_value(bcs_row, 'event_etime', datetime.strftime(event.end_date, "%H%M%S")))
        updated_fields.add(updated_value(bcs_row, 'event_utc_offset', 0))
        updated_fields.add(updated_value(bcs_row, 'event_min_lat', min(event.start_location[0], event.end_location[0])))
        updated_fields.add(updated_value(bcs_row, 'event_max_lat', max(event.start_location[0], event.end_location[0])))
        updated_fields.add(updated_value(bcs_row, 'event_min_lon', min(event.start_location[1], event.end_location[1])))
        updated_fields.add(updated_value(bcs_row, 'event_max_lon', max(event.start_location[1], event.end_location[1])))

        updated_fields.add(updated_value(bcs_row, 'dis_headr_gear_seq', 90000019))  # typically 90000019, not always
        updated_fields.add(updated_value(bcs_row, 'dis_headr_time_qc_code', 0))

        updated_fields.add(updated_value(bcs_row, 'dis_headr_sdate', datetime.strftime(bottle.date_time, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_edate', datetime.strftime(bottle.date_time, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_stime', datetime.strftime(bottle.date_time, "%H%M%S")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_etime', datetime.strftime(bottle.date_time, "%H%M%S")))

        if bottle.latitude:
            updated_fields.add(updated_value(bcs_row, 'dis_headr_slat', bottle.latitude))  # Maybe required to use
            updated_fields.add(updated_value(bcs_row, 'dis_headr_elat', bottle.latitude))  # Event lat/lon

        if bottle.longitude:
            updated_fields.add(updated_value(bcs_row, 'dis_headr_slon', bottle.longitude))  # Maybe required to use
            updated_fields.add(updated_value(bcs_row, 'dis_headr_elon', bottle.longitude))  # Event lat/lon

        updated_fields.add(updated_value(bcs_row, 'dis_headr_start_depth', bottle.pressure))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_end_depth', bottle.pressure))

        updated_fields.add(updated_value(bcs_row, 'process_flag', 'NR'))
        updated_fields.add(updated_value(bcs_row, 'data_center_code', primary_data_center.data_center_code))

        if not batch_name:
            batch_name = f'{event.start_date.strftime("%Y")}{mission.pk}'
        updated_fields.add(updated_value(bcs_row, 'batch_seq', batch_name))

        if not existing_sample:
            bcs_objects_to_create.append(bcs_row)
        elif len(updated_fields) > 0:
            bcs_objects_to_update.append(bcs_row)

    if len(bcs_objects_to_create) > 0:
        print(f"Createing BCS rows: {len(bcs_objects_to_create)}")
        upload_model.objects.bulk_create(bcs_objects_to_create)

    updated_fields.remove('')
    if len(updated_fields) > 0:
        print(f"Updating BCS rows: {len(bcs_objects_to_update)}")
        upload_model.objects.bulk_update(bcs_objects_to_update, updated_fields)

