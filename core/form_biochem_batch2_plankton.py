import os
import subprocess
import time
from pathlib import Path
from typing import Tuple

from bs4 import BeautifulSoup
from crispy_forms.utils import render_crispy_form
from django.conf import settings
from django.db import DatabaseError
from django.db.models import QuerySet
from django.http import HttpResponse
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from biochem import upload
from biochem import models as biochem_models

from core import forms as core_forms, form_biochem_database
from core import models as core_models

from core import form_biochem_batch2

import logging

from core.form_biochem_plankton import BiochemPlanktonBatchForm

user_logger = logging.getLogger('dart.user')


class BiochemDiscreteBatchForm(form_biochem_batch2.BiochemDBBatchForm):

    def get_download_url(self):
        return reverse_lazy("core:form_biochem_plankton_download_batch", args=[self.mission_id])

    def get_upload_url(self):
        return reverse_lazy("core:form_biochem_plankton_upload_batch", args=[self.mission_id])

    def get_header_update_url(self):
        return reverse_lazy("core:form_biochem_plankton_select_batch", args=[self.mission_id])

    def get_batch_choices(self) -> list[Tuple[int, str]]:

        choices = []

        mission = core_models.Mission.objects.get(pk=self.mission_id)
        if form_biochem_database.is_connected():
            try:
                # get batches that exist in the "edit" tables
                edit_batches = biochem_models.Bcbatches.objects.using('biochem').filter(
                    name=mission.mission_descriptor,
                    activity_edits__data_pointer_code__iexact='PL'
                    # batch_seq__in=batch_ids
                ).distinct().order_by('-batch_seq')

                choices = [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in edit_batches]

                # get batches that exist in the BCS/BCD tables, excluding batches in the edit tables because we've already
                # retrieved those batches
                batches = biochem_models.Bcbatches.objects.using('biochem').filter(
                    plankton_station_edits__mission_descriptor__iexact=mission.mission_descriptor
                ).exclude(pk__in=edit_batches).distinct().order_by('-batch_seq')

                choices += [(db.batch_seq, f"{db.batch_seq}: {db.name}") for db in batches]
            except DatabaseError as err:
                # 942 is "table or view does not exist". If connected this shouldn't happen, but if it does
                # we'll return an empty choice list.
                if err.args[0].code != 942:
                    raise err

        return choices


def get_plankton_data(mission: core_models.Mission, upload_all=False) -> (QuerySet, QuerySet):
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


def download_batch_func(mission: core_models.Mission, uploader: str) -> None:
    bcs_file_name = f'{mission.name}_BCS_P.csv'
    bcd_file_name = f'{mission.name}_BCD_P.csv'

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

    samples, bottles = get_plankton_data(mission, upload_all=True)

    sample_rows = upload.get_bcs_p_rows(uploader=uploader, bottles=bottles)
    form_biochem_batch2.write_bcs_file(sample_rows, bcs_file, biochem_models.BcsPReportModel)

    bottle_rows = upload.get_bcd_p_rows(uploader=uploader, samples=samples)
    form_biochem_batch2.write_bcd_file(bottle_rows, bcd_file, biochem_models.BcdPReportModel)

    # if we're on windows then let's pop the directory where we saved the reports open. Just to annoy the user.
    if os.name == 'nt':
        subprocess.Popen(r'explorer {report_path}'.format(report_path=report_path))


def download_batch(request, mission_id):
    return form_biochem_batch2.download_batch(request, mission_id, user_logger.name, download_batch_func)


def upload_batch(request, mission_id):
    raise NotImplementedError


def update_batch_list(request, mission_id):
    # when updating the batch list, we'll return the whole header for the batch card because depending on what's
    # selected there might be different buttons or different button status shown.
    #
    # this function will be called when the selection changes, the biochem_db_connect trigger is fired, or
    # when the reload_batch trigger is fired

    form = BiochemPlanktonBatchForm(request, mission_id=mission_id)
    html = render_crispy_form(form)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup.find(id=form.get_id_builder().get_card_header_id()))


def select_batch(request, mission_id):
    return form_biochem_batch2.get_batch_list(request, mission_id, BiochemDiscreteBatchForm)


prefix = 'biochem/plankton/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/download/', download_batch, name="form_biochem_plankton_download_batch"),
    path(f'<int:mission_id>/{prefix}/upload/', upload_batch, name="form_biochem_plankton_upload_batch"),

    path(f'<int:mission_id>/{prefix}/select_batch/', select_batch, name="form_biochem_plankton_select_batch"),
]