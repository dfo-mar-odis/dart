import math
import numpy as np

from typing import Type

from datetime import datetime

from django.conf import settings
from django.apps import apps
from django.db import connections, DatabaseError, OperationalError
from django.db.models import QuerySet, Min, Max
from django.utils.translation import gettext as _

import bio_tables.models
import core.models
from biochem import models
from dart.utils import updated_value
from core import models as core_models

import logging

user_logger = logging.getLogger('dart.user')
logger = logging.getLogger('dart')


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


def db_write_by_chunk(model, chunk_size, data, fields=None):
    chunks = math.ceil(len(data) / chunk_size)
    for i in range(0, len(data), chunk_size):
        user_logger.info(_("Writing chunk to database") + " : %d/%d", (int(i / chunk_size) + 1), chunks)
        batch = data[i:i + chunk_size]
        if fields:
            model.objects.using('biochem').bulk_update(batch, fields)
        else:
            model.objects.using('biochem').bulk_create(batch)


def upload_db_rows(model, rows_to_create: [], rows_to_update: [], updated_fields: [str]):
    chunk_size = 100
    if len(rows_to_create) > 0:
        db_write_by_chunk(model, chunk_size, rows_to_create)

    if len(rows_to_update) > 0:
        db_write_by_chunk(model, chunk_size, rows_to_update, updated_fields)


# returns the rows to create, rows to update and fields to update
def get_bcs_d_rows(uploader: str, bottles: list[core_models.Bottle], batch_name: str,
                   bcs_d_model: Type[models.BcsD] = None) -> [[models.BcsD], [models.BcsD], [str]]:
    user_logger.info("Creating/updating BCS table")
    bcs_objects_to_create = []
    bcs_objects_to_update = []

    DART_EVENT_COMMENT = "Created using the DFO at-sea Reporting Template"

    batch = batch_name
    existing_samples = {}
    if bcs_d_model:
        existing_samples = {int(sample.dis_headr_collector_sample_id): sample for sample in
                            bcs_d_model.objects.using('biochem').filter(batch_seq=batch)}

    updated_fields = set()
    total_bottles = len(bottles)
    for count, bottle in enumerate(bottles):
        user_logger.info(_("Compiling Bottle") + " : %d/%d", (count + 1), total_bottles)
        # some of the fields below may be the same as the current value if updating. When that happens
        # a blank string is added to the updated_fields set. Before adding a record to the 'things that need
        # updating' list we check to see if the updated_fields set is empty by first removing the blank string
        # if the string isn't in the set though an error is thrown, so add the blank string here so it will
        # definitely exist later.
        updated_fields.add('')

        event = bottle.event
        mission = event.mission
        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}'

        existing_sample = bottle.bottle_id in existing_samples.keys()
        if existing_sample:
            bcs_row = existing_samples[bottle.bottle_id]
        elif bcs_d_model:
            bcs_row = bcs_d_model._meta.model(dis_headr_collector_sample_id=bottle.bottle_id)
        else:
            bcs_row = models.BcsDReportModel(dis_headr_collector_sample_id=bottle.bottle_id)

        m_start_date = mission.start_date
        m_end_date = mission.end_date
        updated_fields.add(updated_value(bcs_row, 'dis_sample_key_value', dis_sample_key_value))
        updated_fields.add(updated_value(bcs_row, 'created_by', uploader))

        updated_fields.add(updated_value(bcs_row, 'mission_descriptor', mission.mission_descriptor))
        updated_fields.add(updated_value(bcs_row, 'mission_name', mission.name))
        updated_fields.add(updated_value(bcs_row, 'mission_leader', mission.lead_scientist))
        updated_fields.add(updated_value(bcs_row, 'mission_sdate', m_start_date))
        updated_fields.add(updated_value(bcs_row, 'mission_edate', m_end_date))
        updated_fields.add(updated_value(bcs_row, 'mission_platform', mission.platform))
        updated_fields.add(updated_value(bcs_row, 'mission_protocol', mission.protocol))
        updated_fields.add(updated_value(bcs_row, 'mission_geographic_region', mission.geographic_region))
        updated_fields.add(updated_value(bcs_row, 'mission_collector_comment1', mission.collector_comments))
        updated_fields.add(updated_value(bcs_row, 'mission_collector_comment2', mission.more_comments))
        updated_fields.add(updated_value(bcs_row, 'mission_data_manager_comment', mission.data_manager_comments))
        updated_fields.add(updated_value(bcs_row, 'mission_institute',
                                         primary_data_center.name if primary_data_center else "Not Specified"))

        updated_fields.add(updated_value(bcs_row, 'event_collector_event_id', f'{event.event_id:03d}'))
        updated_fields.add(updated_value(bcs_row, 'event_collector_comment1', event.comments))
        updated_fields.add(updated_value(bcs_row, 'event_data_manager_comment', DART_EVENT_COMMENT))
        updated_fields.add(updated_value(bcs_row, 'event_collector_stn_name', event.station.name))
        updated_fields.add(updated_value(bcs_row, 'event_sdate', datetime.strftime(event.start_date, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'event_edate', datetime.strftime(event.end_date, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'event_stime', datetime.strftime(event.start_date, "%H%M")))
        updated_fields.add(updated_value(bcs_row, 'event_etime', datetime.strftime(event.end_date, "%H%M")))
        updated_fields.add(updated_value(bcs_row, 'event_utc_offset', 0))
        updated_fields.add(updated_value(bcs_row, 'event_min_lat', min(event.start_location[0], event.end_location[0])))
        updated_fields.add(updated_value(bcs_row, 'event_max_lat', max(event.start_location[0], event.end_location[0])))
        updated_fields.add(updated_value(bcs_row, 'event_min_lon', min(event.start_location[1], event.end_location[1])))
        updated_fields.add(updated_value(bcs_row, 'event_max_lon', max(event.start_location[1], event.end_location[1])))

        updated_fields.add(updated_value(bcs_row, 'dis_headr_gear_seq', 90000019))  # typically 90000019, not always
        updated_fields.add(updated_value(bcs_row, 'dis_headr_time_qc_code', 1))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_position_qc_code', 1))

        if (bottom_action := event.actions.filter(type=core_models.ActionType.bottom)).exists():
            bottom_action = bottom_action[0]
            updated_fields.add(updated_value(bcs_row, 'dis_headr_sounding', bottom_action.sounding))
            updated_fields.add(updated_value(bcs_row, 'dis_headr_collector', bottom_action.data_collector))

        updated_fields.add(updated_value(bcs_row, 'dis_headr_responsible_group', mission.protocol))

        updated_fields.add(updated_value(bcs_row, 'dis_headr_sdate', datetime.strftime(bottle.closed, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_edate', datetime.strftime(bottle.closed, "%Y-%m-%d")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_stime', datetime.strftime(bottle.closed, "%H%M")))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_etime', datetime.strftime(bottle.closed, "%H%M")))

        if bottle.latitude:
            updated_fields.add(updated_value(bcs_row, 'dis_headr_slat', bottle.latitude))  # Maybe required to use
            updated_fields.add(updated_value(bcs_row, 'dis_headr_elat', bottle.latitude))  # Event lat/lon

        if bottle.longitude:
            updated_fields.add(updated_value(bcs_row, 'dis_headr_slon', bottle.longitude))  # Maybe required to use
            updated_fields.add(updated_value(bcs_row, 'dis_headr_elon', bottle.longitude))  # Event lat/lon

        updated_fields.add(updated_value(bcs_row, 'dis_headr_start_depth', bottle.pressure))
        updated_fields.add(updated_value(bcs_row, 'dis_headr_end_depth', bottle.pressure))

        # The process flag is used by the Biochem upload app to indicate if the data should be processed by
        # the application. Pl/SQL code is run on the table and this flag is set to 'SVE' depending on
        # if the data validates.
        updated_fields.add(updated_value(bcs_row, 'process_flag', 'NR'))
        updated_fields.add(updated_value(bcs_row, 'data_center_code', primary_data_center.data_center_code))

        updated_fields.add(updated_value(bcs_row, 'batch_seq', batch))

        # remove the blank string from the updated_fields set, if there are still values in the set after that
        # then this record needs to be updated.
        updated_fields.remove('')

        if not existing_sample:
            bcs_objects_to_create.append(bcs_row)
        elif len(updated_fields) > 0:
            bcs_objects_to_update.append(bcs_row)

    for bcs_row in bcs_objects_to_create:
        bcs_row.created_date = datetime.now().strftime("%Y-%m-%d")

    if len(bcs_objects_to_update):
        updated_fields.add('created_date')
        for bcs_row in bcs_objects_to_update:
            bcs_row.created_date = datetime.now().strftime("%Y-%m-%d")

    return [bcs_objects_to_create, bcs_objects_to_update, updated_fields]


def get_bcs_p_rows(uploader: str, bottles: QuerySet[core_models.Bottle], batch_name: str,
                   bcs_p_model: Type[models.BcsP] = None) -> [[models.BcsP], [models.BcsP], [str]]:

    bcs_objects_to_create = []
    bcs_objects_to_update = []
    updated_fields = set()

    DART_EVENT_COMMENT = "Created using the DFO at-sea Reporting Template"

    # mission_id: int = bottles.values_list('event__mission', flat=True).distinct().first()
    # mission = core_models.Mission.objects.get(pk=mission_id)
    # institute: bio_tables.models.BCDataCenter = mission.data_center

    batch = batch_name
    existing_samples = {}
    if bcs_p_model:
        existing_samples = {sample.plank_sample_key_value: sample for sample in
                            bcs_p_model.objects.using('biochem').filter(batch_seq=batch)}

    total_bottles = len(bottles)
    for count, bottle in enumerate(bottles):
        user_logger.info(_("Compiling BCS") + " : %d/%d", (count + 1), total_bottles)
        # plankton samples may share bottle_ids, a BCS entry is per bottle, per gear type
        gears = bottle.plankton_data.values_list('gear_type', 'mesh_size').distinct()
        event = bottle.event
        mission = event.mission
        institute: bio_tables.models.BCDataCenter = mission.data_center

        sounding = None
        try:
            # The current AZMP template uses the bottom action for the sounding
            bottom_action: core_models.Action = event.actions.get(type=core_models.ActionType.bottom)
            sounding = bottom_action.sounding
        except core_models.Action.DoesNotExist as e:
            logger.error("Could not acquire bottom action for event sounding")

        try:
            # for calculating volume we need either a wire out or a flow meter start and end. Both of these should
            # be, at the very least, attached to the last action of an event.
            recovery_action: core_models.Action = event.actions.get(type=core_models.ActionType.recovered)
        except core_models.Action.DoesNotExist as e:
            # if there's no recovery event then we won't be able to complete this row of data, it also means this
            # event was aborted
            message = _("Event was likely aborted and contains no recovered action")
            message += " " + _("Event") + f" : {event.event_id:03d}"
            logger.error(message)
            continue

        for gear, mesh_size in gears:
            row_update = set("")
            plankton_key = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}_{gear}'

            m_start_date = mission.start_date
            m_end_date = mission.end_date

            if exists := plankton_key in existing_samples.keys():
                bcs_row = existing_samples[plankton_key]
            elif bcs_p_model:
                bcs_row = bcs_p_model._meta.model(plank_sample_key_value=plankton_key)
            else:
                bcs_row = models.BcsPReportModel(plank_sample_key_value=plankton_key)

            # updated_fields.add(updated_value(bcs_row, 'dis_headr_collector_sample_id', bottle.bottle_id))
            row_update.add(updated_value(bcs_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
            row_update.add(updated_value(bcs_row, 'created_by', uploader))

            row_update.add(updated_value(bcs_row, 'mission_descriptor', mission.mission_descriptor))
            row_update.add(updated_value(bcs_row, 'mission_name', mission.name))
            row_update.add(updated_value(bcs_row, 'mission_leader', mission.lead_scientist))
            row_update.add(updated_value(bcs_row, 'mission_sdate', m_start_date))
            row_update.add(updated_value(bcs_row, 'mission_edate', m_end_date))
            row_update.add(updated_value(bcs_row, 'mission_institute', institute.description if institute else "Not Specified"))
            row_update.add(updated_value(bcs_row, 'mission_platform', mission.platform))
            row_update.add(updated_value(bcs_row, 'mission_protocol', mission.protocol))
            row_update.add(updated_value(bcs_row, 'mission_geographic_region', mission.geographic_region))
            row_update.add(updated_value(bcs_row, 'mission_collector_comment', mission.collector_comments))
            row_update.add(updated_value(bcs_row, 'mission_more_comment', mission.more_comments))
            row_update.add(updated_value(bcs_row, 'mission_data_manager_comment', mission.data_manager_comments))

            row_update.add(updated_value(bcs_row, 'event_collector_event_id', f'{event.event_id:03d}'))
            row_update.add(updated_value(bcs_row, 'event_collector_stn_name', event.station.name))
            row_update.add(updated_value(bcs_row, 'event_sdate', datetime.strftime(event.start_date, "%Y-%m-%d")))
            row_update.add(updated_value(bcs_row, 'event_edate', datetime.strftime(event.end_date, "%Y-%m-%d")))
            row_update.add(updated_value(bcs_row, 'event_stime', datetime.strftime(event.start_date, "%H%M")))
            row_update.add(updated_value(bcs_row, 'event_etime', datetime.strftime(event.end_date, "%H%M")))
            row_update.add(updated_value(bcs_row, 'event_utc_offset', 0))
            row_update.add(updated_value(bcs_row, 'event_min_lat', min(event.start_location[0], event.end_location[0])))
            row_update.add(updated_value(bcs_row, 'event_max_lat', max(event.start_location[0], event.end_location[0])))
            row_update.add(updated_value(bcs_row, 'event_min_lon', min(event.start_location[1], event.end_location[1])))
            row_update.add(updated_value(bcs_row, 'event_max_lon', max(event.start_location[1], event.end_location[1])))

            row_update.add(updated_value(bcs_row, 'event_collector_comment', None))
            row_update.add(updated_value(bcs_row, 'event_more_comment', None))
            row_update.add(updated_value(bcs_row, 'event_data_manager_comment', DART_EVENT_COMMENT))

            row_update.add(updated_value(bcs_row, 'pl_headr_collector_sample_id', bottle.bottle_id))
            row_update.add(updated_value(bcs_row, 'pl_headr_gear_seq', gear))

            # This was set to 1 in the existing AZMP Template for phyto
            row_update.add(updated_value(bcs_row, 'pl_headr_time_qc_code', 1))

            # This was set to 1 in the existing AZMP Template for phyto
            row_update.add(updated_value(bcs_row, 'pl_headr_position_qc_code', 1) if not exists else '')
            row_update.add(updated_value(bcs_row, 'pl_headr_preservation_seq', 90000039))


            # use the event starts and stops if not provided by the bottle.
            row_update.add(updated_value(bcs_row, 'pl_headr_sdate', datetime.strftime(event.start_date, "%Y-%m-%d")))
            row_update.add(updated_value(bcs_row, 'pl_headr_edate', datetime.strftime(event.end_date, "%Y-%m-%d")))
            row_update.add(updated_value(bcs_row, 'pl_headr_stime', datetime.strftime(event.start_date, "%H%M")))
            row_update.add(updated_value(bcs_row, 'pl_headr_etime', datetime.strftime(event.end_date, "%H%M")))

            if bottle.latitude:
                row_update.add(updated_value(bcs_row, 'pl_headr_slat', bottle.latitude))
                row_update.add(updated_value(bcs_row, 'pl_headr_elat', bottle.latitude))
            else:
                row_update.add(updated_value(bcs_row, 'pl_headr_slat', event.start_location[0]))
                row_update.add(updated_value(bcs_row, 'pl_headr_elat', event.end_location[0]))

            if bottle.longitude:
                row_update.add(updated_value(bcs_row, 'pl_headr_slon', bottle.longitude))
                row_update.add(updated_value(bcs_row, 'pl_headr_elon', bottle.longitude))
            else:
                row_update.add(updated_value(bcs_row, 'pl_headr_slon', event.start_location[1]))
                row_update.add(updated_value(bcs_row, 'pl_headr_elon', event.end_location[1]))

            row_update.add(updated_value(bcs_row, 'pl_headr_start_depth', bottle.pressure))
            row_update.add(updated_value(bcs_row, 'pl_headr_end_depth', bottle.pressure))

            row_update.add(updated_value(bcs_row, 'process_flag', 'NR'))
            row_update.add(updated_value(bcs_row, 'data_center_code', institute.data_center_code))

            row_update.add(updated_value(bcs_row, 'batch_seq', batch))

            # Maybe this should be averaged?
            row_update.add(updated_value(bcs_row, 'pl_headr_sounding', sounding))

            collection_method = 90000010  # hydrographic if this is phytoplankton
            procedure = 90000001
            storage = 90000016
            shared = 'N'
            large_plankton_removed = "N"  # No if phytoplankton

            if event.instrument.type == core_models.InstrumentType.net:
                collection_method = 90000001  # vertical if this is zooplankton
                large_plankton_removed = 'Y'  # Yes if Zooplankton

            responsible_group = mission.protocol
            collector = recovery_action.data_collector
            comment = recovery_action.comment

            if event.instrument.type == core_models.InstrumentType.net:
                # all nets are 75 cm in diameter use the formula for the volume of a cylinder height * pi * r^2
                diameter = 0.75
                area = np.pi * np.power(float(diameter/2), 2)

                if event.flow_start and event.flow_end:
                    # if there is a flow meter use (flow_end-flow_start)*0.3 has the height of the cylinder
                    # else use the wire out.
                    # multiply by 0.3 to compensate for the flow meters prop rotation
                    height = (event.flow_end - event.flow_start) * 0.3
                    volume = np.round(height * area, 1)

                    row_update.add(updated_value(bcs_row, 'pl_headr_volume', volume))
                    # 90000002 - volume calculated from recorded revolutions and flow meter calibrations
                    row_update.add(updated_value(bcs_row, 'pl_headr_volume_method_seq', 90000002))
                elif event.wire_out:
                    volume = np.round(event.wire_out * area, 1)

                    row_update.add(updated_value(bcs_row, 'pl_headr_volume', volume))
                    # 90000004 - estimate of volume calculated using depth and gear mouth opening (wire angle ignored)
                    row_update.add(updated_value(bcs_row, 'pl_headr_volume_method_seq', 90000004))
            else:
                row_update.add(updated_value(bcs_row, 'pl_headr_volume', 0.001))
                # 90000010 - not applicable; perhaps net lost; perhaps data from a bottle
                row_update.add(updated_value(bcs_row, 'pl_headr_volume_method_seq', 90000010))

            row_update.add(updated_value(bcs_row, 'pl_headr_lrg_plankton_removed', large_plankton_removed))
            row_update.add(updated_value(bcs_row, 'pl_headr_mesh_size', mesh_size if mesh_size else 0))
            row_update.add(updated_value(bcs_row, 'pl_headr_collection_method_seq', collection_method))
            row_update.add(updated_value(bcs_row, 'pl_headr_collector_deplmt_id', None))
            row_update.add(updated_value(bcs_row, 'pl_headr_procedure_seq', procedure))
            row_update.add(updated_value(bcs_row, 'pl_headr_storage_seq', storage))
            row_update.add(updated_value(bcs_row, 'pl_headr_collector', collector))
            row_update.add(updated_value(bcs_row, 'pl_headr_collector_comment', comment))
            row_update.add(updated_value(bcs_row, 'pl_headr_meters_sqd_flag', "Y"))
            row_update.add(updated_value(bcs_row, 'pl_headr_data_manager_comment', DART_EVENT_COMMENT))
            row_update.add(updated_value(bcs_row, 'pl_headr_responsible_group', responsible_group))
            row_update.add(updated_value(bcs_row, 'pl_headr_shared_data', shared))

            row_update.remove('')

            if not exists:
                bcs_objects_to_create.append(bcs_row)
            elif len(row_update) > 0:
                updated_fields.update(row_update)
                bcs_objects_to_update.append(bcs_row)

    return bcs_objects_to_create, bcs_objects_to_update, updated_fields


def get_bcd_d_rows(database, uploader: str, samples: QuerySet[core_models.DiscreteSampleValue], batch_name: str,
                   bcd_d_model: Type[models.BcdD] = None) -> [[models.BcdD], [models.BcdD], [str]]:

    bcd_objects_to_create = []
    bcd_objects_to_update = []
    errors = []

    # if these rows are being generated for a report we don't have the bcd_d_model, which is what
    # links Django to the oracle database so we create a 'fake' BCD row using the BcdDReportModel in
    # place of the BcdD model
    bcd_model = models.BcdDReportModel

    tmp_table = 'biochem_tmp'
    tmp_model_manager = None

    if bcd_d_model:
        # copy the biochem data we're interested in looking at into an in-memory version of the database,
        # which will make queries much faster than doing them over a VPN to a datacenter across the country
        existing_samples_qs = bcd_d_model.objects.using('biochem').filter(batch_seq=batch_name)
        tmp_samples = [sample for sample in existing_samples_qs]
        model = get_model('tmp_bcd_d', models.BcdD)
        tmp_model_manager = get_temp_space(model, tmp_table).objects.using(tmp_table)
        tmp_model_manager.bulk_create(tmp_samples)

        bcd_model = bcd_d_model._meta.model

    user_logger.info("Compiling BCD Discrete samples")

    # update fields is a list of BCD column names that change and will be bulk updated later. If nothing
    # changes, update_fields will be empty
    updated_fields = set()

    total_samples = len(samples)
    for count, ds_sample in enumerate(samples):
        # dis_data_num = count + dis_data_num
        user_logger.info(_("Compiling updates for BCD Discrete samples") + " : " + "%d/%d", (count + 1), total_samples)
        sample = ds_sample.sample
        bottle = sample.bottle
        event = bottle.event
        mission = event.mission

        # Use the row level datatype if provided otherwise use the mission level datatype
        bc_data_type = ds_sample.datatype if ds_sample.datatype else sample.type.datatype

        # if a sample already exists it may need updating
        existing_sample = False

        # Some of the fields below may be the same as the current value if updating a row. When that happens
        # updated_value returns a blank string because adding None to a set will throw an error.
        # So we add a blank string to the update_field set, then update_values returns a blank string if no
        # update is required. Before adding a record to the 'things that need updating' list we remove the blank
        # string (that we know is there) and then check to see if the updated_fields set is empty.
        updated_fields.add('')

        primary_data_center = mission.data_center

        dis_sample_key_value = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}'

        # If the sample doesn't have a dis_data_num or it doesn't match an existing sample create a new row
        collector_id = f'{bottle.bottle_id}'

        bcd_row = bcd_model(dis_detail_collector_samp_id=collector_id)
        if tmp_model_manager:
            existing_samples = tmp_model_manager.filter(
                dis_detail_data_type_seq=bc_data_type.data_type_seq,
                dis_detail_collector_samp_id=collector_id
            )
            if existing_samples.exists():
                replicate = ds_sample.replicate-1
                if replicate < len(existing_samples):
                    bcd_row = existing_samples[replicate]
                    existing_sample = True

        # if not existing_sample:
        #     updated_fields.add(updated_value(bcd_row, 'dis_data_num', dis_data_num))

        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_type_seq', bc_data_type.data_type_seq))

        # ########### Stuff that we get from the bottle object ################################################### #
        updated_fields.add(updated_value(bcd_row, 'dis_header_start_depth', bottle.pressure))
        updated_fields.add(updated_value(bcd_row, 'dis_header_end_depth', bottle.pressure))

        # ########### Stuff that we get from the event object #################################################### #
        event = bottle.event

        updated_fields.add(updated_value(bcd_row, 'event_collector_event_id', f'{event.event_id:03d}'))
        updated_fields.add(updated_value(bcd_row, 'event_collector_stn_name', event.station.name))

        if bottle.latitude and bottle.longitude:
            updated_fields.add(updated_value(bcd_row, 'dis_header_slat', bottle.latitude))
            updated_fields.add(updated_value(bcd_row, 'dis_header_slon', bottle.longitude))
        else:
            location = event.start_location
            updated_fields.add(updated_value(bcd_row, 'dis_header_slat', location[0]))
            updated_fields.add(updated_value(bcd_row, 'dis_header_slon', location[1]))

        if bottle.closed:
            updated_fields.add(updated_value(bcd_row, 'dis_header_sdate', bottle.closed.strftime("%Y-%m-%d")))
            updated_fields.add(updated_value(bcd_row, 'dis_header_stime', bottle.closed.strftime("%H%M")))
        else:
            event_date = event.start_date
            updated_fields.add(updated_value(bcd_row, 'dis_header_sdate', event_date.strftime("%Y-%m-%d")))
            updated_fields.add(updated_value(bcd_row, 'dis_header_stime', event_date.strftime("%H%M")))

        # ########### Stuff that we get from the Mission object #################################################### #
        updated_fields.add(updated_value(bcd_row, 'dis_detail_detail_collector', mission.lead_scientist))

        # mission descriptor
        # 18 + [ship initials i.e 'JC' for fixstation is 'VA'] + 2-digit year + 3-digit cruise number or station code
        # 18VA13666 <- HL_02, 2013, fixstation
        # 18HU21185 <- Hudson, AZMP, 2021
        #
        # According to Robert Benjamin, this identifier is provided by MEDS and will have to be part of the
        # core.models.Mission object as it gets entered later on.
        updated_fields.add(updated_value(bcd_row, 'mission_descriptor', mission.mission_descriptor))

        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_qc_code', ds_sample.flag if ds_sample.flag else 0))
        updated_fields.add(updated_value(bcd_row, 'dis_detail_detection_limit', ds_sample.limit))

        limit = ds_sample.limit if ds_sample.limit else None
        updated_fields.add(updated_value(bcd_row, 'dis_detail_detection_limit', limit))

        # The process flag is used by the Biochem upload app to indicate if the data should be processed by
        # the application. 'NR' is the default code indicating the data needs to be processed
        updated_fields.add(updated_value(bcd_row, 'process_flag', 'NR'))
        updated_fields.add(updated_value(bcd_row, 'created_by', uploader))
        updated_fields.add(updated_value(bcd_row, 'data_center_code', primary_data_center.data_center_code))

        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_type_seq', bc_data_type.data_type_seq))
        updated_fields.add(updated_value(bcd_row, 'data_type_method', bc_data_type.method))
        updated_fields.add(updated_value(bcd_row, 'dis_detail_data_value', ds_sample.value))
        updated_fields.add(updated_value(bcd_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
        updated_fields.add(updated_value(bcd_row, 'dis_sample_key_value', dis_sample_key_value))

        updated_fields.add(updated_value(bcd_row, 'batch_seq', batch_name))

        updated_fields.remove('')

        if not existing_sample:
            bcd_objects_to_create.append(bcd_row)
        elif len(updated_fields) > 0:
            bcd_objects_to_update.append(bcd_row)

    if len(errors) > 0:
        core_models.Error.objects.using(database).bulk_create(errors)

    user_logger.info(_("Indexing Primary Keys"))
    compress_keys(bcd_objects_to_create, bcd_d_model, 'dis_data_num')

    return [bcd_objects_to_create, bcd_objects_to_update, updated_fields]


def get_bcd_p_rows(database, uploader: str, samples: QuerySet[core_models.PlanktonSample], batch_name: str,
                   bcd_p_model: Type[models.BcdP] = None) -> [[models.BcdP], [models.BcdP], [str]]:

    bcd_objects_to_create = []
    bcd_objects_to_update = []
    errors = []

    # if these rows are being generated for a report we don't have the bcd_d_model, which is what
    # links Django to the oracle database so we create a 'fake' BCD row using the BcdDReportModel in
    # place of the BcdD model
    bcd_model = models.BcdPReportModel

    tmp_table = 'biochem_tmp'
    tmp_model_manager = None

    if bcd_p_model:
        # copy the biochem data we're interested in looking at into an in-memory version of the database,
        # which will make queries much faster than doing them over a VPN to a datacenter across the country
        existing_samples_qs = bcd_p_model.objects.using('biochem').filter(batch_seq=batch_name)
        tmp_samples = [sample for sample in existing_samples_qs]
        model = get_model('tmp_bcd_p', models.BcdP)
        tmp_model_manager = get_temp_space(model, tmp_table).objects.using(tmp_table)
        tmp_model_manager.bulk_create(tmp_samples)

        bcd_model = bcd_p_model._meta.model

    user_logger.info("Compiling BCD Plankton samples")

    # update fields is a list of BCD column names that change and will be bulk updated later. If nothing
    # changes, update_fields will be empty
    updated_fields = set()

    total_samples = len(samples)
    for count, sample in enumerate(samples):
        row_update = set("")

        user_logger.info(_("Compiling BCD Plankton rows") + " : %d/%d", (count + 1), total_samples)

        bottle = sample.bottle
        event = bottle.event
        mission = event.mission
        gear = sample.gear_type.pk

        plankton_key = f'{mission.mission_descriptor}_{event.event_id:03d}_{bottle.bottle_id}_{gear}'

        existing_sample = False

        # determine if sample is existing or not here
        bcd_row = bcd_model(plank_sample_key_value=plankton_key)
        if tmp_model_manager:
            existing_samples = tmp_model_manager.filter(plank_sample_key_value=plankton_key)
            if existing_samples.exists():
                bcd_row = existing_samples.first()
                existing_sample = True

        # ########### Stuff that we get from the event object #################################################### #
        # PLANK_DATA_NUM - is the autogenerated primary key
        # PLANK_SAMPLE_KEY_VALUE - is unique to a mission_event_sample_xxx

        # ########### Stuff that we get from the sample object #################################################### #
        # updated_fields.add(uploader.updated_value(bcd_row, 'plank_sample_key_value', sample.plank_sample_key_value))

        taxonomic_id = sample.taxa.taxonomic_name[0:20]  # The collector taxonomic id field is only 20 characters

        row_update.add(updated_value(bcd_row, 'pl_gen_national_taxonomic_seq', sample.taxa.pk))
        row_update.add(updated_value(bcd_row, 'pl_gen_collector_taxonomic_id', taxonomic_id))

        row_update.add(updated_value(bcd_row, 'pl_gen_life_history_seq', sample.stage.pk))
        row_update.add(updated_value(bcd_row, 'pl_gen_trophic_seq', 90000000))

        row_update.add(updated_value(bcd_row, 'pl_gen_min_sieve', sample.min_sieve))
        row_update.add(updated_value(bcd_row, 'pl_gen_max_sieve', sample.max_sieve))

        row_update.add(updated_value(bcd_row, 'pl_gen_split_fraction', sample.split_fraction))
        row_update.add(updated_value(bcd_row, 'pl_gen_sex_seq', sample.sex.pk))

        row_update.add(updated_value(bcd_row, 'pl_gen_counts', sample.count))
        row_update.add(updated_value(bcd_row, 'pl_gen_count_pct', sample.percent))

        # if the wet weight is less than zero then it's being used as a code to generate a collector comment
        # and should be set to None when uploaded to biochem
        wet_weight = sample.raw_wet_weight if sample.raw_wet_weight and sample.raw_wet_weight > 0 else None
        row_update.add(updated_value(bcd_row, 'pl_gen_wet_weight', wet_weight))
        row_update.add(updated_value(bcd_row, 'pl_gen_dry_weight', sample.raw_dry_weight))
        row_update.add(updated_value(bcd_row, 'pl_gen_bio_volume', sample.volume))

        row_update.add(updated_value(bcd_row, 'pl_gen_presence', 'Y'))
        row_update.add(updated_value(bcd_row, 'pl_gen_collector_comment', sample.collector_comment))

        row_update.add(updated_value(bcd_row, 'pl_gen_source', "UNASSIGNED"))
        row_update.add(updated_value(bcd_row, 'pl_gen_modifier', sample.modifier))

        # PL_GEN_DATA_MANAGER_COMMENT
        # PL_FREQ_DATA_TYPE_SEQ
        # PL_FREQ_UPPER_BIN_SIZE
        # PL_FREQ_LOWER_BIN_SIZE
        # PL_FREQ_BUG_COUNT
        # PL_FREQ_BUG_SEQ
        # PL_FREQ_DATA_VALUE
        # PL_FREQ_DATA_QC_CODE
        # PL_FREQ_DETAIL_COLLECTOR
        # PL_DETAIL_DATA_TYPE_SEQ
        # PL_DETAIL_DATA_VALUE
        # PL_DETAIL_DATA_QC_CODE
        # PL_DETAIL_DETAIL_COLLECTOR
        # PL_INDIV_DATA_TYPE_SEQ
        # PL_INDIV_BUG_SEQ
        # PL_INDIV_DATA_VALUE
        # PL_INDIV_DATA_QC_CODE
        # PL_INDIV_DATA_COLLECTOR
        # PL_GEN_MODIFIER
        # PL_GEN_UNIT

        # ########### Stuff that we get from the bottle object #################################################### #
        bottle = sample.bottle

        # ########### Stuff that we get from the event object #################################################### #
        event = bottle.event

        row_update.add(updated_value(bcd_row, 'event_collector_event_id', f'{event.event_id:03d}'))
        row_update.add(updated_value(bcd_row, 'event_collector_stn_name', event.station.name))

        event_date = event.start_date

        # ########### Stuff that we get from the Mission object #################################################### #
        mission = event.mission

        row_update.add(updated_value(bcd_row, 'batch_seq', batch_name))

        # mission descriptor
        # 18 + [ship initials i.e 'JC' for fixstation is 'VA'] + 2-digit year + 3-digit cruise number or station code
        # 18VA13666 <- HL_02, 2013, fixstation
        # 18HU21185 <- Hudson, AZMP, 2021
        #
        # According to Robert Benjamin, this identifier is provided by MEDS and will have to be part of the
        # core.models.Mission object as it gets entered later on.
        row_update.add(updated_value(bcd_row, 'mission_descriptor', mission.mission_descriptor))
        row_update.add(updated_value(bcd_row, 'created_by', uploader))
        row_update.add(updated_value(bcd_row, 'data_center_code', mission.data_center.data_center_code))
        row_update.add(updated_value(bcd_row, 'created_date', datetime.now().strftime("%Y-%m-%d")))
        row_update.add(updated_value(bcd_row, 'process_flag', 'NR'))

        row_update.remove('')

        if not existing_sample:
            bcd_objects_to_create.append(bcd_row)
        elif len(row_update) > 0:
            updated_fields.update(row_update)
            bcd_objects_to_update.append(bcd_row)

    if len(errors) > 0:
        core_models.Error.objects.using(database).bulk_create(errors)

    user_logger.info(_("Indexing Primary Keys"))
    compress_keys(bcd_objects_to_create, bcd_p_model, 'plank_data_num')

    return [bcd_objects_to_create, bcd_objects_to_update, updated_fields]


def compress_keys(bcd_objects_to_create, bcd_model, primary_key):
    if len(bcd_objects_to_create) <= 0:
        return

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
    for index, obj in enumerate(bcd_objects_to_create):
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
