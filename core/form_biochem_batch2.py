import csv
import os

from typing import Tuple, Type

from bs4 import BeautifulSoup
from crispy_forms.bootstrap import StrictButton
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Row, Layout, Field, Div
from crispy_forms.utils import render_crispy_form

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import OperationalError, connections

from django.http import HttpResponse
from django.urls import path, reverse_lazy
from django.utils.connection import ConnectionDoesNotExist
from django.utils.translation import gettext as _

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

    def get_download_url(self):
        raise NotImplementedError("The button url has not been implemented")

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

    def get_upload_url(self):
        raise NotImplementedError("The upload button url has not been implemented")

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

    def get_batch_id(self) -> None | int:
        batch_id = self.initial.get("batch_selection", "")
        return int(batch_id) if batch_id else None

    # if validation hasn't been run return None.
    # if validation has been run and is invalid return False
    # if validation has been run and is valid return True
    def is_batch_stage1_validated(self) -> bool | None:
        raise NotImplementedError

    # return None if conditions for validation aren't met, return the URL otherwise
    def get_stage1_validate_url(self) -> str | None:
        raise NotImplementedError

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
        raise NotImplementedError

    # return None if conditions for validation aren't met, return the URL otherwise
    def get_stage2_validate_url(self) -> str | None:
        raise NotImplementedError

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

    # return None if conditions for delete aren't met, return the URL otherwise
    def get_delete_batch_url(self) -> str | None:
        raise NotImplementedError

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
        url = "/test/"
        attrs = {
            'title': _("Check-in Mission to Archive"),
            'hx-target': f'#{BIOCHEM_BATCH_CONTROL_ROW_ID}',
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

    def get_batch_update_url(self) -> str:
        raise NotImplementedError

    def get_batch_selection(self):

        url = self.get_batch_update_url()
        batch_select_attributes = {
            'id': BIOCHEM_BATCH_SELECTION_ID,
            'hx-target': f'#{BIOCHEM_BATCH_CONTROL_ROW_ID}',
            # biochem_db_connect is fired by the form_biochem_database module when connecting or disconnecting from a DB
            'hx-trigger': "change, batch_updated from:body",
            'hx-get': url
        }

        return Field('batch_selection', css_class="form-select form-select-sm",
                     template=self.field_template, wrapper_class="col-auto", **batch_select_attributes)

    def get_header_update_url(self):
        raise NotImplementedError("The url to update the cards header has not been implemented")

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


def write_bcs_file(rows, bcs_file, report_model):
    # because we're not passing in a link to a database for the bcs_d_model there will be no updated rows or fields
    # only the objects being created will be returned.

    bcs_headers = [field.name for field in report_model._meta.fields]

    with open(bcs_file, 'w', newline='', encoding="UTF8") as f:

        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(bcs_headers)

        for idx, bcs_row in enumerate(rows):
            row = [getattr(bcs_row, header, '') for header in bcs_headers]
            writer.writerow(row)


def write_bcd_file(rows, bcd_file, report_model):
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


def deal_with_batch(request, trigger, mission_id, logger_name, batch_func=None) -> Tuple[bool, HttpResponse]:
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

    msg_alert = core_forms.StatusAlert(BIOCHEM_BATCH_STATUS_ALERT, "Downloading...")
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

        batch_func(mission, uploader)

        msg_alert.set_message("Success")
        msg_alert.set_type("success")
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
        response_obj[1]['HX-Trigger-After-Settle'] = "reload_batch"
        return response_obj[1]
    else:
        return response_obj[1]


def delete_batch(mission_id, batch_id, label, bcd_model, bcs_model):
    unlock = False
    bcmission_edits = biochem_models.Bcmissionedits.objects.using('biochem').filter(batch_id=batch_id)
    if bcmission_edits.exists() and hasattr(bcmission_edits.first(), 'mission'):
        bc_mission = bcmission_edits.first().mission
        unlock = bc_mission.locked_missions if hasattr(bc_mission, 'locked_missions') else None

    response = None
    with connections['biochem'].cursor() as cur:
        user_logger.info(f"Deleteing Batch {batch_id}")
        response = cur.callproc("DELETES_PKG.DELETE_ARCHIVE_DELETES", [batch_id])
        response = cur.callproc("DELETES_PKG.DELETE_EDITS_DELETES", [batch_id])
        response = cur.callproc("ARCHIVE_BATCH.DELETE_BATCH", [batch_id, label])

    bcd_model.objects.using('biochem').filter(batch=batch_id).delete()
    bcs_model.objects.using('biochem').filter(batch=batch_id).delete()
    if unlock:
        unlock.delete()


def get_batch_list(request, mission_id, form_class: Type[BiochemDBBatchForm]) -> HttpResponse:
    form = form_class(mission_id=mission_id, initial=request.GET)
    html = render_crispy_form(form)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup.find(id=form.get_id_builder().get_card_header_id()))


def get_update_controls(request, mission_id, form_class: Type[BiochemDBBatchForm]) -> HttpResponse:
    form = form_class(mission_id=mission_id, initial=request.GET)
    html = render_crispy_form(form)
    soup = BeautifulSoup(html, 'html.parser')

    return HttpResponse(soup.find(id=BIOCHEM_BATCH_CONTROL_ROW_ID))


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


prefix = 'biochem/batch'
url_patterns = [
    path(f'<int:mission_id>/{prefix}/set_descriptor/', set_descriptor, name="form_biochem_batch_mission_descriptor"),
    path(f'<int:mission_id>/{prefix}/set_uploader/', set_uploader, name="form_biochem_batch_uploader"),
]
