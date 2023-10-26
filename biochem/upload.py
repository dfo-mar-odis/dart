from typing import Type

from django.db import connections, DatabaseError

from datetime import datetime

from django.db.models import Avg, QuerySet
from django.db.models.base import ModelBase

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


# returns true if the table already exists, false otherwise, or an exception will be thrown if there was
# a connection or some other database issue.
def check_and_create_model(database_name: str, upload_model) -> bool:
    try:
        upload_model.objects.exists()
        return True
    except DatabaseError as e:
        # A 942 Oracle error means a table doesn't exist, in this case create the model. Otherwise pass the error along
        if e.args[0].code == 942:
            create_model(database_name, upload_model)
        else:
            raise e

    except Exception as e:
        logger.exception(e)

    return False


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


def get_bcs_d_model(table_name: str) -> Type[models.BcsD]:
    bcs_table = table_name + '_bcs_d'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsD,), opts)
    mod._meta.db_table = bcs_table

    return mod


def get_bcd_p_model(table_name: str) -> Type[models.BcdP]:
    bcd_table = table_name + '_bcd_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcd_table, (models.BcdP,), opts)
    mod._meta.db_table = bcd_table

    return mod


def get_bcs_p_model(table_name: str) -> Type[models.BcsP]:
    bcs_table = table_name + '_bcs_p'
    opts = {'__module__': 'biochem'}
    mod = type(bcs_table, (models.BcsP,), opts)
    mod._meta.db_table = bcs_table

    return mod


# This actually just uploads bottle data for the mission. It doesn't upload sample values.
def upload_bcs_d(uploader: str, bcs_d_model: Type[models.BcsD], bottles: list[core_models.Bottle],
                 batch_name: str = None):
    WRITE_LIMIT = 100

    logger.info("Creating/updating BCS table")
    bcs_objects_to_create = []
    bcs_objects_to_update = []

    existing_samples = {int(sample.dis_headr_collector_sample_id): sample for sample in
                        bcs_d_model.objects.all()}

    updated_fields = set()
    for bottle in bottles:
        # some of the fields below may be the same as the current value if updating. When that happens
        # a blank string is added tot he updated_fields set. Before adding a record to the 'things that need
        # updating' list we check to see if the updated_fields set is empty by first removing the blank string
        # if the string isn't in the set though an error is thrown, so add the blank string here so it will
        # definitely exist later.
        updated_fields.add('')

        event = bottle.event
        mission = event.mission
        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:02d}_{bottle.bottle_id}'

        existing_sample = bottle.bottle_id in existing_samples.keys()
        if existing_sample:
            bcs_row = existing_samples[bottle.bottle_id]
        else:
            bcs_row = bcs_d_model._meta.model(dis_headr_collector_sample_id=bottle.bottle_id)

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

        # remove the blank string from the updated_fields set, if there are still values in the set after that
        # then this record needs to be updated.
        updated_fields.remove('')

        if not existing_sample:
            bcs_objects_to_create.append(bcs_row)
        elif len(updated_fields) > 0:
            bcs_objects_to_update.append(bcs_row)

        # if len(bcs_objects_to_create) >= WRITE_LIMIT:
        #     print(f"Createing BCS rows: {len(bcs_objects_to_create)}")
        #     upload_model.objects.bulk_create(bcs_objects_to_create)
        #     bcs_objects_to_create.clear()
        #
        # if len(bcs_objects_to_update) >= WRITE_LIMIT:
        #     print(f"Updating BCS rows: {len(bcs_objects_to_update)}")
        #     upload_model.objects.bulk_update(bcs_objects_to_update, updated_fields)
        #     bcs_objects_to_update.clear()
        #     updated_fields.clear()
        #     updated_fields.add('')

    if len(bcs_objects_to_create) > 0:
        logger.info(f"Createing BCS rows: {len(bcs_objects_to_create)}")
        bcs_d_model.objects.bulk_create(bcs_objects_to_create)

    if len(bcs_objects_to_update) > 0:
        logger.info(f"Updating BCS rows: {len(bcs_objects_to_update)}")
        bcs_d_model.objects.bulk_update(bcs_objects_to_update, updated_fields)


def upload_bcd_d(uploader: str, bcd_d_model: Type[models.BcdD], samples: QuerySet[core_models.DiscreteSampleValue],
                 batch_name: str = None):
    bcd_objects_to_create = []
    bcd_objects_to_update = []

    logger.info("Collecting existing Biochem samples")

    mission = samples.first().sample.bottle.event.mission

    # Biochem datatypes can exist in three capacities. The datatype can be set by the general Sample Type,
    # the general sample types' datatype could be overridden by the mission, and finally
    # the sample type could be specific to a discrete value.
    # As a result we have to collect all the possible datatypes and see if there are rows in the
    # BCD table to figure out if samples already exist and need to be overridden.
    datatype_set = set()
    ds_datatypes = samples.values_list('sample_datatype', flat=True).distinct()
    for dt in ds_datatypes:
        datatype_set.add(dt)

    sample_datatypes = core_models.SampleType.objects.filter(samples__discrete_values__in=samples).distinct()
    for dt in sample_datatypes:
        datatype_set.add(dt.datatype.data_type_seq)

    mission_sampletypes = mission.mission_sample_types.filter(sample_type__in=sample_datatypes)
    for dt in mission_sampletypes:
        datatype_set.add(dt.datatype.data_type_seq)

    bc_samples = bcd_d_model.objects.filter(dis_detail_data_type_seq__in=datatype_set)
    bc_sample_ids = [int(id) for id in bc_samples.values_list('dis_detail_collector_samp_id', flat=True).distinct()]
    existing_samples = {}
    for sample_id in bc_sample_ids:
        existing_samples[int(sample_id)] = bc_samples.filter(dis_detail_collector_samp_id=sample_id)

    updated_fields = set()
    last_id = None
    replicate_id = 0
    for discrete_sample in samples:
        # some of the fields below may be the same as the current value if updating. When that happens
        # a blank string is added tot he updated_fields set. Before adding a record to the 'things that need
        # updating' list we check to see if the updated_fields set is empty by first removing the blank string
        # if the string isn't in the set though an error is thrown, so add the blank string here so it will
        # definitely exist later.
        updated_fields.add('')

        sample = discrete_sample.sample
        bottle = sample.bottle
        event = bottle.event
        mission = event.mission
        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:02d}_{bottle.bottle_id}'
        # datatype priority is a row specific datatype,
        # then if there's a mission specific datatype,
        # then the general sample type datatype
        bc_data_type = sample.type.datatype
        if (mission_data_type := mission.mission_sample_types.filter(sample_type=sample.type)).exists():
            bc_data_type = mission_data_type.first().datatype

        if (row_data_type := sample.discrete_values.first().datatype):
            bc_data_type = row_data_type

        existing_sample = bottle.bottle_id in bc_sample_ids
        if existing_sample:
            if bottle.bottle_id != last_id:
                replicate_id = 0

            bcd_row = existing_samples[bottle.bottle_id][replicate_id]
            replicate_id += 1
        else:
            bcd_row = bcd_d_model._meta.model(dis_detail_collector_samp_id=bottle.bottle_id)
            replicate_id = 0

        last_id = bottle.bottle_id
        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_type_seq', bc_data_type.data_type_seq))

        # ########### Stuff that we get from the bottle object ################################################### #
        updated_fields.add(updated_value(bcd_row, 'dis_header_start_depth', bottle.pressure))
        updated_fields.add(updated_value(bcd_row, 'dis_header_end_depth', bottle.pressure))

        # ########### Stuff that we get from the event object #################################################### #
        event = bottle.event

        updated_fields.add(updated_value(bcd_row, 'event_collector_event_id', event.event_id))
        updated_fields.add(updated_value(bcd_row, 'event_collector_stn_name', event.station.name))

        location = event.start_location
        updated_fields.add(updated_value(bcd_row, 'dis_header_slat', location[0]))
        updated_fields.add(updated_value(bcd_row, 'dis_header_slon', location[1]))

        event_date = event.start_date
        updated_fields.add(updated_value(bcd_row, 'dis_header_sdate', event_date.strftime("%Y-%m-%d")))
        updated_fields.add(updated_value(bcd_row, 'dis_header_stime', event_date.strftime("%H%M")))

        # ########### Stuff that we get from the Mission object #################################################### #
        mission = event.mission

        updated_fields.add(updated_value(bcd_row, 'batch_seq', f'{event_date.strftime("%Y")}{mission.pk}'))
        updated_fields.add(updated_value(bcd_row, 'dis_detail_detail_collector', mission.lead_scientist))

        # mission descriptor
        # 18 + [ship initials i.e 'JC' for fixstation is 'VA'] + 2-digit year + 3-digit cruise number or station code
        # 18VA13666 <- HL_02, 2013, fixstation
        # 18HU21185 <- Hudson, AZMP, 2021
        #
        # According to Robert Benjamin, this identifier is provided by MEDS and will have to be part of the
        # core.models.Mission object as it gets entered later on.
        updated_fields.add(updated_value(bcd_row, 'mission_descriptor', mission.mission_descriptor))

        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_qc_code', 0))
        updated_fields.add(updated_value(bcd_row, 'process_flag', 'NR'))
        updated_fields.add(updated_value(bcd_row, 'created_by', uploader))
        updated_fields.add(updated_value(bcd_row, 'data_center_code', primary_data_center.data_center_code))

        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_type_seq', bc_data_type.data_type_seq))
        updated_fields.add(updated_value(bcd_row, 'data_type_method', bc_data_type.method))
        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_value', discrete_sample.value))
        updated_fields.add(updated_value(bcd_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
        updated_fields.add(updated_value(bcd_row, 'dis_sample_key_value', dis_sample_key_value))

        updated_fields.remove('')

        if not existing_sample:
            bcd_objects_to_create.append(bcd_row)
        elif len(updated_fields) > 0:
            bcd_objects_to_update.append(bcd_row)

    if len(bcd_objects_to_create) > 0:
        logger.info(f"Createing BCD rows: {len(bcd_objects_to_create)}")
        bcd_d_model.objects.bulk_create(bcd_objects_to_create)

    if len(bcd_objects_to_update) > 0:
        logger.info(f"Updating BCD rows: {len(bcd_objects_to_update)}")
        bcd_d_model.objects.bulk_update(bcd_objects_to_update, updated_fields)
