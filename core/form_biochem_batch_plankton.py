from typing import Tuple

from django.db import DatabaseError, connections
from django.urls import path
from django.utils.translation import gettext_lazy as _

from biochem import upload
from biochem import models as biochem_models
from biochem.models import BcdP, BcsP

from core import form_biochem_database
from core import models as core_models

from core import form_biochem_batch

import logging

user_logger = logging.getLogger('dart.user')


class BiochemPlanktonBatchForm(form_biochem_batch.BiochemDBBatchForm):

    datatype = 'PLANKTON'
    bcd_report_model = biochem_models.BcdP
    bcs_report_model = biochem_models.BcsP

    def get_download_url(self, alias: str = "core:form_biochem_plankton_download_batch"):
        return super().get_download_url(alias)

    def get_upload_url(self, alias: str = "core:form_biochem_plankton_upload_batch"):
        return super().get_upload_url(alias)

    def get_header_update_url(self, alias: str = "core:form_biochem_plankton_update_header"):
        return super().get_header_update_url(alias)

    def get_batch_update_url(self, alias: str = "core:form_biochem_plankton_select_batch"):
        return super().get_batch_update_url(alias)

    def get_delete_batch_url(self, alias: str = "core:form_biochem_plankton_delete_batch") -> str | None:
        return super().get_delete_batch_url(alias)

    def get_stage1_validate_url(self, alias: str="core:form_biochem_plankton_stage1_validation") -> str | None:
        return super().get_stage1_validate_url(alias)

    def get_stage2_validate_url(self, alias: str = "core:form_biochem_plankton_stage2_validation") -> str | None:
        return super().get_stage2_validate_url(alias)

    def get_checkin_url(self, alias: str = "core:form_biochem_plankton_checkin") -> str | None:
        return super().get_checkin_url(alias)

    def is_batch_stage1_validated(self, bcs_model = biochem_models.BcsP, bcd_model = biochem_models.BcdP) -> bool | None:
        return super().is_batch_stage1_validated(bcs_model, bcd_model)

    def get_batch_choices(self) -> list[Tuple[int, str]]:

        choices = []

        mission = core_models.Mission.objects.get(pk=self.mission_id)
        if form_biochem_database.is_connected():
            try:
                # get batches that exist in the "edit" tables
                batches = biochem_models.Bcbatches.objects.using('biochem').filter(
                    name=mission.mission_descriptor,
                    # batch_seq__in=batch_ids
                ).distinct().order_by('-batch_seq')

                choices = [(db.batch_seq, f"{db.batch_seq}: {db.name} (Created: {self.get_batch_date(db)})") for db in
                           batches if db.plankton_station_edits.count() > 0 or db.plankton_header_edits.count() > 0]

            except DatabaseError as err:
                # 942 is "table or view does not exist". If connected this shouldn't happen, but if it does
                # we'll return an empty choice list.
                if err.args[0].code != 942:
                    raise err

        return choices


def get_plankton_data(mission: core_models.Mission, upload_all=False):
    # the upload_all variable is more for discrete data since the user can pick and choose
    # what discrete data to upload. For plankton it's all or none.
    samples = core_models.PlanktonSample.objects.filter(bottle__event__mission=mission)
    bottle_ids = samples.values_list('bottle_id').distinct()
    bottles = core_models.Bottle.objects.filter(pk__in=bottle_ids)

    return samples, bottles


def download_batch_func(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None) -> int | None:
    bcs = BcsP
    bcs_upload = upload.get_bcs_p_rows
    bcd = BcdP
    bcd_upload = upload.get_bcd_p_rows
    return form_biochem_batch.download_batch_func(
        mission, uploader, get_data_func=get_plankton_data, file_postfix='P',
        bcd_model=bcd, bcd_upload=bcd_upload, bcs_model=bcs, bcs_upload=bcs_upload
    )


def upload_bcs_p_data(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    # 2) get all the bottles to be uploaded
    samples, bottles = get_plankton_data(mission)
    if bottles.exists():
        # 4) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCS rows"))
        bcs_create = upload.get_bcs_p_rows(uploader=uploader, bottles=bottles, batch=batch)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCS Plankton rows"))
        upload.upload_db_rows(biochem_models.BcsP, bcs_create)
        # biochem_models.BcsP.objects.bulk_create(bcs_create)


def upload_bcd_p_data(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches = None):
    if not form_biochem_database.is_connected():
        raise DatabaseError(f"No Database Connection")

    user_logger.info(_("Compiling BCD rows for : ") + mission.name)

    # 4) if the bcs_p table exist, create with all the bottles. linked to plankton samples
    samples = core_models.PlanktonSample.objects.filter(bottle__event__mission=mission)
    if samples.exists():
        # 5) upload only bottles that are new or were modified since the last biochem upload
        # send_user_notification_queue('biochem', _("Compiling BCS rows"))
        user_logger.info(_("Compiling BCD Plankton rows"))
        bcd_create = upload.get_bcd_p_rows(uploader=uploader, samples=samples, batch=batch)

        # send_user_notification_queue('biochem', _("Creating/updating BCS rows"))
        user_logger.info(_("Creating/updating BCD Plankton rows"))
        upload.upload_db_rows(biochem_models.BcdP, bcd_create)
        # biochem_models.BcdP.objects.using('biochem').bulk_create(bcd_create)


def upload_batch_func(mission: core_models.Mission, uploader: str, batch: biochem_models.Bcbatches) -> int | None:
    # clear previous errors if there were any from the last upload attempt
    mission.errors.filter(type=core_models.ErrorType.biochem_plankton).delete()
    core_models.MissionError.objects.filter(mission=mission, type=core_models.ErrorType.biochem_plankton).delete()

    # send_user_notification_queue('biochem', _("Validating Sensor/Sample Datatypes"))
    user_logger.info(_("Validating Plankton Data"))

    # create and upload the BCS data if it doesn't already exist
    upload_bcs_p_data(mission, uploader, batch)
    upload_bcd_p_data(mission, uploader, batch)


def stage1_validation_func(mission_id, batch_id) -> None:
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating station data")
        stn_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_STATION", str, [batch_id])

        user_logger.info(f"validating plankton data")
        data_pass_var = cur.callfunc("VALIDATE_PLANKTON_STATN_DATA.VALIDATE_PLANKTON_DATA", str, [batch_id])

        if stn_pass_var == 'T' and data_pass_var == 'T':
            user_logger.info(f"Moving BCS/BCD data to workbench")
            cur.callfunc("POPULATE_PLANKTON_EDITS_PKG.POPULATE_PLANKTON_EDITS", str, [batch_id])
        else:
            user_logger.info(f"Errors in BCS/BCD data. Stand by for a damage report.")

        cur.execute('commit')
        cur.close()


def stage2_validation_func(mission_id, batch_id) -> None:
    user = form_biochem_database.get_uploader()
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"validating mission data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_MISSION_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating event data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_EVENT_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating plankton header data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_HEDR_ERRORS", str, [batch_id, user])

        user_logger.info(f"validating plankton general data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_GENERL_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton details data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_DTAIL_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton details data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_FREQ_ERRS", str, [batch_id, user])

        user_logger.info(f"validating plankton replicate data")
        cur.callfunc("BATCH_VALIDATION_PKG.CHECK_BATCH_PLANK_INDIV_ERRS", str, [batch_id, user])


def delete_batch(mission_id: int, batch_id: int) -> None:
    label = "PLANKTON"
    form_biochem_batch.delete_batch(mission_id, batch_id, label)


def checkin_batch(mission_id, batch_id) -> None:

    header_model = biochem_models.Bcplanktnhedrs
    label = "PLANKTON"
    oracle_checkout_proc = "Download_Plankton_Mission"
    oracle_archive_proc = "ARCHIVE_BATCH.ARCHIVE_PLANKTON_BATCH"

    form_biochem_batch.checkin_mission(mission_id, batch_id, label, header_model,
                                        oracle_checkout_proc, oracle_archive_proc, delete_batch)


prefix = 'biochem/plankton/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/download/', form_biochem_batch.download_batch,
         kwargs={'logger_name': user_logger.name, 'download_batch_func': download_batch_func},
         name="form_biochem_plankton_download_batch"),

    path(f'<int:mission_id>/{prefix}/upload/', form_biochem_batch.upload_batch,
         kwargs={'logger_name': user_logger.name, 'upload_batch_func': upload_batch_func},
         name="form_biochem_plankton_upload_batch"),

    path(f'<int:mission_id>/{prefix}/update_batch_list/', form_biochem_batch.get_batch_list,
         kwargs={"form_class": BiochemPlanktonBatchForm},
         name="form_biochem_plankton_update_header"),

    path(f'<int:mission_id>/{prefix}/set_selected_batch/', form_biochem_batch.get_update_controls,
         kwargs={"form_class": BiochemPlanktonBatchForm},
         name="form_biochem_plankton_select_batch"),

    path(f'<int:mission_id>/{prefix}/validate/stage1/<int:batch_id>/', form_biochem_batch.stage_1_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage1_validation_func},
         name="form_biochem_plankton_stage1_validation"),

    path(f'<int:mission_id>/{prefix}/validate/stage2/<int:batch_id>/', form_biochem_batch.stage_2_validation,
         kwargs={'logger_name': user_logger.name, 'batch_func': stage2_validation_func},
         name="form_biochem_plankton_stage2_validation"),

    path(f'<int:mission_id>/{prefix}/delete_selected_batch/<int:batch_id>/', form_biochem_batch.delete_selected_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': delete_batch},
         name="form_biochem_plankton_delete_batch"),

    path(f'<int:mission_id>/{prefix}/checkin_selected_batch/<int:batch_id>/', form_biochem_batch.checkin_batch,
         kwargs={'logger_name': user_logger.name, 'batch_func': checkin_batch},
         name="form_biochem_plankton_checkin"),
]