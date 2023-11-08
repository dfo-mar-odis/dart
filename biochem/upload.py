import math
from typing import Type

from datetime import datetime


from django.db import connections, DatabaseError
from django.db.models import QuerySet
from django.utils.translation import gettext as _

import core.models
from biochem import models
from dart2.utils import updated_value
from core import models as core_models

import logging

user_logger = logging.getLogger('dart.user')
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
            return True
        else:
            raise e

    except Exception as e:
        logger.exception(e)

    return False


# Use when testing DB connections when we don't want to edit the model
#
# example usage:
#
# bcd_d = upload.get_bcd_d_model('some_table')
# try:
#     bcd_d.objects.exists()
# except DatabaseError as e:
#     if e.args[0].code == 12545:
#         # 12545 occurs if we couldn't connect to the DB so the connection is bad
#     elif e.args[0].code == 942:
#         # 942 occurs if we can connect, but the table doesn't exist so the connection is good
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


def db_write_by_chunk(model, chunk_size, data, fields=None):
    chunks = math.ceil(len(data) / chunk_size)
    for i in range(0, len(data), chunk_size):
        user_logger.info(_("Writing chunk to database") + " : %d/%d", (int(i / chunk_size) + 1), chunks)
        batch = data[i:i + chunk_size]
        if fields:
            model.objects.bulk_update(batch, fields)
        else:
            model.objects.bulk_create(batch)


def upload_bcs_d(bcs_d_model: Type[models.BcsD], bcs_rows_to_create: [models.BcsD], bcs_rows_to_update: [models.BcsD],
                 updated_fields: [str]):
    chunk_size = 100
    if len(bcs_rows_to_create) > 0:
        user_logger.info(_("Creating BCS rows") + f" : {len(bcs_rows_to_create)}")
        db_write_by_chunk(bcs_d_model, chunk_size, bcs_rows_to_create)

    if len(bcs_rows_to_update) > 0:
        user_logger.info(_("Updating BCS rows") + f": {len(bcs_rows_to_update)}")
        db_write_by_chunk(bcs_d_model, chunk_size, bcs_rows_to_update, updated_fields)


# returns the rows to create, rows to update and fields to update
def get_bcs_d_rows(uploader: str, bcs_d_model: Type[models.BcsD], bottles: list[core_models.Bottle],
                 batch_name: str = None) -> [[models.BcsD], [models.BcsD], [str]]:

    user_logger.info("Creating/updating BCS table")
    bcs_objects_to_create = []
    bcs_objects_to_update = []

    existing_samples = {int(sample.dis_headr_collector_sample_id): sample for sample in
                        bcs_d_model.objects.all()}

    updated_fields = set()
    total_bottles = len(bottles)
    for count, bottle in enumerate(bottles):
        user_logger.info(_("Compiling Bottle") + " : %d/%d", (count + 1), total_bottles)
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

    return [bcs_objects_to_create, bcs_objects_to_update, updated_fields]


def upload_bcd_d(bcd_d_model: Type[models.BcdD], samples: [core_models.DiscreteSampleValue],
                 bcd_rows_to_create: [models.BcdD], bcd_rows_to_update: [models.BcdD], updated_fields: [str]):
    chunk_size = 100

    update_discrete_fields = set()
    update_discrete_fields.add('bio_upload_date')
    if len(bcd_rows_to_create) > 0:
        user_logger.info(f"Createing BCD rows: {len(bcd_rows_to_create)}")

        # writting thousands of rows at one time is... apparently bad. Break the data up into manageable chunks.
        db_write_by_chunk(bcd_d_model, chunk_size, bcd_rows_to_create)

        update_rows: [models.BcdD] = []
        total_samples = len(samples)
        for count, ds_sample in enumerate(samples):
            user_logger.info(_("Updating keys") + " : %d/%d", (count + 1), total_samples)
            data_type_seq = ds_sample.datatype.data_type_seq
            collector_id = f'{ds_sample.sample.bottle.bottle_id}_{ds_sample.replicate}'
            try:
                bc_row = bcd_d_model.objects.get(dis_detail_data_type_seq=data_type_seq,
                                                 dis_detail_collector_samp_id=collector_id)
            except bcd_d_model.DoesNotExist as e:
                logger.exception(e)
                logger.error(f"row matching data_type_seq {data_type_seq} and id {collector_id} does not exist")
                continue

            bc_row.dis_detail_collector_samp_id = ds_sample.sample.bottle.bottle_id

            ds_sample.dis_data_num = bc_row.dis_data_num
            ds_sample.bio_upload_date = datetime.now().strftime("%Y-%m-%d")

            update_rows.append(bc_row)

        update_discrete_fields.add('dis_data_num')
        db_write_by_chunk(bcd_d_model, chunk_size, update_rows, ['dis_detail_collector_samp_id'])

        # if new rows are being created then the dis_data_num in the local database needs to be updated
        # to the same dis_data_num used by the biochem tables
        user_logger.info("Updating discrete sample dis_data_num for biochem link")
        core_models.DiscreteSampleValue.objects.bulk_update(samples, [field for field in update_discrete_fields])

    if len(bcd_rows_to_update) > 0:
        user_logger.info(f"Updating BCD rows: {len(bcd_rows_to_update)}")
        db_write_by_chunk(bcd_d_model, chunk_size, bcd_rows_to_update, updated_fields)

        for ds_sample in samples:
            ds_sample.bio_upload_date = datetime.now().strftime("%Y-%m-%d")


# Todo: Documentation
# get_bcd_d_rows checks the local database against the BCD model and creates a list of BCD rows
# to either be created or updated. It returns [rows_to_create, rows_to_update, fields_names_to_update]
# if errors occur they'll be written to the local database Error table.
#
# When returned, the rows_to_create list will have the dis_detail_collector_samp_id column set as a compound
# key containing the [bottle_id]_[replicate_number] when written to the database this key needs to be
# changed to just the bottle_id.
#
# Due to database limitations the bcd.dis_data_num (auto generated primary key) can't be retrieved until
# the row has been created. So the row will have to be written, the bcd.dis_data_num retrieved and attached
# to the core.models.DiscreteSampleValue and then updated to fix the dis_detail_collector_samp_id key to be
# just the bottle_id
def get_bcd_d_rows(uploader: str, bcd_d_model: Type[models.BcdD], mission: core_models.Mission,
                   samples: QuerySet[core_models.DiscreteSampleValue], batch_name: str = None
                   ) -> [[models.BcdD], [models.BcdD], [str]]:
    bcd_objects_to_create = []
    bcd_objects_to_update = []
    errors = []

    sample_type_ids = [sample_type for sample_type in samples.values_list('sample__type', flat=True).distinct()]
    sample_types = core_models.SampleType.objects.filter(pk__in=sample_type_ids)
    mission_sample_types = mission.mission_sample_types.filter(sample_type_id__in=sample_types)

    sample_type_datatypes = [dt for dt in sample_types.values_list('datatype__data_type_seq', flat=True).distinct()]
    mission_datatypes = [dt for dt in mission_sample_types.values_list('datatype__data_type_seq', flat=True).distinct()]
    discreate_datatypes = [dt for dt in samples.values_list('sample_datatype__data_type_seq', flat=True).distinct()]

    data_types = sample_type_datatypes + mission_datatypes + discreate_datatypes

    existing_samples = {sample.dis_data_num: sample for sample in
                        bcd_d_model.objects.filter(dis_detail_data_type_seq__in=data_types)}
    user_logger.info("Compiling BCD samples")

    updated_fields = set()
    total_samples = len(samples)
    for count, ds_sample in enumerate(samples):
        user_logger.info(_("Compiling sample") + f" : {ds_sample.sample.type.short_name} - " + "%d/%d",
                         (count+1), total_samples)
        sample = ds_sample.sample
        bottle = sample.bottle
        event = bottle.event
        mission = event.mission

        try:
            bc_data_type = ds_sample.datatype
        except ValueError as e:
            msg = e.args[0]['message'] if 'message' in e.args[0] else _("Unknown Error")

            err = core_models.Error(mission=mission, message=msg, type=core_models.ErrorType.biochem)
            errors.append(err)
            continue

        existing_sample = False
        # some of the fields below may be the same as the current value if updating. When that happens
        # a blank string is added tot he updated_fields set. Before adding a record to the 'things that need
        # updating' list we check to see if the updated_fields set is empty by first removing the blank string
        # if the string isn't in the set though an error is thrown, so add the blank string here so it will
        # definitely exist later.
        updated_fields.add('')

        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:02d}_{bottle.bottle_id}'

        # determine if sample is existing or not here
        if ds_sample.dis_data_num and ds_sample.dis_data_num in existing_samples.keys():
            # If the sample does have a dis_data_num, we can get the corresponding row from the BCD table
            bcd_row = existing_samples[ds_sample.dis_data_num]
            existing_sample = True
            # If the modified date on the discrete sample is less than the creation date on the BCD row
            # nothing needs to be uploaded
        else:
            # If the sample doesn't have a dis_data_num, it's never been uploaded so needs to be created.
            collector_id = f'{bottle.bottle_id}_{ds_sample.replicate}'
            bcd_row = bcd_d_model._meta.model(dis_detail_collector_samp_id=collector_id)

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

        batch = batch_name if batch_name else f'{event_date.strftime("%Y")}{mission.pk}'
        updated_fields.add(updated_value(bcd_row, 'batch_seq', batch))
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
        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_value', ds_sample.value))
        updated_fields.add(updated_value(bcd_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
        updated_fields.add(updated_value(bcd_row, 'dis_sample_key_value', dis_sample_key_value))

        updated_fields.remove('')

        if not existing_sample:
            bcd_objects_to_create.append(bcd_row)
        elif len(updated_fields) > 0:
            bcd_objects_to_update.append(bcd_row)

    if len(errors) > 0:
        core_models.Error.objects.bulk_create(errors)

    return [bcd_objects_to_create, bcd_objects_to_update, updated_fields]