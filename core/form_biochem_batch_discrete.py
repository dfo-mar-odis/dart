from datetime import datetime
from typing import Tuple

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connections
from django.db.models import QuerySet
from django.urls import path
from django.utils.translation import gettext_lazy as _

from biochem import upload
from biochem import models as biochem_models
from biochem.models import BcsD, BcdD

from core import models as core_models

from core import form_biochem_batch, validation, form_biochem_database

import logging

user_logger = logging.getLogger('dart.user')


class BiochemDiscreteBatchForm(form_biochem_batch.BiochemDBBatchForm):

    datatype = 'DISCRETE'
    bcd_report_model = biochem_models.BcdD
    bcs_report_model = biochem_models.BcsD

    def get_download_url(self, alias: str = "core:form_biochem_discrete_download_batch"):
        return super().get_download_url(alias)

    def get_upload_url(self, alias: str = "core:form_biochem_discrete_upload_batch"):
        return super().get_upload_url(alias)

    def get_header_update_url(self, alias: str = "core:form_biochem_discrete_update_header"):
        return super().get_header_update_url(alias)

    def get_batch_update_url(self, alias: str = "core:form_biochem_discrete_select_batch"):
        return super().get_batch_update_url(alias)

    def get_delete_batch_url(self, alias: str = "core:form_biochem_discrete_delete_batch") -> str | None:
        return super().get_delete_batch_url(alias)

    def get_stage1_validate_url(self, alias: str="core:form_biochem_discrete_stage1_validation") -> str | None:
        return super().get_stage1_validate_url(alias)

    def get_stage2_validate_url(self, alias: str = "core:form_biochem_discrete_stage2_validation") -> str | None:
        return super().get_stage2_validate_url(alias)

    def get_checkin_url(self, alias: str = "core:form_biochem_discrete_checkin") -> str | None:
        return super().get_checkin_url(alias)

    def is_batch_stage1_validated(self, bcs_model = biochem_models.BcsD, bcd_model = biochem_models.BcdD) -> bool | None:
        return super().is_batch_stage1_validated(bcs_model, bcd_model)

    def get_batch_choices(self) -> list[Tuple[int, str]]:
        choices = []
        mission = core_models.Mission.objects.get(pk=self.mission_id)

        if form_biochem_database.is_connected():
            try:
                batches: QuerySet = biochem_models.Bcbatches.objects.using('biochem').filter(
                    name=mission.mission_descriptor
                ).order_by('-batch_seq')

                choices = [(db.batch_seq, f"{db.batch_seq}: {db.name} (Created: {self.get_batch_date(db)})") for db in
                           batches if db.discrete_station_edits.count() > 0 or db.discrete_header_edits.count() > 0]
            except DatabaseError as err:
                # 942 is "table or view does not exist". If connected this shouldn't happen, but if it does
                # we'll return an empty choice list.
                if err.args[0].code != 942:
                    raise err

        return choices


def get_discrete_data(mission: core_models.Mission, upload_all=False):
    if upload_all:
        # Fetch all rows regardless of their current state
        data_types = core_models.BioChemUpload.objects.filter(
            type__mission=mission).values_list('type', flat=True).distinct()
    else:
        # Exclude rows that have been marked for deletion.
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


def download_batch_func(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None) -> int | None:
    bcs = BcsD
    bcs_upload = upload.get_bcs_d_rows
    bcd = BcdD
    bcd_upload = upload.get_bcd_d_rows
    return form_biochem_batch.download_batch_func(
        mission, uploader, get_data_func=get_discrete_data, file_postfix='D',
        bcd_model=bcd, bcd_upload=bcd_upload, bcs_model=bcs, bcs_upload=bcs_upload
    )


def upload_bcs_d_data(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    # 2) if the BCS_D table doesn't exist, create with all the bottles. We're only uploading CTD bottles
    samples, bottles = get_discrete_data(mission)
    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        create = upload.get_bcs_d_rows(uploader=uploader, bottles=bottles, batch=batch)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS Discrete rows"))
        upload.upload_db_rows(biochem_models.BcsD, create)
        # biochem_models.BcsD.objects.using('biochem').bulk_create(create)


def upload_bcd_d_data(mission: core_models.Mission, uploader, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    user_logger.info(_("Compiling BCD rows for : ") + mission.name)

    # 3) else filter the samples down to rows based on:
    #  * samples in this mission
    #  * samples of the current sample_type
    samples, bottles = get_discrete_data(mission)
    if samples.exists():
        message = _("Compiling BCD rows for sample type") + " : " + mission.name
        user_logger.info(message)
        create = upload.get_bcd_d_rows(uploader=uploader, samples=samples, batch=batch)

        message = _("Creating/updating BCD rows for sample type") + " : " + mission.name
        user_logger.info(message)

        upload.upload_db_rows(biochem_models.BcdD, create)
        # bcd_d.objects.using("biochem").bulk_create(create)

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


def upload_batch_func(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches) -> int | None:

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

    # create and upload the BCS data if it doesn't already exist
    upload_bcs_d_data(mission, uploader, batch)
    upload_bcd_d_data(mission, uploader, batch)


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
    form_biochem_batch.delete_batch(mission_id, batch_id, label)


def checkin_batch(mission_id, batch_id) -> None:

    header_model = biochem_models.Bcdiscretehedrs
    label = "DISCRETE"
    oracle_checkout_proc = "Download_Discrete_Mission"
    oracle_archive_proc = "ARCHIVE_BATCH.ARCHIVE_DISCRETE_BATCH"

    form_biochem_batch.checkin_mission(mission_id, batch_id, label, header_model,
                                        oracle_checkout_proc, oracle_archive_proc, delete_batch)


prefix = 'biochem/discrete/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/download/', form_biochem_batch.download_batch,
         kwargs={'logger_name': user_logger.name, 'download_batch_func': download_batch_func},
         name="form_biochem_discrete_download_batch"),

    path(f'<int:mission_id>/{prefix}/upload/', form_biochem_batch.upload_batch,
         kwargs={'logger_name': user_logger.name, 'upload_batch_func': upload_batch_func},
         name="form_biochem_discrete_upload_batch"),

    path(f'<int:mission_id>/{prefix}/update_batch_list/', form_biochem_batch.get_batch_list,
         kwargs={"form_class": BiochemDiscreteBatchForm},
         name="form_biochem_discrete_update_header"),

    path(f'<int:mission_id>/{prefix}/set_selected_batch/', form_biochem_batch.get_update_controls,
         kwargs={"form_class": BiochemDiscreteBatchForm},
         name="form_biochem_discrete_select_batch"),

    path(f'<int:mission_id>/{prefix}/validate/stage1/<int:batch_id>/', form_biochem_batch.stage_1_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage1_validation_func},
         name="form_biochem_discrete_stage1_validation"),

    path(f'<int:mission_id>/{prefix}/validate/stage2/<int:batch_id>/', form_biochem_batch.stage_2_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage2_validation_func},
         name="form_biochem_discrete_stage2_validation"),

    path(f'<int:mission_id>/{prefix}/delete_selected_batch/<int:batch_id>/', form_biochem_batch.delete_selected_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': delete_batch},
         name="form_biochem_discrete_delete_batch"),

    path(f'<int:mission_id>/{prefix}/checkin_selected_batch/<int:batch_id>/', form_biochem_batch.checkin_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': checkin_batch},
         name="form_biochem_discrete_checkin"),
]
