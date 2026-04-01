import math

from enum import Enum
from typing import Type
from datetime import datetime

from django.conf import settings
from django.apps import apps
from django.db import connections, DatabaseError, OperationalError
from django.db.models import QuerySet, Min, Max
from django.utils.translation import gettext as _

import bio_tables.models
from biochem import models
from core import models as core_models

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


class BIOCHEM_CODES(Enum):
    MISSING_SOUNDING = 3000


def create_model(database_name: str, model):
    with connections[database_name].schema_editor() as editor:
        editor.create_model(model)


# returns true if the table already exists, false otherwise, or an exception will be thrown if there was
# a connection or some other database issue.
def check_and_create_model(database_name: str, upload_model) -> bool:
    try:
        upload_model.objects.using(database_name).exists()
        return True
    except OperationalError as e:
        # when running unit tests an in-memory database is used and throws a different type of error
        create_model(database_name, upload_model)
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


# create a temporary in-memory database table that can be used to hold remote data for faster access
def get_temp_space(model, tmp_db_name='biochem_tmp') -> Type[models.BcdD | models.BcdP]:
    databases = settings.DATABASES
    if tmp_db_name not in databases:
        databases[tmp_db_name] = databases['default'].copy()
        databases[tmp_db_name]['NAME'] = 'file:memorydb_biochem?mode=memory&cache=shared'

    check_and_create_model(tmp_db_name, model)
    model.objects.using(tmp_db_name).delete()

    return model


# Use when testing DB connections when we don't want to edit the model
#
# example usage:
#
# bcd_d = upload.get_model('some_table', biochem_models.BcdD)
# try:
#     bcd_d.objects.exists()
# except DatabaseError as e:
#     if e.args[0].code == 12545:
#         # 12545 occurs if we couldn't connect to the DB so the connection is bad
#     elif e.args[0].code == 942:
#         # 942 occurs if we can connect, but the table doesn't exist so the connection is good
def get_model(table_name: str, model):

    app_models = apps.get_app_config('biochem').get_models()
    existing_models = {model._meta.label_lower: model for model in app_models}

    model_name = f'biochem.{table_name.lower()}'
    if model_name in existing_models.keys():
        mod = existing_models[model_name]
    else:
        opts = {'__module__': 'biochem'}
        mod = type(table_name, (model,), opts)

    mod._meta.db_table = table_name

    return mod


def db_write_by_chunk(model, chunk_size, data):
    chunks = math.ceil(len(data) / chunk_size)
    for i in range(0, len(data), chunk_size):
        user_logger.info(_("Writing chunk to database") + " : %d/%d", (int(i / chunk_size) + 1), chunks)
        batch = data[i:i + chunk_size]
        model.objects.using('biochem').bulk_create(batch)


def upload_db_rows(model, rows_to_create: list):
    chunk_size = 100
    if len(rows_to_create) > 0:
        db_write_by_chunk(model, chunk_size, rows_to_create)


# returns the rows to create, rows to update and fields to update
def get_bcs_d_rows(uploader: str, bottles: QuerySet[core_models.Bottle], batch: models.Bcbatches = None) -> list[models.BcsD]:
    user_logger.info("Creating/updating BCS table")
    bcs_objects_to_create = []

    DART_EVENT_COMMENT = "Created using the DFO at-sea Reporting Template"

    bottles = bottles.select_related(
        'event__mission__data_center',
        'event__station'
    )

    total_bottles = len(bottles)
    date_now_string = datetime.now().strftime("%Y-%m-%d")

    for count, bottle in enumerate(bottles):
        if count % 10 == 9:
            user_logger.info(_("Compiling Bottle") + " : %d/%d", (count + 1), total_bottles)

        event = bottle.event
        mission = event.mission
        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}'

        try:
            sounding_action = event.sounding_action
            header_sounding = sounding_action.sounding
            header_comment = sounding_action.data_collector
            event_collector_comment = None

        except ValueError as ex:
            logger.exception(ex)
            header_sounding = None
            header_comment = "Unknown"
            event_collector_comment = "No sounding action found for this event"

        m_start_date = mission.start_date
        m_end_date = mission.end_date

        header_slat = bottle.latitude if bottle.latitude else event.start_location[0]
        header_elat = bottle.latitude if bottle.latitude else event.end_location[1]

        header_slon = bottle.longitude if bottle.longitude else event.start_location[0]
        header_elon = bottle.longitude if bottle.longitude else event.end_location[1]

        bcs_row = models.BcsD(
            dis_sample_key_value=dis_sample_key_value,
            dis_headr_collector_sample_id=bottle.bottle_id,
            created_by = uploader,

            mission_descriptor = mission.mission_descriptor,
            mission_name = mission.name,
            mission_leader = mission.lead_scientist,
            mission_sdate = m_start_date,
            mission_edate = m_end_date,
            mission_platform = mission.platform,
            mission_protocol = mission.protocol,
            mission_geographic_region = mission.geographic_region,
            mission_collector_comment1 = mission.collector_comments,
            mission_collector_comment2 = mission.more_comments,
            mission_data_manager_comment = mission.data_manager_comments,
            mission_institute = primary_data_center.name if primary_data_center else "Not Specified",

            event_collector_event_id = f'{event.event_id:03d}',
            event_collector_comment1 = event.comments,
            event_data_manager_comment = DART_EVENT_COMMENT,
            event_collector_stn_name = event.station.name,
            event_sdate = datetime.strftime(event.start_date, "%Y-%m-%d"),
            event_edate = datetime.strftime(event.end_date, "%Y-%m-%d"),
            event_stime = datetime.strftime(event.start_date, "%H%M"),
            event_etime = datetime.strftime(event.end_date, "%H%M"),
            event_utc_offset = 0,
            event_min_lat = min(event.start_location[0], event.end_location[0]),
            event_max_lat = max(event.start_location[0], event.end_location[0]),
            event_min_lon = min(event.start_location[1], event.end_location[1]),
            event_max_lon = max(event.start_location[1], event.end_location[1]),

            dis_headr_gear_seq = 90000019,  # typically 90000019, not always
            dis_headr_time_qc_code = 1,
            dis_headr_position_qc_code = 1,

            dis_headr_sounding = header_sounding,
            dis_headr_collector = header_comment,
            event_collector_comment2 = event_collector_comment,

            dis_headr_responsible_group = mission.protocol,

            dis_headr_sdate = datetime.strftime(bottle.closed, "%Y-%m-%d"),
            dis_headr_edate = datetime.strftime(bottle.closed, "%Y-%m-%d"),
            dis_headr_stime = datetime.strftime(bottle.closed, "%H%M"),
            dis_headr_etime = datetime.strftime(bottle.closed, "%H%M"),

            dis_headr_slat = header_slat,
            dis_headr_elat = header_elat,

            dis_headr_slon = header_slon,
            dis_headr_elon = header_elon,

            dis_headr_start_depth = bottle.pressure,
            dis_headr_end_depth = bottle.pressure,

            # The process flag is used by the Biochem upload app to indicate if the data should be processed by
            # the application. Pl/SQL code is run on the table and this flag is set to 'SVE' depending on
            # if the data validates.
            process_flag = 'NR',
            data_center_code = primary_data_center.data_center_code,
            created_date = date_now_string
        )

        if batch:
            bcs_row.batch = batch
        else:
            bcs_row.batch_id = 0

        bcs_objects_to_create.append(bcs_row)

    return bcs_objects_to_create


def get_bcs_p_rows(uploader: str, bottles: QuerySet[core_models.Bottle], batch: models.Bcbatches = None) -> list[models.BcsP]:

    bcs_objects_to_create = []

    DART_EVENT_COMMENT = "Created using the DFO at-sea Reporting Template"

    # mission_id: int = bottles.values_list('event__mission', flat=True).distinct().first()
    # mission = core_models.Mission.objects.get(pk=mission_id)
    # institute: bio_tables.models.BCDataCenter = mission.data_center

    bottles = bottles.select_related(
        'event__mission__data_center',
        'event__station',
        'event__instrument',
        'gear_type'
    )

    total_bottles = len(bottles)
    date_now_string = datetime.now().strftime("%Y-%m-%d")

    for count, bottle in enumerate(bottles):
        if count % 10 == 9:
            user_logger.info(_("Compiling BCS") + " : %d/%d", (count + 1), total_bottles)
        # plankton samples may share bottle_ids, a BCS entry is per bottle, per gear type
        event = bottle.event
        mission = event.mission
        institute: bio_tables.models.BCDataCenter = mission.data_center

        if event.actions.filter(type=core_models.ActionType.aborted).exists():
            # we don't load aborted events
            continue

        plankton_key = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}_{bottle.gear_type.gear_seq}'

        m_start_date = mission.start_date
        m_end_date = mission.end_date

        bottle_volume = bottle.computed_volume

        header_slat = bottle.latitude if bottle.latitude else event.start_location[0]
        header_slon = bottle.longitude if bottle.longitude else event.start_location[1]

        header_elat = bottle.latitude if bottle.latitude else event.end_location[0]
        header_elon = bottle.longitude if bottle.longitude else event.end_location[1]

        start_pressure = bottle.pressure
        end_pressure = bottle.pressure
        if hasattr(bottle, 'end_pressure') and bottle.end_pressure is not None:
            end_pressure = bottle.end_pressure

        collection_method = 90000010  # hydrographic if this is phytoplankton
        procedure = 90000001
        storage = 90000016
        shared = 'N'
        large_plankton_removed = "N"  # No if phytoplankton

        if event.instrument.type == core_models.InstrumentType.net:
            collection_method = 90000001  # vertical if this is zooplankton
            large_plankton_removed = 'Y'  # Yes if Zooplankton

        try:
            sounding_action = event.sounding_action
            header_sounding = sounding_action.sounding
            header_collector = sounding_action.data_collector
            header_comment = None
        except ValueError as ex:
            logger.exception(ex)
            header_sounding = None
            header_collector = "Unknown"
            header_comment = "No sounding action found for this event"

        bcs_row = models.BcsP(
            plank_sample_key_value=plankton_key,
            created_date = date_now_string,
            created_by = uploader,
            mission_descriptor = mission.mission_descriptor,
            mission_name = mission.name,
            mission_leader = mission.lead_scientist,
            mission_sdate = m_start_date,
            mission_edate = m_end_date,
            mission_institute = institute.name if institute else "Not Specified",
            mission_platform = mission.platform,
            mission_protocol = mission.protocol,
            mission_geographic_region = mission.geographic_region,
            mission_collector_comment = mission.collector_comments,
            mission_more_comment = mission.more_comments,
            mission_data_manager_comment = mission.data_manager_comments,

            event_collector_event_id = f'{event.event_id:03d}',
            event_collector_stn_name = event.station.name,
            event_sdate = datetime.strftime(event.start_date, "%Y-%m-%d"),
            event_edate = datetime.strftime(event.end_date, "%Y-%m-%d"),
            event_stime = datetime.strftime(event.start_date, "%H%M"),
            event_etime = datetime.strftime(event.end_date, "%H%M"),
            event_utc_offset = 0,
            event_min_lat = min(event.start_location[0], event.end_location[0]),
            event_max_lat = max(event.start_location[0], event.end_location[0]),
            event_min_lon = min(event.start_location[1], event.end_location[1]),
            event_max_lon = max(event.start_location[1], event.end_location[1]),

            event_collector_comment = None,
            event_data_manager_comment = DART_EVENT_COMMENT,

            pl_headr_collector_sample_id = bottle.bottle_id,
            pl_headr_gear_seq = bottle.gear_type.gear_seq,

            # This was set to 1 in the existing AZMP Template for phyto
            pl_headr_time_qc_code = 1,

            # This was set to 1 in the existing AZMP Template for phyto
            pl_headr_position_qc_code = 1,
            pl_headr_preservation_seq = 90000039,

            # use the event starts and stops if not provided by the bottle.
            pl_headr_sdate = datetime.strftime(event.start_date, "%Y-%m-%d"),
            pl_headr_edate = datetime.strftime(event.end_date, "%Y-%m-%d"),
            pl_headr_stime = datetime.strftime(event.start_date, "%H%M"),
            pl_headr_etime = datetime.strftime(event.end_date, "%H%M"),

            pl_headr_slat = header_slat,
            pl_headr_elat = header_elat,

            pl_headr_slon = header_slon,
            pl_headr_elon = header_elon,

            pl_headr_start_depth = start_pressure,
            pl_headr_end_depth = end_pressure,

            process_flag = 'NR',
            data_center_code = institute.data_center_code,

            pl_headr_sounding = header_sounding,
            pl_headr_collector = header_collector,
            event_more_comment = header_comment,

            pl_headr_volume_method_seq = bottle_volume[0],
            pl_headr_volume = bottle_volume[1],

            pl_headr_lrg_plankton_removed = large_plankton_removed,
            pl_headr_mesh_size = bottle.mesh_size,
            pl_headr_collection_method_seq = collection_method,
            pl_headr_collector_deplmt_id = None,
            pl_headr_procedure_seq = procedure,
            pl_headr_storage_seq = storage,
            pl_headr_meters_sqd_flag = "Y",
            pl_headr_collector_comment = event.comments,
            pl_headr_data_manager_comment = DART_EVENT_COMMENT,
            pl_headr_responsible_group = mission.protocol,
            pl_headr_shared_data = shared
        )

        if batch:
            bcs_row.batch = batch
        else:
            bcs_row.batch_id = 0

        bcs_objects_to_create.append(bcs_row)

    return bcs_objects_to_create


def get_bcd_d_rows(uploader: str, samples: QuerySet[core_models.DiscreteSampleValue], batch: models.Bcbatches = None) -> list[models.BcdD]:

    bcd_objects_to_create = []
    errors = []

    user_logger.info("Compiling BCD Discrete samples")

    samples = samples.select_related(
        'sample__bottle__event__mission__data_center',
        'sample__bottle__event__station',
        'sample__type__datatype'
    )

    total_samples = len(samples)
    date_now_string = datetime.now().strftime("%Y-%m-%d")
    for count, ds_sample in enumerate(samples):
        # dis_data_num = count + dis_data_num
        if count % 10 == 9:
            user_logger.info(_("Compiling updates for BCD Discrete samples") + " : " + "%d/%d", (count + 1), total_samples)
        sample = ds_sample.sample
        bottle = sample.bottle
        event = bottle.event
        mission = event.mission

        # Use the row level datatype if provided otherwise use the mission level datatype
        bc_data_type = ds_sample.datatype if ds_sample.datatype else sample.type.datatype
        limit = ds_sample.limit if ds_sample.limit else None
        location = event.start_location

        header_date = bottle.closed if bottle.closed else event.start_date

        header_location_lat = bottle.latitude if bottle.latitude else location[0]
        header_location_lon = bottle.longitude if bottle.longitude else location[1]

        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}'

        # If the sample doesn't have a dis_data_num or it doesn't match an existing sample create a new row
        collector_id = f'{bottle.bottle_id}'

        bcd_row = models.BcdD(
            dis_detail_collector_samp_id=collector_id,
            dis_detail_data_type_seq = bc_data_type.data_type_seq,
            dis_header_start_depth = bottle.pressure,
            dis_header_end_depth = bottle.pressure,
            event_collector_event_id = f'{event.event_id:03d}',
            event_collector_stn_name = event.station.name,
            dis_header_slat = header_location_lat,
            dis_header_slon =header_location_lon,
            dis_header_sdate = header_date.strftime("%Y-%m-%d"),
            dis_header_stime = header_date.strftime("%H%M"),
            dis_detail_detail_collector = mission.lead_scientist,
            mission_descriptor = mission.mission_descriptor,
            dis_detail_data_qc_code = ds_sample.flag if ds_sample.flag else 0,
            dis_detail_detection_limit = limit,
            process_flag = 'NR',
            created_by = uploader,
            data_center_code = primary_data_center.data_center_code,
            data_type_method = bc_data_type.method,
            dis_detail_data_value = ds_sample.value,
            created_date = date_now_string,
            dis_sample_key_value = dis_sample_key_value
        )

        if batch:
            bcd_row.batch = batch
        else:
            bcd_row.batch_id = 0
        # bcd_row.batch = batch.pk

        bcd_objects_to_create.append(bcd_row)

    if len(errors) > 0:
        core_models.MissionError.objects.bulk_create(errors)

    compress_keys(bcd_objects_to_create, models.BcdD, 'dis_data_num')

    return bcd_objects_to_create


def get_bcd_p_rows(uploader: str, samples: QuerySet[core_models.PlanktonSample],
                   batch: models.Bcbatches = None) -> list[models.BcdP]:

    bcd_objects_to_create = []

    user_logger.info("Compiling BCD Plankton samples")

    # Prefetch all related objects in a single query to avoid N+1
    samples = samples.select_related(
        'bottle__event__mission__data_center',
        'bottle__event__station',
        'bottle__gear_type',
        'taxa',
        'stage',
        'sex',
    )

    total_samples = len(samples)
    date_now_string = datetime.now().strftime("%Y-%m-%d")

    for count, sample in enumerate(samples):
        if count % 10 == 9:
            user_logger.info(_("Compiling BCD Plankton rows") + " : %d/%d", (count + 1), total_samples)

        bottle = sample.bottle
        event = bottle.event
        mission = event.mission

        plankton_key = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}_{bottle.gear_type.gear_seq}'

        taxonomic_id = sample.taxa.taxonomic_name[0:20]  # The collector taxonomic id field is only 20 characters

        # if the wet weight is less than zero then it's being used as a code to generate a collector comment
        # and should be set to None when uploaded to biochem
        wet_weight = sample.raw_wet_weight if sample.raw_wet_weight and sample.raw_wet_weight > 0 else None

        bcd_row = models.BcdP(plank_sample_key_value=plankton_key,
            pl_gen_national_taxonomic_seq = sample.taxa.pk,
            pl_gen_collector_taxonomic_id = taxonomic_id,
            pl_gen_life_history_seq = sample.stage.pk,
            pl_gen_trophic_seq = 90000000,
            pl_gen_min_sieve = sample.min_sieve,
            pl_gen_max_sieve = sample.max_sieve,
            pl_gen_split_fraction = sample.split_fraction,
            pl_gen_sex_seq = sample.sex.pk,
            pl_gen_counts = sample.count,
            pl_gen_count_pct = sample.percent,
            pl_gen_wet_weight = wet_weight,
            pl_gen_dry_weight = sample.raw_dry_weight,
            pl_gen_bio_volume = sample.volume,
            pl_gen_data_qc_code = sample.flag,
            pl_gen_presence = 'Y',
            pl_gen_collector_comment = sample.collector_comment,
            pl_gen_source = "UNASSIGNED",
            pl_gen_modifier = sample.modifier,
            event_collector_event_id = f'{event.event_id:03d}',
            event_collector_stn_name = event.station.name,
            mission_descriptor = mission.mission_descriptor,
            created_by = uploader,
            data_center_code = mission.data_center.data_center_code,
            created_date = date_now_string,
            process_flag = 'NR'
        )

        if batch:
            bcd_row.batch = batch
        else:
            bcd_row.batch_id = 0

        bcd_objects_to_create.append(bcd_row)

    compress_keys(bcd_objects_to_create, models.BcdP, 'plank_data_num')

    return bcd_objects_to_create


def compress_keys(bcd_objects_to_create, bcd_model, primary_key):
    if len(bcd_objects_to_create) <= 0:
        return

    if len(bcd_objects_to_create) % 200 == 1:
        user_logger.info(_("Indexing Primary Keys") + " :  %d/%d", 0, len(bcd_objects_to_create))

    data_num_seq = []
    if bcd_model:
        # to keep data_num (primary key in the Biochem BCD table) a manageable number get all the
        # currently used dis_data_num/plank_data_num keys in order up to the highest value and create a list of integers
        data_num_query = bcd_model.objects.using('biochem').order_by(primary_key)
        data_num_seq = list(data_num_query.values_list(primary_key, flat=True))

    # find the first and last key in the set and use that to create a range, then subtract keys that are
    # being used from the set. What is left are available keys that can be assigned to new rows being created
    sort_seq = []
    end = 0
    if len(data_num_seq) > 0:
        start, end = data_num_seq[0], data_num_seq[-1]
        sort_seq = sorted(set(range(start, end)).difference(data_num_seq))

    data_num = 0
    total_count = len(bcd_objects_to_create)
    for index, obj in enumerate(bcd_objects_to_create):
        if index % 200 == 1:
            user_logger.info(_("Indexing Primary Keys") + " : %d/%d", (index + 1), total_count)

        if index < len(sort_seq):
            # the index number is a count of which object in the bcd_objects_to_create array we're on.
            # If the index is less than the length of our available keys array, get the next available
            # number in the sequence
            data_num = sort_seq[index]
        else:
            # if we're past the end of the available keys start get the last number in the sequence + 1
            # then just add one to the sequence for every additional object.
            data_num = end + 1 if data_num < end else data_num + 1

        setattr(obj, primary_key, data_num)
