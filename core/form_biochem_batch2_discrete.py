import os
import subprocess
import time

from datetime import datetime
from pathlib import Path
from typing import Tuple

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connections
from django.db.models import QuerySet
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from biochem import upload
from biochem import models as biochem_models

from core import models as core_models

from core import form_biochem_batch2, validation, form_biochem_database

import logging

from core.form_biochem_batch2 import BiochemDBBatchForm

user_logger = logging.getLogger('dart.user')


class BiochemDiscreteBatchForm(form_biochem_batch2.BiochemDBBatchForm):

    def get_download_url(self):
        return reverse_lazy("core:form_biochem_discrete_download_batch", args=[self.mission_id])

    def get_upload_url(self):
        return reverse_lazy("core:form_biochem_discrete_upload_batch", args=[self.mission_id])

    def get_header_update_url(self):
        return reverse_lazy("core:form_biochem_discrete_update_header", args=[self.mission_id])

    def get_batch_update_url(self):
        return reverse_lazy("core:form_biochem_discrete_select_batch", args=[self.mission_id])

    # return None if conditions for delete aren't met, return the URL otherwise
    # override this for custom functionality if required.
    def get_delete_batch_url(self) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy("core:form_biochem_discrete_delete_batch", args=[self.mission_id, batch_id])

    def get_stage1_validate_url(self) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy("core:form_biochem_discrete_stage1_validation", args=[self.mission_id, batch_id])

    def is_batch_stage1_validated(self) -> bool | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        mission: core_models.Mission = core_models.Mission.objects.get(pk=self.mission_id)
        mission_edits = biochem_models.Bcmissionedits.objects.using('biochem').filter(batch__pk=batch_id,
                                                                                      descriptor=mission.mission_descriptor)
        if not mission_edits.exists():
            return None

        mission_edit = mission_edits.first()

        return mission_edit.process_flag == "ENR" or mission_edit.process_flag == "ECN" or mission_edit.process_flag == "EAR"

    def get_stage2_validate_url(self) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy("core:form_biochem_discrete_stage2_validation", args=[self.mission_id, batch_id])

    def get_checkin_url(self) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy("core:form_biochem_discrete_checkin", args=[self.mission_id, batch_id])


    def is_batch_stage2_validated(self) -> bool | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        mission: core_models.Mission = core_models.Mission.objects.get(pk=self.mission_id)
        mission_edits = biochem_models.Bcmissionedits.objects.using('biochem').filter(
            batch__pk=batch_id, descriptor=mission.mission_descriptor)

        if not mission_edits.exists():
            # if there's no process flag this is a new mission.
            return None

        if mission_edits.filter(process_flag='ERR').exists():
            # if there are any ERR flags there are errors in this mission and it's not valid
            return False

        event_edits = biochem_models.Bceventedits.objects.using('biochem').filter(
            batch__pk=batch_id, process_flag='ERR')
        if event_edits.exists():
            # if there are any ERR flags there are errors in this mission and it's not valid
            return False

        hdr_edits = biochem_models.Bcdiscretehedredits.objects.using('biochem').filter(
            batch__pk=batch_id, process_flag='ERR')
        if hdr_edits.exists():
            # if there are any ERR flags there are errors in this mission and it's not valid
            return False

        detail_edits = biochem_models.Bcdiscretedtailedits.objects.using('biochem').filter(
            batch__pk=batch_id, process_flag='ERR')
        if detail_edits.exists():
            # if there are any ERR flags there are errors in this mission and it's not valid
            return False

        replicate_edits = biochem_models.Bcdisreplicatedits.objects.using('biochem').filter(
            batch__pk=batch_id, process_flag='ERR')
        if replicate_edits.exists():
            # if there are any ERR flags there are errors in this mission and it's not valid
            return False

        mission_edit = mission_edits.first()

        if mission_edit.process_flag == "ENR":
            # ENR means this is a new record and hasn't been validated yet.
            return None

        return mission_edit.process_flag == "ECN" or mission_edit.process_flag == "EAR"

    @staticmethod
    def get_batch_date(batch: biochem_models.Bcbatches) -> str:
        if batch.mission_edits.exists():
            return batch.mission_edits.first().created_date.strftime('%Y-%m-%d')

        if (bcs := biochem_models.BcsDReportModel.objects.using('biochem').filter(batch=batch)).exists():
            return bcs.first().created_date.strftime('%Y-%m-%d')

        return "None"

    def get_batch_choices(self) -> list[Tuple[int, str]]:
        choices = []
        mission = core_models.Mission.objects.get(pk=self.mission_id)

        if form_biochem_database.is_connected():
            try:
                batches: QuerySet = biochem_models.Bcbatches.objects.using('biochem').filter(
                    name=mission.mission_descriptor
                ).order_by('-batch_seq')
                choices = [(db.batch_seq, f"{db.batch_seq}: {db.name} (Created: {self.get_batch_date(db)})") for db in
                           batches]
            except DatabaseError as err:
                # 942 is "table or view does not exist". If connected this shouldn't happen, but if it does
                # we'll return an empty choice list.
                if err.args[0].code != 942:
                    raise err

        return choices


def get_discrete_data(mission: core_models.Mission, upload_all=False) -> (QuerySet, QuerySet):
    if upload_all:
        data_types = core_models.BioChemUpload.objects.filter(
            type__mission=mission).values_list('type', flat=True).distinct()
    else:
        data_types = core_models.BioChemUpload.objects.filter(
            type__mission=mission
        ).exclude(
            status=core_models.BioChemUploadStatus.delete
        ).values_list('type', flat=True).distinct()

    samples = core_models.DiscreteSampleValue.objects.filter(sample__bottle__event__mission=mission,
                                                             sample__type_id__in=data_types)
    bottle_ids = samples.values_list('sample__bottle_id').distinct()
    bottles = core_models.Bottle.objects.filter(pk__in=bottle_ids)

    return samples, bottles


def download_batch_func(mission: core_models.Mission, uploader: str) -> int | None:
    bcs_file_name = f'{mission.name}_BCS_D.csv'
    bcd_file_name = f'{mission.name}_BCD_D.csv'

    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    bcs_file = os.path.join(report_path, bcs_file_name)
    bcd_file = os.path.join(report_path, bcd_file_name)

    # check if the files are locked and fail early if they are
    if form_biochem_batch2.is_locked(bcs_file):
        raise IOError(f"Requested file is locked {bcs_file}")

    # check if the files are locked and fail early if they are
    if form_biochem_batch2.is_locked(bcd_file):
        raise IOError(f"Requested file is locked {bcs_file}")

    user_logger.info(f"Creating BCS/BCD files. Using uploader: {uploader}")

    samples, bottles = get_discrete_data(mission, upload_all=True)

    sample_rows = upload.get_bcs_d_rows(uploader=uploader, bottles=bottles)
    form_biochem_batch2.write_bcs_file(sample_rows, bcs_file, biochem_models.BcsDReportModel)

    bottle_rows = upload.get_bcd_d_rows(uploader=uploader, samples=samples)
    form_biochem_batch2.write_bcd_file(bottle_rows, bcd_file, biochem_models.BcdDReportModel)

    # if we're on windows then let's pop the directory where we saved the reports open. Just to annoy the user.
    if os.name == 'nt':
        subprocess.Popen(r'explorer {report_path}'.format(report_path=report_path))

    # No batch ID is created when downloading a mission's BCS/BCD tables
    return 0


def upload_bcs_d_data(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    # 1) get bottles from BCS_D table
    bcs_d = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)
    exists = upload.check_and_create_model('biochem', bcs_d)

    # 2) if the BCS_D table doesn't exist, create with all the bottles. We're only uploading CTD bottles
    samples, bottles = get_discrete_data(mission)
    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        create = upload.get_bcs_d_rows(uploader=uploader, bottles=bottles, batch=batch, bcs_d_model=bcs_d)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS Discrete rows"))
        upload.upload_db_rows(bcs_d, create)


def upload_bcd_d_data(mission: core_models.Mission, uploader, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    # 1) get the biochem BCD_D model
    table_name = form_biochem_database.get_bcd_d_table()
    bcd_d = upload.get_model(table_name, biochem_models.BcdD)

    # 2) if the BCD_D model doesn't exist create it and add all samples specified by sample_id
    exists = upload.check_and_create_model('biochem', bcd_d)
    if not exists:
        raise DatabaseError(f"A database error occurred while uploading BCD D data. "
                            f"Could not connect to table {table_name}")

    user_logger.info(_("Compiling BCD rows for : ") + mission.name)

    # 3) else filter the samples down to rows based on:
    #  * samples in this mission
    #  * samples of the current sample_type
    samples, bottles = get_discrete_data(mission)
    if samples.exists():
        message = _("Compiling BCD rows for sample type") + " : " + mission.name
        user_logger.info(message)
        create = upload.get_bcd_d_rows(uploader=uploader, samples=samples, batch=batch, bcd_d_model=bcd_d)

        message = _("Creating/updating BCD rows for sample type") + " : " + mission.name
        user_logger.info(message)

        upload.upload_db_rows(bcd_d, create)

        # after uploading the samples we want to update the status of the samples in this mission so we
        # know what has been uploaded and what hasn't.
        uploaded = core_models.BioChemUpload.objects.filter(
            type__mission=mission,
            status=core_models.BioChemUploadStatus.upload
        )

        for sample in uploaded:
            sample.status = core_models.BioChemUploadStatus.uploaded
            sample.upload_date = datetime.now()
            sample.save()


def upload_batch_func(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None) -> int | None:
    # are we connected?
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=core_models.ErrorType.biochem).delete()
    core_models.MissionError.objects.filter(mission=mission, type=core_models.ErrorType.biochem).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Sensor/Sample Datatypes"))
    samples_types_for_upload = [bcupload.type for bcupload in
                                core_models.BioChemUpload.objects.filter(type__mission=mission)]

    # Todo: I'm running the standard DART based event/data validation here, but we probably should be running the
    #  BioChem Validation from core.form_biochem_pre_validation.run_biochem_validation() and then not upload
    #  to BioChem if we know there are issues like a missing descriptor or values outside their valid range
    errors = validation.validate_samples_for_biochem(mission=mission, sample_types=samples_types_for_upload)

    if errors:
        # send_user_notification_queue('biochem', _("Datatypes missing see errors"))
        user_logger.info(_("Datatypes missing see errors"))
        core_models.MissionError.objects.bulk_create(errors)

    batch_id = form_biochem_batch2.get_mission_batch_id()
    batch = biochem_models.Bcbatches.objects.using('biochem').get_or_create(name=mission.mission_descriptor,
                                                                            username=uploader,
                                                                            batch_seq=batch_id)[0]
    # create and upload the BCS data if it doesn't already exist
    upload_bcs_d_data(mission, uploader, batch)
    upload_bcd_d_data(mission, uploader, batch)

    return batch_id


def stage1_validation_func(mission_id, batch_id) -> None:
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating station data")
        stn_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_STATION", str, [batch_id])

        if stn_pass_var != 'T':
            raise ValidationError("Database package function failed: Station data in the BCS table did not validate.")

        user_logger.info(f"validating discrete data")
        data_pass_var = cur.callfunc("VALIDATE_DISCRETE_STATN_DATA.VALIDATE_DISCRETE_DATA", str, [batch_id])

        if data_pass_var != 'T':
            raise ValidationError("Database package function failed: Station data in the BCD table did not validate.")

        user_logger.info(f"Moving BCS/BCD data to workbench")
        cur.callfunc("POPULATE_DISCRETE_EDITS_PKG.POPULATE_DISCRETE_EDITS", str, [batch_id])

        cur.execute('commit')


def stage2_validation_func(mission_id, batch_id) -> None:
    user = form_biochem_database.get_uploader()
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating mission data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating event data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete header data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISHEDR_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete detail data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISDETAIL_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating discrete replicate data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_DISREPLIC_ERRORS", str, [batch_id, user])


def delete_batch(mission_id: int, batch_id: int) -> None:
    label = "DISCRETE"
    bcd_model = upload.get_model(form_biochem_database.get_bcd_d_table(), biochem_models.BcdD)
    bcs_model = upload.get_model(form_biochem_database.get_bcs_d_table(), biochem_models.BcsD)

    form_biochem_batch2.delete_batch(mission_id, batch_id, label, bcd_model, bcs_model)


def checkin_batch(mission_id, batch_id) -> None:
    return_status = ''
    return_value = ''

    # check for existing mission matching this batch and check it out to the user edit tables if it exists
    # This is to create a backup which the user can then recover from if something goes wrong.
    batch = biochem_models.Bcbatches.objects.using('biochem').get(batch_seq=batch_id)
    batch_mission_edit = batch.mission_edits.first()

    header_model = biochem_models.Bcdiscretehedrs
    oracle_proc = "Download_Discrete_Mission"

    bc_mission: biochem_models.Bcmissions = form_biochem_batch2.checkout_existing_mission(
        mission=batch_mission_edit,
        label="DISCRETE",
        header_model=header_model,
        oracle_proc=oracle_proc
    )

    # if the **batch_mission_edit** mission has a mission_seq it needs to be archived using the
    # REARCHIVE_DISCRETE_MISSION function. Otherwise, the cursor will return without errors, but won't actually have
    # done anything ( -_-), seriously...
    # if batch_mission_edit.mission_id is not None:
    #     stage2_validation_func(batch_mission_edit.mission_id, batch_id)

    # check in new mission
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Uploading new mission with batch id {batch_id}")
        return_value = cur.callproc("ARCHIVE_BATCH.ARCHIVE_DISCRETE_BATCH", [batch_id, return_status])
        cur.execute('commit')

    # if the checkin fails release the old mission and delete it from the edit tables
    # if successful delete the new mission from the edit tables, but keep the old one.
    try:
        if return_value[1] is not None:
            raise ValueError(return_value[1])

        # confirm the replacement mission was uploaded, this will throw a DoesNotExist exception if the mission doesn't
        # exist in Biochem
        if batch_mission_edit.mission_id is not None:
            uploaded_mission = biochem_models.Bcmissions.objects.using('biochem').get(
                mission_seq=batch_mission_edit.mission_id)
        elif bc_mission:
            uploaded_mission = biochem_models.Bcmissions.objects.using('biochem').exclude(
                mission_seq=bc_mission.mission_seq).get(descriptor=batch_mission_edit.descriptor,
                                                        created_date=batch_mission_edit.created_date)

        # if the mission exists in the lock tables and there was no problem archiving it,
        # then remove it from the locked table
        if bc_mission and bc_mission.locked_missions:
            bc_mission.delete()

        delete_batch(mission_id, batch_id)
    except biochem_models.Bcmissions.DoesNotExist as ex:
        user_logger.error(f"Issues with archiving mission: {return_value[1]}")

        if bc_mission and bc_mission.locked_missions:
            old_batch_id = biochem_models.Bcmissionedits.objects.using('biochem').filter(
                mission_edt_seq=bc_mission.mission_seq).first().batch.batch_seq
            delete_batch(mission_id, old_batch_id)
            bc_mission.locked_missions.delete()

        raise DatabaseError("Could not check in new mission")


prefix = 'biochem/discrete/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/download/', form_biochem_batch2.download_batch,
         kwargs={'logger_name': user_logger.name, 'download_batch_func': download_batch_func},
         name="form_biochem_discrete_download_batch"),

    path(f'<int:mission_id>/{prefix}/upload/', form_biochem_batch2.upload_batch,
         kwargs={'logger_name': user_logger.name, 'upload_batch_func': upload_batch_func},
         name="form_biochem_discrete_upload_batch"),

    path(f'<int:mission_id>/{prefix}/update_batch_list/', form_biochem_batch2.get_batch_list,
         kwargs={"form_class": BiochemDiscreteBatchForm},
         name="form_biochem_discrete_update_header"),

    path(f'<int:mission_id>/{prefix}/set_selected_batch/', form_biochem_batch2.get_update_controls,
         kwargs={"form_class": BiochemDiscreteBatchForm},
         name="form_biochem_discrete_select_batch"),

    path(f'<int:mission_id>/{prefix}/validate/stage1/<int:batch_id>/', form_biochem_batch2.stage_1_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage1_validation_func},
         name="form_biochem_discrete_stage1_validation"),

    path(f'<int:mission_id>/{prefix}/validate/stage2/<int:batch_id>/', form_biochem_batch2.stage_2_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage2_validation_func},
         name="form_biochem_discrete_stage2_validation"),

    path(f'<int:mission_id>/{prefix}/delete_selected_batch/<int:batch_id>/', form_biochem_batch2.delete_selected_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': delete_batch},
         name="form_biochem_discrete_delete_batch"),

    path(f'<int:mission_id>/{prefix}/checkin_selected_batch/<int:batch_id>/', form_biochem_batch2.checkin_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': checkin_batch},
         name="form_biochem_discrete_checkin"),
]
