import csv
import os
import subprocess

from datetime import datetime
from pathlib import Path
from typing import Tuple, Type, Callable

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Row, Layout, Field, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import OperationalError, connections, models, DatabaseError

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import path, reverse_lazy
from django.utils.connection import ConnectionDoesNotExist
from django.utils.translation import gettext as _
from pandas.io.sql import table_exists

from config.utils import load_svg
from core import forms as core_forms
from core import models as core_models
from core import form_biochem_database

from biochem import models as biochem_models

import logging
logger = logging.getLogger("dart")
user_logger = logging.getLogger("dart.user")

card_context = {
    "card_name": "biochem_db_batch_form",
    "card_title": _("Biochem Batches")
}

BIOCHEM_BATCH_STATUS_ALERT = "div_id_data_alert_message"
BIOCHEM_BATCH_SELECTION_ID = "div_id_input_batch_selection"
BIOCHEM_BATCH_CONTROL_ROW_ID = "div_id_row_batch_control"

class BiochemDBBatchForm(core_forms.CollapsableCardForm):

    # I had to override the default Bootstrap template for fields, because someone thought putting 'mb-3'
    # as a default for field wrappers was a good idea and it creates a massive gap under the inputs when
    # used in a card title
    field_template = os.path.join(settings.TEMPLATE_DIR, "field.html")

    mission_id = None
    batch_selection = forms.ChoiceField(
        label="",
        choices=[],
        required=False,
    )

    datatype = None
    bcd_report_model = None
    bcs_report_model = None

    def get_batch_id(self) -> None | int:
        batch_id = self.initial.get("batch_selection", "")
        return int(batch_id) if batch_id else None

    def get_download_url(self, alias: str = None) -> str:
        return reverse_lazy(alias, args=[self.mission_id])

    def get_upload_url(self, alias: str = None) -> str:
        return reverse_lazy(alias, args=[self.mission_id])

    # return None if conditions for validation aren't met, return the URL otherwise
    def get_stage1_validate_url(self, alias: str = None) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy(alias, args=[self.mission_id, batch_id])

    # return None if conditions for validation aren't met, return the URL otherwise
    def get_stage2_validate_url(self, alias: str = None) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy(alias, args=[self.mission_id, batch_id])

    # return None if conditions for delete aren't met, return the URL otherwise
    def get_delete_batch_url(self, alias: str = None) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy(alias, args=[self.mission_id, batch_id])

    def get_checkin_url(self, alias: str = None) -> str | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        return reverse_lazy(alias, args=[self.mission_id, batch_id])

    def get_batch_update_url(self, alias: str = None) -> str:
        return reverse_lazy(alias, args=[self.mission_id])

    def get_header_update_url(self, alias: str = None):
        return reverse_lazy(alias, args=[self.mission_id])

    def get_batch_error_url(self, alias: str = 'core:form_biochem_batch_batch_errors') -> str:
        batch_id = self.get_batch_id()
        if batch_id is None:
            batch_id = 0

        return reverse_lazy(alias, args=[self.mission_id, batch_id])

    def get_download_button(self):
        attrs = {
            'title': _("Download BCS/BCD tables"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'click, download_mission_bcs_bcd from:body'
        }

        if self.mission_id:
            attrs['hx-get'] = self.get_download_url()
        else:
            attrs['disabled'] = "disabled"

        icon = load_svg('arrow-down-square')
        btn = StrictButton(icon, **attrs, css_id="btn_id_batch_download", css_class="btn btn-primary btn-sm")

        return btn

    def get_upload_button(self):
        attrs = {
            'title': _("Upload BCS/BCD tables"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'click, upload_mission_bcs_bcd from:body'
        }

        if self.mission_id:
            attrs['hx-get'] = self.get_upload_url()
        else:
            attrs['disabled'] = "disabled"

        icon = load_svg('arrow-up-square')
        btn = StrictButton(icon, **attrs, css_id="btn_id_batch_upload", css_class="btn btn-primary btn-sm")

        return btn

    # if validation hasn't been run return None.
    # if validation has been run and is invalid return False
    # if validation has been run and is valid return True
    def is_batch_stage1_validated(self, bcs_model = None, bcd_model = None) -> bool | None:
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        mission: core_models.Mission = core_models.Mission.objects.get(pk=self.mission_id)
        mission_edits = biochem_models.Bcmissionedits.objects.using('biochem').filter(
            batch__pk=batch_id, descriptor=mission.mission_descriptor
        )

        if not mission_edits.exists():
            if bcs_model and bcd_model:
                bad_bcd_rows = bcs_model.objects.using('biochem').filter(batch_id=batch_id, process_flag='SVE').exists()
                bad_bcs_rows = bcd_model.objects.using('biochem').filter(batch_id=batch_id, process_flag='SVE').exists()
                # if rows for either of these exist, we aren't validated
                if bad_bcs_rows or bad_bcd_rows:
                    return False
            return None

        mission_edit = mission_edits.first()

        return mission_edit.process_flag in ["ENR", "ECN", "EAR"]

    def get_stage1_validate_button(self, validated: None | bool = None):
        url = self.get_stage1_validate_url()
        attrs = {
            'title': _("Run Stage 1 - Validation on Metadata"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'click, run_stage1_validation from:body',
            'hx-post': url
        }

        icon = load_svg('1-square')
        css_class = "btn btn-sm "
        css_class += "btn-secondary" if validated is None else "btn-success" if validated else "btn-danger"

        if validated is not None:
            attrs['disabled'] = "disabled"

        btn = StrictButton(icon, **attrs, css_id="btn_id_batch_stage1_validate", css_class=css_class)

        return btn

    # if validation hasn't been run return None.
    # if validation has been run and is invalid return False
    # if validation has been run and is valid return True
    def is_batch_stage2_validated(self) -> bool | None:
        # There is actually an oracle procedure for checking if a batch is valid
        # ARCHIVE_BATCH.VALID_BATCH
        batch_id = self.get_batch_id()
        if batch_id is None:
            return None

        result = ''

        missions = biochem_models.Bcmissionedits.objects.using('biochem').filter(batch_id=batch_id)
        if not missions.exists():
            return None

        mission = missions.first()
        # EAR means it was a mission that was previosuly archived
        # ENR means it's a new missio that hasn't been validated yet
        if mission.process_flag is None or mission.process_flag == 'EAR'  or mission.process_flag == 'ENR':
            return None

        with connections['biochem'].cursor() as cur:
            user_logger.info(f"validating batch")
            result = cur.callfunc("ARCHIVE_BATCH.VALID_BATCH", bool, [batch_id, self.datatype])

        return result

    # disabled if stage 1 validation hasn't been run or is invalid
    def get_stage2_validate_button(self, disabled: bool | None = None, validated: None | bool = None):
        url = self.get_stage2_validate_url()
        attrs = {
            'title': _("Run Stage 2 - Validation on Metadata"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'click, run_stage2_validation from:body',
            'hx-post': url
        }

        css_class = "btn btn-sm "
        if disabled is None or disabled or validated is not None:
            attrs['disabled'] = "disabled"

        css_class += "btn-secondary" if validated is None else "btn-success" if validated else "btn-danger"

        icon = load_svg('2-square')
        btn = StrictButton(icon, **attrs, css_id="btn_id_batch_stage2_validate", css_class=css_class)

        return btn

    def get_delete_batch_button(self):
        # The delete button has a hidden element on it so when you click the button you get the confirmation message
        #   If the function is being triggerd other than the button it won't ask for additional confirmation
        url = self.get_delete_batch_url()
        btn_attrs = {
            'title': _("Delete the selected batch"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-confirm': _('Are you sure?'),
            'hx-post': url
        }

        hidden_btn_attrs = {
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'delete_selected_batch from:body',
            'hx-post': url,
            'type': 'hidden'
        }

        icon = load_svg('dash-square')
        btn = StrictButton(icon, **btn_attrs, css_id="btn_id_batch_delete", css_class="btn btn-danger btn-sm")

        div_btn = Div(
            btn,
            **hidden_btn_attrs,
            css_class="d-inline"
        )

        return div_btn

    def get_checkin_button(self, disabled=True):
        url = self.get_checkin_url()
        attrs = {
            'title': _("Check-in Mission to Archive"),
            'hx-target': f'#{self.get_id_builder().get_alert_area_id()}',
            'hx-trigger': 'click, checkin_selected_batch from:body',
            'hx-post': url
        }

        if disabled is None or disabled:
            attrs['disabled'] = "disabled"

        icon = load_svg('check-square')
        btn = StrictButton(icon, **attrs, css_id="btn_id_batch_checkin", css_class="btn btn-secondary btn-sm")

        return btn

    def get_button_row(self):

        # depending on the selected batch and validation status of the batch we'll want to send back different buttons

        button_column = Column(css_class="col-auto")
        row = Row(button_column, css_id=BIOCHEM_BATCH_CONTROL_ROW_ID)
        if self.get_batch_id() is None:
            button_column.append(self.get_download_button())
            button_column.append(self.get_upload_button())
        else:
            validate_1 = self.is_batch_stage1_validated()
            validate_2 = self.is_batch_stage2_validated()
            disabled_2 = validate_1 is None or validate_1 is False or validate_2 is not None

            button_column.append(self.get_stage1_validate_button(validated=validate_1))
            button_column.append(self.get_stage2_validate_button(disabled=disabled_2, validated=validate_2))
            if validate_1 and validate_2:
                button_column.append(self.get_checkin_button(disabled=False))

            button_column.append(self.get_delete_batch_button())

        return row

    def get_batch_selection(self):

        url = self.get_batch_update_url()
        batch_select_attributes = {
            'id': BIOCHEM_BATCH_SELECTION_ID,
            'hx-target': f'#{self.get_id_builder().get_card_id()}',
            'hx-swap': 'outerHTML',
            # biochem_db_connect is fired by the form_biochem_database module when connecting or disconnecting from a DB
            'hx-trigger': "change, batch_updated from:body",
            'hx-get': url
        }

        return Field('batch_selection', css_class="form-select form-select-sm",
                     template=self.field_template, wrapper_class="col-auto", **batch_select_attributes)

    def get_card_header(self, header_attributes: dict = None) -> Div:
        if header_attributes is None:
            url = self.get_header_update_url()
            header_attributes = {
                # biochem_db_connect is fired by the form_biochem_database module when connecting or disconnecting from a DB
                'hx-target': f"#{self.get_id_builder().get_card_header_id()}",
                'hx-trigger': 'biochem_db_connect from:body, reload_batch from:body',
                'hx-get': url
            }

        header = super().get_card_header(header_attributes=header_attributes)

        batch_col = Column(self.get_batch_selection(), css_class="col-auto")
        header.fields[0].append(batch_col)

        # the blank row is to push the buttons to the right of the card header
        blank_col = Column(css_class="col")
        header.fields[0].append(blank_col)

        button_col = Column(
            self.get_button_row(),
            css_class="col-auto"
        )
        header.fields[0].append(button_col)

        return header

    def get_card_body(self) -> Div:
        attrs = {
            'hx-get': self.get_batch_error_url(),
            'hx-trigger': 'load, batch_updated from:body',
        }
        body = Div(css_class='card-body vertical-scrollbar', id=self.get_card_body_id(), **attrs)
        return body

    def get_batch_date(self, batch: biochem_models.Bcbatches) -> str:
        if batch.mission_edits.exists():
            return batch.mission_edits.first().created_date.strftime('%Y-%m-%d')

        if (bcs := self.bcs_report_model.objects.using('biochem').filter(batch=batch)).exists():
            return bcs.first().created_date.strftime('%Y-%m-%d')

        return "None"

    # Implementing classes should return a list of (key, value) pairs where the key is the batch_seq id
    # and the value is a string to be placed in the drop down selectiong
    def get_batch_choices(self) -> list[Tuple[int, str]]:
        raise NotImplementedError("The function to set the batch choices hasn't been implemented yet.")

    def __init__(self, *args, mission_id, **kwargs):
        self.mission_id = mission_id
        super(BiochemDBBatchForm, self).__init__(*args, **card_context, **kwargs)

        self.fields['batch_selection'].choices = [(None, '--- NEW ---')]
        self.fields['batch_selection'].choices += self.get_batch_choices()


class MissionDescriptorForm(forms.Form):

    mission_descriptor = forms.CharField(max_length=10)
    trigger_action = forms.CharField(max_length=50)

    def __init__(self, *args, mission_id, **kwargs):
        self.mission_id = mission_id
        super(MissionDescriptorForm, self).__init__(*args, **kwargs)

        attrs = {
            'title': _("Set mission descriptor"),
            'hx-post': reverse_lazy('core:form_biochem_batch_mission_descriptor', args=[self.mission_id]),
            'hx-target': f"#{BIOCHEM_BATCH_STATUS_ALERT}",
        }

        icon = load_svg("check-square")
        submit = StrictButton(icon, **attrs, css_class='btn btn-primary btn-sm')

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('trigger_action', type="hidden"),
            Field('mission_descriptor', css_class="form-control form-control-sm"),
            submit,
        )


class UploaderForm(forms.Form):

    uploader2 = forms.CharField(max_length=20, label=_("Uploader"),
                                help_text=_("User's lastname and first initial. Lowercase. No spaces"))
    trigger_action = forms.CharField(max_length=50)

    def __init__(self, *args, mission_id, **kwargs):
        self.mission_id = mission_id
        super(UploaderForm, self).__init__(*args, **kwargs)

        attrs = {
            'title': _("Set the Uploader User Name"),
            'hx-post': reverse_lazy('core:form_biochem_batch_uploader', args=[self.mission_id]),
            'hx-target': f"#{BIOCHEM_BATCH_STATUS_ALERT}",
        }

        icon = load_svg("check-square")
        submit = StrictButton(icon, **attrs, css_class='btn btn-primary btn-sm')

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('trigger_action', type="hidden"),
            Field('uploader2', css_class="form-control form-control-sm"),
            submit,
        )


def is_locked(file):
    try:
        # if a file exists and can't be renamed to itself this will throw an exception indicating the file
        # can't be opened and written to
        if os.path.exists(file):
            os.rename(file, file)
        return False
    except OSError:
        return True


def get_mission_batch_id():
    try:
        batch = biochem_models.Bcbatches.objects.using('biochem').order_by('batch_seq')
        batch_seqs = list(batch.values_list('batch_seq', flat=True))

        # find the first and last key in the set and use that to create a range, then subtract keys that are
        # being used from the set. What is left are available keys that can be assigned to new rows being created
        sort_seq = []
        end = 0
        if len(batch_seqs) > 0:
            start, end = 1, batch_seqs[-1]
            sort_seq = sorted(set(range(start, end)).difference(batch_seqs))

        if len(sort_seq) > 0:
            return sort_seq[0]

        return end + 1

    except ConnectionDoesNotExist as ex:
        # if we're not connected, note it. The user may not be logged in or might be creating csv versions
        # of the tables which will either be 1 or the batch_seq stored in the mission table
        logger.exception(ex)
    except OperationalError as ex:
        # if the bcbatches table doesn't exist, note it and return 1 to the user.
        logger.exception(ex)

    return 1


def write_bcs_file(rows, bcs_file, report_model: Type[models.Model]):
    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.

    bcs_headers = [field.name for field in report_model._meta.fields]

    with open(bcs_file, 'w', newline='', encoding="UTF8") as f:

        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(bcs_headers)

        for idx, bcs_row in enumerate(rows):
            row = [getattr(bcs_row, header, '') for header in bcs_headers]
            writer.writerow(row)


def write_bcd_file(rows, bcd_file, report_model: Type[models.Model]):
    # because we're not passing in a link to a database for the bcd_d_model there will be no updated rows or fields
    # only the objects being created will be returned.

    bcd_headers = [field.name for field in report_model._meta.fields]

    with open(bcd_file, 'w', newline='', encoding="UTF8") as f:

        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(bcd_headers)

        for idx, bcd_row in enumerate(rows):
            row = [str(idx + 1) if header == 'dis_data_num' else getattr(bcd_row, header, '') for
                   header in bcd_headers]
            writer.writerow(row)


def download_batch_func(mission: core_models.Mission, uploader: str, get_data_func: Callable, file_postfix: str,
                        bcs_model, bcs_upload, bcd_model, bcd_upload) -> int | None:

    bcs_file_name = f'{mission.name}_BCS_{file_postfix}.csv'
    bcd_file_name = f'{mission.name}_BCD_{file_postfix}.csv'

    report_path = os.path.join(settings.BASE_DIR, "reports")
    Path(report_path).mkdir(parents=True, exist_ok=True)

    bcs_file = os.path.join(report_path, bcs_file_name)
    bcd_file = os.path.join(report_path, bcd_file_name)

    # check if the files are locked and fail early if they are
    if is_locked(bcs_file):
        raise IOError(f"Requested file is locked {bcs_file}")

    # check if the files are locked and fail early if they are
    if is_locked(bcd_file):
        raise IOError(f"Requested file is locked {bcs_file}")

    user_logger.info(f"Creating BCS/BCD files. Using uploader: {uploader}")

    samples, bottles = get_data_func(mission, upload_all=True)

    sample_rows = bcs_upload(uploader=uploader, bottles=bottles)
    write_bcs_file(sample_rows, bcs_file, bcs_model)

    bottle_rows = bcd_upload(uploader=uploader, samples=samples)
    write_bcd_file(bottle_rows, bcd_file, bcd_model)

    # if we're on windows then let's pop the directory where we saved the reports open. Just to annoy the user.
    if os.name == 'nt':
        subprocess.Popen(r'explorer {report_path}'.format(report_path=report_path))

    # No batch ID is created when downloading a mission's BCS/BCD tables
    return 0


def set_descriptor(request, mission_id):
    form = MissionDescriptorForm(request.POST, mission_id=mission_id)

    if form.is_valid():
        mission = core_models.Mission.objects.get(pk=mission_id)
        mission.mission_descriptor = form.cleaned_data['mission_descriptor']
        mission.save()

        response = HttpResponse()
        response['HX-Trigger-After-Settle'] = request.POST.get('trigger_action', '')
        return response

    html = render_crispy_form(form)

    return HttpResponse(html)


# set a session variable to save the uploader
def set_uploader(request, mission_id):
    form = UploaderForm(request.POST, mission_id=mission_id)

    if form.is_valid():
        # save uploader to session
        request.session['uploader2'] = form.cleaned_data['uploader2']

        response = HttpResponse()
        response['HX-Trigger-After-Settle'] = request.POST.get('trigger_action', '')
        return response

    html = render_crispy_form(form)
    return HttpResponse(html)


def _descriptor_form(trigger, mission_id, mission_descriptor=None) -> HttpResponse | None:
    if not mission_descriptor:
        descriptor_form = MissionDescriptorForm(mission_id=mission_id, initial={"trigger_action": trigger})
        html = render_crispy_form(descriptor_form)
        soup = BeautifulSoup(html, 'html.parser')

        msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "")
        msg_alert.include_close_button()
        msg_alert.get_message_container().append(soup)
        return HttpResponse(msg_alert)

    return None


def _uploader_form(trigger, mission_id, uploader=None) -> HttpResponse | None:
    if not uploader:
        uploader_form = UploaderForm(mission_id=mission_id, initial={"trigger_action": trigger})
        html = render_crispy_form(uploader_form)
        soup = BeautifulSoup(html, 'html.parser')

        msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "")
        msg_alert.include_close_button()
        msg_alert.get_message_container().append(soup)
        return HttpResponse(msg_alert)

    return None


def deal_with_batch(request, trigger, mission_id, logger_name, batch_func=None) -> Tuple[int, HttpResponse]:
    """
    Handles batch-related operations for a given mission.

    This function performs the following steps:
        1. Retrieves the mission object based on the provided `mission_id`.
        2. Ensures the mission descriptor is set. If not, returns a form to set it.
        3. Checks if an uploader name is available from an existing DB connection.
            If not, retrieves it from the session or prompts the user to set it.
        4. Initializes a status alert for the operation.
        5. Executes the provided `batch_func` to perform the batch operation (e.g., upload, download).
        6. Handles exceptions and updates the status alert accordingly.

    Args:
        request: The HTTP request object.
        trigger (str): The name of the event that triggered the operation.
        mission_id (int): The ID of the mission associated with the batch.
        logger_name (str): The name of the logger to use for logging messages.
        batch_func (callable, optional): A function to execute the batch operation. Defaults to None.

    Returns:
        Tuple[int, HttpResponse]:
            - `None` if the operation fails or is incomplete.
            - The `batch_id` of the uploaded mission if the operation is successful.
            - An `HttpResponse` object containing the status alert or form.
    """
    mission = core_models.Mission.objects.get(pk=mission_id)
    success = False

    # if the validation function returns a form then we should return that otherwise continue with the function
    if descriptor := _descriptor_form(trigger, mission.pk, mission.mission_descriptor):
        return success, descriptor

    # if the uploader name is missing, maybe because the user isn't logged into a database,
    # then we need to get an uploader name. Get the name from the database module first. If
    # it's not set get it from the session variable. If it's still not set return a form to
    # put it in a session variable
    uploader = form_biochem_database.get_uploader()
    if not uploader:
        uploader = request.session.get('uploader2', None)

        if uploader is None:
            return success, _uploader_form(trigger, mission.pk)

    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Initializing...")
    if not msg_alert.is_socket_connected(logger_name):
        msg_alert.set_socket(logger_name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = trigger
        return success, response

    msg_alert.include_close_button()
    try:
        if not batch_func:
            raise NotImplementedError("Batch function is not implemented.")

        # are we connected?
        if not form_biochem_database.is_connected():
            raise DatabaseError(f"No Database Connection")

        batch_id = get_mission_batch_id()
        batch = biochem_models.Bcbatches.objects.using('biochem').get_or_create(
            name=mission.mission_descriptor, username=uploader, batch_seq=batch_id)[0]

        batch_func(mission, uploader, batch)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")
        success = batch_id
    except IOError as ex:
        # the file was locked
        msg_alert.set_message(_("The requested file may be open and must be closed before updating."))
        msg_alert.get_message_container().append(err_div:=msg_alert.new_tag("div"))
        err_div.string = str(ex)

        msg_alert.set_type("danger")

        logger.exception(ex)
    except Exception as ex:
        msg_alert.set_message(f"Failed: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    return success, HttpResponse(msg_alert)


def download_batch(request, mission_id, logger_name, download_batch_func=None):
    trigger = "download_mission_bcs_bcd"
    return deal_with_batch(request, trigger, mission_id, logger_name, batch_func=download_batch_func)[1]


def upload_batch(request, mission_id, logger_name, upload_batch_func=None):
    trigger = "upload_mission_bcs_bcd"
    response_obj = deal_with_batch(request, trigger, mission_id, logger_name, batch_func=upload_batch_func)
    if response_obj[0]:
        # if response_obj[0] is not none, then I expect it to be the batch_id, which we'll add to the session
        # so when the form is reloaded it can be the selected batch. Then the function that reloads the
        # card header should clear the session variable.
        request.session['batch_id'] = response_obj[0]
        response_obj[1]['HX-Trigger-After-Settle'] = "reload_batch"
        return response_obj[1]
    else:
        return response_obj[1]


def delete_batch(mission_id, batch_id, label):
    unlock = False
    bcmission_edits = biochem_models.Bcmissionedits.objects.using('biochem').filter(batch_id=batch_id)
    if bcmission_edits.exists():
        try:
            bc_mission = bcmission_edits.first().mission
            unlock = bc_mission.locked_missions if hasattr(bc_mission, 'locked_missions') else None
        except biochem_models.Bcmissions.DoesNotExist:
            # There are no existing missions checked out so no locks to release after
            unlock = None

    response = None
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Deleteing Batch {batch_id}")
        func_area_par = "DH" if label.upper()=="DISCRETE" else "PL"
        try:
            response = cur.callproc("ARCHIVE_BATCH.DISABLE_EDITS_BDR_TRIGGERS", [func_area_par])
            response = cur.callproc("DELETES_PKG.DELETE_ARCHIVE_DELETES", [batch_id])
            response = cur.callproc("DELETES_PKG.DELETE_EDITS_DELETES", [batch_id])
            response = cur.callproc("DELETES_PKG.DELETE_EDITS_DELETES", [batch_id])
            biochem_models.Bcbatches.objects.using('biochem').filter(batch_seq=batch_id).delete()
        finally:
            response = cur.callproc("ARCHIVE_BATCH.ENABLE_EDITS_BDR_TRIGGERS", [func_area_par])

    if unlock:
        unlock.delete()


def checkout_existing_mission(mission: biochem_models.Bcmissionedits, label, header_model, oracle_proc) -> biochem_models.Bcmissions | None:
    return_status = ''
    return_value = ''
    data_pointer_code = "DH" if label == 'DISCRETE' else "PL"

    # if the mission doesn't have discrete headers, then it doesn't belong here in form_biochem_discrete
    headers = header_model.objects.using('biochem').filter(event__mission__descriptor__iexact=mission.descriptor)

    if headers.exists():
        bc_mission = headers.first().event.mission
        mission_seq = bc_mission.mission_seq

        # Check if the mission with the mission_seq is already checked out to the users edit tables
        user_missions = biochem_models.Bcmissionedits.objects.using('biochem').filter(mission=bc_mission)
        if not user_missions.exists():
            # If not checked out, check if the mission with mission_seq is in the BCLockedMissions table
            # If in the locked missions table and not in the users table we shouldn't be deleting or overriding
            if hasattr(bc_mission, 'locked_missions'):
                msg = f"'{bc_mission.locked_missions.downloaded_by}' " + _("already has this mission checked out. "
                                                                           "Mission needs to be released from BCLockedMissions before it can be modified.")
                raise PermissionError(msg)

            # Todo: There's also a case where there could be multiple versions of a mission in the Archive.
            #       In this case I only retrieve the first mission that matches the mission.mission_descriptor,
            #       but I don't think this is the right thing to do, I'll need to ask.
            # Todo:
            #       years later and I still really don't have an answer to this. It really only happens for legacy
            #       missions uploaded by a specific person. Most of the time missions have one discreate entry
            #       and one plankton entry, and that's it.
            # check it out to the edit tables.
            with connections['biochem'].cursor() as cur:
                user_logger.info(f"Downloading existing mission to edit tables with matching descriptor {mission_seq}")
                return_value = cur.callproc(oracle_proc, [mission_seq, return_status])

            if return_value[1] is None:
                biochem_models.Bclockedmissions.objects.using('biochem').create(
                    mission=bc_mission,
                    mission_name=bc_mission.name,
                    descriptor=bc_mission.descriptor,
                    data_pointer_code=data_pointer_code,  # reference to BCDataPointers table - "DH" for discrete, "PL" for plankton
                    downloaded_by=form_biochem_database.get_uploader(),
                    downloaded_date=datetime.now()).save(using='biochem')
                return bc_mission
        else:
            return user_missions.first().mission

    return None


def get_batch_list(request, mission_id, form_class: Type[BiochemDBBatchForm]) -> HttpResponse:
    if batch_id := request.session.get('batch_id', None):
        # If the batch_id is set in the session variable use it as the initial selection, then
        # clear the session variable after it's been used.
        form = form_class(mission_id=mission_id, initial={'batch_selection': batch_id})
        del request.session['batch_id']
        request.session.modified = True
    else:
        form = form_class(mission_id=mission_id, initial=request.GET)

    html = render_crispy_form(form)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup.find(id=form.get_id_builder().get_card_header_id()))


def get_update_controls(request, mission_id, form_class: Type[BiochemDBBatchForm]) -> HttpResponse:
    form: BiochemDBBatchForm = form_class(mission_id=mission_id, collapsed=False, initial=request.GET)

    html = render_crispy_form(form)

    return HttpResponse(html)


def stage_1_validation(request, mission_id, batch_id, logger_name, batch_func=None) -> HttpResponse:
    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Preparing to validate...")
    if not msg_alert.is_socket_connected(logger_name):
        msg_alert.set_socket(logger_name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = "run_stage1_validation"
        return response

    msg_alert.include_close_button()
    try:
        if not batch_func:
            raise NotImplementedError("Batch function is not implemented.")

        batch_func(mission_id, batch_id)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")

    except ValidationError as ex:
        msg_alert.set_message(f"Failed Stage 1 validation: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    except Exception as ex:
        msg_alert.set_message(f"Failed: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    response = HttpResponse(msg_alert)
    response['HX-Trigger-After-Settle'] = "batch_updated"
    return response


def stage_2_validation(request, mission_id, batch_id, logger_name, batch_func=None) -> HttpResponse:
    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Preparing to validate...")
    if not msg_alert.is_socket_connected(logger_name):
        msg_alert.set_socket(logger_name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = "run_stage2_validation"
        return response

    msg_alert.include_close_button()
    try:
        if not batch_func:
            raise NotImplementedError("Batch function is not implemented.")

        batch_func(mission_id, batch_id)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")

    except ValidationError as ex:
        msg_alert.set_message(f"Failed Stage 2 validation: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    except Exception as ex:
        msg_alert.set_message(f"Failed: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    response = HttpResponse(msg_alert)
    response['HX-Trigger-After-Settle'] = "batch_updated"
    return response


def delete_selected_batch(request, mission_id, batch_id, logger_name, batch_func=None) -> HttpResponse:
    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Preparing to delete selected batch...")
    if not msg_alert.is_socket_connected(logger_name):
        msg_alert.set_socket(logger_name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = "delete_selected_batch"
        return response

    msg_alert.include_close_button()
    try:
        if not batch_func:
            raise NotImplementedError("Batch function is not implemented.")

        batch_func(mission_id, batch_id)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")

    except ValidationError as ex:
        msg_alert.set_message(f"Failed to delete batch: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    except Exception as ex:
        msg_alert.set_message(f"Failed: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    response = HttpResponse(msg_alert)
    response['HX-Trigger-After-Settle'] = "reload_batch"
    return response


def checkin_mission(mission_id: int, batch_id: int, label: str, header_model,
                    oracle_checkout_proc: str, oracle_archive_proc: str, delete_batch_func: Callable):
    return_status = ''
    return_value = ''

    # check for existing mission matching this batch and check it out to the user edit tables if it exists
    # This is to create a backup which the user can then recover from if something goes wrong.
    batch = biochem_models.Bcbatches.objects.using('biochem').get(batch_seq=batch_id)
    batch_mission_edit = batch.mission_edits.first()

    bc_mission: biochem_models.Bcmissions = checkout_existing_mission(
        mission=batch_mission_edit,
        label=label,
        header_model=header_model,
        oracle_proc=oracle_checkout_proc
    )

    # if the **batch_mission_edit** mission has a mission_seq it needs to be archived using the
    # REARCHIVE_DISCRETE_MISSION function. Otherwise, the cursor will return without errors, but won't actually have
    # done anything ( -_-), seriously...
    # if batch_mission_edit.mission_id is not None:
    #     stage2_validation_func(batch_mission_edit.mission_id, batch_id)

    # check in new mission
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Uploading new mission with batch id {batch_id}")
        return_value = cur.callproc(oracle_archive_proc, [batch_id, return_status])

    # if the checkin fails release the old mission and delete it from the edit tables
    # if successful delete the new mission from the edit tables, but keep the old one.
    try:
        if return_value[1] is not None:
            raise ValueError(return_value[1])

        # confirm the replacement mission was uploaded, this will throw a DoesNotExist exception if the mission doesn't
        # exist in Biochem
        if batch_mission_edit.mission_id is not None:
            biochem_models.Bcmissions.objects.using('biochem').get(mission_seq=batch_mission_edit.mission_id)
        elif bc_mission:
            biochem_models.Bcmissions.objects.using('biochem').exclude(mission_seq=bc_mission.mission_seq).get(
                descriptor=batch_mission_edit.descriptor, created_date=batch_mission_edit.created_date)

        # if the mission exists in the lock tables and there was no problem archiving it,
        # then remove it from the locked table
        if bc_mission and bc_mission.locked_missions:
            bc_mission.delete()

        delete_batch_func(mission_id, batch_id)
    except biochem_models.Bcmissions.DoesNotExist as ex:
        user_logger.error(f"Issues with archiving mission: {return_value[1]}")

        if bc_mission and bc_mission.locked_missions:
            old_batch_id = biochem_models.Bcmissionedits.objects.using('biochem').filter(
                mission_edt_seq=bc_mission.mission_seq).first().batch.batch_seq
            delete_batch_func(mission_id, old_batch_id)
            bc_mission.locked_missions.delete()

        raise DatabaseError("Could not check in new mission")


def checkin_batch(request, mission_id: int, batch_id: int, logger_name: str, batch_func: Callable) -> HttpResponse:
    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Preparing to checkin...")
    if not msg_alert.is_socket_connected(logger_name):
        msg_alert.set_socket(logger_name)
        msg_alert.include_progress_bar()
        response = HttpResponse(msg_alert)
        response['HX-Trigger-After-Settle'] = "checkin_selected_batch"
        return response

    msg_alert.include_close_button()
    try:
        if not batch_func:
            raise NotImplementedError("Batch function is not implemented.")

        batch_func(mission_id, batch_id)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")

    except ValidationError as ex:
        msg_alert.set_message(f"Failed to check-in batch: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    except Exception as ex:
        msg_alert.set_message(f"Failed: {str(ex)}")
        msg_alert.set_type("danger")

        logger.exception(ex)

    response = HttpResponse(msg_alert)
    response['HX-Trigger-After-Settle'] = "reload_batch"
    return response


def get_batch_summary_soup(soup, mission_id, batch_id):
    context = {}

    errors = biochem_models.Bcerrors.objects.using('biochem').filter(batch_id=batch_id)
    context['errors'] = errors

    table_names = errors.values_list('edit_table_name', flat=True).distinct()
    table_models = {}
    for model in apps.get_models():
        if model._meta.db_table in table_names:
            table_models[model._meta.db_table] = model

    def process_attrs(error_set, table_columns):
        attrs = []
        for column in table_columns:
            if isinstance(column, models.ForeignKey):
                if column.related_model == biochem_models.Bcdatatypes:
                    attrs.append({
                        "value": getattr(error_set, column.name + '_id'),
                        "info": getattr(error_set, column.name).method
                    })  # Get the datatype name for Bcdatatypes foreign key
                else:
                    attrs.append({"value": getattr(error_set, column.name + '_id')})  # Get the primary key for other foreign keys  # Get the primary key for foreign keys
            else:
                attrs.append({"value": getattr(error_set, column.name)})  # Get the value for non-foreign key fields

        return attrs

    for model_name in table_names:
        table_model = table_models[model_name]
        row_errors  = errors.filter(edit_table_name=model_name).order_by('record_num_seq').values_list('record_num_seq', flat=True).distinct()

        context['table_name'] = table_model._meta.db_table
        context['table_columns'] = [field for field in table_model._meta.get_fields()]
        context['error_rows'] = [process_attrs(elm, context['table_columns']) for elm in table_model.objects.using('biochem').filter(pk__in=row_errors)]

        table_html = render_to_string('core/partials/table_dynamic.html', context)
        soup_table = BeautifulSoup(table_html, "html.parser")
        soup.append(soup_table)

    return soup


def get_batch_summary(request, mission_id, batch_id):
    if batch_id <= 0:
        return HttpResponse()

    soup = BeautifulSoup("", 'html.parser')
    get_batch_summary_soup(soup, mission_id, batch_id)

    return HttpResponse(soup)


def get_batch_errors(request, mission_id, batch_id):
    context = {}

    if batch_id <= 0:
        return HttpResponse()

    soup = BeautifulSoup("", 'html.parser')

    errors = biochem_models.Bcerrors.objects.using('biochem').filter(batch_id=batch_id).order_by('record_num_seq')
    context['errors'] = errors

    # for errors, the edit_table_name tells us what table has problems and record_num_seq will tells us the
    # primary key of the row with issues.

    table_html = render_to_string('core/partials/table_biochem_batch_errors.html', context)
    soup.append(BeautifulSoup(table_html, 'html.parser'))
    get_batch_summary_soup(soup, mission_id, batch_id)

    return HttpResponse(soup)


prefix = 'biochem/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/set_descriptor/', set_descriptor, name="form_biochem_batch_mission_descriptor"),
    path(f'<int:mission_id>/{prefix}/set_uploader/', set_uploader, name="form_biochem_batch_uploader"),
    path(f'<int:mission_id>/{prefix}/batch_errors/<int:batch_id>/', get_batch_errors, name="form_biochem_batch_batch_errors"),
]
